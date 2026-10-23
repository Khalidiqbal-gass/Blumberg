"""Statistical Validation Engine: Maximum Favourable/Adverse Excursion (MFE/MAE) and Forward Rally Tracking."""
from __future__ import annotations

from dataclasses import dataclass
import numpy as np
import pandas as pd


@dataclass
class MFEValidationResult:
    signals_analyzed_df: pd.DataFrame
    total_signals: int
    median_mfe_20d: float
    median_mae_20d: float
    median_mfe_60d: float
    median_mae_60d: float
    benchmark_outperformance_rate_pct: float
    major_rally_rate_pct: float  # Percentage of signals delivering > +25% MFE
    false_positive_rate_pct: float  # Percentage of signals dropping > -8% before reaching +10%


def evaluate_pre_rally_signals(
    features_df: pd.DataFrame,
    benchmark_bars: pd.DataFrame | None = None,
    min_score_threshold: float = 60.0,
    horizons: tuple[int, ...] = (20, 60),
) -> MFEValidationResult:
    """Evaluate how stocks performed AFTER receiving an early-rally radar signal.

    Measures:
    - MFE (Maximum Favourable Excursion): Peak upside % reached in next H days.
    - MAE (Maximum Adverse Excursion): Max downside % experienced before/during rally.
    - Forward benchmark-relative alpha vs Nifty 50.
    - Time-to-Peak (sessions to reach highest high).
    """
    if features_df.empty:
        empty_df = pd.DataFrame()
        return MFEValidationResult(
            signals_analyzed_df=empty_df,
            total_signals=0,
            median_mfe_20d=0.0,
            median_mae_20d=0.0,
            median_mfe_60d=0.0,
            median_mae_60d=0.0,
            benchmark_outperformance_rate_pct=0.0,
            major_rally_rate_pct=0.0,
            false_positive_rate_pct=0.0,
        )

    # Benchmark forward returns lookup
    bench_fwd_20: dict[pd.Timestamp, float] = {}
    if benchmark_bars is not None and not benchmark_bars.empty:
        b_sorted = benchmark_bars.sort_values("date").reset_index(drop=True)
        b_sorted["fwd_20"] = b_sorted["close"].shift(-20) / b_sorted["close"] - 1.0
        bench_fwd_20 = dict(zip(b_sorted["date"], b_sorted["fwd_20"]))

    df = features_df.sort_values(["symbol", "date"]).copy()
    signal_records: list[dict] = []

    for sym, group in df.groupby("symbol", sort=False):
        sub = group.reset_index(drop=True)
        n = len(sub)

        for i in range(n - 60):  # Allow at least 60 forward sessions for outcome evaluation
            row = sub.iloc[i]
            rvol = float(row.get("relative_volume_20d") or 1.0)
            comp = float(row.get("range_compression_ratio") or 0.8)
            rs = float(row.get("rs_20d") or 0.0)

            # Pre-Rally Signal Criteria: Tight Base (compression < 0.70) + Volume Footprint (rvol > 1.4) + RS positive
            is_pre_rally = (comp <= 0.70) and (rvol >= 1.4) and (rs >= -0.01)

            if is_pre_rally:
                sig_date = row["date"]
                base_close = float(row["close"])

                # Forward windows
                window_20 = sub.iloc[i + 1 : i + 21]
                window_60 = sub.iloc[i + 1 : min(i + 61, n)]

                high_20 = float(window_20["high"].max())
                low_20 = float(window_20["low"].min())
                close_20 = float(window_20["close"].iloc[-1])

                high_60 = float(window_60["high"].max())
                low_60 = float(window_60["low"].min())
                close_60 = float(window_60["close"].iloc[-1])

                # MFE / MAE calculations (percentage excursions)
                mfe_20 = (high_20 / base_close - 1.0) * 100.0
                mae_20 = (low_20 / base_close - 1.0) * 100.0
                fwd_ret_20 = (close_20 / base_close - 1.0) * 100.0

                mfe_60 = (high_60 / base_close - 1.0) * 100.0
                mae_60 = (low_60 / base_close - 1.0) * 100.0
                fwd_ret_60 = (close_60 / base_close - 1.0) * 100.0

                # Sessions to reach 20D MFE
                high_idx_20 = int(window_20["high"].argmax()) + 1

                # Benchmark comparison
                b_fwd = bench_fwd_20.get(sig_date, 0.0) * 100.0
                beat_bench = fwd_ret_20 > b_fwd

                # Classification: Was this a major rally, normal advance, or false positive?
                is_major_rally = mfe_60 >= 25.0
                is_false_pos = mae_20 < -8.0 and mfe_20 < 10.0

                outcome_label = (
                    "MAJOR_RALLY (>+25%)"
                    if is_major_rally
                    else ("FALSE_POSITIVE" if is_false_pos else "CONTROLLED_ADVANCE")
                )

                signal_records.append({
                    "symbol": sym,
                    "signal_date": sig_date,
                    "signal_price": np.round(base_close, 2),
                    "compression_at_signal": np.round(comp, 2),
                    "volume_surge_at_signal": np.round(rvol, 2),
                    "mfe_20d_pct": np.round(mfe_20, 2),
                    "mae_20d_pct": np.round(mae_20, 2),
                    "fwd_ret_20d_pct": np.round(fwd_ret_20, 2),
                    "mfe_60d_pct": np.round(mfe_60, 2),
                    "mae_60d_pct": np.round(mae_60, 2),
                    "fwd_ret_60d_pct": np.round(fwd_ret_60, 2),
                    "days_to_peak": high_idx_20,
                    "beat_nifty_20d": beat_bench,
                    "outcome_classification": outcome_label,
                })

    sig_df = pd.DataFrame(signal_records)
    if sig_df.empty:
        return MFEValidationResult(
            signals_analyzed_df=sig_df,
            total_signals=0,
            median_mfe_20d=0.0,
            median_mae_20d=0.0,
            median_mfe_60d=0.0,
            median_mae_60d=0.0,
            benchmark_outperformance_rate_pct=0.0,
            major_rally_rate_pct=0.0,
            false_positive_rate_pct=0.0,
        )

    tot = len(sig_df)
    med_mfe_20 = float(sig_df["mfe_20d_pct"].median())
    med_mae_20 = float(sig_df["mae_20d_pct"].median())
    med_mfe_60 = float(sig_df["mfe_60d_pct"].median())
    med_mae_60 = float(sig_df["mae_60d_pct"].median())

    beat_rate = (sig_df["beat_nifty_20d"].sum() / tot) * 100.0
    major_rate = ((sig_df["outcome_classification"] == "MAJOR_RALLY (>+25%)").sum() / tot) * 100.0
    false_rate = ((sig_df["outcome_classification"] == "FALSE_POSITIVE").sum() / tot) * 100.0

    return MFEValidationResult(
        signals_analyzed_df=sig_df.sort_values("signal_date", ascending=False).reset_index(drop=True),
        total_signals=tot,
        median_mfe_20d=np.round(med_mfe_20, 1),
        median_mae_20d=np.round(med_mae_20, 1),
        median_mfe_60d=np.round(med_mfe_60, 1),
        median_mae_60d=np.round(med_mae_60, 1),
        benchmark_outperformance_rate_pct=np.round(beat_rate, 1),
        major_rally_rate_pct=np.round(major_rate, 1),
        false_positive_rate_pct=np.round(false_rate, 1),
    )
