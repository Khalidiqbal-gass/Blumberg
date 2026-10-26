"""4-Layer Staged Pre-Rally Pipeline Tracker.

Tracks stocks from the exact session they enter the radar watchlist through four distinct incubation layers:
- Layer 1 (0 to 10 Days): Ignition & Base Squeeze Hold (Day 0 Discovery)
- Layer 2 (11 to 20 Days): Early Breakout & Optimal Buy Zone (Requires confirmed price growth > 0%)
- Layer 3 (21 to 30 Days): Trend Momentum Acceleration (Requires sustained price growth >= +5%)
- Layer 4 (31 to 60 Days): Major Explosive / Multibagger Expansion (Requires sustained price growth >= +15% or peak MFE >= 25%)

Growth-Based Filtering:
Stocks DO NOT automatically advance to higher layers based on days alone.
A stock MUST grow (positive gain above entry price) to graduate from Layer 1 to Layer 2, 3, and 4.
If a stock fails to grow after 10 days, it remains locked in Layer 1 (stagnant base) or gets stopped out at -8%.
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

DEFAULT_PIPELINE_PATH = Path("data/staged_pipeline.json")

LAYER_1_NAME = "Layer 1: Ignition (0-10D)"
LAYER_2_NAME = "Layer 2: Early Breakout (11-20D)"
LAYER_3_NAME = "Layer 3: Trend Momentum (21-30D)"
LAYER_4_NAME = "Layer 4: Explosive Rally (31-60D)"


def classify_layer_by_days(days: int) -> str:
    """Assign default incubation horizon based on days elapsed."""
    if days <= 10:
        return LAYER_1_NAME
    elif days <= 20:
        return LAYER_2_NAME
    elif days <= 30:
        return LAYER_3_NAME
    else:
        return LAYER_4_NAME


def classify_layer_by_growth(
    days: int,
    current_gain_pct: float,
    max_mae_pct: float,
    current_layer: str = LAYER_1_NAME,
    stop_loss_pct: float = -8.0,
    peak_mfe_pct: float = 0.0,
) -> tuple[str, str]:
    """Assign active layer and status strictly on the basis of growth & risk preservation.
    
    Core Philosophy:
    1. If stock dips <= -8%, it triggers STOP_LOSS_DROPPED immediately.
    2. Layer 1 (0–10 Days): Stock stays in Layer 1.
       - When days >= 10:
         * If current_gain_pct > 0.0%: Graduates to Layer 2 (Early Breakout)!
         * If current_gain_pct <= 0.0%: STAYS in Layer 1 (Stagnant Base, waiting for growth).
    3. Layer 2 (11–20 Days):
       - When days >= 20:
         * If current_gain_pct >= 5.0%: Graduates to Layer 3 (Trend Momentum)!
         * If current_gain_pct > 0.0%: Stays in Layer 2 (Consolidating Breakout).
         * If current_gain_pct <= 0.0%: Pulls back to Layer 1.
    4. Layer 3 (21–30 Days):
       - When days >= 30:
         * If current_gain_pct >= 15.0% or peak_mfe_pct >= 25.0%: Graduates to Layer 4 (Multibagger Zone)!
         * Else: Stays in Layer 3.
    5. Layer 4 (31–60 Days):
       - Peak MFE >= 50%: TARGET_ACHIEVED (🚀 +50%+ Multibagger)
       - Peak MFE >= 25%: RALLY_LEADER (🔥 +25%+ Expansion)
    """
    # 1. Stop-Loss Trigger
    if max_mae_pct <= stop_loss_pct and current_gain_pct <= 0.0:
        return current_layer, "STOP_LOSS_DROPPED (⚠️ -8% Hit)"

    # 2. Layer 1 Evaluation
    if current_layer == LAYER_1_NAME or days <= 10:
        if days < 10:
            return LAYER_1_NAME, f"ACTIVE (Day {days}/10 Base Hold)"
        else:  # days >= 10
            if current_gain_pct > 0.0 and max_mae_pct > stop_loss_pct:
                return LAYER_2_NAME, "BREAKOUT_CONFIRMED (⭐ Buy Zone Active)"
            else:
                # User rule: If not growing, it STAYS in Layer 1!
                return LAYER_1_NAME, "L1_STAGNANT (⏳ Waiting for Growth)"

    # 3. Layer 2 Evaluation
    if current_layer == LAYER_2_NAME or (days <= 20 and current_gain_pct > 0.0):
        if days < 20:
            return LAYER_2_NAME, f"BUY_ZONE_ACCUMULATING (Day {days}/20)"
        else:  # days >= 20
            if current_gain_pct >= 5.0 and max_mae_pct > stop_loss_pct:
                return LAYER_3_NAME, "TREND_ACCELERATING (🚀 Momentum Active)"
            elif current_gain_pct > 0.0:
                return LAYER_2_NAME, "L2_CONSOLIDATING (Base Holding)"
            else:
                return LAYER_1_NAME, "L1_STAGNANT (⏳ Pullback to Base)"

    # 4. Layer 3 Evaluation
    if current_layer == LAYER_3_NAME or (days <= 30 and current_gain_pct >= 5.0):
        if days < 30:
            return LAYER_3_NAME, f"TREND_ACCELERATING (Day {days}/30)"
        else:  # days >= 30
            if current_gain_pct >= 15.0 or peak_mfe_pct >= 25.0:
                return LAYER_4_NAME, "RALLY_EXPANDING (🔥 Multibagger Zone)"
            else:
                return LAYER_3_NAME, "L3_MOMENTUM_REST"

    # 5. Layer 4 Evaluation
    if peak_mfe_pct >= 50.0:
        return LAYER_4_NAME, "TARGET_ACHIEVED (🚀 +50%+ Multibagger)"
    elif peak_mfe_pct >= 25.0:
        return LAYER_4_NAME, "RALLY_LEADER (🔥 +25%+ Runner)"
    else:
        return LAYER_4_NAME, "L4_EXPANSION_ACTIVE"


@dataclass
class StagedStockRecord:
    symbol: str
    date_added: str  # YYYY-MM-DD
    entry_price: float
    current_price: float
    market_cap_tier: str  # "Tier 1: Large Cap", "Tier 2: Mid Cap", "Tier 3: Small / Micro Cap"
    sector: str
    series: str
    days_in_pipeline: int
    current_layer: str
    current_gain_pct: float
    peak_mfe_pct: float
    max_mae_pct: float
    status: str  # "ACTIVE", "BREAKOUT_CONFIRMED", "STOP_LOSS_DROPPED", etc.
    stop_loss_pct: float = -8.0
    has_catalyst: bool = False
    order_value_cr: float | None = None
    catalyst_headline: str = ""
    selection_reason: str = ""
    initial_radar_score: float = 65.0


def load_staged_pipeline(path: Path | str = DEFAULT_PIPELINE_PATH) -> list[StagedStockRecord]:
    """Load tracked pipeline entries from persistent JSON storage."""
    p = Path(path)
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        records: list[StagedStockRecord] = []
        for d in data:
            records.append(StagedStockRecord(**d))
        return records
    except Exception as e:
        logger.warning(f"Failed to parse staged pipeline from {p}: {e}")
        return []


def save_staged_pipeline(records: Sequence[StagedStockRecord], path: Path | str = DEFAULT_PIPELINE_PATH) -> None:
    """Save tracked pipeline entries to persistent JSON storage."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    try:
        data = [asdict(r) for r in records]
        p.write_text(json.dumps(data, indent=2), encoding="utf-8")
        logger.info(f"Persisted {len(records)} staged pipeline records to {p}")
    except Exception as e:
        logger.error(f"Failed to persist staged pipeline: {e}")


