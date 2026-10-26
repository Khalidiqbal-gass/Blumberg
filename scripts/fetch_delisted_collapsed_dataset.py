"""
Delisted & Collapsed Equities Ingestion Runner (2000 - 2026):
Fetches daily OHLCV bars for 27 notorious historical crashed, bankrupt, restructured,
and bubble-burst Indian equities (Unitech, RCOM, RPOWER, Jet Airways, Educomp, HDIL, Yes Bank, etc.).
Consolidates them with the 64-equity universe into a Survivorship-Tensioned Dataset.
"""
from __future__ import annotations

import logging
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s]: %(message)s")
logger = logging.getLogger("fetch_delisted")

DATA_DIR = Path("data/cache/historical_2000_2026")
DATA_DIR.mkdir(parents=True, exist_ok=True)

COLLAPSED_SYMBOLS = [
    # Mega Bubble & Collapse (2006-2008 Real Estate & Infra heroes that fell 95-99%)
    "UNITECH.NS", "RCOM.NS", "RPOWER.NS", "RELINFRA.NS", "JETAIRWAYS.NS",
    "EDUCOMP.NS", "HDIL.NS", "GVKPIL.NS", "ABAN.NS", "HCC.NS",
    "JPPOWER.NS", "GTLINFRA.NS", "DBREALTY.NS", "PARSVNATH.NS", "ANSALAPI.NS",
    # Banking & NBFC Crises / Credit Freeze
    "YESBANK.NS", "DHANBANK.NS",
    # Corporate Governance, Auditor Resignations & Frauds (fell 85-95%)
    "VAKRANGEE.NS", "PCJEWELLER.NS", "CGPOWER.NS", "FORTIS.NS",
    # Insolvency, Disruption & Sector Wipeouts
    "ALOKINDS.NS", "IDEA.NS", "DISHTV.NS", "MTNL.NS", "OPTOCIRCUI.BO", "GMRAIRPORT.NS"
]


def run_ingestion():
    logger.info("=" * 80)
    logger.info(f"FETCHING {len(COLLAPSED_SYMBOLS)} HISTORICAL COLLAPSED/DISTRESSED INDIAN EQUITIES")
    logger.info("=" * 80)

    # 1. Download collapsed tickers
    raw = yf.download(COLLAPSED_SYMBOLS, start="2000-01-01", end="2026-10-24", group_by="ticker", threads=True, progress=False)

    new_dfs: list[pd.DataFrame] = []
    for sym in COLLAPSED_SYMBOLS:
        try:
            if sym in raw.columns.levels[0]:
                sub = raw[sym].dropna(how="all").copy()
                if sub.empty or len(sub) < 50:
                    logger.warning(f"  - {sym}: Insufficient bars (<50)")
                    continue
                sub = sub.reset_index()
                sub.columns = [c.lower() for c in sub.columns]
                sub["date"] = pd.to_datetime(sub["date"]).dt.tz_localize(None)
                clean_sym = sym.replace(".NS", "").replace(".BO", "")
                sub["symbol"] = clean_sym

                for col in ["open", "high", "low", "close", "volume"]:
                    if col in sub.columns:
                        sub[col] = pd.to_numeric(sub[col], errors="coerce")

                sub = sub.dropna(subset=["close", "volume"])
                sub = sub[sub["close"] > 0]
                if not sub.empty:
                    new_dfs.append(sub[["symbol", "date", "open", "high", "low", "close", "volume"]])
                    logger.info(f"  + Captured Collapsed Stock {clean_sym}: {len(sub):,} bars ({sub['date'].min().date()} to {sub['date'].max().date()})")
        except Exception as e:
            logger.warning(f"Failed processing {sym}: {e}")

    if not new_dfs:
        raise RuntimeError("No collapsed data fetched!")

    collapsed_df = pd.concat(new_dfs, ignore_index=True)
    collapsed_path = DATA_DIR / "collapsed_bars_2000_2026.parquet"
    collapsed_df.to_parquet(collapsed_path, index=False)
    logger.info(f"Saved {len(collapsed_df):,} bars across {collapsed_df['symbol'].nunique()} collapsed stocks -> {collapsed_path}")

    # 2. Merge with existing 64-equity universe
    base_path = DATA_DIR / "market_bars_2000_2026_unified.parquet"
    if not base_path.exists():
        base_path = DATA_DIR / "market_bars_2000_2026.parquet"

    base_df = pd.read_parquet(base_path)
    logger.info(f"Base dataset: {len(base_df):,} bars across {base_df['symbol'].nunique()} symbols")

    # Combine & deduplicate
    unified_df = pd.concat([base_df, collapsed_df], ignore_index=True)
    unified_df = unified_df.drop_duplicates(subset=["symbol", "date"]).sort_values(["symbol", "date"]).reset_index(drop=True)

    out_unified = DATA_DIR / "market_bars_with_delisted_2000_2026.parquet"
    unified_df.to_parquet(out_unified, index=False)

    logger.info("=" * 80)
    logger.info(f"SUCCESS: Unified Survivorship-Tensioned Dataset Ready!")
    logger.info(f"Total Symbols: {unified_df['symbol'].nunique()} (64 Regular + {collapsed_df['symbol'].nunique()} Collapsed/Delisted)")
    logger.info(f"Total Daily Bars: {len(unified_df):,}")
    logger.info(f"Date Range: {unified_df['date'].min().date()} to {unified_df['date'].max().date()}")
    logger.info(f"File Saved: {out_unified}")
    logger.info("=" * 80)


if __name__ == "__main__":
    run_ingestion()
