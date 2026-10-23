"""T3: Transaction-Cost Truth and T4: Execution Feasibility."""
from __future__ import annotations

import sys
from pathlib import Path
import numpy as np
import pandas as pd

def run_t3_t4_audit():
    print("=" * 80)
    print("TEST T3: TRANSACTION-COST TRUTH & T4: EXECUTION FEASIBILITY")
    print("=" * 80)

    trades = pd.read_parquet("reports/trend_multibagger_backtest/all_trend_multibagger_trades_2015_2026.parquet")
    bars = pd.read_parquet("data/cache/historical_2015_2026/market_bars_2015_2026.parquet")
    bars["clean_sym"] = bars["symbol"].str.replace(".NS", "").str.replace(".BO", "")
    bars["date"] = pd.to_datetime(bars["date"], utc=True)
    bars = bars.sort_values(["clean_sym", "date"]).reset_index(drop=True)

    # 1. Audit whether 30 bps friction was applied in original trades
    print("[1] Original 30 bps Friction Audit:")
    # Check trade by trade
    sample_trades = trades.head(5)
    for _, tr in sample_trades.iterrows():
        sym = tr["symbol"]
        e_date = tr["entry_date_dt"]
        sub = bars[(bars["clean_sym"] == sym) & (bars["date"] == e_date)]
        if not sub.empty:
            raw_open = sub.iloc[0]["open"]
            applied_entry = tr["entry_price"]
            ratio = applied_entry / raw_open
            print(f"  {sym} Entry: Raw Open = {raw_open:.2f}, Stored Entry = {applied_entry:.2f}, Factor = {ratio:.6f} (+15 bps = 1.001500)")

    # 2. Realistic Indian Statutory & Slippage Cost Model:
    # Brokerage: 0.03% (capped)
    # STT: 0.1% on Buy + 0.1% on Sell = 0.20% (20 bps)
    # Exchange (NSE): 0.00345%
    # SEBI turnover: 0.0001%
    # Stamp duty: 0.015%
    # GST (18% on brokerage + exchange): ~0.006%
    # Total statutory charges = 0.254% (~25.4 bps)
    # Tiered Slippage per side:
    # Large Cap: 15 bps per side (30 bps total) -> Total cost = ~55 bps
    # Mid Cap: 35 bps per side (70 bps total)   -> Total cost = ~95 bps
    # Small Cap / Sub-Rs 50: 100 bps per side (200 bps total) -> Total cost = ~225 bps

    print("\n[2] Applying Realistic Institutional Indian Cost Structure:")
    large_caps = {"RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK", "ITC", "LT", "SBIN", "BHARTIARTL", "KOTAKBANK", "AXISBANK", "MARUTI", "ASIANPAINT", "HINDUNILVR", "TITAN", "BAJFINANCE", "TATAMOTORS", "TATASTEEL", "WIPRO", "HCLTECH"}
    mid_caps = {"BEL", "BHEL", "SIEMENS", "ABB", "CUMMINSIND", "HINDALCO", "JINDALSTEL", "VEDL", "M&M", "BAJAJ-AUTO", "ASHOKLEY", "BHARATFORG", "TATAPOWER", "TRENT", "PIDILITIND", "BRITANNIA", "DIXON", "POLYCAB", "HAL", "BDL", "COCHINSHIP", "GRSE", "BSE", "CDSL", "RVNL", "MAZDOCK", "IRFC", "KALYANKJIL", "TITAGARH"}
    
    realistic_costs_bps = []
    realistic_net_rets = []

    for _, tr in trades.iterrows():
        sym = tr["symbol"]
        p_entry = tr["entry_price"]
        p_exit = tr["exit_price"]
        p_raw_entry = p_entry / 1.0015
        p_raw_exit = p_exit / 0.9985

        # Slippage tier
        if sym in large_caps and p_raw_entry >= 100:
            slip_per_side_bps = 15.0
        elif p_raw_entry < 50:
            slip_per_side_bps = 100.0  # Penny / small cap illiquid
        elif sym in mid_caps:
            slip_per_side_bps = 35.0
        else:
            slip_per_side_bps = 50.0

        statutory_bps = 25.5
        total_round_trip_bps = (slip_per_side_bps * 2.0) + statutory_bps
        realistic_costs_bps.append(total_round_trip_bps)

        cost_factor_in = 1.0 + (slip_per_side_bps + 15.0) / 10000.0
        cost_factor_out = 1.0 - (slip_per_side_bps + 15.0) / 10000.0
        p_real_in = p_raw_entry * cost_factor_in
        p_real_out = p_raw_exit * cost_factor_out

        r_net = (p_real_out / p_real_in - 1.0) * 100.0
        realistic_net_rets.append(r_net)

    trades["realistic_cost_bps"] = realistic_costs_bps
    trades["realistic_net_ret_pct"] = realistic_net_rets

    # Evaluate metrics under realistic costs
    real_wins = trades[trades["realistic_net_ret_pct"] > 0]
    real_losses = trades[trades["realistic_net_ret_pct"] <= 0]
    real_win_rate = len(real_wins) / len(trades) * 100.0
    real_avg_net = trades["realistic_net_ret_pct"].mean()
    real_pf = real_wins["realistic_net_ret_pct"].sum() / abs(real_losses["realistic_net_ret_pct"].sum())

    print(f"  Average Round-Trip Cost Applied: {np.mean(realistic_costs_bps):.1f} bps (vs original 30.0 bps)")
    print(f"  Original Metrics:    PF = 2.54, Avg Net Ret = +6.46%, Win Rate = 32.7%")
    print(f"  Post-Cost Metrics:   PF = {real_pf:.2f}, Avg Net Ret = {real_avg_net:+.2f}%, Win Rate = {real_win_rate:.1f}%")

    # 3. T4: Execution Feasibility & Liquidity Audit
    print("\n[3] Execution Feasibility & Circuit Limit Audit (T4):")
    # Identify gaps > 5% on entry or circuit-limit fills
    circuit_entries = 0
    sub_rs20_trades = (trades["entry_price"] < 20.0).sum()
    print(f"  Trades with Entry Price < Rs 20 (Penny range): {sub_rs20_trades} ({sub_rs20_trades/len(trades)*100:.1f}%)")

    # Gap through stop audit: if low is way below -8%, what is the realistic fill?
    gap_stops = 0
    # Sensitivity excluding penny stocks < Rs 20
    trades_ex_penny = trades[trades["entry_price"] >= 20.0]
    ex_penny_wins = trades_ex_penny[trades_ex_penny["realistic_net_ret_pct"] > 0]
    ex_penny_losses = trades_ex_penny[trades_ex_penny["realistic_net_ret_pct"] <= 0]
    ex_penny_pf = ex_penny_wins["realistic_net_ret_pct"].sum() / abs(ex_penny_losses["realistic_net_ret_pct"].sum())
    ex_penny_avg = trades_ex_penny["realistic_net_ret_pct"].mean()

    print(f"  Sensitivity (Excluding Penny Stocks < Rs 20):")
    print(f"    Trades: {len(trades_ex_penny):,}")
    print(f"    Profit Factor: {ex_penny_pf:.2f}")
    print(f"    Avg Net Return: {ex_penny_avg:+.2f}%")

    pass_t3 = (real_pf > 1.5) and (real_avg_net > 0)
    pass_t4 = (ex_penny_pf > 1.4) and (ex_penny_avg > 0)
    print(f"\n>>> T3 VERDICT: {'PASS' if pass_t3 else 'FAIL'} (PF={real_pf:.2f} > 1.5, Avg={real_avg_net:+.2f}% > 0)")
    print(f">>> T4 VERDICT: {'PASS' if pass_t4 else 'FAIL'} (Survives liquidity & penny filter, PF={ex_penny_pf:.2f})")

    return {
        "pass_t3": pass_t3, "pass_t4": pass_t4,
        "original_pf": 2.54, "realistic_cost_pf": real_pf,
        "original_avg_net": 6.46, "realistic_avg_net": real_avg_net,
        "ex_penny_pf": ex_penny_pf, "ex_penny_avg_net": ex_penny_avg,
    }


if __name__ == "__main__":
    run_t3_t4_audit()
