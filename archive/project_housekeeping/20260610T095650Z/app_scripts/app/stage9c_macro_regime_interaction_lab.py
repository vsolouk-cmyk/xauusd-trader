#!/usr/bin/env python3
"""
Stage 9C — Macro Regime Interaction Lab

Purpose:
- Convert imported FRED macro numeric observations into daily macro regime features.
- Annotate Stage 8B trades and Stage 8D forward-shadow signals with those regimes.
- Test whether the Stage 8D/8B technical candidate behaves differently under:
  supportive / hostile / mixed / neutral macro environments.

Inputs:
- data/local/xauusd_local_store.sqlite
  table macro_numeric_observations
- data/reports/stage8b_single_regime_thesis_lab/stage8b_single_regime_trades.csv
- optional Stage 8D signal CSV

Outputs:
- data/reports/stage9c_macro_regime_interaction_lab/stage9c_macro_regime_interaction_lab.md
- data/reports/stage9c_macro_regime_interaction_lab/stage9c_macro_daily_regimes.csv
- data/reports/stage9c_macro_regime_interaction_lab/stage9c_stage8b_candidate_macro_summary.csv
- data/reports/stage9c_macro_regime_interaction_lab/stage9c_stage8b_trades_macro_annotated.csv
- data/reports/stage9c_macro_regime_interaction_lab/stage9c_stage8d_signals_macro_annotated.csv
- local SQLite table macro_daily_regime

Hard rules:
- Research only.
- No trading signal execution.
- No EA change.
- No demo/paper/live authorization.
"""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from statistics import median
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


TOOL_VERSION = "v1"
DEFAULT_DB = Path("data/local/xauusd_local_store.sqlite")
DEFAULT_STAGE8B_TRADES = Path("data/reports/stage8b_single_regime_thesis_lab/stage8b_single_regime_trades.csv")
DEFAULT_STAGE8D_SIGNALS = Path("~/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/users/user/AppData/Roaming/MetaQuotes/Terminal/Common/Files/XAUUSD_DryRun_v2_regime_shadow_signals.csv").expanduser()
DEFAULT_OUT_DIR = Path("data/reports/stage9c_macro_regime_interaction_lab")

BASE_COST_X4_FIELD = "net_x4"


@dataclass
class DailyMacroRegime:
    obs_date: str
    real_yield_10y: Optional[float]
    nominal_yield_10y: Optional[float]
    nominal_yield_2y: Optional[float]
    usd_index: Optional[float]
    wti: Optional[float]
    brent: Optional[float]
    cpi: Optional[float]
    ppi: Optional[float]
    fedfunds: Optional[float]
    d_real_yield_5d: Optional[float]
    d_real_yield_20d: Optional[float]
    d_usd_5d_pct: Optional[float]
    d_usd_20d_pct: Optional[float]
    d_oil_5d_pct: Optional[float]
    d_oil_20d_pct: Optional[float]
    yield_curve_10y2y: Optional[float]
    rate_pressure_score: float
    usd_pressure_score: float
    oil_inflation_pressure_score: float
    growth_fear_score: float
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


def safe_float(v, default: float = 0.0) -> float:
    try:
        if v is None or str(v).strip() == "":
            return default
        return float(str(v).strip())
    except Exception:
        return default


def pct_change(now: Optional[float], prev: Optional[float]) -> Optional[float]:
    if now is None or prev is None or prev == 0:
        return None
    return 100.0 * (now - prev) / abs(prev)


def diff(now: Optional[float], prev: Optional[float]) -> Optional[float]:
    if now is None or prev is None:
        return None
    return now - prev


def score_pos_neg(value: Optional[float], pos_thr: float, neg_thr: float, pos_score: float = 1.0, neg_score: float = -1.0) -> float:
    if value is None:
        return 0.0
    if value >= pos_thr:
        return pos_score
    if value <= neg_thr:
        return neg_score
    return 0.0


def classify_macro(score: float) -> str:
    if score >= 2.0:
        return "supportive"
    if score <= -2.0:
        return "hostile"
    if abs(score) >= 0.75:
        return "mixed"
    return "neutral"


