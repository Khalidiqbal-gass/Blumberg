"""Unit tests for NSE Full-Market Security Master & IPO Engine."""
import pandas as pd
import numpy as np
from pathlib import Path
import pytest

from blumberg_market_radar.data.security_master import (
    sync_nse_security_master,
    get_all_nse_symbols,
    get_recent_ipo_symbols,
    get_security_master_dict,
    _normalize_raw_security_master,
    _categorize_ipo_age,
)
from blumberg_market_radar.scanner.radar import score_pre_rally_candidates


def test_sync_nse_security_master_structure_and_columns(tmp_path):
    """Test sync of security master: schema structure, column presence, and parsing."""
    test_parquet = tmp_path / "test_sec_master.parquet"
    df = sync_nse_security_master(cache_path=test_parquet, force_refresh=False)

    assert not df.empty
    expected_cols = {
        "symbol",
        "company_name",
        "series",
        "listing_date",
        "isin",
        "face_value",
        "listing_age_days",
        "is_recent_ipo",
        "is_fresh_listing",
        "ipo_category",
    }
    assert expected_cols.issubset(set(df.columns))

    # Validate parsing and data types
    assert pd.api.types.is_datetime64_any_dtype(df["listing_date"])
    assert pd.api.types.is_integer_dtype(df["listing_age_days"])
    assert pd.api.types.is_bool_dtype(df["is_recent_ipo"])
    assert pd.api.types.is_bool_dtype(df["is_fresh_listing"])

    # Symbols must be clean uppercase
    assert all(isinstance(s, str) and s == s.upper() and ".NS" not in s for s in df["symbol"])

    # Verify parquet file was persisted
    assert test_parquet.exists()

    # Verify summary metadata
    assert "summary" in df.attrs
    summary = df.attrs["summary"]
    assert "total_equities" in summary
    assert "recent_ipos_count" in summary
    assert summary["total_equities"] >= 100


def test_calculation_of_listing_age_and_ipo_categories():
    """Test point-in-time calculation of listing age days and 3 IPO categories."""
    today = pd.Timestamp.now().normalize()
    
    # 3 distinct listing vintages
    date_fresh = (today - pd.DateOffset(days=30)).strftime("%d-%b-%Y")
    date_recent = (today - pd.DateOffset(days=180)).strftime("%d-%b-%Y")
    date_established = (today - pd.DateOffset(days=800)).strftime("%d-%b-%Y")

    raw_test_df = pd.DataFrame({
        "SYMBOL": ["FRESH1", "RECENT1", "ESTAB1"],
        "NAME OF COMPANY": ["Fresh IPO Ltd", "Recent IPO Ltd", "Old Giant Ltd"],
        " SERIES": ["EQ", "EQ", "EQ"],
        " DATE OF LISTING": [date_fresh, date_recent, date_established],
        " PAID UP VALUE": [10, 10, 10],
        " MARKET LOT": [1, 1, 1],
        " ISIN NUMBER": ["INE001A01010", "INE002A01010", "INE003A01010"],
        " FACE VALUE": [10, 5, 2],
    })

    normalized = _normalize_raw_security_master(raw_test_df)
    assert len(normalized) == 3

    fresh_row = normalized[normalized["symbol"] == "FRESH1"].iloc[0]
    assert 28 <= fresh_row["listing_age_days"] <= 32
    assert fresh_row["is_recent_ipo"] == True
    assert fresh_row["is_fresh_listing"] == True
    assert fresh_row["ipo_category"] == "Fresh IPO (<90D)"

    recent_row = normalized[normalized["symbol"] == "RECENT1"].iloc[0]
    assert 178 <= recent_row["listing_age_days"] <= 182
    assert recent_row["is_recent_ipo"] == True
    assert recent_row["is_fresh_listing"] == False
    assert recent_row["ipo_category"] == "Recent IPO (90-365D)"

    estab_row = normalized[normalized["symbol"] == "ESTAB1"].iloc[0]
    assert estab_row["listing_age_days"] >= 790
    assert estab_row["is_recent_ipo"] == False
    assert estab_row["is_fresh_listing"] == False
    assert estab_row["ipo_category"] == "Established (>1Y)"


