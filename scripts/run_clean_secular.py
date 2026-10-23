import pandas as pd
import numpy as np

def run_clean_secular():
    bars = pd.read_parquet("data/cache/historical_2015_2026/market_bars_2015_2026.parquet")
    bars["date"] = pd.to_datetime(bars["date"], utc=True)
    bars["clean_sym"] = bars["symbol"].str.replace(".NS", "").str.replace(".BO", "")

    bankrupt_bars = pd.read_parquet("data/cache/historical_2015_2026/bankrupt_bars_2015_2026.parquet")
    bankrupt_bars["date"] = pd.to_datetime(bankrupt_bars["date"], utc=True)

    all_bars = pd.concat([bars, bankrupt_bars], ignore_index=True).sort_values(["clean_sym", "date"]).reset_index(drop=True)

    campaigns = []
    statutory_cost = 0.001052 # 105.2 bps round-trip / 2 = 52.6 bps per side

    for sym, grp in all_bars.groupby("clean_sym"):
        df = grp.sort_values("date").reset_index(drop=True)
        df["ema100"] = df["close"].ewm(span=100, adjust=False).mean()

        vol_mean = df["volume"].shift(1).rolling(20, min_periods=10).mean()
        df["rvol"] = df["volume"] / vol_mean.where(vol_mean > 0, 1.0)
        df["ret20"] = df["close"].pct_change(20)
        df["ret5"] = df["close"].pct_change(5)

        df["signal"] = (
            (df["ret5"] > 0) &
            (df["ret20"] > 0) &
            (df["ret20"] <= 0.35) &
            (df["rvol"] >= 1.5)
        )

        n = len(df)
        in_pos = False
        entry_p = 0.0
        entry_d = None
        peak_p = 0.0

        for i in range(n):
            row = df.iloc[i]
            if not in_pos:
                if row["signal"] and i + 1 < n:
                    next_row = df.iloc[i + 1]
                    # Check upper circuit lock
                    if next_row["open"] == next_row["high"] and next_row["high"] == next_row["low"]:
                        continue
                    entry_p = next_row["open"] * (1.0 + statutory_cost)
                    entry_d = next_row["date"]
                    peak_p = entry_p
                    in_pos = True
            else:
                if row["high"] > peak_p:
                    peak_p = row["high"]
                
                gain_from_entry = (peak_p / entry_p - 1.0) * 100.0
                dip_from_peak = (row["close"] / peak_p - 1.0) * 100.0

                # Stage 1: Hard Stop (-8%) for early unproven setups
                if gain_from_entry < 15.0 and row["low"] <= entry_p * 0.92:
                    exit_p = min(entry_p * 0.92, row["open"]) * (1.0 - statutory_cost)
                    campaigns.append({
                        "symbol": sym, "entry_date": entry_d.strftime("%Y-%m-%d"), "entry_price": entry_p,
                        "exit_date": row["date"].strftime("%Y-%m-%d"), "exit_price": exit_p,
                        "peak_price": peak_p, "peak_gain_pct": gain_from_entry,
                        "net_return_pct": (exit_p / entry_p - 1.0) * 100.0,
                        "days_held": (row["date"] - entry_d).days,
                        "exit_reason": "False Breakout (-8% Hard Stop)", "status": "Closed"
                    })
                    in_pos = False

                # Stage 2: Breakeven Defense (+15% reached, protects capital if reverses)
                elif 15.0 <= gain_from_entry < 30.0 and row["low"] <= entry_p * 1.002:
                    exit_p = min(entry_p * 1.002, row["open"]) * (1.0 - statutory_cost)
                    campaigns.append({
                        "symbol": sym, "entry_date": entry_d.strftime("%Y-%m-%d"), "entry_price": entry_p,
                        "exit_date": row["date"].strftime("%Y-%m-%d"), "exit_price": exit_p,
                        "peak_price": peak_p, "peak_gain_pct": gain_from_entry,
                        "net_return_pct": (exit_p / entry_p - 1.0) * 100.0,
                        "days_held": (row["date"] - entry_d).days,
                        "exit_reason": "Breakeven Shield (+0% Retracement)", "status": "Closed"
                    })
                    in_pos = False

                # Stage 3: Secular Trend Riding (>=30% gain): Exit ONLY if 100 EMA breaks AND pullback > 25% from peak
                elif gain_from_entry >= 30.0 and (row["close"] < row["ema100"] and dip_from_peak <= -25.0):
                    exit_p = row["close"] * (1.0 - statutory_cost)
                    campaigns.append({
                        "symbol": sym, "entry_date": entry_d.strftime("%Y-%m-%d"), "entry_price": entry_p,
                        "exit_date": row["date"].strftime("%Y-%m-%d"), "exit_price": exit_p,
                        "peak_price": peak_p, "peak_gain_pct": gain_from_entry,
                        "net_return_pct": (exit_p / entry_p - 1.0) * 100.0,
                        "days_held": (row["date"] - entry_d).days,
                        "exit_reason": "Secular Trend Ended (100 EMA Break & -25% Peak Drop)", "status": "Closed"
                    })
                    in_pos = False

                # Terminal Bar: Still Active Wealth Compounder
                elif i == n - 1:
                    exit_p = row["close"] * (1.0 - statutory_cost)
                    campaigns.append({
                        "symbol": sym, "entry_date": entry_d.strftime("%Y-%m-%d"), "entry_price": entry_p,
                        "exit_date": row["date"].strftime("%Y-%m-%d"), "exit_price": exit_p,
                        "peak_price": peak_p, "peak_gain_pct": gain_from_entry,
                        "net_return_pct": (exit_p / entry_p - 1.0) * 100.0,
                        "days_held": (row["date"] - entry_d).days,
                        "exit_reason": "ACTIVE WEALTH COMPOUNDER (Still Holding / Growing Today)", "status": "Active"
                    })

    cdf = pd.DataFrame(campaigns)
    gains = cdf.loc[cdf["net_return_pct"] > 0, "net_return_pct"].sum()
    losses = abs(cdf.loc[cdf["net_return_pct"] <= 0, "net_return_pct"].sum())
    pf = gains / losses if losses > 0 else 999.0

    print("=" * 80)
    print("CLEAN SECULAR HOLD ENGINE RESULTS")
    print("=" * 80)
    print(f"Total Campaigns: {len(cdf)}")
    print(f"Profit Factor: {pf:.2f}")
    print(f"Win Rate: {(cdf['net_return_pct'] > 0).mean()*100:.1f}%")
    print(f"Average Return per Campaign: +{cdf['net_return_pct'].mean():.1f}%")
    print(f"Average Holding Duration: {cdf['days_held'].mean():.0f} days (~{cdf['days_held'].mean()/365:.1f} years)")

    print("\n--- Bankrupt / Stressed Stocks Audit ---")
    bankrupt = ["YESBANK", "IDEA", "JETAIRWAYS", "UNITECH", "RCOM"]
    b_df = cdf[cdf["symbol"].isin(bankrupt)]
    print(b_df[["symbol", "entry_date", "exit_date", "days_held", "net_return_pct", "exit_reason", "status"]].to_string())

    print("\n--- Top 15 Multibaggers ---")
    top15 = cdf.sort_values("net_return_pct", ascending=False).head(15)
    for _, r in top15.iterrows():
        mult = 1.0 + r["net_return_pct"] / 100.0
        print(f"{r['symbol']:12} | {r['entry_date']} -> {r['exit_date']} | {r['days_held']:4d}d ({r['days_held']/365:.1f}y) | Net: +{r['net_return_pct']:,.1f}% ({mult:.1f}x) | Status: {r['status']}")

    print("\n--- Active Positions (Holding Today) ---")
    active = cdf[cdf["status"] == "Active"].sort_values("net_return_pct", ascending=False)
    print(f"Total Active Positions Today: {len(active)}")
    for _, r in active.head(10).iterrows():
        print(f"{r['symbol']:12} | Entry: {r['entry_date']} @ {r['entry_price']:.1f} | Current: Rs {r['exit_price']:.1f} | {r['days_held']:4d}d | Net: +{r['net_return_pct']:,.1f}%")

    # Save to CSV
    cdf.to_csv("reports/secular_longterm_hold/secular_multibagger_campaigns_2015_2026.csv", index=False)
    print("\nSuccessfully saved updated ledger to reports/secular_longterm_hold/secular_multibagger_campaigns_2015_2026.csv")

if __name__ == "__main__":
    run_clean_secular()
