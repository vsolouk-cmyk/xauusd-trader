from __future__ import annotations

import argparse
import ast
import hashlib
import json
import math
import shutil
import sys
import traceback
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

PROGRAM = "XAUUSD_PIPELINE_CALIBRATION_POSITIVE_CONTROL_AUDIT_V1_REFERENCE_LOCKED"
DEFAULT_CONFIG = Path("configs/xauusd_pipeline_calibration.json")
DEFAULT_TARGETS = Path("reports/xauusd_cross_asset_intraday_panel/cross_asset_intraday_targets.csv")
REPORT_DIR = Path("reports/xauusd_pipeline_calibration")
COLLECT_NAME = "XAUUSD_PIPELINE_CALIBRATION_RESULTS.zip"
CSV_CHUNK_ROWS = 10000

FORBIDDEN_EXECUTION_TOKENS = (
    "order_send(", "mt5.order_send", "trade.buy(", "trade.sell(",
    "positions_get(", "orders_send(", "websocket", "requests.post(",
)


class CalibrationError(RuntimeError):
    pass


@dataclass(frozen=True)
class GateResult:
    checks: dict[str, bool]
    statistical_pass: bool
    commercial_pass: bool


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")


def load_config(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("program") != PROGRAM:
        raise CalibrationError(f"unexpected program in config: {payload.get('program')!r}")
    for key in ("reference_start_utc", "reference_end_utc", "reference_gates", "synthetic", "empirical_tsmom"):
        if key not in payload:
            raise CalibrationError(f"missing config key: {key}")
    if payload.get("paper_order_allowed") or payload.get("demo_order_allowed") or payload.get("live_order_allowed"):
        raise CalibrationError("order permissions must remain false")
    return payload


def resolve_targets(root: Path, explicit: str | None) -> Path:
    if explicit:
        p = Path(explicit).expanduser()
        if not p.is_absolute():
            p = root / p
        return p
    direct = root / DEFAULT_TARGETS
    if direct.is_file():
        return direct
    archive = root / "reports/_archive"
    if archive.is_dir():
        candidates = sorted(archive.glob("xauusd_cross_asset_intraday_panel*/cross_asset_intraday_targets.csv"))
        if candidates:
            return candidates[-1]
    return direct


def read_header(path: Path) -> list[str]:
    try:
        cols = list(pd.read_csv(path, nrows=0).columns)
    except Exception as exc:
        raise CalibrationError(f"cannot read targets header: {type(exc).__name__}: {exc}") from exc
    if len(cols) != len(set(cols)):
        raise CalibrationError("duplicate column names in targets input")
    return cols


def read_reference_targets(path: Path, config: dict[str, Any]) -> tuple[pd.DataFrame, dict[str, Any]]:
    required = ["decision_time_utc", "entry_open", "forward_return_4h_bps"]
    header = read_header(path)
    missing = [c for c in required if c not in header]
    if missing:
        raise CalibrationError(f"targets missing required columns: {missing}")

    start = pd.Timestamp(config["reference_start_utc"])
    end = pd.Timestamp(config["reference_end_utc"])
    frames: list[pd.DataFrame] = []
    rows_parsed = 0
    rows_reference = 0
    crossed_reference_end = False

    try:
        with pd.read_csv(
            path,
            usecols=required,
            chunksize=CSV_CHUNK_ROWS,
            dtype={"decision_time_utc": "string", "entry_open": "string", "forward_return_4h_bps": "string"},
            low_memory=False,
        ) as reader:
            for chunk in reader:
                rows_parsed += len(chunk)
                ts = pd.to_datetime(chunk["decision_time_utc"], utc=True, errors="coerce")
                valid = ts.notna()
                if not valid.any():
                    continue
                chunk = chunk.loc[valid].copy()
                chunk["decision_time_utc"] = ts.loc[valid]
                mask = (chunk["decision_time_utc"] >= start) & (chunk["decision_time_utc"] < end)
                if mask.any():
                    piece = chunk.loc[mask, required].copy()
                    piece["entry_open"] = pd.to_numeric(piece["entry_open"], errors="coerce")
                    piece["forward_return_4h_bps"] = pd.to_numeric(piece["forward_return_4h_bps"], errors="coerce")
                    frames.append(piece)
                    rows_reference += len(piece)
                if (chunk["decision_time_utc"] >= end).any():
                    crossed_reference_end = True
                    break
    except IndexError:
        # pandas 3 C-parser internal concatenation bugs are avoided above; this is a safe fallback.
        all_df = pd.read_csv(path, usecols=required, engine="python", dtype=str)
        ts = pd.to_datetime(all_df["decision_time_utc"], utc=True, errors="coerce")
        mask = ts.notna() & (ts >= start) & (ts < end)
        all_df = all_df.loc[mask, required].copy()
        all_df["decision_time_utc"] = ts.loc[mask]
        all_df["entry_open"] = pd.to_numeric(all_df["entry_open"], errors="coerce")
        all_df["forward_return_4h_bps"] = pd.to_numeric(all_df["forward_return_4h_bps"], errors="coerce")
        frames = [all_df]
        rows_reference = len(all_df)

    if not frames:
        raise CalibrationError("no reference rows loaded from targets")
    out = pd.concat(frames, ignore_index=True)
    out = out.drop_duplicates(subset=["decision_time_utc"], keep="last").sort_values("decision_time_utc").reset_index(drop=True)
    return out, {
        "targets_path": str(path),
        "targets_size_bytes": path.stat().st_size,
        "targets_sha256": sha256_file(path),
        "rows_parsed_until_stop": int(rows_parsed),
        "reference_rows_loaded": int(len(out)),
        "reference_end_crossed_in_parser_chunk": bool(crossed_reference_end),
        "diagnostic_rows_used": 0,
    }


def eligible_nonoverlap_opportunities(frame: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    f = frame.copy()
    f = f.loc[f["forward_return_4h_bps"].notna() & f["entry_open"].notna()].copy()
    f["hour_utc"] = f["decision_time_utc"].dt.hour
    f["weekday"] = f["decision_time_utc"].dt.weekday
    f = f.loc[
        f["hour_utc"].isin([int(x) for x in config["allowed_hours_utc"]])
        & f["weekday"].isin([int(x) for x in config["allowed_weekdays"]])
    ].sort_values("decision_time_utc")

    keep: list[int] = []
    last: pd.Timestamp | None = None
    for idx, ts in zip(f.index, f["decision_time_utc"]):
        if last is None or ts - last >= pd.Timedelta(hours=4):
            keep.append(idx)
            last = ts
    out = f.loc[keep].copy().reset_index(drop=True)
    out["year"] = out["decision_time_utc"].dt.year.astype(int)
    out["hour_utc"] = out["decision_time_utc"].dt.hour.astype(int)
    bucket_mean = out.groupby(["year", "hour_utc"])["forward_return_4h_bps"].transform("mean")
    out["centered_4h_bps"] = pd.to_numeric(out["forward_return_4h_bps"], errors="coerce") - bucket_mean
    return out


def profit_factor(values: Iterable[float]) -> float:
    arr = np.asarray(list(values), dtype="float64")
    arr = arr[np.isfinite(arr)]
    pos = arr[arr > 0].sum()
    neg = -arr[arr < 0].sum()
    if neg <= 0:
        return float("inf") if pos > 0 else 0.0
    return float(pos / neg)


def bootstrap_p10(values: np.ndarray, reps: int, block: int, rng: np.random.Generator) -> float:
    arr = np.asarray(values, dtype="float64")
    arr = arr[np.isfinite(arr)]
    n = len(arr)
    if n == 0:
        return float("nan")
    if n == 1:
        return float(arr[0])
    block = max(1, min(int(block), n))
    blocks_needed = int(math.ceil(n / block))
    starts = rng.integers(0, n, size=(int(reps), blocks_needed))
    offsets = np.arange(block, dtype=int)
    idx = (starts[:, :, None] + offsets[None, None, :]) % n
    idx = idx.reshape(int(reps), -1)[:, :n]
    means = arr[idx].mean(axis=1)
    return float(np.quantile(means, 0.10))


def fixed_period_years(config: dict[str, Any]) -> float:
    start = pd.Timestamp(config["reference_start_utc"])
    end = pd.Timestamp(config["reference_end_utc"])
    return max((end - start).total_seconds() / (365.2425 * 86400.0), 1e-9)


def metric_and_gates(
    timestamps: pd.DatetimeIndex,
    severe_values: np.ndarray,
    config: dict[str, Any],
    rng: np.random.Generator,
) -> tuple[dict[str, Any], GateResult]:
    vals = np.asarray(severe_values, dtype="float64")
    n = len(vals)
    syn = config["synthetic"]
    p10 = bootstrap_p10(vals, int(syn["bootstrap_reps"]), int(syn["bootstrap_block_trades"]), rng)
    remove_largest = float((vals.sum() - vals.max()) / (n - 1)) if n >= 2 else (float(vals[0]) if n == 1 else float("nan"))

    fold_means: list[float] = []
    for fold in config["reference_folds"]:
        start = pd.Timestamp(fold["start_utc"])
        end = pd.Timestamp(fold["end_utc"])
        mask = (timestamps >= start) & (timestamps < end)
        v = vals[np.asarray(mask)]
        fold_means.append(float(np.mean(v)) if len(v) else float("nan"))
    finite_folds = [x for x in fold_means if np.isfinite(x)]
    positive_folds = sum(x > 0 for x in finite_folds)
    worst_fold = min(finite_folds) if finite_folds else float("nan")

    annual_sums: list[float] = []
    years = np.asarray(timestamps.year)
    for year in sorted(set(int(y) for y in years)):
        annual_sums.append(float(vals[years == year].sum()))
    positive_year_sums = [x for x in annual_sums if x > 0]
    year_concentration = (
        float(max(positive_year_sums) / sum(positive_year_sums))
        if positive_year_sums and sum(positive_year_sums) > 0 else float("nan")
    )

    risk_ratio = float(config["locked_notional_to_equity"])
    equity = 1.0
    for v in vals:
        equity *= max(1e-12, 1.0 + risk_ratio * float(v) / 10000.0)
    cagr = float(equity ** (1.0 / fixed_period_years(config)) - 1.0) if equity > 0 else -1.0

    metric = {
        "trades": int(n),
        "mean_severe_net_bps": float(np.mean(vals)) if n else float("nan"),
        "profit_factor": profit_factor(vals),
        "bootstrap_p10_mean_bps": p10,
        "remove_largest_winner_mean_bps": remove_largest,
        # Synthetic controls are explicitly centered by year/hour before planting edge,
        # so zero is the matched-bucket baseline by construction.
        "matched_excess_mean_bps": float(np.mean(vals)) if n else float("nan"),
        "matched_excess_bootstrap_p10_bps": p10,
        "positive_reference_folds": int(positive_folds),
        "worst_reference_fold_mean_bps": float(worst_fold),
        "max_positive_year_profit_share": float(year_concentration),
        "final_equity_locked_risk": float(equity),
        "locked_risk_cagr": float(cagr),
    }

    g = config["reference_gates"]
    checks = {
        "minimum_trades": n >= int(g["minimum_trades"]),
        "mean_severe_positive": metric["mean_severe_net_bps"] > float(g["minimum_mean_severe_bps"]),
        "profit_factor": metric["profit_factor"] >= float(g["minimum_profit_factor"]),
        "bootstrap_p10_positive": metric["bootstrap_p10_mean_bps"] > float(g["minimum_bootstrap_p10_bps"]),
        "remove_largest_positive": metric["remove_largest_winner_mean_bps"] > 0,
        "matched_excess_positive": metric["matched_excess_mean_bps"] > 0,
        "matched_excess_p10_positive": metric["matched_excess_bootstrap_p10_bps"] > 0,
        "positive_folds": metric["positive_reference_folds"] >= int(g["minimum_positive_folds"]),
        "worst_fold": metric["worst_reference_fold_mean_bps"] >= float(g["minimum_worst_fold_mean_bps"]),
        "year_concentration": (
            np.isfinite(metric["max_positive_year_profit_share"])
            and metric["max_positive_year_profit_share"] <= float(g["maximum_positive_year_profit_share"])
        ),
        "cagr": metric["locked_risk_cagr"] >= float(g["minimum_locked_risk_cagr"]),
    }
    # CAGR is a commercial hurdle, not evidence that an edge is statistically undetectable.
    statistical_checks = {k: v for k, v in checks.items() if k != "cagr"}
    return metric, GateResult(checks=checks, statistical_pass=all(statistical_checks.values()), commercial_pass=all(checks.values()))


def run_synthetic_controls(opportunities: pd.DataFrame, config: dict[str, Any]) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    syn = config["synthetic"]
    seed = int(syn["seed"])
    max_n = max(int(x) for x in syn["sample_sizes"])
    if len(opportunities) < max(max_n, int(syn["minimum_reference_opportunities"])):
        raise CalibrationError(
            f"insufficient non-overlapping reference opportunities: {len(opportunities)}; "
            f"need >= {max(max_n, int(syn['minimum_reference_opportunities']))}"
        )

    rows: list[dict[str, Any]] = []
    gate_accumulator: dict[tuple[int, float, str], int] = {}
    trials = int(syn["trials_per_cell"])

    for n0 in syn["sample_sizes"]:
        n = int(n0)
        for alpha0 in syn["planted_severe_net_bps"]:
            alpha = float(alpha0)
            stat_passes = 0
            commercial_passes = 0
            metric_sums: dict[str, list[float]] = {}
            for trial in range(trials):
                rng = np.random.default_rng(seed + n * 100000 + int(round(alpha * 100)) * 100 + trial)
                idx = rng.choice(len(opportunities), size=n, replace=False)
                d = opportunities.iloc[idx].sort_values("decision_time_utc")
                random_side = rng.choice(np.asarray([-1.0, 1.0]), size=n, replace=True)
                severe = random_side * d["centered_4h_bps"].to_numpy(dtype="float64") + alpha
                metric, gates = metric_and_gates(
                    pd.DatetimeIndex(d["decision_time_utc"]), severe, config, rng
                )
                stat_passes += int(gates.statistical_pass)
                commercial_passes += int(gates.commercial_pass)
                for k, v in metric.items():
                    if isinstance(v, (int, float, np.floating)) and np.isfinite(v):
                        metric_sums.setdefault(k, []).append(float(v))
                for gate, passed in gates.checks.items():
                    gate_accumulator[(n, alpha, gate)] = gate_accumulator.get((n, alpha, gate), 0) + int(passed)

            row = {
                "sample_size": n,
                "planted_severe_net_bps": alpha,
                "trials": trials,
                "statistical_detection_rate": stat_passes / trials,
                "commercial_promotion_rate": commercial_passes / trials,
            }
            for k, values in metric_sums.items():
                row[f"mean_{k}"] = float(np.mean(values)) if values else float("nan")
            rows.append(row)

    curve = pd.DataFrame(rows).sort_values(["sample_size", "planted_severe_net_bps"]).reset_index(drop=True)
    gate_rows = [
        {
            "sample_size": n,
            "planted_severe_net_bps": alpha,
            "gate": gate,
            "pass_rate": count / trials,
            "trials": trials,
        }
        for (n, alpha, gate), count in sorted(gate_accumulator.items())
    ]
    gate_rates = pd.DataFrame(gate_rows)

    profile = {
        "opportunities": int(len(opportunities)),
        "first_opportunity": str(opportunities["decision_time_utc"].min()),
        "last_opportunity": str(opportunities["decision_time_utc"].max()),
        "centered_return_mean_bps": float(opportunities["centered_4h_bps"].mean()),
        "centered_return_std_bps": float(opportunities["centered_4h_bps"].std(ddof=1)),
        "centered_return_p01_bps": float(opportunities["centered_4h_bps"].quantile(0.01)),
        "centered_return_p99_bps": float(opportunities["centered_4h_bps"].quantile(0.99)),
        "matched_control_contract": "YEAR_HOUR_CENTERED_NULL; MATCHED_EXCESS_BASELINE_ZERO_BY_CONSTRUCTION",
        "planted_edge_definition": "EXPECTED_SEVERE_NET_BPS_ADDED_AFTER_YEAR_HOUR_CENTERING",
    }
    return curve, gate_rates, profile


def curve_value(curve: pd.DataFrame, n: int, alpha: float, column: str) -> float:
    m = curve[(curve["sample_size"] == int(n)) & np.isclose(curve["planted_severe_net_bps"], float(alpha))]
    if len(m) != 1:
        raise CalibrationError(f"calibration cell missing or duplicated: n={n}, alpha={alpha}")
    return float(m.iloc[0][column])


def maximum_monotonicity_drop(curve: pd.DataFrame, column: str) -> float:
    worst = 0.0
    for _, group in curve.groupby("sample_size"):
        vals = group.sort_values("planted_severe_net_bps")[column].to_numpy(dtype="float64")
        if len(vals) >= 2:
            drops = vals[:-1] - vals[1:]
            worst = max(worst, float(np.max(drops)))
    return worst


def calibration_decision(curve: pd.DataFrame, config: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    t = config["calibration_decision_thresholds"]
    checks = {
        "statistical_false_positive_n1000": curve_value(curve, 1000, 0.0, "statistical_detection_rate") <= float(t["maximum_statistical_false_positive_rate_n1000"]),
        "statistical_power_n100_alpha12": curve_value(curve, 100, 12.0, "statistical_detection_rate") >= float(t["minimum_statistical_detection_rate_n100_alpha12"]),
        "statistical_power_n300_alpha8": curve_value(curve, 300, 8.0, "statistical_detection_rate") >= float(t["minimum_statistical_detection_rate_n300_alpha8"]),
        "commercial_false_positive_n1000": curve_value(curve, 1000, 0.0, "commercial_promotion_rate") <= float(t["maximum_commercial_false_positive_rate_n1000"]),
        "commercial_power_n1000_alpha16": curve_value(curve, 1000, 16.0, "commercial_promotion_rate") >= float(t["minimum_commercial_detection_rate_n1000_alpha16"]),
        "statistical_monotonicity": maximum_monotonicity_drop(curve, "statistical_detection_rate") <= float(t["maximum_monotonicity_drop"]),
        "commercial_monotonicity": maximum_monotonicity_drop(curve, "commercial_promotion_rate") <= float(t["maximum_monotonicity_drop"]),
    }
    false_positive_ok = checks["statistical_false_positive_n1000"] and checks["commercial_false_positive_n1000"]
    power_ok = checks["statistical_power_n100_alpha12"] and checks["statistical_power_n300_alpha8"] and checks["commercial_power_n1000_alpha16"]
    monotonic_ok = checks["statistical_monotonicity"] and checks["commercial_monotonicity"]
    if all(checks.values()):
        decision = "PIPELINE_CALIBRATED_PASS"
    elif false_positive_ok and (not power_ok or not monotonic_ok):
        decision = "PIPELINE_OVERCONSERVATIVE_RECALIBRATION_REQUIRED"
    else:
        decision = "PIPELINE_INCONCLUSIVE"
    details = {
        "checks": checks,
        "observed": {
            "statistical_false_positive_rate_n1000": curve_value(curve, 1000, 0.0, "statistical_detection_rate"),
            "statistical_detection_rate_n100_alpha12": curve_value(curve, 100, 12.0, "statistical_detection_rate"),
            "statistical_detection_rate_n300_alpha8": curve_value(curve, 300, 8.0, "statistical_detection_rate"),
            "commercial_false_positive_rate_n1000": curve_value(curve, 1000, 0.0, "commercial_promotion_rate"),
            "commercial_detection_rate_n1000_alpha16": curve_value(curve, 1000, 16.0, "commercial_promotion_rate"),
            "maximum_statistical_monotonicity_drop": maximum_monotonicity_drop(curve, "statistical_detection_rate"),
            "maximum_commercial_monotonicity_drop": maximum_monotonicity_drop(curve, "commercial_promotion_rate"),
        },
        "interpretation_contract": {
            "statistical_detection": "all locked robustness gates except CAGR",
            "commercial_promotion": "all locked robustness gates including 2pct CAGR",
            "important": "A statistical edge can be detected while failing commercial promotion; that is not a validator defect.",
        },
    }
    return decision, details


def max_drawdown(returns: np.ndarray) -> float:
    vals = np.asarray(returns, dtype="float64")
    equity = np.cumprod(1.0 + vals)
    peak = np.maximum.accumulate(equity)
    dd = equity / peak - 1.0
    return float(dd.min()) if len(dd) else float("nan")


def empirical_tsmom(reference: pd.DataFrame, config: dict[str, Any]) -> tuple[pd.DataFrame, dict[str, Any]]:
    # This is a gold-CFD proxy sanity benchmark, not a faithful 58-contract replication.
    e = config["empirical_tsmom"]
    prices = reference.loc[reference["entry_open"].notna(), ["decision_time_utc", "entry_open"]].copy()
    prices = prices.drop_duplicates("decision_time_utc").sort_values("decision_time_utc")
    prices["date"] = prices["decision_time_utc"].dt.floor("D")
    daily = prices.groupby("date", as_index=False).tail(1).set_index("date")["entry_open"].astype(float)
    daily_ret = daily.pct_change()

    com = float(e["volatility_center_of_mass_days"])
    annual_days = float(e["annualization_days"])
    # Past-only ex-ante vol: today's strategy may only use volatility estimated through yesterday.
    exante_vol = daily_ret.ewm(com=com, adjust=False, min_periods=30).std(bias=False).shift(1) * math.sqrt(annual_days)

    monthly_price = daily.resample("ME").last()
    monthly_ret = monthly_price.pct_change()
    lookback = int(e["lookback_months"])
    past_12m = monthly_price / monthly_price.shift(lookback) - 1.0
    signal = np.sign(past_12m)
    monthly_vol = exante_vol.resample("ME").last()
    position_scale = float(e["target_annualized_volatility"]) / monthly_vol
    next_ret = monthly_ret.shift(-1)
    strategy_gross = signal * position_scale * next_ret
    passive_gross = position_scale * next_ret

    out = pd.DataFrame({
        "formation_month": monthly_price.index,
        "price": monthly_price.to_numpy(),
        "past_12m_return": past_12m.to_numpy(),
        "signal": signal.to_numpy(),
        "exante_annualized_vol": monthly_vol.to_numpy(),
        "position_scale": position_scale.to_numpy(),
        "next_month_return": next_ret.to_numpy(),
        "tsmom_gross_return": strategy_gross.to_numpy(),
        "passive_vol_scaled_gross_return": passive_gross.to_numpy(),
    })
    out = out.loc[out["tsmom_gross_return"].notna() & out["position_scale"].notna()].copy().reset_index(drop=True)
    for cost_bps in e["monthly_cost_sensitivity_bps"]:
        c = float(cost_bps)
        out[f"tsmom_net_{c:g}bps"] = out["tsmom_gross_return"] - c / 10000.0

    gross = out["tsmom_gross_return"].to_numpy(dtype="float64")
    passive = out["passive_vol_scaled_gross_return"].to_numpy(dtype="float64")
    ann_mean = float(np.mean(gross) * 12.0) if len(gross) else float("nan")
    ann_vol = float(np.std(gross, ddof=1) * math.sqrt(12.0)) if len(gross) > 1 else float("nan")
    sharpe = ann_mean / ann_vol if np.isfinite(ann_vol) and ann_vol > 0 else float("nan")
    passive_ann_mean = float(np.mean(passive) * 12.0) if len(passive) else float("nan")
    summary = {
        "role": "EMPIRICAL_SANITY_BENCHMARK_NOT_CALIBRATION_DECIDER",
        "instrument": "XAUUSD_CFD_PROXY_FROM_EXISTING_PANEL",
        "literature_specification": "sign(past_12m_return) * 40pct/exante_vol * next_month_return",
        "deviation_from_paper": "single XAUUSD CFD proxy; not 58 futures/forwards; no roll/excess-return reconstruction",
        "months": int(len(out)),
        "first_formation_month": str(out["formation_month"].min()) if len(out) else None,
        "last_formation_month": str(out["formation_month"].max()) if len(out) else None,
        "gross_annualized_mean_return": ann_mean,
        "gross_annualized_volatility": ann_vol,
        "gross_sharpe_zero_rf": float(sharpe),
        "gross_positive_month_share": float((gross > 0).mean()) if len(gross) else float("nan"),
        "gross_max_drawdown": max_drawdown(gross),
        "passive_vol_scaled_annualized_mean_return": passive_ann_mean,
        "max_position_scale": float(out["position_scale"].max()) if len(out) else float("nan"),
        "directionally_positive": bool(np.isfinite(ann_mean) and ann_mean > 0),
        "calibration_decision_dependency": "NONE",
    }
    for cost_bps in e["monthly_cost_sensitivity_bps"]:
        c = float(cost_bps)
        v = out[f"tsmom_net_{c:g}bps"].to_numpy(dtype="float64")
        summary[f"net_{c:g}bps_annualized_mean_return"] = float(np.mean(v) * 12.0) if len(v) else float("nan")
    return out, summary


def static_execution_violations(root: Path) -> list[str]:
    path = root / "app/xauusd_pipeline_calibration.py"
    if not path.is_file():
        return []
    tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
    forbidden_calls = {"order_send", "buy", "sell", "positions_get", "orders_send", "post"}
    forbidden_import_roots = {"MetaTrader5", "requests", "websocket", "websockets"}
    violations: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in forbidden_import_roots:
                    violations.append(f"import:{alias.name}")
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.module.split(".")[0] in forbidden_import_roots:
                violations.append(f"importfrom:{node.module}")
        elif isinstance(node, ast.Call):
            name = None
            if isinstance(node.func, ast.Name):
                name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                name = node.func.attr
            if name in forbidden_calls:
                violations.append(f"call:{name}")
    return sorted(set(violations))


def preflight(root: Path, config_path: Path, targets_arg: str | None) -> dict[str, Any]:
    config = load_config(config_path)
    targets = resolve_targets(root, targets_arg)
    if not targets.is_file():
        raise CalibrationError(f"targets input not found: {targets}")
    ref, contract = read_reference_targets(targets, config)
    opportunities = eligible_nonoverlap_opportunities(ref, config)
    required = max(
        max(int(x) for x in config["synthetic"]["sample_sizes"]),
        int(config["synthetic"]["minimum_reference_opportunities"]),
    )
    if len(opportunities) < required:
        raise CalibrationError(f"insufficient calibration opportunities: {len(opportunities)} < {required}")
    violations = static_execution_violations(root)
    if violations:
        raise CalibrationError(f"static execution violations: {violations}")
    return {
        "program": PROGRAM,
        "generated_utc": utc_now(),
        "decision": "PASS_PIPELINE_CALIBRATION_PREFLIGHT_REFERENCE_ONLY",
        "pass": True,
        "paper_order_allowed": False,
        "demo_order_allowed": False,
        "live_order_allowed": False,
        "targets_contract": contract,
        "reference_nonoverlap_opportunities": int(len(opportunities)),
        "reference_first": str(opportunities["decision_time_utc"].min()),
        "reference_last": str(opportunities["decision_time_utc"].max()),
        "synthetic_cells": int(len(config["synthetic"]["sample_sizes"]) * len(config["synthetic"]["planted_severe_net_bps"])),
        "trials_per_cell": int(config["synthetic"]["trials_per_cell"]),
        "diagnostic_2025_plus_evaluated": False,
        "static_execution_violations": [],
        "required_next_action": "RUN_PIPELINE_CALIBRATION_ONCE",
    }


def archive_existing_report(root: Path, report: Path) -> str | None:
    if not report.exists() or not any(report.iterdir()):
        return None
    archive = root / "reports/_archive"
    archive.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = archive / f"xauusd_pipeline_calibration_{stamp}"
    shutil.move(str(report), str(dest))
    return str(dest)


def decision_markdown(summary: dict[str, Any]) -> str:
    obs = summary["calibration_details"]["observed"]
    return f"""# XAUUSD Pipeline Calibration Decision\n\n- Program: `{PROGRAM}`\n- Decision: `{summary['decision']}`\n- Statistical false-positive rate (n=1000, alpha=0): {obs['statistical_false_positive_rate_n1000']:.3f}\n- Statistical detection rate (n=100, alpha=12bps): {obs['statistical_detection_rate_n100_alpha12']:.3f}\n- Statistical detection rate (n=300, alpha=8bps): {obs['statistical_detection_rate_n300_alpha8']:.3f}\n- Commercial false-positive rate (n=1000, alpha=0): {obs['commercial_false_positive_rate_n1000']:.3f}\n- Commercial promotion rate (n=1000, alpha=16bps): {obs['commercial_detection_rate_n1000_alpha16']:.3f}\n- 2025+ diagnostic evaluated: **NO**\n\n## Interpretation\n\nStatistical detection excludes only the locked 2% CAGR hurdle. Commercial promotion includes it. A planted edge can therefore be statistically detected but intentionally rejected as commercially too small. This distinction prevents a commercial hurdle from being misread as evidence that the validator cannot detect alpha.\n\nThe empirical TSMOM result is a gold-CFD proxy sanity benchmark and does **not** control the calibration decision.\n"""


def run(root: Path, config_path: Path, targets_arg: str | None) -> dict[str, Any]:
    config = load_config(config_path)
    targets = resolve_targets(root, targets_arg)
    report = root / REPORT_DIR
    archived = archive_existing_report(root, report)
    report.mkdir(parents=True, exist_ok=True)

    ref, contract = read_reference_targets(targets, config)
    opportunities = eligible_nonoverlap_opportunities(ref, config)
    curve, gate_rates, profile = run_synthetic_controls(opportunities, config)
    decision, details = calibration_decision(curve, config)
    tsmom_rows, tsmom_summary = empirical_tsmom(ref, config)

    curve.to_csv(report / "synthetic_detection_curve.csv", index=False)
    gate_rates.to_csv(report / "synthetic_gate_pass_rates.csv", index=False)
    tsmom_rows.to_csv(report / "empirical_tsmom_monthly.csv", index=False)
    write_json(report / "synthetic_control_profile.json", profile)
    write_json(report / "empirical_tsmom_summary.json", tsmom_summary)
    write_json(report / "input_manifest.json", contract)
    write_json(report / "calibration_contract.json", {
        "program": PROGRAM,
        "reference_start_utc": config["reference_start_utc"],
        "reference_end_utc": config["reference_end_utc"],
        "diagnostic_2025_plus_evaluated": False,
        "synthetic": config["synthetic"],
        "reference_gates": config["reference_gates"],
        "calibration_decision_thresholds": config["calibration_decision_thresholds"],
        "statistical_detection_excludes_only": ["cagr"],
        "commercial_promotion_includes": "ALL_LOCKED_REFERENCE_GATES",
        "empirical_tsmom_affects_decision": False,
        "order_permissions": {"paper": False, "demo": False, "live": False},
    })

    summary = {
        "program": PROGRAM,
        "generated_utc": utc_now(),
        "decision": decision,
        "pass": decision == "PIPELINE_CALIBRATED_PASS",
        "paper_order_allowed": False,
        "demo_order_allowed": False,
        "live_order_allowed": False,
        "reference_rows_loaded": int(len(ref)),
        "reference_nonoverlap_opportunities": int(len(opportunities)),
        "synthetic_cells": int(len(curve)),
        "synthetic_trials_total": int(curve["trials"].sum()),
        "calibration_details": details,
        "empirical_tsmom": tsmom_summary,
        "diagnostic_2025_plus_evaluated": False,
        "archived_previous_report": archived,
        "required_next_action": (
            "TRUST_PIPELINE_KILL_PASS_DISTINCTION_AND_REASSESS_STRATEGIC_OPTIONS"
            if decision == "PIPELINE_CALIBRATED_PASS"
            else "RECALIBRATE_VALIDATION_PIPELINE_BEFORE_ANY_STRATEGIC_PIVOT"
            if decision == "PIPELINE_OVERCONSERVATIVE_RECALIBRATION_REQUIRED"
            else "INVESTIGATE_CALIBRATION_INCONCLUSIVE_BEFORE_RESEARCH_OR_COMMERCIAL_PIVOT"
        ),
    }
    write_json(report / "pipeline_calibration_summary.json", summary)
    (report / "pipeline_calibration_decision.md").write_text(decision_markdown(summary), encoding="utf-8")
    return summary


def collect(root: Path) -> Path:
    report = root / REPORT_DIR
    summary = report / "pipeline_calibration_summary.json"
    if not summary.is_file():
        raise CalibrationError("pipeline calibration summary missing; run calibration first")
    names = [
        "pipeline_calibration_summary.json",
        "pipeline_calibration_decision.md",
        "calibration_contract.json",
        "input_manifest.json",
        "synthetic_control_profile.json",
        "synthetic_detection_curve.csv",
        "synthetic_gate_pass_rates.csv",
        "empirical_tsmom_summary.json",
        "empirical_tsmom_monthly.csv",
    ]
    missing = [n for n in names if not (report / n).is_file()]
    if missing:
        raise CalibrationError(f"missing result files: {missing}")
    dest = Path.home() / "Downloads" / COLLECT_NAME
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()
    manifest: list[dict[str, Any]] = []
    for n in names:
        p = report / n
        manifest.append({"path": n, "size_bytes": p.stat().st_size, "sha256": sha256_file(p)})
    manifest_path = report / "RESULTS_MANIFEST.json"
    write_json(manifest_path, {"program": PROGRAM, "generated_utc": utc_now(), "files": manifest})
    with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for n in names + ["RESULTS_MANIFEST.json"]:
            z.write(report / n, arcname=n)
    return dest


def failure_payload(exc: Exception, stage: str) -> dict[str, Any]:
    return {
        "program": PROGRAM,
        "generated_utc": utc_now(),
        "decision": "PIPELINE_CALIBRATION_FAIL_CLOSED",
        "pass": False,
        "paper_order_allowed": False,
        "demo_order_allowed": False,
        "live_order_allowed": False,
        "stage": stage,
        "error": f"{type(exc).__name__}: {exc}",
        "traceback": traceback.format_exc(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=PROGRAM)
    parser.add_argument("action", choices=["preflight", "run", "collect"])
    parser.add_argument("--root", default=".")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--targets", default=None, help="Optional explicit cross_asset_intraday_targets.csv(.gz) path")
    args = parser.parse_args(argv)
    root = Path(args.root).expanduser().resolve()
    config_path = Path(args.config).expanduser()
    if not config_path.is_absolute():
        config_path = root / config_path

    stage = "NOT_STARTED"
    try:
        if args.action == "preflight":
            stage = "PREFLIGHT"
            payload = preflight(root, config_path, args.targets)
            print(json.dumps(payload, indent=2, default=str))
            return 0
        if args.action == "run":
            stage = "RUN_CALIBRATION"
            payload = run(root, config_path, args.targets)
            print(json.dumps(payload, indent=2, default=str))
            return 0 if payload["decision"] in {
                "PIPELINE_CALIBRATED_PASS",
                "PIPELINE_OVERCONSERVATIVE_RECALIBRATION_REQUIRED",
                "PIPELINE_INCONCLUSIVE",
            } else 2
        stage = "COLLECT"
        dest = collect(root)
        print(json.dumps({"program": PROGRAM, "decision": "COLLECT_PASS", "artifact": str(dest), "sha256": sha256_file(dest)}, indent=2))
        return 0
    except Exception as exc:
        payload = failure_payload(exc, stage)
        if args.action == "run":
            report = root / REPORT_DIR
            report.mkdir(parents=True, exist_ok=True)
            write_json(report / "pipeline_calibration_failure.json", payload)
        elif args.action == "preflight":
            write_json(root / "reports/xauusd_pipeline_calibration_preflight_failure.json", payload)
        print(json.dumps(payload, indent=2, default=str), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
