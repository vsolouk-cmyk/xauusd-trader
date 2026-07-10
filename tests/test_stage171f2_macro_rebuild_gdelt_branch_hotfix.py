from pathlib import Path
import importlib.util, json, tempfile, csv

ROOT=Path(__file__).resolve().parents[1]
MOD=ROOT/'app'/'stage171f_h64l_4h_macro_gdelt_orchestrator.py'


def load():
    spec=importlib.util.spec_from_file_location('stage171f2', MOD)
    m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


def test_config_has_exact_stage64k_args():
    cfg=json.loads((ROOT/'configs'/'stage171f_h64l_4h_macro_gdelt_orchestrator.json').read_text())
    step=[x for x in cfg['local_pipeline'] if 'stage64k' in x['name']][0]
    argv=' '.join(step['argv'])
    assert '--config' in argv and '--out' in argv and step['required'] is True
    assert not any('stage67d6' in ' '.join(x['argv']) for x in cfg['local_pipeline'])


def test_stale_artifact_is_rejected():
    m=load()
    with tempfile.TemporaryDirectory() as td:
        root=Path(td); dl=root/'downloads'; dl.mkdir(); report=root/'reports'; report.mkdir()
        z=dl/'stage166f-gdelt-refresh-1.zip'
        import zipfile, os, time
        with zipfile.ZipFile(z,'w') as f:
            f.writestr('stage166f_current_event_intraday_panel.csv','time_bucket_utc,event_count\n2026-01-01T00:00:00Z,1\n')
        old=time.time()-48*3600; os.utime(z,(old,old))
        out=m.artifact_import_gdelt(root, {'downloads_dir':str(dl),'artifact_globs':['*.zip'],'max_artifact_age_hours':18}, report)
        assert out['ok'] is False and out['error']=='STALE_GDELT_ARTIFACT_NOT_IMPORTED'


def test_merge_helper_preserves_history():
    import subprocess, sys
    with tempfile.TemporaryDirectory() as td:
        t=Path(td); old=t/'old.csv'; new=t/'new.csv'; out=t/'out.csv'
        old.write_text('time_bucket_utc,event_count\n2026-01-01T00:00:00Z,1\n')
        new.write_text('time_bucket_utc,event_count\n2026-01-02T00:00:00Z,2\n')
        subprocess.run([sys.executable,str(ROOT/'app'/'stage166f_merge_refresh_snapshot.py'),'--existing',str(old),'--incoming',str(new),'--out',str(out)],check=True)
        rows=list(csv.DictReader(out.open()))
        assert len(rows)==2
