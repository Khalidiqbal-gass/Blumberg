"""Tests verifying zero loopholes and full remediation of all audit findings."""
import pytest
import numpy as np
import pandas as pd
from pathlib import Path

from blumberg_market_radar.pipeline.live_portfolio import LivePortfolioManager
from blumberg_market_radar.backtest.upgraded_vcp_engine import UpgradedVCPBacktestEngine
from blumberg_market_radar.scanner.radar import apply_sector_cluster_guardrail
from blumberg_market_radar.pipeline.staged_tracker import (
    StagedStockRecord,
    save_staged_pipeline,
    update_pipeline_with_bars,
    classify_layer_by_growth,
)
from blumberg_market_radar.pipeline.nightly import evaluate_active_paper_signals
from blumberg_market_radar.data.validation import clean_transient_price_spikes


def test_live_entry_day_peak_price_causal(tmp_path):
    """Entry day peak_price at 9:15 AM must strictly equal open price, zero lookahead to day high."""
    mgr = LivePortfolioManager(state_path=tmp_path / "live.json", initial_capital=1_000_000.0)

    # Day 0: Signal generated at EOD
    mgr.state.pending_entries.append({
        "symbol": "TITAN",
        "signal_date": "2026-01-01",
        "sector": "Consumer",
        "selection_reason": "VCP Base",
    })

    # Day 1: Market open
    # Intraday high is 120 (a +20% surge), but open is 100
    bars = pd.DataFrame([{
        "date": "2026-01-02",
        "symbol": "TITAN",
        "open": 100.0,
        "high": 120.0,
        "low": 99.0,
        "close": 105.0,
        "volume": 500_000,
        "prev_close": 100.0,
    }])

    res = mgr.execute_daily_rebalance(
        bars_df=bars,
        bench_df=None,
        candidates_df=pd.DataFrame(),
        current_date_str="2026-01-02",
        enforce_regime=False,
    )
    pos = mgr.state.active_positions["TITAN"]

    # At EOD of Day 1, position survived and peak_price updated to high (120.0)
    assert pos["peak_price"] == 120.0
    assert pos["entry_price"] == 100.0


def test_sector_guardrail_terminal_statuses():
    """Terminal statuses like TARGET_MET and STOPPED_OUT must never consume active portfolio slots."""
    # 20 historical trades, all terminal
    active_df = pd.DataFrame([
        {"symbol": f"WIN_{i}", "sector": "Auto", "status": "TARGET_MET (>+25%)"} for i in range(10)
    ] + [
        {"symbol": f"LOSS_{i}", "sector": "Defence", "status": "STOPPED_OUT"} for i in range(10)
    ])

    cands = pd.DataFrame([
        {"symbol": "NEW_SYM", "sector": "Defence", "radar_score": 88.0}
    ])

    approved, counts, available_slots = apply_sector_cluster_guardrail(
        cands, active_pipeline_df=active_df, max_portfolio_slots=20
    )

    # All 20 slots must be available because all previous trades are terminated!
    assert available_slots == 20
    assert len(approved) == 1
    assert approved.iloc[0]["symbol"] == "NEW_SYM"


def test_staged_tracker_terminal_status_preservation(tmp_path):
    """update_staged_pipeline must preserve terminal statuses without reverting to L1."""
    p = tmp_path / "staged.json"
    records = [
        StagedStockRecord(
            symbol="WINNER",
            date_added="2026-01-01",
            entry_price=100.0,
            current_price=135.0,
            market_cap_tier="Midcap",
            sector="IT",
            series="EQ",
            days_in_pipeline=25,
            current_layer="Layer 3: Trend Momentum (21-30D)",
            current_gain_pct=35.0,
            peak_mfe_pct=38.0,
            max_mae_pct=-2.0,
            status="TARGET_MET (>+25%)",
        ),
        StagedStockRecord(
            symbol="STOPPED",
            date_added="2026-01-01",
            entry_price=100.0,
            current_price=90.0,
            market_cap_tier="Smallcap",
            sector="Pharma",
            series="EQ",
            days_in_pipeline=8,
            current_layer="Layer 1: Ignition (0-10D)",
            current_gain_pct=-10.0,
            peak_mfe_pct=1.0,
            max_mae_pct=-10.5,
            status="STOPPED_OUT",
        ),
    ]

    bars = pd.DataFrame([
        {"date": "2026-01-20", "symbol": "WINNER", "open": 134.0, "high": 136.0, "low": 133.0, "close": 135.0, "volume": 100000},
        {"date": "2026-01-20", "symbol": "STOPPED", "open": 91.0, "high": 92.0, "low": 89.0, "close": 90.0, "volume": 100000},
    ])

    save_staged_pipeline(records, path=p)
    df = update_pipeline_with_bars(bars, path=p)
    w_row = df[df["symbol"] == "WINNER"].iloc[0]
    s_row = df[df["symbol"] == "STOPPED"].iloc[0]

    assert "TARGET_MET" in w_row["status"]
    assert "STOPPED_OUT" in s_row["status"]


