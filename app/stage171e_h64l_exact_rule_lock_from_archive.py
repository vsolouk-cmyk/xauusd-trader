#!/usr/bin/env python3
"""Stage171E — H64L exact rule lock from archived evidence.

Read-only / no-order stage.

Purpose:
- Recover the exact H64L locked rule from archived Stage64/Stage66 artifacts.
- Prefer authoritative locked-rule configs over reconstructed expert-feedback rules.
- Produce a human-reviewable evidence table and exact-rule JSON.
- Do not scan thresholds, optimize, write MT5 signals, or authorize demo/live.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import glob
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

STAGE = "Stage171E_H64L_EXACT_RULE_LOCK_FROM_ARCHIVE"

CANONICAL_FEATURES = {
    "gold_sma20_over_50": {"op": ">", "threshold": 0.0},
    "dxy_ret_20d": {"op": "<", "threshold": 0.0},
    "real_yield_change_20d": {"op": "<", "threshold": 0.0},
    "etf_flow_tonnes_3m": {"op": ">", "threshold": 0.0},
}

DISALLOWED_TERMS = [
    "optimiz", "grid", "sweep", "threshold_search", "post_hoc", "post-hoc", "new_indicator", "GDELT_as_alpha"
]

PRIORITY_PATHS = [
    "archive/_local_archive_final_cleanup/configs_inactive/h64l_locked_rule_v2_stage66a3_exact_reconciled.json",
    "archive/_local_archive_final_cleanup/configs_inactive/h64l_locked_rule_v1.json",
    "archive/_local_archive_final_cleanup/configs_inactive/stage66a3_h64l_exact_match_rule_lock_resolver.json",
    "archive/_local_archive_final_cleanup/configs_inactive/stage66a2_h64l_reconstruction_reconciler.json",
    "archive/repo_cleanup_20260626/reports_inactive/stage66a3_h64l_exact_match_rule_lock_resolver/stage66a3_h64l_exact_match_rule_lock_resolver_summary.json",
    "archive/repo_cleanup_20260626/reports_inactive/stage66a3_h64l_exact_match_rule_lock_resolver/stage66a3_h64l_exact_match_rule_lock_resolver_report.md",
    "archive/repo_cleanup_20260626/reports_inactive/stage66a2_h64l_reconstruction_reconciler/stage66a2_h64l_reconstruction_reconciler_summary.json",
    "archive/repo_cleanup_20260626/reports_inactive/stage66a_h64l_concentration_audit/stage66a_h64l_active_events.json",
    "data/forward_shadow/stage65_macro_signal_ledger.csv",
]

GLOB_PATTERNS = [
    "archive/**/h64l*locked*.json",
    "archive/**/stage66a3*h64l*.json",
    "archive/**/stage66a2*h64l*.json",
    "archive/**/stage66a*h64l*summary.json",
    "archive/**/stage66a*h64l*report.md",
    "archive/**/stage64r*summary.json",
    "archive/**/stage64r*report.md",
    "reports/**/stage64r*summary.json",
    "reports/**/stage64r*report.md",
    "data/forward_shadow/*h64l*.csv",
    "data/forward_shadow/*macro_signal_ledger*.csv",
]


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path, chunk: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def safe_read_text(path: Path, max_bytes: int = 2_000_000) -> str:
    try:
        with path.open("rb") as f:
            data = f.read(max_bytes)
        return data.decode("utf-8", errors="replace")
    except Exception as e:  # pragma: no cover
        return f"__READ_ERROR__ {type(e).__name__}: {e}"


def try_load_json(path: Path) -> Tuple[Optional[Any], Optional[str]]:
    try:
        return json.loads(safe_read_text(path, max_bytes=10_000_000)), None
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


def flatten_json(obj: Any, prefix: str = "") -> Iterable[Tuple[str, Any]]:
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{prefix}.{k}" if prefix else str(k)
            yield from flatten_json(v, p)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            p = f"{prefix}[{i}]"
            yield from flatten_json(v, p)
    else:
        yield prefix, obj


def detect_condition_mentions(text: str) -> Dict[str, bool]:
    t = text.lower()
    out = {}
    for feat in CANONICAL_FEATURES:
        out[feat] = feat.lower() in t
    return out


def extract_condition_strings(text: str) -> List[str]:
    # Extract lines / JSON values that contain canonical features and possible comparisons.
    candidates: List[str] = []
    for feat in CANONICAL_FEATURES:
        # direct comparisons such as dxy_ret_20d < 0, or ledger style dxy_ret_20d:0.01<0.0
        patterns = [
            rf"{re.escape(feat)}\s*[>:<]=?\s*-?\d+(?:\.\d+)?",
            rf"{re.escape(feat)}\s*:\s*[^;\n\r,]+[<>]=?\s*-?\d+(?:\.\d+)?",
        ]
        for pat in patterns:
            for m in re.finditer(pat, text, flags=re.IGNORECASE):
                s = m.group(0).strip()
                if s not in candidates:
                    candidates.append(s)
    # Also capture semicolon-delimited ledger condition blocks.
    for m in re.finditer(r"(?:gold_sma20_over_50|dxy_ret_20d|real_yield_change_20d|etf_flow_tonnes_3m)[^\n\r]{0,260}", text, flags=re.IGNORECASE):
        s = m.group(0).strip()
        if any(f in s for f in CANONICAL_FEATURES) and s not in candidates:
            candidates.append(s[:500])
    return candidates[:50]


def infer_op_threshold_from_text(text: str, feat: str) -> Tuple[Optional[str], Optional[float]]:
    # Prefer exact canonical expressions, but accept ledger "feature:value<0.0" style.
    pats = [
        rf"{re.escape(feat)}\s*(>=|<=|>|<|==)\s*(-?\d+(?:\.\d+)?)",
        rf"{re.escape(feat)}\s*:\s*[^;\n\r,]+\s*(>=|<=|>|<|==)\s*(-?\d+(?:\.\d+)?)",
    ]
    for pat in pats:
        m = re.search(pat, text, flags=re.IGNORECASE)
        if m:
            try:
                return m.group(1), float(m.group(2))
            except Exception:
                return m.group(1), None
    return None, None


def summarize_artifact(path: Path, root: Path, priority: int) -> Dict[str, Any]:
    rel = str(path.relative_to(root)) if path.is_relative_to(root) else str(path)
    exists = path.exists()
    row: Dict[str, Any] = {
        "priority": priority,
        "path": rel,
        "exists": exists,
        "suffix": path.suffix.lower(),
        "size_bytes": path.stat().st_size if exists else None,
        "sha256": sha256_file(path) if exists and path.is_file() else None,
        "parse_status": "NOT_READ",
        "h64l_mentions": 0,
        "all_four_feature_terms_present": False,
        "condition_strings": "",
        "disallowed_term_hits": "",
        "evidence_strength": "NONE",
    }
    if not exists or not path.is_file():
        return row
    text = ""
    if path.suffix.lower() == ".json":
        obj, err = try_load_json(path)
        if err:
            text = safe_read_text(path)
            row["parse_status"] = f"JSON_PARSE_FAIL:{err}"
        else:
            row["parse_status"] = "JSON_OK"
            flat_bits = []
            for k, v in flatten_json(obj):
                if isinstance(v, (str, int, float, bool)) or v is None:
                    flat_bits.append(f"{k}={v}")
            text = "\n".join(flat_bits)[:2_000_000]
    else:
        text = safe_read_text(path)
        row["parse_status"] = "TEXT_OK"
    lower = text.lower()
    row["h64l_mentions"] = lower.count("h64l")
    mentions = detect_condition_mentions(text)
    row.update({f"mentions_{k}": v for k, v in mentions.items()})
    row["all_four_feature_terms_present"] = all(mentions.values())
    conds = extract_condition_strings(text)
    row["condition_strings"] = " | ".join(conds[:12])
    disallowed = sorted({term for term in DISALLOWED_TERMS if term.lower() in lower})
    row["disallowed_term_hits"] = ";".join(disallowed)
    name = path.name.lower()
    if "locked_rule_v2" in name or "exact_reconciled" in name:
        row["evidence_strength"] = "AUTHORITATIVE_LOCKED_RULE_V2_NAME"
    elif "locked_rule_v1" in name:
        row["evidence_strength"] = "AUTHORITATIVE_LOCKED_RULE_V1_NAME"
    elif "exact_match_rule_lock" in name:
        row["evidence_strength"] = "EXACT_MATCH_RESOLVER"
    elif row["all_four_feature_terms_present"]:
        row["evidence_strength"] = "ALL_FEATURE_TERMS_PRESENT"
    elif row["h64l_mentions"]:
        row["evidence_strength"] = "H64L_MENTION_ONLY"
    return row


def collect_artifacts(root: Path) -> List[Path]:
    seen: Dict[str, Path] = {}
    for rel in PRIORITY_PATHS:
        p = root / rel
        if p.exists():
            seen[str(p.resolve())] = p
    for pat in GLOB_PATTERNS:
        for s in glob.glob(str(root / pat), recursive=True):
            p = Path(s)
            if p.is_file():
                seen[str(p.resolve())] = p
    # Deterministic order: priority list first, then rest lexicographic.
    priority_resolved = [str((root / rel).resolve()) for rel in PRIORITY_PATHS]
    def key(p: Path) -> Tuple[int, str]:
        r = str(p.resolve())
        return (priority_resolved.index(r) if r in priority_resolved else 9999, str(p))
    return sorted(seen.values(), key=key)


def select_authoritative_rule(rows: List[Dict[str, Any]], root: Path) -> Dict[str, Any]:
    def score(row: Dict[str, Any]) -> int:
        s = 0
        if row["evidence_strength"] == "AUTHORITATIVE_LOCKED_RULE_V2_NAME":
            s += 100
        elif row["evidence_strength"] == "AUTHORITATIVE_LOCKED_RULE_V1_NAME":
            s += 80
        elif row["evidence_strength"] == "EXACT_MATCH_RESOLVER":
            s += 65
        elif row["evidence_strength"] == "ALL_FEATURE_TERMS_PRESENT":
            s += 40
        elif row["evidence_strength"] == "H64L_MENTION_ONLY":
            s += 10
        if row.get("all_four_feature_terms_present"):
            s += 30
        if not row.get("disallowed_term_hits"):
            s += 5
        if row.get("parse_status") == "JSON_OK":
            s += 5
        return s
    candidates = [r for r in rows if r.get("exists") and r.get("evidence_strength") != "NONE"]
    candidates.sort(key=lambda r: (-score(r), int(r.get("priority", 9999))))
    best = candidates[0] if candidates else None
    conditions: List[Dict[str, Any]] = []
    exact_features = True
    source_text = ""
    if best:
        p = root / best["path"]
        if p.exists():
            if p.suffix.lower() == ".json":
                obj, _ = try_load_json(p)
                if obj is not None:
                    source_text = "\n".join([f"{k}={v}" for k, v in flatten_json(obj) if isinstance(v, (str, int, float, bool)) or v is None])
                else:
                    source_text = safe_read_text(p)
            else:
                source_text = safe_read_text(p)
    for feat, canonical in CANONICAL_FEATURES.items():
        op, th = infer_op_threshold_from_text(source_text, feat)
        if op is None or th is None:
            # fallback: use canonical candidate but mark as not exact from artifact.
            op = canonical["op"]
            th = canonical["threshold"]
            exact_features = False
        conditions.append({
            "feature": feat,
            "operator": op,
            "threshold": th,
            "canonical_operator": canonical["op"],
            "canonical_threshold": canonical["threshold"],
            "matches_canonical_feedback": bool(op == canonical["op"] and float(th) == float(canonical["threshold"])),
        })
    locked = bool(best and best.get("evidence_strength") in {"AUTHORITATIVE_LOCKED_RULE_V2_NAME", "AUTHORITATIVE_LOCKED_RULE_V1_NAME"} and all(c["matches_canonical_feedback"] for c in conditions) and not best.get("disallowed_term_hits"))
    return {
        "selected_evidence_path": best["path"] if best else None,
        "selected_evidence_strength": best["evidence_strength"] if best else "NONE",
        "selected_evidence_sha256": best.get("sha256") if best else None,
        "exact_rule_locked": locked,
        "exact_rule_lock_confidence": "HIGH_FROM_ARCHIVED_LOCKED_RULE" if locked else ("MEDIUM_AUTHORITATIVE_ARTIFACT_NEEDS_HUMAN_REVIEW" if best else "LOW_NO_AUTHORITY_FOUND"),
        "conditions": conditions,
        "notes": [
            "No threshold optimization was performed.",
            "Only archived locked-rule evidence and canonical H64L feedback conditions were used.",
            "If exact_rule_locked is false, treat H64L bridge as blocked pending human review of selected evidence.",
        ],
    }


def write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    keys: List[str] = []
    for r in rows:
        for k in r.keys():
            if k not in keys:
                keys.append(k)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def render_md(summary: Dict[str, Any], rule: Dict[str, Any], rows: List[Dict[str, Any]]) -> str:
    md = []
    md.append("# Stage171E H64L Exact Rule Lock From Archive\n")
    md.append(f"Generated UTC: `{summary['generated_utc']}`\n")
    md.append(f"Decision: `{summary['decision']}`  \n")
    md.append(f"Recommended action: `{summary['recommended_action']}`\n")
    md.append("## Scope\n")
    md.append("Read-only evidence recovery. No scan, no threshold optimization, no MT5 signal, no order, no demo/live authorization.\n")
    md.append("## Rule-lock result\n")
    md.append(f"- Exact rule locked: `{rule['exact_rule_locked']}`\n")
    md.append(f"- Confidence: `{rule['exact_rule_lock_confidence']}`\n")
    md.append(f"- Selected evidence: `{rule['selected_evidence_path']}`\n")
    md.append(f"- Evidence strength: `{rule['selected_evidence_strength']}`\n")
    md.append("\n## Conditions\n")
    md.append("| feature | operator | threshold | matches canonical feedback |\n|---|---:|---:|---:|\n")
    for c in rule["conditions"]:
        md.append(f"| {c['feature']} | {c['operator']} | {c['threshold']} | {c['matches_canonical_feedback']} |\n")
    md.append("\n## Top evidence artifacts\n")
    md.append("| path | strength | all four features | parse |\n|---|---:|---:|---:|\n")
    for r in rows[:12]:
        md.append(f"| `{r['path']}` | {r['evidence_strength']} | {r['all_four_feature_terms_present']} | {r['parse_status']} |\n")
    md.append("\n## Next\n")
    if rule["exact_rule_locked"]:
        md.append("Continue daily Stage171D shadow logging. Do not bridge until a real shadow hit occurs and specialist approves limited 0.01-lot demo bridge review.\n")
    else:
        md.append("Review the selected archived evidence manually. Continue daily Stage171D shadow logging, but do not bridge to demo. If the rule cannot be confirmed inside the timebox, mark H64L rescue INCONCLUSIVE.\n")
    return "".join(md)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--stage171d-summary", default=None)
    ap.add_argument("--stage171b-rule-candidate", default=None)
    ap.add_argument("--output-dir", default=None)
    args = ap.parse_args(argv)

    root = Path(args.root).expanduser().resolve()
    out_dir = Path(args.output_dir).expanduser().resolve() if args.output_dir else root / "reports" / "stage171e_h64l_exact_rule_lock_from_archive"
    out_dir.mkdir(parents=True, exist_ok=True)

    paths = collect_artifacts(root)
    rows = [summarize_artifact(p, root, i) for i, p in enumerate(paths)]
    # Sort by evidence strength priority and priority index for output.
    strength_rank = {
        "AUTHORITATIVE_LOCKED_RULE_V2_NAME": 0,
        "AUTHORITATIVE_LOCKED_RULE_V1_NAME": 1,
        "EXACT_MATCH_RESOLVER": 2,
        "ALL_FEATURE_TERMS_PRESENT": 3,
        "H64L_MENTION_ONLY": 4,
        "NONE": 9,
    }
    rows.sort(key=lambda r: (strength_rank.get(r["evidence_strength"], 9), int(r["priority"]), r["path"]))
    rule = select_authoritative_rule(rows, root)

    decision = "STAGE171E_H64L_EXACT_RULE_LOCK_CONFIRMED_CONTINUE_SHADOW_NO_ORDER" if rule["exact_rule_locked"] else "STAGE171E_H64L_RULE_EVIDENCE_FOUND_BUT_HUMAN_CONFIRMATION_REQUIRED_NO_ORDER"
    recommended = "CONTINUE_STAGE171D_SHADOW_LOGGING; NO_ORDER; WAIT_FOR_REAL_SHADOW_HIT_AND_SPECIALIST_APPROVAL" if rule["exact_rule_locked"] else "CONTINUE_STAGE171D_SHADOW_LOGGING; NO_ORDER; HUMAN_REVIEW_ARCHIVED_RULE_EVIDENCE_WITHIN_TIMEBOX"
    summary = {
        "stage": STAGE,
        "generated_utc": utc_now(),
        "root": str(root),
        "order_routing_allowed": False,
        "demo_release_allowed": False,
        "status": "STAGE171E_COMPLETE_READONLY_RULE_EVIDENCE_RECOVERY",
        "decision": decision,
        "recommended_action": recommended,
        "artifact_count": len(rows),
        "authoritative_locked_rule_candidates": sum(1 for r in rows if r["evidence_strength"].startswith("AUTHORITATIVE")),
        "exact_rule_locked": rule["exact_rule_locked"],
        "exact_rule_lock_confidence": rule["exact_rule_lock_confidence"],
        "selected_evidence_path": rule["selected_evidence_path"],
        "hard_constraints": {
            "threshold_reoptimization_allowed": False,
            "orders_allowed": False,
            "manual_shadow_continues": True,
            "gdelt_news_guard_only": True,
        },
        "outputs": {
            "summary_json": str(out_dir / "stage171e_h64l_exact_rule_lock_summary.json"),
            "decision_md": str(out_dir / "stage171e_decision.md"),
            "locked_rule_json": str(out_dir / "stage171e_h64l_exact_locked_rule.json"),
            "evidence_table_csv": str(out_dir / "stage171e_h64l_locked_rule_evidence_table.csv"),
        },
        "next": [
            "Continue daily Stage171D shadow logging; log-only, no orders.",
            "If exact_rule_locked is true, wait for a real H64L shadow hit and request specialist approval for limited 0.01-lot demo bridge review.",
            "If exact_rule_locked is false, manually review selected archived evidence inside the timebox; otherwise mark H64L INCONCLUSIVE.",
        ],
    }

    write_csv(out_dir / "stage171e_h64l_locked_rule_evidence_table.csv", rows)
    (out_dir / "stage171e_h64l_exact_locked_rule.json").write_text(json.dumps(rule, indent=2, ensure_ascii=False), encoding="utf-8")
    (out_dir / "stage171e_h64l_exact_rule_lock_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    (out_dir / "stage171e_decision.md").write_text(render_md(summary, rule, rows), encoding="utf-8")

    print(json.dumps({"decision": decision, "exact_rule_locked": rule["exact_rule_locked"], "selected_evidence_path": rule["selected_evidence_path"], "output_dir": str(out_dir)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
