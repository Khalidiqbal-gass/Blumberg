"""Tests for data ingestion, synthetic market generation, and corporate intel."""
import pandas as pd
from blumberg_market_radar.data.ingestion import generate_synthetic_universe, DEFAULT_INDIAN_UNIVERSE
from blumberg_market_radar.corporate_intel.events import get_corporate_events


def test_synthetic_universe_generation():
    df = generate_synthetic_universe(DEFAULT_INDIAN_UNIVERSE[:5], num_days=50)
    assert not df.empty
    assert set(df.columns) == {"date", "symbol", "open", "high", "low", "close", "volume"}
    assert df["symbol"].nunique() == 5
    assert (df["volume"] > 0).all()
    assert (df["high"] >= df["low"]).all()


def test_corporate_events_structure():
    events = get_corporate_events(["BEL", "MAZDOCK"])
    assert not events.empty
    assert "order_value_cr" in events.columns
    assert "evidence_quote" in events.columns
    assert "source_url" in events.columns
    assert set(events["symbol"].unique()).issubset({"BEL", "MAZDOCK"})
