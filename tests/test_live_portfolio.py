"""Unit tests for Live Autonomous Paper Portfolio Engine."""
import pytest
import pandas as pd
import numpy as np
from pathlib import Path
from blumberg_market_radar.pipeline.live_portfolio import LivePortfolioManager, DEFAULT_PORTFOLIO_PATH

@pytest.fixture
def temp_portfolio(tmp_path):
    state_file = tmp_path / "test_portfolio.json"
    mgr = LivePortfolioManager(state_path=state_file, initial_capital=1_000_000.0, max_slots=8)
    return mgr

def test_initial_state(temp_portfolio):
    summary = temp_portfolio.get_summary()
    assert summary["initial_capital"] == 1_000_000.0
    assert summary["cash"] == 1_000_000.0
    assert summary["active_positions_count"] == 0
    assert summary["available_slots"] == 8
    assert summary["total_equity"] == 1_000_000.0

def _bar(date, o, h, l, c, sym="DIXON", v=100000):
    return pd.DataFrame([{"date": date, "symbol": sym, "open": o, "high": h, "low": l, "close": c, "volume": v}])


# Live runner feeds ~2 years of benchmark history; EMA200 needs >= 200 bars (rising trend => regime ON)
_BENCH_DATES = pd.bdate_range(end="2026-10-26", periods=250)
BENCH = pd.DataFrame({"date": _BENCH_DATES, "close": np.linspace(20000.0, 25000.0, 250), "volume": 1000000})
CAND = pd.DataFrame([{"symbol": "DIXON", "close": 1000.0, "radar_score": 85.0,
                      "sector": "EMS / Electronics", "primary_driver": "VCP Squeeze"}])


def _enter(mgr):
    """Day 1: signal -> order queued. Day 2: filled at the OPEN. Returns fill price."""
    mgr.execute_daily_rebalance(_bar("2026-10-26", 1000.0, 1010.0, 990.0, 1000.0), BENCH, CAND, current_date_str="2026-10-26")
    assert mgr.get_summary()["active_positions_count"] == 0  # NOT filled at the signal-day close
    assert [q["symbol"] for q in mgr.state.pending_entries] == ["DIXON"]
    mgr.execute_daily_rebalance(_bar("2026-10-27", 1020.0, 1030.0, 1015.0, 1025.0), BENCH, pd.DataFrame(), current_date_str="2026-10-27")
    return 1020.0


def test_entry_is_queued_then_filled_at_next_open(temp_portfolio):
    fill = _enter(temp_portfolio)
    assert temp_portfolio.state.pending_entries == []
    pos = temp_portfolio.state.active_positions["DIXON"]
    assert pos["tranche1_price"] == fill
    assert pos["tranche2_active"] is False
    assert pos["bars_held"] == 0          # engine: not evaluated/aged on its entry day
    assert pos["peak_price"] == 1030.0    # entry-day high


def test_pending_orders_survive_state_reload(temp_portfolio, tmp_path):
    temp_portfolio.execute_daily_rebalance(_bar("2026-10-26", 1000.0, 1010.0, 990.0, 1000.0), BENCH, CAND, current_date_str="2026-10-26")
    reloaded = LivePortfolioManager(state_path=temp_portfolio.state_path, initial_capital=1_000_000.0, max_slots=8)
    assert [q["symbol"] for q in reloaded.state.pending_entries] == ["DIXON"]


def test_execution_tranche1_and_exit(temp_portfolio):
    fill = _enter(temp_portfolio)
    # -10% hard stop hit on the following session
    temp_portfolio.execute_daily_rebalance(_bar("2026-10-28", 920.0, 930.0, 890.0, 895.0), BENCH, pd.DataFrame(), current_date_str="2026-10-28")
    assert temp_portfolio.get_summary()["active_positions_count"] == 0
    assert len(temp_portfolio.state.closed_trades) == 1
    assert "Extreme Circuit Breaker" in temp_portfolio.state.closed_trades[0]["exit_reason"]


