"""Stage25A Regime / No-Trade Filter Discovery

Research/shadow diagnostic only.

Hotfix 1:
- Robust AMarkets/MT5 CSV loader for tab-separated files with headers like
  <DATE>\t<TIME>\t<OPEN>\t<HIGH>\t<LOW>\t<CLOSE>\t<TICKVOL>\t<VOL>\t<SPREAD>.
- Defensive column normalization for Stage23C trades.
- Generates a report even when some optional columns are missing.

This module does not modify Stage18A/Stage23D and does not authorize EA,
paper, live, or orders.
"""
from __future__ import annotations

import json
import math
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

PROJECT_ROOT = Path.cwd()
REPORT_DIR = PROJECT_ROOT / "data" / "reports" / "stage25a_regime_filter_discovery"
REPORT_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_M1_PATHS = [
    Path.home() / "Downloads" / "amarkets_xauusd_1m.csv",
    PROJECT_ROOT / "data" / "amarkets_xauusd_1m.csv",
    PROJECT_ROOT / "data" / "local" / "amarkets_xauusd_1m.csv",
]
DEFAULT_H1_PATHS = [
    Path.home() / "Downloads" / "amarkets_xauusd_1h.csv",
    PROJECT_ROOT / "data" / "amarkets_xauusd_1h.csv",
    PROJECT_ROOT / "data" / "local" / "amarkets_xauusd_1h.csv",
]
DEFAULT_STAGE23C_TRADES = PROJECT_ROOT / "data" / "reports" / "stage23c_promotion_candidate_validation" / "stage23c_exact_trades.csv"

ROUNDTRIP_COST_X1 = float(os.environ.get("STAGE25A_ROUNDTRIP_COST_X1", "0.35"))
MIN_EVENTS = int(os.environ.get("STAGE25A_MIN_EVENTS", "20"))
MAX_FILTERS_TO_SHOW = int(os.environ.get("STAGE25A_MAX_FILTERS_TO_SHOW", "30"))


@dataclass
class FilterResult:
    filter_name: str
    rule: str
    retained_events: int
    removed_events: int
    retained_ratio: float
    pf_x1: float
    pf_x4: float
    pf_x6: float
    total_x1: float
    total_x4: float
    total_x6: float
    win_rate_x4: float
    median_x4: float
    improvement_pf_x4: float
    decision: str


def first_existing(paths: Sequence[Path]) -> Optional[Path]:
    for p in paths:
        try:
            if p.exists() and p.is_file():
                return p
        except OSError:
            continue
    return None


def normalize_col(c: Any) -> str:
    s = str(c).strip().lower()
    s = s.replace("\ufeff", "")
    s = s.replace("<", "").replace(">", "")
    s = re.sub(r"[^a-z0-9_]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    aliases = {
        "date": "date",
        "time": "time",
        "open": "open",
        "high": "high",
        "low": "low",
        "close": "close",
        "tickvol": "tick_volume",
        "tick_volume": "tick_volume",
        "tick_volume_": "tick_volume",
        "vol": "volume",
        "real_volume": "volume",
        "spread": "spread",
    }
    return aliases.get(s, s)


def read_any_csv(path: Path, *, parse_market: bool = False) -> pd.DataFrame:
    """Read CSV/TSV robustly.

    MT5 exports often look like one CSV column if read with comma separator:
    '<DATE>\t<TIME>\t<OPEN>...'. This function detects that and re-reads with tab.
    """
    if not path.exists():
        raise FileNotFoundError(str(path))

    # Try automatic separator first, but keep a deterministic fallback list.
    attempts: List[Tuple[str, Dict[str, Any]]] = [
        ("python_sniff", {"sep": None, "engine": "python"}),
        ("tab", {"sep": "\t"}),
        ("comma", {"sep": ","}),
        ("semicolon", {"sep": ";"}),
    ]
    last_err: Optional[Exception] = None
    for _, kwargs in attempts:
        try:
            df = pd.read_csv(path, **kwargs)
            # If pandas created exactly one column and it contains tab characters,
            # force tab parsing. This fixes the reported KeyError.
            if len(df.columns) == 1 and "\t" in str(df.columns[0]):
                df = pd.read_csv(path, sep="\t")
            if len(df.columns) == 1 and df.shape[0] > 0 and isinstance(df.iloc[0, 0], str) and "\t" in df.iloc[0, 0]:
                df = pd.read_csv(path, sep="\t", header=None)
                # Promote first row to header if it looks like MT5 header.
                first_row = [str(x) for x in df.iloc[0].tolist()]
                if any("date" in x.lower() for x in first_row):
                    df.columns = first_row
                    df = df.iloc[1:].reset_index(drop=True)
            df.columns = [normalize_col(c) for c in df.columns]
            if parse_market:
                df = normalize_market_df(df, path)
            return df
        except Exception as e:  # pragma: no cover - diagnostic fallback
            last_err = e
            continue
    raise RuntimeError(f"Could not read {path}: {last_err}")


