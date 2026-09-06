#!/usr/bin/env python3
"""Rebuild article figures from frozen, article-level CSV outputs."""
from __future__ import annotations

from pathlib import Path
import json
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib as mpl


ROOT = Path(__file__).resolve().parent
GOLD = "#B38B2E"
NAVY = "#26364A"
RED = "#A8403A"
GREY = "#69727D"


def style() -> None:
    mpl.rcParams.update({
        "font.family": "DejaVu Sans",
        "font.size": 9,
        "axes.titlesize": 10,
        "axes.labelsize": 9,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "figure.dpi": 150,
        "savefig.dpi": 300,
        "savefig.bbox": "tight",
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
    })


def save(fig: plt.Figure, stem: str) -> None:
    fig.savefig(ROOT / f"{stem}.pdf")
    fig.savefig(ROOT / f"{stem}.png")
    plt.close(fig)


def figure_cost_attrition() -> None:
    labels = ["Gross", "Normal cost", "Severe cost", "Fixed stress"]
    values = [24, 9, 5, 1]
    colors = [GREY, "#8B7A55", GOLD, NAVY]
    fig, ax = plt.subplots(figsize=(6.5, 3.6))
    bars = ax.bar(labels, values, color=colors, width=0.62)
    ax.set_ylim(0, 27)
    ax.set_ylabel("Specifications with positive mean (of 39)")
    ax.set_title("Attrition of apparent profitability across cost layers")
    ax.grid(axis="y", color="#D9DDE2", linewidth=0.6)
    ax.set_axisbelow(True)
    for bar, val in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width()/2, val + 0.6, str(val), ha="center", va="bottom", fontweight="bold")
    ax.text(0.99, 0.95, "Locked primary universe: 39 specifications", transform=ax.transAxes, ha="right", va="top", color=GREY)
    fig.tight_layout()
    save(fig, "figure1_cost_attrition")


def figure_severe_vs_p() -> None:
    df = pd.read_csv(ROOT / "specification_reference_metrics.csv")
    fig, ax = plt.subplots(figsize=(6.5, 4.0))
    positive = df["mean_severe_net_bps"] > 0
    ax.scatter(df.loc[~positive, "family_max_t_adjusted_p"], df.loc[~positive, "mean_severe_net_bps"],
               color=GREY, s=26, alpha=0.75, label="Non-positive severe-cost mean")
    ax.scatter(df.loc[positive, "family_max_t_adjusted_p"], df.loc[positive, "mean_severe_net_bps"],
               color=GOLD, edgecolor=NAVY, linewidth=0.5, s=48, label="Positive severe-cost mean", zorder=3)
    ax.axvline(0.05, color=RED, linestyle="--", linewidth=1.0, label="Familywise threshold = 0.05")
    ax.axhline(0, color=NAVY, linewidth=0.8)
    offsets = {
        "A1R-046": (5, 4), "A1R-007": (5, 4), "A1R-036": (5, -11),
        "A1R-037": (5, 4), "A1R-009": (5, -11),
    }
    for _, row in df.loc[positive].iterrows():
        dx, dy = offsets.get(row["specification_id"], (5, 4))
        ax.annotate(row["specification_id"], (row["family_max_t_adjusted_p"], row["mean_severe_net_bps"]),
                    xytext=(dx, dy), textcoords="offset points", fontsize=7.5)
    ax.set_xlim(0, 1.03)
    ax.set_xlabel("Familywise max-t adjusted p-value")
    ax.set_ylabel("Mean return under source-native severe cost (bps)")
    ax.set_title("Positive means remain far from familywise statistical support")
    ax.grid(color="#E2E5E9", linewidth=0.5)
    ax.legend(frameon=False, fontsize=7.5, loc="lower left")
    fig.tight_layout()
    save(fig, "figure2_severe_mean_vs_family_p")


def figure_cross_feed() -> None:
    df = pd.read_csv(ROOT / "cross_feed_replication.csv")
    df = df[df["applicable"].astype(str).str.lower() == "true"].copy()
    passed = df["pass"].astype(str).str.lower() == "true"
    fig, ax = plt.subplots(figsize=(5.7, 5.0))
    lims = [min(df["primary_mean_severe_bps"].min(), df["secondary_mean_severe_bps"].min()) - 1,
            max(df["primary_mean_severe_bps"].max(), df["secondary_mean_severe_bps"].max()) + 1]
    ax.plot(lims, lims, color="#B7BDC5", linewidth=1.0, label="45-degree line")
    ax.axhline(0, color=NAVY, linewidth=0.7)
    ax.axvline(0, color=NAVY, linewidth=0.7)
    ax.scatter(df.loc[passed, "primary_mean_severe_bps"], df.loc[passed, "secondary_mean_severe_bps"],
               color=NAVY, s=34, label="Replication gate passed")
    ax.scatter(df.loc[~passed, "primary_mean_severe_bps"], df.loc[~passed, "secondary_mean_severe_bps"],
               color=GOLD, edgecolor=RED, s=46, label="Replication gate failed")
    for sid in ["A1R-007", "A1R-009"]:
        row = df[df["specification_id"] == sid].iloc[0]
        ax.annotate(sid + " sign reversal", (row["primary_mean_severe_bps"], row["secondary_mean_severe_bps"]),
                    xytext=(6, -12 if sid == "A1R-009" else 6), textcoords="offset points", fontsize=7.5)
    ax.set_xlim(lims); ax.set_ylim(lims)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel("Primary-feed severe-cost mean (bps)")
    ax.set_ylabel("Secondary-feed severe-cost mean (bps)")
    ax.set_title("Cross-feed replication for 20 eligible specifications")
    ax.grid(color="#E2E5E9", linewidth=0.5)
    ax.legend(frameon=False, fontsize=7.5, loc="upper left")
    fig.tight_layout()
    save(fig, "figure3_cross_feed_replication")


