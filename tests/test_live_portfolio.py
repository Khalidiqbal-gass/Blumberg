"""Unit tests for Live Autonomous Paper Portfolio Engine."""
import pytest
import pandas as pd
import numpy as np
from pathlib import Path
from blumberg_market_radar.pipeline.live_portfolio import LivePortfolioManager, DEFAULT_PORTFOLIO_PATH

@pytest.fixture
def temp_portfolio(tmp_path):
    state_file = tmp_path / "test_portfolio.json"
    mgr = LivePortfolioManager(state_path=state_file, initial_capital=1_000_000.0, max_slots=8)
    return mgr

def test_initial_state(temp_portfolio):
    summary = temp_portfolio.get_summary()
    assert summary["initial_capital"] == 1_000_000.0
    assert summary["cash"] == 1_000_000.0
    assert summary["active_positions_count"] == 0
    assert summary["available_slots"] == 8
    assert summary["total_equity"] == 1_000_000.0

def test_execution_tranche1_and_exit(temp_portfolio):
    # Dummy candidates
    candidates = pd.DataFrame([{
        "symbol": "DIXON",
        "close": 1000.0,
        "radar_score": 85.0,
        "sector": "EMS / Electronics",
        "primary_driver": "VCP Squeeze",
    }])

    # Dummy bars
    bars = pd.DataFrame([
        {"date": "2026-10-26", "symbol": "DIXON", "open": 1000.0, "high": 1010.0, "low": 990.0, "close": 1000.0, "volume": 100000},
    ])
    bench = pd.DataFrame([
        {"date": "2026-10-26", "close": 25000.0, "volume": 1000000}
    ])

    res = temp_portfolio.execute_daily_rebalance(bars, bench, candidates, current_date_str="2026-10-26")
    summary = temp_portfolio.get_summary()

    # Tranche 1 entered!
    assert summary["active_positions_count"] == 1
    assert "DIXON" in temp_portfolio.state.active_positions
    pos = temp_portfolio.state.active_positions["DIXON"]
    assert pos["tranche1_price"] == 1000.0
    assert pos["tranche2_active"] is False

    # Simulate stock falling to 890 (-10% stop hit during active trading)
    bars_drop = pd.DataFrame([
        {"date": "2026-10-27", "symbol": "DIXON", "open": 920.0, "high": 930.0, "low": 890.0, "close": 895.0, "volume": 100000},
    ])
    res2 = temp_portfolio.execute_daily_rebalance(bars_drop, bench, pd.DataFrame(), current_date_str="2026-10-27")
    summary2 = temp_portfolio.get_summary()

    assert summary2["active_positions_count"] == 0
    assert len(temp_portfolio.state.closed_trades) == 1
    assert "Extreme Circuit Breaker" in temp_portfolio.state.closed_trades[0]["exit_reason"]


def test_lower_circuit_exit_deferral(temp_portfolio):
    # Dummy candidates
    candidates = pd.DataFrame([{
        "symbol": "DIXON",
        "close": 1000.0,
        "radar_score": 85.0,
        "sector": "EMS / Electronics",
        "primary_driver": "VCP Squeeze",
    }])

    bars = pd.DataFrame([
        {"date": "2026-10-26", "symbol": "DIXON", "open": 1000.0, "high": 1010.0, "low": 990.0, "close": 1000.0, "volume": 100000},
    ])
    bench = pd.DataFrame([
        {"date": "2026-10-26", "close": 25000.0, "volume": 1000000}
    ])

    temp_portfolio.execute_daily_rebalance(bars, bench, candidates, current_date_str="2026-10-26")
    assert temp_portfolio.get_summary()["active_positions_count"] == 1

    # Simulate stock hitting hard limit-down lower circuit: high == low == 890
    bars_locked = pd.DataFrame([
        {"date": "2026-10-27", "symbol": "DIXON", "open": 890.0, "high": 890.0, "low": 890.0, "close": 890.0, "volume": 10000},
    ])
    res2 = temp_portfolio.execute_daily_rebalance(bars_locked, bench, pd.DataFrame(), current_date_str="2026-10-27")
    summary2 = temp_portfolio.get_summary()

    # Position must NOT be closed because it was locked limit-down (exit deferred!)
    assert summary2["active_positions_count"] == 1
    assert "CIRCUIT_DEFER" in temp_portfolio.state.active_positions["DIXON"]["current_stage"]