def normalize_market_df(df: pd.DataFrame, path: Path) -> pd.DataFrame:
    # Handle the exact broken-column signature if it survived.
    if len(df.columns) == 1 and "date_time_open_high_low_close" in df.columns[0]:
        df = pd.read_csv(path, sep="\t")
        df.columns = [normalize_col(c) for c in df.columns]

    # Some MT5 files use all uppercase after normalization already handled.
    required = {"open", "high", "low", "close"}
    if "date" in df.columns and "time" in df.columns:
        ts = pd.to_datetime(df["date"].astype(str).str.strip() + " " + df["time"].astype(str).str.strip(), errors="coerce", utc=True)
    else:
        time_col = pick_col(df, ["timestamp", "datetime", "time", "broker_time", "utc_time", "date_time"])
        if time_col is None:
            raise KeyError(f"No timestamp columns found in {path}; columns={list(df.columns)[:20]}")
        ts = pd.to_datetime(df[time_col], errors="coerce", utc=True)

    out = df.copy()
    out["timestamp"] = ts
    out = out.dropna(subset=["timestamp"]).copy()

    missing = sorted(required - set(out.columns))
    if missing:
        raise KeyError(f"Missing OHLC columns in {path}: {missing}; columns={list(out.columns)[:20]}")

    for c in ["open", "high", "low", "close", "tick_volume", "volume", "spread"]:
        if c in out.columns:
            out[c] = pd.to_numeric(out[c], errors="coerce")
    out = out.dropna(subset=["open", "high", "low", "close"]).copy()
    out = out.sort_values("timestamp").drop_duplicates("timestamp", keep="last").reset_index(drop=True)
    return out[[c for c in ["timestamp", "open", "high", "low", "close", "tick_volume", "volume", "spread"] if c in out.columns]]


def pick_col(df: pd.DataFrame, names: Iterable[str]) -> Optional[str]:
    cols = list(df.columns)
    for name in names:
        if name in cols:
            return name
    # fuzzy fallback
    for name in names:
        for c in cols:
            if name in c:
                return c
    return None


def safe_float(v: Any, default: float = 0.0) -> float:
    try:
        if pd.isna(v):
            return default
        return float(v)
    except Exception:
        return default


def profit_factor(values: Sequence[float]) -> float:
    vals = np.asarray([safe_float(v) for v in values], dtype=float)
    if vals.size == 0:
        return 0.0
    wins = vals[vals > 0].sum()
    losses = -vals[vals < 0].sum()
    if losses <= 1e-12:
        return float("inf") if wins > 0 else 0.0
    return float(wins / losses)


