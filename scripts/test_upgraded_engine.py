"""
Fast Vectorized Comparative Engine Test: Base Model vs Upgraded Institutional Model (2000 - 2026)
Vectorizes rolling 52w highs and regime lookups for blazing speed.
"""
import sys
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

import pandas as pd
import numpy as np

print("Loading data...")
bars_df = pd.read_parquet("data/cache/historical_2000_2026/market_bars_2000_2026_unified.parquet")
bench_df = pd.read_parquet("data/cache/historical_2000_2026/sensex_bench_2000_2026.parquet")
bench_df["date"] = pd.to_datetime(bench_df["date"]).dt.tz_localize(None)
bench_df = bench_df.sort_values("date").reset_index(drop=True)
bench_df["bench_ema200"] = bench_df["close"].ewm(span=200, adjust=False).mean()
bench_df["is_bull_regime"] = bench_df["close"] >= bench_df["bench_ema200"]

bench_regime = dict(zip(bench_df["date"], bench_df["is_bull_regime"]))

# Features
from blumberg_market_radar.scanner.radar import compute_pre_rally_features
features_df = compute_pre_rally_features(bars_df, bench_df)
features_df["date"] = pd.to_datetime(features_df["date"]).dt.tz_localize(None)
features_df = features_df.sort_values(["symbol", "date"]).reset_index(drop=True)

# Precompute vectorized filters
print("Pre-computing vectorized market regime and 52w high filters...")
features_df["high_52w"] = features_df.groupby("symbol")["high"].transform(lambda s: s.rolling(250, min_periods=1).max())
features_df["stage2_uptrend"] = features_df["close"] >= features_df["high_52w"] * 0.75
features_df["is_bull_regime"] = features_df["date"].map(bench_regime).fillna(True)


def simulate_engine(apply_regime_filter: bool, apply_stage2_filter: bool, min_rs: float = -0.01):
    cost_factor = 102.6 / 10000.0
    initial_stop_pct = 8.0
    breakeven_trigger_pct = 15.0
    stagnation_days = 30
    trades = []

    for sym, group in features_df.groupby("symbol"):
        df = group.reset_index(drop=True)
        n = len(df)
        if n < 30:
            continue

        # Extract numpy arrays for blazing 0.05s execution
        opens = df["open"].to_numpy()
        highs = df["high"].to_numpy()
        lows = df["low"].to_numpy()
        closes = df["close"].to_numpy()
        dates = df["date"].to_numpy()
        comps = df["range_compression_ratio"].fillna(1.0).to_numpy()
        rvols = df["relative_volume_20d"].fillna(1.0).to_numpy()
        rss = df["rs_20d"].fillna(0.0).to_numpy()
        stage2s = df["stage2_uptrend"].to_numpy()
        bulls = df["is_bull_regime"].to_numpy()

        in_pos = False
        entry_idx = 0
        entry_date = None
        entry_price = 0.0
        peak_price = 0.0

        for i in range(n - 1):
            if not in_pos:
                if apply_regime_filter and not bulls[i]:
                    continue
                if apply_stage2_filter and not stage2s[i]:
                    continue
                if comps[i] <= 0.70 and rvols[i] >= 1.40 and rss[i] >= min_rs:
                    next_open = opens[i + 1] if opens[i + 1] > 0 else closes[i]
                    if next_open < closes[i] * 0.98:  # avoid severe gap-downs
                        continue

                    in_pos = True
                    entry_idx = i + 1
                    entry_date = dates[i + 1]
                    entry_price = next_open * (1.0 + cost_factor)
                    peak_price = entry_price
            else:
                cur_high = highs[i]
                cur_low = lows[i]
                cur_close = closes[i]
                cur_date = dates[i]
                days_held = i - entry_idx + 1

                if cur_high > peak_price:
                    peak_price = cur_high

                peak_gain_pct = (peak_price / entry_price - 1.0) * 100.0
                dip_from_peak_pct = (cur_close / peak_price - 1.0) * 100.0

                if peak_gain_pct >= 100.0:
                    trail_buffer = 20.0
                elif peak_gain_pct >= 50.0:
                    trail_buffer = 17.0
                elif peak_gain_pct >= 25.0:
                    trail_buffer = 14.0
                else:
                    trail_buffer = None

                # 1. Hard Initial Stop Loss (-8.0%)
                if (cur_low <= entry_price * (1.0 - initial_stop_pct / 100.0)) and (peak_gain_pct < breakeven_trigger_pct):
                    exit_price = entry_price * (1.0 - initial_stop_pct / 100.0) * (1.0 - cost_factor)
                    net_ret = (exit_price / entry_price - 1.0) * 100.0
                    trades.append({
                        "symbol": sym,
                        "entry_date": entry_date,
                        "exit_date": cur_date,
                        "days_held": days_held,
                        "net_return_pct": net_ret,
                        "multiple": 1.0 + net_ret / 100.0,
                        "win": net_ret > 0.0,
                    })
                    in_pos = False

                # 2. Breakeven Stop
                elif (peak_gain_pct >= breakeven_trigger_pct) and (trail_buffer is None) and (cur_low <= entry_price):
                    exit_price = entry_price * (1.0 - cost_factor)
                    net_ret = (exit_price / entry_price - 1.0) * 100.0
                    trades.append({
                        "symbol": sym,
                        "entry_date": entry_date,
                        "exit_date": cur_date,
                        "days_held": days_held,
                        "net_return_pct": net_ret,
                        "multiple": 1.0 + net_ret / 100.0,
                        "win": net_ret > 0.0,
                    })
                    in_pos = False

                # 3. Dynamic Trailing Exit
                elif (trail_buffer is not None) and (dip_from_peak_pct <= -trail_buffer):
                    exit_price = cur_close * (1.0 - cost_factor)
                    net_ret = (exit_price / entry_price - 1.0) * 100.0
                    trades.append({
                        "symbol": sym,
                        "entry_date": entry_date,
                        "exit_date": cur_date,
                        "days_held": days_held,
                        "net_return_pct": net_ret,
                        "multiple": 1.0 + net_ret / 100.0,
                        "win": net_ret > 0.0,
                    })
                    in_pos = False

                # 4. Stagnation Timeout
                elif (days_held >= stagnation_days) and (peak_gain_pct < 10.0):
                    exit_price = cur_close * (1.0 - cost_factor)
                    net_ret = (exit_price / entry_price - 1.0) * 100.0
                    trades.append({
                        "symbol": sym,
                        "entry_date": entry_date,
                        "exit_date": cur_date,
                        "days_held": days_held,
                        "net_return_pct": net_ret,
                        "multiple": 1.0 + net_ret / 100.0,
                        "win": net_ret > 0.0,
                    })
                    in_pos = False

        if in_pos:
            exit_price = closes[-1] * (1.0 - cost_factor)
            net_ret = (exit_price / entry_price - 1.0) * 100.0
            trades.append({
                "symbol": sym,
                "entry_date": entry_date,
                "exit_date": dates[-1],
                "days_held": n - entry_idx,
                "net_return_pct": net_ret,
                "multiple": 1.0 + net_ret / 100.0,
                "win": net_ret > 0.0,
            })

    t_df = pd.DataFrame(trades)
    
    # Portfolio simulation: Allocate 10% per slot
    capital = 1_000_000.0
    equity = [capital]
    for _, tr in t_df.sort_values("entry_date").iterrows():
        gain = (capital * 0.10) * (tr["net_return_pct"] / 100.0)
        capital += gain
        equity.append(capital)
    
    eq_series = pd.Series(equity)
    cagr = ((capital / 1_000_000.0) ** (1.0 / 26.8) - 1.0) * 100.0
    roll_max = eq_series.cummax()
    max_dd = float(((eq_series - roll_max) / roll_max).min()) * 100.0
    
    gains = t_df[t_df["net_return_pct"] > 0]["net_return_pct"].sum()
    losses = abs(t_df[t_df["net_return_pct"] < 0]["net_return_pct"].sum())
    pf = gains / losses if losses > 0 else 0.0
    
    mb_2x = (t_df["net_return_pct"] >= 100.0).sum()
    mb_3x = (t_df["net_return_pct"] >= 200.0).sum()
    mb_5x = (t_df["net_return_pct"] >= 400.0).sum()

    return {
        "trades": len(t_df),
        "win_rate": t_df["win"].mean() * 100.0,
        "avg_return": t_df["net_return_pct"].mean(),
        "profit_factor": pf,
        "cagr": cagr,
        "max_dd": max_dd,
        "final_cap_lakhs": capital / 100_000.0,
        "mb_2x": mb_2x,
        "mb_3x": mb_3x,
        "mb_5x": mb_5x,
    }

