"""NSE Full-Market Security Master & IPO Engine.

Manages the comprehensive universe of all 2,600+ NSE listed equities, tracking
listing dates, listing ages, IPO categories (Fresh IPO <90D, Recent IPO 90-365D,
Established >1Y), and newly listed equity detection.
"""
from __future__ import annotations

import io
import logging
from pathlib import Path
from typing import Any, Sequence
import urllib.request
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

OFFICIAL_NSE_EQUITY_L_URL = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"
DEFAULT_SECURITY_MASTER_PATH = Path("data/universe/nse_security_master.parquet")
DEFAULT_OFFLINE_CSV_PATH = Path("data/universe/EQUITY_L.csv")


def _categorize_ipo_age(days: int) -> str:
    """Categorize an equity by listing age."""
    if 0 <= days <= 90:
        return "Fresh IPO (<90D)"
    elif 90 < days <= 365:
        return "Recent IPO (90-365D)"
    else:
        return "Established (>1Y)"


def _normalize_raw_security_master(raw_df: pd.DataFrame) -> pd.DataFrame:
    """Normalize raw NSE EQUITY_L dataframe into standardized security master schema."""
    col_map = {str(c).strip().lower(): c for c in raw_df.columns}

    sym_col = col_map.get("symbol", "SYMBOL")
    name_col = col_map.get("name of company", col_map.get("company_name", "NAME OF COMPANY"))
    series_col = col_map.get("series", "SERIES")
    date_col = col_map.get("date of listing", col_map.get("listing_date", "DATE OF LISTING"))
    isin_col = col_map.get("isin number", col_map.get("isin", "ISIN NUMBER"))
    face_val_col = col_map.get("face value", col_map.get("face_value", "FACE VALUE"))

    clean_symbols: list[str] = []
    company_names: list[str] = []
    series_list: list[str] = []
    raw_dates: list[str] = []
    isins: list[str] = []
    face_values: list[float] = []

    for _, row in raw_df.iterrows():
        sym_raw = str(row[sym_col]).strip().upper() if sym_col in raw_df.columns else ""
        if not sym_raw or sym_raw == "NAN":
            continue
        clean_sym = sym_raw.replace(".NS", "").replace(".BO", "")
        name = str(row[name_col]).strip() if name_col in raw_df.columns and not pd.isna(row[name_col]) else f"{clean_sym} Ltd"
        ser = str(row[series_col]).strip().upper() if series_col in raw_df.columns and not pd.isna(row[series_col]) else "EQ"
        dt_val = str(row[date_col]).strip() if date_col in raw_df.columns and not pd.isna(row[date_col]) else ""
        isin_val = str(row[isin_col]).strip() if isin_col in raw_df.columns and not pd.isna(row[isin_col]) else ""
        
        fv_val = 10.0
        if face_val_col in raw_df.columns:
            try:
                fv_val = float(row[face_val_col])
            except (ValueError, TypeError):
                fv_val = 10.0

        clean_symbols.append(clean_sym)
        company_names.append(name)
        series_list.append(ser)
        raw_dates.append(dt_val)
        isins.append(isin_val)
        face_values.append(fv_val)

    # Parse listing dates as Series for safe .dt access
    raw_dates_series = pd.Series(raw_dates)
    parsed_dates = pd.to_datetime(raw_dates_series, format="%d-%b-%Y", errors="coerce")
    if parsed_dates.isna().any():
        unparsed_mask = parsed_dates.isna()
        parsed_dates[unparsed_mask] = pd.to_datetime(
            raw_dates_series[unparsed_mask], format="mixed", errors="coerce"
        )

    today = pd.Timestamp.now().normalize()
    # Age in days
    age_series = (today - parsed_dates).dt.days
    # If date could not be parsed, mark as established (9999 days)
    age_series = age_series.fillna(9999).astype(int)

    is_recent_ipo = (age_series >= 0) & (age_series <= 365)
    is_fresh_listing = (age_series >= 0) & (age_series <= 90)
    ipo_categories = [_categorize_ipo_age(d) for d in age_series]

    out_df = pd.DataFrame({
        "symbol": clean_symbols,
        "company_name": company_names,
        "series": series_list,
        "listing_date": parsed_dates,
        "isin": isins,
        "face_value": face_values,
        "listing_age_days": age_series,
        "is_recent_ipo": is_recent_ipo,
        "is_fresh_listing": is_fresh_listing,
        "ipo_category": ipo_categories,
    })

    return out_df.drop_duplicates(subset=["symbol"]).reset_index(drop=True)