def summarize_pnl(df: pd.DataFrame, x1_col: str, x4_col: str, x6_col: Optional[str] = None) -> Dict[str, float]:
    if df.empty:
        return {
            "events": 0, "pf_x1": 0.0, "pf_x4": 0.0, "pf_x6": 0.0,
            "total_x1": 0.0, "total_x4": 0.0, "total_x6": 0.0,
            "win_rate_x4": 0.0, "median_x4": 0.0,
        }
    x1 = pd.to_numeric(df[x1_col], errors="coerce").fillna(0.0).to_numpy()
    x4 = pd.to_numeric(df[x4_col], errors="coerce").fillna(0.0).to_numpy()
    if x6_col and x6_col in df.columns:
        x6 = pd.to_numeric(df[x6_col], errors="coerce").fillna(0.0).to_numpy()
    else:
        # Approximate x6 from x1 if no explicit x6 exists. A 5x extra-cost penalty
        # relative to x1 is conservative for filtering diagnostics.
        x6 = x1 - (ROUNDTRIP_COST_X1 * 5.0)
    return {
        "events": int(len(df)),
        "pf_x1": profit_factor(x1),
        "pf_x4": profit_factor(x4),
        "pf_x6": profit_factor(x6),
        "total_x1": float(np.sum(x1)),
        "total_x4": float(np.sum(x4)),
        "total_x6": float(np.sum(x6)),
        "win_rate_x4": float(np.mean(x4 > 0)) if len(x4) else 0.0,
        "median_x4": float(np.median(x4)) if len(x4) else 0.0,
    }


def normalize_trades(df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, str]]:
    original_cols = list(df.columns)
    df = df.copy()
    df.columns = [normalize_col(c) for c in df.columns]

    ts_col = pick_col(df, [
        "entry_time", "entry_ts", "entry_timestamp", "entry_bar_time", "signal_time",
        "open_time", "timestamp", "time", "broker_time", "utc_time",
    ])
    if ts_col is None:
        raise KeyError(f"No entry timestamp column found in Stage23C trades. columns={original_cols}")
    df["entry_timestamp"] = pd.to_datetime(df[ts_col], errors="coerce", utc=True)
    df = df.dropna(subset=["entry_timestamp"]).copy()

    direction_col = pick_col(df, ["direction", "side", "signal_direction", "trade_direction"])
    if direction_col is not None:
        df["direction_norm"] = df[direction_col].astype(str).str.lower().str.strip()
    else:
        df["direction_norm"] = "unknown"

    x1_col = pick_col(df, ["net_x1", "pnl_x1", "ret_x1", "profit_x1", "total_x1", "r_x1", "pnl", "net", "profit"])
    x4_col = pick_col(df, ["net_x4", "pnl_x4", "ret_x4", "profit_x4", "total_x4", "r_x4"])
    x6_col = pick_col(df, ["net_x6", "pnl_x6", "ret_x6", "profit_x6", "total_x6", "r_x6"])

    # If Stage23C only produced x1, derive x4/x6 consistently for diagnostics.
    if x1_col is None:
        # Last-resort: use outcome/net column if available after fuzzy matching.
        numeric_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
        if not numeric_cols:
            raise KeyError(f"No PnL column found in Stage23C trades. columns={original_cols}")
        x1_col = numeric_cols[-1]

    df["pnl_x1_norm"] = pd.to_numeric(df[x1_col], errors="coerce").fillna(0.0)
    if x4_col is not None:
        df["pnl_x4_norm"] = pd.to_numeric(df[x4_col], errors="coerce").fillna(0.0)
    else:
        # x4 means 4x assumed roundtrip cost. If x1 already contains 1x cost,
        # subtract the additional 3x cost.
        df["pnl_x4_norm"] = df["pnl_x1_norm"] - (ROUNDTRIP_COST_X1 * 3.0)
    if x6_col is not None:
        df["pnl_x6_norm"] = pd.to_numeric(df[x6_col], errors="coerce").fillna(0.0)
    else:
        df["pnl_x6_norm"] = df["pnl_x1_norm"] - (ROUNDTRIP_COST_X1 * 5.0)

    return df, {"timestamp": ts_col, "direction": direction_col or "", "x1": x1_col, "x4": x4_col or "derived", "x6": x6_col or "derived"}


def build_m15(m1: pd.DataFrame) -> pd.DataFrame:
    df = m1.set_index("timestamp").sort_index()
    m15 = df.resample("15min").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna().reset_index()
    return m15