def connect_db(path: Path) -> sqlite3.Connection:
    if not path.exists():
        raise FileNotFoundError(f"DB not found: {path}")
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def load_macro_observations(conn: sqlite3.Connection) -> Dict[str, Dict[str, float]]:
    """
    Returns date -> series_id -> value from macro_numeric_observations.
    """
    rows = conn.execute("""
        SELECT series_id, obs_date, value
        FROM macro_numeric_observations
        WHERE value IS NOT NULL
        ORDER BY obs_date ASC
    """).fetchall()
    by_date: Dict[str, Dict[str, float]] = {}
    for r in rows:
        d = str(r["obs_date"])[:10]
        by_date.setdefault(d, {})[str(r["series_id"])] = float(r["value"])
    return by_date


def date_range(start: date, end: date) -> Iterable[date]:
    cur = start
    while cur <= end:
        yield cur
        cur += timedelta(days=1)


def ffill_series(raw: Dict[str, Dict[str, float]]) -> Dict[str, Dict[str, Optional[float]]]:
    if not raw:
        return {}
    start = min(datetime.strptime(d, "%Y-%m-%d").date() for d in raw)
    end = max(datetime.strptime(d, "%Y-%m-%d").date() for d in raw)
    series_ids = sorted({sid for vals in raw.values() for sid in vals.keys()})
    last: Dict[str, Optional[float]] = {sid: None for sid in series_ids}
    out: Dict[str, Dict[str, Optional[float]]] = {}
    for d in date_range(start, end):
        ds = d.isoformat()
        if ds in raw:
            for sid, val in raw[ds].items():
                last[sid] = val
        out[ds] = dict(last)
    return out


def value_n_days_back(ff: Dict[str, Dict[str, Optional[float]]], ds: str, sid: str, n: int) -> Optional[float]:
    d = datetime.strptime(ds, "%Y-%m-%d").date() - timedelta(days=n)
    while d >= datetime.strptime(min(ff.keys()), "%Y-%m-%d").date():
        key = d.isoformat()
        if key in ff and ff[key].get(sid) is not None:
            return ff[key].get(sid)
        d -= timedelta(days=1)
    return None


