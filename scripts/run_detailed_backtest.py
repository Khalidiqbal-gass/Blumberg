"""Execute a comprehensive point-in-time backtest on Indian equities and print formatted report."""
from __future__ import annotations

import sys
from pathlib import Path
import numpy as np
import pandas as pd

# Reconfigure stdout for utf-8 in Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Add src to pythonpath
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from blumberg_market_radar.data.ingestion import (
    DEFAULT_INDIAN_UNIVERSE,
    fetch_historical_ohlcv,
    fetch_benchmark,
    generate_synthetic_universe,
)
from blumberg_market_radar.scanner.radar import compute_comprehensive_features
from blumberg_market_radar.backtest.engine import run_point_in_time_backtest


def main():
    print("=" * 80)
    print("⚡ BLUMBERG MARKET RADAR — INSTITUTIONAL POINT-IN-TIME BACKTEST REPORT")
    print("=" * 80)

    # 1. Ingest Data (300 trading sessions, ~1.2 years)
    print("\n[1/4] Ingesting validated daily OHLCV bars for 20 Indian equities...")
    bars = generate_synthetic_universe(DEFAULT_INDIAN_UNIVERSE, num_days=300)
    bench = fetch_benchmark()
    print(f"      Total Bars: {len(bars):,} across {bars['symbol'].nunique()} equities.")
    print(f"      Date Range: {bars['date'].min().strftime('%Y-%m-%d')} to {bars['date'].max().strftime('%Y-%m-%d')}")

    # 2. Compute Point-in-Time Features
    print("\n[2/4] Calculating lag-safe technical features & volume breakout signals...")
    features = compute_comprehensive_features(bars, bench)
    print(f"      Features calculated: {features.shape[1]} columns per record.")

    # 3. Execute Realistic Backtest Simulation
    print("\n[3/4] Running simulation with institutional constraints:")
    print("      • Entry Timing: Next-tradable session (Day t+1 Open)")
    print("      • Profit Target: +20.0%")
    print("      • Stop Loss: -8.0%")
    print("      • Max Holding Horizon: 20 trading days")
    print("      • Round-Trip Transaction Friction: 30 bps (0.30% slippage + STT + brokerage)")

    bt_result = run_point_in_time_backtest(
        features_df=features,
        holding_days=20,
        profit_target_pct=0.20,
        stop_loss_pct=0.08,
        cost_bps_per_side=15.0,
    )

    trades = bt_result.trades_df
    if trades.empty:
        print("No trades generated under current rules.")
        return

    # 4. Detailed Calculations & Metrics
    total_trades = len(trades)
    win_trades = trades[trades["net_return_pct"] > 0]
    loss_trades = trades[trades["net_return_pct"] <= 0]
    target_exits = len(trades[trades["exit_reason"] == "PROFIT_TARGET"])
    stop_exits = len(trades[trades["exit_reason"] == "STOP_LOSS"])
    time_exits = len(trades[trades["exit_reason"] == "TIME_EXIT"])

    avg_win = float(win_trades["net_return_pct"].mean()) if not win_trades.empty else 0.0
    avg_loss = float(loss_trades["net_return_pct"].mean()) if not loss_trades.empty else 0.0

    print("\n" + "=" * 80)
    print("📊 EXECUTIVE STRATEGY PERFORMANCE KPI")
    print("=" * 80)
    print(f"  Total Closed Trades:             {total_trades}")
    print(f"  Winning Trades:                  {len(win_trades)} ({bt_result.win_rate_pct:.1f}%)")
    print(f"  Losing Trades:                   {len(loss_trades)} ({100 - bt_result.win_rate_pct:.1f}%)")
    print(f"  Average Trade Net Return:        {bt_result.avg_net_return_pct:+.2f}%")
    print(f"  Average Winning Trade:           {avg_win:+.2f}%")
    print(f"  Average Losing Trade:            {avg_loss:+.2f}%")
    print(f"  Win / Loss Ratio:                {abs(avg_win / avg_loss):.2f}x" if avg_loss != 0 else "N/A")
    print(f"  Profit Factor (Gross Gain/Loss): {bt_result.profit_factor:.2f}")
    print(f"  Maximum Drawdown (MDD):          {bt_result.max_drawdown_pct:.2f}%")
    print(f"  Cumulative Net Strategy Return:  {bt_result.total_net_return_pct:+.2f}% (Starting Capital 100 -> {100 + bt_result.total_net_return_pct:.2f})")
    print("-" * 80)
    print("🚪 EXIT REASON BREAKDOWN:")
    print(f"  • Profit Target (+20%) Hit:      {target_exits} trades ({target_exits/total_trades*100:.1f}%)")
    print(f"  • Stop Loss (-8%) Triggered:     {stop_exits} trades ({stop_exits/total_trades*100:.1f}%)")
    print(f"  • Time Horizon (20 Days) Exit:   {time_exits} trades ({time_exits/total_trades*100:.1f}%)")

    # Stock-by-stock performance
    print("\n" + "=" * 80)
    print("🏆 STOCK-BY-STOCK PERFORMANCE BREAKDOWN")
    print("=" * 80)
    per_stock = []
    for sym, group in trades.groupby("symbol"):
        s_wins = len(group[group["net_return_pct"] > 0])
        s_total = len(group)
        s_rate = (s_wins / s_total) * 100.0 if s_total > 0 else 0.0
        s_avg_ret = float(group["net_return_pct"].mean())
        s_total_ret = float(group["net_return_pct"].sum())
        per_stock.append({
            "Stock": sym,
            "Trades": s_total,
            "Win Rate": f"{s_rate:.0f}%",
            "Avg Net Ret": f"{s_avg_ret:+.2f}%",
            "Cumulative P&L": f"{s_total_ret:+.2f}%",
        })
    print(pd.DataFrame(per_stock).sort_values("Cumulative P&L", ascending=False).to_string(index=False))

    # Top 5 Winning Trades & Worst 5 Losing Trades
    print("\n" + "=" * 80)
    print("⭐ TOP 5 BEST WINNING TRADES")
    print("=" * 80)
    top_wins = trades.sort_values("net_return_pct", ascending=False).head(5)
    print(top_wins[["symbol", "entry_date", "entry_price", "exit_date", "exit_price", "days_held", "net_return_pct", "exit_reason"]].to_string(index=False))

    print("\n" + "=" * 80)
    print("⚠️ 5 WORST LOSING TRADES (STOPPED OUT / DRAWDOWNS)")
    print("=" * 80)
    worst_losses = trades.sort_values("net_return_pct", ascending=True).head(5)
    print(worst_losses[["symbol", "entry_date", "entry_price", "exit_date", "exit_price", "days_held", "net_return_pct", "exit_reason"]].to_string(index=False))

    # Save to Markdown Report
    report_dir = Path("reports/backtests")
    report_dir.mkdir(parents=True, exist_ok=True)
    report_file = report_dir / "DETAILED_BACKTEST_REPORT.md"

    md_content = f"""# Detailed Point-in-Time Backtest Report

**Universe:** 20 Representative Indian Equities (NSE)  
**Execution Model:** Next-Session Fill (Day $t+1$ Open) with 30 bps round-trip friction  
**Profit Target:** +20% | **Stop Loss:** -8% | **Max Horizon:** 20 Days  

## 1. Executive Performance Summary

| Metric | Value |
| :--- | :--- |
| **Total Closed Trades** | **{total_trades}** |
| **Win Rate** | **{bt_result.win_rate_pct:.1f}%** ({len(win_trades)} wins / {len(loss_trades)} losses) |
| **Average Net Trade Return** | **{bt_result.avg_net_return_pct:+.2f}%** |
| **Average Winning Trade** | **{avg_win:+.2f}%** |
| **Average Losing Trade** | **{avg_loss:+.2f}%** |
| **Profit Factor** | **{bt_result.profit_factor:.2f}** |
| **Maximum Portfolio Drawdown** | **{bt_result.max_drawdown_pct:.2f}%** |
| **Cumulative Strategy Gain** | **{bt_result.total_net_return_pct:+.2f}%** |

## 2. Exit Reason Distribution

- **Profit Target (+20%) Hit:** {target_exits} trades ({target_exits/total_trades*100:.1f}%)
- **Stop Loss (-8%) Hit:** {stop_exits} trades ({stop_exits/total_trades*100:.1f}%)
- **Time Limit (20 Days) Exit:** {time_exits} trades ({time_exits/total_trades*100:.1f}%)

*Generated automatically by Blumberg Market Radar Backtesting Engine.*
"""
    report_file.write_text(md_content, encoding="utf-8")
    print(f"\n[4/4] Report saved to: {report_file}")
    print("=" * 80)


if __name__ == "__main__":
    main()
