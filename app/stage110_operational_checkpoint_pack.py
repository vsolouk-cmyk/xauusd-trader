#!/usr/bin/env python3
"""Stage110 Operational Checkpoint Pack.

Creates a local checkpoint summary after Stage109 succeeds. No order, no broker,
no MT5 change. This is a documentation/checkpoint builder only.
"""
from __future__ import annotations
import argparse, json, hashlib, zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

HARD_BLOCKS = ["NO_AUTOMATED_ORDER","NO_PAPER_ORDER","NO_BROKER_CONNECTION","NO_MT5_OR_EA_CHANGE","NO_PAPER_LIVE","NO_LIVE","NO_ORDER_AUTHORIZATION_FROM_STAGE110"]

def sha256_file(path: Path) -> str | None:
    if not path.exists() or not path.is_file(): return None
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024), b''): h.update(chunk)
    return h.hexdigest()

def read_json(path: Path) -> Dict[str, Any]:
    if not path.exists(): return {"exists": False, "path": str(path)}
    try:
        data=json.loads(path.read_text(encoding='utf-8'))
        data.setdefault('exists', True); data.setdefault('path', str(path)); return data
    except Exception as e:
        return {"exists": True, "path": str(path), "read_error": str(e)}

def main(argv=None) -> int:
    p=argparse.ArgumentParser(); p.add_argument('--root', default='.'); p.add_argument('--config', required=False); p.add_argument('--out', required=True); p.add_argument('--make-zip', action='store_true')
    args=p.parse_args(argv)
    root=Path(args.root).expanduser().resolve(); out=Path(args.out).expanduser().resolve(); out.mkdir(parents=True, exist_ok=True)
    stage109=read_json(root/'reports/stage109_daily_unified_second_order_observer_combo/stage109_daily_unified_second_order_observer_combo_summary.json')
    stage108=read_json(root/'reports/stage108_unified_observer_second_order_expansion/stage108_unified_observer_second_order_expansion_summary.json')
    bridge=root/'data/mt5_bridge/unified_observer_signal.csv'
    status='STAGE110_COMPLETE_NO_PROMOTION'
    decision='STAGE110_OPERATIONAL_CHECKPOINT_READY_NO_ORDER'
    if stage109.get('status') not in {'STAGE109_COMPLETE_NO_PROMOTION'}:
        status='STAGE110_COMPLETE_WITH_WARNINGS_NO_PROMOTION'; decision='STAGE110_CHECKPOINT_READY_WITH_STAGE109_WARNING_NO_ORDER'
    summary={
        'stage':'Stage110_OPERATIONAL_CHECKPOINT_PACK','root':str(root),'generated_utc':datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'status':status,'decision':decision,'classification':'S110_OPERATIONAL_CHECKPOINT_READY','disposition':'TRANSFER_CHECKPOINT_READY_NO_ORDER',
        'current_operational_runner':'Stage109_DAILY_UNIFIED_SECOND_ORDER_OBSERVER_COMBO','current_observer':'Unified Observer Only 7-rule',
        'rule_ids':['K06_RESILIENT_GOLD_VS_DXY_H120','K03_SAFE_HAVEN_REALYIELD_H120','K07_DXY_TREND_RELIEF_GOLD_TREND_H120','S83_14_REALYIELD_120D_DOWN_GOLD_NOT_TRENDING_H120','S83_13_DXY_120D_DOWN_GOLD_NOT_TRENDING_H120','C96_07_CB_SUPPORT_NOT_CROWDED_H120','S105_03_COT_DECROWDING_CB_SUPPORT_RY_RELIEF_H120'],
        'stage109_reference': {'status': stage109.get('status'), 'decision': stage109.get('decision'), 'issues': stage109.get('issues'), 'path': stage109.get('path')},
        'stage108_reference': {'status': stage108.get('status'), 'decision': stage108.get('decision'), 'issues': stage108.get('issues'), 'path': stage108.get('path')},
        'bridge_csv': {'path': str(bridge), 'exists': bridge.exists(), 'sha256': sha256_file(bridge)},
        'hard_blocks': HARD_BLOCKS,
        'next_recommended_actions':['Commit Stage105-Stage110 and EA panel changes after git status review.','Use Stage109 as the daily runner.','Move to a new session with this checkpoint before starting the next research frontier.']
    }
    sp=out/'stage110_operational_checkpoint_pack_summary.json'; sp.write_text(json.dumps(summary, ensure_ascii=False, indent=2)+"\n", encoding='utf-8')
    md=out/'stage110_operational_checkpoint_pack.md'
    md.write_text("\n".join([
        '# Stage110 Operational Checkpoint Pack','',
        f"- status: `{status}`", f"- decision: `{decision}`", '',
        '## Current operational state','',
        '- Daily runner: `Stage109_DAILY_UNIFIED_SECOND_ORDER_OBSERVER_COMBO`',
        '- Observer: `Unified Observer Only 7-rule`',
        '- Order/broker/live: blocked', '',
        '## Rule IDs', *[f"- `{r}`" for r in summary['rule_ids']], '',
        '## Next actions', *[f"- {x}" for x in summary['next_recommended_actions']]
    ])+"\n", encoding='utf-8')
    if args.make_zip:
        zp=out/'stage110_transfer_checkpoint.zip'
        with zipfile.ZipFile(zp, 'w', zipfile.ZIP_DEFLATED) as z:
            z.write(sp, sp.name); z.write(md, md.name)
            for rel in ['reports/stage109_daily_unified_second_order_observer_combo/stage109_daily_unified_second_order_observer_combo_summary.json','reports/stage108_unified_observer_second_order_expansion/stage108_unified_observer_second_order_expansion_summary.json']:
                p=root/rel
                if p.exists(): z.write(p, rel)
        summary['checkpoint_zip']={'path':str(zp),'sha256':sha256_file(zp)}
        sp.write_text(json.dumps(summary, ensure_ascii=False, indent=2)+"\n", encoding='utf-8')
    print(json.dumps({'status':status,'decision':decision,'summary_json':str(sp),'report_md':str(md)}, ensure_ascii=False, indent=2))
    return 0
if __name__=='__main__':
    raise SystemExit(main())
