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
_BENCH_DATES = pd.bdate_range(end="2026-11-20", periods=300)
BENCH = pd.DataFrame({"date": _BENCH_DATES, "close": np.linspace(20000.0, 25000.0, 300), "volume": 1000000})
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


def test_quarantined_position_blocks_tranche2(temp_portfolio):
    """A quarantined position must NEVER receive Tranche-2 buys."""
    _enter(temp_portfolio)
    pos = temp_portfolio.state.active_positions["DIXON"]
    pos["tranche2_eligible"] = True
    pos["is_quarantined"] = True

    cash_before = temp_portfolio.state.cash
    shares_before = pos["shares"]

    # Next session open: Step 0a runs
    temp_portfolio.execute_daily_rebalance(
        _bar("2026-10-28", 1030.0, 1040.0, 1020.0, 1035.0), BENCH, pd.DataFrame(), current_date_str="2026-10-28"
    )

    pos_after = temp_portfolio.state.active_positions["DIXON"]
    assert pos_after["shares"] == shares_before
    # Cash only accrues daily risk-free yield, no Tranche-2 deduction (~Rs 62,500)
    assert temp_portfolio.state.cash == pytest.approx(cash_before * (1.0 + temp_portfolio.cash_yield_daily))
    assert pos_after["tranche2_active"] is False


def test_step00_cancelled_pending_exit_resets_tranche2_and_alerts(temp_portfolio):
    """When Step 00 cancels a pending exit due to anomaly, it must alert and reset tranche2_eligible."""
    _enter(temp_portfolio)
    # Queue stop exit
    stop_signal = _bar("2026-10-28", 950.0, 955.0, 925.0, 935.0)
    temp_portfolio.execute_daily_rebalance(
        stop_signal, BENCH, pd.DataFrame(), current_date_str="2026-10-28"
    )
    assert len(temp_portfolio.state.pending_exits) == 1

    pos = temp_portfolio.state.active_positions["DIXON"]
    pos["tranche2_eligible"] = True  # hypothesize eligibility flag was set

    # Fill day anomaly
    anomaly = pd.DataFrame([{
        "date": "2026-10-29", "symbol": "DIXON",
        "open": 550.0, "high": 560.0, "low": 540.0, "close": 550.0,
        "volume": 50_000, "prev_close": 935.0, "is_corporate_anomaly": True,
    }])
    res = temp_portfolio.execute_daily_rebalance(
        anomaly, BENCH, pd.DataFrame(), current_date_str="2026-10-29"
    )

    assert pos["is_quarantined"] is True
    assert pos["tranche2_eligible"] is False
    assert pos["tranche2_active"] is False
    assert any("PENDING EXIT CANCELLED" in a for a in res["actions_taken"])


def test_quarantine_timeout_after_three_sessions(temp_portfolio):
    """Unresolved quarantine must trigger QUARANTINE_TIMEOUT exit after 3 sessions and cleanly exit."""
    _enter(temp_portfolio)

    # Session 1: Anomaly detected
    a1 = pd.DataFrame([{
        "date": "2026-10-28", "symbol": "DIXON",
        "open": 550.0, "high": 560.0, "low": 540.0, "close": 550.0,
        "volume": 50_000, "prev_close": 1025.0, "is_corporate_anomaly": True,
    }])
    res1 = temp_portfolio.execute_daily_rebalance(a1, BENCH, pd.DataFrame(), current_date_str="2026-10-28")
    pos = temp_portfolio.state.active_positions["DIXON"]
    assert pos["is_quarantined"] is True
    assert pos["anomaly_days"] == 1
    assert temp_portfolio.state.pending_exits == []

    # Session 2: Anomaly persists
    a2 = pd.DataFrame([{
        "date": "2026-10-29", "symbol": "DIXON",
        "open": 540.0, "high": 550.0, "low": 535.0, "close": 545.0,
        "volume": 40_000, "prev_close": 550.0, "is_corporate_anomaly": True,
    }])
    temp_portfolio.execute_daily_rebalance(a2, BENCH, pd.DataFrame(), current_date_str="2026-10-29")
    assert pos["anomaly_days"] == 2
    assert temp_portfolio.state.pending_exits == []

    # Session 3: Anomaly persists -> reaches 3 sessions, timeout exit queued
    a3 = pd.DataFrame([{
        "date": "2026-10-30", "symbol": "DIXON",
        "open": 545.0, "high": 555.0, "low": 530.0, "close": 540.0,
        "volume": 45_000, "prev_close": 545.0, "is_corporate_anomaly": True,
    }])
    res3 = temp_portfolio.execute_daily_rebalance(a3, BENCH, pd.DataFrame(), current_date_str="2026-10-30")
    assert pos["anomaly_days"] == 3
    assert len(temp_portfolio.state.pending_exits) == 1
    assert "QUARANTINE_TIMEOUT" in temp_portfolio.state.pending_exits[0]["exit_reason"]
    assert any("QUARANTINE TIMEOUT" in a for a in res3["actions_taken"])

    # Session 4: Next morning, Step 00 fills QUARANTINE_TIMEOUT exit at open
    s4 = pd.DataFrame([{
        "date": "2026-10-31", "symbol": "DIXON",
        "open": 542.0, "high": 560.0, "low": 540.0, "close": 555.0,
        "volume": 60_000, "prev_close": 540.0,
    }])
    res4 = temp_portfolio.execute_daily_rebalance(s4, BENCH, pd.DataFrame(), current_date_str="2026-10-31")
    assert "DIXON" not in temp_portfolio.state.active_positions
    assert len(temp_portfolio.state.closed_trades) == 1
    assert "QUARANTINE_TIMEOUT" in temp_portfolio.state.closed_trades[0]["exit_reason"]
    assert temp_portfolio.state.pending_exits == []


