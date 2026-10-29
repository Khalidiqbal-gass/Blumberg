"""Backtest simulators for baseline 1-day benchmarks and multi-day trend holding."""
from __future__ import annotations

from typing import Any
import numpy as np
import pandas as pd
from blumberg_market_radar.data.validation import validate_ohlcv

# Statutory Indian equity delivery transaction cost:
# STT 0.1% buy + 0.1% sell (20 bps) + Stamp duty (1.5 bps) + Exchange/SEBI/GST (3.5 bps) + Slippage (27.6 bps)
# = 52.6 bps per side (105.2 bps round trip)
DEFAULT_INDIAN_STATUTORY_BPS_PER_SIDE = 52.6


def simulate_next_close_entries(
    bars_with_signal: pd.DataFrame,
    *,
    signal_column: str = "signal",
    cost_bps_per_side: float = DEFAULT_INDIAN_STATUTORY_BPS_PER_SIDE,
) -> pd.DataFrame:
    """Map a signal at t to close[t+1] entry and close[t+2] exit for 1-day benchmark testing.

    Calls validate_ohlcv to prevent duplicate or corrupted data from bypassing quality checks.
    """
    if cost_bps_per_side < 0:
        raise ValueError("cost_bps_per_side cannot be negative.")
    if signal_column not in bars_with_signal.columns:
        raise ValueError(f"Missing required signal column: '{signal_column}'")

    # Strict structural validation
    has_full_ohlcv = {"open", "high", "low", "volume"}.issubset(bars_with_signal.columns)
    if has_full_ohlcv:
        clean = validate_ohlcv(bars_with_signal, clean_glitches=True)
        clean[signal_column] = bars_with_signal.loc[clean.index, signal_column].fillna(False).astype(bool)
    else:
        # Close-only validation: reject duplicates and non-positive prices
        frame_input = bars_with_signal.copy()
        frame_input["date"] = pd.to_datetime(frame_input["date"], utc=True, errors="coerce")
        if frame_input["date"].isna().any():
            raise ValueError("Invalid date found.")
        frame_input["symbol"] = frame_input["symbol"].astype("string").str.strip().str.upper()
        if frame_input["symbol"].isna().any() or frame_input["symbol"].eq("").any():
            raise ValueError("Symbol cannot be empty.")
        frame_input["close"] = pd.to_numeric(frame_input["close"], errors="coerce")
        if frame_input["close"].isna().any() or (frame_input["close"] <= 0).any():
            raise ValueError("Close prices must be positive numeric values.")
        if frame_input.duplicated(["symbol", "date"], keep=False).any():
            raise ValueError("Duplicate symbol/date rows detected.")
        clean = frame_input

    frame = clean.sort_values(["symbol", "date"], kind="stable").reset_index(drop=True)
    frame["entry_close"] = frame.groupby("symbol")["close"].shift(-1)
    frame["exit_close"] = frame.groupby("symbol")["close"].shift(-2)
    frame["gross_return"] = frame["exit_close"] / frame["entry_close"] - 1.0
    
    one_side = cost_bps_per_side / 10_000.0
    frame["net_return"] = (1.0 + frame["gross_return"]) * (1.0 - one_side) ** 2 - 1.0

    # Clean hygiene: null all trade outcome columns for non-signal rows
    non_signals = ~frame[signal_column].astype(bool)
    frame.loc[non_signals, ["entry_close", "exit_close", "gross_return", "net_return"]] = np.nan
    frame["round_trip_cost_assumption"] = 2.0 * one_side
    return frame


