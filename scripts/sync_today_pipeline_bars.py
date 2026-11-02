"""Sync latest market bars up to today (2026-10-23) and advance the Staged Pipeline Tracker."""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from blumberg_market_radar.pipeline.staged_tracker import (
    load_staged_pipeline,
    save_staged_pipeline,
    update_pipeline_with_bars,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s]: %(message)s")
logger = logging.getLogger("sync_today")

CACHE_PARQUET = Path("data/cache/market_eod_all_equities.parquet")


def sync_today():
    print("=" * 80)
    print("SYNCING LATEST MARKET BARS & ADVANCING STAGED PIPELINE")
    print("=" * 80)

    # 1. Load existing parquet cache
    existing_bars = pd.read_parquet(CACHE_PARQUET)
    print(f"Existing cache: {len(existing_bars):,} bars, max date: {existing_bars['date'].max()}")

    # 2. Get unique symbols
    symbols = sorted(existing_bars["symbol"].unique().tolist())
    print(f"Fetching recent 5-day bars for {len(symbols)} symbols from Yahoo Finance...")

    # Download recent 5 days
    raw = yf.download(symbols, period="5d", progress=False)
    
    new_rows = []
    if not raw.empty and "Close" in raw:
        for sym in symbols:
            try:
                if sym in raw["Close"]:
                    sym_c = raw["Close"][sym].dropna()
                    sym_o = raw["Open"][sym].dropna() if "Open" in raw and sym in raw["Open"] else pd.Series(dtype=float)
                    sym_h = raw["High"][sym].dropna() if "High" in raw and sym in raw["High"] else pd.Series(dtype=float)
                    sym_l = raw["Low"][sym].dropna() if "Low" in raw and sym in raw["Low"] else pd.Series(dtype=float)
                    sym_v = raw["Volume"][sym].dropna() if "Volume" in raw and sym in raw["Volume"] else pd.Series(dtype=float)

                    for dt in sym_c.index:
                        # Only accept genuine bars with valid OHLCV; never fabricate missing values
                        if (
                            dt in sym_o.index and pd.notna(sym_o.loc[dt])
                            and dt in sym_h.index and pd.notna(sym_h.loc[dt])
                            and dt in sym_l.index and pd.notna(sym_l.loc[dt])
                            and dt in sym_v.index and pd.notna(sym_v.loc[dt])
                        ):
                            o_v = float(sym_o.loc[dt])
                            h_v = float(sym_h.loc[dt])
                            l_v = float(sym_l.loc[dt])
                            c_v = float(sym_c.loc[dt])
                            v_v = float(sym_v.loc[dt])
                            if o_v > 0 and h_v >= max(o_v, l_v, c_v) and l_v <= min(o_v, h_v, c_v) and c_v > 0 and v_v >= 0:
                                dt_utc = pd.to_datetime(dt, utc=True)
                                new_rows.append({
                                    "date": dt_utc,
                                    "open": o_v,
                                    "high": h_v,
                                    "low": l_v,
                                    "close": c_v,
                                    "volume": v_v,
                                    "symbol": sym,
                                })
            except Exception as e:
                logger.warning(f"Error parsing {sym}: {e}")

    if new_rows:
        new_df = pd.DataFrame(new_rows)
        combined = pd.concat([existing_bars, new_df], ignore_index=True)
        # Normalize date to day boundary for exact deduplication
        combined["date_norm"] = combined["date"].dt.strftime("%Y-%m-%d")
        combined = combined.drop_duplicates(subset=["symbol", "date_norm"]).drop(columns=["date_norm"])
        combined = combined.sort_values(["symbol", "date"]).reset_index(drop=True)
        combined.to_parquet(CACHE_PARQUET, index=False)
        print(f"Updated cache: {len(combined):,} bars, new max date: {combined['date'].max()}")
        bars_for_pipeline = combined
    else:
        bars_for_pipeline = existing_bars

    # 3. Advance Staged Pipeline with updated bars
    print("\nAdvancing Staged Pipeline with new bars...")
    updated_pipe_df = update_pipeline_with_bars(bars_for_pipeline)
    
    print("\n=== UPDATED STAGED PIPELINE STATUS ===")
    display_cols = ["symbol", "days_in_pipeline", "date_added", "entry_price", "current_price", "current_gain_pct", "peak_mfe_pct", "status"]
    print(updated_pipe_df[display_cols].to_string(index=False))

    return updated_pipe_df


if __name__ == "__main__":
    sync_today()