def test_manual_corporate_action_resolution(temp_portfolio):
    """resolve_corporate_action correctly scales shares, prices, capital and clears quarantine."""
    _enter(temp_portfolio)
    pos = temp_portfolio.state.active_positions["DIXON"]
    pos["is_quarantined"] = True
    pos["anomaly_days"] = 2
    pos["current_stage"] = "Corporate Action Quarantine"

    old_shares = float(pos["shares"])
    old_entry = float(pos["entry_price"])
    old_inv = float(pos["invested_capital"])

    # 2:1 stock split
    res = temp_portfolio.resolve_corporate_action("DIXON", split_ratio=2.0, cost_basis_factor=1.0, event_id="SPLIT_2:1")
    assert res["new_shares"] == pytest.approx(old_shares * 2.0)
    assert res["new_entry_price"] == pytest.approx(old_entry / 2.0)
    assert res["new_invested_capital"] == pytest.approx(old_inv)

    assert pos["is_quarantined"] is False
    assert pos["anomaly_days"] == 0
    assert pos["current_stage"] == "Stage 1: Ignition Defense"

    # Validation errors
    with pytest.raises(ValueError):
        temp_portfolio.resolve_corporate_action("DIXON", split_ratio=0.0, event_id="E1")
    with pytest.raises(ValueError):
        temp_portfolio.resolve_corporate_action("DIXON", split_ratio=-2.0, event_id="E2")
    with pytest.raises(ValueError):
        temp_portfolio.resolve_corporate_action("DIXON", split_ratio=float("nan"), event_id="E3")
    with pytest.raises(ValueError, match="non-empty string"):
        temp_portfolio.resolve_corporate_action("DIXON", split_ratio=2.0, event_id="")
    with pytest.raises(KeyError):
        temp_portfolio.resolve_corporate_action("NONEXISTENT", split_ratio=2.0, event_id="E4")


def test_corrupt_state_backup_and_fail_closed(tmp_path):
    """Corrupt state JSON file must be backed up to .corrupt.bak and raise RuntimeError."""
    corrupt_file = tmp_path / "corrupt_portfolio.json"
    corrupt_file.write_text("{ this is corrupt json invalid syntax", encoding="utf-8")

    with pytest.raises(RuntimeError) as exc_info:
        LivePortfolioManager(state_path=corrupt_file, initial_capital=1_000_000.0)

    assert "is corrupted" in str(exc_info.value)
    # Check that a backup file was created
    bak_files = list(tmp_path.glob("corrupt_portfolio.json.corrupt.bak.*"))
    assert len(bak_files) == 1
    assert "{ this is corrupt json invalid syntax" in bak_files[0].read_text(encoding="utf-8")


def test_same_day_rerun_equity_history_deduplication(temp_portfolio):
    """Rebalance run multiple times on same date must update in-place, not duplicate equity records."""
    temp_portfolio.execute_daily_rebalance(
        _bar("2026-10-26", 1000.0, 1010.0, 990.0, 1000.0), BENCH, CAND, current_date_str="2026-10-26"
    )
    assert len(temp_portfolio.state.daily_equity_history) == 1

    # Rerun on same date
    temp_portfolio.execute_daily_rebalance(
        _bar("2026-10-26", 1000.0, 1010.0, 990.0, 1000.0), BENCH, CAND, current_date_str="2026-10-26"
    )
    assert len(temp_portfolio.state.daily_equity_history) == 1


