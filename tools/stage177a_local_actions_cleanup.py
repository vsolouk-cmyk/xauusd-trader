#!/usr/bin/env python3
from __future__ import annotations

import argparse
import getpass
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

API_ROOT = "https://api.github.com"
API_HOST = "api.github.com"
API_VERSION = "2022-11-28"
CONFIRMATION = "DELETE_ALL_XAUUSD_ACTIONS_STORAGE"


def run(cmd: list[str], *, check: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        text=True,
        capture_output=True,
        check=check,
    )


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return run(["git", *args], check=check)


def repo_from_origin() -> tuple[str, str]:
    try:
        remote = git("remote", "get-url", "origin").stdout.strip()
    except Exception as exc:
        raise RuntimeError("Run this script inside the repository.") from exc

    patterns = [
        r"^git@github\.com:([^/]+)/(.+?)(?:\.git)?$",
        r"^ssh://git@github\.com/([^/]+)/(.+?)(?:\.git)?$",
        r"^https?://github\.com/([^/]+)/(.+?)(?:\.git)?$",
    ]
    for pattern in patterns:
        match = re.match(pattern, remote)
        if match:
            return match.group(1), match.group(2)
    raise RuntimeError(f"Unsupported GitHub origin URL: {remote}")


def dns_preflight() -> dict[str, Any]:
    result: dict[str, Any] = {
        "host": API_HOST,
        "python_resolution": "FAIL",
        "addresses": [],
        "curl_resolution": "NOT_RUN",
        "curl_detail": "",
    }

    try:
        records = socket.getaddrinfo(API_HOST, 443, type=socket.SOCK_STREAM)
        addresses = sorted({record[4][0] for record in records})
        result["python_resolution"] = "PASS"
        result["addresses"] = addresses
    except socket.gaierror as exc:
        result["python_error"] = f"{type(exc).__name__}: {exc}"

    curl = shutil.which("curl")
    if not curl:
        result["curl_resolution"] = "CURL_NOT_FOUND"
        return result

    probe = run(
        [
            curl,
            "--silent",
            "--show-error",
            "--location",
            "--connect-timeout",
            "15",
            "--max-time",
            "30",
            "--output",
            "/dev/null",
            "--write-out",
            "%{http_code}",
            f"{API_ROOT}/rate_limit",
        ]
    )
    result["curl_exit_code"] = probe.returncode
    result["curl_http_code"] = probe.stdout.strip()
    result["curl_detail"] = probe.stderr.strip()

    if probe.returncode == 0 and probe.stdout.strip().isdigit():
        result["curl_resolution"] = "PASS"
    elif "Could not resolve host" in probe.stderr:
        result["curl_resolution"] = "DNS_FAIL"
    else:
        result["curl_resolution"] = "NETWORK_FAIL"

    return result


class CurlAPI:
    def __init__(self, token: str):
        curl = shutil.which("curl")
        if not curl:
            raise RuntimeError("curl was not found on this Mac.")
        self.curl = curl
        self.token = token

    def call(self, method: str, path: str, expected=(200,)):
        url = API_ROOT + path
        command = [
            self.curl,
            "--silent",
            "--show-error",
            "--location",
            "--connect-timeout",
            "20",
            "--max-time",
            "60",
            "--request",
            method,
            "--header",
            "Accept: application/vnd.github+json",
            "--header",
            f"Authorization: Bearer {self.token}",
            "--header",
            f"X-GitHub-Api-Version: {API_VERSION}",
            "--header",
            "User-Agent: xauusd-stage177a-local-cleanup",
            "--output",
            "-",
            "--write-out",
            "\n__HTTP_STATUS__:%{http_code}",
            url,
        ]
        result = run(command)
        if result.returncode != 0:
            detail = result.stderr.strip()
            if "Could not resolve host" in detail:
                raise RuntimeError(
                    f"DNS resolution failed for {API_HOST}. curl detail: {detail}"
                )
            raise RuntimeError(
                f"curl failed for {method} {path}, exit={result.returncode}: {detail}"
            )

        marker = "\n__HTTP_STATUS__:"
        if marker not in result.stdout:
            raise RuntimeError(f"Could not parse GitHub response for {method} {path}")

        body, status_text = result.stdout.rsplit(marker, 1)
        try:
            status = int(status_text.strip())
        except ValueError as exc:
            raise RuntimeError(
                f"Invalid HTTP status from GitHub: {status_text!r}"
            ) from exc

        if status not in expected:
            raise RuntimeError(
                f"{method} {path} -> HTTP {status}: {body.strip()}"
            )

        if not body.strip():
            return None
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            return body

    def paged(self, path: str, key: str):
        page = 1
        items = []
        while True:
            separator = "&" if "?" in path else "?"
            payload = self.call(
                "GET", f"{path}{separator}per_page=100&page={page}"
            )
            batch = payload.get(key, [])
            if not isinstance(batch, list):
                raise RuntimeError(f"Unexpected API payload for key {key!r}")
            items.extend(batch)
            if len(batch) < 100:
                return items
            page += 1


