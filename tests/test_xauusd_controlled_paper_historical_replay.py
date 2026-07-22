from __future__ import annotations

import csv
import importlib.util
import json
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "app/xauusd_controlled_paper_historical_replay.py"
spec = importlib.util.spec_from_file_location("hist_replay_v5_source_proven", MODULE_PATH)
assert spec and spec.loader
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)
UTC = timezone.utc


class Bar:
    def __init__(self, ts: int, o: float = 2000.0, c: float = 2000.0):
        self.timestamp_ms = ts
        self.open = o
        self.close = c


def dt_ms(start: datetime, hours: int) -> int:
    return int((start + timedelta(hours=hours)).timestamp() * 1000)


def make_signal_row(
    start: datetime,
    bars: list[Bar],
    signal_index: int,
    *,
    side: str,
    gross_bps: float,
    status: str = "EVALUATED",
    spread_bps: float = 1.0,
    direction_metadata: str | None = None,
    research_gross_bps: float | None = None,
) -> dict[str, str]:
    entry_index = signal_index + 1
    exit_index = signal_index + 24
    entry_open = 2000.0 + signal_index * 0.001
    sign = 1.0 if side == "LONG" else -1.0
    exit_close = entry_open * (1.0 + sign * gross_bps / 10000.0)
    bars[entry_index].open = entry_open
    bars[exit_index].close = exit_close
    probability = 0.70 if side == "LONG" else 0.30
    direction = direction_metadata if direction_metadata is not None else ("1" if side == "LONG" else "0")
    normal_cost = max(3.0, spread_bps + 0.5)
    severe_cost = max(4.5, spread_bps * 1.5 + 2.0)
    research_gross = gross_bps if research_gross_bps is None else research_gross_bps
    stress8_cost = max(8.0, spread_bps + 4.0)
    stress10_cost = max(10.0, spread_bps + 6.0)
    signal = bars[signal_index].timestamp_ms
    entry = bars[entry_index].timestamp_ms
    exit_ = bars[exit_index].timestamp_ms
    return {
        "timestamp": str(signal),
        "dt": m.iso_utc(m.parse_timestamp(signal)),
        "source_period": "HOLDOUT",
        "fold": "F1",
        "direction": direction,
        "probability_up": str(probability),
        "resolution_hours": "24",
        "research_gross_bps": str(research_gross),
        "horizon_semantics": "ENTRY_H1_ROW_I_PLUS_1_EXIT_H1_ROW_I_PLUS_24",
        "entry_bucket_timestamp": str(entry),
        "exit_bucket_timestamp": str(exit_),
        "entry_bucket_utc": m.iso_utc(m.parse_timestamp(entry)),
        "exit_bucket_utc": m.iso_utc(m.parse_timestamp(exit_)),
        "status": status,
        "m5_gross_bps": str(gross_bps),
        "gross_transfer_difference_bps": str(gross_bps - research_gross),
        "entry_open": str(entry_open),
        "exit_close": str(exit_close),
        "observed_spread_bps": str(spread_bps),
        "normal_execution_cost_bps": str(normal_cost),
        "severe_execution_cost_bps": str(severe_cost),
        "normal_net_bps": str(gross_bps - normal_cost),
        "severe_net_bps": str(gross_bps - severe_cost),
        "stress_8bps_net_bps": str(gross_bps - stress8_cost),
        "stress_10bps_net_bps": str(gross_bps - stress10_cost),
    }


