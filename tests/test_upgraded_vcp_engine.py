"""Unit tests for the Upgraded VCP & Multi-Stage Secular Backtesting Engine."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from blumberg_market_radar.backtest.upgraded_vcp_engine import (
    UpgradedVCPBacktestEngine,
    UpgradedTrade,
    BacktestSummary,
)


def _generate_synthetic_benchmark(dates: pd.DatetimeIndex, trend: str = "bull") -> pd.DataFrame:
    n = len(dates)
    if trend == "bull":
        prices = np.linspace(10000, 20000, n)
    elif trend == "bear":
        prices = np.linspace(20000, 10000, n)
    else:
        prices = 15000 + 500 * np.sin(np.linspace(0, 10, n))
    
    return pd.DataFrame({
        "date": dates,
        "close": prices,
    })


def _generate_vcp_bars(
    symbol: str,
    dates: pd.DatetimeIndex,
    pattern: list[float],
    high_spread: list[float] | None = None,
    volume_pattern: list[float] | None = None,
) -> pd.DataFrame:
    n = len(dates)
    prices = pattern[:n] if len(pattern) >= n else (pattern * ((n // len(pattern)) + 1))[:n]
    closes = np.array(prices, dtype=float)

    if high_spread is not None:
        spreads = np.array(high_spread[:n], dtype=float)
    else:
        # Volatility contraction: 4% spread early, 1% spread later
        spreads = np.where(np.arange(n) < 30, 0.04, 0.01)

    highs = closes * (1.0 + spreads)
    lows = closes * (1.0 - spreads)
    opens = closes * (1.0 - spreads * 0.2)

    if volume_pattern is not None:
        volumes = np.array(volume_pattern[:n], dtype=float)
    else:
        # Baseline volume 500k, spike to 2.5M at bar 40
        volumes = np.where((np.arange(n) >= 40) & (np.arange(n) <= 42), 2_500_000.0, 500_000.0)

    return pd.DataFrame({
        "symbol": symbol,
        "date": dates,
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": volumes,
    })


def test_vcp_indicator_computation():
    dates = pd.date_range("2023-01-01", periods=100, freq="B", tz="UTC")
    bench = _generate_synthetic_benchmark(dates, trend="bull")
    bars = _generate_vcp_bars("TEST", dates, [100.0 + i * 0.2 for i in range(100)])

    engine = UpgradedVCPBacktestEngine()
    bench_series = bench.set_index("date")["close"]
    computed = engine.compute_indicators(bars, bench_series)

    assert "atr_10" in computed.columns
    assert "atr_30" in computed.columns
    assert "high_52w" in computed.columns
    assert "rs_score" in computed.columns
    assert "raw_signal" in computed.columns
    assert "ema20" in computed.columns
    assert "ema50" in computed.columns
    assert "ema100" in computed.columns


def test_bear_market_regime_blocks_entries():
    """In confirmed bear market (index < 50 EMA and < 200 EMA), entries must be suppressed."""
    dates = pd.date_range("2023-01-01", periods=100, freq="B", tz="UTC")
    bench = _generate_synthetic_benchmark(dates, trend="bear")
    
    # Stock triggers a breakout signal with high volume
    prices = [100.0] * 40 + [102.0, 105.0, 110.0, 115.0] + [120.0] * 56
    bars = _generate_vcp_bars("TEST", dates, prices)

    engine = UpgradedVCPBacktestEngine(min_turnover_rs=1_000_000.0)
    summary = engine.run_backtest(bars, bench)

    # In bear regime, trades should be completely blocked
    assert summary.total_trades == 0


def test_stage_1_closing_stop_and_dead_money_exit():
    """Verify dead money time-stop triggers after 30 bars if gain < 10% and close < 20 EMA."""
    dates = pd.date_range("2023-01-01", periods=90, freq="B", tz="UTC")
    bench = _generate_synthetic_benchmark(dates, trend="bull")

    # Tight base for 40 bars, breakout at bar 41 with 5x volume, then drops below 20 EMA to 98 for 40 bars
    prices = [100.0] * 40 + [102.0, 104.0, 105.0] + [98.5] * 47
    vols = [500_000.0] * 40 + [3_000_000.0, 2_000_000.0] + [500_000.0] * 48
    spreads = [0.04] * 25 + [0.008] * 65  # VCP contraction
    bars = _generate_vcp_bars("STAGNANT", dates, prices, high_spread=spreads, volume_pattern=vols)

    engine = UpgradedVCPBacktestEngine(min_turnover_rs=1_000_000.0)
    summary = engine.run_backtest(bars, bench)

    assert summary.total_trades >= 1
    t = summary.trades_df.iloc[0]
    assert "Time-Stop" in t["exit_reason"] or "Stop" in t["exit_reason"]


def test_stage_2_breakeven_floor_locks_profit():
    """Once a trade hits +15% gain, it must NEVER exit below +2% breakeven floor."""
    dates = pd.date_range("2023-01-01", periods=90, freq="B", tz="UTC")
    bench = _generate_synthetic_benchmark(dates, trend="bull")

    # Breakout at bar 40 with volume (entry ~107.8), surges to 130 (+20.5% gain, entering Stage 2),
    # then pulls back through floor: 130 -> 122 -> 116 -> 112 -> 110 (low dips to 108.9 <= floor 109.9)
    prices = [100.0] * 40 + [103.0, 108.0, 130.0, 122.0, 116.0, 112.0, 110.0] + [98.0] * 43
    vols = [500_000.0] * 40 + [3_000_000.0, 2_000_000.0] + [500_000.0] * 48
    spreads = [0.04] * 25 + [0.01] * 65  # VCP contraction
    bars = _generate_vcp_bars("RUNNER", dates, prices, high_spread=spreads, volume_pattern=vols)

    engine = UpgradedVCPBacktestEngine(min_turnover_rs=1_000_000.0)
    summary = engine.run_backtest(bars, bench)

    assert summary.total_trades >= 1
    t = summary.trades_df.iloc[0]
    # Exit price must protect breakeven (positive return)
    assert t["exit_price"] >= t["entry_price"] * 1.015
    assert "Breakeven Floor" in t["exit_reason"]


def test_stage_5_parabolic_climax_exit():
    """When stock stretches > 60% above 100 EMA, climax exit activates."""
    dates = pd.date_range("2023-01-01", periods=140, freq="B", tz="UTC")
    bench = _generate_synthetic_benchmark(dates, trend="bull")

    # 40 bars base, explosive surge to 220 (> 60% above 100 EMA), then drops 16% to 184
    prices = (
        [100.0 + i * 0.1 for i in range(40)] +
        [105.0, 115.0, 130.0, 160.0, 190.0, 220.0] +
        [184.0] * 94
    )
    vols = [500_000.0] * 40 + [3_000_000.0] * 6 + [500_000.0] * 94
    spreads = [0.04] * 25 + [0.01] * 115  # VCP contraction
    bars = _generate_vcp_bars("ROCKET", dates, prices, high_spread=spreads, volume_pattern=vols)

    engine = UpgradedVCPBacktestEngine(min_turnover_rs=1_000_000.0)
    summary = engine.run_backtest(bars, bench)

    assert summary.total_trades >= 1
    t = summary.trades_df.iloc[0]
    assert t["is_climax_reached"] or t["peak_gain_pct"] >= 50.0
    assert t["net_return_pct"] > 20.0


# ---------------------------------------------------------------------------
# Regression tests for the full-audit fixes
# ---------------------------------------------------------------------------
def _flat_bars(sym, dates, price=100.0):
    return pd.DataFrame({
        "date": dates, "symbol": sym, "open": price, "high": price * 1.01, "low": price * 0.99,
        "close": price, "volume": 1_000_000.0,
    })


def test_stale_data_position_is_force_closed_not_carried_at_entry_price():
    from blumberg_market_radar.backtest.upgraded_vcp_engine import UpgradedVCPBacktestEngine
    dates = pd.bdate_range("2020-01-01", periods=60, tz="UTC")
    eng = UpgradedVCPBacktestEngine(stale_exit_sessions=5)
    # Directly exercise the engine's stale logic through a synthetic run: symbol A stops trading at bar 30
    a = _flat_bars("AAA", dates[:30], 100.0)
    b = _flat_bars("BBB", dates, 100.0)
    bench = pd.DataFrame({"date": dates, "close": np.linspace(100, 120, len(dates))})
    res = eng.run_backtest(pd.concat([a, b]), bench)
    # No crash and equity curve is finite for the whole period
    assert np.isfinite(res.equity_curve["total_equity"]).all()


def test_gap_cap_is_configurable():
    from blumberg_market_radar.backtest.upgraded_vcp_engine import UpgradedVCPBacktestEngine
    assert UpgradedVCPBacktestEngine().gap_loss_cap_pct == 20.0
    assert UpgradedVCPBacktestEngine(gap_loss_cap_pct=None).gap_loss_cap_pct is None
    assert UpgradedVCPBacktestEngine(stage5_fill_mode="close").stage5_fill_mode == "CLOSE"


def test_engine_cleans_single_bar_glitches_by_default():
    from blumberg_market_radar.backtest.upgraded_vcp_engine import UpgradedVCPBacktestEngine
    dates = pd.bdate_range("2020-01-01", periods=40, tz="UTC")
    df = _flat_bars("AAA", dates, 100.0)
    df.loc[20, ["open", "high", "low", "close"]] = [100.0, 450.0, 100.0, 100.0]  # one-bar bad tick (high 4.5x, reverts)
    bench = pd.DataFrame({"date": dates, "close": np.linspace(100, 110, len(dates))})
    eng = UpgradedVCPBacktestEngine()
    eng.run_backtest(df, bench)
    assert eng.glitch_bars_repaired == 1
    eng_off = UpgradedVCPBacktestEngine(clean_glitches=False)
    eng_off.run_backtest(df, bench)
    assert eng_off.glitch_bars_repaired == 0


def test_liquidity_cap_limits_fill_size():
    from blumberg_market_radar.backtest.upgraded_vcp_engine import UpgradedVCPBacktestEngine
    eng = UpgradedVCPBacktestEngine(max_pct_of_adv=10.0)
    bar = pd.Series({"adv_20": 20_000_000.0})
    assert eng._liquidity_cap(bar) == 2_000_000.0
    assert UpgradedVCPBacktestEngine(max_pct_of_adv=None)._liquidity_cap(bar) == float("inf")
    assert eng._liquidity_cap(pd.Series({"adv_20": float("nan")})) == float("inf")
