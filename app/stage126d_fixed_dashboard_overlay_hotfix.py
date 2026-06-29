#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, shutil
from pathlib import Path

STAGE = "Stage126D_FIXED_DASHBOARD_OVERLAY_HOTFIX"

DEFAULT_MT5_ROOT = Path("/Users/vahid/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5/MQL5")
INDICATOR_FILES = [
    "XAUUSD_Stage124F_Rule8OverlayIndicator.mq5",
    "XAUUSD_Stage126_Rule9FrontierOverlayIndicator.mq5",
]

def copy_indicators(root: Path, mt5_root: Path) -> dict:
    src_dir = root / "mql5" / "Indicators"
    out_root = mt5_root / "Indicators"
    out_nested = mt5_root / "Indicators" / "Advisors" / "XAUUSD"
    out_root.mkdir(parents=True, exist_ok=True)
    out_nested.mkdir(parents=True, exist_ok=True)
    copied = []
    for fname in INDICATOR_FILES:
        src = src_dir / fname
        if not src.exists():
            raise FileNotFoundError(f"Missing indicator source: {src}")
        for dst_dir in (out_root, out_nested):
            dst = dst_dir / fname
            shutil.copy2(src, dst)
            copied.append(str(dst))
    return {"copied": copied, "count": len(copied)}

def run(root: Path, mt5_root: Path, write_mt5_indicators: bool) -> dict:
    report_dir = root / "reports" / "stage126d_fixed_dashboard_overlay_hotfix"
    report_dir.mkdir(parents=True, exist_ok=True)
    result = {
        "stage": STAGE,
        "status": "STAGE126D_COMPLETE_FIXED_DASHBOARD_HOTFIX_READY_NO_ORDER",
        "decision": "STAGE126D_INDICATOR_LAYOUT_FIXED_NO_ORDER",
        "hard_blocks": ["NO_ORDER_SEND", "NO_CTRADE_USAGE", "NO_PAPER_LIVE", "NO_LIVE", "NO_EA_CHANGE"],
        "root": str(root),
        "mt5_root": str(mt5_root),
        "write_mt5_indicators": write_mt5_indicators,
        "layout_policy": "BOTTOM_LEFT_FIXED_PIXEL_ANCHOR_WITH_CHART_CHANGE_RERENDER",
        "stage124f_defaults": {"corner": "CORNER_LEFT_LOWER", "x": 10, "y": 170, "font_size": 6, "line_height": 17},
        "stage126_defaults": {"corner": "CORNER_LEFT_LOWER", "x": 10, "y": 75, "font_size": 6, "line_height": 17},
        "notes": [
            "Keeps the 7-rule EA unchanged.",
            "Uses OBJ_LABEL fixed-pixel bottom-left anchor rather than chart price/time coordinates.",
            "Re-renders on CHARTEVENT_CHART_CHANGE to restore font and distances after chart zoom/resize/scroll.",
        ],
    }
    if write_mt5_indicators:
        result["mt5_copy"] = copy_indicators(root, mt5_root)
    summary = report_dir / "stage126d_fixed_dashboard_overlay_hotfix_summary.json"
    report = report_dir / "stage126d_fixed_dashboard_overlay_hotfix_report.md"
    summary.write_text(json.dumps(result, indent=2), encoding="utf-8")
    report.write_text("# Stage126D fixed dashboard overlay hotfix\n\nNo-order indicator layout patch.\n", encoding="utf-8")
    result["summary_json"] = str(summary)
    result["report_md"] = str(report)
    print(json.dumps(result, indent=2))
    return result

def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--root", default=".")
    p.add_argument("--mt5-root", default=str(DEFAULT_MT5_ROOT))
    p.add_argument("--write-mt5-indicators", action="store_true")
    args = p.parse_args()
    run(Path(args.root).expanduser().resolve(), Path(args.mt5_root).expanduser(), args.write_mt5_indicators)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