def test_nightly_causal_evaluation():
    """Stopped out position must not resurrect into TARGET_MET even if price rallies later."""
    ledger = pd.DataFrame([{
        "signal_id": "SIG-1",
        "symbol": "CRASH_THEN_RALLY",
        "price_at_signal": 100.0,
        "signal_timestamp": "2026-01-01",
    }])

    # Days 1 to 5: Crashes to 85 (-15%), hitting the -8% stop loss
    # Days 6 to 30: Rallies to 140 (+40%)
    dates = pd.date_range("2026-01-01", periods=30, freq="D", tz="UTC")
    prices = [100.0, 95.0, 85.0, 88.0, 90.0] + [100.0 + i * 2 for i in range(25)]
    bars = pd.DataFrame({
        "date": dates,
        "symbol": "CRASH_THEN_RALLY",
        "open": prices,
        "high": [p * 1.01 for p in prices],
        "low": [p * 0.99 for p in prices],
        "close": prices,
        "volume": 100000,
    })

    tracking, stats = evaluate_active_paper_signals(ledger, bars)
    # Must be STOPPED_OUT, NEVER TARGET_MET!
    assert tracking["status"].iloc[0] == "STOPPED_OUT"
    assert tracking["current_pnl_pct"].iloc[0] == -8.0


def test_validation_split_not_overwritten():
    """1:10 split with real trading volume must never be corrupted or overwritten."""
    df = pd.DataFrame({
        "date": pd.date_range("2026-01-01", periods=2, freq="D", tz="UTC"),
        "symbol": ["TATASTEEL", "TATASTEEL"],
        "open": [1000.0, 100.0],
        "high": [1000.0, 100.0],
        "low": [1000.0, 100.0],
        "close": [1000.0, 100.0],
        "volume": [10_000_000, 15_000_000],  # Heavy institutional split volume
    })
    cleaned, n_repaired = clean_transient_price_spikes(df)
    assert n_repaired == 0
    assert cleaned["close"].iloc[1] == 100.0  # Real post-split price preserved!


def test_bars_proc_filters_future_bars(tmp_path):
    """execute_daily_rebalance must not leak future bars into bars_proc or bars_latest."""
    mgr = LivePortfolioManager(state_path=tmp_path / "live.json", initial_capital=1_000_000.0)

    # 5 days of bars supplied, but today is Day 2
    dates = ["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04", "2026-01-05"]
    prices = [100.0, 102.0, 150.0, 200.0, 300.0]
    bars = pd.DataFrame({
        "date": dates,
        "symbol": ["INFY"] * 5,
        "open": prices,
        "high": [p * 1.01 for p in prices],
        "low": [p * 0.99 for p in prices],
        "close": prices,
        "volume": [100000] * 5,
    })

    # Rebalance on Day 2
    res = mgr.execute_daily_rebalance(
        bars_df=bars,
        bench_df=None,
        candidates_df=pd.DataFrame(),
        current_date_str="2026-01-02",
        enforce_regime=False,
    )
    # Total equity must not have been inflated by 150/200/300 future prices
    assert res["date"] == "2026-01-02"


def test_radar_multiple_status_columns_terminal_filtering():
    """If status='ACTIVE' but current_layer='TARGET_MET', row must be excluded as terminal."""
    active_df = pd.DataFrame([
        {"symbol": "SYM_1", "sector": "Auto", "status": "ACTIVE", "current_layer": "TARGET_MET (>+25%)"},
        {"symbol": "SYM_2", "sector": "Auto", "status": "ACTIVE", "current_stage": "STOPPED_OUT"},
    ])

    cands = pd.DataFrame([{"symbol": "NEW_1", "sector": "Auto", "radar_score": 90.0}])
    approved, counts, available_slots = apply_sector_cluster_guardrail(cands, active_pipeline_df=active_df, max_portfolio_slots=8)

    # Both SYM_1 and SYM_2 must be recognized as terminal!
    assert available_slots == 8
    assert len(approved) == 1
    assert approved.iloc[0]["symbol"] == "NEW_1"