def initialize_pipeline_from_today_candidates(
    candidates_df: pd.DataFrame,
    path: Path | str = DEFAULT_PIPELINE_PATH,
    force_reset: bool = False,
    min_score_threshold: float = 35.0,
) -> pd.DataFrame:
    """Initialize the pipeline with TODAY's freshly scanned radar candidates into Layer 1 (Day 0).
    
    - Layer 1: Contains all today's candidates at Day 0 (Current Gain = 0.0%).
    - Layer 2, Layer 3, Layer 4: Start at 0 stocks! (Empty until stocks grow over 10, 20, 30 days).
    - No dummy historical stocks.
    """
    p = Path(path)
    if not force_reset and p.exists() and p.stat().st_size > 10:
        existing = load_staged_pipeline(path=p)
        # Check if existing pipeline contains old mock seed data (AKCAPIT with 3 days, etc.)
        is_mock_seed = any(r.symbol in ("AKCAPIT", "AVANTEL") and r.days_in_pipeline in (3, 6) for r in existing)
        if existing and not is_mock_seed:
            return pd.DataFrame([asdict(r) for r in existing])

    if candidates_df.empty:
        save_staged_pipeline([], path=path)
        return pd.DataFrame()

    today_str = datetime.now().strftime("%Y-%m-%d")
    records: list[StagedStockRecord] = []
    seen: set[str] = set()

    for _, row in candidates_df.iterrows():
        sym = str(row["symbol"]).upper().replace(".NS", "").replace(".BO", "").strip()
        score = float(row.get("radar_score") or 0.0)
        if score < min_score_threshold or sym in seen:
            continue
        seen.add(sym)

        close = float(row["close"])
        dt_val = row.get("date")
        if pd.notna(dt_val) and str(dt_val) != "NaT":
            dt_str = pd.to_datetime(dt_val).strftime("%Y-%m-%d")
        else:
            dt_str = today_str

        tier = str(row.get("market_cap_tier", "Tier 3: Small / Micro Cap"))
        sec = str(row.get("sector", "Diversified / General"))
        ser = str(row.get("series", "EQ")).upper()
        reason = str(row.get("selection_reason", row.get("primary_driver", "Consolidation Base Compression")))
        has_cat = bool(row.get("has_catalyst", False))
        order_val = float(row["order_value_cr"]) if pd.notna(row.get("order_value_cr")) and row.get("order_value_cr") else None
        cat_desc = str(row.get("catalyst_summary", ""))

        rec = StagedStockRecord(
            symbol=sym,
            date_added=dt_str,
            entry_price=np.round(close, 2),
            current_price=np.round(close, 2),
            market_cap_tier=tier,
            sector=sec,
            series=ser,
            days_in_pipeline=0,
            current_layer=LAYER_1_NAME,
            current_gain_pct=0.0,
            peak_mfe_pct=0.0,
            max_mae_pct=0.0,
            status="ACTIVE (Day 0 Ignition)",
            stop_loss_pct=-8.0,
            has_catalyst=has_cat,
            order_value_cr=order_val,
            catalyst_headline=cat_desc,
            selection_reason=reason,
            initial_radar_score=score,
        )
        records.append(rec)

    save_staged_pipeline(records, path=path)
    logger.info(f"Initialized clean 4-layer pipeline with {len(records)} stocks in Layer 1 (Day 0). Layer 2/3/4 = 0 stocks.")
    return pd.DataFrame([asdict(r) for r in records])


