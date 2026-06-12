#!/usr/bin/env python3
"""
Stage28B ML-lite / meta-label feature screen for the XAUUSD research project.

Purpose:
- Do NOT create orders or modify active trackers.
- Use the validated Stage23/25 lineage trade artifact as a research dataset.
- Screen available numeric/time/session/regime features with simple non-linear gates,
  plus limited pairwise combinations, to identify meta-label/gate candidates.
- DB market candles are used only for metadata sanity via the validated Stage25C loader;
  the trade artifact is a research artifact, not market-data fallback.

This module intentionally avoids sklearn dependencies. It is a deterministic feature/gate
screen rather than a trained black-box model.
"""
from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

DEFAULT_DB_PATH = Path(os.getenv("XAUUSD_DB_PATH", "data/local/xauusd_local_store.sqlite"))
DEFAULT_ARTIFACT = Path(
    os.getenv(
        "STAGE28B_TRADE_ARTIFACT",
        "data/reports/stage25c_deduped_filter_validation/stage25c_enriched_canonical_trades.csv",
    )
)
REPORT_DIR = Path("data/reports/stage28b_ml_meta_feature_screen")
MIN_EVENTS = int(os.getenv("STAGE28B_MIN_EVENTS", "30"))
BOOT_N = int(os.getenv("STAGE28B_BOOT_N", "250"))
MAX_SINGLE_GATES = int(os.getenv("STAGE28B_MAX_SINGLE_GATES", "400"))
MAX_PAIRWISE_BASE = int(os.getenv("STAGE28B_MAX_PAIRWISE_BASE", "24"))
RANDOM_SEED = int(os.getenv("STAGE28B_RANDOM_SEED", "2802"))
REQUESTED_CANDIDATE = os.getenv("STAGE28B_CANDIDATE", "S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65")

NET_COLS = ["net_x1", "net_x4", "net_x6"]
EXCLUDE_FEATURE_SUBSTRINGS = (
    "net_",
    "gross",
    "exit_price",
    "entry_price",
    "pnl",
    "profit",
    "loss",
    "return",
    "ret_",
    "target",
    "label",
)
EXCLUDE_FEATURE_COLS = {
    "candidate",
    "family",
    "reason",
    "exit_reason",
    "date",
    "timestamp",
    "entry_time",
    "exit_time",
    "exit_ts",
    "time",
}

@dataclass
class Metrics:
    events: int
    pf_x1: float
    pf_x4: float
    pf_x6: float
    boot_pf_p05_x4: float
    median_x4: float
    total_x4: float
    win_rate_x4: float
    years_positive_x4: int
    year_count: int

@dataclass
class GateResult:
    decision: str
    gate_name: str
    gate_kind: str
    retained_events: int
    retained_ratio: float
    pf_x1: float
    pf_x4: float
    pf_x6: float
    boot_pf_p05_x4: float
    median_x4: float
    total_x4: float
    win_rate_x4: float
    years_positive_x4: int
    year_count: int
    improvement_pf_x4: float
    improvement_pf_x6: float
    improvement_total_x4: float
    rank_score: float


def _safe_float(x: Any) -> float:
    try:
        f = float(x)
        if math.isnan(f) or math.isinf(f):
            return f
        return round(f, 6)
    except Exception:
        return 0.0


def _profit_factor(values: pd.Series) -> float:
    v = pd.to_numeric(values, errors="coerce").dropna()
    gains = float(v[v > 0].sum())
    losses = float((-v[v < 0]).sum())
    if losses <= 0:
        return float("inf") if gains > 0 else 0.0
    return gains / losses


