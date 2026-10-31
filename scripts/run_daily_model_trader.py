"""
Daily Autonomous Model Execution Script (HYBRID_50_50 Champion Model).

Runs the complete daily execution cycle for the Live Paper Portfolio:
1. Mark-to-market active holdings and accrue daily 6.5% liquid cash yield.
2. Step 1 (Exits): Evaluate trailing stops, circuit breakers, and profit floors -> Execute SELLS.
3. Step 2 (Graduations): Check active trades at Day 7+ -> Add TRANCHE 2 if in profit.
4. Step 3 (Entries): Scan today's market for VCP breakouts -> Enter TRANCHE 1 in free slots.
5. Saves state persistently to data/live_portfolio_state.json.

BACKTEST-LIVE PARITY:
- signal_source="ENGINE_VCP" (Default): Uses exact UpgradedVCPBacktestEngine.compute_indicators
  raw_signal condition and rs_score ranking (63-day RS vs Sensex * RVOL) for 100% parity with backtest.
- signal_source="RADAR_COMPOSITE": Uses 4-factor Pre-Rally Radar composite scoring.
"""
from __future__ import annotations

import sys
from pathlib import Path
import pandas as pd
import numpy as np

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from blumberg_market_radar.data.ingestion import fetch_historical_ohlcv, fetch_benchmark
from blumberg_market_radar.backtest.upgraded_vcp_engine import UpgradedVCPBacktestEngine
from blumberg_market_radar.scanner.radar import (
    compute_pre_rally_features,
    score_pre_rally_candidates,
    apply_sector_cluster_guardrail,
)
from blumberg_market_radar.pipeline.live_portfolio import LivePortfolioManager
from blumberg_market_radar.data.validation import validate_ohlcv

DATA_DIR = PROJECT_ROOT / "data"
STATE_FILE = DATA_DIR / "live_portfolio_state.json"
HISTORICAL_DIR = DATA_DIR / "cache" / "historical_2000_2026"
CACHE_MARKET = DATA_DIR / "cache" / "market_eod_all_equities.parquet"


def scan_engine_vcp_candidates(bars_df: pd.DataFrame, bench_df: pd.DataFrame) -> pd.DataFrame:
    """Scan candidate breakout setups using the EXACT quantitative logic of UpgradedVCPBacktestEngine.
    
    Parity details:
    - Same VCP compression check (atr_10 < atr_30)
    - Same 52W high proximity (close >= 0.85 * 52W_high)
    - Same base consolidation (0 < ret_20d <= 0.35)
    - Same volume ignition (ret_5d > 0 and rvol >= 1.4)
    - Same dynamic turnover floor (turnover >= dyn_floor)
    - Same cross-sectional ranking: rs_score = max(0.01, rs_63d) * rvol
    """
    bench_sorted = bench_df.sort_values("date").copy()
    bench_series = bench_sorted.set_index("date")["close"]
    candidates = []

    for sym, grp in bars_df.groupby("symbol"):
        clean_sym = str(sym).replace(".NS", "").replace(".BO", "").strip()
        ind_df = UpgradedVCPBacktestEngine.compute_indicators(grp, bench_series)
        if ind_df.empty:
            continue
        last_row = ind_df.iloc[-1]
        if bool(last_row.get("raw_signal", False)):
            close_p = float(last_row["close"])
            if close_p < 50.0:
                continue  # penny stock filter
            rs_score = float(last_row["rs_score"]) if pd.notna(last_row.get("rs_score")) else 0.01
            rvol = float(last_row["rvol"]) if pd.notna(last_row.get("rvol")) else 1.0
            atr_14 = float(last_row["atr_14"]) if pd.notna(last_row.get("atr_14")) else 0.0
            sector = str(last_row.get("sector", "Diversified"))
            candidates.append({
                "symbol": clean_sym,
                "close": close_p,
                "rs_score": rs_score,
                "rvol": rvol,
                "atr_14": atr_14,
                "sector": sector,
                "selection_reason": f"VCP Breakout (ATR10<30) | RS Score {rs_score:.2f} | RVOL {rvol:.1f}x",
            })

    if not candidates:
        return pd.DataFrame()
    cand_df = pd.DataFrame(candidates)
    # Cross-Sectional Ranking: Rank by score descending (exact same as upgraded_vcp_engine.py line 461)
    return cand_df.sort_values("rs_score", ascending=False).reset_index(drop=True)


