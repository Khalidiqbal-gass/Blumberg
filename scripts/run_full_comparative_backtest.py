"""
Run Full Comparative Backtest across all 3 modes using UpgradedVCPBacktestEngine:
1. HYBRID_50_50
2. LAYER_2_CONFIRMATION
3. LAYER_1_FULL
Across:
- Modern Clean Era (2015-2026, Nifty 50 Benchmark)
- Full 26.8-Year Survivorship-Tensioned Era (2000-2026, Sensex Benchmark, 27 Bankrupt Stocks Included)
"""
from __future__ import annotations
import sys
from pathlib import Path

# Force UTF-8 stdout if available
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import pandas as pd
from blumberg_market_radar.backtest.upgraded_vcp_engine import UpgradedVCPBacktestEngine


def run_comparative_backtests():
    print("=" * 95)
    print("               BLUMBERG MARKET RADAR - MULTI-ERA COMPREHENSIVE BACKTEST")
    print("=" * 95)

    cache_2015 = PROJECT_ROOT / "data" / "cache" / "historical_2015_2026"
    cache_2000 = PROJECT_ROOT / "data" / "cache" / "historical_2000_2026"

    # =========================================================================
    # PART 1: MODERN CLEAN ERA (2015 - 2026, 11.8 YEARS, NIFTY 50 BENCHMARK)
    # =========================================================================
    print("\n" + "-" * 95)
    print("1. MODERN CLEAN ERA (2015-01-01 to 2026-10-21, 11.8 YEARS, NIFTY 50 BENCHMARK)")
    print("-" * 95)

    if (cache_2015 / "market_bars_2015_2026.parquet").exists():
        bars1 = pd.read_parquet(cache_2015 / "market_bars_2015_2026.parquet")
        bars2 = pd.read_parquet(cache_2015 / "bankrupt_bars_2015_2026.parquet")
        bars_2015 = pd.concat([bars1, bars2], ignore_index=True)
        bench_2015 = pd.read_parquet(cache_2015 / "nifty50_bench_2015_2026.parquet")
    else:
        bars_2015 = pd.read_parquet(cache_2000 / "market_bars_with_delisted_2000_2026.parquet")
        bench_2015 = pd.read_parquet(cache_2000 / "sensex_bench_2000_2026.parquet")

    results_2015 = []
    modes = [
        ("HYBRID_50_50", "HYBRID 50-50 Pyramiding (Recommended)"),
        ("LAYER_2_CONFIRMATION", "Layer 2 Confirmation (10-Day Incubation)"),
        ("LAYER_1_FULL", "Layer 1 Full (Day 0 Aggressive Entry)"),
    ]

    for mode_id, mode_label in modes:
        engine = UpgradedVCPBacktestEngine(
            initial_capital=1_000_000.0,
            max_slots=8,
            risk_per_trade_pct=0.02,
            min_turnover_rs=30_000_000.0,
            mode=mode_id,
            use_vol_parity=True,
            use_sector_leadership=True,
            tranche2_days=7,
        )
        summary = engine.run_backtest(bars_2015, bench_2015, start_date="2015-01-01", end_date="2026-12-31", mode=mode_id)
        results_2015.append({
            "Mode": mode_label,
            "Net CAGR %": f"+{summary.compounded_cagr_pct:.2f}%",
            "Max Drawdown %": f"{summary.max_drawdown_pct:.2f}%",
            "Final Capital (Lakhs)": f"Rs. {summary.final_capital/100000:.1f}L",
            "Multiple": f"{summary.final_capital/summary.initial_capital:.2f}x",
            "Trades": summary.total_trades,
            "Win Rate %": f"{summary.win_rate_pct:.1f}%",
            "Profit Factor": f"{summary.profit_factor:.2f}",
            "Payoff Ratio": f"{summary.win_loss_ratio:.2f}x",
        })

    df_2015 = pd.DataFrame(results_2015)
    print(df_2015.to_string(index=False))

    # =========================================================================
    # PART 2: FULL 26.8-YEAR SURVIVORSHIP-TENSIONED ERA (2000 - 2026)
    # =========================================================================
    print("\n" + "-" * 95)
    print("2. 26.8-YEAR SURVIVORSHIP-TENSIONED ERA (2000 - 2026, 91 STOCKS, 27 BANKRUPT INCLUDED)")
    print("-" * 95)

    if (cache_2000 / "market_bars_with_delisted_2000_2026.parquet").exists():
        bars_2000 = pd.read_parquet(cache_2000 / "market_bars_with_delisted_2000_2026.parquet")
        bench_2000 = pd.read_parquet(cache_2000 / "sensex_bench_2000_2026.parquet")

        results_2000 = []
        for mode_id, mode_label in modes:
            engine = UpgradedVCPBacktestEngine(
                initial_capital=1_000_000.0,
                max_slots=10,
                risk_per_trade_pct=0.02,
                min_turnover_rs=30_000_000.0,
                mode=mode_id,
                use_vol_parity=True,
                use_sector_leadership=True,
                tranche2_days=10,
            )
            summary = engine.run_backtest(bars_2000, bench_2000, start_date="2000-01-01", end_date="2026-12-31", mode=mode_id)
            results_2000.append({
                "Mode": mode_label,
                "Net CAGR %": f"+{summary.compounded_cagr_pct:.2f}%",
                "Max Drawdown %": f"{summary.max_drawdown_pct:.2f}%",
                "Final Capital": f"Rs. {summary.final_capital/10000000:.2f} Cr" if summary.final_capital >= 10000000 else f"Rs. {summary.final_capital/100000:.1f} Lakhs",
                "Multiple": f"{summary.final_capital/summary.initial_capital:.1f}x",
                "Trades": summary.total_trades,
                "Win Rate %": f"{summary.win_rate_pct:.1f}%",
                "Profit Factor": f"{summary.profit_factor:.2f}",
                "Payoff Ratio": f"{summary.win_loss_ratio:.2f}x",
            })

        df_2000 = pd.DataFrame(results_2000)
        print(df_2000.to_string(index=False))

    print("\n" + "=" * 95)
    print("BACKTEST RUN COMPLETED SUCCESSFULLY!")
    print("=" * 95)


if __name__ == "__main__":
    run_comparative_backtests()