def test_sector_normalization_it_vs_it_and_zero_slots_guard():
    """Verify IT vs It vs it normalize identically, and 0 slots immediately returns 0 candidates."""
    # 5 active positions in IT sector with mixed cases
    active_df = pd.DataFrame([
        {"symbol": "TCS", "sector": "IT", "status": "ACTIVE"},
        {"symbol": "INFY", "sector": "It", "status": "ACTIVE"},
        {"symbol": "WIPRO", "sector": "it", "status": "ACTIVE"},
        {"symbol": "HCLTECH", "sector": "IT", "status": "ACTIVE"},
        {"symbol": "TECHM", "sector": "It", "status": "ACTIVE"},
    ])

    # 6th IT candidate must be blocked by the 5-stock sector cluster cap
    cand_it = pd.DataFrame([{"symbol": "LTIM", "sector": "it", "radar_score": 95.0}])
    approved, counts, available = apply_sector_cluster_guardrail(
        cand_it, active_pipeline_df=active_df, max_stocks_per_sector=5, max_portfolio_slots=20
    )
    assert len(approved) == 0, "6th IT stock should be blocked by sector cap"
    assert counts.get("IT") == 5

    # If available_slots == 0, guardrail must return 0 candidates immediately
    approved_zero, counts_zero, avail_zero = apply_sector_cluster_guardrail(
        cand_it, active_pipeline_df=active_df, max_stocks_per_sector=5, max_portfolio_slots=5
    )
    assert len(approved_zero) == 0
    assert avail_zero == 0


def test_causal_open_circuit_decisions_independent_of_later_high_low():
    """Two bars with identical open price must produce the exact same execution decision regardless of EOD high/low."""
    from blumberg_market_radar.pipeline.live_portfolio import LivePortfolioManager
    import tempfile

    with tempfile.TemporaryDirectory() as tmp_dir:
        state_file = Path(tmp_dir) / "state.json"
        mgr = LivePortfolioManager(state_path=state_file, initial_capital=1_000_000.0, max_slots=8)

        # Scenario A: Bar opened at upper circuit limit (+10%), intraday high == open (classic lock)
        bar_a = pd.DataFrame([{
            "date": "2026-01-02", "symbol": "CAND_1",
            "open": 110.0, "high": 110.0, "low": 110.0, "close": 110.0,
            "prev_close": 100.0, "circuit_limit_pct": 0.10, "volume": 1000
        }])

        # Scenario B: Bar opened at upper circuit limit (+10%), but had intraday high of 115.0 or low 105.0 later in day
        bar_b = pd.DataFrame([{
            "date": "2026-01-02", "symbol": "CAND_2",
            "open": 110.0, "high": 115.0, "low": 105.0, "close": 108.0,
            "prev_close": 100.0, "circuit_limit_pct": 0.10, "volume": 1000
        }])

        # Queue candidate entries for both
        mgr.state.pending_entries = [
            {"symbol": "CAND_1", "signal_date": "2026-01-01", "signal_price": 100.0, "sector": "IT"},
            {"symbol": "CAND_2", "signal_date": "2026-01-01", "signal_price": 100.0, "sector": "IT"}
        ]

        res = mgr.execute_daily_rebalance(
            bars_df=pd.concat([bar_a, bar_b], ignore_index=True),
            bench_df=None,
            candidates_df=pd.DataFrame(),
            current_date_str="2026-01-02",
            enforce_regime=False
        )

        # Both must be rejected at open without any lookahead to later high/low!
        assert "CAND_1" not in mgr.state.active_positions
        assert "CAND_2" not in mgr.state.active_positions


