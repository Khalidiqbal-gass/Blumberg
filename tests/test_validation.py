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


def test_clean_transient_price_spikes_is_strictly_causal_no_lookahead():
    """Verify clean_transient_price_spikes has zero look-ahead bias.

    Day D output must be 100% bit-for-bit identical whether Day D+1 is present or absent.
    """
    from blumberg_market_radar.data.validation import clean_transient_price_spikes

    dates = pd.bdate_range("2026-01-01", periods=10, tz="UTC")
    # Base bars
    df_full = pd.DataFrame({
        "date": dates,
        "symbol": "RELIANCE",
        "open": [100.0] * 10,
        "high": [102.0] * 10,
        "low": [98.0] * 10,
        "close": [100.0] * 10,
        "volume": [1_000_000.0] * 10,
    })

    # Day 5 (index 4) has an intraday needle spike
    df_full.loc[4, ["open", "high", "low", "close"]] = [100.0, 450.0, 100.0, 100.0]

    # Subset up to Day 5 only (Day 6+ absent)
    df_up_to_day5 = df_full.iloc[:5].copy()

    cleaned_full, glitches_full = clean_transient_price_spikes(df_full)
    cleaned_day5, glitches_day5 = clean_transient_price_spikes(df_up_to_day5)

    assert glitches_full >= 1
    assert glitches_day5 >= 1

    # Crucial assertion: Day 5 output is identical with or without Day 6+ data present
    row_full_day5 = cleaned_full.loc[4]
    row_isolated_day5 = cleaned_day5.loc[4]

    assert row_full_day5["high"] == row_isolated_day5["high"]
    assert row_full_day5["open"] == row_isolated_day5["open"]
    assert row_full_day5["low"] == row_isolated_day5["low"]
    assert row_full_day5["close"] == row_isolated_day5["close"]


def test_clean_transient_price_spikes_flat_tick_repair():
    """Verify flat zero-volume ticks (like CIPLA 2003-04-14) are repaired causally."""
    from blumberg_market_radar.data.validation import clean_transient_price_spikes

    dates = pd.bdate_range("2026-01-01", periods=5, tz="UTC")
    df = pd.DataFrame({
        "date": dates,
        "symbol": "CIPLA",
        "open": [1000.0] * 5,
        "high": [1010.0] * 5,
        "low": [990.0] * 5,
        "close": [1000.0] * 5,
        "volume": [500_000.0] * 5,
    })
    # Glitch on Day 3: zero volume flat tick at 80.0 (prev close was 1000.0)
    df.loc[2, ["open", "high", "low", "close", "volume"]] = [80.0, 80.0, 80.0, 80.0, 0.0]

    cleaned, n_repaired = clean_transient_price_spikes(df)
    assert n_repaired == 1
    assert cleaned.loc[2, "close"] == 1000.0
    assert cleaned.loc[2, "open"] == 1000.0


def test_validate_ohlcv_preserves_extra_columns():
    """Verify validate_ohlcv does not drop auxiliary columns like is_corporate_anomaly or sector."""
    df = sample_bars()
    df["is_corporate_anomaly"] = [False, True]
    df["custom_meta"] = ["val1", "val2"]

    validated = validate_ohlcv(df)
    assert "is_corporate_anomaly" in validated.columns
    assert "custom_meta" in validated.columns
    assert validated["is_corporate_anomaly"].tolist() == [True, False]  # sorted order


def test_cleaner_does_not_rewrite_real_split_with_volume():
    """A genuine 2:1 stock split or flat candle with real volume must NOT be rewritten to prior close."""
    from blumberg_market_radar.data.validation import clean_transient_price_spikes

    dates = pd.bdate_range("2026-01-01", periods=5, tz="UTC")
    df = pd.DataFrame({
        "date": dates,
        "symbol": "TCS",
        "open": [1000.0] * 5,
        "high": [1010.0] * 5,
        "low": [990.0] * 5,
        "close": [1000.0] * 5,
        "volume": [500_000.0] * 5,
    })
    # 2:1 split with 500k shares traded: flat open at 500.0, close at 500.0
    df.loc[2, ["open", "high", "low", "close", "volume"]] = [500.0, 500.0, 500.0, 500.0, 500_000.0]

    cleaned, n_repaired = clean_transient_price_spikes(df)
    # Must NOT be repaired; this is a genuine corporate action with volume, not a data glitch
    assert n_repaired == 0
    assert cleaned.loc[2, "close"] == 500.0
