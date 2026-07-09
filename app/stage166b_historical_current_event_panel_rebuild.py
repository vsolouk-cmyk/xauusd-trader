#!/usr/bin/env python3
"""
Stage166B Historical Current-Event Panel Rebuild

Builds a trainable historical current-event shock panel for XAUUSD/gold.
This stage is read-only for trading: it never writes MT5 KV files and never
allows demo/live routing.

Primary purpose:
- Replace sparse recent-only event panels with a dense historical panel.
- Use historical GDELT DOC TimelineVolRaw counts and optional local/manual event files.
- Emit the same event-panel schema expected by Stage167.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import csv
import hashlib
import json
import math
import os
import re
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import pandas as pd

STAGE = "Stage166C_FAST_GDELT_HISTORICAL_EVENT_PANEL_REBUILD"

PROFILE_SPECS: Dict[str, Dict[str, Any]] = {
    "geopolitical_escalation": {
        "query": '(gold OR bullion OR xauusd) (war OR conflict OR missile OR attack OR invasion OR sanction OR geopolitical OR "middle east" OR israel OR iran OR russia OR ukraine)',
        "score_col": "geopolitical_escalation_score",
        "long_weight": 1.00,
        "short_weight": 0.00,
    },
    "deescalation": {
        "query": '(gold OR bullion OR xauusd) (ceasefire OR truce OR "peace talks" OR deescalation OR de-escalation OR diplomacy OR "hostage deal")',
        "score_col": "deescalation_score",
        "long_weight": 0.00,
        "short_weight": 0.65,
    },
    "macro_policy_hawkish": {
        "query": '(gold OR bullion OR xauusd OR dollar) (fed OR fomc OR powell OR "federal reserve" OR rates OR yields) (hawkish OR hike OR tightening OR inflation OR "higher for longer")',
        "score_col": "macro_policy_hawkish_score",
        "long_weight": 0.00,
        "short_weight": 1.00,
    },
    "macro_policy_dovish": {
        "query": '(gold OR bullion OR xauusd OR dollar) (fed OR fomc OR powell OR "federal reserve" OR rates OR yields) (dovish OR cut OR easing OR recession OR slowdown)',
        "score_col": "macro_policy_dovish_score",
        "long_weight": 0.85,
        "short_weight": 0.00,
    },
    "inflation_energy_shock": {
        "query": '(gold OR bullion OR xauusd OR dollar) (oil OR energy OR inflation OR cpi OR pce OR tariff OR supply shock OR "red sea" OR shipping)',
        "score_col": "inflation_energy_shock_score",
        "long_weight": 0.70,
        "short_weight": 0.10,
    },
}

PANEL_COLUMNS = [
    "time_bucket_utc",
    "event_count",
    "gold_long_pressure",
    "gold_short_pressure",
    "shock_abs",
    "geopolitical_escalation_score",
    "deescalation_score",
    "macro_policy_hawkish_score",
    "macro_policy_dovish_score",
    "inflation_energy_shock_score",
    "net_gold_event_pressure",
    "event_shock_regime",
]


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, obj: Dict[str, Any]) -> None:
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")


def normalize_col(c: Any) -> str:
    s = str(c).strip().strip("\ufeff").replace("<", "").replace(">", "")
    return s.lower().replace(" ", "_").replace("-", "_").replace("/", "_")


def _read_csv_auto(path: Path, nrows: Optional[int] = None) -> pd.DataFrame:
    best_sep = ","
    best_score = -1
    for sep in ["\t", ",", ";", "|"]:
        try:
            df = pd.read_csv(path, sep=sep, nrows=5)
            score = len(df.columns)
            if score > best_score:
                best_score = score
                best_sep = sep
        except Exception:
            continue
    return pd.read_csv(path, sep=best_sep, nrows=nrows)


def load_bars(path: Path, timestamp_shift_hours: float = -3.0) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(str(path))
    df = _read_csv_auto(path)
    raw_cols = list(df.columns)
    df.columns = [normalize_col(c) for c in df.columns]
    meta: Dict[str, Any] = {
        "source_path": str(path),
        "raw_columns": raw_cols,
        "raw_row_count": int(len(df)),
        "timestamp_shift_hours": timestamp_shift_hours,
    }
    if "date" in df.columns and "time" in df.columns:
        ts = pd.to_datetime(
            df["date"].astype(str).str.strip() + " " + df["time"].astype(str).str.strip(),
            format="%Y.%m.%d %H:%M:%S",
            errors="coerce",
            utc=False,
        )
        ts = ts + pd.to_timedelta(timestamp_shift_hours, unit="h")
        ts = pd.to_datetime(ts, utc=True, errors="coerce")
        meta["parse_mode"] = "mt5_split_date_time"
    else:
        time_col = None
        for c in ["time_utc", "utc_time", "datetime", "timestamp", "server_time", "time"]:
            if c in df.columns:
                time_col = c
                break
        if not time_col:
            for c in df.columns:
                if any(x in c for x in ["date", "time", "utc"]):
                    time_col = c
                    break
        if not time_col:
            raise ValueError(f"No timestamp column in {path}; columns={list(df.columns)}")
        ts = pd.to_datetime(df[time_col], errors="coerce", utc=True)
        if timestamp_shift_hours and time_col not in {"time_utc", "utc_time"}:
            ts = ts + pd.to_timedelta(timestamp_shift_hours, unit="h")
        meta["parse_mode"] = f"single_timestamp:{time_col}"
    out = pd.DataFrame({"time_utc": ts})
    for c in ["open", "high", "low", "close", "spread"]:
        if c in df.columns:
            out[c] = pd.to_numeric(df[c], errors="coerce")
    out = out.dropna(subset=["time_utc"]).sort_values("time_utc").drop_duplicates("time_utc", keep="last").reset_index(drop=True)
    meta.update({
        "bar_count": int(len(out)),
        "min_time_utc": str(out["time_utc"].min()) if len(out) else None,
        "max_time_utc": str(out["time_utc"].max()) if len(out) else None,
    })
    return out, meta


def parse_dt_any(x: Any) -> Optional[pd.Timestamp]:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return None
    s = str(x).strip()
    if not s:
        return None
    # GDELT usually emits YYYYMMDDHHMMSS or YYYYMMDDTHHMMSSZ-like strings.
    digits = re.sub(r"\D", "", s)
    if len(digits) >= 14:
        try:
            return pd.to_datetime(digits[:14], format="%Y%m%d%H%M%S", utc=True)
        except Exception:
            pass
    if len(digits) == 8:
        try:
            return pd.to_datetime(digits, format="%Y%m%d", utc=True)
        except Exception:
            pass
    try:
        return pd.to_datetime(s, errors="coerce", utc=True)
    except Exception:
        return None


def dt_to_gdelt(ts: pd.Timestamp) -> str:
    ts = pd.to_datetime(ts, utc=True)
    return ts.strftime("%Y%m%d%H%M%S")


def chunk_ranges(start: pd.Timestamp, end: pd.Timestamp, days: int) -> Iterable[Tuple[pd.Timestamp, pd.Timestamp]]:
    cur = pd.to_datetime(start, utc=True)
    end = pd.to_datetime(end, utc=True)
    step = pd.Timedelta(days=max(1, int(days)))
    while cur < end:
        nxt = min(cur + step, end)
        yield cur, nxt
        cur = nxt + pd.Timedelta(seconds=1)


def cache_key(url: str) -> str:
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:20]


def gdelt_url(query: str, start: pd.Timestamp, end: pd.Timestamp) -> str:
    params = {
        "query": query,
        "mode": "TimelineVolRaw",
        "format": "json",
        "startdatetime": dt_to_gdelt(start),
        "enddatetime": dt_to_gdelt(end),
        "timelinesmooth": "0",
    }
    return "https://api.gdeltproject.org/api/v2/doc/doc?" + urllib.parse.urlencode(params)


def extract_timeline_points(obj: Any, profile: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []

    def walk(x: Any) -> None:
        if isinstance(x, dict):
            keys = {str(k).lower(): k for k in x.keys()}
            date_key = None
            value_key = None
            for k in ["date", "datetime", "time", "timestamp"]:
                if k in keys:
                    date_key = keys[k]
                    break
            for k in ["value", "count", "total", "volume", "vol", "articlecount", "articles"]:
                if k in keys:
                    value_key = keys[k]
                    break
            if date_key is not None and value_key is not None:
                ts = parse_dt_any(x.get(date_key))
                try:
                    val = float(x.get(value_key))
                except Exception:
                    val = 0.0
                if ts is not None and pd.notna(ts):
                    rows.append({"time_utc": ts, "profile": profile, "raw_count": val})
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for item in x:
                walk(item)

    walk(obj)
    return rows


def _fetch_one_gdelt_task(task: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Fetch or load one GDELT timeline task. Kept top-level for thread safety."""
    profile = str(task["profile"])
    url = str(task["url"])
    path = Path(task["path"])
    timeout = int(task["timeout"])
    refresh_cache = bool(task["refresh_cache"])
    a = task["start"]
    b = task["end"]
    loaded_from_cache = path.exists() and not refresh_cache
    ok = False
    err = ""
    obj: Any = None
    if loaded_from_cache:
        try:
            obj = json.loads(path.read_text(encoding="utf-8"))
            ok = True
        except Exception as e:
            err = f"cache_read_failed:{type(e).__name__}:{e}"
    if not ok:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "xauusd-stage166c/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
            path.write_bytes(raw)
            obj = json.loads(raw.decode("utf-8", errors="replace"))
            ok = True
        except Exception as e:
            err = f"fetch_failed:{type(e).__name__}:{e}"
    points: List[Dict[str, Any]] = []
    if ok and obj is not None:
        points = extract_timeline_points(obj, profile)
    status = {
        "profile": profile,
        "start_utc": str(a),
        "end_utc": str(b),
        "cache_file": str(path),
        "loaded_from_cache": bool(loaded_from_cache),
        "ok": bool(ok),
        "point_count": int(len(points)),
        "error": err,
    }
    return points, status