def session_features(m15: pd.DataFrame) -> pd.DataFrame:
    df = m15.copy()
    df["date"] = df["timestamp"].dt.date
    df["hour"] = df["timestamp"].dt.hour
    df["rng"] = df["high"] - df["low"]

    daily = df.groupby("date").agg(
        day_open=("open", "first"), day_high=("high", "max"), day_low=("low", "min"), day_close=("close", "last")
    ).reset_index()
    daily["day_range"] = daily["day_high"] - daily["day_low"]
    daily["day_dir"] = np.sign(daily["day_close"] - daily["day_open"])
    daily["prior_day_range"] = daily["day_range"].shift(1)
    daily["prior_day_dir"] = daily["day_dir"].shift(1)
    daily["prior_day_close"] = daily["day_close"].shift(1)

    asia = df[(df["hour"] >= 0) & (df["hour"] < 7)].groupby("date").agg(
        asia_open=("open", "first"), asia_high=("high", "max"), asia_low=("low", "min"), asia_close=("close", "last")
    ).reset_index()
    asia["asia_range"] = asia["asia_high"] - asia["asia_low"]
    asia["asia_dir"] = np.sign(asia["asia_close"] - asia["asia_open"])

    london = df[(df["hour"] >= 7) & (df["hour"] < 13)].groupby("date").agg(
        london_open=("open", "first"), london_high=("high", "max"), london_low=("low", "min"), london_close=("close", "last")
    ).reset_index()
    london["london_range"] = london["london_high"] - london["london_low"]
    london["london_move"] = london["london_close"] - london["london_open"]
    london["london_dir"] = np.sign(london["london_move"])
    london["london_eff"] = london["london_move"].abs() / london["london_range"].replace(0, np.nan)

    early_ny = df[(df["hour"] >= 13) & (df["hour"] < 15)].groupby("date").agg(
        early_ny_high=("high", "max"), early_ny_low=("low", "min")
    ).reset_index()
    early_ny["early_ny_range"] = early_ny["early_ny_high"] - early_ny["early_ny_low"]

    feats = daily.merge(asia, on="date", how="left").merge(london, on="date", how="left").merge(early_ny, on="date", how="left")
    return feats


def enrich_trades(trades: pd.DataFrame, feats: pd.DataFrame) -> pd.DataFrame:
    out = trades.copy()
    out["date"] = out["entry_timestamp"].dt.date
    out = out.merge(feats, on="date", how="left")

    direction_map = {"long": 1, "buy": 1, "short": -1, "sell": -1}
    out["trade_dir_num"] = out["direction_norm"].map(direction_map).fillna(0).astype(int)
    out["align_london"] = np.where((out["trade_dir_num"] != 0) & out["london_dir"].notna(), out["trade_dir_num"] == out["london_dir"], np.nan)
    out["align_prior_day"] = np.where((out["trade_dir_num"] != 0) & out["prior_day_dir"].notna(), out["trade_dir_num"] == out["prior_day_dir"], np.nan)
    out["entry_hour"] = out["entry_timestamp"].dt.hour
    return out


def qcut_flags(series: pd.Series, prefix: str) -> List[Tuple[str, pd.Series]]:
    s = pd.to_numeric(series, errors="coerce")
    flags: List[Tuple[str, pd.Series]] = []
    if s.notna().sum() < MIN_EVENTS * 2:
        return flags
    q20, q30, q70, q80 = s.quantile([0.2, 0.3, 0.7, 0.8]).tolist()
    flags.extend([
        (f"{prefix}_drop_low20", s >= q20),
        (f"{prefix}_drop_low30", s >= q30),
        (f"{prefix}_drop_high20", s <= q80),
        (f"{prefix}_drop_high30", s <= q70),
        (f"{prefix}_middle_20_80", (s >= q20) & (s <= q80)),
        (f"{prefix}_middle_30_70", (s >= q30) & (s <= q70)),
    ])
    return flags


