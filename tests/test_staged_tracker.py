"""Unit tests for the 4-layer staged incubation tracker."""
from pathlib import Path
import pandas as pd
import numpy as np
import pytest

from blumberg_market_radar.pipeline.staged_tracker import (
    LAYER_1_NAME,
    LAYER_2_NAME,
    LAYER_3_NAME,
    LAYER_4_NAME,
    classify_layer_by_days,
    classify_layer_by_growth,
    load_staged_pipeline,
    save_staged_pipeline,
    add_candidates_to_pipeline,
    update_pipeline_with_bars,
    initialize_pipeline_from_today_candidates,
    StagedStockRecord,
)


def test_classify_layer_by_days():
    assert classify_layer_by_days(0) == LAYER_1_NAME
    assert classify_layer_by_days(10) == LAYER_1_NAME
    assert classify_layer_by_days(11) == LAYER_2_NAME
    assert classify_layer_by_days(20) == LAYER_2_NAME
    assert classify_layer_by_days(21) == LAYER_3_NAME
    assert classify_layer_by_days(30) == LAYER_3_NAME
    assert classify_layer_by_days(31) == LAYER_4_NAME
    assert classify_layer_by_days(60) == LAYER_4_NAME


def test_classify_layer_by_growth():
    # Day 5 in Layer 1: stays in Layer 1
    layer, status = classify_layer_by_growth(days=5, current_gain_pct=1.5, max_mae_pct=-2.0)
    assert layer == LAYER_1_NAME
    assert "Base Hold" in status

    # Day 12 with NO growth (gain <= 0%): MUST STAY IN LAYER 1!
    layer_stagnant, status_stagnant = classify_layer_by_growth(days=12, current_gain_pct=-1.5, max_mae_pct=-4.0)
    assert layer_stagnant == LAYER_1_NAME
    assert "L1_STAGNANT" in status_stagnant

    # Day 12 with POSITIVE growth (gain > 0%): GRADUATES TO LAYER 2!
    layer_grad, status_grad = classify_layer_by_growth(days=12, current_gain_pct=4.5, max_mae_pct=-2.0)
    assert layer_grad == LAYER_2_NAME
    assert "BREAKOUT_CONFIRMED" in status_grad

    # Stop Loss breach (-8%): triggers STOP_LOSS_DROPPED
    layer_stop, status_stop = classify_layer_by_growth(days=7, current_gain_pct=-9.0, max_mae_pct=-9.2)
    assert "STOP_LOSS_DROPPED" in status_stop


def test_staged_pipeline_persistence(tmp_path: Path):
    test_json = tmp_path / "test_pipeline.json"
    records = [
        StagedStockRecord(
            symbol="TATAMOTORS",
            date_added="2026-10-01",
            entry_price=250.0,
            current_price=268.0,
            market_cap_tier="Tier 1: Large Cap",
            sector="Automotive & EV",
            series="EQ",
            days_in_pipeline=15,
            current_layer=LAYER_2_NAME,
            current_gain_pct=7.2,
            peak_mfe_pct=8.5,
            max_mae_pct=-1.2,
            status="ACTIVE",
            has_catalyst=True,
            order_value_cr=1400.0,
            selection_reason="Confirmed Order ₹1,400 Cr | Base Squeeze",
            initial_radar_score=78.5,
        )
    ]
    save_staged_pipeline(records, path=test_json)
    loaded = load_staged_pipeline(path=test_json)
    assert len(loaded) == 1
    assert loaded[0].symbol == "TATAMOTORS"
    assert loaded[0].current_layer == LAYER_2_NAME
    assert loaded[0].order_value_cr == 1400.0


def test_initialize_pipeline_from_today_candidates(tmp_path: Path):
    test_json = tmp_path / "test_pipeline.json"
    candidates_df = pd.DataFrame([
        {
            "symbol": "MAZDOCK.NS",
            "date": "2026-10-22",
            "close": 1916.0,
            "radar_score": 82.0,
            "market_cap_tier": "Tier 2: Mid Cap",
            "sector": "Defence & Aerospace",
            "series": "EQ",
            "selection_reason": "Order Win ₹4,500 Cr",
            "has_catalyst": True,
            "order_value_cr": 4500.0,
        },
        {
            "symbol": "ZOMATO.NS",
            "date": "2026-10-22",
            "close": 304.8,
            "radar_score": 75.0,
            "market_cap_tier": "Tier 1: Large Cap",
            "sector": "Consumer & Retail",
            "series": "EQ",
            "selection_reason": "Accumulation Footprint",
            "has_catalyst": False,
        }
    ])

    init_df = initialize_pipeline_from_today_candidates(candidates_df, path=test_json, force_reset=True)
    assert len(init_df) == 2
    # All must start at Layer 1 Day 0
    assert (init_df["current_layer"] == LAYER_1_NAME).all()
    assert (init_df["days_in_pipeline"] == 0).all()
    assert (init_df["current_gain_pct"] == 0.0).all()


