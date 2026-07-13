import importlib.util
from pathlib import Path
import pandas as pd

MODULE = Path(__file__).resolve().parents[1] / 'app' / 'stage171h_h64l_forward_feature_materializer.py'
spec = importlib.util.spec_from_file_location('stage171h2', MODULE)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def write_series(path: Path, end: str, periods: int, name: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    dates = pd.date_range(end=end, periods=periods, freq='D', tz='UTC')
    pd.DataFrame({'date_utc': dates.strftime('%Y-%m-%d'), name: range(100, 100+periods)}).to_csv(path, index=False)


def test_backup_is_excluded_and_fresh_active_selected(tmp_path):
    root = tmp_path / 'repo'; inbox = tmp_path / 'inbox'
    write_series(root/'data/exogenous/_repair_backups/dxy_old.csv', '2026-06-26', 100, 'value')
    write_series(root/'data/exogenous/dxy.csv', '2026-07-09', 30, 'value')
    files = mod.candidate_files(root, inbox, 'dxy')
    assert all('_repair_backups' not in str(p) for p in files)
    s, meta = mod.choose_series(root, inbox, 'dxy', pd.Timestamp('2026-07-09', tz='UTC'))
    assert meta['path'].endswith('data/exogenous/dxy.csv')
    assert meta['latest_date_utc'] == '2026-07-09'


def test_latest_date_beats_longer_stale_series(tmp_path):
    root = tmp_path / 'repo'; inbox = tmp_path / 'inbox'
    write_series(root/'data/macro_regime/raw/dxy_daily_2011_present.csv', '2026-06-20', 200, 'value')
    write_series(root/'data/exogenous/dxy.csv', '2026-07-09', 30, 'value')
    _, meta = mod.choose_series(root, inbox, 'dxy', pd.Timestamp('2026-07-09', tz='UTC'))
    assert meta['latest_date_utc'] == '2026-07-09'
    assert meta['selection_policy'].startswith('LATEST_DATE')


def test_attempt_ledger_written_when_blocked(tmp_path):
    out = tmp_path/'attempts.csv'
    mod.append_attempt(out, '2026-07-13T00:00:00Z', False, ['DXY_STALE_14D'], {'feature_date_utc':'2026-07-10'})
    text = out.read_text()
    assert 'DXY_STALE_14D' in text
    assert '2026-07-10' in text
