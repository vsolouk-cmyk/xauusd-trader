from pathlib import Path
import importlib.util, json, shutil
ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('stage110', ROOT/'app/stage110_operational_checkpoint_pack.py')
stage110 = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(stage110)

def test_stage110_checkpoint(tmp_path):
    import shutil
    if tmp_path.exists():
        shutil.rmtree(tmp_path)
    root=tmp_path/'repo'; (root/'reports/stage109_daily_unified_second_order_observer_combo').mkdir(parents=True); (root/'data/mt5_bridge').mkdir(parents=True)
    (root/'reports/stage109_daily_unified_second_order_observer_combo/stage109_daily_unified_second_order_observer_combo_summary.json').write_text(json.dumps({'status':'STAGE109_COMPLETE_NO_PROMOTION','decision':'OK','issues':[]}), encoding='utf-8')
    (root/'data/mt5_bridge/unified_observer_signal.csv').write_text('schema_version,stage108_unified_observer_second_order_v1\n', encoding='utf-8')
    out=root/'reports/stage110'; rc=stage110.main(['--root',str(root),'--out',str(out),'--make-zip'])
    assert rc==0
    summ=json.loads((out/'stage110_operational_checkpoint_pack_summary.json').read_text())
    assert summ['status']=='STAGE110_COMPLETE_NO_PROMOTION'
    assert len(summ['rule_ids'])==7
    assert (out/'stage110_transfer_checkpoint.zip').exists()

if __name__ == '__main__':
    test_stage110_checkpoint(Path('/tmp/stage110_test'))
    print('Stage110 tests passed')