def build_fixture() -> tuple[datetime, list[Bar], list[dict[str, str]]]:
    start = datetime(2020, 1, 1, tzinfo=UTC)
    bars = [Bar(dt_ms(start, i)) for i in range(6000)]
    rows: list[dict[str, str]] = []
    gross_pattern = (24.0, -12.0, 18.0, -8.0, 32.0, -14.0)
    for j in range(146):
        side = "LONG" if j < 55 else "SHORT"
        # Reproduce the real V2 failure shape: the generic direction column
        # conflicts with executable probability-tail side on 93 rows.  It is
        # metadata and must not control the trade side.
        direction_metadata = "0" if j < 2 else "1"
        gross = gross_pattern[j % len(gross_pattern)]
        # Exact production discriminator shape: four rows have both a material
        # research/execution transfer difference and observed spread >10 bps.
        special = j in {37, 83, 85, 86}
        rows.append(
            make_signal_row(
                start,
                bars,
                j * 30,
                side=side,
                gross_bps=gross,
                spread_bps=12.5 if special else 1.0,
                research_gross_bps=(gross + 1.25) if special else gross,
                direction_metadata=direction_metadata,
            )
        )
    base = 146 * 30
    for j in range(19):
        rows.append(
            make_signal_row(
                start,
                bars,
                base + j * 30,
                side="LONG",
                gross_bps=10.0,
                status="SIGNAL_H1_TIMESTAMP_MISSING",
            )
        )
    base += 19 * 30
    for j in range(3):
        rows.append(
            make_signal_row(
                start,
                bars,
                base + j * 30,
                side="LONG",
                gross_bps=10.0,
                status="MISSING_COMPLETE_M5_BUCKET",
            )
        )
    return start, bars, rows


def summary_from_signals(signals: list[m.ReplaySignal]) -> dict:
    return {
        "candidate": "logistic__direction_24h",
        "signals_total": 168,
        "execution_evaluated_trades": 146,
        "execution_metrics": m.metric_block([s.normal_net_bps for s in signals]),
        "severe_execution_metrics": m.metric_block([s.severe_net_bps for s in signals]),
        "stress_8bps_metrics": m.metric_block([s.stress_8_net_bps for s in signals]),
        "stress_10bps_metrics": m.metric_block([s.stress_10_net_bps for s in signals]),
    }


def sample_signal(start: datetime, source_row: int = 2, *, side: str = "LONG", net: float = 10.0, spread: float = 1.0, signal_hour: int = 0, exit_hour: int = 24) -> m.ReplaySignal:
    probability = 0.7 if side == "LONG" else 0.3
    return m.ReplaySignal(
        source_row=source_row,
        signal_ms=dt_ms(start, signal_hour),
        signal_utc=m.iso_utc(m.parse_timestamp(dt_ms(start, signal_hour))),
        entry_ms=dt_ms(start, signal_hour + 1),
        entry_utc=m.iso_utc(m.parse_timestamp(dt_ms(start, signal_hour + 1))),
        exit_ms=dt_ms(start, exit_hour),
        exit_utc=m.iso_utc(m.parse_timestamp(dt_ms(start, exit_hour))),
        probability_up=probability,
        side=side,
        direction_metadata="1",
        observed_spread_bps=spread,
        execution_gross_bps=net + 3.0,
        normal_net_bps=net,
        severe_net_bps=net - 1.5,
        stress_8_net_bps=net - 5.0,
        stress_10_net_bps=net - 7.0,
        entry_open=2000.0,
        exit_close=2020.0,
        source_period="",
        fold="F1",
    )


