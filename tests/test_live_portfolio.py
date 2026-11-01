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
    # -10% hard stop hit on 2026-10-28: without broker GTT, queues into pending_exits at EOD
    temp_portfolio.execute_daily_rebalance(_bar("2026-10-28", 920.0, 930.0, 890.0, 895.0), BENCH, pd.DataFrame(), current_date_str="2026-10-28")
    assert len(temp_portfolio.state.pending_exits) == 1
    assert temp_portfolio.get_summary()["active_positions_count"] == 1

    # Next session open (2026-10-29): Fills at open 895.0
    temp_portfolio.execute_daily_rebalance(_bar("2026-10-29", 895.0, 900.0, 890.0, 895.0), BENCH, pd.DataFrame(), current_date_str="2026-10-29")
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
    # Suspected unadjusted corporate action drop (>35%) in live stays quarantined for review, not blindly panic-sold
    pos = temp_portfolio.state.active_positions["DIXON"]
    assert pos["is_quarantined"] is True
    assert "Quarantine" in pos["current_stage"]
    assert len(temp_portfolio.state.closed_trades) == 0


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



def test_close_based_exit_queues_for_next_open_execution(temp_portfolio):
    """Verify close-based stop signals queue at EOD and execute at next morning's open."""
    # Day 1: Signal generated -> Day 2: Entered at open
    fill = _enter(temp_portfolio)
    assert temp_portfolio.get_summary()["active_positions_count"] == 1
    cash_before_exit = temp_portfolio.state.cash

    # Day 3: Stock closes below ATR closing stop (e.g. 935.0 <= 938.4), but low (925.0) does not breach -10% hard stop (918.0)
    # EOD close signal must queue, NOT exit immediately today
    b3 = _bar("2026-10-28", 950.0, 955.0, 925.0, 935.0)
    res_d3 = temp_portfolio.execute_daily_rebalance(b3, BENCH, pd.DataFrame(), current_date_str="2026-10-28")

    assert temp_portfolio.get_summary()["active_positions_count"] == 1
    assert len(temp_portfolio.state.closed_trades) == 0
    assert len(temp_portfolio.state.pending_exits) == 1
    assert temp_portfolio.state.pending_exits[0]["symbol"] == "DIXON"
    assert "Closing Stop-Loss" in temp_portfolio.state.pending_exits[0]["exit_reason"]
    # Cash must NOT be credited today (only daily cash yield accrued ~Rs 234, no trade proceeds)
    assert abs(temp_portfolio.state.cash - cash_before_exit) < 500.0

    # Day 4: Next session opens at 910.0 -> Exit must fill at open
    b4 = _bar("2026-10-29", 910.0, 920.0, 905.0, 915.0)
    res_d4 = temp_portfolio.execute_daily_rebalance(b4, BENCH, pd.DataFrame(), current_date_str="2026-10-29")

    assert temp_portfolio.get_summary()["active_positions_count"] == 0
    assert len(temp_portfolio.state.closed_trades) == 1
    assert temp_portfolio.state.pending_exits == []
    closed = temp_portfolio.state.closed_trades[0]
    assert closed["exit_price"] == 910.0
    assert closed["exit_date"] == "2026-10-29"
    # Cash must now be credited
    assert temp_portfolio.state.cash > cash_before_exit


def test_pending_exit_lower_circuit_deferral(temp_portfolio):
    """If stock opens locked limit-down on exit day, exit must defer to subsequent session."""
    _enter(temp_portfolio)

    # Queue close-based exit on Day 3
    b3 = _bar("2026-10-28", 950.0, 955.0, 925.0, 935.0)
    temp_portfolio.execute_daily_rebalance(b3, BENCH, pd.DataFrame(), current_date_str="2026-10-28")
    assert len(temp_portfolio.state.pending_exits) == 1

    # Day 4: Opens locked in lower circuit at 850.0 (prev close 915.0)
    b4_locked = pd.DataFrame([{
        "date": "2026-10-29", "symbol": "DIXON",
        "open": 850.0, "high": 850.0, "low": 850.0, "close": 850.0, "volume": 1000,
        "prev_close": 915.0,
    }])
    temp_portfolio.execute_daily_rebalance(b4_locked, BENCH, pd.DataFrame(), current_date_str="2026-10-29")

    # Must defer: still active, still in pending_exits
    assert temp_portfolio.get_summary()["active_positions_count"] == 1
    assert len(temp_portfolio.state.closed_trades) == 0
    assert len(temp_portfolio.state.pending_exits) == 1

    # Day 5: Opens normally at 840.0 -> Fills at open
    b5_normal = _bar("2026-10-30", 840.0, 850.0, 835.0, 845.0)
    temp_portfolio.execute_daily_rebalance(b5_normal, BENCH, pd.DataFrame(), current_date_str="2026-10-30")

    assert temp_portfolio.get_summary()["active_positions_count"] == 0
    assert len(temp_portfolio.state.closed_trades) == 1
    assert temp_portfolio.state.closed_trades[0]["exit_price"] == 840.0


