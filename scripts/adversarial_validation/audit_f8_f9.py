"""Diagnostic for F8 (Cross-document numerical inconsistencies) and F9 (Live book bugs)."""
import pandas as pd
import numpy as np

# Load trade parquet and year summary CSV
trades = pd.read_parquet("reports/trend_multibagger_backtest/all_trend_multibagger_trades_2015_2026.parquet")
yr_df = pd.read_csv("reports/trend_multibagger_backtest/year_by_year_trend_summary_2015_2026.csv")

print("=" * 80)
print("AUDIT F8: NUMERICAL RECONCILIATION")
print("=" * 80)

print(f"Total trades in parquet: {len(trades)}")

# 1. Exit reasons
print("\n[1] Trades by Exit Reason:")
exit_counts = trades["exit_reason"].value_counts()
print(exit_counts)
print(f"Sum of exit reasons: {exit_counts.sum()}")

# 2. Return Brackets (Realized Net Return)
print("\n[2] Trades by Realized Net Return Brackets:")
b_loss = (trades["net_return_pct"] <= 0).sum()
b_0_20 = ((trades["net_return_pct"] > 0) & (trades["net_return_pct"] < 20)).sum()
b_20_50 = ((trades["net_return_pct"] >= 20) & (trades["net_return_pct"] < 50)).sum()
b_50_100 = ((trades["net_return_pct"] >= 50) & (trades["net_return_pct"] < 100)).sum()
b_100_200 = ((trades["net_return_pct"] >= 100) & (trades["net_return_pct"] < 200)).sum()
b_200_plus = (trades["net_return_pct"] >= 200).sum()

print(f"<= 0% (Losses): {b_loss}")
print(f"0% - 20%:       {b_0_20}")
print(f"20% - 50%:      {b_20_50}")
print(f"50% - 100%:     {b_50_100}")
print(f"100% - 200%:    {b_100_200}")
print(f">= 200%:        {b_200_plus}")
print(f"Sum of return brackets: {b_loss + b_0_20 + b_20_50 + b_50_100 + b_100_200 + b_200_plus}")

# Explain where the 1,897 came from
claimed_in_review = 833 + 158 + 381 + 353 + 130 + 29 + 13
print(f"\nDesk Review Sum: 833 (stop) + 158 (be) + 381 (stag) + 353 (0-20) + 130 (20-50) + 29 (100-200) + 13 (>=200) = {claimed_in_review}")
print("-> Explanatory Finding: Desk review mixed 3 exit reasons (833+158+381=1372) with 4 return brackets (353+130+29+13=525), omitting 50-100% bracket (50 trades) and other exit reasons (356 trades)!")

# 3. Multibaggers >= 2x (+100%) and >= 3x (+200%)
print("\n[3] Reconciling >= 2x and >= 3x Counts:")
realized_2x = (trades["net_return_pct"] >= 100.0).sum()
peak_2x = (trades["peak_gain_pct"] >= 100.0).sum()
realized_3x = (trades["net_return_pct"] >= 200.0).sum()
peak_3x = (trades["peak_gain_pct"] >= 200.0).sum()

print(f"Realized >= 2x (+100% net): {realized_2x}")
print(f"Peak (MFE) >= 2x (+100% peak): {peak_2x}")
print(f"Realized >= 3x (+200% net): {realized_3x}")
print(f"Peak (MFE) >= 3x (+200% peak): {peak_3x}")

yr_realized_2x = yr_df["realized_ge_100pct"].sum()
yr_peak_2x = yr_df["rallies_ge_100pct"].sum()
yr_peak_3x = yr_df["rallies_ge_200pct"].sum()
print(f"Year-by-year CSV sums: realized >= 2x: {yr_realized_2x}, peak >= 2x: {yr_peak_2x}, peak >= 3x: {yr_peak_3x}")

