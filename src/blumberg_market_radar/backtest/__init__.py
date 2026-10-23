"""Backtesting utilities with conservative execution assumptions."""
from blumberg_market_radar.backtest.baseline import (
    DEFAULT_INDIAN_STATUTORY_BPS_PER_SIDE,
    simulate_multiday_trend_trades,
    simulate_next_close_entries,
)
from blumberg_market_radar.backtest.engine import (
    BacktestResult,
    run_point_in_time_backtest,
)
from blumberg_market_radar.backtest.upgraded_vcp_engine import (
    BacktestSummary,
    UpgradedTrade,
    UpgradedVCPBacktestEngine,
)

__all__ = [
    "DEFAULT_INDIAN_STATUTORY_BPS_PER_SIDE",
    "simulate_multiday_trend_trades",
    "simulate_next_close_entries",
    "BacktestResult",
    "run_point_in_time_backtest",
    "UpgradedTrade",
    "BacktestSummary",
    "UpgradedVCPBacktestEngine",
]