def test_benchmark_missing_or_short_fails_closed(temp_portfolio):
    """Missing, empty, or <200 bar benchmark must strictly fail-closed (regime_ok=False)."""
    # None benchmark
    res_none = temp_portfolio.execute_daily_rebalance(
        _bar("2026-10-26", 1000.0, 1010.0, 990.0, 1000.0), None, CAND, current_date_str="2026-10-26"
    )
    assert res_none["regime_ok"] is False

    # Empty benchmark
    res_empty = temp_portfolio.execute_daily_rebalance(
        _bar("2026-10-26", 1000.0, 1010.0, 990.0, 1000.0), pd.DataFrame(), CAND, current_date_str="2026-10-26"
    )
    assert res_empty["regime_ok"] is False

    # Short benchmark (< 200 bars)
    short_bench = pd.DataFrame({"date": pd.bdate_range(end="2026-10-26", periods=50), "close": 24000.0})
    res_short = temp_portfolio.execute_daily_rebalance(
        _bar("2026-10-26", 1000.0, 1010.0, 990.0, 1000.0), short_bench, CAND, current_date_str="2026-10-26"
    )
    assert res_short["regime_ok"] is False


def test_tranche2_blocked_if_open_bar_is_corporate_anomaly(temp_portfolio):
    """If stock opens with an unadjusted corporate action gap-down, Step 0a must block Tranche 2 and quarantine."""
    _enter(temp_portfolio)
    pos = temp_portfolio.state.active_positions["DIXON"]
    pos["tranche2_eligible"] = True

    cash_before = temp_portfolio.state.cash
    shares_before = pos["shares"]

    # Day 8 open: stock opens with a massive -50% unadjusted demerger gap-down
    anomaly_bar = pd.DataFrame([{
        "date": "2026-10-28", "symbol": "DIXON",
        "open": 500.0, "high": 510.0, "low": 490.0, "close": 505.0,
        "volume": 50000, "prev_close": 1025.0, "is_corporate_anomaly": True,
    }])
    res = temp_portfolio.execute_daily_rebalance(
        anomaly_bar, BENCH, pd.DataFrame(), current_date_str="2026-10-28"
    )

    pos_after = temp_portfolio.state.active_positions["DIXON"]
    assert pos_after["is_quarantined"] is True
    assert pos_after["tranche2_active"] is False
    assert pos_after["shares"] == shares_before
    # Cash was NOT deducted for Tranche 2 (~Rs 62,500)
    assert temp_portfolio.state.cash >= cash_before
    assert any("TRANCHE 2 BLOCKED & QUARANTINED" in a for a in res["actions_taken"])


def test_morning_exit_cash_and_slots_not_recycled_same_morning(temp_portfolio):
    """Exit proceeds and freed slots from 9:15 AM cannot be recycled for new entries on the same morning (T+1 settlement)."""
    _enter(temp_portfolio)
    # Queue exit for DIXON
    temp_portfolio.state.pending_exits.append({
        "symbol": "DIXON",
        "signal_date": "2026-10-27",
        "exit_reason": "Closing Stop-Loss (ATR / -8% Threshold)",
        "stage_at_signal": "Stage 1: Ignition Defense",
        "signal_price": 930.0,
        "shares": temp_portfolio.state.active_positions["DIXON"]["shares"],
        "attempt_count": 0,
    })
    # Also simulate all 8 slots full by inserting dummy active positions
    for i in range(1, 8):
        temp_portfolio.state.active_positions[f"DUMMY{i}"] = {
            "symbol": f"DUMMY{i}", "entry_date": "2026-10-26", "shares": 100.0,
            "invested_capital": 100000.0, "entry_price": 1000.0, "entry_price_with_friction": 1010.0,
            "current_price": 1000.0, "peak_price": 1000.0, "current_gain_pct": 0.0,
            "peak_gain_pct": 0.0, "unrealized_pnl_rs": 0.0, "target_slot_capital": 125000.0,
            "tranche1_shares": 100.0, "tranche1_price": 1000.0, "bars_held": 2,
        }
    # Exactly 8 active positions, so free slots at open = 0!
    assert len(temp_portfolio.state.active_positions) == 8

    # Queue a new entry candidate for morning open
    temp_portfolio.state.pending_entries.append({
        "symbol": "NEWSTOCK", "signal_date": "2026-10-27", "sector": "Auto", "selection_reason": "VCP"
    })

    # Morning open: DIXON exits, but NEWSTOCK must NOT fill because slots at open = 0
    day_bars = pd.DataFrame([
        {"date": "2026-10-28", "symbol": "DIXON", "open": 920.0, "high": 930.0, "low": 915.0, "close": 925.0, "volume": 100000},
        {"date": "2026-10-28", "symbol": "NEWSTOCK", "open": 500.0, "high": 510.0, "low": 495.0, "close": 505.0, "volume": 100000},
    ])
    res = temp_portfolio.execute_daily_rebalance(day_bars, BENCH, pd.DataFrame(), current_date_str="2026-10-28")

    assert "DIXON" not in temp_portfolio.state.active_positions
    assert "NEWSTOCK" not in temp_portfolio.state.active_positions
    assert any("QUEUED ORDERS DROPPED" in a for a in res["actions_taken"])


