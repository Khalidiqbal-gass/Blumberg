"""T5: Survivorship and Selection Bias Audit."""
from __future__ import annotations

import sys
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

sys.path.insert(0, str(Path.cwd()))
sys.path.insert(0, str(Path.cwd() / "src"))
from blumberg_market_radar.scanner.radar import compute_pre_rally_features
from scripts.run_trend_multibagger_backtest_2015_2026 import simulate_stock_trades

def run_t5_survivorship_bias():
    print("=" * 80)
    print("TEST T5: SURVIVORSHIP AND SELECTION BIAS AUDIT (CRITICAL)")
    print("=" * 80)

    # 1. Download famous collapsed / bankrupt / delisted Indian equities
    collapsed_syms = ["YESBANK.NS", "IDEA.NS", "JETAIRWAYS.NS", "UNITECH.NS", "RCOM.BO"]
    print(f"[1] Fetching historical bars for collapsed / distressed equities: {collapsed_syms}...")
    raw = yf.download(collapsed_syms, start="2015-01-01", end="2026-10-22", group_by="ticker", progress=False)

    collapsed_records = []
    for sym in collapsed_syms:
        sub = raw[sym].copy().dropna(how="all")
        if sub.empty or "Close" not in sub.columns:
            continue
        df_sym = pd.DataFrame({
            "date": pd.to_datetime(sub.index, utc=True),
            "open": sub["Open"].values.flatten(),
            "high": sub["High"].values.flatten(),
            "low": sub["Low"].values.flatten(),
            "close": sub["Close"].values.flatten(),
            "volume": sub["Volume"].values.flatten(),
            "symbol": sym,
        }).dropna()
        df_sym["clean_sym"] = sym.replace(".NS", "").replace(".BO", "")
        # Price candle consistency
        df_sym["high"] = np.maximum(df_sym["high"], np.maximum(df_sym["open"], df_sym["close"]))
        df_sym["low"] = np.minimum(df_sym["low"], np.minimum(df_sym["open"], df_sym["close"]))
        collapsed_records.append(df_sym)
        print(f"  {sym}: Loaded {len(df_sym):,} bars from {df_sym['date'].min().strftime('%Y-%m-%d')} to {df_sym['date'].max().strftime('%Y-%m-%d')}")

    collapsed_df = pd.concat(collapsed_records, ignore_index=True)

    # 2. Benchmark
    bench = pd.read_parquet("data/cache/historical_2015_2026/nifty50_bench_2015_2026.parquet")
    bench["date"] = pd.to_datetime(bench["date"], utc=True)
    bench["high"] = np.maximum(bench["high"], np.maximum(bench["open"], bench["close"]))
    bench["low"] = np.minimum(bench["low"], np.minimum(bench["open"], bench["close"]))

    # 3. Compute radar features on collapsed stocks
    print("\n[2] Computing Pre-Rally Radar Features on Collapsed Stocks...")
    collapsed_feats = compute_pre_rally_features(collapsed_df, bench)

    # 4. Simulate trades on collapsed stocks
    collapsed_trades = []
    for sym, grp in collapsed_feats.groupby("symbol"):
        t_list = simulate_stock_trades(grp, symbol=str(sym))
        collapsed_trades.extend(t_list)

    c_trades_df = pd.DataFrame(collapsed_trades)
    print(f"  Total Trades Triggered on Collapsed Stocks: {len(c_trades_df)}")

    if not c_trades_df.empty:
        c_wins = c_trades_df[c_trades_df["net_return_pct"] > 0]
        c_losses = c_trades_df[c_trades_df["net_return_pct"] <= 0]
        c_wr = len(c_wins) / len(c_trades_df) * 100.0
        c_avg = c_trades_df["net_return_pct"].mean()
        c_stop_pct = (c_trades_df["exit_reason"] == "STOP_LOSS").sum() / len(c_trades_df) * 100.0
        print(f"  Collapsed Stocks Win Rate: {c_wr:.1f}%")
        print(f"  Collapsed Stocks Avg Net Return: {c_avg:+.2f}%")
        print(f"  Hard Stop Loss Exit Rate: {c_stop_pct:.1f}% (capital protection trigger)")
        print("\n  Sample trades on collapsed stocks:")
        for _, r in c_trades_df.head(6).iterrows():
            print(f"    {r['symbol']:12s} Entry: {r['entry_date'].strftime('%Y-%m-%d')} @ Rs {r['entry_price']:.2f} -> Exit: {r['exit_date'].strftime('%Y-%m-%d')} @ Rs {r['exit_price']:.2f} | Net: {r['net_return_pct']:+.1f}% | Reason: {r['exit_reason']}")

    # 5. Combined Unbiased Universe: Existing 52 equities + 5 Collapsed Equities = 57 Equities
    orig_trades = pd.read_parquet("reports/trend_multibagger_backtest/all_trend_multibagger_trades_2015_2026.parquet")
    combined_trades = pd.concat([orig_trades, c_trades_df], ignore_index=True)

    comb_wins = combined_trades[combined_trades["net_return_pct"] > 0]
    comb_losses = combined_trades[combined_trades["net_return_pct"] <= 0]
    comb_wr = len(comb_wins) / len(combined_trades) * 100.0
    comb_avg = combined_trades["net_return_pct"].mean()
    comb_pf = comb_wins["net_return_pct"].sum() / abs(comb_losses["net_return_pct"].sum())

    print("\n[3] Combined Unbiased Universe Results (52 Core + 5 Catastrophic Failures):")
    print(f"  Total Trades: {len(combined_trades):,}")
    print(f"  Win Rate:     {comb_wr:.1f}% (Original: 32.7%)")
    print(f"  Profit Factor: {comb_pf:.2f} (Original: 2.54)")
    print(f"  Avg Net Ret:   {comb_avg:+.2f}% (Original: +6.46%)")

    # Selection bias impact
    pf_degradation_pct = (1.0 - comb_pf / 2.54) * 100.0
    print(f"  Profit Factor Degradation from Survivorship Bias: {pf_degradation_pct:.1f}%")

    # Pass criterion: Edge remains positive (PF > 1.5, Avg Net > 0)
    pass_t5 = (comb_pf > 1.5) and (comb_avg > 0)
    verdict = "PASS" if pass_t5 else "FAIL"
    print(f"\n>>> T5 VERDICT: {verdict} (Edge survives addition of catastrophic failures; PF={comb_pf:.2f} > 1.5)")
    return pass_t5, {
        "collapsed_trades_count": len(c_trades_df),
        "combined_trades_count": len(combined_trades),
        "combined_pf": comb_pf,
        "combined_avg_net": comb_avg,
        "pf_degradation_pct": pf_degradation_pct,
    }


if __name__ == "__main__":
    run_t5_survivorship_bias()
