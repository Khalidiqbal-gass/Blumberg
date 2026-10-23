"""Complete, unabridged 2015-2026 institutional backtest audit and code execution."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
import numpy as np
import pandas as pd
import yfinance as yf

sys.path.insert(0, str(Path.cwd()))
sys.path.insert(0, str(Path.cwd() / "src"))

from blumberg_market_radar.data.ingestion import get_symbol_sector_map
from blumberg_market_radar.data.validation import validate_ohlcv, detect_corporate_action_anomalies
from blumberg_market_radar.features.technical import build_daily_features, baseline_early_rally_signal
from blumberg_market_radar.backtest.baseline import (
    DEFAULT_INDIAN_STATUTORY_BPS_PER_SIDE,
    simulate_multiday_trend_trades,
)

def load_or_fetch_combined_universe() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Load 52 primary equities + 5 bankrupt stocks + NIFTY 50 & NIFTY 500 benchmarks."""
    print("Loading primary 52-equity dataset...")
    primary_bars = pd.read_parquet("data/cache/historical_2015_2026/market_bars_2015_2026.parquet")
    primary_bars["clean_sym"] = primary_bars["symbol"].str.replace(".NS", "").str.replace(".BO", "")
    primary_bars["date"] = pd.to_datetime(primary_bars["date"], utc=True)

    # 5 Catastrophic Bankrupt / Collapsed Equities
    bankrupt_cache_path = Path("data/cache/historical_2015_2026/bankrupt_bars_2015_2026.parquet")
    if bankrupt_cache_path.exists():
        print("Loading cached 5 bankrupt equities...")
        bankrupt_bars = pd.read_parquet(bankrupt_cache_path)
        bankrupt_bars["date"] = pd.to_datetime(bankrupt_bars["date"], utc=True)
    else:
        print("Fetching 5 bankrupt equities from Yahoo Finance (YESBANK, IDEA, JETAIRWAYS, UNITECH, RCOM)...")
        b_syms = ["YESBANK.NS", "IDEA.NS", "JETAIRWAYS.NS", "UNITECH.NS", "RCOM.BO"]
        b_raw = yf.download(b_syms, start="2015-01-01", end="2026-10-22", group_by="ticker", progress=False)
        b_records = []
        for s in b_syms:
            sub = b_raw[s].copy().dropna(how="all")
            if sub.empty or "Close" not in sub.columns:
                continue
            df_s = pd.DataFrame({
                "date": pd.to_datetime(sub.index, utc=True),
                "open": sub["Open"].values.flatten(),
                "high": sub["High"].values.flatten(),
                "low": sub["Low"].values.flatten(),
                "close": sub["Close"].values.flatten(),
                "volume": sub["Volume"].values.flatten(),
                "symbol": s,
            }).dropna()
            df_s["clean_sym"] = s.replace(".NS", "").replace(".BO", "")
            df_s["high"] = np.maximum(df_s["high"], np.maximum(df_s["open"], df_s["close"]))
            df_s["low"] = np.minimum(df_s["low"], np.minimum(df_s["open"], df_s["close"]))
            b_records.append(df_s)
        bankrupt_bars = pd.concat(b_records, ignore_index=True)
        bankrupt_bars.to_parquet(bankrupt_cache_path)

    # Combine 52 + 5 = 57 stocks
    all_bars = pd.concat([primary_bars, bankrupt_bars], ignore_index=True)
    all_bars = all_bars.sort_values(["clean_sym", "date"]).reset_index(drop=True)
    print(f"Total Combined Universe: {all_bars['clean_sym'].nunique()} equities, {len(all_bars):,} bars.")

    # Benchmarks
    nifty50 = pd.read_parquet("data/cache/historical_2015_2026/nifty50_bench_2015_2026.parquet")
    nifty50["date"] = pd.to_datetime(nifty50["date"], utc=True)
    nifty50 = nifty50.sort_values("date").reset_index(drop=True)

    nifty500_cache = Path("data/cache/historical_2015_2026/nifty500_bench_2015_2026.parquet")
    if nifty500_cache.exists():
        nifty500 = pd.read_parquet(nifty500_cache)
        nifty500["date"] = pd.to_datetime(nifty500["date"], utc=True)
    else:
        print("Fetching NIFTY 500 (^CRSLDX) benchmark...")
        n500_raw = yf.download("^CRSLDX", start="2015-01-01", end="2026-10-22", progress=False)
        nifty500 = pd.DataFrame({
            "date": pd.to_datetime(n500_raw.index, utc=True),
            "close": n500_raw["Close"].values.flatten(),
        }).dropna().sort_values("date").reset_index(drop=True)
        nifty500.to_parquet(nifty500_cache)

    return all_bars, nifty50, nifty500


