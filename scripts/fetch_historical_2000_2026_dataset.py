"""
Historical Ingestion Runner (2000 - 2026):
Fetches 26 years of daily OHLCV bars for Indian Equities & Benchmark (BSE Sensex / Nifty 50).
Saves clean consolidated Parquet files for institutional-grade multi-phase backtesting.
"""
from __future__ import annotations

import logging
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s]: %(message)s")
logger = logging.getLogger("fetch_2000_2026")

OUTPUT_DIR = Path("data/cache/historical_2000_2026")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Broad universe spanning ancient market leaders (2000s) to modern multibaggers (2020s)
SYMBOLS = [
    # Vintage 2000s Pillars & IT Giants
    "RELIANCE.NS", "INFY.NS", "WIPRO.NS", "TCS.NS", "HCLTECH.NS",
    # Banking & NBFC Compounders
    "HDFCBANK.NS", "ICICIBANK.NS", "SBIN.NS", "AXISBANK.NS", "KOTAKBANK.NS", "BAJFINANCE.NS",
    # Metals, Infra, Power & Capital Goods (2003-2007 Bull Run Heroes)
    "TATASTEEL.NS", "JSWSTEEL.NS", "HINDALCO.NS", "LT.NS", "BHEL.NS", "TATAPOWER.NS", "GRASIM.NS",
    # FMCG & Consumption Multibaggers
    "TITAN.NS", "ITC.NS", "HINDUNILVR.NS", "ASIANPAINT.NS", "BRITANNIA.NS", "TRENT.NS",
    # Pharma & Healthcare Defenders
    "CIPLA.NS", "SUNPHARMA.NS", "DRREDDY.NS", "DIVISLAB.NS", "LUPIN.NS",
    # Energy, Oil & PSU Leaders
    "BPCL.NS", "ONGC.NS", "GAIL.NS", "BEL.NS",
    # Auto & Manufacturing Leaders
    "MARUTI.NS", "MAHMSTEEL.NS", "EICHERMOT.NS",
    # Modern Multibaggers (2015-2026)
    "POLYCAB.NS", "DIXON.NS", "HAL.NS", "BDL.NS", "MAZDOCK.NS"
]


def fetch_and_save():
    logger.info("=" * 80)
    logger.info("FETCHING 2000 - 2026 (26 YEARS) HISTORICAL MARKET DATASET")
    logger.info("=" * 80)

    # 1. Fetch Benchmark: BSE Sensex (^BSESN) starts 2000-01-03, Nifty starts 2007-09-17
    logger.info("Downloading BSE SENSEX (^BSESN) benchmark from 2000 to 2026...")
    bench_raw = yf.download("^BSESN", start="2000-01-01", end="2026-10-24", progress=False)
    if isinstance(bench_raw.columns, pd.MultiIndex):
        bench_raw.columns = bench_raw.columns.get_level_values(0)
    
    bench_df = bench_raw.reset_index()
    bench_df.columns = [c.lower() for c in bench_df.columns]
    bench_df.rename(columns={"date": "date"}, inplace=True)
    bench_df["date"] = pd.to_datetime(bench_df["date"]).dt.tz_localize(None)
    bench_df["symbol"] = "SENSEX"
    bench_df = bench_df.sort_values("date").dropna(subset=["close"])
    
    bench_path = OUTPUT_DIR / "sensex_bench_2000_2026.parquet"
    bench_df.to_parquet(bench_path, index=False)
    logger.info(f"Saved Benchmark: {len(bench_df):,} bars from {bench_df['date'].min().date()} to {bench_df['date'].max().date()} -> {bench_path}")

    # 2. Fetch Equity Bars
    logger.info(f"Downloading {len(SYMBOLS)} Indian Equities across 2000 - 2026...")
    raw_data = yf.download(SYMBOLS, start="2000-01-01", end="2026-10-24", group_by="ticker", threads=True, progress=False)

    all_dfs: list[pd.DataFrame] = []
    
    for sym in SYMBOLS:
        try:
            if sym in raw_data.columns.levels[0]:
                sub = raw_data[sym].dropna(how="all").copy()
                if sub.empty or len(sub) < 50:
                    continue
                sub = sub.reset_index()
                sub.columns = [c.lower() for c in sub.columns]
                sub["date"] = pd.to_datetime(sub["date"]).dt.tz_localize(None)
                sub["symbol"] = sym.replace(".NS", "").replace(".BO", "")
                
                # Ensure standard OHLCV
                for col in ["open", "high", "low", "close", "volume"]:
                    if col in sub.columns:
                        sub[col] = pd.to_numeric(sub[col], errors="coerce")
                
                sub = sub.dropna(subset=["close", "volume"])
                sub = sub[sub["close"] > 0]
                if not sub.empty:
                    all_dfs.append(sub[["symbol", "date", "open", "high", "low", "close", "volume"]])
                    logger.info(f"  + {sym}: {len(sub):,} bars ({sub['date'].min().date()} to {sub['date'].max().date()})")
        except Exception as e:
            logger.warning(f"Failed processing {sym}: {e}")

    if not all_dfs:
        raise RuntimeError("No equity data fetched!")

    consolidated_df = pd.concat(all_dfs, ignore_index=True)
    consolidated_df = consolidated_df.sort_values(["symbol", "date"]).reset_index(drop=True)
    
    market_path = OUTPUT_DIR / "market_bars_2000_2026.parquet"
    consolidated_df.to_parquet(market_path, index=False)
    logger.info("=" * 80)
    logger.info(f"CONSOLIDATED DATASET SAVED: {len(consolidated_df):,} bars across {consolidated_df['symbol'].nunique()} equities -> {market_path}")
    logger.info("=" * 80)
    return market_path, bench_path


if __name__ == "__main__":
    fetch_and_save()
