import json
import subprocess
import sys
from pathlib import Path

import pandas as pd


def test_family_key_from_rule_id():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
    import stage159_locked_family_repair_discovery as s
    assert s.family_key_from_rule_id("D150C_M5_ret_3h_bps_GEQ35__trend_50_100_bps_LEQ65") == "D150C_M5_ret_3h_bps__trend_50_100_bps"


def test_parse_conditions():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
    import stage159_locked_family_repair_discovery as s
    conds = s.parse_conditions('[{"feature":"ret_3h_bps","op":">=","threshold":1.5}]')
    assert conds[0]["feature"] == "ret_3h_bps"


def test_stage159_smoke(tmp_path):
    root = tmp_path
    bars = tmp_path / "bars.tsv"
    rows = []
    t = pd.Timestamp("2026-01-01 00:00:00", tz="UTC")
    price = 1000.0
    for i in range(420):
        price += 0.1
        rows.append([t.strftime("%Y.%m.%d"), t.strftime("%H:%M:%S"), price, price + 0.2, price - 0.2, price, 100, 0, 30])
        t += pd.Timedelta(minutes=5)
    pd.DataFrame(rows).to_csv(bars, sep="\t", header=False, index=False)

    score = tmp_path / "scores.csv"
    pd.DataFrame([
        {
            "rule_id": "D150C_M5_ret_3h_bps_GEQ35__trend_50_100_bps_GEQ35",
            "conditions_json": json.dumps([
                {"feature": "ret_3h_bps", "op": ">=", "threshold": -9999},
                {"feature": "trend_50_100_bps", "op": ">=", "threshold": -9999},
            ]),
            "status": "PASS",
        }
    ]).to_csv(score, index=False)
    risk = tmp_path / "risk.json"
    risk.write_text(json.dumps({"per_family": []}))

    script = Path(__file__).resolve().parents[1] / "app" / "stage159_locked_family_repair_discovery.py"
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--root",
            str(root),
            "--bars-m5",
            str(bars),
            "--score-csv",
            str(score),
            "--risk-summary",
            str(risk),
            "--timestamp-shift-hours",
            "0",
            "--min-events",
            "3",
            "--min-positive-folds",
            "1",
            "--min-session-positive",
            "1",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    out = json.loads(result.stdout)
    assert out["bar_count"] == 420
    assert out["candidate_rows_scored"] == 1
    assert Path(out["candidate_scores_csv"]).exists()
