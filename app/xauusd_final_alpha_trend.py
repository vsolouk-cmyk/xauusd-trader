#!/usr/bin/env python3
from __future__ import annotations

import argparse
import calendar
import hashlib
import json
import math
import shutil
import sys
import zipfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

PROGRAM = "XAUUSD_FINAL_ALPHA_CAMPAIGN_CANONICAL_LONG_HORIZON_TREND_V1"
PREFLIGHT_PASS = "PASS_FINAL_ALPHA_TREND_PREFLIGHT_REFERENCE_ONLY"
REF_FAIL = "NO_REFERENCE_EDGE_CLOSE_LONG_HORIZON_TREND_ON_XAUUSD_CFD"
REF_PASS_DIAG_FAIL = "REFERENCE_PASS_DIAGNOSTIC_BREAKDOWN_REJECT_TREND_PATH"
REF_PASS_DIAG_PASS = "REFERENCE_PASS_DIAGNOSTIC_SUPPORT_READY_FOR_INDEPENDENT_GC_REPLICATION"
FAIL_CLOSED = "FINAL_ALPHA_TREND_FAIL_CLOSED"


class CampaignError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, obj: dict) -> None:
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")


def last_sunday(year: int, month: int) -> int:
    last_day = calendar.monthrange(year, month)[1]
    d = datetime(year, month, last_day)
    return last_day - ((d.weekday() + 1) % 7)


def eu_dst_utc(dt_utc: datetime) -> bool:
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=timezone.utc)
    else:
        dt_utc = dt_utc.astimezone(timezone.utc)
    y = dt_utc.year
    start = datetime(y, 3, last_sunday(y, 3), 1, 0, tzinfo=timezone.utc)
    end = datetime(y, 10, last_sunday(y, 10), 1, 0, tzinfo=timezone.utc)
    return start <= dt_utc < end


def server_naive_to_utc(ts: pd.Timestamp, std_minutes: int, dst_minutes: int) -> pd.Timestamp:
    py = ts.to_pydatetime().replace(tzinfo=None)
    cand_std = (py + timedelta(minutes=std_minutes)).replace(tzinfo=timezone.utc)
    cand_dst = (py + timedelta(minutes=dst_minutes)).replace(tzinfo=timezone.utc)
    std_valid = not eu_dst_utc(cand_std)
    dst_valid = eu_dst_utc(cand_dst)
    if std_valid and not dst_valid:
        return pd.Timestamp(cand_std)
    if dst_valid and not std_valid:
        return pd.Timestamp(cand_dst)
    if dst_valid:
        return pd.Timestamp(cand_dst)
    return pd.Timestamp(cand_std)


def _find_col(columns: Iterable[str], names: list[str]) -> str | None:
    exact = {str(c).strip().lower(): str(c) for c in columns}
    for n in names:
        if n.lower() in exact:
            return exact[n.lower()]
    return None