def build_daily_regimes(ff: Dict[str, Dict[str, Optional[float]]]) -> List[DailyMacroRegime]:
    regimes: List[DailyMacroRegime] = []

    for ds in sorted(ff.keys()):
        row = ff[ds]
        dfii10 = row.get("DFII10")
        dgs10 = row.get("DGS10")
        dgs2 = row.get("DGS2")
        usd = row.get("DTWEXBGS")
        wti = row.get("DCOILWTICO")
        brent = row.get("DCOILBRENTEU")
        cpi = row.get("CPIAUCSL")
        ppi = row.get("PPIACO")
        fedfunds = row.get("FEDFUNDS")

        dfii10_5 = value_n_days_back(ff, ds, "DFII10", 5)
        dfii10_20 = value_n_days_back(ff, ds, "DFII10", 20)
        usd_5 = value_n_days_back(ff, ds, "DTWEXBGS", 5)
        usd_20 = value_n_days_back(ff, ds, "DTWEXBGS", 20)
        wti_5 = value_n_days_back(ff, ds, "DCOILWTICO", 5)
        wti_20 = value_n_days_back(ff, ds, "DCOILWTICO", 20)

        d_real_5 = diff(dfii10, dfii10_5)
        d_real_20 = diff(dfii10, dfii10_20)
        d_usd_5 = pct_change(usd, usd_5)
        d_usd_20 = pct_change(usd, usd_20)
        d_oil_5 = pct_change(wti, wti_5)
        d_oil_20 = pct_change(wti, wti_20)
        yc = diff(dgs10, dgs2)

        # Gold-long macro logic:
        # Rising real yield = hostile to gold.
        # Falling real yield = supportive to gold.
        rate_pressure = 0.0
        rate_pressure += score_pos_neg(d_real_5, pos_thr=0.12, neg_thr=-0.12, pos_score=-1.0, neg_score=1.0)
        rate_pressure += score_pos_neg(d_real_20, pos_thr=0.25, neg_thr=-0.25, pos_score=-1.0, neg_score=1.0)

        # Strong USD = hostile; weak USD = supportive.
        usd_pressure = 0.0
        usd_pressure += score_pos_neg(d_usd_5, pos_thr=0.8, neg_thr=-0.8, pos_score=-1.0, neg_score=1.0)
        usd_pressure += score_pos_neg(d_usd_20, pos_thr=1.5, neg_thr=-1.5, pos_score=-1.0, neg_score=1.0)

        # Oil jump can be mixed/hostile through inflation/Fed pressure.
        # Oil fall is mildly supportive if it reduces inflation pressure.
        oil_pressure = 0.0
        oil_pressure += score_pos_neg(d_oil_5, pos_thr=5.0, neg_thr=-5.0, pos_score=-0.75, neg_score=0.5)
        oil_pressure += score_pos_neg(d_oil_20, pos_thr=10.0, neg_thr=-10.0, pos_score=-0.75, neg_score=0.5)

        # Inverted/worsening curve can proxy growth fear; this is supportive for gold if rates/USD do not dominate.
        growth_fear = 0.0
        if yc is not None and yc < -0.45:
            growth_fear += 0.5
        if yc is not None and yc > 0.50:
            growth_fear -= 0.25

        macro_score = rate_pressure + usd_pressure + oil_pressure + growth_fear

        reasons = []
        for name, val in [
            ("rate", rate_pressure),
            ("usd", usd_pressure),
            ("oil", oil_pressure),
            ("growth", growth_fear),
        ]:
            if val:
                reasons.append(f"{name}={round(val, 3)}")
        if not reasons:
            reasons.append("no_material_numeric_pressure")

        regimes.append(DailyMacroRegime(
            obs_date=ds,
            real_yield_10y=dfii10,
            nominal_yield_10y=dgs10,
            nominal_yield_2y=dgs2,
            usd_index=usd,
            wti=wti,
            brent=brent,
            cpi=cpi,
            ppi=ppi,
            fedfunds=fedfunds,
            d_real_yield_5d=d_real_5,
            d_real_yield_20d=d_real_20,
            d_usd_5d_pct=d_usd_5,
            d_usd_20d_pct=d_usd_20,
            d_oil_5d_pct=d_oil_5,
            d_oil_20d_pct=d_oil_20,
            yield_curve_10y2y=yc,
            rate_pressure_score=round(rate_pressure, 6),
            usd_pressure_score=round(usd_pressure, 6),
            oil_inflation_pressure_score=round(oil_pressure, 6),
            growth_fear_score=round(growth_fear, 6),
            macro_score_long_gold=round(macro_score, 6),
            macro_regime=classify_macro(macro_score),
            regime_reason=";".join(reasons),
        ))
    return regimes


def ensure_macro_daily_table(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS macro_daily_regime (
            obs_date TEXT PRIMARY KEY,
            real_yield_10y REAL,
            nominal_yield_10y REAL,
            nominal_yield_2y REAL,
            usd_index REAL,
            wti REAL,
            brent REAL,
            cpi REAL,
            ppi REAL,
            fedfunds REAL,
            d_real_yield_5d REAL,
            d_real_yield_20d REAL,
            d_usd_5d_pct REAL,
            d_usd_20d_pct REAL,
            d_oil_5d_pct REAL,
            d_oil_20d_pct REAL,
            yield_curve_10y2y REAL,
            rate_pressure_score REAL,
            usd_pressure_score REAL,
            oil_inflation_pressure_score REAL,
            growth_fear_score REAL,
            macro_score_long_gold REAL,
            macro_regime TEXT,
            regime_reason TEXT,
            generated_utc TEXT
        )
    """)
    conn.commit()


def upsert_daily_regimes(conn: sqlite3.Connection, regimes: Sequence[DailyMacroRegime]) -> int:
    ensure_macro_daily_table(conn)
    gen = now_iso()
    n = 0
    for r in regimes:
        conn.execute("""
            INSERT OR REPLACE INTO macro_daily_regime (
                obs_date, real_yield_10y, nominal_yield_10y, nominal_yield_2y, usd_index,
                wti, brent, cpi, ppi, fedfunds,
                d_real_yield_5d, d_real_yield_20d, d_usd_5d_pct, d_usd_20d_pct,
                d_oil_5d_pct, d_oil_20d_pct, yield_curve_10y2y,
                rate_pressure_score, usd_pressure_score, oil_inflation_pressure_score,
                growth_fear_score, macro_score_long_gold, macro_regime, regime_reason, generated_utc
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            r.obs_date, r.real_yield_10y, r.nominal_yield_10y, r.nominal_yield_2y, r.usd_index,
            r.wti, r.brent, r.cpi, r.ppi, r.fedfunds,
            r.d_real_yield_5d, r.d_real_yield_20d, r.d_usd_5d_pct, r.d_usd_20d_pct,
            r.d_oil_5d_pct, r.d_oil_20d_pct, r.yield_curve_10y2y,
            r.rate_pressure_score, r.usd_pressure_score, r.oil_inflation_pressure_score,
            r.growth_fear_score, r.macro_score_long_gold, r.macro_regime, r.regime_reason, gen,
        ))
        n += 1
    conn.commit()
    return n


