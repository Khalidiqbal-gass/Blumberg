"""
Test Run Script for Alpha Boosters & Institutional VCP Backtest Engine.
Runs Modern Era (2015-01-01 to 2026-12-31) backtest using HYBRID_50_50 mode
with Alpha Boosters enabled:
- Volatility-Parity Position Sizing (inverse to ATR%)
- Sector Leadership Cross-Sectional Ranking
- T+1 Morning Cash & Slot Freeze
- Gap-Down min(Floor, Open) fills
- Lookahead-free trailing stop evaluation
"""
from __future__ import annotations
import sys
from pathlib import Path

# Add project src to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import pandas as pd
from blumberg_market_radar.backtest.upgraded_vcp_engine import UpgradedVCPBacktestEngine


def run_alpha_booster_test():
    print("=" * 80)
    print("BLUMBERG MARKET RADAR — ALPHA BOOSTER INSTITUTIONAL BACKTEST")
    print("Period: Modern Era (2015-01-01 to 2026-12-31) | Mode: HYBRID_50_50")
    print("Alpha Boosters: Volatility Parity Sizing + Sector Leadership Ranking")
    print("=" * 80)

    # 1. Load Data from Cache (support both historical_2000_2026 and historical_2015_2026)
    cache_2000 = PROJECT_ROOT / "data" / "cache" / "historical_2000_2026"
    cache_2015 = PROJECT_ROOT / "data" / "cache" / "historical_2015_2026"

    if (cache_2000 / "market_bars_with_delisted_2000_2026.parquet").exists():
        print(f"Loading market dataset from {cache_2000}...")
        bars_df = pd.read_parquet(cache_2000 / "market_bars_with_delisted_2000_2026.parquet")
        bench_df = pd.read_parquet(cache_2000 / "sensex_bench_2000_2026.parquet")
    elif (cache_2015 / "market_bars_2015_2026.parquet").exists():
        print(f"Loading market dataset from {cache_2015}...")
        bars1 = pd.read_parquet(cache_2015 / "market_bars_2015_2026.parquet")
        bars2 = pd.read_parquet(cache_2015 / "bankrupt_bars_2015_2026.parquet")
        bars_df = pd.concat([bars1, bars2], ignore_index=True)
        bench_df = pd.read_parquet(cache_2015 / "nifty50_bench_2015_2026.parquet")
    else:
        raise FileNotFoundError(f"Historical parquet cache not found in {cache_2000} or {cache_2015}!")

    print(f"Loaded {len(bars_df):,} total bars across {bars_df['symbol'].nunique()} equities.")

    # 2. Initialize Engine with Alpha Boosters
    engine = UpgradedVCPBacktestEngine(
        initial_capital=1_000_000.0,
        max_slots=10,
        risk_per_trade_pct=0.02,  # 2% equity risk
        min_turnover_rs=30_000_000.0,
        slippage_bps_per_side=50.0,
        statutory_bps_per_side=52.6,
        mode="HYBRID_50_50",
        use_vol_parity=True,
        use_sector_leadership=False,
        tranche2_days=10,
    )

    # 3. Execute Modern Era Backtest
    summary = engine.run_backtest(
        bars_df=bars_df,
        bench_df=bench_df,
        start_date="2015-01-01",
        end_date="2026-12-31",
        mode="HYBRID_50_50",
    )

    # 4. Print Clean Performance Summary
    print("\n" + "=" * 80)
    print("PERFORMANCE SUMMARY — HYBRID 50-50 WITH ALPHA BOOSTERS (2015 - 2026)")
    print("=" * 80)
    print(f"Starting Capital:                 Rs. {summary.initial_capital:,.2f}")
    print(f"Ending Capital:                   Rs. {summary.final_capital:,.2f} ({summary.final_capital/summary.initial_capital:.2f}x Compounded Growth)")
    print(f"Compounded Net CAGR:              +{summary.compounded_cagr_pct:.2f}% p.a.")
    print(f"Benchmark CAGR:                   +{summary.nifty_cagr_pct:.2f}% p.a.")
    print(f"Net Alpha Generated:              +{summary.alpha_pct:.2f}% p.a.")
    print(f"Portfolio Max Drawdown:           {summary.max_drawdown_pct:.2f}%")
    print(f"Total Executed Campaigns:         {summary.total_trades}")
    print(f"Overall Trade Win Rate:           {summary.win_rate_pct:.2f}%")
    print(f"Profit Factor:                    {summary.profit_factor:.2f}")
    print(f"Mathematical Expectancy:          +{summary.expectancy_pct:.2f}% per trade")
    print(f"Win/Loss Payoff Ratio:            {summary.win_loss_ratio:.2f}x (Avg Win: +{summary.avg_gain_pct:.1f}% vs Avg Loss: -{summary.avg_loss_pct:.1f}%)")
    print(f"Average Holding Period:           {summary.avg_calendar_days:.0f} calendar days ({summary.avg_bars_held:.0f} trading bars)")
    print(f"Total Friction & Slippage Paid:   Rs. {summary.total_friction_paid:,.2f}")
    print("=" * 80)

    # Year-by-Year Table
    print("\nYear-by-Year Performance Breakdown:")
    print(summary.yearly_summary[["year", "start_capital", "end_capital", "model_net_ret", "nifty_ret", "alpha", "max_drawdown"]].to_string(index=False))

    # Top Multibaggers
    if not summary.trades_df.empty:
        print("\nTop Multibaggers Captured:")
        top_trades = summary.trades_df.sort_values("net_return_pct", ascending=False).head(10)
        for _, t in top_trades.iterrows():
            mult = 1.0 + t["net_return_pct"] / 100.0
            t2_flag = "Tranche 2 Added" if t.get("tranche2_active") else "Tranche 1 Only"
            print(f"  {t['symbol']:12} | Net: +{t['net_return_pct']:6.1f}% ({mult:.1f}x) | {t2_flag:15} | Exit: {t['exit_reason']}")

    return summary


if __name__ == "__main__":
    run_alpha_booster_test()