def human_size(value: int) -> str:
    size = float(value)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if size < 1024 or unit == "TiB":
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{value} B"


def branch_exists() -> bool:
    result = git(
        "ls-remote",
        "--exit-code",
        "--heads",
        "origin",
        "automation/gdelt-latest",
        check=False,
    )
    return result.returncode == 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Delete GitHub Actions storage locally through the REST API."
    )
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm", default="")
    parser.add_argument("--purge-caches", action="store_true")
    parser.add_argument("--delete-gdelt-branch", action="store_true")
    parser.add_argument(
        "--network-check-only",
        action="store_true",
        help="Only test DNS and HTTPS access to api.github.com.",
    )
    args = parser.parse_args()

    preflight = dns_preflight()
    print(json.dumps(preflight, indent=2))

    if args.network_check_only:
        return 0 if preflight["curl_resolution"] == "PASS" else 2

    if preflight["curl_resolution"] != "PASS":
        print(
            "\nNetwork preflight failed before authentication. "
            "Fix DNS/VPN access to api.github.com first.",
            file=sys.stderr,
        )
        return 2

    if args.execute and args.confirm != CONFIRMATION:
        print(
            f"Refusing destructive run. Use --confirm {CONFIRMATION}",
            file=sys.stderr,
        )
        return 2

    owner, repo = repo_from_origin()
    token = os.getenv("GITHUB_TOKEN", "").strip()
    if not token:
        token = getpass.getpass("GitHub token (hidden): ").strip()
    if not token:
        print("No token supplied.", file=sys.stderr)
        return 2

    api = CurlAPI(token)
    print(f"Repository: {owner}/{repo}")
    print(f"Mode: {'EXECUTE' if args.execute else 'DRY RUN'}")

    artifacts = api.paged(
        f"/repos/{owner}/{repo}/actions/artifacts", "artifacts"
    )
    artifact_bytes = sum(int(x.get("size_in_bytes") or 0) for x in artifacts)
    print(
        f"Artifacts: {len(artifacts)} | reported size: "
        f"{human_size(artifact_bytes)}"
    )

    caches = []
    cache_bytes = 0
    if args.purge_caches:
        caches = api.paged(
            f"/repos/{owner}/{repo}/actions/caches", "actions_caches"
        )
        cache_bytes = sum(int(x.get("size_in_bytes") or 0) for x in caches)
        print(
            f"Caches: {len(caches)} | reported size: "
            f"{human_size(cache_bytes)}"
        )

    gdelt_present = False
    if args.delete_gdelt_branch:
        gdelt_present = branch_exists()
        print(f"GDELT snapshot branch exists: {gdelt_present}")

    if not args.execute:
        print("\nDry run complete. Nothing was deleted.")
        return 0

    errors = []
    artifacts_deleted = 0
    for i, item in enumerate(artifacts, start=1):
        try:
            api.call(
                "DELETE",
                f"/repos/{owner}/{repo}/actions/artifacts/{item['id']}",
                expected=(204,),
            )
            artifacts_deleted += 1
            print(f"[artifact {i}/{len(artifacts)}] deleted: {item.get('name')}")
        except Exception as exc:
            errors.append(str(exc))
            print(f"[artifact {i}] ERROR: {exc}", file=sys.stderr)
        time.sleep(0.05)

    caches_deleted = 0
    if args.purge_caches:
        for i, item in enumerate(caches, start=1):
            try:
                api.call(
                    "DELETE",
                    f"/repos/{owner}/{repo}/actions/caches/{item['id']}",
                    expected=(204,),
                )
                caches_deleted += 1
                print(f"[cache {i}/{len(caches)}] deleted: {item.get('key')}")
            except Exception as exc:
                errors.append(str(exc))
                print(f"[cache {i}] ERROR: {exc}", file=sys.stderr)
            time.sleep(0.05)

    gdelt_deleted = False
    if args.delete_gdelt_branch and gdelt_present:
        result = git(
            "push",
            "origin",
            "--delete",
            "automation/gdelt-latest",
            check=False,
        )
        gdelt_deleted = result.returncode == 0
        if not gdelt_deleted:
            errors.append((result.stderr or result.stdout).strip())

    summary = {
        "repository": f"{owner}/{repo}",
        "network_preflight": preflight,
        "artifacts_found": len(artifacts),
        "artifacts_deleted": artifacts_deleted,
        "artifact_bytes_reported": artifact_bytes,
        "caches_found": len(caches),
        "caches_deleted": caches_deleted,
        "cache_bytes_reported": cache_bytes,
        "gdelt_branch_present": gdelt_present,
        "gdelt_branch_deleted": gdelt_deleted,
        "errors": errors,
    }
    out = Path("reports/stage177a_local_actions_cleanup_summary.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"\nSummary: {out}")

    if errors:
        print(f"Completed with {len(errors)} error(s).", file=sys.stderr)
        return 1

    print("Cleanup completed successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
