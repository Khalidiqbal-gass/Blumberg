"""Generate publication-grade charts for the Blumberg Master System Specification & Audit PDF."""
from __future__ import annotations

import sys
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker

# Setup paths
DESKTOP_DIR = Path(r"C:\Users\DELL\OneDrive\Desktop\BLUMBERG_AUDIT_FILES\8_SLOT_AUDIT")
IMG_DIR = DESKTOP_DIR / "charts"
IMG_DIR.mkdir(parents=True, exist_ok=True)

# Load data
equity = pd.read_csv(DESKTOP_DIR / "8_slot_equity_2000_2026.csv")
trades = pd.read_csv(DESKTOP_DIR / "8_slot_trades_2000_2026.csv")
yearly = pd.read_csv(DESKTOP_DIR / "8_SLOT_YEAR_BY_YEAR_PERFORMANCE.csv")

equity['date'] = pd.to_datetime(equity['date'])

# Style configuration
plt.rcParams['font.sans-serif'] = 'DejaVu Sans'
plt.rcParams['axes.edgecolor'] = '#CBD5E0'
plt.rcParams['axes.linewidth'] = 0.8

# -------------------------------------------------------------
# CHART 1: Cumulative Equity & Drawdown (Log Scale)
# -------------------------------------------------------------
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 5.5), sharex=True, gridspec_kw={'height_ratios': [2.2, 1]})

# Equity Curve (Log Scale in Crores)
equity_cr = equity['total_equity'] / 1e7
ax1.plot(equity['date'], equity_cr, color='#1A365D', linewidth=1.8, label='Blumberg 8-Slot Sweet Spot (Rs. 10L -> Rs. 29.16 Cr | +23.58% CAGR)')

# Sensex normalized
nifty_start = equity['nifty_close'].dropna().iloc[0]
nifty_cr = (equity['nifty_close'] / nifty_start) * 0.10  # Normalized to Rs 0.10 Cr (10L)
ax1.plot(equity['date'], nifty_cr, color='#718096', linewidth=1.2, linestyle='--', label='Sensex Benchmark (Rs. 10L -> Rs. 1.36 Cr | +10.23% CAGR)')

ax1.set_yscale('log')
ax1.set_ylabel('Portfolio Value (Rs. Cr - Log)', fontsize=9, fontweight='bold', color='#2D3748')
ax1.yaxis.set_major_formatter(ticker.FuncFormatter(lambda y, _: f'Rs.{y:g} Cr' if y >= 1 else f'Rs.{y*100:g} L'))
ax1.grid(True, linestyle=':', alpha=0.5, color='#CBD5E0')
ax1.legend(loc='upper left', frameon=True, facecolor='white', edgecolor='#E2E8F0', fontsize=8)
ax1.set_title('Blumberg 8-Slot Portfolio vs Sensex: 26.8-Year Wealth Compounding (2000 - 2026)', fontsize=11, fontweight='bold', color='#1A365D', pad=10)

# Drawdown Curve
ax2.plot(equity['date'], equity['drawdown'], color='#E53E3E', linewidth=1.0)
ax2.fill_between(equity['date'], equity['drawdown'], 0, color='#FED7D7', alpha=0.6)
ax2.set_ylabel('Drawdown (%)', fontsize=8, fontweight='bold', color='#2D3748')
ax2.set_ylim(-45, 2)
ax2.grid(True, linestyle=':', alpha=0.5, color='#CBD5E0')
ax2.axhline(-36.25, color='#C53030', linestyle=':', linewidth=1.0, label='Max DD: -36.25% (May 2004)')
ax2.legend(loc='lower left', frameon=True, facecolor='white', edgecolor='#E2E8F0', fontsize=7.5)

plt.tight_layout()
chart1_path = IMG_DIR / "chart1_equity_drawdown.png"
fig.savefig(chart1_path, dpi=300)
plt.close(fig)
print(f"Chart 1 saved to {chart1_path}")

# -------------------------------------------------------------
# CHART 2: Annual Returns & Alpha Bars (2000 - 2026)
# -------------------------------------------------------------
fig, ax = plt.subplots(figsize=(10, 4.2))
x = np.arange(len(yearly))
width = 0.38

