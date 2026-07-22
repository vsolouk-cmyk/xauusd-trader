#!/usr/bin/env python3
"""Stage180 — frozen-model parallel shadow cycle.

This program refreshes the already-approved AMarkets UTC alignment only when
its raw source is newer, loads the exact frozen Stage178 model and feature
contract, processes every completed H1 bar after model activation, and writes
an idempotent observation-only shadow ledger.

It never places, routes, previews, or simulates a broker order.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import pickle
import sqlite3
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

MS_HOUR = 3_600_000
DECISION_ACTIVE = "STAGE180_FROZEN_MODEL_SHADOW_ACTIVE_NO_ORDER"
DECISION_WAIT = "STAGE180_WAITING_FOR_POST_ACTIVATION_COMPLETE_BAR"
DECISION_BLOCK = "STAGE180_BLOCKED_MODEL_OR_INPUT_CONTRACT"


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_alignment_contract_from_db(
    aligned_db: Path,
    fallback_report: Path,
) -> dict[str, Any]:
    """Prefer immutable PASS provenance over a report a failed re-audit may overwrite."""
    if aligned_db.exists():
        try:
            with sqlite3.connect(aligned_db) as connection:
                row = connection.execute(
                    "SELECT value FROM provenance WHERE key = ?",
                    ("stage177c_time_contract",),
                ).fetchone()
            if row is not None:
                payload = json.loads(row[0])
                if str(payload.get("decision", "")).startswith("PASS"):
                    return payload
        except (sqlite3.Error, json.JSONDecodeError, KeyError):
            pass
    return read_json(fallback_report)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve(root: Path, value: str) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else root / path


def import_module(path: Path, name: str) -> Any:
    """Import a source module with normal sys.modules registration.

    Python 3.14 dataclasses inspect ``sys.modules[cls.__module__]`` while the
    class decorator runs. ``module_from_spec`` alone does not perform that
    registration, so the module must be inserted before ``exec_module``.
    """
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot import module from {path}")

    module = importlib.util.module_from_spec(spec)
    previous = sys.modules.get(name)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        if previous is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = previous
        raise
    return module


def authorization_check(stage178: dict[str, Any], stage179: dict[str, Any]) -> dict[str, Any]:
    gates = stage179.get("gates", {})
    failed = sorted(key for key, value in gates.items() if not bool(value))
    selected178 = stage178.get("selected_candidate", {})
    selected179 = stage179.get("stage178_selected", {})
    checks = {
        "stage178_survivor": stage178.get("decision")
        == "PROMOTE_TO_CONTROLLED_PAPER_DESIGN",
        "stage179_research_survivor": stage179.get("decision")
        == "RESEARCH_SURVIVOR_NEEDS_ONE_TARGETED_DIAGNOSTIC",
        "only_uncertainty_gate_failed": failed == ["candidate_bootstrap_p10_positive"],
        "stage178_parity": bool(stage179.get("parity", {}).get("pass")),
        "candidate_match": selected178.get("candidate") == selected179.get("candidate"),
        "model_match": selected178.get("model") == selected179.get("model"),
        "target_match": selected178.get("target") == selected179.get("target"),
        "broker_order_forbidden": not bool(stage179.get("broker_order_allowed", False)),
    }
    return {
        "checks": checks,
        "pass": all(checks.values()),
        "failed_stage179_gates": failed,
        "basis": (
            "Observation-only override is permitted only when the sole failed "
            "Stage179 gate is bootstrap lower-bound uncertainty. It does not "
            "authorize paper, demo, or live orders."
        ),
    }


def load_model(path: Path) -> Any:
    if path.suffix.lower() == ".pkl":
        with path.open("rb") as handle:
            return pickle.load(handle)
    if path.suffix.lower() == ".joblib":
        try:
            import joblib
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "The frozen model is joblib format but joblib is unavailable."
            ) from exc
        return joblib.load(path)
    raise RuntimeError(f"Unsupported frozen model format: {path}")


def find_model(root: Path, candidates: list[str]) -> Path:
    for value in candidates:
        path = resolve(root, value)
        if path.exists():
            return path
    raise FileNotFoundError(
        "Frozen Stage178 model not found. Checked: " + ", ".join(candidates)
    )


def load_complete_h1(db_path: Path, table: str, minimum_m5_bar_count: int) -> pd.DataFrame:
    if not db_path.exists():
        raise FileNotFoundError(db_path)
    with sqlite3.connect(db_path) as connection:
        columns = [
            row[1]
            for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
        ]
        required = {"timestamp", "open", "high", "low", "close", "volume"}
        missing = sorted(required - set(columns))
        if missing:
            raise RuntimeError(f"{table} missing columns: {missing}")
        where = ""
        parameters: tuple[Any, ...] = ()
        if "m5_bar_count" in columns:
            where = " WHERE m5_bar_count >= ?"
            parameters = (int(minimum_m5_bar_count),)
        frame = pd.read_sql_query(
            f"""
            SELECT timestamp, open, high, low, close, volume
            {", m5_bar_count" if "m5_bar_count" in columns else ""}
            FROM {table}
            {where}
            ORDER BY timestamp
            """,
            connection,
            params=parameters,
        )

    if frame.empty:
        raise RuntimeError("No complete aligned AMarkets H1 rows found")
    frame["timestamp"] = pd.to_numeric(frame["timestamp"], errors="coerce")
    for column in ["open", "high", "low", "close", "volume"]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.dropna(subset=["timestamp", "open", "high", "low", "close"])
    frame["timestamp"] = frame["timestamp"].astype("int64")
    frame = frame.sort_values("timestamp").drop_duplicates("timestamp", keep="last")
    frame["dt"] = pd.to_datetime(frame["timestamp"], unit="ms", utc=True)

    if frame["timestamp"].duplicated().any() or not frame["timestamp"].is_monotonic_increasing:
        raise RuntimeError("Aligned H1 timestamps are invalid")
    invariant = (
        (frame["high"] >= frame[["open", "close", "low"]].max(axis=1))
        & (frame["low"] <= frame[["open", "close", "high"]].min(axis=1))
    )
    if not bool(invariant.all()):
        raise RuntimeError("Aligned H1 OHLC invariant failed")
    return frame.reset_index(drop=True)


def model_contract_check(
    stage178: dict[str, Any],
    stage179: dict[str, Any],
    contract: dict[str, Any],
) -> dict[str, Any]:
    selected = stage178["selected_candidate"]
    checks = {
        "stage": str(contract.get("stage")) == "178",
        "candidate": contract.get("candidate") == selected.get("candidate"),
        "model": contract.get("model") == selected.get("model"),
        "target": contract.get("target") == selected.get("target"),
        "horizon": int(contract.get("horizon_hours", -1))
        == int(selected.get("horizon_hours", -2)),
        "threshold": 0.5 < float(contract.get("probability_threshold", 0.0)) < 1.0,
        "features_present": len(contract.get("feature_columns", [])) > 0,
        "selection_no_holdout": not bool(
            contract.get("selection_used_amarkets_holdout", True)
        ),
        "execution_forbidden": not bool(contract.get("execution_allowed", True)),
        "stage179_candidate": stage179["stage178_selected"]["candidate"]
        == contract.get("candidate"),
    }
    return {"checks": checks, "pass": all(checks.values())}


def probability_to_direction(probability: float, threshold: float) -> int:
    if probability >= threshold:
        return 1
    if probability <= 1.0 - threshold:
        return -1
    return 0


def init_ledger(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS observations (
                signal_timestamp INTEGER PRIMARY KEY,
                signal_dt TEXT NOT NULL,
                probability_up REAL NOT NULL,
                direction INTEGER NOT NULL,
                observation_status TEXT NOT NULL,
                created_utc TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS signals (
                signal_timestamp INTEGER PRIMARY KEY,
                signal_dt TEXT NOT NULL,
                direction INTEGER NOT NULL,
                probability_up REAL NOT NULL,
                entry_open REAL,
                exit_close REAL,
                gross_bps REAL,
                net_bps REAL,
                severe_net_bps REAL,
                resolution_status TEXT NOT NULL,
                created_utc TEXT NOT NULL,
                resolved_utc TEXT
            );
            """
        )