def generate_filter_masks(df: pd.DataFrame) -> List[Tuple[str, str, pd.Series]]:
    masks: List[Tuple[str, str, pd.Series]] = []
    for col in ["prior_day_range", "asia_range", "london_range", "london_eff", "early_ny_range"]:
        if col in df.columns:
            for name, mask in qcut_flags(df[col], col):
                masks.append((name, f"keep rows satisfying {name}", mask.fillna(False)))

    if "align_london" in df.columns:
        masks.append(("keep_london_aligned", "trade direction aligned with London move", df["align_london"].fillna(False).astype(bool)))
        masks.append(("drop_london_aligned", "trade direction not aligned with London move", (~df["align_london"].fillna(False).astype(bool))))
    if "align_prior_day" in df.columns:
        masks.append(("keep_prior_day_aligned", "trade direction aligned with prior-day direction", df["align_prior_day"].fillna(False).astype(bool)))
        masks.append(("drop_prior_day_aligned", "trade direction not aligned with prior-day direction", (~df["align_prior_day"].fillna(False).astype(bool))))
    if "direction_norm" in df.columns:
        masks.append(("keep_long_only", "long-only diagnostic", df["direction_norm"].isin(["long", "buy"])))
        masks.append(("keep_short_only", "short-only diagnostic", df["direction_norm"].isin(["short", "sell"])))
    if "entry_hour" in df.columns:
        for h in sorted(df["entry_hour"].dropna().unique().tolist()):
            if pd.notna(h):
                masks.append((f"keep_entry_hour_{int(h)}", f"entry hour equals {int(h)}", df["entry_hour"] == h))
    # Year-only diagnostic, not an operational filter.
    if "entry_timestamp" in df.columns:
        years = sorted(df["entry_timestamp"].dt.year.dropna().unique().tolist())
        for y in years:
            masks.append((f"diagnostic_drop_year_{int(y)}", f"diagnostic only: exclude year {int(y)}", df["entry_timestamp"].dt.year != y))
    return masks


def evaluate_filters(df: pd.DataFrame, base: Dict[str, float]) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    for filter_name, rule, mask in generate_filter_masks(df):
        keep = df[mask.fillna(False).astype(bool)].copy()
        if len(keep) < MIN_EVENTS:
            continue
        s = summarize_pnl(keep, "pnl_x1_norm", "pnl_x4_norm", "pnl_x6_norm")
        improvement = s["pf_x4"] - base.get("pf_x4", 0.0)
        if s["pf_x4"] >= 1.25 and s["pf_x6"] >= 1.0 and improvement >= 0.15 and len(keep) >= MIN_EVENTS:
            decision = "STAGE25A_FILTER_CANDIDATE_REVIEW_ONLY"
        elif s["pf_x4"] > base.get("pf_x4", 0.0) and s["pf_x4"] >= 1.0 and len(keep) >= MIN_EVENTS:
            decision = "STAGE25A_KEEP_WATCHLIST_ONLY"
        else:
            decision = "STAGE25A_REJECT"
        rows.append({
            "decision": decision,
            "filter_name": filter_name,
            "rule": rule,
            "retained_events": int(len(keep)),
            "removed_events": int(len(df) - len(keep)),
            "retained_ratio": round(float(len(keep) / max(1, len(df))), 4),
            "pf_x1": s["pf_x1"],
            "pf_x4": s["pf_x4"],
            "pf_x6": s["pf_x6"],
            "total_x1": s["total_x1"],
            "total_x4": s["total_x4"],
            "total_x6": s["total_x6"],
            "win_rate_x4": s["win_rate_x4"],
            "median_x4": s["median_x4"],
            "improvement_pf_x4": improvement,
        })
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out = out.sort_values(["decision", "pf_x4", "pf_x6", "retained_events"], ascending=[True, False, False, False]).reset_index(drop=True)
    # Put review/watchlist above rejects in a stable way.
    order = {"STAGE25A_FILTER_CANDIDATE_REVIEW_ONLY": 0, "STAGE25A_KEEP_WATCHLIST_ONLY": 1, "STAGE25A_REJECT": 2}
    out["_order"] = out["decision"].map(order).fillna(9)
    out = out.sort_values(["_order", "pf_x4", "pf_x6", "retained_events"], ascending=[True, False, False, False]).drop(columns=["_order"]).reset_index(drop=True)
    return out


def md_fmt(v: Any) -> str:
    if isinstance(v, float):
        if math.isinf(v):
            return "inf"
        if math.isnan(v):
            return ""
        return f"{v:.4f}".rstrip("0").rstrip(".")
    if isinstance(v, (list, tuple, set)):
        return ", ".join(str(x) for x in v)
    if isinstance(v, dict):
        return json.dumps(v, ensure_ascii=False)
    if pd.isna(v):
        return ""
    return str(v)


