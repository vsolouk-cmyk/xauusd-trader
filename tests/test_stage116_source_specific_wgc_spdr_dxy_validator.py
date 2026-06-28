from pathlib import Path
import csv
import json

from app.stage116_source_specific_wgc_spdr_dxy_validator import parse_direct_dxy, run


def write_csv(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)


def test_parse_valid_direct_dxy(tmp_path):
    p = tmp_path / 'stooq_dx_f_dxy_daily.csv'
    rows = [{'Date': f'2024-01-{(i%28)+1:02d}', 'Close': 100+i} for i in range(60)]
    # make unique dates
    rows = [{'Date': f'2024-03-{i+1:02d}', 'Close': 100+i} for i in range(28)] + [{'Date': f'2024-04-{i+1:02d}', 'Close': 120+i} for i in range(28)]
    write_csv(p, rows)
    res = parse_direct_dxy(p)
    assert res.valid
    assert res.valid_close_rows >= 50


def test_parse_html_invalid(tmp_path):
    p = tmp_path / 'dxy.csv'
    p.write_text('<html>Forbidden</html>', encoding='utf-8')
    res = parse_direct_dxy(p)
    assert not res.valid
    assert res.source_mode == 'HTML_OR_BLOCKED'


def test_run_fallback_to_dtwexbgs(tmp_path):
    root = tmp_path / 'repo'
    inbox = tmp_path / 'inbox'
    dxy_dir = inbox / 'macro_misc' / 'dxy'
    dxy_dir.mkdir(parents=True)
    write_csv(dxy_dir / 'stooq_dx_f_dxy_daily.csv', [{'Date':'2024-01-01','Close':'100'}])
    fred = root / 'data' / 'fundamental_event_inbox' / 'features' / 'stage115_fred_macro_daily_wide.csv'
    rows = [{'date': f'2024-01-{(i%28)+1:02d}', 'DTWEXBGS': 100+i} for i in range(60)]
    # unique dates over months
    rows = [{'date': f'2024-01-{i+1:02d}', 'DTWEXBGS': 100+i} for i in range(28)] + [{'date': f'2024-02-{i+1:02d}', 'DTWEXBGS': 130+i} for i in range(28)]
    write_csv(fred, rows)
    summary = run(root, inbox)
    assert summary['dxy_fallback_active'] is True
    assert summary['validated_dollar_pressure_rows'] >= 50
    assert (root / 'data' / 'fundamental_event_inbox' / 'features' / 'stage116_validated_dollar_pressure.csv').exists()
