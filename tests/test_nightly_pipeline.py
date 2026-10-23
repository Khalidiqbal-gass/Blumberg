"""Unit and integration tests for the Nightly EOD Automation & Paper Tracking Pipeline."""
import subprocess
import sys
from pathlib import Path
import pandas as pd
import pytest

from blumberg_market_radar.data.ingestion import generate_synthetic_universe
from blumberg_market_radar.ledger.journal import load_signal_ledger, record_signal_snapshots
from blumberg_market_radar.pipeline.nightly import (
    evaluate_active_paper_signals,
    generate_market_regime_summary,
    run_nightly_eod_pipeline,
)


def test_nightly_pipeline_end_to_end(tmp_path):
    """Test full execution of nightly pipeline in offline mode."""
    out_dir = tmp_path / "digests"
    ledger_file = tmp_path / "ledger.jsonl"

    result = run_nightly_eod_pipeline(
        mode="offline",
        output_dir=out_dir,
        ledger_path=ledger_file,
        min_score=40.0,
        symbols=["BEL", "HAL", "MAZDOCK", "TRENT"],
        execution_date="2026-10-22",
    )

    assert result["status"] == "SUCCESS"
    assert result["mode"] == "offline"
    assert result["execution_date"] == "2026-10-22"
    assert result["bars_ingested"] == 4 * 300
    assert result["symbols_scanned"] == 4
    assert result["report_path"] == str(out_dir / "DIGEST_2026-10-22.md")

    # Verify report file exists and has expected structure
    digest_path = Path(result["report_path"])
    assert digest_path.exists()
    content = digest_path.read_text(encoding="utf-8")

    assert "# 📡 Blumberg Market Radar — End-of-Day Intelligence Digest" in content
    assert "## 1. 🌐 Executive Summary & Market Regime" in content
    assert "## 2. 🎯 Qualified Pre-Rally Candidates Flagged Today" in content
    assert "## 3. 📈 Active Paper Tracking Performance" in content
    assert "## 4. 🛡️ Data Quality & Integrity Audit Stamp" in content
    assert "AUDIT_PASSED" in content


def test_ledger_append_only_persistence(tmp_path):
    """Verify that recurring nightly pipeline runs append to ledger without overwriting history."""
    out_dir = tmp_path / "digests"
    ledger_file = tmp_path / "ledger.jsonl"

    # First run
    res1 = run_nightly_eod_pipeline(
        mode="offline",
        output_dir=out_dir,
        ledger_path=ledger_file,
        min_score=40.0,
        symbols=["BEL", "HAL", "TRENT"],
    )
    assert ledger_file.exists()
    ledger_df1 = load_signal_ledger(ledger_file)
    n1 = len(ledger_df1)
    assert n1 > 0

    # Second run on next day
    res2 = run_nightly_eod_pipeline(
        mode="offline",
        output_dir=out_dir,
        ledger_path=ledger_file,
        min_score=40.0,
        symbols=["BEL", "HAL", "TRENT"],
        execution_date="2026-10-23",
    )
    ledger_df2 = load_signal_ledger(ledger_file)
    n2 = len(ledger_df2)

    # Append-only check: total ledger count must increase
    assert n2 >= n1 + res2["qualified_candidates_count"]
    assert "signal_id" in ledger_df2.columns
    assert "price_at_signal" in ledger_df2.columns


def test_digest_when_no_candidates_qualify(tmp_path):
    """Verify clean handling and capital preservation note when threshold is strict."""
    out_dir = tmp_path / "digests"
    ledger_file = tmp_path / "ledger.jsonl"

    result = run_nightly_eod_pipeline(
        mode="offline",
        output_dir=out_dir,
        ledger_path=ledger_file,
        min_score=999.0,  # Unattainable score threshold
        symbols=["BEL", "HAL"],
    )

    assert result["status"] == "SUCCESS"
    assert result["qualified_candidates_count"] == 0

    digest_path = Path(result["report_path"])
    assert digest_path.exists()
    content = digest_path.read_text(encoding="utf-8")

    assert "No candidates qualified today" in content
    assert "Capital preservation protocol maintained" in content


def test_market_regime_and_breadth_evaluation():
    """Verify market regime analysis calculation on benchmark & universe bars."""
    bars = generate_synthetic_universe(["BEL", "HAL", "TRENT"], num_days=100)
    dates = sorted(bars["date"].unique())
    bench_bars = pd.DataFrame({
        "date": dates,
        "symbol": "NIFTY50",
        "open": 24000.0,
        "high": 24200.0,
        "low": 23900.0,
        "close": 24150.0,
        "volume": 10000000,
    })

    summary = generate_market_regime_summary(bench_bars, bars)
    assert "nifty_close" in summary
    assert "regime" in summary
    assert "breadth_above_20d_pct" in summary
    assert summary["regime"] in ["BULLISH_EXPANSION", "CONSOLIDATION_NEUTRAL", "DEFENSIVE_PULLBACK"]
    assert 0.0 <= summary["breadth_above_20d_pct"] <= 100.0


def test_active_paper_signals_evaluation(tmp_path):
    """Verify calculation of MFE, MAE, current PnL and lifecycle status for active paper tracking."""
    ledger_file = tmp_path / "test_paper_ledger.jsonl"
    bars = generate_synthetic_universe(["BEL"], num_days=60)
    latest_bar = bars.sort_values("date").iloc[-1]
    ref_price = float(latest_bar["close"])

    scored_mock = pd.DataFrame([{
        "symbol": "BEL",
        "close": ref_price,
        "radar_score": 75.0,
        "compression_ratio": 0.45,
        "relative_volume": 2.2,
        "rs_20d_pct": 12.5,
        "primary_driver": "VCP Base Breakout",
        "reason_codes": ["Tight Base", "Accumulation Surge"],
        "risk_flags": ["Normal Risk"],
        "catalyst_summary": "Major export order",
    }])
    record_signal_snapshots(scored_mock, ledger_path=ledger_file)

    ledger_df = load_signal_ledger(ledger_file)
    tracking_df, stats = evaluate_active_paper_signals(ledger_df, bars)

    assert not tracking_df.empty
    assert stats["total_signals"] == 1
    assert "mfe_pct" in tracking_df.columns
    assert "mae_pct" in tracking_df.columns
    assert "status" in tracking_df.columns
    assert tracking_df.iloc[0]["mfe_pct"] >= tracking_df.iloc[0]["mae_pct"]


def test_invalid_mode_raises_value_error(tmp_path):
    """Pipeline should reject invalid execution modes."""
    with pytest.raises(ValueError, match="Invalid mode"):
        run_nightly_eod_pipeline(mode="unsupported_mode", output_dir=tmp_path)


def test_cli_execution_subprocess(tmp_path):
    """Test running nightly_eod_pipeline CLI via python subprocess."""
    out_dir = tmp_path / "cli_digests"
    ledger_path = tmp_path / "cli_ledger.jsonl"

    cmd = [
        sys.executable,
        "scripts/nightly_eod_pipeline.py",
        "--mode", "offline",
        "--output", str(out_dir),
        "--ledger", str(ledger_path),
        "--min-score", "40.0",
        "--date", "2026-10-22",
    ]

    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, f"CLI stderr: {proc.stderr}"
    assert "NIGHTLY PIPELINE EXECUTION COMPLETED SUCCESSFULLY" in proc.stdout
    assert (out_dir / "DIGEST_2026-10-22.md").exists()
    assert ledger_path.exists()
