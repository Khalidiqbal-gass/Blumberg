import pandas as pd
from run_2020_detailed_audit import run_2020_backtest

res_r = run_2020_backtest(apply_regime=True)
res_nr = run_2020_backtest(apply_regime=False)

print("=" * 80)
print("2020 FULL YEAR BACKTEST REPORT (COVID YEAR: CRASH + EPIC RALLY)")
print("=" * 80)

for label, res in [("1. WITH 200-EMA REGIME FILTER (Conservative Mode)", res_r),
                   ("2. WITHOUT REGIME FILTER (Full Momentum Radar Mode)", res_nr)]:
    print(f"\n--- {label} ---")
    tdf = res["trades_df"]
    win_m = tdf["outcome"] == "WIN"
    loss_m = tdf["outcome"] == "LOSS"
    win_pnl = tdf[win_m]["net_pnl"].sum()
    loss_pnl = tdf[loss_m]["net_pnl"].sum()

    print(f"Starting Capital:     Rs {res['start_equity']:,.2f}")
    print(f"Ending Capital:       Rs {res['end_equity']:,.2f}")
    print(f"Net Profit (1 Year):  Rs {res['net_pnl']:,.2f} (+{res['net_return_pct']:.2f}%)")
    print(f"Max Covid Drawdown:   {res['max_drawdown']:.2f}% (vs Sensex Crash: -39.35%)")
    print(f"Total Trades Taken:   {len(tdf)}")
    print(f"Good Stocks (Winners): {win_m.sum()} ({res['win_rate_pct']:.1f}% win rate)")
    print(f"False Stocks (Losers): {loss_m.sum()} (Failed Breakouts)")
    print(f"Total Money Won:      +Rs {win_pnl:,.2f} (Avg Win: +{res['avg_win_pct']:.1f}%)")
    print(f"Total Money Lost:     -Rs {abs(loss_pnl):,.2f} (Avg Loss: {res['avg_loss_pct']:.1f}%)")
    print(f"Losses Cut in Half:   {res['halved_loss_count']} Trades (Tranche 2 never added!)")
    print(f"2x+ Multibaggers:     {res['multibaggers_2x']} Stocks")

    print("\nTop 8 Winners Caught:")
    top_w = tdf.sort_values("net_return_pct", ascending=False).head(8)
    for _, r in top_w.iterrows():
        t2_str = "Yes (Full)" if r["tranche2_added"] else "No (Half)"
        print(f"  + {r['symbol']:12} | Entry: {r['entry_date']} -> Exit: {r['exit_date']} | Held: {r['days_held']:3d}d | T2: {t2_str:9} | Net: +{r['net_return_pct']:5.1f}% | Profit: +Rs {r['net_pnl']:9,.2f} | {r['exit_reason']}")

    print("\nWorst 8 False Stocks (Failed Breakouts):")
    worst_l = tdf.sort_values("net_return_pct", ascending=True).head(8)
    for _, r in worst_l.iterrows():
        t2_str = "Yes (Full)" if r["tranche2_added"] else "No (Half)"
        print(f"  - {r['symbol']:12} | Entry: {r['entry_date']} -> Exit: {r['exit_date']} | Held: {r['days_held']:3d}d | T2: {t2_str:9} | Net: {r['net_return_pct']:5.1f}% | Loss: Rs {r['net_pnl']:9,.2f} | {r['exit_reason']}")
