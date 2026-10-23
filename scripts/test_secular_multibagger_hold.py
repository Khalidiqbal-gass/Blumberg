"""Secular Long-Term Pre-Rally Hold Strategy:
Find stock before rally starts, enter at ignition point, and HOLD continuously as long as growth trend persists.
Zero premature selling. Zero frequent trading churn.
"""
import pandas as pd
import numpy as np
from pathlib import Path

def run_secular_model():
    print("=" * 80)
    print("SECULAR PRE-RALLY IGNITION & LONG-TERM HOLD MODEL (2015-2026)")
    print("=" * 80)

    # 1. Load bars
    bars = pd.read_parquet("data/cache/historical_2015_2026/market_bars_2015_2026.parquet")
    bars["date"] = pd.to_datetime(bars["date"], utc=True)
    bars["clean_sym"] = bars["symbol"].str.replace(".NS", "").str.replace(".BO", "")

    bankrupt_bars = pd.read_parquet("data/cache/historical_2015_2026/bankrupt_bars_2015_2026.parquet")
    bankrupt_bars["date"] = pd.to_datetime(bankrupt_bars["date"], utc=True)

    all_bars = pd.concat([bars, bankrupt_bars], ignore_index=True).sort_values(["clean_sym", "date"]).reset_index(drop=True)

    # 2. Benchmark
    bench = pd.read_parquet("data/cache/historical_2015_2026/nifty50_bench_2015_2026.parquet")
    bench["date"] = pd.to_datetime(bench["date"], utc=True)
    b_first = bench.iloc[0]["close"]
    b_last = bench.iloc[-1]["close"]
    n50_cagr = ((b_last / b_first) ** (1.0 / 11.3) - 1.0) * 100.0

    campaigns = []
    
    for sym, grp in all_bars.groupby("clean_sym"):
        df = grp.sort_values("date").reset_index(drop=True)
        # 50 and 100 daily EMA
        df["ema50"] = df["close"].ewm(span=50, adjust=False).mean()
        df["ema100"] = df["close"].ewm(span=100, adjust=False).mean()
        
        # Pre-Rally Radar Ignition Features:
        # 1. 20-day return between 0% and 35% (Base Consolidation, not late-stage overextended)
        # 2. Relative Volume >= 1.5x of 20-day average
        # 3. 5-day return > 0 (Ignition trigger)
        vol_mean = df["volume"].shift(1).rolling(20, min_periods=10).mean()
        df["rvol"] = df["volume"] / vol_mean.where(vol_mean > 0, 1.0)
        df["ret20"] = df["close"].pct_change(20)
        df["ret5"] = df["close"].pct_change(5)
        
        df["signal"] = (df["ret5"] > 0) & (df["ret20"] > 0) & (df["ret20"] <= 0.35) & (df["rvol"] >= 1.5)
        
        n = len(df)
        in_pos = False
        entry_p = 0.0
        entry_d = None
        peak_p = 0.0
        peak_d = None
        
        for i in range(n):
            row = df.iloc[i]
            if not in_pos:
                if row["signal"] and i + 1 < n:
                    next_row = df.iloc[i + 1]
                    # Fill Day t+1 Open (with 0.1% friction)
                    entry_p = next_row["open"] * 1.001
                    entry_d = next_row["date"]
                    peak_p = entry_p
                    peak_d = entry_d
                    in_pos = True
            else:
                # In Position: Track peak price
                if row["high"] > peak_p:
                    peak_p = row["high"]
                    peak_d = row["date"]
                
                gain_from_entry = (peak_p / entry_p - 1.0) * 100.0
                dip_from_peak = (row["close"] / peak_p - 1.0) * 100.0
                
                # Risk Rule 1: Immediate false breakout defense (-8% Hard Stop)
                # If stock fails right away before gaining +15%, cut loss at -8%
                if gain_from_entry < 15.0 and row["low"] <= entry_p * 0.92:
                    exit_p = min(entry_p * 0.92, row["open"]) * 0.999
                    days_held = (row["date"] - entry_d).days
                    campaigns.append({
                        "symbol": sym,
                        "entry_date": entry_d.strftime("%Y-%m-%d"),
                        "entry_price": entry_p,
                        "exit_date": row["date"].strftime("%Y-%m-%d"),
                        "exit_price": exit_p,
                        "peak_price": peak_p,
                        "peak_gain_pct": gain_from_entry,
                        "net_return_pct": (exit_p / entry_p - 1.0) * 100.0,
                        "days_held": days_held,
                        "exit_reason": "False Breakout (-8% Hard Stop)",
                        "status": "Closed"
                    })
                    in_pos = False
                
                # Risk Rule 2: Secular Trend Riding Rule
                # We HOLD as long as the multi-month/multi-year trend grows!
                # Only exit when:
                # 1. Stock has achieved significant growth (gain >= 30%) AND
                # 2. Price suffers a major structural breakdown (Close below 100 EMA and drops > 25% from peak)
                elif gain_from_entry >= 30.0 and (row["close"] < row["ema100"] and dip_from_peak <= -25.0):
                    exit_p = row["close"] * 0.999
                    days_held = (row["date"] - entry_d).days
                    campaigns.append({
                        "symbol": sym,
                        "entry_date": entry_d.strftime("%Y-%m-%d"),
                        "entry_price": entry_p,
                        "exit_date": row["date"].strftime("%Y-%m-%d"),
                        "exit_price": exit_p,
                        "peak_price": peak_p,
                        "peak_gain_pct": gain_from_entry,
                        "net_return_pct": (exit_p / entry_p - 1.0) * 100.0,
                        "days_held": days_held,
                        "exit_reason": "Secular Trend Ended (100 EMA Break & -25% Peak Retracement)",
                        "status": "Closed"
                    })
                    in_pos = False
                
                # Rule 3: Still Active and Growing Today (Terminal Bar)
                elif i == n - 1:
                    exit_p = row["close"] * 0.999
                    days_held = (row["date"] - entry_d).days
                    campaigns.append({
                        "symbol": sym,
                        "entry_date": entry_d.strftime("%Y-%m-%d"),
                        "entry_price": entry_p,
                        "exit_date": row["date"].strftime("%Y-%m-%d"),
                        "exit_price": exit_p,
                        "peak_price": peak_p,
                        "peak_gain_pct": gain_from_entry,
                        "net_return_pct": (exit_p / entry_p - 1.0) * 100.0,
                        "days_held": days_held,
                        "exit_reason": "ACTIVE WEALTH COMPOUNDER (Still Holding / Growing Today)",
                        "status": "Active"
                    })

    camp_df = pd.DataFrame(campaigns)
    print(f"Total Secular Campaigns across 57 symbols: {len(camp_df)}")
    print(f"Average Holding Duration: {camp_df['days_held'].mean():.0f} calendar days (~{camp_df['days_held'].mean()/365:.1f} years!)")
    
    # Win rate and Profit factor
    gains = camp_df.loc[camp_df["net_return_pct"] > 0, "net_return_pct"].sum()
    losses = abs(camp_df.loc[camp_df["net_return_pct"] <= 0, "net_return_pct"].sum())
    pf = gains / losses if losses > 0 else 999.0
    win_rate = (camp_df["net_return_pct"] > 0).mean() * 100.0
    avg_ret = camp_df["net_return_pct"].mean()
    
    print(f"Secular Strategy Win Rate: {win_rate:.1f}%")
    print(f"Secular Strategy Profit Factor: {pf:.2f}")
    print(f"Average Return per Campaign: +{avg_ret:.1f}%\n")

    # Sort by Net Return
    sorted_camps = camp_df.sort_values("net_return_pct", ascending=False).reset_index(drop=True)
    
    # Save CSV
    out_dir = Path("reports/secular_longterm_hold")
    out_dir.mkdir(parents=True, exist_ok=True)
    sorted_camps.to_csv(out_dir / "secular_multibagger_campaigns_2015_2026.csv", index=False)
    print(f"Saved secular campaigns ledger to {out_dir / 'secular_multibagger_campaigns_2015_2026.csv'}")

    return sorted_camps

if __name__ == "__main__":
    run_secular_model()
