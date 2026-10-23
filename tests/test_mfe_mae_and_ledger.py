"""Unit tests for MFE/MAE validation engine and Signal Ledger."""
from blumberg_market_radar.data.ingestion import generate_synthetic_universe
from blumberg_market_radar.scanner.radar import compute_pre_rally_features, score_pre_rally_candidates
from blumberg_market_radar.backtest.mfe_mae import evaluate_pre_rally_signals
from blumberg_market_radar.ledger.journal import record_signal_snapshots, load_signal_ledger


def test_mfe_mae_evaluation(tmp_path):
    bars = generate_synthetic_universe(["BEL", "MAZDOCK", "TRENT"], num_days=120)
    features = compute_pre_rally_features(bars)
    
    assert "range_compression_ratio" in features.columns
    assert "volume_dry_up_ratio" in features.columns
    assert "relative_volume_20d" in features.columns

    res = evaluate_pre_rally_signals(features)
    assert res.total_signals >= 0
    if res.total_signals > 0:
        assert not res.signals_analyzed_df.empty
        assert "mfe_20d_pct" in res.signals_analyzed_df.columns
        assert "mae_20d_pct" in res.signals_analyzed_df.columns
        assert (res.signals_analyzed_df["mfe_20d_pct"] >= res.signals_analyzed_df["mae_20d_pct"]).all()


def test_signal_ledger_snapshot(tmp_path):
    ledger_file = tmp_path / "test_ledger.jsonl"
    bars = generate_synthetic_universe(["BEL", "HAL"], num_days=60)
    features = compute_pre_rally_features(bars)
    scored = score_pre_rally_candidates(features)

    snaps = record_signal_snapshots(scored.head(3), ledger_path=ledger_file)
    assert len(snaps) <= 3

    loaded = load_signal_ledger(ledger_path=ledger_file)
    assert len(loaded) == len(snaps)
    assert "price_at_signal" in loaded.columns
    assert "radar_score" in loaded.columns