def load_mt5_h1(path: Path, cfg: dict) -> pd.DataFrame:
    with path.open("r", encoding="utf-8-sig", errors="ignore") as fh:
        first = fh.readline()
    if "\t" in first:
        sep = "\t"
    elif ";" in first and first.count(";") > first.count(","):
        sep = ";"
    else:
        sep = ","
    df = pd.read_csv(path, sep=sep, low_memory=False)
    if df.empty:
        raise CampaignError("H1 input is empty")

    cols = [str(c) for c in df.columns]
    date_col = _find_col(cols, ["<DATE>", "date"])
    time_col = _find_col(cols, ["<TIME>", "time"])
    ts_col = _find_col(cols, ["timestamp", "timestamp_utc", "datetime", "dt"])
    open_col = _find_col(cols, ["<OPEN>", "open"])
    high_col = _find_col(cols, ["<HIGH>", "high"])
    low_col = _find_col(cols, ["<LOW>", "low"])
    close_col = _find_col(cols, ["<CLOSE>", "close"])

    if not all([open_col, high_col, low_col, close_col]):
        raise CampaignError(f"OHLC schema not recognized; columns={cols}")

    if date_col and time_col:
        naive = pd.to_datetime(
            df[date_col].astype(str).str.strip() + " " + df[time_col].astype(str).str.strip(),
            errors="coerce",
        )
        tc = cfg["time_contract"]
        converted = [
            server_naive_to_utc(x, int(tc["standard_shift_minutes"]), int(tc["dst_shift_minutes"]))
            if not pd.isna(x) else pd.NaT
            for x in naive
        ]
        ts = pd.to_datetime(converted, utc=True, errors="coerce")
        loader = "MT5_DATE_TIME_EU_DST"
    elif ts_col:
        raw = pd.to_datetime(df[ts_col], utc=True, errors="coerce")
        ts = raw
        loader = "DIRECT_UTC_TIMESTAMP"
    else:
        raise CampaignError(f"timestamp schema not recognized; columns={cols}")

    out = pd.DataFrame({
        "timestamp_utc": ts,
        "open": pd.to_numeric(df[open_col], errors="coerce"),
        "high": pd.to_numeric(df[high_col], errors="coerce"),
        "low": pd.to_numeric(df[low_col], errors="coerce"),
        "close": pd.to_numeric(df[close_col], errors="coerce"),
    })
    raw_rows = len(out)
    out = out.dropna().sort_values("timestamp_utc")
    out = out.drop_duplicates("timestamp_utc", keep="last").reset_index(drop=True)
    valid = (
        (out["high"] >= out[["open", "close", "low"]].max(axis=1))
        & (out["low"] <= out[["open", "close", "high"]].min(axis=1))
        & (out[["open", "high", "low", "close"]] > 0).all(axis=1)
    )
    if not bool(valid.all()):
        raise CampaignError(f"OHLC invariant failure rows={int((~valid).sum())}")
    if len(out) < 10000:
        raise CampaignError(f"insufficient H1 rows: {len(out)}")
    out.attrs["raw_rows"] = raw_rows
    out.attrs["loader"] = loader
    return out


def resolve_input(cfg: dict, explicit: str | None) -> Path:
    if explicit:
        p = Path(explicit).expanduser().resolve()
        if not p.is_file():
            raise CampaignError(f"explicit H1 input not found: {p}")
        return p
    for raw in cfg.get("input_candidates", []):
        p = Path(raw).expanduser()
        if p.is_file():
            return p.resolve()
    raise CampaignError("no AMarkets H1 file found in configured input_candidates; use --h1 PATH")


