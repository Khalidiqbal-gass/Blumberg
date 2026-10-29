"""
Fine-Tuned Institutional Backtest Script (2000 - 2026).
Fine-tuned parameters:
- Realistic Institutional Friction: 20 bps slippage + 35 bps taxes (55 bps total per side).
- Strict Liquidity & Quality Gate: min_turnover_rs = ₹5 Cr + RS Score filtering to eliminate over-trading.
- Clean T+1 Cash Settlement & Zero Lookahead Execution.
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

from blumberg_market_radar.backtest.upgraded_vcp_engine import UpgradedVCPBacktestEngine

DATA_DIR = PROJECT_ROOT / "data" / "cache" / "historical_2000_2026"
REPORT_DIR = PROJECT_ROOT / "reports" / "finetuned_institutional_audit"
REPORT_DIR.mkdir(parents=True, exist_ok=True)


def run_finetuned_audit() -> None:
    bench_path = DATA_DIR / "sensex_bench_2000_2026.parquet"
    market_path = DATA_DIR / "market_bars_with_delisted_2000_2026.parquet"

    if not bench_path.exists() or not market_path.exists():
        print(f"[ERROR] Required Parquet data files missing in {DATA_DIR}")
        sys.exit(1)

    print("Loading historical market and benchmark parquet archives...")
    bench_df = pd.read_parquet(bench_path)
    bars_df = pd.read_parquet(market_path)
    print(f"Loaded {len(bars_df):,} daily bars across {bars_df['symbol'].nunique()} equities.\n")

    # Fine-tuned institutional configurations
    configurations = [
        ("HYBRID_50_50 (Fine-Tuned Institutional)", "HYBRID_50_50", 10),
        ("LAYER_2_CONFIRMATION (Low-Risk 10d Incubation)", "LAYER_2_CONFIRMATION", 10),
        ("LAYER_1_FULL (Aggressive Day 0 Entry)", "LAYER_1_FULL", 10),
    ]

    summary_rows = []

    print("=" * 115)
    print(f"{'Configuration Name':<45} | {'Trades':>6} | {'Win %':>6} | {'CAGR %':>9} | {'Max DD %':>9} | {'Final Value':>14}")
    print("=" * 115)

    for label, mode, slots in configurations:
        engine = UpgradedVCPBacktestEngine(
            initial_capital=1_000_000.0,
            max_slots=slots,
            risk_per_trade_pct=0.01,
            min_turnover_rs=50_000_000.0,    # ₹5 Cr daily liquidity filter to eliminate noise
            slippage_bps_per_side=20.0,     # Fine-tuned liquid slippage (20 bps)
            statutory_bps_per_side=35.0,    # STT + GST + Stamp Duty (35 bps) -> Total 55 bps per side
            entry_mode=mode,
            incubation_days=10,
            use_vol_parity=True,
            use_sector_leadership=False,
        )

        res = engine.run_backtest(
            bars_df=bars_df,
            bench_df=bench_df,
            start_date="2000-01-01",
            end_date="2026-12-31",
        )

        final_lakhs = res.final_capital / 100_000.0
        print(
            f"{label:<45} | {res.total_trades:>6,} | {res.win_rate_pct:>5.1f}% | "
            f"{res.compounded_cagr_pct:>+8.2f}% | {res.max_drawdown_pct:>8.2f}% | "
            f"Rs {final_lakhs:>11,.1f} L"
        )

        summary_rows.append({
            "Configuration": label,
            "Entry_Mode": mode,
            "Total_Trades": res.total_trades,
            "Win_Rate_Pct": round(res.win_rate_pct, 2),
            "Net_CAGR_Pct": round(res.compounded_cagr_pct, 2),
            "Max_Drawdown_Pct": round(res.max_drawdown_pct, 2),
            "Profit_Factor": round(res.profit_factor, 2),
            "Final_Capital_Rs": round(res.final_capital, 2),
            "Total_Friction_Paid_Rs": round(res.total_friction_paid, 2),
        })

        tag = mode.lower()
        res.trades_df.to_csv(REPORT_DIR / f"trades_{tag}.csv", index=False)
        res.equity_curve.to_csv(REPORT_DIR / f"equity_{tag}.csv", index=False)

    print("=" * 115)
    summary_df = pd.DataFrame(summary_rows)
    summary_df.to_csv(REPORT_DIR / "FINETUNED_AUDIT_SUMMARY.csv", index=False)
    print(f"\nSaved fine-tuned master audit summary report to: {REPORT_DIR / 'FINETUNED_AUDIT_SUMMARY.csv'}")


if __name__ == "__main__":
    run_finetuned_audit()
