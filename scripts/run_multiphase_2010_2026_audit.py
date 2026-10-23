"""Comprehensive Multi-Phase Backtest Audit across 16 Years (2010 - 2026).

Executes the Upgraded 5-Stage VCP & Secular Multibagger Engine across the 10 requested timelines:
1. 2010-2012 (Post-GFC Recovery & Stagnation)
2. 2013-2015 (Policy Paralysis & 2014 Modi Election Bull Run)
3. 2016-2018 (Demonetization, GST & 2018 Midcap Bear Market)
4. 2019-2021 (NBFC Freeze, March 2020 Covid Crash & Liquidity Wave)
5. 2022-2024 (Global Rate Tightening & Indian Capex/PSU/Rail Super-Cycle)
6. 2025-2026 (Forward Walk & Current Market Consolidation)
7. 2010-2015 (Macro Era 1: Pre-2015 Foundation - 5.5 Years)
8. 2016-2020 (Macro Era 2: Reform Shocks & Pandemic Stress - 5.0 Years)
9. 2021-2025 (Macro Era 3: Capex, Defense & Retail Super-Cycle - 5.0 Years)
10. 2010-2026 (Full 16.8-Year Complete Multi-Cycle Benchmark)
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
import numpy as np
import pandas as pd

from blumberg_market_radar.backtest.upgraded_vcp_engine import (
    UpgradedVCPBacktestEngine,
    BacktestSummary,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s]: %(message)s")
logger = logging.getLogger("multiphase_audit")

OUTPUT_DIR = Path("reports/secular_longterm_hold")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

PHASES = [
    {
        "phase_num": 1,
        "name": "2010–2012",
        "start": "2010-01-01",
        "end": "2012-12-31",
        "title": "Post-GFC Recovery & Rangebound Consolidation",
        "regime": "Volatile Sideways / Macro Headwinds",
    },
    {
        "phase_num": 2,
        "name": "2013–2015",
        "start": "2013-01-01",
        "end": "2015-12-31",
        "title": "Policy Paralysis to 2014 Modi Election Bull Run",
        "regime": "Momentum Inflection & Election Rally",
    },
    {
        "phase_num": 3,
        "name": "2016–2018",
        "start": "2016-01-01",
        "end": "2018-12-31",
        "title": "Demonetization, GST Boom & 2018 Midcap Bear Market",
        "regime": "Structural Policy Shock & Midcap Divergence",
    },
    {
        "phase_num": 4,
        "name": "2019–2021",
        "start": "2019-01-01",
        "end": "2021-12-31",
        "title": "NBFC Crisis, March 2020 Covid Shock & Massive V-Rally",
        "regime": "Extreme Flash Crash & Historic Liquidity Wave",
    },
    {
        "phase_num": 5,
        "name": "2022–2024",
        "start": "2022-01-01",
        "end": "2024-12-31",
        "title": "Global Rate Tightening & Capex/PSU/Rail Super-Cycle",
        "regime": "Secular Domestic Multibagger Wave",
    },
    {
        "phase_num": 6,
        "name": "2025–2026",
        "start": "2025-01-01",
        "end": "2026-10-21",
        "title": "Forward Walk & Current Market Cycle",
        "regime": "Out-of-Sample Forward Walk / High Valuation Dispersion",
    },
    {
        "phase_num": 7,
        "name": "2010–2015",
        "start": "2010-01-01",
        "end": "2015-12-31",
        "title": "Pre-2015 Era: Stagflation to Political Transition",
        "regime": "Macro 5.5-Year Composite Cycle",
    },
    {
        "phase_num": 8,
        "name": "2016–2020",
        "start": "2016-01-01",
        "end": "2020-12-31",
        "title": "Midcap Bear Market & Global Pandemic Stress Era",
        "regime": "Macro 5.0-Year Crisis & Recovery Cycle",
    },
    {
        "phase_num": 9,
        "name": "2021–2025",
        "start": "2021-01-01",
        "end": "2025-12-31",
        "title": "Post-Covid Capex, Defense, Railway & Retail Boom",
        "regime": "Macro 5.0-Year Secular Bull Super-Cycle",
    },
    {
        "phase_num": 10,
        "name": "2010–2026",
        "start": "2010-01-01",
        "end": "2026-10-21",
        "title": "Complete 16.8-Year Long-Term Multi-Cycle Benchmark",
        "regime": "Full Multi-Decade Secular Compounding",
    },
]


def load_dataset() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load and merge all available historical bars and benchmark data across 2010-2026."""
    b10_path = Path("data/cache/historical_2010_2026/market_bars_2010_2026.parquet")
    b15_path = Path("data/cache/historical_2015_2026/market_bars_2015_2026.parquet")
    bb_path = Path("data/cache/historical_2015_2026/bankrupt_bars_2015_2026.parquet")

    dfs = []
    if b10_path.exists():
        dfs.append(pd.read_parquet(b10_path))
    if b15_path.exists():
        dfs.append(pd.read_parquet(b15_path))
    if bb_path.exists():
        dfs.append(pd.read_parquet(bb_path))

    all_bars = pd.concat(dfs, ignore_index=True)
    all_bars["date"] = pd.to_datetime(all_bars["date"], utc=True)
    all_bars = all_bars.drop_duplicates(subset=["symbol", "date"]).sort_values(["symbol", "date"]).reset_index(drop=True)

    n10_path = Path("data/cache/historical_2010_2026/nifty50_bench_2010_2026.parquet")
    n15_path = Path("data/cache/historical_2015_2026/nifty50_bench_2015_2026.parquet")
    b_dfs = []
    if n10_path.exists():
        b_dfs.append(pd.read_parquet(n10_path))
    if n15_path.exists():
        b_dfs.append(pd.read_parquet(n15_path))

    all_bench = pd.concat(b_dfs, ignore_index=True)
    all_bench["date"] = pd.to_datetime(all_bench["date"], utc=True)
    all_bench = all_bench.drop_duplicates(subset=["date"]).sort_values("date").reset_index(drop=True)

    logger.info(f"Loaded {len(all_bars):,} equity bars ({all_bars['symbol'].nunique()} symbols) and {len(all_bench):,} benchmark bars.")
    return all_bars, all_bench


