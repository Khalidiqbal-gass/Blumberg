"""Comprehensive unit tests verifying all adversarial fixes and quantitative robustness."""
import numpy as np
import pandas as pd
import pytest

from blumberg_market_radar.data.validation import (
    MarketDataError,
    detect_corporate_action_anomalies,
    validate_ohlcv,
)
from blumberg_market_radar.features.technical import (
    baseline_early_rally_signal,
    build_daily_features,
)
from blumberg_market_radar.backtest.baseline import (
    DEFAULT_INDIAN_STATUTORY_BPS_PER_SIDE,
    simulate_multiday_trend_trades,
    simulate_next_close_entries,
)


# =========================================================================
# 1. VALIDATION TESTS
# =========================================================================

def test_vectorized_finite_validation():
    bars = pd.DataFrame({
        "date": ["2026-01-01", "2026-01-02"],
        "symbol": ["TEST", "TEST"],
        "open": [100.0, 102.0],
        "high": [105.0, 106.0],
        "low": [98.0, 101.0],
        "close": [103.0, np.inf],  # Non-finite inf
        "volume": [1000.0, 1500.0],
    })
    with pytest.raises(MarketDataError, match="non-finite values"):
        validate_ohlcv(bars)


def test_microstructure_tagging_circuit_and_zero_volume():
    bars = pd.DataFrame({
        "date": ["2026-01-01", "2026-01-02", "2026-01-05"],
        "symbol": ["TEST", "TEST", "TEST"],
        "open": [100.0, 110.0, 105.0],
        "high": [105.0, 110.0, 108.0],
        "low": [98.0, 110.0, 104.0],
        "close": [102.0, 110.0, 107.0],
        "volume": [1000.0, 50.0, 0.0],  # Zero volume on day 3
    })
    result = validate_ohlcv(bars, tag_microstructure=True)
    assert "is_circuit_locked" in result.columns
    assert "is_zero_volume" in result.columns

    # Day 2 is locked at circuit (open == high == low == close == 110.0)
    assert not result.loc[0, "is_circuit_locked"]
    assert result.loc[1, "is_circuit_locked"]
    assert not result.loc[2, "is_circuit_locked"]

    # Day 3 has zero volume
    assert not result.loc[0, "is_zero_volume"]
    assert not result.loc[1, "is_zero_volume"]
    assert result.loc[2, "is_zero_volume"]


def test_corporate_action_anomaly_detector():
    # Simulates unadjusted stock split (e.g. Vedanta 758 -> 283 on 2026-04-30, -62.6% drop)
    dates = pd.date_range("2026-04-01", periods=25, freq="B")
    closes = [750.0] * 24 + [280.0]  # Single day -62.6% drop
    bars = pd.DataFrame({
        "date": dates,
        "symbol": ["VEDL"] * 25,
        "open": closes,
        "high": [c + 5.0 for c in closes],
        "low": [c - 5.0 for c in closes],
        "close": closes,
        "volume": [100_000.0] * 25,  # Normal volume, not panic liquidation
    })
    anomalies = detect_corporate_action_anomalies(bars, drop_threshold_pct=-40.0)
    assert "is_corporate_anomaly" in anomalies.columns
    assert anomalies.iloc[-1]["is_corporate_anomaly"]
    assert "Unadjusted split/demerger signature" in anomalies.iloc[-1]["anomaly_reason"]
    assert not anomalies.iloc[0]["is_corporate_anomaly"]


# =========================================================================
# 2. FEATURE & SIGNAL TESTS
# =========================================================================

def test_calendar_gap_suspension_invalidation():
    # 5 business rows, but row 4 has a 30-calendar-day suspension gap
    dates = [
        pd.Timestamp("2026-01-01", tz="UTC"),
        pd.Timestamp("2026-01-02", tz="UTC"),
        pd.Timestamp("2026-01-05", tz="UTC"),
        pd.Timestamp("2026-01-06", tz="UTC"),
        pd.Timestamp("2026-01-07", tz="UTC"),
        pd.Timestamp("2026-02-15", tz="UTC"),  # Gap of >35 days
    ]
    bars = pd.DataFrame({
        "date": dates,
        "symbol": ["TEST"] * 6,
        "open": [100, 101, 102, 103, 104, 150],
        "high": [101, 102, 103, 104, 105, 155],
        "low": [99, 100, 101, 102, 103, 148],
        "close": [100, 101, 102, 103, 104, 150],
        "volume": [1000] * 6,
    })
    features = build_daily_features(bars, max_calendar_gap_5d=15)
    # The 5-day return across the suspension should be NaN
    assert np.isnan(features.iloc[5]["return_5d"])


def test_late_rally_upper_bound_and_volatility_filters():
    features = pd.DataFrame({
        "return_5d": [0.05, 0.05, 0.05],
        "return_20d": [0.15, 0.65, 0.15],  # Row 1 is normal (+15%), Row 2 is overextended (+65%)
        "relative_volume_20d": [2.0, 2.5, 2.0],
        "volatility_20d": [0.03, 0.04, 0.12],  # Row 3 has elevated volatility (loose base)
        "turnover": [50_000_000, 60_000_000, 1_000_000],  # Row 3 has poor turnover
        "is_circuit_locked": [False, False, False],
        "is_zero_volume": [False, False, False],
    })

    # Standard signal triggers on Row 1 and Row 2
    sig_raw = baseline_early_rally_signal(features)
    assert sig_raw.tolist() == [True, True, True]

    # With upper bound on return_20d (max 35%): Row 2 (overextended) is rejected!
    sig_capped = baseline_early_rally_signal(features, max_return_20d=0.35)
    assert sig_capped.tolist() == [True, False, True]

    # With volatility contraction filter (max 0.05): Row 3 (loose base) is rejected!
    sig_tight = baseline_early_rally_signal(features, max_return_20d=0.35, max_volatility_20d=0.05)
    assert sig_tight.tolist() == [True, False, False]

    # With minimum turnover filter (min ₹1 Crore): Row 3 is rejected!
    sig_liq = baseline_early_rally_signal(features, min_turnover=10_000_000)
    assert sig_liq.tolist() == [True, True, False]


