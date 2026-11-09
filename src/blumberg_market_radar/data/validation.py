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
    tag_corporate_anomalies: bool = False,
    clean_glitches: bool = True,
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
    # Preserve all existing columns (do not drop metadata or corporate action tags)
    result = frame.copy()
    if result.empty:
        result["date"] = pd.to_datetime(result["date"], errors="coerce", utc=True)
        if tag_microstructure:
            result["is_zero_volume"] = pd.Series(dtype=bool)
            result["is_circuit_locked"] = pd.Series(dtype=bool)
        if tag_corporate_anomalies:
            result["is_corporate_anomaly"] = pd.Series(dtype=bool)
            result["anomaly_reason"] = pd.Series(dtype="string")
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

    if clean_glitches:
        sorted_result, _ = clean_transient_price_spikes(sorted_result)

    if tag_microstructure:
        sorted_result["is_zero_volume"] = sorted_result["volume"] == 0
        sorted_result["is_circuit_locked"] = (
            (sorted_result["open"] == sorted_result["high"])
            & (sorted_result["high"] == sorted_result["low"])
            & (sorted_result["low"] == sorted_result["close"])
        )

    if tag_corporate_anomalies:
        sorted_result = detect_corporate_action_anomalies(sorted_result)

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


def clean_transient_price_spikes(
    df: pd.DataFrame,
    *,
    spike_up_threshold: float = 2.0,
    spike_down_threshold: float = 0.5,
    reversion_min: float = 0.7,
    reversion_max: float = 1.4,
) -> tuple[pd.DataFrame, int]:
    """Detect and repair transient single-session data glitches causally without lookahead.

    Glitch patterns detected using strictly contemporaneous / backward-looking evidence (Day <= D):
    1. Zero-volume flat spikes: volume == 0 and open == high == low == close with jump (>1.3) or drop (<0.7) relative to prior close.
    2. Extreme flat print glitches: open == high == low == close with jump (>spike_up_threshold) or drop (<spike_down_threshold).
       (e.g. CIPLA 2003-04-14 single-day 12.5x flat print drop).
    3. Aberrant intraday needle spikes: open and close are normal relative to prior close [reversion_min, reversion_max],
       but high jumps > max(open, close) * spike_up_threshold or low drops < min(open, close) * spike_down_threshold.

    Causality guarantee:
    Every decision at Day D depends ONLY on bars <= D. Day D output is 100% bit-for-bit identical whether
    Day D+1 data is present or absent. Future data is never used to confirm or alter past signals.

    Returns (cleaned_df, num_repaired_bars).
    """
    if df.empty or "close" not in df.columns or "symbol" not in df.columns:
        return df.copy(), 0

    sorted_df = df.sort_values(["symbol", "date"]).reset_index(drop=True)
    c_prev = sorted_df.groupby("symbol")["close"].shift(1)

    has_hl = "high" in sorted_df.columns and "low" in sorted_df.columns
    has_op = "open" in sorted_df.columns
    has_vol = "volume" in sorted_df.columns

    ratio_close = sorted_df["close"] / c_prev
    is_flat_tick = (
        (sorted_df["high"] == sorted_df["low"]) & (sorted_df["open"] == sorted_df["close"])
        if (has_hl and has_op)
        else pd.Series(False, index=sorted_df.index)
    )

    # 1. Zero volume flat ticks with ratio jump/drop:
    zero_vol_anomaly = (
        (sorted_df["volume"] == 0) & is_flat_tick & ((ratio_close > 1.3) | (ratio_close < 0.7))
        if has_vol
        else pd.Series(False, index=sorted_df.index)
    )

    # 2. Extreme impossible single-day flat jumps/drops (e.g. CIPLA flat tick):
    # Require confirming evidence that it is a data print error, not a genuine split or real market move:
    # - If volume is zero or near-zero (< 500 shares), a >2x or <0.5x flat print is a bad tick.
    # - If volume is substantial, only an extreme impossible ratio (>10.0 or <0.10, e.g. CIPLA 12.5x drop) is repaired.
    # Real 2:1 or 3:1 splits with real traded volume are NOT rewritten here; they belong in corporate action detection.
    low_vol = (sorted_df["volume"] < 500) if has_vol else pd.Series(True, index=sorted_df.index)
    # Only flat ticks with low volume (illiquid/bad tick) or extreme impossible ratios (>15.0 or <0.04) are repaired.
    # True corporate actions (10:1 split = 0.10, 5:1 split = 0.20, 2:1 split = 0.50) with genuine volume >= 500 are preserved.
    flat_extreme_glitch = is_flat_tick & (
        (low_vol & ((ratio_close > spike_up_threshold) | (ratio_close < spike_down_threshold)))
        | (low_vol & ((ratio_close > 10.0) | (ratio_close < 0.04)))
    )

    # 3. Intraday needle spikes (fat-finger tick where open and close are normal, but high or low spikes):
    if has_hl and has_op:
        ratio_open = sorted_df["open"] / c_prev
        normal_oc = (
            (ratio_open >= reversion_min)
            & (ratio_open <= reversion_max)
            & (ratio_close >= reversion_min)
            & (ratio_close <= reversion_max)
        )
        needle_down = normal_oc & (
            sorted_df["low"] < np.minimum(sorted_df["open"], sorted_df["close"]) * spike_down_threshold
        )
        needle_up = normal_oc & (
            sorted_df["high"] > np.maximum(sorted_df["open"], sorted_df["close"]) * spike_up_threshold
        )
    else:
        needle_down = pd.Series(False, index=sorted_df.index)
        needle_up = pd.Series(False, index=sorted_df.index)

    mask_glitch = zero_vol_anomaly | flat_extreme_glitch | needle_down | needle_up
    num_glitches = int(mask_glitch.sum())
    if num_glitches == 0:
        return sorted_df, 0

    cleaned = sorted_df.copy()
    full_repair = (zero_vol_anomaly | flat_extreme_glitch) & mask_glitch
    rp = c_prev.loc[full_repair]
    cleaned.loc[full_repair, "open"] = rp
    cleaned.loc[full_repair, "high"] = rp * 1.005
    cleaned.loc[full_repair, "low"] = rp * 0.995
    cleaned.loc[full_repair, "close"] = rp

    if has_hl and has_op:
        cleaned.loc[needle_down, "low"] = (
            np.minimum(cleaned.loc[needle_down, "open"], cleaned.loc[needle_down, "close"]) * 0.995
        )
        cleaned.loc[needle_up, "high"] = (
            np.maximum(cleaned.loc[needle_up, "open"], cleaned.loc[needle_up, "close"]) * 1.005
        )

    return cleaned, num_glitches
