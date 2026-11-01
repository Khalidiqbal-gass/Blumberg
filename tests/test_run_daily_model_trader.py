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