def write_csv(path: Path, rows: Sequence[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    cols = list(rows[0].keys()) if rows else ["empty"]
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def load_csv(path: Path) -> List[dict]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    if not text.strip():
        return []
    return list(csv.DictReader(text.splitlines()))


def regime_lookup(regimes: Sequence[DailyMacroRegime]) -> Dict[str, DailyMacroRegime]:
    return {r.obs_date: r for r in regimes}


def row_time_to_date(row: dict) -> Optional[str]:
    for key in ("entry_utc", "planned_entry_utc", "signal_closed_h1_utc", "signal_utc"):
        t = parse_time(row.get(key, ""))
        if t is not None:
            return t.date().isoformat()
    return None


def annotate_rows(rows: Sequence[dict], regimes: Sequence[DailyMacroRegime]) -> List[dict]:
    lookup = regime_lookup(regimes)
    out: List[dict] = []
    for row in rows:
        d = row_time_to_date(row)
        r = lookup.get(d or "")
        new = dict(row)
        if r is None:
            new.update({
                "macro_obs_date": d or "",
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
            new.update({
                "macro_obs_date": r.obs_date,
                "macro_regime_numeric": r.macro_regime,
                "macro_score_long_gold": r.macro_score_long_gold,
                "macro_regime_reason": r.regime_reason,
                "real_yield_10y": r.real_yield_10y,
                "usd_index": r.usd_index,
                "wti": r.wti,
                "d_real_yield_5d": r.d_real_yield_5d,
                "d_usd_5d_pct": r.d_usd_5d_pct,
                "d_oil_5d_pct": r.d_oil_5d_pct,
            })
        out.append(new)
    return out


def profit_factor(vals: Sequence[float]) -> float:
    wins = sum(v for v in vals if v > 0)
    losses = abs(sum(v for v in vals if v < 0))
    if losses == 0:
        return 999.0 if wins > 0 else 0.0
    return round(wins / losses, 6)


def max_drawdown(vals: Sequence[float]) -> float:
    eq = 0.0
    peak = 0.0
    dd = 0.0
    for v in vals:
        eq += v
        peak = max(peak, eq)
        dd = min(dd, eq - peak)
    return round(dd, 6)


def summarize_trades(rows: Sequence[dict], net_field: str = BASE_COST_X4_FIELD) -> List[dict]:
    groups: Dict[Tuple[str, str, str, str], List[dict]] = {}
    for row in rows:
        # Focus summary by candidate definition/guard/geometry and macro regime.
        definition = row.get("definition", "unknown")
        guard = row.get("guard_variant", "unknown")
        geometry = row.get("geometry", "unknown")
        macro = row.get("macro_regime_numeric", "unknown")
        key = (definition, guard, geometry, macro)
        groups.setdefault(key, []).append(row)

    summary: List[dict] = []
    for (definition, guard, geometry, macro), rs in groups.items():
        vals = [safe_float(r.get(net_field), 0.0) for r in rs]
        if not vals:
            continue
        wins = [v for v in vals if v > 0]
        summary.append({
            "definition": definition,
            "guard_variant": guard,
            "geometry": geometry,
            "macro_regime_numeric": macro,
            "trades": len(vals),
            "total_net_x4": round(sum(vals), 6),
            "median_net_x4": round(median(vals), 6),
            "pf_x4": profit_factor(vals),
            "win_rate_x4": round(len(wins) / len(vals), 6),
            "max_dd_x4": max_drawdown(vals),
        })

    summary.sort(key=lambda r: (r["definition"], r["guard_variant"], r["geometry"], -r["total_net_x4"]))
    return summary


def filter_stage8d_candidate(rows: Sequence[dict]) -> List[dict]:
    """
    Keep rows closest to the selected v2 candidate:
    liquidity_session / nonoverlap / time_exit_12h.
    """
    out = []
    for r in rows:
        if r.get("definition") != "liquidity_session":
            continue
        if "nonoverlap" not in r.get("guard_variant", ""):
            continue
        if r.get("geometry") != "time_exit_12h":
            continue
        out.append(r)
    return out


def write_outputs(
    out_dir: Path,
    payload: dict,
    regimes: Sequence[DailyMacroRegime],
    stage8b_annotated: Sequence[dict],
    stage8b_summary_all: Sequence[dict],
    stage8b_summary_candidate: Sequence[dict],
    stage8d_annotated: Sequence[dict],
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    write_csv(out_dir / "stage9c_macro_daily_regimes.csv", [asdict(r) for r in regimes])
    write_csv(out_dir / "stage9c_stage8b_trades_macro_annotated.csv", stage8b_annotated)
    write_csv(out_dir / "stage9c_stage8b_all_macro_summary.csv", stage8b_summary_all)
    write_csv(out_dir / "stage9c_stage8b_candidate_macro_summary.csv", stage8b_summary_candidate)
    write_csv(out_dir / "stage9c_stage8d_signals_macro_annotated.csv", stage8d_annotated)

    payload["daily_regime_counts"] = {}
    for r in regimes:
        payload["daily_regime_counts"][r.macro_regime] = payload["daily_regime_counts"].get(r.macro_regime, 0) + 1
    payload["stage8b_candidate_macro_summary"] = list(stage8b_summary_candidate)
    (out_dir / "stage9c_macro_regime_interaction_lab.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [
        "# Stage 9C Macro Regime Interaction Lab",
        "",
        f"Generated UTC: `{payload['generated_utc']}`",
        f"Tool version: `{TOOL_VERSION}`",
        "",
        "> Hard rule: research only. This does not authorize demo, paper, or live orders.",
        "",
        "## Inputs",
        f"- db: `{payload['db_path']}`",
        f"- macro_numeric_rows: `{payload['macro_numeric_rows']}`",
        f"- daily_regime_rows: `{len(regimes)}`",
        f"- stage8b_trades_loaded: `{payload['stage8b_trades_loaded']}`",
        f"- stage8b_candidate_trades_loaded: `{payload['stage8b_candidate_trades_loaded']}`",
        f"- stage8d_signals_loaded: `{payload['stage8d_signals_loaded']}`",
        "",
        "## Daily numeric macro regime coverage",
        "| Macro regime | Days |",
        "|---|---:|",
    ]
    for k, v in sorted(payload["daily_regime_counts"].items()):
        lines.append(f"| {k} | {v} |")

    lines += [
        "",
        "## Stage 8D candidate family × numeric macro regime",
        "Candidate filter used here:",
        "",
        "```text",
        "definition = liquidity_session",
        "guard_variant contains nonoverlap",
        "geometry = time_exit_12h",
        "```",
        "",
        "| Definition | Guard | Geometry | Macro regime | Trades | Total x4 | Median x4 | PF x4 | WR x4 | DD x4 |",
        "|---|---|---|---|---:|---:|---:|---:|---:|---:|",
    ]

    if stage8b_summary_candidate:
        for r in stage8b_summary_candidate:
            lines.append(
                f"| {r['definition']} | {r['guard_variant']} | {r['geometry']} | {r['macro_regime_numeric']} | "
                f"{r['trades']} | {r['total_net_x4']} | {r['median_net_x4']} | {r['pf_x4']} | "
                f"{r['win_rate_x4']} | {r['max_dd_x4']} |"
            )
    else:
        lines.append("| none | none | none | none | 0 | 0 | 0 | 0 | 0 | 0 |")

    lines += [
        "",
        "## Scoring model",
        "For long-gold bias:",
        "",
        "```text",
        "macro_score = rate_pressure + usd_pressure + oil_inflation_pressure + growth_fear",
        "",
        "rising real yield  -> hostile",
        "falling real yield -> supportive",
        "strong USD         -> hostile",
        "weak USD           -> supportive",
        "oil spike          -> mixed/hostile via inflation/Fed pressure",
        "deeply inverted curve -> mild growth-fear support",
        "```",
        "",
        "## Interpretation rules",
        "- If supportive/mixed regimes improve PF, median and drawdown without destroying trade count, macro is useful as a guard.",
        "- If macro segmentation only removes trades without improving robustness, it is filter-mining and should be rejected.",
        "- This stage uses numeric macro pressure only. Scheduled event/shock windows remain a separate layer.",
        "",
        "## Decision",
        "- No EA/order workflow changes are allowed from Stage 9C alone.",
        "- If a regime interaction is strong, Stage 9D should create a macro-aware forward-shadow report, not order execution.",
    ]

    (out_dir / "stage9c_macro_regime_interaction_lab.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--db", default=str(DEFAULT_DB))
    p.add_argument("--stage8b-trades", default=str(DEFAULT_STAGE8B_TRADES))
    p.add_argument("--stage8d-signals", default=str(DEFAULT_STAGE8D_SIGNALS))
    p.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    args = p.parse_args()

    db_path = Path(args.db)
    out_dir = Path(args.out_dir)

    conn = connect_db(db_path)
    raw = load_macro_observations(conn)
    ff = ffill_series(raw)
    regimes = build_daily_regimes(ff)
    upserted = upsert_daily_regimes(conn, regimes)
    macro_numeric_rows = conn.execute("SELECT COUNT(*) AS n FROM macro_numeric_observations").fetchone()["n"]
    conn.close()

    stage8b_rows = load_csv(Path(args.stage8b_trades))
    stage8b_annotated = annotate_rows(stage8b_rows, regimes)
    stage8b_summary_all = summarize_trades(stage8b_annotated)

    stage8b_candidate = filter_stage8d_candidate(stage8b_annotated)
    stage8b_summary_candidate = summarize_trades(stage8b_candidate)

    stage8d_rows = load_csv(Path(args.stage8d_signals).expanduser())
    stage8d_annotated = annotate_rows(stage8d_rows, regimes)

    payload = {
        "tool_version": TOOL_VERSION,
        "generated_utc": now_iso(),
        "db_path": str(db_path),
        "stage8b_trades_csv": str(Path(args.stage8b_trades)),
        "stage8d_signals_csv": str(Path(args.stage8d_signals).expanduser()),
        "macro_numeric_rows": int(macro_numeric_rows),
        "daily_regime_rows_upserted": upserted,
        "stage8b_trades_loaded": len(stage8b_rows),
        "stage8b_candidate_trades_loaded": len(stage8b_candidate),
        "stage8d_signals_loaded": len(stage8d_rows),
    }

    write_outputs(
        out_dir,
        payload,
        regimes,
        stage8b_annotated,
        stage8b_summary_all,
        stage8b_summary_candidate,
        stage8d_annotated,
    )

    print("Stage 9C macro regime interaction lab: DONE")
    print(f"macro_numeric_rows={macro_numeric_rows} daily_regimes={len(regimes)} stage8b_trades={len(stage8b_rows)} candidate_trades={len(stage8b_candidate)} stage8d_signals={len(stage8d_rows)}")
    print(f"Report: {out_dir / 'stage9c_macro_regime_interaction_lab.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
