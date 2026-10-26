"""
Quantitative Experiment: Layer 1 (Day 0 Ignition Entry) vs Layer 2 (Day 10 Confirmation Entry).
Compares:
1. Win Rate %
2. Number of Trades
3. Total Multibaggers Captured
4. 26-Year CAGR % (at 5% and 10% slot)
5. Max Drawdown %
6. Average Winner Return %
"""
from __future__ import annotations
import pandas as pd
import numpy as np
from pathlib import Path

DATA_DIR = Path("data/cache/historical_2000_2026")

def compute_cagr(start_val: float, end_val: float, years: float) -> float:
    if start_val <= 0 or end_val <= 0 or years <= 0:
        return 0.0
    return ((end_val / start_val) ** (1.0 / years) - 1.0) * 100.0

def compute_max_drawdown(equity_series: pd.Series) -> float:
    roll_max = equity_series.cummax()
    drawdown = (equity_series - roll_max) / roll_max
    return float(drawdown.min()) * 100.0

# 1. Load Data
bench_df = pd.read_parquet(DATA_DIR / "sensex_bench_2000_2026.parquet")
bench_df["date"] = pd.to_datetime(bench_df["date"]).dt.tz_localize(None)
bench_df = bench_df.sort_values("date").reset_index(drop=True)
bench_df["bench_ret20"] = bench_df["close"].pct_change(20)
bench_series = bench_df[["date", "bench_ret20"]]

market_path = DATA_DIR / "market_bars_with_delisted_2000_2026.parquet"
market_df = pd.read_parquet(market_path)
market_df["date"] = pd.to_datetime(market_df["date"]).dt.tz_localize(None)

