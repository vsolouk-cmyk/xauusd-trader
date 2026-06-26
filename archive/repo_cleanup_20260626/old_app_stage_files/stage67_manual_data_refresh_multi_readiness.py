#!/usr/bin/env python3
"""
Stage67 Manual Data Refresh + Multi-Readiness Runner

Local-only orchestrator. It does not download data from the internet.
It imports/copies user-refreshed CSV files from ~/Downloads, rebuilds the local
macro feature dataset when possible, then runs Stage66J2 only when fresh data
was imported or the operator explicitly forces readiness execution.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any, Dict, Iterable, List, Optional, Tuple

UTC = dt.timezone.utc


def utcnow_iso() -> str:
    return dt.datetime.now(UTC).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def sha256_file(path: Path) -> Optional[str]:
    if not path.exists() or not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def parse_date_any(value: Any) -> Optional[dt.date]:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    s = s.replace('\ufeff', '').strip()
    # epoch milliseconds / seconds fallback
    if s.isdigit() and len(s) >= 10:
        try:
            n = int(s)
            if len(s) > 10:
                n = n / 1000.0
            return dt.datetime.fromtimestamp(n, UTC).date()
        except Exception:
            pass
    s0 = s.replace('Z', '+00:00')
    for fmt in ('%Y-%m-%d', '%Y/%m/%d', '%d.%m.%Y', '%m/%d/%Y', '%d/%m/%Y'):
        try:
            return dt.datetime.strptime(s[:10], fmt).date()
        except Exception:
            pass
    try:
        return dt.datetime.fromisoformat(s0).date()
    except Exception:
        pass
    # split on whitespace/T separators
    for sep in (' ', 'T'):
        if sep in s:
            return parse_date_any(s.split(sep)[0])
    return None


def parse_dt_any(value: Any) -> Optional[dt.datetime]:
    if value is None:
        return None
    s = str(value).strip().replace('\ufeff', '')
    if not s:
        return None
    if s.isdigit() and len(s) >= 10:
        try:
            n = int(s)
            if len(s) > 10:
                n = n / 1000.0
            return dt.datetime.fromtimestamp(n, UTC)
        except Exception:
            pass
    s0 = s.replace('Z', '+00:00')
    try:
        x = dt.datetime.fromisoformat(s0)
        if x.tzinfo is None:
            x = x.replace(tzinfo=UTC)
        return x.astimezone(UTC)
    except Exception:
        pass
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y/%m/%d %H:%M:%S', '%Y-%m-%d', '%Y/%m/%d'):
        try:
            x = dt.datetime.strptime(s, fmt)
            return x.replace(tzinfo=UTC)
        except Exception:
            pass
    d = parse_date_any(s)
    if d:
        return dt.datetime(d.year, d.month, d.day, tzinfo=UTC)
    return None


def parse_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    s = str(value).strip().replace(',', '')
    if not s or s.lower() in {'nan', 'none', 'null', '-'}:
        return None
    try:
        v = float(s)
        if math.isfinite(v):
            return v
    except Exception:
        return None
    return None


def read_csv_dicts(path: Path) -> Tuple[List[Dict[str, str]], List[str]]:
    encodings = ('utf-8-sig', 'utf-8', 'cp1256', 'latin1')
    last_err = None
    for enc in encodings:
        try:
            with path.open('r', encoding=enc, newline='') as f:
                sample = f.read(4096)
                f.seek(0)
                try:
                    dialect = csv.Sniffer().sniff(sample, delimiters=',;\t|')
                except Exception:
                    dialect = csv.excel
                reader = csv.DictReader(f, dialect=dialect)
                rows = [{(k or '').strip().replace('\ufeff', ''): (v or '').strip() for k, v in r.items()} for r in reader]
                fieldnames = [(x or '').strip().replace('\ufeff', '') for x in (reader.fieldnames or [])]
                return rows, fieldnames
        except Exception as e:
            last_err = e
    raise RuntimeError(f'Could not read CSV {path}: {last_err}')


def write_csv_dicts(path: Path, rows: List[Dict[str, Any]], fieldnames: List[str]) -> None:
    ensure_dir(path.parent)
    with path.open('w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, '') for k in fieldnames})


def find_col(cols: Iterable[str], candidates: Iterable[str], contains: Optional[str] = None) -> Optional[str]:
    norm = {c.lower().strip(): c for c in cols}
    for cand in candidates:
        if cand.lower() in norm:
            return norm[cand.lower()]
    if contains:
        c = contains.lower()
        for key, orig in norm.items():
            if c in key:
                return orig
    return None


def latest_date_in_csv(path: Path, date_candidates: List[str]) -> Optional[dt.date]:
    if not path.exists():
        return None
    rows, cols = read_csv_dicts(path)
    dcol = find_col(cols, date_candidates, 'date') or find_col(cols, date_candidates, 'time')
    if not dcol:
        return None
    dates = [parse_date_any(r.get(dcol)) for r in rows]
    dates = [d for d in dates if d]
    return max(dates) if dates else None


def discover_download_file(download_dir: Path, names: List[str]) -> Optional[Path]:
    # Prefer exact candidates, then most recent case-insensitive partial match.
    for name in names:
        p = download_dir / name
        if p.exists() and p.is_file():
            return p
    lowered = [n.lower() for n in names]
    candidates: List[Path] = []
    if download_dir.exists():
        for p in download_dir.glob('*.csv'):
            lp = p.name.lower()
            if any(n.replace('.csv', '') in lp for n in lowered):
                candidates.append(p)
    if not candidates:
        return None
    candidates.sort(key=lambda x: x.stat().st_mtime, reverse=True)
    return candidates[0]


def read_ohlc_any(path: Path) -> List[Dict[str, Any]]:
    rows, cols = read_csv_dicts(path)
    time_col = find_col(cols, ['utc_time', 'time_utc', 'datetime', 'date_time', 'timestamp', 'time', 'date_utc', 'date'], 'time')
    date_col = find_col(cols, ['date_utc', 'date'], 'date')
    open_col = find_col(cols, ['open', 'o'])
    high_col = find_col(cols, ['high', 'h'])
    low_col = find_col(cols, ['low', 'l'])
    close_col = find_col(cols, ['close', 'c', 'last', 'price'])
    volume_col = find_col(cols, ['volume', 'vol', 'tick_volume'])
    if not (open_col and high_col and low_col and close_col):
        raise RuntimeError(f'OHLC columns not found in {path}; columns={cols}')
    out = []
    for r in rows:
        xdt = parse_dt_any(r.get(time_col)) if time_col else None
        if not xdt and date_col:
            d = parse_date_any(r.get(date_col))
            if d:
                xdt = dt.datetime(d.year, d.month, d.day, tzinfo=UTC)
        if not xdt:
            continue
        o = parse_float(r.get(open_col)); h = parse_float(r.get(high_col)); l = parse_float(r.get(low_col)); c = parse_float(r.get(close_col))
        if None in (o, h, l, c):
            continue
        out.append({
            'dt': xdt,
            'date': xdt.date(),
            'open': o, 'high': h, 'low': l, 'close': c,
            'volume': parse_float(r.get(volume_col)) if volume_col else None,
        })
    out.sort(key=lambda x: x['dt'])
    return out


def resample_ohlc_to_d1(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    by_date: Dict[dt.date, List[Dict[str, Any]]] = {}
    for r in rows:
        by_date.setdefault(r['date'], []).append(r)
    out = []
    for d in sorted(by_date):
        xs = sorted(by_date[d], key=lambda r: r['dt'])
        vol_values = [x['volume'] for x in xs if x.get('volume') is not None]
        out.append({
            'date_utc': d.isoformat(),
            'open': xs[0]['open'],
            'high': max(x['high'] for x in xs),
            'low': min(x['low'] for x in xs),
            'close': xs[-1]['close'],
            'volume': sum(vol_values) if vol_values else '',
            'source': 'stage67_manual_resample',
        })
    return out


def load_existing_d1(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    rows, cols = read_csv_dicts(path)
    dcol = find_col(cols, ['date_utc', 'date', 'time_utc', 'utc_time'], 'date')
    ocol = find_col(cols, ['open', 'o'])
    hcol = find_col(cols, ['high', 'h'])
    lcol = find_col(cols, ['low', 'l'])
    ccol = find_col(cols, ['close', 'c', 'last', 'price'])
    vcol = find_col(cols, ['volume', 'vol'])
    out = []
    if not (dcol and ocol and hcol and lcol and ccol):
        return []
    for r in rows:
        d = parse_date_any(r.get(dcol))
        o = parse_float(r.get(ocol)); h = parse_float(r.get(hcol)); l = parse_float(r.get(lcol)); c = parse_float(r.get(ccol))
        if not d or None in (o,h,l,c):
            continue
        out.append({'date_utc': d.isoformat(), 'open': o, 'high': h, 'low': l, 'close': c, 'volume': r.get(vcol,'') if vcol else '', 'source': r.get('source', 'existing')})
    out.sort(key=lambda r: r['date_utc'])
    return out


def merge_d1(existing: List[Dict[str, Any]], new_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    by_date: Dict[str, Dict[str, Any]] = {r['date_utc']: dict(r) for r in existing}
    for r in new_rows:
        by_date[r['date_utc']] = dict(r)
    return [by_date[k] for k in sorted(by_date)]


def sma(values: List[Optional[float]], idx: int, window: int) -> Optional[float]:
    if idx + 1 < window:
        return None
    xs = values[idx-window+1:idx+1]
    if any(v is None for v in xs):
        return None
    return sum(xs) / window  # type: ignore


def read_series(path: Path, preferred_value_cols: List[str], date_candidates: Optional[List[str]] = None) -> Dict[str, float]:
    if not path.exists():
        return {}
    rows, cols = read_csv_dicts(path)
    date_candidates = date_candidates or ['date_utc', 'feature_date_utc', 'date', 'time_utc', 'utc_time', 'datetime', 'timestamp']
    dcol = find_col(cols, date_candidates, 'date') or find_col(cols, date_candidates, 'time')
    vcol = find_col(cols, preferred_value_cols)
    if not vcol:
        # last numeric-like column fallback, excluding date/time columns
        for c in reversed(cols):
            if c == dcol or 'date' in c.lower() or 'time' in c.lower():
                continue
            if any(parse_float(r.get(c)) is not None for r in rows[:50]):
                vcol = c
                break
    if not dcol or not vcol:
        return {}
    out: Dict[str, float] = {}
    for r in rows:
        d = parse_date_any(r.get(dcol))
        v = parse_float(r.get(vcol))
        if d and v is not None:
            out[d.isoformat()] = v
    return out


def ffill_series_to_dates(series: Dict[str, float], dates: List[str], max_ffill_days: int = 21) -> Dict[str, Optional[float]]:
    out: Dict[str, Optional[float]] = {}
    sorted_items = [(dt.date.fromisoformat(k), v) for k, v in sorted(series.items())]
    j = -1
    last_d: Optional[dt.date] = None
    last_v: Optional[float] = None
    for ds in dates:
        d = dt.date.fromisoformat(ds)
        while j + 1 < len(sorted_items) and sorted_items[j+1][0] <= d:
            j += 1
            last_d, last_v = sorted_items[j]
        if last_d is not None and last_v is not None and (d - last_d).days <= max_ffill_days:
            out[ds] = last_v
        else:
            out[ds] = None
    return out


def pct_ratio(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if a is None or b is None or b == 0:
        return None
    return a / b - 1.0


def diff(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if a is None or b is None:
        return None
    return a - b


def fmt_num(x: Optional[float]) -> str:
    if x is None or not math.isfinite(x):
        return ''
    return repr(float(x))


def build_macro_dataset(root: Path, config: Dict[str, Any], external_d1_path: Path, macro_path: Path) -> Dict[str, Any]:
    existing_macro_latest_before = latest_date_in_csv(macro_path, ['feature_date_utc', 'date_utc', 'date'])
    existing_macro_hash_before = sha256_file(macro_path)
    d1 = load_existing_d1(external_d1_path)
    if not d1:
        return {'status': 'SKIP', 'reason': 'external_d1_missing_or_empty'}
    dates = [r['date_utc'] for r in d1]
    closes = [parse_float(r['close']) for r in d1]

    raw_cfg = config['paths']['raw_sources']
    raw_base = root
    dxy_path = raw_base / raw_cfg.get('dxy', 'data/exogenous/dxy.csv')
    ry_path = raw_base / raw_cfg.get('real_yield', 'data/exogenous/real_yield.csv')
    vix_path = raw_base / raw_cfg.get('vix', 'data/exogenous/vix.csv')
    etf_path = raw_base / raw_cfg.get('etf_flow', 'data/exogenous/etf_flow.csv')
    cb_path = raw_base / raw_cfg.get('central_bank_demand', 'data/exogenous/central_bank_demand.csv')

    series_info: Dict[str, Any] = {}
    dxy = ffill_series_to_dates(read_series(dxy_path, ['close','dxy','value','price']), dates, 10)
    ry = ffill_series_to_dates(read_series(ry_path, ['real_yield','value','close','yield']), dates, 10)
    vix = ffill_series_to_dates(read_series(vix_path, ['close','vix','value','price']), dates, 10)
    etf_direct = ffill_series_to_dates(read_series(etf_path, ['etf_flow_tonnes_3m','flow_tonnes_3m','tonnes_3m','value','flow_tonnes','tonnes']), dates, 45)
    cb_direct = ffill_series_to_dates(read_series(cb_path, ['central_bank_demand_tonnes_3m','demand_tonnes_3m','tonnes_3m','value','demand_tonnes','tonnes']), dates, 120)

    for name, path, ser in [('dxy', dxy_path, dxy), ('real_yield', ry_path, ry), ('vix', vix_path, vix), ('etf_flow', etf_path, etf_direct), ('central_bank_demand', cb_path, cb_direct)]:
        avail = sum(1 for v in ser.values() if v is not None)
        series_info[name] = {'path': str(path), 'exists': path.exists(), 'coverage_rows': avail, 'coverage_pct': round(100.0*avail/max(len(dates),1), 3)}

    dxy_vals = [dxy[d] for d in dates]
    ry_vals = [ry[d] for d in dates]
    vix_vals = [vix[d] for d in dates]
    etf_vals = [etf_direct[d] for d in dates]
    cb_vals = [cb_direct[d] for d in dates]

    rows: List[Dict[str, Any]] = []
    for i, ds in enumerate(dates):
        sma20 = sma(closes, i, 20); sma50 = sma(closes, i, 50); sma200 = sma(closes, i, 200)
        dxy_sma20 = sma(dxy_vals, i, 20); dxy_sma50 = sma(dxy_vals, i, 50)
        row = {
            'feature_date_utc': ds,
            'sample_available_after_utc': (dt.date.fromisoformat(ds) + dt.timedelta(days=1)).isoformat() + 'T00:00:00Z',
            'gold_close': fmt_num(closes[i]),
            'gold_sma20_over_50': fmt_num(pct_ratio(sma20, sma50)),
            'gold_sma50_over_200': fmt_num(pct_ratio(sma50, sma200)),
            'dxy_close': fmt_num(dxy_vals[i]),
            'dxy_ret_20d': fmt_num(pct_ratio(dxy_vals[i], dxy_vals[i-20] if i >= 20 else None)),
            'dxy_sma20_over_50': fmt_num(pct_ratio(dxy_sma20, dxy_sma50)),
            'real_yield': fmt_num(ry_vals[i]),
            'real_yield_change_20d': fmt_num(diff(ry_vals[i], ry_vals[i-20] if i >= 20 else None)),
            'vix': fmt_num(vix_vals[i]),
            'vix_change_20d': fmt_num(diff(vix_vals[i], vix_vals[i-20] if i >= 20 else None)),
            'etf_flow_tonnes_3m': fmt_num(etf_vals[i]),
            'central_bank_demand_tonnes_3m': fmt_num(cb_vals[i]),
        }
        # Keep only rows with enough gold history; exogenous may be blank but readiness gates will fail safely.
        if row['gold_sma20_over_50'] and row['gold_sma50_over_200']:
            rows.append(row)

    if not rows:
        return {'status': 'SKIP', 'reason': 'no_macro_rows_built', 'series_info': series_info}

    fieldnames = ['feature_date_utc','sample_available_after_utc','gold_close','gold_sma20_over_50','gold_sma50_over_200','dxy_close','dxy_ret_20d','dxy_sma20_over_50','real_yield','real_yield_change_20d','vix','vix_change_20d','etf_flow_tonnes_3m','central_bank_demand_tonnes_3m']
    write_csv_dicts(macro_path, rows, fieldnames)
    latest_after = parse_date_any(rows[-1]['feature_date_utc'])
    hash_after = sha256_file(macro_path)
    return {
        'status': 'PASS',
        'macro_path': str(macro_path),
        'rows': len(rows),
        'latest_before': existing_macro_latest_before.isoformat() if existing_macro_latest_before else None,
        'latest_after': latest_after.isoformat() if latest_after else None,
        'hash_before': existing_macro_hash_before,
        'hash_after': hash_after,
        'latest_advanced': bool(latest_after and (not existing_macro_latest_before or latest_after > existing_macro_latest_before)),
        'hash_changed': existing_macro_hash_before != hash_after,
        'series_info': series_info,
    }


def copy_manual_sources(root: Path, download_dir: Path, config: Dict[str, Any]) -> Dict[str, Any]:
    results: Dict[str, Any] = {}
    manual_sources = config.get('manual_sources', {})
    for key, spec in manual_sources.items():
        if key in {'gold_intraday', 'gold_d1'}:
            continue
        target = root / spec.get('target_path')
        names = spec.get('filenames', [])
        src = discover_download_file(download_dir, names)
        before_hash = sha256_file(target)
        if src:
            ensure_dir(target.parent)
            shutil.copy2(src, target)
            after_hash = sha256_file(target)
            results[key] = {'source': str(src), 'target': str(target), 'copied': True, 'hash_changed': before_hash != after_hash, 'target_sha256': after_hash}
        else:
            results[key] = {'source': None, 'target': str(target), 'copied': False, 'exists_existing': target.exists(), 'target_sha256': before_hash}
    return results


def import_gold_d1(root: Path, download_dir: Path, config: Dict[str, Any]) -> Dict[str, Any]:
    external_path = root / config['paths']['external_d1_path']
    ensure_dir(external_path.parent)
    before_latest = latest_date_in_csv(external_path, ['date_utc', 'date', 'time_utc', 'utc_time'])
    before_hash = sha256_file(external_path)

    gold_d1_spec = config.get('manual_sources', {}).get('gold_d1', {})
    gold_intraday_spec = config.get('manual_sources', {}).get('gold_intraday', {})
    d1_src = discover_download_file(download_dir, gold_d1_spec.get('filenames', [])) if gold_d1_spec else None
    intraday_src = discover_download_file(download_dir, gold_intraday_spec.get('filenames', [])) if gold_intraday_spec else None

    selected_source = None
    new_d1_rows: List[Dict[str, Any]] = []
    mode = None
    if d1_src:
        selected_source = d1_src
        mode = 'copy_or_merge_d1'
        new_d1_rows = load_existing_d1(d1_src)
    elif intraday_src:
        selected_source = intraday_src
        mode = 'resample_intraday_to_d1'
        new_d1_rows = resample_ohlc_to_d1(read_ohlc_any(intraday_src))
    else:
        return {
            'status': 'NO_INPUT',
            'message': 'No manual gold D1 or intraday CSV found in download directory.',
            'external_path': str(external_path),
            'latest_before': before_latest.isoformat() if before_latest else None,
        }
    existing = load_existing_d1(external_path)
    merged = merge_d1(existing, new_d1_rows)
    write_csv_dicts(external_path, merged, ['date_utc','open','high','low','close','volume','source'])
    after_latest = latest_date_in_csv(external_path, ['date_utc', 'date'])
    after_hash = sha256_file(external_path)
    return {
        'status': 'PASS',
        'mode': mode,
        'source': str(selected_source),
        'external_path': str(external_path),
        'new_source_rows': len(new_d1_rows),
        'merged_rows': len(merged),
        'latest_before': before_latest.isoformat() if before_latest else None,
        'latest_after': after_latest.isoformat() if after_latest else None,
        'hash_before': before_hash,
        'hash_after': after_hash,
        'latest_advanced': bool(after_latest and (not before_latest or after_latest > before_latest)),
        'hash_changed': before_hash != after_hash,
    }


def run_child_stage(root: Path, outdir: Path, config: Dict[str, Any], force: bool=False) -> Dict[str, Any]:
    stage_cfg = config['stage66j2_run']
    cmd = [
        sys.executable,
        str(root / stage_cfg['script_path']),
        '--root', str(root),
        '--config', str(root / stage_cfg['config_path']),
        '--out', str(root / stage_cfg['out_path']),
    ]
    if stage_cfg.get('no_run', False):
        cmd.append('--no-run')
    p = subprocess.run(cmd, cwd=str(root), text=True, capture_output=True)
    summary_path = root / stage_cfg['summary_path']
    summary = None
    if summary_path.exists():
        try:
            summary = json.loads(summary_path.read_text(encoding='utf-8'))
        except Exception:
            summary = None
    return {
        'attempted': True,
        'cmd': cmd,
        'returncode': p.returncode,
        'status': 'PASS' if p.returncode == 0 and summary_path.exists() else 'FAIL',
        'stdout_tail': p.stdout[-2000:],
        'stderr_tail': p.stderr[-2000:],
        'summary_path': str(summary_path.relative_to(root)) if summary_path.exists() else str(summary_path),
        'summary_found': summary_path.exists(),
        'summary_sha256': sha256_file(summary_path),
        'summary_decision': summary.get('decision') if isinstance(summary, dict) else None,
        'summary_classification': summary.get('classification') if isinstance(summary, dict) else None,
    }


def append_ledger(path: Path, row: Dict[str, Any]) -> None:
    ensure_dir(path.parent)
    exists = path.exists()
    fieldnames = list(row.keys())
    with path.open('a', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        if not exists:
            w.writeheader()
        w.writerow(row)


def write_report(path: Path, summary: Dict[str, Any]) -> None:
    ensure_dir(path.parent)
    lines = []
    lines.append('# Stage67 Manual Data Refresh + Multi-Readiness Runner')
    lines.append('')
    lines.append('## Decision')
    lines.append('')
    lines.append(f"- status: `{summary.get('status')}`")
    lines.append(f"- decision: `{summary.get('decision')}`")
    lines.append(f"- classification: `{summary.get('classification')}`")
    lines.append('')
    lines.append('## Data refresh')
    lines.append('')
    lines.append('```json')
    lines.append(json.dumps(summary.get('data_refresh', {}), ensure_ascii=False, indent=2, sort_keys=True))
    lines.append('```')
    lines.append('')
    lines.append('## Readiness runner')
    lines.append('')
    lines.append('```json')
    lines.append(json.dumps(summary.get('readiness_run', {}), ensure_ascii=False, indent=2, sort_keys=True))
    lines.append('```')
    lines.append('')
    lines.append('## Issues')
    lines.append('')
    issues = summary.get('issues') or []
    if not issues:
        lines.append('- none')
    else:
        for x in issues:
            lines.append(f'- `{x}`')
    lines.append('')
    lines.append('## Hard blocks')
    lines.append('')
    for b in summary.get('hard_blocks', []):
        lines.append(f'- `{b}`')
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', default='.')
    ap.add_argument('--config', default='configs/stage67_manual_data_refresh_multi_readiness.json')
    ap.add_argument('--out', default='reports/stage67_manual_data_refresh_multi_readiness')
    ap.add_argument('--download-dir', default=None)
    ap.add_argument('--force-readiness', action='store_true', help='Run Stage66J2 even when no new manual data was imported.')
    args = ap.parse_args()

    root = Path(args.root).expanduser().resolve()
    config_path = (root / args.config).resolve() if not Path(args.config).is_absolute() else Path(args.config).resolve()
    config = json.loads(config_path.read_text(encoding='utf-8'))
    outdir = (root / args.out).resolve() if not Path(args.out).is_absolute() else Path(args.out).resolve()
    ensure_dir(outdir)
    download_dir = Path(args.download_dir or config.get('manual_download_dir', '~/Downloads')).expanduser().resolve()

    issues: List[str] = []
    hard_blocks = [
        'NO_AUTOMATED_ORDER',
        'NO_PAPER_ORDER',
        'NO_BROKER_CONNECTION',
        'NO_EA_PROMOTION',
        'NO_PAPER_LIVE',
        'NO_LIVE',
        'NO_ORDER_AUTHORIZATION_FROM_STAGE67',
        'NO_INTERNET_DOWNLOAD_FROM_STAGE67',
        'NO_THRESHOLD_TUNING',
        'NO_PROMOTION_FROM_DATA_REFRESH_ONLY',
    ]

    data_refresh: Dict[str, Any] = {'download_dir': str(download_dir)}
    if not download_dir.exists():
        issues.append('DOWNLOAD_DIR_NOT_FOUND')

    try:
        gold_import = import_gold_d1(root, download_dir, config)
    except Exception as e:
        gold_import = {'status': 'FAIL', 'error': str(e)}
        issues.append('GOLD_IMPORT_FAILED')
    data_refresh['gold_import'] = gold_import

    try:
        copied_sources = copy_manual_sources(root, download_dir, config)
    except Exception as e:
        copied_sources = {'status': 'FAIL', 'error': str(e)}
        issues.append('MANUAL_SOURCE_COPY_FAILED')
    data_refresh['manual_sources'] = copied_sources

    external_d1_path = root / config['paths']['external_d1_path']
    macro_path = root / config['paths']['macro_dataset_path']
    try:
        macro_build = build_macro_dataset(root, config, external_d1_path, macro_path)
    except Exception as e:
        macro_build = {'status': 'FAIL', 'error': str(e)}
        issues.append('MACRO_BUILD_FAILED')
    data_refresh['macro_build'] = macro_build

    imported_new_data = bool(gold_import.get('latest_advanced') or macro_build.get('latest_advanced') or any(v.get('hash_changed') for v in copied_sources.values() if isinstance(v, dict)))
    macro_latest = macro_build.get('latest_after') or latest_date_in_csv(macro_path, ['feature_date_utc', 'date_utc', 'date'])
    if isinstance(macro_latest, dt.date):
        macro_latest_s = macro_latest.isoformat()
    else:
        macro_latest_s = macro_latest
    data_refresh['imported_new_data'] = imported_new_data
    data_refresh['macro_latest'] = macro_latest_s

    readiness_run: Dict[str, Any] = {'attempted': False, 'reason': None}
    should_run = imported_new_data or args.force_readiness or config.get('run_readiness_when_no_update', False)
    if should_run:
        readiness_run = run_child_stage(root, outdir, config)
        if readiness_run.get('status') != 'PASS':
            issues.append('STAGE66J2_RUN_FAILED')
    else:
        readiness_run = {'attempted': False, 'reason': 'NO_NEW_MANUAL_DATA_IMPORTED_USE_FORCE_READINESS_TO_REPLAY_EXISTING_SNAPSHOT'}

    if issues:
        decision = 'STAGE67_STOP_INPUT_OR_REFRESH_FAILURE_NO_ORDER'
        classification = 'S67_STOP'
        status = 'STAGE67_COMPLETE_WITH_ISSUES_NO_PROMOTION'
        exit_code = 2
    elif not imported_new_data and not readiness_run.get('attempted'):
        decision = 'STAGE67_NO_NEW_MANUAL_DATA_IMPORTED_NO_FORWARD_READINESS_RUN'
        classification = 'S67_DATA_UNCHANGED_WAIT_MANUAL_REFRESH'
        status = 'STAGE67_COMPLETE_NO_PROMOTION'
        exit_code = 0
    elif readiness_run.get('status') == 'PASS':
        child_decision = readiness_run.get('summary_decision') or 'UNKNOWN_CHILD_DECISION'
        decision = f'STAGE67_REFRESH_COMPLETE_{child_decision}'
        classification = 'S67_REFRESH_AND_READINESS_COMPLETE'
        status = 'STAGE67_COMPLETE_NO_PROMOTION'
        exit_code = 0
    else:
        decision = 'STAGE67_REFRESH_COMPLETE_READINESS_NOT_RUN_NO_ORDER'
        classification = 'S67_REFRESH_ONLY'
        status = 'STAGE67_COMPLETE_NO_PROMOTION'
        exit_code = 0

    summary = {
        'stage': 'Stage67_MANUAL_DATA_REFRESH_MULTI_READINESS',
        'status': status,
        'decision': decision,
        'classification': classification,
        'generated_utc': utcnow_iso(),
        'root': str(root),
        'config': str(config_path.relative_to(root) if str(config_path).startswith(str(root)) else config_path),
        'data_refresh': data_refresh,
        'readiness_run': readiness_run,
        'issues': issues,
        'hard_blocks': hard_blocks,
        'outputs': {
            'summary_json': str((outdir / 'stage67_manual_data_refresh_multi_readiness_summary.json').relative_to(root)),
            'report_md': str((outdir / 'stage67_manual_data_refresh_multi_readiness_report.md').relative_to(root)),
            'ledger_csv': config['paths']['stage67_ledger_path'],
        },
        'next_step': 'If refreshed and Stage66J2 says WAIT, continue manual data refresh cadence. If any dry-run ticket appears, review only; real paper order requires a later explicit authorization package.',
    }

    summary_path = outdir / 'stage67_manual_data_refresh_multi_readiness_summary.json'
    report_path = outdir / 'stage67_manual_data_refresh_multi_readiness_report.md'
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True) + '\n', encoding='utf-8')
    write_report(report_path, summary)
    append_ledger(root / config['paths']['stage67_ledger_path'], {
        'generated_utc': summary['generated_utc'],
        'decision': decision,
        'classification': classification,
        'imported_new_data': imported_new_data,
        'macro_latest': macro_latest_s or '',
        'stage66j2_decision': readiness_run.get('summary_decision') or '',
        'issues': ';'.join(issues),
    })

    print(json.dumps({
        'decision': decision,
        'classification': classification,
        'summary_json': str(summary_path),
        'report_md': str(report_path),
    }, indent=2, ensure_ascii=False))
    return exit_code


if __name__ == '__main__':
    raise SystemExit(main())
