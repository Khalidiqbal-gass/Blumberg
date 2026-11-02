"""Parity/stale-signal tests for scripts/run_daily_model_trader.py::scan_engine_vcp_candidates."""
import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "run_daily_model_trader.py"


def _load():
    spec = importlib.util.spec_from_file_location("run_daily_model_trader", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _series(sym, dates, price):
    n = len(dates)
    close = price * (1 + np.linspace(0, 0.1, n))
    return pd.DataFrame({
        "date": dates, "symbol": sym, "open": close, "high": close * 1.01, "low": close * 0.99,
        "close": close, "volume": 1_000_000,
    })


def test_script_importable_and_sync_path_registered():
    import sys
    _load()
    assert str(SCRIPT.parent.parent) in sys.path  # `scripts.sync_today_pipeline_bars` must resolve


def test_stale_symbol_is_never_a_candidate(monkeypatch):
    mod = _load()
    dates = pd.bdate_range("2026-01-01", periods=300)
    bars = pd.concat([_series("LIVE", dates, 100.0), _series("STALE", dates[:-3], 100.0)])
    bench = pd.DataFrame({"date": dates, "close": np.linspace(100, 110, len(dates))})

    def fake_indicators(grp, bench_series):
        out = grp.copy()
        out["raw_signal"] = True
        out["rs_score"] = 1.0
        out["rvol"] = 2.0
        out["atr_14"] = 1.0
        return out

    monkeypatch.setattr(mod.UpgradedVCPBacktestEngine, "compute_indicators", staticmethod(fake_indicators))
    res = mod.scan_engine_vcp_candidates(bars, bench)
    assert list(res["symbol"]) == ["LIVE"]


def test_min_price_default_matches_backtest_no_floor(monkeypatch):
    mod = _load()
    dates = pd.bdate_range("2026-01-01", periods=300)
    bars = _series("CHEAP", dates, 10.0)
    bench = pd.DataFrame({"date": dates, "close": np.linspace(100, 110, len(dates))})

    def fake_indicators(grp, bench_series):
        out = grp.copy()
        out["raw_signal"] = True
        out["rs_score"] = 1.0
        out["rvol"] = 2.0
        out["atr_14"] = 1.0
        return out

    monkeypatch.setattr(mod.UpgradedVCPBacktestEngine, "compute_indicators", staticmethod(fake_indicators))
    assert len(mod.scan_engine_vcp_candidates(bars, bench)) == 1
    assert len(mod.scan_engine_vcp_candidates(bars, bench, min_price=50.0)) == 0


def test_candidate_scanning_propagates_is_corporate_anomaly(monkeypatch):
    mod = _load()
    dates = pd.bdate_range("2026-01-01", periods=300)
    bars = _series("ANOM", dates, 100.0)
    bench = pd.DataFrame({"date": dates, "close": np.linspace(100, 110, len(dates))})

    def fake_indicators(grp, bench_series):
        out = grp.copy()
        out["raw_signal"] = True
        out["rs_score"] = 1.0
        out["rvol"] = 2.0
        out["atr_14"] = 1.0
        out["is_corporate_anomaly"] = True
        return out

    monkeypatch.setattr(mod.UpgradedVCPBacktestEngine, "compute_indicators", staticmethod(fake_indicators))
    res = mod.scan_engine_vcp_candidates(bars, bench)
    assert len(res) == 1
    assert "is_corporate_anomaly" in res.columns
    assert bool(res.iloc[0]["is_corporate_anomaly"]) is True


def test_sync_today_rejects_missing_volume_and_fabricated_bars(tmp_path, monkeypatch):
    import scripts.sync_today_pipeline_bars as sync_mod
    cache_file = tmp_path / "mock_cache.parquet"
    existing_df = pd.DataFrame([{
        "date": pd.to_datetime("2026-10-20", utc=True),
        "open": 100.0, "high": 105.0, "low": 99.0, "close": 102.0, "volume": 10000.0,
        "symbol": "TESTSYM.NS"
    }])
    existing_df.to_parquet(cache_file)
    monkeypatch.setattr(sync_mod, "CACHE_PARQUET", cache_file)

    # Mock yfinance download with missing Volume for day 2
    dates = [pd.to_datetime("2026-10-21", utc=True)]
    mock_raw = pd.DataFrame({
        ("Close", "TESTSYM.NS"): [104.0],
        ("Open", "TESTSYM.NS"): [103.0],
        ("High", "TESTSYM.NS"): [106.0],
        ("Low", "TESTSYM.NS"): [102.0],
        ("Volume", "TESTSYM.NS"): [np.nan],
    }, index=dates)
    mock_raw.columns = pd.MultiIndex.from_tuples(mock_raw.columns)

    monkeypatch.setattr(sync_mod.yf, "download", lambda *args, **kwargs: mock_raw)
    monkeypatch.setattr(
        sync_mod,
        "update_pipeline_with_bars",
        lambda df: pd.DataFrame(columns=["symbol", "days_in_pipeline", "date_added", "entry_price", "current_price", "current_gain_pct", "peak_mfe_pct", "status"])
    )

    sync_mod.sync_today()

    res = pd.read_parquet(cache_file)
    assert len(res) == 1
    assert "ZOMATO.NS" not in set(res["symbol"])
    assert "TATAMOTORS.NS" not in set(res["symbol"])
