"""End-of-Day (EOD) Market Data Synchronizer & Parquet Cache Builder.

Downloads daily candles for NSE/BSE listed equities and newly listed IPOs
via Angel One SmartAPI after market close (4:00 PM IST).
Consolidates all candles into high-speed Parquet cache for instantaneous UI scanning.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence
import pandas as pd
from dotenv import load_dotenv

# Ensure blumberg_market_radar is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from blumberg_market_radar.connectors.angel_one import get_angel_connector
from blumberg_market_radar.data.ingestion import (
    DEFAULT_INDIAN_UNIVERSE,
    NIFTY_MOMENTUM_UNIVERSE_50,
    NIFTY_500_HIGH_BETA_100,
)
from blumberg_market_radar.data.security_master import (
    sync_nse_security_master,
    get_all_nse_symbols,
    get_recent_ipo_symbols,
)
from blumberg_market_radar.corporate_intel.nse_scraper import sync_nse_corporate_announcements
from blumberg_market_radar.pipeline.nightly import run_nightly_eod_pipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("sync_eod_market")


def consolidate_parquet_cache(
    cache_dir: Path | str = "data/cache/angel_one",
    output_parquet: Path | str = "data/cache/market_eod_all_equities.parquet",
) -> pd.DataFrame:
    """Merge individual symbol parquets into a single ultra-fast consolidated Parquet file."""
    c_path = Path(cache_dir)
    out_path = Path(output_parquet)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if not c_path.exists():
        logger.warning(f"Cache dir {c_path} does not exist.")
        return pd.DataFrame()

    files = list(c_path.glob("*.parquet"))
    if not files:
        logger.warning(f"No parquet files found in {c_path}.")
        return pd.DataFrame()

    frames = []
    for f in files:
        sym = f.stem
        if sym in ("NIFTY50", "NIFTY", "^NSEI"):
            continue
        try:
            df = pd.read_parquet(f)
            if not df.empty and "date" in df.columns:
                df["symbol"] = f"{sym}.NS" if not sym.endswith(".NS") else sym
                frames.append(df)
        except Exception as e:
            logger.debug(f"Error reading {f}: {e}")

    if not frames:
        return pd.DataFrame()

    combined = pd.concat(frames, ignore_index=True)
    combined = combined.drop_duplicates(subset=["symbol", "date"]).sort_values(["symbol", "date"]).reset_index(drop=True)
    combined.to_parquet(out_path, index=False)
    logger.info(f"Consolidated {len(combined):,} bars across {combined['symbol'].nunique()} equities -> {out_path} ({out_path.stat().st_size / 1024:.1f} KB)")
    return combined


def sync_eod_market(
    max_symbols: int | None = None,
    include_all_nse: bool = False,
    days: int = 300,
    rate_limit_delay: float = 0.70,
    run_pipeline: bool = True,
) -> None:
    """Main synchronization routine executed at 4:00 PM IST."""
    load_dotenv()
    logger.info("=" * 70)
    logger.info("⚡ BLUMBERG MARKET RADAR — END-OF-DAY BATCH DATA SYNC")
    logger.info("=" * 70)

    # 1. Sync Official NSE Security Master (detects newly listed IPOs & active equities)
    logger.info("Step 1: Syncing official NSE Security Master...")
    sec_master = sync_nse_security_master()
    total_nse = len(sec_master)
    recent_ipos = get_recent_ipo_symbols(max_age_days=365)
    fresh_ipos = get_recent_ipo_symbols(max_age_days=90)
    logger.info(f"NSE Master active: {total_nse} equities | Recent IPOs (<1Y): {len(recent_ipos)} | Fresh IPOs (<90D): {len(fresh_ipos)}")

    # 1b. Sync Official NSE Corporate Announcements (order wins & capex)
    logger.info("Step 1b: Scanning official NSE Corporate Announcements for material order wins...")
    try:
        new_orders = sync_nse_corporate_announcements(max_entries=60)
        logger.info(f"Extracted {len(new_orders)} new corporate orders/filings into ledger.")
    except Exception as ann_err:
        logger.debug(f"Corporate announcement auto-scan note: {ann_err}")

    # 2. Determine universe priority
    if include_all_nse:
        # Full market: all 2,600+ equities
        all_syms = get_all_nse_symbols()
        # Prioritize Curated 50 + Nifty 500 + Fresh IPOs first, then remaining
        priority_set = set(NIFTY_MOMENTUM_UNIVERSE_50 + recent_ipos + DEFAULT_INDIAN_UNIVERSE)
        high_prio = [s for s in all_syms if s in priority_set]
        low_prio = [s for s in all_syms if s not in priority_set]
        target_symbols = high_prio + low_prio
    else:
        # Default smart priority: Curated Momentum + High Beta + Fresh IPOs
        seen = set()
        target_symbols = []
        for s in (NIFTY_MOMENTUM_UNIVERSE_50 + recent_ipos + NIFTY_500_HIGH_BETA_100):
            if s not in seen:
                seen.add(s)
                target_symbols.append(s)

    if max_symbols and max_symbols > 0:
        target_symbols = target_symbols[:max_symbols]

    logger.info(f"Step 2: Syncing Angel One candles for {len(target_symbols)} equities (Days: {days})...")
    conn = get_angel_connector()
    if not conn.connect():
        logger.error("Could not connect to Angel One SmartAPI. Please check credentials in .env.")
        return

    # Sync NIFTY 50 benchmark first
    logger.info("Syncing official NIFTY 50 index benchmark...")
    conn.fetch_nifty_benchmark(days=days)

    # Batch sync target symbols with progress display
    total_targets = len(target_symbols)
    synced_count = 0
    cached_count = 0

    for idx, sym in enumerate(target_symbols, 1):
        clean = sym.replace(".NS", "").replace(".BO", "").strip().upper()
        # Check if already cached today
        cached = conn.get_cached_candles(clean, max_age_hours=12.0)
        if cached is not None and not cached.empty:
            cached_count += 1
            if idx % 25 == 0 or idx == total_targets:
                logger.info(f"[{idx}/{total_targets}] Progress: {synced_count} fetched, {cached_count} from cache")
            continue

        token = conn.get_token_for_symbol(clean)
        if not token:
            continue

        try:
            sub = conn.fetch_historical_candles(
                symbol_token=token,
                exchange="NSE",
                interval="ONE_DAY",
                days=days,
            )
            if not sub.empty:
                sub["symbol"] = f"{clean}.NS"
                conn.save_cached_candles(clean, sub)
                synced_count += 1

            time.sleep(rate_limit_delay)
        except Exception as err:
            logger.debug(f"Failed to fetch {clean}: {err}")

        if idx % 25 == 0 or idx == total_targets:
            logger.info(f"[{idx}/{total_targets}] Progress: {synced_count} fetched, {cached_count} from cache")

    logger.info(f"Angel One sync complete: {synced_count} freshly downloaded, {cached_count} loaded from local cache.")

    # 3. Consolidate into single Parquet file for instant UI scans
    logger.info("Step 3: Consolidating Parquet cache for ultra-fast UI scans...")
    consolidated = consolidate_parquet_cache()

    # 4. Advance 4-Layer Staged Pre-Rally Incubation Pipeline (10D/20D/30D/60D)
    if not consolidated.empty:
        try:
            from blumberg_market_radar.pipeline.staged_tracker import update_pipeline_with_bars
            logger.info("Step 4: Advancing 4-Layer Staged Pipeline with today's EOD bars...")
            updated_pipe = update_pipeline_with_bars(consolidated)
            logger.info(f"✅ Advanced {len(updated_pipe)} incubating stocks across 4 layers (10D/20D/30D/60D).")
        except Exception as p_err:
            logger.warning(f"Could not update staged pipeline: {p_err}")

    # 5. Optional: Run EOD Nightly Pipeline to generate Daily Digest report
    if run_pipeline and not consolidated.empty:
        logger.info("Step 5: Running automated EOD Pre-Rally Radar & Intelligence Digest...")
        digest_summary = run_nightly_eod_pipeline(
            mode="offline",
            symbols=list(consolidated["symbol"].unique()),
            min_score=50.0,
            min_turnover_cr=1.0,
        )
        report_path = digest_summary.get("report_path", "reports/daily_digests/")
        logger.info(f"✅ EOD Daily Digest generated successfully: {report_path}")

    logger.info("=" * 70)
    logger.info("🎉 EOD BATCH SYNC COMPLETED SUCCESSFULLY!")
    logger.info("=" * 70)


def main():
    parser = argparse.ArgumentParser(description="Blumberg Market Radar EOD Batch Data Sync")
    parser.add_argument("--all", action="store_true", help="Sync all 2,600+ NSE listed equities")
    parser.add_argument("--max", type=int, default=None, help="Maximum number of symbols to sync")
    parser.add_argument("--days", type=int, default=300, help="Number of historical candle days (default 300)")
    parser.add_argument("--delay", type=float, default=0.70, help="Delay between Angel One API calls (default 0.70s)")
    parser.add_argument("--no-pipeline", action="store_true", help="Skip running daily digest pipeline after sync")
    args = parser.parse_args()

    sync_eod_market(
        max_symbols=args.max,
        include_all_nse=args.all,
        days=args.days,
        rate_limit_delay=args.delay,
        run_pipeline=not args.no_pipeline,
    )


if __name__ == "__main__":
    main()