def test_lower_circuit_exit_deferral(temp_portfolio):
    _enter(temp_portfolio)
    # limit-down lock: high == low == 890 (down vs previous close) -> exit must be deferred
    temp_portfolio.execute_daily_rebalance(_bar("2026-10-28", 890.0, 890.0, 890.0, 890.0, v=10000), BENCH, pd.DataFrame(), current_date_str="2026-10-28")
    assert temp_portfolio.get_summary()["active_positions_count"] == 1
    assert "CIRCUIT_DEFER" in temp_portfolio.state.active_positions["DIXON"]["current_stage"]


def test_tranche2_fills_at_next_open_after_day_seven(temp_portfolio):
    _enter(temp_portfolio)
    px = 1025.0
    day = pd.Timestamp("2026-10-28")
    for _ in range(7):
        px *= 1.004
        temp_portfolio.execute_daily_rebalance(
            _bar(day.strftime("%Y-%m-%d"), px, px * 1.005, px * 0.998, px), BENCH, pd.DataFrame(),
            current_date_str=day.strftime("%Y-%m-%d"))
        day += pd.Timedelta(days=1)
        if temp_portfolio.state.active_positions["DIXON"].get("tranche2_eligible"):
            break
    pos = temp_portfolio.state.active_positions["DIXON"]
    assert pos["tranche2_eligible"] and not pos["tranche2_active"]   # flagged at the close, NOT yet filled
    open_next = px * 1.01
    temp_portfolio.execute_daily_rebalance(
        _bar(day.strftime("%Y-%m-%d"), open_next, open_next * 1.01, open_next * 0.995, open_next), BENCH, pd.DataFrame(),
        current_date_str=day.strftime("%Y-%m-%d"))
    pos = temp_portfolio.state.active_positions["DIXON"]
    assert pos["tranche2_active"] and pos["tranche2_price"] == open_next


def test_unresolved_corporate_action_drop_is_force_exited_after_three_sessions(temp_portfolio):
    _enter(temp_portfolio)
    for d in ("2026-10-28", "2026-10-29", "2026-10-30"):
        temp_portfolio.execute_daily_rebalance(_bar(d, 600.0, 640.0, 590.0, 610.0), BENCH, pd.DataFrame(), current_date_str=d)
    assert temp_portfolio.get_summary()["active_positions_count"] == 0
    assert "forced exit" in temp_portfolio.state.closed_trades[-1]["exit_reason"]