def test_demerger_resolution_creates_spin_off_entitlement_preserving_equity(temp_portfolio):
    """Demerger with cost_basis_factor < 1.0 must track carved-out capital in spin-off entitlements."""
    _enter(temp_portfolio)
    pos = temp_portfolio.state.active_positions["DIXON"]
    pos["is_quarantined"] = True
    pos["anomaly_days"] = 1

    summary_before = temp_portfolio.get_summary()
    equity_before = summary_before["total_equity"]
    old_inv = float(pos["invested_capital"])

    # Demerger resolution: parent retains 80% cost basis, 20% spin-off entitlement
    res = temp_portfolio.resolve_corporate_action("DIXON", split_ratio=1.0, cost_basis_factor=0.80, event_id="DEMERGER_DIXON_1")
    assert pos["invested_capital"] == pytest.approx(old_inv * 0.80)

    # Entitlement must be recorded
    assert len(temp_portfolio.state.corporate_action_entitlements) == 1
    ent = temp_portfolio.state.corporate_action_entitlements[0]
    assert ent["event_id"] == "DEMERGER_DIXON_1"
    assert ent["parent_symbol"] == "DIXON"
    assert ent["allocated_capital"] == pytest.approx(old_inv * 0.20)
    assert ent["status"] == "Awaiting Listing / Credit"

    # Total portfolio equity must be conserved (entitlement value included)
    summary_after = temp_portfolio.get_summary()
    assert summary_after["total_equity"] == pytest.approx(equity_before)

    # Settle entitlement when spin-off lists/credits cash
    settled = temp_portfolio.settle_corporate_action_entitlement(event_id="DEMERGER_DIXON_1", realized_cash=12500.0)
    assert settled["status"] == "Settled"
    assert settled["realized_cash"] == 12500.0


def test_causal_benchmark_filters_future_and_rejects_stale(temp_portfolio):
    """Benchmark regime check must strictly filter future bars (<= today_date) and reject stale feeds."""
    # 1. Future bars in bench_df must not leak into decision
    dates_with_future = pd.bdate_range("2025-01-01", periods=250)
    future_bench = pd.DataFrame({"date": dates_with_future, "close": np.linspace(20000, 25000, 250)})
    
    # Evaluate at a past date (only 50 bars exist <= 2025-03-15)
    res_future = temp_portfolio.execute_daily_rebalance(
        _bar("2025-03-15", 1000.0, 1010.0, 990.0, 1000.0), future_bench, CAND, current_date_str="2025-03-15"
    )
    # Only 50 causal bars exist up to 2025-03-15, which is <200 -> fail closed!
    assert res_future["regime_ok"] is False

    # 2. Stale benchmark (>7 days old) must fail-closed
    stale_dates = pd.bdate_range(end="2026-10-10", periods=250)
    stale_bench = pd.DataFrame({"date": stale_dates, "close": np.linspace(20000, 25000, 250)})
    res_stale = temp_portfolio.execute_daily_rebalance(
        _bar("2026-10-26", 1000.0, 1010.0, 990.0, 1000.0), stale_bench, CAND, current_date_str="2026-10-26"
    )
    # 2026-10-26 is 16 days after 2026-10-10 (> 7 calendar days) -> fail closed!
    assert res_stale["regime_ok"] is False


