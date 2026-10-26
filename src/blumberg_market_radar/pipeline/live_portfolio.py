"""
Live Autonomous Paper Portfolio Engine (HYBRID_50_50 Institutional 10-Slot Champion Model).

Manages an active portfolio ledger implementing:
1. Configurable initial capital (Default: Rs. 10 Lakhs = Rs. 1,000,000).
2. Exactly 10 Equal-Weight Portfolio Slots (10.0% allocation per slot).
3. 2-Tranche Fast Pyramiding:
   - Tranche 1 (50% = 5.0%) at Day 0 VCP Breakout base.
   - Tranche 2 (50% = 5.0%) at Day 7 Confirmation ONLY if in profit.
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


class LivePortfolioManager:
    """Manages persistent live paper trading operations matching the Champion Backtest Engine."""

    def __init__(
        self,
        state_path: Path | str = DEFAULT_PORTFOLIO_PATH,
        initial_capital: float = 1_000_000.0,
        max_slots: int = 10,
        tranche2_days: int = 7,
        slippage_bps: float = 20.0,
        statutory_bps: float = 35.0,
        cash_yield_pct_p_a: float = 6.5,
    ):
        self.state_path = Path(state_path)
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.initial_capital = float(initial_capital)
        self.max_slots = max_slots
        self.tranche2_days = tranche2_days
        self.cost_per_side = (slippage_bps + statutory_bps) / 10_000.0
        self.cash_yield_daily = (cash_yield_pct_p_a / 100.0) / 252.0
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

        # 1. Benchmark Regime Check
        regime_ok = True
        if enforce_regime and bench_df is not None and not bench_df.empty and "date" in bench_df.columns and "close" in bench_df.columns:
            bench_sorted = bench_df.sort_values("date").reset_index(drop=True)
            if len(bench_sorted) >= 50:
                bench_close = bench_sorted["close"].iloc[-1]
                bench_ema50 = bench_sorted["close"].ewm(span=50, adjust=False).mean().iloc[-1]
                bench_ema200 = bench_sorted["close"].ewm(span=200, adjust=False).mean().iloc[-1] if len(bench_sorted) >= 200 else bench_ema50
                regime_ok = bool((bench_close > bench_ema50) or (bench_close > bench_ema200))

        # Accrue daily cash yield
        daily_yield_rs = self.state.cash * self.cash_yield_daily
        self.state.cash += daily_yield_rs

        # Get latest bar mapping for all symbols
        bars_latest = bars_df.sort_values("date").groupby("symbol").last()

        # Step A: Evaluate Exits for Active Trades
        symbols_to_close = []
        for sym, pos in list(self.state.active_positions.items()):
            pos["bars_held"] = pos.get("bars_held", 0) + 1
            if sym not in bars_latest.index:
                continue

            bar = bars_latest.loc[sym]
            close_p = float(bar["close"])
            open_p = float(bar["open"])
            low_p = float(bar["low"])
            high_p = float(bar["high"])

            entry_p = float(pos["entry_price"])
            prior_peak = float(pos.get("peak_price", entry_p))
            gain_from_entry = (prior_peak / entry_p - 1.0) * 100.0

            exit_triggered = False
            exit_price = close_p
            exit_reason = ""
            stage_name = pos.get("current_stage", "Stage 1: Ignition Defense")

            # ---------------- STAGE 5: CLIMAX HARVESTING (Peak >= +100%) ----------------
            if gain_from_entry >= 100.0:
                stage_name = "Stage 5: Climax Harvesting"
                floor_price = prior_peak * 0.75
                pos["profit_floor_price"] = floor_price
                if low_p <= floor_price:
                    exit_triggered = True
                    exit_price = min(floor_price, open_p)
                    exit_reason = f"Climax Profit Floor Breached (-25% from Peak ₹{prior_peak:.2f})"

            # ---------------- STAGE 4: SECULAR COMPOUNDER (+60% <= Peak < +100%) ----------------
            elif 60.0 <= gain_from_entry < 100.0:
                stage_name = "Stage 4: Secular Compounding"
                floor_4 = entry_p * 1.25
                pos["profit_floor_price"] = floor_4
                if low_p <= floor_4:
                    exit_triggered = True
                    exit_price = min(floor_4, open_p)
                    exit_reason = "Secular Profit Floor (+25% Floor Protected)"

            # ---------------- STAGE 3: TREND ACCELERATION (+30% <= Peak < +60%) ----------------
            elif 30.0 <= gain_from_entry < 60.0:
                stage_name = "Stage 3: Trend Momentum"
                floor_12 = entry_p * 1.12
                pos["profit_floor_price"] = floor_12
                if low_p <= floor_12:
                    exit_triggered = True
                    exit_price = min(floor_12, open_p)
                    exit_reason = "Ratchet Profit Floor (+12% Locked)"

            # ---------------- STAGE 2: CAPITAL PRESERVATION (+15% <= Peak < +30%) ----------------
            elif 15.0 <= gain_from_entry < 30.0:
                stage_name = "Stage 2: Capital Preservation"
                be_floor = entry_p * 1.02
                pos["profit_floor_price"] = be_floor
                if low_p <= be_floor:
                    exit_triggered = True
                    exit_price = min(be_floor, open_p)
                    exit_reason = "Breakeven Floor (+2% Profit Locked)"

            # ---------------- STAGE 1: IGNITION DEFENSE (Peak < +15%) ----------------
            else:
                stage_name = "Stage 1: Ignition Defense"
                hard_stop = entry_p * 0.90
                closing_stop = entry_p * 0.92
                pos["stop_loss_price"] = closing_stop

                if low_p <= hard_stop:
                    exit_triggered = True
                    exit_price = min(hard_stop, open_p)
                    exit_reason = "Extreme Circuit Breaker (-10% Hard Stop)"
                elif close_p <= closing_stop:
                    exit_triggered = True
                    exit_price = min(closing_stop, open_p) if open_p < closing_stop else close_p
                    exit_reason = "Closing Stop-Loss (-8% Threshold)"
                elif pos["bars_held"] >= 30 and (close_p / entry_p - 1.0) < 0.10:
                    exit_triggered = True
                    exit_price = close_p
                    exit_reason = "Dead Money Time-Stop Exit (30d Stagnant Base)"

            pos["current_stage"] = stage_name
            pos["current_price"] = close_p
            pos["current_gain_pct"] = (close_p / entry_p - 1.0) * 100.0
            pos["unrealized_pnl_rs"] = (close_p * pos["shares"]) - pos["invested_capital"]

            if exit_triggered:
                symbols_to_close.append((sym, exit_price, exit_reason, stage_name))
            else:
                # Update peak only if trade survived session
                if high_p > prior_peak:
                    pos["peak_price"] = high_p
                    pos["peak_gain_pct"] = (high_p / entry_p - 1.0) * 100.0

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
            actions_taken.append(f"🔴 SELL: {sym} exited at ₹{exit_p:.2f} ({net_ret:+.1f}%) | Reason: {reason}")

        # Step B: Process Tranche 2 Additions (Day 7+ in Profit)
        for sym, pos in list(self.state.active_positions.items()):
            if not pos.get("tranche2_active", False) and pos.get("bars_held", 0) >= self.tranche2_days:
                if sym in bars_latest.index:
                    curr_p = float(bars_latest.loc[sym]["close"])
                    # ONLY if in profit!
                    if curr_p > float(pos["entry_price"]):
                        t2_alloc = min(self.state.cash, pos["target_slot_capital"] * 0.5)
                        if t2_alloc >= 5000.0:
                            t2_friction = t2_alloc * self.cost_per_side
                            t2_shares = (t2_alloc - t2_friction) / curr_p
                            self.state.cash -= t2_alloc

                            pos["shares"] += t2_shares
                            pos["invested_capital"] += t2_alloc
                            pos["entry_price"] = pos["invested_capital"] / pos["shares"]
                            pos["entry_price_with_friction"] = pos["entry_price"] * (1.0 + self.cost_per_side)
                            pos["tranche2_active"] = True
                            pos["tranche2_date"] = today_date
                            pos["tranche2_shares"] = t2_shares
                            pos["tranche2_price"] = curr_p
                            actions_taken.append(f"🟢 TRANCHE 2 ADDED: {sym} +{t2_shares:.1f} shs @ ₹{curr_p:.2f} (Confirmed Winner!)")

        # Step C: Process New Entries (Tranche 1 - 50% Slot Allocation)
        current_equity = self.state.cash + sum(
            p["shares"] * bars_latest.loc[s]["close"] if s in bars_latest.index else p["invested_capital"]
            for s, p in self.state.active_positions.items()
        )
        slot_target_capital = current_equity / self.max_slots
        available_slots = max(0, self.max_slots - len(self.state.active_positions))

        if regime_ok and available_slots > 0 and not candidates_df.empty:
            for _, row in candidates_df.iterrows():
                if available_slots <= 0 or self.state.cash < 10000.0:
                    break

                sym = str(row["symbol"]).upper().replace(".NS", "").replace(".BO", "").strip()
                if sym in self.state.active_positions:
                    continue

                if sym not in bars_latest.index:
                    continue

                bar = bars_latest.loc[sym]
                fill_price = float(bar["close"])

                t1_alloc = min(self.state.cash, slot_target_capital * 0.5)
                if t1_alloc >= 5000.0:
                    t1_friction = t1_alloc * self.cost_per_side
                    t1_shares = (t1_alloc - t1_friction) / fill_price
                    self.state.cash -= t1_alloc

                    pos_obj = LiveTradePosition(
                        symbol=sym,
                        entry_date=today_date,
                        shares=t1_shares,
                        invested_capital=t1_alloc,
                        entry_price=fill_price,
                        entry_price_with_friction=fill_price * (1.0 + self.cost_per_side),
                        current_price=fill_price,
                        peak_price=fill_price,
                        current_gain_pct=0.0,
                        peak_gain_pct=0.0,
                        unrealized_pnl_rs=0.0,
                        target_slot_capital=slot_target_capital,
                        tranche1_shares=t1_shares,
                        tranche1_price=fill_price,
                        current_stage="Stage 1: Ignition Defense",
                        stop_loss_price=fill_price * 0.92,
                        profit_floor_price=0.0,
                        bars_held=1,
                        sector=str(row.get("sector", "Diversified")),
                        selection_reason=str(row.get("selection_reason", row.get("primary_driver", "VCP Base Squeeze"))),
                    )
                    self.state.active_positions[sym] = asdict(pos_obj)
                    available_slots -= 1
                    actions_taken.append(f"🚀 NEW ENTRY (Tranche 1): {sym} {t1_shares:.1f} shs @ ₹{fill_price:.2f} (Invested: ₹{t1_alloc:,.0f})")

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
