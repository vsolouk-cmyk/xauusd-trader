from __future__ import annotations

import argparse
import glob
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

import requests


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def latest_file(pattern: str) -> Optional[Path]:
    files = sorted(glob.glob(pattern), key=lambda p: Path(p).stat().st_mtime, reverse=True)
    return Path(files[0]) if files else None


def latest_summary() -> Optional[Path]:
    # Prefer newest Stage 2B, then Stage 2A.
    patterns = [
        "data/reports/stage2b_validation_summary_*.json",
        "data/reports/stage2a_baseline_summary_*.json",
    ]
    candidates = []
    for pattern in patterns:
        candidates.extend(glob.glob(pattern))
    if not candidates:
        return None
    return Path(sorted(candidates, key=lambda p: Path(p).stat().st_mtime, reverse=True)[0])


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


def score_key(item: Dict[str, Any]) -> float:
    return float(item.get("total_net_usd", -10**18) or -10**18)


def best_baseline(summary: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    items = summary.get("summaries", []) or []
    if not items:
        return None

    robust = [x for x in items if x.get("robust_candidate")]
    candidates = [x for x in items if x.get("candidate")]
    pool = robust or candidates or items
    return sorted(pool, key=score_key, reverse=True)[0]


def decision_status(summary: Dict[str, Any]) -> str:
    decision = summary.get("decision", {}) or {}
    return str(decision.get("status", "n/a"))


def build_message(summary: Optional[Dict[str, Any]], status: str, run_url: str = "", include_run_link: bool = False) -> str:
    lines = []
    lines.append("XAUUSD Research Update")

    if summary:
        stage = summary.get("stage", "n/a")
        decision = summary.get("decision", {}) or {}
        lines.append(f"Stage: {stage}")
        lines.append(f"Workflow status: {status}")
        lines.append(f"Decision: {decision.get('status', 'n/a')}")
        lines.append(f"Reason: {decision.get('reason', 'n/a')}")

        if "robust_candidate_count" in decision:
            lines.append(f"Robust candidates: {decision.get('robust_candidate_count', 0)}")
        else:
            lines.append(f"Candidates: {decision.get('candidate_count', 0)}")

        top = best_baseline(summary)
        if top:
            lines.append("")
            lines.append("Top baseline snapshot:")
            lines.append(f"- name: {top.get('baseline', 'n/a')}")
            lines.append(f"- trades: {top.get('trade_count', 'n/a')}")
            if "robust_candidate" in top:
                lines.append(f"- robust: {top.get('robust_candidate', 'n/a')}")
            elif "candidate" in top:
                lines.append(f"- candidate: {top.get('candidate', 'n/a')}")
            lines.append(f"- win rate: {fmt_pct(top.get('win_rate'))}")
            lines.append(f"- avg net USD: {fmt_float(top.get('avg_net_usd'))}")
            lines.append(f"- total net USD: {fmt_float(top.get('total_net_usd'))}")
            lines.append(f"- max DD USD: {fmt_float(top.get('max_drawdown_usd'))}")
            if "overlap_reduction_ratio" in top:
                lines.append(f"- overlap reduced: {fmt_pct(top.get('overlap_reduction_ratio'))}")

        cost = summary.get("cost_model", {}) or {}
        if cost:
            lines.append("")
            lines.append("Cost model:")
            lines.append(f"- roundtrip cost USD: {fmt_float(cost.get('effective_roundtrip_cost_usd'))}")
            lines.append("- spread: assumed, not broker-measured")

    else:
        lines.append("Stage: unknown")
        lines.append(f"Workflow status: {status}")
        lines.append("Summary file: not found")
        lines.append("Meaning: pipeline may have failed before summary generation.")

    lines.append("")
    lines.append("Warning: diagnostic only. No ML, no paper-order, no live decision.")
    lines.append("Current limitation: Twelve Data has no broker bid/ask spread in this pipeline.")

    # For success, keep Telegram clean by default. For failure, include run link automatically.
    should_include_link = bool(run_url) and (include_run_link or str(status).lower() != "success")
    if should_include_link:
        lines.append("")
        lines.append(f"Run: {run_url}")

    return "\n".join(lines)[:3900]


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
    parser.add_argument("--status", default=os.getenv("WORKFLOW_STATUS", "unknown"))
    parser.add_argument("--include-run-link", action="store_true")
    parser.add_argument("--allow-missing-secrets", action="store_true", default=True)
    args = parser.parse_args()

    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()

    if not token or not chat_id:
        print("Telegram notification skipped: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is missing.")
        return 0 if args.allow_missing_secrets else 2

    summary_path = Path(args.summary) if args.summary else latest_summary()
    summary = load_json(summary_path) if summary_path and summary_path.exists() else None

    repo = os.getenv("GITHUB_REPOSITORY", "").strip()
    run_id = os.getenv("GITHUB_RUN_ID", "").strip()
    run_url = f"https://github.com/{repo}/actions/runs/{run_id}" if repo and run_id else ""

    env_include_link = os.getenv("TELEGRAM_INCLUDE_RUN_LINK", "").strip().lower() in {"1", "true", "yes", "on"}
    text = build_message(
        summary=summary,
        status=args.status,
        run_url=run_url,
        include_run_link=bool(args.include_run_link or env_include_link),
    )

    result = send_telegram(token=token, chat_id=chat_id, text=text)
    print(json.dumps({"ok": True, "telegram_ok": result.get("ok"), "summary": str(summary_path) if summary_path else None}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
