#!/usr/bin/env python3
"""Materialize read-only archived Stage64 reports required by archived rebuilders.

Copies only missing files from archive/repo_cleanup_20260626/reports_inactive/stage64*
into reports/stage64*. Existing active files are never overwritten. Reports are
operational compatibility inputs and remain subject to the repo's reports ignore policy.
"""
from __future__ import annotations
import argparse, json, shutil
from datetime import datetime, timezone
from pathlib import Path


def iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00','Z')


def main() -> int:
    p=argparse.ArgumentParser()
    p.add_argument('--root', required=True)
    p.add_argument('--archive-dir', default='archive/repo_cleanup_20260626/reports_inactive')
    p.add_argument('--active-dir', default='reports')
    p.add_argument('--prefix', action='append', default=['stage64'])
    a=p.parse_args()
    root=Path(a.root).expanduser().resolve()
    archive=(root/a.archive_dir).resolve()
    active=(root/a.active_dir).resolve()
    if not archive.exists():
        raise SystemExit(f'archive reports missing: {archive}')
    copied=[]; existing=[]
    prefixes=tuple(a.prefix)
    for src in sorted(archive.rglob('*')):
        if not src.is_file():
            continue
        rel=src.relative_to(archive)
        if not rel.parts or not rel.parts[0].startswith(prefixes):
            continue
        dst=active/rel
        if dst.exists():
            existing.append(str(rel)); continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src,dst)
        copied.append(str(rel))
    out=root/'reports'/'stage171g_stage64_archive_compat_materializer'
    out.mkdir(parents=True, exist_ok=True)
    summary={
        'stage':'Stage171G_STAGE64_ARCHIVE_COMPAT_MATERIALIZER',
        'generated_utc':iso(),
        'archive_dir':str(archive),
        'active_dir':str(active),
        'copied_count':len(copied),
        'already_existing_count':len(existing),
        'required_stage64j5_exists':(active/'stage64j5_event_calendar_forward_governance_acceptance'/'stage64j5_event_calendar_forward_governance_acceptance_summary.json').exists(),
        'overwrote_existing':False,
    }
    (out/'stage171g_stage64_archive_compat_summary.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(summary,indent=2))
    return 0 if summary['required_stage64j5_exists'] else 2

if __name__=='__main__':
    raise SystemExit(main())
