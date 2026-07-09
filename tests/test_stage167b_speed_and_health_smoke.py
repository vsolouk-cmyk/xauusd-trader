import csv
import json
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path


def write_mt5_bars(path: Path, rows: int = 1200) -> None:
    start = datetime(2022, 1, 1, 0, 0, 0)
    with path.open('w', newline='') as f:
        w = csv.writer(f, delimiter='\t')
        w.writerow(['<DATE>', '<TIME>', '<OPEN>', '<HIGH>', '<LOW>', '<CLOSE>', '<TICKVOL>', '<VOL>', '<SPREAD>'])
        price = 1800.0
        for i in range(rows):
            t = start + timedelta(minutes=5*i)
            price += 0.05 if i % 7 else -0.08
            op = price
            hi = price + 0.6
            lo = price - 0.6
            cl = price + (0.12 if i % 3 else -0.09)
            w.writerow([t.strftime('%Y.%m.%d'), t.strftime('%H:%M:%S'), f'{op:.2f}', f'{hi:.2f}', f'{lo:.2f}', f'{cl:.2f}', 100, 0, 20])


def write_sparse_events(path: Path) -> None:
    with path.open('w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['time_bucket_utc','event_count','gold_long_pressure','gold_short_pressure','shock_abs','event_side_bias','event_shock_regime'])
        w.writerow(['2022-01-04T00:00:00Z',1,1.0,0.0,1.0,'LONG','GEOPOLITICAL_ESCALATION'])
        w.writerow(['2022-01-04T12:00:00Z',1,0.0,1.0,1.0,'SHORT','DEESCALATION'])


def test_fast_stop_sparse_event_panel(tmp_path: Path):
    root = tmp_path / 'repo'
    root.mkdir()
    bars = tmp_path / 'bars.tsv'
    events = tmp_path / 'events.csv'
    write_mt5_bars(bars)
    write_sparse_events(events)
    script = Path(__file__).resolve().parents[1] / 'app' / 'stage167_event_aware_medium_frequency_discovery_and_holdout_gate.py'
    result = subprocess.run([
        sys.executable, str(script),
        '--root', str(root),
        '--bars-m5', str(bars),
        '--event-panel', str(events),
        '--holdout-pct', '0.20'
    ], capture_output=True, text=True, check=True)
    summary = json.loads(result.stdout)
    assert summary['status'] == 'STAGE167_COMPLETE_EVENT_AWARE_HOLDOUT_GATE_READY'
    assert summary['decision'] == 'STAGE167B_EVENT_PANEL_NOT_TRAINABLE_FAST_STOP_REBUILD_STAGE166_HISTORY_FIRST'
    assert summary['event_panel_health']['fast_stop'] is True
    assert Path(summary['outputs']['summary_json']).exists()
