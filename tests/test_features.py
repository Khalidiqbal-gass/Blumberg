import pandas as pd
from blumberg_market_radar.features.technical import baseline_early_rally_signal, build_daily_features


def test_feature_columns_and_prior_volume_baseline():
    n = 30
    frame = pd.DataFrame({
        "date": pd.date_range("2026-01-01", periods=n, freq="B"),
        "symbol": ["TEST"] * n,
        "open": [100 + i for i in range(n)], "high": [101 + i for i in range(n)],
        "low": [99 + i for i in range(n)], "close": [100 + i for i in range(n)],
        "volume": [1000] * (n - 1) + [3000],
    })
    result = build_daily_features(frame)
    assert {"return_5d", "return_20d", "relative_volume_20d", "volatility_20d"}.issubset(result)
    assert result.iloc[-1]["relative_volume_20d"] == 3.0


def test_signal_returns_boolean_series():
    frame = pd.DataFrame({
        "return_5d": [0.1, -0.1], "return_20d": [0.2, 0.1],
        "relative_volume_20d": [2.0, 3.0],
    })
    assert baseline_early_rally_signal(frame).tolist() == [True, False]
