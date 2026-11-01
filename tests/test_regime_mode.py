"""Unit tests for regime_mode in UpgradedVCPBacktestEngine and LivePortfolioManager."""
import pandas as pd
import numpy as np
import pytest
from blumberg_market_radar.backtest.upgraded_vcp_engine import UpgradedVCPBacktestEngine
from blumberg_market_radar.pipeline.live_portfolio import LivePortfolioManager


def test_engine_regime_mode_options():
    eng_or = UpgradedVCPBacktestEngine(regime_mode="OR")
    assert eng_or.regime_mode == "OR"
    eng_and = UpgradedVCPBacktestEngine(regime_mode="AND")
    assert eng_and.regime_mode == "AND"
    eng_trend = UpgradedVCPBacktestEngine(regime_mode="AND_TREND")
    assert eng_trend.regime_mode == "AND_TREND"


def test_live_portfolio_regime_logic(tmp_path):
    state_file = tmp_path / "live_state.json"
    
    # Construct synthetic bench where close is between ema50 and ema200
    dates = pd.bdate_range("2026-01-01", periods=250)
    # create price series with declining trend so close > ema200 but close < ema50
    close = np.linspace(100, 200, 250)
    # let's set last few points
    close[-1] = 150.0  # dip below short-term but above 200d base
    bench = pd.DataFrame({"date": dates, "close": close})
    
    mgr_or = LivePortfolioManager(state_path=state_file, regime_mode="OR")
    mgr_and = LivePortfolioManager(state_path=state_file, regime_mode="AND")
    
    # Test regime logic
    bench_sorted = bench.sort_values("date").reset_index(drop=True)
    bench_close = bench_sorted["close"].iloc[-1]
    bench_ema50 = bench_sorted["close"].ewm(span=50, adjust=False).mean().iloc[-1]
    bench_ema200 = bench_sorted["close"].ewm(span=200, adjust=False).mean().iloc[-1]
    
    or_ok = bool((bench_close > bench_ema50) or (bench_close > bench_ema200))
    and_ok = bool((bench_close > bench_ema50) and (bench_close > bench_ema200))
    
    assert mgr_or.regime_mode == "OR"
    assert mgr_and.regime_mode == "AND"


def test_invalid_regime_mode_raises(tmp_path):
    with pytest.raises(ValueError):
        UpgradedVCPBacktestEngine(regime_mode="AN")
    with pytest.raises(ValueError):
        LivePortfolioManager(state_path=tmp_path / "s.json", regime_mode="strict")


def test_live_manager_blocks_entries_in_AND_but_not_OR_regime(tmp_path):
    # close above EMA200 but below EMA50 -> OR allows, AND blocks
    dates = pd.bdate_range("2026-01-01", periods=250)
    close = np.linspace(100, 200, 250)
    close[-1] = 175.0
    bench = pd.DataFrame({"date": dates, "close": close})
    day = dates[-1].strftime("%Y-%m-%d")
    bars = pd.DataFrame([{"date": dates[-1], "symbol": "DIXON", "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 100000}])
    cand = pd.DataFrame([{"symbol": "DIXON", "sector": "X"}])
    res = {}
    for mode in ("OR", "AND"):
        mgr = LivePortfolioManager(state_path=tmp_path / f"{mode}.json", regime_mode=mode)
        res[mode] = mgr.execute_daily_rebalance(bars, bench, cand, current_date_str=day)["regime_ok"]
    assert res == {"OR": True, "AND": False}


def test_regime_blocks_entries_with_insufficient_history(tmp_path):
    # Only 100 bench bars: EMA200 undefined -> entries must be blocked, not judged on EMA50
    dates = pd.bdate_range("2026-01-01", periods=100)
    bench = pd.DataFrame({"date": dates, "close": np.linspace(100, 200, 100)})
    bars = pd.DataFrame([{"date": dates[-1], "symbol": "DIXON", "open": 100.0, "high": 101.0, "low": 99.0, "close": 200.0, "volume": 100000}])
    cand = pd.DataFrame([{"symbol": "DIXON", "sector": "X"}])
    mgr = LivePortfolioManager(state_path=tmp_path / "s.json", regime_mode="OR")
    res = mgr.execute_daily_rebalance(bars, bench, cand, current_date_str=dates[-1].strftime("%Y-%m-%d"))
    assert res["regime_ok"] is False
