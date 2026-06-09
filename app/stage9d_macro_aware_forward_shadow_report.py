#!/usr/bin/env python3
"""
Stage 9D — Macro-Aware Forward Shadow Report

Purpose:
- Combine Stage 8D forward-shadow signals/outcomes with Stage 9C numeric macro regimes.
- Produce a macro-aware monitoring report.
- Do NOT change EA logic and do NOT create a macro guard yet.

Rationale:
Stage 9C showed the technical candidate remains profitable across neutral/mixed/supportive
numeric regimes, while hostile sample count was too small and profitable. Therefore macro
numeric data is useful for context/reporting now, not for blocking trades yet.

Inputs:
- SQLite:
  - macro_daily_regime
- Stage 8D signals CSV:
  - XAUUSD_DryRun_v2_regime_shadow_signals.csv
- Stage 8D outcomes CSV if available:
  - data/reports/stage8d_forward_shadow_outcomes/stage8d_forward_shadow_outcomes.csv

Outputs:
- data/reports/stage9d_macro_aware_forward_shadow_report/stage9d_macro_aware_forward_shadow_report.md
- data/reports/stage9d_macro_aware_forward_shadow_report/stage9d_signals_macro_annotated.csv
- data/reports/stage9d_macro_aware_forward_shadow_report/stage9d_outcomes_macro_annotated.csv
- data/reports/stage9d_macro_aware_forward_shadow_report/stage9d_macro_aware_forward_shadow_report.json

Hard rules:
- Report only.
- No EA change.
- No demo/paper/live/order authorization.
"""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Dict, List, Optional, Sequence


TOOL_VERSION = "v1"
DEFAULT_DB = Path("data/local/xauusd_local_store.sqlite")
DEFAULT_SIGNALS = Path("~/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/users/user/AppData/Roaming/MetaQuotes/Terminal/Common/Files/XAUUSD_DryRun_v2_regime_shadow_signals.csv").expanduser()
DEFAULT_OUTCOMES = Path("data/reports/stage8d_forward_shadow_outcomes/stage8d_forward_shadow_outcomes.csv")
DEFAULT_OUT_DIR = Path("data/reports/stage9d_macro_aware_forward_shadow_report")


@dataclass
class MacroRegime:
    obs_date: str
    real_yield_10y: Optional[float]
    nominal_yield_10y: Optional[float]
    nominal_yield_2y: Optional[float]
    usd_index: Optional[float]
    wti: Optional[float]
    brent: Optional[float]
    d_real_yield_5d: Optional[float]
    d_usd_5d_pct: Optional[float]
    d_oil_5d_pct: Optional[float]
    macro_score_long_gold: float
    macro_regime: str
    regime_reason: str


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def parse_time(v: str) -> Optional[datetime]:
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y.%m.%d %H:%M:%S", "%Y.%m.%d"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
        except Exception:
            pass
    return None


def safe_float(v, default=0.0) -> float:
    try:
        if v is None or str(v).strip() == "":
            return default
        return float(str(v).strip())
    except Exception:
        return default


def connect_ro(path: Path) -> sqlite3.Connection:
    if not path.exists():
        raise FileNotFoundError(f"DB not found: {path}")
    conn = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def load_macro_regimes(conn: sqlite3.Connection) -> Dict[str, MacroRegime]:
    rows = conn.execute("""
        SELECT
            obs_date, real_yield_10y, nominal_yield_10y, nominal_yield_2y,
            usd_index, wti, brent, d_real_yield_5d, d_usd_5d_pct, d_oil_5d_pct,
            macro_score_long_gold, macro_regime, regime_reason
        FROM macro_daily_regime
        ORDER BY obs_date ASC
    """).fetchall()
    out: Dict[str, MacroRegime] = {}
    for r in rows:
        out[r["obs_date"]] = MacroRegime(
            obs_date=r["obs_date"],
            real_yield_10y=r["real_yield_10y"],
            nominal_yield_10y=r["nominal_yield_10y"],
            nominal_yield_2y=r["nominal_yield_2y"],
            usd_index=r["usd_index"],
            wti=r["wti"],
            brent=r["brent"],
            d_real_yield_5d=r["d_real_yield_5d"],
            d_usd_5d_pct=r["d_usd_5d_pct"],
            d_oil_5d_pct=r["d_oil_5d_pct"],
            macro_score_long_gold=r["macro_score_long_gold"],
            macro_regime=r["macro_regime"],
            regime_reason=r["regime_reason"],
        )
    return out


def latest_macro(regimes: Dict[str, MacroRegime]) -> Optional[MacroRegime]:
    if not regimes:
        return None
    return regimes[sorted(regimes.keys())[-1]]


