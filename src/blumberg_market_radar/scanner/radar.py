"""Early Rally Scanner: Pre-rally range compression, volume footprint, and explainable scoring."""
from __future__ import annotations

import numpy as np
import pandas as pd

from blumberg_market_radar.data.ingestion import (
    get_symbol_sector_map,
    NIFTY_100_LARGECAPS,
    NIFTY_MIDCAP_150,
)
from blumberg_market_radar.data.security_master import get_security_master_dict
from blumberg_market_radar.data.validation import validate_ohlcv


def compute_pre_rally_features(
    bars: pd.DataFrame,
    benchmark_bars: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Calculate multi-horizon returns, range compression, volume footprints, and relative strength.

    Strict point-in-time design:
    - Today's volume does NOT leak into its historical 20-day or 50-day baseline (uses shift(1)).
    - Range compression uses prior high/low windows to detect consolidation bases before breakouts.
    - Prices are normalized so a ₹10 stock and a ₹2,000 stock are evaluated fairly.
    - Populates sector metadata and computes sector peer relative strength.
    """
    clean = validate_ohlcv(bars)
    if clean.empty:
        return clean

    sector_map = get_symbol_sector_map(include_nifty500=False)

    # Benchmark return mappings (Nifty 50) with normalized date alignment
    bench_ret_20d: dict[pd.Timestamp, float] = {}
    bench_ret_60d: dict[pd.Timestamp, float] = {}
    if benchmark_bars is not None and not benchmark_bars.empty:
        b_clean = validate_ohlcv(benchmark_bars).sort_values("date")
        b_clean["b_ret_20d"] = b_clean["close"].pct_change(20, fill_method=None)
        b_clean["b_ret_60d"] = b_clean["close"].pct_change(60, fill_method=None)
        b_norm = b_clean["date"].dt.normalize()
        bench_ret_20d = dict(zip(b_norm, b_clean["b_ret_20d"]))
        bench_ret_60d = dict(zip(b_norm, b_clean["b_ret_60d"]))

    parts: list[pd.DataFrame] = []
    for symbol, group in clean.groupby("symbol", sort=False):
        df = group.sort_values("date").copy()
        clean_sym = str(symbol).replace(".NS", "").replace(".BO", "").strip().upper()
        sec = sector_map.get(clean_sym, sector_map.get(str(symbol), "Diversified / General"))
        df["sector"] = sec

        c = df["close"]
        h = df["high"]
        l = df["low"]
        v = df["volume"]

        # 1. Multi-Session Returns (1d, 5d, 10d, 20d, 60d)
        df["return_1d"] = c.pct_change(1, fill_method=None)
        df["return_5d"] = c.pct_change(5, fill_method=None)
        df["return_10d"] = c.pct_change(10, fill_method=None)
        df["return_20d"] = c.pct_change(20, fill_method=None)
        df["return_60d"] = c.pct_change(60, fill_method=None)

        # 2. Benchmark Relative Strength (RS vs Nifty 50 with normalized dates)
        norm_date = df["date"].dt.normalize()
        if bench_ret_20d:
            b20 = norm_date.map(bench_ret_20d).fillna(0.0)
            df["rs_20d"] = df["return_20d"] - b20
        else:
            df["rs_20d"] = df["return_20d"]

        if bench_ret_60d:
            b60 = norm_date.map(bench_ret_60d).fillna(0.0)
            df["rs_60d"] = df["return_60d"] - b60
        else:
            df["rs_60d"] = df["return_60d"]

        # Circuit Lockout Flag (Upper circuit: high == low, close >= open, return_1d >= 4.5%)
        df["is_upper_circuit"] = (h == l) & (c >= df["open"]) & (df["return_1d"] >= 0.045)

        # 3. Volume Footprint (Dry-Up then Quiet Accumulation)
        # Shift(1) ensures today's volume never leaks into baseline calculation
        prior_vol_20 = v.shift(1).rolling(20, min_periods=5).mean()
        prior_vol_50 = v.shift(1).rolling(50, min_periods=10).mean()

        df["relative_volume_20d"] = v / prior_vol_20.replace(0, np.nan)
        # Volume dry-up: Did volume contract significantly prior to today? (< 0.7x 50-day average)
        recent_3d_vol_mean = v.shift(1).rolling(3, min_periods=2).mean()
        df["volume_dry_up_ratio"] = recent_3d_vol_mean / prior_vol_50.replace(0, np.nan)

        # 4. Range Compression (Volatility Contraction Pattern - VCP)
        # Ratio of recent 20-day range to 60-day range. Lower ratio = tighter base formation
        roll_20_high = h.shift(1).rolling(20, min_periods=5).max()
        roll_20_low = l.shift(1).rolling(20, min_periods=5).min()
        roll_60_high = h.shift(1).rolling(60, min_periods=15).max()
        roll_60_low = l.shift(1).rolling(60, min_periods=15).min()

        range_20d = (roll_20_high - roll_20_low) / c.shift(1)
        range_60d = (roll_60_high - roll_60_low) / c.shift(1)
        # Compression ratio: values < 0.60 indicate strong consolidation base
        df["range_compression_ratio"] = (range_20d / range_60d.replace(0, np.nan)).clip(0.1, 1.5)

        # 5. Distance to 52-Week High (250 sessions)
        # 5. Distance to 52-Week High (250 sessions - shifted by 1 to prevent lookahead)
        roll_250_high = h.shift(1).rolling(250, min_periods=20).max()
        df["high_52w"] = roll_250_high
        df["dist_to_52w_high_pct"] = (c / roll_250_high - 1.0) * 100.0

        # Fresh 20-day consolidation breakout flag
        df["is_breakout_20d"] = c > roll_20_high

        # 6. Daily Traded Value / Liquidity (Turnover in ₹ Crores)
        df["turnover_cr"] = (c * v) / 10_000_000.0
        df["avg_turnover_20d_cr"] = df["turnover_cr"].rolling(20, min_periods=5).mean()

        # 7. Volatility (ATR%)
        tr = np.maximum(
            h - l,
            np.maximum(
                np.abs(h - c.shift(1)),
                np.abs(l - c.shift(1)),
            ),
        )
        atr_14 = tr.rolling(14, min_periods=5).mean()
        df["atr_pct"] = (atr_14 / c) * 100.0
        df["volatility_20d"] = c.pct_change(fill_method=None).rolling(20, min_periods=5).std()

        parts.append(df)

    result = pd.concat(parts, ignore_index=True)

    # 8. Sector Relative Strength (RS vs Sector Peer Group)
    if "sector" in result.columns and len(result) > 0:
        sector_group_mean = result.groupby(["date", "sector"])["return_20d"].transform("mean")
        result["sector_return_20d"] = sector_group_mean
        result["sector_rs_20d"] = result["return_20d"] - sector_group_mean
    else:
        result["sector_return_20d"] = 0.0
        result["sector_rs_20d"] = 0.0

    return result.sort_values(["symbol", "date"], kind="stable").reset_index(drop=True)


def score_pre_rally_candidates(
    features_df: pd.DataFrame,
    events_df: pd.DataFrame | None = None,
    min_turnover_cr: float = 1.0,
) -> pd.DataFrame:
    """Compute an explainable Pre-Rally Radar Score (0-100) identifying stocks before large moves.

    Score Components:
    - 35% Range Compression & Base Formation (Volatility Contraction Pattern)
    - 30% Volume Footprint (Dry-Up followed by Quiet Accumulation)
    - 25% Relative Strength vs Benchmark (Higher lows while Nifty is flat/down)
    - 10% Disclosed Corporate Catalyst (Verified order win / Capex)

    Populates:
    - Sector metadata and Sector Relative Strength
    - Price Tier classification (₹<50, ₹50-₹500, ₹500-₹2,000, ₹2,000+)
    """
    if features_df.empty:
        return features_df

    sector_map = get_symbol_sector_map(include_nifty500=False)
    sec_master = get_security_master_dict()
    latest_rows = features_df.sort_values("date").groupby("symbol", as_index=False).last()
    scored_records: list[dict] = []

    for _, row in latest_rows.iterrows():
        sym = str(row["symbol"]).strip().upper()
        clean_sym = sym.replace(".NS", "").replace(".BO", "")
        sector = str(row.get("sector") or sector_map.get(clean_sym, sector_map.get(sym, "Diversified / General")))

        # Security Master Metadata
        meta = sec_master.get(clean_sym, sec_master.get(sym, {}))
        series = str(meta.get("series", "EQ")).upper()
        is_recent_ipo = bool(meta.get("is_recent_ipo", False))
        ipo_category = str(meta.get("ipo_category", "Established (>1Y)"))
        listing_date = meta.get("listing_date")
        listing_age_days = meta.get("listing_age_days")

        close = float(row["close"])
        high = float(row.get("high", close))
        low = float(row.get("low", close))
        open_p = float(row.get("open", close))
        ret_1d = float(row.get("return_1d")) if pd.notna(row.get("return_1d")) else 0.0
        ret_5d = float(row.get("return_5d")) if pd.notna(row.get("return_5d")) else 0.0
        ret_20d = float(row.get("return_20d")) if pd.notna(row.get("return_20d")) else 0.0
        rs_20d = float(row.get("rs_20d")) if pd.notna(row.get("rs_20d")) else 0.0
        sector_rs_20d = float(row.get("sector_rs_20d")) if pd.notna(row.get("sector_rs_20d")) else 0.0
        rvol = float(row.get("relative_volume_20d")) if pd.notna(row.get("relative_volume_20d")) else 1.0
        dry_up = float(row.get("volume_dry_up_ratio")) if pd.notna(row.get("volume_dry_up_ratio")) else 1.0
        compression = float(row.get("range_compression_ratio")) if pd.notna(row.get("range_compression_ratio")) else 0.8
        dist_52w = float(row.get("dist_to_52w_high_pct")) if pd.notna(row.get("dist_to_52w_high_pct")) else -20.0
        is_breakout = bool(row.get("is_breakout_20d") or False)
        atr_pct = float(row.get("atr_pct")) if pd.notna(row.get("atr_pct")) else 2.5
        turnover_cr = float(row.get("avg_turnover_20d_cr")) if pd.notna(row.get("avg_turnover_20d_cr")) else 5.0

        # Upper Circuit Detection: locked candle where high == low, close >= open, and 1D gain >= 4.5%
        is_circuit_locked = bool(row.get("is_upper_circuit", False))
        if not is_circuit_locked and high == low and close >= open_p and ret_1d >= 0.045:
            is_circuit_locked = True

        # 1. Base & Range Compression Score (35%)
        comp_score = np.clip((1.0 - compression) * 160.0, 10.0, 100.0)

        # 2. Volume Footprint Score (30%)
        vol_score = 0.0
        if rvol >= 1.4:
            vol_score += np.clip((rvol - 1.0) * 35.0, 0, 70.0)
        if dry_up < 0.85:
            vol_score += 30.0  # Bonus for volume dry-up before expansion
        vol_score = np.clip(vol_score, 0.0, 100.0)

        # 3. Relative Strength vs Benchmark Score (25%)
        rs_score = np.clip((rs_20d + 0.02) * 500.0, 0.0, 100.0)

        # 4. Corporate Event Catalyst Score (10% - Point-in-Time Verified)
        has_catalyst = False
        catalyst_desc = ""
        catalyst_order_val = None
        if events_df is not None and not events_df.empty:
            sym_events = events_df[(events_df["symbol"] == clean_sym) | (events_df["symbol"] == sym)]
            if not sym_events.empty:
                # Point-in-time check: event date must precede or match candle date
                curr_date = pd.to_datetime(row["date"])
                ev_dates = pd.to_datetime(sym_events["date"])
                if curr_date.tz is not None and ev_dates.dt.tz is None:
                    ev_dates = ev_dates.dt.tz_localize("UTC")
                elif curr_date.tz is None and ev_dates.dt.tz is not None:
                    ev_dates = ev_dates.dt.tz_localize(None)

                # Active within last 120 days before or on candle date
                valid_events = sym_events[(ev_dates <= curr_date) & ((curr_date - ev_dates).dt.days <= 120)]
                if not valid_events.empty:
                    ev = valid_events.iloc[0]
                    has_catalyst = True
                    catalyst_desc = str(ev.get("headline", ""))
                    catalyst_order_val = ev.get("order_value_cr")

        cat_score = 100.0 if has_catalyst else 20.0

        # Weighted Composite Pre-Rally Score (0 to 100)
        composite = (
            (comp_score * 0.35)
            + (vol_score * 0.30)
            + (rs_score * 0.25)
            + (cat_score * 0.10)
        )

        # Liquidity penalty if below turnover floor
        if turnover_cr < min_turnover_cr:
            composite *= 0.50

        # Reasons for Pre-Rally Identification
        reasons: list[str] = []

        # Detect IPO Base Consolidation setup
        is_ipo_base = is_recent_ipo and (compression < 0.70)
        if is_ipo_base:
            reasons.append("Recent IPO Listing")
            reasons.append("Post-Listing Volatility Squeeze")
        elif is_recent_ipo:
            reasons.append(f"Recent IPO Listing ({ipo_category})")

        if compression < 0.60:
            reasons.append(f"Tight Range Base (Compression {compression:.2f})")
        if rvol >= 2.0:
            reasons.append(f"Accumulation Footprint ({rvol:.1f}x Volume)")
        elif rvol >= 1.4:
            reasons.append(f"Quiet Volume Buildup ({rvol:.1f}x)")
        if dry_up < 0.80:
            reasons.append("Prior Volume Dry-Up (Seller Exhaustion)")
        if rs_20d > 0.04:
            reasons.append(f"Decoupled from Nifty (+{rs_20d * 100:.1f}%)")
        if sector_rs_20d > 0.03:
            reasons.append(f"Leading {sector} Sector (+{sector_rs_20d * 100:.1f}%)")
        if is_breakout:
            reasons.append("Initial Range Breakout Trigger")
        if has_catalyst:
            if catalyst_order_val is not None and not pd.isna(catalyst_order_val):
                reasons.append(f"Confirmed Order Win: ₹{catalyst_order_val:,.0f} Cr")
            else:
                reasons.append("Verified Corporate Catalyst")

        if not reasons:
            reasons.append("Multi-Month Baseline Base")

        primary_driver = "🌟 Fresh IPO Base Accumulation" if is_ipo_base else (reasons[0] if reasons else "Consolidation")

        # Risk Flags
        risks: list[str] = []
        if is_circuit_locked:
            risks.append("⚠️ Upper Circuit Locked (Zero Sellers - Illiquid Entry Risk)")
        if series == "BE":
            risks.append("⚠️ Trade-to-Trade (T2T Series - Intraday Blocked, 100% Delivery)")
        elif series == "BZ":
            risks.append("⚠️ Surveillance BZ Series (Default / Non-Compliant Risk)")
        if atr_pct > 4.5:
            risks.append(f"High Volatility Band (ATR {atr_pct:.1f}%)")
        if turnover_cr < 2.0:
            risks.append(f"Thin Liquidity (₹{turnover_cr:.1f} Cr/day)")
        if dist_52w < -30.0:
            risks.append("Deep Overhead Supply (>30% below 52W High)")
        if not risks:
            risks.append("Normal Pre-Rally Risk Profile")

        # Determine Market Cap Tier (Tier 1: Large Cap, Tier 2: Mid Cap, Tier 3: Small / Micro Cap)
        if clean_sym in NIFTY_100_LARGECAPS:
            cap_tier = "Tier 1: Large Cap"
        elif clean_sym in NIFTY_MIDCAP_150:
            cap_tier = "Tier 2: Mid Cap"
        elif turnover_cr >= 35.0 and series == "EQ":
            cap_tier = "Tier 1: Large Cap"
        elif turnover_cr >= 5.0 and series == "EQ":
            cap_tier = "Tier 2: Mid Cap"
        else:
            cap_tier = "Tier 3: Small / Micro Cap"

        # Determine Price Category for flexible filtering
        if close < 50:
            price_tier = "Small Cap / Micro (₹<50)"
        elif close < 500:
            price_tier = "Mid Tier (₹50 - ₹500)"
        elif close < 2000:
            price_tier = "Large Tier (₹500 - ₹2,000)"
        else:
            price_tier = "Premium Tier (₹2,000+)"

        # Construct explicit, human-readable selection reason
        reason_parts = []
        if has_catalyst and catalyst_order_val:
            reason_parts.append(f"Confirmed Order: ₹{catalyst_order_val:,.0f} Cr")
        elif has_catalyst:
            reason_parts.append("Verified Corporate Catalyst")
        if is_ipo_base:
            reason_parts.append("Fresh IPO Base Compression")
        elif compression < 0.60:
            reason_parts.append(f"Base Squeeze (Comp {compression:.2f})")
        if rvol >= 2.0:
            reason_parts.append(f"Accumulation Footprint ({rvol:.1f}x Vol)")
        elif rvol >= 1.4:
            reason_parts.append(f"Quiet Volume Buildup ({rvol:.1f}x)")
        if rs_20d > 0.03:
            reason_parts.append(f"Outperforming Nifty (+{rs_20d*100:.1f}%)")
        if not reason_parts:
            reason_parts = reasons[:2]

        selection_reason = " | ".join(reason_parts[:3]) if reason_parts else "Multi-Month Baseline Consolidation"

        scored_records.append({
            "symbol": clean_sym,
            "sector": sector,
            "series": series,
            "market_cap_tier": cap_tier,
            "date": row["date"],
            "close": np.round(close, 2),
            "price_tier": price_tier,
            "radar_score": np.round(composite, 1),
            "selection_reason": selection_reason,
            "compression_ratio": np.round(compression, 2),
            "relative_volume": np.round(rvol, 2),
            "rs_20d_pct": np.round(rs_20d * 100, 2),
            "sector_rs_20d_pct": np.round(sector_rs_20d * 100, 2),
            "return_5d_pct": np.round(ret_5d * 100, 2),
            "return_20d_pct": np.round(ret_20d * 100, 2),
            "turnover_cr": np.round(turnover_cr, 2),
            "dist_52w_high_pct": np.round(dist_52w, 2),
            "is_breakout": is_breakout,
            "is_circuit_locked": is_circuit_locked,
            "has_catalyst": has_catalyst,
            "order_value_cr": catalyst_order_val,
            "catalyst_summary": catalyst_desc,
            "is_recent_ipo": is_recent_ipo,
            "ipo_category": ipo_category,
            "listing_date": listing_date,
            "listing_age_days": listing_age_days,
            "primary_driver": primary_driver,
            "reason_codes": reasons[:3],
            "risk_flags": risks,
        })

    out_df = pd.DataFrame(scored_records)
    return out_df.sort_values("radar_score", ascending=False).reset_index(drop=True)


def apply_sector_cluster_guardrail(
    ranked_candidates: pd.DataFrame,
    active_pipeline_df: pd.DataFrame | None = None,
    max_stocks_per_sector: int = 5,
    max_portfolio_slots: int = 20,
) -> tuple[pd.DataFrame, dict[str, int], int]:
    """Applies the Institutional Golden Sweet Spot Guardrail (5% Sizing + 25% Cluster Rule):
    - 5% Allocation per slot -> Maximum 20 portfolio positions.
    - Max 25% Portfolio Exposure per Sector -> Maximum 5 stocks per Sector Cluster.
    - Captures the entire cluster of winners (e.g. HAL, BEL, Mazdock, Cochin, GRSE) without missing super-runners.
    - Caps sector risk so that a sector crash cannot hit the portfolio by more than -2.0% max.
    - Prioritizes candidates by highest Composite Pre-Rally Radar Score.

    Returns:
        (approved_candidates_df, sector_counts_dict, available_slots)
    """
    if ranked_candidates.empty:
        return ranked_candidates, {}, max_portfolio_slots

    sector_counts: dict[str, int] = {}
    active_symbols: set[str] = set()

    if active_pipeline_df is not None and not active_pipeline_df.empty:
        status_col = "status" if "status" in active_pipeline_df.columns else ("current_layer" if "current_layer" in active_pipeline_df.columns else None)
        if status_col:
            active_rows = active_pipeline_df[
                ~active_pipeline_df[status_col].astype(str).str.contains("STOP_LOSS|DROPPED|EXIT", case=False, na=False)
            ]
        else:
            active_rows = active_pipeline_df

        for _, r in active_rows.iterrows():
            sec = str(r.get("sector") or "Diversified / General").strip()
            sym = str(r.get("symbol") or "").strip().upper()
            if sym:
                active_symbols.add(sym)
            sector_counts[sec] = sector_counts.get(sec, 0) + 1

    total_active = len(active_symbols)
    available_slots = max(0, max_portfolio_slots - total_active)

    approved_records: list[dict] = []
    for _, row in ranked_candidates.iterrows():
        sym = str(row.get("symbol") or "").strip().upper()
        if sym in active_symbols:
            continue  # Already active in portfolio

        sec = str(row.get("sector") or "Diversified / General").strip()
        current_count = sector_counts.get(sec, 0)

        # Enforce maximum 5 stocks per sector (25% exposure)
        if current_count < max_stocks_per_sector:
            approved_records.append(dict(row))
            sector_counts[sec] = current_count + 1
            active_symbols.add(sym)
            if len(approved_records) >= available_slots:
                break

    approved_df = pd.DataFrame(approved_records) if approved_records else pd.DataFrame()
    return approved_df, sector_counts, available_slots


# Aliases for backward compatibility
compute_comprehensive_features = compute_pre_rally_features
score_early_rally_candidates = score_pre_rally_candidates
