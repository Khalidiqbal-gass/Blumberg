"""Strict validation and microstructure tagging for daily OHLCV bars before feature calculation."""
from __future__ import annotations

import numpy as np
import pandas as pd

REQUIRED_COLUMNS = ("date", "symbol", "open", "high", "low", "close", "volume")
NUMERIC_COLUMNS = ("open", "high", "low", "close", "volume")


class MarketDataError(ValueError):
    """Raised when market data is malformed or unsafe to process."""


def validate_ohlcv(
    frame: pd.DataFrame,
    *,
    tag_microstructure: bool = False,
) -> pd.DataFrame:
    """Validate daily OHLCV rows and return a sorted copy.

    Reject duplicate symbol/date pairs instead of silently choosing a row.
    Uses fast vectorized numpy checks.
    
    If `tag_microstructure` is True, adds boolean flags:
      - `is_zero_volume`: volume == 0 (illiquid/suspended trading)
      - `is_circuit_locked`: open == high == low == close (circuit freeze)
    """
    if not isinstance(frame, pd.DataFrame):
        raise MarketDataError("Input must be a pandas DataFrame.")
    missing = sorted(set(REQUIRED_COLUMNS) - set(frame.columns))
    if missing:
        raise MarketDataError(f"Missing required columns: {', '.join(missing)}")
    result = frame.loc[:, REQUIRED_COLUMNS].copy()
    if result.empty:
        result["date"] = pd.to_datetime(result["date"], errors="coerce", utc=True)
        if tag_microstructure:
            result["is_zero_volume"] = pd.Series(dtype=bool)
            result["is_circuit_locked"] = pd.Series(dtype=bool)
        return result

    result["date"] = pd.to_datetime(result["date"], errors="coerce", utc=True)
    if result["date"].isna().any():
        raise MarketDataError("One or more dates are missing or invalid.")
    result["symbol"] = result["symbol"].astype("string").str.strip().str.upper()
    if result["symbol"].isna().any() or result["symbol"].eq("").any():
        raise MarketDataError("Symbol cannot be empty.")

    # Vectorized numeric conversion and finite checks
    for column in NUMERIC_COLUMNS:
        result[column] = pd.to_numeric(result[column], errors="coerce")
        col_vals = result[column].to_numpy(dtype=np.float64)
        if np.isnan(col_vals).any():
            raise MarketDataError(f"Column '{column}' contains missing or non-numeric values.")
        if not np.isfinite(col_vals).all():
            raise MarketDataError(f"Column '{column}' contains non-finite values.")

    # Vectorized price bounds check
    price_cols = ["open", "high", "low", "close"]
    if (result[price_cols].to_numpy() <= 0).any():
        raise MarketDataError("OHLC prices must be greater than zero.")
    if (result["volume"].to_numpy() < 0).any():
        raise MarketDataError("Volume cannot be negative.")

    # Vectorized high/low candle consistency check
    o_vals = result["open"].to_numpy()
    h_vals = result["high"].to_numpy()
    l_vals = result["low"].to_numpy()
    c_vals = result["close"].to_numpy()

    invalid = (h_vals < np.maximum(o_vals, c_vals)) | (l_vals > np.minimum(o_vals, c_vals))
    if invalid.any():
        raise MarketDataError("Found inconsistent OHLC candle: high/low does not contain open/close.")

    duplicates = result.duplicated(["symbol", "date"], keep=False)
    if duplicates.any():
        sample = result.loc[duplicates, ["symbol", "date"]].head(3).to_dict("records")
        raise MarketDataError(f"Duplicate symbol/date rows detected (sample: {sample}).")

    sorted_result = result.sort_values(["symbol", "date"], kind="stable").reset_index(drop=True)

    if tag_microstructure:
        sorted_result["is_zero_volume"] = sorted_result["volume"] == 0
        sorted_result["is_circuit_locked"] = (
            (sorted_result["open"] == sorted_result["high"])
            & (sorted_result["high"] == sorted_result["low"])
            & (sorted_result["low"] == sorted_result["close"])
        )

    return sorted_result


def detect_corporate_action_anomalies(
    frame: pd.DataFrame,
    *,
    drop_threshold_pct: float = -40.0,
    volume_spike_multiplier: float = 3.0,
) -> pd.DataFrame:
    """Identify suspicious single-day price drops that indicate unadjusted corporate actions (splits/demergers).

    If a stock drops by >40% in a single session without an accompanying massive volume surge or news,
    it is almost always an unadjusted stock split or demerger (e.g. Vedanta 758 -> 283 on 2026-04-30).
    """
    clean = validate_ohlcv(frame)
    if clean.empty:
        clean["is_corporate_anomaly"] = pd.Series(dtype=bool)
        clean["anomaly_reason"] = pd.Series(dtype="string")
        return clean

    parts = []
    for _, group in clean.groupby("symbol", sort=False):
        part = group.copy()
        prev_close = part["close"].shift(1)
        day_ret_pct = (part["close"] / prev_close - 1.0) * 100.0
        
        # 20-day median volume
        med_vol = part["volume"].shift(1).rolling(20, min_periods=5).median()
        vol_ratio = part["volume"] / med_vol.where(med_vol > 0, 1.0)
        
        # Flag if drop exceeds threshold and volume is NOT an extreme panic liquidation (typical split signature)
        is_split_candidate = (day_ret_pct <= drop_threshold_pct) & (vol_ratio < volume_spike_multiplier)
        
        part["is_corporate_anomaly"] = is_split_candidate.fillna(False)
        part["anomaly_reason"] = pd.Series(
            np.where(
                part["is_corporate_anomaly"],
                f"Unadjusted split/demerger signature: Single-day drop <= {drop_threshold_pct:.0f}%",
                ""
            ),
            dtype="string"
        )
        parts.append(part)

    return pd.concat(parts, ignore_index=True).sort_values(["symbol", "date"], kind="stable").reset_index(drop=True)
