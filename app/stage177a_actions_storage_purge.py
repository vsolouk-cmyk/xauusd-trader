#!/usr/bin/env python3
"""One-time GitHub Actions storage purge for the current repository.

Deletes workflow artifacts and optional Actions caches through the official REST API.
Optionally deletes the obsolete GDELT snapshot branch. Designed for workflow_dispatch
with an explicitly scoped GITHUB_TOKEN.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, asdict
from typing import Any, Iterable

API_VERSION = "2026-03-10"
ACCEPT = "application/vnd.github+json"


@dataclass
class PurgeStats:
    artifacts_found: int = 0
    artifacts_deleted: int = 0
    artifact_bytes_found: int = 0
    caches_found: int = 0
    caches_deleted: int = 0
    cache_bytes_found: int = 0
    gdelt_branch_deleted: bool = False
    dry_run: bool = True
    errors: list[str] | None = None

    def __post_init__(self) -> None:
        if self.errors is None:
            self.errors = []


class GitHubAPI:
    def __init__(self, repository: str, token: str, api_url: str = "https://api.github.com") -> None:
        if "/" not in repository:
            raise ValueError("repository must be OWNER/REPO")
        if not token:
            raise ValueError("GitHub token is required")
        self.repository = repository
        self.token = token
        self.api_url = api_url.rstrip("/")

    def request(self, method: str, path: str, *, expected: Iterable[int] = (200,), retries: int = 4) -> Any:
        url = f"{self.api_url}{path}"
        last_error: Exception | None = None
        for attempt in range(1, retries + 1):
            req = urllib.request.Request(
                url,
                method=method,
                headers={
                    "Accept": ACCEPT,
                    "Authorization": f"Bearer {self.token}",
                    "X-GitHub-Api-Version": API_VERSION,
                    "User-Agent": "xauusd-stage177a-storage-purge",
                },
            )
            try:
                with urllib.request.urlopen(req, timeout=45) as response:
                    status = response.status
                    body = response.read()
                if status not in set(expected):
                    raise RuntimeError(f"Unexpected HTTP {status} for {method} {path}")
                if not body:
                    return None
                return json.loads(body.decode("utf-8"))
            except urllib.error.HTTPError as exc:
                if exc.code in set(expected):
                    return None
                if exc.code == 404:
                    raise FileNotFoundError(path) from exc
                last_error = exc
                retry_after = exc.headers.get("Retry-After") if exc.headers else None
                wait = float(retry_after) if retry_after and retry_after.isdigit() else min(2 ** attempt, 20)
                if exc.code not in (403, 429, 500, 502, 503, 504) or attempt == retries:
                    raise RuntimeError(f"GitHub API HTTP {exc.code}: {method} {path}") from exc
                print(f"[purge] transient HTTP {exc.code}; retry {attempt}/{retries} after {wait:.1f}s", flush=True)
                time.sleep(wait)
            except (urllib.error.URLError, TimeoutError) as exc:
                last_error = exc
                if attempt == retries:
                    raise RuntimeError(f"GitHub API request failed: {method} {path}: {exc}") from exc
                time.sleep(min(2 ** attempt, 20))
        raise RuntimeError(f"GitHub API request failed: {last_error}")

    def list_artifacts(self, page: int = 1) -> list[dict[str, Any]]:
        payload = self.request("GET", f"/repos/{self.repository}/actions/artifacts?per_page=100&page={page}")
        return list((payload or {}).get("artifacts", []))

    def list_caches(self, page: int = 1) -> list[dict[str, Any]]:
        payload = self.request("GET", f"/repos/{self.repository}/actions/caches?per_page=100&page={page}")
        return list((payload or {}).get("actions_caches", []))

    def delete_artifact(self, artifact_id: int) -> None:
        self.request("DELETE", f"/repos/{self.repository}/actions/artifacts/{artifact_id}", expected=(204,))

    def delete_cache(self, cache_id: int) -> None:
        self.request("DELETE", f"/repos/{self.repository}/actions/caches/{cache_id}", expected=(204,))

    def delete_branch(self, branch: str) -> bool:
        encoded = urllib.parse.quote(f"heads/{branch}", safe="/")
        try:
            self.request("DELETE", f"/repos/{self.repository}/git/refs/{encoded}", expected=(204,))
            return True
        except FileNotFoundError:
            return False


def _human_bytes(value: int) -> str:
    size = float(value)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if size < 1024 or unit == "TiB":
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{value} B"


def purge_artifacts(api: GitHubAPI, stats: PurgeStats, dry_run: bool) -> None:
    page = 1
    while True:
        # During destructive deletion, always re-read page 1 because the collection shrinks.
        artifacts = api.list_artifacts(page if dry_run else 1)
        if not artifacts:
            return
        stats.artifacts_found += len(artifacts)
        stats.artifact_bytes_found += sum(int(item.get("size_in_bytes") or 0) for item in artifacts)
        for item in artifacts:
            artifact_id = int(item["id"])
            name = str(item.get("name", ""))
            size = int(item.get("size_in_bytes") or 0)
            print(f"[purge][artifact] {'WOULD DELETE' if dry_run else 'DELETE'} id={artifact_id} size={_human_bytes(size)} name={name}", flush=True)
            if not dry_run:
                api.delete_artifact(artifact_id)
                stats.artifacts_deleted += 1
                time.sleep(0.10)
        if dry_run:
            page += 1


def purge_caches(api: GitHubAPI, stats: PurgeStats, dry_run: bool) -> None:
    page = 1
    while True:
        caches = api.list_caches(page if dry_run else 1)
        if not caches:
            return
        stats.caches_found += len(caches)
        stats.cache_bytes_found += sum(int(item.get("size_in_bytes") or 0) for item in caches)
        for item in caches:
            cache_id = int(item["id"])
            key = str(item.get("key", ""))
            size = int(item.get("size_in_bytes") or 0)
            print(f"[purge][cache] {'WOULD DELETE' if dry_run else 'DELETE'} id={cache_id} size={_human_bytes(size)} key={key}", flush=True)
            if not dry_run:
                api.delete_cache(cache_id)
                stats.caches_deleted += 1
                time.sleep(0.10)
        if dry_run:
            page += 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", default=os.getenv("GITHUB_REPOSITORY", ""))
    parser.add_argument("--token", default=os.getenv("GITHUB_TOKEN", ""))
    parser.add_argument("--confirmation", required=True)
    parser.add_argument("--dry-run", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--purge-caches", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--delete-gdelt-branch", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--summary-out", default="stage177a_storage_purge_summary.json")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    expected_confirmation = "PREVIEW" if args.dry_run else "DELETE_ALL_XAUUSD_ACTIONS_STORAGE"
    if args.confirmation != expected_confirmation:
        print(f"Refusing: confirmation must equal {expected_confirmation!r}", file=sys.stderr)
        return 2

    api = GitHubAPI(args.repository, args.token)
    stats = PurgeStats(dry_run=args.dry_run)
    try:
        purge_artifacts(api, stats, args.dry_run)
        if args.purge_caches:
            purge_caches(api, stats, args.dry_run)
        if args.delete_gdelt_branch:
            if args.dry_run:
                print("[purge][branch] WOULD DELETE automation/gdelt-latest", flush=True)
            else:
                stats.gdelt_branch_deleted = api.delete_branch("automation/gdelt-latest")
                print(f"[purge][branch] deleted={stats.gdelt_branch_deleted} branch=automation/gdelt-latest", flush=True)
    except Exception as exc:  # fail closed and preserve a machine-readable summary
        stats.errors.append(f"{type(exc).__name__}:{exc}")

    with open(args.summary_out, "w", encoding="utf-8") as handle:
        json.dump(asdict(stats), handle, indent=2, sort_keys=True)
        handle.write("\n")

    print(json.dumps(asdict(stats), indent=2, sort_keys=True), flush=True)
    return 0 if not stats.errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
