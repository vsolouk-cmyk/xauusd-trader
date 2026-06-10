#!/usr/bin/env python3
"""
Stage 10B GDELT Probe

Purpose:
- Diagnose whether GitHub Actions can fetch GDELT DOC API results.
- This script does not change event pipeline data.
- It writes a small report and CSV with per-query status.

Hard rules:
- Diagnostics only.
- No trading signal.
- No EA/order/demo/paper/live authorization.
"""

from __future__ import annotations

import argparse
import csv
import json
import ssl
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict


TOOL_VERSION = "v1"
DEFAULT_OUT_DIR = Path("data/reports/stage10b_gdelt_probe")


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def build_ssl_context(ssl_mode: str):
    if ssl_mode == "insecure":
        return ssl._create_unverified_context()
    if ssl_mode == "certifi":
        try:
            import certifi  # type: ignore
            return ssl.create_default_context(cafile=certifi.where())
        except Exception:
            return None
    return None


def fetch_json(url: str, timeout: int, ssl_mode: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "xauusd-trader-gdelt-probe/1.0"})
    ctx = build_ssl_context(ssl_mode)
    if ctx is None:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
        return json.loads(resp.read().decode("utf-8"))


def write_csv(path: Path, rows: List[Dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    cols = list(rows[0].keys()) if rows else ["empty"]
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def run(out_dir: Path, timespan: str, max_records: int, timeout: int, retries: int, ssl_mode: str) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    generated = now_iso()

    queries = [
        "gold",
        "XAUUSD",
        "gold dollar",
        "gold yields",
        "gold federal reserve",
        "gold Iran Israel",
        "gold oil",
        "gold central bank",
    ]

    statuses = []
    total_articles = 0
    sample_articles = []

    for q in queries:
        params = {
            "query": q,
            "mode": "ArtList",
            "format": "json",
            "maxrecords": str(max_records),
            "timespan": timespan,
            "sort": "HybridRel",
        }
        url = "https://api.gdeltproject.org/api/v2/doc/doc?" + urllib.parse.urlencode(params)
        data = None
        last_error = ""

        for attempt in range(1, retries + 2):
            try:
                data = fetch_json(url, timeout=timeout, ssl_mode=ssl_mode)
                last_error = ""
                break
            except Exception as e:
                last_error = f"{type(e).__name__}: {e}"
                if attempt <= retries:
                    time.sleep(min(5, 2 * attempt))

        if data is None:
            statuses.append({
                "query": q,
                "status": "error",
                "articles": 0,
                "error": last_error,
                "url": url,
            })
            continue

        articles = data.get("articles", []) if isinstance(data, dict) else []
        total_articles += len(articles)
        statuses.append({
            "query": q,
            "status": "ok",
            "articles": len(articles),
            "error": "",
            "url": url,
        })

        for a in articles[:5]:
            sample_articles.append({
                "query": q,
                "seen_date": a.get("seendate") or a.get("seenDate") or "",
                "domain": a.get("domain") or "",
                "title": (a.get("title") or "").replace("\n", " ")[:240],
                "url": a.get("url") or "",
            })

    status = "ok" if total_articles > 0 else "no_articles_or_errors"

    write_csv(out_dir / "gdelt_probe_query_status.csv", statuses)
    write_csv(out_dir / "gdelt_probe_sample_articles.csv", sample_articles)

    payload = {
        "tool_version": TOOL_VERSION,
        "generated_utc": generated,
        "status": status,
        "timespan": timespan,
        "max_records": max_records,
        "timeout": timeout,
        "retries": retries,
        "ssl_mode": ssl_mode,
        "query_count": len(queries),
        "total_articles": total_articles,
        "statuses": statuses,
        "sample_articles": sample_articles[:40],
    }
    (out_dir / "gdelt_probe.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [
        "# Stage 10B GDELT Probe",
        "",
        f"Generated UTC: `{generated}`",
        f"Tool version: `{TOOL_VERSION}`",
        "",
        "> Diagnostics only. No trading authorization.",
        "",
        "## Status",
        f"- status: `{status}`",
        f"- total_articles: `{total_articles}`",
        f"- timespan: `{timespan}`",
        f"- max_records: `{max_records}`",
        f"- timeout: `{timeout}`",
        f"- retries: `{retries}`",
        "",
        "## Query status",
        "| Query | Status | Articles | Error |",
        "|---|---|---:|---|",
    ]
    for r in statuses:
        err = str(r["error"]).replace("|", "/")[:160]
        lines.append(f"| {r['query']} | {r['status']} | {r['articles']} | {err} |")

    lines += [
        "",
        "## Sample articles",
        "| Query | Seen date | Domain | Title |",
        "|---|---|---|---|",
    ]
    if sample_articles:
        for a in sample_articles[:30]:
            title = (a["title"] or "").replace("|", "/")[:160]
            lines.append(f"| {a['query']} | {a['seen_date']} | {a['domain']} | {title} |")
    else:
        lines.append("| none | none | none | none |")

    lines += [
        "",
        "## Interpretation",
        "- If GitHub shows `total_articles > 0`, GDELT works in GitHub and Stage 10B query logic should be improved/merged.",
        "- If GitHub also shows errors/timeouts, the problem is not only the MacBook.",
        "- If GitHub shows status ok but articles=0, query/timespan is the issue.",
    ]
    (out_dir / "gdelt_probe.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("Stage 10B GDELT probe: DONE")
    print(f"status={status} total_articles={total_articles} report={out_dir / 'gdelt_probe.md'}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    p.add_argument("--timespan", default="7d")
    p.add_argument("--max-records", type=int, default=10)
    p.add_argument("--timeout", type=int, default=60)
    p.add_argument("--retries", type=int, default=2)
    p.add_argument("--ssl-mode", default="default", choices=["default", "certifi", "insecure"])
    args = p.parse_args()
    return run(Path(args.out_dir), args.timespan, args.max_records, args.timeout, args.retries, args.ssl_mode)


if __name__ == "__main__":
    raise SystemExit(main())
