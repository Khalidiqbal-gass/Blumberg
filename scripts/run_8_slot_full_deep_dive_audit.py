"""
Master 8-Slot Quantitative Audit Suite (2000 - 2026).

Computes:
1. Complete 26-Year Profit/Loss Metrics:
   - Total Trades, Wins, Losses, SL Hits Count
   - Total Gross Profit (Rs), Total Gross Loss (Rs), Net Realized PnL (Rs)
   - Exit Reason Attribution Breakdown
2. Stock-by-Stock Comprehensive Attribution (All Equities):
   - Win/Loss counts, Win Rate %, Net PnL (Rs), Cumulative Multiple, Best/Worst Trade
3. Year-by-Year Calendar Breakdown (2000 to 2026):
   - Annual Return %, Benchmark (Sensex) Return %, Intra-Year Max DD %, Trades, Win Rate, Realized PnL
4. 11 Historical Multi-Timelines / Eras Breakdown
"""
from __future__ import annotations

import sys
from pathlib import Path
import numpy as np
import pandas as pd

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from blumberg_market_radar.backtest.upgraded_vcp_engine import UpgradedVCPBacktestEngine

REPORT_DIR = PROJECT_ROOT / "reports" / "8_slot_audit"
DESKTOP_DIR = Path(r"C:\Users\DELL\OneDrive\Desktop\BLUMBERG_AUDIT_FILES\8_SLOT_AUDIT")
REPORT_DIR.mkdir(parents=True, exist_ok=True)
DESKTOP_DIR.mkdir(parents=True, exist_ok=True)

DATA_CACHE = PROJECT_ROOT / "data" / "cache" / "historical_2000_2026"
BARS_PARQUET = DATA_CACHE / "market_bars_with_delisted_2000_2026.parquet"
BENCH_PARQUET = DATA_CACHE / "sensex_bench_2000_2026.parquet"


