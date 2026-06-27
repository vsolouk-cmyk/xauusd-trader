#!/usr/bin/env python3
"""Stage75 historical activation drill for K06.

This script does not authorize or route any order. It replays historical K06
activation dates as if each activation date were "today" and builds review-only
activation packets from same-day lag-safe features. Future prices are used only
after the configured historical horizon to score matured drill outcomes.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:
    import pandas as pd
except Exception as exc:  # pragma: no cover
    raise SystemExit(f"pandas is required for Stage75: {exc}")


@dataclass
class Condition:
    column: str
    operator: str
    threshold: float

    def evaluate(self, row: pd.Series) -> Tuple[bool, Optional[float], str]:
        if self.column not in row.index:
            return False, None, "missing_column"
        value = row[self.column]
        if pd.isna(value):
            return False, None, "missing_value"
        try:
            v = float(value)
        except Exception:
            return False, None, "non_numeric_value"
        if self.operator == ">":
            passed = v > self.threshold
        elif self.operator == ">=":
            passed = v >= self.threshold
        elif self.operator == "<":
            passed = v < self.threshold
        elif self.operator == "<=":
            passed = v <= self.threshold
        elif self.operator == "==":
            passed = v == self.threshold
        else:
            return False, v, f"unsupported_operator:{self.operator}"
        return bool(passed), v, "ok" if passed else f"{v}{self.operator}{self.threshold}"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def write_markdown(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def ensure_float(x: Any) -> Optional[float]:
    if x is None:
        return None
    try:
        if pd.isna(x):
            return None
        return float(x)
    except Exception:
        return None


def load_macro(root: Path, cfg: Dict[str, Any]) -> Tuple[pd.DataFrame, Path]:
    macro_path = root / cfg["macro_path"]
    if not macro_path.exists():
        raise FileNotFoundError(f"Macro dataset not found: {macro_path}")
    df = pd.read_csv(macro_path)
    date_col = cfg.get("date_col", "feature_date_utc")
    price_col = cfg.get("price_col", "gold_close")
    if date_col not in df.columns:
        raise ValueError(f"Missing date column: {date_col}")
    if price_col not in df.columns:
        raise ValueError(f"Missing price column: {price_col}")
    df[date_col] = pd.to_datetime(df[date_col], utc=True, errors="coerce")
    df = df.dropna(subset=[date_col]).sort_values(date_col).reset_index(drop=True)
    return df, macro_path


def lock_checks(root: Path, cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for spec in cfg.get("required_lock_files", []):
        p = root / spec["path"]
        item: Dict[str, Any] = {
            "stage": spec.get("stage"),
            "path": str(p),
            "exists": p.exists(),
            "read_ok": False,
            "required_disposition": spec.get("required_disposition"),
            "actual_disposition": None,
            "matches_required": False,
            "issue": None,
        }
        if not p.exists():
            item["issue"] = "LOCK_FILE_MISSING"
            out.append(item)
            continue
        try:
            data = read_json(p)
            item["read_ok"] = True
            actual = data.get("disposition") or data.get("decision")
            item["actual_disposition"] = actual
            item["matches_required"] = actual == spec.get("required_disposition")
            if not item["matches_required"]:
                item["issue"] = "LOCK_DISPOSITION_MISMATCH"
        except Exception as exc:
            item["issue"] = f"LOCK_READ_ERROR:{exc}"
        out.append(item)
    return out


def row_date_str(row: pd.Series, date_col: str) -> str:
    dt = row[date_col]
    if hasattr(dt, "strftime"):
        return dt.strftime("%Y-%m-%d")
    return str(dt)[:10]


def evaluate_signal(row: pd.Series, conditions: List[Condition]) -> Dict[str, Any]:
    results = []
    failures = []
    missing_cols = []
    missing_values = []
    active = True
    for cond in conditions:
        passed, value, reason = cond.evaluate(row)
        item = {
            "column": cond.column,
            "operator": cond.operator,
            "threshold": cond.threshold,
            "value": value,
            "passed": passed,
            "reason": reason,
        }
        results.append(item)
        if not passed:
            active = False
            if reason == "missing_column":
                missing_cols.append(cond.column)
            elif reason == "missing_value":
                missing_values.append(cond.column)
            else:
                failures.append(f"{cond.column}:{reason}")
    return {
        "signal_active": active,
        "condition_results": results,
        "rule_failures": failures,
        "missing_columns": missing_cols,
        "missing_values": missing_values,
    }


def select_window(df: pd.DataFrame, cfg: Dict[str, Any]) -> pd.DataFrame:
    date_col = cfg.get("date_col", "feature_date_utc")
    start = cfg.get("drill_start_date")
    end = cfg.get("drill_end_date")
    w = df.copy()
    if start:
        w = w[w[date_col] >= pd.Timestamp(start, tz="UTC")]
    if end:
        w = w[w[date_col] <= pd.Timestamp(end, tz="UTC")]
    return w.reset_index(drop=False).rename(columns={"index": "source_row_index"})


def compute_events(df: pd.DataFrame, cfg: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], int, int, int]:
    date_col = cfg.get("date_col", "feature_date_utc")
    price_col = cfg.get("price_col", "gold_close")
    conditions = [Condition(**c) for c in cfg["conditions"]]
    horizon = int(cfg.get("horizon_trading_days", 120))
    cooldown = int(cfg.get("entry_cooldown_trading_days", horizon))
    cost_bps = float(cfg.get("cost_bps_total", 50.0))
    window = select_window(df, cfg)

    missing_required_feature_rows = 0
    active_days = 0
    events: List[Dict[str, Any]] = []
    next_allowed_source_idx = -1
    lookahead_violations = 0

    required_cols = {date_col, price_col, *[c["column"] for c in cfg["conditions"]]}

    for _, row in window.iterrows():
        source_idx = int(row["source_row_index"])
        if any((col not in row.index) or pd.isna(row[col]) for col in required_cols):
            missing_required_feature_rows += 1
            continue
        signal = evaluate_signal(row, conditions)
        if signal["signal_active"]:
            active_days += 1
        if not signal["signal_active"]:
            continue
        if source_idx < next_allowed_source_idx:
            continue
        entry_price = ensure_float(row[price_col])
        if entry_price is None or entry_price <= 0:
            missing_required_feature_rows += 1
            continue
        exit_idx = source_idx + horizon
        matured = exit_idx < len(df)
        exit_price = None
        gross_bps = None
        net_bps = None
        exit_date = None
        if matured:
            exit_row = df.iloc[exit_idx]
            exit_price = ensure_float(exit_row[price_col])
            exit_date = row_date_str(exit_row, date_col)
            if exit_price is None or exit_price <= 0:
                matured = False
            else:
                gross_bps = (exit_price / entry_price - 1.0) * 10000.0
                net_bps = gross_bps - cost_bps
        packet = {
            "packet_id": f"K06_HISTORICAL_ACTIVATION_{row_date_str(row, date_col)}",
            "thesis_id": cfg.get("thesis_id", "K06_RESILIENT_GOLD_VS_DXY"),
            "family": cfg.get("family", "GOLD_RESILIENCE_AGAINST_DXY"),
            "direction": cfg.get("direction", "long"),
            "entry_date_utc": row_date_str(row, date_col),
            "entry_source_row_index": source_idx,
            "entry_price": round(entry_price, 6),
            "horizon_trading_days": horizon,
            "entry_cooldown_trading_days": cooldown,
            "cost_bps_total_reference": cost_bps,
            "same_day_signal_snapshot": signal,
            "review_only": True,
            "order_authorized": False,
            "broker_connection_allowed": False,
            "matured": matured,
            "exit_date_utc": exit_date,
            "exit_price": round(exit_price, 6) if exit_price is not None else None,
            "gross_return_bps": round(gross_bps, 4) if gross_bps is not None else None,
            "net_return_bps": round(net_bps, 4) if net_bps is not None else None,
            "outcome_label": None,
        }
        if net_bps is not None:
            packet["outcome_label"] = "WIN" if net_bps > 0 else "LOSS"
        events.append(packet)
        next_allowed_source_idx = source_idx + cooldown

    return events, active_days, missing_required_feature_rows, lookahead_violations


def metrics(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    matured = [e for e in events if e.get("matured") and e.get("net_return_bps") is not None]
    vals = [float(e["net_return_bps"]) for e in matured]
    if not vals:
        return {
            "entry_count": len(events),
            "matured_count": 0,
            "mean_net_return_bps": None,
            "median_net_return_bps": None,
            "win_rate": None,
            "min_net_return_bps": None,
            "max_net_return_bps": None,
            "total_net_return_bps": 0.0,
        }
    s = pd.Series(vals, dtype="float64")
    return {
        "entry_count": len(events),
        "matured_count": len(vals),
        "mean_net_return_bps": round(float(s.mean()), 4),
        "median_net_return_bps": round(float(s.median()), 4),
        "win_rate": round(float((s > 0).mean()), 4),
        "min_net_return_bps": round(float(s.min()), 4),
        "max_net_return_bps": round(float(s.max()), 4),
        "total_net_return_bps": round(float(s.sum()), 4),
    }


def build_latest_packet(events: List[Dict[str, Any]], cfg: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    matured = [e for e in events if e.get("matured")]
    if not matured:
        return None
    # latest_matured_activation policy
    chosen = sorted(matured, key=lambda e: e["entry_date_utc"])[-1]
    packet = dict(chosen)
    packet["packet_role"] = "HISTORICAL_REVIEW_ONLY_ACTIVATION_DRILL_PACKET"
    packet["operator_instruction"] = (
        "This packet is generated from a historical activation date. It proves the activation-review "
        "protocol can be built without waiting for a live active signal. It cannot authorize any order."
    )
    packet["hard_blocks"] = cfg.get("hard_blocks", [])
    return packet


def packet_to_md(packet: Dict[str, Any]) -> str:
    sig = packet.get("same_day_signal_snapshot", {})
    lines = [
        "# Stage75 K06 Historical Review-Only Activation Packet",
        "",
        "## Packet",
        f"- packet_id: `{packet.get('packet_id')}`",
        f"- packet_role: `{packet.get('packet_role')}`",
        f"- thesis_id: `{packet.get('thesis_id')}`",
        f"- direction: `{packet.get('direction')}`",
        f"- entry_date_utc: `{packet.get('entry_date_utc')}`",
        f"- entry_price: `{packet.get('entry_price')}`",
        f"- horizon_trading_days: `{packet.get('horizon_trading_days')}`",
        f"- review_only: `{packet.get('review_only')}`",
        f"- order_authorized: `{packet.get('order_authorized')}`",
        "",
        "## Same-day signal snapshot",
        f"- signal_active: `{sig.get('signal_active')}`",
    ]
    for cr in sig.get("condition_results", []):
        lines.append(
            f"- `{cr.get('column')}` {cr.get('operator')} `{cr.get('threshold')}`: "
            f"value=`{cr.get('value')}`, passed=`{cr.get('passed')}`"
        )
    lines += [
        "",
        "## Matured historical outcome",
        f"- matured: `{packet.get('matured')}`",
        f"- exit_date_utc: `{packet.get('exit_date_utc')}`",
        f"- exit_price: `{packet.get('exit_price')}`",
        f"- gross_return_bps: `{packet.get('gross_return_bps')}`",
        f"- net_return_bps: `{packet.get('net_return_bps')}`",
        f"- outcome_label: `{packet.get('outcome_label')}`",
        "",
        "## Hard blocks",
    ]
    for block in packet.get("hard_blocks", []):
        lines.append(f"- `{block}`")
    lines.append("")
    return "\n".join(lines)


def write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    # Flatten nested fields lightly for CSV.
    flat_rows: List[Dict[str, Any]] = []
    for row in rows:
        r = {}
        for k, v in row.items():
            if isinstance(v, (dict, list)):
                r[k] = json.dumps(v, ensure_ascii=False, sort_keys=True)
            else:
                r[k] = v
        flat_rows.append(r)
    keys = list(flat_rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        for r in flat_rows:
            writer.writerow(r)


def make_report(summary: Dict[str, Any]) -> str:
    m = summary.get("activation_drill_metrics", {})
    latest = summary.get("latest_historical_activation_packet", {})
    lines = [
        "# Stage75 Historical Activation Drill",
        "",
        "## Decision",
        f"- status: `{summary.get('status')}`",
        f"- decision: `{summary.get('decision')}`",
        f"- classification: `{summary.get('classification')}`",
        f"- disposition: `{summary.get('disposition')}`",
        "",
        "## Principle",
        summary.get("principle", ""),
        "",
        "## Drill metrics",
        f"- replay_rows: `{summary.get('replay_rows')}`",
        f"- active_days: `{summary.get('active_days')}`",
        f"- activation_packets: `{summary.get('activation_packets')}`",
        f"- matured_activation_packets: `{m.get('matured_count')}`",
        f"- mean_net_return_bps: `{m.get('mean_net_return_bps')}`",
        f"- median_net_return_bps: `{m.get('median_net_return_bps')}`",
        f"- win_rate: `{m.get('win_rate')}`",
        f"- min_net_return_bps: `{m.get('min_net_return_bps')}`",
        f"- max_net_return_bps: `{m.get('max_net_return_bps')}`",
        f"- lookahead_violations: `{summary.get('lookahead_violations')}`",
        f"- missing_required_feature_rows: `{summary.get('missing_required_feature_rows')}`",
        "",
        "## Latest historical review-only activation packet",
    ]
    if latest:
        lines += [
            f"- packet_id: `{latest.get('packet_id')}`",
            f"- entry_date_utc: `{latest.get('entry_date_utc')}`",
            f"- entry_price: `{latest.get('entry_price')}`",
            f"- exit_date_utc: `{latest.get('exit_date_utc')}`",
            f"- net_return_bps: `{latest.get('net_return_bps')}`",
            f"- order_authorized: `{latest.get('order_authorized')}`",
        ]
    else:
        lines.append("- none")
    lines += [
        "",
        "## Lock checks",
    ]
    for item in summary.get("lock_checks", []):
        lines.append(
            f"- `{item.get('stage')}`: exists=`{item.get('exists')}`, read_ok=`{item.get('read_ok')}`, "
            f"matches_required=`{item.get('matches_required')}`, actual=`{item.get('actual_disposition')}`"
        )
    lines += [
        "",
        "## Issues",
    ]
    if summary.get("issues"):
        for i in summary["issues"]:
            lines.append(f"- `{i}`")
    else:
        lines.append("- none")
    lines += ["", "## Cautions"]
    if summary.get("cautions"):
        for c in summary["cautions"]:
            lines.append(f"- `{c}`")
    else:
        lines.append("- none")
    lines += ["", "## Hard blocks"]
    for b in summary.get("hard_blocks", []):
        lines.append(f"- `{b}`")
    lines.append("")
    return "\n".join(lines)


def run(root: Path, config_path: Path, out_dir: Path) -> Dict[str, Any]:
    cfg = read_json(config_path)
    df, macro_path = load_macro(root, cfg)
    events, active_days, missing_required_feature_rows, lookahead_violations = compute_events(df, cfg)
    mets = metrics(events)
    locks = lock_checks(root, cfg)
    lock_failures = [l for l in locks if not l.get("matches_required")]
    latest_packet = build_latest_packet(events, cfg)

    date_col = cfg.get("date_col", "feature_date_utc")
    window = select_window(df, cfg)
    replay_rows = len(window)

    constraints = cfg.get("decision_constraints", {})
    issues: List[str] = []
    cautions: List[str] = []

    if lock_failures:
        issues.append("LOCK_CHECKS_NOT_ALL_PASS")
    if mets.get("matured_count", 0) < int(constraints.get("min_matured_activation_packets", 3)):
        issues.append("INSUFFICIENT_MATURED_ACTIVATION_PACKETS")
    if lookahead_violations > int(constraints.get("max_lookahead_violations", 0)):
        issues.append("LOOKAHEAD_VIOLATIONS_PRESENT")
    if missing_required_feature_rows > int(constraints.get("max_missing_required_feature_rows", 0)):
        issues.append("MISSING_REQUIRED_FEATURE_ROWS_PRESENT")
    if mets.get("mean_net_return_bps") is None or mets["mean_net_return_bps"] < float(constraints.get("min_mean_net_return_bps", 0.0)):
        issues.append("MEAN_NET_RETURN_BELOW_DRILL_FLOOR")
    if mets.get("win_rate") is None or mets["win_rate"] < float(constraints.get("min_win_rate", 0.5)):
        issues.append("WIN_RATE_BELOW_DRILL_FLOOR")
    worst = mets.get("min_net_return_bps")
    if worst is not None and abs(float(worst)) > float(constraints.get("max_abs_worst_loss_bps", 1500.0)):
        cautions.append("WORST_LOSS_EXCEEDS_REFERENCE_LIMIT")

    if issues:
        decision = "STAGE75_HISTORICAL_ACTIVATION_DRILL_FAIL_NO_ORDER"
        classification = "S75_K06_HISTORICAL_ACTIVATION_DRILL_FAIL"
        disposition = "K06_HISTORICAL_ACTIVATION_DRILL_FAIL"
    elif cautions:
        decision = "STAGE75_HISTORICAL_ACTIVATION_DRILL_PASS_WITH_CAUTION_NO_ORDER"
        classification = "S75_K06_HISTORICAL_ACTIVATION_DRILL_PASS_WITH_CAUTION"
        disposition = "K06_PASSES_HISTORICAL_ACTIVATION_DRILL_WITH_CAUTION"
    else:
        decision = "STAGE75_HISTORICAL_ACTIVATION_DRILL_PASS_NO_ORDER"
        classification = "S75_K06_HISTORICAL_ACTIVATION_DRILL_PASS"
        disposition = "K06_PASSES_HISTORICAL_ACTIVATION_DRILL"

    out_dir.mkdir(parents=True, exist_ok=True)
    ledger_csv = out_dir / "stage75_k06_historical_activation_drill_ledger.csv"
    write_csv(ledger_csv, events)
    packets_jsonl = out_dir / "stage75_k06_historical_activation_packets.jsonl"
    with packets_jsonl.open("w", encoding="utf-8") as f:
        for e in events:
            f.write(json.dumps(e, ensure_ascii=False, sort_keys=True) + "\n")

    packet_json_path = None
    packet_md_path = None
    if latest_packet:
        packet_json_path = out_dir / "stage75_k06_latest_historical_review_only_activation_packet.json"
        packet_md_path = out_dir / "stage75_k06_latest_historical_review_only_activation_packet.md"
        write_json(packet_json_path, latest_packet)
        write_markdown(packet_md_path, packet_to_md(latest_packet))

    latest_row = df.iloc[-1]
    latest_signal = evaluate_signal(latest_row, [Condition(**c) for c in cfg["conditions"]])

    summary: Dict[str, Any] = {
        "stage": "Stage75_HISTORICAL_ACTIVATION_DRILL",
        "root": str(root),
        "config": str(config_path),
        "generated_utc": utc_now_iso(),
        "status": "STAGE75_COMPLETE_NO_PROMOTION",
        "decision": decision,
        "classification": classification,
        "disposition": disposition,
        "principle": (
            "Do not wait for a live active signal to test activation protocol. Historical K06 activations are replayed as if "
            "each activation date were today; future prices are used only after the historical horizon has matured."
        ),
        "champion": {
            "thesis_id": cfg.get("thesis_id"),
            "family": cfg.get("family"),
            "direction": cfg.get("direction"),
            "horizon_trading_days": cfg.get("horizon_trading_days"),
            "entry_cooldown_trading_days": cfg.get("entry_cooldown_trading_days"),
            "conditions_text": ";".join(f"{c['column']}{c['operator']}{c['threshold']}" for c in cfg["conditions"]),
            "cost_bps_total": cfg.get("cost_bps_total"),
        },
        "macro_dataset": {
            "path": str(macro_path),
            "rows_raw": len(df),
            "rows_replayed": replay_rows,
            "date_col": date_col,
            "price_col": cfg.get("price_col", "gold_close"),
            "min_date": row_date_str(df.iloc[0], date_col) if len(df) else None,
            "max_date": row_date_str(df.iloc[-1], date_col) if len(df) else None,
            "drill_start_date": cfg.get("drill_start_date"),
            "drill_end_date": cfg.get("drill_end_date"),
            "sha256": sha256_file(macro_path),
        },
        "lock_checks": locks,
        "lock_pass_count": sum(1 for l in locks if l.get("matches_required")),
        "lock_total_count": len(locks),
        "replay_rows": replay_rows,
        "active_days": active_days,
        "activation_packets": len(events),
        "missing_required_feature_rows": missing_required_feature_rows,
        "lookahead_violations": lookahead_violations,
        "activation_drill_metrics": mets,
        "latest_historical_activation_packet": latest_packet,
        "latest_real_signal_snapshot": {
            "latest_feature_date_utc": row_date_str(latest_row, date_col),
            **latest_signal,
        },
        "decision_constraints": constraints,
        "issues": issues,
        "cautions": cautions,
        "hard_blocks": cfg.get("hard_blocks", []),
        "operator_instructions": [
            "Stage75 cannot authorize orders.",
            "Historical activation packets are review-only drills and must not be routed to broker, EA, paper-live, or live.",
            "Do not wait for a live active signal merely to test packet generation or operational review mechanics.",
            "Do not retune K06 thresholds from Stage75.",
        ],
        "outputs": {
            "summary_json": str(out_dir / "stage75_historical_activation_drill_summary.json"),
            "report_md": str(out_dir / "stage75_historical_activation_drill_report.md"),
            "ledger_csv": str(ledger_csv),
            "packets_jsonl": str(packets_jsonl),
            "latest_packet_json": str(packet_json_path) if packet_json_path else None,
            "latest_packet_md": str(packet_md_path) if packet_md_path else None,
        },
    }

    write_json(out_dir / "stage75_historical_activation_drill_summary.json", summary)
    write_markdown(out_dir / "stage75_historical_activation_drill_report.md", make_report(summary))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--config", default="configs/stage75_historical_activation_drill.json")
    parser.add_argument("--out", default="reports/stage75_historical_activation_drill")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    config = (root / args.config).resolve() if not Path(args.config).is_absolute() else Path(args.config)
    out = (root / args.out).resolve() if not Path(args.out).is_absolute() else Path(args.out)
    summary = run(root, config, out)
    print(json.dumps({
        "status": summary["status"],
        "decision": summary["decision"],
        "classification": summary["classification"],
        "activation_packets": summary["activation_packets"],
        "matured_count": summary["activation_drill_metrics"].get("matured_count"),
        "latest_packet_json": summary["outputs"].get("latest_packet_json"),
    }, indent=2))


if __name__ == "__main__":
    main()
