#!/usr/bin/env python3
"""Stage76E K06 observer bridge mode-key fix.

Writes key,value CSV with both mode and ea_mode for the K06 observer-only EA.
"""
from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

K06_CONDITIONS = [
    ("gold_sma20_over_50", ">", 0.0),
    ("dxy_ret_20d", ">", 0.0),
    ("real_yield_change_20d", "<", 0.0),
]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--root", default=".")
    p.add_argument("--config", required=True)
    p.add_argument("--out", required=True)
    return p.parse_args()


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def read_last_csv_row(path: Path, date_col: str) -> Dict[str, str]:
    last = None
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if date_col not in (reader.fieldnames or []):
            raise RuntimeError(f"date_col missing: {date_col}")
        for row in reader:
            last = row
    if last is None:
        raise RuntimeError("macro csv has no rows")
    return last


def to_float(v: str | None) -> float | None:
    if v is None:
        return None
    s = str(v).strip()
    if not s or s.lower() in {"nan", "none", "null"}:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def eval_condition(row: Dict[str, str], col: str, op: str, threshold: float) -> Dict[str, Any]:
    val = to_float(row.get(col))
    if val is None:
        return {"column": col, "operator": op, "threshold": threshold, "value": None, "passed": False, "reason": "missing_or_non_numeric"}
    passed = val > threshold if op == ">" else val < threshold
    return {"column": col, "operator": op, "threshold": threshold, "value": val, "passed": passed, "reason": "ok" if passed else f"{val}{op}{threshold}"}


def clean_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return ""
    return str(value).replace("\n", " ").replace("\r", " ").replace(",", ";")


def write_key_value_csv(path: Path, pairs: Iterable[Tuple[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        f.write("key,value\n")
        for k, v in pairs:
            f.write(f"{clean_value(k)},{clean_value(v)}\n")


def main() -> None:
    args = parse_args()
    root = Path(args.root).expanduser().resolve()
    config_path = (root / args.config).resolve() if not Path(args.config).is_absolute() else Path(args.config)
    config = load_json(config_path)
    out_dir = (root / args.out).resolve() if not Path(args.out).is_absolute() else Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    macro_path = root / config["macro_path"]
    date_col = config.get("date_col", "feature_date_utc")
    row = read_last_csv_row(macro_path, date_col)
    checks = [eval_condition(row, *c) for c in K06_CONDITIONS]
    failures = [f"{c['column']}:{c['reason']}" for c in checks if not c["passed"]]
    active = not failures
    mode = "OBSERVER_ONLY_NO_TRADE"

    bridge_path = root / config.get("bridge_csv_path", "data/mt5_bridge/k06_observer_signal.csv")
    pairs: List[Tuple[str, Any]] = [
        ("schema_version", "stage76e_k06_observer_v1"),
        ("stage", "Stage76E_K06_OBSERVER_MODE_FIX"),
        ("generated_utc", datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")),
        ("thesis", "K06_RESILIENT_GOLD_VS_DXY"),
        ("thesis_id", "K06_RESILIENT_GOLD_VS_DXY"),
        ("feature_date", row.get(date_col, "")),
        ("latest_feature_date_utc", row.get(date_col, "")),
        ("signal_active", active),
        ("mode", mode),
        ("ea_mode", mode),
        ("execution_allowed", False),
        ("order_authorized", False),
        ("broker_connection_allowed", False),
        ("failures", "|".join(failures)),
        ("rule_failures", "|".join(failures)),
    ]
    write_key_value_csv(bridge_path, pairs)

    summary = {
        "stage": "Stage76E_K06_OBSERVER_MODE_FIX",
        "status": "STAGE76E_COMPLETE_NO_PROMOTION",
        "decision": "STAGE76E_K06_OBSERVER_CSV_MODE_FIXED_NO_ORDER",
        "latest_feature_date_utc": row.get(date_col, ""),
        "signal_active": active,
        "rule_failures": failures,
        "bridge_csv": str(bridge_path),
        "mode_exported": mode,
        "hard_blocks": ["NO_AUTOMATED_ORDER", "NO_PAPER_ORDER", "NO_BROKER_CONNECTION", "OBSERVER_ONLY_EA", "NO_LIVE"],
    }
    with (out_dir / "stage76e_k06_observer_mode_fix_summary.json").open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    (out_dir / "stage76e_k06_observer_mode_fix_report.md").write_text(
        "# Stage76E K06 Observer Mode Fix\n\n"
        f"- decision: `{summary['decision']}`\n"
        f"- feature_date: `{summary['latest_feature_date_utc']}`\n"
        f"- signal_active: `{summary['signal_active']}`\n"
        f"- mode_exported: `{mode}`\n"
        f"- bridge_csv: `{bridge_path}`\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
