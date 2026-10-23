import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import pandas as pd
import numpy as np
from scripts.run_capital_constrained_secular_audit import run_simulation

camps_df, eq_df, year_df, stats = run_simulation(num_slots=15)

# Load all 57 symbols
data_dir = Path("data/cache/historical_2015_2026")
bars = pd.read_parquet(data_dir / "market_bars_2015_2026.parquet")
bankrupt_bars = pd.read_parquet(data_dir / "bankrupt_bars_2015_2026.parquet")
all_bars = pd.concat([bars, bankrupt_bars], ignore_index=True)
all_bars["clean_sym"] = all_bars["symbol"].str.replace(".NS", "").str.replace(".BO", "")
all_57_symbols = sorted(all_bars["clean_sym"].unique())

print(f"Total Unique Symbols in Universe: {len(all_57_symbols)}")

# Compute per-symbol metrics
stock_ledger = []
for sym in all_57_symbols:
    sym_camps = camps_df[camps_df["symbol"] == sym]
    n_exec = len(sym_camps)
    if n_exec > 0:
        win_rate = (sym_camps["net_return_pct"] > 0).mean() * 100.0
        avg_cal_days = sym_camps["calendar_days"].mean()
        avg_trade_days = sym_camps["trading_days"].mean()
        avg_ret = sym_camps["net_return_pct"].mean()
        # Real compounded multiple
        comp_mult = np.prod(1.0 + sym_camps["net_return_pct"] / 100.0)
        best_ret = sym_camps["net_return_pct"].max()
        worst_ret = sym_camps["net_return_pct"].min()
        total_pnl = sym_camps["pnl_amount"].sum()
        is_active = (sym_camps["status"] == "Active").any()
    else:
        win_rate = 0.0
        avg_cal_days = 0.0
        avg_trade_days = 0.0
        avg_ret = 0.0
        comp_mult = 1.0
        best_ret = 0.0
        worst_ret = 0.0
        total_pnl = 0.0
        is_active = False

    stock_ledger.append({
        "symbol": sym,
        "executed_campaigns": n_exec,
        "win_rate_pct": win_rate,
        "avg_calendar_days": avg_cal_days,
        "avg_trading_days": avg_trade_days,
        "avg_ret_pct": avg_ret,
        "compounded_multiple": comp_mult,
        "best_ret_pct": best_ret,
        "worst_ret_pct": worst_ret,
        "total_pnl_rs": total_pnl,
        "active_now": "ACTIVE" if is_active else "No"
    })

stock_df = pd.DataFrame(stock_ledger).sort_values("compounded_multiple", ascending=False).reset_index(drop=True)
stock_df.index = stock_df.index + 1
stock_df.to_csv("reports/secular_longterm_hold/all_57_stocks_compounded_ledger.csv")

print("\n--- ALL 57 STOCKS SUMMARY ---")
print(stock_df[["symbol", "executed_campaigns", "win_rate_pct", "avg_calendar_days", "avg_ret_pct", "compounded_multiple", "best_ret_pct", "worst_ret_pct", "active_now"]].to_string())