def test_live_fill_is_capped_by_adv(temp_portfolio):
    # ~20 prior sessions of thin volume: turnover ~ Rs 1 Cr/day -> 10% cap = ~Rs 10 L per fill (vs Rs 5 L target? raise target via capital)
    mgr = LivePortfolioManager(state_path=temp_portfolio.state_path.with_name("big.json"), initial_capital=100_000_000.0, max_slots=8)
    dates = pd.bdate_range("2026-09-01", periods=25)
    rows = [{"date": d.strftime("%Y-%m-%d"), "symbol": "DIXON", "open": 1000.0, "high": 1010.0, "low": 990.0,
             "close": 1000.0, "volume": 10_000} for d in dates]          # turnover = Rs 1 Cr/day
    bars = pd.DataFrame(rows)
    last = dates[-1].strftime("%Y-%m-%d")
    mgr.execute_daily_rebalance(bars, BENCH, CAND, current_date_str=last)
    nxt = (dates[-1] + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    bars2 = pd.concat([bars, pd.DataFrame([{"date": nxt, "symbol": "DIXON", "open": 1000.0, "high": 1010.0, "low": 990.0, "close": 1005.0, "volume": 10_000}])])
    mgr.execute_daily_rebalance(bars2, BENCH, pd.DataFrame(), current_date_str=nxt)
    pos = mgr.state.active_positions["DIXON"]
    assert pos["invested_capital"] <= 1_000_000.0 + 1.0   # 10% of Rs 1 Cr ADV, not Rs 6.25 Cr (half of a 12.5 Cr slot)


def test_stale_signal_is_not_queued(temp_portfolio):
    """A candidate whose symbol has no bar today must not be queued."""
    bars = pd.concat([
        _bar("2026-10-26", 1000.0, 1010.0, 990.0, 1000.0, sym="DIXON"),
        _bar("2026-10-23", 500.0, 510.0, 490.0, 500.0, sym="STALE"),
    ])
    cand = pd.DataFrame([{"symbol": "STALE", "close": 500.0, "sector": "X"}])
    temp_portfolio.execute_daily_rebalance(bars, BENCH, cand, current_date_str="2026-10-26")
    assert temp_portfolio.state.pending_entries == []


def test_dropped_queued_orders_are_logged(temp_portfolio):
    temp_portfolio.state.pending_entries = [
        {"symbol": "DIXON", "signal_date": "2026-10-26", "sector": "X", "selection_reason": "t"}
    ]
    temp_portfolio.state.cash = 100.0  # no cash -> order cannot fill
    res = temp_portfolio.execute_daily_rebalance(
        _bar("2026-10-27", 1020.0, 1030.0, 1015.0, 1025.0), BENCH, pd.DataFrame(), current_date_str="2026-10-27"
    )
    assert any("QUEUED ORDERS DROPPED" in a and "DIXON" in a for a in res["actions_taken"])


def test_sector_guardrail_does_not_cap_unclassified_sectors():
    from blumberg_market_radar.scanner.radar import apply_sector_cluster_guardrail
    cands = pd.DataFrame([{"symbol": f"S{i}", "sector": "Diversified"} for i in range(8)])
    approved, _, free = apply_sector_cluster_guardrail(cands, None, max_stocks_per_sector=2, max_portfolio_slots=8)
    assert free == 8 and len(approved) == 8
    classified = pd.DataFrame([{"symbol": f"S{i}", "sector": "Banks"} for i in range(8)])
    approved, _, _ = apply_sector_cluster_guardrail(classified, None, max_stocks_per_sector=2, max_portfolio_slots=8)
    assert len(approved) == 2  # real sector cap still enforced
def test_stale_bar_does_not_trigger_exit(temp_portfolio):
    """A held stock with no bar for today must not be exited on an older bar's stop-loss."""
    dates = pd.bdate_range("2026-01-01", periods=40)
    rows = []
    for dt in dates:
        rows.append(dict(symbol="AAA", date=dt, open=100.0, high=101.0, low=99.0, close=100.0, volume=1e6))
        if dt != dates[-1]:
            rows.append(dict(symbol="BBB", date=dt, open=50.0, high=50.5, low=49.5, close=50.0, volume=1e6))
    bars = pd.DataFrame(rows)
    bars.loc[(bars.symbol == "BBB") & (bars.date == dates[-2]), ["open", "low", "close"]] = [45.0, 40.0, 41.0]
    bench = pd.DataFrame({"date": dates, "close": [100.0 + i for i in range(40)]})
    temp_portfolio.state.active_positions["BBB"] = dict(
        symbol="BBB", entry_date="2026-01-01", shares=1000.0, invested_capital=50000.0,
        entry_price=50.0, entry_price_with_friction=50.0, current_price=50.0, peak_price=50.0,
        current_gain_pct=0.0, peak_gain_pct=0.0, unrealized_pnl_rs=0.0, target_slot_capital=125000.0,
        tranche1_shares=1000.0, tranche1_price=50.0, bars_held=29, sector="X",
    )
    temp_portfolio.state.cash = 950000.0
    res = temp_portfolio.execute_daily_rebalance(
        bars, bench, pd.DataFrame(), current_date_str=dates[-1].strftime("%Y-%m-%d"), enforce_regime=False
    )
    assert "BBB" in temp_portfolio.state.active_positions
    assert not any("SELL: BBB" in a for a in res["actions_taken"])
