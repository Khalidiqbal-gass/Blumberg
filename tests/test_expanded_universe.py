"""Unit tests for expanded Indian equities universe, sector mapping, and pre-rally screening."""
from __future__ import annotations

from pathlib import Path
import pandas as pd
import pytest

from blumberg_market_radar.data.ingestion import (
    DEFAULT_INDIAN_UNIVERSE,
    NIFTY_MOMENTUM_UNIVERSE_50,
    NIFTY_SMALLCAP_GROWTH,
    NIFTY_500_HIGH_BETA_100,
    get_symbol_sector_map,
    fetch_nifty500_symbol_list,
    generate_synthetic_universe,
    fetch_historical_ohlcv,
    _deterministic_base_price,
)
from blumberg_market_radar.scanner.radar import (
    compute_pre_rally_features,
    score_pre_rally_candidates,
)


def test_get_symbol_sector_map_returns_valid_sectors():
    """Verify get_symbol_sector_map maps Indian equities across all required growth sectors."""
    sector_map = get_symbol_sector_map(include_nifty500=True)
    assert isinstance(sector_map, dict)
    assert len(sector_map) >= 100

    # Test key thematic sector assignments
    assert sector_map.get("HAL") == "Defence & Aerospace"
    assert sector_map.get("HAL.NS") == "Defence & Aerospace"
    assert sector_map.get("BEL") == "Defence & Aerospace"
    assert sector_map.get("MAZDOCK") == "Defence & Aerospace"
    assert sector_map.get("RVNL") == "Railways & Infra"
    assert sector_map.get("TITAGARH") == "Railways & Infra"
    assert sector_map.get("SUZLON") == "Green Energy & Wind"
    assert sector_map.get("INOXWIND") == "Green Energy & Wind"
    assert sector_map.get("DIXON") == "EMS & Technology"
    assert sector_map.get("KAYNES") == "EMS & Technology"
    assert sector_map.get("BSE") == "Financial Market Infrastructure"
    assert sector_map.get("CDSL") == "Financial Market Infrastructure"
    assert sector_map.get("BHEL") == "Capital Goods"
    assert sector_map.get("TRENT") == "Consumer & Retail"
    assert sector_map.get("KPITTECH") == "IT & Digital Transformation"

    # Ensure no empty or None sectors
    for sym, sec in sector_map.items():
        assert sym and isinstance(sym, str)
        assert sec and isinstance(sec, str)


def test_fetch_nifty500_symbol_list_structure():
    """Verify fetch_nifty500_symbol_list returns validated DataFrame with symbols and sectors."""
    nifty_df = fetch_nifty500_symbol_list()
    assert isinstance(nifty_df, pd.DataFrame)
    assert not nifty_df.empty
    assert len(nifty_df) >= 100

    expected_cols = {"symbol", "company_name", "industry", "sector"}
    assert expected_cols.issubset(set(nifty_df.columns))

    # Check clean symbols
    assert (nifty_df["symbol"].str.contains(r"\.NS$|\.BO$", regex=True) == False).all()
    assert (nifty_df["symbol"].str.isupper()).all()
    assert (nifty_df["sector"].str.len() > 0).all()


def test_curated_universe_definitions():
    """Verify integrity of curated lists: sizes, uniqueness, and suffix conventions."""
    assert len(NIFTY_MOMENTUM_UNIVERSE_50) == 50
    assert len(set(NIFTY_MOMENTUM_UNIVERSE_50)) == 50
    assert all(s.endswith(".NS") for s in NIFTY_MOMENTUM_UNIVERSE_50)

    assert len(NIFTY_SMALLCAP_GROWTH) >= 20
    assert len(set(NIFTY_SMALLCAP_GROWTH)) == len(NIFTY_SMALLCAP_GROWTH)
    assert all(s.endswith(".NS") for s in NIFTY_SMALLCAP_GROWTH)

    assert len(NIFTY_500_HIGH_BETA_100) == 100
    assert len(set(NIFTY_500_HIGH_BETA_100)) == 100

    # Ensure DEFAULT_INDIAN_UNIVERSE is completely preserved in the momentum 50
    assert set(DEFAULT_INDIAN_UNIVERSE).issubset(set(NIFTY_MOMENTUM_UNIVERSE_50))


def test_generate_synthetic_universe_expanded():
    """Verify generate_synthetic_universe seamlessly handles 50+ symbols with diverse prices."""
    bars = generate_synthetic_universe(NIFTY_MOMENTUM_UNIVERSE_50, num_days=30)
    assert not bars.empty
    assert set(bars.columns) == {"date", "symbol", "open", "high", "low", "close", "volume"}
    assert bars["symbol"].nunique() == 50
    assert (bars["volume"] > 0).all()
    assert (bars["high"] >= bars["low"]).all()
    assert (bars["high"] >= bars[["open", "close"]].max(axis=1)).all()
    assert (bars["low"] <= bars[["open", "close"]].min(axis=1)).all()

    # Verify diverse price span (from < ₹100 to > ₹5,000)
    min_price = bars["close"].min()
    max_price = bars["close"].max()
    assert min_price < 150.0  # E.g. SUZLON around ₹75
    assert max_price > 5000.0  # E.g. DIXON around ₹12,500, TRENT around ₹7,200


def test_score_pre_rally_candidates_includes_sector_and_price_tiers():
    """Verify radar scanner populates sector metadata, sector relative strength, and price tiers."""
    sample_symbols = [
        "SUZLON", "BEL", "HAL", "MAZDOCK", "DIXON",
        "KAYNES", "RVNL", "TITAGARH", "BSE", "TRENT",
        "RELIANCE", "TCS", "HDFCBANK", "TATAMOTORS"
    ]
    bars = generate_synthetic_universe(sample_symbols, num_days=60)
    features = compute_pre_rally_features(bars)

    assert "sector" in features.columns
    assert "sector_return_20d" in features.columns
    assert "sector_rs_20d" in features.columns

    scored = score_pre_rally_candidates(features, min_turnover_cr=0.1)
    assert not scored.empty
    assert "sector" in scored.columns
    assert "price_tier" in scored.columns
    assert "sector_rs_20d_pct" in scored.columns
    assert "radar_score" in scored.columns

    # Verify valid sectors and price tiers
    valid_tiers = {
        "Small Cap / Micro (₹<50)",
        "Mid Tier (₹50 - ₹500)",
        "Large Tier (₹500 - ₹2,000)",
        "Premium Tier (₹2,000+)",
    }
    for _, row in scored.iterrows():
        assert row["sector"] and isinstance(row["sector"], str)
        assert row["price_tier"] in valid_tiers
        assert 0.0 <= row["radar_score"] <= 100.0


def test_universe_batch_caching(tmp_path: Path):
    """Verify parquet caching per universe batch."""
    cache_file = tmp_path / "custom_universe_cache.parquet"
    assert not cache_file.exists()

    # First fetch writes to parquet cache
    symbols = ["BEL", "SUZLON", "HAL"]
    df1 = fetch_historical_ohlcv(symbols, period="3mo", cache_path=cache_file, use_cache=True)
    assert cache_file.exists()
    assert not df1.empty

    # Second fetch reads directly from cache
    df2 = fetch_historical_ohlcv(symbols, period="3mo", cache_path=cache_file, use_cache=True)
    assert len(df1) == len(df2)
    assert set(df1["symbol"].unique()) == set(df2["symbol"].unique())
