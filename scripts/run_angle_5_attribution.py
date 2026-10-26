"""Angle 5: Stock-Level Attribution & Multibagger / Stop-Loss Breakdown."""
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
REPORT_DIR = PROJECT_ROOT / "reports" / "adversarial_champion_audit"
DESKTOP_DIR = Path(r"C:\Users\DELL\OneDrive\Desktop\BLUMBERG_AUDIT_FILES\ADVERSARIAL_CHAMPION_AUDIT")

REPORT_DIR.mkdir(parents=True, exist_ok=True)
DESKTOP_DIR.mkdir(parents=True, exist_ok=True)

bench_df = pd.read_parquet(DATA_DIR / "sensex_bench_2000_2026.parquet")
bars_df = pd.read_parquet(DATA_DIR / "market_bars_with_delisted_2000_2026.parquet")

engine = UpgradedVCPBacktestEngine(
    initial_capital=1_000_000.0,
    max_slots=7,
    mode="HYBRID_50_50",
    min_turnover_rs=30_000_000.0,
    slippage_bps_per_side=20.0,
    statutory_bps_per_side=35.0,
    use_equal_weight_slots=True,
    cash_yield_pct_p_a=6.5,
    use_sector_leadership=True,
    tranche2_days=7,
)

res = engine.run_backtest(bars_df, bench_df, start_date="2000-01-01", end_date="2026-10-26")
trades_df = res.trades_df

stock_records = []
for s, grp in trades_df.groupby("symbol"):
    tot = len(grp)
    wins = len(grp[grp["net_return_pct"] > 0])
    sl_hits = len(grp[grp["exit_reason"].str.contains("STOP|Stop|INITIAL|Initial|Circuit Breaker")])
    tot_pnl = grp["pnl_amount"].sum()
    best_gain = grp["net_return_pct"].max()
    worst_loss = grp["net_return_pct"].min()
    cum_mult = (1.0 + grp["net_return_pct"] / 100.0).prod()

    stock_records.append({
        "Symbol": s,
        "Trades": tot,
        "Wins": wins,
        "SL_Hits": sl_hits,
        "Win_Rate_%": round(wins / tot * 100.0, 1),
        "Best_Gain_%": round(best_gain, 1),
        "Worst_Loss_%": round(worst_loss, 1),
        "Cumulative_Multiple": round(cum_mult, 2),
        "Total_PnL_Rs": round(tot_pnl, 2),
    })

stk_df = pd.DataFrame(stock_records).sort_values("Cumulative_Multiple", ascending=False)
stk_df.to_csv(REPORT_DIR / "ADVERSARIAL_ALL_EQUITIES_ATTRIBUTION.csv", index=False)
stk_df.to_csv(DESKTOP_DIR / "ADVERSARIAL_ALL_EQUITIES_ATTRIBUTION.csv", index=False)

print("=" * 100)
print("TOP 10 WEALTH MULTIPLIER EQUITIES (2000 - 2026)")
print("=" * 100)
print(stk_df.head(10).to_string(index=False))

print("\n" + "=" * 100)
print("TOP 10 BIGGEST PnL GENERATING EQUITIES (Rupees)")
print("=" * 100)
pnl_sorted = stk_df.sort_values("Total_PnL_Rs", ascending=False)
print(pnl_sorted.head(10).to_string(index=False))

print("\n" + "=" * 100)
print("TOP 5 MOST PUNISHED EQUITIES (Highest SL Hitters)")
print("=" * 100)
sl_sorted = stk_df.sort_values("SL_Hits", ascending=False)
print(sl_sorted.head(5).to_string(index=False))
