"""Run full 2015-2026 audit using the Upgraded VCP & Multi-Stage Secular Engine."""
from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pandas as pd
from blumberg_market_radar.backtest.upgraded_vcp_engine import UpgradedVCPBacktestEngine

def run_audit():
    print("=" * 80)
    print("RUNNING 2015-2026 UPGRADED VCP & MULTI-STAGE SECULAR AUDIT")
    print("=" * 80)

    data_dir = Path("data/cache/historical_2015_2026")
    bars = pd.read_parquet(data_dir / "market_bars_2015_2026.parquet")
    bankrupt_bars = pd.read_parquet(data_dir / "bankrupt_bars_2015_2026.parquet")
    all_bars = pd.concat([bars, bankrupt_bars], ignore_index=True).sort_values(["symbol", "date"]).reset_index(drop=True)

    bench = pd.read_parquet(data_dir / "nifty50_bench_2015_2026.parquet")

    engine = UpgradedVCPBacktestEngine(
        initial_capital=1_000_000.0,
        max_slots=15,
        risk_per_trade_pct=0.01, # 1% risk
        min_turnover_rs=30_000_000.0, # Rs 3 Crores
        slippage_bps_per_side=50.0, # 0.5% slippage
        statutory_bps_per_side=52.6, # Delivery statutory costs
    )

    summary = engine.run_backtest(all_bars, bench)

    print("\n" + "=" * 80)
    print("UPGRADED ENGINE EMPIRICAL PERFORMANCE (2015-2026)")
    print("=" * 80)
    print(f"Starting Capital: Rs. {summary.initial_capital:,.2f}")
    print(f"Ending Capital: Rs. {summary.final_capital:,.2f} ({summary.final_capital/summary.initial_capital:.2f}x Compounded Growth)")
    print(f"Compounded Net CAGR: +{summary.compounded_cagr_pct:.2f}% p.a.")
    print(f"NIFTY 50 CAGR: +{summary.nifty_cagr_pct:.2f}% p.a.")
    print(f"Net Institutional Alpha: +{summary.alpha_pct:.2f}% p.a.")
    print(f"Portfolio Max Drawdown: {summary.max_drawdown_pct:.2f}%")
    print(f"Total Executed Trades: {summary.total_trades}")
    print(f"Win Rate: {summary.win_rate_pct:.2f}%")
    print(f"Profit Factor: {summary.profit_factor:.2f}")
    print(f"Mathematical Expectancy: +{summary.expectancy_pct:.2f}% per trade")
    print(f"Win/Loss Payoff Ratio: {summary.win_loss_ratio:.2f}x (Avg Gain +{summary.avg_gain_pct:.1f}% vs Avg Loss -{summary.avg_loss_pct:.1f}%)")
    print(f"Average Holding: {summary.avg_calendar_days:.0f} calendar days ({summary.avg_bars_held:.0f} trading bars)")
    print(f"Total Friction & Slippage Paid: Rs. {summary.total_friction_paid:,.2f}")

    print("\n--- Year-by-Year Performance ---")
    print(summary.yearly_summary.to_string(index=False))

    print("\n--- Top 10 Multibaggers Captured ---")
    top10 = summary.trades_df.sort_values("net_return_pct", ascending=False).head(10)
    for _, r in top10.iterrows():
        mult = 1.0 + r["net_return_pct"] / 100.0
        print(f"{r['symbol']:12} | {r['entry_date'].strftime('%Y-%m-%d')} -> {r['exit_date'].strftime('%Y-%m-%d')} | {r['calendar_days']:4d}d ({r['bars_held']:4d}b) | Net: +{r['net_return_pct']:,.1f}% ({mult:.1f}x) | Exit: {r['exit_reason']}")

    print("\n--- Exit Reason Distribution ---")
    print(summary.trades_df["exit_reason"].value_counts().to_string())

if __name__ == "__main__":
    run_audit()