def test_add_candidates_to_pipeline(tmp_path: Path):
    test_json = tmp_path / "test_pipeline.json"
    candidates_df = pd.DataFrame([
        {
            "symbol": "MAZDOCK.NS",
            "date": "2026-10-22",
            "close": 1916.0,
            "radar_score": 82.0,
            "market_cap_tier": "Tier 2: Mid Cap",
            "sector": "Defence & Aerospace",
            "series": "EQ",
            "selection_reason": "Order Win ₹4,500 Cr",
            "has_catalyst": True,
            "order_value_cr": 4500.0,
        },
        {
            "symbol": "LOWSCORE.NS",
            "date": "2026-10-22",
            "close": 50.0,
            "radar_score": 20.0,  # Below threshold
        }
    ])

    added = add_candidates_to_pipeline(candidates_df, path=test_json, max_score_threshold=35.0)
    assert added == 1
    loaded = load_staged_pipeline(path=test_json)
    assert len(loaded) == 1
    assert loaded[0].symbol == "MAZDOCK"
    assert loaded[0].current_layer == LAYER_1_NAME
    assert loaded[0].days_in_pipeline == 0


def test_update_pipeline_with_bars_growth_progression(tmp_path: Path):
    test_json = tmp_path / "test_pipeline.json"
    # Create 2 stocks at Day 0: one will grow (+20%), one will decline/stagnate (-2%)
    rec_growing = StagedStockRecord(
        symbol="GROWSTOCK",
        date_added="2026-10-01",
        entry_price=100.0,
        current_price=100.0,
        market_cap_tier="Tier 3: Small / Micro Cap",
        sector="Capital Goods",
        series="EQ",
        days_in_pipeline=0,
        current_layer=LAYER_1_NAME,
        current_gain_pct=0.0,
        peak_mfe_pct=0.0,
        max_mae_pct=0.0,
        status="ACTIVE",
    )
    rec_stagnant = StagedStockRecord(
        symbol="STAGSTOCK",
        date_added="2026-10-01",
        entry_price=100.0,
        current_price=100.0,
        market_cap_tier="Tier 3: Small / Micro Cap",
        sector="Capital Goods",
        series="EQ",
        days_in_pipeline=0,
        current_layer=LAYER_1_NAME,
        current_gain_pct=0.0,
        peak_mfe_pct=0.0,
        max_mae_pct=0.0,
        status="ACTIVE",
    )
    save_staged_pipeline([rec_growing, rec_stagnant], path=test_json)

    # Simulate 15 days of bars
    dates = pd.date_range("2026-10-01", periods=16, freq="B", tz="UTC")
    closes_grow = [100.0 + i * 1.5 for i in range(16)]  # Rallies to 122.5
    closes_stag = [100.0 - (i * 0.2) for i in range(16)]  # Slips to 97.0 (no stop hit, but negative return)

    bars_g = pd.DataFrame({
        "symbol": "GROWSTOCK.NS",
        "date": dates,
        "open": closes_grow,
        "high": [c + 1.0 for c in closes_grow],
        "low": [c - 0.5 for c in closes_grow],
        "close": closes_grow,
        "volume": 100000,
    })
    bars_s = pd.DataFrame({
        "symbol": "STAGSTOCK.NS",
        "date": dates,
        "open": closes_stag,
        "high": [c + 0.5 for c in closes_stag],
        "low": [c - 0.5 for c in closes_stag],
        "close": closes_stag,
        "volume": 100000,
    })
    bars = pd.concat([bars_g, bars_s], ignore_index=True)

    updated_df = update_pipeline_with_bars(bars, path=test_json)
    assert len(updated_df) == 2

    # GROWSTOCK: Day 15 with positive return -> Must be in LAYER 2!
    grow_row = updated_df[updated_df["symbol"] == "GROWSTOCK"].iloc[0]
    assert grow_row["current_layer"] == LAYER_2_NAME
    assert grow_row["current_gain_pct"] > 0

    # STAGSTOCK: Day 15 with negative return -> MUST STAY IN LAYER 1 (Stagnant)!
    stag_row = updated_df[updated_df["symbol"] == "STAGSTOCK"].iloc[0]
    assert stag_row["current_layer"] == LAYER_1_NAME
    assert "L1_STAGNANT" in stag_row["status"]
