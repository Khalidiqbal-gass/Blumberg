import pandas as pd

# Check in the 15-slot simulation campaigns
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.run_capital_constrained_secular_audit import run_simulation
camps, eq, yr, stats = run_simulation(num_slots=15)

overlaps = []
for sym, grp in camps.groupby("symbol"):
    grp = grp.sort_values("entry_date").reset_index(drop=True)
    for i in range(len(grp) - 1):
        if grp.loc[i, "exit_date"] > grp.loc[i+1, "entry_date"]:
            overlaps.append((sym, grp.loc[i, "exit_date"], grp.loc[i+1, "entry_date"]))

if overlaps:
    print(f"FOUND {len(overlaps)} OVERLAPS:")
    for o in overlaps[:10]:
        print(o)
else:
    print("SUCCESS: EXACTLY ZERO OVERLAPPING CAMPAIGNS! Non-overlapping constraint verified 100%.")
