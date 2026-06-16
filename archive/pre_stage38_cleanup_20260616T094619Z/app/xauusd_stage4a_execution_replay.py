from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd
import yaml

from app.xauusd_candidate_eval import finalize_df
from app.xauusd_sqlite_store import connect, read_interval


def load_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with path.open('r', encoding='utf-8') as f:
        return yaml.safe_load(f) or {}


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(path)


def read_db_interval(db_path: str, interval: str) -> pd.DataFrame:
    con = connect(db_path)
    try:
        df = read_interval(con, interval)
    finally:
        con.close()
    return finalize_df(df)


def basic_data_window(df: pd.DataFrame) -> Dict[str, Any]:
    if df.empty:
        return {'rows': 0, 'start_utc': None, 'end_utc': None}
    return {
        'rows': int(len(df)),
        'start_utc': df['time_utc'].min().isoformat(),
        'end_utc': df['time_utc'].max().isoformat(),
    }


def nonoverlap_filter(entries: list[Dict[str, Any]], cooldown_bars: int, horizon_bars: int) -> list[Dict[str, Any]]:
    accepted: list[Dict[str, Any]] = []
    next_allowed_idx = -1
    for signal in sorted(entries, key=lambda x: int(x['signal_idx'])):
        idx = int(signal['signal_idx'])
        if idx < next_allowed_idx:
            continue
        accepted.append(signal)
        next_allowed_idx = idx + int(horizon_bars) + int(cooldown_bars) + 1
    return accepted


def build_h1_signals(h1: pd.DataFrame, cfg: Dict[str, Any]) -> list[Dict[str, Any]]:
    candidate = cfg.get('candidate', {}) or {}
    sma_window = int(candidate.get('sma_window', 10))
    horizon_bars = int(candidate.get('horizon_bars', 12))
    min_distance = float(candidate.get('min_distance_usd', 10.0))
    cooldown_bars = int(candidate.get('cooldown_bars', 1))

    work = h1.copy()
    work['sma'] = work['close'].rolling(sma_window).mean()
    work['diff'] = work['close'] - work['sma']

    raw_signals: list[Dict[str, Any]] = []
    for i in range(sma_window, len(work) - horizon_bars - 1):
        sma = work.loc[i, 'sma']
        if pd.isna(sma):
            continue
        diff = float(work.loc[i, 'diff'])
        if abs(diff) < min_distance:
            continue

        direction = 1 if diff > 0 else -1
        signal_time = pd.to_datetime(work.loc[i, 'time_utc'], utc=True)
        next_h1_time = pd.to_datetime(work.loc[i + 1, 'time_utc'], utc=True)
        planned_exit_h1_time = pd.to_datetime(work.loc[i + 1 + horizon_bars, 'time_utc'], utc=True)

        raw_signals.append(
            {
                'signal_idx': int(i),
                'signal_time_utc': signal_time.isoformat(),
                'entry_target_time_utc': next_h1_time.isoformat(),
                'planned_exit_target_time_utc': planned_exit_h1_time.isoformat(),
                'direction': int(direction),
                'direction_label': 'long' if direction > 0 else 'short',
                'signal_close': float(work.loc[i, 'close']),
                'sma': float(sma),
                'diff': diff,
                'reason': f'close_sma_diff_{diff:.4f}',
            }
        )

    return nonoverlap_filter(raw_signals, cooldown_bars=cooldown_bars, horizon_bars=horizon_bars)


def first_m1_at_or_after(m1: pd.DataFrame, ts: pd.Timestamp) -> Optional[pd.Series]:
    rows = m1[m1['time_utc'] >= ts]
    if rows.empty:
        return None
    return rows.iloc[0]