def load_csv(path: Path) -> List[dict]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    if not text.strip():
        return []
    return list(csv.DictReader(text.splitlines()))


def row_date(row: dict) -> str:
    for key in ("planned_entry_utc", "entry_utc", "signal_closed_h1_utc", "signal_utc"):
        t = parse_time(row.get(key, ""))
        if t is not None:
            return t.date().isoformat()
    return ""


def annotate(rows: Sequence[dict], regimes: Dict[str, MacroRegime]) -> List[dict]:
    out = []
    for row in rows:
        d = row_date(row)
        m = regimes.get(d)
        r = dict(row)
        r["macro_obs_date"] = d
        if m is None:
            r.update({
                "macro_regime_numeric": "unknown",
                "macro_score_long_gold": "",
                "macro_regime_reason": "",
                "real_yield_10y": "",
                "usd_index": "",
                "wti": "",
                "d_real_yield_5d": "",
                "d_usd_5d_pct": "",
                "d_oil_5d_pct": "",
            })
        else:
            r.update({
                "macro_regime_numeric": m.macro_regime,
                "macro_score_long_gold": m.macro_score_long_gold,
                "macro_regime_reason": m.regime_reason,
                "real_yield_10y": m.real_yield_10y,
                "usd_index": m.usd_index,
                "wti": m.wti,
                "d_real_yield_5d": m.d_real_yield_5d,
                "d_usd_5d_pct": m.d_usd_5d_pct,
                "d_oil_5d_pct": m.d_oil_5d_pct,
            })
        out.append(r)
    return out