def run_daily_autonomous_trader(
    enforce_regime: bool = True,
    initial_capital: float = 1_000_000.0,
    sync_live: bool = False,
    signal_source: str = "ENGINE_VCP",  # "ENGINE_VCP" (100% backtest parity) or "RADAR_COMPOSITE"
    reset_state: bool = False,
) -> None:
    print("=" * 100)
    print("   BLUMBERG AUTONOMOUS MODEL TRADER — HYBRID_50_50 CHAMPION REBALANCE")
    print(f"   Mode: Signal Source = {signal_source} | Friction = 102.6 bps | Next-Open Execution")
    print("=" * 100)

    # 0. Sync fresh live EOD data if requested
    if sync_live:
        print("[INFO] Fetching fresh live market bars before daily rebalance...")
        try:
            from scripts.sync_today_pipeline_bars import sync_today
            sync_today()
        except Exception as exc:
            print(f"[WARNING] Live sync encountered: {exc}. Proceeding with latest cached data.")

    # 1. Load Market Data
    if (HISTORICAL_DIR / "market_bars_with_delisted_2000_2026.parquet").exists():
        bars_path = HISTORICAL_DIR / "market_bars_with_delisted_2000_2026.parquet"
        bench_path = HISTORICAL_DIR / "sensex_bench_2000_2026.parquet"
        bars_df = pd.read_parquet(bars_path)
        bench_df = pd.read_parquet(bench_path)
    elif CACHE_MARKET.exists():
        bars_df = pd.read_parquet(CACHE_MARKET)
        bench_df = fetch_benchmark(period="1y")
    else:
        print("[ERROR] No market data parquet cache found.")
        return

    # Use recent bars for feature scanning
    max_dt = bars_df["date"].max()
    recent_bars = bars_df[bars_df["date"] >= (max_dt - pd.Timedelta(days=730))].copy()
    recent_bars = validate_ohlcv(recent_bars, clean_glitches=True)
    recent_bench = bench_df[bench_df["date"] >= (max_dt - pd.Timedelta(days=730))].copy()

    print(f"Loaded {len(recent_bars):,} bars across {recent_bars['symbol'].nunique()} equities up to {max_dt.strftime('%Y-%m-%d')}.")

    # 2. Compute Candidate Setups based on selected signal_source
    if signal_source.upper() == "ENGINE_VCP":
        print("Scanning candidates via UpgradedVCPBacktestEngine (100% Backtest Parity Mode)...")
        ranked_clean = scan_engine_vcp_candidates(recent_bars, recent_bench)
    else:
        print("Scanning candidates via Pre-Rally Radar 4-factor composite score...")
        feats = compute_pre_rally_features(recent_bars, recent_bench)
        ranked = score_pre_rally_candidates(feats, None, min_turnover_cr=1.5)
        ranked_clean = ranked[ranked["close"] >= 50.0].copy() if not ranked.empty else pd.DataFrame()

    print(f"Identified {len(ranked_clean)} candidate setups meeting breakout and liquidity criteria.\n")

    # 3. Initialize Live Portfolio Manager
    mgr = LivePortfolioManager(
        state_path=STATE_FILE,
        initial_capital=initial_capital,
        max_slots=8,
        tranche2_days=7,
        slippage_bps=50.0,
        statutory_bps=52.6,
        max_pct_of_adv=10.0,
    )

    if reset_state:
        print(f"[RESET] Resetting live portfolio state with Rs. {initial_capital:,.2f} clean cash...")
        mgr.reset_portfolio(capital=initial_capital)

    # 4. Apply Sector Concentration Guardrail (Max 2 stocks per sector in 8-slot model = 25% sector cap)
    active_df = pd.DataFrame(list(mgr.state.active_positions.values()))
    approved_candidates, sector_counts, free_slots = apply_sector_cluster_guardrail(
        ranked_clean,
        active_pipeline_df=active_df,
        max_stocks_per_sector=2,
        max_portfolio_slots=8,
    )
    print(f"Sector guardrail applied: {len(approved_candidates)} candidates approved (Active sector exposures: {sector_counts}).")

    # 5. Execute Autonomous Daily Rebalance
    cur_date_str = max_dt.strftime("%Y-%m-%d")
    res = mgr.execute_daily_rebalance(
        bars_df=recent_bars,
        bench_df=recent_bench,
        candidates_df=approved_candidates,
        current_date_str=cur_date_str,
        enforce_regime=enforce_regime,
    )

    print("=" * 100)
    print("DAILY EXECUTION ORDERS & ACTIONS:")
    print("=" * 100)
    if res["actions_taken"]:
        for act in res["actions_taken"]:
            print(" ", act)
    else:
        print("  [INFO] No rebalance actions required today. Active holdings & cash are in optimal balance.")

    # 6. Display Current Portfolio State
    summary = mgr.get_summary()
    print("\n" + "=" * 100)
    print("LIVE PORTFOLIO STATUS (Updated):")
    print("=" * 100)
    print(f"Total Portfolio Value:     Rs {summary['total_equity']:>15,.2f}  ({summary['total_return_pct']:>+6.2f}%)")
    print(f"Cash in Hand (Settled):    Rs {summary['cash']:>15,.2f}")
    print(f"Invested Holdings Value:   Rs {summary['market_value_holdings']:>15,.2f}  (Unrealized: Rs {summary['unrealized_pnl_rs']:>+,.2f})")
    print(f"Realized PnL to Date:      Rs {summary['realized_pnl_rs']:>15,.2f}  (Win Rate: {summary['win_rate_pct']:.1f}%)")
    print(f"Active Slots Utilized:     {summary['active_positions_count']:>2} / {summary['max_slots']} Slots  ({summary['available_slots']} available)")
    print("=" * 100)

    if mgr.state.active_positions:
        print("\n--- ACTIVE HOLDINGS BREAKDOWN ---")
        pos_rows = []
        for sym, p in mgr.state.active_positions.items():
            pos_rows.append({
                "Symbol": sym,
                "Stage": p["current_stage"],
                "Shares": round(p["shares"], 1),
                "Avg Entry": round(p["entry_price"], 2),
                "Current LTP": round(p["current_price"], 2),
                "Invested Rs": round(p["invested_capital"], 2),
                "PnL %": round(p["current_gain_pct"], 2),
                "Tranche 2?": "ACTIVE" if p["tranche2_active"] else "WAITING (D7)",
                "Stop Loss": round(p["stop_loss_price"], 2),
                "Floor": round(p["profit_floor_price"], 2),
            })
        print(pd.DataFrame(pos_rows).to_string(index=False))

    print(f"\n[SUCCESS] State safely saved to {STATE_FILE}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--capital", type=float, default=1_000_000.0, help="Initial capital in Rupees")
    parser.add_argument("--no-regime", action="store_true", help="Bypass benchmark regime filter")
    parser.add_argument("--sync-live", action="store_true", help="Fetch fresh live market bars before rebalance")
    parser.add_argument("--signal-source", choices=["ENGINE_VCP", "RADAR_COMPOSITE"], default="ENGINE_VCP",
                        help="ENGINE_VCP (100 percent Backtest Parity) or RADAR_COMPOSITE (Legacy 4-factor)")
    parser.add_argument("--reset-state", action="store_true", help="Reset live portfolio to clean cash before run")
    args = parser.parse_args()

    run_daily_autonomous_trader(
        enforce_regime=not args.no_regime,
        initial_capital=args.capital,
        sync_live=args.sync_live,
        signal_source=args.signal_source,
        reset_state=args.reset_state,
    )
