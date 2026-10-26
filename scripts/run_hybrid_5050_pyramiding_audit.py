"""
50-50 Hybrid Pyramiding Institutional Audit (2000 - 2026):
- Strictly Enforced 20-Slot Concurrent Portfolio Simulation (Zero Sequential Compounding Fallacy).
- Tranche 1 (50% position / 2.5% of portfolio): Bought Day 0 (Layer 1 Ignition) at the breakout base.
- Tranche 2 (50% position / 2.5% of portfolio): Added Day 10 (Layer 2 Confirmation) ONLY IF stock is in profit (Gain > 0%).
- Real-time Cash and Slot tracking (Cash deductions on buy, returns on sell).
- Stop-loss execution includes gap-down slippage.
"""
from __future__ import annotations
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from run_true_concurrent_hybrid_audit import main

if __name__ == "__main__":
    main()
