"""CLI Runner for Blumberg Market Radar Nightly EOD Automation Pipeline.

Usage:
    python scripts/nightly_eod_pipeline.py --mode offline
    python scripts/nightly_eod_pipeline.py --mode live --output reports/daily_digests
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys
import time

# Safely reconfigure stdout/stderr for utf-8 on Windows consoles
if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Ensure src is in python path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "src"))

from blumberg_market_radar.pipeline.nightly import run_nightly_eod_pipeline


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Blumberg Market Radar — Nightly EOD Automation & Paper Tracking Pipeline",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--mode",
        choices=["offline", "live"],
        default="offline",
        help="Pipeline execution mode: 'offline' (synthetic data fallback) or 'live' (Yahoo Finance/NSE).",
    )
    parser.add_argument(
        "--output",
        "--output-dir",
        dest="output_dir",
        default="reports/daily_digests",
        help="Destination directory for markdown daily intelligence digests.",
    )
    parser.add_argument(
        "--ledger",
        "--ledger-path",
        dest="ledger_path",
        default="data/signal_ledger.jsonl",
        help="Path to the immutable append-only JSONL signal ledger.",
    )
    parser.add_argument(
        "--min-score",
        type=float,
        default=50.0,
        help="Minimum pre-rally radar score threshold (0-100) to qualify candidates.",
    )
    parser.add_argument(
        "--min-turnover",
        type=float,
        default=1.0,
        help="Minimum 20-day average daily turnover floor in ₹ Crores.",
    )
    parser.add_argument(
        "--date",
        dest="execution_date",
        default=None,
        help="Optional override date (YYYY-MM-DD) for backfilling or scheduling.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    print("=" * 80)
    print("📡 BLUMBERG MARKET RADAR — NIGHTLY EOD AUTOMATION & PAPER TRACKING")
    print("=" * 80)
    print(f"Mode:             {args.mode.upper()}")
    print(f"Digest Directory: {args.output_dir}")
    print(f"Signal Ledger:    {args.ledger_path}")
    print(f"Min Radar Score:  {args.min_score}")
    print(f"Min Turnover:     ₹{args.min_turnover:.1f} Cr/day")
    print("-" * 80)

    start_time = time.time()
    try:
        print("[1/4] Ingesting daily OHLCV bars & corporate intelligence...")
        print("[2/4] Computing pre-rally range compression & volume footprint features...")
        print("[3/4] Ranking candidates and logging snapshots to signal ledger...")
        print("[4/4] Evaluating active paper tracking performance (MFE/MAE) & writing digest...")

        result = run_nightly_eod_pipeline(
            mode=args.mode,
            output_dir=args.output_dir,
            ledger_path=args.ledger_path,
            min_score=args.min_score,
            min_turnover_cr=args.min_turnover,
            execution_date=args.execution_date,
        )

        elapsed = time.time() - start_time
        print("\n" + "=" * 80)
        print("✅ NIGHTLY PIPELINE EXECUTION COMPLETED SUCCESSFULLY")
        print("=" * 80)
        print(f"Execution Date:       {result['execution_date']}")
        print(f"Bars Ingested:        {result['bars_ingested']:,} ({result['symbols_scanned']} equities)")
        print(f"Candidates Qualified: {result['qualified_candidates_count']}")
        if result["qualified_candidates"]:
            print(f"Qualified Symbols:    {', '.join(result['qualified_candidates'])}")
        print(f"Total Ledger Signals: {result['total_ledger_signals']}")
        print(f"Active Paper Signals: {result['active_tracked_signals']}")
        print(f"Median Peak MFE:      +{result['median_mfe_pct']:.2f}%")
        print(f"Median Adverse MAE:   {result['median_mae_pct']:.2f}%")
        print(f"Digest Markdown:      {result['report_path']}")
        print(f"Elapsed Time:         {elapsed:.2f} seconds")
        print("=" * 80)
        return 0

    except Exception as exc:
        print("\n" + "!" * 80, file=sys.stderr)
        print(f"❌ PIPELINE EXECUTION FAILED: {exc}", file=sys.stderr)
        print("!" * 80, file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
