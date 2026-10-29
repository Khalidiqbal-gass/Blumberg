import sys
from pathlib import Path
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from simulate_fy_tax_drag import run_fy_tax_analysis

trades_p = PROJECT_ROOT / "reports" / "8_slot_audit" / "8_slot_trades_2000_2026.csv"
equity_p = PROJECT_ROOT / "reports" / "8_slot_audit" / "8_slot_equity_2000_2026.csv"

trades_df = pd.read_csv(trades_p)
equity_df = pd.read_csv(equity_p)

print("=" * 80)
print("INSTITUTIONAL TAX & REINVESTMENT DRAG ON MASTER 8-SLOT AUDIT (2000 - 2026)")
print("=" * 80)

# 1. CURRENT LAW WITH 6.5% LIQUID YIELD
tax_curr = run_fy_tax_analysis(trades_df, equity_df, with_yield=True, yield_pct=6.5, regime="CURRENT")
print("\n1. CURRENT LAW (20% STCG / 12.5% LTCG / 30% Liquid Slab):")
print(f"   Pre-Tax Final:   Rs {tax_curr['pre_tax_final'] / 1e7:.2f} Cr")
print(f"   Pre-Tax CAGR:    {tax_curr['pre_tax_cagr']:.2f}%")
print(f"   Total Tax Paid:  Rs {tax_curr['total_tax_paid'] / 1e7:.2f} Cr")
print(f"     - STCG Tax:    Rs {tax_curr['total_stcg_tax'] / 1e7:.2f} Cr")
print(f"     - LTCG Tax:    Rs {tax_curr['total_ltcg_tax'] / 1e7:.2f} Cr")
print(f"     - Liquid Tax:  Rs {tax_curr['total_liquid_tax'] / 1e7:.2f} Cr")
print(f"   Post-Tax Final:  Rs {tax_curr['post_tax_final'] / 1e7:.2f} Cr")
print(f"   Post-Tax CAGR:   {tax_curr['post_tax_cagr']:.2f}%")
print(f"   Tax Drag:        {tax_curr['tax_drag_pts']:.2f} percentage points")

# 2. HISTORICAL LAW WITH 6.5% LIQUID YIELD
tax_hist = run_fy_tax_analysis(trades_df, equity_df, with_yield=True, yield_pct=6.5, regime="HISTORICAL")
print("\n2. HISTORICAL LAW (Sec 10(38) Tax-Free LTCG 2004-2018):")
print(f"   Total Tax Paid:  Rs {tax_hist['total_tax_paid'] / 1e7:.2f} Cr")
print(f"   Post-Tax Final:  Rs {tax_hist['post_tax_final'] / 1e7:.2f} Cr")
print(f"   Post-Tax CAGR:   {tax_hist['post_tax_cagr']:.2f}%")
print(f"   Tax Drag:        {tax_hist['tax_drag_pts']:.2f} percentage points")

# 3. CURRENT LAW ZERO YIELD (ORGANIC ONLY)
tax_curr_0 = run_fy_tax_analysis(trades_df, equity_df, with_yield=False, regime="CURRENT")
print("\n3. CURRENT LAW (ORGANIC CAPITAL ONLY - No Liquid Sweep):")
print(f"   Total Tax Paid:  Rs {tax_curr_0['total_tax_paid'] / 1e7:.2f} Cr")
print(f"   Post-Tax Final:  Rs {tax_curr_0['post_tax_final'] / 1e7:.2f} Cr")
print(f"   Post-Tax CAGR:   {tax_curr_0['post_tax_cagr']:.2f}%")

# 4. HISTORICAL LAW ZERO YIELD
tax_hist_0 = run_fy_tax_analysis(trades_df, equity_df, with_yield=False, regime="HISTORICAL")
print("\n4. HISTORICAL LAW (ORGANIC CAPITAL ONLY - No Liquid Sweep):")
print(f"   Total Tax Paid:  Rs {tax_hist_0['total_tax_paid'] / 1e7:.2f} Cr")
print(f"   Post-Tax Final:  Rs {tax_hist_0['post_tax_final'] / 1e7:.2f} Cr")
print(f"   Post-Tax CAGR:   {tax_hist_0['post_tax_cagr']:.2f}%")
print("=" * 80)