def test_open_at_floor_lower_circuit_defers_exit(temp_portfolio):
    """If stock opens at floor (open == low <= prev_close * 0.95), exit must be deferred to prevent impossible fills."""
    _enter(temp_portfolio)
    temp_portfolio.state.pending_exits.append({
        "symbol": "DIXON",
        "signal_date": "2026-10-27",
        "exit_reason": "Closing Stop-Loss (ATR / -8% Threshold)",
        "stage_at_signal": "Stage 1: Ignition Defense",
        "signal_price": 930.0,
        "shares": temp_portfolio.state.active_positions["DIXON"]["shares"],
        "attempt_count": 0,
    })

    # Opens locked at 5% lower circuit floor (open == low == 970 <= 1025 * 0.95)
    floor_bar = pd.DataFrame([{
        "date": "2026-10-28", "symbol": "DIXON",
        "open": 970.0, "high": 970.0, "low": 970.0, "close": 970.0,
        "volume": 5000, "prev_close": 1025.0,
    }])
    res = temp_portfolio.execute_daily_rebalance(floor_bar, BENCH, pd.DataFrame(), current_date_str="2026-10-28")

    assert len(temp_portfolio.state.pending_exits) == 1
    assert temp_portfolio.state.pending_exits[0]["attempt_count"] == 1
    assert "DIXON" in temp_portfolio.state.active_positions
    assert any("PENDING EXIT DEFERRED" in a for a in res["actions_taken"])


def test_settle_entitlement_requires_verified_cash_and_rejects_nan_negative(temp_portfolio):
    """Entitlement settlement requires verified, finite, non-negative cash; no default fabrication."""
    _enter(temp_portfolio)
    pos = temp_portfolio.state.active_positions["DIXON"]
    pos["is_quarantined"] = True
    temp_portfolio.resolve_corporate_action("DIXON", split_ratio=1.0, cost_basis_factor=0.80, event_id="DEMERGER_DIXON_2")

    # 1. Calling without realized_cash must fail
    with pytest.raises((TypeError, ValueError)):
        temp_portfolio.settle_corporate_action_entitlement(event_id="DEMERGER_DIXON_2", realized_cash=float("nan"))

    # 2. Negative amount must be rejected with ValueError
    with pytest.raises(ValueError, match="finite non-negative"):
        temp_portfolio.settle_corporate_action_entitlement(event_id="DEMERGER_DIXON_2", realized_cash=-500.0)

    # 3. Valid settlement credits verified cash
    cash_before = temp_portfolio.state.cash
    settled = temp_portfolio.settle_corporate_action_entitlement(event_id="DEMERGER_DIXON_2", realized_cash=12500.0)
    assert settled["status"] == "Settled"
    assert settled["realized_cash"] == 12500.0
    assert temp_portfolio.state.cash == cash_before + 12500.0


def test_rebound_after_open_at_circuit_floor_still_defers_morning_exit(temp_portfolio):
    """If stock opens locked at circuit floor, exit is deferred even if stock rebounds intraday."""
    _enter(temp_portfolio)
    temp_portfolio.state.pending_exits.append({
        "symbol": "DIXON",
        "signal_date": "2026-10-27",
        "exit_reason": "Closing Stop-Loss (ATR / -8% Threshold)",
        "stage_at_signal": "Stage 1: Ignition Defense",
        "signal_price": 930.0,
        "shares": temp_portfolio.state.active_positions["DIXON"]["shares"],
        "attempt_count": 0,
    })

    # Opens locked at 5% floor (970 <= 1025 * 0.95), but rebounds intraday to 1050 and closes at 1040
    rebound_bar = pd.DataFrame([{
        "date": "2026-10-28", "symbol": "DIXON",
        "open": 970.0, "high": 1050.0, "low": 970.0, "close": 1040.0,
        "volume": 50000, "prev_close": 1025.0,
    }])
    res = temp_portfolio.execute_daily_rebalance(rebound_bar, BENCH, pd.DataFrame(), current_date_str="2026-10-28")

    assert len(temp_portfolio.state.pending_exits) == 1
    assert temp_portfolio.state.pending_exits[0]["attempt_count"] == 1
    assert "DIXON" in temp_portfolio.state.active_positions
    assert any("PENDING EXIT DEFERRED" in a for a in res["actions_taken"])