def simulate_multiday_trend_trades(
    bars_with_signal: pd.DataFrame,
    *,
    signal_column: str = "signal",
    cost_bps_per_side: float = DEFAULT_INDIAN_STATUTORY_BPS_PER_SIDE,
    initial_stop_pct: float = -8.0,
    breakeven_trigger_pct: float = 15.0,
    trailing_trigger_pct: float = 25.0,
    trail_tier1_pct: float = -14.0,
    trail_tier2_trigger_pct: float = 50.0,
    trail_tier2_pct: float = -17.0,
    trail_tier3_trigger_pct: float = 100.0,
    trail_tier3_pct: float = -20.0,
    stagnation_days: int = 30,
    stagnation_min_gain_pct: float = 10.0,
    suppress_overlapping: bool = True,
    reject_upper_circuit_entry: bool = True,
) -> dict[str, Any]:
    """Simulate realistic multi-day trend following trades capturing 2x-5x multibagger rallies.

    Execution & Risk Engine:
      1. Entry: Fills at Day t+1 Open with cost_bps_per_side friction applied.
      2. Upper Circuit Rejection: If Day t+1 open == high == low, fill is rejected (cannot buy locked circuit).
      3. Overlapping Trade Suppression: A symbol cannot open a second trade while one is currently open.
      4. Complete Loop Boundary: Runs to range(entry_idx, n) so final bar exits and peak prices are evaluated.
      5. Risk Hierarchy (Stop-first conservative assumption):
         - Initial Hard Stop: Evaluated against intraday Low <= entry_price * (1 + initial_stop_pct/100).
         - Breakeven Stop: Low <= entry_price once peak gain reaches +15%.
         - Multi-tier Trailing Stop: Evaluated against daily Close once peak gain exceeds thresholds.
         - Stagnation Exit: Days held >= 30 and peak gain < 10% exits on Close.
    """
    if cost_bps_per_side < 0:
        raise ValueError("cost_bps_per_side cannot be negative.")
    if signal_column not in bars_with_signal.columns:
        raise ValueError(f"Missing required signal column: '{signal_column}'")

    clean = validate_ohlcv(bars_with_signal, clean_glitches=True)
    clean[signal_column] = bars_with_signal.loc[clean.index, signal_column].fillna(False).astype(bool)

    one_side = cost_bps_per_side / 10_000.0
    trades: list[dict[str, Any]] = []
    unfilled_circuit_count = 0

    for sym, group in clean.groupby("symbol", sort=False):
        df = group.sort_values("date").reset_index(drop=True)
        n = len(df)
        active_trade: dict[str, Any] | None = None

        for i in range(n):
            current_bar = df.iloc[i]
            has_signal = bool(current_bar[signal_column])

            # Manage active position
            if active_trade is not None:
                entry_price = active_trade["entry_price"]
                raw_high = current_bar["high"]
                raw_low = current_bar["low"]
                raw_close = current_bar["close"]
                bar_date = current_bar["date"]

                if raw_high > active_trade["peak_price"]:
                    active_trade["peak_price"] = raw_high
                    active_trade["peak_date"] = bar_date

                peak_price = active_trade["peak_price"]
                peak_gain = (peak_price / entry_price - 1.0) * 100.0
                active_trade["days_held"] += 1
                days_held = active_trade["days_held"]

                trade_closed = False
                exit_price = 0.0
                exit_reason = ""

                # 1. Initial Stop Loss (Intraday Low <= entry * (1 + initial_stop_pct/100))
                hard_stop_price = entry_price * (1.0 + initial_stop_pct / 100.0)
                if peak_gain < breakeven_trigger_pct and raw_low <= hard_stop_price:
                    exit_price = min(hard_stop_price, current_bar["open"]) * (1.0 - one_side)
                    exit_reason = f"Initial Stop Loss ({initial_stop_pct:.1f}%)"
                    trade_closed = True

                # 2. Breakeven Stop (Intraday Low <= entry once peak_gain >= 15%)
                elif peak_gain >= breakeven_trigger_pct and peak_gain < trailing_trigger_pct and raw_low <= entry_price:
                    exit_price = min(entry_price, current_bar["open"]) * (1.0 - one_side)
                    exit_reason = "Breakeven Stop (+15% reached)"
                    trade_closed = True

                # 3. Dynamic Multi-Tier Trailing Stop (Close based)
                elif peak_gain >= trailing_trigger_pct:
                    if peak_gain >= trail_tier3_trigger_pct:
                        trail_pct = trail_tier3_pct
                    elif peak_gain >= trail_tier2_trigger_pct:
                        trail_pct = trail_tier2_pct
                    else:
                        trail_pct = trail_tier1_pct

                    trail_exit_threshold = peak_price * (1.0 + trail_pct / 100.0)
                    if raw_close <= trail_exit_threshold:
                        exit_price = raw_close * (1.0 - one_side)
                        exit_reason = f"Trailing Stop ({trail_pct:.1f}% from peak)"
                        trade_closed = True

                # 4. Stagnation Exit
                if not trade_closed and days_held >= stagnation_days and peak_gain < stagnation_min_gain_pct:
                    exit_price = raw_close * (1.0 - one_side)
                    exit_reason = f"Stagnation Exit ({stagnation_days}d < {stagnation_min_gain_pct:.0f}%)"
                    trade_closed = True

                # 5. Final Date End of Period Exit (Full loop reaches n)
                if not trade_closed and i == n - 1:
                    exit_price = raw_close * (1.0 - one_side)
                    exit_reason = "Open Position (End of Period)"
                    trade_closed = True

                if trade_closed:
                    net_return = (exit_price / entry_price - 1.0) * 100.0
                    active_trade["exit_date"] = bar_date
                    active_trade["exit_price"] = exit_price
                    active_trade["exit_reason"] = exit_reason
                    active_trade["peak_gain_pct"] = peak_gain
                    active_trade["net_return_pct"] = net_return
                    trades.append(active_trade)
                    active_trade = None

            # New Entry Trigger (Day t+1 Open Fill)
            if has_signal:
                if active_trade is not None and suppress_overlapping:
                    # Suppress overlapping signals for symbol with open trade
                    continue

                if i + 1 < n:
                    next_bar = df.iloc[i + 1]
                    # Upper Circuit Check on Day t+1
                    is_circuit = (next_bar["open"] == next_bar["high"]) and (next_bar["high"] == next_bar["low"])
                    if reject_upper_circuit_entry and is_circuit:
                        unfilled_circuit_count += 1
                        continue

                    # Fill at Day t+1 Open
                    fill_price = next_bar["open"] * (1.0 + one_side)
                    active_trade = {
                        "symbol": sym,
                        "signal_date": current_bar["date"],
                        "entry_date": next_bar["date"],
                        "entry_price": fill_price,
                        "peak_price": fill_price,
                        "peak_date": next_bar["date"],
                        "days_held": 0,
                    }

    trades_df = pd.DataFrame(trades)
    if trades_df.empty:
        return {
            "trades": trades_df,
            "total_trades": 0,
            "profit_factor": 0.0,
            "win_rate": 0.0,
            "avg_net_return": 0.0,
            "unfilled_circuit_count": unfilled_circuit_count,
        }

    gains = trades_df.loc[trades_df["net_return_pct"] > 0, "net_return_pct"].sum()
    losses = abs(trades_df.loc[trades_df["net_return_pct"] <= 0, "net_return_pct"].sum())
    pf = float(gains / losses) if losses > 0 else (999.0 if gains > 0 else 0.0)
    win_rate = float((trades_df["net_return_pct"] > 0).mean() * 100.0)
    avg_return = float(trades_df["net_return_pct"].mean())

    return {
        "trades": trades_df,
        "total_trades": len(trades_df),
        "profit_factor": pf,
        "win_rate": win_rate,
        "avg_net_return": avg_return,
        "unfilled_circuit_count": unfilled_circuit_count,
    }
