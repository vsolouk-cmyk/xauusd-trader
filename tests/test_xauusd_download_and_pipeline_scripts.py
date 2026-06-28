import json
from pathlib import Path

from scripts.download_xauusd_official_data_batch import main as download_main, scrub, content_issue, load_env_file, env_present


def test_dry_run_download_prints_progress_and_masks_secret(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv('FRED_API_KEY', 'SECRET_FRED_KEY')
    rc = download_main(['--inbox', str(tmp_path / 'inbox'), '--dry-run', '--from-year', '2026', '--to-year', '2026', '--skip-wgc-direct'])
    assert rc == 0
    captured = capsys.readouterr().out
    assert '[01/' in captured
    assert 'START' in captured
    assert 'DONE' in captured
    assert 'SECRET_FRED_KEY' not in captured
    assert 'Official economic-events backbone' in captured
    log_text = ''.join((tmp_path / 'inbox' / '_logs').glob('download_xauusd_official_data_batch_*.jsonl').__iter__().__next__().read_text().splitlines())
    assert 'SECRET_FRED_KEY' not in log_text
    assert '${FRED_API_KEY}' in log_text


def test_scrub_masks_keys(monkeypatch):
    monkeypatch.setenv('BEA_API_KEY', 'SECRET_BEA')
    assert 'SECRET_BEA' not in scrub('https://x?UserID=SECRET_BEA')


def test_content_issue_flags_html_for_xlsx(tmp_path):
    p = tmp_path / 'blocked.xlsx'
    p.write_text('<html>forbidden</html>', encoding='utf-8')
    assert content_issue(p) == 'HTML_OR_BLOCKED'


def test_env_file_loads_census_key_without_leaking_value(tmp_path, monkeypatch, capsys):
    secret = 'SECRET_CENSUS_VALUE'
    env_file = tmp_path / '.xauusd_official_data.env'
    env_file.write_text(f'CENSUS_API_KEY={secret}\n', encoding='utf-8')
    monkeypatch.delenv('CENSUS_API_KEY', raising=False)
    loaded = load_env_file(env_file)
    assert loaded == ['CENSUS_API_KEY']
    assert env_present('CENSUS_API_KEY')
    assert secret not in scrub(f'https://api.census.gov/x?key={secret}')
    rc = download_main(['--inbox', str(tmp_path / 'inbox'), '--dry-run', '--from-year', '2026', '--to-year', '2026', '--env-file', str(env_file), '--skip-wgc-direct', '--quiet'])
    assert rc == 0
    logs = list((tmp_path / 'inbox' / '_logs').glob('download_xauusd_official_data_batch_*.jsonl'))
    assert logs
    text = logs[0].read_text(encoding='utf-8')
    assert secret not in text
    assert '${CENSUS_API_KEY}' in text