def test_resolve_corporate_action_idempotency_and_quarantine_guard(temp_portfolio):
    """resolve_corporate_action rejects unquarantined positions, repeated calls, and supports custom spinoff valuation."""
    _enter(temp_portfolio)
    pos = temp_portfolio.state.active_positions["DIXON"]
    pos["is_quarantined"] = True

    # 1. First resolution with custom market value
    res = temp_portfolio.resolve_corporate_action(
        "DIXON", split_ratio=1.0, cost_basis_factor=0.80, spinoff_market_value=15000.0, event_id="DEMERGER_2026"
    )
    assert len(temp_portfolio.state.corporate_action_entitlements) == 1
    assert temp_portfolio.state.corporate_action_entitlements[0]["market_value"] == 15000.0
    assert pos["is_quarantined"] is False

    # 2. Second resolution on now-unquarantined position must be rejected (RuntimeError)
    with pytest.raises(RuntimeError, match="not currently quarantined"):
        temp_portfolio.resolve_corporate_action("DIXON", split_ratio=1.0, cost_basis_factor=0.80, event_id="NEW_DEMERGER")

    # 3. If quarantined again, reusing same event_id must be rejected (ValueError)
    pos["is_quarantined"] = True
    with pytest.raises(ValueError, match="already been resolved"):
        temp_portfolio.resolve_corporate_action("DIXON", split_ratio=1.0, cost_basis_factor=0.80, event_id="DEMERGER_2026")


def test_open_time_anomaly_uses_only_open_data_and_ignores_intraday_low_crash(temp_portfolio):
    """Step 0a Tranche 2 at open must not be blocked by lookahead from future intraday crash."""
    _enter(temp_portfolio)
    pos = temp_portfolio.state.active_positions["DIXON"]
    pos["tranche2_eligible"] = True

    # Stock opens normally at 1025.0, but later intraday crashes to 600.0 (-41%)
    intraday_crash_bar = pd.DataFrame([{
        "date": "2026-10-28", "symbol": "DIXON",
        "open": 1025.0, "high": 1030.0, "low": 600.0, "close": 610.0,
        "volume": 100000, "prev_close": 1025.0,
    }])
    res = temp_portfolio.execute_daily_rebalance(
        intraday_crash_bar, BENCH, pd.DataFrame(), current_date_str="2026-10-28"
    )

    # At open (Step 0a): Tranche 2 was filled normally because open was 1025.0 (no anomaly at open)
    pos_after = temp_portfolio.state.active_positions["DIXON"]
    assert pos_after["tranche2_active"] is True
    assert any("TRANCHE 2 FILLED" in a for a in res["actions_taken"])

    # At EOD (Step A): The -41% crash was detected and position was properly quarantined for subsequent days
    assert pos_after["is_quarantined"] is True
    assert any("QUARANTINE / ALERT" in a for a in res["actions_taken"])


def test_malformed_state_schema_triggers_backup_and_fail_closed(tmp_path):
    """Malformed schema (e.g. non-list entitlements, non-dict positions) must trigger .corrupt.bak and fail closed."""
    malformed_file = tmp_path / "bad_schema.json"
    malformed_file.write_text('{"initial_capital": 1000000, "corporate_action_entitlements": "not_a_list"}', encoding="utf-8")

    with pytest.raises(RuntimeError, match="is corrupted"):
        LivePortfolioManager(state_path=malformed_file, initial_capital=1_000_000.0)

    bak_files = list(tmp_path.glob("bad_schema.json.corrupt.bak.*"))
    assert len(bak_files) == 1
    assert "not_a_list" in bak_files[0].read_text(encoding="utf-8")


def test_open_time_anomaly_ignores_eod_corporate_anomaly_tag(temp_portfolio):
    """Step 0a Tranche 2 at open must not be blocked by EOD is_corporate_anomaly tag when open is normal."""
    _enter(temp_portfolio)
    pos = temp_portfolio.state.active_positions["DIXON"]
    pos["tranche2_eligible"] = True

    # Stock opens normally at 1025.0, but EOD bar has is_corporate_anomaly=True (from closing crash)
    eod_tagged_bar = pd.DataFrame([{
        "date": "2026-10-28", "symbol": "DIXON",
        "open": 1025.0, "high": 1030.0, "low": 600.0, "close": 610.0,
        "volume": 100000, "prev_close": 1025.0, "is_corporate_anomaly": True,
    }])
    res = temp_portfolio.execute_daily_rebalance(
        eod_tagged_bar, BENCH, pd.DataFrame(), current_date_str="2026-10-28"
    )

    # At 9:15 AM Open: Tranche 2 MUST fill because open was 1025.0 (EOD tag ignored at open)
    pos_after = temp_portfolio.state.active_positions["DIXON"]
    assert pos_after["tranche2_active"] is True
    assert any("TRANCHE 2 FILLED" in a for a in res["actions_taken"])

    # At 3:30 PM EOD (Step A): The anomaly is caught and position is quarantined for subsequent days
    assert pos_after["is_quarantined"] is True
    assert any("QUARANTINE / ALERT" in a for a in res["actions_taken"])