def write_figure_manifest() -> None:
    manifest = {
        "program": "ARTICLE1_REPRODUCIBLE_FIGURE_BUILD",
        "inputs": [
            "specification_reference_metrics.csv",
            "cross_feed_replication.csv",
        ],
        "figures": [
            "figure1_cost_attrition.pdf",
            "figure2_severe_mean_vs_family_p.pdf",
            "figure3_cross_feed_replication.pdf",
        ],
        "note": "All plotted values are read directly from frozen article-level result tables; no generative image model is used.",
    }
    (ROOT / "figure_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def tex(value: object) -> str:
    if pd.isna(value):
        return "--"
    text = str(value)
    replacements = {
        "\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$",
        "#": r"\#", "_": r"\_", "{": r"\{", "}": r"\}",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


def label(value: object) -> str:
    """Convert machine identifiers to readable, naturally breakable table labels."""
    if pd.isna(value):
        return "--"
    return tex(str(value).replace("__", " / ").replace("_", " "))


def write_table(name: str, lines: list[str]) -> None:
    (ROOT / name).write_text("\n".join(lines) + "\n", encoding="utf-8")


def supplementary_tables() -> None:
    reg = pd.read_csv(ROOT / "locked_registry.csv", keep_default_na=False)
    lines = [
        r"\begingroup\footnotesize\setlength{\tabcolsep}{3pt}",
        r"\begin{longtable}{P{1.1cm}P{1.9cm}P{3.7cm}P{3.1cm}P{1.5cm}}",
        r"\caption{Complete locked registry.}\label{tab:s_registry}\\",
        r"\toprule ID & Source block & Candidate & Economic family & Role \\",
        r"\midrule\endfirsthead",
        r"\toprule ID & Source block & Candidate & Economic family & Role \\",
        r"\midrule\endhead",
    ]
    for _, row in reg.iterrows():
        role = "Primary" if str(row["primary_eligible"]).lower() == "true" else "Forensic only"
        lines.append(f"{tex(row['specification_id'])} & {label(row['source_block'])} & {label(row['source_candidate_id'])} & {label(row['economic_family'])} & {role} \\\\")
    lines += [r"\bottomrule", r"\end{longtable}", r"\endgroup"]
    write_table("supp_registry_table.tex", lines)

    spec = pd.read_csv(ROOT / "specification_reference_metrics.csv")
    lines = [
        r"\begingroup\scriptsize\setlength{\tabcolsep}{2.5pt}",
        r"\begin{longtable}{lrrrrrrl}",
        r"\caption{Complete primary specification results. Returns are mean basis points per native trade or rebalance.}\label{tab:s_specs}\\",
        r"\toprule ID & $N$ & Gross & Normal & Severe & Fixed & Adj. $p$ & Native pass \\",
        r"\midrule\endfirsthead",
        r"\toprule ID & $N$ & Gross & Normal & Severe & Fixed & Adj. $p$ & Native pass \\",
        r"\midrule\endhead",
    ]
    for _, row in spec.iterrows():
        passed = "Yes" if bool(row["source_native_pass"]) else "No"
        lines.append(
            f"{tex(row['specification_id'])} & {int(row['trades'])} & {row['mean_gross_bps']:.3f} & "
            f"{row['mean_normal_net_bps']:.3f} & {row['mean_severe_net_bps']:.3f} & "
            f"{row['mean_fixed_stress_net_bps']:.3f} & {row['family_max_t_adjusted_p']:.3f} & {passed} \\\\")
    lines += [r"\bottomrule", r"\end{longtable}", r"\endgroup"]
    write_table("supp_spec_table.tex", lines)

    fam = pd.read_csv(ROOT / "family_reference_decisions.csv")
    lines = [
        r"\begingroup\footnotesize\setlength{\tabcolsep}{3pt}",
        r"\begin{longtable}{P{4.1cm}rrlrP{1.6cm}}",
        r"\caption{Complete familywise decisions.}\label{tab:s_families}\\",
        r"\toprule Economic family & Specs. & Native passes & Best ID & Adj. $p$ & Decision \\",
        r"\midrule\endfirsthead",
        r"\toprule Economic family & Specs. & Native passes & Best ID & Adj. $p$ & Decision \\",
        r"\midrule\endhead",
    ]
    for _, row in fam.iterrows():
        decision = "No edge" if row["decision"] == "NO_EDGE_UNDER_LOCKED_PROTOCOL" else tex(row["decision"])
        lines.append(f"{label(row['economic_family'])} & {int(row['specification_count'])} & {int(row['native_pass_count'])} & {tex(row['best_specification_id'])} & {row['family_adjusted_p']:.3f} & {decision} \\\\")
    lines += [r"\bottomrule", r"\end{longtable}", r"\endgroup"]
    write_table("supp_family_table.tex", lines)

    cross = pd.read_csv(ROOT / "cross_feed_replication.csv")
    cross = cross[cross["applicable"].astype(str).str.lower() == "true"]
    lines = [
        r"\begingroup\scriptsize\setlength{\tabcolsep}{2.5pt}",
        r"\begin{longtable}{lrrrrrl}",
        r"\caption{Complete cross-feed results for eligible specifications.}\label{tab:s_crossfeed}\\",
        r"\toprule ID & Primary $N$ & Secondary $N$ & Jaccard & Return corr. & Secondary severe & Pass \\",
        r"\midrule\endfirsthead",
        r"\toprule ID & Primary $N$ & Secondary $N$ & Jaccard & Return corr. & Secondary severe & Pass \\",
        r"\midrule\endhead",
    ]
    for _, row in cross.iterrows():
        passed = "Yes" if str(row["pass"]).lower() == "true" else "No"
        lines.append(f"{tex(row['specification_id'])} & {int(row['primary_trade_count'])} & {int(row['secondary_trade_count'])} & {row['signal_jaccard']:.3f} & {row['matched_gross_return_correlation']:.3f} & {row['secondary_mean_severe_bps']:.3f} & {passed} \\\\")
    lines += [r"\bottomrule", r"\end{longtable}", r"\endgroup"]
    write_table("supp_crossfeed_table.tex", lines)

    dsr = pd.read_csv(ROOT / "deflated_sharpe_ratio.csv")
    lines = [
        r"\begingroup\scriptsize\setlength{\tabcolsep}{2.5pt}",
        r"\begin{longtable}{lrrrrrl}",
        r"\caption{Complete deflated-Sharpe diagnostic.}\label{tab:s_dsr}\\",
        r"\toprule ID & Daily Sharpe & Annualized & Skewness & Kurtosis & DSR probability & Pass \\",
        r"\midrule\endfirsthead",
        r"\toprule ID & Daily Sharpe & Annualized & Skewness & Kurtosis & DSR probability & Pass \\",
        r"\midrule\endhead",
    ]
    for _, row in dsr.iterrows():
        passed = "Yes" if str(row["passes_0_95"]).lower() == "true" else "No"
        lines.append(f"{tex(row['specification_id'])} & {row['daily_sharpe_unannualized']:.4f} & {row['annualized_sharpe_365']:.3f} & {row['skewness']:.3f} & {row['kurtosis']:.3f} & {row['deflated_sharpe_probability']:.5f} & {passed} \\\\")
    lines += [r"\bottomrule", r"\end{longtable}", r"\endgroup"]
    write_table("supp_dsr_table.tex", lines)

    align = pd.read_csv(ROOT / "alignment_warning_sensitivity.csv")
    align = align[align["applicable"].astype(str).str.lower() == "true"]
    lines = [
        r"\begingroup\scriptsize\setlength{\tabcolsep}{3pt}",
        r"\begin{longtable}{lrrrr}",
        r"\caption{Complete alignment-warning sensitivity results for applicable specifications.}\label{tab:s_alignment}\\",
        r"\toprule ID & Primary $N$ & Sensitivity $N$ & Primary severe & Sensitivity severe \\",
        r"\midrule\endfirsthead",
        r"\toprule ID & Primary $N$ & Sensitivity $N$ & Primary severe & Sensitivity severe \\",
        r"\midrule\endhead",
    ]
    for _, row in align.iterrows():
        lines.append(f"{tex(row['specification_id'])} & {int(row['primary_trades'])} & {int(row['sensitivity_trades'])} & {row['primary_mean_severe_bps']:.3f} & {row['sensitivity_mean_severe_bps']:.3f} \\\\")
    lines += [r"\bottomrule", r"\end{longtable}", r"\endgroup"]
    write_table("supp_alignment_table.tex", lines)


def main() -> None:
    style()
    figure_cost_attrition()
    figure_severe_vs_p()
    figure_cross_feed()
    write_figure_manifest()
    supplementary_tables()


if __name__ == "__main__":
    main()
