"""Download and cache 16-year historical daily OHLCV bars (2010-2026) for multi-phase backtesting."""
from __future__ import annotations

import logging
from pathlib import Path
import pandas as pd
import yfinance as yf

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s]: %(message)s")
logger = logging.getLogger("historical_downloader")

OUTPUT_DIR = Path("data/cache/historical_2010_2026")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

CORE_HISTORICAL_UNIVERSE = [
    # Benchmark
    "^NSEI",
    # Banking & Financial Services
    "HDFCBANK.NS", "ICICIBANK.NS", "SBIN.NS", "AXISBANK.NS", "KOTAKBANK.NS", "BAJFINANCE.NS",
    # IT & Digital Leaders
    "TCS.NS", "INFY.NS", "WIPRO.NS", "HCLTECH.NS",
    # Capital Goods, Engineering, Power & Defence
    "LT.NS", "BEL.NS", "BHEL.NS", "TATAPOWER.NS", "SIEMENS.NS", "ABB.NS", "CUMMINSIND.NS",
    # Metals, Mining & Resources
    "TATASTEEL.NS", "HINDALCO.NS", "JINDALSTEL.NS", "SAIL.NS", "VEDL.NS",
    # Automotive & EV Supply Chain
    "MARUTI.NS", "M&M.NS", "BAJAJ-AUTO.NS", "ASHOKLEY.NS", "BHARATFORG.NS", "APOLLOTYRE.NS",
    # Telecom & Optical Networks
    "BHARTIARTL.NS", "HFCL.NS", "STLTECH.NS",
    # Consumer & Retail Multibaggers
    "TITAN.NS", "TRENT.NS", "ASIANPAINT.NS", "PIDILITIND.NS", "HINDUNILVR.NS", "ITC.NS", "BRITANNIA.NS", "SUZLON.NS",
]


def download_and_save_all(start_date: str = "2010-01-01", end_date: str = "2026-10-22") -> pd.DataFrame:
    combined_parquet = OUTPUT_DIR / "market_bars_2010_2026.parquet"
    bench_parquet = OUTPUT_DIR / "nifty50_bench_2010_2026.parquet"

    if combined_parquet.exists() and bench_parquet.exists():
        logger.info(f"Historical parquet cache already exists at {combined_parquet}. Loading...")
        return pd.read_parquet(combined_parquet)

    logger.info(f"Downloading historical daily bars for {len(CORE_HISTORICAL_UNIVERSE)} instruments ({start_date} to {end_date})...")

    # Download benchmark first
    logger.info("Downloading NIFTY 50 Benchmark (^NSEI)...")
    bench_raw = yf.download("^NSEI", start=start_date, end=end_date, progress=False)
    if not bench_raw.empty:
        bench_df = pd.DataFrame({
            "date": pd.to_datetime(bench_raw.index, utc=True),
            "open": bench_raw["Open"].values.flatten(),
            "high": bench_raw["High"].values.flatten(),
            "low": bench_raw["Low"].values.flatten(),
            "close": bench_raw["Close"].values.flatten(),
            "volume": bench_raw["Volume"].values.flatten(),
            "symbol": "NIFTY50",
        }).dropna().drop_duplicates(subset=["date"]).sort_values("date").reset_index(drop=True)
        bench_df.to_parquet(bench_parquet, index=False)
        logger.info(f"Saved {len(bench_df)} benchmark bars to {bench_parquet}")

    # Download equities
    symbols = [s for s in CORE_HISTORICAL_UNIVERSE if s != "^NSEI"]
    logger.info(f"Downloading {len(symbols)} Indian equities...")
    raw = yf.download(symbols, start=start_date, end=end_date, group_by="ticker", progress=False)

    records: list[pd.DataFrame] = []
    for sym in symbols:
        try:
            sub = raw[sym].copy().dropna(how="all")
            if sub.empty or "Close" not in sub.columns:
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
            # Clean symbol
            clean_sym = sym.replace(".NS", "").replace(".BO", "")
            df_sym["clean_sym"] = clean_sym
            records.append(df_sym)
            logger.info(f"Processed {sym}: {len(df_sym)} trading sessions.")
        except Exception as e:
            logger.warning(f"Failed to process {sym}: {e}")

    if not records:
        logger.error("No equity records downloaded!")
        return pd.DataFrame()

    full_df = pd.concat(records, ignore_index=True)
    full_df = full_df.drop_duplicates(subset=["symbol", "date"]).sort_values(["symbol", "date"]).reset_index(drop=True)
    full_df.to_parquet(combined_parquet, index=False)
    logger.info(f"Successfully saved {len(full_df):,} bars across {full_df['symbol'].nunique()} equities -> {combined_parquet}")
    return full_df


if __name__ == "__main__":
    download_and_save_all()
