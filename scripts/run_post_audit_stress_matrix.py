"""
Master Post-Audit Stress Matrix (2000 - 2026)
Executes:
1. Baseline with Full Audit Fixes (gap_loss_cap_pct=20.0, stage5_fill_mode="FLOOR", stale_exit_sessions=20)
2. Stress Run A: gap_loss_cap_pct=None (unconstrained gap execution at open)
3. Stress Run B: stage5_fill_mode="CLOSE" (Stage 5 fills at the triggering close)
4. Stress Run C (Combined Stress): gap_loss_cap_pct=None AND stage5_fill_mode="CLOSE"
"""
import sys
from pathlib import Path
import pandas as pd
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from blumberg_market_radar.backtest.upgraded_vcp_engine import UpgradedVCPBacktestEngine

def run_matrix():
    data_cache = PROJECT_ROOT / "data" / "cache" / "historical_2000_2026"
    bars_p = data_cache / "market_bars_with_delisted_2000_2026.parquet"
    bench_p = data_cache / "sensex_bench_2000_2026.parquet"

    bars_df = pd.read_parquet(bars_p)
    bench_df = pd.read_parquet(bench_p)

    matrix_configs = [
        {
            "name": "1. Production Default (gap_cap=20%, stage5=FLOOR, stale=20d)",
            "gap_cap": 20.0,
            "stage5_mode": "FLOOR",
            "stale_sessions": 20,
        },
        {
            "name": "2. Stress: Uncapped Gaps (gap_cap=None, stage5=FLOOR, stale=20d)",
            "gap_cap": None,
            "stage5_mode": "FLOOR",
            "stale_sessions": 20,
        },
        {
            "name": "3. Stress: Realistic Stage 5 (gap_cap=20%, stage5=CLOSE, stale=20d)",
            "gap_cap": 20.0,
            "stage5_mode": "CLOSE",
            "stale_sessions": 20,
        },
        {
            "name": "4. Stress: Worst-Case Combined (gap_cap=None, stage5=CLOSE, stale=20d)",
            "gap_cap": None,
            "stage5_mode": "CLOSE",
            "stale_sessions": 20,
        },
    ]

    results = []

    for cfg in matrix_configs:
        print(f"\nExecuting {cfg['name']}...")
        engine = UpgradedVCPBacktestEngine(
            initial_capital=1_000_000.0,
            max_slots=8,
            mode="HYBRID_50_50",
            min_turnover_rs=30_000_000.0,
            slippage_bps_per_side=50.0,
            statutory_bps_per_side=52.6,
            use_equal_weight_slots=True,
            cash_yield_pct_p_a=6.5,
            use_sector_leadership=False,
            tranche2_days=7,
            gap_loss_cap_pct=cfg["gap_cap"],
            stage5_fill_mode=cfg["stage5_mode"],
            stale_exit_sessions=cfg["stale_sessions"],
        )

        res = engine.run_backtest(bars_df, bench_df, start_date="2000-01-01", end_date="2026-10-26")
        eq = res.equity_curve.copy()
        trades = res.trades_df.copy()

        # Drawdown analysis
        eq["peak"] = eq["total_equity"].cummax()
        eq["dd"] = (eq["total_equity"] / eq["peak"] - 1.0) * 100.0
        worst_idx = eq["dd"].idxmin()
        worst_row = eq.iloc[worst_idx]
        peak_sub = eq.iloc[:worst_idx]
        peak_before = peak_sub.loc[peak_sub["total_equity"] == worst_row["peak"]].iloc[-1]

        # Check stale exits
        stale_exits = trades[trades["exit_reason"].str.contains("STALE_DATA_EXIT", case=False, na=False)]

        results.append({
            "Config": cfg["name"],
            "Final_Cap_Cr": round(res.final_capital / 1e7, 2),
            "Multiple": round(res.final_capital / res.initial_capital, 1),
            "CAGR_Pct": round(res.compounded_cagr_pct, 2),
            "Max_DD_Pct": round(res.max_drawdown_pct, 2),
            "DD_Peak_Date": str(peak_before["date"])[:10],
            "DD_Trough_Date": str(worst_row["date"])[:10],
            "DD_Peak_Cr": round(peak_before["total_equity"] / 1e7, 2),
            "DD_Trough_Cr": round(worst_row["total_equity"] / 1e7, 2),
            "Trades": len(trades),
            "Wins": len(trades[trades["pnl_amount"] > 0]),
            "WinRate_Pct": round(len(trades[trades["pnl_amount"] > 0]) / len(trades) * 100.0, 1),
            "Profit_Factor": round(res.profit_factor, 2),
            "Stale_Exits": len(stale_exits),
        })

    res_df = pd.DataFrame(results)
    print("\n" + "=" * 115)
    print("               POST-AUDIT REALISM & STRESS MATRIX RESULTS (2000 - 2026)")
    print("=" * 115)
    print(res_df.to_string(index=False))

    out_csv = PROJECT_ROOT / "reports" / "8_slot_audit" / "post_audit_stress_matrix_2000_2026.csv"
    res_df.to_csv(out_csv, index=False)
    print(f"\nSaved stress matrix to {out_csv}")

if __name__ == "__main__":
    run_matrix()
