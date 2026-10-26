"""
Master Adversarial Multi-Angle Stress Testing & Validation Suite (2000 - 2026).
Conducts institutional stress testing across 5 independent angles:
Angle 1: 10-Phase Market Regime Breakdown (Dot-com, Lehman, Taper Tantrum, DeMod, COVID, etc.)
Angle 2: Monte Carlo Bootstrap Simulation (1,000 Iterations) - 95% Confidence Intervals
Angle 3: Outlier Exclusion Stress Test (Excluding Top 1, Top 3, Top 5 Multibaggers)
Angle 4: Friction Sensitivity Degradation (From 20 bps up to 100 bps slippage)
Angle 5: Stock-Level Multibagger & Downside SL Attribution
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

DATA_DIR = PROJECT_ROOT / "data" / "cache" / "historical_2000_2026"
REPORT_DIR = PROJECT_ROOT / "reports" / "adversarial_champion_audit"
DESKTOP_DIR = Path(r"C:\Users\DELL\OneDrive\Desktop\BLUMBERG_AUDIT_FILES\ADVERSARIAL_CHAMPION_AUDIT")

REPORT_DIR.mkdir(parents=True, exist_ok=True)
DESKTOP_DIR.mkdir(parents=True, exist_ok=True)


def run_full_adversarial_audit():
    print("=" * 115)
    print("         BLUMBERG QUANTITATIVE SYSTEM - MASTER ADVERSARIAL MULTI-ANGLE STRESS TEST")
    print("=" * 115)

    bench_path = DATA_DIR / "sensex_bench_2000_2026.parquet"
    market_path = DATA_DIR / "market_bars_with_delisted_2000_2026.parquet"

    if not bench_path.exists() or not market_path.exists():
        print(f"[ERROR] Missing Parquet files in {DATA_DIR}")
        return

    bench_df = pd.read_parquet(bench_path)
    bars_df = pd.read_parquet(market_path)
    print(f"Loaded {len(bars_df):,} daily bars across {bars_df['symbol'].nunique()} equities.\n")

    # =========================================================================
    # ANGLE 1: 10-PHASE MARKET REGIME STRESS TEST
    # =========================================================================
    print("=" * 115)
    print("ANGLE 1: 10-PHASE MARKET REGIME AUDIT (DOT-COM TO PRESENT)")
    print("=" * 115)

    phases = [
        ("Phase 1: 2000-2003 (Dot-Com Crash & Base)", "2000-01-01", "2003-12-31"),
        ("Phase 2: 2004-2007 (The Great Capex Bull Run)", "2004-01-01", "2007-12-31"),
        ("Phase 3: 2008-2008 (Lehman GFC Global Crash)", "2008-01-01", "2008-12-31"),
        ("Phase 4: 2009-2010 (Post-Crisis QE Rebound)", "2009-01-01", "2010-12-31"),
        ("Phase 5: 2011-2013 (Policy Paralysis & Chop)", "2011-01-01", "2013-12-31"),
        ("Phase 6: 2014-2017 (Modi Bull Run & DeMod)", "2014-01-01", "2017-12-31"),
        ("Phase 7: 2018-2019 (NBFC IL&FS Midcap Carnage)", "2018-01-01", "2019-12-31"),
        ("Phase 8: 2020-2020 (COVID-19 40% Crash & V-Rebound)", "2020-01-01", "2020-12-31"),
        ("Phase 9: 2021-2023 (Post-COVID Retail/PSU Boom)", "2021-01-01", "2023-12-31"),
        ("Phase 10: 2024-2026 (Modern Mega Rally & Expansion)", "2024-01-01", "2026-10-26"),
        ("Phase 11: 2000-2026 (The Complete 26.8-Yr Arc)", "2000-01-01", "2026-10-26"),
    ]

    phase_rows = []
    engine_base = UpgradedVCPBacktestEngine(
        initial_capital=1_000_000.0,
        max_slots=7,
        mode="HYBRID_50_50",
        min_turnover_rs=30_000_000.0,
        slippage_bps_per_side=20.0,
        statutory_bps_per_side=35.0,
        use_equal_weight_slots=True,
        cash_yield_pct_p_a=6.5,
        use_sector_leadership=True,
        tranche2_days=7,
    )

    print(f"{'Market Phase':<45} | {'Years':>5} | {'Final Capital':>13} | {'Mult':>5} | {'CAGR %':>8} | {'Max DD %':>9} | {'Trades':>6} | {'Win %':>6} | {'PF':>5} | {'Payoff':>6}")
    print("-" * 125)

    base_26yr_summary = None

    for label, st, en in phases:
        res = engine_base.run_backtest(bars_df, bench_df, start_date=st, end_date=en)
        if label == "Phase 11: 2000-2026 (The Complete 26.8-Yr Arc)":
            base_26yr_summary = res

        years = max(0.5, (pd.to_datetime(en) - pd.to_datetime(st)).days / 365.25)
        mult = res.final_capital / res.initial_capital
        fin_str = f"Rs {res.final_capital/100000:.1f} L" if res.final_capital < 10_000_000 else f"Rs {res.final_capital/10_000_000:.2f} Cr"

        print(
            f"{label:<45} | {years:>5.1f} | {fin_str:>13} | {mult:>4.1f}x | "
            f"{res.compounded_cagr_pct:>+7.2f}% | {res.max_drawdown_pct:>8.2f}% | "
            f"{res.total_trades:>6} | {res.win_rate_pct:>5.1f}% | {res.profit_factor:>5.2f} | {res.win_loss_ratio:>5.2f}x"
        )

        phase_rows.append({
            "Phase": label,
            "Start_Date": st,
            "End_Date": en,
            "Years": round(years, 1),
            "Initial_Capital_Rs": res.initial_capital,
            "Final_Capital_Rs": round(res.final_capital, 2),
            "Multiple": round(mult, 2),
            "CAGR_Pct": round(res.compounded_cagr_pct, 2),
            "Max_Drawdown_Pct": round(res.max_drawdown_pct, 2),
            "Trades": res.total_trades,
            "Win_Rate_Pct": round(res.win_rate_pct, 2),
            "Profit_Factor": round(res.profit_factor, 2),
            "Payoff_Ratio": round(res.win_loss_ratio, 2),
        })

    phase_df = pd.DataFrame(phase_rows)
    phase_df.to_csv(REPORT_DIR / "ADVERSARIAL_10_PHASES_SUMMARY.csv", index=False)
    phase_df.to_csv(DESKTOP_DIR / "ADVERSARIAL_10_PHASES_SUMMARY.csv", index=False)

    # =========================================================================
    # ANGLE 2: MONTE CARLO BOOTSTRAP SIMULATION (1,000 RUNS)
    # =========================================================================
    print("\n" + "=" * 115)
    print("ANGLE 2: MONTE CARLO BOOTSTRAP SIMULATION (1,000 PERMUTATION RUNS)")
    print("=" * 115)

    all_trades_df = base_26yr_summary.trades_df.copy()
    ret_series = all_trades_df["net_return_pct"].values / 100.0
    num_trades = len(ret_series)

    np.random.seed(42)
    n_sims = 1000
    mc_cagrs = []
    mc_max_dds = []
    mc_finals = []

    years_total = 26.8
    slot_alloc = 1.0 / 7.0

    print(f"Bootstrapping {n_sims:,} synthetic trade sequences of {num_trades} trades each...")
    for _ in range(n_sims):
        sampled_rets = np.random.choice(ret_series, size=num_trades, replace=True)
        # Simulate compounding path with 7 slots
        cap = 1_000_000.0
        peak = cap
        mdd = 0.0
        for r in sampled_rets:
            trade_pnl = cap * slot_alloc * r
            cap += trade_pnl
            if cap > peak:
                peak = cap
            dd = (cap - peak) / peak
            if dd < mdd:
                mdd = dd

        sim_cagr = (max(cap, 1.0) / 1_000_000.0) ** (1.0 / years_total) - 1.0
        mc_cagrs.append(sim_cagr * 100.0)
        mc_max_dds.append(mdd * 100.0)
        mc_finals.append(cap)

    mc_cagrs = np.array(mc_cagrs)
    mc_max_dds = np.array(mc_max_dds)

    p5_cagr = np.percentile(mc_cagrs, 5)
    p50_cagr = np.percentile(mc_cagrs, 50)
    p95_cagr = np.percentile(mc_cagrs, 95)

    p5_mdd = np.percentile(mc_max_dds, 5)  # Worst case DD
    p50_mdd = np.percentile(mc_max_dds, 50)
    p95_mdd = np.percentile(mc_max_dds, 95)

    p5_final = np.percentile(mc_finals, 5)
    p50_final = np.percentile(mc_finals, 50)
    p95_final = np.percentile(mc_finals, 95)

    print(f"5th  Percentile (Worst-Case 95% Confidence): CAGR = {p5_cagr:+.2f}% | Max DD = {p5_mdd:.2f}% | Final = Rs {p5_final/10000000:.2f} Cr")
    print(f"50th Percentile (Expected Median Path):       CAGR = {p50_cagr:+.2f}% | Max DD = {p50_mdd:.2f}% | Final = Rs {p50_final/10000000:.2f} Cr")
    print(f"95th Percentile (Best-Case Trajectory):       CAGR = {p95_cagr:+.2f}% | Max DD = {p95_mdd:.2f}% | Final = Rs {p95_final/10000000:.2f} Cr")

    mc_df = pd.DataFrame([{
        "Metric": "Monte Carlo 1,000 Runs",
        "Worst_Case_5th_CAGR_%": round(p5_cagr, 2),
        "Median_50th_CAGR_%": round(p50_cagr, 2),
        "Best_Case_95th_CAGR_%": round(p95_cagr, 2),
        "Worst_Case_5th_MaxDD_%": round(p5_mdd, 2),
        "Median_50th_MaxDD_%": round(p50_mdd, 2),
        "Worst_Case_Final_Capital_Rs": round(p5_final, 2),
        "Median_Final_Capital_Rs": round(p50_final, 2),
        "Best_Case_Final_Capital_Rs": round(p95_final, 2),
    }])
    mc_df.to_csv(REPORT_DIR / "ADVERSARIAL_MONTE_CARLO_CONFIDENCE.csv", index=False)
    mc_df.to_csv(DESKTOP_DIR / "ADVERSARIAL_MONTE_CARLO_CONFIDENCE.csv", index=False)

    # =========================================================================
    # ANGLE 3: OUTLIER EXCLUSION STRESS TEST (IS IT A ONE-HIT WONDER?)
    # =========================================================================
    print("\n" + "=" * 115)
    print("ANGLE 3: OUTLIER EXCLUSION STRESS TEST (EXCLUDING TOP MULTIBAGGERS)")
    print("=" * 115)

    outlier_configs = [
        ("Baseline (All 599 Trades)", []),
        ("Stress 1: Exclude Top 1 Winner (DIXON: +439%)", ["DIXON"]),
        ("Stress 2: Exclude Top 3 Winners (DIXON, BAJFINANCE, UNITECH)", ["DIXON", "BAJFINANCE", "UNITECH"]),
        ("Stress 3: Exclude Top 5 Winners (DIXON, BAJFINANCE, UNITECH, BHEL, STLTECH)", ["DIXON", "BAJFINANCE", "UNITECH", "BHEL", "STLTECH"]),
    ]

    outlier_rows = []
    for label, excluded in outlier_configs:
        filtered_bars = bars_df[~bars_df["symbol"].str.replace(".NS", "").str.replace(".BO", "").isin(excluded)].copy()
        res = engine_base.run_backtest(filtered_bars, bench_df, start_date="2000-01-01", end_date="2026-10-26")

        fin_str = f"Rs {res.final_capital/10000000:.2f} Cr"
        mult = res.final_capital / res.initial_capital
        print(f"{label:<75} | CAGR: {res.compounded_cagr_pct:>+6.2f}% | Max DD: {res.max_drawdown_pct:>6.2f}% | Final: {fin_str:>13} ({mult:>4.1f}x)")

        outlier_rows.append({
            "Exclusion_Scenario": label,
            "Excluded_Symbols": ", ".join(excluded) if excluded else "None",
            "CAGR_Pct": round(res.compounded_cagr_pct, 2),
            "Max_Drawdown_Pct": round(res.max_drawdown_pct, 2),
            "Final_Capital_Rs": round(res.final_capital, 2),
            "Multiple": round(mult, 2),
            "Trades": res.total_trades,
            "Win_Rate_Pct": round(res.win_rate_pct, 2),
        })

    outlier_df = pd.DataFrame(outlier_rows)
    outlier_df.to_csv(REPORT_DIR / "ADVERSARIAL_OUTLIER_EXCLUSION_STRESS.csv", index=False)
    outlier_df.to_csv(DESKTOP_DIR / "ADVERSARIAL_OUTLIER_EXCLUSION_STRESS.csv", index=False)

    # =========================================================================
    # ANGLE 4: FRICTION SENSITIVITY DEGRADATION (SLIPPAGE STRESS)
    # =========================================================================
    print("\n" + "=" * 115)
    print("ANGLE 4: FRICTION & SLIPPAGE SENSITIVITY DEGRADATION AUDIT")
    print("=" * 115)

    frictions = [
        ("Liquid Baseline (20 bps slip + 35 bps tax = 55 bps side)", 20.0, 35.0),
        ("Medium Impact (40 bps slip + 35 bps tax = 75 bps side)", 40.0, 35.0),
        ("High Small-Cap Friction (65 bps slip + 35 bps tax = 100 bps side)", 65.0, 35.0),
        ("Punishing Friction (100 bps slip + 52.6 bps tax = 152.6 bps side)", 100.0, 52.6),
    ]

    fric_rows = []
    for label, slip, stat in frictions:
        engine_fric = UpgradedVCPBacktestEngine(
            initial_capital=1_000_000.0,
            max_slots=7,
            mode="HYBRID_50_50",
            min_turnover_rs=30_000_000.0,
            slippage_bps_per_side=slip,
            statutory_bps_per_side=stat,
            use_equal_weight_slots=True,
            cash_yield_pct_p_a=6.5,
            use_sector_leadership=True,
            tranche2_days=7,
        )
        res = engine_fric.run_backtest(bars_df, bench_df, start_date="2000-01-01", end_date="2026-10-26")
        fin_str = f"Rs {res.final_capital/10000000:.2f} Cr"
        fric_str = f"Rs {res.total_friction_paid/10000000:.2f} Cr"
        mult = res.final_capital / res.initial_capital

        print(f"{label:<68} | CAGR: {res.compounded_cagr_pct:>+6.2f}% | Max DD: {res.max_drawdown_pct:>6.2f}% | Final: {fin_str:>13} ({mult:>4.1f}x) | Friction Paid: {fric_str}")

        fric_rows.append({
            "Scenario": label,
            "Slippage_Bps": slip,
            "Statutory_Bps": stat,
            "Total_Bps_Per_Side": slip + stat,
            "CAGR_Pct": round(res.compounded_cagr_pct, 2),
            "Max_Drawdown_Pct": round(res.max_drawdown_pct, 2),
            "Final_Capital_Rs": round(res.final_capital, 2),
            "Multiple": round(mult, 2),
            "Total_Friction_Paid_Rs": round(res.total_friction_paid, 2),
        })

    fric_df = pd.DataFrame(fric_rows)
    fric_df.to_csv(REPORT_DIR / "ADVERSARIAL_FRICTION_DEGRADATION_STRESS.csv", index=False)
    fric_df.to_csv(DESKTOP_DIR / "ADVERSARIAL_FRICTION_DEGRADATION_STRESS.csv", index=False)

    # =========================================================================
    # ANGLE 5: STOCK-LEVEL DOWN-SIDE SL & MULTIBAGGER AUDIT
    # =========================================================================
    print("\n" + "=" * 115)
    print("ANGLE 5: STOCK-LEVEL ATTRIBUTION AUDIT (TOP 10 WINNERS & WORST 5 SL HITTERS)")
    print("=" * 115)

    stock_records = []
    for s, grp in all_trades_df.groupby("symbol"):
        tot = len(grp)
        wins = len(grp[grp["net_return_pct"] > 0])
        sl_hits = len(grp[grp["exit_reason"].str.contains("STOP|Stop|INITIAL|Initial|Circuit Breaker")])
        tot_pnl = grp["pnl_amount"].sum()
        best_gain = grp["net_return_pct"].max()
        worst_loss = grp["net_return_pct"].min()
        cum_mult = (1.0 + grp["net_return_pct"] / 100.0).prod()

        stock_records.append({
            "Symbol": s,
            "Trades": tot,
            "Wins": wins,
            "SL_Hits": sl_hits,
            "Win_Rate_%": round(wins / tot * 100.0, 1),
            "Best_Gain_%": round(best_gain, 1),
            "Worst_Loss_%": round(worst_loss, 1),
            "Cumulative_Multiple": round(cum_mult, 2),
            "Total_PnL_Rs": round(tot_pnl, 2),
        })

    stk_summary_df = pd.DataFrame(stock_records).sort_values("Cumulative_Multiple", ascending=False)
    stk_summary_df.to_csv(REPORT_DIR / "ADVERSARIAL_ALL_EQUITIES_ATTRIBUTION.csv", index=False)
    stk_summary_df.to_csv(DESKTOP_DIR / "ADVERSARIAL_ALL_EQUITIES_ATTRIBUTION.csv", index=False)

    print("--- Top 10 Wealth Multipliers Across 26.8 Years ---")
    print(stk_summary_df.head(10).to_string(index=False))

    print("\n--- Bottom 5 Most Punished Stocks (Highest SL Hitters) ---")
    print(stk_summary_df.tail(5).to_string(index=False))

    print("\n" + "=" * 115)
    print(f"[SUCCESS] All 5 Adversarial Stress Testing Reports Saved to Desktop: {DESKTOP_DIR}")
    print("=" * 115)


if __name__ == "__main__":
    run_full_adversarial_audit()
