#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import subprocess
import sys
import tempfile
from pathlib import Path


def write_dummy_stage(path: Path, csv_writer: bool = False) -> None:
    if csv_writer:
        body = r'''
import argparse, csv
from pathlib import Path
p=argparse.ArgumentParser(); p.add_argument('--root'); p.add_argument('--config'); p.add_argument('--out'); args=p.parse_args()
root=Path(args.root); out=Path(args.out); out.mkdir(parents=True, exist_ok=True)
csv_path=root/'data/mt5_bridge/unified_observer_signal.csv'; csv_path.parent.mkdir(parents=True, exist_ok=True)
rows=[
 ['key','value'],
 ['schema_version','stage99_unified_observer_cot_v1'],
 ['stage','Stage99_UNIFIED_OBSERVER_COT_EXPANSION'],
 ['feature_date','2026-06-26'],
 ['latest_feature_date_utc','2026-06-26'],
 ['rule_count','6'],
 ['mode','OBSERVER_ONLY_NO_TRADE'],
 ['ea_mode','OBSERVER_ONLY_NO_TRADE'],
 ['any_signal_active','false'],
 ['selected_rule_id',''],
 ['order_authorized','false'],
 ['broker_connection_allowed','false'],
 ['K06_primary_active','false'],
 ['K06_signal_active','false'],
 ['K03_signal_active','false'],
 ['K07_signal_active','false'],
 ['S83_14_signal_active','false'],
 ['S83_13_signal_active','false'],
 ['C96_07_active','false'],
 ['C96_07_failures','cot_mm_net_z:1.2<1.0'],
]
with csv_path.open('w', newline='', encoding='utf-8') as f: csv.writer(f).writerows(rows)
print('{"status":"PASS"}')
'''
    else:
        body = r'''
import argparse
from pathlib import Path
p=argparse.ArgumentParser(); p.add_argument('--root'); p.add_argument('--config'); p.add_argument('--out'); p.add_argument('--run-readiness', action='store_true'); p.add_argument('--run-frequency', action='store_true'); p.add_argument('--timeout-seconds', default='180'); p.add_argument('--no-download', action='store_true')
args=p.parse_args(); Path(args.out).mkdir(parents=True, exist_ok=True); print('{"status":"PASS"}')
'''
    path.write_text(body, encoding='utf-8')


def main() -> None:
    repo_pkg = Path(__file__).resolve().parents[1]
    combo_script = repo_pkg / 'app/stage100_daily_unified_cot_observer_combo.py'
    assert combo_script.exists()
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / 'repo'
        root.mkdir()
        (root/'app').mkdir()
        (root/'configs').mkdir()
        mt5_dir = Path(td) / 'mt5 files'
        write_dummy_stage(root/'app/stage67d6_download_format_aware_rebuild_macro.py')
        write_dummy_stage(root/'app/stage67e_central_bank_changes_mapper.py')
        write_dummy_stage(root/'app/stage95_cot_official_dataset_builder.py')
        write_dummy_stage(root/'app/stage99_unified_observer_cot_expansion.py', csv_writer=True)
        for name in ['stage67d6_download_format_aware_rebuild_macro.json','stage67e_central_bank_changes_mapper.json','stage95_cot_official_dataset_builder.json','stage99_unified_observer_cot_expansion.json']:
            (root/'configs'/name).write_text('{}', encoding='utf-8')
        cfg = {
            'mt5_files_dir': str(mt5_dir),
            'unified_observer_csv': 'data/mt5_bridge/unified_observer_signal.csv',
            'child_stages': [
                {'name':'Stage67D6_DOWNLOAD_FORMAT_AWARE_REBUILD_MACRO','enabled':True,'refresh_stage':True,'command':[sys.executable, str(root/'app/stage67d6_download_format_aware_rebuild_macro.py'), '--root', str(root), '--config', str(root/'configs/stage67d6_download_format_aware_rebuild_macro.json'), '--out', str(root/'reports/stage67d6')]},
                {'name':'Stage67E_CENTRAL_BANK_CHANGES_MAPPER','enabled':True,'refresh_stage':True,'command':[sys.executable, str(root/'app/stage67e_central_bank_changes_mapper.py'), '--root', str(root), '--config', str(root/'configs/stage67e_central_bank_changes_mapper.json'), '--out', str(root/'reports/stage67e'), '--run-readiness', '--run-frequency', '--timeout-seconds', '180']},
                {'name':'Stage95_COT_OFFICIAL_DATASET_BUILDER_NO_DOWNLOAD','enabled':True,'refresh_stage':True,'command':[sys.executable, str(root/'app/stage95_cot_official_dataset_builder.py'), '--root', str(root), '--config', str(root/'configs/stage95_cot_official_dataset_builder.json'), '--out', str(root/'reports/stage95'), '--no-download']},
                {'name':'Stage99_UNIFIED_OBSERVER_COT_EXPANSION','enabled':True,'refresh_stage':False,'command':[sys.executable, str(root/'app/stage99_unified_observer_cot_expansion.py'), '--root', str(root), '--config', str(root/'configs/stage99_unified_observer_cot_expansion.json'), '--out', str(root/'reports/stage99')]},
            ]
        }
        cfg_path = root/'configs/stage100_daily_unified_cot_observer_combo.json'
        cfg_path.write_text(json.dumps(cfg), encoding='utf-8')
        out_dir = root/'reports/stage100'
        result = subprocess.run([sys.executable, str(combo_script), '--root', str(root), '--config', str(cfg_path), '--out', str(out_dir), '--copy-to-mt5-files'], text=True, capture_output=True)
        assert result.returncode == 0, result.stderr + result.stdout
        summary_path = out_dir/'stage100_daily_unified_cot_observer_combo_summary.json'
        summary = json.loads(summary_path.read_text(encoding='utf-8'))
        assert summary['status'] == 'STAGE100_COMPLETE_NO_PROMOTION'
        assert summary['csv_snapshot']['schema_version'] == 'stage99_unified_observer_cot_v1'
        assert summary['csv_snapshot']['rule_count'] == '6'
        assert summary['csv_snapshot']['C96_07_active'] == 'false'
        assert summary['csv_copy']['status'] == 'COPIED'
        assert (mt5_dir/'unified_observer_signal.csv').exists()
        result2 = subprocess.run([sys.executable, str(combo_script), '--root', str(root), '--config', str(cfg_path), '--out', str(out_dir), '--skip-refresh'], text=True, capture_output=True)
        assert result2.returncode == 0, result2.stderr + result2.stdout
        summary2 = json.loads(summary_path.read_text(encoding='utf-8'))
        statuses = {c['name']: c['status'] for c in summary2['child_runs']}
        assert statuses['Stage67D6_DOWNLOAD_FORMAT_AWARE_REBUILD_MACRO'] == 'SKIPPED_REFRESH'
        assert statuses['Stage67E_CENTRAL_BANK_CHANGES_MAPPER'] == 'SKIPPED_REFRESH'
        assert statuses['Stage95_COT_OFFICIAL_DATASET_BUILDER_NO_DOWNLOAD'] == 'SKIPPED_REFRESH'
        assert statuses['Stage99_UNIFIED_OBSERVER_COT_EXPANSION'] == 'PASS'
    print('Stage100 tests passed')


if __name__ == '__main__':
    main()
