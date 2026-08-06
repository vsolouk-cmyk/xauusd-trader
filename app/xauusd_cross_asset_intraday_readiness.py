#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import zipfile
from datetime import datetime, timezone
from pathlib import Path

PROGRAM = "XAUUSD_CROSS_ASSET_INTRADAY_READINESS_V1_2_SELF_VALIDATING_CSV_REPAIR"
REPORT_DIR = Path("reports/xauusd_cross_asset_intraday_readiness")
CONFIG_PATH = Path("config/xauusd_cross_asset_intraday_readiness_v1.json")
FORBIDDEN_EXECUTION_TOKENS = (
    "OrderSend(", "CTrade", ".Buy(", ".Sell(", "PositionOpen(",
    "PositionClose(", "TRADE_ACTION_DEAL", "MqlTradeRequest",
)


class ReadinessError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_path(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_config(root: Path) -> dict:
    path = root / CONFIG_PATH
    if not path.is_file():
        raise ReadinessError(f"config missing: {path}")
    cfg = json.loads(path.read_text(encoding="utf-8"))
    if cfg.get("program") != PROGRAM:
        raise ReadinessError("config program mismatch")
    return cfg


def static_no_execution_check(root: Path) -> list[str]:
    violations: list[str] = []
    for rel in (Path("mt5/XAUUSD_CrossAssetInventory.mq5"),):
        path = root / rel
        if not path.is_file():
            violations.append(f"missing:{rel}")
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for token in FORBIDDEN_EXECUTION_TOKENS:
            if token in text:
                violations.append(f"{rel}:{token}")
    return violations


def canonical_mt5_csv(cfg: dict) -> Path:
    base = Path(cfg["mt5_files_directory"]).expanduser()
    return (base / cfg["mt5_inventory_relative_path"]).resolve()


def inventory_candidate_paths(cfg: dict, override: str | None = None) -> list[Path]:
    if override:
        return [Path(override).expanduser().resolve()]
    canonical = canonical_mt5_csv(cfg)
    pattern = cfg.get("mt5_inventory_snapshot_glob", "mt5_cross_asset_inventory_*.csv")
    candidates = [canonical]
    if canonical.parent.is_dir():
        candidates.extend(canonical.parent.glob(pattern))
    unique: dict[str, Path] = {}
    for path in candidates:
        unique[str(path)] = path
    return sorted(
        unique.values(),
        key=lambda path: path.stat().st_mtime_ns if path.is_file() else -1,
        reverse=True,
    )


def parse_int(value: str | None) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def parse_float(value: str | None) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def epoch_iso(value: str | None) -> str | None:
    seconds = parse_int(value)
    if seconds <= 0:
        return None
    return datetime.fromtimestamp(seconds, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def read_inventory(path: Path) -> list[dict]:
    if not path.is_file():
        raise ReadinessError(f"MT5 inventory CSV missing: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)
        fieldnames = set(reader.fieldnames or [])
    required = {
        "symbol", "description", "categories", "trade_mode",
        "h1_bars", "h1_first_epoch", "h1_last_epoch", "h1_synchronized",
        "m15_bars", "d1_bars", "spread_bps",
    }
    if not rows:
        raise ReadinessError("MT5 inventory contains no matching symbols")
    missing = required - fieldnames
    if missing:
        raise ReadinessError(f"MT5 inventory missing columns: {sorted(missing)}")
    normalized: list[dict] = []
    for raw in rows:
        categories = sorted({part.strip() for part in (raw.get("categories") or "").split("|") if part.strip()})
        if not raw.get("symbol") or not categories:
            continue
        normalized.append({
            "symbol": raw.get("symbol", ""),
            "description": raw.get("description", ""),
            "categories": categories,
            "selected": bool(parse_int(raw.get("selected"))),
            "trade_mode": parse_int(raw.get("trade_mode")),
            "digits": parse_int(raw.get("digits")),
            "point": parse_float(raw.get("point")),
            "bid": parse_float(raw.get("bid")),
            "ask": parse_float(raw.get("ask")),
            "spread_points": parse_float(raw.get("spread_points")),
            "spread_bps": parse_float(raw.get("spread_bps")),
            "m15_bars": parse_int(raw.get("m15_bars")),
            "m15_first_utc": epoch_iso(raw.get("m15_first_epoch")),
            "m15_last_utc": epoch_iso(raw.get("m15_last_epoch")),
            "m15_synchronized": bool(parse_int(raw.get("m15_synchronized"))),
            "h1_bars": parse_int(raw.get("h1_bars")),
            "h1_first_utc": epoch_iso(raw.get("h1_first_epoch")),
            "h1_last_utc": epoch_iso(raw.get("h1_last_epoch")),
            "h1_synchronized": bool(parse_int(raw.get("h1_synchronized"))),
            "d1_bars": parse_int(raw.get("d1_bars")),
            "d1_first_utc": epoch_iso(raw.get("d1_first_epoch")),
            "d1_last_utc": epoch_iso(raw.get("d1_last_epoch")),
            "d1_synchronized": bool(parse_int(raw.get("d1_synchronized"))),
        })
    if not normalized:
        raise ReadinessError("MT5 inventory contains no valid matching symbol rows")
    return normalized


def inventory_file_probe(path: Path) -> dict:
    probe = {"path": str(path), "exists": path.is_file()}
    if not path.is_file():
        return probe
    raw = path.read_bytes()
    probe.update({
        "size": len(raw),
        "line_count": raw.count(b"\n"),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "head_hex": raw[:96].hex(),
    })
    return probe


def select_valid_inventory(cfg: dict, override: str | None = None) -> tuple[Path, list[dict], list[dict]]:
    diagnostics: list[dict] = []
    valid: list[tuple[Path, list[dict]]] = []
    for path in inventory_candidate_paths(cfg, override):
        if not path.is_file():
            diagnostics.append({**inventory_file_probe(path), "valid": False, "reason": "missing"})
            continue
        try:
            rows = read_inventory(path)
        except Exception as exc:
            diagnostics.append({
                **inventory_file_probe(path),
                "valid": False,
                "reason": f"{type(exc).__name__}: {exc}",
            })
            continue
        diagnostics.append({
            **inventory_file_probe(path),
            "valid": True,
            "rows": len(rows),
            "mtime_ns": path.stat().st_mtime_ns,
        })
        valid.append((path, rows))
    if valid:
        return valid[0][0], valid[0][1], diagnostics
    detail = "; ".join(f"{item['path']}={item.get('reason', 'invalid')}" for item in diagnostics)
    raise ReadinessError(f"no valid MT5 inventory CSV found; {detail}")


def category_presence(rows: list[dict]) -> dict[str, list[dict]]:
    present: dict[str, list[dict]] = {}
    for row in rows:
        for cat in row["categories"]:
            present.setdefault(cat, []).append(row)
    if "USD_INDEX" in present:
        present["USD_PROXY"] = list(present["USD_INDEX"])
    elif "USD_FX_PROXY" in present:
        fx_names = {r["symbol"].upper() for r in present["USD_FX_PROXY"]}
        if any("EURUSD" in name for name in fx_names) and any("USDJPY" in name for name in fx_names):
            present["USD_PROXY"] = list(present["USD_FX_PROXY"])
    return present


def local_file_category(path: Path) -> str | None:
    text = path.name.upper()
    mappings = [
        ("US_RATES", ("US10Y", "UST10", "TNX", "TREASURY")),
        ("USD_INDEX", ("DXY", "USDX", "DOLLAR_INDEX")),
        ("VOLATILITY", ("VIX", "VOLX")),
        ("SILVER", ("XAG", "SILVER")),
        ("USD_FX_PROXY", ("EURUSD", "USDJPY")),
        ("EQUITY_RISK", ("US500", "SPX500", "SP500")),
        ("ENERGY", ("WTI", "USOIL", "BRENT", "XTI", "XBR")),
    ]
    for category, tokens in mappings:
        if any(token in text for token in tokens):
            return category
    return None


def scan_local_files(root: Path) -> list[dict]:
    scan_roots = [root / "data", root / "reports", Path.home() / "Downloads" / "xauusd_fundamental_event_inbox"]
    results: list[dict] = []
    for base in scan_roots:
        if not base.exists():
            continue
        for current, dirs, files in os.walk(base, followlinks=False):
            dirs[:] = [d for d in dirs if d not in {".git", "_archive"} and not d.startswith("_incoming")]
            current_path = Path(current)
            if current_path.is_symlink():
                dirs[:] = []
                continue
            for name in files:
                path = current_path / name
                if path.is_symlink():
                    continue
                category = local_file_category(path)
                if category:
                    results.append({
                        "category": category,
                        "path": str(path),
                        "size": path.stat().st_size,
                        "sha256": sha256_path(path),
                    })
    return sorted(results, key=lambda item: (item["category"], item["path"]))


def readiness_decision(rows: list[dict], cfg: dict) -> tuple[str, dict]:
    present = category_presence(rows)
    minimum = int(cfg["minimum_h1_bars"])
    category_status: dict[str, dict] = {}
    categories = sorted(set(cfg["required_categories"] + cfg["optional_categories"] + ["USD_INDEX", "USD_FX_PROXY"]))
    for category in categories:
        matches = present.get(category, [])
        history_ready = [r for r in matches if r["h1_synchronized"] and r["h1_bars"] >= minimum]
        category_status[category] = {
            "symbol_present": bool(matches),
            "history_ready": bool(history_ready),
            "symbols": [r["symbol"] for r in matches],
            "history_ready_symbols": [r["symbol"] for r in history_ready],
        }

    required = cfg["required_categories"]
    missing_symbols = [cat for cat in required if not category_status.get(cat, {}).get("symbol_present")]
    history_needed = [cat for cat in required if category_status.get(cat, {}).get("symbol_present") and not category_status[cat]["history_ready"]]

    if missing_symbols:
        decision = "PARTIAL_CROSS_ASSET_INTRADAY_REQUIRES_EXTERNAL_OR_BROKER_SYMBOLS"
    elif history_needed:
        decision = "PASS_SYMBOLS_PRESENT_HISTORY_DOWNLOAD_REQUIRED"
    else:
        decision = "PASS_CROSS_ASSET_INTRADAY_CORE_AVAILABLE_FOR_CAUSAL_PANEL"
    return decision, {
        "category_status": category_status,
        "missing_required_categories": missing_symbols,
        "history_download_required_categories": history_needed,
    }


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted({key for row in rows for key in row}) if rows else ["empty"]
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            cooked = {key: "|".join(value) if isinstance(value, list) else value for key, value in row.items()}
            writer.writerow(cooked)


def create_results_zip(report_dir: Path) -> Path:
    output = Path.home() / "Downloads" / "XAUUSD_CROSS_ASSET_INTRADAY_READINESS_RESULTS.zip"
    output.parent.mkdir(parents=True, exist_ok=True)
    files = sorted(p for p in report_dir.iterdir() if p.is_file() and p.name != "RESULTS_MANIFEST.json")
    manifest = {"program": PROGRAM, "generated_utc": utc_now(), "files": []}
    for path in files:
        manifest["files"].append({"path": path.name, "size": path.stat().st_size, "sha256": sha256_path(path)})
    manifest_path = report_dir / "RESULTS_MANIFEST.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    files.append(manifest_path)
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(files):
            archive.write(path, path.name)
    return output


def preflight(root: Path) -> dict:
    cfg = load_config(root)
    violations = static_no_execution_check(root)
    selected_path: Path | None = None
    selected_rows: list[dict] = []
    diagnostics: list[dict] = []
    try:
        selected_path, selected_rows, diagnostics = select_valid_inventory(cfg)
    except ReadinessError as exc:
        diagnostics = [{"valid": False, "reason": str(exc)}]
    result = {
        "program": PROGRAM,
        "generated_utc": utc_now(),
        "decision": "PASS_CROSS_ASSET_READINESS_PREFLIGHT_NO_ORDER",
        "pass": not violations,
        "paper_order_allowed": False,
        "demo_order_allowed": False,
        "live_order_allowed": False,
        "mt5_inventory_expected_path": str(canonical_mt5_csv(cfg)),
        "mt5_inventory_valid": selected_path is not None,
        "mt5_inventory_selected_path": str(selected_path) if selected_path else None,
        "mt5_inventory_rows": len(selected_rows),
        "inventory_candidate_diagnostics": diagnostics,
        "static_execution_violations": violations,
        "required_next_action": "COLLECT" if selected_path else "RUN_MT5_SCRIPT_ONCE_THEN_COLLECT",
    }
    if violations:
        result["decision"] = "CROSS_ASSET_READINESS_PREFLIGHT_FAIL_CLOSED"
    return result


def collect(root: Path, override: str | None = None) -> dict:
    cfg = load_config(root)
    violations = static_no_execution_check(root)
    if violations:
        raise ReadinessError(f"execution-token violations: {violations}")
    mt5_csv, rows, diagnostics = select_valid_inventory(cfg, override)
    local_files = scan_local_files(root)
    decision, readiness = readiness_decision(rows, cfg)
    report_dir = root / REPORT_DIR
    report_dir.mkdir(parents=True, exist_ok=True)
    write_csv(report_dir / "mt5_cross_asset_symbols_normalized.csv", rows)
    write_csv(report_dir / "local_cross_asset_files.csv", local_files)
    (report_dir / "mt5_inventory_selection.json").write_text(
        json.dumps({
            "program": PROGRAM,
            "generated_utc": utc_now(),
            "selected_path": str(mt5_csv),
            "selected_rows": len(rows),
            "candidate_diagnostics": diagnostics,
        }, indent=2),
        encoding="utf-8",
    )
    summary = {
        "program": PROGRAM,
        "generated_utc": utc_now(),
        "decision": decision,
        "pass": True,
        "paper_order_allowed": False,
        "demo_order_allowed": False,
        "live_order_allowed": False,
        "mt5_inventory_source": str(mt5_csv),
        "mt5_symbol_rows": len(rows),
        "local_matching_files": len(local_files),
        **readiness,
    }
    (report_dir / "cross_asset_readiness_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    lines = [
        "# XAUUSD Cross-Asset Intraday Readiness",
        "",
        f"Decision: `{decision}`",
        "",
        f"Inventory source: `{mt5_csv}`",
        "",
        "No paper, demo or live orders are authorized.",
        "",
        "## Required categories",
    ]
    for category in cfg["required_categories"]:
        status = readiness["category_status"].get(category, {})
        lines.append(f"- {category}: symbols={status.get('symbols', [])}; history_ready={status.get('history_ready', False)}")
    lines.extend(["", "## Optional categories"])
    for category in cfg["optional_categories"]:
        status = readiness["category_status"].get(category, {})
        lines.append(f"- {category}: symbols={status.get('symbols', [])}; history_ready={status.get('history_ready', False)}")
    (report_dir / "cross_asset_readiness_decision.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    output = create_results_zip(report_dir)
    summary["results_zip"] = str(output)
    summary["results_zip_sha256"] = sha256_path(output)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("preflight", "collect"))
    parser.add_argument("--root", default=".")
    parser.add_argument("--mt5-csv")
    args = parser.parse_args(argv)
    root = Path(args.root).expanduser().resolve()
    try:
        result = preflight(root) if args.command == "preflight" else collect(root, args.mt5_csv)
        print(json.dumps(result, indent=2))
        return 0 if result.get("pass") else 2
    except Exception as exc:
        failure = {
            "program": PROGRAM,
            "generated_utc": utc_now(),
            "decision": "CROSS_ASSET_READINESS_FAIL_CLOSED",
            "pass": False,
            "paper_order_allowed": False,
            "demo_order_allowed": False,
            "live_order_allowed": False,
            "error": f"{type(exc).__name__}: {exc}",
        }
        print(json.dumps(failure, indent=2))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
