import csv, json, subprocess, sys
from pathlib import Path


def wcsv(path, rows, fields):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', newline='', encoding='utf-8') as f:
        w=csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(rows)


def test_failed_range_retains_prior(tmp_path):
    prior=tmp_path/'prior'; incoming=tmp_path/'incoming'; out=tmp_path/'out'
    fields=['time_bucket_utc','profile','event_count','gold_long_pressure','gold_short_pressure','geopolitical_escalation_score','deescalation_score','macro_policy_hawkish_score','macro_policy_dovish_score','inflation_energy_shock_score','market_stress_score','central_bank_gold_score','source']
    wcsv(prior/'stage166g_persistent_gdelt_points.csv',[{'time_bucket_utc':'2026-07-10T00:00:00Z','profile':'market_stress','event_count':'5','source':'GDELT'}],fields)
    wcsv(incoming/'stage166f_gdelt_points.csv',[],fields)
    sf=['profile','start_utc','end_utc','ok','bytes','point_count','error','json_fallback_ok','json_fallback_bytes','json_fallback_error','url']
    wcsv(incoming/'stage166f_fetch_status.csv',[{'profile':'market_stress','start_utc':'2026-07-09T00:00:00Z','end_utc':'2026-07-11T00:00:00Z','ok':'False','error':'HTTP 429'}],sf)
    script=Path(__file__).parents[1]/'app'/'stage166g_gdelt_persistent_store.py'
    cp=subprocess.run([sys.executable,str(script),'--prior-dir',str(prior),'--incoming-dir',str(incoming),'--out-dir',str(out)],text=True,capture_output=True)
    assert cp.returncode==0, cp.stderr
    rows=list(csv.DictReader((out/'stage166g_persistent_gdelt_points.csv').open()))
    assert len(rows)==1 and rows[0]['event_count']=='5'
    m=json.loads((out/'stage166g_persistent_manifest.json').read_text())
    assert m['failed_task_count']==1


def test_successful_zero_range_clears_prior(tmp_path):
    prior=tmp_path/'prior'; incoming=tmp_path/'incoming'; out=tmp_path/'out'
    fields=['time_bucket_utc','profile','event_count','gold_long_pressure','gold_short_pressure','geopolitical_escalation_score','deescalation_score','macro_policy_hawkish_score','macro_policy_dovish_score','inflation_energy_shock_score','market_stress_score','central_bank_gold_score','source']
    wcsv(prior/'stage166g_persistent_gdelt_points.csv',[{'time_bucket_utc':'2026-07-10T00:00:00Z','profile':'market_stress','event_count':'5','source':'GDELT'}],fields)
    wcsv(incoming/'stage166f_gdelt_points.csv',[],fields)
    sf=['profile','start_utc','end_utc','ok','bytes','point_count','error','json_fallback_ok','json_fallback_bytes','json_fallback_error','url']
    wcsv(incoming/'stage166f_fetch_status.csv',[{'profile':'market_stress','start_utc':'2026-07-09T00:00:00Z','end_utc':'2026-07-11T00:00:00Z','ok':'True','point_count':'0'}],sf)
    script=Path(__file__).parents[1]/'app'/'stage166g_gdelt_persistent_store.py'
    cp=subprocess.run([sys.executable,str(script),'--prior-dir',str(prior),'--incoming-dir',str(incoming),'--out-dir',str(out)],text=True,capture_output=True)
    assert cp.returncode==0, cp.stderr
    rows=list(csv.DictReader((out/'stage166g_persistent_gdelt_points.csv').open()))
    assert rows==[]
