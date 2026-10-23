"""Tests for early rally radar scanner and point-in-time backtesting engine."""
from blumberg_market_radar.data.ingestion import generate_synthetic_universe
from blumberg_market_radar.corporate_intel.events import get_corporate_events
from blumberg_market_radar.scanner.radar import compute_comprehensive_features, score_early_rally_candidates
from blumberg_market_radar.backtest.engine import run_point_in_time_backtest


def test_radar_scoring_pipeline():
    bars = generate_synthetic_universe(["BEL", "RELIANCE", "SUZLON"], num_days=60)
    events = get_corporate_events(["BEL", "SUZLON"])
    features = compute_comprehensive_features(bars)
    
    assert "relative_volume_20d" in features.columns
    assert "return_20d" in features.columns
    assert "atr_pct" in features.columns

    scored = score_early_rally_candidates(features, events, min_turnover_cr=0.1)
    assert not scored.empty
    assert "radar_score" in scored.columns
    assert "reason_codes" in scored.columns
    assert "risk_flags" in scored.columns
    assert (scored["radar_score"] >= 0).all() and (scored["radar_score"] <= 100).all()


def test_point_in_time_backtest_execution():
    bars = generate_synthetic_universe(["BEL", "HAL", "TRENT"], num_days=100)
    features = compute_comprehensive_features(bars)
    result = run_point_in_time_backtest(features, holding_days=15, cost_bps_per_side=10.0)

    assert result.win_rate_pct >= 0.0
    assert result.max_drawdown_pct >= 0.0
    if result.total_trades > 0:
        assert not result.trades_df.empty
        assert "exit_reason" in result.trades_df.columns
