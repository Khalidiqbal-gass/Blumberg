"""
Ablation Study: Disentangling Entry Anchor, T1 Friction Blend, and Glitch Cleaning
to precisely determine why Max Drawdown deepened from -36.25% to -41.27%.
"""
import sys
from pathlib import Path
import pandas as pd
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from blumberg_market_radar.backtest.upgraded_vcp_engine import UpgradedVCPBacktestEngine
from blumberg_market_radar.data.validation import clean_transient_price_spikes

def run_ablation():
    data_cache = PROJECT_ROOT / "data" / "cache" / "historical_2000_2026"
    bars_p = data_cache / "market_bars_with_delisted_2000_2026.parquet"
    bench_p = data_cache / "sensex_bench_2000_2026.parquet"

    raw_bars = pd.read_parquet(bars_p)
    bench_df = pd.read_parquet(bench_p)

    # Cleaned bars
    clean_bars, num_repaired = clean_transient_price_spikes(raw_bars)
    print(f"Repaired {num_repaired} transient price spikes in cleaned dataset.")

    configs = [
        {
            "name": "1. Raw Data + Legacy Anchor (Pre-Patch Baseline)",
            "data": raw_bars,
            "anchor_mode": "T1_INITIAL",
            "blend_mode": "INVESTED_OVER_SHARES",
        },
        {
            "name": "2. Raw Data + Legacy Anchor + Fixed T1 Fill",
            "data": raw_bars,
            "anchor_mode": "T1_INITIAL",
            "blend_mode": "RAW_FILL",
        },
        {
            "name": "3. Raw Data + New Blended Anchor + Legacy T1 Fill",
            "data": raw_bars,
            "anchor_mode": "BLENDED_RAW",
            "blend_mode": "INVESTED_OVER_SHARES",
        },
        {
            "name": "4. Raw Data + New Blended Anchor + Fixed T1 Fill (Current Committed)",
            "data": raw_bars,
            "anchor_mode": "BLENDED_RAW",
            "blend_mode": "RAW_FILL",
        },
        {
            "name": "5. Clean Data + Legacy Anchor + Legacy T1 Fill",
            "data": clean_bars,
            "anchor_mode": "T1_INITIAL",
            "blend_mode": "INVESTED_OVER_SHARES",
        },
        {
            "name": "6. Clean Data + New Blended Anchor + Fixed T1 Fill",
            "data": clean_bars,
            "anchor_mode": "BLENDED_RAW",
            "blend_mode": "RAW_FILL",
        },
    ]

    results = []

    for cfg in configs:
        print(f"\nRunning {cfg['name']}...")
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
            entry_anchor_mode=cfg["anchor_mode"],
            t1_blend_mode=cfg["blend_mode"],
        )

        res = engine.run_backtest(cfg["data"], bench_df, start_date="2000-01-01", end_date="2026-10-26")
        eq = res.equity_curve.copy()
        trades = res.trades_df.copy()

        # Find worst DD peak & trough
        eq["peak"] = eq["total_equity"].cummax()
        eq["dd"] = (eq["total_equity"] / eq["peak"] - 1.0) * 100.0
        worst_idx = eq["dd"].idxmin()
        worst_row = eq.iloc[worst_idx]
        peak_sub = eq.iloc[:worst_idx]
        peak_before = peak_sub.loc[peak_sub["total_equity"] == worst_row["peak"]].iloc[-1]

        results.append({
            "Config": cfg["name"],
            "Final_Cap_Cr": round(res.final_capital / 1e7, 2),
            "CAGR_Pct": round(res.compounded_cagr_pct, 2),
            "Max_DD_Pct": round(res.max_drawdown_pct, 2),
            "DD_Peak_Date": str(peak_before["date"])[:10],
            "DD_Trough_Date": str(worst_row["date"])[:10],
            "DD_Peak_Cr": round(peak_before["total_equity"] / 1e7, 2),
            "DD_Trough_Cr": round(worst_row["total_equity"] / 1e7, 2),
            "Trades": len(trades),
            "Wins": len(trades[trades["net_return_pct"] > 0]),
            "WinRate_Pct": round(res.win_rate_pct, 1),
            "Profit_Factor": round(res.profit_factor, 2),
        })

    res_df = pd.DataFrame(results)
    print("\n" + "=" * 110)
    print("                      ABLATION STUDY RESULTS (2000 - 2026)")
    print("=" * 110)
    print(res_df.to_string(index=False))
    
    out_path = PROJECT_ROOT / "reports" / "8_slot_audit" / "ablation_drawdown_anchor_vs_glitch.csv"
    res_df.to_csv(out_path, index=False)
    print(f"\nSaved results to {out_path}")

if __name__ == "__main__":
    run_ablation()
