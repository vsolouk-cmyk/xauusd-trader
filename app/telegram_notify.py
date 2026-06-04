from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

import requests


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def latest_file(pattern: str) -> Optional[Path]:
    files = sorted(glob.glob(pattern), key=lambda p: Path(p).stat().st_mtime, reverse=True)
    return Path(files[0]) if files else None


def fmt_float(value: Any, digits: int = 4) -> str:
    if value is None:
        return "n/a"
    try:
        return f"{float(value):.{digits}f}"
    except Exception:
        return "n/a"


def fmt_pct(value: Any) -> str:
    if value is None:
        return "n/a"
    try:
        return f"{100.0 * float(value):.1f}%"
    except Exception:
        return "n/a"


def best_baseline(summary: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    items = summary.get("summaries", []) or []
    if not items:
        return None
    # Prefer candidate baselines; otherwise sort by total net.
    candidates = [x for x in items if x.get("candidate")]
    pool = candidates if candidates else items
    return sorted(pool, key=lambda x: float(x.get("total_net_usd", -10**18) or -10**18), reverse=True)[0]


def build_message(summary: Optional[Dict[str, Any]], status: str, run_url: str = "") -> str:
    lines = []
    lines.append("XAUUSD Research Update")
    lines.append(f"Stage: 2A Baseline Lab")
    lines.append(f"Workflow status: {status}")

    if summary:
        decision = summary.get("decision", {}) or {}
        lines.append(f"Decision: {decision.get('status', 'n/a')}")
        lines.append(f"Reason: {decision.get('reason', 'n/a')}")
        lines.append(f"Candidates: {decision.get('candidate_count', 0)}")

        top = best_baseline(summary)
        if top:
            lines.append("")
            lines.append("Top baseline snapshot:")
            lines.append(f"- name: {top.get('baseline', 'n/a')}")
            lines.append(f"- trades: {top.get('trade_count', 'n/a')}")
            lines.append(f"- candidate: {top.get('candidate', 'n/a')}")
            lines.append(f"- win rate: {fmt_pct(top.get('win_rate'))}")
            lines.append(f"- avg net USD: {fmt_float(top.get('avg_net_usd'))}")
            lines.append(f"- total net USD: {fmt_float(top.get('total_net_usd'))}")
            lines.append(f"- max DD USD: {fmt_float(top.get('max_drawdown_usd'))}")

        cost = summary.get("cost_model", {}) or {}
        if cost:
            lines.append("")
            lines.append("Cost model:")
            lines.append(f"- roundtrip cost USD: {fmt_float(cost.get('effective_roundtrip_cost_usd'))}")
            lines.append("- spread: assumed, not broker-measured")

    else:
        lines.append("Summary file: not found")
        lines.append("Meaning: pipeline may have failed before baseline summary generation.")

    lines.append("")
    lines.append("Warning: diagnostic only. No ML, no paper-order, no live decision.")
    lines.append("Current limitation: Twelve Data has no broker bid/ask spread in this pipeline.")

    if run_url:
        lines.append("")
        lines.append(f"Run: {run_url}")

    text = "\n".join(lines)
    # Telegram sendMessage max is 4096 chars. Keep margin.
    return text[:3900]


def send_telegram(token: str, chat_id: str, text: str, timeout_sec: int = 20) -> Dict[str, Any]:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    response = requests.post(
        url,
        json={
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": True,
        },
        timeout=timeout_sec,
    )
    try:
        payload = response.json()
    except Exception:
        payload = {"raw": response.text[:500]}

    if response.status_code != 200:
        raise RuntimeError(f"Telegram sendMessage failed: status={response.status_code}, body={payload}")

    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Send optional Telegram notification for XAUUSD pipeline reports.")
    parser.add_argument("--summary", default=None, help="Path to summary JSON.")
    parser.add_argument("--latest-pattern", default="data/reports/stage2a_baseline_summary_*.json")
    parser.add_argument("--status", default=os.getenv("WORKFLOW_STATUS", "unknown"))
    parser.add_argument("--allow-missing-secrets", action="store_true", default=True)
    args = parser.parse_args()

    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()

    if not token or not chat_id:
        print("Telegram notification skipped: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is missing.")
        return 0 if args.allow_missing_secrets else 2

    summary_path = Path(args.summary) if args.summary else latest_file(args.latest_pattern)
    summary = None
    if summary_path and summary_path.exists():
        summary = load_json(summary_path)

    repo = os.getenv("GITHUB_REPOSITORY", "").strip()
    run_id = os.getenv("GITHUB_RUN_ID", "").strip()
    run_url = f"https://github.com/{repo}/actions/runs/{run_id}" if repo and run_id else ""

    text = build_message(summary=summary, status=args.status, run_url=run_url)
    result = send_telegram(token=token, chat_id=chat_id, text=text)
    print(json.dumps({"ok": True, "telegram_ok": result.get("ok"), "summary": str(summary_path) if summary_path else None}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