def fetch_gdelt_history(
    cache_dir: Path,
    start: pd.Timestamp,
    end: pd.Timestamp,
    chunk_days: int,
    timeout: int,
    pause_seconds: float,
    refresh_cache: bool,
    max_workers: int = 5,
    max_queries: int = 0,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    ensure_dir(cache_dir)
    tasks: List[Dict[str, Any]] = []
    for profile, spec in PROFILE_SPECS.items():
        for a, b in chunk_ranges(start, end, chunk_days):
            url = gdelt_url(str(spec["query"]), a, b)
            path = cache_dir / f"{profile}_{dt_to_gdelt(a)}_{dt_to_gdelt(b)}_{cache_key(url)}.json"
            tasks.append({
                "profile": profile,
                "start": a,
                "end": b,
                "url": url,
                "path": str(path),
                "timeout": timeout,
                "refresh_cache": refresh_cache,
            })
    # Deterministic newest-first order is more useful commercially when max_queries is bounded.
    tasks = sorted(tasks, key=lambda t: (pd.to_datetime(t["end"], utc=True), str(t["profile"])), reverse=True)
    total_planned = len(tasks)
    if max_queries and max_queries > 0:
        tasks = tasks[: int(max_queries)]
    all_rows: List[Dict[str, Any]] = []
    status_rows: List[Dict[str, Any]] = []
    workers = max(1, min(int(max_workers), len(tasks) if tasks else 1))
    if tasks:
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
            futs = [ex.submit(_fetch_one_gdelt_task, t) for t in tasks]
            for fut in concurrent.futures.as_completed(futs):
                try:
                    points, status = fut.result()
                except Exception as e:
                    points, status = [], {"profile": "UNKNOWN", "ok": False, "point_count": 0, "error": f"worker_failed:{type(e).__name__}:{e}"}
                all_rows.extend(points)
                status_rows.append(status)
        if pause_seconds > 0:
            time.sleep(min(float(pause_seconds), 1.0))
    status = pd.DataFrame(status_rows)
    if len(status):
        status = status.sort_values(["profile", "start_utc"]).reset_index(drop=True)
        status.to_csv(cache_dir / "stage166b_fetch_status.csv", index=False)
    meta = {
        "fetch_query_count": int(len(status_rows)),
        "fetch_query_count_planned_before_limit": int(total_planned),
        "fetch_query_limit_applied": int(max_queries) if max_queries else 0,
        "fetch_ok_count": int(status["ok"].sum()) if len(status) and "ok" in status else 0,
        "fetch_point_count": int(len(all_rows)),
        "cache_dir": str(cache_dir),
        "max_workers": int(workers),
        "timeout_seconds": int(timeout),
        "chunk_days": int(chunk_days),
    }
    return pd.DataFrame(all_rows), meta


def load_manual_or_cached_events(event_inbox: Path) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Load optional user/event cache CSV files if present.

    Accepted schemas are intentionally loose. The best case schema is:
      time_utc, profile, raw_count
    Or direct score columns:
      time_utc, geopolitical_escalation_score, ...
    """
    if not event_inbox.exists():
        return pd.DataFrame(), {"event_inbox": str(event_inbox), "loaded_files": [], "row_count": 0}
    patterns = [
        "**/*stage166b*_events*.csv",
        "**/*current*event*.csv",
        "**/*manual*event*.csv",
        "**/*news*shock*.csv",
        "**/*gdelt*timeline*.csv",
        "**/*gdelt*events*.csv",
    ]
    candidates: List[Path] = []
    for pat in patterns:
        candidates.extend(event_inbox.glob(pat))
    candidates = sorted(set([p for p in candidates if p.is_file() and p.suffix.lower() == ".csv"]))
    rows: List[pd.DataFrame] = []
    loaded: List[Dict[str, Any]] = []
    for p in candidates:
        try:
            df = _read_csv_auto(p)
            raw_cols = list(df.columns)
            df.columns = [normalize_col(c) for c in df.columns]
            time_col = None
            for c in ["time_utc", "utc_time", "time_bucket_utc", "datetime", "timestamp", "date"]:
                if c in df.columns:
                    time_col = c
                    break
            if not time_col:
                loaded.append({"path": str(p), "loaded": False, "reason": "no_time_col", "raw_columns": raw_cols})
                continue
            df["time_utc"] = pd.to_datetime(df[time_col], errors="coerce", utc=True)
            df = df.dropna(subset=["time_utc"])
            if df.empty:
                loaded.append({"path": str(p), "loaded": False, "reason": "no_parseable_times", "raw_columns": raw_cols})
                continue
            if "profile" not in df.columns:
                # Convert direct score columns into profile rows where possible.
                direct_frames = []
                for profile, spec in PROFILE_SPECS.items():
                    score_col = spec["score_col"]
                    if score_col in df.columns:
                        t = df[["time_utc", score_col]].copy()
                        t["profile"] = profile
                        t["raw_count"] = pd.to_numeric(t[score_col], errors="coerce").fillna(0.0)
                        direct_frames.append(t[["time_utc", "profile", "raw_count"]])
                if direct_frames:
                    out = pd.concat(direct_frames, ignore_index=True)
                else:
                    count_col = None
                    for c in ["event_count", "count", "raw_count", "value", "score"]:
                        if c in df.columns:
                            count_col = c
                            break
                    out = df[["time_utc"]].copy()
                    out["profile"] = "geopolitical_escalation"
                    out["raw_count"] = pd.to_numeric(df[count_col], errors="coerce").fillna(1.0) if count_col else 1.0
            else:
                count_col = "raw_count" if "raw_count" in df.columns else "event_count" if "event_count" in df.columns else "count" if "count" in df.columns else "value" if "value" in df.columns else None
                out = df[["time_utc", "profile"]].copy()
                out["profile"] = out["profile"].astype(str).str.strip().str.lower()
                out["raw_count"] = pd.to_numeric(df[count_col], errors="coerce").fillna(1.0) if count_col else 1.0
            rows.append(out)
            loaded.append({"path": str(p), "loaded": True, "row_count": int(len(out)), "raw_columns": raw_cols})
        except Exception as e:
            loaded.append({"path": str(p), "loaded": False, "reason": f"{type(e).__name__}:{e}"})
    if rows:
        combined = pd.concat(rows, ignore_index=True)
    else:
        combined = pd.DataFrame(columns=["time_utc", "profile", "raw_count"])
    return combined, {"event_inbox": str(event_inbox), "loaded_files": loaded, "row_count": int(len(combined))}


def standardize_event_rows(events: pd.DataFrame) -> pd.DataFrame:
    if events.empty:
        return pd.DataFrame(columns=["time_utc", "profile", "raw_count"])
    e = events.copy()
    e["time_utc"] = pd.to_datetime(e["time_utc"], errors="coerce", utc=True)
    e["profile"] = e["profile"].astype(str).str.strip().str.lower()
    aliases = {
        "geopolitical": "geopolitical_escalation",
        "geo": "geopolitical_escalation",
        "war": "geopolitical_escalation",
        "macro_hawkish": "macro_policy_hawkish",
        "hawkish": "macro_policy_hawkish",
        "macro_dovish": "macro_policy_dovish",
        "dovish": "macro_policy_dovish",
        "inflation": "inflation_energy_shock",
        "energy": "inflation_energy_shock",
    }
    e["profile"] = e["profile"].map(lambda x: aliases.get(x, x))
    e = e[e["profile"].isin(PROFILE_SPECS.keys())].copy()
    e["raw_count"] = pd.to_numeric(e["raw_count"], errors="coerce").fillna(0.0).clip(lower=0)
    e = e.dropna(subset=["time_utc"])
    e["time_bucket_utc"] = e["time_utc"].dt.floor("1h")
    return e[["time_bucket_utc", "profile", "raw_count"]]


def score_events(events: pd.DataFrame) -> pd.DataFrame:
    if events.empty:
        return pd.DataFrame(columns=["time_bucket_utc", "profile", "raw_count", "score"])
    e = events.copy()
    e["raw_count"] = pd.to_numeric(e["raw_count"], errors="coerce").fillna(0.0).clip(lower=0)
    # Use log1p counts to reduce article-volume dominance. Normalize by profile median absolute scale.
    e["log_count"] = e["raw_count"].map(lambda x: math.log1p(float(x)))
    scored_parts: List[pd.DataFrame] = []
    for profile, sub in e.groupby("profile"):
        scale = float(sub["log_count"].quantile(0.75)) if len(sub) else 1.0
        if not math.isfinite(scale) or scale <= 0:
            scale = 1.0
        t = sub.copy()
        t["score"] = (t["log_count"] / scale).clip(lower=0, upper=5)
        scored_parts.append(t)
    return pd.concat(scored_parts, ignore_index=True) if scored_parts else pd.DataFrame(columns=["time_bucket_utc", "profile", "raw_count", "score"])


def build_dense_hourly_panel(
    scored: pd.DataFrame,
    start: pd.Timestamp,
    end: pd.Timestamp,
    carry_hours: int = 24,
) -> pd.DataFrame:
    start = pd.to_datetime(start, utc=True).floor("1h")
    end = pd.to_datetime(end, utc=True).ceil("1h")
    idx = pd.date_range(start=start, end=end, freq="1h", tz="UTC")
    panel = pd.DataFrame({"time_bucket_utc": idx})
    for profile, spec in PROFILE_SPECS.items():
        score_col = spec["score_col"]
        if scored.empty:
            series = pd.Series(0.0, index=idx)
        else:
            sub = scored[scored["profile"] == profile]
            if sub.empty:
                series = pd.Series(0.0, index=idx)
            else:
                h = sub.groupby("time_bucket_utc")["score"].sum()
                h.index = pd.to_datetime(h.index, utc=True)
                h = h.reindex(idx, fill_value=0.0)
                # 24-hour rolling intensity creates an event-impact state rather than a one-hour blip.
                series = h.rolling(max(1, int(carry_hours)), min_periods=1).sum()
        panel[score_col] = series.values

    if scored.empty:
        event_count = pd.Series(0.0, index=idx)
    else:
        raw = scored.groupby("time_bucket_utc")["raw_count"].sum()
        raw.index = pd.to_datetime(raw.index, utc=True)
        raw = raw.reindex(idx, fill_value=0.0)
        event_count = raw.rolling(max(1, int(carry_hours)), min_periods=1).sum()
    panel["event_count"] = event_count.values

    long_pressure = pd.Series(0.0, index=panel.index)
    short_pressure = pd.Series(0.0, index=panel.index)
    for _profile, spec in PROFILE_SPECS.items():
        score_col = spec["score_col"]
        long_pressure += panel[score_col] * float(spec["long_weight"])
        short_pressure += panel[score_col] * float(spec["short_weight"])
    panel["gold_long_pressure"] = long_pressure
    panel["gold_short_pressure"] = short_pressure
    panel["net_gold_event_pressure"] = panel["gold_long_pressure"] - panel["gold_short_pressure"]
    panel["shock_abs"] = panel["gold_long_pressure"].abs() + panel["gold_short_pressure"].abs()

    def regime(row: pd.Series) -> str:
        if row["shock_abs"] <= 0:
            return "NO_CURRENT_EVENT_SHOCK"
        net = row["net_gold_event_pressure"]
        if net >= 1.5:
            return "EVENT_GOLD_LONG_PRESSURE"
        if net <= -1.5:
            return "EVENT_GOLD_SHORT_PRESSURE"
        return "EVENT_MIXED_OR_LOW_CONVICTION"

    panel["event_shock_regime"] = panel.apply(regime, axis=1)
    return panel[PANEL_COLUMNS]


def join_panel_to_bars(bars: pd.DataFrame, panel: pd.DataFrame) -> pd.DataFrame:
    b = bars[["time_utc"]].copy().sort_values("time_utc")
    p = panel.copy().sort_values("time_bucket_utc")
    p["time_bucket_utc"] = pd.to_datetime(p["time_bucket_utc"], utc=True)
    out = pd.merge_asof(b, p, left_on="time_utc", right_on="time_bucket_utc", direction="backward", tolerance=pd.Timedelta(hours=1))
    for c in PANEL_COLUMNS:
        if c == "time_bucket_utc" or c == "event_shock_regime":
            continue
        if c in out.columns:
            out[c] = pd.to_numeric(out[c], errors="coerce").fillna(0.0)
    if "event_shock_regime" in out.columns:
        out["event_shock_regime"] = out["event_shock_regime"].fillna("NO_CURRENT_EVENT_SHOCK")
    return out


def event_panel_health(bars: pd.DataFrame, panel: pd.DataFrame, holdout_pct: float, min_train_active_event_bars: int, min_panel_rows: int) -> Dict[str, Any]:
    joined = join_panel_to_bars(bars, panel)
    n = len(joined)
    split_idx = int(n * (1.0 - holdout_pct)) if n else 0
    train = joined.iloc[:split_idx]
    holdout = joined.iloc[split_idx:]
    active = lambda df: int(((pd.to_numeric(df.get("shock_abs", 0), errors="coerce").fillna(0) > 0) | (pd.to_numeric(df.get("event_count", 0), errors="coerce").fillna(0) > 0)).sum()) if len(df) else 0
    shock_nonzero = int((pd.to_numeric(panel.get("shock_abs", 0), errors="coerce").fillna(0) > 0).sum()) if len(panel) else 0
    long_nonzero = int((pd.to_numeric(panel.get("gold_long_pressure", 0), errors="coerce").fillna(0) > 0).sum()) if len(panel) else 0
    short_nonzero = int((pd.to_numeric(panel.get("gold_short_pressure", 0), errors="coerce").fillna(0) > 0).sum()) if len(panel) else 0
    train_active = active(train)
    reasons = []
    if len(panel) < min_panel_rows:
        reasons.append("PANEL_ROWS_LT_MIN")
    if train_active < min_train_active_event_bars:
        reasons.append("TRAIN_ACTIVE_EVENT_BARS_LT_MIN")
    if shock_nonzero == 0:
        reasons.append("SHOCK_ALL_ZERO")
    return {
        "panel_rows": int(len(panel)),
        "panel_nonzero_shock_rows": shock_nonzero,
        "panel_nonzero_long_rows": long_nonzero,
        "panel_nonzero_short_rows": short_nonzero,
        "bar_rows": int(n),
        "holdout_pct": holdout_pct,
        "train_rows": int(len(train)),
        "holdout_rows": int(len(holdout)),
        "train_active_event_bars": train_active,
        "holdout_active_event_bars": active(holdout),
        "min_panel_rows": int(min_panel_rows),
        "min_train_active_event_bars": int(min_train_active_event_bars),
        "event_overlay_trainable": len(reasons) == 0,
        "reasons": reasons,
    }


def run(args: argparse.Namespace) -> Dict[str, Any]:
    root = Path(args.root).expanduser().resolve()
    report_dir = root / "reports" / "stage166b_historical_current_event_panel_rebuild"
    ensure_dir(report_dir)
    outputs = {
        "summary_json": str(report_dir / "stage166b_historical_current_event_panel_rebuild_summary.json"),
        "normalized_events_csv": str(report_dir / "stage166b_normalized_historical_events.csv"),
        "current_event_intraday_panel_csv": str(report_dir / "stage166b_current_event_intraday_panel.csv"),
        "fetch_status_csv": str(report_dir / "stage166b_fetch_status.csv"),
        "compatible_stage166_panel_csv": str(root / "reports" / "stage166_current_event_shock_overlay" / "stage166_current_event_intraday_panel.csv"),
    }
    try:
        bars, bars_meta = load_bars(Path(args.bars_m5).expanduser(), args.timestamp_shift_hours)
        if args.start_date:
            start = pd.to_datetime(args.start_date, utc=True)
        else:
            start = pd.to_datetime(bars["time_utc"].min(), utc=True).floor("1D")
        if args.end_date:
            end = pd.to_datetime(args.end_date, utc=True)
        else:
            end = pd.to_datetime(bars["time_utc"].max(), utc=True).ceil("1h")
        event_inbox = Path(args.event_inbox).expanduser()

        local_events, local_meta = load_manual_or_cached_events(event_inbox)
        fetched_events = pd.DataFrame(columns=["time_utc", "profile", "raw_count"])
        fetch_meta: Dict[str, Any] = {"fetch_enabled": bool(args.fetch_gdelt_history)}
        if args.fetch_gdelt_history:
            cache_dir = event_inbox / "_processed" / "stage166b_gdelt_timeline_cache"
            fetched_events, fetch_meta = fetch_gdelt_history(
                cache_dir=cache_dir,
                start=start,
                end=end,
                chunk_days=args.gdelt_chunk_days,
                timeout=args.gdelt_timeout_seconds,
                pause_seconds=args.gdelt_pause_seconds,
                refresh_cache=args.refresh_gdelt_cache,
                max_workers=args.gdelt_max_workers,
                max_queries=args.gdelt_max_queries,
            )
            # Copy fetch status next to reports for quick review.
            cache_status = cache_dir / "stage166b_fetch_status.csv"
            if cache_status.exists():
                try:
                    pd.read_csv(cache_status).to_csv(outputs["fetch_status_csv"], index=False)
                except Exception:
                    pass
        all_events = pd.concat([local_events, fetched_events], ignore_index=True) if len(local_events) or len(fetched_events) else pd.DataFrame(columns=["time_utc", "profile", "raw_count"])
        normalized = standardize_event_rows(all_events)
        scored = score_events(normalized)
        scored.to_csv(outputs["normalized_events_csv"], index=False)
        panel = build_dense_hourly_panel(scored, start=start, end=end, carry_hours=args.carry_hours)
        panel.to_csv(outputs["current_event_intraday_panel_csv"], index=False)

        compatible_written = False
        compatible_backup = None
        if args.write_stage166_compatible_panel:
            compatible_path = Path(outputs["compatible_stage166_panel_csv"])
            ensure_dir(compatible_path.parent)
            if compatible_path.exists() and args.backup_existing_compatible_panel:
                compatible_backup = compatible_path.with_suffix(".pre_stage166b_backup.csv")
                try:
                    compatible_path.replace(compatible_backup)
                except Exception:
                    compatible_backup = None
            panel.to_csv(compatible_path, index=False)
            compatible_written = True

        health = event_panel_health(
            bars=bars,
            panel=panel,
            holdout_pct=args.holdout_pct,
            min_train_active_event_bars=args.min_train_active_event_bars,
            min_panel_rows=args.min_panel_rows,
        )
        decision = "STAGE166B_HISTORICAL_EVENT_PANEL_TRAINABLE_RUN_STAGE167_AGAIN" if health["event_overlay_trainable"] else "STAGE166B_EVENT_PANEL_STILL_NOT_TRAINABLE_DO_NOT_RUN_STAGE167"
        severity = "INFO" if health["event_overlay_trainable"] else "HIGH"
        recommended = "RUN_STAGE167_WITH_STAGE166B_PANEL" if health["event_overlay_trainable"] else "INSPECT_FETCH_STATUS_AND_ADD_MANUAL_OR_ALTERNATE_NEWS_HISTORY"
        summary = {
            "stage": STAGE,
            "generated_utc": now_utc_iso(),
            "root": str(root),
            "order_routing_allowed": False,
            "demo_release_allowed": False,
            "status": "STAGE166B_COMPLETE_HISTORICAL_EVENT_PANEL_REBUILD_READY",
            "decision": decision,
            "severity": severity,
            "recommended_action": recommended,
            "bars_m5": str(Path(args.bars_m5).expanduser()),
            "event_inbox": str(event_inbox),
            "start_utc": str(start),
            "end_utc": str(end),
            "bars_meta": bars_meta,
            "local_event_meta": local_meta,
            "gdelt_fetch_meta": fetch_meta,
            "normalized_event_rows": int(len(normalized)),
            "scored_event_rows": int(len(scored)),
            "panel_rows": int(len(panel)),
            "event_panel_health": health,
            "write_stage166_compatible_panel": bool(args.write_stage166_compatible_panel),
            "compatible_stage166_panel_written": compatible_written,
            "compatible_stage166_panel_backup": str(compatible_backup) if compatible_backup else None,
            "outputs": outputs,
            "next": [
                "If decision is trainable, rerun Stage167 using the Stage166B panel or the compatible Stage166 panel.",
                "If decision is still not trainable, inspect stage166b_fetch_status.csv and add a manual/current-event history CSV or alternate source.",
                "Do not use Stage167 results as event-aware until train_active_event_bars is nonzero and thresholds do not collapse.",
            ],
        }
        write_json(Path(outputs["summary_json"]), summary)
        return summary
    except Exception as e:
        summary = {
            "stage": STAGE,
            "generated_utc": now_utc_iso(),
            "root": str(root),
            "order_routing_allowed": False,
            "demo_release_allowed": False,
            "status": "STAGE166B_FAILURE_ARTIFACTS_WRITTEN",
            "decision": "STAGE166B_FAILED_DO_NOT_RUN_STAGE167_AS_EVENT_AWARE",
            "severity": "HIGH",
            "recommended_action": "INSPECT_ERROR_AND_REPAIR_EVENT_PANEL_REBUILD",
            "error_type": type(e).__name__,
            "error_message": str(e),
            "outputs": outputs,
        }
        ensure_dir(report_dir)
        write_json(Path(outputs["summary_json"]), summary)
        pd.DataFrame(columns=["time_bucket_utc", "profile", "raw_count", "score"]).to_csv(outputs["normalized_events_csv"], index=False)
        pd.DataFrame(columns=PANEL_COLUMNS).to_csv(outputs["current_event_intraday_panel_csv"], index=False)
        return summary


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Stage166B historical current-event panel rebuild")
    p.add_argument("--root", required=True)
    p.add_argument("--bars-m5", required=True)
    p.add_argument("--event-inbox", required=True)
    p.add_argument("--start-date", default="")
    p.add_argument("--end-date", default="")
    p.add_argument("--timestamp-shift-hours", type=float, default=-3.0)
    p.add_argument("--fetch-gdelt-history", action="store_true")
    p.add_argument("--refresh-gdelt-cache", action="store_true")
    p.add_argument("--gdelt-chunk-days", type=int, default=180)
    p.add_argument("--gdelt-timeout-seconds", type=int, default=8)
    p.add_argument("--gdelt-pause-seconds", type=float, default=0.05)
    p.add_argument("--gdelt-max-workers", type=int, default=5)
    p.add_argument("--gdelt-max-queries", type=int, default=0, help="0 means no cap; positive values bound the newest-first fetch task count")
    p.add_argument("--carry-hours", type=int, default=24)
    p.add_argument("--holdout-pct", type=float, default=0.20)
    p.add_argument("--min-panel-rows", type=int, default=3000)
    p.add_argument("--min-train-active-event-bars", type=int, default=500)
    p.add_argument("--write-stage166-compatible-panel", action="store_true")
    p.add_argument("--backup-existing-compatible-panel", action="store_true")
    return p


if __name__ == "__main__":
    print(json.dumps(run(build_arg_parser().parse_args()), indent=2, ensure_ascii=False, default=str))
