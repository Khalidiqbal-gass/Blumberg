"""
Daily Autonomous Model Execution Script (HYBRID_50_50 Champion Model).

Runs the complete daily execution cycle for the Live Paper Portfolio:
1. Mark-to-market active holdings and accrue daily 6.5% liquid cash yield.
2. Step 1 (Exits): Evaluate trailing stops, circuit breakers, and profit floors -> Execute SELLS.
3. Step 2 (Graduations): Check active trades at Day 7+ -> Add TRANCHE 2 if in profit.
4. Step 3 (Entries): Scan today's market for VCP breakouts -> Enter TRANCHE 1 in free slots.
5. Saves state persistently to data/live_portfolio_state.json.
"""
from __future__ import annotations

import sys
from pathlib import Path
import pandas as pd

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from blumberg_market_radar.data.ingestion import fetch_historical_ohlcv, fetch_benchmark
from blumberg_market_radar.scanner.radar import compute_pre_rally_features, score_pre_rally_candidates
from blumberg_market_radar.pipeline.live_portfolio import LivePortfolioManager

DATA_DIR = PROJECT_ROOT / "data"
STATE_FILE = DATA_DIR / "live_portfolio_state.json"
HISTORICAL_DIR = DATA_DIR / "cache" / "historical_2000_2026"
CACHE_MARKET = DATA_DIR / "cache" / "market_eod_all_equities.parquet"


def run_daily_autonomous_trader(enforce_regime: bool = True, initial_capital: float = 1_000_000.0) -> None:
    print("=" * 100)
    print("   BLUMBERG AUTONOMOUS MODEL TRADER — HYBRID_50_50 CHAMPION REBALANCE")
    print("=" * 100)

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
    recent_bars = bars_df[bars_df["date"] >= (max_dt - pd.Timedelta(days=365))].copy()
    recent_bench = bench_df[bench_df["date"] >= (max_dt - pd.Timedelta(days=365))].copy()

    print(f"Loaded {len(recent_bars):,} bars across {recent_bars['symbol'].nunique()} equities up to {max_dt.strftime('%Y-%m-%d')}.")

    # 2. Compute VCP Features & Score Candidates
    print("Scanning market for VCP compression & relative strength...")
    feats = compute_pre_rally_features(recent_bars, recent_bench)
    ranked = score_pre_rally_candidates(feats, None, min_turnover_cr=1.5)
    # Filter out penny stocks (>= Rs 50)
    ranked_clean = ranked[ranked["close"] >= 50.0].copy() if not ranked.empty else pd.DataFrame()
    print(f"Identified {len(ranked_clean)} clean candidate setups meeting turnover and price floors.\n")

    # 3. Initialize Live Portfolio Manager
    mgr = LivePortfolioManager(
        state_path=STATE_FILE,
        initial_capital=initial_capital,
        max_slots=10,
        tranche2_days=7,
        slippage_bps=20.0,
        statutory_bps=35.0,
    )

    # 4. Execute Autonomous Daily Rebalance
    cur_date_str = max_dt.strftime("%Y-%m-%d")
    res = mgr.execute_daily_rebalance(
        bars_df=recent_bars,
        bench_df=recent_bench,
        candidates_df=ranked_clean,
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

    # 5. Display Current Portfolio State
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
    args = parser.parse_args()

    run_daily_autonomous_trader(enforce_regime=not args.no_regime, initial_capital=args.capital)