def test_get_all_nse_symbols_and_recent_ipos():
    """Test retrieval of active clean symbols and recent IPO symbol subsets."""
    all_symbols = get_all_nse_symbols(series=("EQ", "BE"))
    assert isinstance(all_symbols, list)
    assert len(all_symbols) >= 100
    # Confirm clean formatting without exchange suffix
    for s in all_symbols[:20]:
        assert "." not in s

    recent_ipos = get_recent_ipo_symbols(max_age_days=365)
    assert isinstance(recent_ipos, list)
    assert len(recent_ipos) > 0
    assert set(recent_ipos).issubset(set(get_all_nse_symbols(series=None)))

    # Test dictionary lookup
    sec_dict = get_security_master_dict()
    assert isinstance(sec_dict, dict)
    sample_sym = all_symbols[0]
    
    # Both bare symbol and .NS suffixed key must resolve to the record
    assert sample_sym in sec_dict
    assert f"{sample_sym}.NS" in sec_dict
    record = sec_dict[sample_sym]
    assert "company_name" in record
    assert "ipo_category" in record
    assert "listing_age_days" in record


def test_ipo_base_detection_in_scanner(tmp_path):
    """Test IPO Base Consolidation setup detection in candidate scoring.

    If is_recent_ipo is True and compression_ratio < 0.70:
    - Primary driver must be '🌟 Fresh IPO Base Accumulation'
    - Reason codes must include 'Recent IPO Listing' and 'Post-Listing Volatility Squeeze'.
    """
    # Create test master with one recent IPO and one established stock
    today = pd.Timestamp.now().normalize()
    custom_master = pd.DataFrame([
        {
            "symbol": "IPOLEADER",
            "company_name": "IPO Leader Tech Ltd",
            "series": "EQ",
            "listing_date": today - pd.DateOffset(days=60),
            "isin": "INE999A01011",
            "face_value": 10.0,
            "listing_age_days": 60,
            "is_recent_ipo": True,
            "is_fresh_listing": True,
            "ipo_category": "Fresh IPO (<90D)",
        },
        {
            "symbol": "OLDGIANT",
            "company_name": "Old Giant Corp Ltd",
            "series": "EQ",
            "listing_date": today - pd.DateOffset(days=2000),
            "isin": "INE888A01012",
            "face_value": 10.0,
            "listing_age_days": 2000,
            "is_recent_ipo": False,
            "is_fresh_listing": False,
            "ipo_category": "Established (>1Y)",
        },
    ])
    master_path = tmp_path / "custom_master.parquet"
    custom_master.to_parquet(master_path, index=False)

    # Mock the default cache path to test path during scoring
    features = pd.DataFrame([
        {
            "symbol": "IPOLEADER",
            "date": today,
            "close": 240.0,
            "range_compression_ratio": 0.52,  # Compression < 0.70 triggers IPO base
            "relative_volume_20d": 1.9,
            "volume_dry_up_ratio": 0.70,
            "rs_20d": 0.08,
            "sector_rs_20d": 0.05,
            "return_5d": 0.03,
            "return_20d": 0.08,
            "dist_to_52w_high_pct": -4.0,
            "is_breakout_20d": False,
            "atr_pct": 2.2,
            "avg_turnover_20d_cr": 15.0,
        },
        {
            "symbol": "OLDGIANT",
            "date": today,
            "close": 1500.0,
            "range_compression_ratio": 0.52,  # Established base
            "relative_volume_20d": 1.2,
            "volume_dry_up_ratio": 0.90,
            "rs_20d": 0.01,
            "sector_rs_20d": 0.0,
            "return_5d": 0.01,
            "return_20d": 0.02,
            "dist_to_52w_high_pct": -15.0,
            "is_breakout_20d": False,
            "atr_pct": 1.8,
            "avg_turnover_20d_cr": 50.0,
        },
    ])

    # Score with the custom security master via mock/patch or direct sync
    import blumberg_market_radar.scanner.radar as radar_mod
    original_dict_func = radar_mod.get_security_master_dict

    try:
        radar_mod.get_security_master_dict = lambda: get_security_master_dict(cache_path=master_path)
        candidates = score_pre_rally_candidates(features, min_turnover_cr=1.0)
    finally:
        radar_mod.get_security_master_dict = original_dict_func

    assert len(candidates) == 2
    ipo_cand = candidates[candidates["symbol"] == "IPOLEADER"].iloc[0]
    old_cand = candidates[candidates["symbol"] == "OLDGIANT"].iloc[0]

    # IPO Leader checks
    assert ipo_cand["is_recent_ipo"] == True
    assert ipo_cand["ipo_category"] == "Fresh IPO (<90D)"
    assert ipo_cand["primary_driver"] == "🌟 Fresh IPO Base Accumulation"
    assert "Recent IPO Listing" in ipo_cand["reason_codes"]
    assert "Post-Listing Volatility Squeeze" in ipo_cand["reason_codes"]

    # Old Giant checks
    assert old_cand["is_recent_ipo"] == False
    assert old_cand["primary_driver"] != "🌟 Fresh IPO Base Accumulation"


