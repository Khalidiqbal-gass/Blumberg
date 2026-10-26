"""
Detailed Forensic 2020 Backtest:
Evaluates 50-50 Hybrid Pyramiding throughout the 2020 Covid Crash and Recovery:
1. Jan - Mar 2020: Pre-Covid & Massive Covid Crash (-38% Sensex fall).
2. Apr - Dec 2020: Epic Post-Covid Multibagger Rally.
Tracks:
- Total Profit / Loss in 1 Year.
- False Breakout Stocks Caught (Losers) & How Pyramiding Halved Their Losses.
- Monster Compounders Caught (Winners) & Pyramiding Full Riding.
- Month-by-Month PnL Table & March Drawdown Protection.
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import Optional

DATA_DIR = Path("data/cache/historical_2000_2026")
REPORT_DIR = Path("reports/audit_2020")
REPORT_DIR.mkdir(parents=True, exist_ok=True)

@dataclass
class Position:
    symbol: str
    entry_date1: pd.Timestamp
    entry_price1: float
    shares1: float
    invested1: float
    tranche2_active: bool = False
    tranche2_eligible: bool = False
    entry_date2: Optional[pd.Timestamp] = None
    entry_price2: float = 0.0
    shares2: float = 0.0
    invested2: float = 0.0
    blended_entry: float = 0.0
    total_shares: float = 0.0
    total_invested: float = 0.0
    peak_price: float = 0.0
    days_held: int = 0

def run_2020_backtest(initial_capital: float = 1_000_000.0, max_slots: int = 20, apply_regime: bool = True):
    cost_factor = 0.0015  # 15 bps each side = 30 bps round trip

    bench_df = pd.read_parquet(DATA_DIR / "sensex_bench_2000_2026.parquet")
    bench_df["date"] = pd.to_datetime(bench_df["date"]).dt.tz_localize(None)
    bench_df = bench_df.sort_values("date").reset_index(drop=True)
    bench_df["ema200"] = bench_df["close"].ewm(span=200, adjust=False).mean()
    bench_regime = dict(zip(bench_df["date"], bench_df["close"] > bench_df["ema200"]))
    bench_ret20 = bench_df.set_index("date")["close"].pct_change(20)
    bench_close_dict = dict(zip(bench_df["date"], bench_df["close"]))

    market_df = pd.read_parquet(DATA_DIR / "market_bars_with_delisted_2000_2026.parquet")
    market_df["date"] = pd.to_datetime(market_df["date"]).dt.tz_localize(None)

    # Compute features for all symbols
    symbol_frames = {}
    for sym, grp in market_df.groupby("symbol"):
        df = grp.sort_values("date").reset_index(drop=True)
        if len(df) < 40:
            continue
        df["prev_close"] = df["close"].shift(1)
        df["ret20"] = df["close"].pct_change(20)
        df["ret5"] = df["close"].pct_change(5)
        vol_mean = df["volume"].shift(1).rolling(20, min_periods=10).mean()
        df["rvol"] = df["volume"] / vol_mean.where(vol_mean > 0, 1.0)
        
        range_20 = df["high"].shift(1).rolling(20, min_periods=5).max() - df["low"].shift(1).rolling(20, min_periods=5).min()
        range_5 = df["high"].shift(1).rolling(5, min_periods=2).max() - df["low"].shift(1).rolling(5, min_periods=2).min()
        df["compression"] = (range_5 / range_20.where(range_20 > 0, 1.0)).fillna(1.0)
        bench_ret = df["date"].map(bench_ret20).fillna(0.0)
        df["rs_20"] = df["ret20"] - bench_ret
        
        df["radar_signal"] = (
            ((df["compression"] <= 0.70) | ((df["ret5"] > 0) & (df["ret20"] > 0) & (df["ret20"] <= 0.35)))
            & (df["rvol"] >= 1.40)
            & (df["rs_20"] >= -0.01)
        )
        symbol_frames[sym] = df.set_index("date")

    # Filter to 2020 trading days
    all_dates = sorted(market_df["date"].unique())
    sim_dates = [d for d in all_dates if pd.Timestamp("2020-01-01") <= d <= pd.Timestamp("2020-12-31")]

    cash = initial_capital
    active_positions: dict[str, Position] = {}
    closed_trades: list[dict] = []
    daily_records: list[dict] = []

    for d_idx, cur_date in enumerate(sim_dates):
        # 1. Update active positions & evaluate exits
        closed_syms = []
        for sym, pos in active_positions.items():
            s_df = symbol_frames[sym]
            if cur_date not in s_df.index:
                continue
            bar = s_df.loc[cur_date]
            cur_open = float(bar["open"])
            cur_high = float(bar["high"])
            cur_low = float(bar["low"])
            cur_close = float(bar["close"])

            pos.days_held += 1
            if cur_high > pos.peak_price:
                pos.peak_price = cur_high

            peak_gain_pct = (pos.peak_price / pos.blended_entry - 1.0) * 100.0
            dip_from_peak_pct = (cur_close / pos.peak_price - 1.0) * 100.0

            trail_buffer = 20.0 if peak_gain_pct >= 100.0 else (17.0 if peak_gain_pct >= 50.0 else (14.0 if peak_gain_pct >= 25.0 else None))

            exit_triggered = False
            exit_price = 0.0
            exit_reason = ""

            # Check Day 10 Pyramiding eligibility
            if not pos.tranche2_active and pos.days_held >= 10:
                if cur_close > pos.entry_price1 and cur_low > pos.entry_price1 * 0.92:
                    pos.tranche2_eligible = True

            # Exit Condition 1: Initial Stop Loss (-8%)
            if (cur_low <= pos.blended_entry * 0.92) and (peak_gain_pct < 15.0):
                exit_triggered = True
                exit_price = min(pos.blended_entry * 0.92, cur_open) * (1.0 - cost_factor)
                exit_reason = "INITIAL_STOP_LOSS (-8%)"

            # Exit Condition 2: Breakeven Stop (+15% peak gain -> floor at entry)
            elif (peak_gain_pct >= 15.0) and (trail_buffer is None) and (cur_low <= pos.blended_entry):
                exit_triggered = True
                exit_price = min(pos.blended_entry, cur_open) * (1.0 - cost_factor)
                exit_reason = "BREAKEVEN_STOP (Profit Protected)"

            # Exit Condition 3: Trailing Stop
            elif (trail_buffer is not None) and (dip_from_peak_pct <= -trail_buffer):
                exit_triggered = True
                exit_price = cur_close * (1.0 - cost_factor)
                exit_reason = f"TRAILING_EXIT_{int(trail_buffer)}PCT"

            # Exit Condition 4: Stagnation Timeout (30 days without progress)
            elif (pos.days_held >= 30) and (peak_gain_pct < 10.0):
                exit_triggered = True
                exit_price = cur_close * (1.0 - cost_factor)
                exit_reason = "STAGNATION_TIMEOUT (30 Days Dead Money)"

            if exit_triggered:
                proceeds = pos.total_shares * exit_price
                cash += proceeds
                net_pnl = proceeds - pos.total_invested
                net_ret_pct = (net_pnl / pos.total_invested) * 100.0

                closed_trades.append({
                    "symbol": sym,
                    "entry_date": pos.entry_date1.strftime("%Y-%m-%d"),
                    "exit_date": cur_date.strftime("%Y-%m-%d"),
                    "entry_price": pos.entry_price1,
                    "blended_entry": pos.blended_entry,
                    "exit_price": exit_price,
                    "days_held": pos.days_held,
                    "tranche2_added": pos.tranche2_active,
                    "total_invested": pos.total_invested,
                    "net_pnl": net_pnl,
                    "net_return_pct": net_ret_pct,
                    "multiple": 1.0 + net_ret_pct / 100.0,
                    "exit_reason": exit_reason,
                    "outcome": "WIN" if net_ret_pct > 0 else "LOSS",
                })
                closed_syms.append(sym)

        for s in closed_syms:
            del active_positions[s]

        # 2. Mark-to-market portfolio value
        mtm_val = 0.0
        for sym, pos in active_positions.items():
            s_df = symbol_frames[sym]
            c_val = float(s_df.loc[cur_date, "close"]) if cur_date in s_df.index else pos.blended_entry
            mtm_val += pos.total_shares * c_val
        total_equity = cash + mtm_val

        # 3. Add Tranche 2 on cur_date open if eligible
        for sym, pos in list(active_positions.items()):
            if getattr(pos, "tranche2_eligible", False) and not pos.tranche2_active:
                pos.tranche2_eligible = False
                s_df = symbol_frames[sym]
                if cur_date in s_df.index:
                    bar = s_df.loc[cur_date]
                    b_open, b_high, b_low = float(bar["open"]), float(bar["high"]), float(bar["low"])
                    if not (b_open == b_high and b_high == b_low):
                        t2_alloc = min(cash, total_equity * 0.025)
                        if t2_alloc >= 5000:
                            t2_entry = b_open * (1.0 + cost_factor)
                            t2_shares = t2_alloc / t2_entry
                            cash -= t2_alloc
                            pos.shares2 = t2_shares
                            pos.invested2 = t2_alloc
                            pos.total_shares += t2_shares
                            pos.total_invested += t2_alloc
                            pos.blended_entry = pos.total_invested / pos.total_shares
                            pos.tranche2_active = True

        # 4. Process new entries from previous day signals
        if d_idx > 0:
            prev_date = sim_dates[d_idx - 1]
            regime_ok = bench_regime.get(prev_date, True) if apply_regime else True
            
            if regime_ok:
                candidates = []
                for sym, s_df in symbol_frames.items():
                    if sym in active_positions:
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
                    sym = cand["symbol"]
                    s_df = symbol_frames[sym]
                    if cur_date not in s_df.index:
                        continue
                    bar = s_df.loc[cur_date]
                    c_open, c_high, c_low = float(bar["open"]), float(bar["high"]), float(bar["low"])
                    if c_open == c_high and c_high == c_low:
                        continue
                    if len(active_positions) >= max_slots:
                        break
                    alloc = min(cash, total_equity * 0.025)  # Tranche 1: 2.5% of equity
                    if alloc < 2500:
                        break
                    entry_p = c_open * (1.0 + cost_factor)
                    shares = alloc / entry_p
                    cash -= alloc
                    active_positions[sym] = Position(
                        symbol=sym,
                        entry_date1=cur_date,
                        entry_price1=entry_p,
                        shares1=shares,
                        invested1=alloc,
                        tranche2_active=False,
                        blended_entry=entry_p,
                        total_shares=shares,
                        total_invested=alloc,
                        peak_price=entry_p,
                    )

        daily_records.append({
            "date": cur_date,
            "total_equity": total_equity,
            "cash": cash,
            "active_positions": len(active_positions),
            "sensex": bench_close_dict.get(cur_date, np.nan),
        })

    # Close open positions on 2020-12-31 at mark-to-market
    last_date = sim_dates[-1]
    for sym, pos in list(active_positions.items()):
        s_df = symbol_frames[sym]
        last_close = float(s_df.loc[last_date, "close"]) if last_date in s_df.index else pos.blended_entry
        exit_price = last_close * (1.0 - cost_factor)
        proceeds = pos.total_shares * exit_price
        net_pnl = proceeds - pos.total_invested
        net_ret_pct = (net_pnl / pos.total_invested) * 100.0
        closed_trades.append({
            "symbol": sym,
            "entry_date": pos.entry_date1.strftime("%Y-%m-%d"),
            "exit_date": last_date.strftime("%Y-%m-%d"),
            "entry_price": pos.entry_price1,
            "blended_entry": pos.blended_entry,
            "exit_price": exit_price,
            "days_held": pos.days_held,
            "tranche2_added": pos.tranche2_active,
            "total_invested": pos.total_invested,
            "net_pnl": net_pnl,
            "net_return_pct": net_ret_pct,
            "multiple": 1.0 + net_ret_pct / 100.0,
            "exit_reason": "HOLDING_END_OF_YEAR (M2M)",
            "outcome": "WIN" if net_ret_pct > 0 else "LOSS",
        })

    tdf = pd.DataFrame(closed_trades)
    eq_df = pd.DataFrame(daily_records)
    eq_df["drawdown"] = (eq_df["total_equity"] - eq_df["total_equity"].cummax()) / eq_df["total_equity"].cummax() * 100.0
    
    start_equity = initial_capital
    end_equity = float(eq_df.iloc[-1]["total_equity"])
    net_return_pct = (end_equity / start_equity - 1.0) * 100.0
    max_dd = float(eq_df["drawdown"].min())

    # Benchmark Sensex 2020 return & drawdown
    sensex_start = float(eq_df.iloc[0]["sensex"])
    sensex_end = float(eq_df.iloc[-1]["sensex"])
    sensex_ret = (sensex_end / sensex_start - 1.0) * 100.0
    s_series = eq_df["sensex"]
    sensex_max_dd = float(((s_series - s_series.cummax()) / s_series.cummax()).min()) * 100.0

    winners = tdf[tdf["outcome"] == "WIN"]
    losers = tdf[tdf["outcome"] == "LOSS"]

    # Month-by-month table
    eq_df["month"] = eq_df["date"].dt.strftime("%Y-%m")
    monthly_rows = []
    prev_m_cap = start_equity
    for m, grp in eq_df.groupby("month"):
        m_start = prev_m_cap
        m_end = float(grp.iloc[-1]["total_equity"])
        m_ret = (m_end / m_start - 1.0) * 100.0
        m_min_dd = float(grp["drawdown"].min())
        monthly_rows.append({
            "Month": m,
            "Start Capital (Rs)": m_start,
            "End Capital (Rs)": m_end,
            "Monthly Return %": m_ret,
            "Max Drawdown %": m_min_dd,
            "Avg Open Positions": grp["active_positions"].mean(),
        })
        prev_m_cap = m_end
    month_df = pd.DataFrame(monthly_rows)

    return {
        "apply_regime": apply_regime,
        "start_equity": start_equity,
        "end_equity": end_equity,
        "net_pnl": end_equity - start_equity,
        "net_return_pct": net_return_pct,
        "max_drawdown": max_dd,
        "sensex_ret": sensex_ret,
        "sensex_max_dd": sensex_max_dd,
        "total_trades": len(tdf),
        "winners_count": len(winners),
        "losers_count": len(losers),
        "win_rate_pct": (len(winners) / len(tdf) * 100.0) if len(tdf) > 0 else 0.0,
        "total_profit_amount": winners["net_pnl"].sum(),
        "total_loss_amount": losers["net_pnl"].sum(),
        "avg_win_pct": winners["net_return_pct"].mean() if len(winners) > 0 else 0.0,
        "avg_loss_pct": losers["net_return_pct"].mean() if len(losers) > 0 else 0.0,
        "halved_loss_count": int(((tdf["outcome"] == "LOSS") & (~tdf["tranche2_added"])).sum()),
        "multibaggers_2x": int((tdf["net_return_pct"] >= 100.0).sum()),
        "trades_df": tdf,
        "equity_df": eq_df,
        "month_df": month_df,
    }

if __name__ == "__main__":
    res_regime = run_2020_backtest(apply_regime=True)
    res_no_regime = run_2020_backtest(apply_regime=False)

    print("=" * 80)
    print("DETAILED 2020 BACKTEST RESULTS (WITH REGIME FILTER)")
    print("=" * 80)
    print(f"Starting Capital:     Rs {res_regime['start_equity']:,.2f}")
    print(f"Ending Capital:       Rs {res_regime['end_equity']:,.2f}")
    print(f"Net 2020 Profit:      Rs {res_regime['net_pnl']:,.2f} (+{res_regime['net_return_pct']:.2f}%)")
    print(f"Sensex 2020 Return:   +{res_regime['sensex_ret']:.2f}% (Alpha: +{res_regime['net_return_pct'] - res_regime['sensex_ret']:.2f}%)")
    print(f"Max Portfolio DD:     {res_regime['max_drawdown']:.2f}% (vs Sensex Crash: {res_regime['sensex_max_dd']:.2f}%)")
    print(f"Total Trades Taken:   {res_regime['total_trades']}")
    print(f"Win Rate:             {res_regime['win_rate_pct']:.1f}% ({res_regime['winners_count']} Winners vs {res_regime['losers_count']} Losers)")
    print(f"Total Profit Won:     Rs {res_regime['total_profit_amount']:,.2f} (Avg Win: +{res_regime['avg_win_pct']:.1f}%)")
    print(f"Total Loss Incurred:  Rs {res_regime['total_loss_amount']:,.2f} (Avg Loss: {res_regime['avg_loss_pct']:.1f}%)")
    print(f"Trades Loss Halved:   {res_regime['halved_loss_count']} Trades (Tranche 2 never added!)")
    print(f"2x+ Multibaggers:     {res_regime['multibaggers_2x']} Stocks")

    print("\n--- Month-by-Month 2020 Table ---")
    print(res_regime['month_df'].to_string(index=False))

    print("\n--- Top Winners Captured in 2020 ---")
    top_w = res_regime['trades_df'].sort_values('net_return_pct', ascending=False).head(10)
    print(top_w[['symbol', 'entry_date', 'exit_date', 'days_held', 'tranche2_added', 'net_return_pct', 'net_pnl', 'exit_reason']].to_string(index=False))

    print("\n--- Worst Losers (False Breakouts) in 2020 ---")
    worst_l = res_regime['trades_df'].sort_values('net_return_pct', ascending=True).head(10)
    print(worst_l[['symbol', 'entry_date', 'exit_date', 'days_held', 'tranche2_added', 'net_return_pct', 'net_pnl', 'exit_reason']].to_string(index=False))
