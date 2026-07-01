from pathlib import Path
import csv,sys
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from app.stage135b_schema_adaptive_demo_probe_discovery import run, choose_ret_col

def make(path):
    path.parent.mkdir(parents=True,exist_ok=True); fields=['feature_date','fwd_ret_bps_h120','macro_a','macro_b']
    rows=[]
    for i in range(150):
        good=i%3==0
        rows.append({'feature_date':f'2026-06-{(i%20)+1:02d}','fwd_ret_bps_h120':'20' if good else '-2','macro_a':'-1' if good else '2','macro_b':str(i%7)})
    rows[-1]={'feature_date':'2026-06-30','fwd_ret_bps_h120':'20','macro_a':'-1','macro_b':'3'}
    with path.open('w',encoding='utf-8',newline='') as f: w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(rows)

def test_choose_ret_col(): assert choose_ret_col(['x','fwd_ret_bps_h120'])=='fwd_ret_bps_h120'
def test_run_schema_adaptive(tmp_path):
    ds=tmp_path/'data/fundamental_event_inbox/features/stage117_joined_macro_cot_dollar_h1_research_dataset.csv'; make(ds); mt5=tmp_path/'MQL5/Files'; mt5.mkdir(parents=True)
    s=run(tmp_path,ds,mt5,0,5,1.0,.45,9999,True,100)
    assert s['numeric_feature_cols_scanned']>=1
    assert Path(s['score_csv']).exists()
    assert Path(s['repo_kv']).exists()
    assert Path(s['mt5_kv']).exists()
def test_missing_dataset(tmp_path):
    s=run(tmp_path,tmp_path/'missing.csv',tmp_path/'MQL5/Files',0,5,1,.45,10,False,100)
    assert s['decision']=='STAGE135B_DATASET_MISSING'