def _generate_synthetic_security_master() -> pd.DataFrame:
    """Fallback generator for synthetic security master when all network and offline sources are absent."""
    from blumberg_market_radar.data.ingestion import NIFTY_500_HIGH_BETA_100
    today = pd.Timestamp.now().normalize()
    records = []
    
    # Generate realistic listings with a portion marked as fresh/recent IPOs
    for idx, sym in enumerate(NIFTY_500_HIGH_BETA_100):
        clean_sym = sym.replace(".NS", "").replace(".BO", "")
        if idx < 10:
            # Fresh IPOs (<90D)
            listing_dt = today - pd.Timedelta(days=15 + idx * 7)
        elif idx < 25:
            # Recent IPOs (90-365D)
            listing_dt = today - pd.Timedelta(days=100 + idx * 10)
        else:
            # Established (>1Y)
            listing_dt = today - pd.Timedelta(days=500 + idx * 50)

        age_days = (today - listing_dt).days
        records.append({
            "symbol": clean_sym,
            "company_name": f"{clean_sym} India Limited",
            "series": "EQ",
            "listing_date": listing_dt,
            "isin": f"INE{idx:03d}A010{idx%10}",
            "face_value": 10.0 if idx % 2 == 0 else 5.0,
            "listing_age_days": age_days,
            "is_recent_ipo": 0 <= age_days <= 365,
            "is_fresh_listing": 0 <= age_days <= 90,
            "ipo_category": _categorize_ipo_age(age_days),
        })

    return pd.DataFrame(records)


def sync_nse_security_master(
    cache_path: Path | str = DEFAULT_SECURITY_MASTER_PATH,
    force_refresh: bool = False,
) -> pd.DataFrame:
    """Ingest official NSE security master with robust offline fallback, parsing, and change tracking.

    - Downloads official NSE security master (`https://archives.nseindia.com/content/equities/EQUITY_L.csv`).
    - Falls back to local cached files or synthetic definitions if offline.
    - Parses columns: `symbol`, `company_name`, `series`, `listing_date`, `isin`, `face_value`.
    - Calculates `listing_age_days = (today - listing_date).days`.
    - Computes `is_recent_ipo` (<=365 days) and `is_fresh_listing` (<=90 days).
    - Categorizes `ipo_category`: "Fresh IPO (<90D)", "Recent IPO (90-365D)", "Established (>1Y)".
    - Identifies newly added symbols compared to previous snapshot.
    - Persists to parquet at `cache_path`.
    - Returns standardized DataFrame with summary metadata in `.attrs`.
    """
    target_cache = Path(cache_path)
    today = pd.Timestamp.now().normalize()

    # 1. Fast Cache Read if not forcing refresh
    if target_cache.exists() and not force_refresh:
        try:
            cached_df = pd.read_parquet(target_cache)
            if not cached_df.empty and "symbol" in cached_df.columns and "listing_date" in cached_df.columns:
                # Recalculate age and flags relative to today's date for fresh point-in-time accuracy
                listing_dates = pd.to_datetime(cached_df["listing_date"], errors="coerce")
                age_series = (today - listing_dates).dt.days.fillna(9999).astype(int)
                cached_df["listing_age_days"] = age_series
                cached_df["is_recent_ipo"] = (age_series >= 0) & (age_series <= 365)
                cached_df["is_fresh_listing"] = (age_series >= 0) & (age_series <= 90)
                cached_df["ipo_category"] = [_categorize_ipo_age(d) for d in age_series]
                cached_df.attrs["newly_added_symbols"] = []
                cached_df.attrs["summary"] = {
                    "total_equities": len(cached_df),
                    "newly_added_count": 0,
                    "newly_added_symbols": [],
                    "recent_ipos_count": int(cached_df["is_recent_ipo"].sum()),
                    "fresh_listings_count": int(cached_df["is_fresh_listing"].sum()),
                }
                return cached_df
        except Exception as read_err:
            logger.warning(f"Failed to read security master parquet cache {target_cache}: {read_err}. Re-syncing.")

    # Track prior snapshot symbols for diffing
    prev_symbols: set[str] = set()
    if target_cache.exists():
        try:
            prior_df = pd.read_parquet(target_cache)
            if "symbol" in prior_df.columns:
                prev_symbols = set(prior_df["symbol"].dropna().astype(str))
        except Exception:
            pass

    raw_df: pd.DataFrame | None = None
    raw_csv_bytes: bytes | None = None

    # 2. Ingest from Official NSE Repository
    try:
        req = urllib.request.Request(
            OFFICIAL_NSE_EQUITY_L_URL,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
            },
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw_csv_bytes = resp.read()
            raw_df = pd.read_csv(io.BytesIO(raw_csv_bytes))
            if raw_df is not None and not raw_df.empty:
                # Cache offline CSV copy
                try:
                    DEFAULT_OFFLINE_CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
                    DEFAULT_OFFLINE_CSV_PATH.write_bytes(raw_csv_bytes)
                except Exception as csv_save_err:
                    logger.debug(f"Could not persist offline CSV backup: {csv_save_err}")
                logger.info(f"Downloaded official NSE security master ({len(raw_df)} rows).")
    except Exception as fetch_err:
        logger.warning(f"Could not download NSE EQUITY_L.csv live: {fetch_err}. Activating offline fallback.")

    # 3. Offline Fallback: Local offline CSV copy
    if raw_df is None or raw_df.empty:
        if DEFAULT_OFFLINE_CSV_PATH.exists():
            try:
                raw_df = pd.read_csv(DEFAULT_OFFLINE_CSV_PATH)
                logger.info(f"Loaded {len(raw_df)} rows from offline CSV fallback {DEFAULT_OFFLINE_CSV_PATH}.")
            except Exception as off_err:
                logger.warning(f"Failed to read offline CSV fallback: {off_err}")

    # 4. Fallback: Existing parquet cache
    if raw_df is None or raw_df.empty:
        if target_cache.exists():
            try:
                return pd.read_parquet(target_cache)
            except Exception:
                pass

    # 5. Last Resort Fallback: Synthetic Security Master
    if raw_df is None or raw_df.empty:
        logger.info("Generating synthetic security master fallback dataset.")
        out_df = _generate_synthetic_security_master()
    else:
        out_df = _normalize_raw_security_master(raw_df)

    # Calculate newly added symbols compared to previous snapshot
    current_symbols = set(out_df["symbol"].dropna().astype(str))
    newly_added = sorted(list(current_symbols - prev_symbols)) if prev_symbols else []

    summary = {
        "total_equities": len(out_df),
        "newly_added_count": len(newly_added),
        "newly_added_symbols": newly_added,
        "recent_ipos_count": int(out_df["is_recent_ipo"].sum()),
        "fresh_listings_count": int(out_df["is_fresh_listing"].sum()),
    }
    out_df.attrs["summary"] = summary
    out_df.attrs["newly_added_symbols"] = newly_added

    logger.info(
        f"NSE Security Master synchronized: {len(out_df)} listed equities tracked. "
        f"Recent IPOs: {summary['recent_ipos_count']}, Fresh Listings: {summary['fresh_listings_count']}. "
        f"Newly added symbols: {len(newly_added)}."
    )

    # Persist to Parquet
    try:
        target_cache.parent.mkdir(parents=True, exist_ok=True)
        out_df.to_parquet(target_cache, index=False)
        logger.info(f"Persisted security master to {target_cache}")
    except Exception as write_err:
        logger.warning(f"Could not persist security master to {target_cache}: {write_err}")

    return out_df


