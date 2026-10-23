"""Experiment: Dissect why profit dropped and find the exact optimal sweet spot."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pandas as pd
from blumberg_market_radar.backtest.upgraded_vcp_engine import UpgradedVCPBacktestEngine

data_dir = Path("data/cache/historical_2015_2026")
bars = pd.read_parquet(data_dir / "market_bars_2015_2026.parquet")
bankrupt_bars = pd.read_parquet(data_dir / "bankrupt_bars_2015_2026.parquet")
all_bars = pd.concat([bars, bankrupt_bars], ignore_index=True).sort_values(["symbol", "date"]).reset_index(drop=True)
bench = pd.read_parquet(data_dir / "nifty50_bench_2015_2026.parquet")

print("=" * 80)
print("PROFIT DROP ROOT-CAUSE EXPERIMENT")
print("=" * 80)

# Case 1: The Upgraded Engine as run (Heavy Slippage 50 bps, 1% ATR sizing, Climax exits)
e1 = UpgradedVCPBacktestEngine(
    initial_capital=1_000_000.0,
    max_slots=15,
    risk_per_trade_pct=0.01,
    min_turnover_rs=30_000_000.0,
    slippage_bps_per_side=50.0,
    statutory_bps_per_side=52.6,
)
s1 = e1.run_backtest(all_bars, bench)
print(f"Case 1 (Heavy Constraints + 50bps Slippage + Climax Exits): Ending Cap: Rs. {s1.final_capital:,.0f} | CAGR: +{s1.compounded_cagr_pct:.2f}% | Max DD: {s1.max_drawdown_pct:.2f}% | Total Friction: Rs. {s1.total_friction_paid:,.0f}")

# Case 2: Realistic Friction (15 bps slippage + 52.6 bps statutory = 67.6 bps per side)
e2 = UpgradedVCPBacktestEngine(
    initial_capital=1_000_000.0,
    max_slots=15,
    risk_per_trade_pct=0.01,
    min_turnover_rs=30_000_000.0,
    slippage_bps_per_side=15.0, # Realistic delivery slippage
    statutory_bps_per_side=52.6,
)
s2 = e2.run_backtest(all_bars, bench)
print(f"Case 2 (Realistic 15bps Slippage): Ending Cap: Rs. {s2.final_capital:,.0f} | CAGR: +{s2.compounded_cagr_pct:.2f}% | Max DD: {s2.max_drawdown_pct:.2f}% | Total Friction: Rs. {s2.total_friction_paid:,.0f}")

# Case 3: Removing the Climax Cut (Letting true multibaggers breathe without choking on 20 EMA)
# Let's inspect where trades like HAL and Titagarh got choked
print("\nCase 1 Top Trades:")
for _, r in s1.trades_df.sort_values("net_return_pct", ascending=False).head(5).iterrows():
    print(f"  {r['symbol']:10} Net: +{r['net_return_pct']:,.1f}% | Exit: {r['exit_reason']}")
