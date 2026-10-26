"""
Master Multi-Timeline Institutional Backtest & Stock-by-Stock Audit (2000 - 2026).
Runs comprehensive backtests across all 11 discrete market eras:
1.  2000 - 2003 (Dot-Com Crash & Sideways Bottom)
2.  2004 - 2008 (Secular Bull Run & Lehman Collapse)
3.  2006 - 2010 (Pre-GFC Euphoria, Crash & Recovery)
4.  2009 - 2013 (Post-Crisis Stimulus & Consolidation)
5.  2011 - 2015 (Policy Paralysis, Rupee Crash & Modi-1 Rally)
6.  2014 - 2019 (Modi-1 Era, DeMod, GST & 2018 Midcap Crash)
7.  2016 - 2020 (Demonetization to COVID Crash)
8.  2020 - 2021 (COVID V-Shaped Liquidity Explosion)
9.  2021 - 2026 (Post-COVID Cycle to Modern Era)
10. 2022 - 2026 (Global Rate Hikes to Current Mega Rally)
11. 2000 - 2026 (The Complete 26.8-Year Grand Cycle)

Generates:
- Comprehensive multi-timeline summary table (CAGR, Max DD, Final Capital, Win Rate, Payoff).
- Stock-by-stock metrics (Multiple X, Peak Gain %, Loss %, Net Profit, Exit Type, SL Hits).
- Saves all CSVs directly to Desktop folder: C:\\Users\\DELL\\OneDrive\\Desktop\\BLUMBERG_AUDIT_FILES\\MULTI_TIMELINE_AUDIT.
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

DATA_DIR = PROJECT_ROOT / "data" / "cache" / "historical_2000_2026"
REPORT_DIR = PROJECT_ROOT / "reports" / "multi_timeline_audit"
DESKTOP_DIR = Path(r"C:\Users\DELL\OneDrive\Desktop\BLUMBERG_AUDIT_FILES\MULTI_TIMELINE_AUDIT")

REPORT_DIR.mkdir(parents=True, exist_ok=True)
DESKTOP_DIR.mkdir(parents=True, exist_ok=True)


def simulate_timeline(all_bars: pd.DataFrame, bench_df: pd.DataFrame, start_date: str, end_date: str, timeline_name: str):
    # Slice date range
    st_dt = pd.to_datetime(start_date)
    end_dt = pd.to_datetime(end_date)

    bench = bench_df[(bench_df["date"] >= st_dt) & (bench_df["date"] <= end_dt)].sort_values("date").reset_index(drop=True)
    if len(bench) < 30:
        return None

    bench["ema50"] = bench["close"].ewm(span=50, adjust=False).mean()
    bench["ema200"] = bench["close"].ewm(span=200, adjust=False).mean()
    bench["regime_ok"] = (bench["close"] > bench["ema50"]) | (bench["close"] > bench["ema200"])
    bench_regime = bench.set_index("date")["regime_ok"].to_dict()
    bench_close = bench.set_index("date")["close"].to_dict()
    bench_ret20 = bench.set_index("date")["close"].pct_change(20)

    # Filter bars
    bars_window = all_bars[(all_bars["date"] >= st_dt - pd.Timedelta(days=90)) & (all_bars["date"] <= end_dt)].copy()

    symbol_frames = {}
    for sym, grp in bars_window.groupby("symbol"):
        df = grp.sort_values("date").reset_index(drop=True)
        if len(df) < 30:
            continue
        df["turnover"] = df["close"] * df["volume"]
        df["ret20"] = df["close"].pct_change(20)
        df["ret5"] = df["close"].pct_change(5)
        vol_mean = df["volume"].shift(1).rolling(20, min_periods=10).mean()
        df["rvol"] = df["volume"] / vol_mean.where(vol_mean > 0, 1.0)

        range_20 = df["high"].shift(1).rolling(20, min_periods=5).max() - df["low"].shift(1).rolling(20, min_periods=5).min()
        range_5 = df["high"].shift(1).rolling(5, min_periods=2).max() - df["low"].shift(1).rolling(5, min_periods=2).min()
        df["compression"] = (range_5 / range_20.where(range_20 > 0, 1.0)).fillna(1.0)

        b_ret = df["date"].map(bench_ret20).fillna(0.0)
        df["rs_20"] = df["ret20"] - b_ret

        # VCP signal with dynamic inflation turnover
        # Pre-2008: 1 Cr, 2008-2016: 2 Cr, Post-2016: 3 Cr
        yr = st_dt.year
        min_turnover = 10_000_000.0 if yr < 2008 else (20_000_000.0 if yr < 2016 else 30_000_000.0)

        df["radar_signal"] = (
            ((df["compression"] <= 0.70) | ((df["ret5"] > 0) & (df["ret20"] > 0) & (df["ret20"] <= 0.35)))
            & (df["rvol"] >= 1.40)
            & (df["rs_20"] >= -0.01)
            & (df["turnover"] >= min_turnover)
        )
        symbol_frames[sym] = df[df["date"] >= st_dt].set_index("date")

    all_dates = sorted([d for d in bench["date"].unique() if d >= st_dt and d <= end_dt])
    if not all_dates:
        return None

    max_slots = 8
    t2_day = 7
    sl_pct = 0.08
    cost_factor = 0.0015  # 15 bps per side friction
    slot_alloc_pct = 1.0 / max_slots

    initial_capital = 1_000_000.0
    cash = initial_capital
    active_pos = {}
    closed_trades = []
    equity_hist = []

    for d_idx, cur_date in enumerate(all_dates):
        regime_ok = bench_regime.get(cur_date, True)
        existing_syms = list(active_pos.keys())
        available_cash = cash
        available_slots = max(0, max_slots - len(existing_syms))

        mtm_open = sum(
            pos["shares"] * float(symbol_frames[s].loc[cur_date, "open"])
            if (s in symbol_frames and cur_date in symbol_frames[s].index) else pos["invested"]
            for s, pos in active_pos.items()
        )
        tot_eq = cash + mtm_open

        # A. Tranche 2 Additions at Open
        for sym in existing_syms:
            pos = active_pos[sym]
            if pos.get("t2_eligible") and not pos.get("t2_active"):
                pos["t2_eligible"] = False
                if sym in symbol_frames and cur_date in symbol_frames[sym].index:
                    b = symbol_frames[sym].loc[cur_date]
                    if not (b["open"] == b["high"] and b["high"] == b["low"]):
                        t2_alloc = min(available_cash, tot_eq * (slot_alloc_pct * 0.5))
                        if t2_alloc >= 5000:
                            t2_entry = float(b["open"]) * (1.0 + cost_factor)
                            pos["shares"] += t2_alloc / t2_entry
                            pos["invested"] += t2_alloc
                            pos["blended_entry"] = pos["invested"] / pos["shares"]
                            pos["t2_active"] = True
                            cash -= t2_alloc
                            available_cash -= t2_alloc

        # B. New Entries at Open
        if d_idx > 0 and available_slots > 0 and available_cash >= 5000 and regime_ok:
            prev_date = all_dates[d_idx - 1]
            candidates = []
            for sym, s_df in symbol_frames.items():
                if sym in active_pos:
                    continue
                if prev_date in s_df.index and s_df.loc[prev_date, "radar_signal"]:
                    p_row = s_df.loc[prev_date]
                    candidates.append({
                        "symbol": sym,
                        "rs": float(p_row["rs_20"]),
                        "rvol": float(p_row["rvol"]),
                        "score": float(p_row["rs_20"]) * float(p_row["rvol"]),
                    })
            candidates.sort(key=lambda x: x["score"], reverse=True)

            for cand in candidates:
                if available_slots <= 0 or available_cash < 5000:
                    break
                sym = cand["symbol"]
                s_df = symbol_frames[sym]
                if cur_date not in s_df.index:
                    continue
                b = s_df.loc[cur_date]
                if b["open"] == b["high"] and b["high"] == b["low"]:
                    continue

                alloc = min(available_cash, tot_eq * (slot_alloc_pct * 0.5))
                if alloc < 2500:
                    continue
                entry_p = float(b["open"]) * (1.0 + cost_factor)
                cash -= alloc
                available_cash -= alloc
                available_slots -= 1
                active_pos[sym] = {
                    "symbol": sym, "entry_date": cur_date, "entry_price": entry_p,
                    "shares": alloc / entry_p, "invested": alloc, "blended_entry": entry_p,
                    "peak_price": entry_p, "days_held": 0, "t2_active": False,
                }

        # C. Exits Evaluated Against Prior Peak
        closed_syms = []
        for sym in existing_syms:
            pos = active_pos[sym]
            if sym not in symbol_frames or cur_date not in symbol_frames[sym].index:
                continue
            bar = symbol_frames[sym].loc[cur_date]
            c_open, c_high, c_low, c_close = float(bar["open"]), float(bar["high"]), float(bar["low"]), float(bar["close"])

            prior_peak = pos["peak_price"]
            peak_gain = (prior_peak / pos["blended_entry"] - 1.0) * 100.0
            dip_from_peak = (c_close / prior_peak - 1.0) * 100.0
            trail_buf = 20.0 if peak_gain >= 100.0 else (17.0 if peak_gain >= 50.0 else (14.0 if peak_gain >= 25.0 else None))

            exit_trig = False
            exit_p = 0.0
            exit_reason = ""

            if not pos["t2_active"] and pos["days_held"] >= (t2_day - 1):
                if c_close > pos["entry_price"] and c_low > pos["entry_price"] * (1.0 - sl_pct):
                    pos["t2_eligible"] = True

            # 1. Hard Initial Stop Loss (-8%)
            if (c_low <= pos["blended_entry"] * (1.0 - sl_pct)) and (peak_gain < 15.0):
                exit_trig = True
                exit_p = min(pos["blended_entry"] * (1.0 - sl_pct), c_open) * (1.0 - cost_factor)
                exit_reason = "STOP_LOSS_8PCT"

            # 2. Breakeven Stop
            elif (peak_gain >= 15.0) and (trail_buf is None) and (c_low <= pos["blended_entry"]):
                exit_trig = True
                exit_p = min(pos["blended_entry"], c_open) * (1.0 - cost_factor)
                exit_reason = "BREAKEVEN_STOP"

            # 3. Dynamic Growth-Trailing Exit
            elif (trail_buf is not None) and (dip_from_peak <= -trail_buf):
                exit_trig = True
                exit_p = min(c_open, c_close) * (1.0 - cost_factor) if c_open < c_close else c_close * (1.0 - cost_factor)
                exit_reason = f"TRAILING_{int(trail_buf)}PCT"

            # 4. Stagnation Timeout (30 days)
            elif (pos["days_held"] >= 30) and (peak_gain < 10.0):
                exit_trig = True
                exit_p = c_close * (1.0 - cost_factor)
                exit_reason = "STAGNATION_TIMEOUT"

            if exit_trig:
                proceeds = pos["shares"] * exit_p
                cash += proceeds
                net_pnl = proceeds - pos["invested"]
                net_ret_pct = (net_pnl / pos["invested"]) * 100.0
                closed_trades.append({
                    "symbol": sym, "entry_date": pos["entry_date"], "exit_date": cur_date,
                    "invested_rs": pos["invested"], "proceeds_rs": proceeds, "pnl_rs": net_pnl,
                    "net_return_pct": net_ret_pct, "win": net_ret_pct > 0,
                    "exit_reason": exit_reason, "t2_added": pos["t2_active"]
                })
                closed_syms.append(sym)
            else:
                if c_high > pos["peak_price"]:
                    pos["peak_price"] = c_high
                pos["days_held"] += 1

        for sym in closed_syms:
            del active_pos[sym]

        for sym, pos in active_pos.items():
            if sym not in existing_syms and sym in symbol_frames and cur_date in symbol_frames[sym].index:
                b = symbol_frames[sym].loc[cur_date]
                if float(b["high"]) > pos["peak_price"]:
                    pos["peak_price"] = float(b["high"])

        mtm_val = 0.0
        for sym, pos in active_pos.items():
            if sym in symbol_frames and cur_date in symbol_frames[sym].index:
                c_val = float(symbol_frames[sym].loc[cur_date, "close"])
            else:
                c_val = pos["blended_entry"]
            mtm_val += pos["shares"] * c_val

        equity_hist.append({
            "date": cur_date, "equity": cash + mtm_val,
            "cash": cash, "active_slots": len(active_pos),
            "bench": bench_close.get(cur_date, np.nan)
        })

    # Close remaining open positions at terminal date
    for sym, pos in active_pos.items():
        c_val = float(symbol_frames[sym].iloc[-1]["close"]) if sym in symbol_frames else pos["blended_entry"]
        proceeds = pos["shares"] * c_val * (1.0 - cost_factor)
        net_pnl = proceeds - pos["invested"]
        net_ret_pct = (net_pnl / pos["invested"]) * 100.0
        closed_trades.append({
            "symbol": sym, "entry_date": pos["entry_date"], "exit_date": all_dates[-1],
            "invested_rs": pos["invested"], "proceeds_rs": proceeds, "pnl_rs": net_pnl,
            "net_return_pct": net_ret_pct, "win": net_ret_pct > 0,
            "exit_reason": "TERMINAL_CLOSE", "t2_added": pos["t2_active"]
        })

    eq_df = pd.DataFrame(equity_hist)
    final_cap = eq_df["equity"].iloc[-1]
    years = max(0.5, (all_dates[-1] - all_dates[0]).days / 365.25)
    cagr = (final_cap / initial_capital) ** (1.0 / years) - 1.0

    roll_max = eq_df["equity"].cummax()
    drawdowns = (eq_df["equity"] - roll_max) / roll_max
    max_dd = drawdowns.min() * 100.0

    tdf = pd.DataFrame(closed_trades)
    tot_trades = len(tdf)
    win_trades = tdf[tdf["win"]]
    loss_trades = tdf[~tdf["win"]]
    sl_hits = tdf[tdf["exit_reason"] == "STOP_LOSS_8PCT"]

    win_rate = (len(win_trades) / tot_trades * 100.0) if tot_trades > 0 else 0.0
    wins_sum = win_trades["net_return_pct"].sum() if len(win_trades) > 0 else 0.0
    loss_sum = loss_trades["net_return_pct"].abs().sum() if len(loss_trades) > 0 else 0.0
    pf = (wins_sum / loss_sum) if loss_sum > 0 else 0.0

    avg_win = win_trades["net_return_pct"].mean() if len(win_trades) > 0 else 0.0
    avg_loss = loss_trades["net_return_pct"].abs().mean() if len(loss_trades) > 0 else 0.0
    payoff = (avg_win / avg_loss) if avg_loss > 0 else 0.0

    # Stock-by-stock aggregation in this timeline
    stock_summary = []
    if tot_trades > 0:
        for s, s_grp in tdf.groupby("symbol"):
            s_trades = len(s_grp)
            s_wins = len(s_grp[s_grp["win"]])
            s_losses = len(s_grp[~s_grp["win"]])
            s_sl = len(s_grp[s_grp["exit_reason"] == "STOP_LOSS_8PCT"])
            tot_pnl = s_grp["pnl_rs"].sum()
            best_ret = s_grp["net_return_pct"].max()
            worst_ret = s_grp["net_return_pct"].min()
            cum_mult = (1.0 + s_grp["net_return_pct"] / 100.0).prod()
            top_exit = s_grp.sort_values("net_return_pct", ascending=False).iloc[0]["exit_reason"]

            stock_summary.append({
                "Timeline": timeline_name,
                "Symbol": s,
                "Trades": s_trades,
                "Wins": s_wins,
                "Losses": s_losses,
                "SL_Hits": s_sl,
                "Win_Rate_%": round(s_wins / s_trades * 100.0, 1),
                "Best_Return_%": round(best_ret, 1),
                "Worst_Return_%": round(worst_ret, 1),
                "Cumulative_Multiple": round(cum_mult, 2),
                "Total_PnL_Rs": round(tot_pnl, 2),
                "Primary_Exit_Reason": top_exit,
            })

    stock_df = pd.DataFrame(stock_summary)
    if len(stock_df) > 0:
        stock_df = stock_df.sort_values("Cumulative_Multiple", ascending=False)

    return {
        "timeline": timeline_name,
        "start_date": start_date,
        "end_date": end_date,
        "years": round(years, 1),
        "initial_capital": initial_capital,
        "final_capital": final_cap,
        "capital_multiple": round(final_cap / initial_capital, 2),
        "cagr_pct": round(cagr * 100.0, 2),
        "max_drawdown_pct": round(max_dd, 2),
        "total_trades": tot_trades,
        "wins": len(win_trades),
        "losses": len(loss_trades),
        "sl_hits": len(sl_hits),
        "win_rate_pct": round(win_rate, 2),
        "profit_factor": round(pf, 2),
        "payoff_ratio": round(payoff, 2),
        "stock_df": stock_df,
        "trades_df": tdf,
        "equity_df": eq_df,
    }


def run_all_timelines():
    print("=" * 115)
    print("      BLUMBERG MARKET RADAR - MULTI-TIMELINE COMPREHENSIVE INSTITUTIONAL AUDIT (2000 - 2026)")
    print("=" * 115)

    market_path = DATA_DIR / "market_bars_with_delisted_2000_2026.parquet"
    bench_path = DATA_DIR / "sensex_bench_2000_2026.parquet"

    if not market_path.exists() or not bench_path.exists():
        print("[ERROR] Parquet files missing!")
        sys.exit(1)

    all_bars = pd.read_parquet(market_path)
    all_bars["date"] = pd.to_datetime(all_bars["date"]).dt.tz_localize(None)
    bench_df = pd.read_parquet(bench_path)
    bench_df["date"] = pd.to_datetime(bench_df["date"]).dt.tz_localize(None)

    timelines = [
        ("2000 - 2003", "2000-01-01", "2003-12-31"),
        ("2004 - 2008", "2004-01-01", "2008-12-31"),
        ("2006 - 2010", "2006-01-01", "2010-12-31"),
        ("2009 - 2013", "2009-01-01", "2013-12-31"),
        ("2011 - 2015", "2011-01-01", "2015-12-31"),
        ("2014 - 2019", "2014-01-01", "2019-12-31"),
        ("2016 - 2020", "2016-01-01", "2020-12-31"),
        ("2020 - 2021", "2020-01-01", "2021-12-31"),
        ("2021 - 2026", "2021-01-01", "2026-10-26"),
        ("2022 - 2026", "2022-01-01", "2026-10-26"),
        ("2000 - 2026", "2000-01-01", "2026-10-26"),
    ]

    summary_rows = []
    all_stock_dfs = []

    print(f"\n{'Timeline Period':<15} | {'Years':>5} | {'Initial':>8} | {'Final Value':>13} | {'Mult':>5} | {'CAGR %':>8} | {'Max DD %':>9} | {'Trades':>6} | {'Win %':>6} | {'SL Hits':>7} | {'PF':>5} | {'Payoff':>6}")
    print("-" * 120)

    for label, st, en in timelines:
        res = simulate_timeline(all_bars, bench_df, st, en, label)
        if res is None:
            continue

        cagr_str = f"{res['cagr_pct']:+.2f}%"
        dd_str = f"{res['max_drawdown_pct']:.2f}%"
        fin_str = f"Rs {res['final_capital']/100000:.1f} L" if res['final_capital'] < 10_000_000 else f"Rs {res['final_capital']/10_000_000:.2f} Cr"

        print(
            f"{label:<15} | {res['years']:>5.1f} | Rs 10.0L | {fin_str:>13} | {res['capital_multiple']:>4.1f}x | "
            f"{cagr_str:>8} | {dd_str:>9} | {res['total_trades']:>6} | {res['win_rate_pct']:>5.1f}% | "
            f"{res['sl_hits']:>7} | {res['profit_factor']:>5.2f} | {res['payoff_ratio']:>5.2f}x"
        )

        summary_rows.append({
            "Timeline": label,
            "Start_Date": st,
            "End_Date": en,
            "Years": res["years"],
            "Initial_Capital_Rs": res["initial_capital"],
            "Final_Capital_Rs": round(res["final_capital"], 2),
            "Capital_Multiple": res["capital_multiple"],
            "CAGR_Pct": res["cagr_pct"],
            "Max_Drawdown_Pct": res["max_drawdown_pct"],
            "Total_Trades": res["total_trades"],
            "Wins": res["wins"],
            "Losses": res["losses"],
            "SL_Hits": res["sl_hits"],
            "Win_Rate_Pct": res["win_rate_pct"],
            "Profit_Factor": res["profit_factor"],
            "Payoff_Ratio": res["payoff_ratio"],
        })

        tag = label.replace(" - ", "_")
        if len(res["stock_df"]) > 0:
            res["stock_df"].to_csv(REPORT_DIR / f"stocks_{tag}.csv", index=False)
            res["stock_df"].to_csv(DESKTOP_DIR / f"stocks_{tag}.csv", index=False)
            all_stock_dfs.append(res["stock_df"])

        res["trades_df"].to_csv(REPORT_DIR / f"trades_{tag}.csv", index=False)
        res["trades_df"].to_csv(DESKTOP_DIR / f"trades_{tag}.csv", index=False)

        res["equity_df"].to_csv(REPORT_DIR / f"equity_{tag}.csv", index=False)
        res["equity_df"].to_csv(DESKTOP_DIR / f"equity_{tag}.csv", index=False)

    print("=" * 120)

    # Master summaries
    sum_df = pd.DataFrame(summary_rows)
    sum_df.to_csv(REPORT_DIR / "MULTI_TIMELINE_CAGR_SUMMARY.csv", index=False)
    sum_df.to_csv(DESKTOP_DIR / "MULTI_TIMELINE_CAGR_SUMMARY.csv", index=False)

    if all_stock_dfs:
        master_stocks = pd.concat(all_stock_dfs, ignore_index=True)
        master_stocks.to_csv(REPORT_DIR / "ALL_TIMELINES_STOCK_METRICS.csv", index=False)
        master_stocks.to_csv(DESKTOP_DIR / "ALL_TIMELINES_STOCK_METRICS.csv", index=False)

    print(f"\n[SUCCESS] Saved all 11 timeline audit reports and stock breakdowns directly to Desktop:")
    print(f"Directory: {DESKTOP_DIR}")


if __name__ == "__main__":
    run_all_timelines()