# Alias for backward compatibility
seed_sample_pipeline_if_empty = initialize_pipeline_from_today_candidates


def add_candidates_to_pipeline(
    candidates_df: pd.DataFrame,
    path: Path | str = DEFAULT_PIPELINE_PATH,
    max_score_threshold: float = 35.0,
    max_stocks_per_sector: int = 5,
    max_portfolio_slots: int = 20,
) -> int:
    """Ingest newly flagged radar candidates into Layer 1 (Day 0).
    
    Enforces the Golden Sweet Spot Guardrail:
    - 5% Allocation per slot -> Maximum 20 portfolio positions.
    - Max 25% Portfolio Exposure per Sector -> Maximum 5 stocks per Sector Cluster.
    - Existing symbols already being tracked will not be duplicated.
    """
    if candidates_df.empty:
        return 0

    existing = load_staged_pipeline(path=path)
    existing_symbols = {r.symbol.upper(): r for r in existing}

    # Count active holdings per sector (excluding dropped/stop-loss)
    active_sector_counts: dict[str, int] = {}
    active_count = 0
    for r in existing:
        if not any(k in r.status.upper() for k in ("STOP_LOSS", "DROPPED", "EXIT")):
            active_count += 1
            sec = r.sector or "Diversified / General"
            active_sector_counts[sec] = active_sector_counts.get(sec, 0) + 1

    available_slots = max(0, max_portfolio_slots - active_count)
    if available_slots <= 0:
        logger.info(f"Pipeline portfolio slots full ({active_count}/{max_portfolio_slots}). No new candidates added.")
        return 0

    added_count = 0
    today_str = datetime.now().strftime("%Y-%m-%d")

    for _, row in candidates_df.iterrows():
        if added_count >= available_slots:
            break

        sym = str(row["symbol"]).upper().replace(".NS", "").replace(".BO", "").strip()
        score = float(row.get("radar_score") or 0.0)
        if score < max_score_threshold:
            continue

        if sym in existing_symbols:
            continue

        sec = str(row.get("sector", "Diversified / General"))
        current_sec_count = active_sector_counts.get(sec, 0)

        # Enforce max 5 stocks per sector (25% exposure cap)
        if current_sec_count >= max_stocks_per_sector:
            logger.info(f"Skipping {sym}: Sector '{sec}' already has {current_sec_count}/{max_stocks_per_sector} active positions.")
            continue

        close = float(row["close"])
        dt_val = row.get("date")
        dt_str = pd.to_datetime(dt_val).strftime("%Y-%m-%d") if pd.notna(dt_val) and str(dt_val) != "NaT" else today_str
        tier = str(row.get("market_cap_tier", "Tier 3: Small / Micro Cap"))
        ser = str(row.get("series", "EQ")).upper()
        reason = str(row.get("selection_reason", row.get("primary_driver", "Consolidation Base Compression")))
        has_cat = bool(row.get("has_catalyst", False))
        order_val = float(row["order_value_cr"]) if pd.notna(row.get("order_value_cr")) and row.get("order_value_cr") else None
        cat_desc = str(row.get("catalyst_summary", ""))

        record = StagedStockRecord(
            symbol=sym,
            date_added=dt_str,
            entry_price=np.round(close, 2),
            current_price=np.round(close, 2),
            market_cap_tier=tier,
            sector=sec,
            series=ser,
            days_in_pipeline=0,
            current_layer=LAYER_1_NAME,
            current_gain_pct=0.0,
            peak_mfe_pct=0.0,
            max_mae_pct=0.0,
            status="ACTIVE (Day 0 Ignition)",
            stop_loss_pct=-8.0,
            has_catalyst=has_cat,
            order_value_cr=order_val,
            catalyst_headline=cat_desc,
            selection_reason=reason,
            initial_radar_score=score,
        )
        existing.append(record)
        existing_symbols[sym] = record
        active_sector_counts[sec] = current_sec_count + 1
        added_count += 1

    if added_count > 0:
        save_staged_pipeline(existing, path=path)
        logger.info(f"Added {added_count} new candidates into Layer 1 pipeline (5% Sizing + 25% Sector Cluster Guardrail applied).")

    return added_count