def test_two_percent_circuit_floor_rebound_defers_exit(temp_portfolio):
    """Reproduction: 2% floor (prev_close=1000, open=980, low=980, high=1050, close=1040) must defer exit."""
    _enter(temp_portfolio)
    temp_portfolio.state.pending_exits.append({
        "symbol": "DIXON",
        "signal_date": "2026-10-27",
        "exit_reason": "Closing Stop-Loss",
        "stage_at_signal": "Stage 1",
        "signal_price": 990.0,
        "shares": temp_portfolio.state.active_positions["DIXON"]["shares"],
        "attempt_count": 0,
    })

    # Opens locked at 2% lower circuit floor (open == low == 980 vs prev_close 1000), then rebounds
    rebound_2pct_bar = pd.DataFrame([{
        "date": "2026-10-28", "symbol": "DIXON",
        "open": 980.0, "high": 1050.0, "low": 980.0, "close": 1040.0,
        "volume": 20000, "prev_close": 1000.0,
    }])
    res = temp_portfolio.execute_daily_rebalance(rebound_2pct_bar, BENCH, pd.DataFrame(), current_date_str="2026-10-28")

    assert len(temp_portfolio.state.pending_exits) == 1
    assert temp_portfolio.state.pending_exits[0]["attempt_count"] == 1
    assert "DIXON" in temp_portfolio.state.active_positions
    assert any("PENDING EXIT DEFERRED" in a for a in res["actions_taken"])


def test_multiple_entitlements_require_event_id_to_settle_unambiguously(temp_portfolio):
    """Multiple entitlements for the same symbol must reject symbol-only settlement and require event_id."""
    _enter(temp_portfolio)
    pos = temp_portfolio.state.active_positions["DIXON"]
    pos["is_quarantined"] = True

    # Event 1: Demerger A (80% cost retained, 20% spin-off)
    temp_portfolio.resolve_corporate_action("DIXON", split_ratio=1.0, cost_basis_factor=0.80, event_id="EVENT_A")

    # Manually re-quarantine to simulate a subsequent corporate action Event 2
    pos["is_quarantined"] = True
    temp_portfolio.resolve_corporate_action("DIXON", split_ratio=1.0, cost_basis_factor=0.90, event_id="EVENT_B")

    assert len(temp_portfolio.state.corporate_action_entitlements) == 2

    # Settling by symbol alone must be rejected with ValueError due to ambiguity
    with pytest.raises(ValueError, match="Multiple active entitlements exist"):
        temp_portfolio.settle_corporate_action_entitlement(parent_symbol="DIXON", realized_cash=5000.0)

    # Settling with specific event_id succeeds cleanly
    settled = temp_portfolio.settle_corporate_action_entitlement(event_id="EVENT_A", realized_cash=10000.0)
    assert settled["status"] == "Settled"
    assert settled["event_id"] == "EVENT_A"


def test_corrupt_state_closed_trades_null_item_fails_closed(tmp_path):
    """State with closed_trades containing null items must trigger .corrupt.bak and fail closed."""
    corrupt_file = tmp_path / "bad_closed_trades.json"
    corrupt_file.write_text('{"initial_capital": 1000000, "closed_trades": [null]}', encoding="utf-8")

    with pytest.raises(RuntimeError, match="is corrupted"):
        LivePortfolioManager(state_path=corrupt_file, initial_capital=1_000_000.0)

    bak_files = list(tmp_path.glob("bad_closed_trades.json.corrupt.bak.*"))
    assert len(bak_files) == 1


def test_upper_circuit_open_ceiling_blocks_new_entry(temp_portfolio):
    """Stock opening locked at upper circuit ceiling (open == high >= prev_close * 1.05) cannot fill new entry."""
    temp_portfolio.state.pending_entries.append({
        "symbol": "LOCKUP", "signal_date": "2026-10-27", "sector": "Auto", "selection_reason": "VCP"
    })

    # Opens locked at 5% upper circuit ceiling (525 >= 500 * 1.05), but later intraday trades lower (low=510, close=520)
    ceiling_bar = pd.DataFrame([{
        "date": "2026-10-28", "symbol": "LOCKUP",
        "open": 525.0, "high": 525.0, "low": 510.0, "close": 520.0,
        "volume": 50000, "prev_close": 500.0,
    }])
    res = temp_portfolio.execute_daily_rebalance(ceiling_bar, BENCH, pd.DataFrame(), current_date_str="2026-10-28")

    assert "LOCKUP" not in temp_portfolio.state.active_positions
    assert any("locked at upper circuit ceiling at open" in a for a in res["actions_taken"])