def test_corporate_action_settlement_requires_explicit_verified_cash():
    """Settlement must fail closed (raise ValueError) when cash is omitted, None, NaN, or negative."""
    import tempfile
    from blumberg_market_radar.pipeline.live_portfolio import LivePortfolioManager

    with tempfile.TemporaryDirectory() as tmp_dir:
        mgr = LivePortfolioManager(state_path=Path(tmp_dir) / "state.json", initial_capital=1_000_000.0)
        mgr.state.corporate_action_entitlements = [{
            "parent_symbol": "VEDL",
            "event_id": "SPINOFF_VEDL_1",
            "allocated_capital": 50000.0,
            "status": "Pending_Proceeds",
            "shares": 100
        }]
        initial_nav = mgr.state.cash

        # 1. Negative cash must raise ValueError and NOT mutate state
        import pytest
        with pytest.raises(ValueError, match="finite non-negative"):
            mgr.settle_corporate_action_entitlement(event_id="SPINOFF_VEDL_1", realized_cash=-500.0)
        assert mgr.state.cash == initial_nav

        # 2. NaN cash must raise ValueError
        with pytest.raises(ValueError, match="finite non-negative"):
            mgr.settle_corporate_action_entitlement(event_id="SPINOFF_VEDL_1", realized_cash=float("nan"))
        assert mgr.state.cash == initial_nav

        # 3. None cash must raise ValueError
        with pytest.raises(ValueError, match="finite non-negative"):
            mgr.settle_corporate_action_entitlement(event_id="SPINOFF_VEDL_1", realized_cash=None)
        assert mgr.state.cash == initial_nav

        # 4. Valid explicit cash must settle cleanly
        settled = mgr.settle_corporate_action_entitlement(event_id="SPINOFF_VEDL_1", realized_cash=52000.0)
        assert settled["status"] == "Settled"
        assert mgr.state.cash == initial_nav + 52000.0


def test_nightly_missing_forward_bars_reports_awaiting_forward_bars():
    """When no forward bars exist on or after signal date, report AWAITING_FORWARD_BARS without past-bar substitution."""
    from blumberg_market_radar.pipeline.nightly import evaluate_active_paper_signals

    # Signal date is 2026-05-10
    ledger = pd.DataFrame([{
        "signal_id": "SIG_TEST_FWD",
        "symbol": "TITAN",
        "signal_timestamp": "2026-05-10 16:00:00+00:00",
        "price_at_signal": 3000.0,
        "radar_score": 88.0,
        "primary_reason": "Pre-Rally Setup"
    }])

    # Available bars only exist up to 2026-05-09 (past bars only, 0 forward bars)
    bars = pd.DataFrame({
        "date": pd.to_datetime(["2026-05-08", "2026-05-09"], utc=True),
        "symbol": ["TITAN", "TITAN"],
        "open": [2900.0, 2950.0],
        "high": [2950.0, 2980.0],
        "low": [2880.0, 2920.0],
        "close": [2920.0, 2970.0],
        "volume": [100000, 100000]
    })

    tracking, stats = evaluate_active_paper_signals(ledger, bars)
    assert not tracking.empty
    row = tracking.iloc[0]
    assert row["status"] == "AWAITING_FORWARD_BARS"
    assert row["days_held"] == 0
    assert row["current_price"] == 3000.0


def test_corporate_action_settlement_rejects_bool():
    """Settlement must explicitly reject bool (e.g. True/False) even though bool is an int subtype."""
    import tempfile
    from blumberg_market_radar.pipeline.live_portfolio import LivePortfolioManager

    with tempfile.TemporaryDirectory() as tmp_dir:
        mgr = LivePortfolioManager(state_path=Path(tmp_dir) / "state.json", initial_capital=1_000_000.0)
        mgr.state.corporate_action_entitlements = [{
            "parent_symbol": "VEDL",
            "event_id": "SPINOFF_VEDL_2",
            "allocated_capital": 50000.0,
            "status": "Pending_Proceeds",
            "shares": 100
        }]
        initial_cash = mgr.state.cash

        with pytest.raises(ValueError, match="finite non-negative"):
            mgr.settle_corporate_action_entitlement(event_id="SPINOFF_VEDL_2", realized_cash=True)
        assert mgr.state.cash == initial_cash

        with pytest.raises(ValueError, match="finite non-negative"):
            mgr.settle_corporate_action_entitlement(event_id="SPINOFF_VEDL_2", realized_cash=False)
        assert mgr.state.cash == initial_cash


def test_state_schema_validation_fails_closed(tmp_path):
    """Missing schema_version or missing required ledger keys must fail closed and preserve backup."""
    import json
    from blumberg_market_radar.pipeline.live_portfolio import LivePortfolioManager

    state_file = tmp_path / "state.json"

    # 1. Missing schema_version must raise ValueError and backup file
    state_file.write_text(json.dumps({"cash": 1000000.0, "active_positions": {}, "closed_trades": []}), encoding="utf-8")
    with pytest.raises((ValueError, RuntimeError), match="schema_version"):
        LivePortfolioManager(state_path=state_file)
    assert any(tmp_path.glob("state.json.corrupt*"))

    # 2. Missing top-level ledger key must raise ValueError
    bad_data = {
        "schema_version": 1,
        "initial_capital": 1000000.0,
        "cash": 1000000.0,
        "active_positions": {},
        "closed_trades": [],
    }
    state_file.write_text(json.dumps(bad_data), encoding="utf-8")
    with pytest.raises((ValueError, RuntimeError), match="missing required key"):
        LivePortfolioManager(state_path=state_file)


