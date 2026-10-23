"""Unit and integration tests for Angel One SmartAPI connector and data caching."""
from pathlib import Path
import pandas as pd
import pytest

from blumberg_market_radar.connectors.angel_one import AngelOneConnector, get_angel_connector
from blumberg_market_radar.data.ingestion import fetch_historical_ohlcv, fetch_benchmark


def test_angel_one_token_resolution():
    conn = AngelOneConnector()
    # Test top equities tokens
    rel_token = conn.get_token_for_symbol("RELIANCE")
    assert rel_token == "2885"

    tcs_token = conn.get_token_for_symbol("TCS.NS")
    assert tcs_token == "11536"

    # Test Nifty benchmark token
    nifty_token = conn.get_token_for_symbol("NIFTY50")
    assert nifty_token == "99926000"


def test_angel_one_local_parquet_cache(tmp_path: Path):
    cache_dir = tmp_path / "angel_cache"
    conn = AngelOneConnector(cache_dir=cache_dir)

    # Empty cache check
    assert conn.get_cached_candles("TESTSYM") is None

    # Save mock candles
    mock_df = pd.DataFrame({
        "date": pd.date_range("2026-01-01", periods=5, freq="D", tz="UTC"),
        "open": [100.0, 102.0, 101.0, 103.0, 105.0],
        "high": [103.0, 104.0, 103.0, 106.0, 107.0],
        "low": [99.0, 101.0, 100.0, 102.0, 104.0],
        "close": [102.0, 101.0, 103.0, 105.0, 106.0],
        "volume": [10000, 12000, 15000, 11000, 20000],
    })
    conn.save_cached_candles("TESTSYM", mock_df)

    # Retrieve from cache
    cached = conn.get_cached_candles("TESTSYM")
    assert cached is not None
    assert len(cached) == 5
    assert (cached["close"] == mock_df["close"]).all()


def test_get_angel_connector_singleton():
    c1 = get_angel_connector()
    c2 = get_angel_connector()
    assert c1 is c2


def test_fetch_historical_ohlcv_with_angel_one_mode():
    # If uncached or offline, fetch_historical_ohlcv gracefully returns valid frame
    df = fetch_historical_ohlcv(
        symbols=["RELIANCE.NS", "TCS.NS"],
        period="1mo",
        data_source="angel_one",
        use_cache=True,
    )
    assert not df.empty
    assert "close" in df.columns
    assert "volume" in df.columns
    assert df["symbol"].nunique() >= 1