model_ret = yearly['Model_Annual_Return_%']
sensex_ret = yearly['Sensex_Annual_Return_%']

model_bars = ax.bar(x - width/2, model_ret, width, label='Blumberg Model Return (%)', color='#2B6CB0', alpha=0.9)
nifty_bars = ax.bar(x + width/2, sensex_ret, width, label='Sensex Return (%)', color='#A0AEC0', alpha=0.85)

ax.set_ylabel('Calendar Return (%)', fontsize=8, fontweight='bold', color='#2D3748')
ax.set_title('Year-by-Year Calendar Performance: Blumberg 8-Slot vs Sensex Benchmark (2000 - 2026)', fontsize=10.5, fontweight='bold', color='#1A365D')
ax.set_xticks(x)
ax.set_xticklabels(yearly['Year'], rotation=45, ha='right', fontsize=7.5)
ax.grid(True, axis='y', linestyle=':', alpha=0.5, color='#CBD5E0')
ax.axhline(0, color='#718096', linewidth=0.8)
ax.legend(loc='upper right', frameon=True, facecolor='white', edgecolor='#E2E8F0', fontsize=8)

plt.tight_layout()
chart2_path = IMG_DIR / "chart2_yearly_returns.png"
fig.savefig(chart2_path, dpi=300)
plt.close(fig)
print(f"Chart 2 saved to {chart2_path}")

# -------------------------------------------------------------
# CHART 3: Asymmetric Math - Stop-Loss Cuts vs Trailing Compounders
# -------------------------------------------------------------
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 3.8))

# Pie Chart: Trades Count (64.9% Stops vs 35.1% Wealth Compounders)
labels = ['Stage 1 Defensive Stops\n(454 Trades | 64.9%)', 'Stages 2-5 Profit Locks\n(244 Trades | 34.9%)', 'Active Holdings\n(2 Trades | 0.3%)']
sizes = [454, 244, 2]
colors_pie = ['#FEB2B2', '#68D391', '#63B3ED']
explode = (0.05, 0.05, 0.1)

ax1.pie(sizes, explode=explode, labels=labels, colors=colors_pie, autopct='%1.1f%%', startangle=140, textprops={'fontsize': 8, 'fontweight': 'bold'})
ax1.set_title('Trade Execution Distribution\n(Win Rate: 24.1% by Design)', fontsize=9.5, fontweight='bold', color='#1A365D')

# Bar Chart: Total Rupee PnL Generated
pnl_categories = ['Stage 1 Stop Losses\n(-Rs. 8.28 Cr surrendered)', 'Stages 2-5 Profit Harvest\n(+Rs. 18.46 Cr captured)', 'Net Wealth Created\n(+Rs. 10.18 Cr net)']
pnl_values = [-8.28, 18.46, 10.18]
pnl_colors = ['#E53E3E', '#38A169', '#2B6CB0']

bars_pnl = ax2.bar(pnl_categories, pnl_values, color=pnl_colors, width=0.55)
ax2.axhline(0, color='#718096', linewidth=0.8)
ax2.set_ylabel('Total Cumulative PnL (Rs. Crore)', fontsize=8, fontweight='bold', color='#2D3748')
ax2.set_title('Asymmetric PnL Attribution\n(8.87x Payoff Ratio Mechanics)', fontsize=9.5, fontweight='bold', color='#1A365D')
ax2.grid(True, axis='y', linestyle=':', alpha=0.5, color='#CBD5E0')

for bar in bars_pnl:
    yval = bar.get_height()
    va = 'bottom' if yval >= 0 else 'top'
    ax2.text(bar.get_x() + bar.get_width()/2, yval + (0.5 if yval >= 0 else -0.8), f'Rs.{yval:+.2f} Cr', ha='center', va=va, fontsize=8, fontweight='bold')

plt.tight_layout()
chart3_path = IMG_DIR / "chart3_asymmetric_payoff.png"
fig.savefig(chart3_path, dpi=300)
plt.close(fig)
print(f"Chart 3 saved to {chart3_path}")

print("All charts generated successfully!")
