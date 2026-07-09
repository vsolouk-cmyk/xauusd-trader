#!/usr/bin/env python3
"""
Stage166 Current Event Shock Overlay

Commercial-purpose, read-only current-event/news-shock overlay for XAUUSD/gold.

What it does:
- Optionally fetches fresh GDELT DOC articles for gold-sensitive current-event queries.
- Reads local current-event/news artifacts already downloaded into the fundamental event inbox.
- Normalizes article/event-like records into a compact event table.
- Scores current-event pressure into gold-relevant shock dimensions.
- Builds daily and intraday shock panels and a strict latest-20% holdout map.
- Writes discovery-ready overlay artifacts for the next rule-discovery gate.

What it does NOT do:
- It does not write MT5 KV/CSV execution signals.
- It does not authorize demo, paper, or live orders.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import pandas as pd

STAGE = "Stage166_CURRENT_EVENT_SHOCK_OVERLAY"

DEFAULT_QUERIES = [
    'gold (war OR military OR missile OR attack OR ceasefire OR escalation OR sanctions OR geopolitical)',
    'xauusd OR "gold price" OR "safe haven"',
    'Iran Israel missile OR Middle East escalation OR Red Sea shipping',
    'Federal Reserve inflation dollar yields gold',
    'oil shock shipping sanctions dollar gold',
]

GDELT_DOC_ENDPOINT = "https://api.gdeltproject.org/api/v2/doc/doc"

# Scores are intentionally transparent and deterministic.  This is not an NLP model.
KEYWORD_WEIGHTS: Dict[str, List[Tuple[str, float]]] = {
    "geopolitical_escalation": [
        ("war", 3.0), ("missile", 3.0), ("strike", 2.6), ("attack", 2.5),
        ("airstrike", 3.2), ("drone", 2.0), ("military", 2.0), ("troop", 1.8),
        ("conflict", 2.2), ("invasion", 3.0), ("explosion", 2.2),
        ("nuclear", 3.0), ("retaliat", 2.6), ("escalat", 2.8),
        ("sanction", 2.0), ("blockade", 2.2), ("red sea", 2.5), ("strait", 2.2),
        ("iran", 1.6), ("israel", 1.6), ("russia", 1.2), ("ukraine", 1.2),
        ("middle east", 2.0), ("taiwan", 1.4), ("china", 1.0),
    ],
    "deescalation": [
        ("ceasefire", 3.0), ("truce", 2.8), ("peace", 2.0), ("talks", 1.4),
        ("deal", 1.2), ("agreement", 1.5), ("de-escalat", 2.8), ("deescalat", 2.8),
        ("withdraw", 1.8), ("diplomatic", 1.5),
    ],
    "macro_policy_hawkish": [
        ("hawkish", 2.5), ("rate hike", 3.0), ("higher for longer", 3.0),
        ("inflation hotter", 2.5), ("strong dollar", 2.0), ("yields rise", 2.0),
        ("treasury yields rise", 2.5), ("fed hold", 1.3), ("tightening", 2.0),
    ],
    "macro_policy_dovish": [
        ("dovish", 2.5), ("rate cut", 3.0), ("cuts rates", 3.0),
        ("weak dollar", 2.0), ("yields fall", 2.0), ("treasury yields fall", 2.5),
        ("easing", 2.0), ("recession fears", 2.5),
    ],
    "inflation_energy_shock": [
        ("oil surge", 2.6), ("oil prices rise", 2.4), ("energy shock", 3.0),
        ("shipping disruption", 2.4), ("supply disruption", 2.2),
        ("inflation", 1.2), ("cpi", 1.0), ("pce", 1.0),
    ],
    "gold_direct": [
        ("gold", 1.0), ("xauusd", 2.0), ("bullion", 1.3), ("safe haven", 2.2),
        ("precious metal", 1.0), ("central bank gold", 1.6),
    ],
}

SOURCE_PRIORITY = {
    "gdelt_doc": 1.0,
    "local_json": 0.9,
    "local_csv": 0.85,
    "local_text": 0.6,
}


def now_utc() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def now_utc_iso() -> str:
    return now_utc().isoformat().replace("+00:00", "Z")


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, obj: Dict[str, Any]) -> None:
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")


def normalize_col(c: Any) -> str:
    s = str(c).strip().strip("\ufeff")
    s = re.sub(r"[<>]", "", s)
    return s.lower().replace(" ", "_").replace("-", "_")


def stable_id(parts: Sequence[Any]) -> str:
    h = hashlib.sha256("|".join(str(x) for x in parts if x is not None).encode("utf-8", "ignore")).hexdigest()
    return h[:16]


def parse_dt(value: Any) -> Optional[pd.Timestamp]:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    # GDELT seendate is often YYYYMMDDTHHMMSSZ.
    for fmt in ["%Y%m%dT%H%M%SZ", "%Y%m%d%H%M%S", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S"]:
        try:
            return pd.Timestamp(datetime.strptime(s, fmt), tz="UTC")
        except Exception:
            pass
    try:
        ts = pd.to_datetime(s, errors="coerce", utc=True)
        if pd.isna(ts):
            return None
        return ts
    except Exception:
        return None


def read_text_safe(path: Path, limit_bytes: int = 1_000_000) -> str:
    try:
        if path.suffix.lower() == ".gz":
            with gzip.open(path, "rt", encoding="utf-8", errors="ignore") as f:
                return f.read(limit_bytes)
        return path.read_text(encoding="utf-8", errors="ignore")[:limit_bytes]
    except Exception:
        return ""


def json_walk_records(obj: Any, source_path: str) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    if isinstance(obj, dict):
        # Common article/event containers.
        for key in ["articles", "items", "events", "data", "results", "records"]:
            if isinstance(obj.get(key), list):
                for item in obj[key]:
                    if isinstance(item, dict):
                        records.append(item)
        # Treat a single dict with text-ish fields as a record.
        if any(k in obj for k in ["title", "url", "seendate", "date", "headline", "summary", "body", "text"]):
            records.append(obj)
    elif isinstance(obj, list):
        for item in obj:
            if isinstance(item, dict):
                records.append(item)
    for r in records:
        r.setdefault("_source_path", source_path)
    return records


def extract_record_fields(record: Dict[str, Any], source_kind: str, fallback_time: Optional[pd.Timestamp] = None) -> Dict[str, Any]:
    lower = {normalize_col(k): v for k, v in record.items()}
    title = lower.get("title") or lower.get("headline") or lower.get("name") or lower.get("summary") or ""
    url = lower.get("url") or lower.get("link") or lower.get("articleurl") or lower.get("sourceurl") or ""
    domain = lower.get("domain") or lower.get("sourcecountry") or lower.get("source") or ""
    text_fields = [title, lower.get("summary"), lower.get("description"), lower.get("body"), lower.get("text"), lower.get("themes")]
    text = " ".join(str(x) for x in text_fields if x is not None)
    dt = None
    for k in ["seendate", "date", "datetime", "timestamp", "published", "publishedat", "time_utc", "utc_time"]:
        if k in lower:
            dt = parse_dt(lower.get(k))
            if dt is not None:
                break
    if dt is None:
        dt = fallback_time or pd.Timestamp(now_utc())
    return {
        "event_id": stable_id([source_kind, dt, title, url, domain]),
        "time_utc": dt,
        "source_kind": source_kind,
        "source_path": str(record.get("_source_path", "")),
        "query": str(lower.get("query", "")),
        "title": str(title)[:500],
        "url": str(url)[:1000],
        "domain": str(domain)[:200],
        "text": text[:3000],
    }


def fetch_gdelt_articles(query: str, maxrecords: int, timespan_hours: int, timeout: int = 20) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    params = {
        "query": query,
        "mode": "artlist",
        "format": "json",
        "maxrecords": str(maxrecords),
        "sort": "datedesc",
        "timespan": f"{int(timespan_hours)}h",
    }
    url = GDELT_DOC_ENDPOINT + "?" + urllib.parse.urlencode(params)
    meta = {"query": query, "url": url, "ok": False, "article_count": 0, "error": None}
    req = urllib.request.Request(url, headers={"User-Agent": "xauusd-stage166/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "ignore")
        obj = json.loads(raw)
        articles = obj.get("articles", []) if isinstance(obj, dict) else []
        out: List[Dict[str, Any]] = []
        for a in articles:
            if not isinstance(a, dict):
                continue
            a = dict(a)
            a["query"] = query
            out.append(a)
        meta.update({"ok": True, "article_count": len(out)})
        return out, meta
    except Exception as e:
        meta.update({"error": f"{type(e).__name__}: {e}"})
        return [], meta


def collect_gdelt(event_inbox: Path, queries: Sequence[str], maxrecords: int, timespan_hours: int) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Optional[Path]]:
    raw_dir = event_inbox / "current_events" / "gdelt_doc"
    ensure_dir(raw_dir)
    stamp = now_utc().strftime("%Y%m%dT%H%M%SZ")
    raw_path = raw_dir / f"stage166_gdelt_doc_articles_{stamp}.jsonl"
    records: List[Dict[str, Any]] = []
    metas: List[Dict[str, Any]] = []
    with raw_path.open("w", encoding="utf-8") as f:
        for q in queries:
            articles, meta = fetch_gdelt_articles(q, maxrecords=maxrecords, timespan_hours=timespan_hours)
            metas.append(meta)
            for a in articles:
                a["_source_path"] = str(raw_path)
                a["_source_kind"] = "gdelt_doc"
                f.write(json.dumps(a, ensure_ascii=False, default=str) + "\n")
                records.append(a)
            time.sleep(0.35)
    return records, metas, raw_path


def load_local_event_records(event_inbox: Path, recent_days: int, max_files: int) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    cutoff = pd.Timestamp(now_utc() - timedelta(days=recent_days))
    patterns = ["**/*.json", "**/*.jsonl", "**/*.csv", "**/*.txt", "**/*.html"]
    files: List[Path] = []
    for pat in patterns:
        files.extend(event_inbox.glob(pat))
    # prioritize explicitly current/news/log/event-looking files and recent mtimes.
    def score_path(p: Path) -> Tuple[int, float, str]:
        name = str(p).lower()
        kscore = 0
        for k in ["gdelt", "news", "event", "fomc", "fred", "bls", "bea", "treasury", "logs", "macro"]:
            if k in name:
                kscore += 1
        try:
            mtime = p.stat().st_mtime
        except Exception:
            mtime = 0.0
        return (-kscore, -mtime, str(p))
    files = sorted(set(files), key=score_path)[:max_files]
    records: List[Dict[str, Any]] = []
    file_status: List[Dict[str, Any]] = []
    for p in files:
        suffix = p.suffix.lower()
        status = {"path": str(p), "records": 0, "kind": suffix, "error": None}
        try:
            if suffix == ".jsonl":
                for line in read_text_safe(p, limit_bytes=5_000_000).splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except Exception:
                        continue
                    if isinstance(obj, dict):
                        obj["_source_path"] = str(p)
                        records.append(obj)
                        status["records"] += 1
            elif suffix == ".json":
                text = read_text_safe(p, limit_bytes=5_000_000)
                if text:
                    obj = json.loads(text)
                    recs = json_walk_records(obj, str(p))
                    records.extend(recs)
                    status["records"] += len(recs)
            elif suffix == ".csv":
                try:
                    df = pd.read_csv(p, nrows=5000)
                    df.columns = [normalize_col(c) for c in df.columns]
                    for _, row in df.iterrows():
                        d = row.dropna().to_dict()
                        d["_source_path"] = str(p)
                        records.append(d)
                        status["records"] += 1
                except Exception:
                    pass
            elif suffix in {".txt", ".html"}:
                text = read_text_safe(p, limit_bytes=500_000)
                if text and any(k in text.lower() for k in ["gold", "war", "fed", "inflation", "missile", "sanction", "israel", "iran", "oil"]):
                    records.append({"title": p.name, "text": text[:5000], "date": datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc).isoformat(), "_source_path": str(p)})
                    status["records"] = 1
            file_status.append(status)
        except Exception as e:
            status["error"] = f"{type(e).__name__}: {e}"
            file_status.append(status)
    # Filter very old parsed timestamps only after extraction; many static release calendars are older but still have future dates.
    meta = {"event_inbox": str(event_inbox), "scanned_files": len(files), "file_status": file_status[:200], "raw_record_count": len(records), "recent_cutoff": str(cutoff)}
    return records, meta


def keyword_score(text: str) -> Dict[str, float]:
    low = text.lower()
    scores: Dict[str, float] = {}
    for bucket, pairs in KEYWORD_WEIGHTS.items():
        total = 0.0
        for kw, w in pairs:
            if kw in low:
                total += w
        scores[bucket] = total
    return scores


def recency_weight(ts: pd.Timestamp, half_life_hours: float, max_age_days: int) -> float:
    try:
        age_hours = max(0.0, (pd.Timestamp(now_utc()) - ts).total_seconds() / 3600.0)
    except Exception:
        age_hours = max_age_days * 24.0
    if age_hours > max_age_days * 24:
        return 0.0
    return float(0.5 ** (age_hours / max(1.0, half_life_hours)))


def normalize_and_score(records: List[Dict[str, Any]], source_kind_default: str, recent_days: int, half_life_hours: float) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    for r in records:
        source_kind = str(r.get("_source_kind") or source_kind_default)
        row = extract_record_fields(r, source_kind=source_kind)
        text = " ".join([row.get("title", ""), row.get("domain", ""), row.get("text", "")])
        scores = keyword_score(text)
        ts = pd.Timestamp(row["time_utc"])
        rw = recency_weight(ts, half_life_hours=half_life_hours, max_age_days=recent_days)
        source_w = SOURCE_PRIORITY.get(source_kind, SOURCE_PRIORITY.get(source_kind_default, 0.75))
        geop = scores["geopolitical_escalation"]
        deesc = scores["deescalation"]
        hawk = scores["macro_policy_hawkish"]
        dovish = scores["macro_policy_dovish"]
        energy = scores["inflation_energy_shock"]
        gold_direct = scores["gold_direct"]
        # Gold pressure: positive favors long/safe-haven/inflation hedge; negative favors short/risk-on/hawkish-real-yield headwind.
        gold_long_pressure = geop * 1.0 + dovish * 0.85 + energy * 0.55 + gold_direct * 0.25 - deesc * 0.75 - hawk * 0.80
        gold_short_pressure = hawk * 0.9 + deesc * 0.65 - geop * 0.35 - dovish * 0.55
        shock_abs = abs(gold_long_pressure) + 0.5 * (geop + hawk + dovish + energy + deesc)
        weighted_long = gold_long_pressure * rw * source_w
        weighted_short = gold_short_pressure * rw * source_w
        weighted_abs = shock_abs * rw * source_w
        if weighted_long >= 3.0 and weighted_long >= abs(weighted_short):
            side_bias = "LONG"
        elif weighted_short >= 3.0 and weighted_short > weighted_long:
            side_bias = "SHORT"
        elif weighted_abs >= 2.0:
            side_bias = "VOLATILITY_ONLY"
        else:
            side_bias = "NONE"
        out = {
            **{k: v for k, v in row.items() if k != "text"},
            "text_excerpt": row.get("text", "")[:500],
            "recency_weight": round(rw, 6),
            "source_weight": source_w,
            "geopolitical_escalation_score": round(geop, 4),
            "deescalation_score": round(deesc, 4),
            "macro_policy_hawkish_score": round(hawk, 4),
            "macro_policy_dovish_score": round(dovish, 4),
            "inflation_energy_shock_score": round(energy, 4),
            "gold_direct_score": round(gold_direct, 4),
            "gold_long_pressure_raw": round(gold_long_pressure, 4),
            "gold_short_pressure_raw": round(gold_short_pressure, 4),
            "shock_abs_raw": round(shock_abs, 4),
            "gold_long_pressure": round(weighted_long, 6),
            "gold_short_pressure": round(weighted_short, 6),
            "shock_abs": round(weighted_abs, 6),
            "event_side_bias": side_bias,
        }
        # Drop pure noise rows.
        if out["shock_abs_raw"] > 0 or out["gold_direct_score"] > 0:
            rows.append(out)
    if not rows:
        return pd.DataFrame(columns=["event_id", "time_utc", "source_kind", "title", "url", "gold_long_pressure", "gold_short_pressure", "shock_abs", "event_side_bias"])
    df = pd.DataFrame(rows)
    df["time_utc"] = pd.to_datetime(df["time_utc"], errors="coerce", utc=True)
    df = df.dropna(subset=["time_utc"]).sort_values("time_utc").drop_duplicates("event_id", keep="last")
    return df.reset_index(drop=True)


def load_bars(path: Path, timestamp_shift_hours: float = -3.0) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    if not path.exists():
        return pd.DataFrame(), {"loaded": False, "reason": "missing", "path": str(path)}
    # delimiter heuristic
    best_sep = ","
    best_cols = 0
    for sep in ["\t", ",", ";"]:
        try:
            test = pd.read_csv(path, sep=sep, nrows=5)
            if len(test.columns) > best_cols:
                best_cols = len(test.columns)
                best_sep = sep
        except Exception:
            pass
    df = pd.read_csv(path, sep=best_sep)
    raw_cols = list(df.columns)
    df.columns = [normalize_col(c) for c in df.columns]
    if "date" in df.columns and "time" in df.columns:
        ts = pd.to_datetime(df["date"].astype(str).str.strip() + " " + df["time"].astype(str).str.strip(), format="%Y.%m.%d %H:%M:%S", errors="coerce")
        ts = pd.to_datetime(ts + pd.to_timedelta(timestamp_shift_hours, unit="h"), utc=True, errors="coerce")
    else:
        time_col = None
        for c in ["time_utc", "utc_time", "datetime", "timestamp", "server_time", "time"]:
            if c in df.columns:
                time_col = c
                break
        if time_col is None:
            for c in df.columns:
                if any(x in c for x in ["date", "time", "utc"]):
                    time_col = c
                    break
        if time_col is None:
            return pd.DataFrame(), {"loaded": False, "reason": "no_timestamp", "path": str(path), "raw_columns": raw_cols}
        ts = pd.to_datetime(df[time_col], errors="coerce", utc=True)
    out = pd.DataFrame({"time_utc": ts})
    for c in ["open", "high", "low", "close", "volume", "tickvol", "spread"]:
        if c in df.columns:
            out[c] = pd.to_numeric(df[c], errors="coerce")
    if "volume" not in out.columns and "tickvol" in out.columns:
        out["volume"] = out["tickvol"]
    out = out.dropna(subset=["time_utc"]).sort_values("time_utc").drop_duplicates("time_utc", keep="last")
    meta = {
        "loaded": True,
        "path": str(path),
        "raw_rows": int(len(df)),
        "bar_count": int(len(out)),
        "min_time_utc": str(out["time_utc"].min()) if len(out) else None,
        "max_time_utc": str(out["time_utc"].max()) if len(out) else None,
        "raw_columns": raw_cols,
        "sep": best_sep,
    }
    return out.reset_index(drop=True), meta


def build_panels(events: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    if events.empty:
        cols = ["time_bucket_utc", "event_count", "gold_long_pressure", "gold_short_pressure", "shock_abs", "net_gold_event_pressure", "event_shock_regime"]
        return pd.DataFrame(columns=cols), pd.DataFrame(columns=["date_utc"] + cols[1:])
    x = events.copy()
    x["time_utc"] = pd.to_datetime(x["time_utc"], utc=True)
    x["time_bucket_utc"] = x["time_utc"].dt.floor("4h")
    x["date_utc"] = x["time_utc"].dt.floor("1d")
    agg_cols = {
        "event_id": "count",
        "gold_long_pressure": "sum",
        "gold_short_pressure": "sum",
        "shock_abs": "sum",
        "geopolitical_escalation_score": "sum",
        "deescalation_score": "sum",
        "macro_policy_hawkish_score": "sum",
        "macro_policy_dovish_score": "sum",
        "inflation_energy_shock_score": "sum",
    }
    intraday = x.groupby("time_bucket_utc").agg(agg_cols).rename(columns={"event_id": "event_count"}).reset_index()
    daily = x.groupby("date_utc").agg(agg_cols).rename(columns={"event_id": "event_count"}).reset_index()
    for df in [intraday, daily]:
        df["net_gold_event_pressure"] = df["gold_long_pressure"] - df["gold_short_pressure"]
        df["event_shock_regime"] = df.apply(classify_panel_row, axis=1)
    return intraday, daily


def classify_panel_row(row: pd.Series) -> str:
    net = float(row.get("net_gold_event_pressure", 0.0) or 0.0)
    shock = float(row.get("shock_abs", 0.0) or 0.0)
    if shock < 2.5:
        return "EVENT_NEUTRAL"
    if net >= 3.0:
        return "EVENT_SAFE_HAVEN_LONG_PRESSURE"
    if net <= -3.0:
        return "EVENT_RISK_ON_OR_HAWKISH_SHORT_PRESSURE"
    return "EVENT_VOLATILITY_SHOCK_NO_DIRECTION"


def build_holdout_map(bars: pd.DataFrame, holdout_pct: float) -> Dict[str, Any]:
    if bars.empty:
        return {"loaded": False, "reason": "bars_missing"}
    n = len(bars)
    holdout_n = max(1, int(math.ceil(n * holdout_pct)))
    split_idx = max(0, n - holdout_n)
    split_time = bars.iloc[split_idx]["time_utc"]
    return {
        "loaded": True,
        "bar_count": int(n),
        "holdout_pct": holdout_pct,
        "train_rows": int(split_idx),
        "holdout_rows": int(n - split_idx),
        "train_start_utc": str(bars.iloc[0]["time_utc"]),
        "train_end_utc": str(bars.iloc[split_idx - 1]["time_utc"]) if split_idx > 0 else None,
        "holdout_start_utc": str(split_time),
        "holdout_end_utc": str(bars.iloc[-1]["time_utc"]),
    }


def write_overlay_config(report_dir: Path, daily: pd.DataFrame, intraday: pd.DataFrame, holdout_map: Dict[str, Any], strict_gate_min_events: int) -> Path:
    latest_daily = daily.tail(1).to_dict("records")[0] if not daily.empty else {}
    latest_intraday = intraday.tail(1).to_dict("records")[0] if not intraday.empty else {}
    config = {
        "stage": STAGE,
        "generated_utc": now_utc_iso(),
        "order_routing_allowed": False,
        "demo_release_allowed": False,
        "intended_use": "feature overlay for Stage167 discovery and Stage168 holdout gate, not standalone signal",
        "holdout_policy": holdout_map,
        "recommended_feature_columns": [
            "event_count", "gold_long_pressure", "gold_short_pressure", "shock_abs",
            "net_gold_event_pressure", "event_shock_regime",
            "geopolitical_escalation_score", "deescalation_score", "macro_policy_hawkish_score",
            "macro_policy_dovish_score", "inflation_energy_shock_score",
        ],
        "candidate_filter_rules": [
            "Do not create a new low-frequency rule that depends only on rare event spikes.",
            "Use event_shock_regime as a regime/permission/blackout overlay first, not as a standalone entry trigger.",
            "Require the newest holdout segment to pass before demo expansion.",
            f"Require at least {strict_gate_min_events} holdout-resolved candidate events unless the rule is explicitly a market-open emergency-risk gate.",
        ],
        "latest_daily_event_state": latest_daily,
        "latest_intraday_event_state": latest_intraday,
    }
    p = report_dir / "stage166_current_event_overlay_config.json"
    write_json(p, config)
    return p


def run(args: argparse.Namespace) -> Dict[str, Any]:
    root = Path(args.root).expanduser().resolve()
    event_inbox = Path(args.event_inbox).expanduser().resolve()
    bars_m5 = Path(args.bars_m5).expanduser().resolve()
    report_dir = root / "reports" / "stage166_current_event_shock_overlay"
    ensure_dir(report_dir)

    outputs = {
        "summary_json": str(report_dir / "stage166_current_event_shock_overlay_summary.json"),
        "normalized_events_csv": str(report_dir / "stage166_normalized_current_events.csv"),
        "intraday_panel_csv": str(report_dir / "stage166_current_event_intraday_panel.csv"),
        "daily_panel_csv": str(report_dir / "stage166_current_event_daily_panel.csv"),
        "overlay_config_json": str(report_dir / "stage166_current_event_overlay_config.json"),
        "holdout_map_json": str(report_dir / "stage166_holdout_map.json"),
        "fetch_status_json": str(report_dir / "stage166_fetch_status.json"),
    }

    fetch_records: List[Dict[str, Any]] = []
    fetch_status: Dict[str, Any] = {"enabled": bool(args.fetch_gdelt), "metas": [], "raw_path": None}
    queries = [q.strip() for q in str(args.queries).split("||") if q.strip()] if args.queries else DEFAULT_QUERIES
    if args.fetch_gdelt:
        fetch_records, metas, raw_path = collect_gdelt(
            event_inbox=event_inbox,
            queries=queries,
            maxrecords=args.gdelt_maxrecords,
            timespan_hours=args.gdelt_timespan_hours,
        )
        fetch_status.update({"metas": metas, "raw_path": str(raw_path) if raw_path else None})

    local_records, local_meta = load_local_event_records(event_inbox, recent_days=args.recent_days, max_files=args.max_local_files)
    fetch_status["local_meta"] = local_meta
    write_json(Path(outputs["fetch_status_json"]), fetch_status)

    all_scored_parts: List[pd.DataFrame] = []
    if fetch_records:
        all_scored_parts.append(normalize_and_score(fetch_records, source_kind_default="gdelt_doc", recent_days=args.recent_days, half_life_hours=args.half_life_hours))
    if local_records:
        all_scored_parts.append(normalize_and_score(local_records, source_kind_default="local_json", recent_days=args.recent_days, half_life_hours=args.half_life_hours))
    events = pd.concat(all_scored_parts, ignore_index=True) if all_scored_parts else normalize_and_score([], "local_json", args.recent_days, args.half_life_hours)
    if not events.empty:
        events = events.sort_values("time_utc").drop_duplicates("event_id", keep="last").reset_index(drop=True)
    events.to_csv(outputs["normalized_events_csv"], index=False)

    intraday, daily = build_panels(events)
    intraday.to_csv(outputs["intraday_panel_csv"], index=False)
    daily.to_csv(outputs["daily_panel_csv"], index=False)

    bars, bars_meta = load_bars(bars_m5, timestamp_shift_hours=args.timestamp_shift_hours)
    holdout_map = build_holdout_map(bars, holdout_pct=args.holdout_pct)
    write_json(Path(outputs["holdout_map_json"]), holdout_map)
    overlay_config_path = write_overlay_config(report_dir, daily, intraday, holdout_map, strict_gate_min_events=args.strict_gate_min_events)

    event_count = int(len(events))
    latest_state = daily.tail(1).to_dict("records")[0] if not daily.empty else {}
    actionable_panels = int((intraday["event_shock_regime"] != "EVENT_NEUTRAL").sum()) if not intraday.empty else 0
    if event_count == 0:
        decision = "STAGE166_CURRENT_EVENT_DATA_MISSING_BLOCK_DISCOVERY_RELEASE"
        severity = "HIGH"
        recommended_action = "ENABLE_GDELT_FETCH_OR_ADD_CURRENT_EVENT_FEEDS_BEFORE_NEXT_RULE_DISCOVERY"
    elif actionable_panels == 0:
        decision = "STAGE166_EVENTS_LOADED_BUT_NO_ACTIONABLE_SHOCK_KEEP_AS_CONTEXT_ONLY"
        severity = "WARN"
        recommended_action = "USE_PANEL_AS_BLACKOUT_CONTEXT_ONLY_UNTIL_SHOCK_STATE_APPEARS"
    else:
        decision = "STAGE166_CURRENT_EVENT_SHOCK_OVERLAY_READY_FOR_STAGE167_DISCOVERY"
        severity = "MEDIUM"
        recommended_action = "RUN_STAGE167_EVENT_AWARE_RULE_DISCOVERY_WITH_20PCT_HOLDOUT"

    summary = {
        "stage": STAGE,
        "generated_utc": now_utc_iso(),
        "root": str(root),
        "event_inbox": str(event_inbox),
        "bars_m5": str(bars_m5),
        "order_routing_allowed": False,
        "demo_release_allowed": False,
        "status": "STAGE166_COMPLETE_CURRENT_EVENT_SHOCK_OVERLAY_READY",
        "decision": decision,
        "severity": severity,
        "recommended_action": recommended_action,
        "event_count": event_count,
        "gdelt_fetch_enabled": bool(args.fetch_gdelt),
        "gdelt_success_count": int(sum(1 for m in fetch_status.get("metas", []) if m.get("ok"))),
        "local_raw_record_count": int(local_meta.get("raw_record_count", 0)),
        "intraday_panel_rows": int(len(intraday)),
        "daily_panel_rows": int(len(daily)),
        "actionable_intraday_panel_count": actionable_panels,
        "latest_daily_event_state": latest_state,
        "bars_meta": bars_meta,
        "holdout_map": holdout_map,
        "outputs": outputs,
        "next": [
            "Do not route orders from Stage166.",
            "Use Stage166 overlay only as a current-event regime feature, permission filter, or blackout overlay.",
            "Run Stage167 as high-frequency event-aware discovery with the newest 20% holdout locked out from tuning.",
            "Reject any candidate that still has low frequency plus weak win rate/edge after event overlay.",
        ],
    }
    write_json(Path(outputs["summary_json"]), summary)
    return summary


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Stage166 current-event/news-shock overlay for XAUUSD")
    p.add_argument("--root", default="~/Desktop/xauusd-trader")
    p.add_argument("--event-inbox", default="~/Downloads/xauusd_fundamental_event_inbox")
    p.add_argument("--bars-m5", default="~/Downloads/xauusd_fundamental_event_inbox/amarkets_xauusd_5m.csv")
    p.add_argument("--timestamp-shift-hours", type=float, default=-3.0)
    p.add_argument("--fetch-gdelt", action="store_true", help="Fetch fresh GDELT DOC article lists before scoring")
    p.add_argument("--gdelt-maxrecords", type=int, default=75)
    p.add_argument("--gdelt-timespan-hours", type=int, default=72)
    p.add_argument("--queries", default="", help="Override GDELT queries separated by ||")
    p.add_argument("--recent-days", type=int, default=30)
    p.add_argument("--half-life-hours", type=float, default=36.0)
    p.add_argument("--max-local-files", type=int, default=250)
    p.add_argument("--holdout-pct", type=float, default=0.20)
    p.add_argument("--strict-gate-min-events", type=int, default=40)
    return p


if __name__ == "__main__":
    result = run(build_arg_parser().parse_args())
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
