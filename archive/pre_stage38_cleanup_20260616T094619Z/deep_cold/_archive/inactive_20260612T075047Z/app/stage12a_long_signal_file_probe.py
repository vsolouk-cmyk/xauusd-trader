#!/usr/bin/env python3
"""
Stage 12A Long Signal File Probe

Purpose:
- Diagnose MT5/EA signal CSV file status before feeding it to Stage 12A.
- Distinguish:
  1) file_missing
  2) file_exists_empty
  3) file_exists_bom_only
  4) file_exists_header_only
  5) file_exists_with_rows

Hard rules:
- Diagnostic only.
- No EA change.
- No automatic trading.
"""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple


TOOL_VERSION = "v1"
DEFAULT_OUT_DIR = Path("data/reports/stage12a_long_signal_file_probe")


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def decode_bytes(raw: bytes) -> Tuple[str, str]:
    if raw.startswith(b"\xff\xfe"):
        try:
            return raw.decode("utf-16"), "utf-16"
        except Exception:
            pass
    if raw.startswith(b"\xfe\xff"):
        try:
            return raw.decode("utf-16-be"), "utf-16-be"
        except Exception:
            pass
    if raw.startswith(b"\xef\xbb\xbf"):
        try:
            return raw.decode("utf-8-sig"), "utf-8-sig"
        except Exception:
            pass
    for enc in ["utf-8-sig", "utf-8", "utf-16", "cp1252", "latin1"]:
        try:
            return raw.decode(enc), enc
        except Exception:
            continue
    return raw.decode("latin1", errors="replace"), "latin1-replace"


def probe_file(path: Path) -> Dict:
    rec = {
        "path": str(path),
        "exists": path.exists(),
        "tool_version": TOOL_VERSION,
    }
    if not path.exists():
        rec.update({
            "status": "file_missing",
            "size_bytes": 0,
            "encoding_detected": "",
            "rows": 0,
            "headers": [],
            "latest_row": {},
            "interpretation": "The MT5/EA signal file path does not exist.",
        })
        return rec

    raw = path.read_bytes()
    text, enc = decode_bytes(raw)
    stripped = text.strip("\ufeff\r\n\t ")
    rec["size_bytes"] = len(raw)
    rec["encoding_detected"] = enc
    rec["raw_hex_prefix"] = raw[:16].hex()

    if len(raw) == 0:
        rec.update({
            "status": "file_exists_empty",
            "rows": 0,
            "headers": [],
            "latest_row": {},
            "interpretation": "The signal file exists but has zero bytes. EA has not written header or signal rows.",
        })
        return rec

    if len(raw) <= 3 and stripped == "":
        rec.update({
            "status": "file_exists_bom_only",
            "rows": 0,
            "headers": [],
            "latest_row": {},
            "interpretation": "The signal file exists but contains only a byte-order mark. This usually means the EA created the file but has not written any signal/header rows.",
        })
        return rec

    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        rec.update({
            "status": "file_exists_no_text_rows",
            "rows": 0,
            "headers": [],
            "latest_row": {},
            "interpretation": "The file exists, but no non-empty text rows were found.",
        })
        return rec

    try:
        sample = "\n".join(lines)
        reader = csv.DictReader(sample.splitlines())
        rows = list(reader)
        headers = list(reader.fieldnames or [])
    except Exception:
        rows = []
        headers = []

    if headers and not rows:
        rec.update({
            "status": "file_exists_header_only",
            "rows": 0,
            "headers": headers,
            "latest_row": {},
            "interpretation": "The signal file has a header but no signal rows yet.",
        })
        return rec

    if rows:
        rec.update({
            "status": "file_exists_with_rows",
            "rows": len(rows),
            "headers": headers,
            "latest_row": rows[-1],
            "interpretation": "The signal file has at least one signal row and can be consumed by Stage 12A.",
        })
        return rec

    rec.update({
        "status": "file_exists_unparsed_text",
        "rows": 0,
        "headers": [],
        "latest_row": {},
        "text_preview": lines[:5],
        "interpretation": "The file contains text, but it could not be parsed as CSV with a header.",
    })
    return rec


def write_report(out_dir: Path, rec: Dict) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "stage12a_long_signal_file_probe.json"
    md_path = out_dir / "stage12a_long_signal_file_probe.md"
    json_path.write_text(json.dumps(rec, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [
        "# Stage 12A Long Signal File Probe",
        "",
        f"Generated UTC: `{now_iso()}`",
        f"Tool version: `{TOOL_VERSION}`",
        "",
        "> Hard rule: diagnostic only. No EA change, no automatic trading.",
        "",
        "## Result",
        f"- path: `{rec.get('path')}`",
        f"- exists: `{rec.get('exists')}`",
        f"- status: `{rec.get('status')}`",
        f"- size_bytes: `{rec.get('size_bytes')}`",
        f"- encoding_detected: `{rec.get('encoding_detected')}`",
        f"- rows: `{rec.get('rows')}`",
        f"- headers: `{rec.get('headers')}`",
        "",
        "## Interpretation",
        f"- {rec.get('interpretation')}",
        "",
        "## Latest row",
        "```json",
        json.dumps(rec.get("latest_row", {}), indent=2, ensure_ascii=False),
        "```",
        "",
        "## Next action",
    ]

    status = rec.get("status")
    if status in {"file_exists_bom_only", "file_exists_empty", "file_exists_header_only", "file_exists_no_text_rows"}:
        lines += [
            "- Keep Stage 12A as dashboard, but treat long-signal file as found-with-zero-signals.",
            "- Let the EA continue running until it writes an actual signal row.",
            "- If you want a persistent heartbeat/header, patch the EA later; do not add order logic.",
        ]
    elif status == "file_exists_with_rows":
        lines += [
            "- Run Stage 12A with this same `--long-signal-csv` path.",
            "- The report should show long signal rows.",
        ]
    elif status == "file_missing":
        lines += [
            "- Re-check the MT5 Common Files path.",
        ]
    else:
        lines += [
            "- Inspect file format and delimiter.",
        ]

    lines += [
        "",
        "## Output files",
        f"- json: `{json_path}`",
        f"- md: `{md_path}`",
    ]

    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return md_path


def run(path: Path, out_dir: Path) -> int:
    rec = probe_file(path)
    md = write_report(out_dir, rec)
    print("Stage 12A long signal file probe: DONE")
    print(f"status={rec.get('status')} rows={rec.get('rows')} size_bytes={rec.get('size_bytes')} encoding={rec.get('encoding_detected')}")
    print(f"Report: {md}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--signal-csv", required=True, help="Full path to MT5/EA signal CSV")
    p.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    args = p.parse_args()
    return run(Path(args.signal_csv).expanduser(), Path(args.out_dir))


if __name__ == "__main__":
    raise SystemExit(main())
