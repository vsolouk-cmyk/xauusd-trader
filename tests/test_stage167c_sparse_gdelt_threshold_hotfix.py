import csv
import json
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path


def write_mt5_bars(path: Path, rows: int = 2400) -> None:
    start = datetime(2022, 1, 1, 0, 0, 0)
    with path.open('w', newline='') as f:
        w = csv.writer(f, delimiter='\t')
        w.writerow(['<DATE>', '<TIME>', '<OPEN>', '<HIGH>', '<LOW>', '<CLOSE>', '<TICKVOL>', '<VOL>', '<SPREAD>'])
        price = 1800.0
        for i in range(rows):
            t = start + timedelta(minutes=5*i)
            price += 0.03 if i % 5 else -0.04
            op = price
            hi = price + 0.8
            lo = price - 0.7
            cl = price + (0.10 if i % 4 else -0.08)
            w.writerow([t.strftime('%Y.%m.%d'), t.strftime('%H:%M:%S'), f'{op:.2f}', f'{hi:.2f}', f'{lo:.2f}', f'{cl:.2f}', 100, 0, 20])


def write_too_sparse_events(path: Path) -> None:
    with path.open('w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['time_bucket_utc','event_count','gold_long_pressure','gold_short_pressure','shock_abs','event_side_bias','event_shock_regime'])
        w.writerow(['2022-01-04T00:00:00Z',1,1.0,0.0,1.0,'LONG','GOLD_LONG_EVENT_PRESSURE'])


def write_valid_sparse_events(path: Path) -> None:
    with path.open('w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['time_bucket_utc','event_count','gold_long_pressure','gold_short_pressure','shock_abs','event_side_bias','event_shock_regime'])
        # Sparse hourly events: enough train coverage after asof tolerance, but still sparse enough
        # that all-bar event quantiles would be zero.
        for i in range(6):
            t = datetime(2022, 1, 3, 0, 0, 0) + timedelta(hours=18*i)
            w.writerow([t.strftime('%Y-%m-%dT%H:%M:%SZ'), 100+i, 80+i*10, 0.0, 120+i*20, 'LONG', 'GOLD_LONG_EVENT_PRESSURE'])


def run_stage(script: Path, root: Path, bars: Path, events: Path, *extra):
    result = subprocess.run([
        sys.executable, str(script),
        '--root', str(root),
        '--bars-m5', str(bars),
        '--event-panel', str(events),
        '--holdout-pct', '0.20',
        *extra,
    ], capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def test_too_sparse_event_panel_still_fast_stops(tmp_path: Path):
    root = tmp_path / 'repo'; root.mkdir()
    bars = tmp_path / 'bars.tsv'; events = tmp_path / 'events.csv'
    write_mt5_bars(bars)
    write_too_sparse_events(events)
    script = Path(__file__).resolve().parents[1] / 'app' / 'stage167_event_aware_medium_frequency_discovery_and_holdout_gate.py'
    summary = run_stage(script, root, bars, events)
    assert summary['decision'] == 'STAGE167C_EVENT_PANEL_NOT_TRAINABLE_FAST_STOP_REBUILD_STAGE166_HISTORY_FIRST'
    assert summary['event_panel_health']['fast_stop'] is True


def test_valid_sparse_event_panel_scans_with_positive_thresholds(tmp_path: Path):
    root = tmp_path / 'repo'; root.mkdir()
    bars = tmp_path / 'bars.tsv'; events = tmp_path / 'events.csv'
    write_mt5_bars(bars)
    write_valid_sparse_events(events)
    script = Path(__file__).resolve().parents[1] / 'app' / 'stage167_event_aware_medium_frequency_discovery_and_holdout_gate.py'
    summary = run_stage(script, root, bars, events, '--min-train-active-event-bars', '50', '--min-event-panel-rows', '5')
    assert summary['event_panel_health']['fast_stop'] is False
    assert summary['event_panel_health']['event_overlay_trainable'] is True
    assert summary['event_panel_health']['event_threshold_source'] == 'positive_train_distribution'
    assert summary['thresholds']['shock_q80'] > 0
    assert summary['evaluation_context']['score_count'] == 120
