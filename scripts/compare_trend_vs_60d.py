"""Compare 60-Day Capped Excursion vs Dynamic Growth-Trailing Exit."""
import sys
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

import pandas as pd
import numpy as np

# Load trades and daily bars
trades = pd.read_parquet("reports/trend_multibagger_backtest/all_trend_multibagger_trades_2015_2026.parquet")
bars = pd.read_parquet("data/cache/historical_2015_2026/market_bars_2015_2026.parquet")
bars["clean_sym"] = bars["symbol"].str.replace(".NS", "").str.replace(".BO", "")
bars["date"] = pd.to_datetime(bars["date"], utc=True)
bars = bars.sort_values(["clean_sym", "date"]).reset_index(drop=True)

sym_bars = {s: grp.reset_index(drop=True) for s, grp in bars.groupby("clean_sym")}

print("=" * 80)
print("🏆 TOP 15 MONSTER MULTIBAGGERS: TREND-RIDING VS 60-DAY CAP")
print("=" * 80)

top15 = trades.sort_values("net_return_pct", ascending=False).head(15)

rows = []
for _, tr in top15.iterrows():
    sym = tr["symbol"]
    sub = sym_bars.get(sym)
    e_dt = tr["entry_date_dt"]
    p_in = tr["entry_price"]
    
    # 60-day price
    ret_60d = 0.0
    if sub is not None:
        future = sub[sub["date"] >= e_dt].reset_index(drop=True)
        if len(future) >= 60:
            c60 = float(future.iloc[59]["close"])
            ret_60d = (c60 / p_in - 1.0) * 100.0
        elif len(future) > 0:
            c60 = float(future.iloc[-1]["close"])
            ret_60d = (c60 / p_in - 1.0) * 100.0

    realized_ret = tr["net_return_pct"]
    peak_ret = tr["peak_gain_pct"]
    days = tr["days_held"]
    
    extra_alpha = realized_ret - ret_60d
    multiple = 1.0 + realized_ret / 100.0
    
    rows.append({
        "symbol": sym,
        "entry_date": e_dt.strftime("%Y-%m-%d"),
        "entry_price": p_in,
        "exit_date": tr["exit_date_dt"].strftime("%Y-%m-%d"),
        "exit_price": tr["exit_price"],
        "days_held": days,
        "ret_60d": ret_60d,
        "realized_ret": realized_ret,
        "peak_ret": peak_ret,
        "multiple": multiple,
        "extra_alpha": extra_alpha,
    })
    print(f"{sym:<12} (Entry: {e_dt.strftime('%Y-%m-%d')}): 60D Gain: {ret_60d:>+6.1f}% -> Trend-Hold Realized: {realized_ret:>+6.1f}% ({multiple:4.1f}x) | Days Held: {days:4d}d | Extra Edge: {extra_alpha:>+6.1f}%")

print("=" * 80)
