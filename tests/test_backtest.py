import pandas as pd
import pytest
from blumberg_market_radar.backtest.baseline import simulate_next_close_entries


def test_signal_uses_next_bars_for_outcome():
    bars = pd.DataFrame({
        "symbol": ["ABC"] * 4, "date": pd.date_range("2026-01-01", periods=4, freq="B"),
        "close": [100.0, 101.0, 105.0, 110.0], "signal": [True, False, False, False],
    })
    result = simulate_next_close_entries(bars, cost_bps_per_side=0)
    assert result.loc[0, "entry_close"] == 101.0
    assert result.loc[0, "exit_close"] == 105.0
    assert result.loc[0, "net_return"] == pytest.approx(105 / 101 - 1)


def test_negative_cost_is_rejected():
    bars = pd.DataFrame({
        "symbol": ["ABC"], "date": ["2026-01-01"], "close": [10.0], "signal": [True],
    })
    with pytest.raises(ValueError, match="cannot be negative"):
        simulate_next_close_entries(bars, cost_bps_per_side=-1)