# 2. Simulate Layer 1 (Day 0 Entry) vs Layer 2 (Day 10 Entry)
def simulate_universe(entry_mode: str = "LAYER_1"):
    # entry_mode: "LAYER_1" (Buy Day t+1) or "LAYER_2" (Watch 10 days, buy Day t+11 if gain > 0%)
    cost_factor = 0.0015  # 15 bps each way
    trades = []
    
    for sym, group in market_df.groupby("symbol"):
        df = group.sort_values("date").reset_index(drop=True)
        n = len(df)
        if n < 40:
            continue
            
        df["ret20"] = df["close"].pct_change(20)
        df["ret5"] = df["close"].pct_change(5)
        vol_mean = df["volume"].shift(1).rolling(20, min_periods=10).mean()
        df["rvol"] = df["volume"] / vol_mean.where(vol_mean > 0, 1.0)
        range_20 = df["high"].rolling(20).max() - df["low"].rolling(20).min()
        range_5 = df["high"].rolling(5).max() - df["low"].rolling(5).min()
        df["compression"] = (range_5 / range_20.where(range_20 > 0, 1.0)).fillna(1.0)
        
        merged = pd.merge(df[["date", "ret20"]], bench_series, on="date", how="left")
        df["rs_20"] = merged["ret20"] - merged["bench_ret20"].fillna(0.0)
        
        in_pos = False
        in_watch = False
        watch_idx = 0
        watch_price = 0.0
        
        entry_idx = 0
        entry_date = None
        entry_price = 0.0
        peak_price = 0.0
        
        for i in range(25, n - 1):
            row = df.iloc[i]
            next_row = df.iloc[i + 1]
            
            if not in_pos and not in_watch:
                comp = float(row["compression"]) if pd.notna(row["compression"]) else 1.0
                rvol = float(row["rvol"]) if pd.notna(row["rvol"]) else 1.0
                rs = float(row["rs_20"]) if pd.notna(row["rs_20"]) else 0.0
                ret5 = float(row["ret5"]) if pd.notna(row["ret5"]) else 0.0
                ret20 = float(row["ret20"]) if pd.notna(row["ret20"]) else 0.0
                
                radar_signal = (
                    ((comp <= 0.70) or (ret5 > 0 and 0 < ret20 <= 0.35))
                    and (rvol >= 1.40)
                    and (rs >= -0.01)
                )
                
                if radar_signal:
                    next_open = float(next_row["open"])
                    next_high = float(next_row["high"])
                    next_low = float(next_row["low"])
                    if next_open == next_high and next_high == next_low:
                        continue  # circuit lock
                        
                    if entry_mode == "LAYER_1":
                        in_pos = True
                        entry_idx = i + 1
                        entry_date = pd.to_datetime(next_row["date"])
                        entry_price = next_open * (1.0 + cost_factor)
                        peak_price = entry_price
                    else:  # LAYER_2: Put on 10-day incubation watchlist
                        in_watch = True
                        watch_idx = i + 1
                        watch_price = next_open
            
            elif in_watch:
                # Stock is incubating in Layer 1 watchlist (Day 0 to 10)
                days_incubated = (i - watch_idx + 1)
                if days_incubated >= 10:
                    cur_close = float(row["close"])
                    # Check if stock has positive growth above discovery price (Gain > 0%)
                    if cur_close > watch_price and float(row["low"]) > watch_price * 0.92:
                        # Graduated to Layer 2! Buy at next open
                        next_open = float(next_row["open"])
                        next_high = float(next_row["high"])
                        next_low = float(next_row["low"])
                        if next_open == next_high and next_high == next_low:
                            in_watch = False
                            continue
                        in_pos = True
                        entry_idx = i + 1
                        entry_date = pd.to_datetime(next_row["date"])
                        entry_price = next_open * (1.0 + cost_factor)
                        peak_price = entry_price
                        in_watch = False
                    else:
                        # Failed Layer 1 incubation: drop from watchlist
                        in_watch = False
                        
            elif in_pos:
                cur_date = pd.to_datetime(row["date"])
                cur_open = float(row["open"])
                cur_high = float(row["high"])
                cur_low = float(row["low"])
                cur_close = float(row["close"])
                days_held = i - entry_idx + 1
                
                # Hardened against Lookahead: evaluate trailing stops using prior peak
                prior_peak = peak_price
                peak_gain_pct = (prior_peak / entry_price - 1.0) * 100.0
                dip_from_peak_pct = (cur_close / prior_peak - 1.0) * 100.0
                
                if peak_gain_pct >= 100.0:
                    trail_buffer = 20.0
                elif peak_gain_pct >= 50.0:
                    trail_buffer = 17.0
                elif peak_gain_pct >= 25.0:
                    trail_buffer = 14.0
                else:
                    trail_buffer = None
                    
                # 1. Hard Initial Stop Loss (-8% with gap-down fill)
                if (cur_low <= entry_price * 0.92) and (peak_gain_pct < 15.0):
                    fill_p = min(entry_price * 0.92, cur_open)
                    exit_price = fill_p * (1.0 - cost_factor)
                    net_ret = (exit_price / entry_price - 1.0) * 100.0
                    trades.append({
                        "symbol": sym, "entry_date": entry_date, "exit_date": cur_date,
                        "entry_price": entry_price, "exit_price": exit_price,
                        "days_held": days_held, "net_return_pct": net_ret,
                        "peak_gain_pct": peak_gain_pct, "multiple": exit_price / entry_price,
                        "exit_reason": "INITIAL_STOP_LOSS"
                    })
                    in_pos = False
                # 2. Breakeven Stop
                elif (peak_gain_pct >= 15.0) and (trail_buffer is None) and (cur_low <= entry_price):
                    exit_price = entry_price * (1.0 - cost_factor)
                    net_ret = (exit_price / entry_price - 1.0) * 100.0
                    trades.append({
                        "symbol": sym, "entry_date": entry_date, "exit_date": cur_date,
                        "entry_price": entry_price, "exit_price": exit_price,
                        "days_held": days_held, "net_return_pct": net_ret,
                        "peak_gain_pct": peak_gain_pct, "multiple": exit_price / entry_price,
                        "exit_reason": "BREAKEVEN_STOP"
                    })
                    in_pos = False
                # 3. Dynamic Growth-Trailing Exit
                elif (trail_buffer is not None) and (dip_from_peak_pct <= -trail_buffer):
                    exit_price = cur_close * (1.0 - cost_factor)
                    net_ret = (exit_price / entry_price - 1.0) * 100.0
                    trades.append({
                        "symbol": sym, "entry_date": entry_date, "exit_date": cur_date,
                        "entry_price": entry_price, "exit_price": exit_price,
                        "days_held": days_held, "net_return_pct": net_ret,
                        "peak_gain_pct": peak_gain_pct, "multiple": exit_price / entry_price,
                        "exit_reason": f"TRAILING_EXIT_{int(trail_buffer)}PCT"
                    })
                    in_pos = False
                # 4. Stagnation Timeout (30 days if peak < 10%)
                elif (days_held >= 30) and (peak_gain_pct < 10.0):
                    exit_price = cur_close * (1.0 - cost_factor)
                    net_ret = (exit_price / entry_price - 1.0) * 100.0
                    trades.append({
                        "symbol": sym, "entry_date": entry_date, "exit_date": cur_date,
                        "entry_price": entry_price, "exit_price": exit_price,
                        "days_held": days_held, "net_return_pct": net_ret,
                        "peak_gain_pct": peak_gain_pct, "multiple": exit_price / entry_price,
                        "exit_reason": "STAGNATION_TIMEOUT"
                    })
                    in_pos = False

                if in_pos:
                    if cur_high > peak_price:
                        peak_price = cur_high
                    
    tdf = pd.DataFrame(trades).sort_values("entry_date").reset_index(drop=True)
    tdf["win"] = tdf["net_return_pct"] > 0
    tdf["is_multibagger_2x"] = tdf["net_return_pct"] >= 100.0
    tdf["is_super_runner_3x"] = tdf["net_return_pct"] >= 200.0
    
    # Portfolio equity simulation (5% slot)
    cap = 1_000_000.0
    equity = [cap]
    for _, tr in tdf.iterrows():
        gain = (cap * 0.05) * (tr["net_return_pct"] / 100.0)
        cap += gain
        equity.append(cap)
    eq_series = pd.Series(equity)
    cagr_5 = compute_cagr(1_000_000.0, cap, 26.8)
    mdd_5 = compute_max_drawdown(eq_series)
    
    # Portfolio equity simulation (10% slot)
    cap10 = 1_000_000.0
    equity10 = [cap10]
    for _, tr in tdf.iterrows():
        gain = (cap10 * 0.10) * (tr["net_return_pct"] / 100.0)
        cap10 += gain
        equity10.append(cap10)
    cagr_10 = compute_cagr(1_000_000.0, cap10, 26.8)
    mdd_10 = compute_max_drawdown(pd.Series(equity10))
    
    return {
        "mode": entry_mode,
        "total_trades": len(tdf),
        "win_rate_pct": tdf["win"].mean() * 100.0,
        "stop_losses": (tdf["exit_reason"] == "INITIAL_STOP_LOSS").sum(),
        "multibaggers_2x": tdf["is_multibagger_2x"].sum(),
        "super_runners_3x": tdf["is_super_runner_3x"].sum(),
        "avg_win_pct": tdf[tdf["win"]]["net_return_pct"].mean(),
        "avg_loss_pct": tdf[~tdf["win"]]["net_return_pct"].mean(),
        "cagr_5pct_slot": cagr_5,
        "mdd_5pct_slot": mdd_5,
        "cagr_10pct_slot": cagr_10,
        "mdd_10pct_slot": mdd_10,
        "final_cap_5pct": cap,
    }

