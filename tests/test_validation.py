import pandas as pd
import pytest
from blumberg_market_radar.data.validation import MarketDataError, validate_ohlcv


def sample_bars():
    return pd.DataFrame({
        "date": ["2026-01-02", "2026-01-01"], "symbol": ["abc", "ABC"],
        "open": [11, 10], "high": [12, 11], "low": [10, 9],
        "close": [11.5, 10.5], "volume": [100, 90],
    })


def test_validation_normalizes_and_sorts():
    result = validate_ohlcv(sample_bars())
    assert result["symbol"].tolist() == ["ABC", "ABC"]
    assert result["date"].is_monotonic_increasing


def test_duplicate_symbol_date_is_rejected():
    frame = sample_bars()
    frame.loc[1, "date"] = frame.loc[0, "date"]
    with pytest.raises(MarketDataError, match="Duplicate"):
        validate_ohlcv(frame)


def test_invalid_candle_is_rejected():
    frame = sample_bars()
    frame.loc[0, "high"] = 10
    with pytest.raises(MarketDataError, match="inconsistent OHLC"):
        validate_ohlcv(frame)


def test_negative_volume_is_rejected():
    frame = sample_bars()
    frame.loc[0, "volume"] = -1
    with pytest.raises(MarketDataError, match="Volume"):
        validate_ohlcv(frame)