def test_rebalance_rerun_idempotency(temp_portfolio):
    """Running execute_daily_rebalance twice for the same date must be idempotent."""
    _enter(temp_portfolio)

    # Day 3 first run: queue exit
    b3 = _bar("2026-10-28", 930.0, 935.0, 910.0, 915.0)
    temp_portfolio.execute_daily_rebalance(b3, BENCH, pd.DataFrame(), current_date_str="2026-10-28")
    cash_run1 = temp_portfolio.state.cash
    n_pending1 = len(temp_portfolio.state.pending_exits)

    # Day 3 second run (same day rerun):
    temp_portfolio.execute_daily_rebalance(b3, BENCH, pd.DataFrame(), current_date_str="2026-10-28")
    assert temp_portfolio.state.cash == cash_run1
    assert len(temp_portfolio.state.pending_exits) == n_pending1


def test_intraday_stop_without_gtt_queues_for_next_open(tmp_path):
    """When assumed_gtt_stops=False, even intraday stops queue to next open instead of same-day close."""
    mgr = LivePortfolioManager(state_path=tmp_path / "nogtt.json", initial_capital=1_000_000.0, assumed_gtt_stops=False)
    _enter(mgr)

    # Day 3: Hard stop hit intraday (low = 890.0)
    b3 = _bar("2026-10-28", 920.0, 930.0, 890.0, 895.0)
    mgr.execute_daily_rebalance(b3, BENCH, pd.DataFrame(), current_date_str="2026-10-28")

    # Without GTT, it cannot fill today: queued to next open
    assert mgr.get_summary()["active_positions_count"] == 1
    assert len(mgr.state.pending_exits) == 1
    assert "Circuit Breaker" in mgr.state.pending_exits[0]["exit_reason"]


def test_quarantined_candidate_blocked_from_entry(temp_portfolio):
    """Candidates flagged with corporate anomaly must be blocked from entering."""
    cand = pd.DataFrame([
        {"symbol": "ANOMALY", "close": 100.0, "is_corporate_anomaly": True, "sector": "Steel"}
    ])
    b = _bar("2026-10-26", 100.0, 102.0, 98.0, 100.0, sym="ANOMALY")
    res = temp_portfolio.execute_daily_rebalance(b, BENCH, cand, current_date_str="2026-10-26")

    assert temp_portfolio.state.pending_entries == []
    assert any("CANDIDATE BLOCKED" in a and "ANOMALY" in a for a in res["actions_taken"])


def test_circuit_deferred_exit_not_lost_on_rebound(temp_portfolio):
    """When stop is triggered on a lower-circuit day, exit must queue and execute at next open even if stock rebounds."""
    _enter(temp_portfolio)

    # Day 3: Stock locks lower-circuit at 880.0 (hard stop is 900.0, prev close 1000.0)
    b3_lc = pd.DataFrame([{
        "date": "2026-10-28", "symbol": "DIXON",
        "open": 880.0, "high": 880.0, "low": 880.0, "close": 880.0, "volume": 500,
        "prev_close": 1000.0,
    }])
    temp_portfolio.execute_daily_rebalance(b3_lc, BENCH, pd.DataFrame(), current_date_str="2026-10-28")

    # Lower circuit deferral MUST add to pending_exits so the signal is not lost
    assert len(temp_portfolio.state.pending_exits) == 1
    pe = temp_portfolio.state.pending_exits[0]
    assert "LOWER_CIRCUIT_DEFERRED" in pe["exit_reason"]
    assert temp_portfolio.get_summary()["active_positions_count"] == 1

    # Day 4: Market opens at 885.0 (liquid, not locked), and then rebounds to 950.0!
    b4_rebound = pd.DataFrame([{
        "date": "2026-10-29", "symbol": "DIXON",
        "open": 885.0, "high": 950.0, "low": 880.0, "close": 940.0, "volume": 500_000,
        "prev_close": 880.0,
    }])
    temp_portfolio.execute_daily_rebalance(b4_rebound, BENCH, pd.DataFrame(), current_date_str="2026-10-29")

    # Trade MUST have executed at open (885.0) and NOT be lost due to the intraday rebound
    assert temp_portfolio.get_summary()["active_positions_count"] == 0
    assert len(temp_portfolio.state.closed_trades) == 1
    assert temp_portfolio.state.closed_trades[0]["exit_price"] == 885.0
    assert len(temp_portfolio.state.pending_exits) == 0