print("Running Layer 1 simulation...")
res_l1 = simulate_universe("LAYER_1")
print("Running Layer 2 simulation...")
res_l2 = simulate_universe("LAYER_2")

import sys
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

print("\n" + "=" * 80)
print("EXACT QUANTITATIVE COMPARISON: LAYER 1 ENTRY vs LAYER 2 ENTRY")
print("=" * 80)
print("Metric / Dimension              | Layer 1 Entry (Day 0 Ignition) | Layer 2 Entry (Day 10 Confirmation)")
print("--------------------------------|--------------------------------|-------------------------------------")
print(f"Total Trades Taken              | {res_l1['total_trades']:,} trades                  | {res_l2['total_trades']:,} trades")
print(f"Win Rate %                      | {res_l1['win_rate_pct']:.1f}%                          | {res_l2['win_rate_pct']:.1f}%")
print(f"Total Stop Loss Hits (-8%)      | {res_l1['stop_losses']:,} hits                   | {res_l2['stop_losses']:,} hits")
print(f"2x+ Multibaggers Captured       | {res_l1['multibaggers_2x']} Stocks                      | {res_l2['multibaggers_2x']} Stocks")
print(f"3x+ Super-Runners Captured      | {res_l1['super_runners_3x']} Stocks                      | {res_l2['super_runners_3x']} Stocks")
print(f"Avg Gain on Winners             | +{res_l1['avg_win_pct']:.1f}%                        | +{res_l2['avg_win_pct']:.1f}%")
print(f"26-Yr CAGR % (Optimal 5% Slot)  | {res_l1['cagr_5pct_slot']:.1f}%                         | {res_l2['cagr_5pct_slot']:.1f}%")
print(f"Max Historical Drawdown (5%)    | {res_l1['mdd_5pct_slot']:.1f}%                        | {res_l2['mdd_5pct_slot']:.1f}%")
print(f"26-Yr CAGR % (Aggressive 10%)   | {res_l1['cagr_10pct_slot']:.1f}%                         | {res_l2['cagr_10pct_slot']:.1f}%")
print(f"Rs 10 Lakhs Grown To (5% Slot)  | Rs {res_l1['final_cap_5pct']/100000:,.1f} Lakhs           | Rs {res_l2['final_cap_5pct']/100000:,.1f} Lakhs")
print("=" * 80)