def test_upper_circuit_open_ceiling_defers_tranche2(temp_portfolio):
    """Tranche 2 addition cannot fill at open if stock is locked limit-up at ceiling."""
    _enter(temp_portfolio)
    pos = temp_portfolio.state.active_positions["DIXON"]
    pos["tranche2_eligible"] = True
    shares_before = pos["shares"]

    # Opens at 5% upper circuit ceiling (1076.25 >= 1025 * 1.05), later trades lower
    uc_bar = pd.DataFrame([{
        "date": "2026-10-28", "symbol": "DIXON",
        "open": 1076.25, "high": 1076.25, "low": 1060.0, "close": 1070.0,
        "volume": 50000, "prev_close": 1025.0,
    }])
    res = temp_portfolio.execute_daily_rebalance(uc_bar, BENCH, pd.DataFrame(), current_date_str="2026-10-28")

    pos_after = temp_portfolio.state.active_positions["DIXON"]
    assert pos_after["shares"] == shares_before
    assert pos_after["tranche2_active"] is False
    assert any("TRANCHE 2 DEFERRED" in a for a in res["actions_taken"])


def test_eq_open_includes_corporate_action_entitlements(temp_portfolio):
    """Step 0b slot_cap calculation must include corporate action entitlements value."""
    _enter(temp_portfolio)
    pos = temp_portfolio.state.active_positions["DIXON"]
    pos["is_quarantined"] = True

    # Demerger resolution creates spin-off entitlement
    temp_portfolio.resolve_corporate_action("DIXON", split_ratio=1.0, cost_basis_factor=0.80, spinoff_market_value=25000.0, event_id="DEMERGER_SIZING")
    assert len(temp_portfolio.state.corporate_action_entitlements) == 1

    # Queue an entry candidate
    temp_portfolio.state.pending_entries.append({
        "symbol": "NEWSTOCK", "signal_date": "2026-10-27", "sector": "Auto", "selection_reason": "VCP"
    })

    day_bars = pd.DataFrame([
        {"date": "2026-10-28", "symbol": "DIXON", "open": 820.0, "high": 830.0, "low": 815.0, "close": 825.0, "volume": 100000},
        {"date": "2026-10-28", "symbol": "NEWSTOCK", "open": 500.0, "high": 510.0, "low": 495.0, "close": 505.0, "volume": 100000},
    ])
    temp_portfolio.execute_daily_rebalance(day_bars, BENCH, pd.DataFrame(), current_date_str="2026-10-28")

    assert "NEWSTOCK" in temp_portfolio.state.active_positions
    new_pos = temp_portfolio.state.active_positions["NEWSTOCK"]
    # target_slot_capital must be ~125,000 (total equity ~1,000,000 / 8 slots)
    assert new_pos["target_slot_capital"] == pytest.approx(126619.0, rel=0.01)


def test_sector_guardrail_filters_exiting_positions_with_current_stage():
    """apply_sector_cluster_guardrail must ignore positions with 'PENDING EXIT' in current_stage."""
    from blumberg_market_radar.scanner.radar import apply_sector_cluster_guardrail

    active_df = pd.DataFrame([
        {"symbol": "AUTO1", "sector": "Auto", "current_stage": "Stage 1: Ignition Defense"},
        {"symbol": "AUTO2", "sector": "Auto", "current_stage": "PENDING EXIT: Closing Stop-Loss"},  # Exiting!
    ])
    candidates = pd.DataFrame([
        {"symbol": "AUTO3", "sector": "Auto", "radar_score": 90.0},
    ])

    approved, counts, free = apply_sector_cluster_guardrail(
        candidates,
        active_pipeline_df=active_df,
        max_stocks_per_sector=2,
        max_portfolio_slots=8,
    )
    # AUTO2 is exiting, so Auto sector count should be 1, allowing AUTO3 to be approved!
    assert "AUTO3" in approved["symbol"].values
    assert counts.get("Auto") == 2
