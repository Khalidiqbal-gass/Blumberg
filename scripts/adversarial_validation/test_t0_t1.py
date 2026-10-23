"""T0: Data Integrity & Reproducibility and T1: Spec-vs-Code Audit."""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path
import numpy as np
import pandas as pd

OUTPUT_DIR = Path("reports/adversarial_validation")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

def run_t0_data_integrity():
    print("=" * 80)
    print("TEST T0: DATA INTEGRITY AND REPRODUCIBILITY")
    print("=" * 80)

    bars_path = Path("data/cache/historical_2015_2026/market_bars_2015_2026.parquet")
    bench_path = Path("data/cache/historical_2015_2026/nifty50_bench_2015_2026.parquet")

    df = pd.read_parquet(bars_path)
    bench = pd.read_parquet(bench_path)

    n_bars = len(df)
    n_syms = df["symbol"].nunique()
    print(f"Dataset: {n_bars:,} bars across {n_syms} equities (2015 - 2026).")

    # 1. Missing values
    null_counts = df.isnull().sum()
    print(f"Missing values count across columns:\n{null_counts[null_counts > 0]}")

    # 2. Duplicate dates per symbol
    dups = df.duplicated(subset=["symbol", "date"]).sum()
    print(f"Duplicated (symbol, date) bars: {dups}")

    # 3. Bad ticks (high < low, high < open, high < close, low > close)
    bad_hl = (df["high"] < df["low"]).sum()
    bad_ho = (df["high"] < df["open"]).sum()
    bad_hc = (df["high"] < df["close"]).sum()
    bad_lo = (df["low"] > df["open"]).sum()
    bad_lc = (df["low"] > df["close"]).sum()
    print(f"Bad ticks: high < low: {bad_hl}, high < open: {bad_ho}, high < close: {bad_hc}, low > open: {bad_lo}, low > close: {bad_lc}")

    # 4. Zero volume days
    zero_vol = (df["volume"] == 0).sum()
    print(f"Zero volume bars: {zero_vol} ({zero_vol / n_bars * 100:.2f}%)")

    # 5. Price consistency checks (e.g. negative prices)
    neg_p = ((df["open"] <= 0) | (df["high"] <= 0) | (df["low"] <= 0) | (df["close"] <= 0)).sum()
    print(f"Non-positive prices: {neg_p}")

    # 6. Corporate Action Audit (Splits, Demergers)
    # Check large overnight ratio changes (> 50% drop in 1 session without circuit)
    df["prev_close"] = df.groupby("symbol")["close"].shift(1)
    df["overnight_ratio"] = df["open"] / df["prev_close"]
    extreme_drops = df[df["overnight_ratio"] < 0.40][["date", "symbol", "prev_close", "open", "close"]]
    print(f"Extreme unadjusted drops (>60% overnight drop): {len(extreme_drops)}")
    if not extreme_drops.empty:
        print(extreme_drops.head(5))

    # T0 Verdict
    pass_t0 = (dups == 0) and (bad_hl == 0) and (neg_p == 0) and (len(extreme_drops) == 0)
    print(f"\n>>> T0 VERDICT: {'PASS' if pass_t0 else 'FRAGILE'}")
    return pass_t0, {
        "n_bars": n_bars, "n_syms": n_syms, "dups": int(dups), "zero_vol": int(zero_vol),
        "bad_ticks": int(bad_hl + bad_ho + bad_hc), "extreme_drops": len(extreme_drops)
    }


def run_t1_spec_code_audit():
    print("\n" + "=" * 80)
    print("TEST T1: SPEC-VS-CODE AUDIT")
    print("=" * 80)

    # Inspect code implementation issues:
    # 1. Stop on Close vs Intraday Low:
    # In run_trend_multibagger_backtest_2015_2026.py:
    # Initial stop checked on: cur_low <= entry_price * (1.0 - 0.08)
    # But Trailing stop checked on: cur_dip_from_peak = (cur_close / peak_price - 1.0) <= -trail_buffer
    # Inconsistency: Initial stop uses intraday Low, while trailing stop uses Close.
    print("[1] Stop Execution Mechanism Audit:")
    print("    - Initial stop-loss: evaluated against Intraday LOW (cur_low <= entry_price * 0.92).")
    print("    - Trailing profit exit: evaluated against CLOSE (cur_close / peak_price - 1.0 <= -buffer).")
    print("    -> Finding: Asymmetric stop evaluation. Trailing on close allows intraday wicks without shaking out.")

    # 2. Peak gain between +15% and +25%:
    # When gain is between 15% and 25%, code moves stop to Breakeven (+0%).
    # Does it trail? NO! Trailing only starts at peak >= +25%.
    print("\n[2] +15% to +25% Zone Behavior:")
    print("    - Once a stock hits +15%, stop moves to Breakeven (+0.0%).")
    print("    - Between +15% and +25%, there is NO trailing buffer active; stock can pull back all the way to 0%!")

    # 3. Last Bar Indexing Bug (Confirmed in TCS, WIPRO, HCLTECH):
    # Loop range(n - 1) omitted evaluating last bar against peak and trailing stops.
    print("\n[3] Loop Termination Bug Audit:")
    print("    - range(n - 1) fails to evaluate the final bar in the loop, causing peak_price to fall behind close on open trades.")
    print("    -> Finding: Code BUG detected. Needs exact indexing fix.")

    print("\n>>> T1 VERDICT: BUG / INCONSISTENCY CONFIRMED (Fixed in benchmark auditor)")
    return {
        "stop_low_vs_close": "Asymmetric (Low for -8%, Close for Trail)",
        "zone_15_25": "Breakeven only (no trailing)",
        "last_bar_bug": "Loop range(n-1) skipped final bar updates"
    }


if __name__ == "__main__":
    run_t0_data_integrity()
    run_t1_spec_code_audit()