def get_all_nse_symbols(
    series: Sequence[str] = ("EQ", "BE", "BZ", "SM"),
    cache_path: Path | str = DEFAULT_SECURITY_MASTER_PATH,
) -> list[str]:
    """Return list of all active NSE symbols (e.g. 2,600+ clean tickers).
    
    Filters by designated trading series (default EQ, BE, BZ, and SM).
    """
    df = sync_nse_security_master(cache_path=cache_path)
    if df.empty:
        return []
    if series:
        filtered = df[df["series"].isin(series)]
    else:
        filtered = df
    return filtered["symbol"].tolist()


def get_recent_ipo_symbols(
    max_age_days: int = 365,
    cache_path: Path | str = DEFAULT_SECURITY_MASTER_PATH,
) -> list[str]:
    """Return list of equities listed within the designated listing age (default 365 days)."""
    df = sync_nse_security_master(cache_path=cache_path)
    if df.empty:
        return []
    filtered = df[(df["listing_age_days"] >= 0) & (df["listing_age_days"] <= max_age_days)]
    return filtered["symbol"].tolist()


def get_security_master_dict(
    cache_path: Path | str = DEFAULT_SECURITY_MASTER_PATH,
) -> dict[str, dict[str, Any]]:
    """Return fast O(1) lookup dictionary from symbol to security master metadata.
    
    Supports both clean symbol ("ZOMATO") and exchange-suffixed ("ZOMATO.NS").
    """
    df = sync_nse_security_master(cache_path=cache_path)
    if df.empty:
        return {}

    master_dict: dict[str, dict[str, Any]] = {}
    for _, row in df.iterrows():
        sym = str(row["symbol"]).strip().upper()
        clean_sym = sym.replace(".NS", "").replace(".BO", "")
        record = {
            "symbol": clean_sym,
            "company_name": str(row["company_name"]),
            "series": str(row["series"]),
            "listing_date": row["listing_date"],
            "isin": str(row["isin"]),
            "face_value": float(row["face_value"]) if pd.notna(row["face_value"]) else 10.0,
            "listing_age_days": int(row["listing_age_days"]),
            "is_recent_ipo": bool(row["is_recent_ipo"]),
            "is_fresh_listing": bool(row["is_fresh_listing"]),
            "ipo_category": str(row["ipo_category"]),
        }
        master_dict[clean_sym] = record
        master_dict[f"{clean_sym}.NS"] = record

    return master_dict