def main():
    print("=" * 115)
    print("   BLUMBERG QUANTITATIVE SYSTEM â€” 8-SLOT SWEET SPOT DEEP DIVE AUDIT (2000 - 2026)")
    print("=" * 115)

    if not BARS_PARQUET.exists() or not BENCH_PARQUET.exists():
        print("[ERROR] Parquet files not found in cache.")
        return

    bars_df = pd.read_parquet(BARS_PARQUET)
    bench_df = pd.read_parquet(BENCH_PARQUET)
    print(f"Loaded {len(bars_df):,} bars across {bars_df['symbol'].nunique()} equities up to {bars_df['date'].max()}.\n")

    # Initialize 8-Slot Engine (Conservative 102.6 bps transaction drag per Claude patch)
    engine_8 = UpgradedVCPBacktestEngine(
        initial_capital=1_000_000.0,
        max_slots=8,
        mode="HYBRID_50_50",
        min_turnover_rs=30_000_000.0,
        slippage_bps_per_side=50.0,
        statutory_bps_per_side=52.6,
        use_equal_weight_slots=True,
        cash_yield_pct_p_a=6.5,
        use_sector_leadership=False,
        tranche2_days=7,
    )

    print("Executing Master 26.8-Year Arc (2000-01-01 to 2026-10-26)...")
    res_26 = engine_8.run_backtest(bars_df, bench_df, start_date="2000-01-01", end_date="2026-10-26")

    trades_df = res_26.trades_df.copy()
    equity_df = res_26.equity_curve.copy()

    # Save raw trades and equity
    trades_df.to_csv(REPORT_DIR / "8_slot_trades_2000_2026.csv", index=False)
    trades_df.to_csv(DESKTOP_DIR / "8_slot_trades_2000_2026.csv", index=False)
    equity_df.to_csv(REPORT_DIR / "8_slot_equity_2000_2026.csv", index=False)
    equity_df.to_csv(DESKTOP_DIR / "8_slot_equity_2000_2026.csv", index=False)

    # =========================================================================
    # PART 1: OVERALL PROFIT & LOSS / STOP-LOSS HIT SUMMARY
    # =========================================================================
    total_trades = len(trades_df)
    win_trades = trades_df[trades_df["net_return_pct"] > 0]
    loss_trades = trades_df[trades_df["net_return_pct"] <= 0]

    wins_count = len(win_trades)
    loss_count = len(loss_trades)
    win_rate = (wins_count / total_trades) * 100.0 if total_trades > 0 else 0.0

    gross_profit_rs = win_trades["pnl_amount"].sum()
    gross_loss_rs = loss_trades["pnl_amount"].sum()  # Negative number
    net_pnl_rs = trades_df["pnl_amount"].sum()
    profit_factor = abs(gross_profit_rs / gross_loss_rs) if gross_loss_rs != 0 else np.nan

    # Categorize Exits / Stop-Loss Hits
    hard_sl = trades_df[trades_df["exit_reason"].str.contains("Circuit Breaker|-10% Hard Stop", case=False, na=False)]
    closing_sl = trades_df[trades_df["exit_reason"].str.contains("Closing Stop|-8%", case=False, na=False)]
    dead_money_sl = trades_df[trades_df["exit_reason"].str.contains("Dead Money", case=False, na=False)]
    stage2_be = trades_df[trades_df["stage_at_exit"].str.contains("Stage 2", case=False, na=False)]
    stage3_ratchet = trades_df[trades_df["stage_at_exit"].str.contains("Stage 3", case=False, na=False)]
    stage4_secular = trades_df[trades_df["stage_at_exit"].str.contains("Stage 4", case=False, na=False)]
    stage5_climax = trades_df[trades_df["stage_at_exit"].str.contains("Stage 5", case=False, na=False)]

    total_sl_hits = len(hard_sl) + len(closing_sl) + len(dead_money_sl)
    total_trailing_exits = len(stage2_be) + len(stage3_ratchet) + len(stage4_secular) + len(stage5_climax)

    print("\n" + "=" * 115)
    print("1. MASTER 26-YEAR STOP-LOSS & PnL SUMMARY (8-SLOT MODEL: 2000 - 2026)")
    print("=" * 115)
    print(f"Starting Capital:              Rs 1,000,000.00 (Rs 10 Lakhs)")
    print(f"Final Capital:                 Rs {res_26.final_capital:,.2f}  ({res_26.final_capital/res_26.initial_capital:.2f}x Multiple)")
    print(f"Net Compounded CAGR:           +{res_26.compounded_cagr_pct:.2f}%")
    print(f"Maximum Portfolio Drawdown:    {res_26.max_drawdown_pct:.2f}%")
    print(f"Total Friction Paid (Taxes/Slip): Rs {res_26.total_friction_paid:,.2f}")
    print("-" * 115)
    print(f"Total Completed Trades:        {total_trades}")
    print(f"  â€¢ Winning Trades:            {wins_count:>4} ({win_rate:.2f}%)   --> Total Gross Profit: +Rs {gross_profit_rs:,.2f}")
    print(f"  â€¢ Losing Trades (Total):     {loss_count:>4} ({100-win_rate:.2f}%) --> Total Gross Loss:   -Rs {abs(gross_loss_rs):,.2f}")
    print(f"  â€¢ Net Realized Trading PnL:                                     --> Net Realized PnL:  +Rs {net_pnl_rs:,.2f}")
    print(f"Profit Factor (Gross Gain / Loss): {profit_factor:.2f}x")
    print("-" * 115)
    print("EXIT MECHANISM & STOP-LOSS BREAKDOWN:")
    print(f"  ðŸ›‘ Hard Stops (-10% Circuit Breaker):   {len(hard_sl):>4} trades | Total Loss: -Rs {abs(hard_sl['pnl_amount'].sum()):,.2f} | Avg Loss: {hard_sl['net_return_pct'].mean():.2f}%")
    print(f"  âš ï¸  Closing Stops (-8% Threshold):       {len(closing_sl):>4} trades | Total Loss: -Rs {abs(closing_sl['pnl_amount'].sum()):,.2f} | Avg Loss: {closing_sl['net_return_pct'].mean():.2f}%")
    print(f"  â³ Dead-Money Stops (30d Stagnant):     {len(dead_money_sl):>4} trades | Total Loss: -Rs {abs(dead_money_sl['pnl_amount'].sum()):,.2f} | Avg Ret:  {dead_money_sl['net_return_pct'].mean():.2f}%")
    print(f"  -------------------------------------------------------------")
    print(f"  ðŸ”´ TOTAL STOP-LOSS HITS:               {total_sl_hits:>4} trades ({total_sl_hits/total_trades*100:.1f}% of all trades)")
    print(f"  -------------------------------------------------------------")
    print(f"  ðŸ›¡ï¸  Stage 2 Breakeven (+2% Floor Locked):{len(stage2_be):>4} trades | Total PnL:  +Rs {stage2_be['pnl_amount'].sum():,.2f}")
    print(f"  ðŸ“ˆ Stage 3 Ratchet (+12% Floor Locked): {len(stage3_ratchet):>4} trades | Total PnL:  +Rs {stage3_ratchet['pnl_amount'].sum():,.2f}")
    print(f"  ðŸš€ Stage 4 Secular (+25% Floor Locked): {len(stage4_secular):>4} trades | Total PnL:  +Rs {stage4_secular['pnl_amount'].sum():,.2f}")
    print(f"  ðŸ† Stage 5 Climax (Parabolic Blow-off): {len(stage5_climax):>4} trades | Total PnL:  +Rs {stage5_climax['pnl_amount'].sum():,.2f}")
    print(f"  -------------------------------------------------------------")
    print(f"  ðŸŸ¢ TOTAL PROFIT-FLOOR TRAIL EXITS:     {total_trailing_exits:>4} trades ({total_trailing_exits/total_trades*100:.1f}% of all trades)")

    summary_metric_df = pd.DataFrame([{
        "Metric": "8-Slot Master Backtest (2000-2026)",
        "Starting_Capital_Rs": res_26.initial_capital,
        "Final_Capital_Rs": round(res_26.final_capital, 2),
        "Multiple": round(res_26.final_capital / res_26.initial_capital, 2),
        "CAGR_Pct": round(res_26.compounded_cagr_pct, 2),
        "Max_Drawdown_Pct": round(res_26.max_drawdown_pct, 2),
        "Total_Trades": total_trades,
        "Winning_Trades": wins_count,
        "Losing_Trades": loss_count,
        "Win_Rate_Pct": round(win_rate, 2),
        "Gross_Profit_Rs": round(gross_profit_rs, 2),
        "Gross_Loss_Rs": round(gross_loss_rs, 2),
        "Net_Realized_PnL_Rs": round(net_pnl_rs, 2),
        "Total_Friction_Paid_Rs": round(res_26.total_friction_paid, 2),
        "Total_SL_Hits": total_sl_hits,
        "Hard_Stop_Hits": len(hard_sl),
        "Closing_Stop_Hits": len(closing_sl),
        "Dead_Money_Hits": len(dead_money_sl),
        "Trailing_Floor_Exits": total_trailing_exits,
    }])
    summary_metric_df.to_csv(REPORT_DIR / "8_SLOT_TOTAL_PROFIT_LOSS_SUMMARY.csv", index=False)
    summary_metric_df.to_csv(DESKTOP_DIR / "8_SLOT_TOTAL_PROFIT_LOSS_SUMMARY.csv", index=False)

    # =========================================================================
    # PART 2: STOCK-BY-STOCK COMPLETE PROFIT VS LOSS ATTRIBUTION
    # =========================================================================
    print("\n" + "=" * 115)
    print("2. STOCK-BY-STOCK PROFIT VS LOSS ATTRIBUTION (ALL EQUITIES)")
    print("=" * 115)

    stock_records = []
    for sym, grp in trades_df.groupby("symbol"):
        tot = len(grp)
        w_df = grp[grp["net_return_pct"] > 0]
        l_df = grp[grp["net_return_pct"] <= 0]
        w_cnt = len(w_df)
        l_cnt = len(l_df)
        sl_hits = len(grp[grp["exit_reason"].str.contains("Stop|Circuit Breaker|Dead Money", case=False, na=False)])
        
        g_prof = w_df["pnl_amount"].sum()
        g_loss = l_df["pnl_amount"].sum()
        tot_pnl = grp["pnl_amount"].sum()
        best_g = grp["net_return_pct"].max()
        worst_l = grp["net_return_pct"].min()
        cum_mult = (1.0 + grp["net_return_pct"] / 100.0).prod()
        sec = grp["sector"].iloc[0] if "sector" in grp.columns else "Diversified"

        stock_records.append({
            "Symbol": sym,
            "Sector": sec,
            "Total_Trades": tot,
            "Wins": w_cnt,
            "Losses": l_cnt,
            "SL_Hits": sl_hits,
            "Win_Rate_%": round(w_cnt / tot * 100.0, 1),
            "Gross_Profit_Rs": round(g_prof, 2),
            "Gross_Loss_Rs": round(g_loss, 2),
            "Net_PnL_Rs": round(tot_pnl, 2),
            "Cumulative_Multiple": round(cum_mult, 2),
            "Best_Trade_%": round(best_g, 1),
            "Worst_Trade_%": round(worst_l, 1),
            "Status": "PROFITABLE" if tot_pnl > 0 else "LOSS-MAKING",
        })

    stk_df = pd.DataFrame(stock_records).sort_values("Net_PnL_Rs", ascending=False).reset_index(drop=True)
    stk_df.to_csv(REPORT_DIR / "8_SLOT_ALL_STOCKS_PROFIT_LOSS_LEDGER.csv", index=False)
    stk_df.to_csv(DESKTOP_DIR / "8_SLOT_ALL_STOCKS_PROFIT_LOSS_LEDGER.csv", index=False)

    profitable_stocks = stk_df[stk_df["Net_PnL_Rs"] > 0]
    losing_stocks = stk_df[stk_df["Net_PnL_Rs"] <= 0]

    print(f"Total Unique Stocks Traded:    {len(stk_df)}")
    print(f"  â€¢ Net Profitable Stocks:     {len(profitable_stocks)} ({len(profitable_stocks)/len(stk_df)*100:.1f}%)")
    print(f"  â€¢ Net Loss-Making Stocks:    {len(losing_stocks)} ({len(losing_stocks)/len(stk_df)*100:.1f}%)")
    print("\n--- TOP 10 HIGHEST PROFIT-GENERATING STOCKS ---")
    print(profitable_stocks.head(10)[["Symbol", "Sector", "Total_Trades", "Wins", "Win_Rate_%", "Net_PnL_Rs", "Best_Trade_%", "Worst_Trade_%"]].to_string(index=False))

    print("\n--- TOP 5 HIGHEST LOSS-MAKING STOCKS ---")
    print(losing_stocks.tail(5)[["Symbol", "Sector", "Total_Trades", "Losses", "SL_Hits", "Win_Rate_%", "Net_PnL_Rs", "Best_Trade_%", "Worst_Trade_%"]].to_string(index=False))

    # =========================================================================
    # PART 3: YEAR-BY-YEAR (PER YEAR) 1-BY-1 PERFORMANCE (2000 TO 2026)
    # =========================================================================
    print("\n" + "=" * 115)
    print("3. YEAR-BY-YEAR (PER YEAR) 1-BY-1 CALENDAR AUDIT (2000 TO 2026)")
    print("=" * 115)

    equity_df["dt"] = pd.to_datetime(equity_df["date"], utc=True)
    equity_df["year"] = equity_df["dt"].dt.year
    trades_df["exit_dt"] = pd.to_datetime(trades_df["exit_date"], utc=True)
    trades_df["exit_year"] = trades_df["exit_dt"].dt.year

    years_list = sorted(equity_df["year"].unique())
    yearly_records = []

    print(f"{'Year':<6} | {'Start Capital':>14} | {'End Capital':>14} | {'Model Ret %':>11} | {'Sensex %':>9} | {'Alpha %':>8} | {'Max DD %':>9} | {'Trades':>6} | {'Win %':>6} | {'Realized PnL':>14}")
    print("-" * 115)

    for y in years_list:
        sub_eq = equity_df[equity_df["year"] == y].sort_values("dt").reset_index(drop=True)
        if sub_eq.empty:
            continue

        start_val = sub_eq.iloc[0]["total_equity"]
        end_val = sub_eq.iloc[-1]["total_equity"]
        ann_ret_pct = (end_val / start_val - 1.0) * 100.0

        # Benchmark return in that year
        bench_start = sub_eq.iloc[0]["nifty_close"]
        bench_end = sub_eq.iloc[-1]["nifty_close"]
        bench_ret_pct = (bench_end / bench_start - 1.0) * 100.0 if bench_start > 0 else 0.0
        alpha_pct = ann_ret_pct - bench_ret_pct

        # Intra-year drawdown
        roll_peak = sub_eq["total_equity"].cummax()
        sub_dd = ((sub_eq["total_equity"] - roll_peak) / roll_peak) * 100.0
        intra_max_dd = sub_dd.min()

        # Trades closed in this year
        y_trades = trades_df[trades_df["exit_year"] == y]
        tot_yt = len(y_trades)
        y_wins = len(y_trades[y_trades["net_return_pct"] > 0])
        y_losses = len(y_trades[y_trades["net_return_pct"] <= 0])
        y_sl = len(y_trades[y_trades["exit_reason"].str.contains("Stop|Circuit Breaker|Dead Money", case=False, na=False)])
        y_win_rate = (y_wins / tot_yt * 100.0) if tot_yt > 0 else 0.0
        y_pnl = y_trades["pnl_amount"].sum() if tot_yt > 0 else 0.0

        print(
            f"{y:<6} | Rs {start_val:>11,.0f} | Rs {end_val:>11,.0f} | "
            f"{ann_ret_pct:>+10.2f}% | {bench_ret_pct:>+8.2f}% | {alpha_pct:>+7.2f}% | "
            f"{intra_max_dd:>8.2f}% | {tot_yt:>6} | {y_win_rate:>5.1f}% | Rs {y_pnl:>11,.0f}"
        )

        yearly_records.append({
            "Year": y,
            "Start_Equity_Rs": round(start_val, 2),
            "End_Equity_Rs": round(end_val, 2),
            "Model_Annual_Return_%": round(ann_ret_pct, 2),
            "Sensex_Annual_Return_%": round(bench_ret_pct, 2),
            "Alpha_vs_Sensex_%": round(alpha_pct, 2),
            "Intra_Year_Max_Drawdown_%": round(intra_max_dd, 2),
            "Trades_Closed": tot_yt,
            "Wins": y_wins,
            "Losses": y_losses,
            "SL_Hits": y_sl,
            "Win_Rate_%": round(y_win_rate, 2),
            "Realized_PnL_Rs": round(y_pnl, 2),
        })

    year_df = pd.DataFrame(yearly_records)
    year_df.to_csv(REPORT_DIR / "8_SLOT_YEAR_BY_YEAR_PERFORMANCE.csv", index=False)
    year_df.to_csv(DESKTOP_DIR / "8_SLOT_YEAR_BY_YEAR_PERFORMANCE.csv", index=False)

    # =========================================================================
    # PART 4: 11 HISTORICAL TIMELINES / ERAS AUDIT (8 SLOTS)
    # =========================================================================
    print("\n" + "=" * 115)
    print("4. 11 HISTORICAL TIMELINES & MARKET CYCLES (8 SLOTS)")
    print("=" * 115)

    timelines = [
        ("2000 - 2003 (Dot-Com Crash & Base)", "2000-01-01", "2003-12-31"),
        ("2004 - 2008 (The Great Capex Bull Run)", "2004-01-01", "2008-12-31"),
        ("2006 - 2010 (Mid-Cycle to Lehman Rebound)", "2006-01-01", "2010-12-31"),
        ("2009 - 2013 (QE Rebound to Taper Tantrum)", "2009-01-01", "2013-12-31"),
        ("2011 - 2015 (Policy Paralysis to Modi Rally)", "2011-01-01", "2015-12-31"),
        ("2014 - 2019 (Modi-1 Bull Run & NBFC Crash)", "2014-01-01", "2019-12-31"),
        ("2016 - 2020 (Demonetization to COVID Crash)", "2016-01-01", "2020-12-31"),
        ("2020 - 2021 (COVID V-Bottom Rebound)", "2020-01-01", "2021-12-31"),
        ("2021 - 2026 (Post-COVID Retail/PSU Expansion)", "2021-01-01", "2026-10-26"),
        ("2022 - 2026 (Post-Fed Rate Hike Era)", "2022-01-01", "2026-10-26"),
        ("2000 - 2026 (The Complete 26.8-Year Arc)", "2000-01-01", "2026-10-26"),
    ]

    tl_records = []
    print(f"{'Timeline / Era':<45} | {'Years':>5} | {'Final Capital':>14} | {'Mult':>5} | {'CAGR %':>8} | {'Max DD %':>9} | {'Trades':>6} | {'Win %':>6} | {'PF':>5} | {'Payoff':>6}")
    print("-" * 125)

    for label, st_dt, en_dt in timelines:
        r = engine_8.run_backtest(bars_df, bench_df, start_date=st_dt, end_date=en_dt)
        years = max(0.5, (pd.to_datetime(en_dt) - pd.to_datetime(st_dt)).days / 365.25)
        mult = r.final_capital / r.initial_capital
        fin_str = f"Rs {r.final_capital/100000:.1f} L" if r.final_capital < 10_000_000 else f"Rs {r.final_capital/10_000_000:.2f} Cr"

        print(
            f"{label:<45} | {years:>5.1f} | {fin_str:>14} | {mult:>4.1f}x | "
            f"{r.compounded_cagr_pct:>+7.2f}% | {r.max_drawdown_pct:>8.2f}% | "
            f"{r.total_trades:>6} | {r.win_rate_pct:>5.1f}% | {r.profit_factor:>5.2f} | {r.win_loss_ratio:>5.2f}x"
        )

        tl_records.append({
            "Timeline": label,
            "Start_Date": st_dt,
            "End_Date": en_dt,
            "Years": round(years, 1),
            "Initial_Capital_Rs": r.initial_capital,
            "Final_Capital_Rs": round(r.final_capital, 2),
            "Capital_Multiple": round(mult, 2),
            "CAGR_Pct": round(r.compounded_cagr_pct, 2),
            "Max_Drawdown_Pct": round(r.max_drawdown_pct, 2),
            "Total_Trades": r.total_trades,
            "Win_Rate_Pct": round(r.win_rate_pct, 2),
            "Profit_Factor": round(r.profit_factor, 2),
            "Payoff_Ratio": round(r.win_loss_ratio, 2),
        })

    tl_df = pd.DataFrame(tl_records)
    tl_df.to_csv(REPORT_DIR / "8_SLOT_11_TIMELINES_SUMMARY.csv", index=False)
    tl_df.to_csv(DESKTOP_DIR / "8_SLOT_11_TIMELINES_SUMMARY.csv", index=False)

    print("\n" + "=" * 115)
    print(f"[SUCCESS] All 8-Slot Deep Dive CSV Reports Generated & Saved to Desktop:\n  {DESKTOP_DIR}")
    print("=" * 115)


if __name__ == "__main__":
    main()