class ReplayTests(unittest.TestCase):
    def setUp(self):
        self.start, self.bars, self.rows = build_fixture()

    def test_unevaluated_is_missing_not_evaluated(self):
        self.assertEqual(m.classify_status("UNEVALUATED"), "MISSING")
        self.assertEqual(m.classify_status("EVALUATED"), "EVALUATED")

    def test_canonical_rank_prefers_non_invalid(self):
        good = Path("reports/commercial_closure_sprint/commercial_closure_execution_ledger.csv")
        bad = Path("reports/commercial_closure_sprint_invalid_clock_horizon/x.csv")
        self.assertLess(m.canonical_rank(good), m.canonical_rank(bad))

    def test_bidirectional_146_rows_are_valid(self):
        signals, missing, validation = m.validate_and_build_signals(self.rows, self.bars)
        self.assertEqual(len(signals), 146)
        self.assertEqual(len(missing), 22)
        self.assertEqual(validation["evaluated_side_counts"], {"LONG": 55, "SHORT": 91})
        self.assertTrue(validation["bidirectional_probability_contract"]["pass"])
        self.assertEqual(
            validation["stress_cost_contract"]["detected_contract"],
            "EXECUTION_GROSS_FLOOR_OR_OBSERVED_SPREAD_PLUS_SLIPPAGE",
        )
        self.assertTrue(
            validation["stress_cost_contract"]["commercial_execution_parity_pass"]
        )

    def test_exact_four_rows_activate_spread_plus_slippage_branch(self):
        _, _, validation = m.validate_and_build_signals(self.rows, self.bars)
        contract = validation["stress_cost_contract"]
        self.assertEqual(contract["discriminating_row_count"], 4)
        self.assertEqual(
            contract["detected_contract"],
            "EXECUTION_GROSS_FLOOR_OR_OBSERVED_SPREAD_PLUS_SLIPPAGE",
        )
        self.assertTrue(contract["source_proven"])

    def test_naive_fixed_stress_on_one_high_spread_row_fails_closed(self):
        row = self.rows[37]
        gross = float(row["m5_gross_bps"])
        row["stress_8bps_net_bps"] = str(gross - 8.0)
        row["stress_10bps_net_bps"] = str(gross - 10.0)
        with self.assertRaises(m.ReplayError):
            m.validate_and_build_signals(self.rows, self.bars)

    def test_spread_only_floor_without_slippage_addon_fails_closed(self):
        row = self.rows[37]
        gross = float(row["m5_gross_bps"])
        spread = float(row["observed_spread_bps"])
        row["stress_8bps_net_bps"] = str(gross - max(8.0, spread))
        row["stress_10bps_net_bps"] = str(gross - max(10.0, spread))
        with self.assertRaises(m.ReplayError):
            m.validate_and_build_signals(self.rows, self.bars)

    def test_research_gross_basis_fails_closed(self):
        row = self.rows[37]
        research = float(row["research_gross_bps"])
        spread = float(row["observed_spread_bps"])
        row["stress_8bps_net_bps"] = str(research - max(8.0, spread + 4.0))
        row["stress_10bps_net_bps"] = str(research - max(10.0, spread + 6.0))
        with self.assertRaises(m.ReplayError):
            m.validate_and_build_signals(self.rows, self.bars)

    def test_unrecognized_stress_values_fail_closed(self):
        row = self.rows[37]
        row["stress_8bps_net_bps"] = "123.456"
        row["stress_10bps_net_bps"] = "120.123"
        with self.assertRaises(m.ReplayError):
            m.validate_and_build_signals(self.rows, self.bars)

    def test_original_91_short_regression_no_long_only_failure(self):
        signals, _, _ = m.validate_and_build_signals(self.rows, self.bars)
        shorts = [s for s in signals if s.side == "SHORT"]
        self.assertEqual(len(shorts), 91)
        self.assertTrue(all(s.probability_up <= 0.4 for s in shorts))

    def test_entry_mismatch_fails(self):
        self.rows[0]["entry_bucket_timestamp"] = str(dt_ms(self.start, 2))
        with self.assertRaises(m.ReplayError):
            m.validate_and_build_signals(self.rows, self.bars)

    def test_long_row_flipped_to_short_probability_fails_gross_parity(self):
        self.rows[0]["probability_up"] = "0.30"
        with self.assertRaises(m.ReplayError):
            m.validate_and_build_signals(self.rows, self.bars)

    def test_short_row_flipped_to_long_probability_fails_gross_parity(self):
        self.rows[55]["probability_up"] = "0.70"
        with self.assertRaises(m.ReplayError):
            m.validate_and_build_signals(self.rows, self.bars)

    def test_neutral_band_evaluated_row_fails(self):
        self.rows[55]["probability_up"] = "0.50"
        with self.assertRaises(m.ReplayError):
            m.validate_and_build_signals(self.rows, self.bars)

    def test_direction_metadata_does_not_control_execution_side(self):
        self.rows[55]["direction"] = "LONG"
        signals, _, validation = m.validate_and_build_signals(self.rows, self.bars)
        signal = [item for item in signals if item.source_row == 57][0]
        self.assertEqual(signal.side, "SHORT")
        self.assertEqual(signal.direction_metadata, "LONG")
        self.assertEqual(validation["execution_side_source"], "PROBABILITY_TAILS_ONLY")

    def test_exact_93_metadata_conflicts_are_diagnostic_only(self):
        signals, _, validation = m.validate_and_build_signals(self.rows, self.bars)
        self.assertEqual(len(signals), 146)
        self.assertEqual(
            validation["direction_metadata_vs_probability_side"],
            {"CONFLICT": 93, "MATCH": 53},
        )

    def test_commercial_reference_metric_parity(self):
        signals, _, _ = m.validate_and_build_signals(self.rows, self.bars)
        result = m.commercial_reference_parity(signals, summary_from_signals(signals))
        self.assertTrue(result["pass"])

    def test_commercial_reference_metric_mismatch_fails(self):
        signals, _, _ = m.validate_and_build_signals(self.rows, self.bars)
        summary = summary_from_signals(signals)
        summary["execution_metrics"]["trades"] = 145
        with self.assertRaises(m.ReplayError):
            m.commercial_reference_parity(signals, summary)

    def test_current_long_only_policy_is_not_reference_parity(self):
        signals, _, _ = m.validate_and_build_signals(self.rows, self.bars)
        diagnostic = m.current_forward_policy_diagnostic(signals, {"direction": "LONG_ONLY"})
        self.assertFalse(diagnostic["pass"])
        self.assertEqual(diagnostic["forward_policy_eligible_trade_count"], 55)
        self.assertEqual(diagnostic["excluded_reference_trade_count"], 91)

    def test_bidirectional_forward_policy_would_match_side_scope(self):
        signals, _, _ = m.validate_and_build_signals(self.rows, self.bars)
        diagnostic = m.current_forward_policy_diagnostic(signals, {"direction": "BIDIRECTIONAL"})
        self.assertTrue(diagnostic["pass"])
        self.assertEqual(diagnostic["forward_policy_eligible_trade_count"], 146)

    def test_concurrency_blocks_before_exit_and_no_early_pnl(self):
        a = sample_signal(self.start, 2, signal_hour=0, exit_hour=24, net=100.0)
        b = sample_signal(self.start, 3, signal_hour=2, exit_hour=26, net=100.0)
        track = m.TrackState("T", "REPORT_ONLY")
        track.process(a, True, "OK")
        self.assertEqual(track.equity, 1.0)
        track.process(b, True, "OK")
        self.assertEqual(track.rows[-1]["reason"], "MAX_CONCURRENT_POSITION_GUARD")
        self.assertEqual(track.equity, 1.0)
        track.finish()
        self.assertGreater(track.equity, 1.0)

    def test_spread_guard(self):
        signal = sample_signal(self.start, spread=10.0)
        track = m.TrackState("T", "REPORT_ONLY")
        track.process(signal, True, "OK")
        self.assertEqual(track.rows[-1]["reason"], "SPREAD_GUARD")

    def test_event_absent_strict_blocks_core_does_not(self):
        signal = sample_signal(self.start)
        strict = m.TrackState("S", "STRICT")
        core = m.TrackState("C", "REPORT_ONLY")
        strict.process(signal, False, "EVENT_DATA_ABSENT_FAIL_CLOSED")
        core.process(signal, False, "EVENT_DATA_ABSENT_FAIL_CLOSED")
        self.assertEqual(strict.rows[-1]["reason"], "EVENT_DATA_ABSENT_FAIL_CLOSED")
        self.assertEqual(len(core.active), 1)

    def test_daily_cap(self):
        track = m.TrackState("T", "REPORT_ONLY")
        first = sample_signal(self.start, 2, signal_hour=0, exit_hour=2)
        second = sample_signal(self.start, 3, signal_hour=3, exit_hour=5)
        track.process(first, True, "OK")
        track.process(second, True, "OK")
        self.assertEqual(track.rows[-1]["reason"], "DAILY_NEW_POSITION_CAP")

    def test_weekly_pause(self):
        track = m.TrackState("T", "REPORT_ONLY")
        week = self.start.isocalendar()
        track.weekly_pnl[f"{week.year}-W{week.week:02d}"] = -2.1
        track.process(sample_signal(self.start), True, "OK")
        self.assertEqual(track.rows[-1]["reason"], "WEEKLY_LOSS_PAUSE_ACTIVE")

    def test_hard_kill_blocks(self):
        track = m.TrackState("T", "REPORT_ONLY")
        track.hard_kill = True
        track.process(sample_signal(self.start), True, "OK")
        self.assertEqual(track.rows[-1]["reason"], "HARD_DRAWDOWN_KILL_SWITCH_ACTIVE")

    def test_profit_factor(self):
        self.assertAlmostEqual(m.profit_factor([10, -5, 5]), 3.0)

    def test_real_commercial_artifacts_tie_out_when_present(self):
        root = Path(__file__).resolve().parents[1]
        ledger_path = (
            root / "reports/commercial_closure_sprint/"
            "commercial_closure_execution_ledger.csv"
        )
        summary_path = (
            root / "reports/commercial_closure_sprint/"
            "commercial_closure_summary.json"
        )
        if not ledger_path.is_file() or not summary_path.is_file():
            self.skipTest("canonical commercial artifacts are not present")

        with ledger_path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        summary = json.loads(summary_path.read_text(encoding="utf-8"))

        evaluated = [
            row for row in rows
            if m.classify_status(row.get("status")) == "EVALUATED"
        ]
        missing = [
            row for row in rows
            if m.classify_status(row.get("status")) == "MISSING"
        ]
        self.assertEqual(len(rows), 168)
        self.assertEqual(len(evaluated), 146)
        self.assertEqual(len(missing), 22)

        side_counts = {"LONG": 0, "SHORT": 0}
        branch_count = 0
        signals = []
        for source_row, row in enumerate(rows, start=2):
            if m.classify_status(row.get("status")) != "EVALUATED":
                continue
            probability = float(row["probability_up"])
            side = m.side_from_probability(probability)
            self.assertIn(side, {"LONG", "SHORT"})
            side_counts[side] += 1
            sign = 1.0 if side == "LONG" else -1.0
            entry_open = float(row["entry_open"])
            exit_close = float(row["exit_close"])
            execution_gross = float(row["m5_gross_bps"])
            derived_gross = sign * (exit_close / entry_open - 1.0) * 10000.0
            self.assertAlmostEqual(derived_gross, execution_gross, places=8)

            observed = float(row["observed_spread_bps"])
            stress8 = float(row["stress_8bps_net_bps"])
            stress10 = float(row["stress_10bps_net_bps"])
            stress = m.source_proven_stress_contract(
                execution_gross,
                observed,
                stress8,
                stress10,
                tolerance_bps=1e-9,
            )
            self.assertTrue(stress["pass"], msg={"source_row": source_row, **stress})
            branch_count += int(stress["spread_plus_slippage_branch"])

            normal_cost = float(row["normal_execution_cost_bps"])
            severe_cost = float(row["severe_execution_cost_bps"])
            normal = float(row["normal_net_bps"])
            severe = float(row["severe_net_bps"])
            self.assertAlmostEqual(execution_gross - normal_cost, normal, places=9)
            self.assertAlmostEqual(execution_gross - severe_cost, severe, places=9)

            signal_ms = m.timestamp_ms(row["timestamp"])
            entry_ms = m.timestamp_ms(row["entry_bucket_timestamp"])
            exit_ms = m.timestamp_ms(row["exit_bucket_timestamp"])
            signals.append(
                m.ReplaySignal(
                    source_row=source_row,
                    signal_ms=signal_ms,
                    signal_utc=m.iso_utc(m.parse_timestamp(signal_ms)),
                    entry_ms=entry_ms,
                    entry_utc=m.iso_utc(m.parse_timestamp(entry_ms)),
                    exit_ms=exit_ms,
                    exit_utc=m.iso_utc(m.parse_timestamp(exit_ms)),
                    probability_up=probability,
                    side=side,
                    direction_metadata=m.normalize_direction_metadata(row.get("direction")),
                    observed_spread_bps=observed,
                    execution_gross_bps=execution_gross,
                    normal_net_bps=normal,
                    severe_net_bps=severe,
                    stress_8_net_bps=stress8,
                    stress_10_net_bps=stress10,
                    entry_open=entry_open,
                    exit_close=exit_close,
                    source_period=str(row.get("source_period") or ""),
                    fold=str(row.get("fold") or ""),
                )
            )

        self.assertEqual(side_counts, {"LONG": 55, "SHORT": 91})
        self.assertEqual(branch_count, 4)
        parity = m.commercial_reference_parity(signals, summary)
        self.assertTrue(parity["pass"])

    def test_no_execution_connector_tokens(self):
        text = MODULE_PATH.read_text(encoding="utf-8").lower()
        for token in ("ordersend", "place_order", "send_order", "initialize_terminal"):
            self.assertNotIn(token, text)


if __name__ == "__main__":
    unittest.main()
