"""Download additional high-growth multibaggers and compile the unified 2015-2026 historical universe."""
from __future__ import annotations

import logging
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s]: %(message)s")
logger = logging.getLogger("merge_2015_2026")

OUTPUT_DIR = Path("data/cache/historical_2015_2026")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

ADDITIONAL_MULTIBAGGERS = [
    "DIXON.NS",       # EMS & Consumer Tech
    "POLYCAB.NS",     # Wires & Cables Infrastructure
    "HAL.NS",         # Defence & Fighter Aircraft
    "BDL.NS",         # Defence Missiles & Torpedoes
    "COCHINSHIP.NS",  # Defence Shipyard & Aircraft Carrier
    "GRSE.NS",        # Defence Frigates & Warships
    "BSE.NS",         # Financial Exchange & Trading
    "CDSL.NS",        # Depository & Retail Accounts
    "RVNL.NS",        # Railway Electrification & Track Infrastructure
    "MAZDOCK.NS",     # Defence Submarines & Destroyers
    "IRFC.NS",        # Railway Infrastructure Financing
    "KALYANKJIL.NS",  # Jewellery & Retail Multibagger
    "TITAGARH.NS",    # Railway Wagons & Vande Bharat Metro
]


def create_unified_2015_2026_dataset(start_date: str = "2015-01-01", end_date: str = "2026-10-22") -> pd.DataFrame:
    """Combine core historical 39 equities with additional high-growth multibaggers."""
    # 1. Load core historical dataset
    core_parquet = Path("data/cache/historical_2010_2026/market_bars_2010_2026.parquet")
    bench_parquet = Path("data/cache/historical_2010_2026/nifty50_bench_2010_2026.parquet")
    
    if not core_parquet.exists():
        raise FileNotFoundError(f"{core_parquet} not found!")

    logger.info("Loading existing 16-year core dataset...")
    core_df = pd.read_parquet(core_parquet)
    bench_df = pd.read_parquet(bench_parquet)

    # Filter core to 2015-2026
    core_df["date"] = pd.to_datetime(core_df["date"], utc=True)
    bench_df["date"] = pd.to_datetime(bench_df["date"], utc=True)
    
    core_filtered = core_df[(core_df["date"] >= start_date) & (core_df["date"] <= end_date)].copy()
    bench_filtered = bench_df[(bench_df["date"] >= start_date) & (bench_df["date"] <= end_date)].copy()
    logger.info(f"Core equities 2015-2026: {len(core_filtered):,} bars across {core_filtered['symbol'].nunique()} equities.")

    # 2. Download additional multibaggers
    logger.info(f"Downloading {len(ADDITIONAL_MULTIBAGGERS)} additional growth multibaggers...")
    raw = yf.download(ADDITIONAL_MULTIBAGGERS, start=start_date, end=end_date, group_by="ticker", progress=False)

    extra_records: list[pd.DataFrame] = []
    for sym in ADDITIONAL_MULTIBAGGERS:
        try:
            sub = raw[sym].copy().dropna(how="all")
            if sub.empty or "Close" not in sub.columns:
                logger.warning(f"No valid data for {sym}")
                continue
            df_sym = pd.DataFrame({
                "date": pd.to_datetime(sub.index, utc=True),
                "open": sub["Open"].values.flatten(),
                "high": sub["High"].values.flatten(),
                "low": sub["Low"].values.flatten(),
                "close": sub["Close"].values.flatten(),
                "volume": sub["Volume"].values.flatten(),
                "symbol": sym,
            }).dropna()
            clean_sym = sym.replace(".NS", "").replace(".BO", "")
            df_sym["clean_sym"] = clean_sym
            extra_records.append(df_sym)
            logger.info(f"Downloaded {sym}: {len(df_sym)} sessions (from {df_sym['date'].min().strftime('%Y-%m-%d')})")
        except Exception as e:
            logger.warning(f"Failed to process {sym}: {e}")

    # Combine all
    if extra_records:
        extra_df = pd.concat(extra_records, ignore_index=True)
        combined_df = pd.concat([core_filtered, extra_df], ignore_index=True)
    else:
        combined_df = core_filtered

    # Clean precision & candle consistency
    combined_df["high"] = np.maximum(combined_df["high"], np.maximum(combined_df["open"], combined_df["close"]))
    combined_df["low"] = np.minimum(combined_df["low"], np.minimum(combined_df["open"], combined_df["close"]))
    bench_filtered["high"] = np.maximum(bench_filtered["high"], np.maximum(bench_filtered["open"], bench_filtered["close"]))
    bench_filtered["low"] = np.minimum(bench_filtered["low"], np.minimum(bench_filtered["open"], bench_filtered["close"]))

    combined_df = combined_df.drop_duplicates(subset=["symbol", "date"]).sort_values(["symbol", "date"]).reset_index(drop=True)
    bench_filtered = bench_filtered.drop_duplicates(subset=["date"]).sort_values("date").reset_index(drop=True)

    # Save to disk
    target_combined = OUTPUT_DIR / "market_bars_2015_2026.parquet"
    target_bench = OUTPUT_DIR / "nifty50_bench_2015_2026.parquet"

    combined_df.to_parquet(target_combined, index=False)
    bench_filtered.to_parquet(target_bench, index=False)

    logger.info(f"✅ Saved unified dataset: {len(combined_df):,} bars across {combined_df['symbol'].nunique()} equities -> {target_combined}")
    logger.info(f"✅ Saved benchmark: {len(bench_filtered):,} sessions -> {target_bench}")
    return combined_df


if __name__ == "__main__":
    create_unified_2015_2026_dataset()
