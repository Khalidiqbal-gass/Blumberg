import sys
from pathlib import Path
sys.path.insert(0, 'src')
import pandas as pd
import numpy as np
from blumberg_market_radar.backtest.upgraded_vcp_engine import UpgradedVCPBacktestEngine

def get_fy(dt):
    dt = pd.to_datetime(dt)
    if dt.month >= 4:
        return f"FY{dt.year % 100:02d}-{(dt.year + 1) % 100:02d}", dt.year + 1
    else:
        return f"FY{(dt.year - 1) % 100:02d}-{dt.year % 100:02d}", dt.year

def run_fy_tax_analysis(trades_df, equity_df, with_yield=False, yield_pct=6.5, regime="CURRENT"):
    """
    Performs FY-by-FY tax calculation according to Indian IT Act (Sec 70-74):
    - STCG (< 365 days): 20% (Current) or 15% (Historical 2004-2024) / 30% (pre-2004)
    - LTCG (>= 365 days): 12.5% above 1.25L exemption (Current) or 0% (2004-2018 under Sec 10(38))
    - Liquid yield: 30% slab rate
    - Loss carry-forward: 8 Assessment Years queue
    - Dynamic reinvestment drag: Tax deducted annually at March 31
    """
    trades = trades_df.copy()
    trades['exit_date'] = pd.to_datetime(trades['exit_date']).dt.tz_localize(None)
    trades['entry_date'] = pd.to_datetime(trades['entry_date']).dt.tz_localize(None)
    
    equity_df = equity_df.copy()
    if 'date' in equity_df.columns:
        equity_df['dt'] = pd.to_datetime(equity_df['date']).dt.tz_localize(None)
        equity_df = equity_df.set_index('dt')
    else:
        equity_df.index = pd.to_datetime(equity_df.index).dt.tz_localize(None)
    
    fy_info = trades['exit_date'].apply(get_fy)
    trades['fy'] = [x[0] for x in fy_info]
    trades['ay_year'] = [x[1] for x in fy_info]
    trades['is_ltcg'] = trades['calendar_days'] >= 365

    # Group trades by FY
    all_fys = sorted(list(set(trades['fy'])))
    
    # Carry forward loss queues: list of [loss_amount, remaining_years]
    cf_stcl = []
    cf_ltcl = []
    
    fy_records = []
    
    # Track annual capital and compounding drag
    initial_cap = 1_000_000.0
    
    for fy in all_fys:
        fy_trades = trades[trades['fy'] == fy]
        
        stcg_trades = fy_trades[~fy_trades['is_ltcg']]
        ltcg_trades = fy_trades[fy_trades['is_ltcg']]
        
        stcg_pnl = stcg_trades['pnl_amount'].sum() if len(stcg_trades) > 0 else 0.0
        ltcg_pnl = ltcg_trades['pnl_amount'].sum() if len(ltcg_trades) > 0 else 0.0
        
        # Determine year for historical rates
        fy_end_year = int("20" + fy.split("-")[1])
        
        if regime == "CURRENT":
            stcg_rate = 0.20
            ltcg_rate = 0.125
            ltcg_exemption = 125_000.0
            liquid_tax_rate = 0.30
        else: # HISTORICAL
            if fy_end_year <= 2004:
                stcg_rate = 0.30
                ltcg_rate = 0.20
                ltcg_exemption = 0.0
            elif fy_end_year <= 2018:
                stcg_rate = 0.15
                ltcg_rate = 0.00 # Sec 10(38) tax-free!
                ltcg_exemption = 0.0
            elif fy_end_year <= 2024:
                stcg_rate = 0.15
                ltcg_rate = 0.10
                ltcg_exemption = 100_000.0
            else:
                stcg_rate = 0.20
                ltcg_rate = 0.125
                ltcg_exemption = 125_000.0
            liquid_tax_rate = 0.30
            
        # 1. Intra-year intra-head netting
        curr_stcg = stcg_pnl
        curr_ltcg = ltcg_pnl
        
        # 2. Inter-head netting in same FY
        # STCL can offset LTCG
        if curr_stcg < 0 and curr_ltcg > 0:
            offset = min(abs(curr_stcg), curr_ltcg)
            curr_ltcg -= offset
            curr_stcg += offset
        # Note: LTCL cannot offset STCG under Sec 70(3)
        
        # 3. Apply carried forward losses
        # Age existing carried forward losses
        cf_stcl = [[amt, yrs - 1] for amt, yrs in cf_stcl if yrs > 1]
        cf_ltcl = [[amt, yrs - 1] for amt, yrs in cf_ltcl if yrs > 1]
        
        # Offset STCG with CF STCL
        if curr_stcg > 0 and cf_stcl:
            for item in cf_stcl:
                if curr_stcg <= 0:
                    break
                offset = min(curr_stcg, item[0])
                curr_stcg -= offset
                item[0] -= offset
            cf_stcl = [item for item in cf_stcl if item[0] > 0]
            
        # Offset LTCG with CF LTCL first, then CF STCL
        if curr_ltcg > 0 and cf_ltcl:
            for item in cf_ltcl:
                if curr_ltcg <= 0:
                    break
                offset = min(curr_ltcg, item[0])
                curr_ltcg -= offset
                item[0] -= offset
            cf_ltcl = [item for item in cf_ltcl if item[0] > 0]
            
        if curr_ltcg > 0 and cf_stcl:
            for item in cf_stcl:
                if curr_ltcg <= 0:
                    break
                offset = min(curr_ltcg, item[0])
                curr_ltcg -= offset
                item[0] -= offset
            cf_stcl = [item for item in cf_stcl if item[0] > 0]
            
        # Add remaining negative balances to carry-forward queues (8 years validity)
        if curr_stcg < 0:
            cf_stcl.append([abs(curr_stcg), 8])
            taxable_stcg = 0.0
        else:
            taxable_stcg = curr_stcg
            
        if curr_ltcg < 0:
            cf_ltcl.append([abs(curr_ltcg), 8])
            taxable_ltcg = 0.0
        else:
            taxable_ltcg = max(0.0, curr_ltcg - ltcg_exemption)
            
        tax_stcg = taxable_stcg * stcg_rate
        tax_ltcg = taxable_ltcg * ltcg_rate
        
        # Liquid yield tax if applicable
        # Estimate FY average idle cash from equity curve
        liquid_tax = 0.0
        if with_yield:
            # Approximate idle cash yield in this FY
            fy_start_date = pd.to_datetime(f"{fy_end_year-1}-04-01")
            fy_end_date = pd.to_datetime(f"{fy_end_year}-03-31")
            eq_fy = equity_df[(equity_df.index >= fy_start_date) & (equity_df.index <= fy_end_date)]
            if len(eq_fy) > 0 and 'cash' in eq_fy.columns:
                avg_cash = eq_fy['cash'].mean()
                fy_yield = avg_cash * (yield_pct / 100.0)
                liquid_tax = fy_yield * liquid_tax_rate
            else:
                # fallback based on 30% idle cash assumption
                if len(eq_fy) > 0:
                    avg_eq = eq_fy['total_equity'].mean()
                    fy_yield = (avg_eq * 0.30) * (yield_pct / 100.0)
                    liquid_tax = fy_yield * liquid_tax_rate
        
        total_tax = tax_stcg + tax_ltcg + liquid_tax
        
        fy_records.append({
            'fy': fy,
            'stcg_pnl': stcg_pnl,
            'ltcg_pnl': ltcg_pnl,
            'taxable_stcg': taxable_stcg,
            'taxable_ltcg': taxable_ltcg,
            'tax_stcg': tax_stcg,
            'tax_ltcg': tax_ltcg,
            'liquid_tax': liquid_tax,
            'total_tax': total_tax,
            'num_trades': len(fy_trades),
            'num_ltcg': len(ltcg_trades),
            'num_stcg': len(stcg_trades),
        })
        
    fy_df = pd.DataFrame(fy_records)
    total_tax_paid = fy_df['total_tax'].sum()
    
    # Dynamic Compounding Drag Simulation (Size-Scaled Replay)
    # Replay annual returns with annual tax outflows scaled to actual post-tax capital size:
    # dyn_equity = dyn_equity * growth_ratio - tax_this_fy * (dyn_equity / pre_equity)
    equity_df_copy = equity_df.copy()
    equity_df_copy['fy'] = equity_df_copy.index.map(lambda d: get_fy(d)[0])
    
    # Calculate pre-tax capital end
    pre_tax_final = equity_df['total_equity'].iloc[-1]
    years = (equity_df.index[-1] - equity_df.index[0]).days / 365.25
    pre_tax_cagr = (pre_tax_final / initial_cap) ** (1.0 / years) - 1.0
    
    # Post-tax capital with size-scaled annual tax deduction:
    pre_equity = initial_cap
    dyn_equity = initial_cap
    fy_list = list(fy_df['fy'])
    
    for i, fy in enumerate(fy_list):
        eq_sub = equity_df_copy[equity_df_copy['fy'] == fy]
        if len(eq_sub) > 1:
            growth_ratio = eq_sub['total_equity'].iloc[-1] / eq_sub['total_equity'].iloc[0]
        else:
            growth_ratio = 1.0
            
        tax_this_fy = fy_df.loc[fy_df['fy'] == fy, 'total_tax'].values[0]
        
        pre_equity *= growth_ratio
        dyn_equity *= growth_ratio
        
        # Scale rupee tax by (dyn_equity / pre_equity) to match smaller post-tax compounding capital base
        scale_ratio = dyn_equity / pre_equity if pre_equity > 0 else 1.0
        dyn_equity = max(10_000.0, dyn_equity - tax_this_fy * scale_ratio)
        
    post_tax_final = dyn_equity
    post_tax_cagr = (post_tax_final / initial_cap) ** (1.0 / years) - 1.0
    
    return {
        'fy_df': fy_df,
        'total_tax_paid': total_tax_paid,
        'pre_tax_final': pre_tax_final,
        'pre_tax_cagr': pre_tax_cagr * 100.0,
        'post_tax_final': post_tax_final,
        'post_tax_cagr': post_tax_cagr * 100.0,
        'tax_drag_pts': (pre_tax_cagr - post_tax_cagr) * 100.0,
        'years': years,
        'total_stcg_tax': fy_df['tax_stcg'].sum(),
        'total_ltcg_tax': fy_df['tax_ltcg'].sum(),
        'total_liquid_tax': fy_df['liquid_tax'].sum(),
    }