# 4. Check Phase Table sums
phases = [
    ("Phase 1: 2015-2017", 2015, 2017),
    ("Phase 2: 2018-2020", 2018, 2020),
    ("Phase 3: 2021-2023", 2021, 2023),
    ("Phase 4: 2024-2026", 2024, 2026),
]
print("\nPhase Counts from raw trades:")
for p_name, s, e in phases:
    sub = trades[(trades["entry_year"] >= s) & (trades["entry_year"] <= e)]
    p_real_2x = (sub["net_return_pct"] >= 100.0).sum()
    p_peak_2x = (sub["peak_gain_pct"] >= 100.0).sum()
    p_peak_3x = (sub["peak_gain_pct"] >= 200.0).sum()
    p_real_3x = (sub["net_return_pct"] >= 200.0).sum()
    print(f"  {p_name}: Peak 2x = {p_peak_2x}, Realized 2x = {p_real_2x} | Peak 3x = {p_peak_3x}, Realized 3x = {p_real_3x}")

# 5. Suzlon Day 60 gain discrepancy
bars = pd.read_parquet("data/cache/historical_2015_2026/market_bars_2015_2026.parquet")
suz_bars = bars[bars['symbol'].str.contains('SUZLON')].sort_values('date').reset_index(drop=True)
suz_bars['date_str'] = suz_bars['date'].dt.strftime('%Y-%m-%d')
suz_tr = trades[(trades['symbol']=='SUZLON') & (trades['entry_year']==2023)].iloc[0]
e_dt = suz_tr['entry_date_dt']
future_suz = suz_bars[suz_bars['date'] >= e_dt].reset_index(drop=True)
if len(future_suz) >= 60:
    c60 = future_suz.iloc[59]['close']
    h60 = future_suz.iloc[:60]['high'].max()
    print(f"\nSuzlon 2023 Trigger Day 60:")
    print(f"  Entry price: {suz_tr['entry_price']:.2f}")
    print(f"  Day 60 close: {c60:.2f} -> Close-to-Entry return: {(c60/suz_tr['entry_price'] - 1)*100:.1f}%")
    print(f"  Day 60 peak high: {h60:.2f} -> Peak MFE return: {(h60/suz_tr['entry_price'] - 1)*100:.1f}%")
    print("  -> Discrepancy explained: One report quoted close-to-close at day 60 (+126.3%), while the other quoted peak high MFE (+137.2%)!")

print("\n" + "=" * 80)
print("AUDIT F9: LIVE BOOK / RUNNING TRADES AUDIT")
print("=" * 80)

running = trades[trades["exit_reason"] == "STILL_RUNNING_TODAY"].copy()
print(f"Total Still Running trades: {len(running)}")

# Check for peak < current return
bad_peak = running[running["peak_gain_pct"] < running["net_return_pct"]]
print(f"Trades where peak_gain < net_return: {len(bad_peak)}")
for _, r in bad_peak.iterrows():
    print(f"  BUG DETECTED: {r['symbol']} entry {r['entry_date_dt'].strftime('%Y-%m-%d')}: net_return = {r['net_return_pct']:.2f}%, peak_gain = {r['peak_gain_pct']:.2f}%")

# Check Siemens trailing exit
sie_tr = running[running["symbol"] == "SIEMENS"]
if not sie_tr.empty:
    r = sie_tr.iloc[0]
    print(f"\nSIEMENS Analysis:")
    print(f"  Entry: {r['entry_date_dt'].strftime('%Y-%m-%d')} @ {r['entry_price']:.2f}")
    print(f"  Peak price: {r['peak_price']:.2f} (+{r['peak_gain_pct']:.2f}%)")
    print(f"  Exit/Current price: {r['exit_price']:.2f} (+{r['net_return_pct']:.2f}%)")
    print(f"  Dip from peak: {(r['exit_price']/r['peak_price'] - 1)*100:.2f}%")
    print(f"  Trailing buffer required for peak >= 25%: -14%")
    print(f"  Dip is {(r['exit_price']/r['peak_price'] - 1)*100:.2f}% <= -14%: SHOULD HAVE TRIGGERED TRAILING EXIT!")
