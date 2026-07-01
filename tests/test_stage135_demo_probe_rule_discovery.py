
from pathlib import Path
import csv, sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.stage135_demo_probe_rule_discovery import run, get_ret_col, find_col

def write_dataset(path:Path):
    path.parent.mkdir(parents=True,exist_ok=True)
    fields=['feature_date','fwd_ret_bps_h120','dxy_ret_20d','gold_sma20_over_50','real_yield_change_20d']
    rows=[]
    for i in range(100):
        good=i%3==0
        rows.append({'feature_date':f'2026-06-{(i%20)+1:02d}','fwd_ret_bps_h120':'20' if good else '-3','dxy_ret_20d':'-1' if good else '2','gold_sma20_over_50':'1' if good else '-1','real_yield_change_20d':'-1' if good else '2'})
    rows[-1].update({'feature_date':'2026-06-30','dxy_ret_20d':'-1','gold_sma20_over_50':'1','real_yield_change_20d':'-1','fwd_ret_bps_h120':'20'})
    with path.open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(rows)

def test_column_detection():
    cols=['abc','fwd_ret_bps_h120','dxy_ret_20d']
    assert get_ret_col(cols)=='fwd_ret_bps_h120'
    assert find_col(cols,['dxy_change_20d','dxy_ret_20d'])=='dxy_ret_20d'

def test_run_writes_stage134_compatible_kv(tmp_path):
    root=tmp_path; dataset=root/'data/fundamental_event_inbox/features/stage117_joined_macro_cot_dollar_h1_research_dataset.csv'; write_dataset(dataset)
    mt5=tmp_path/'MQL5/Files'; mt5.mkdir(parents=True)
    s=run(root,dataset,mt5,0,5,1.0,0.45,9999,True)
    assert s['candidate_count']>=1
    assert Path(s['repo_kv']).exists() and Path(s['mt5_kv']).exists()
    txt=Path(s['mt5_kv']).read_text(encoding='utf-8')
    assert 'any_signal_active|' in txt and 'allow_trading|false' in txt and 'order_send|false' in txt

def test_missing_dataset_returns_summary(tmp_path):
    root=tmp_path; mt5=tmp_path/'MQL5/Files'; mt5.mkdir(parents=True)
    s=run(root,root/'missing.csv',mt5,0,5,1.0,0.45,10,False)
    assert s['decision']=='STAGE135_DATASET_MISSING_NO_DEMO_PROBE'