def update_pipeline_with_bars(
    bars_df: pd.DataFrame,
    path: Path | str = DEFAULT_PIPELINE_PATH,
) -> pd.DataFrame:
    """Advance all incubating stocks session-by-session and evaluate growth-based layer transitions.
    
    - Checks high/low excursion relative to initial discovery entry price.
    - Evaluates price growth: Stocks MUST show positive gain to graduate from Layer 1 to Layer 2.
    - If a stock is stagnant (gain <= 0%), it remains in Layer 1.
    - Triggers 'STOP_LOSS_DROPPED' if stock breaches -8% from base.
    - Transitions to Layer 3 (days >= 20, gain >= 5%) and Layer 4 (days >= 30, gain >= 15% / MFE >= 25%).
    """
    records = load_staged_pipeline(path=path)
    if not records or bars_df.empty:
        return pd.DataFrame([asdict(r) for r in records]) if records else pd.DataFrame()

    bars_by_symbol: dict[str, pd.DataFrame] = {}
    for sym, grp in bars_df.groupby("symbol"):
        clean = str(sym).upper().replace(".NS", "").replace(".BO", "").strip()
        bars_by_symbol[clean] = grp.sort_values("date").reset_index(drop=True)

    updated_records: list[StagedStockRecord] = []
    for r in records:
        sym = r.symbol
        if sym not in bars_by_symbol:
            updated_records.append(r)
            continue

        sym_bars = bars_by_symbol[sym]
        entry_dt = pd.to_datetime(r.date_added)
        sym_dates = pd.to_datetime(sym_bars["date"])
        if sym_dates.dt.tz is not None:
            sym_dates = sym_dates.dt.tz_localize(None)
        if entry_dt.tz is not None:
            entry_dt = entry_dt.tz_localize(None)
        # Slices candles on or after entry date
        post_entry = sym_bars[sym_dates >= entry_dt].reset_index(drop=True)

        if post_entry.empty:
            # Entry date may be today or after latest cached bar
            latest_close = float(sym_bars["close"].iloc[-1])
            base_price = r.entry_price if r.entry_price > 0 else latest_close
            current_gain = (latest_close / base_price - 1.0) * 100.0
            r.current_price = np.round(latest_close, 2)
            r.current_gain_pct = np.round(current_gain, 2)
            updated_records.append(r)
            continue

        n_sessions = len(post_entry) - 1  # 0 on discovery day
        latest_close = float(post_entry["close"].iloc[-1])
        base_price = r.entry_price if r.entry_price > 0 else float(post_entry["close"].iloc[0])

        # Excursion calculations
        high_water = float(post_entry["high"].max())
        low_water = float(post_entry["low"].min())

        current_gain = (latest_close / base_price - 1.0) * 100.0
        peak_mfe = max((high_water / base_price - 1.0) * 100.0, r.peak_mfe_pct)
        worst_mae = min((low_water / base_price - 1.0) * 100.0, r.max_mae_pct)

        # Growth-based layer and status assignment (Terminal status preservation)
        if any(k in r.status.upper() for k in ('STOP_LOSS', 'DROPPED')):
            current_layer = r.current_layer
            status = r.status
        else:
            current_layer, status = classify_layer_by_growth(
            days=n_sessions,
            current_gain_pct=current_gain,
            max_mae_pct=worst_mae,
            current_layer=r.current_layer,
            stop_loss_pct=r.stop_loss_pct,
            peak_mfe_pct=peak_mfe,
        )

        updated = StagedStockRecord(
            symbol=r.symbol,
            date_added=r.date_added,
            entry_price=np.round(base_price, 2),
            current_price=np.round(latest_close, 2),
            market_cap_tier=r.market_cap_tier,
            sector=r.sector,
            series=r.series,
            days_in_pipeline=n_sessions,
            current_layer=current_layer,
            current_gain_pct=np.round(current_gain, 2),
            peak_mfe_pct=np.round(peak_mfe, 2),
            max_mae_pct=np.round(worst_mae, 2),
            status=status,
            stop_loss_pct=r.stop_loss_pct,
            has_catalyst=r.has_catalyst,
            order_value_cr=r.order_value_cr,
            catalyst_headline=r.catalyst_headline,
            selection_reason=r.selection_reason,
            initial_radar_score=r.initial_radar_score,
        )
        updated_records.append(updated)

    save_staged_pipeline(updated_records, path=path)
    return pd.DataFrame([asdict(r) for r in updated_records])
