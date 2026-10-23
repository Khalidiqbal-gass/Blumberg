"""Deterministic price/volume features and an institutional early-rally signal."""
from __future__ import annotations

import numpy as np
import pandas as pd
from blumberg_market_radar.data.validation import validate_ohlcv


def build_daily_features(
    bars: pd.DataFrame,
    *,
    max_calendar_gap_5d: int = 15,
    max_calendar_gap_20d: int = 45,
) -> pd.DataFrame:
    """Build lag-safe rolling features for each symbol with calendar-gap validation.

    Production input should first pass a documented corporate-action adjustment process.
    Features at t use data available through t; they do not imply a fill at that same close.
    """
    clean = validate_ohlcv(bars, tag_microstructure=True)
    feature_names = (
        "return_5d",
        "return_20d",
        "relative_volume_20d",
        "volatility_20d",
        "turnover",
        "calendar_days_5d",
        "calendar_days_20d",
    )
    if clean.empty:
        for name in feature_names:
            clean[name] = pd.Series(dtype="float64")
        return clean

    parts = []
    for _, group in clean.groupby("symbol", sort=False):
        part = group.copy()
        close = part["close"]
        volume = part["volume"]
        dates = part["date"]

        # Turnover (traded value in currency units)
        part["turnover"] = close * volume

        # Calendar gap check
        date_shift_5 = dates.shift(5)
        date_shift_20 = dates.shift(20)
        part["calendar_days_5d"] = (dates - date_shift_5).dt.days
        part["calendar_days_20d"] = (dates - date_shift_20).dt.days

        raw_ret_5d = close.pct_change(5, fill_method=None)
        raw_ret_20d = close.pct_change(20, fill_method=None)

        # Invalidate returns across prolonged trading suspensions or data gaps
        part["return_5d"] = raw_ret_5d.where(part["calendar_days_5d"] <= max_calendar_gap_5d, np.nan)
        part["return_20d"] = raw_ret_20d.where(part["calendar_days_20d"] <= max_calendar_gap_20d, np.nan)

        prior_volume_mean = volume.shift(1).rolling(20, min_periods=10).mean()
        part["relative_volume_20d"] = volume / prior_volume_mean.where(prior_volume_mean > 0)
        part["volatility_20d"] = close.pct_change(fill_method=None).rolling(20, min_periods=10).std()
        parts.append(part)

    return pd.concat(parts, ignore_index=True).sort_values(
        ["symbol", "date"], kind="stable"
    ).reset_index(drop=True)


def baseline_early_rally_signal(
    features: pd.DataFrame,
    *,
    min_relative_volume: float = 1.5,
    max_return_20d: float | None = None,
    max_volatility_20d: float | None = None,
    min_turnover: float | None = None,
    suppress_circuits: bool = True,
) -> pd.Series:
    """Return an early-rally breakout signal designed to catch multibaggers before late-stage chasing.

    Filters:
      - Positive short-term ignition: return_5d > 0
      - Early-stage breakout: return_20d > 0
      - Overextension upper bound: return_20d <= max_return_20d (prevents chasing stocks up 50%-100%)
      - Institutional volume surge: relative_volume_20d >= min_relative_volume
      - Volatility contraction base: volatility_20d <= max_volatility_20d (if specified)
      - Minimum liquidity: turnover >= min_turnover (if specified)
      - Circuit freeze rejection: suppresses Upper/Lower circuit bars if suppress_circuits is True.
    """
    required = {"return_5d", "return_20d", "relative_volume_20d"}
    missing = required - set(features.columns)
    if missing:
        raise ValueError(f"Missing feature columns: {', '.join(sorted(missing))}")

    condition = (
        features["return_5d"].gt(0)
        & features["return_20d"].gt(0)
        & features["relative_volume_20d"].ge(min_relative_volume)
    )

    # Upper bound to prevent chasing already overextended rallies
    if max_return_20d is not None:
        condition = condition & features["return_20d"].le(max_return_20d)

    # Volatility contraction / tight consolidation base check
    if max_volatility_20d is not None and "volatility_20d" in features.columns:
        condition = condition & features["volatility_20d"].le(max_volatility_20d)

    # Liquidity / turnover filter
    if min_turnover is not None and "turnover" in features.columns:
        condition = condition & features["turnover"].ge(min_turnover)

    # Circuit lock & zero volume suppression
    if suppress_circuits:
        if "is_circuit_locked" in features.columns:
            condition = condition & (~features["is_circuit_locked"].fillna(False))
        if "is_zero_volume" in features.columns:
            condition = condition & (~features["is_zero_volume"].fillna(False))

    return condition.fillna(False).astype(bool)
