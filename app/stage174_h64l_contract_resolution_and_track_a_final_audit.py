#!/usr/bin/env python3
"""Stage174 — resolve original H64L contracts and run Track A only.

This stage is intentionally narrow. It:
1) resolves the original Stage64R holding horizon using authoritative-artifact priority;
2) resolves/fingerprints the DXY source contract used by the Stage64K lag-safe dataset;
3) validates and normalizes the historical-as-of H64L feature table; and
4) runs the final cost-aware locked-holdout H64L decision audit.

No order, demo, live, paper-order, ML, parameter scan, or Track B path exists.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

STAGE = "Stage174_H64L_CONTRACT_RESOLUTION_AND_TRACK_A_FINAL_AUDIT"
DEFAULT_OUT = "reports/stage174_h64l_contract_resolution_and_track_a_final_audit"
REQ_FEATURES = ["gold_sma20_over_50", "dxy_ret_20d", "real_yield_change_20d", "etf_flow_tonnes_3m"]


def utc_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def resolve(root: Path, value: str | Path) -> Path:
    p = Path(value).expanduser()
    return p if p.is_absolute() else root / p


def detect_sep(path: Path) -> str:
    with path.open("r", encoding="utf-8-sig", errors="replace") as f:
        line = f.readline()
    return max(["\t", ",", ";", "|"], key=line.count)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")


def first_existing(root: Path, values: Sequence[str]) -> Optional[Path]:
    for v in values:
        p = resolve(root, v)
        if p.exists() and p.is_file():
            return p
    return None


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def nested_numbers(obj: Any, keys: set[str], prefix: str = "") -> List[Tuple[str, float]]:
    out: List[Tuple[str, float]] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            name = f"{prefix}.{k}" if prefix else str(k)
            if str(k).lower() in keys and isinstance(v, (int, float)) and math.isfinite(float(v)):
                out.append((name, float(v)))
            out.extend(nested_numbers(v, keys, name))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out.extend(nested_numbers(v, keys, f"{prefix}[{i}]"))
    return out


def extract_horizons(path: Path) -> List[Tuple[str, int]]:
    text = read_text(path)
    found: List[Tuple[str, int]] = []
    try:
        obj = json.loads(text)
        for key, value in nested_numbers(obj, {"horizon_days", "holding_days", "hold_days"}):
            if 1 <= int(value) <= 500:
                found.append((key, int(value)))
    except Exception:
        pass
    for m in re.finditer(r"(?i)\b(horizon_days|holding_days|hold_days)\b\s*[`\"']?\s*[:=]\s*[`\"']?\s*(\d{1,3})", text):
        value = int(m.group(2))
        if 1 <= value <= 500:
            found.append((m.group(1), value))
    # stable de-duplication
    seen = set()
    out = []
    for item in found:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def resolve_horizon_contract(root: Path, cfg: Dict[str, Any]) -> Dict[str, Any]:
    evidence: List[Dict[str, Any]] = []
    weights: Dict[int, float] = {}
    for spec in cfg["contracts"]["horizon_authority"]:
        p = resolve(root, spec["path"])
        if not p.exists():
            continue
        values = extract_horizons(p)
        for key, value in values:
            row = {
                "path": str(p), "sha256": sha256(p), "authority": spec["authority"],
                "weight": float(spec["weight"]), "field": key, "value": int(value),
            }
            evidence.append(row)
            weights[value] = weights.get(value, 0.0) + float(spec["weight"])
    total = sum(weights.values())
    if not weights or total <= 0:
        return {"status": "HOLDING_HORIZON_UNRESOLVED", "evidence": evidence, "weighted_votes": weights}
    ranked = sorted(weights.items(), key=lambda kv: (-kv[1], kv[0]))
    winner, score = ranked[0]
    runner = ranked[1][1] if len(ranked) > 1 else 0.0
    min_weight = float(cfg["contracts"]["minimum_horizon_authority_weight"])
    min_share = float(cfg["contracts"]["minimum_horizon_vote_share"])
    resolved = score >= min_weight and score / total >= min_share and score > runner
    return {
        "status": "RESOLVED" if resolved else "HOLDING_HORIZON_UNRESOLVED",
        "holding_days": int(winner) if resolved else None,
        "weighted_votes": {str(k): v for k, v in ranked},
        "winning_share": score / total,
        "evidence": evidence,
        "rule": "AUTHORITATIVE_STAGE64R_AND_REPLICATION_CONTRACTS_OUTRANK_INCIDENTAL_STAGE_VALUES",
    }


def date_column(raw: pd.DataFrame) -> Optional[str]:
    cmap = {str(c).strip().lower(): str(c) for c in raw.columns}
    for key in ["sample_available_after_utc", "available_after_utc", "feature_date_utc", "date_utc", "observation_date", "date", "timestamp", "datetime"]:
        if key in cmap:
            return cmap[key]
    return None


def load_target_feature(path: Path) -> pd.DataFrame:
    raw = pd.read_csv(path, sep=detect_sep(path), low_memory=False)
    cmap = {str(c).strip().lower(): c for c in raw.columns}
    dc = next((cmap[k] for k in ["feature_date_utc", "date_utc", "date", "timestamp"] if k in cmap), None)
    if dc is None or "dxy_ret_20d" not in cmap:
        raise ValueError("Stage64K dataset lacks date or dxy_ret_20d")
    out = pd.DataFrame({
        "date": pd.to_datetime(raw[dc], errors="coerce", utc=True).dt.floor("D"),
        "target": pd.to_numeric(raw[cmap["dxy_ret_20d"]], errors="coerce"),
    }).dropna().sort_values("date").drop_duplicates("date", keep="last")
    if len(out) < 100:
        raise ValueError("Insufficient Stage64K DXY target rows")
    return out


def choose_numeric_series(raw: pd.DataFrame, excluded: set[str]) -> Tuple[str, pd.Series]:
    candidates = []
    for c in raw.columns:
        if str(c) in excluded:
            continue
        v = pd.to_numeric(raw[c], errors="coerce")
        n = int(v.notna().sum())
        if n >= 100:
            candidates.append((n, str(c), v))
    if not candidates:
        raise ValueError("No numeric series with sufficient coverage")
    # Prefer semantically named value/close/index columns, then coverage.
    def rank(item: Tuple[int, str, pd.Series]) -> Tuple[int, int, str]:
        n, name, _ = item
        low = name.lower()
        semantic = int(any(x in low for x in ["close", "value", "dxy", "index", "price"]))
        return (semantic, n, name)
    n, name, series = max(candidates, key=rank)
    return name, series


def load_candidate_dxy(path: Path) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    raw = pd.read_csv(path, sep=detect_sep(path), low_memory=False)
    cmap = {str(c).strip().lower(): c for c in raw.columns}
    dc = next((cmap[k] for k in ["date_utc", "observation_date", "date", "timestamp", "datetime"] if k in cmap), None)
    if dc is None:
        raise ValueError("No date column")
    dates = pd.to_datetime(raw[dc], errors="coerce", utc=True).dt.floor("D")
    direct = cmap.get("dxy_ret_20d")
    if direct is not None:
        values = pd.to_numeric(raw[direct], errors="coerce")
        method = "DIRECT_DXY_RET_20D"
        value_col = str(direct)
    else:
        value_col, level = choose_numeric_series(raw, {str(dc)})
        values = level.pct_change(20)
        method = "PCT_CHANGE_20_ROWS_FROM_LEVEL"
    out = pd.DataFrame({"date": dates, "candidate": values}).dropna().sort_values("date").drop_duplicates("date", keep="last")
    semantic_text_parts = [" ".join(str(c) for c in raw.columns)]
    for c in raw.columns:
        if not pd.api.types.is_numeric_dtype(raw[c]):
            vals = raw[c].dropna().astype(str).head(20).tolist()
            semantic_text_parts.extend(vals)
    return out, {"value_column": value_col, "method": method, "rows": int(len(out)), "semantic_text": " ".join(semantic_text_parts)[:8000]}


def classify_dxy_semantics(path: Path, nearby_text: str = "") -> str:
    text = (str(path) + "\n" + nearby_text).lower()
    if "dtwexbgs" in text or "broad trade weighted" in text:
        return "FRED_DTWEXBGS"
    if any(x in text for x in ["dx-y.nyb", "ice_usdx", "ice dxy", "ice dollar index"]):
        return "ICE_DXY"
    return "GENERIC_DXY_UNRESOLVED"


def authority_text_evidence(root: Path, cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = []
    for item in cfg["contracts"]["dxy_authority_paths"]:
        p = resolve(root, item)
        if not p.exists() or not p.is_file():
            continue
        text = read_text(p)
        tokens = []
        for token in ["DTWEXBGS", "DX-Y.NYB", "ICE_USDX", "ICE DXY", "dxy.csv"]:
            if token.lower() in text.lower():
                tokens.append(token)
        if tokens:
            rows.append({"path": str(p), "sha256": sha256(p), "tokens": tokens, "semantic": classify_dxy_semantics(p, text)})
    return rows


def candidate_paths(root: Path, cfg: Dict[str, Any]) -> List[Path]:
    out: List[Path] = []
    for value in cfg["data"]["dxy_candidates"]:
        p = resolve(root, value)
        if p.exists() and p.is_file():
            out.append(p)
    for pattern in cfg["data"]["dxy_globs"]:
        out.extend([p for p in root.glob(pattern) if p.is_file() and p.suffix.lower() in {".csv", ".txt"}])
    uniq = []
    seen = set()
    for p in out:
        rp = str(p.resolve())
        if rp not in seen:
            seen.add(rp)
            uniq.append(p)
    return uniq[: int(cfg["contracts"]["maximum_dxy_candidates"])]


def fingerprint_dxy_contract(root: Path, cfg: Dict[str, Any], stage64k: Path) -> Dict[str, Any]:
    target = load_target_feature(stage64k)
    text_evidence = authority_text_evidence(root, cfg)
    rows: List[Dict[str, Any]] = []
    for p in candidate_paths(root, cfg):
        try:
            cand, meta = load_candidate_dxy(p)
            z = target.merge(cand, on="date", how="inner").dropna()
            if len(z) < int(cfg["contracts"]["minimum_dxy_overlap_rows"]):
                continue
            scored = []
            for scale in [1.0, 100.0, 0.01]:
                scaled = z["candidate"] * scale
                corr = float(z["target"].corr(scaled))
                diff = (z["target"] - scaled).abs()
                sign = float((np.sign(z["target"]) == np.sign(scaled)).mean())
                scored.append((float(diff.median()), -corr, -sign, scale, corr, diff, sign))
            _, _, _, scale, corr, diff, sign = min(scored, key=lambda item: item[:3])
            semantic = classify_dxy_semantics(p, meta.pop("semantic_text", ""))
            rows.append({
                "path": str(p), "sha256": sha256(p), **meta,
                "overlap_rows": int(len(z)), "scale_factor": scale, "correlation": corr,
                "median_abs_error": float(diff.median()), "p90_abs_error": float(diff.quantile(0.9)),
                "sign_agreement": sign, "semantic": semantic,
            })
        except Exception as exc:
            rows.append({"path": str(p), "error": f"{type(exc).__name__}:{exc}", "semantic": classify_dxy_semantics(p)})
    valid = [r for r in rows if "correlation" in r]
    valid.sort(key=lambda r: (-r["correlation"], r["median_abs_error"], -r["overlap_rows"]))
    best = valid[0] if valid else None
    direct_semantics = {r["semantic"] for r in text_evidence if r["semantic"] != "GENERIC_DXY_UNRESOLVED"}
    semantic: Optional[str] = None
    resolution_basis = None
    if len(direct_semantics) == 1:
        semantic = next(iter(direct_semantics))
        resolution_basis = "AUTHORITATIVE_STAGE64_TEXT"
    if best:
        exact = (
            best["correlation"] >= float(cfg["contracts"]["minimum_dxy_correlation"])
            and best["sign_agreement"] >= float(cfg["contracts"]["minimum_dxy_sign_agreement"])
            and best["median_abs_error"] <= float(cfg["contracts"]["maximum_dxy_median_abs_error"])
        )
        if exact and best["semantic"] != "GENERIC_DXY_UNRESOLVED":
            if semantic is None:
                semantic = best["semantic"]
                resolution_basis = "NUMERIC_FINGERPRINT_AND_NAMED_SOURCE"
            elif semantic != best["semantic"]:
                return {"status": "DXY_SOURCE_CONTRACT_CONFLICT", "text_evidence": text_evidence, "candidate_scores": rows, "best": best}
        elif exact and semantic is not None:
            resolution_basis = (resolution_basis or "AUTHORITATIVE_STAGE64_TEXT") + "+NUMERIC_FINGERPRINT_GENERIC_FILE"
    resolved = semantic is not None and best is not None and best.get("correlation", -1) >= float(cfg["contracts"]["minimum_dxy_correlation"])
    return {
        "status": "RESOLVED" if resolved else "DXY_SOURCE_CONTRACT_UNRESOLVED",
        "source_contract": semantic if resolved else None,
        "resolution_basis": resolution_basis,
        "best_match": best,
        "text_evidence": text_evidence,
        "candidate_scores": rows,
        "target_dataset": str(stage64k),
        "target_sha256": sha256(stage64k),
    }


def normalize_h64l_features(stage64k: Path, output: Path) -> Dict[str, Any]:
    raw = pd.read_csv(stage64k, sep=detect_sep(stage64k), low_memory=False)
    cmap = {str(c).strip().lower(): c for c in raw.columns}
    missing = [c for c in REQ_FEATURES if c not in cmap]
    if missing:
        raise ValueError(f"Stage64K missing features: {missing}")
    dc = next((cmap[k] for k in ["feature_date_utc", "date_utc", "date", "timestamp"] if k in cmap), None)
    ac = next((cmap[k] for k in ["sample_available_after_utc", "available_after_utc", "release_timestamp_utc"] if k in cmap), None)
    if dc is None:
        raise ValueError("Stage64K date column missing")
    if ac is None:
        raise ValueError("Stage64K has no explicit availability timestamp; no lag assumption permitted")
    out = pd.DataFrame({
        "feature_date_utc": pd.to_datetime(raw[dc], errors="coerce", utc=True).dt.floor("D"),
        "available_after_utc": pd.to_datetime(raw[ac], errors="coerce", utc=True),
    })
    for c in REQ_FEATURES:
        out[c] = pd.to_numeric(raw[cmap[c]], errors="coerce")
    out = out.dropna().sort_values(["available_after_utc", "feature_date_utc"]).drop_duplicates("feature_date_utc", keep="last")
    if len(out) < 500:
        raise ValueError("Insufficient complete historical-as-of H64L rows")
    if (out["available_after_utc"] < out["feature_date_utc"]).any():
        raise ValueError("Availability precedes feature date")
    output.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(output, index=False)
    return {
        "status": "PASS",
        "source": str(stage64k), "source_sha256": sha256(stage64k),
        "output": str(output), "output_sha256": sha256(output),
        "rows": int(len(out)), "start": str(out["feature_date_utc"].min()), "end": str(out["feature_date_utc"].max()),
        "availability_contract": "EXPLICIT_STAGE64K_SAMPLE_AVAILABLE_AFTER_UTC_NO_SYNTHETIC_LAG",
    }


def load_bars(path: Path) -> pd.DataFrame:
    raw = pd.read_csv(path, sep=detect_sep(path), low_memory=False)
    cmap = {str(c).strip().lower(): c for c in raw.columns}
    tc = next((cmap[k] for k in ["timestamp", "timestamp_utc", "time", "datetime", "date"] if k in cmap), None)
    if tc is None:
        raise ValueError("Bar timestamp missing")
    cols = {}
    for k in ["open", "high", "low", "close"]:
        if k not in cmap:
            raise ValueError(f"Bar {k} missing")
        cols[k] = pd.to_numeric(raw[cmap[k]], errors="coerce")
    out = pd.DataFrame({"ts": pd.to_datetime(raw[tc], errors="coerce", utc=True), **cols}).dropna().sort_values("ts").drop_duplicates("ts", keep="last")
    if len(out) < 1000:
        raise ValueError("Insufficient H1 bars")
    return out


def daily_from_h1(h1: pd.DataFrame) -> pd.DataFrame:
    x = h1.copy()
    x["date"] = x["ts"].dt.floor("D")
    d = x.groupby("date", as_index=False).agg(open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last"), bars=("close", "size"))
    return d[d["bars"] >= 12].reset_index(drop=True)


def locked_cutoff(dates: pd.Series, fraction: float) -> pd.Timestamp:
    uniq = pd.Series(pd.to_datetime(dates, utc=True).dropna().unique()).sort_values().reset_index(drop=True)
    idx = min(len(uniq) - 1, max(1, int(math.floor(len(uniq) * (1.0 - fraction)))))
    return pd.Timestamp(uniq.iloc[idx])


def build_episodes(frame: pd.DataFrame, active_col: str, min_gap_days: int) -> pd.DataFrame:
    x = frame.sort_values("date").copy()
    x[active_col] = x[active_col].fillna(False).astype(bool)
    x["prev_active"] = x[active_col].shift(1, fill_value=False).astype(bool)
    x["raw_start"] = x[active_col] & (~x["prev_active"])
    starts = x[x["raw_start"]].copy()
    keep = []
    last: Optional[pd.Timestamp] = None
    for idx, row in starts.iterrows():
        if last is None or (row["date"] - last).days >= min_gap_days:
            keep.append(idx)
            last = row["date"]
    return starts.loc[keep].copy()


def metrics(values: pd.Series) -> Dict[str, Any]:
    s = pd.to_numeric(values, errors="coerce").dropna()
    if s.empty:
        return {"trades": 0, "net_expectancy_bps": None, "median_net_bps": None, "win_rate": None, "profit_factor": None, "total_net_bps": None, "max_drawdown_bps": None}
    wins = s[s > 0].sum()
    losses = -s[s < 0].sum()
    curve = s.cumsum()
    dd = curve.cummax() - curve
    return {
        "trades": int(len(s)), "net_expectancy_bps": float(s.mean()), "median_net_bps": float(s.median()),
        "win_rate": float((s > 0).mean()), "profit_factor": float(wins / losses) if losses > 0 else None,
        "total_net_bps": float(s.sum()), "max_drawdown_bps": float(dd.max()) if len(dd) else 0.0,
    }


def concentration(frame: pd.DataFrame, col: str) -> Dict[str, Any]:
    if frame.empty or col not in frame:
        return {"max_share": None, "leader": None, "counts": {}}
    c = frame[col].astype(str).value_counts()
    return {"max_share": float(c.iloc[0] / c.sum()), "leader": str(c.index[0]), "counts": {str(k): int(v) for k, v in c.items()}}


def audit_track_a(feature_path: Path, h1_path: Path, holding_days: int, cfg: Dict[str, Any], out: Path) -> Dict[str, Any]:
    f = pd.read_csv(feature_path, low_memory=False)
    f["feature_date_utc"] = pd.to_datetime(f["feature_date_utc"], errors="coerce", utc=True).dt.floor("D")
    f["available_after_utc"] = pd.to_datetime(f["available_after_utc"], errors="coerce", utc=True)
    h1 = load_bars(h1_path)
    d = daily_from_h1(h1)
    d["gold_ret_fwd_bps"] = (d["close"].shift(-holding_days) / d["close"] - 1.0) * 10000.0
    z = pd.merge_asof(d.sort_values("date"), f.sort_values("available_after_utc"), left_on="date", right_on="available_after_utc", direction="backward")
    z["h64l_active"] = (z["gold_sma20_over_50"] > 0) & (z["dxy_ret_20d"] < 0) & (z["real_yield_change_20d"] < 0) & (z["etf_flow_tonnes_3m"] > 0)
    z["trend_active"] = z["gold_sma20_over_50"] > 0
    cutoff = locked_cutoff(d["date"], float(cfg["governance"]["holdout_fraction"]))
    cost = float(cfg["costs"]["round_trip_cost_bps"]) + float(cfg["costs"]["slippage_bps"])
    gap = int(cfg["track_a"].get("minimum_days_between_independent_episodes", holding_days))

    def episode_table(active_col: str, name: str) -> pd.DataFrame:
        ep = build_episodes(z.dropna(subset=["gold_ret_fwd_bps"]), active_col, gap)
        ep["strategy"] = name
        ep["entry_ts"] = ep["date"]
        ep["gross_bps"] = ep["gold_ret_fwd_bps"]
        ep["net_bps"] = ep["gross_bps"] - cost
        ep["year"] = ep["entry_ts"].dt.year
        ep["regime"] = pd.cut(ep["gold_sma20_over_50"], [-np.inf, 0.02, 0.05, np.inf], labels=["MILD", "MEDIUM", "STRONG"]).astype(str)
        ep["partition"] = np.where(ep["entry_ts"] >= cutoff, "HOLDOUT", "DEVELOPMENT")
        return ep

    h64l = episode_table("h64l_active", "H64L_EXACT_LOCKED")
    trend = episode_table("trend_active", "GOLD_SMA20_OVER_50_LONG")
    drift = z.dropna(subset=["gold_ret_fwd_bps"]).copy()
    drift["net_bps"] = drift["gold_ret_fwd_bps"] - cost
    drift["partition"] = np.where(drift["date"] >= cutoff, "HOLDOUT", "DEVELOPMENT")

    h_hold = h64l[h64l["partition"] == "HOLDOUT"]
    t_hold = trend[trend["partition"] == "HOLDOUT"]
    d_hold = drift[drift["partition"] == "HOLDOUT"]
    hm, tm, dm = metrics(h_hold["net_bps"]), metrics(t_hold["net_bps"]), metrics(d_hold["net_bps"])
    yc, rc = concentration(h_hold, "year"), concentration(h_hold, "regime")
    years = max(1.0, (d["date"].max() - d["date"].min()).days / 365.25)
    freq = len(h64l) / years
    gaps = h64l["entry_ts"].sort_values().diff().dt.days.dropna()
    tc = cfg["track_a"]
    gates = {
        "holdout_episodes": len(h_hold) >= int(tc["minimum_holdout_episodes"]),
        "positive_net_expectancy": hm["net_expectancy_bps"] is not None and hm["net_expectancy_bps"] >= float(tc["minimum_net_expectancy_bps"]),
        "drawdown": hm["max_drawdown_bps"] is not None and hm["max_drawdown_bps"] <= float(tc["maximum_drawdown_bps"]),
        "year_concentration": yc["max_share"] is not None and yc["max_share"] <= float(tc["maximum_single_year_share"]),
        "regime_concentration": rc["max_share"] is not None and rc["max_share"] <= float(tc["maximum_single_regime_share"]),
        "beats_gold_drift": hm["net_expectancy_bps"] is not None and dm["net_expectancy_bps"] is not None and hm["net_expectancy_bps"] > dm["net_expectancy_bps"],
        "beats_simple_trend": hm["net_expectancy_bps"] is not None and tm["net_expectancy_bps"] is not None and hm["net_expectancy_bps"] > tm["net_expectancy_bps"],
    }
    if not gates["holdout_episodes"] or not gates["positive_net_expectancy"] or not gates["beats_gold_drift"] or not gates["beats_simple_trend"]:
        decision = "KILL"
    elif freq < float(tc["minimum_annual_frequency_for_shadow"]) or not all([gates["drawdown"], gates["year_concentration"], gates["regime_concentration"]]):
        decision = "OVERLAY_ONLY"
    else:
        decision = "SHADOW_CANDIDATE"

    cols = ["strategy", "entry_ts", "gross_bps", "net_bps", "year", "regime", "partition", *REQ_FEATURES]
    h64l[cols].to_csv(out / "stage174_h64l_episodes.csv", index=False)
    trend[cols].to_csv(out / "stage174_simple_trend_baseline_episodes.csv", index=False)
    return {
        "status": "COMPLETE", "decision": decision, "holding_days": holding_days,
        "independent_episode_gap_days": gap, "holdout_cutoff_utc": str(cutoff),
        "episode_count": int(len(h64l)), "holdout_episode_count": int(len(h_hold)),
        "annual_frequency": float(freq), "median_gap_days": float(gaps.median()) if len(gaps) else None,
        "holdout_metrics": hm, "simple_trend_holdout": tm, "gold_drift_holdout": dm,
        "year_concentration": yc, "regime_concentration": rc,
        "session_concentration": {"status": "NOT_APPLICABLE_DAILY_MACRO_ENTRY"},
        "gates": gates, "feature_source": str(feature_path), "feature_sha256": sha256(feature_path),
        "gold_source": str(h1_path), "gold_sha256": sha256(h1_path),
    }


def decision_markdown(summary: Dict[str, Any]) -> str:
    lines = [
        "# Stage174 Decision", "", f"Generated: {summary['generated_utc']}", "",
        "## Hard controls", "", "- Orders/demo/live/paper-order: forbidden.", "- ML: forbidden.", "- Broad scan and Track B rerun: forbidden.", "",
        "## Contract resolution", "", f"- Horizon: `{summary['contracts']['horizon'].get('status')}` / `{summary['contracts']['horizon'].get('holding_days')}`",
        f"- DXY: `{summary['contracts']['dxy'].get('status')}` / `{summary['contracts']['dxy'].get('source_contract')}`", "",
        "## Track A — H64L final audit", "", f"**Decision: `{summary['track_a'].get('decision')}`**", f"Status: `{summary['track_a'].get('status')}`", "",
        "## Program decision", "", f"**`{summary['program_decision']}`**", "",
        "No new technical/COT scan and no execution bridge is authorized.",
    ]
    for issue in summary.get("issues", []):
        lines.append(f"- {issue}")
    return "\n".join(lines) + "\n"


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="~/Desktop/xauusd-trader")
    ap.add_argument("--config", default="configs/stage174_h64l_contract_resolution_and_track_a_final_audit.json")
    ap.add_argument("--out-dir", default=DEFAULT_OUT)
    args = ap.parse_args(argv)
    root = Path(args.root).expanduser().resolve()
    cfg = json.loads(resolve(root, args.config).read_text(encoding="utf-8"))
    out = resolve(root, args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    summary: Dict[str, Any] = {
        "stage": STAGE, "generated_utc": utc_iso(), "root": str(root),
        "hard_controls": cfg["governance"], "issues": [], "contracts": {},
    }

    stage64k = first_existing(root, cfg["data"]["stage64k_feature_candidates"])
    h1 = first_existing(root, cfg["data"]["h1_candidates"])
    if stage64k is None:
        summary["issues"].append("STAGE64K_LAG_SAFE_FEATURE_DATASET_NOT_FOUND")
    if h1 is None:
        summary["issues"].append("AMARKETS_H1_NOT_FOUND")

    horizon = resolve_horizon_contract(root, cfg)
    summary["contracts"]["horizon"] = horizon
    if horizon["status"] != "RESOLVED":
        summary["issues"].append("HOLDING_HORIZON_UNRESOLVED")

    if stage64k is not None:
        dxy = fingerprint_dxy_contract(root, cfg, stage64k)
    else:
        dxy = {"status": "DXY_SOURCE_CONTRACT_UNRESOLVED", "reason": "NO_STAGE64K_TARGET"}
    summary["contracts"]["dxy"] = dxy
    if dxy["status"] != "RESOLVED":
        summary["issues"].append(dxy["status"])

    pd.DataFrame(horizon.get("evidence", [])).to_csv(out / "stage174_horizon_contract_evidence.csv", index=False)
    pd.DataFrame(dxy.get("candidate_scores", [])).to_csv(out / "stage174_dxy_fingerprint_scores.csv", index=False)
    write_json(out / "stage174_dxy_contract_evidence.json", dxy)

    feature_meta: Dict[str, Any] = {"status": "BLOCKED"}
    track_a: Dict[str, Any] = {"status": "BLOCKED", "decision": "INCONCLUSIVE_BLOCKED", "issues": list(summary["issues"])}
    if not summary["issues"] and stage64k is not None and h1 is not None:
        try:
            feature_path = resolve(root, cfg["data"]["normalized_h64l_output"])
            feature_meta = normalize_h64l_features(stage64k, feature_path)
            track_a = audit_track_a(feature_path, h1, int(horizon["holding_days"]), cfg, out)
        except Exception as exc:
            issue = f"TRACK_A_FATAL:{type(exc).__name__}:{exc}"
            summary["issues"].append(issue)
            track_a = {"status": "BLOCKED", "decision": "INCONCLUSIVE_BLOCKED", "issues": [issue]}
    summary["historical_asof_feature_table"] = feature_meta
    summary["track_a"] = track_a

    if track_a.get("status") != "COMPLETE":
        program = "BLOCK_H64L_PENDING_EXACT_CONTRACT_OR_INPUT_RESOLUTION_NO_NEW_SCAN"
    elif track_a.get("decision") == "KILL":
        program = "KILL_H64L_RESCUE_CLOSE_TRACK_A_NO_ML_AUTHORIZE_ONLY_NARROW_PREWRITTEN_NEW_THESIS_DELTA_REVIEW"
    elif track_a.get("decision") == "OVERLAY_ONLY":
        program = "LOCK_H64L_AS_OVERLAY_ONLY_CONTINUE_UNATTENDED_LOGGING_NO_EXECUTION_BUILD_ONE_NARROW_PRIMARY_THESIS_DELTA"
    else:
        program = "H64L_SHADOW_CANDIDATE_LOG_ONLY_NO_EXECUTION_PRIMARY_GENERATOR_STILL_REQUIRED"
    summary["program_decision"] = program
    write_json(out / "stage174_summary.json", summary)
    (out / "stage174_decision.md").write_text(decision_markdown(summary), encoding="utf-8")
    return 0 if track_a.get("status") == "COMPLETE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