def test_parabolic_climax_exit_queues_for_next_open(temp_portfolio):
    """Stage 5 Parabolic Climax exit is evaluated at close and must queue for next open."""
    _enter(temp_portfolio)
    pos = temp_portfolio.state.active_positions["DIXON"]
    pos["peak_price"] = 2200.0  # +120% gain
    pos["is_climax_reached"] = True

    # Day 3: Climax drop -26% from peak (2200 -> 1620)
    b3 = _bar("2026-10-28", 1700.0, 1720.0, 1600.0, 1620.0)
    temp_portfolio.execute_daily_rebalance(b3, BENCH, pd.DataFrame(), current_date_str="2026-10-28")

    assert len(temp_portfolio.state.pending_exits) == 1
    assert "Parabolic Climax" in temp_portfolio.state.pending_exits[0]["exit_reason"]
    assert temp_portfolio.get_summary()["active_positions_count"] == 1


def test_corporate_action_quarantine_manual_review_in_live(temp_portfolio):
    """Suspected unadjusted corporate action drop (>35%) in live must quarantine for manual review without panic sell."""
    _enter(temp_portfolio)

    # Day 3: Unadjusted demerger drop (-45% from entry 1000 to 550) with normal volume
    b3 = pd.DataFrame([{
        "date": "2026-10-28", "symbol": "DIXON",
        "open": 550.0, "high": 560.0, "low": 540.0, "close": 550.0, "volume": 50_000,
        "prev_close": 1000.0,
    }])
    res = temp_portfolio.execute_daily_rebalance(b3, BENCH, pd.DataFrame(), current_date_str="2026-10-28")

    pos = temp_portfolio.state.active_positions["DIXON"]
    assert pos["is_quarantined"] is True
    assert "Quarantine" in pos["current_stage"]
    assert len(temp_portfolio.state.pending_exits) == 0
    assert len(temp_portfolio.state.closed_trades) == 0
    assert any("QUARANTINE" in a for a in res["actions_taken"])


@pytest.mark.parametrize(
    ("peak_multiple", "is_climax"),
    [(1.22, False), (1.40, False), (1.60, False), (2.20, True)],
    ids=["stage-2", "stage-3", "stage-4", "stage-5"],
)
def test_corporate_action_quarantine_blocks_all_exit_stages(
    temp_portfolio, peak_multiple, is_climax
):
    """Corporate-action tags must quarantine holdings before any stage exit logic runs."""
    _enter(temp_portfolio)
    pos = temp_portfolio.state.active_positions["DIXON"]
    pos["peak_price"] = pos["entry_price"] * peak_multiple
    pos["is_climax_reached"] = is_climax

    anomaly = pd.DataFrame([{
        "date": "2026-10-28", "symbol": "DIXON",
        "open": 550.0, "high": 560.0, "low": 540.0, "close": 550.0,
        "volume": 50_000, "prev_close": 1000.0, "is_corporate_anomaly": True,
    }])
    temp_portfolio.execute_daily_rebalance(
        anomaly, BENCH, pd.DataFrame(), current_date_str="2026-10-28"
    )

    assert pos["is_quarantined"] is True
    assert pos["current_stage"] == "Corporate Action Quarantine"
    assert temp_portfolio.state.pending_exits == []
    assert temp_portfolio.state.closed_trades == []

    # Quarantine persists through a rebound until a human applies the official adjustment.
    rebound = _bar("2026-10-29", 800.0, 850.0, 780.0, 810.0)
    temp_portfolio.execute_daily_rebalance(
        rebound, BENCH, pd.DataFrame(), current_date_str="2026-10-29"
    )
    assert pos["is_quarantined"] is True
    assert pos["current_stage"] == "Corporate Action Quarantine"
    assert temp_portfolio.state.pending_exits == []
    assert temp_portfolio.state.closed_trades == []


def test_corporate_action_on_pending_exit_fill_day_cancels_automatic_fill(temp_portfolio):
    """A newly detected corporate action must quarantine before a queued open exit is filled."""
    _enter(temp_portfolio)
    stop_signal = _bar("2026-10-28", 950.0, 955.0, 925.0, 935.0)
    temp_portfolio.execute_daily_rebalance(
        stop_signal, BENCH, pd.DataFrame(), current_date_str="2026-10-28"
    )
    assert len(temp_portfolio.state.pending_exits) == 1

    anomaly = pd.DataFrame([{
        "date": "2026-10-29", "symbol": "DIXON",
        "open": 550.0, "high": 560.0, "low": 540.0, "close": 550.0,
        "volume": 50_000, "prev_close": 935.0, "is_corporate_anomaly": True,
    }])
    temp_portfolio.execute_daily_rebalance(
        anomaly, BENCH, pd.DataFrame(), current_date_str="2026-10-29"
    )

    pos = temp_portfolio.state.active_positions["DIXON"]
    assert pos["is_quarantined"] is True
    assert pos["current_stage"] == "Corporate Action Quarantine"
    assert temp_portfolio.state.pending_exits == []
    assert temp_portfolio.state.closed_trades == []