def ewma_daily_vol(h1: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    x = h1.copy()
    x["availability_utc"] = x["timestamp_utc"] + pd.Timedelta(hours=1)
    x["bar_date"] = x["timestamp_utc"].dt.floor("D")
    daily = (
        x.sort_values("timestamp_utc")
         .groupby("bar_date", as_index=False)
         .agg(close=("close", "last"), close_available_utc=("availability_utc", "max"))
    )
    daily["return"] = daily["close"].pct_change()
    vcfg = cfg["volatility"]
    com = float(vcfg["ewma_center_of_mass_days"])
    delta = com / (1.0 + com)
    alpha = 1.0 - delta
    r = daily["return"]
    m1 = r.ewm(alpha=alpha, adjust=True, min_periods=int(vcfg["min_daily_returns"])).mean()
    m2 = (r * r).ewm(alpha=alpha, adjust=True, min_periods=int(vcfg["min_daily_returns"])).mean()
    var = (m2 - m1 * m1).clip(lower=0)
    daily["ex_ante_vol"] = np.sqrt(var * float(vcfg["annualization_days"]))
    return daily


def build_monthly_strategy(h1: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    x = h1.copy().sort_values("timestamp_utc").reset_index(drop=True)
    x["month"] = x["timestamp_utc"].dt.strftime("%Y-%m")
    first_idx = x.groupby("month", sort=True).head(1).index
    entries = x.loc[first_idx, ["month", "timestamp_utc", "open"]].copy().reset_index(drop=True)
    entries = entries.rename(columns={"timestamp_utc": "entry_utc", "open": "entry_open"})

    x["availability_utc"] = x["timestamp_utc"] + pd.Timedelta(hours=1)
    daily = ewma_daily_vol(x, cfg)

    signal_close = []
    signal_close_time = []
    signal_vol = []
    for e in entries["entry_utc"]:
        prior = x.loc[x["availability_utc"] <= e]
        if prior.empty:
            signal_close.append(np.nan)
            signal_close_time.append(pd.NaT)
        else:
            row = prior.iloc[-1]
            signal_close.append(float(row["close"]))
            signal_close_time.append(row["availability_utc"])
        dprior = daily.loc[daily["close_available_utc"] <= e]
        signal_vol.append(float(dprior.iloc[-1]["ex_ante_vol"]) if not dprior.empty else np.nan)

    entries["signal_close"] = signal_close
    entries["signal_close_available_utc"] = pd.to_datetime(signal_close_time, utc=True)
    entries["ex_ante_vol"] = signal_vol
    lookback = int(cfg["lookback_months"])
    entries["signal_return_12m"] = entries["signal_close"] / entries["signal_close"].shift(lookback) - 1.0
    entries["signal"] = np.sign(entries["signal_return_12m"]).astype(float)

    pcfg = cfg["position"]
    raw_scale = float(pcfg["target_annual_volatility"]) / entries["ex_ante_vol"]
    entries["vol_scale"] = raw_scale.clip(lower=0, upper=float(pcfg["max_abs_position"]))
    entries["position"] = entries["signal"] * entries["vol_scale"]
    entries["passive_position"] = entries["vol_scale"]

    entries["exit_utc"] = entries["entry_utc"].shift(-1)
    entries["exit_open"] = entries["entry_open"].shift(-1)
    entries["underlying_return"] = entries["exit_open"] / entries["entry_open"] - 1.0

    eligible = (
        entries["signal_return_12m"].notna()
        & entries["ex_ante_vol"].notna()
        & np.isfinite(entries["ex_ante_vol"])
        & (entries["ex_ante_vol"] > 0)
        & entries["exit_utc"].notna()
        & entries["underlying_return"].notna()
        & entries["signal_close_available_utc"].notna()
        & (entries["signal_close_available_utc"] <= entries["entry_utc"])
    )
    entries = entries.loc[eligible].reset_index(drop=True)
    entries["turnover"] = (entries["position"] - entries["position"].shift(1).fillna(0.0)).abs()
    entries["passive_turnover"] = (entries["passive_position"] - entries["passive_position"].shift(1).fillna(0.0)).abs()
    entries["buyhold_turnover"] = 0.0
    if len(entries):
        entries.loc[0, "buyhold_turnover"] = 1.0
    entries["gross_return"] = entries["position"] * entries["underlying_return"]
    entries["passive_gross_return"] = entries["passive_position"] * entries["underlying_return"]
    entries["buyhold_gross_return"] = entries["underlying_return"]
    ccfg = cfg["cost_bps_per_1x_turnover"]
    for label in ["normal", "severe"]:
        c = float(ccfg[label]) / 10000.0
        entries[f"net_return_{label}"] = entries["gross_return"] - c * entries["turnover"]
        entries[f"passive_net_return_{label}"] = entries["passive_gross_return"] - c * entries["passive_turnover"]
        entries[f"buyhold_net_return_{label}"] = entries["buyhold_gross_return"] - c * entries["buyhold_turnover"]
    return entries


def annualized_return(r: pd.Series) -> float:
    r = pd.Series(r, dtype=float).dropna()
    if r.empty:
        return float("nan")
    equity = float(np.prod(1.0 + r.to_numpy()))
    if equity <= 0:
        return -1.0
    return equity ** (12.0 / len(r)) - 1.0


def sharpe(r: pd.Series) -> float:
    r = pd.Series(r, dtype=float).dropna()
    if len(r) < 2:
        return float("nan")
    sd = float(r.std(ddof=1))
    return float(r.mean() / sd * math.sqrt(12.0)) if sd > 0 else (float("inf") if r.mean() > 0 else 0.0)


def max_drawdown(r: pd.Series) -> float:
    r = pd.Series(r, dtype=float).fillna(0.0)
    eq = (1.0 + r).cumprod()
    peak = eq.cummax()
    dd = eq / peak - 1.0
    return float(dd.min()) if len(dd) else float("nan")


def profit_factor(r: pd.Series) -> float | None:
    r = pd.Series(r, dtype=float).dropna()
    pos = float(r[r > 0].sum())
    neg = float(-r[r < 0].sum())
    if neg == 0:
        return None if pos == 0 else float("inf")
    return pos / neg


def moving_block_bootstrap_means(values: np.ndarray, iterations: int, block: int, seed: int) -> np.ndarray:
    values = np.asarray(values, dtype=float)
    n = len(values)
    if n == 0:
        return np.array([])
    rng = np.random.default_rng(seed)
    starts = np.arange(max(1, n - block + 1))
    out = np.empty(iterations, dtype=float)
    needed = int(math.ceil(n / block))
    for i in range(iterations):
        chunks = []
        for s in rng.choice(starts, size=needed, replace=True):
            chunks.append(values[s : min(s + block, n)])
        sample = np.concatenate(chunks)[:n]
        out[i] = float(sample.mean())
    return out


def metrics(df: pd.DataFrame, col: str, cfg: dict, prefix: str = "") -> dict:
    r = pd.Series(df[col], dtype=float)
    bcfg = cfg["bootstrap"]
    boot = moving_block_bootstrap_means(
        r.to_numpy(), int(bcfg["iterations"]), int(bcfg["block_months"]), int(bcfg["seed"])
    )
    best_idx = r.idxmax() if len(r) else None
    without = r.drop(index=best_idx) if best_idx is not None and len(r) > 1 else pd.Series(dtype=float)
    return {
        f"{prefix}months": int(len(r)),
        f"{prefix}mean_monthly": float(r.mean()) if len(r) else None,
        f"{prefix}annualized_return": annualized_return(r),
        f"{prefix}sharpe": sharpe(r),
        f"{prefix}max_drawdown": max_drawdown(r),
        f"{prefix}profit_factor": profit_factor(r),
        f"{prefix}bootstrap_p10_monthly_mean": float(np.quantile(boot, float(bcfg["lower_quantile"]))) if len(boot) else None,
        f"{prefix}remove_best_month_annualized_return": annualized_return(without) if len(without) else None,
        f"{prefix}best_month": float(r.max()) if len(r) else None,
        f"{prefix}worst_month": float(r.min()) if len(r) else None,
    }


def fold_metrics(df: pd.DataFrame, col: str) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    chunks = np.array_split(np.arange(len(df)), 3)
    rows = []
    for i, idx in enumerate(chunks, 1):
        sub = df.iloc[idx]
        r = sub[col]
        rows.append({
            "fold": i,
            "months": len(sub),
            "start_entry_utc": sub["entry_utc"].min(),
            "end_exit_utc": sub["exit_utc"].max(),
            "annualized_return": annualized_return(r),
            "sharpe": sharpe(r),
            "max_drawdown": max_drawdown(r),
        })
    return pd.DataFrame(rows)


def year_metrics(df: pd.DataFrame, col: str) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    z = df.copy()
    z["year"] = z["entry_utc"].dt.year
    rows = []
    for y, sub in z.groupby("year"):
        r = sub[col]
        rows.append({
            "year": int(y),
            "months": int(len(sub)),
            "annualized_return": annualized_return(r),
            "sum_return": float(r.sum()),
            "sharpe": sharpe(r),
            "max_drawdown": max_drawdown(r),
        })
    return pd.DataFrame(rows)


def paired_excess_metrics(df: pd.DataFrame, cfg: dict, a: str, b: str) -> dict:
    excess = (df[a] - df[b]).astype(float)
    bcfg = cfg["bootstrap"]
    boot = moving_block_bootstrap_means(
        excess.to_numpy(), int(bcfg["iterations"]), int(bcfg["block_months"]), int(bcfg["seed"]) + 17
    )
    return {
        "mean_monthly": float(excess.mean()),
        "annualized_arithmetic": float(excess.mean() * 12.0),
        "bootstrap_p10_monthly_mean": float(np.quantile(boot, float(bcfg["lower_quantile"]))),
    }


def reference_gate_checks(ref: pd.DataFrame, cfg: dict, m: dict, folds: pd.DataFrame, years: pd.DataFrame, paired: dict) -> dict:
    g = cfg["reference_gates"]
    positive_years = int((years["annualized_return"] > 0).sum()) if not years.empty else 0
    positive_year_share = positive_years / len(years) if len(years) else 0.0
    positive_sums = years.loc[years["sum_return"] > 0, "sum_return"] if not years.empty else pd.Series(dtype=float)
    total_pos = float(positive_sums.sum())
    concentration = float(positive_sums.max() / total_pos) if total_pos > 0 else 1.0
    positive_folds = int((folds["annualized_return"] > 0).sum()) if not folds.empty else 0
    worst_fold = float(folds["annualized_return"].min()) if not folds.empty else float("nan")
    checks = {
        "min_months": len(ref) >= int(g["min_months"]),
        "severe_annualized_return": float(m["annualized_return"]) > float(g["min_severe_annualized_return"]),
        "severe_sharpe": float(m["sharpe"]) > float(g["min_severe_sharpe"]),
        "bootstrap_p10": float(m["bootstrap_p10_monthly_mean"]) > float(g["bootstrap_p10_monthly_mean_gt"]),
        "remove_best_month": float(m["remove_best_month_annualized_return"]) > float(g["remove_best_month_annualized_return_gt"]),
        "positive_folds": positive_folds >= int(g["min_positive_folds"]),
        "worst_fold": worst_fold > float(g["worst_fold_annualized_return_gt"]),
        "positive_year_share": positive_year_share >= float(g["min_positive_year_share"]),
        "positive_year_concentration": concentration <= float(g["max_positive_year_concentration"]),
        "max_drawdown": abs(float(m["max_drawdown"])) <= float(g["max_drawdown_abs"]),
        "paired_excess_mean_vs_passive": float(paired["mean_monthly"]) > float(g["paired_excess_mean_vs_passive_gt"]),
        "paired_excess_bootstrap_p10": float(paired["bootstrap_p10_monthly_mean"]) > float(g["paired_excess_bootstrap_p10_gt"]),
    }
    checks["all"] = bool(all(checks.values()))
    checks["derived"] = {
        "positive_years": positive_years,
        "year_count": int(len(years)),
        "positive_year_share": positive_year_share,
        "max_positive_year_concentration": concentration,
        "positive_folds": positive_folds,
        "worst_fold_annualized_return": worst_fold,
    }
    return checks


def diagnostic_gate_checks(diag: pd.DataFrame, cfg: dict, m: dict, paired: dict) -> dict:
    g = cfg["diagnostic_kill_gates"]
    checks = {
        "min_months": len(diag) >= int(g["min_months"]),
        "annualized_return": float(m["annualized_return"]) > float(g["annualized_return_gt"]),
        "sharpe": float(m["sharpe"]) > float(g["sharpe_gt"]),
        "max_drawdown": abs(float(m["max_drawdown"])) <= float(g["max_drawdown_abs"]),
        "annualized_excess_vs_passive": float(paired["annualized_arithmetic"]) > float(g["annualized_excess_vs_passive_gt"]),
    }
    checks["all"] = bool(all(checks.values()))
    return checks


def safe_scalar(x):
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (np.floating,)):
        if not np.isfinite(x):
            return None
        return float(x)
    if isinstance(x, pd.Timestamp):
        return x.isoformat()
    return x


def output_manifest(outdir: Path, exclude: set[str] | None = None) -> dict:
    exclude = exclude or set()
    files = []
    for p in sorted(outdir.iterdir()):
        if p.is_file() and p.name not in exclude:
            files.append({"name": p.name, "size_bytes": p.stat().st_size, "sha256": sha256_file(p)})
    return {"program": PROGRAM, "files": files}


def clean_or_archive(outdir: Path) -> None:
    if not outdir.exists() or not any(outdir.iterdir()):
        outdir.mkdir(parents=True, exist_ok=True)
        return
    archive = outdir.parent / "_archive"
    archive.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = archive / f"{outdir.name}_{stamp}"
    shutil.move(str(outdir), str(dest))
    outdir.mkdir(parents=True, exist_ok=True)


def make_summary_base(input_path: Path, h1: pd.DataFrame, ref_monthly: pd.DataFrame, cfg: dict) -> dict:
    ref_end = pd.Timestamp(cfg["reference_end_utc"])
    return {
        "program": PROGRAM,
        "strategy_id": cfg["strategy_id"],
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "input": {
            "path": str(input_path),
            "sha256": sha256_file(input_path),
            "size_bytes": input_path.stat().st_size,
            "raw_rows": int(h1.attrs.get("raw_rows", len(h1))),
            "valid_rows": int(len(h1)),
            "loader": h1.attrs.get("loader"),
            "first_utc": h1["timestamp_utc"].min().isoformat(),
            "last_utc": h1["timestamp_utc"].max().isoformat(),
            "post_boundary_h1_rows_metadata_only": int((h1["timestamp_utc"] >= ref_end).sum()),
        },
        "locked_contract": {
            "literature_anchor": "Moskowitz_Ooi_Pedersen_2012_Time_Series_Momentum",
            "signal": "sign of trailing 12-month XAUUSD broker-price return",
            "holding_rebalance": "one calendar month; first executable H1 open of month",
            "volatility": "past-only EWMA daily-return variance; center of mass 60 days; annualization 261",
            "literature_target_vol_note": "paper uses 40% per instrument; authors state scaling choice is inconsequential",
            "broker_target_annual_volatility": cfg["position"]["target_annual_volatility"],
            "max_abs_position": cfg["position"]["max_abs_position"],
            "cost_normal_bps_per_1x_turnover": cfg["cost_bps_per_1x_turnover"]["normal"],
            "cost_severe_bps_per_1x_turnover": cfg["cost_bps_per_1x_turnover"]["severe"],
            "selection_boundary_utc": cfg["reference_end_utc"],
            "selection_used_2025_plus": False,
            "parameter_scan": False,
            "macro_filter": False,
            "intraday_filter": False,
        },
        "counts": {
            "reference_eligible_months": int(len(ref_monthly)),
            "diagnostic_months_computed": 0,
        },
        "authorization": cfg["execution_authorization"],
    }


def run_campaign(root: Path, config_path: Path, h1_arg: str | None, mode: str) -> dict:
    cfg = read_json(config_path)
    if cfg.get("program") != PROGRAM:
        raise CampaignError("config program mismatch")
    input_path = resolve_input(cfg, h1_arg)
    h1 = load_mt5_h1(input_path, cfg)
    ref_end = pd.Timestamp(cfg["reference_end_utc"])

    # Critical holdout discipline: build strategy outcomes only from pre-boundary bars first.
    # 2025+ bars may be present in the raw file and are counted only as metadata here; no
    # signal/return/diagnostic computation is performed unless every reference gate passes.
    h1_ref = h1.loc[h1["timestamp_utc"] < ref_end].copy()
    h1_ref.attrs.update(h1.attrs)
    ref_monthly = build_monthly_strategy(h1_ref, cfg)
    ref = ref_monthly.loc[ref_monthly["exit_utc"] < ref_end].copy().reset_index(drop=True)
    base = make_summary_base(input_path, h1, ref, cfg)
    if len(ref) < int(cfg["reference_gates"]["min_months"]):
        raise CampaignError(f"insufficient eligible reference months: {len(ref)}")

    if mode == "preflight":
        out = dict(base)
        out.update({"decision": PREFLIGHT_PASS, "pass": True, "reference_only": True})
        return out

    outdir = (root / cfg["output_dir"]).resolve()
    clean_or_archive(outdir)

    ref.to_csv(outdir / "reference_monthly_ledger.csv", index=False)
    m = metrics(ref, "net_return_severe", cfg)
    normal_m = metrics(ref, "net_return_normal", cfg, "normal_")
    passive_m = metrics(ref, "passive_net_return_severe", cfg, "passive_")
    buyhold_m = metrics(ref, "buyhold_net_return_severe", cfg, "buyhold_")
    folds = fold_metrics(ref, "net_return_severe")
    years = year_metrics(ref, "net_return_severe")
    paired = paired_excess_metrics(ref, cfg, "net_return_severe", "passive_net_return_severe")
    folds.to_csv(outdir / "reference_fold_metrics.csv", index=False)
    years.to_csv(outdir / "reference_year_metrics.csv", index=False)

    gates = reference_gate_checks(ref, cfg, m, folds, years, paired)
    reference_metrics = {
        "strategy_severe": m,
        "strategy_normal": normal_m,
        "passive_vol_scaled_severe": passive_m,
        "buyhold_severe": buyhold_m,
        "paired_excess_vs_passive_severe": paired,
        "gates": gates,
    }
    write_json(outdir / "reference_metrics.json", reference_metrics)

    summary = dict(base)
    summary["reference"] = reference_metrics
    summary["diagnostic_2025_plus_evaluated"] = False
    summary["diagnostic_label"] = cfg["diagnostic_label"]

    if not gates["all"]:
        summary.update({"decision": REF_FAIL, "pass": False})
    else:
        # Only now is the 2025+ strategy ledger constructed/evaluated.
        monthly_full = build_monthly_strategy(h1, cfg)
        diag = monthly_full.loc[monthly_full["entry_utc"] >= ref_end].copy().reset_index(drop=True)
        diag.to_csv(outdir / "diagnostic_2025_plus_monthly_ledger.csv", index=False)
        dm = metrics(diag, "net_return_severe", cfg)
        dpass = metrics(diag, "passive_net_return_severe", cfg, "passive_")
        dpaired = paired_excess_metrics(diag, cfg, "net_return_severe", "passive_net_return_severe")
        dgates = diagnostic_gate_checks(diag, cfg, dm, dpaired)
        diagnostic = {
            "label": cfg["diagnostic_label"],
            "strategy_severe": dm,
            "passive_vol_scaled_severe": dpass,
            "paired_excess_vs_passive_severe": dpaired,
            "kill_gates": dgates,
        }
        write_json(outdir / "diagnostic_2025_plus_metrics.json", diagnostic)
        summary["counts"]["diagnostic_months_computed"] = int(len(diag))
        summary["diagnostic_2025_plus_evaluated"] = True
        summary["diagnostic_2025_plus"] = diagnostic
        if dgates["all"]:
            summary.update({"decision": REF_PASS_DIAG_PASS, "pass": True})
        else:
            summary.update({"decision": REF_PASS_DIAG_FAIL, "pass": False})

    write_json(outdir / "final_alpha_trend_summary.json", summary)
    decision_md = f"""# XAUUSD Final Alpha Trend Decision\n\n- Program: `{PROGRAM}`\n- Decision: `{summary['decision']}`\n- Reference months: `{summary['counts']['reference_eligible_months']}`\n- 2025+ diagnostic evaluated: `{summary['diagnostic_2025_plus_evaluated']}`\n- Paper/demo/live authorization: `false`\n\nThis campaign evaluates one pre-registered long-horizon trend specification only. No parameter grid, macro rescue, intraday filter, or holdout tuning is permitted.\n"""
    (outdir / "final_alpha_trend_decision.md").write_text(decision_md, encoding="utf-8")
    write_json(outdir / "RESULTS_MANIFEST.json", output_manifest(outdir, {"RESULTS_MANIFEST.json"}))
    return summary

def collect(root: Path, config_path: Path) -> Path:
    cfg = read_json(config_path)
    outdir = (root / cfg["output_dir"]).resolve()
    summary_path = outdir / "final_alpha_trend_summary.json"
    manifest_path = outdir / "RESULTS_MANIFEST.json"
    if not summary_path.is_file() or not manifest_path.is_file():
        raise CampaignError("completed run artifacts not found")
    manifest = read_json(manifest_path)
    for item in manifest.get("files", []):
        p = outdir / item["name"]
        if not p.is_file() or p.stat().st_size != int(item["size_bytes"]) or sha256_file(p) != item["sha256"]:
            raise CampaignError(f"manifest verification failed: {item['name']}")
    dest = Path.home() / "Downloads" / cfg["collect_name"]
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()
    with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for p in sorted(outdir.iterdir()):
            if p.is_file():
                z.write(p, p.name)
    return dest


def failure_record(root: Path, config_path: Path, stage: str, exc: Exception) -> None:
    try:
        cfg = read_json(config_path)
        p = root / "reports" / "xauusd_final_alpha_trend_failure.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        write_json(p, {
            "program": PROGRAM,
            "decision": FAIL_CLOSED,
            "pass": False,
            "stage": stage,
            "error": f"{type(exc).__name__}: {exc}",
            "generated_utc": datetime.now(timezone.utc).isoformat(),
            "authorization": cfg.get("execution_authorization", {}),
        })
    except Exception:
        pass


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["preflight", "run", "collect"])
    ap.add_argument("--root", default=".")
    ap.add_argument("--config", default="configs/xauusd_final_alpha_trend.json")
    ap.add_argument("--h1", default=None)
    args = ap.parse_args(argv)
    root = Path(args.root).expanduser().resolve()
    config_path = (root / args.config).resolve() if not Path(args.config).is_absolute() else Path(args.config)
    stage = args.command.upper()
    try:
        if args.command == "collect":
            dest = collect(root, config_path)
            print(json.dumps({"program": PROGRAM, "decision": "COLLECT_PASS", "output": str(dest)}, indent=2))
            return 0
        result = run_campaign(root, config_path, args.h1, args.command)
        print(json.dumps(result, indent=2, default=safe_scalar))
        if args.command == "preflight":
            return 0
        return 0 if result.get("decision") == REF_PASS_DIAG_PASS else 2
    except Exception as exc:
        failure_record(root, config_path, stage, exc)
        print(json.dumps({"program": PROGRAM, "decision": FAIL_CLOSED, "stage": stage, "error": f"{type(exc).__name__}: {exc}"}, indent=2), file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