if __name__ == '__main__':
    df = pd.read_parquet('data/cache/historical_2000_2026/market_bars_with_delisted_2000_2026.parquet')
    bench_df = pd.read_parquet('data/cache/historical_2000_2026/sensex_bench_2000_2026.parquet')
    df = df.sort_values(['symbol', 'date']).reset_index(drop=True)

    df['c_prev'] = df.groupby('symbol')['close'].shift(1)
    df['c_next'] = df.groupby('symbol')['close'].shift(-1)
    mask_glitch = ((df['high'] / df['c_prev'] > 2.0) | (df['low'] / df['c_prev'] < 0.5)) & (df['c_next'] / df['c_prev'] >= 0.7) & (df['c_next'] / df['c_prev'] <= 1.4)

    df_clean = df.copy()
    interp_price = (df_clean.loc[mask_glitch, 'c_prev'] + df_clean.loc[mask_glitch, 'c_next']) / 2.0
    df_clean.loc[mask_glitch, 'open'] = interp_price
    df_clean.loc[mask_glitch, 'high'] = interp_price * 1.01
    df_clean.loc[mask_glitch, 'low'] = interp_price * 0.99
    df_clean.loc[mask_glitch, 'close'] = interp_price

    print("================================================================================")
    print("RUNNING INSTITUTIONAL FY-BY-FY TAX & REINVESTMENT DRAG SIMULATION (2000-2026)")
    print("================================================================================")

    # 1. CLEAN DATA - ZERO YIELD (ORGANIC)
    print("\n--- 1. CLEAN DATA: ZERO YIELD (ORGANIC TRADING ONLY) ---")
    e1 = UpgradedVCPBacktestEngine(max_slots=8, cash_yield_pct_p_a=0.0)
    res1 = e1.run_backtest(df_clean, bench_df)
    tax_clean_zero_curr = run_fy_tax_analysis(res1.trades_df, res1.equity_curve, with_yield=False, regime="CURRENT")
    tax_clean_zero_hist = run_fy_tax_analysis(res1.trades_df, res1.equity_curve, with_yield=False, regime="HISTORICAL")

    print(f"Pre-Tax: Final = Rs {tax_clean_zero_curr['pre_tax_final']/1e7:.2f} Cr | CAGR = {tax_clean_zero_curr['pre_tax_cagr']:.2f}% | Trades = {len(res1.trades_df)}")
    print(f"Current Tax Law (20% STCG / 12.5% LTCG):")
    print(f"  Total Tax Paid = Rs {tax_clean_zero_curr['total_tax_paid']/1e7:.2f} Cr (STCG Tax: Rs {tax_clean_zero_curr['total_stcg_tax']/1e7:.2f}Cr, LTCG Tax: Rs {tax_clean_zero_curr['total_ltcg_tax']/1e7:.2f}Cr)")
    print(f"  Post-Tax Final = Rs {tax_clean_zero_curr['post_tax_final']/1e7:.2f} Cr | Post-Tax CAGR = {tax_clean_zero_curr['post_tax_cagr']:.2f}% (Drag = {tax_clean_zero_curr['tax_drag_pts']:.2f} pts)")
    print(f"Historical Tax Law (2004-2018 Sec 10(38) Tax-Free LTCG):")
    print(f"  Total Tax Paid = Rs {tax_clean_zero_hist['total_tax_paid']/1e7:.2f} Cr | Post-Tax CAGR = {tax_clean_zero_hist['post_tax_cagr']:.2f}%")

    # 2. CLEAN DATA - WITH 6.5% LIQUID YIELD
    print("\n--- 2. CLEAN DATA: WITH 6.5% LIQUID FUND SWEEP ---")
    e2 = UpgradedVCPBacktestEngine(max_slots=8, cash_yield_pct_p_a=6.5)
    res2 = e2.run_backtest(df_clean, bench_df)
    tax_clean_yield_curr = run_fy_tax_analysis(res2.trades_df, res2.equity_curve, with_yield=True, yield_pct=6.5, regime="CURRENT")
    tax_clean_yield_hist = run_fy_tax_analysis(res2.trades_df, res2.equity_curve, with_yield=True, yield_pct=6.5, regime="HISTORICAL")

    print(f"Pre-Tax: Final = Rs {tax_clean_yield_curr['pre_tax_final']/1e7:.2f} Cr | CAGR = {tax_clean_yield_curr['pre_tax_cagr']:.2f}% | Trades = {len(res2.trades_df)}")
    print(f"Current Tax Law (20% STCG / 12.5% LTCG / 30% Liquid Slab):")
    print(f"  Total Tax Paid = Rs {tax_clean_yield_curr['total_tax_paid']/1e7:.2f} Cr (STCG: Rs {tax_clean_yield_curr['total_stcg_tax']/1e7:.2f}Cr, LTCG: Rs {tax_clean_yield_curr['total_ltcg_tax']/1e7:.2f}Cr, Liquid: Rs {tax_clean_yield_curr['total_liquid_tax']/1e7:.2f}Cr)")
    print(f"  Post-Tax Final = Rs {tax_clean_yield_curr['post_tax_final']/1e7:.2f} Cr | Post-Tax CAGR = {tax_clean_yield_curr['post_tax_cagr']:.2f}% (Drag = {tax_clean_yield_curr['tax_drag_pts']:.2f} pts)")
    print(f"Historical Tax Law (2004-2018 Sec 10(38) Tax-Free LTCG):")
    print(f"  Total Tax Paid = Rs {tax_clean_yield_hist['total_tax_paid']/1e7:.2f} Cr | Post-Tax CAGR = {tax_clean_yield_hist['post_tax_cagr']:.2f}%")

    # 3. RAW DATA - ZERO YIELD
    print("\n--- 3. RAW DATA: ZERO YIELD ---")
    e3 = UpgradedVCPBacktestEngine(max_slots=8, cash_yield_pct_p_a=0.0)
    res3 = e3.run_backtest(df, bench_df)
    tax_raw_zero_curr = run_fy_tax_analysis(res3.trades_df, res3.equity_curve, with_yield=False, regime="CURRENT")
    print(f"Pre-Tax: Final = Rs {tax_raw_zero_curr['pre_tax_final']/1e7:.2f} Cr | CAGR = {tax_raw_zero_curr['pre_tax_cagr']:.2f}% | Trades = {len(res3.trades_df)}")
    print(f"Current Tax Law: Post-Tax Final = Rs {tax_raw_zero_curr['post_tax_final']/1e7:.2f} Cr | Post-Tax CAGR = {tax_raw_zero_curr['post_tax_cagr']:.2f}%")

    # 4. RAW DATA - WITH YIELD
    print("\n--- 4. RAW DATA: WITH 6.5% YIELD ---")
    e4 = UpgradedVCPBacktestEngine(max_slots=8, cash_yield_pct_p_a=6.5)
    res4 = e4.run_backtest(df, bench_df)
    tax_raw_yield_curr = run_fy_tax_analysis(res4.trades_df, res4.equity_curve, with_yield=True, yield_pct=6.5, regime="CURRENT")
    print(f"Pre-Tax: Final = Rs {tax_raw_yield_curr['pre_tax_final']/1e7:.2f} Cr | CAGR = {tax_raw_yield_curr['pre_tax_cagr']:.2f}% | Trades = {len(res4.trades_df)}")
    print(f"Current Tax Law: Post-Tax Final = Rs {tax_raw_yield_curr['post_tax_final']/1e7:.2f} Cr | Post-Tax CAGR = {tax_raw_yield_curr['post_tax_cagr']:.2f}%")
