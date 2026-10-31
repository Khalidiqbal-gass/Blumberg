"""
Live Autonomous Paper Portfolio Engine (HYBRID_50_50 Sweet Spot 8-Slot Champion Model).

Manages an active portfolio ledger implementing:
1. Configurable initial capital (Default: Rs. 10 Lakhs = Rs. 1,000,000).
2. Exactly 8 Equal-Weight Portfolio Slots (12.5% allocation per slot).
3. 2-Tranche Fast Pyramiding:
   - Tranche 1 (50% = 6.25%) at Day 0 VCP Breakout base.
   - Tranche 2 (50% = 6.25%) at Day 7 Confirmation ONLY if in profit.
4. 5-Stage Multi-Tiered Dynamic Exit Engine:
   - Stage 1: Hard Stop (-10%) / ATR Stop (-8%) / 30d Dead-Money Stop
   - Stage 2: Breakeven Floor (+2% Profit Locked) at +15% Peak
   - Stage 3: Ratchet Floor (+12% Profit Locked & 50 EMA) at +30% Peak
   - Stage 4: Secular Multibagger Floor (+25% Profit Locked & 100 EMA) at +60% Peak
   - Stage 5: Climax Harvesting (25% Trailing Drawdown from Peak) at +100%+ Peak
5. Persistent JSON Ledger storage (data/live_portfolio_state.json).
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

DEFAULT_PORTFOLIO_PATH = Path("data/live_portfolio_state.json")


@dataclass
class LiveTradePosition:
    symbol: str
    entry_date: str
    shares: float
    invested_capital: float
    entry_price: float
    entry_price_with_friction: float
    current_price: float
    peak_price: float
    current_gain_pct: float
    peak_gain_pct: float
    unrealized_pnl_rs: float
    target_slot_capital: float
    tranche1_shares: float
    tranche1_price: float
    tranche2_active: bool = False
    tranche2_date: str | None = None
    tranche2_shares: float = 0.0
    tranche2_price: float = 0.0
    current_stage: str = "Stage 1: Ignition Defense"
    stop_loss_price: float = 0.0
    profit_floor_price: float = 0.0
    bars_held: int = 1
    is_climax_reached: bool = False
    sector: str = "Diversified"
    selection_reason: str = "VCP Volatility Contraction Breakout"


@dataclass
class ClosedTradeRecord:
    symbol: str
    entry_date: str
    exit_date: str
    shares: float
    entry_price: float
    exit_price: float
    gross_return_pct: float
    net_return_pct: float
    net_pnl_rs: float
    exit_reason: str
    stage_at_exit: str
    bars_held: int
    sector: str = "Diversified"


@dataclass
class LivePortfolioState:
    initial_capital: float = 1_000_000.0
    cash: float = 1_000_000.0
    active_positions: dict[str, dict] = field(default_factory=dict)
    closed_trades: list[dict] = field(default_factory=list)
    daily_equity_history: list[dict] = field(default_factory=list)
    last_rebalance_date: str = ""
    created_at: str = ""
    pending_entries: list[dict] = field(default_factory=list)  # signals to be filled at the NEXT session open


class LivePortfolioManager:
    """Manages persistent live paper trading operations matching the Champion Backtest Engine."""

    def __init__(
        self,
        state_path: Path | str = DEFAULT_PORTFOLIO_PATH,
        initial_capital: float = 1_000_000.0,
        max_slots: int = 8,
        tranche2_days: int = 7,
        slippage_bps: float = 50.0,
        statutory_bps: float = 52.6,
        cash_yield_pct_p_a: float = 6.5,
        max_pct_of_adv: float | None = 10.0,  # cap each fill at this % of 20d avg turnover (same as backtest)
    ):
        self.state_path = Path(state_path)
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.initial_capital = float(initial_capital)
        self.max_slots = max_slots
        self.tranche2_days = tranche2_days
        self.cost_per_side = (slippage_bps + statutory_bps) / 10_000.0
        self.max_pct_of_adv = max_pct_of_adv
        # FIX: compound daily yield matches engine formula: (1 + r_annual)^(1/252) - 1
        # Old formula (r/252) gives ~6.72% effective annual yield when compounded daily instead of 6.50%.
        self.cash_yield_daily = (
            (1.0 + cash_yield_pct_p_a / 100.0) ** (1.0 / 252.0) - 1.0
            if cash_yield_pct_p_a > 0.0
            else 0.0
        )
        self.state = self.load_state()

    def load_state(self) -> LivePortfolioState:
        """Load state from JSON or initialize fresh."""
        if self.state_path.exists():
            try:
                with open(self.state_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return LivePortfolioState(
                    initial_capital=float(data.get("initial_capital", self.initial_capital)),
                    cash=float(data.get("cash", self.initial_capital)),
                    active_positions=data.get("active_positions", {}),
                    closed_trades=data.get("closed_trades", []),
                    daily_equity_history=data.get("daily_equity_history", []),
                    last_rebalance_date=data.get("last_rebalance_date", ""),
                    created_at=data.get("created_at", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
                    pending_entries=data.get("pending_entries", []),
                )
            except Exception as exc:
                logger.warning(f"Could not parse state file: {exc}. Starting fresh.")

        today_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        fresh = LivePortfolioState(
            initial_capital=self.initial_capital,
            cash=self.initial_capital,
            active_positions={},
            closed_trades=[],
            daily_equity_history=[],
            last_rebalance_date="",
            created_at=today_str,
        )
        self.save_state(fresh)
        return fresh

    def save_state(self, state: LivePortfolioState | None = None) -> None:
        """Save portfolio state to JSON."""
        target = state or self.state
        with open(self.state_path, "w", encoding="utf-8") as f:
            json.dump(asdict(target), f, indent=2)

    def reset_portfolio(self, capital: float | None = None) -> LivePortfolioState:
        """Completely reset portfolio ledger with new capital."""
        cap = float(capital) if capital is not None else self.initial_capital
        today_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.state = LivePortfolioState(
            initial_capital=cap,
            cash=cap,
            active_positions={},
            closed_trades=[],
            daily_equity_history=[],
            last_rebalance_date="",
            created_at=today_str,
        )
        self.save_state()
        return self.state

    def get_summary(self, latest_prices: dict[str, float] | None = None) -> dict:
        """Compute live portfolio metrics."""
        prices = latest_prices or {}
        mtm_positions = 0.0

        for sym, pos_dict in self.state.active_positions.items():
            curr_p = prices.get(sym, pos_dict.get("current_price", pos_dict.get("entry_price", 0.0)))
            shares = pos_dict.get("shares", 0.0)
            mtm_positions += shares * curr_p

        total_equity = self.state.cash + mtm_positions
        invested = sum(p.get("invested_capital", 0.0) for p in self.state.active_positions.values())
        unrealized_pnl = mtm_positions - invested
        realized_pnl = sum(c.get("net_pnl_rs", 0.0) for c in self.state.closed_trades)
        total_pnl = total_equity - self.state.initial_capital
        total_return_pct = (total_equity / self.state.initial_capital - 1.0) * 100.0 if self.state.initial_capital > 0 else 0.0

        total_closed = len(self.state.closed_trades)
        winning_closed = len([c for c in self.state.closed_trades if c.get("net_pnl_rs", 0.0) > 0])
        win_rate = (winning_closed / total_closed * 100.0) if total_closed > 0 else 0.0

        return {
            "initial_capital": self.state.initial_capital,
            "total_equity": total_equity,
            "cash": self.state.cash,
            "invested_capital": invested,
            "market_value_holdings": mtm_positions,
            "unrealized_pnl_rs": unrealized_pnl,
            "unrealized_pnl_pct": (unrealized_pnl / invested * 100.0) if invested > 0 else 0.0,
            "realized_pnl_rs": realized_pnl,
            "total_pnl_rs": total_pnl,
            "total_return_pct": total_return_pct,
            "active_positions_count": len(self.state.active_positions),
            "max_slots": self.max_slots,
            "available_slots": max(0, self.max_slots - len(self.state.active_positions)),
            "total_closed_trades": total_closed,
            "winning_closed_trades": winning_closed,
            "win_rate_pct": win_rate,
            "last_rebalance_date": self.state.last_rebalance_date,
        }

    def execute_daily_rebalance(
        self,
        bars_df: pd.DataFrame,
        bench_df: pd.DataFrame,
        candidates_df: pd.DataFrame,
        current_date_str: str | None = None,
        enforce_regime: bool = True,
    ) -> dict:
        """Run complete daily decision cycle (Exits -> Tranche 2 -> New Entries -> MTM)."""
        today_date = current_date_str or datetime.now().strftime("%Y-%m-%d")
        actions_taken = []
        is_same_day_rerun = (self.state.last_rebalance_date == today_date)

        # 1. Benchmark Regime Check
        regime_ok = True
        if enforce_regime and bench_df is not None and not bench_df.empty and "date" in bench_df.columns and "close" in bench_df.columns:
            bench_sorted = bench_df.sort_values("date").reset_index(drop=True)
            if len(bench_sorted) >= 50:
                bench_close = bench_sorted["close"].iloc[-1]
                bench_ema50 = bench_sorted["close"].ewm(span=50, adjust=False).mean().iloc[-1]
                bench_ema200 = bench_sorted["close"].ewm(span=200, adjust=False).mean().iloc[-1] if len(bench_sorted) >= 200 else bench_ema50
                regime_ok = bool((bench_close > bench_ema50) or (bench_close > bench_ema200))

        # Accrue daily cash yield (Only once per calendar day)
        if not is_same_day_rerun:
            daily_yield_rs = self.state.cash * self.cash_yield_daily
            self.state.cash += daily_yield_rs

        # Ensure 14-day True Range ATR is computed across historical bars for accurate dynamic stops
        bars_proc = bars_df.sort_values(["symbol", "date"]).copy()
        if "atr_14" not in bars_proc.columns and "high" in bars_proc.columns and "low" in bars_proc.columns:
            prev_close = bars_proc.groupby("symbol")["close"].shift(1)
            tr1 = bars_proc["high"] - bars_proc["low"]
            tr2 = (bars_proc["high"] - prev_close).abs()
            tr3 = (bars_proc["low"] - prev_close).abs()
            bars_proc["tr"] = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            bars_proc["atr_14"] = bars_proc.groupby("symbol")["tr"].transform(
                lambda s: s.rolling(14, min_periods=14).mean()
            )

        if "adv_20" not in bars_proc.columns and "volume" in bars_proc.columns:
            _turn = bars_proc["close"] * bars_proc["volume"]
            bars_proc["adv_20"] = _turn.groupby(bars_proc["symbol"]).transform(
                lambda x: x.shift(1).rolling(20, min_periods=10).mean()
            )

        def _liq_cap(b_) -> float:
            if self.max_pct_of_adv is None or "adv_20" not in b_.index or pd.isna(b_["adv_20"]) or float(b_["adv_20"]) <= 0:
                return float("inf")
            return float(b_["adv_20"]) * self.max_pct_of_adv / 100.0

        if "prev_close" not in bars_proc.columns:
            bars_proc["prev_close"] = bars_proc.groupby("symbol")["close"].shift(1)
        for _span in (20, 50, 100):
            _col = f"ema{_span}"
            if _col not in bars_proc.columns:
                bars_proc[_col] = bars_proc.groupby("symbol")["close"].transform(
                    lambda s, n=_span: s.ewm(span=n, adjust=False).mean()
                )

        # Get latest bar mapping for all symbols
        bars_latest = bars_proc.groupby("symbol").last()

        def _bar_today(sym_: str):
            """Latest bar for sym_ if (and only if) it is today's session, else None."""
            if sym_ not in bars_latest.index:
                return None
            b_ = bars_latest.loc[sym_]
            if "date" in b_.index and pd.Timestamp(b_["date"]).strftime("%Y-%m-%d") != today_date:
                return None
            return b_

        # Step 0: Fill orders queued yesterday at TODAY'S OPEN (identical to backtest: signal at close D, fill at open D+1).
        # Cash/slots are those available before today's exits (T+1 settlement), exactly like the engine.
        fills_today: set[str] = set()
        if not is_same_day_rerun:
            # 0a. Tranche 2 (flagged eligible at yesterday's close) fills at today's open
            for sym, pos in list(self.state.active_positions.items()):
                if pos.get("tranche2_eligible") and not pos.get("tranche2_active", False):
                    pos["tranche2_eligible"] = False
                    b = _bar_today(sym)
                    if b is None or float(b["high"]) == float(b["low"]):  # no bar / upper-circuit lock
                        continue
                    raw_t2 = float(b["open"])
                    t2_alloc = min(self.state.cash, pos["target_slot_capital"] * 0.5, _liq_cap(b))
                    if t2_alloc < 2500.0:
                        continue
                    t2_shares = (t2_alloc * (1.0 - self.cost_per_side)) / raw_t2
                    self.state.cash -= t2_alloc
                    t1_shares = float(pos["shares"])
                    t1_price = float(pos.get("tranche1_price", pos["entry_price"]))
                    total_shares = t1_shares + t2_shares
                    pos["shares"] = total_shares
                    pos["invested_capital"] = float(pos["invested_capital"]) + t2_alloc
                    pos["entry_price"] = (t1_price * t1_shares + raw_t2 * t2_shares) / total_shares
                    pos["entry_price_with_friction"] = pos["entry_price"] * (1.0 + self.cost_per_side)
                    pos["tranche2_active"] = True
                    pos["tranche2_date"] = today_date
                    pos["tranche2_shares"] = t2_shares
                    pos["tranche2_price"] = raw_t2
                    actions_taken.append(f"ðŸŸ¢ TRANCHE 2 FILLED: {sym} +{t2_shares:.1f} shs @ open â‚¹{raw_t2:.2f} (Confirmed Winner)")

            # 0b. Tranche 1 entries queued yesterday
            queued = list(self.state.pending_entries)
            self.state.pending_entries = []
            if queued:
                eq_open = self.state.cash + sum(
                    float(p_["shares"]) * float(bars_latest.loc[s_]["open"]) if s_ in bars_latest.index else float(p_["invested_capital"])
                    for s_, p_ in self.state.active_positions.items()
                )
                slot_cap = eq_open / self.max_slots
                free_slots = max(0, self.max_slots - len(self.state.active_positions))
                for q in queued:
                    qsym = q["symbol"]
                    if free_slots <= 0 or self.state.cash < 2500.0:
                        break
                    if qsym in self.state.active_positions:
                        continue
                    b = _bar_today(qsym)
                    if b is None:
                        # Not traded today (holiday/suspension): keep the order only for a few sessions
                        age = (pd.Timestamp(today_date) - pd.Timestamp(q["signal_date"])).days
                        if age <= 5:
                            self.state.pending_entries.append(q)
                        continue
                    if float(b["high"]) == float(b["low"]):  # upper-circuit lock: cannot buy
                        actions_taken.append(f"â›” ORDER REJECTED: {qsym} locked at circuit, no entry")
                        continue
                    raw_entry = float(b["open"])
                    t1_alloc = min(self.state.cash, slot_cap * 0.5, _liq_cap(b))
                    if t1_alloc < 2500.0:
                        continue
                    t1_shares = (t1_alloc * (1.0 - self.cost_per_side)) / raw_entry
                    self.state.cash -= t1_alloc
                    pos_obj = LiveTradePosition(
                        symbol=qsym, entry_date=today_date, shares=t1_shares, invested_capital=t1_alloc,
                        entry_price=raw_entry, entry_price_with_friction=raw_entry * (1.0 + self.cost_per_side),
                        current_price=raw_entry, peak_price=max(raw_entry, float(b["high"])),
                        current_gain_pct=0.0, peak_gain_pct=0.0, unrealized_pnl_rs=0.0,
                        target_slot_capital=slot_cap, tranche1_shares=t1_shares, tranche1_price=raw_entry,
                        current_stage="Stage 1: Ignition Defense", stop_loss_price=raw_entry * 0.92,
                        profit_floor_price=0.0, bars_held=0, sector=str(q.get("sector", "Diversified")),
                        selection_reason=str(q.get("selection_reason", "VCP Base Squeeze")),
                    )
                    self.state.active_positions[qsym] = asdict(pos_obj)
                    fills_today.add(qsym)
                    free_slots -= 1
                    actions_taken.append(f"ðŸš€ ENTRY FILLED (Tranche 1): {qsym} {t1_shares:.1f} shs @ open â‚¹{raw_entry:.2f} (Invested: â‚¹{t1_alloc:,.0f})")

        # Step A: Evaluate Exits for Active Trades (positions opened this morning are not evaluated today, as in the engine)
        symbols_to_close = []
        for sym, pos in list(self.state.active_positions.items()):
            if sym in fills_today:
                continue
            if sym not in bars_latest.index:
                continue

            bar = bars_latest.loc[sym]
            close_p = float(bar["close"])
            open_p = float(bar["open"])
            low_p = float(bar["low"])
            high_p = float(bar["high"])

            # Same anchor as backtest: blended raw entry (friction-free) for milestones, stops and floors
            entry_p = float(pos["entry_price"])
            prior_peak = float(pos.get("peak_price", entry_p))
            gain_from_entry = (prior_peak / entry_p - 1.0) * 100.0

            exit_triggered = False
            exit_price = close_p
            exit_reason = ""
            stage_name = pos.get("current_stage", "Stage 1: Ignition Defense")

            dip_from_peak = (close_p / prior_peak - 1.0) * 100.0
            ema20_v = float(bar["ema20"]) if "ema20" in bar and pd.notna(bar["ema20"]) else None
            ema50_v = float(bar["ema50"]) if "ema50" in bar and pd.notna(bar["ema50"]) else None
            ema100_v = float(bar["ema100"]) if "ema100" in bar and pd.notna(bar["ema100"]) else None
            is_climax = bool(pos.get("is_climax_reached", False))

            # Tranche 2 eligibility (decided at today's close, filled at tomorrow's open) - same rule as the engine
            if (not pos.get("tranche2_active", False)) and pos.get("bars_held", 0) >= (self.tranche2_days - 1):
                if close_p > entry_p and low_p > entry_p * 0.92:
                    pos["tranche2_eligible"] = True

            # Exit ladder mirrors UpgradedVCPBacktestEngine one-for-one (same triggers, same fills).
            # ---------------- STAGE 5: CLIMAX (needs climax flag AND prior peak >= +100%) ----------------
            if is_climax and gain_from_entry >= 100.0:
                stage_name = "Stage 5: Climax Harvesting"
                pos["profit_floor_price"] = prior_peak * 0.75
                if dip_from_peak <= -25.0:
                    exit_triggered = True
                    exit_price = min(prior_peak * 0.75, open_p)
                    exit_reason = f"Parabolic Climax Exit (-25% Trail from Peak â‚¹{prior_peak:.2f})"

            # ---------------- STAGE 4: SECULAR COMPOUNDER (peak >= +50%) ----------------
            elif gain_from_entry >= 50.0:
                stage_name = "Stage 4: Secular Compounding"
                floor_4 = entry_p * 1.25
                pos["profit_floor_price"] = floor_4
                if low_p <= floor_4:
                    exit_triggered = True
                    exit_price = min(floor_4, open_p)
                    exit_reason = "Secular Profit Floor (+25% Floor Protected)"
                elif ema100_v is not None and close_p < ema100_v and dip_from_peak <= -20.0:
                    exit_triggered = True
                    exit_price = close_p
                    exit_reason = "Secular Trend Ended (100 EMA Break & -20% Drop)"

            # ---------------- STAGE 3: PROGRESSIVE RATCHET (+30% <= peak < +50%) ----------------
            elif 30.0 <= gain_from_entry < 50.0:
                stage_name = "Stage 3: Trend Momentum"
                floor_12 = entry_p * 1.12
                floor_px = max(floor_12, ema50_v) if ema50_v is not None else floor_12
                pos["profit_floor_price"] = floor_12
                if low_p <= floor_12:
                    exit_triggered = True
                    exit_price = min(floor_12, open_p)
                    exit_reason = "Ratchet Profit Floor (+12% Locked)"
                elif close_p < floor_px:
                    exit_triggered = True
                    exit_price = min(floor_px, open_p) if open_p < floor_px else close_p
                    exit_reason = "Ratchet Profit Floor (+12% / 50 EMA Locked)"

            # ---------------- STAGE 2: CAPITAL PRESERVATION (+15% <= peak < +30%) ----------------
            elif 15.0 <= gain_from_entry < 30.0:
                stage_name = "Stage 2: Capital Preservation"
                be_floor = entry_p * 1.02
                pos["profit_floor_price"] = be_floor
                if low_p <= be_floor:
                    exit_triggered = True
                    exit_price = min(be_floor, open_p)
                    exit_reason = "Breakeven Floor (+2% Profit Locked)"

            # ---------------- STAGE 1: IGNITION DEFENSE (peak < +15%) ----------------
            else:
                stage_name = "Stage 1: Ignition Defense"
                hard_stop = entry_p * 0.90
                atr_val = float(bar["atr_14"]) if ("atr_14" in bar and pd.notna(bar["atr_14"])) else close_p * 0.03
                closing_stop = max(entry_p * 0.92, entry_p - 2.5 * atr_val)
                pos["stop_loss_price"] = closing_stop

                # Demerger / Corporate Action anomaly check (LIVE-ONLY safety): a >35% single-day drop on an
                # unadjusted corporate action (e.g. VEDL demerger) must not trigger a blind panic exit.
                is_corp_action_anomaly = (low_p <= entry_p * 0.65) and (prior_peak >= entry_p * 0.95)

                if is_corp_action_anomaly:
                    if not is_same_day_rerun:
                        pos["anomaly_days"] = int(pos.get("anomaly_days", 0)) + 1
                    if int(pos.get("anomaly_days", 0)) >= 3:
                        # A genuine crash must not be held forever just because it looks like an unadjusted corporate action
                        exit_triggered = True
                        exit_price = close_p
                        exit_reason = "Unresolved >35% Drop (3 sessions) - forced exit"
                    else:
                        logger.warning(f"âš ï¸ Potential unadjusted corporate action / demerger anomaly in {sym}. Halting automated exit.")
                        actions_taken.append(f"âš ï¸ HOLD / ALERT: {sym} dropped >35% (Possible Corporate Action/Demerger). Auto-exit halted for audit; forced exit after 3 sessions.")
                elif low_p <= hard_stop:
                    exit_triggered = True
                    exit_price = min(hard_stop, open_p)
                    exit_reason = "Extreme Circuit Breaker (-10% Hard Stop)"
                elif close_p <= closing_stop:
                    exit_triggered = True
                    exit_price = min(closing_stop, open_p) if open_p < closing_stop else close_p
                    exit_reason = "Closing Stop-Loss (ATR / -8% Threshold)"
                elif pos["bars_held"] >= 30 and gain_from_entry < 10.0 and (ema20_v is None or close_p < ema20_v):
                    exit_triggered = True
                    exit_price = close_p
                    exit_reason = "Dead Money Time-Stop Exit (30d Stagnant Base & Below 20 EMA)"

            prev_recorded_price = pos.get("current_price")
            pos["current_stage"] = stage_name
            pos["current_price"] = close_p
            pos["current_gain_pct"] = (close_p / entry_p - 1.0) * 100.0
            pos["unrealized_pnl_rs"] = (close_p * pos["shares"]) - pos["invested_capital"]

            if exit_triggered:
                # Lower circuit check: if stock is locked limit-down, cannot sell today
                prev_c = float(bar["prev_close"]) if "prev_close" in bar and pd.notna(bar["prev_close"]) else None
                if prev_c is None and prev_recorded_price:
                    prev_c = float(prev_recorded_price)  # price recorded at the previous rebalance
                is_lower_circuit = (open_p == low_p and high_p == low_p and prev_c is not None and close_p < prev_c)  # locked DOWN
                if is_lower_circuit and "Dead Money" not in exit_reason:
                    pos["current_stage"] = f"CIRCUIT_DEFER: {exit_reason}"
                    if not is_same_day_rerun:
                        pos["bars_held"] = pos.get("bars_held", 0) + 1
                    actions_taken.append(f"âš ï¸ PENDING EXIT: {sym} locked in Lower Circuit. Exit deferred to next session.")
                    if high_p > prior_peak:
                        pos["peak_price"] = high_p
                        pos["peak_gain_pct"] = (high_p / entry_p - 1.0) * 100.0
                else:
                    symbols_to_close.append((sym, exit_price, exit_reason, stage_name))
            else:
                # Update peak only if trade survived session
                if not is_same_day_rerun:
                    pos["bars_held"] = pos.get("bars_held", 0) + 1
                if high_p > prior_peak:
                    pos["peak_price"] = high_p
                    pos["peak_gain_pct"] = (high_p / entry_p - 1.0) * 100.0
                # Climax flag with bidirectional reset (same rule as backtest)
                if ema100_v is not None and ema100_v > 0:
                    dist100 = close_p / ema100_v - 1.0
                    if dist100 > 0.60:
                        pos["is_climax_reached"] = True
                    elif is_climax and dist100 < 0.35:
                        pos["is_climax_reached"] = False

        # Execute Exits
        for sym, exit_p, reason, stg in symbols_to_close:
            pos = self.state.active_positions[sym]
            sell_friction = exit_p * pos["shares"] * self.cost_per_side
            net_proceeds = (exit_p * pos["shares"]) - sell_friction
            self.state.cash += net_proceeds

            net_ret = (exit_p * (1.0 - self.cost_per_side) / pos["entry_price_with_friction"] - 1.0) * 100.0
            net_pnl = net_proceeds - pos["invested_capital"]

            closed_rec = ClosedTradeRecord(
                symbol=sym,
                entry_date=pos["entry_date"],
                exit_date=today_date,
                shares=pos["shares"],
                entry_price=pos["entry_price"],
                exit_price=exit_p,
                gross_return_pct=(exit_p / pos["entry_price"] - 1.0) * 100.0,
                net_return_pct=net_ret,
                net_pnl_rs=net_pnl,
                exit_reason=reason,
                stage_at_exit=stg,
                bars_held=pos["bars_held"],
                sector=pos.get("sector", "Diversified"),
            )
            self.state.closed_trades.append(asdict(closed_rec))
            del self.state.active_positions[sym]
            actions_taken.append(f"ðŸ”´ SELL: {sym} exited at â‚¹{exit_p:.2f} ({net_ret:+.1f}%) | Reason: {reason}")

        # Step C: Queue new signals. They are FILLED at tomorrow's open (never at the signal-day close,
        # which is unattainable and not what the backtest assumes).
        available_slots = max(0, self.max_slots - len(self.state.active_positions) - len(self.state.pending_entries))
        queued_syms = {q["symbol"] for q in self.state.pending_entries}
        if (not is_same_day_rerun) and regime_ok and available_slots > 0 and candidates_df is not None and not candidates_df.empty:
            for _, row in candidates_df.iterrows():
                if available_slots <= 0:
                    break
                sym = str(row["symbol"]).upper().replace(".NS", "").replace(".BO", "").strip()
                if sym in self.state.active_positions or sym in queued_syms or sym not in bars_latest.index:
                    continue
                self.state.pending_entries.append({
                    "symbol": sym,
                    "signal_date": today_date,
                    "sector": str(row.get("sector", "Diversified")),
                    "selection_reason": str(row.get("selection_reason", row.get("primary_driver", "VCP Base Squeeze"))),
                })
                queued_syms.add(sym)
                available_slots -= 1
                actions_taken.append(f"ðŸ“ BUY ORDER QUEUED: {sym} (fills at next session open)")

        # Step D: Final Mark to Market & Save
        final_summary = self.get_summary(bars_latest["close"].to_dict())
        self.state.last_rebalance_date = today_date
        self.state.daily_equity_history.append({
            "date": today_date,
            "total_equity": final_summary["total_equity"],
            "cash": final_summary["cash"],
            "invested": final_summary["invested_capital"],
            "active_slots": final_summary["active_positions_count"],
        })
        self.save_state()

        return {
            "date": today_date,
            "regime_ok": regime_ok,
            "actions_taken": actions_taken,
            "summary": final_summary,
        }
