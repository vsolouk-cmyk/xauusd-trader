#!/usr/bin/env python3
"""
Stage166E Event Data Failover Intake

Purpose:
- Do not depend on a single network path/source (e.g., GDELT only).
- Try fast URL probes with urllib and/or curl, ingest local browser-downloaded files,
  and ingest a manual event seed CSV.
- Score external/current events into a Stage166-compatible hourly event panel.
- Never routes demo/live orders.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
import subprocess
import sys
import tempfile
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import pandas as pd

STAGE = "Stage166E_EVENT_DATA_FAILOVER_INTAKE"


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, obj: Dict[str, Any]) -> None:
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")


def normalize_col(c: Any) -> str:
    s = str(c).strip().strip("\ufeff")
    s = s.replace("<", "").replace(">", "")
    return s.lower().replace(" ", "_").replace("-", "_")


def _read_csv_auto(path: Path, nrows: Optional[int] = None) -> pd.DataFrame:
    best_sep, best_score = ",", -1
    for sep in ["\t", ",", ";", "|"]:
        try:
            df = pd.read_csv(path, sep=sep, nrows=5)
            score = len(df.columns)
            if score > best_score:
                best_sep, best_score = sep, score
        except Exception:
            pass
    return pd.read_csv(path, sep=best_sep, nrows=nrows)


def load_bars(path: Path, timestamp_shift_hours: float = -3.0) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(str(path))
    df = _read_csv_auto(path)
    raw_cols = list(df.columns)
    df.columns = [normalize_col(c) for c in df.columns]
    if "date" in df.columns and "time" in df.columns:
        ts = pd.to_datetime(
            df["date"].astype(str).str.strip() + " " + df["time"].astype(str).str.strip(),
            format="%Y.%m.%d %H:%M:%S",
            errors="coerce",
            utc=False,
        )
        ts = ts + pd.to_timedelta(timestamp_shift_hours, unit="h")
        ts = pd.to_datetime(ts, utc=True, errors="coerce")
        parse_mode = "mt5_split_date_time"
    else:
        tcol = None
        for c in ["time_utc", "utc_time", "datetime", "timestamp", "time"]:
            if c in df.columns:
                tcol = c
                break
        if not tcol:
            for c in df.columns:
                if any(k in c for k in ["date", "time", "utc"]):
                    tcol = c
                    break
        if not tcol:
            raise ValueError(f"No timestamp column found in {path}")
        ts = pd.to_datetime(df[tcol], errors="coerce", utc=True)
        parse_mode = f"single_timestamp:{tcol}"
    out = pd.DataFrame({"time_utc": ts})
    for c in ["open", "high", "low", "close", "tickvol", "volume", "spread"]:
        if c in df.columns:
            dst = "volume" if c in {"tickvol"} else c
            out[dst] = pd.to_numeric(df[c], errors="coerce")
    for c in ["open", "high", "low", "close"]:
        if c not in out.columns:
            raise ValueError(f"Missing OHLC column: {c}")
    if "spread" not in out.columns:
        out["spread"] = float("nan")
    out = out.dropna(subset=["time_utc", "open", "high", "low", "close"]).sort_values("time_utc")
    out = out.drop_duplicates("time_utc", keep="last").reset_index(drop=True)
    meta = {
        "source_path": str(path),
        "raw_columns": raw_cols,
        "raw_row_count": int(len(df)),
        "timestamp_shift_hours": timestamp_shift_hours,
        "parse_mode": parse_mode,
        "bar_count": int(len(out)),
        "min_time_utc": str(out["time_utc"].min()) if len(out) else None,
        "max_time_utc": str(out["time_utc"].max()) if len(out) else None,
        "spread_nonnull_pct": round(float(out["spread"].notna().mean() * 100.0), 4) if len(out) else 0.0,
    }
    return out, meta


DEFAULT_URLS = [
    {
        "name": "google_news_gold_geopolitics_rss",
        "url": "https://news.google.com/rss/search?q=gold%20geopolitical%20risk%20OR%20XAUUSD&hl=en-US&gl=US&ceid=US:en",
        "format": "rss",
    },
    {
        "name": "google_news_gold_fed_rss",
        "url": "https://news.google.com/rss/search?q=gold%20Federal%20Reserve%20yields%20dollar&hl=en-US&gl=US&ceid=US:en",
        "format": "rss",
    },
    {
        "name": "gdelt_doc_gold_timeline_24h",
        "url": "https://api.gdeltproject.org/api/v2/doc/doc?query=gold%20OR%20XAUUSD%20OR%20geopolitical%20risk&mode=timelinevolraw&format=csv&timespan=24h",
        "format": "csv",
    },
]


@dataclass
class Event:
    timestamp_utc: pd.Timestamp
    source: str
    title: str
    description: str = ""
    url: str = ""
    category_hint: str = ""
    side_hint: str = ""
    impact: float = 1.0
    confidence: float = 0.6
    decay_hours: float = 72.0
    ingestion_method: str = "unknown"

    def text(self) -> str:
        return f"{self.title} {self.description} {self.category_hint} {self.side_hint}".lower()


def parse_any_datetime(x: Any, fallback: Optional[pd.Timestamp] = None) -> Optional[pd.Timestamp]:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return fallback
    s = str(x).strip()
    if not s:
        return fallback
    try:
        dt = parsedate_to_datetime(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return pd.Timestamp(dt).tz_convert("UTC")
    except Exception:
        pass
    try:
        return pd.to_datetime(s, errors="raise", utc=True)
    except Exception:
        return fallback


def fetch_url_urllib(name: str, url: str, timeout: int, max_bytes: int) -> Dict[str, Any]:
    t0 = datetime.now(timezone.utc)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 XAUUSD-stage166e"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = r.read(max_bytes)
            status = getattr(r, "status", 200)
        return {"name": name, "url": url, "ok": True, "transport": "urllib", "status": status, "bytes": len(data), "data": data, "error": "", "started_utc": t0.isoformat()}
    except Exception as e:
        return {"name": name, "url": url, "ok": False, "transport": "urllib", "status": None, "bytes": 0, "data": b"", "error": f"{type(e).__name__}: {e}", "started_utc": t0.isoformat()}


def fetch_url_curl(name: str, url: str, timeout: int, max_bytes: int) -> Dict[str, Any]:
    t0 = datetime.now(timezone.utc)
    if not shutil_which("curl"):
        return {"name": name, "url": url, "ok": False, "transport": "curl", "status": None, "bytes": 0, "data": b"", "error": "curl_not_found", "started_utc": t0.isoformat()}
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        tmp_path = tmp.name
    try:
        cmd = ["curl", "-L", "--compressed", "--connect-timeout", str(timeout), "--max-time", str(timeout), "--retry", "0", "-A", "Mozilla/5.0 XAUUSD-stage166e", "-o", tmp_path, "-w", "%{http_code}", url]
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 5)
        status_text = (p.stdout or "").strip()[-3:]
        status = int(status_text) if status_text.isdigit() else None
        data = Path(tmp_path).read_bytes()[:max_bytes]
        ok = p.returncode == 0 and status is not None and 200 <= status < 400 and len(data) > 0
        err = "" if ok else (p.stderr.strip() or f"curl_returncode={p.returncode} status={status}")
        return {"name": name, "url": url, "ok": ok, "transport": "curl", "status": status, "bytes": len(data), "data": data, "error": err, "started_utc": t0.isoformat()}
    except Exception as e:
        return {"name": name, "url": url, "ok": False, "transport": "curl", "status": None, "bytes": 0, "data": b"", "error": f"{type(e).__name__}: {e}", "started_utc": t0.isoformat()}
    finally:
        try:
            os.remove(tmp_path)
        except Exception:
            pass


def shutil_which(cmd: str) -> Optional[str]:
    for p in os.environ.get("PATH", "").split(os.pathsep):
        x = Path(p) / cmd
        if x.exists() and os.access(x, os.X_OK):
            return str(x)
    return None


def parse_rss_bytes(data: bytes, source_name: str) -> List[Event]:
    events: List[Event] = []
    try:
        root = ET.fromstring(data)
    except Exception:
        return events
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        desc = (item.findtext("description") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub = item.findtext("pubDate") or item.findtext("date") or item.findtext("updated")
        ts = parse_any_datetime(pub, pd.Timestamp.utcnow().tz_convert("UTC") if hasattr(pd.Timestamp.utcnow(), 'tz_convert') else pd.Timestamp.now(tz='UTC'))
        if title and ts is not None:
            events.append(Event(timestamp_utc=ts, source=source_name, title=title, description=desc, url=link, ingestion_method="rss"))
    return events


def _json_walk_articles(obj: Any) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if isinstance(obj, list):
        for x in obj:
            out.extend(_json_walk_articles(x))
    elif isinstance(obj, dict):
        # Common containers first.
        for key in ["articles", "items", "results", "data", "stories"]:
            if key in obj and isinstance(obj[key], list):
                out.extend(_json_walk_articles(obj[key]))
        # Treat leaf dict with a likely title/text field as article.
        if any(k in obj for k in ["title", "headline", "name"]):
            out.append(obj)
    return out


def parse_json_bytes(data: bytes, source_name: str) -> List[Event]:
    try:
        obj = json.loads(data.decode("utf-8", errors="replace"))
    except Exception:
        return []
    events: List[Event] = []
    for a in _json_walk_articles(obj):
        title = str(a.get("title") or a.get("headline") or a.get("name") or "").strip()
        desc = str(a.get("description") or a.get("summary") or a.get("content") or a.get("body") or "").strip()
        url = str(a.get("url") or a.get("link") or "").strip()
        date = a.get("publishedAt") or a.get("published_at") or a.get("date") or a.get("datetime") or a.get("timestamp")
        ts = parse_any_datetime(date, pd.Timestamp.now(tz="UTC"))
        if title and ts is not None:
            events.append(Event(timestamp_utc=ts, source=source_name, title=title, description=desc, url=url, ingestion_method="json"))
    return events


def detect_cols(df: pd.DataFrame) -> Dict[str, Optional[str]]:
    cols = {normalize_col(c): c for c in df.columns}
    def pick(cands: Sequence[str]) -> Optional[str]:
        for c in cands:
            if c in cols:
                return cols[c]
        for key, orig in cols.items():
            if any(c in key for c in cands):
                return orig
        return None
    return {
        "timestamp": pick(["timestamp_utc", "time_utc", "utc_time", "publishedat", "published_at", "pubdate", "date", "datetime", "time"]),
        "title": pick(["title", "headline", "name", "event", "summary"]),
        "description": pick(["description", "summary", "content", "text", "body"]),
        "source": pick(["source", "publisher", "domain"]),
        "url": pick(["url", "link"]),
        "category": pick(["category", "event_type", "tag"]),
        "side": pick(["side", "gold_side", "bias"]),
        "impact": pick(["impact", "severity", "score", "importance"]),
        "confidence": pick(["confidence", "conf"]),
        "decay_hours": pick(["decay_hours", "decay"]),
    }


def parse_csv_path(path: Path, source_name: str, ingestion_method: str = "csv") -> Tuple[List[Event], List[str]]:
    errors: List[str] = []
    try:
        df = _read_csv_auto(path)
    except Exception as e:
        return [], [f"{path}: read_csv_failed {type(e).__name__}: {e}"]
    if df.empty:
        return [], []
    cols = detect_cols(df)
    events: List[Event] = []
    for _, row in df.iterrows():
        title = str(row.get(cols["title"], "") if cols["title"] else "").strip()
        desc = str(row.get(cols["description"], "") if cols["description"] else "").strip()
        if not title and desc:
            title = desc[:120]
        if not title:
            continue
        ts = parse_any_datetime(row.get(cols["timestamp"], None) if cols["timestamp"] else None, pd.Timestamp.now(tz="UTC"))
        if ts is None:
            continue
        def fnum(name: str, default: float) -> float:
            c = cols.get(name)
            if not c:
                return default
            try:
                return float(row.get(c, default))
            except Exception:
                return default
        source = str(row.get(cols["source"], source_name) if cols["source"] else source_name).strip() or source_name
        events.append(Event(
            timestamp_utc=ts,
            source=source,
            title=title,
            description=desc,
            url=str(row.get(cols["url"], "") if cols["url"] else ""),
            category_hint=str(row.get(cols["category"], "") if cols["category"] else ""),
            side_hint=str(row.get(cols["side"], "") if cols["side"] else ""),
            impact=max(0.0, fnum("impact", 1.0)),
            confidence=min(1.0, max(0.0, fnum("confidence", 0.7))),
            decay_hours=max(1.0, fnum("decay_hours", 72.0)),
            ingestion_method=ingestion_method,
        ))
    return events, errors


def parse_fetched_result(res: Dict[str, Any], fmt: str) -> List[Event]:
    if not res.get("ok"):
        return []
    data = res.get("data") or b""
    source_name = str(res.get("name") or "fetch")
    fmt = (fmt or "").lower()
    if fmt == "rss" or data[:100].lstrip().startswith(b"<"):
        return parse_rss_bytes(data, source_name)
    if fmt == "json" or data[:20].lstrip().startswith((b"{", b"[")):
        return parse_json_bytes(data, source_name)
    if fmt == "csv" or b"," in data[:500]:
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
            tmp.write(data)
            tmp_path = Path(tmp.name)
        try:
            ev, _ = parse_csv_path(tmp_path, source_name, ingestion_method="fetched_csv")
            # GDELT timelinevolraw rows usually do not have article titles. Preserve as source-level events if no rows parsed.
            if not ev:
                txt = data[:800].decode("utf-8", errors="replace")
                return [Event(timestamp_utc=pd.Timestamp.now(tz="UTC"), source=source_name, title=f"Fetched timeline data from {source_name}", description=txt, ingestion_method="fetched_csv_raw")]
            return ev
        finally:
            try:
                tmp_path.unlink()
            except Exception:
                pass
    txt = data[:2000].decode("utf-8", errors="replace")
    if txt.strip():
        return [Event(timestamp_utc=pd.Timestamp.now(tz="UTC"), source=source_name, title=f"Fetched text from {source_name}", description=txt, ingestion_method="fetched_text")]
    return []


KEYWORDS = {
    "geopolitical_escalation": ["war", "missile", "attack", "strike", "conflict", "military", "invasion", "sanction", "sanctions", "escalation", "iran", "israel", "red sea", "russia", "ukraine", "taiwan", "nato", "drone", "houthi", "oil shock"],
    "deescalation": ["ceasefire", "truce", "peace", "deal", "talks", "negotiation", "de-escalation", "deescalation", "agreement", "withdrawal"],
    "macro_policy_hawkish": ["hawkish", "rate hike", "higher rates", "yields rise", "dollar strengthens", "strong dollar", "fed warns", "inflation sticky"],
    "macro_policy_dovish": ["dovish", "rate cut", "lower rates", "yields fall", "dollar weakens", "recession", "soft landing", "fed cuts"],
    "inflation_energy_shock": ["oil jumps", "oil surge", "energy shock", "tariff", "inflation shock", "supply disruption", "shipping disruption"],
}


def count_keywords(text: str, words: Sequence[str]) -> int:
    t = text.lower()
    score = 0
    for w in words:
        if " " in w:
            score += t.count(w)
        else:
            score += len(re.findall(r"\b" + re.escape(w) + r"\b", t))
    return score


def score_event(ev: Event) -> Dict[str, float]:
    txt = ev.text()
    base = max(0.0, ev.impact) * max(0.0, min(1.0, ev.confidence))
    # Manual hints can force score without keyword exact match.
    side = ev.side_hint.upper().strip()
    cat = ev.category_hint.lower().strip()
    scores = {k: float(count_keywords(txt, v)) for k, v in KEYWORDS.items()}
    for k in list(scores):
        if k in cat:
            scores[k] += 2.0
    if side == "LONG":
        scores["geopolitical_escalation"] += 1.0
    elif side == "SHORT":
        scores["deescalation"] += 1.0
    # Any relevant gold/XAU event with no category gets a small neutral shock.
    raw_sum = sum(scores.values())
    if raw_sum == 0 and any(w in txt for w in ["gold", "xau", "xauusd", "fed", "dollar", "yield", "geopolitical"]):
        scores["geopolitical_escalation"] += 0.25
    for k in list(scores):
        scores[k] = round(scores[k] * base, 6)
    long_pressure = scores["geopolitical_escalation"] + scores["macro_policy_dovish"] + scores["inflation_energy_shock"]
    short_pressure = scores["deescalation"] + scores["macro_policy_hawkish"]
    scores["gold_long_pressure"] = round(long_pressure, 6)
    scores["gold_short_pressure"] = round(short_pressure, 6)
    scores["net_gold_event_pressure"] = round(long_pressure - short_pressure, 6)
    scores["shock_abs"] = round(abs(long_pressure - short_pressure) + 0.5 * (long_pressure + short_pressure), 6)
    return scores


def build_hourly_panel(bars: pd.DataFrame, events: List[Event], holdout_pct: float) -> Tuple[pd.DataFrame, pd.DataFrame, Dict[str, Any]]:
    start = pd.to_datetime(bars["time_utc"].min(), utc=True).floor("1h")
    end = pd.to_datetime(bars["time_utc"].max(), utc=True).ceil("1h")
    hours = pd.date_range(start=start, end=end, freq="1h", tz="UTC")
    panel = pd.DataFrame({"time_bucket_utc": hours})
    for c in ["event_count", "gold_long_pressure", "gold_short_pressure", "shock_abs", "geopolitical_escalation_score", "deescalation_score", "macro_policy_hawkish_score", "macro_policy_dovish_score", "inflation_energy_shock_score", "net_gold_event_pressure"]:
        panel[c] = 0.0

    norm_rows = []
    if events:
        # Direct positional index from hour timestamp for speed.
        hour_to_idx = {pd.Timestamp(h): i for i, h in enumerate(panel["time_bucket_utc"])}
        for ev in events:
            ev_ts = pd.to_datetime(ev.timestamp_utc, utc=True).floor("1h")
            sc = score_event(ev)
            decay = max(1.0, float(ev.decay_hours))
            # cap propagation to keep runtime deterministic.
            max_h = int(min(max(decay * 2.0, 1.0), 168.0))
            for h in range(max_h + 1):
                bucket = ev_ts + pd.Timedelta(hours=h)
                idx = hour_to_idx.get(bucket)
                if idx is None:
                    continue
                w = math.exp(-h / decay)
                panel.at[idx, "event_count"] += w
                panel.at[idx, "gold_long_pressure"] += sc["gold_long_pressure"] * w
                panel.at[idx, "gold_short_pressure"] += sc["gold_short_pressure"] * w
                panel.at[idx, "shock_abs"] += sc["shock_abs"] * w
                panel.at[idx, "geopolitical_escalation_score"] += sc["geopolitical_escalation"] * w
                panel.at[idx, "deescalation_score"] += sc["deescalation"] * w
                panel.at[idx, "macro_policy_hawkish_score"] += sc["macro_policy_hawkish"] * w
                panel.at[idx, "macro_policy_dovish_score"] += sc["macro_policy_dovish"] * w
                panel.at[idx, "inflation_energy_shock_score"] += sc["inflation_energy_shock"] * w
                panel.at[idx, "net_gold_event_pressure"] += sc["net_gold_event_pressure"] * w
            norm_rows.append({
                "timestamp_utc": ev.timestamp_utc,
                "source": ev.source,
                "title": ev.title,
                "description": ev.description,
                "url": ev.url,
                "category_hint": ev.category_hint,
                "side_hint": ev.side_hint,
                "impact": ev.impact,
                "confidence": ev.confidence,
                "decay_hours": ev.decay_hours,
                "ingestion_method": ev.ingestion_method,
                **sc,
            })
    panel["event_shock_regime"] = "NO_EVENT_SHOCK"
    panel.loc[panel["net_gold_event_pressure"] > 0, "event_shock_regime"] = "GOLD_LONG_EVENT_PRESSURE"
    panel.loc[panel["net_gold_event_pressure"] < 0, "event_shock_regime"] = "GOLD_SHORT_EVENT_PRESSURE"
    norm = pd.DataFrame(norm_rows)

    # Health on bar-space using asof-like hourly floor.
    split_idx = int(len(bars) * (1.0 - holdout_pct))
    split_time = bars.iloc[max(0, min(len(bars) - 1, split_idx))]["time_utc"] if len(bars) else None
    active_hours = panel[panel["shock_abs"] > 0]["time_bucket_utc"]
    train_active_hours = active_hours[active_hours <= split_time] if split_time is not None else active_hours.iloc[0:0]
    holdout_active_hours = active_hours[active_hours > split_time] if split_time is not None else active_hours.iloc[0:0]
    recent_cut = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=14)
    recent_event_rows = int((norm["timestamp_utc"] >= recent_cut).sum()) if len(norm) and "timestamp_utc" in norm else 0
    health = {
        "panel_rows": int(len(panel)),
        "panel_nonzero_shock_rows": int((panel["shock_abs"] > 0).sum()),
        "normalized_event_rows": int(len(norm)),
        "recent_14d_event_rows": recent_event_rows,
        "bar_rows": int(len(bars)),
        "holdout_pct": holdout_pct,
        "split_time_utc": str(split_time) if split_time is not None else None,
        "train_active_event_hours": int(len(train_active_hours)),
        "holdout_active_event_hours": int(len(holdout_active_hours)),
        "event_overlay_trainable_historical": bool(len(train_active_hours) >= 500 and len(norm) >= 100),
        "current_event_operational_ready": bool(recent_event_rows >= 3 or int((panel["shock_abs"] > 0).tail(24*14).sum()) > 0),
    }
    return panel, norm, health


def load_url_specs(path: Optional[Path]) -> List[Dict[str, Any]]:
    if path and path.exists():
        obj = json.loads(path.read_text(encoding="utf-8"))
        return obj if isinstance(obj, list) else obj.get("urls", [])
    return DEFAULT_URLS


def ingest_local_raw_dir(path: Optional[Path]) -> Tuple[List[Event], List[str]]:
    if not path or not path.exists():
        return [], []
    events: List[Event] = []
    errors: List[str] = []
    for f in sorted(path.rglob("*")):
        if not f.is_file() or f.name.startswith("."):
            continue
        ext = f.suffix.lower()
        try:
            if ext in [".csv", ".tsv"]:
                ev, er = parse_csv_path(f, f.stem, ingestion_method="local_csv")
                events.extend(ev); errors.extend(er)
            elif ext in [".json"]:
                events.extend(parse_json_bytes(f.read_bytes(), f.stem))
            elif ext in [".xml", ".rss"]:
                events.extend(parse_rss_bytes(f.read_bytes(), f.stem))
            elif ext in [".txt", ".md", ".html"]:
                txt = f.read_text(encoding="utf-8", errors="replace")[:10000]
                if txt.strip():
                    events.append(Event(timestamp_utc=pd.Timestamp.fromtimestamp(f.stat().st_mtime, tz="UTC"), source=f.stem, title=f"Local raw text {f.name}", description=txt, ingestion_method="local_text"))
        except Exception as e:
            errors.append(f"{f}: {type(e).__name__}: {e}")
    return events, errors


def run(args: argparse.Namespace) -> Dict[str, Any]:
    root = Path(args.root).expanduser().resolve()
    report_dir = root / "reports" / "stage166e_event_data_failover_intake"
    ensure_dir(report_dir)
    raw_dir = report_dir / "raw_fetch_cache"
    ensure_dir(raw_dir)
    outputs = {
        "summary_json": str(report_dir / "stage166e_event_data_failover_summary.json"),
        "fetch_status_csv": str(report_dir / "stage166e_fetch_status.csv"),
        "normalized_events_csv": str(report_dir / "stage166e_normalized_external_events.csv"),
        "current_event_intraday_panel_csv": str(report_dir / "stage166e_current_event_intraday_panel.csv"),
        "event_panel_health_json": str(report_dir / "stage166e_event_panel_health.json"),
        "compatible_stage166_panel_csv": str(root / "reports" / "stage166_current_event_shock_overlay" / "stage166_current_event_intraday_panel.csv"),
    }
    bars, bars_meta = load_bars(Path(args.bars_m5).expanduser(), args.timestamp_shift_hours)

    events: List[Event] = []
    errors: List[str] = []
    fetch_rows: List[Dict[str, Any]] = []

    # Manual CSV first.
    manual_path = Path(args.manual_events_csv).expanduser() if args.manual_events_csv else Path(args.event_inbox).expanduser() / "manual_current_events.csv"
    if manual_path.exists():
        ev, er = parse_csv_path(manual_path, "manual_current_events", ingestion_method="manual_csv")
        events.extend(ev); errors.extend(er)

    # Local raw cache/browser downloads.
    local_raw_dir = Path(args.local_raw_dir).expanduser() if args.local_raw_dir else Path(args.event_inbox).expanduser() / "news_raw"
    ev, er = ingest_local_raw_dir(local_raw_dir)
    events.extend(ev); errors.extend(er)

    # Network fetch, strictly bounded.
    if args.fetch:
        specs = load_url_specs(Path(args.url_config).expanduser() if args.url_config else None)[:args.max_urls]
        transports = [x.strip() for x in args.transports.split(",") if x.strip()]
        with ThreadPoolExecutor(max_workers=max(1, args.max_workers)) as ex:
            futs = []
            for spec in specs:
                name, url, fmt = str(spec.get("name", "url")), str(spec.get("url", "")), str(spec.get("format", ""))
                for tr in transports:
                    if tr == "urllib":
                        futs.append((fmt, ex.submit(fetch_url_urllib, name, url, args.timeout_seconds, args.max_bytes)))
                    elif tr == "curl":
                        futs.append((fmt, ex.submit(fetch_url_curl, name, url, args.timeout_seconds, args.max_bytes)))
            for fmt, fut in futs:
                res = fut.result()
                data = res.pop("data", b"")
                if res.get("ok") and data:
                    suffix = "xml" if fmt == "rss" else fmt or "raw"
                    cache_path = raw_dir / f"{res['name']}_{res['transport']}.{suffix}"
                    try:
                        cache_path.write_bytes(data)
                        res["cache_path"] = str(cache_path)
                    except Exception as e:
                        res["cache_error"] = str(e)
                    res["data"] = data
                    events.extend(parse_fetched_result(res, fmt))
                    res.pop("data", None)
                fetch_rows.append(res)

    # Deduplicate events.
    dedup: Dict[Tuple[str, str, str], Event] = {}
    for ev in events:
        key = (str(ev.timestamp_utc.floor("min")), ev.source[:80], ev.title[:160])
        dedup[key] = ev
    events = list(dedup.values())

    panel, norm, health = build_hourly_panel(bars, events, args.holdout_pct)
    fetch_df = pd.DataFrame(fetch_rows)
    if fetch_df.empty:
        fetch_df = pd.DataFrame(columns=["name", "url", "ok", "transport", "status", "bytes", "error", "started_utc", "cache_path"])
    fetch_df.to_csv(outputs["fetch_status_csv"], index=False)
    norm.to_csv(outputs["normalized_events_csv"], index=False)
    panel.to_csv(outputs["current_event_intraday_panel_csv"], index=False)
    write_json(Path(outputs["event_panel_health_json"]), health)

    compatible_written = False
    compatible_backup = None
    if args.write_stage166_compatible_panel:
        comp = Path(outputs["compatible_stage166_panel_csv"])
        ensure_dir(comp.parent)
        if comp.exists() and args.backup_existing_compatible_panel:
            compatible_backup = str(comp.with_suffix(".pre_stage166e_backup.csv"))
            comp.replace(compatible_backup)
        panel.to_csv(comp, index=False)
        compatible_written = True

    fetch_ok = int(fetch_df["ok"].sum()) if "ok" in fetch_df.columns and len(fetch_df) else 0
    if health["event_overlay_trainable_historical"]:
        decision = "STAGE166E_EXTERNAL_EVENT_PANEL_HISTORICALLY_TRAINABLE_RERUN_STAGE167"
        severity = "INFO"
        action = "RERUN_STAGE167_WITH_EXTERNAL_EVENT_PANEL"
    elif health["current_event_operational_ready"]:
        decision = "STAGE166E_CURRENT_EVENT_PANEL_READY_NOT_HISTORICAL_TRAINABLE"
        severity = "WARN"
        action = "USE_AS_CURRENT_REGIME_GUARD_AND_COMBINE_WITH_STAGE166D_PROXY_FOR_DISCOVERY"
    else:
        decision = "STAGE166E_EXTERNAL_EVENT_INTAKE_FAILED_OR_EMPTY"
        severity = "HIGH"
        action = "USE_BROWSER_MANUAL_DOWNLOAD_OR_FILL_MANUAL_EVENTS_CSV"

    summary = {
        "stage": STAGE,
        "generated_utc": now_utc_iso(),
        "root": str(root),
        "order_routing_allowed": False,
        "demo_release_allowed": False,
        "status": "STAGE166E_COMPLETE_EVENT_DATA_FAILOVER_READY",
        "decision": decision,
        "severity": severity,
        "recommended_action": action,
        "bars_m5": str(Path(args.bars_m5).expanduser()),
        "event_inbox": str(Path(args.event_inbox).expanduser()),
        "manual_events_csv": str(manual_path),
        "local_raw_dir": str(local_raw_dir),
        "bars_meta": bars_meta,
        "fetch_meta": {
            "fetch_enabled": bool(args.fetch),
            "fetch_attempt_count": int(len(fetch_df)),
            "fetch_ok_count": fetch_ok,
            "transports": [x.strip() for x in args.transports.split(",") if x.strip()],
            "timeout_seconds": args.timeout_seconds,
            "max_workers": args.max_workers,
            "max_urls": args.max_urls,
        },
        "event_counts": {
            "normalized_events": int(len(norm)),
            "manual_events": int((norm["ingestion_method"] == "manual_csv").sum()) if len(norm) and "ingestion_method" in norm else 0,
            "local_raw_events": int(norm["ingestion_method"].astype(str).str.startswith("local_").sum()) if len(norm) and "ingestion_method" in norm else 0,
            "fetched_events": int(norm["ingestion_method"].astype(str).str.startswith("rss").sum() + norm["ingestion_method"].astype(str).str.startswith("json").sum() + norm["ingestion_method"].astype(str).str.startswith("fetched").sum()) if len(norm) and "ingestion_method" in norm else 0,
        },
        "event_panel_health": health,
        "errors": errors[:50],
        "write_stage166_compatible_panel": bool(args.write_stage166_compatible_panel),
        "compatible_stage166_panel_written": compatible_written,
        "compatible_stage166_panel_backup": compatible_backup,
        "outputs": outputs,
        "next": [
            "If decision is historically trainable, rerun Stage167.",
            "If current-event only, use it as a current regime guard and keep Stage166D for historical post-shock proxy discovery.",
            "If empty, put browser-downloaded RSS/CSV/JSON files into event_inbox/news_raw or fill event_inbox/manual_current_events.csv and rerun.",
        ],
    }
    write_json(Path(outputs["summary_json"]), summary)
    return summary


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Stage166E event data failover intake")
    p.add_argument("--root", required=True)
    p.add_argument("--bars-m5", required=True)
    p.add_argument("--event-inbox", required=True)
    p.add_argument("--manual-events-csv", default="")
    p.add_argument("--local-raw-dir", default="")
    p.add_argument("--url-config", default="")
    p.add_argument("--fetch", action="store_true")
    p.add_argument("--transports", default="urllib,curl")
    p.add_argument("--timeout-seconds", type=int, default=10)
    p.add_argument("--max-workers", type=int, default=3)
    p.add_argument("--max-urls", type=int, default=8)
    p.add_argument("--max-bytes", type=int, default=2_000_000)
    p.add_argument("--timestamp-shift-hours", type=float, default=-3.0)
    p.add_argument("--holdout-pct", type=float, default=0.20)
    p.add_argument("--write-stage166-compatible-panel", action="store_true")
    p.add_argument("--backup-existing-compatible-panel", action="store_true")
    return p


if __name__ == "__main__":
    summary = run(build_parser().parse_args())
    print(json.dumps(summary, indent=2, ensure_ascii=False, default=str))