def test_circuit_locked_signal_suppression():
    features = pd.DataFrame({
        "return_5d": [0.05, 0.05],
        "return_20d": [0.15, 0.15],
        "relative_volume_20d": [2.0, 2.0],
        "is_circuit_locked": [False, True],  # Row 2 is locked at circuit
        "is_zero_volume": [False, False],
    })
    sig = baseline_early_rally_signal(features, suppress_circuits=True)
    assert sig.tolist() == [True, False]


# =========================================================================
# 3. BACKTEST SIMULATION TESTS
# =========================================================================

def test_statutory_indian_cost_default_105_2_bps():
    # Statutory cost default is 52.6 bps per side = 105.2 bps round trip
    assert DEFAULT_INDIAN_STATUTORY_BPS_PER_SIDE == pytest.approx(52.6, abs=0.1)
    bars = pd.DataFrame({
        "symbol": ["ABC"] * 4,
        "date": pd.date_range("2026-01-01", periods=4, freq="B"),
        "open": [100.0, 100.0, 100.0, 100.0],
        "high": [101.0, 101.0, 101.0, 101.0],
        "low": [99.0, 99.0, 99.0, 99.0],
        "close": [100.0, 100.0, 100.0, 100.0],
        "volume": [1000] * 4,
        "signal": [True, False, False, False],
    })
    res = simulate_next_close_entries(bars)
    # Price did not move: gross return is 0, net return should reflect statutory friction of ~ -1.05%
    expected_cost = 2 * (DEFAULT_INDIAN_STATUTORY_BPS_PER_SIDE / 10_000.0)
    assert res.loc[0, "gross_return"] == 0.0
    assert res.loc[0, "net_return"] == pytest.approx(-expected_cost, abs=0.001)


def test_multiday_trend_upper_circuit_entry_rejection():
    # Signal on Day 1. Day 2 is locked at upper circuit (110 = open = high = low = close)
    bars = pd.DataFrame({
        "symbol": ["ABC"] * 4,
        "date": pd.date_range("2026-01-01", periods=4, freq="B"),
        "open": [100.0, 110.0, 112.0, 115.0],
        "high": [102.0, 110.0, 114.0, 116.0],
        "low": [99.0, 110.0, 111.0, 114.0],
        "close": [101.0, 110.0, 113.0, 115.0],
        "volume": [1000, 10, 500, 1000],
        "signal": [True, False, False, False],
    })
    res = simulate_multiday_trend_trades(bars, reject_upper_circuit_entry=True)
    # The trade should NOT be filled because Day 2 was locked in upper circuit
    assert res["unfilled_circuit_count"] == 1
    assert res["total_trades"] == 0


def test_multiday_trend_final_bar_evaluation():
    # Ensure loop range(n) does NOT skip the final bar
    # 4 bars: Signal on Day 1, filled Day 2 at Open 100.
    # Day 4 (final bar) drops to 90 (below -8% stop loss).
    bars = pd.DataFrame({
        "symbol": ["ABC"] * 4,
        "date": pd.date_range("2026-01-01", periods=4, freq="B"),
        "open": [100.0, 100.0, 101.0, 91.0],
        "high": [101.0, 102.0, 102.0, 92.0],
        "low": [99.0, 99.0, 100.0, 89.0],  # Day 4 low is 89 (triggers -8% stop)
        "close": [100.0, 101.0, 101.0, 90.0],
        "volume": [1000] * 4,
        "signal": [True, False, False, False],
    })
    res = simulate_multiday_trend_trades(bars, cost_bps_per_side=0.0)
    assert res["total_trades"] == 1
    trade = res["trades"].iloc[0]
    # Trade must have exited on the final bar due to stop loss
    expected_exit_date = pd.to_datetime(bars.iloc[3]["date"], utc=True)
    assert trade["exit_date"] == expected_exit_date
    assert "Stop Loss" in trade["exit_reason"]


def test_multiday_trend_overlapping_signals_suppressed():
    # Signal on Day 1 and Day 2 on same stock. Only Day 1 should open a position!
    bars = pd.DataFrame({
        "symbol": ["ABC"] * 5,
        "date": pd.date_range("2026-01-01", periods=5, freq="B"),
        "open": [100.0, 102.0, 104.0, 106.0, 108.0],
        "high": [101.0, 103.0, 105.0, 107.0, 109.0],
        "low": [99.0, 101.0, 103.0, 105.0, 107.0],
        "close": [100.0, 102.0, 104.0, 106.0, 108.0],
        "volume": [1000] * 5,
        "signal": [True, True, False, False, False],  # Consecutive signals
    })
    res = simulate_multiday_trend_trades(bars, suppress_overlapping=True)
    # Only 1 trade should be opened, the second signal while active should be ignored
    assert res["total_trades"] == 1
