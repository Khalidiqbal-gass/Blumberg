"""
Fine-tuning Hybrid 50-50 and Layer 1 to achieve target:
CAGR: 21% - 23%+
Max Drawdown: < 25% - 28%
"""
from pathlib import Path
import pandas as pd
import numpy as np

def compute_cagr(start_val: float, end_val: float, years: float) -> float:
    if start_val <= 0 or end_val <= 0 or years <= 0:
        return 0.0
    return ((end_val / start_val) ** (1.0 / years) - 1.0) * 100.0

def compute_max_drawdown(equity_series: pd.Series) -> float:
    roll_max = equity_series.cummax()
    drawdown = (equity_series - roll_max) / roll_max
    return float(drawdown.min()) * 100.0

def run_fine_tune():
    data_dir = Path("data/cache/historical_2015_2026")
    bars = pd.read_parquet(data_dir / "market_bars_2015_2026.parquet")
    bankrupt_bars = pd.read_parquet(data_dir / "bankrupt_bars_2015_2026.parquet")
    all_bars = pd.concat([bars, bankrupt_bars], ignore_index=True).sort_values(["symbol", "date"]).reset_index(drop=True)
    all_bars["date"] = pd.to_datetime(all_bars["date"]).dt.tz_localize(None)

    bench = pd.read_parquet(data_dir / "nifty50_bench_2015_2026.parquet")
    bench["date"] = pd.to_datetime(bench["date"]).dt.tz_localize(None)
    bench = bench.sort_values("date").reset_index(drop=True)
    bench["ema50"] = bench["close"].ewm(span=50, adjust=False).mean()
    bench["ema200"] = bench["close"].ewm(span=200, adjust=False).mean()
    bench["regime_ok"] = (bench["close"] > bench["ema50"]) | (bench["close"] > bench["ema200"])
    bench_regime = bench.set_index("date")["regime_ok"].to_dict()
    bench_ret20 = bench.set_index("date")["close"].pct_change(20)

    # Compute indicators per symbol
    symbol_frames = {}
    for sym, grp in all_bars.groupby("symbol"):
        df = grp.sort_values("date").reset_index(drop=True)
        if len(df) < 40:
            continue
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

    all_dates = sorted(all_bars["date"].unique())

    def simulate(mode: str, max_slots: int, t2_day: int = 10, sl_pct: float = 0.08):
        initial_capital = 1_000_000.0
        cash = initial_capital
        slot_alloc_pct = 1.0 / max_slots
        cost_factor = 0.0015

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
                if cur_date in symbol_frames[s].index else pos["invested"]
                for s, pos in active_pos.items()
            )
            total_equity_open = cash + mtm_open

            # A. Process Tranche 2 for HYBRID_5050 at open
            if mode == "HYBRID_5050":
                for sym in existing_syms:
                    pos = active_pos[sym]
                    if pos.get("t2_eligible") and not pos.get("t2_active"):
                        pos["t2_eligible"] = False
                        s_df = symbol_frames[sym]
                        if cur_date in s_df.index:
                            b = s_df.loc[cur_date]
                            b_open = float(b["open"])
                            b_high = float(b["high"])
                            b_low = float(b["low"])
                            if not (b_open == b_high and b_high == b_low):
                                t2_alloc = min(available_cash, total_equity_open * (slot_alloc_pct * 0.5))
                                if t2_alloc >= 5_000:
                                    t2_entry = b_open * (1.0 + cost_factor)
                                    t2_shares = t2_alloc / t2_entry
                                    cash -= t2_alloc
                                    available_cash -= t2_alloc
                                    pos["shares"] += t2_shares
                                    pos["invested"] += t2_alloc
                                    pos["blended_entry"] = pos["invested"] / pos["shares"]
                                    pos["t2_active"] = True

            # B. New Entries from previous day signal
            if d_idx > 0 and available_slots > 0 and available_cash >= 5_000 and regime_ok:
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
                    if available_slots <= 0 or available_cash < 5_000:
                        break
                    sym = cand["symbol"]
                    s_df = symbol_frames[sym]
                    if cur_date not in s_df.index:
                        continue
                    b = s_df.loc[cur_date]
                    c_open = float(b["open"])
                    c_high = float(b["high"])
                    c_low = float(b["low"])
                    if c_open == c_high and c_high == c_low:
                        continue

                    if mode == "HYBRID_5050":
                        alloc = min(available_cash, total_equity_open * (slot_alloc_pct * 0.5))
                        if alloc < 2_500:
                            continue
                        entry_p = c_open * (1.0 + cost_factor)
                        shares = alloc / entry_p
                        cash -= alloc
                        available_cash -= alloc
                        available_slots -= 1
                        active_pos[sym] = {
                            "symbol": sym, "entry_date": cur_date, "entry_price": entry_p,
                            "shares": shares, "invested": alloc, "blended_entry": entry_p,
                            "peak_price": entry_p, "days_held": 0, "t2_active": False,
                        }

            # C. Evaluate Exits for existing positions
            closed_syms = []
            for sym in existing_syms:
                pos = active_pos[sym]
                s_df = symbol_frames[sym]
                if cur_date not in s_df.index:
                    continue
                bar = s_df.loc[cur_date]
                cur_open = float(bar["open"])
                cur_high = float(bar["high"])
                cur_low = float(bar["low"])
                cur_close = float(bar["close"])

                prior_peak = pos["peak_price"]
                peak_gain_pct = (prior_peak / pos["blended_entry"] - 1.0) * 100.0
                dip_from_peak_pct = (cur_close / prior_peak - 1.0) * 100.0

                if peak_gain_pct >= 100.0:
                    trail_buffer = 20.0
                elif peak_gain_pct >= 50.0:
                    trail_buffer = 17.0
                elif peak_gain_pct >= 25.0:
                    trail_buffer = 14.0
                else:
                    trail_buffer = None

                exit_triggered = False
                exit_price = 0.0

                # Check Pyramiding Tranche 2 eligibility
                if mode == "HYBRID_5050" and not pos["t2_active"] and pos["days_held"] >= (t2_day - 1):
                    if cur_close > pos["entry_price"] and cur_low > pos["entry_price"] * (1.0 - sl_pct):
                        pos["t2_eligible"] = True

                # 1. Hard Initial Stop Loss
                if (cur_low <= pos["blended_entry"] * (1.0 - sl_pct)) and (peak_gain_pct < 15.0):
                    exit_triggered = True
                    fill_price = min(pos["blended_entry"] * (1.0 - sl_pct), cur_open)
                    exit_price = fill_price * (1.0 - cost_factor)

                # 2. Breakeven Stop
                elif (peak_gain_pct >= 15.0) and (trail_buffer is None) and (cur_low <= pos["blended_entry"]):
                    exit_triggered = True
                    fill_price = min(pos["blended_entry"], cur_open)
                    exit_price = fill_price * (1.0 - cost_factor)

                # 3. Dynamic Growth-Trailing Exit
                elif (trail_buffer is not None) and (dip_from_peak_pct <= -trail_buffer):
                    exit_triggered = True
                    exit_price = min(cur_open, cur_close) * (1.0 - cost_factor) if cur_open < cur_close else cur_close * (1.0 - cost_factor)

                # 4. Stagnation Timeout (30 days)
                elif (pos["days_held"] >= 30) and (peak_gain_pct < 10.0):
                    exit_triggered = True
                    exit_price = cur_close * (1.0 - cost_factor)

                if exit_triggered:
                    proceeds = pos["shares"] * exit_price
                    cash += proceeds
                    net_pnl = proceeds - pos["invested"]
                    net_ret_pct = (net_pnl / pos["invested"]) * 100.0
                    closed_trades.append({"net_return_pct": net_ret_pct, "win": net_ret_pct > 0})
                    closed_syms.append(sym)
                else:
                    if cur_high > pos["peak_price"]:
                        pos["peak_price"] = cur_high
                    pos["days_held"] += 1

            for sym in closed_syms:
                del active_pos[sym]

            for sym, pos in active_pos.items():
                if sym not in existing_syms:
                    s_df = symbol_frames[sym]
                    if cur_date in s_df.index:
                        b = s_df.loc[cur_date]
                        if float(b["high"]) > pos["peak_price"]:
                            pos["peak_price"] = float(b["high"])

            mtm_val = 0.0
            for sym, pos in active_pos.items():
                s_df = symbol_frames[sym]
                c_val = float(s_df.loc[cur_date, "close"]) if cur_date in s_df.index else pos["blended_entry"]
                mtm_val += pos["shares"] * c_val
            equity_hist.append({"date": cur_date, "equity": cash + mtm_val})

        eq_s = pd.DataFrame(equity_hist).set_index("date")["equity"]
        final_cap = float(eq_s.iloc[-1])
        years = (all_dates[-1] - all_dates[0]).days / 365.25
        cagr = compute_cagr(initial_capital, final_cap, years)
        mdd = compute_max_drawdown(eq_s)
        tdf = pd.DataFrame(closed_trades)
        win_rate = (tdf["win"].mean() * 100.0) if len(tdf) > 0 else 0.0

        return {
            "slots": max_slots, "t2_day": t2_day, "sl": sl_pct,
            "cagr": cagr, "max_drawdown": mdd, "final_capital": final_cap,
            "trades": len(tdf), "win_rate": win_rate,
        }

    print("\n" + "=" * 90)
    print("HYBRID 50-50 PARAMETER TUNING ON 2015-2026 (11.8 YEARS)")
    print("=" * 90)

    for slots in [7, 8, 10, 12]:
        for t2_d in [7, 10]:
            for sl in [0.07, 0.08]:
                r = simulate("HYBRID_5050", max_slots=slots, t2_day=t2_d, sl_pct=sl)
                print(f"Slots: {r['slots']:2d} | Tranche2 Day: {r['t2_day']:2d} | SL: {r['sl']*100:.0f}% | CAGR: {r['cagr']:6.2f}% | MaxDD: {r['max_drawdown']:6.2f}% | Final: Rs {r['final_capital']/100000:6.1f}L | Trades: {r['trades']:3d} | WinRate: {r['win_rate']:.1f}%")

if __name__ == "__main__":
    run_fine_tune()