def test_security_master_diff_tracks_newly_added_symbols(tmp_path):
    """Test that syncing tracks new listings compared to a previous snapshot."""
    snap1_path = tmp_path / "snap.parquet"
    today = pd.Timestamp.now().normalize()
    
    # Snapshot 1 with 2 symbols
    df1 = pd.DataFrame([
        {
            "symbol": "SYM1",
            "company_name": "Sym 1 Ltd",
            "series": "EQ",
            "listing_date": today - pd.DateOffset(days=200),
            "isin": "INE111",
            "face_value": 10.0,
            "listing_age_days": 200,
            "is_recent_ipo": True,
            "is_fresh_listing": False,
            "ipo_category": "Recent IPO (90-365D)",
        },
    ])
    df1.to_parquet(snap1_path, index=False)

    # Sync using local CSV fallback with more symbols
    raw_df2 = pd.DataFrame({
        "SYMBOL": ["SYM1", "NEWLISTING"],
        "NAME OF COMPANY": ["Sym 1 Ltd", "New Listing Ltd"],
        " SERIES": ["EQ", "EQ"],
        " DATE OF LISTING": [today.strftime("%d-%b-%Y"), today.strftime("%d-%b-%Y")],
        " PAID UP VALUE": [10, 10],
        " MARKET LOT": [1, 1],
        " ISIN NUMBER": ["INE111", "INE222"],
        " FACE VALUE": [10, 10],
    })
    
    # Mock offline CSV
    test_csv = tmp_path / "EQUITY_L.csv"
    raw_df2.to_csv(test_csv, index=False)

    import blumberg_market_radar.data.security_master as sm_mod
    orig_url = sm_mod.OFFICIAL_NSE_EQUITY_L_URL
    orig_csv = sm_mod.DEFAULT_OFFLINE_CSV_PATH

    try:
        sm_mod.OFFICIAL_NSE_EQUITY_L_URL = "http://invalid-test-domain-12345.com/EQUITY_L.csv"
        sm_mod.DEFAULT_OFFLINE_CSV_PATH = test_csv
        df_synced = sync_nse_security_master(cache_path=snap1_path, force_refresh=True)
    finally:
        sm_mod.OFFICIAL_NSE_EQUITY_L_URL = orig_url
        sm_mod.DEFAULT_OFFLINE_CSV_PATH = orig_csv

    assert "NEWLISTING" in df_synced.attrs["newly_added_symbols"]
    assert df_synced.attrs["summary"]["newly_added_count"] == 1