def write_csv(path: Path, rows: Sequence[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    cols = list(rows[0].keys()) if rows else ["empty"]
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for row in rows:
            w.writerow(row)


def pf(vals: Sequence[float]) -> float:
    wins = sum(v for v in vals if v > 0)
    losses = abs(sum(v for v in vals if v < 0))
    if losses == 0:
        return 999.0 if wins > 0 else 0.0
    return round(wins / losses, 6)


def summarize_outcomes(rows: Sequence[dict]) -> List[dict]:
    groups: Dict[str, List[float]] = {}
    for r in rows:
        if r.get("status") and r.get("status") != "RESOLVED":
            continue
        regime = r.get("macro_regime_numeric", "unknown")
        if "net_x4" in r:
            net = safe_float(r.get("net_x4"))
        elif "net_x4_usd" in r:
            net = safe_float(r.get("net_x4_usd"))
        else:
            continue
        groups.setdefault(regime, []).append(net)

    out = []
    for regime, vals in sorted(groups.items()):
        wins = [v for v in vals if v > 0]
        out.append({
            "macro_regime_numeric": regime,
            "resolved": len(vals),
            "total_net_x4": round(sum(vals), 6),
            "median_net_x4": round(median(vals), 6) if vals else 0.0,
            "pf_x4": pf(vals),
            "win_rate_x4": round(len(wins) / len(vals), 6) if vals else 0.0,
        })
    return out


def warning_from_macro(m: Optional[MacroRegime]) -> str:
    if m is None:
        return "NO_MACRO_DATA"
    if m.macro_regime == "hostile":
        return "MACRO_HOSTILE_CONTEXT_ONLY_DO_NOT_BLOCK_YET"
    if m.macro_regime == "mixed":
        return "MACRO_MIXED_CONTEXT_MONITOR"
    if m.macro_regime == "supportive":
        return "MACRO_SUPPORTIVE_CONTEXT_MONITOR"
    return "MACRO_NEUTRAL_CONTEXT_MONITOR"


def run(db_path: Path, signals_path: Path, outcomes_path: Path, out_dir: Path) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    generated = now_iso()

    conn = connect_ro(db_path)
    regimes = load_macro_regimes(conn)
    conn.close()

    latest = latest_macro(regimes)
    signals = load_csv(signals_path)
    outcomes = load_csv(outcomes_path)

    signals_ann = annotate(signals, regimes)
    outcomes_ann = annotate(outcomes, regimes)
    outcome_summary = summarize_outcomes(outcomes_ann)

    write_csv(out_dir / "stage9d_signals_macro_annotated.csv", signals_ann)
    write_csv(out_dir / "stage9d_outcomes_macro_annotated.csv", outcomes_ann)
    write_csv(out_dir / "stage9d_outcomes_macro_summary.csv", outcome_summary)

    payload = {
        "tool_version": TOOL_VERSION,
        "generated_utc": generated,
        "db_path": str(db_path),
        "signals_csv": str(signals_path),
        "outcomes_csv": str(outcomes_path),
        "macro_regime_rows": len(regimes),
        "latest_macro": asdict(latest) if latest else None,
        "signals_loaded": len(signals),
        "outcomes_loaded": len(outcomes),
        "outcome_summary": outcome_summary,
        "monitoring_warning": warning_from_macro(latest),
    }
    (out_dir / "stage9d_macro_aware_forward_shadow_report.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [
        "# Stage 9D Macro-Aware Forward Shadow Report",
        "",
        f"Generated UTC: `{generated}`",
        f"Tool version: `{TOOL_VERSION}`",
        "",
        "> Hard rule: report only. This does not authorize demo, paper, or live orders.",
        "",
        "## Inputs",
        f"- db: `{db_path}`",
        f"- signals_csv: `{signals_path}`",
        f"- outcomes_csv: `{outcomes_path}`",
        f"- macro_regime_rows: `{len(regimes)}`",
        f"- signals_loaded: `{len(signals)}`",
        f"- outcomes_loaded: `{len(outcomes)}`",
        "",
        "## Latest numeric macro snapshot",
    ]

    if latest is None:
        lines += ["- latest_macro: `none`"]
    else:
        lines += [
            f"- obs_date: `{latest.obs_date}`",
            f"- macro_regime: `{latest.macro_regime}`",
            f"- macro_score_long_gold: `{latest.macro_score_long_gold}`",
            f"- reason: `{latest.regime_reason}`",
            f"- real_yield_10y: `{latest.real_yield_10y}`",
            f"- nominal_yield_10y: `{latest.nominal_yield_10y}`",
            f"- nominal_yield_2y: `{latest.nominal_yield_2y}`",
            f"- usd_index: `{latest.usd_index}`",
            f"- wti: `{latest.wti}`",
            f"- d_real_yield_5d: `{latest.d_real_yield_5d}`",
            f"- d_usd_5d_pct: `{latest.d_usd_5d_pct}`",
            f"- d_oil_5d_pct: `{latest.d_oil_5d_pct}`",
        ]

    lines += [
        "",
        "## Monitoring warning",
        f"- `{warning_from_macro(latest)}`",
        "",
        "## Stage 8D live forward-shadow outcomes by macro regime",
        "| Macro regime | Resolved | Total x4 | Median x4 | PF x4 | WR x4 |",
        "|---|---:|---:|---:|---:|---:|",
    ]

    if outcome_summary:
        for r in outcome_summary:
            lines.append(
                f"| {r['macro_regime_numeric']} | {r['resolved']} | {r['total_net_x4']} | "
                f"{r['median_net_x4']} | {r['pf_x4']} | {r['win_rate_x4']} |"
            )
    else:
        lines.append("| none | 0 | 0 | 0 | 0 | 0 |")

    lines += [
        "",
        "## Recent annotated signals",
        "| Planned entry UTC | Session | Macro regime | Macro score | Reason |",
        "|---|---|---|---:|---|",
    ]
    for r in signals_ann[-20:]:
        lines.append(
            f"| {r.get('planned_entry_utc','')} | {r.get('session_utc','')} | "
            f"{r.get('macro_regime_numeric','')} | {r.get('macro_score_long_gold','')} | "
            f"{r.get('macro_regime_reason','')} |"
        )
    if not signals_ann:
        lines.append("| none | none | none | 0 | no Stage 8D signal yet |")

    lines += [
        "",
        "## Interpretation",
        "- Stage 9C did not justify a macro block/allow rule yet.",
        "- Numeric macro context should be monitored and reported, not used to modify EA entries.",
        "- Hostile numeric regime has too few historical candidate trades and was not bad enough to justify blocking.",
        "- Event/shock windows remain separate from numeric regime and must be handled in the event layer.",
        "",
        "## Decision",
        "- No EA change.",
        "- No macro guard yet.",
        "- Continue Stage 8D forward-shadow logging and report macro context alongside each signal/outcome.",
    ]

    (out_dir / "stage9d_macro_aware_forward_shadow_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("Stage 9D macro-aware forward shadow report: DONE")
    print(f"macro_regime_rows={len(regimes)} signals={len(signals)} outcomes={len(outcomes)}")
    print(f"Report: {out_dir / 'stage9d_macro_aware_forward_shadow_report.md'}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--db", default=str(DEFAULT_DB))
    p.add_argument("--signals-csv", default=str(DEFAULT_SIGNALS))
    p.add_argument("--outcomes-csv", default=str(DEFAULT_OUTCOMES))
    p.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    args = p.parse_args()
    return run(Path(args.db), Path(args.signals_csv).expanduser(), Path(args.outcomes_csv), Path(args.out_dir))


if __name__ == "__main__":
    raise SystemExit(main())