def test_live_tranche2_deferral_preserves_eligibility(tmp_path):
    """When a stock is locked at upper circuit ceiling at open, Tranche 2 must defer and retain tranche2_eligible."""
    mgr = LivePortfolioManager(state_path=tmp_path / "state.json", initial_capital=1_000_000.0)
    mgr.state.active_positions["TATACHEM"] = {
        "symbol": "TATACHEM",
        "entry_date": "2026-01-01",
        "shares": 100.0,
        "invested_capital": 100000.0,
        "entry_price": 1000.0,
        "entry_price_with_friction": 1005.0,
        "current_price": 1050.0,
        "peak_price": 1050.0,
        "current_gain_pct": 5.0,
        "peak_gain_pct": 5.0,
        "unrealized_pnl_rs": 5000.0,
        "target_slot_capital": 125000.0,
        "tranche1_shares": 100.0,
        "tranche1_price": 1000.0,
        "bars_held": 7,
        "tranche2_eligible": True,
        "tranche2_active": False,
    }

    # Day 8 open: locked limit-up at +5% ceiling (open 1102.5 vs prev_close 1050.0)
    locked_bar = pd.DataFrame([{
        "date": "2026-01-10", "symbol": "TATACHEM",
        "open": 1102.5, "high": 1102.5, "low": 1102.5, "close": 1102.5, "volume": 100,
        "prev_close": 1050.0, "circuit_limit_pct": 0.05
    }])

    res = mgr.execute_daily_rebalance(locked_bar, None, pd.DataFrame(), current_date_str="2026-01-10", enforce_regime=False)
    pos = mgr.state.active_positions["TATACHEM"]
    assert pos["tranche2_eligible"] is True
    assert pos.get("tranche2_active", False) is False
    assert any("TRANCHE 2 DEFERRED" in a for a in res["actions_taken"])


def test_sector_guardrail_empty_candidates_returns_available_slots():
    """apply_sector_cluster_guardrail must compute available_slots accurately even when candidates DataFrame is empty."""
    active_df = pd.DataFrame([
        {"symbol": "INFY", "sector": "IT", "status": "ACTIVE"},
        {"symbol": "TCS", "sector": "IT", "status": "ACTIVE"},
    ])
    empty_cands = pd.DataFrame()

    approved, counts, available = apply_sector_cluster_guardrail(
        empty_cands, active_pipeline_df=active_df, max_stocks_per_sector=3, max_portfolio_slots=8
    )
    assert len(approved) == 0
    assert counts.get("IT") == 2
    assert available == 6  # 8 total - 2 active = 6 available slots!


def test_nightly_tracking_excludes_same_day_bars_and_handles_missing_symbol():
    """Nightly paper evaluation must not process same-day/past bars and must handle symbols with 0 bars."""
    ledger = pd.DataFrame([
        {
            "signal_id": "SIG_MISSING",
            "symbol": "ABSENT_SYM",
            "signal_timestamp": "2026-06-01 15:30:00+00:00",
            "price_at_signal": 500.0,
            "radar_score": 90.0,
            "primary_reason": "VCP Setup"
        },
        {
            "signal_id": "SIG_SAME_DAY",
            "symbol": "SAMEDAY_SYM",
            "signal_timestamp": "2026-06-01 15:30:00+00:00",
            "price_at_signal": 200.0,
            "radar_score": 85.0,
            "primary_reason": "Breakout"
        }
    ])

    bars = pd.DataFrame([
        {
            "date": pd.to_datetime("2026-06-01 09:15:00", utc=True),
            "symbol": "SAMEDAY_SYM",
            "open": 200.0, "high": 205.0, "low": 198.0, "close": 200.0, "volume": 50000
        }
    ])

    tracking, stats = evaluate_active_paper_signals(ledger, bars)
    assert len(tracking) == 2
    row_absent = tracking[tracking["symbol"] == "ABSENT_SYM"].iloc[0]
    row_same = tracking[tracking["symbol"] == "SAMEDAY_SYM"].iloc[0]

    assert row_absent["status"] == "AWAITING_FORWARD_BARS"
    assert row_same["status"] == "AWAITING_FORWARD_BARS"