def write_metadata(path: Path, values: dict[str, Any]) -> None:
    with sqlite3.connect(path) as connection:
        for key, value in values.items():
            connection.execute(
                "INSERT OR REPLACE INTO metadata(key, value) VALUES (?, ?)",
                (str(key), json.dumps(value, sort_keys=True, default=str)),
            )
        connection.commit()


def latest_processed_timestamp(path: Path) -> int | None:
    with sqlite3.connect(path) as connection:
        row = connection.execute(
            "SELECT MAX(signal_timestamp) FROM observations"
        ).fetchone()
    return None if row is None or row[0] is None else int(row[0])


def latest_signal_timestamp(path: Path) -> int | None:
    with sqlite3.connect(path) as connection:
        row = connection.execute(
            "SELECT MAX(signal_timestamp) FROM signals"
        ).fetchone()
    return None if row is None or row[0] is None else int(row[0])


def insert_observation(
    path: Path,
    timestamp: int,
    probability: float,
    direction: int,
    status: str,
) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            INSERT OR IGNORE INTO observations
            (signal_timestamp, signal_dt, probability_up, direction,
             observation_status, created_utc)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                int(timestamp),
                pd.to_datetime(timestamp, unit="ms", utc=True).isoformat(),
                float(probability),
                int(direction),
                status,
                now_utc(),
            ),
        )
        connection.commit()


