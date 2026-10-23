import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.run_capital_constrained_secular_audit import run_simulation

for slots in [10, 15, 20]:
    print(f"\n{'#'*30} TESTING {slots} SLOTS {'#'*30}")
    c, eq, yr, stats = run_simulation(num_slots=slots)
    print(f"Slots: {slots} | Final Capital: Rs {stats['final_capital']:,.2f} | Net CAGR: +{stats['model_cagr']:.2f}% | Max DD: {stats['max_drawdown']:.2f}% | Executed: {stats['executed_campaigns']} | Skipped: {stats['skipped_slots_full']}")