def _bootstrap_pf_p05(values: pd.Series, n: int = BOOT_N, seed: int = RANDOM_SEED) -> float:
    v = pd.to_numeric(values, errors="coerce").dropna().to_numpy(dtype=float)
    if len(v) < 5:
        return 0.0
    rng = np.random.default_rng(seed)
    pfs: List[float] = []
    for _ in range(max(1, n)):
        sample = rng.choice(v, size=len(v), replace=True)
        gains = float(sample[sample > 0].sum())
        losses = float((-sample[sample < 0]).sum())
        if losses <= 0:
            pfs.append(float("inf") if gains > 0 else 0.0)
        else:
            pfs.append(gains / losses)
    finite = np.array([x for x in pfs if np.isfinite(x)], dtype=float)
    if len(finite) == 0:
        return float("inf")
    return float(np.percentile(finite, 5))


def _metrics(df: pd.DataFrame, boot_n: int = BOOT_N) -> Metrics:
    if df.empty:
        return Metrics(0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
    n = int(len(df))
    x1 = pd.to_numeric(df.get("net_x1", pd.Series(dtype=float)), errors="coerce")
    x4 = pd.to_numeric(df.get("net_x4", pd.Series(dtype=float)), errors="coerce")
    x6 = pd.to_numeric(df.get("net_x6", pd.Series(dtype=float)), errors="coerce")
    years_positive = 0
    year_count = 0
    if "year" in df.columns:
        yearly = df.groupby("year")["net_x4"].sum(numeric_only=True)
        year_count = int(len(yearly))
        years_positive = int((yearly > 0).sum())
    return Metrics(
        events=n,
        pf_x1=_safe_float(_profit_factor(x1)),
        pf_x4=_safe_float(_profit_factor(x4)),
        pf_x6=_safe_float(_profit_factor(x6)),
        boot_pf_p05_x4=_safe_float(_bootstrap_pf_p05(x4, boot_n)),
        median_x4=_safe_float(float(x4.median()) if len(x4.dropna()) else 0.0),
        total_x4=_safe_float(float(x4.sum()) if len(x4.dropna()) else 0.0),
        win_rate_x4=_safe_float(float((x4 > 0).mean()) if len(x4.dropna()) else 0.0),
        years_positive_x4=years_positive,
        year_count=year_count,
    )


def _detect_time_col(df: pd.DataFrame) -> Optional[str]:
    for c in ["entry_time", "timestamp", "time", "date"]:
        if c in df.columns:
            return c
    return None


def _normalize_artifact(path: Path) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    manifest: Dict[str, Any] = {"path": str(path), "exists": path.exists(), "status": "missing", "rows": 0}
    if not path.exists():
        raise FileNotFoundError(f"Trade artifact not found: {path}")
    df = pd.read_csv(path)
    manifest.update({"rows": int(len(df)), "status": "loaded"})

    # Candidate filtering is best-effort; some artifacts may not include candidate.
    if "candidate" in df.columns and REQUESTED_CANDIDATE:
        subset = df[df["candidate"].astype(str) == REQUESTED_CANDIDATE].copy()
        if not subset.empty:
            df = subset
            manifest["candidate_filter"] = REQUESTED_CANDIDATE
            manifest["rows_after_candidate_filter"] = int(len(df))
        else:
            manifest["candidate_filter"] = "requested_not_found_kept_all"

    # Standardize required net columns.
    for c in NET_COLS:
        if c not in df.columns:
            # If only gross exists, approximate net_x1 from gross; x4/x6 remain unavailable.
            if c == "net_x1" and "gross" in df.columns:
                df[c] = pd.to_numeric(df["gross"], errors="coerce")
            else:
                raise ValueError(f"Required column missing in artifact: {c}")
        df[c] = pd.to_numeric(df[c], errors="coerce")

    time_col = _detect_time_col(df)
    manifest["time_column_used"] = time_col or "none"
    if time_col:
        t = pd.to_datetime(df[time_col], errors="coerce", utc=True)
        df["entry_ts_norm"] = t
        df["year"] = t.dt.year
        df["month"] = t.dt.month
        df["dow"] = t.dt.dayofweek
        df["entry_hour"] = t.dt.hour
    else:
        # fall back to artifact-provided columns where possible
        if "year" not in df.columns:
            df["year"] = 0
        if "entry_hour" not in df.columns:
            df["entry_hour"] = -1
        if "dow" not in df.columns:
            df["dow"] = -1
        if "month" not in df.columns:
            df["month"] = -1

    # Event de-duplication: prefer unique timestamp+direction if possible.
    dedup_cols = [c for c in ["entry_ts_norm", "direction", "entry_price", "exit_time", "exit_ts"] if c in df.columns]
    before = len(df)
    if dedup_cols:
        df = df.drop_duplicates(subset=dedup_cols).copy()
    manifest["rows_after_event_dedup"] = int(len(df))
    manifest["dedup_removed"] = int(before - len(df))
    return df.reset_index(drop=True), manifest


def _load_db_meta() -> Dict[str, Any]:
    meta: Dict[str, Any] = {
        "db_path": str(DEFAULT_DB_PATH),
        "db_first": True,
        "csv_fallback_enabled": False,
        "loader_mode": "reused:app.stage25c_deduped_filter_validation.load_bars_from_db",
    }
    try:
        from app.stage25c_deduped_filter_validation import load_bars_from_db  # type: ignore

        m1, m1_meta = load_bars_from_db(DEFAULT_DB_PATH, "M1")
        h1, h1_meta = load_bars_from_db(DEFAULT_DB_PATH, "H1")
        meta.update(
            {
                "m1_rows": int(len(m1)),
                "h1_rows": int(len(h1)),
                "m1_span": f"{m1.index.min()} → {m1.index.max()}" if len(m1) else "unavailable",
                "h1_span": f"{h1.index.min()} → {h1.index.max()}" if len(h1) else "unavailable",
                "m1_loader_meta": m1_meta,
                "h1_loader_meta": h1_meta,
            }
        )
    except Exception as exc:  # metadata sanity should not block artifact screening
        meta.update({"db_meta_status": "warning", "db_meta_error": f"{type(exc).__name__}: {exc}"})
    return meta


def _feature_columns(df: pd.DataFrame) -> List[str]:
    cols: List[str] = []
    for c in df.columns:
        cl = str(c).lower()
        if c in EXCLUDE_FEATURE_COLS:
            continue
        if any(s in cl for s in EXCLUDE_FEATURE_SUBSTRINGS):
            continue
        if pd.api.types.is_numeric_dtype(df[c]):
            valid = pd.to_numeric(df[c], errors="coerce").dropna()
            if len(valid) >= MIN_EVENTS and valid.nunique() >= 2:
                cols.append(c)
    # Always include known categorical/time fields if numeric.
    for c in ["direction", "dir_mult", "entry_hour", "dow", "month", "year"]:
        if c in df.columns and c not in cols:
            try:
                df[c] = pd.to_numeric(df[c], errors="coerce")
                if df[c].dropna().nunique() >= 2:
                    cols.append(c)
            except Exception:
                pass
    return cols


def _classify_gate(m: Metrics, base: Metrics, kind: str) -> str:
    if kind.startswith("direction"):
        return "STAGE28B_WATCHLIST_ONLY"
    if (
        m.events >= MIN_EVENTS
        and m.pf_x4 >= max(1.75, base.pf_x4 + 0.45)
        and m.pf_x6 >= max(1.05, base.pf_x6 + 0.20)
        and m.boot_pf_p05_x4 >= 1.10
        and m.total_x4 >= base.total_x4
        and (m.year_count == 0 or m.years_positive_x4 >= max(3, min(4, m.year_count - 1)))
    ):
        return "STAGE28B_GATE_CANDIDATE_REVIEW_ONLY"
    if (
        m.events >= MIN_EVENTS
        and m.pf_x4 >= base.pf_x4
        and m.pf_x6 >= base.pf_x6
        and m.total_x4 > 0
    ):
        return "STAGE28B_WATCHLIST_ONLY"
    return "STAGE28B_REJECT"


def _rank(m: Metrics, base: Metrics) -> float:
    if m.events <= 0:
        return -999.0
    return float(
        (m.pf_x4 - base.pf_x4) * 0.45
        + (m.pf_x6 - base.pf_x6) * 0.30
        + min(m.boot_pf_p05_x4, 5.0) * 0.15
        + np.sign(m.total_x4 - base.total_x4) * 0.10
        + min(m.events / max(base.events, 1), 1.0) * 0.05
    )


def _make_gate_result(name: str, kind: str, mask: pd.Series, df: pd.DataFrame, base: Metrics) -> GateResult:
    g = df[mask.fillna(False)].copy()
    m = _metrics(g)
    return GateResult(
        decision=_classify_gate(m, base, kind),
        gate_name=name,
        gate_kind=kind,
        retained_events=m.events,
        retained_ratio=_safe_float(m.events / max(base.events, 1)),
        pf_x1=m.pf_x1,
        pf_x4=m.pf_x4,
        pf_x6=m.pf_x6,
        boot_pf_p05_x4=m.boot_pf_p05_x4,
        median_x4=m.median_x4,
        total_x4=m.total_x4,
        win_rate_x4=m.win_rate_x4,
        years_positive_x4=m.years_positive_x4,
        year_count=m.year_count,
        improvement_pf_x4=_safe_float(m.pf_x4 - base.pf_x4),
        improvement_pf_x6=_safe_float(m.pf_x6 - base.pf_x6),
        improvement_total_x4=_safe_float(m.total_x4 - base.total_x4),
        rank_score=_safe_float(_rank(m, base)),
    )


def _single_feature_gates(df: pd.DataFrame, features: Sequence[str], base: Metrics) -> List[Tuple[GateResult, pd.Series]]:
    out: List[Tuple[GateResult, pd.Series]] = []
    quantiles = [0.2, 0.25, 0.3, 0.35, 0.4, 0.6, 0.65, 0.7, 0.75, 0.8]
    for col in features:
        s = pd.to_numeric(df[col], errors="coerce")
        unique_count = int(s.dropna().nunique())
        if unique_count <= 10 or col in {"direction", "dir_mult", "entry_hour", "dow", "month", "year"}:
            values = sorted([v for v in s.dropna().unique() if pd.notna(v)])[:30]
            for v in values:
                mask_keep = s == v
                mask_drop = s != v
                kind = "direction_diag" if col in {"direction", "dir_mult"} else "categorical"
                out.append((_make_gate_result(f"keep_{col}_{v}", kind, mask_keep, df, base), mask_keep))
                out.append((_make_gate_result(f"drop_{col}_{v}", kind, mask_drop, df, base), mask_drop))
            continue
        for q in quantiles:
            try:
                thr = float(s.quantile(q))
            except Exception:
                continue
            if not np.isfinite(thr):
                continue
            mask_low = s <= thr
            mask_high = s >= thr
            out.append((_make_gate_result(f"{col}_keep_le_q{int(q*100)}", "numeric_quantile", mask_low, df, base), mask_low))
            out.append((_make_gate_result(f"{col}_keep_ge_q{int(q*100)}", "numeric_quantile", mask_high, df, base), mask_high))
        if len(out) > MAX_SINGLE_GATES * 2:
            break
    return out[:MAX_SINGLE_GATES]


def _pairwise_gates(df: pd.DataFrame, singles: List[Tuple[GateResult, pd.Series]], base: Metrics) -> List[GateResult]:
    ranked = sorted(singles, key=lambda x: x[0].rank_score, reverse=True)
    ranked = [x for x in ranked if x[0].retained_events >= MIN_EVENTS and x[0].gate_kind != "direction_diag"][:MAX_PAIRWISE_BASE]
    out: List[GateResult] = []
    seen: set[str] = set()
    for i in range(len(ranked)):
        for j in range(i + 1, len(ranked)):
            g1, m1 = ranked[i]
            g2, m2 = ranked[j]
            # Avoid combining trivially same base feature prefix.
            prefix1 = g1.gate_name.split("_keep_")[0].split("_drop_")[0].split("_keep")[0]
            prefix2 = g2.gate_name.split("_keep_")[0].split("_drop_")[0].split("_keep")[0]
            if prefix1 == prefix2:
                continue
            name = f"combo__{g1.gate_name}__AND__{g2.gate_name}"
            if name in seen:
                continue
            seen.add(name)
            mask = m1 & m2
            out.append(_make_gate_result(name, "pairwise_combo", mask, df, base))
    return out


def _split_diagnostics(df: pd.DataFrame, gate_name: str, mask: pd.Series) -> pd.DataFrame:
    g = df[mask.fillna(False)].copy()
    rows: List[Dict[str, Any]] = []
    for split in ["year", "direction", "entry_hour", "dow", "month"]:
        if split not in g.columns:
            continue
        for bucket, part in g.groupby(split):
            m = _metrics(part, boot_n=50)
            rows.append({
                "gate_name": gate_name,
                "split": split,
                "bucket": bucket,
                "events": m.events,
                "pf_x4": m.pf_x4,
                "pf_x6": m.pf_x6,
                "total_x4": m.total_x4,
                "win_rate_x4": m.win_rate_x4,
            })
    return pd.DataFrame(rows)


def _format_table(df: pd.DataFrame, max_rows: int = 30) -> str:
    if df.empty:
        return "No rows."
    return df.head(max_rows).to_markdown(index=False)


def run() -> Dict[str, Any]:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    db_meta = _load_db_meta()
    trades, manifest = _normalize_artifact(DEFAULT_ARTIFACT)
    base = _metrics(trades)
    features = _feature_columns(trades)
    singles = _single_feature_gates(trades, features, base)
    pairwise = _pairwise_gates(trades, singles, base)
    gate_rows = [asdict(g) for g, _ in singles] + [asdict(g) for g in pairwise]
    gates = pd.DataFrame(gate_rows)
    if not gates.empty:
        gates = gates.sort_values(["decision", "rank_score", "pf_x4"], ascending=[True, False, False])
        # Better display order: candidates/review first by custom rank.
        order = {
            "STAGE28B_GATE_CANDIDATE_REVIEW_ONLY": 0,
            "STAGE28B_WATCHLIST_ONLY": 1,
            "STAGE28B_REJECT": 2,
        }
        gates["_decision_order"] = gates["decision"].map(order).fillna(9)
        gates = gates.sort_values(["_decision_order", "rank_score", "pf_x4"], ascending=[True, False, False]).drop(columns=["_decision_order"])

    review_count = int((gates.get("decision", pd.Series(dtype=str)) == "STAGE28B_GATE_CANDIDATE_REVIEW_ONLY").sum()) if not gates.empty else 0
    watch_count = int((gates.get("decision", pd.Series(dtype=str)) == "STAGE28B_WATCHLIST_ONLY").sum()) if not gates.empty else 0
    decision = "STAGE28B_HAS_META_GATE_CANDIDATE_REVIEW_ONLY" if review_count else "STAGE28B_NO_META_GATE_PROMOTION_KEEP_DISCOVERY_OPEN"

    top_gate_name = str(gates.iloc[0]["gate_name"]) if not gates.empty else "none"
    top_mask: Optional[pd.Series] = None
    for g, mask in singles:
        if g.gate_name == top_gate_name:
            top_mask = mask
            break
    if top_mask is None:
        top_mask = pd.Series([False] * len(trades), index=trades.index)
    splits = _split_diagnostics(trades, top_gate_name, top_mask)

    all_path = REPORT_DIR / "stage28b_meta_gate_candidates.csv"
    splits_path = REPORT_DIR / "stage28b_top_gate_splits.csv"
    manifest_path = REPORT_DIR / "stage28b_artifact_manifest.csv"
    db_path = REPORT_DIR / "stage28b_db_schema_diagnostic.json"
    enriched_path = REPORT_DIR / "stage28b_normalized_lineage_trades.csv"
    gates.to_csv(all_path, index=False)
    splits.to_csv(splits_path, index=False)
    pd.DataFrame([manifest]).to_csv(manifest_path, index=False)
    trades.to_csv(enriched_path, index=False)
    db_path.write_text(json.dumps(db_meta, indent=2, default=str), encoding="utf-8")

    summary = {
        "decision": decision,
        "db_meta": db_meta,
        "artifact_manifest": manifest,
        "base_metrics": asdict(base),
        "feature_count": len(features),
        "features_sample": features[:60],
        "single_gate_count": len(singles),
        "pairwise_gate_count": len(pairwise),
        "gate_candidates_tested": len(gates),
        "gate_candidate_review_count": review_count,
        "watchlist_only_count": watch_count,
        "outputs": {
            "md": str(REPORT_DIR / "stage28b_ml_meta_feature_screen.md"),
            "json": str(REPORT_DIR / "stage28b_ml_meta_feature_screen.json"),
            "gate_candidates": str(all_path),
            "top_gate_splits": str(splits_path),
            "artifact_manifest": str(manifest_path),
            "normalized_trades": str(enriched_path),
            "db_schema_diagnostic": str(db_path),
        },
    }

    md = _render_markdown(summary, gates, splits)
    (REPORT_DIR / "stage28b_ml_meta_feature_screen.md").write_text(md, encoding="utf-8")
    (REPORT_DIR / "stage28b_ml_meta_feature_screen.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    return summary


def _render_markdown(summary: Dict[str, Any], gates: pd.DataFrame, splits: pd.DataFrame) -> str:
    db = summary["db_meta"]
    manifest = summary["artifact_manifest"]
    base = summary["base_metrics"]
    lines: List[str] = []
    lines.append("# Stage28B ML-lite Meta-Feature Screen")
    lines.append("")
    lines.append("## Decision")
    lines.append("")
    lines.append("```text")
    lines.append(str(summary["decision"]))
    lines.append("```")
    lines.append("")
    lines.append("## Scope guardrails")
    lines.append("")
    lines.append("- Research/shadow feature screening only.")
    lines.append("- No EA change, no automatic trading, no paper/live/order authorization.")
    lines.append("- Stage18A/Stage23D/Stage25D/Stage27D remain unchanged.")
    lines.append("- Market candle sanity is DB-first via the validated Stage25C loader; AMarkets CSV market fallback is disabled.")
    lines.append("- Trade artifact is used only as research evidence for meta-label/gate screening.")
    lines.append("- This is ML-lite/nonlinear feature screening, not a black-box prediction model.")
    lines.append("")
    lines.append("## DB source of truth")
    lines.append("")
    lines.append(f"- loader_mode: `{db.get('loader_mode')}`")
    lines.append(f"- db_path: `{db.get('db_path')}`")
    lines.append(f"- db_first: `{db.get('db_first')}`")
    lines.append(f"- csv_fallback_enabled: `{db.get('csv_fallback_enabled')}`")
    lines.append(f"- m1_rows: `{db.get('m1_rows', 'unavailable')}`")
    lines.append(f"- h1_rows: `{db.get('h1_rows', 'unavailable')}`")
    if db.get("db_meta_status") == "warning":
        lines.append(f"- db_meta_warning: `{db.get('db_meta_error')}`")
    lines.append("")
    lines.append("## Trade artifact")
    lines.append("")
    lines.append(f"- selected_artifact: `{manifest.get('path')}`")
    lines.append(f"- rows: `{manifest.get('rows')}`")
    lines.append(f"- rows_after_event_dedup: `{manifest.get('rows_after_event_dedup')}`")
    lines.append(f"- time_column_used: `{manifest.get('time_column_used')}`")
    lines.append("")
    lines.append("## Base metrics")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(base, indent=2, default=str))
    lines.append("```")
    lines.append("")
    lines.append("## Counts")
    lines.append("")
    lines.append(f"- feature_count: `{summary['feature_count']}`")
    lines.append(f"- single_gate_count: `{summary['single_gate_count']}`")
    lines.append(f"- pairwise_gate_count: `{summary['pairwise_gate_count']}`")
    lines.append(f"- gate_candidates_tested: `{summary['gate_candidates_tested']}`")
    lines.append(f"- gate_candidate_review_count: `{summary['gate_candidate_review_count']}`")
    lines.append(f"- watchlist_only_count: `{summary['watchlist_only_count']}`")
    lines.append("")
    lines.append("## Features screened")
    lines.append("")
    sample = summary.get("features_sample", [])
    lines.append(", ".join(f"`{x}`" for x in sample) if sample else "No usable features detected.")
    lines.append("")
    lines.append("## Top meta-gate diagnostics")
    lines.append("")
    cols = [
        "decision", "gate_name", "gate_kind", "retained_events", "retained_ratio",
        "pf_x4", "pf_x6", "boot_pf_p05_x4", "median_x4", "total_x4",
        "win_rate_x4", "years_positive_x4", "year_count", "improvement_pf_x4",
        "improvement_pf_x6", "improvement_total_x4", "rank_score",
    ]
    lines.append(_format_table(gates[[c for c in cols if c in gates.columns]], 40))
    lines.append("")
    lines.append("## Top gate split diagnostics")
    lines.append("")
    lines.append(_format_table(splits, 80))
    lines.append("")
    lines.append("## Interpretation")
    lines.append("")
    lines.append("- Stage28B screens meta-label/gate features around the strongest Stage23/25 lineage instead of inventing a new raw entry rule.")
    lines.append("- A candidate here remains research-only and requires a dedicated validation stage before any forward tracker.")
    lines.append("- If no meta-gate survives, the next useful step is adding richer exogenous/macro/news proxy features rather than mutating raw OHLC entries.")
    lines.append("")
    lines.append("## Operational reminder")
    lines.append("")
    lines.append("```bash")
    lines.append("cd ~/Desktop/xauusd-trader")
    lines.append("python3 -m app.run_active_shadow_suite")
    lines.append("python3 -m app.stage28a_discovery_factory_batch_runner")
    lines.append("python3 -m app.stage28b_ml_meta_feature_screen")
    lines.append("```")
    lines.append("")
    lines.append("## Output files")
    lines.append("")
    for k, v in summary["outputs"].items():
        lines.append(f"- `{v}`")
    return "\n".join(lines) + "\n"


def main() -> None:
    try:
        run()
    except Exception as exc:
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        md = "\n".join([
            "# Stage28B ML-lite Meta-Feature Screen",
            "",
            "## Decision",
            "",
            "```text",
            "STAGE28B_ERROR_DIAGNOSTIC_ONLY",
            "```",
            "",
            "## Error",
            "",
            "```text",
            f"{type(exc).__name__}: {exc}",
            "```",
            "",
            "- DB-first market sanity is intended.",
            "- CSV market fallback is intentionally disabled.",
            "- Active forward trackers remain unchanged.",
            "",
        ])
        (REPORT_DIR / "stage28b_ml_meta_feature_screen.md").write_text(md, encoding="utf-8")
        (REPORT_DIR / "stage28b_ml_meta_feature_screen.json").write_text(
            json.dumps({"decision": "STAGE28B_ERROR_DIAGNOSTIC_ONLY", "error": f"{type(exc).__name__}: {exc}"}, indent=2),
            encoding="utf-8",
        )
        raise


if __name__ == "__main__":
    main()