def insert_signal(
    path: Path,
    timestamp: int,
    probability: float,
    direction: int,
) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            INSERT OR IGNORE INTO signals
            (signal_timestamp, signal_dt, direction, probability_up,
             resolution_status, created_utc)
            VALUES (?, ?, ?, ?, 'PENDING', ?)
            """,
            (
                int(timestamp),
                pd.to_datetime(timestamp, unit="ms", utc=True).isoformat(),
                int(direction),
                float(probability),
                now_utc(),
            ),
        )
        connection.commit()


def resolve_pending_signals(
    ledger: Path,
    bars: pd.DataFrame,
    horizon_bars: int,
    normal_cost_bps: float,
    severe_cost_bps: float,
) -> int:
    position = {int(ts): i for i, ts in enumerate(bars["timestamp"].tolist())}
    with sqlite3.connect(ledger) as connection:
        pending = connection.execute(
            """
            SELECT signal_timestamp, direction
            FROM signals
            WHERE resolution_status = 'PENDING'
            ORDER BY signal_timestamp
            """
        ).fetchall()
        resolved = 0
        for signal_timestamp, direction in pending:
            index = position.get(int(signal_timestamp))
            if index is None:
                continue
            entry_index = index + 1
            exit_index = index + int(horizon_bars)
            if exit_index >= len(bars):
                continue
            entry_open = float(bars.iloc[entry_index]["open"])
            exit_close = float(bars.iloc[exit_index]["close"])
            gross = int(direction) * (exit_close / entry_open - 1.0) * 10_000.0
            connection.execute(
                """
                UPDATE signals
                SET entry_open = ?, exit_close = ?, gross_bps = ?,
                    net_bps = ?, severe_net_bps = ?,
                    resolution_status = 'RESOLVED', resolved_utc = ?
                WHERE signal_timestamp = ?
                """,
                (
                    entry_open,
                    exit_close,
                    gross,
                    gross - float(normal_cost_bps),
                    gross - float(severe_cost_bps),
                    now_utc(),
                    int(signal_timestamp),
                ),
            )
            resolved += 1
        connection.commit()
    return resolved


def ledger_frames(path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    with sqlite3.connect(path) as connection:
        observations = pd.read_sql_query(
            "SELECT * FROM observations ORDER BY signal_timestamp", connection
        )
        signals = pd.read_sql_query(
            "SELECT * FROM signals ORDER BY signal_timestamp", connection
        )
    return observations, signals


def should_refresh_alignment(
    aligned_db: Path,
    time_contract: dict[str, Any],
) -> tuple[bool, dict[str, Any]]:
    source_paths = []
    for key in ["source_amarkets_h1", "source_amarkets_m5"]:
        value = time_contract.get(key)
        if value:
            path = Path(value).expanduser()
            if path.exists():
                source_paths.append(path)
    if not aligned_db.exists():
        return True, {"reason": "aligned_db_missing", "sources": [str(p) for p in source_paths]}
    db_mtime = aligned_db.stat().st_mtime
    newer = [path for path in source_paths if path.stat().st_mtime > db_mtime]
    return bool(newer), {
        "reason": "raw_source_newer" if newer else "aligned_db_current",
        "aligned_db_mtime": db_mtime,
        "newer_sources": [str(p) for p in newer],
        "sources": [str(p) for p in source_paths],
    }


def refresh_alignment(root: Path, script_path: Path) -> dict[str, Any]:
    result = subprocess.run(
        [sys.executable, str(script_path)],
        cwd=root,
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "Frozen operational alignment refresh failed.\nSTDOUT:\n"
            + result.stdout[-4000:]
            + "\nSTDERR:\n"
            + result.stderr[-4000:]
        )
    return {
        "status": "REFRESHED_FROZEN_CONTRACT",
        "returncode": result.returncode,
        "stdout_tail": result.stdout[-1000:],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        default="configs/stage180_frozen_model_shadow.json",
    )
    parser.add_argument(
        "--skip-alignment-refresh",
        action="store_true",
        help="Use the current Stage177C aligned database without checking raw source mtimes.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = repo_root()
    config_path = resolve(root, args.config)
    config = read_json(config_path)

    out = resolve(root, config["output_dir"])
    out.mkdir(parents=True, exist_ok=True)

    stage178_path = resolve(root, config["stage178_summary"])
    stage179_path = resolve(root, config["stage179_summary"])
    contract_path = resolve(root, config["model_contract"])
    stage178_app_path = resolve(root, config["stage178_app"])
    time_contract_path = resolve(root, config["stage177c_time_contract"])
    aligned_db = resolve(root, config["aligned_amarkets_db"])
    ledger = resolve(root, config["ledger_db"])

    stage178 = read_json(stage178_path)
    stage179 = read_json(stage179_path)
    contract = read_json(contract_path)
    time_contract = read_alignment_contract_from_db(aligned_db, time_contract_path)

    authorization = authorization_check(stage178, stage179)
    contract_audit = model_contract_check(stage178, stage179, contract)
    if not authorization["pass"] or not contract_audit["pass"]:
        payload = {
            "stage": "180",
            "decision": DECISION_BLOCK,
            "authorization": authorization,
            "model_contract_audit": contract_audit,
            "execution_allowed": False,
            "broker_order_allowed": False,
        }
        write_json(out / "stage180_summary.json", payload)
        print(json.dumps(payload, indent=2))
        return 2

    refresh_info: dict[str, Any] = {"status": "SKIPPED_BY_FLAG"}
    if not args.skip_alignment_refresh:
        needs_refresh, refresh_diag = should_refresh_alignment(aligned_db, time_contract)
        refresh_info = {"status": "NOT_REQUIRED", **refresh_diag}
        if needs_refresh:
            frozen_refresh_script = resolve(
                root, config["frozen_alignment_refresh_script"]
            )
            refresh_info = {
                **refresh_diag,
                **refresh_alignment(root, frozen_refresh_script),
            }

    model_path = find_model(root, config["model_candidates"])
    model = load_model(model_path)
    stage178_module = import_module(stage178_app_path, "stage178_runtime_for_stage180")

    bars = load_complete_h1(
        aligned_db,
        config["aligned_h1_table"],
        int(config["minimum_m5_bar_count"]),
    )
    features, generated_columns = stage178_module.build_features(bars)
    required_features = list(contract["feature_columns"])
    missing_features = sorted(set(required_features) - set(generated_columns))
    if missing_features:
        raise RuntimeError(f"Frozen feature contract missing at runtime: {missing_features}")

    activation_text = contract.get("generated_utc") or stage178.get("generated_utc")
    activation_ms = int(pd.Timestamp(activation_text).timestamp() * 1000)
    init_ledger(ledger)

    write_metadata(
        ledger,
        {
            "stage": "180",
            "activated_utc": activation_text,
            "candidate": contract["candidate"],
            "model": contract["model"],
            "target": contract["target"],
            "horizon_bars": int(contract["horizon_hours"]),
            "probability_threshold": float(contract["probability_threshold"]),
            "normal_cost_bps": float(contract["round_trip_cost_bps"]),
            "severe_cost_bps": float(contract["severe_round_trip_cost_bps"]),
            "model_sha256": sha256_file(model_path),
            "contract_sha256": sha256_file(contract_path),
            "broker_order_allowed": False,
            "paper_order_allowed": False,
            "demo_order_allowed": False,
            "live_order_allowed": False,
        },
    )

    last_processed = latest_processed_timestamp(ledger)
    lower_bound = activation_ms if last_processed is None else max(activation_ms, last_processed)
    candidates = features[features["timestamp"] > lower_bound].copy()
    candidates = candidates.dropna(subset=required_features).sort_values("timestamp")

    threshold = float(contract["probability_threshold"])
    last_signal = latest_signal_timestamp(ledger)
    next_allowed = -2**63 if last_signal is None else int(last_signal) + int(
        contract["horizon_hours"]
    ) * MS_HOUR

    new_observations = 0
    new_signals = 0
    if not candidates.empty:
        probabilities = model.predict_proba(candidates[required_features])[:, 1]
        for (_, row), probability in zip(candidates.iterrows(), probabilities):
            timestamp = int(row["timestamp"])
            direction = probability_to_direction(float(probability), threshold)
            if direction == 0:
                status = "NO_SIGNAL"
            elif timestamp < next_allowed:
                status = "BLOCKED_NONOVERLAP"
            else:
                status = "SHADOW_SIGNAL"
                insert_signal(ledger, timestamp, float(probability), direction)
                next_allowed = timestamp + int(contract["horizon_hours"]) * MS_HOUR
                new_signals += 1
            insert_observation(
                ledger,
                timestamp,
                float(probability),
                direction,
                status,
            )
            new_observations += 1

    resolved_now = resolve_pending_signals(
        ledger,
        bars,
        int(contract["horizon_hours"]),
        float(contract["round_trip_cost_bps"]),
        float(contract["severe_round_trip_cost_bps"]),
    )

    observations, signals = ledger_frames(ledger)
    observations.to_csv(out / "stage180_observations.csv", index=False)
    signals.to_csv(out / "stage180_signals.csv", index=False)
    resolved = signals[signals["resolution_status"] == "RESOLVED"].copy()
    resolved.to_csv(out / "stage180_resolved_signals.csv", index=False)

    if len(bars) == 0 or int(bars.iloc[-1]["timestamp"]) <= activation_ms:
        decision = DECISION_WAIT
    else:
        decision = DECISION_ACTIVE

    latest_observation = (
        observations.iloc[-1].to_dict() if len(observations) else None
    )
    latest_signal = signals.iloc[-1].to_dict() if len(signals) else None
    payload = {
        "stage": "180",
        "decision": decision,
        "generated_utc": now_utc(),
        "execution_allowed": False,
        "broker_order_allowed": False,
        "paper_order_allowed": False,
        "demo_order_allowed": False,
        "live_order_allowed": False,
        "shadow_observation_allowed": True,
        "research_continues_in_parallel": True,
        "authorization": authorization,
        "model_contract_audit": contract_audit,
        "refresh": refresh_info,
        "model_path": str(model_path),
        "model_sha256": sha256_file(model_path),
        "contract_path": str(contract_path),
        "contract_sha256": sha256_file(contract_path),
        "aligned_db": str(aligned_db),
        "aligned_complete_h1_rows": int(len(bars)),
        "aligned_last_complete_bar_utc": bars.iloc[-1]["dt"].isoformat(),
        "activation_utc": activation_text,
        "new_observations": int(new_observations),
        "new_signals": int(new_signals),
        "signals_resolved_this_run": int(resolved_now),
        "observations_total": int(len(observations)),
        "signals_total": int(len(signals)),
        "resolved_signals_total": int(len(resolved)),
        "latest_observation": latest_observation,
        "latest_signal": latest_signal,
        "stage179_uncertainty": {
            "candidate_mean_bps": stage179["candidate_metrics"]["mean_bps"],
            "candidate_profit_factor": stage179["candidate_metrics"]["profit_factor"],
            "bootstrap_p10_bps": stage179["bootstrap_candidate"]["p10"],
            "bootstrap_probability_mean_le_zero": stage179["bootstrap_candidate"][
                "probability_mean_le_zero"
            ],
        },
    }
    write_json(out / "stage180_summary.json", payload)
    write_json(out / "stage180_latest_observation.json", latest_observation or {})

    decision_md = "\n".join(
        [
            "# Stage180 Frozen-Model Parallel Shadow",
            "",
            f"Decision: `{decision}`",
            "",
            f"- Candidate: `{contract['candidate']}`",
            f"- Activation: `{activation_text}`",
            f"- Complete aligned H1 rows: `{len(bars)}`",
            f"- New observations: `{new_observations}`",
            f"- New shadow signals: `{new_signals}`",
            f"- Resolved this run: `{resolved_now}`",
            f"- Total shadow signals: `{len(signals)}`",
            "",
            "## Boundary",
            "",
            "- Frozen model only; no retraining or threshold tuning.",
            "- No paper, demo, or live broker order is authorized.",
            "- Shadow observation runs in parallel and does not block research.",
            "",
        ]
    )
    (out / "stage180_decision.md").write_text(decision_md, encoding="utf-8")

    print(
        json.dumps(
            {
                "decision": decision,
                "new_observations": new_observations,
                "new_signals": new_signals,
                "resolved_this_run": resolved_now,
                "signals_total": len(signals),
                "latest_complete_bar": bars.iloc[-1]["dt"].isoformat(),
                "output_dir": str(out),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
