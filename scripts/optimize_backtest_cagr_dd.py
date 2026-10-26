"""
Empirical Grid Optimization: Find the parameter combination that achieves:
CAGR: 21% - 25%+
Drawdown: Low (<20% - 25%)
Across:
1. 2015-2026 (Modern Clean Data with Nifty 50)
2. 2000-2026 (Full 26-Year Historical Data with Regime Filter)
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pandas as pd
import numpy as np
from blumberg_market_radar.backtest.upgraded_vcp_engine import UpgradedVCPBacktestEngine

def run_grid_2015_2026():
    data_dir = Path("data/cache/historical_2015_2026")
    bars = pd.read_parquet(data_dir / "market_bars_2015_2026.parquet")
    bankrupt_bars = pd.read_parquet(data_dir / "bankrupt_bars_2015_2026.parquet")
    all_bars = pd.concat([bars, bankrupt_bars], ignore_index=True).sort_values(["symbol", "date"]).reset_index(drop=True)
    bench = pd.read_parquet(data_dir / "nifty50_bench_2015_2026.parquet")

    results = []

    # Configurations to test:
    configs = [
        {"name": "Ultra-Conservative (Current)", "slots": 15, "risk": 0.01, "max_alloc": 1/15},
        {"name": "Moderate Institutional (1.5% Risk, 12 Slots)", "slots": 12, "risk": 0.015, "max_alloc": 1/12},
        {"name": "Growth Institutional (2.0% Risk, 10 Slots)", "slots": 10, "risk": 0.020, "max_alloc": 1/10},
        {"name": "Optimal Pyramiding (2.5% Risk, 8-10 Slots)", "slots": 10, "risk": 0.025, "max_alloc": 1/10},
        {"name": "Concentrated Alpha (8 Slots, 2.5% Risk)", "slots": 8, "risk": 0.025, "max_alloc": 1/8},
        {"name": "Fixed 10% Sizing (10 Slots)", "slots": 10, "risk": 0.05, "max_alloc": 0.10},
    ]

    for cfg in configs:
        engine = UpgradedVCPBacktestEngine(
            initial_capital=1_000_000.0,
            max_slots=cfg["slots"],
            risk_per_trade_pct=cfg["risk"],
            min_turnover_rs=30_000_000.0,
            slippage_bps_per_side=50.0,
            statutory_bps_per_side=52.6,
        )
        summary = engine.run_backtest(all_bars, bench)
        results.append({
            "Configuration": cfg["name"],
            "Slots": cfg["slots"],
            "Risk/Trade": f"{cfg['risk']*100:.1f}%",
            "CAGR %": summary.compounded_cagr_pct,
            "Max Drawdown %": summary.max_drawdown_pct,
            "Calmar Ratio": abs(summary.compounded_cagr_pct / summary.max_drawdown_pct) if summary.max_drawdown_pct != 0 else 0,
            "Final Capital (Lakhs)": summary.final_capital / 100_000.0,
            "Trades": summary.total_trades,
            "Win Rate %": summary.win_rate_pct,
            "Profit Factor": summary.profit_factor,
            "Expectancy %": summary.expectancy_pct,
        })

    res_df = pd.DataFrame(results)
    print("\n" + "=" * 90)
    print("2015-2026 MODERN CLEAN ERA GRID OPTIMIZATION (11.8 YEARS)")
    print("=" * 90)
    print(res_df.to_string(index=False))
    return res_df

if __name__ == "__main__":
    run_grid_2015_2026()
