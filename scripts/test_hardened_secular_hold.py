import pandas as pd
import numpy as np
from pathlib import Path

def test_engine():
    data_dir = Path("data/cache/historical_2010_2026")
    df_raw = pd.read_parquet(data_dir / "market_bars_2010_2026.parquet")
    df_raw = df_raw[(df_raw["date"] >= "2015-01-01") & (df_raw["date"] <= "2026-04-30")].copy()
    df_raw = df_raw.sort_values(["symbol", "date"]).reset_index(drop=True)

    campaigns = []
    for sym, df in df_raw.groupby("symbol"):
        df = df.copy().reset_index(drop=True)
        n = len(df)
        df["turnover"] = df["close"] * df["volume"]
        df["ret_5d"] = df["close"] / df["close"].shift(5) - 1.0
        df["ret_20d"] = df["close"] / df["close"].shift(20) - 1.0
        df["vol_20d_mean"] = df["volume"].rolling(20).mean()
        df["rvol"] = df["volume"] / df["vol_20d_mean"].replace(0, np.nan)
        df["ema100"] = df["close"].ewm(span=100, adjust=False).mean()

        signal = (
            (df["ret_5d"] > 0) &
            (df["ret_20d"] > 0.0) &
            (df["ret_20d"] <= 0.35) &
            (df["rvol"] >= 1.5) &
            (df["turnover"] >= 5_000_000)
        )
        df["signal"] = signal

        in_pos = False
        entry_p = 0.0
        entry_d = None
        peak_p = 0.0

        for i in range(n):
            row = df.iloc[i]
            if not in_pos:
                if row["signal"] and i + 1 < n:
                    next_row = df.iloc[i + 1]
                    # Check upper circuit on open
                    if next_row["open"] == next_row["high"] and next_row["high"] == next_row["low"]:
                        continue # Cannot enter locked circuit
                    entry_p = next_row["open"] * 1.001052 # 105.2 bps statutory round-trip / 2
                    entry_d = next_row["date"]
                    peak_p = entry_p
                    in_pos = True
            else:
                if row["high"] > peak_p:
                    peak_p = row["high"]
                
                gain_from_entry = (peak_p / entry_p - 1.0) * 100.0
                dip_from_peak = (row["close"] / peak_p - 1.0) * 100.0

                # 1. Hard Stop (-8%) if not yet reached +15%
                if gain_from_entry < 15.0 and row["low"] <= entry_p * 0.92:
                    exit_p = min(entry_p * 0.92, row["open"]) * (1.0 - 0.001052)
                    campaigns.append({
                        "symbol": sym, "entry_date": entry_d.strftime("%Y-%m-%d"), "entry_price": entry_p,
                        "exit_date": row["date"].strftime("%Y-%m-%d"), "exit_price": exit_p,
                        "peak_price": peak_p, "peak_gain_pct": gain_from_entry,
                        "net_return_pct": (exit_p / entry_p - 1.0) * 100.0,
                        "days_held": (row["date"] - entry_d).days,
                        "exit_reason": "False Breakout (-8% Hard Stop)", "status": "Closed"
                    })
                    in_pos = False

                # 2. Breakeven Shield if gain reached 15% but not 30%
                elif 15.0 <= gain_from_entry < 30.0 and row["low"] <= entry_p * 1.002:
                    exit_p = min(entry_p * 1.002, row["open"]) * (1.0 - 0.001052)
                    campaigns.append({
                        "symbol": sym, "entry_date": entry_d.strftime("%Y-%m-%d"), "entry_price": entry_p,
                        "exit_date": row["date"].strftime("%Y-%m-%d"), "exit_price": exit_p,
                        "peak_price": peak_p, "peak_gain_pct": gain_from_entry,
                        "net_return_pct": (exit_p / entry_p - 1.0) * 100.0,
                        "days_held": (row["date"] - entry_d).days,
                        "exit_reason": "Breakeven Shield (+0% Retracement)", "status": "Closed"
                    })
                    in_pos = False

                # 3. Secular Trend Exit for proven winners (>= 30% gain): 100 EMA break & -20% from peak
                elif gain_from_entry >= 30.0 and (row["close"] < row["ema100"] and dip_from_peak <= -20.0):
                    exit_p = row["close"] * (1.0 - 0.001052)
                    campaigns.append({
                        "symbol": sym, "entry_date": entry_d.strftime("%Y-%m-%d"), "entry_price": entry_p,
                        "exit_date": row["date"].strftime("%Y-%m-%d"), "exit_price": exit_p,
                        "peak_price": peak_p, "peak_gain_pct": gain_from_entry,
                        "net_return_pct": (exit_p / entry_p - 1.0) * 100.0,
                        "days_held": (row["date"] - entry_d).days,
                        "exit_reason": "Secular Trend Ended (100 EMA Break & -20% Pullback)", "status": "Closed"
                    })
                    in_pos = False

                # 4. Terminal date: Still Active Compounder
                elif i == n - 1:
                    exit_p = row["close"] * (1.0 - 0.001052)
                    campaigns.append({
                        "symbol": sym, "entry_date": entry_d.strftime("%Y-%m-%d"), "entry_price": entry_p,
                        "exit_date": row["date"].strftime("%Y-%m-%d"), "exit_price": exit_p,
                        "peak_price": peak_p, "peak_gain_pct": gain_from_entry,
                        "net_return_pct": (exit_p / entry_p - 1.0) * 100.0,
                        "days_held": (row["date"] - entry_d).days,
                        "exit_reason": "ACTIVE WEALTH COMPOUNDER (Still Holding Today)", "status": "Active"
                    })

    cdf = pd.DataFrame(campaigns)
    gains = cdf.loc[cdf["net_return_pct"] > 0, "net_return_pct"].sum()
    losses = abs(cdf.loc[cdf["net_return_pct"] <= 0, "net_return_pct"].sum())
    pf = gains / losses if losses > 0 else 999.0
    print(f"Total Campaigns: {len(cdf)}")
    print(f"Profit Factor: {pf:.2f}")
    print(f"Win Rate: {(cdf['net_return_pct'] > 0).mean()*100:.1f}%")
    print(f"Average Return per Campaign: +{cdf['net_return_pct'].mean():.1f}%")
    print(f"Average Days Held: {cdf['days_held'].mean():.0f} days (~{cdf['days_held'].mean()/365:.1f} years)")

    print("\nCheck Bankrupt stocks:")
    bankrupt = ["YESBANK", "IDEA", "JETAIRWAYS", "UNITECH", "RCOM"]
    b_df = cdf[cdf["symbol"].isin(bankrupt)]
    print(b_df[["symbol", "entry_date", "exit_date", "net_return_pct", "exit_reason", "status"]].to_string())

    print("\nTop 10 Multibaggers:")
    top10 = cdf.sort_values("net_return_pct", ascending=False).head(10)
    for _, r in top10.iterrows():
        mult = 1.0 + r["net_return_pct"] / 100.0
        print(f"{r['symbol']:12} | {r['entry_date']} -> {r['exit_date']} | {r['days_held']}d ({r['days_held']/365:.1f}y) | Net: +{r['net_return_pct']:,.1f}% ({mult:.1f}x) | Status: {r['status']}")

if __name__ == "__main__":
    test_engine()
