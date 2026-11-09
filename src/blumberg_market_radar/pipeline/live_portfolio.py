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
   - Stage 4: Secular Multibagger Floor (+25% Profit Locked & 100 EMA) at +50% Peak
   - Stage 5: Climax Harvesting (25% Trailing Drawdown from Peak) at +100%+ Peak
5. Persistent JSON Ledger storage (data/live_portfolio_state.json).
"""
from __future__ import annotations

import json
import os
import shutil
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
    pending_exits: list[dict] = field(default_factory=list)  # exit orders queued at EOD to fill at NEXT session open
    corporate_action_entitlements: list[dict] = field(default_factory=list)  # unlisted/pending spin-offs from demergers
    resolved_corporate_action_events: list[str] = field(default_factory=list)  # unique corporate action event IDs already processed


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
        regime_mode: str = "AND",  # Default strict "AND" (Close > 50 AND > 200 EMA); "OR" and "AND_TREND" optional
        assumed_gtt_stops: bool = False,  # False = stops detected at EOD queue to next open (realistic, no broker GTT assumed)
    ):
        self.state_path = Path(state_path)
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.initial_capital = float(initial_capital)
        self.max_slots = max_slots
        self.tranche2_days = tranche2_days
        self.cost_per_side = (slippage_bps + statutory_bps) / 10_000.0
        self.max_pct_of_adv = max_pct_of_adv
        self.assumed_gtt_stops = assumed_gtt_stops
        self.regime_mode = str(regime_mode).upper()
        if self.regime_mode not in ("OR", "AND", "AND_TREND"):
            raise ValueError(f"Invalid regime_mode {regime_mode!r}; expected OR, AND or AND_TREND")
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

                if not isinstance(data, dict):
                    raise ValueError(f"State root must be a dict, got {type(data).__name__}")

                # Schema validation for all persisted list fields and nested item structures
                for list_field in (
                    "closed_trades",
                    "daily_equity_history",
                    "pending_entries",
                    "pending_exits",
                    "corporate_action_entitlements",
                    "resolved_corporate_action_events",
                ):
                    val = data.get(list_field, [])
                    if not isinstance(val, list):
                        raise ValueError(f"Field {list_field!r} must be a list, got {type(val).__name__}")
                    if list_field != "resolved_corporate_action_events":
                        for idx, item in enumerate(val):
                            if not isinstance(item, dict):
                                raise ValueError(f"Item {idx} in {list_field!r} must be a dict, got {type(item).__name__}")
                    else:
                        for idx, item in enumerate(val):
                            if not isinstance(item, str):
                                raise ValueError(f"Item {idx} in {list_field!r} must be a str, got {type(item).__name__}")

                # Deep validation of nested list items to prevent NoneType / partial corruptions
                for idx, ct in enumerate(data.get("closed_trades", [])):
                    if not isinstance(ct.get("symbol"), str) or not ct.get("symbol"):
                        raise ValueError(f"closed_trades[{idx}] missing valid 'symbol'")
                    if not isinstance(ct.get("net_pnl_rs"), (int, float)) or not np.isfinite(ct.get("net_pnl_rs")):
                        raise ValueError(f"closed_trades[{idx}] missing finite 'net_pnl_rs'")

                for idx, eh in enumerate(data.get("daily_equity_history", [])):
                    if not isinstance(eh.get("date"), str) or not eh.get("date"):
                        raise ValueError(f"daily_equity_history[{idx}] missing valid 'date'")
                    if not isinstance(eh.get("total_equity"), (int, float)) or not np.isfinite(eh.get("total_equity")):
                        raise ValueError(f"daily_equity_history[{idx}] missing finite 'total_equity'")

                for idx, pe in enumerate(data.get("pending_entries", [])):
                    if not isinstance(pe.get("symbol"), str) or not pe.get("symbol"):
                        raise ValueError(f"pending_entries[{idx}] missing valid 'symbol'")

                for idx, px in enumerate(data.get("pending_exits", [])):
                    if not isinstance(px.get("symbol"), str) or not px.get("symbol"):
                        raise ValueError(f"pending_exits[{idx}] missing valid 'symbol'")

                for idx, ent in enumerate(data.get("corporate_action_entitlements", [])):
                    if not isinstance(ent.get("parent_symbol"), str) or not ent.get("parent_symbol"):
                        raise ValueError(f"corporate_action_entitlements[{idx}] missing valid 'parent_symbol'")
                    if not isinstance(ent.get("allocated_capital"), (int, float)) or not np.isfinite(ent.get("allocated_capital")):
                        raise ValueError(f"corporate_action_entitlements[{idx}] missing finite 'allocated_capital'")

                active_pos = data.get("active_positions", {})
                if not isinstance(active_pos, dict):
                    raise ValueError(f"active_positions must be a dict, got {type(active_pos).__name__}")
                for sym_key, pos_val in active_pos.items():
                    if not isinstance(pos_val, dict):
                        raise ValueError(f"active_positions[{sym_key!r}] must be a dict, got {type(pos_val).__name__}")
                    for req_f in ("shares", "entry_price", "invested_capital"):
                        if req_f not in pos_val or not isinstance(pos_val[req_f], (int, float)) or not np.isfinite(pos_val[req_f]):
                            raise ValueError(f"active_positions[{sym_key!r}] missing finite '{req_f}'")

                cash_val = data.get("cash", self.initial_capital)
                if not (isinstance(cash_val, (int, float)) and np.isfinite(cash_val) and cash_val >= 0.0):
                    raise ValueError(f"cash must be a finite non-negative number, got {cash_val!r}")

                return LivePortfolioState(
                    initial_capital=float(data.get("initial_capital", self.initial_capital)),
                    cash=float(cash_val),
                    active_positions=active_pos,
                    closed_trades=data.get("closed_trades", []),
                    daily_equity_history=data.get("daily_equity_history", []),
                    last_rebalance_date=data.get("last_rebalance_date", ""),
                    created_at=data.get("created_at", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
                    pending_entries=data.get("pending_entries", []),
                    pending_exits=data.get("pending_exits", []),
                    corporate_action_entitlements=data.get("corporate_action_entitlements", []),
                    resolved_corporate_action_events=data.get("resolved_corporate_action_events", []),
                )
            except Exception as exc:
                bak_path = self.state_path.with_name(
                    f"{self.state_path.name}.corrupt.bak.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                )
                try:
                    shutil.copy2(self.state_path, bak_path)
                    logger.error(f"State file {self.state_path} corrupted: {exc}. Backed up to {bak_path}")
                except Exception as b_exc:
                    logger.error(f"Failed to backup corrupt state: {b_exc}")
                raise RuntimeError(
                    f"Portfolio state file {self.state_path} is corrupted ({exc}). "
                    f"Backed up to {bak_path}. Aborting to prevent silent state wipe."
                ) from exc

        today_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        fresh = LivePortfolioState(
            initial_capital=self.initial_capital,
            cash=self.initial_capital,
            active_positions={},
            closed_trades=[],
            daily_equity_history=[],
            last_rebalance_date="",
            created_at=today_str,
            corporate_action_entitlements=[],
            resolved_corporate_action_events=[],
        )
        self.save_state(fresh)
        return fresh

    def save_state(self, state: LivePortfolioState | None = None) -> None:
        """Save portfolio state to JSON atomically."""
        target = state or self.state
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.state_path.with_name(f"{self.state_path.name}.tmp.{os.getpid()}")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(asdict(target), f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, self.state_path)

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

    def resolve_corporate_action(
        self,
        symbol: str,
        split_ratio: float,
        cost_basis_factor: float = 1.0,
        spinoff_market_value: float | None = None,
        event_id: str = "",
    ) -> dict:
        """Manually resolve a corporate action (split, bonus, or demerger) for a quarantined position.

        Parameters
        ----------
        symbol : str
            The equity ticker (e.g. 'VEDL' or 'DIXON').
        split_ratio : float
            Multiplier for share quantity (e.g., 2.0 for 2:1 split; 1.5 for 3:2 bonus).
            Must be a positive finite float (> 0).
        cost_basis_factor : float
            Adjustment factor for invested capital / cost basis (e.g., 1.0 for pure split/bonus;
            0.80 if 20% value separated in a demerger). Must be positive finite float (> 0).
        spinoff_market_value : float | None, optional
            Independent verified fair market value of the carved-out spin-off entitlement.
            If None, defaults to the proportional market value (old_mtm * (1 - cost_basis_factor)).
        event_id : str | None, optional
            Unique corporate action event identifier for idempotency.

        Returns
        -------
        dict
            Adjustment audit summary containing old and new position values.
        """
        sym = str(symbol).upper().replace(".NS", "").replace(".BO", "").strip()
        if sym not in self.state.active_positions:
            raise KeyError(f"Symbol {sym!r} is not currently an active position in portfolio.")

        if not (isinstance(split_ratio, (int, float)) and np.isfinite(split_ratio) and split_ratio > 0):
            raise ValueError(f"Invalid split_ratio {split_ratio!r}; must be a positive finite number.")
        if not (isinstance(cost_basis_factor, (int, float)) and np.isfinite(cost_basis_factor) and cost_basis_factor > 0):
            raise ValueError(f"Invalid cost_basis_factor {cost_basis_factor!r}; must be a positive finite number.")
        if spinoff_market_value is not None:
            if not (isinstance(spinoff_market_value, (int, float)) and np.isfinite(spinoff_market_value) and spinoff_market_value >= 0.0):
                raise ValueError(f"Invalid spinoff_market_value {spinoff_market_value!r}; must be a non-negative finite number.")

        if not (isinstance(event_id, str) and event_id.strip()):
            raise ValueError("event_id must be a non-empty string uniquely identifying this corporate action event.")
        event_id = event_id.strip()

        if event_id in self.state.resolved_corporate_action_events:
            raise ValueError(f"Corporate action event {event_id!r} has already been resolved for this portfolio.")

        pos = self.state.active_positions[sym]
        if not pos.get("is_quarantined", False):
            raise RuntimeError(
                f"Position {sym} is not currently quarantined. Cannot apply corporate action resolution to an unquarantined position."
            )

        split_ratio = float(split_ratio)
        cost_basis_factor = float(cost_basis_factor)

        old_shares = float(pos["shares"])
        old_entry_price = float(pos["entry_price"])
        old_invested_cap = float(pos["invested_capital"])
        old_current_price = float(pos.get("current_price", old_entry_price))

        # 1. Scale shares up by split_ratio
        new_shares = old_shares * split_ratio
        pos["shares"] = new_shares

        # 2. Adjust entry price per share: old_price * cost_basis_factor / split_ratio
        price_adj_multiplier = cost_basis_factor / split_ratio
        pos["entry_price"] = old_entry_price * price_adj_multiplier
        if "entry_price_with_friction" in pos:
            pos["entry_price_with_friction"] = float(pos["entry_price_with_friction"]) * price_adj_multiplier

        # 3. Adjust tranche-specific details if present
        if "tranche1_shares" in pos and pos["tranche1_shares"]:
            pos["tranche1_shares"] = float(pos["tranche1_shares"]) * split_ratio
        if "tranche1_price" in pos and pos["tranche1_price"]:
            pos["tranche1_price"] = float(pos["tranche1_price"]) * price_adj_multiplier
        if "tranche2_shares" in pos and pos["tranche2_shares"]:
            pos["tranche2_shares"] = float(pos["tranche2_shares"]) * split_ratio
        if "tranche2_price" in pos and pos["tranche2_price"]:
            pos["tranche2_price"] = float(pos["tranche2_price"]) * price_adj_multiplier

        # 4. Scale peak price, profit floor, stop loss, and current price
        if "peak_price" in pos and pos["peak_price"]:
            pos["peak_price"] = float(pos["peak_price"]) * price_adj_multiplier
        if "profit_floor_price" in pos and pos["profit_floor_price"]:
            pos["profit_floor_price"] = float(pos["profit_floor_price"]) * price_adj_multiplier
        if "stop_loss_price" in pos and pos["stop_loss_price"]:
            pos["stop_loss_price"] = float(pos["stop_loss_price"]) * price_adj_multiplier
        if "current_price" in pos and pos["current_price"]:
            pos["current_price"] = float(pos["current_price"]) * price_adj_multiplier

        # 5. Invested capital scales by cost_basis_factor; for demergers, track carved-out spin-off entitlement
        carved_out_mtm = 0.0
        if cost_basis_factor < 1.0:
            carved_out_cap = old_invested_cap * (1.0 - cost_basis_factor)
            carved_out_mtm = (
                float(spinoff_market_value)
                if spinoff_market_value is not None
                else (old_shares * old_current_price) * (1.0 - cost_basis_factor)
            )
            self.state.corporate_action_entitlements.append({
                "event_id": event_id,
                "parent_symbol": sym,
                "entitlement_type": "SPIN_OFF",
                "allocated_capital": carved_out_cap,
                "market_value": carved_out_mtm,
                "created_date": datetime.now().strftime("%Y-%m-%d"),
                "status": "Awaiting Listing / Credit",
                "description": f"Spin-off entitlement from {sym} demerger ({(1.0 - cost_basis_factor)*100:.1f}% cost basis)",
            })
        new_invested_cap = old_invested_cap * cost_basis_factor
        pos["invested_capital"] = new_invested_cap

        # Track event_id at state level to prevent duplicate application even after re-quarantine
        if event_id not in self.state.resolved_corporate_action_events:
            self.state.resolved_corporate_action_events.append(event_id)

        # Record audit resolution on position
        if "resolved_corporate_actions" not in pos:
            pos["resolved_corporate_actions"] = []
        pos["resolved_corporate_actions"].append({
            "event_id": event_id,
            "split_ratio": split_ratio,
            "cost_basis_factor": cost_basis_factor,
            "spinoff_market_value": carved_out_mtm if cost_basis_factor < 1.0 else 0.0,
            "resolved_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "old_shares": old_shares,
            "new_shares": new_shares,
            "old_invested_capital": old_invested_cap,
            "new_invested_capital": new_invested_cap,
        })

        # 6. Clear quarantine flags and reset anomaly counter
        pos["is_quarantined"] = False
        pos["anomaly_days"] = 0
        pos["current_stage"] = "Stage 1: Ignition Defense"

        # 7. Remove any queued quarantine timeout exit orders
        self.state.pending_exits = [
            pe for pe in self.state.pending_exits
            if not (pe.get("symbol") == sym and "QUARANTINE" in pe.get("exit_reason", ""))
        ]

        # 8. Persist atomically
        self.save_state()

        logger.info(
            f"Resolved corporate action for {sym}: shares {old_shares:.1f} -> {new_shares:.1f}, "
            f"entry Rs {old_entry_price:.2f} -> Rs {pos['entry_price']:.2f}, "
            f"invested Rs {old_invested_cap:.2f} -> Rs {new_invested_cap:.2f}."
        )

        return {
            "symbol": sym,
            "old_shares": old_shares,
            "new_shares": new_shares,
            "old_entry_price": old_entry_price,
            "new_entry_price": pos["entry_price"],
            "old_invested_capital": old_invested_cap,
            "new_invested_capital": new_invested_cap,
            "split_ratio": split_ratio,
            "cost_basis_factor": cost_basis_factor,
            "is_quarantined": False,
        }

    def settle_corporate_action_entitlement(
        self,
        parent_symbol: str | None = None,
        realized_cash: float = 0.0,
        event_id: str | None = None,
    ) -> dict:
        """Settle a pending corporate action entitlement when spin-off proceeds are realized.

        Parameters
        ----------
        parent_symbol : str | None, optional
            The equity ticker (e.g. 'VEDL' or 'DIXON').
        realized_cash : float
            Actual verified cash proceeds received from liquidation/dividend/credit.
            Must be a non-negative, finite float (>= 0.0).
        event_id : str | None, optional
            The specific unique corporate action event identifier.
            Required if multiple unsettled entitlements exist for the same parent symbol.

        Returns
        -------
        dict
            The updated entitlement record with status 'Settled'.
        """
        if event_id is None and parent_symbol is None:
            raise ValueError("Must provide either event_id or parent_symbol to settle corporate action entitlement.")

        if not (isinstance(realized_cash, (int, float)) and np.isfinite(realized_cash) and realized_cash >= 0.0):
            raise ValueError(f"realized_cash must be a finite non-negative number, got {realized_cash!r}")

        matched = []
        if event_id:
            matched = [e for e in self.state.corporate_action_entitlements if e.get("event_id") == event_id and e.get("status") != "Settled"]
            if not matched:
                raise KeyError(f"No active corporate action entitlement found for event_id {event_id!r}")
            ent = matched[0]
        else:
            sym = str(parent_symbol).upper().replace(".NS", "").replace(".BO", "").strip()
            matched = [e for e in self.state.corporate_action_entitlements if e.get("parent_symbol") == sym and e.get("status") != "Settled"]
            if not matched:
                raise KeyError(f"No active corporate action entitlement found for symbol {sym!r}")
            if len(matched) > 1:
                active_events = [e.get("event_id") for e in matched]
                raise ValueError(
                    f"Multiple active entitlements exist for {sym!r} ({active_events}). "
                    "Must specify event_id to settle unambiguously."
                )
            ent = matched[0]
        ent["status"] = "Settled"
        ent["settled_date"] = datetime.now().strftime("%Y-%m-%d")
        cash_added = float(realized_cash)
        ent["realized_cash"] = cash_added
        self.state.cash += cash_added
        self.save_state()
        return ent

    def get_summary(self, latest_prices: dict[str, float] | None = None) -> dict:
        """Compute live portfolio metrics."""
        prices = latest_prices or {}
        mtm_positions = 0.0

        for sym, pos_dict in self.state.active_positions.items():
            curr_p = prices.get(sym, pos_dict.get("current_price", pos_dict.get("entry_price", 0.0)))
            shares = pos_dict.get("shares", 0.0)
            mtm_positions += shares * curr_p

        entitlements_mtm = sum(
            float(e.get("market_value", e.get("allocated_capital", 0.0)))
            for e in self.state.corporate_action_entitlements
            if e.get("status") != "Settled"
        )
        entitlements_cost = sum(
            float(e.get("allocated_capital", 0.0))
            for e in self.state.corporate_action_entitlements
            if e.get("status") != "Settled"
        )
        settled_entitlement_pnl = sum(
            float(e.get("realized_cash", 0.0)) - float(e.get("allocated_capital", 0.0))
            for e in self.state.corporate_action_entitlements
            if e.get("status") == "Settled"
        )
        total_equity = self.state.cash + mtm_positions + entitlements_mtm
        invested = sum(p.get("invested_capital", 0.0) for p in self.state.active_positions.values()) + entitlements_cost
        unrealized_pnl = (mtm_positions + entitlements_mtm) - invested
        realized_pnl = sum(c.get("net_pnl_rs", 0.0) for c in self.state.closed_trades) + settled_entitlement_pnl
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
            "corporate_action_entitlements_val": entitlements_mtm,
            "unrealized_pnl_rs": unrealized_pnl,
            "unrealized_pnl_pct": (unrealized_pnl / invested * 100.0) if invested > 0 else 0.0,
            "realized_pnl_rs": realized_pnl,
            "total_pnl_rs": total_pnl,
            "total_return_pct": total_return_pct,
            "active_positions_count": len(self.state.active_positions),
            "pending_exits_count": len(self.state.pending_exits),
            "pending_entries_count": len(self.state.pending_entries),
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

        # 1. Benchmark Regime Check (Strictly fail-closed, strictly causal, no lookahead, no stale data)
        regime_ok = True
        if enforce_regime:
            if bench_df is None or bench_df.empty or "date" not in bench_df.columns or "close" not in bench_df.columns:
                regime_ok = False
                logger.warning("Benchmark data missing or invalid: regime set to fail-closed (regime_ok=False)")
            else:
                # 1. Strictly causal: filter benchmark bars up to today_date (prevents lookahead from future benchmark data)
                bench_proc = bench_df.copy()
                bench_proc["_date_str"] = pd.to_datetime(bench_proc["date"]).dt.strftime("%Y-%m-%d")
                bench_causal = bench_proc[bench_proc["_date_str"] <= today_date].sort_values("date").reset_index(drop=True)

                if len(bench_causal) < 200:
                    regime_ok = False
                    logger.warning(
                        f"Benchmark has only {len(bench_causal)} causal bars up to {today_date} (<200): "
                        "regime set to fail-closed (regime_ok=False)"
                    )
                else:
                    # 2. Staleness check: benchmark must not be disconnected/stale (>7 calendar days gap)
                    latest_bench_dt = pd.to_datetime(bench_causal["date"].iloc[-1]).tz_localize(None) if pd.to_datetime(bench_causal["date"].iloc[-1]).tzinfo else pd.to_datetime(bench_causal["date"].iloc[-1])
                    curr_dt = pd.to_datetime(today_date)
                    gap_days = (curr_dt - latest_bench_dt).days
                    if gap_days > 7:
                        regime_ok = False
                        logger.warning(
                            f"Benchmark data is stale ({gap_days} calendar days old, latest bar: {latest_bench_dt.strftime('%Y-%m-%d')}): "
                            "regime set to fail-closed (regime_ok=False)"
                        )
                    else:
                        bench_close = float(bench_causal["close"].iloc[-1])
                        bench_ema50 = float(bench_causal["close"].ewm(span=50, adjust=False).mean().iloc[-1])
                        bench_ema200 = float(bench_causal["close"].ewm(span=200, adjust=False).mean().iloc[-1])
                        if self.regime_mode == "AND":
                            regime_ok = bool((bench_close > bench_ema50) and (bench_close > bench_ema200))
                        elif self.regime_mode == "AND_TREND":
                            regime_ok = bool((bench_close > bench_ema50) and (bench_close > bench_ema200) and (bench_ema50 > bench_ema200))
                        else:
                            regime_ok = bool((bench_close > bench_ema50) or (bench_close > bench_ema200))

        # Accrue daily cash yield (Only once per calendar day)
        if not is_same_day_rerun:
            daily_yield_rs = self.state.cash * self.cash_yield_daily
            self.state.cash += daily_yield_rs

        # Ensure 14-day True Range ATR is computed across historical bars for accurate dynamic stops
        # Strictly causal: filter bars up to today_date to prevent future bars leaking into bars_latest or MTM
        bars_df_causal = bars_df.copy()
        if "date" in bars_df_causal.columns:
            bars_df_causal["_date_str"] = pd.to_datetime(bars_df_causal["date"]).dt.strftime("%Y-%m-%d")
            bars_df_causal = bars_df_causal[bars_df_causal["_date_str"] <= today_date].drop(columns=["_date_str"])
        bars_proc = bars_df_causal.sort_values(["symbol", "date"]).copy()
        if "atr_14" not in bars_proc.columns and "high" in bars_proc.columns and "low" in bars_proc.columns:
            prev_close = bars_proc.groupby("symbol")["close"].shift(1)
            tr1 = bars_proc["high"] - bars_proc["low"]
            tr2 = (bars_proc["high"] - prev_close).abs()
            tr3 = (bars_proc["low"] - prev_close).abs()
            bars_proc["tr"] = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            bars_proc["atr_14"] = bars_proc.groupby("symbol")["tr"].transform(
                lambda s: s.rolling(14, min_periods=7).mean()
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

        def _is_corporate_action_anomaly(bar_, position: dict, at_open: bool = False) -> bool:
            entry = float(position.get("entry_price", 0.0))
            peak = float(position.get("peak_price", entry))
            previous_price = position.get("current_price")

            if at_open:
                # Time-causal at 9:15 AM Open:
                # NEVER inspect the EOD 'is_corporate_anomaly' tag which is computed from full-day close!
                # Only use pre-market corporate announcements, existing quarantine, or open-price gap down.
                premarket_announced = bool(bar_.get("corporate_action_announced", False))
                open_p = float(bar_["open"])
                return bool(
                    position.get("is_quarantined", False)
                    or premarket_announced
                    or (entry > 0 and open_p <= entry * 0.65 and peak >= entry * 0.95)
                    or (
                        previous_price is not None
                        and float(previous_price) > 0
                        and (open_p / float(previous_price) - 1.0) <= -0.35
                    )
                )
            else:
                # EOD Close (Step A): Full-day OHLC and EOD anomaly tags are final and known
                tag = bar_.get("is_corporate_anomaly", False)
                tagged = pd.notna(tag) and bool(tag)
                low_p = float(bar_["low"])
                close_p = float(bar_["close"])
                return bool(
                    position.get("is_quarantined", False)
                    or tagged
                    or (entry > 0 and low_p <= entry * 0.65 and peak >= entry * 0.95)
                    or (
                        previous_price is not None
                        and float(previous_price) > 0
                        and (min(low_p, close_p) / float(previous_price) - 1.0) <= -0.35
                    )
                )

        # Step 0: Fill orders queued yesterday at TODAY'S OPEN (identical to backtest: signal at close D, fill at open D+1).
        # Rule: Entries & Tranches at morning open can ONLY use cash & slots available from yesterday's close.
        # Exit proceeds from today's trades are NOT available immediately (T+1 settlement / prevents same-morning recycling).
        cash_avail_at_open = float(self.state.cash)
        slots_avail_at_open = max(0, self.max_slots - len(self.state.active_positions))

        fills_today: set[str] = set()
        if not is_same_day_rerun:
            # 00. Pending Exits queued at previous session's close fill at TODAY'S OPEN
            if self.state.pending_exits:
                remaining_pending_exits = []
                for pe in self.state.pending_exits:
                    psym = pe["symbol"]
                    pos = self.state.active_positions.get(psym)
                    if pos is None:
                        continue
                    b = _bar_today(psym)
                    if b is None:
                        pe["attempt_count"] = pe.get("attempt_count", 0) + 1
                        remaining_pending_exits.append(pe)
                        actions_taken.append(f"⚠️ PENDING EXIT HELD: {psym} had no session bar today. Retrying next session.")
                        continue

                    if "QUARANTINE_TIMEOUT" not in pe.get("exit_reason", "") and _is_corporate_action_anomaly(b, pos, at_open=True):
                        pos["is_quarantined"] = True
                        pos["current_stage"] = "Corporate Action Quarantine"
                        pos["tranche2_eligible"] = False
                        if not is_same_day_rerun:
                            pos["anomaly_days"] = int(pos.get("anomaly_days", 0)) + 1
                        actions_taken.append(
                            f"⚠️ PENDING EXIT CANCELLED: {psym} quarantined due to corporate action anomaly. Automated exit halted."
                        )
                        continue

                    open_p = float(b["open"])
                    low_p = float(b["low"])
                    high_p = float(b["high"])
                    close_p = float(b["close"])
                    prev_c = float(b["prev_close"]) if "prev_close" in b and pd.notna(b["prev_close"]) else float(pos.get("current_price", open_p))
                    
                    # Lower circuit check at open:
                    # An exit order cannot execute if stock is locked limit-down without liquidity at market open.
                    # Supports explicit exchange metadata (is_lower_circuit, circuit_limit_pct) and detects
                    # open-at-floor locks across all exchange circuit bands (2% ESM/T2T, 5%, 10%, 20%) without
                    # lookahead to intraday rebound highs or closes.
                    circuit_limit = float(b.get("circuit_limit_pct", 0.0))
                    drop_from_prev = (1.0 - open_p / prev_c) if (prev_c is not None and prev_c > 0) else 0.0

                    if circuit_limit > 0:
                        is_floor_lock = (open_p == low_p and open_p <= prev_c * (1.0 - circuit_limit + 1e-4))
                    else:
                        is_standard_band = any(abs(drop_from_prev - band) <= 0.005 for band in (0.02, 0.05, 0.10, 0.20))
                        is_floor_lock = (open_p == low_p and (is_standard_band or drop_from_prev >= 0.045))

                    is_lower_circuit = bool(
                        b.get("is_lower_circuit", False)
                        or is_floor_lock
                        or (open_p == low_p and high_p == low_p and prev_c is not None and close_p < prev_c)
                    )

                    if is_lower_circuit:
                        pe["attempt_count"] = pe.get("attempt_count", 0) + 1
                        remaining_pending_exits.append(pe)
                        actions_taken.append(f"⚠️ PENDING EXIT DEFERRED: {psym} locked in Lower Circuit at open ₹{open_p:.2f}. Retrying next session.")
                        continue

                    fill_price = open_p
                    shares = float(pos["shares"])
                    sell_friction = fill_price * shares * self.cost_per_side
                    net_proceeds = (fill_price * shares) - sell_friction
                    self.state.cash += net_proceeds  # Credited to cash ledger, but unavailable for same-morning rebuys

                    net_ret = (fill_price * (1.0 - self.cost_per_side) / pos["entry_price_with_friction"] - 1.0) * 100.0
                    net_pnl = net_proceeds - float(pos["invested_capital"])

                    closed_rec = ClosedTradeRecord(
                        symbol=psym,
                        entry_date=pos["entry_date"],
                        exit_date=today_date,
                        shares=shares,
                        entry_price=float(pos["entry_price"]),
                        exit_price=fill_price,
                        gross_return_pct=(fill_price / float(pos["entry_price"]) - 1.0) * 100.0,
                        net_return_pct=net_ret,
                        net_pnl_rs=net_pnl,
                        exit_reason=pe["exit_reason"],
                        stage_at_exit=pe.get("stage_at_signal", pos.get("current_stage", "")),
                        bars_held=int(pos.get("bars_held", 0)),
                        sector=str(pos.get("sector", "Diversified")),
                    )
                    self.state.closed_trades.append(asdict(closed_rec))
                    del self.state.active_positions[psym]
                    actions_taken.append(
                        f"🔴 EXIT FILLED (at Open): {psym} exited at open ₹{fill_price:.2f} ({net_ret:+.1f}%) | Reason: {pe['exit_reason']}"
                    )

                self.state.pending_exits = remaining_pending_exits

            # 0a. Tranche 2 (flagged eligible at yesterday's close) fills at today's open
            for sym, pos in list(self.state.active_positions.items()):
                if pos.get("is_quarantined", False):
                    continue
                if pos.get("tranche2_eligible") and not pos.get("tranche2_active", False):
                    pos["tranche2_eligible"] = False
                    b = _bar_today(sym)
                    if b is None:
                        continue
                    t2_open_p = float(b["open"])
                    t2_high_p = float(b["high"])
                    t2_low_p = float(b["low"])
                    t2_prev_c = float(b["prev_close"]) if "prev_close" in b and pd.notna(b["prev_close"]) else float(pos.get("current_price", t2_open_p))
                    t2_circuit_limit = float(b.get("circuit_limit_pct", 0.0))
                    t2_rise_from_prev = (t2_open_p / t2_prev_c - 1.0) if (t2_prev_c > 0) else 0.0

                    if t2_circuit_limit > 0:
                        is_t2_ceiling_lock = (t2_open_p == t2_high_p and t2_open_p >= t2_prev_c * (1.0 + t2_circuit_limit - 1e-4))
                    else:
                        is_t2_std_upper = any(abs(t2_rise_from_prev - band) <= 0.0025 for band in (0.02, 0.05, 0.10, 0.20))
                        is_t2_ceiling_lock = (t2_open_p == t2_high_p and (is_t2_std_upper or t2_rise_from_prev >= 0.045))

                    is_t2_upper_circuit = bool(
                        b.get("is_upper_circuit", False)
                        or (t2_high_p == t2_low_p and t2_open_p > t2_prev_c)
                        or is_t2_ceiling_lock
                    )
                    if is_t2_upper_circuit:
                        actions_taken.append(f"⚠️ TRANCHE 2 DEFERRED: {sym} locked at upper circuit ceiling at open (no sellers).")
                        continue

                    # FIX: Detect if today's open is an unadjusted corporate action gap-down!
                    if _is_corporate_action_anomaly(b, pos, at_open=True):
                        pos["is_quarantined"] = True
                        pos["current_stage"] = "Corporate Action Quarantine"
                        if not is_same_day_rerun:
                            pos["anomaly_days"] = int(pos.get("anomaly_days", 0)) + 1
                        actions_taken.append(
                            f"⚠️ TRANCHE 2 BLOCKED & QUARANTINED: {sym} opened with corporate action anomaly. Tranche 2 cancelled."
                        )
                        continue

                    raw_t2 = float(b["open"])
                    t2_alloc = min(cash_avail_at_open, pos["target_slot_capital"] * 0.5, _liq_cap(b))
                    if t2_alloc < 2500.0:
                        continue
                    t2_shares = (t2_alloc * (1.0 - self.cost_per_side)) / raw_t2
                    self.state.cash -= t2_alloc
                    cash_avail_at_open -= t2_alloc
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
                    actions_taken.append(f"🟢 TRANCHE 2 FILLED: {sym} +{t2_shares:.1f} shs @ open ₹{raw_t2:.2f} (Confirmed Winner)")

            # 0b. Tranche 1 entries queued yesterday (strictly uses cash and slots available before today's exits)
            queued = list(self.state.pending_entries)
            self.state.pending_entries = []
            if queued:
                entitlements_mtm = sum(
                    float(e.get("market_value", e.get("allocated_capital", 0.0)))
                    for e in self.state.corporate_action_entitlements
                    if e.get("status") != "Settled"
                )
                # Target slot cap is sized against true total portfolio ledger equity at open.
                # Cash spent on new orders remains strictly capped to cash_avail_at_open (T+1 freeze).
                total_ledger_equity_at_open = (
                    max(0.0, float(self.state.cash))
                    + sum(
                        float(p_["shares"]) * float(bars_latest.loc[s_]["open"]) if s_ in bars_latest.index else float(p_["invested_capital"])
                        for s_, p_ in self.state.active_positions.items()
                    )
                    + entitlements_mtm
                )
                slot_cap = total_ledger_equity_at_open / self.max_slots
                free_slots = min(slots_avail_at_open, max(0, self.max_slots - len(self.state.active_positions)))
                for q in queued:
                    qsym = q["symbol"]
                    if free_slots <= 0 or cash_avail_at_open < 2500.0:
                        dropped = [x["symbol"] for x in queued[queued.index(q):] if x["symbol"] not in self.state.active_positions]
                        actions_taken.append(
                            f"⚠️ QUEUED ORDERS DROPPED (no free slot/cash): {', '.join(dropped)}"
                        )
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

                    # Upper circuit ceiling rejection at open (cannot buy into zero-seller lockup)
                    open_p = float(b["open"])
                    high_p = float(b["high"])
                    low_p = float(b["low"])
                    prev_c = float(b["prev_close"]) if "prev_close" in b and pd.notna(b["prev_close"]) else open_p
                    circuit_limit = float(b.get("circuit_limit_pct", 0.0))
                    rise_from_prev = (open_p / prev_c - 1.0) if (prev_c > 0) else 0.0

                    if circuit_limit > 0:
                        is_ceiling_lock = (open_p == high_p and open_p >= prev_c * (1.0 + circuit_limit - 1e-4))
                    else:
                        is_std_upper = any(abs(rise_from_prev - band) <= 0.0025 for band in (0.02, 0.05, 0.10, 0.20))
                        is_ceiling_lock = (open_p == high_p and (is_std_upper or rise_from_prev >= 0.045))

                    is_upper_circuit = bool(
                        b.get("is_upper_circuit", False)
                        or (high_p == low_p and open_p > prev_c)
                        or is_ceiling_lock
                    )
                    if is_upper_circuit:
                        actions_taken.append(f"⛔ ORDER REJECTED: {qsym} locked at upper circuit ceiling at open, no entry")
                        continue
                    raw_entry = float(b["open"])
                    t1_alloc = min(cash_avail_at_open, slot_cap * 0.5, _liq_cap(b))
                    if t1_alloc < 2500.0:
                        continue
                    t1_shares = (t1_alloc * (1.0 - self.cost_per_side)) / raw_entry
                    self.state.cash -= t1_alloc
                    cash_avail_at_open -= t1_alloc
                    pos_obj = LiveTradePosition(
                        symbol=qsym, entry_date=today_date, shares=t1_shares, invested_capital=t1_alloc,
                        entry_price=raw_entry, entry_price_with_friction=raw_entry * (1.0 + self.cost_per_side),
                        current_price=raw_entry, peak_price=raw_entry,
                        current_gain_pct=0.0, peak_gain_pct=0.0, unrealized_pnl_rs=0.0,
                        target_slot_capital=slot_cap, tranche1_shares=t1_shares, tranche1_price=raw_entry,
                        current_stage="Stage 1: Ignition Defense", stop_loss_price=raw_entry * 0.92,
                        profit_floor_price=0.0, bars_held=0, sector=str(q.get("sector", "Diversified")),
                        selection_reason=str(q.get("selection_reason", "VCP Base Squeeze")),
                    )
                    self.state.active_positions[qsym] = asdict(pos_obj)
                    fills_today.add(qsym)
                    free_slots -= 1
                    slots_avail_at_open -= 1
                    actions_taken.append(f"🚀 ENTRY FILLED (Tranche 1): {qsym} {t1_shares:.1f} shs @ open ₹{raw_entry:.2f} (Invested: ₹{t1_alloc:,.0f})")

        # Step A: Evaluate Exits for Active Trades (positions opened this morning are not evaluated today, as in the engine)
        symbols_to_close = []
        for sym, pos in list(self.state.active_positions.items()):
            if sym in fills_today:
                continue
            if sym not in bars_latest.index:
                continue
            # Only evaluate exits on today's session bar; a stale bar must never trigger a sale
            if _bar_today(sym) is None:
                continue

            bar = bars_latest.loc[sym]
            close_p = float(bar["close"])
            open_p = float(bar["open"])
            low_p = float(bar["low"])
            high_p = float(bar["high"])

            # Same anchor as backtest: blended raw entry (friction-free) for milestones, stops and floors
            entry_p = float(pos["entry_price"])
            prev_recorded_price = pos.get("current_price")
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

            is_corp_action_anomaly = _is_corporate_action_anomaly(bar, pos, at_open=False)

            if is_corp_action_anomaly:
                pos["is_quarantined"] = True
                pos["tranche2_eligible"] = False
                stage_name = "Corporate Action Quarantine"
                if not is_same_day_rerun:
                    pos["anomaly_days"] = int(pos.get("anomaly_days", 0)) + 1

                # If unresolved for 3 trading sessions, queue QUARANTINE_TIMEOUT exit to prevent indefinite lockup
                if int(pos.get("anomaly_days", 0)) >= 3:
                    already_pending = any(pe["symbol"] == sym for pe in self.state.pending_exits)
                    if not already_pending and not is_same_day_rerun:
                        self.state.pending_exits.append({
                            "symbol": sym,
                            "signal_date": today_date,
                            "exit_reason": "QUARANTINE_TIMEOUT: Unresolved Corporate Action (>3 sessions)",
                            "stage_at_signal": "Corporate Action Quarantine",
                            "signal_price": close_p,
                            "shares": pos["shares"],
                            "attempt_count": 0,
                        })
                        pos["current_stage"] = "PENDING EXIT: QUARANTINE_TIMEOUT: Unresolved Corporate Action (>3 sessions)"
                        actions_taken.append(
                            f"🚨 QUARANTINE TIMEOUT: {sym} unresolved for {pos['anomaly_days']} sessions. "
                            "Exit queued to sell at next session open."
                        )
                else:
                    logger.warning(
                        f"Potential unadjusted corporate action / demerger anomaly in {sym}. "
                        "Quarantining position; automated liquidation halted."
                    )
                    actions_taken.append(
                        f"QUARANTINE / ALERT: {sym} may have an unadjusted corporate action. "
                        "Automated exits and additions are halted pending manual adjustment."
                    )
            else:
                # Tranche 2 eligibility (decided at today's close, filled at tomorrow's open).
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
                        exit_reason = f"Parabolic Climax Exit (-25% Trail from Peak ₹{prior_peak:.2f})"

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

                    if low_p <= hard_stop:
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
                    already_pending = any(pe["symbol"] == sym for pe in self.state.pending_exits)
                    if not already_pending and not is_same_day_rerun:
                        self.state.pending_exits.append({
                            "symbol": sym,
                            "signal_date": today_date,
                            "exit_reason": f"LOWER_CIRCUIT_DEFERRED: {exit_reason}",
                            "stage_at_signal": stage_name,
                            "signal_price": close_p,
                            "shares": pos["shares"],
                            "attempt_count": 1,
                        })
                    pos["current_stage"] = f"PENDING EXIT: LOWER_CIRCUIT_DEFERRED: {exit_reason}"
                    if not is_same_day_rerun:
                        pos["bars_held"] = pos.get("bars_held", 0) + 1
                    actions_taken.append(
                        f"⚠️ PENDING EXIT QUEUED: {sym} locked in Lower Circuit ({exit_reason}). "
                        "Exit queued to execute at first liquid session open."
                    )
                    if high_p > prior_peak:
                        pos["peak_price"] = high_p
                        pos["peak_gain_pct"] = (high_p / entry_p - 1.0) * 100.0
                else:
                    is_close_based = (
                        "Closing Stop" in exit_reason
                        or "Dead Money" in exit_reason
                        or "100 EMA Break" in exit_reason
                        or "50 EMA Locked" in exit_reason
                        or "Parabolic Climax" in exit_reason
                        or "Secular Trend Ended" in exit_reason
                        or "Unresolved >35% Drop" in exit_reason
                        or "QUARANTINE" in exit_reason
                        or "LOWER_CIRCUIT" in exit_reason
                    )
                    if is_close_based or not self.assumed_gtt_stops:
                        already_pending = any(pe["symbol"] == sym for pe in self.state.pending_exits)
                        if not already_pending and not is_same_day_rerun:
                            self.state.pending_exits.append({
                                "symbol": sym,
                                "signal_date": today_date,
                                "exit_reason": exit_reason,
                                "stage_at_signal": stage_name,
                                "signal_price": close_p,
                                "shares": pos["shares"],
                                "attempt_count": 0,
                            })
                            pos["current_stage"] = f"PENDING EXIT: {exit_reason}"
                            actions_taken.append(
                                f"📋 EXIT SIGNAL QUEUED: {sym} ({exit_reason}) -> queued to sell at next session open"
                            )
                    else:
                        symbols_to_close.append((sym, exit_price, exit_reason + " [Broker GTT Assumed]", stage_name))
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
            actions_taken.append(f"🔴 SELL: {sym} exited at ₹{exit_p:.2f} ({net_ret:+.1f}%) | Reason: {reason}")

        # Update peak price for newly entered positions that survived today's session (causal EOD update)
        for sym in fills_today:
            if sym in self.state.active_positions:
                b_sym = _bar_today(sym)
                if b_sym is not None:
                    h_sym = float(b_sym["high"])
                    p_rec = self.state.active_positions[sym]
                    if h_sym > p_rec["peak_price"]:
                        p_rec["peak_price"] = h_sym
                        p_rec["peak_gain_pct"] = (h_sym / p_rec["entry_price"] - 1.0) * 100.0

        # Step C: Queue new signals. They are FILLED at tomorrow's open (never at the signal-day close,
        # which is unattainable and not what the backtest assumes).
        available_slots = max(0, self.max_slots - len(self.state.active_positions) - len(self.state.pending_entries))
        queued_syms = {q["symbol"] for q in self.state.pending_entries}
        if (not is_same_day_rerun) and regime_ok and available_slots > 0 and candidates_df is not None and not candidates_df.empty:
            for _, row in candidates_df.iterrows():
                if available_slots <= 0:
                    break
                sym = str(row["symbol"]).upper().replace(".NS", "").replace(".BO", "").strip()
                if sym in self.state.active_positions or sym in queued_syms or _bar_today(sym) is None:
                    continue  # no bar today -> stale signal, never queue
                if bool(row.get("is_corporate_anomaly", False)) or any(p.get("is_quarantined") for s, p in self.state.active_positions.items() if s == sym):
                    actions_taken.append(f"⛔ CANDIDATE BLOCKED: {sym} has unadjusted corporate action anomaly")
                    continue
                self.state.pending_entries.append({
                    "symbol": sym,
                    "signal_date": today_date,
                    "sector": str(row.get("sector", "Diversified")),
                    "selection_reason": str(row.get("selection_reason", row.get("primary_driver", "VCP Base Squeeze"))),
                })
                queued_syms.add(sym)
                available_slots -= 1
                actions_taken.append(f"📝 BUY ORDER QUEUED: {sym} (fills at next session open)")

        # Step D: Final Mark to Market & Save
        final_summary = self.get_summary(bars_latest["close"].to_dict())
        self.state.last_rebalance_date = today_date
        equity_record = {
            "date": today_date,
            "total_equity": final_summary["total_equity"],
            "cash": final_summary["cash"],
            "invested": final_summary["invested_capital"],
            "active_slots": final_summary["active_positions_count"],
        }
        if self.state.daily_equity_history and self.state.daily_equity_history[-1].get("date") == today_date:
            self.state.daily_equity_history[-1] = equity_record
        else:
            self.state.daily_equity_history.append(equity_record)
        self.save_state()

        return {
            "date": today_date,
            "regime_ok": regime_ok,
            "actions_taken": actions_taken,
            "summary": final_summary,
        }