print("Running Base Model...")
base_res = simulate_engine(apply_regime_filter=False, apply_stage2_filter=False, min_rs=-0.01)

print("Running Upgraded Model (Nifty 200-EMA Regime + Stage 2 Filter + RS >= 0.0)...")
upgr_res = simulate_engine(apply_regime_filter=True, apply_stage2_filter=True, min_rs=0.0)

print("\n" + "=" * 80)
print("🎯 SIDE-BY-SIDE COMPARISON: BASE MODEL VS UPGRADED INSTITUTIONAL MODEL")
print("=" * 80)
print(f"{'Metric':<30} | {'Base Model (Current PDF)':<25} | {'Upgraded Model':<25}")
print("-" * 80)
print(f"{'Total Executed Trades':<30} | {base_res['trades']:<25} | {upgr_res['trades']:<25}")
print(f"{'Win Rate %':<30} | {base_res['win_rate']:<24.1f}% | {upgr_res['win_rate']:<24.1f}%")
print(f"{'Profit Factor':<30} | {base_res['profit_factor']:<25.2f} | {upgr_res['profit_factor']:<25.2f}")
print(f"{'Average Return Per Trade %':<30} | {base_res['avg_return']:<+24.2f}% | {upgr_res['avg_return']:<+24.2f}%")
print(f"{'Max Drawdown %':<30} | {base_res['max_dd']:<24.1f}% | {upgr_res['max_dd']:<24.1f}%")
print(f"{'26-Year CAGR %':<30} | {base_res['cagr']:<24.2f}% | {upgr_res['cagr']:<24.2f}%")
print(f"{'2x+ Multibaggers (100%+)':<30} | {base_res['mb_2x']:<25} | {upgr_res['mb_2x']:<25}")
print(f"{'3x+ Multibaggers (200%+)':<30} | {base_res['mb_3x']:<25} | {upgr_res['mb_3x']:<25}")
print(f"{'5x+ Multibaggers (400%+)':<30} | {base_res['mb_5x']:<25} | {upgr_res['mb_5x']:<25}")
print("=" * 80)