def run_full_backtest_audit():
    print("=" * 80)
    print("EXECUTING 2015-2026 FULL INSTITUTIONAL AUDIT WITH REMEDIATED ENGINE")
    print("=" * 80)

    bars, nifty50, nifty500 = load_or_fetch_combined_universe()
    sector_map = get_symbol_sector_map(include_nifty500=True)

    # 1. Feature Calculation with Calendar Gap & Anti-Chasing VCP Filter
    print("\n[Step 1] Building daily features and hardened early-rally signals...")
    feature_dfs = []
    for sym, group in bars.groupby("clean_sym", sort=False):
        f = build_daily_features(group, max_calendar_gap_5d=15, max_calendar_gap_20d=45)
        # Apply hardened baseline signal with VCP cap (return_20d <= 0.35) and circuit suppression
        f["signal"] = baseline_early_rally_signal(
            f,
            min_relative_volume=1.5,
            max_return_20d=0.35,  # Anti-Chasing VCP Upper Bound
            suppress_circuits=True
        )
        feature_dfs.append(f)

    bars_with_signals = pd.concat(feature_dfs, ignore_index=True)
    total_signals = int(bars_with_signals["signal"].sum())
    print(f"Total Early-Rally Pre-Breakout Signals Generated: {total_signals:,}")

    # 2. Multi-Day Trend Simulation Engine
    print("\n[Step 2] Executing simulate_multiday_trend_trades() across 57 stocks...")
    sim_result = simulate_multiday_trend_trades(
        bars_with_signals,
        signal_column="signal",
        cost_bps_per_side=DEFAULT_INDIAN_STATUTORY_BPS_PER_SIDE, # 52.6 bps per side = 105.2 bps round trip
        initial_stop_pct=-8.0,
        breakeven_trigger_pct=15.0,
        trailing_trigger_pct=25.0,
        trail_tier1_pct=-14.0,
        trail_tier2_trigger_pct=50.0,
        trail_tier2_pct=-17.0,
        trail_tier3_trigger_pct=100.0,
        trail_tier3_pct=-20.0,
        stagnation_days=30,
        stagnation_min_gain_pct=10.0,
        suppress_overlapping=True,
        reject_upper_circuit_entry=True,
    )

    trades_df = sim_result["trades"]
    trades_df["entry_date"] = pd.to_datetime(trades_df["entry_date"], utc=True)
    trades_df["exit_date"] = pd.to_datetime(trades_df["exit_date"], utc=True)
    trades_df["entry_year"] = trades_df["entry_date"].dt.year
    trades_df["exit_year"] = trades_df["exit_date"].dt.year
    trades_df["clean_sym"] = trades_df["symbol"].str.replace(".NS", "").str.replace(".BO", "")
    trades_df["sector"] = trades_df["clean_sym"].map(lambda s: sector_map.get(s, "Diversified / Growth"))

    # Map sector for bankrupt stocks explicitly if missing
    bankrupt_sector_map = {
        "YESBANK": "Banking & Finance (Distressed)",
        "IDEA": "Telecom (Distressed)",
        "JETAIRWAYS": "Aviation (Insolvent)",
        "UNITECH": "Real Estate (Defaulted)",
        "RCOM": "Telecom (Insolvent)",
    }
    for b_sym, sec in bankrupt_sector_map.items():
        trades_df.loc[trades_df["clean_sym"] == b_sym, "sector"] = sec

    # Calculate Gross Return and Fee Drag
    one_side = DEFAULT_INDIAN_STATUTORY_BPS_PER_SIDE / 10_000.0
    # Entry Price has 1 + one_side; Exit Price has 1 - one_side
    raw_entry = trades_df["entry_price"] / (1.0 + one_side)
    raw_exit = trades_df["exit_price"] / (1.0 - one_side)
    trades_df["gross_return_pct"] = (raw_exit / raw_entry - 1.0) * 100.0
    trades_df["fee_drag_pct"] = trades_df["gross_return_pct"] - trades_df["net_return_pct"]

    print(f"Executed Trades: {len(trades_df):,}")
    print(f"Unfilled (Upper Circuit): {sim_result['unfilled_circuit_count']}")
    print(f"Profit Factor: {sim_result['profit_factor']:.2f}")
    print(f"Win Rate: {sim_result['win_rate']:.1f}%")
    print(f"Average Net Return: {sim_result['avg_net_return']:+.2f}%\n")

    out_dir = Path("reports/audit_2015_2026")
    out_dir.mkdir(parents=True, exist_ok=True)
    trades_df.to_csv(out_dir / "all_trades_ledger_2015_2026.csv", index=False)
    print(f"Exported detailed trade ledger to {out_dir / 'all_trades_ledger_2015_2026.csv'}")

    return {
        "trades": trades_df,
        "bars": bars_with_signals,
        "nifty50": nifty50,
        "nifty500": nifty500,
        "unfilled_circuit_count": sim_result["unfilled_circuit_count"],
        "sector_map": sector_map,
        "bankrupt_sector_map": bankrupt_sector_map,
    }

if __name__ == "__main__":
    run_full_backtest_audit()