def m1_window(m1: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    return m1[(m1['time_utc'] >= start) & (m1['time_utc'] <= end)].copy()


def replay_signal(signal: Dict[str, Any], m1: pd.DataFrame, cost_usd: float) -> Optional[Dict[str, Any]]:
    entry_target = pd.to_datetime(signal['entry_target_time_utc'], utc=True)
    exit_target = pd.to_datetime(signal['planned_exit_target_time_utc'], utc=True)

    entry_bar = first_m1_at_or_after(m1, entry_target)
    if entry_bar is None:
        return None

    entry_time = pd.to_datetime(entry_bar['time_utc'], utc=True)
    entry_price = float(entry_bar['open'])

    path = m1_window(m1, entry_time, exit_target)
    if path.empty:
        return None

    exit_bar = first_m1_at_or_after(m1, exit_target)
    if exit_bar is None:
        return None

    exit_time = pd.to_datetime(exit_bar['time_utc'], utc=True)
    exit_price = float(exit_bar['close'])
    direction = int(signal['direction'])

    raw = direction * (exit_price - entry_price)
    net = raw - float(cost_usd)

    if direction > 0:
        mfe = float(path['high'].max() - entry_price)
        mae = float(entry_price - path['low'].min())
    else:
        mfe = float(entry_price - path['low'].min())
        mae = float(path['high'].max() - entry_price)

    return {
        **signal,
        'entry_time_utc': entry_time.isoformat(),
        'exit_time_utc': exit_time.isoformat(),
        'entry_price': entry_price,
        'exit_price': exit_price,
        'raw_usd': float(raw),
        'cost_usd': float(cost_usd),
        'net_usd': float(net),
        'mfe_usd': mfe,
        'mae_usd': mae,
        'path_high': float(path['high'].max()),
        'path_low': float(path['low'].min()),
        'm1_bars_in_trade': int(len(path)),
    }


def profit_factor(values: np.ndarray) -> Optional[float]:
    if values.size == 0:
        return None
    wins = values[values > 0]
    losses = values[values <= 0]
    loss_abs = abs(float(losses.sum()))
    if loss_abs == 0:
        return None
    return float(wins.sum() / loss_abs)


def max_drawdown(values: np.ndarray) -> float:
    if values.size == 0:
        return 0.0
    equity = np.cumsum(values)
    peak = np.maximum.accumulate(equity)
    return float(np.min(equity - peak))


def metrics(values: np.ndarray) -> Dict[str, Any]:
    values = np.asarray(values, dtype=float)
    if values.size == 0:
        return {
            'trade_count': 0,
            'total_net_usd': 0.0,
            'avg_net_usd': 0.0,
            'median_net_usd': 0.0,
            'win_rate': 0.0,
            'profit_factor': None,
            'max_drawdown_usd': 0.0,
        }
    return {
        'trade_count': int(values.size),
        'total_net_usd': float(values.sum()),
        'avg_net_usd': float(values.mean()),
        'median_net_usd': float(np.median(values)),
        'win_rate': float((values > 0).mean()),
        'profit_factor': profit_factor(values),
        'best_net_usd': float(values.max()),
        'worst_net_usd': float(values.min()),
        'max_drawdown_usd': max_drawdown(values),
    }


def quantiles(series: pd.Series, qs: list[float]) -> Dict[str, float]:
    out: Dict[str, float] = {}
    if series.empty:
        return out
    for q in qs:
        out[f'q{int(float(q)*100)}'] = float(series.quantile(float(q)))
    return out


def direction_breakdown(trades: pd.DataFrame) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for direction, g in trades.groupby('direction_label', sort=True):
        out[str(direction)] = metrics(g['net_usd'].to_numpy(dtype=float))
    return out


def monthly_breakdown(trades: pd.DataFrame) -> Dict[str, Any]:
    work = trades.copy()
    work['entry_month_utc'] = pd.to_datetime(work['entry_time_utc'], utc=True).dt.to_period('M').astype(str)
    rows = []
    for month, g in work.groupby('entry_month_utc', sort=True):
        m = metrics(g['net_usd'].to_numpy(dtype=float))
        m['month'] = month
        rows.append(m)
    positive = [r for r in rows if float(r.get('total_net_usd', 0.0)) > 0]
    return {
        'month_count': int(len(rows)),
        'positive_month_count': int(len(positive)),
        'positive_month_ratio': float(len(positive) / max(len(rows), 1)),
        'months': rows,
    }


def fold_breakdown(trades: pd.DataFrame, folds: int = 5) -> Dict[str, Any]:
    work = trades.sort_values('entry_time_utc').reset_index(drop=True)
    n = len(work)
    rows = []
    for i in range(folds):
        start = int(i * n / folds)
        end = int((i + 1) * n / folds)
        m = metrics(work.iloc[start:end]['net_usd'].to_numpy(dtype=float))
        m['fold'] = i + 1
        rows.append(m)
    positive = [r for r in rows if float(r.get('total_net_usd', 0.0)) > 0]
    return {
        'fold_count': int(len(rows)),
        'positive_fold_count': int(len(positive)),
        'positive_fold_ratio': float(len(positive) / max(len(rows), 1)),
        'folds': rows,
    }


def mae_mfe_summary(trades: pd.DataFrame, qs: list[float]) -> Dict[str, Any]:
    if trades.empty:
        return {}
    return {
        'mae_usd': {
            'avg': float(trades['mae_usd'].mean()),
            'median': float(trades['mae_usd'].median()),
            **quantiles(trades['mae_usd'], qs),
        },
        'mfe_usd': {
            'avg': float(trades['mfe_usd'].mean()),
            'median': float(trades['mfe_usd'].median()),
            **quantiles(trades['mfe_usd'], qs),
        },
        'winner_mae_usd': {
            **quantiles(trades.loc[trades['net_usd'] > 0, 'mae_usd'], qs),
        },
        'loser_mfe_usd': {
            **quantiles(trades.loc[trades['net_usd'] <= 0, 'mfe_usd'], qs),
        },
    }


def write_markdown(path: Path, payload: Dict[str, Any]) -> None:
    lines = []
    lines.append('# XAUUSD Stage 4A MT5 M1/H1 Execution Replay')
    lines.append('')
    lines.append(f"- Generated at UTC: `{payload['generated_at_utc']}`")
    lines.append(f"- Decision: `{payload['decision']['status']}`")
    lines.append(f"- Reason: `{payload['decision']['reason']}`")
    lines.append('')
    lines.append('## Data windows')
    lines.append('')
    lines.append(f"- H1: `{payload['data_windows']['h1']}`")
    lines.append(f"- M1: `{payload['data_windows']['m1']}`")
    lines.append('')
    lines.append('## Summary')
    lines.append('')
    base = payload['base']
    pf = base.get('profit_factor')
    lines.append(f"- trades: `{base.get('trade_count')}`")
    lines.append(f"- total net USD: `{base.get('total_net_usd')}`")
    lines.append(f"- profit factor: `{'n/a' if pf is None else round(float(pf), 4)}`")
    lines.append(f"- win rate: `{base.get('win_rate')}`")
    lines.append(f"- max DD USD: `{base.get('max_drawdown_usd')}`")
    lines.append('')
    lines.append('## MAE/MFE')
    lines.append('')
    lines.append('```json')
    lines.append(json.dumps(payload['mae_mfe'], indent=2))
    lines.append('```')
    lines.append('')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def main() -> int:
    parser = argparse.ArgumentParser(description='Stage 4A MT5 M1/H1 execution-realistic replay for fixed XAUUSD candidate.')
    parser.add_argument('--config', default='configs/stage4a.yaml')
    parser.add_argument('--mt5-db', default=None)
    parser.add_argument('--report-dir', default=None)
    args = parser.parse_args()

    cfg = load_yaml(Path(args.config))
    candidate = cfg.get('candidate', {}) or {}
    data_cfg = cfg.get('data', {}) or {}
    cost_cfg = cfg.get('cost_model', {}) or {}
    diag_cfg = cfg.get('diagnostics', {}) or {}

    mt5_db = args.mt5_db or data_cfg.get('mt5_db_path', 'data/second_source/second_source.sqlite')
    signal_interval = str(candidate.get('signal_interval', '1h'))
    path_interval = str(candidate.get('path_interval', '1min'))
    report_dir = Path(args.report_dir or cfg.get('report_dir', 'data/reports'))
    report_dir.mkdir(parents=True, exist_ok=True)

    cost_usd = float(cost_cfg.get('total_roundtrip_cost_usd', 0.35))

    h1 = read_db_interval(mt5_db, signal_interval)
    m1 = read_db_interval(mt5_db, path_interval)

    signals = build_h1_signals(h1, cfg)
    trades = []
    skipped = 0

    for signal in signals:
        trade = replay_signal(signal, m1, cost_usd=cost_usd)
        if trade is None:
            skipped += 1
            continue
        trades.append(trade)

    trades_df = pd.DataFrame(trades)
    if not trades_df.empty:
        trades_df = trades_df.sort_values('entry_time_utc').reset_index(drop=True)

    qs = [float(x) for x in diag_cfg.get('mae_mfe_quantiles', [0.1, 0.25, 0.5, 0.75, 0.9])]
    base = metrics(trades_df['net_usd'].to_numpy(dtype=float) if not trades_df.empty else np.array([], dtype=float))

    min_trades = int(diag_cfg.get('min_trades', 100))
    status = 'stage4a_execution_replay_ready' if int(base['trade_count']) >= min_trades else 'stage4a_insufficient_trades'
    reason = (
        'MT5 H1/M1 replay completed with enough trades for diagnostics.'
        if status == 'stage4a_execution_replay_ready'
        else 'MT5 H1/M1 replay completed, but trade count is below diagnostic threshold.'
    )

    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    summary_json = report_dir / f'stage4a_execution_replay_summary_{stamp}.json'
    summary_md = report_dir / f'stage4a_execution_replay_summary_{stamp}.md'
    trades_csv = report_dir / f'stage4a_execution_replay_trades_{stamp}.csv'

    if bool(diag_cfg.get('save_trades_csv', True)):
        trades_df.to_csv(trades_csv, index=False)

    payload = {
        'ok': True,
        'stage': 'stage4a_mt5_m1_h1_execution_replay',
        'generated_at_utc': datetime.now(timezone.utc).isoformat(),
        'candidate': {
            'family': candidate.get('family'),
            'variant': candidate.get('variant'),
            'signal_interval': signal_interval,
            'path_interval': path_interval,
        },
        'mt5_db_path': mt5_db,
        'data_windows': {
            'h1': basic_data_window(h1),
            'm1': basic_data_window(m1),
        },
        'signal_count': int(len(signals)),
        'replayed_trade_count': int(len(trades_df)),
        'skipped_signal_count': int(skipped),
        'base': base,
        'direction': direction_breakdown(trades_df) if not trades_df.empty else {},
        'monthly': monthly_breakdown(trades_df) if not trades_df.empty else {},
        'folds': fold_breakdown(trades_df) if not trades_df.empty else {},
        'mae_mfe': mae_mfe_summary(trades_df, qs=qs) if not trades_df.empty else {},
        'trades_csv': str(trades_csv) if bool(diag_cfg.get('save_trades_csv', True)) else None,
        'decision': {
            'status': status,
            'reason': reason,
        },
        'warning': 'Diagnostic only. No TP/SL finalization, no paper-order, no live trading.',
    }

    write_json(summary_json, payload)
    write_markdown(summary_md, payload)

    print(json.dumps({
        'ok': True,
        'decision': payload['decision'],
        'summary_json': str(summary_json),
        'summary_md': str(summary_md),
        'trades_csv': payload['trades_csv'],
        'h1_rows': int(len(h1)),
        'm1_rows': int(len(m1)),
        'signals': len(signals),
        'replayed_trades': len(trades_df),
        'skipped': skipped,
    }, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
