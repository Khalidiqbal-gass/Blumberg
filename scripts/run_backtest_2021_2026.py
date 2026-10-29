"""
Comprehensive Backtest Script for Recent Era (2021 - 2026).
Covers:
- 2021 Bull Run
- 2022 Global Rate-Hike / Sideways Consolidation
- 2023 Mega Mid/Smallcap Expansion
- 2024 Election & Expansion Year
- 2025 - 2026 Modern Market
"""
from __future__ import annotations

import sys
from pathlib import Path
import numpy as np
import pandas as pd

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from blumberg_market_radar.backtest.upgraded_vcp_engine import UpgradedVCPBacktestEngine

CACHE_DIR = PROJECT_ROOT / "data" / "cache" / "historical_2015_2026"
REPORT_DIR = PROJECT_ROOT / "reports" / "backtest_2021_2026"
REPORT_DIR.mkdir(parents=True, exist_ok=True)


def run_2021_2026_backtest():
    print("=" * 115)
    print("         BLUMBERG MARKET RADAR - 2021 TO 2026 POST-COVID BULL/BEAR CYCLE AUDIT")
    print("=" * 115)

    bars_clean = CACHE_DIR / "market_bars_2015_2026.parquet"
    bars_bankrupt = CACHE_DIR / "bankrupt_bars_2015_2026.parquet"
    bench_path = CACHE_DIR / "nifty50_bench_2015_2026.parquet"

    if bars_clean.exists():
        b1 = pd.read_parquet(bars_clean)
        b2 = pd.read_parquet(bars_bankrupt) if bars_bankrupt.exists() else pd.DataFrame()
        bars_df = pd.concat([b1, b2], ignore_index=True)
        bench_df = pd.read_parquet(bench_path)
    else:
        cache_2000 = PROJECT_ROOT / "data" / "cache" / "historical_2000_2026"
        bars_df = pd.read_parquet(cache_2000 / "market_bars_with_delisted_2000_2026.parquet")
        bench_df = pd.read_parquet(cache_2000 / "sensex_bench_2000_2026.parquet")

    configurations = [
        ("HYBRID_50_50 (Recommended Sweet-Spot)", "HYBRID_50_50", 8, 7, 20.0, 35.0),
        ("LAYER_1_FULL (Aggressive Day 0)", "LAYER_1_FULL", 8, 10, 20.0, 35.0),
        ("LAYER_2_CONFIRMATION (10d Incubation)", "LAYER_2_CONFIRMATION", 8, 10, 20.0, 35.0),
    ]

    results = []

    print(f"\n{'Configuration Name':<45} | {'Trades':>6} | {'Win %':>6} | {'CAGR %':>9} | {'Max DD %':>9} | {'Final Value':>14} | {'Mult':>5}")
    print("-" * 115)

    summaries = {}

    for label, mode, slots, t2_days, slip_bps, stat_bps in configurations:
        engine = UpgradedVCPBacktestEngine(
            initial_capital=1_000_000.0,
            max_slots=slots,
            risk_per_trade_pct=0.015,
            min_turnover_rs=30_000_000.0,
            slippage_bps_per_side=slip_bps,
            statutory_bps_per_side=stat_bps,
            mode=mode,
            tranche2_days=t2_days,
            use_vol_parity=True,
            use_sector_leadership=False,
        )

        res = engine.run_backtest(
            bars_df=bars_df,
            bench_df=bench_df,
            start_date="2021-01-01",
            end_date="2026-12-31",
            mode=mode,
        )

        summaries[mode] = res
        final_lakhs = res.final_capital / 100_000.0
        mult = res.final_capital / res.initial_capital

        print(
            f"{label:<45} | {res.total_trades:>6,} | {res.win_rate_pct:>5.1f}% | "
            f"{res.compounded_cagr_pct:>+8.2f}% | {res.max_drawdown_pct:>8.2f}% | "
            f"Rs {final_lakhs:>11,.1f} L | {mult:>4.1f}x"
        )

        results.append({
            "Configuration": label,
            "Mode": mode,
            "Total_Trades": res.total_trades,
            "Win_Rate_Pct": round(res.win_rate_pct, 2),
            "Net_CAGR_Pct": round(res.compounded_cagr_pct, 2),
            "Max_Drawdown_Pct": round(res.max_drawdown_pct, 2),
            "Profit_Factor": round(res.profit_factor, 2),
            "Payoff_Ratio": round(res.win_loss_ratio, 2),
            "Final_Capital_Rs": round(res.final_capital, 2),
            "Multiple": round(mult, 2),
            "Total_Friction_Paid_Rs": round(res.total_friction_paid, 2),
        })

        # Save artifacts
        tag = mode.lower()
        res.trades_df.to_csv(REPORT_DIR / f"trades_{tag}.csv", index=False)
        res.equity_curve.to_csv(REPORT_DIR / f"equity_{tag}.csv", index=False)

    print("=" * 115)
    summary_df = pd.DataFrame(results)
    summary_df.to_csv(REPORT_DIR / "AUDIT_SUMMARY_2021_2026.csv", index=False)

    # Detailed Year-by-Year breakdown for HYBRID_50_50
    hybrid_res = summaries["HYBRID_50_50"]
    eq_df = hybrid_res.equity_curve.copy()
    eq_df["date"] = pd.to_datetime(eq_df["date"]).dt.tz_localize(None)
    eq_df["year"] = eq_df["date"].dt.year

    bench_copy = bench_df.copy()
    bench_copy["date"] = pd.to_datetime(bench_copy["date"]).dt.tz_localize(None)
    bench_dict = bench_copy.set_index("date")["close"].to_dict()

    yearly_stats = []
    for yr, grp in eq_df.groupby("year"):
        st_val = grp["total_equity"].iloc[0]
        end_val = grp["total_equity"].iloc[-1]
        yr_ret = (end_val / st_val - 1.0) * 100.0

        st_dt = grp["date"].iloc[0]
        end_dt = grp["date"].iloc[-1]
        b_st = bench_dict.get(st_dt, np.nan)
        b_end = bench_dict.get(end_dt, np.nan)
        b_ret = ((b_end / b_st - 1.0) * 100.0) if (pd.notna(b_st) and pd.notna(b_end) and b_st > 0) else np.nan

        roll_max = grp["total_equity"].cummax()
        dd = ((grp["total_equity"] - roll_max) / roll_max).min() * 100.0

        yearly_stats.append({
            "Year": yr,
            "Start Capital": f"Rs {st_val/100000:.1f} L",
            "End Capital": f"Rs {end_val/100000:.1f} L",
            "Strategy Return": f"{yr_ret:+.2f}%",
            "Nifty Return": f"{b_ret:+.2f}%" if pd.notna(b_ret) else "N/A",
            "Alpha vs Nifty": f"{(yr_ret - b_ret):+.2f}%" if pd.notna(b_ret) else "N/A",
            "Max Drawdown": f"{dd:.2f}%",
        })

    ydf = pd.DataFrame(yearly_stats)
    print("\n--- Year-by-Year Performance (HYBRID 50-50: 2021 - 2026) ---")
    print(ydf.to_string(index=False))

    # Multibaggers
    print("\n--- Top Multibaggers Captured (2021 - 2026) ---")
    tdf = hybrid_res.trades_df
    top_trades = tdf.sort_values("net_return_pct", ascending=False).head(10)
    for _, tr in top_trades.iterrows():
        mult = 1.0 + tr["net_return_pct"] / 100.0
        print(f"{tr['symbol']:<14} | Net Return: +{tr['net_return_pct']:>6.1f}% ({mult:.1f}x) | Exit: {tr['exit_reason']}")


if __name__ == "__main__":
    run_2021_2026_backtest()
