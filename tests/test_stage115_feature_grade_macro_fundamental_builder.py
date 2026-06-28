import csv
import json
import zipfile
from pathlib import Path

from app.stage115_feature_grade_macro_fundamental_builder import run


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    keys = []
    for r in rows:
        for k in r:
            if k not in keys:
                keys.append(k)
    with path.open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def test_stage115_builds_macro_panel_with_dxy_fallback(tmp_path: Path):
    root = tmp_path
    norm = root / 'data/fundamental_event_inbox/normalized'
    report114b = root / 'reports/stage114b_classification_and_macro_event_hotfix'
    norm.mkdir(parents=True)
    report114b.mkdir(parents=True)

    fred_rows = []
    for i in range(80):
        day = f"2024-01-{(i % 28) + 1:02d}" if i < 28 else f"2024-02-{((i-28) % 28) + 1:02d}" if i < 56 else f"2024-03-{((i-56) % 24) + 1:02d}"
        # de-duplicate date values still okay; enough rows not needed for test.
        fred_rows.append({'date': day, 'series_id': 'DTWEXBGS', 'value': str(100 + i)})
        fred_rows.append({'date': day, 'series_id': 'DFII10', 'value': str(1.0 + i/100)})
        fred_rows.append({'date': day, 'series_id': 'DGS10', 'value': str(4.0 + i/100)})
        fred_rows.append({'date': day, 'series_id': 'DGS2', 'value': str(3.5 + i/100)})
    write_csv(norm / 'fred_macro_normalized.csv', fred_rows)
    write_csv(norm / 'dxy_reference_normalized.csv', [{'date': '2024-01-01', 'close': '101'}, {'date': '2024-01-02', 'close': '102'}])
    for name in ['fred_release_calendar_normalized.csv','fomc_calendar_extracted.csv','treasury_auctions_normalized.csv','bls_macro_normalized.csv','bea_macro_shell_normalized.csv','census_macro_shell_normalized.csv','wgc_gold_etf_xlsx_rows.csv','wgc_central_bank_gold_xlsx_rows.csv','spdr_gld_xlsx_rows.csv']:
        write_csv(norm / name, [])
    write_csv(report114b / 'stage114b_corrected_file_classification.csv', [])

    summary = run(root)
    assert summary['dxy_fallback_active'] is True
    panel = root / 'data/fundamental_event_inbox/features/stage115_daily_macro_feature_panel.csv'
    rows = list(csv.DictReader(panel.open()))
    assert rows
    assert 'dollar_pressure_index' in rows[0]
    assert any(r['dollar_pressure_source'] == 'FRED_DTWEXBGS_FALLBACK' for r in rows)


def test_stage115_parses_cot_gold_zip(tmp_path: Path):
    root = tmp_path
    norm = root / 'data/fundamental_event_inbox/normalized'
    report114b = root / 'reports/stage114b_classification_and_macro_event_hotfix'
    cotdir = root / 'cot/cftc'
    norm.mkdir(parents=True)
    report114b.mkdir(parents=True)
    cotdir.mkdir(parents=True)
    for name in ['fred_macro_normalized.csv','dxy_reference_normalized.csv','fred_release_calendar_normalized.csv','fomc_calendar_extracted.csv','treasury_auctions_normalized.csv','bls_macro_normalized.csv','bea_macro_shell_normalized.csv','census_macro_shell_normalized.csv','wgc_gold_etf_xlsx_rows.csv','wgc_central_bank_gold_xlsx_rows.csv','spdr_gld_xlsx_rows.csv']:
        write_csv(norm / name, [])

    zpath = cotdir / 'fut_disagg_txt_2024.zip'
    member_text = "Market_and_Exchange_Names,Report_Date_as_YYYY-MM-DD,Open_Interest_All,M_Money_Positions_Long_All,M_Money_Positions_Short_All,Prod_Merc_Positions_Long_All,Prod_Merc_Positions_Short_All\n"
    member_text += "GOLD - COMMODITY EXCHANGE INC.,2024-01-02,1000,300,100,200,400\n"
    member_text += "SILVER - COMMODITY EXCHANGE INC.,2024-01-02,1000,300,100,200,400\n"
    with zipfile.ZipFile(zpath, 'w') as zf:
        zf.writestr('annual.txt', member_text)
    write_csv(report114b / 'stage114b_corrected_file_classification.csv', [{
        'path': str(zpath), 'filename': zpath.name, 'logical_filename': zpath.name,
        'source_family': 'cot_cftc', 'parser_hint': 'cot_zip'
    }])

    summary = run(root)
    assert summary['cot_gold_weekly_feature_rows'] == 1
    cot = list(csv.DictReader((root / 'data/fundamental_event_inbox/features/stage115_cot_gold_weekly_features.csv').open()))
    assert cot[0]['market_name'].startswith('GOLD')
    assert float(cot[0]['mm_net_all']) == 200.0


def test_stage115_reads_shell_csv_with_large_payload_field(tmp_path: Path):
    from app.stage115_feature_grade_macro_fundamental_builder import read_csv_dicts, CSV_FIELD_SIZE_LIMIT

    p = tmp_path / 'large_shell.csv'
    large_payload = '{"payload":"' + ('x' * 200000) + '"}'
    write_csv(p, [{'source_family': 'bea', 'payload': large_payload}])

    rows = read_csv_dicts(p)
    assert CSV_FIELD_SIZE_LIMIT > 131072
    assert rows[0]['payload'] == large_payload
