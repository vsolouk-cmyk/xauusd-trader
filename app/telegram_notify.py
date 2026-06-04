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


def latest_summary() -> Optional[Path]:
    patterns = [
        "data/reports/stage2k_walkforward_summary_*.json",
        "data/reports/stage2j_candidate_stability_summary_*.json",
        "data/reports/stage2d_grid_summary_*.json",
        "data/reports/stage2c_robustness_summary_*.json",
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


def best_item(summary: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if summary.get("stage") == "stage2k_walkforward_validation":
        analyses = summary.get("analyses", []) or []
        passed = [x for x in analyses if x.get("walkforward_pass")]
        pool = passed or analyses
        if not pool:
            return None
        return sorted(pool, key=lambda x: float(x.get("base", {}).get("total_net_usd", -10**18)), reverse=True)[0]
    if summary.get("stage") == "stage2j_candidate_stability_analysis":
        top = summary.get("top_analyses", []) or []
        return top[0] if top else None
    if summary.get("stage") == "stage2d_baseline_grid_lab":
        top = summary.get("top_variants", []) or []
        return top[0] if top else None
    return None


def build_message(summary: Optional[Dict[str, Any]], status: str, run_url: str = "", include_run_link: bool = False) -> str:
    lines = ["XAUUSD Research Update"]

    if summary:
        stage = summary.get("stage", "n/a")
        decision = summary.get("decision", {}) or {}
        lines.append(f"Stage: {stage}")
        lines.append(f"Workflow status: {status}")
        lines.append(f"Decision: {decision.get('status', 'n/a')}")
        lines.append(f"Reason: {decision.get('reason', 'n/a')}")

        for key in ["walkforward_pass_count", "stable_candidate_count", "robust_after_stage2c_count", "robust_candidate_count", "candidate_count"]:
            if key in decision:
                lines.append(f"{key}: {decision.get(key)}")

        item = best_item(summary)
        if item:
            lines.append("")
            lines.append("Top snapshot:")
            lines.append(f"- family/name: {item.get('family', item.get('baseline', 'n/a'))}")
            if item.get("variant"):
                lines.append(f"- variant: {item.get('variant')}")

            base = item.get("base", {}) or {}
            if base:
                lines.append(f"- trades: {base.get('trade_count', 'n/a')}")
                if "walkforward_pass" in item:
                    lines.append(f"- walk-forward: {item.get('walkforward_pass')}")
                elif "stable_candidate" in item:
                    lines.append(f"- stable: {item.get('stable_candidate')}")
                elif "robust_grid_candidate" in item:
                    lines.append(f"- robust: {item.get('robust_grid_candidate')}")
                lines.append(f"- win rate: {fmt_pct(base.get('win_rate'))}")
                lines.append(f"- total net: {fmt_float(base.get('total_net_usd'))}")
                lines.append(f"- PF: {fmt_float(base.get('profit_factor'), 3)}")
                if "folds" in item:
                    folds = item.get("folds", {}) or {}
                    lines.append(f"- fold +ratio: {fmt_pct(folds.get('positive_fold_ratio'))}")
                    last = folds.get("last_fold", {}) or {}
                    lines.append(f"- last fold: {fmt_float(last.get('total_net_usd'))}")
                if "rolling" in item:
                    roll = item.get("rolling", {}) or {}
                    lines.append(f"- neg rolling windows: {fmt_pct(roll.get('negative_window_ratio'))}")
                if "last_50" in item:
                    lines.append(f"- last 50: {fmt_float((item.get('last_50') or {}).get('total_net_usd'))}")

    else:
        lines.append("Stage: unknown")
        lines.append(f"Workflow status: {status}")
        lines.append("Summary file: not found")

    lines.append("")
    lines.append("Warning: diagnostic only. No ML, no paper-order, no live decision.")
    lines.append("Current limitation: Twelve Data has no broker bid/ask spread in this pipeline.")

    if bool(run_url) and (include_run_link or str(status).lower() != "success"):
        lines.append("")
        lines.append(f"Run: {run_url}")

    return "\n".join(lines)[:3900]


def send_telegram(token: str, chat_id: str, text: str, timeout_sec: int = 20) -> Dict[str, Any]:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    response = requests.post(
        url,
        json={"chat_id": chat_id, "text": text, "disable_web_page_preview": True},
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
    parser.add_argument("--summary", default=None)
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
    text = build_message(summary=summary, status=args.status, run_url=run_url, include_run_link=bool(args.include_run_link or env_include_link))

    result = send_telegram(token=token, chat_id=chat_id, text=text)
    print(json.dumps({"ok": True, "telegram_ok": result.get("ok"), "summary": str(summary_path) if summary_path else None}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
