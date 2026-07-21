#!/usr/bin/env python3
"""Stage179 — selected-candidate commercial audit and shadow-paper contract.

This stage does not place orders. It audits the exact Stage178 selected
holdout trade ledger, compares it with always-long on the same selected
timestamps, performs cost stress and moving-block bootstrap, and emits a
shadow-paper contract only when all frozen gates pass.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd


DECISION_PASS = "AUTHORIZE_PARALLEL_CONTROLLED_SHADOW_PAPER"
DECISION_REVIEW = "RESEARCH_SURVIVOR_NEEDS_ONE_TARGETED_DIAGNOSTIC"
DECISION_KILL = "KILL_STAGE178_SELECTED_CANDIDATE"


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def profit_factor(values: Iterable[float]) -> float | None:
    arr = np.asarray(list(values), dtype=float)
    gains = float(arr[arr > 0].sum())
    losses = float(-arr[arr < 0].sum())
    if losses == 0.0:
        return None if gains == 0.0 else 999.0
    return gains / losses


def max_drawdown(values: Iterable[float]) -> float:
    arr = np.asarray(list(values), dtype=float)
    if arr.size == 0:
        return 0.0
    equity = np.cumsum(arr)
    peaks = np.maximum.accumulate(np.r_[0.0, equity])
    return float(np.max(peaks[1:] - equity))


def metrics(values: Iterable[float]) -> dict[str, Any]:
    arr = np.asarray(list(values), dtype=float)
    if arr.size == 0:
        return {
            "trades": 0,
            "mean_bps": None,
            "median_bps": None,
            "win_rate": None,
            "profit_factor": None,
            "max_drawdown_bps": None,
            "total_bps": None,
        }
    return {
        "trades": int(arr.size),
        "mean_bps": float(np.mean(arr)),
        "median_bps": float(np.median(arr)),
        "win_rate": float(np.mean(arr > 0.0)),
        "profit_factor": profit_factor(arr),
        "max_drawdown_bps": max_drawdown(arr),
        "total_bps": float(np.sum(arr)),
    }


def load_trades(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    required = {
        "timestamp",
        "dt",
        "direction",
        "gross_bps",
        "net_bps",
        "severe_net_bps",
        "probability_up",
    }
    missing = sorted(required - set(frame.columns))
    if missing:
        raise RuntimeError(f"Stage178 trade ledger missing columns: {missing}")

    for column in [
        "timestamp",
        "direction",
        "gross_bps",
        "net_bps",
        "severe_net_bps",
        "probability_up",
    ]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame["dt"] = pd.to_datetime(frame["dt"], utc=True, errors="coerce")

    if frame[list(required)].isna().any().any():
        raise RuntimeError("Stage178 trade ledger contains null/invalid required values")
    if not set(frame["direction"].astype(int).unique()).issubset({-1, 1}):
        raise RuntimeError("Trade directions must be only -1 or +1")
    if frame["timestamp"].duplicated().any():
        raise RuntimeError("Duplicate trade timestamps found")
    frame = frame.sort_values("timestamp").reset_index(drop=True)
    if not frame["timestamp"].is_monotonic_increasing:
        raise RuntimeError("Trade timestamps are not monotonic")
    return frame


def infer_costs(frame: pd.DataFrame) -> tuple[float, float]:
    normal = float(np.median(frame["gross_bps"] - frame["net_bps"]))
    severe = float(np.median(frame["gross_bps"] - frame["severe_net_bps"]))
    if not np.allclose(frame["gross_bps"] - frame["net_bps"], normal, atol=1e-8):
        raise RuntimeError("Normal cost is not constant in Stage178 ledger")
    if not np.allclose(
        frame["gross_bps"] - frame["severe_net_bps"], severe, atol=1e-8
    ):
        raise RuntimeError("Severe cost is not constant in Stage178 ledger")
    return normal, severe


def parity_audit(
    frame: pd.DataFrame,
    stage178_summary: dict[str, Any],
    tolerance: float,
) -> dict[str, Any]:
    expected = stage178_summary["selected_holdout_metrics"]
    actual = metrics(frame["net_bps"])
    checks = {
        "trade_count": actual["trades"] == int(expected["trades"]),
        "mean_net_bps": abs(actual["mean_bps"] - float(expected["mean_net_bps"]))
        <= tolerance,
        "profit_factor": abs(
            float(actual["profit_factor"]) - float(expected["profit_factor"])
        )
        <= tolerance,
        "max_drawdown_bps": abs(
            actual["max_drawdown_bps"] - float(expected["max_drawdown_bps"])
        )
        <= tolerance,
        "first_trade": frame["dt"].iloc[0].isoformat()
        == pd.Timestamp(expected["first_trade_utc"]).isoformat(),
        "last_trade": frame["dt"].iloc[-1].isoformat()
        == pd.Timestamp(expected["last_trade_utc"]).isoformat(),
    }
    return {"checks": checks, "pass": all(checks.values()), "actual": actual}


def moving_block_means(
    values: np.ndarray,
    *,
    reps: int,
    block_length: int,
    seed: int,
) -> np.ndarray:
    values = np.asarray(values, dtype=float)
    n = len(values)
    if n == 0:
        return np.array([], dtype=float)
    block_length = max(1, min(block_length, n))
    blocks_needed = math.ceil(n / block_length)
    starts_max = n - block_length
    rng = np.random.default_rng(seed)
    out = np.empty(reps, dtype=float)
    for i in range(reps):
        starts = rng.integers(0, starts_max + 1, size=blocks_needed)
        sample = np.concatenate(
            [values[start : start + block_length] for start in starts]
        )[:n]
        out[i] = float(np.mean(sample))
    return out


def bootstrap_summary(
    values: np.ndarray,
    *,
    reps: int,
    block_length: int,
    seed: int,
) -> dict[str, Any]:
    boot = moving_block_means(
        values, reps=reps, block_length=block_length, seed=seed
    )
    if boot.size == 0:
        return {
            "reps": reps,
            "block_length": block_length,
            "mean": None,
            "p10": None,
            "p50": None,
            "p90": None,
            "probability_mean_le_zero": None,
        }
    return {
        "reps": int(reps),
        "block_length": int(block_length),
        "mean": float(np.mean(values)),
        "p10": float(np.quantile(boot, 0.10)),
        "p50": float(np.quantile(boot, 0.50)),
        "p90": float(np.quantile(boot, 0.90)),
        "probability_mean_le_zero": float(np.mean(boot <= 0.0)),
    }


def side_metrics(frame: pd.DataFrame, normal_cost: float) -> pd.DataFrame:
    underlying = frame["gross_bps"] / frame["direction"]
    records: list[dict[str, Any]] = []
    for direction, label in [(1, "LONG"), (-1, "SHORT")]:
        mask = frame["direction"].astype(int) == direction
        vals = direction * underlying[mask].to_numpy(float) - normal_cost
        records.append(
            {
                "side": label,
                **metrics(vals),
                "share": float(mask.mean()),
            }
        )
    return pd.DataFrame(records)


def session_name(hour: int) -> str:
    if 7 <= hour < 13:
        return "LONDON"
    if 13 <= hour < 21:
        return "NEW_YORK"
    return "OTHER"


def concentration(frame: pd.DataFrame) -> dict[str, Any]:
    years = frame["dt"].dt.year.value_counts(normalize=True)
    months = frame["dt"].dt.strftime("%Y-%m").value_counts(normalize=True)
    sessions = frame["dt"].dt.hour.map(session_name).value_counts(normalize=True)
    return {
        "max_year_share": float(years.iloc[0]),
        "max_month_share": float(months.iloc[0]),
        "max_session_share": float(sessions.iloc[0]),
        "year_counts": {
            str(k): int(v) for k, v in frame["dt"].dt.year.value_counts().items()
        },
        "month_counts": {
            str(k): int(v)
            for k, v in frame["dt"].dt.strftime("%Y-%m").value_counts().items()
        },
        "session_counts": {
            str(k): int(v)
            for k, v in frame["dt"].dt.hour.map(session_name).value_counts().items()
        },
    }


def cost_stress(frame: pd.DataFrame, costs: list[float]) -> pd.DataFrame:
    records = []
    gross = frame["gross_bps"].to_numpy(float)
    for cost in costs:
        records.append({"cost_bps": cost, **metrics(gross - cost)})
    return pd.DataFrame(records)


def always_long_matched(frame: pd.DataFrame, cost_bps: float) -> np.ndarray:
    underlying = frame["gross_bps"].to_numpy(float) / frame["direction"].to_numpy(float)
    return underlying - cost_bps


def markdown(summary: dict[str, Any]) -> str:
    failed = [k for k, v in summary["gates"].items() if not v]
    selected = summary["stage178_selected"]
    audit = summary["candidate_metrics"]
    return "\n".join(
        [
            "# Stage179 Selected Candidate Commercial Audit",
            "",
            f"Decision: `{summary['decision']}`",
            "",
            "## Candidate",
            "",
            f"- Candidate: `{selected['candidate']}`",
            f"- Target: `{selected['target']}`",
            f"- Trades: `{audit['trades']}`",
            f"- Mean net: `{audit['mean_bps']}` bps",
            f"- Profit factor: `{audit['profit_factor']}`",
            f"- Maximum drawdown: `{audit['max_drawdown_bps']}` bps",
            "",
            "## Drift and uncertainty controls",
            "",
            f"- Same-timestamp always-long mean: `{summary['matched_always_long']['mean_bps']}` bps",
            f"- Candidate minus same-timestamp always-long mean: `{summary['paired_alpha_bps']}` bps",
            f"- Full-holdout always-long mean: `{summary['full_holdout_always_long_mean_bps']}` bps",
            f"- Candidate bootstrap p10: `{summary['bootstrap_candidate']['p10']}` bps",
            f"- Paired-alpha bootstrap p10: `{summary['bootstrap_paired_alpha']['p10']}` bps",
            "",
            "## Gates",
            "",
            f"- Failed gates: `{failed}`",
            "",
            "## Operational boundary",
            "",
            "No broker order, demo order, or live order is authorized.",
            "A PASS authorizes only a parallel signal/shadow ledger using the frozen",
            "Stage178 model contract while research and governance continue.",
            "",
        ]
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        default="configs/stage179_selected_candidate_commercial_audit.json",
    )
    parser.add_argument("--stage178-dir")
    parser.add_argument("--out")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = repo_root()
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = root / config_path
    config = read_json(config_path)

    stage178_dir = (
        Path(args.stage178_dir)
        if args.stage178_dir
        else root / config["stage178_report_dir"]
    )
    if not stage178_dir.is_absolute():
        stage178_dir = root / stage178_dir
    out = Path(args.out) if args.out else root / config["output_dir"]
    if not out.is_absolute():
        out = root / out
    out.mkdir(parents=True, exist_ok=True)

    summary_path = stage178_dir / "stage178_summary.json"
    trades_path = stage178_dir / "stage178_selected_holdout_trades.csv"
    baselines_path = stage178_dir / "stage178_holdout_baselines.csv"
    for path in [summary_path, trades_path, baselines_path]:
        if not path.exists():
            raise FileNotFoundError(path)

    stage178_summary = read_json(summary_path)
    if stage178_summary.get("decision") != "PROMOTE_TO_CONTROLLED_PAPER_DESIGN":
        raise RuntimeError("Stage178 did not authorize controlled paper design")

    trades = load_trades(trades_path)
    normal_cost, severe_cost = infer_costs(trades)
    parity = parity_audit(
        trades,
        stage178_summary,
        float(config["parity_tolerance"]),
    )

    candidate_metrics = metrics(trades["net_bps"])
    matched_long_values = always_long_matched(trades, normal_cost)
    matched_long_metrics = metrics(matched_long_values)
    paired_alpha = trades["net_bps"].to_numpy(float) - matched_long_values

    baselines = pd.read_csv(baselines_path)
    always_rows = baselines[baselines["baseline"] == "always_long"]
    if len(always_rows) != 1:
        raise RuntimeError("Expected exactly one full-holdout always_long baseline")
    full_long_mean = float(always_rows.iloc[0]["mean_net_bps"])

    costs = [float(value) for value in config["cost_stress_bps"]]
    stress = cost_stress(trades, costs)
    stress.to_csv(out / "stage179_cost_stress.csv", index=False)

    sides = side_metrics(trades, normal_cost)
    sides.to_csv(out / "stage179_direction_metrics.csv", index=False)

    candidate_bootstrap = bootstrap_summary(
        trades["net_bps"].to_numpy(float),
        reps=int(config["bootstrap_reps"]),
        block_length=int(config["bootstrap_block_length"]),
        seed=int(config["random_seed"]),
    )
    paired_bootstrap = bootstrap_summary(
        paired_alpha,
        reps=int(config["bootstrap_reps"]),
        block_length=int(config["bootstrap_block_length"]),
        seed=int(config["random_seed"]) + 1,
    )

    conc = concentration(trades)
    severe_row = stress.loc[
        np.isclose(stress["cost_bps"], float(config["required_stress_cost_bps"]))
    ]
    if len(severe_row) != 1:
        raise RuntimeError("Required stress cost missing from cost grid")
    severe_mean = float(severe_row.iloc[0]["mean_bps"])

    gates_cfg = config["gates"]
    gates = {
        "stage178_parity": bool(parity["pass"]),
        "minimum_trades": candidate_metrics["trades"]
        >= int(gates_cfg["minimum_trades"]),
        "minimum_profit_factor": candidate_metrics["profit_factor"] is not None
        and candidate_metrics["profit_factor"]
        >= float(gates_cfg["minimum_profit_factor"]),
        "stress_mean_positive": severe_mean
        >= float(gates_cfg["minimum_stress_mean_bps"]),
        "candidate_bootstrap_p10_positive": candidate_bootstrap["p10"] is not None
        and candidate_bootstrap["p10"]
        >= float(gates_cfg["minimum_candidate_bootstrap_p10_bps"]),
        "beats_full_holdout_long": candidate_metrics["mean_bps"]
        >= full_long_mean + float(gates_cfg["minimum_margin_over_full_long_bps"]),
        "paired_alpha_nonnegative": float(np.mean(paired_alpha))
        >= float(gates_cfg["minimum_paired_alpha_mean_bps"]),
        "month_concentration": conc["max_month_share"]
        <= float(gates_cfg["maximum_month_share"]),
        "drawdown_cap": candidate_metrics["max_drawdown_bps"]
        <= float(gates_cfg["maximum_drawdown_bps"]),
    }

    if all(gates.values()):
        decision = DECISION_PASS
    elif (
        parity["pass"]
        and candidate_metrics["mean_bps"] > 0
        and severe_mean > 0
    ):
        decision = DECISION_REVIEW
    else:
        decision = DECISION_KILL

    selected = stage178_summary["selected_candidate"]
    payload = {
        "stage": "179",
        "decision": decision,
        "execution_allowed": False,
        "broker_order_allowed": False,
        "shadow_signal_ledger_allowed": decision == DECISION_PASS,
        "stage178_selected": selected,
        "normal_cost_bps": normal_cost,
        "severe_cost_bps": severe_cost,
        "candidate_metrics": candidate_metrics,
        "matched_always_long": matched_long_metrics,
        "paired_alpha_bps": float(np.mean(paired_alpha)),
        "full_holdout_always_long_mean_bps": full_long_mean,
        "bootstrap_candidate": candidate_bootstrap,
        "bootstrap_paired_alpha": paired_bootstrap,
        "concentration": conc,
        "gates": gates,
        "parity": parity,
    }
    write_json(out / "stage179_summary.json", payload)
    write_json(
        out / "stage179_bootstrap.json",
        {
            "candidate": candidate_bootstrap,
            "paired_alpha": paired_bootstrap,
        },
    )
    (out / "stage179_decision.md").write_text(
        markdown(payload), encoding="utf-8"
    )

    contract = {
        "stage": "179",
        "status": "ACTIVE" if decision == DECISION_PASS else "NOT_AUTHORIZED",
        "candidate": selected["candidate"],
        "model": selected["model"],
        "target": selected["target"],
        "signal_timeframe": "H1",
        "entry_contract": "next_H1_open_after_signal",
        "maximum_concurrent_positions": 1,
        "holding_contract": "fixed_24h_directional_target",
        "probability_threshold": 0.60,
        "normal_cost_bps": normal_cost,
        "severe_cost_bps": severe_cost,
        "broker_order_allowed": False,
        "demo_order_allowed": False,
        "live_order_allowed": False,
        "purpose": "parallel shadow signal ledger; does not block ongoing research",
        "minimum_new_shadow_signals_before_execution_review": 20,
        "maximum_calendar_wait_days_for_review": 90,
    }
    write_json(out / "stage179_shadow_paper_contract.json", contract)

    # Preserve a reconciled audit ledger for future governance.
    audit_trades = trades.copy()
    audit_trades["underlying_bps"] = (
        audit_trades["gross_bps"] / audit_trades["direction"]
    )
    audit_trades["matched_always_long_net_bps"] = matched_long_values
    audit_trades["paired_alpha_bps"] = paired_alpha
    audit_trades.to_csv(out / "stage179_reconciled_holdout_trades.csv", index=False)

    print(json.dumps({
        "decision": decision,
        "trades": candidate_metrics["trades"],
        "mean_net_bps": candidate_metrics["mean_bps"],
        "profit_factor": candidate_metrics["profit_factor"],
        "stress_mean_bps": severe_mean,
        "bootstrap_p10_bps": candidate_bootstrap["p10"],
        "failed_gates": [k for k, v in gates.items() if not v],
        "output_dir": str(out),
    }, indent=2))
    return 0 if decision != DECISION_KILL else 2


if __name__ == "__main__":
    raise SystemExit(main())
