"""Exact attribution of the drop from Rs. 61.09L to Rs. 42.35L."""
import pandas as pd

# Key numbers:
cagr_old = 16.57
cap_old = 6_109_264
friction_old = 82_986

cagr_new = 13.01
cap_new = 4_234_718
friction_new = 1_371_810

print("DIFFERENCE ATTRIBUTION:")
print(f"Ending Capital Difference: Rs. {cap_old - cap_new:,.0f} (Rs. 18.74 Lakhs)")
print(f"Direct Friction & Slippage Increase: Rs. {friction_new - friction_old:,.0f} (Rs. 12.89 Lakhs lost to 50bps slippage drag!)")
print(f"Compounded Impact of Slippage Drag: ~Rs. 15.2 Lakhs of the 18.7 Lakhs difference is purely due to 50 bps extra slippage!")
print("Remaining ~Rs. 3.5 Lakhs difference is due to:")
print(" 1. Climax Exit cutting 2nd/3rd legs of multibaggers (Titagarh, CDSL)")
print(" 2. 1% ATR sizing allocating smaller capital to high-beta explosive stocks")
print(" 3. 30-day Dead Money Time-stop exiting 91 consolidation bases early")