def run_all_phases():
    all_bars, all_bench = load_dataset()

    engine = UpgradedVCPBacktestEngine(
        initial_capital=1_000_000.0,
        max_slots=15,
        risk_per_trade_pct=0.01,
        min_turnover_rs=30_000_000.0,
        slippage_bps_per_side=50.0,
        statutory_bps_per_side=52.6,
    )

    phase_results = []
    all_phase_trades = []

    print("\n" + "=" * 105)
    print("EXECUTING 10-PHASE HISTORICAL BACKTEST AUDIT (2010 - 2026)")
    print("=" * 105)

    for p in PHASES:
        p_name = p["name"]
        p_start = p["start"]
        p_end = p["end"]
        logger.info(f"Running Phase: {p_name} ({p_start} to {p_end}) - {p['title']}")

        summary: BacktestSummary = engine.run_backtest(
            bars_df=all_bars,
            bench_df=all_bench,
            start_date=p_start,
            end_date=p_end,
        )

        # Calculate total phase return
        phase_net_return = (summary.final_capital / summary.initial_capital - 1.0) * 100.0
        
        # Calculate nifty return
        eq_df = summary.equity_curve
        valid_nifty = eq_df.dropna(subset=["nifty_close"])
        if len(valid_nifty) >= 2:
            n_start = valid_nifty.iloc[0]["nifty_close"]
            n_end = valid_nifty.iloc[-1]["nifty_close"]
            nifty_ret = (n_end / n_start - 1.0) * 100.0
        else:
            nifty_ret = 0.0

        alpha_ret = phase_net_return - nifty_ret

        # Top winners in this phase
        tdf = summary.trades_df.copy()
        top_winners_str = "None"
        if not tdf.empty:
            tdf["phase"] = p_name
            all_phase_trades.append(tdf)
            top3 = tdf.sort_values("net_return_pct", ascending=False).head(3)
            winner_items = [f"{r['symbol']} (+{r['net_return_pct']:.1f}%)" for _, r in top3.iterrows() if r["net_return_pct"] > 0]
            if winner_items:
                top_winners_str = ", ".join(winner_items)

        row = {
            "phase_num": p["phase_num"],
            "phase": p_name,
            "title": p["title"],
            "regime": p["regime"],
            "start_date": p_start,
            "end_date": p_end,
            "start_capital": summary.initial_capital,
            "final_capital": summary.final_capital,
            "model_net_return_pct": phase_net_return,
            "model_cagr_pct": summary.compounded_cagr_pct,
            "nifty_return_pct": nifty_ret,
            "nifty_cagr_pct": summary.nifty_cagr_pct,
            "alpha_cagr_pct": summary.alpha_pct,
            "max_drawdown_pct": summary.max_drawdown_pct,
            "win_rate_pct": summary.win_rate_pct,
            "profit_factor": summary.profit_factor,
            "expectancy_pct": summary.expectancy_pct,
            "total_trades": summary.total_trades,
            "avg_gain_pct": summary.avg_gain_pct,
            "avg_loss_pct": summary.avg_loss_pct,
            "avg_calendar_days": summary.avg_calendar_days,
            "avg_bars_held": summary.avg_bars_held,
            "total_friction_paid": summary.total_friction_paid,
            "top_winners": top_winners_str,
        }
        phase_results.append(row)

        print(f"| {p_name:11} | Ret: {phase_net_return:+7.1f}% | CAGR: {summary.compounded_cagr_pct:+6.1f}% | NiftyRet: {nifty_ret:+6.1f}% | AlphaCAGR: {summary.alpha_pct:+6.1f}% | MaxDD: {summary.max_drawdown_pct:5.1f}% | WR: {summary.win_rate_pct:4.1f}% | PF: {summary.profit_factor:4.2f} | Trades: {summary.total_trades:3d} |")

    phase_df = pd.DataFrame(phase_results)
    csv_path = OUTPUT_DIR / "multiphase_2010_2026_summary.csv"
    phase_df.to_csv(csv_path, index=False)
    logger.info(f"Saved phase summary to {csv_path}")

    if all_phase_trades:
        trades_combined = pd.concat(all_phase_trades, ignore_index=True)
        trades_parquet = OUTPUT_DIR / "multiphase_2010_2026_trades.parquet"
        trades_combined.to_parquet(trades_parquet, index=False)
        logger.info(f"Saved {len(trades_combined)} multi-phase trades to {trades_parquet}")

    print("\n" + "=" * 105)
    print("MASTER 10-PHASE COMPARATIVE TABLE (2010–2026)")
    print("=" * 105)
    display_cols = [
        "phase", "title", "model_net_return_pct", "model_cagr_pct",
        "nifty_return_pct", "nifty_cagr_pct", "alpha_cagr_pct", "max_drawdown_pct",
        "win_rate_pct", "profit_factor", "total_trades"
    ]
    print(phase_df[display_cols].to_string(index=False))
    return phase_df


if __name__ == "__main__":
    run_all_phases()