def markdown_table(df: pd.DataFrame, cols: Sequence[str], limit: int = 20) -> str:
    if df is None or df.empty:
        return "No rows."
    show = df[[c for c in cols if c in df.columns]].head(limit).copy()
    if show.empty:
        return "No rows."
    lines = ["| " + " | ".join(show.columns) + " |", "| " + " | ".join(["---"] * len(show.columns)) + " |"]
    for _, row in show.iterrows():
        lines.append("| " + " | ".join(md_fmt(row[c]) for c in show.columns) + " |")
    return "\n".join(lines)


def render_report(report: Dict[str, Any], base: Dict[str, float], filters: pd.DataFrame, source_cols: Dict[str, str]) -> str:
    if not filters.empty:
        candidate_count = int((filters["decision"] == "STAGE25A_FILTER_CANDIDATE_REVIEW_ONLY").sum())
        watch_count = int((filters["decision"] == "STAGE25A_KEEP_WATCHLIST_ONLY").sum())
    else:
        candidate_count = watch_count = 0
    if candidate_count > 0:
        decision = "STAGE25A_HAS_FILTER_CANDIDATE_REVIEW_ONLY"
    elif watch_count > 0:
        decision = "STAGE25A_HAS_WATCHLIST_FILTER_ONLY"
    else:
        decision = "STAGE25A_NO_FILTER_PROMOTION_KEEP_RESEARCH_OPEN"
    report["decision"] = decision
    report["filter_candidate_count"] = candidate_count
    report["watchlist_filter_count"] = watch_count

    lines: List[str] = []
    lines.append("# Stage25A Regime / No-Trade Filter Discovery")
    lines.append("")
    lines.append("## Decision")
    lines.append("")
    lines.append("```text")
    lines.append(decision)
    lines.append("```")
    lines.append("")
    lines.append("## Scope guardrails")
    lines.append("")
    lines.append("- Research/shadow diagnostic only.")
    lines.append("- Stage18A v2 remains unchanged.")
    lines.append("- Stage23D remains unchanged.")
    lines.append("- No EA change, no automatic trading, no paper/live/order authorization.")
    lines.append("- Filters found here are not operational promotions; they require separate forward-shadow validation.")
    lines.append("")
    lines.append("## Data / loader")
    lines.append("")
    lines.append(f"- m1_path: `{report.get('m1_path', '')}`")
    lines.append(f"- h1_path: `{report.get('h1_path', '')}`")
    lines.append(f"- stage23c_trades_path: `{report.get('stage23c_trades_path', '')}`")
    lines.append(f"- m1_rows: {report.get('m1_rows', 0)}")
    lines.append(f"- h1_rows: {report.get('h1_rows', 0)}")
    lines.append(f"- m15_rows: {report.get('m15_rows', 0)}")
    lines.append(f"- source_columns: `{json.dumps(source_cols, ensure_ascii=False)}`")
    lines.append("")
    lines.append("## Base Stage23C trade metrics")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(base, indent=2, ensure_ascii=False, default=str))
    lines.append("```")
    lines.append("")
    lines.append("## Top filter diagnostics")
    lines.append("")
    lines.append(markdown_table(filters, [
        "decision", "filter_name", "retained_events", "retained_ratio", "pf_x1", "pf_x4", "pf_x6",
        "improvement_pf_x4", "total_x4", "win_rate_x4", "median_x4"
    ], MAX_FILTERS_TO_SHOW))
    lines.append("")
    lines.append("## Interpretation")
    lines.append("")
    lines.append("- This stage tests whether Stage23C's candidate can be improved by excluding bad regimes.")
    lines.append("- A filter candidate here is research-only and must be forward-shadowed separately before any operational use.")
    lines.append("- This hotfix specifically handles MT5/AMarkets tab-separated CSV exports so the header is not treated as one broken column.")
    lines.append("")
    lines.append("## Operational reminder")
    lines.append("")
    lines.append("```bash")
    lines.append("cd ~/Desktop/xauusd-trader")
    lines.append("python3 -m app.stage18a_unified_shadow_ops_cycle")
    lines.append("cat data/reports/stage18a_unified_shadow_ops_cycle/stage18a_unified_shadow_ops_cycle.md")
    lines.append("")
    lines.append("python3 -m app.stage23d_forward_shadow_candidate")
    lines.append("cat data/reports/stage23d_forward_shadow_candidate/stage23d_forward_shadow_candidate.md")
    lines.append("```")
    lines.append("")
    lines.append("## Output files")
    lines.append("")
    lines.append("- `data/reports/stage25a_regime_filter_discovery/stage25a_regime_filter_discovery.json`")
    lines.append("- `data/reports/stage25a_regime_filter_discovery/stage25a_regime_filter_discovery.md`")
    lines.append("- `data/reports/stage25a_regime_filter_discovery/stage25a_filter_candidates.csv`")
    lines.append("- `data/reports/stage25a_regime_filter_discovery/stage25a_enriched_stage23c_trades.csv`")
    return "\n".join(lines)


def render_error_report(err: Exception) -> None:
    report = {
        "decision": "STAGE25A_ERROR_DIAGNOSTIC_ONLY",
        "error": f"{type(err).__name__}: {err}",
    }
    (REPORT_DIR / "stage25a_regime_filter_discovery.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    md = [
        "# Stage25A Regime / No-Trade Filter Discovery",
        "",
        "## Decision",
        "",
        "```text",
        "STAGE25A_ERROR_DIAGNOSTIC_ONLY",
        "```",
        "",
        "## Error",
        "",
        "```text",
        f"{type(err).__name__}: {err}",
        "```",
        "",
        "## Interpretation",
        "",
        "- This is a diagnostic/reporting error, not an authorization change.",
        "- Stage18A v2 and Stage23D remain unchanged.",
    ]
    (REPORT_DIR / "stage25a_regime_filter_discovery.md").write_text("\n".join(md), encoding="utf-8")


def main() -> None:
    try:
        m1_path = Path(os.environ["STAGE25A_M1_CSV"]) if os.environ.get("STAGE25A_M1_CSV") else first_existing(DEFAULT_M1_PATHS)
        h1_path = Path(os.environ["STAGE25A_H1_CSV"]) if os.environ.get("STAGE25A_H1_CSV") else first_existing(DEFAULT_H1_PATHS)
        trades_path = Path(os.environ.get("STAGE25A_STAGE23C_TRADES", str(DEFAULT_STAGE23C_TRADES)))

        if m1_path is None:
            raise FileNotFoundError("M1 CSV not found. Expected ~/Downloads/amarkets_xauusd_1m.csv or set STAGE25A_M1_CSV.")
        if h1_path is None:
            raise FileNotFoundError("H1 CSV not found. Expected ~/Downloads/amarkets_xauusd_1h.csv or set STAGE25A_H1_CSV.")
        if not trades_path.exists():
            raise FileNotFoundError(f"Stage23C trades CSV not found: {trades_path}")

        m1 = read_any_csv(m1_path, parse_market=True)
        h1 = read_any_csv(h1_path, parse_market=True)
        trades_raw = read_any_csv(trades_path, parse_market=False)
        trades, source_cols = normalize_trades(trades_raw)

        m15 = build_m15(m1)
        feats = session_features(m15)
        enriched = enrich_trades(trades, feats)

        base = summarize_pnl(enriched, "pnl_x1_norm", "pnl_x4_norm", "pnl_x6_norm")
        filters = evaluate_filters(enriched, base)

        enriched.to_csv(REPORT_DIR / "stage25a_enriched_stage23c_trades.csv", index=False)
        filters.to_csv(REPORT_DIR / "stage25a_filter_candidates.csv", index=False)

        report = {
            "m1_path": str(m1_path),
            "h1_path": str(h1_path),
            "stage23c_trades_path": str(trades_path),
            "m1_rows": int(len(m1)),
            "h1_rows": int(len(h1)),
            "m15_rows": int(len(m15)),
            "base": base,
        }
        md = render_report(report, base, filters, source_cols)
        (REPORT_DIR / "stage25a_regime_filter_discovery.md").write_text(md, encoding="utf-8")
        (REPORT_DIR / "stage25a_regime_filter_discovery.json").write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    except Exception as err:  # Always leave a readable diagnostic report.
        render_error_report(err)
        raise


if __name__ == "__main__":
    main()
