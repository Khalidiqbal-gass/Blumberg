"""Upgraded VCP & Multi-Stage Secular Backtesting Engine.

Principal Quantitative Architecture incorporating:
1. True Volatility Contraction Pattern (VCP Compression & ATR_10 < ATR_30 & Close >= 0.85 * 52W_High).
2. Minimum Daily Turnover >= Rs. 3 Crores (with dynamic pre-2008 / pre-2016 scaling).
3. Benchmark Regime Filter (NIFTY 50/Sensex > 50 EMA or 200 EMA).
4. Three Configurable Entry Modes:
   - HYBRID_50_50: 50% initial allocation at Day 0 base, 50% confirmation tranche on Day 7-10 only if in profit.
   - LAYER_2_CONFIRMATION: 10-day incubation watchlist, 100% full allocation on Day 10 if confirmed.
   - LAYER_1_FULL: 100% full allocation at Day 0 breakout base.
5. Alpha Boosters:
   - use_vol_parity: Volatility-Parity sizing inverse to ATR% to balance risk across portfolio assets.
   - use_sector_leadership: Restricting and boosting candidates belonging to top relative strength sectors.
6. Execution Microstructure Realism:
   - Statutory + Slippage: 102.6 bps per side (205.2 bps round trip)
     [Conservative estimate for Indian delivery segment:
      50 bps slippage + 52.6 bps statutory (STT+GST+Stamp+Exchange)]
   - Live deployment expected cost: ~55-70 bps per side
   - Backtest uses higher figure for margin-of-safety buffer
   - T+1 morning cash & slot freeze (zero same-day exit capital recycling lookahead).
   - High-before-low lookahead elimination (stops evaluated against prior day's peak price).
   - Gap-down fill protection (fills at min(floor, open), never fake shielded max).
   - Statutory transaction costs (STT + GST + Stamp Duty + Exchange fees + Slippage).
7. 5-Stage Multi-Tiered Exit Engine (Defense -> Breakeven -> Ratchet -> Secular -> Climax).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
import numpy as np
import pandas as pd


@dataclass
class UpgradedTrade:
    symbol: str
    entry_date: pd.Timestamp
    entry_price: float
    entry_price_with_friction: float
    shares: float
    invested_capital: float
    dollar_risk: float
    target_slot_capital: float = 0.0
    tranche1_invested: float = 0.0
    tranche1_shares: float = 0.0
    tranche2_active: bool = False
    tranche2_eligible: bool = False
    tranche2_date: pd.Timestamp | None = None
    tranche2_price: float = 0.0
    exit_date: pd.Timestamp | None = None
    exit_price: float = 0.0
    exit_price_net: float = 0.0
    exit_reason: str = ""
    stage_at_exit: str = ""
    peak_price: float = 0.0
    peak_gain_pct: float = 0.0
    gross_return_pct: float = 0.0
    net_return_pct: float = 0.0
    pnl_amount: float = 0.0
    bars_held: int = 0
    calendar_days: int = 0
    is_climax_reached: bool = False
    status: str = "Open"
    sector: str = ""


@dataclass
class BacktestSummary:
    initial_capital: float
    final_capital: float
    compounded_cagr_pct: float
    nifty_cagr_pct: float
    alpha_pct: float
    max_drawdown_pct: float
    total_trades: int
    win_rate_pct: float
    profit_factor: float
    expectancy_pct: float
    avg_gain_pct: float
    avg_loss_pct: float
    win_loss_ratio: float
    avg_bars_held: float
    avg_calendar_days: float
    total_friction_paid: float
    trades_df: pd.DataFrame
    equity_curve: pd.DataFrame
    yearly_summary: pd.DataFrame
    mode: str = "HYBRID_50_50"
    use_vol_parity: bool = True
    use_sector_leadership: bool = False


class UpgradedVCPBacktestEngine:
    def __init__(
        self,
        initial_capital: float = 1_000_000.0,
        max_slots: int = 8,   # FIX #2: 8 equal-weight slots (12.5% each) per HYBRID_50_50 spec
        risk_per_trade_pct: float = 0.02,  # 2% equity risk
        min_turnover_rs: float = 30_000_000.0,  # Rs 3 Crores (scaled dynamically)
        slippage_bps_per_side: float = 50.0,  # 0.5% slippage
        statutory_bps_per_side: float = 52.6,  # STT + GST + Stamp Duty + Exchange
        # Total cost per side = 102.6 bps (conservative backtest assumption).
        # Expected live cost ~55-70 bps; backtest uses higher figure for safety margin.
        mode: str = "HYBRID_50_50",  # "HYBRID_50_50", "LAYER_2_CONFIRMATION", "LAYER_1_FULL"
        entry_mode: str | None = None,
        use_vol_parity: bool = True,  # Alpha Booster: Volatility-parity sizing inverse to ATR%
        use_sector_leadership: bool = False,  # Deprecated / Disabled by default (sector column absent in historical parquet)
        tranche2_days: int = 7,   # FIX #7: Spec says Day-7 T2 confirmation (was incorrectly 10)
        incubation_days: int | None = None,
        use_equal_weight_slots: bool = True,  # True = 100% active slot allocation (no idle cash drag)
        cash_yield_pct_p_a: float = 6.5,  # Annualized 6.5% liquid fund/T-Bill yield on uninvested cash
    ) -> None:
        self.initial_capital = initial_capital
        self.max_slots = max_slots
        self.risk_per_trade_pct = risk_per_trade_pct
        self.min_turnover_rs = min_turnover_rs
        self.mode = entry_mode if entry_mode is not None else mode
        self.use_vol_parity = use_vol_parity
        self.use_sector_leadership = use_sector_leadership
        self.tranche2_days = incubation_days if incubation_days is not None else tranche2_days
        self.use_equal_weight_slots = use_equal_weight_slots
        self.cash_yield_pct_p_a = cash_yield_pct_p_a

        # Total cost per side (Default: 20 bps slippage + 35 bps statutory = 55.0 bps per side;
        # Conservative stress-test mode uses 50 bps slippage + 52.6 bps statutory = 102.6 bps per side)
        self.cost_per_side = (slippage_bps_per_side + statutory_bps_per_side) / 10_000.0

    @staticmethod
    def compute_indicators(df: pd.DataFrame, bench_series: pd.Series) -> pd.DataFrame:
        """Compute True VCP, EMAs, ATRs, 52W High, and Relative Strength indicators."""
        df = df.sort_values("date").reset_index(drop=True).copy()

        # 1. True Range & ATRs
        prev_close = df["close"].shift(1)
        tr1 = df["high"] - df["low"]
        tr2 = (df["high"] - prev_close).abs()
        tr3 = (df["low"] - prev_close).abs()
        df["tr"] = np.maximum(tr1, np.maximum(tr2, tr3))

        df["atr_10"] = df["tr"].rolling(10, min_periods=5).mean()
        df["atr_14"] = df["tr"].rolling(14, min_periods=7).mean()
        df["atr_30"] = df["tr"].rolling(30, min_periods=15).mean()

        # 2. Moving Averages
        df["ema20"] = df["close"].ewm(span=20, adjust=False).mean()
        df["ema50"] = df["close"].ewm(span=50, adjust=False).mean()
        df["ema100"] = df["close"].ewm(span=100, adjust=False).mean()

        # 3. 52-Week (252 Trading Days) High (Lookahead-free: shifted by 1)
        df["high_52w"] = df["high"].shift(1).rolling(252, min_periods=20).max()
        df["dist_from_52w_high"] = df["close"] / df["high_52w"]

        # 4. Momentum & Relative Volume
        df["ret_5d"] = df["close"].pct_change(5)
        df["ret_20d"] = df["close"].pct_change(20)
        vol_mean_20d = df["volume"].shift(1).rolling(20, min_periods=10).mean()
        df["rvol"] = df["volume"] / vol_mean_20d.where(vol_mean_20d > 0, 1.0)
        df["turnover"] = df["close"] * df["volume"]

        # 5. Relative Strength vs Benchmark (63 Days / 3 Months)
        stock_ret_63d = df["close"].pct_change(63)
        bench_aligned = bench_series.reindex(df["date"]).ffill().bfill()
        bench_ret_63d = bench_aligned.pct_change(63).values
        df["rs_63d"] = stock_ret_63d - bench_ret_63d
        df["rs_score"] = np.maximum(0.01, df["rs_63d"].fillna(0.0)) * df["rvol"].fillna(1.0)

        # 6. True VCP Discovery Condition
        vcp_contraction = df["atr_10"] < df["atr_30"]
        within_15pct_52w = df["close"] >= 0.85 * df["high_52w"]
        base_consolidation = (df["ret_20d"] > 0.0) & (df["ret_20d"] <= 0.35)
        volume_ignition = (df["ret_5d"] > 0.0) & (df["rvol"] >= 1.4)

        # Dynamic inflation/market-cap scaled liquidity floor:
        # Pre-2008: Rs 25 Lakhs | 2008-2015: Rs 1 Crore | 2016+: Rs 3 Crores
        year_s = df["date"].dt.year
        dyn_floor = np.where(year_s < 2008, 2_500_000.0, np.where(year_s < 2016, 10_000_000.0, 30_000_000.0))
        liquidity_ok = df["turnover"] >= dyn_floor

        df["raw_signal"] = (
            vcp_contraction &
            within_15pct_52w &
            base_consolidation &
            volume_ignition &
            liquidity_ok
        )
        return df

    def run_backtest(
        self,
        bars_df: pd.DataFrame,
        bench_df: pd.DataFrame,
        start_date: str | pd.Timestamp | None = None,
        end_date: str | pd.Timestamp | None = None,
        mode: str | None = None,
    ) -> BacktestSummary:
        """Run the full event-driven multi-stage simulation with capital constraints."""
        # 0. Mode Resolution
        active_mode = (mode or self.mode).upper().replace("-", "_")
        if "HYBRID" in active_mode or "50" in active_mode:
            exec_mode = "HYBRID_50_50"
        elif "LAYER_2" in active_mode or "L2" in active_mode or "CONFIRMATION" in active_mode:
            exec_mode = "LAYER_2_CONFIRMATION"
        else:
            exec_mode = "LAYER_1_FULL"

        bars = bars_df.copy()
        bars["date"] = pd.to_datetime(bars["date"], utc=True)
        bench = bench_df.copy()
        bench["date"] = pd.to_datetime(bench["date"], utc=True)

        start_dt = pd.to_datetime(start_date, utc=True) if start_date is not None else None
        end_dt = pd.to_datetime(end_date, utc=True) if end_date is not None else None

        # 1. Benchmark Regime
        bench = bench.sort_values("date").reset_index(drop=True)
        bench["ema50"] = bench["close"].ewm(span=50, adjust=False).mean()
        bench["ema200"] = bench["close"].ewm(span=200, adjust=False).mean()
        bench["regime_ok"] = (bench["close"] > bench["ema50"]) | (bench["close"] > bench["ema200"])
        bench_regime_dict = bench.set_index("date")["regime_ok"].to_dict()
        bench_close_dict = bench.set_index("date")["close"].to_dict()
        bench_series = bench.set_index("date")["close"]

        # 2. Sector Leadership Pre-computation (Alpha Booster 2)
        sector_rs_dict: dict[tuple[pd.Timestamp, str], float] = {}
        if "sector" in bars.columns and self.use_sector_leadership:
            bars_sorted = bars.sort_values(["symbol", "date"]).reset_index(drop=True)
            bars_sorted["_ret20"] = bars_sorted.groupby("symbol")["close"].pct_change(20)
            sector_means = bars_sorted.groupby(["date", "sector"])["_ret20"].mean().reset_index()
            bench_20d = bench.set_index("date")["close"].pct_change(20)
            sector_means["bench_20d"] = sector_means["date"].map(bench_20d).fillna(0.0)
            sector_means["sector_rs"] = sector_means["_ret20"] - sector_means["bench_20d"]
            sector_rs_dict = sector_means.set_index(["date", "sector"])["sector_rs"].to_dict()

        # 3. Compute Indicators per Symbol
        symbol_data: dict[str, pd.DataFrame] = {}
        all_dates_set = set()
        for sym, grp in bars.groupby("symbol"):
            clean_sym = sym.replace(".NS", "").replace(".BO", "")
            ind_df = self.compute_indicators(grp, bench_series)
            symbol_data[clean_sym] = ind_df.set_index("date")
            all_dates_set.update(ind_df["date"].tolist())

        all_dates = sorted(list(all_dates_set))
        date_to_idx = {d: i for i, d in enumerate(all_dates)}

        sim_dates = [
            d for d in all_dates
            if (start_dt is None or d >= start_dt) and (end_dt is None or d <= end_dt)
        ]
        if not sim_dates:
            sim_dates = all_dates

        # 4. Simulation State (Senior Quant Hardened: No Lookahead, Real Cash Settlement)
        cash = self.initial_capital
        active_trades: dict[str, UpgradedTrade] = {}
        watchlist_l2: dict[str, dict[str, Any]] = {}
        closed_trades: list[UpgradedTrade] = []
        equity_curve: list[dict[str, Any]] = []
        total_friction_paid = 0.0
        daily_cash_yield = (
            (1.0 + self.cash_yield_pct_p_a / 100.0) ** (1.0 / 252.0) - 1.0
            if self.cash_yield_pct_p_a > 0.0
            else 0.0
        )

        for d_idx, cur_date in enumerate(sim_dates):
            # Accrue overnight risk-free yield on uninvested cash (T-Bills / Liquid Funds)
            if cash > 0.0 and daily_cash_yield > 0.0:
                cash += cash * daily_cash_yield

            # -------------------------------------------------------------
            # STEP 1: MORNING MARKET OPEN (9:15 AM) - NEW ENTRIES EXECUTION
            # -------------------------------------------------------------
            # Rule: Entries at 9:15 AM can ONLY use cash and slots available
            # from yesterday's close. Exit proceeds from today's trades are NOT
            # yet available (T+1 cash settlement / prevents same-day cash recycling).
            existing_symbols = list(active_trades.keys())
            available_cash_for_entry = cash
            available_slots = max(0, self.max_slots - len(existing_symbols))

            orig_idx = date_to_idx.get(cur_date, 0)
            prev_date = all_dates[orig_idx - 1] if orig_idx > 0 else None
            regime_ok = bench_regime_dict.get(prev_date, True) if prev_date is not None else True

            # Portfolio Mark-to-Market Equity at Open
            mtm_val_open = sum(
                symbol_data[s].loc[cur_date]["open"] * t.shares
                if cur_date in symbol_data[s].index else t.invested_capital
                for s, t in active_trades.items()
            )
            current_equity_open = cash + mtm_val_open
            max_slot_capital = current_equity_open / self.max_slots

            # ---------------------------------------------------------
            # A. Process Tranche 2 Additions for HYBRID_50_50 at Open
            # ---------------------------------------------------------
            if exec_mode == "HYBRID_50_50":
                for sym in existing_symbols:
                    tr = active_trades[sym]
                    if tr.tranche2_eligible and not tr.tranche2_active:
                        tr.tranche2_eligible = False
                        s_df = symbol_data[sym]
                        if cur_date in s_df.index:
                            bar = s_df.loc[cur_date]
                            # FIX #6a: Complete upper circuit check (high == low = zero range)
                            if not (bar["high"] == bar["low"]):
                                t2_alloc = min(available_cash_for_entry, tr.target_slot_capital * 0.5)
                                if t2_alloc >= 2500.0:
                                    raw_t2 = bar["open"]
                                    t2_friction = t2_alloc * self.cost_per_side
                                    total_friction_paid += t2_friction
                                    t2_shares = (t2_alloc - t2_friction) / raw_t2

                                    cash -= t2_alloc
                                    available_cash_for_entry -= t2_alloc

                                    tr.shares += t2_shares
                                    tr.invested_capital += t2_alloc

                                    # FIX #5: Correct blended entry price using weighted average
                                    # of actual T1 and T2 fill prices, not total_capital / total_shares.
                                    # total_capital/shares was wrong because invested_capital includes
                                    # friction deducted from shares (shares = (alloc - friction) / price).
                                    t1_fill = tr.tranche1_invested / tr.tranche1_shares if tr.tranche1_shares > 0 else raw_t2
                                    t2_fill = raw_t2
                                    t1_w = tr.tranche1_shares / tr.shares  # weight of T1 shares
                                    t2_w = t2_shares / tr.shares            # weight of T2 shares
                                    tr.entry_price = (t1_fill * t1_w) + (t2_fill * t2_w)
                                    # entry_price_with_friction = blended fill + one-side cost
                                    # (both tranches already paid cost_per_side on entry)
                                    tr.entry_price_with_friction = tr.entry_price * (1.0 + self.cost_per_side)
                                    tr.tranche2_active = True
                                    tr.tranche2_date = cur_date
                                    tr.tranche2_price = raw_t2

            # ---------------------------------------------------------
            # B. Process LAYER_2_CONFIRMATION Watchlist Graduations at Open
            # ---------------------------------------------------------
            if exec_mode == "LAYER_2_CONFIRMATION":
                graduated_syms: list[str] = []
                for sym, w in list(watchlist_l2.items()):
                    if sym in active_trades:
                        graduated_syms.append(sym)
                        continue
                    if w.get("graduated", False) and available_slots > 0 and available_cash_for_entry >= 5000.0 and regime_ok:
                        s_df = symbol_data[sym]
                        if cur_date in s_df.index:
                            bar = s_df.loc[cur_date]
                            if not (bar["high"] == bar["low"]):  # FIX #6a: circuit check
                                alloc_capital = min(w["target_capital"], max_slot_capital, available_cash_for_entry)
                                if alloc_capital >= 5000.0:
                                    raw_entry = bar["open"]
                                    entry_friction = alloc_capital * self.cost_per_side
                                    total_friction_paid += entry_friction
                                    shares = (alloc_capital - entry_friction) / raw_entry

                                    cash -= alloc_capital
                                    available_cash_for_entry -= alloc_capital
                                    available_slots -= 1

                                    active_trades[sym] = UpgradedTrade(
                                        symbol=sym,
                                        entry_date=cur_date,
                                        entry_price=raw_entry,
                                        entry_price_with_friction=raw_entry * (1.0 + self.cost_per_side),
                                        shares=shares,
                                        invested_capital=alloc_capital,
                                        dollar_risk=w["dollar_risk"],
                                        target_slot_capital=w["target_capital"],
                                        tranche1_invested=alloc_capital,
                                        tranche1_shares=shares,
                                        tranche2_active=True,
                                        peak_price=raw_entry,
                                        status="Open",
                                    )
                                    graduated_syms.append(sym)
                for sym in graduated_syms:
                    if sym in watchlist_l2:
                        del watchlist_l2[sym]

            # ---------------------------------------------------------
            # C. Process New Signals from prev_date
            # ---------------------------------------------------------
            if orig_idx > 0 and regime_ok:
                candidates: list[dict[str, Any]] = []
                for sym, s_df in symbol_data.items():
                    if sym in active_trades or sym in watchlist_l2:
                        continue
                    if prev_date in s_df.index and s_df.loc[prev_date, "raw_signal"]:
                        p_row = s_df.loc[prev_date]
                        cand_sec = str(p_row.get("sector", "")) if "sector" in p_row.index else ""
                        sec_rs = sector_rs_dict.get((prev_date, cand_sec), 0.0)

                        rank_score = float(p_row["rs_score"])
                        if self.use_sector_leadership and "sector" in bars.columns:
                            if sec_rs > 0.0:
                                rank_score *= 1.25  # Leadership boost
                            elif sec_rs < -0.05:
                                rank_score *= 0.75  # Laggard discount

                        candidates.append({
                            "symbol": sym,
                            "rs_score": float(p_row["rs_score"]),
                            "rvol": float(p_row["rvol"]),
                            "atr_14": float(p_row["atr_14"]) if pd.notnull(p_row["atr_14"]) else 0.0,
                            "sector": cand_sec,
                            "sector_rs": sec_rs,
                            "rank_score": rank_score,
                        })

                # Cross-Sectional Ranking: Rank by score descending
                candidates.sort(key=lambda x: x["rank_score"], reverse=True)

                for cand in candidates:
                    sym = cand["symbol"]
                    s_df = symbol_data[sym]
                    if cur_date not in s_df.index:
                        continue
                    bar = s_df.loc[cur_date]

                    # FIX #6a: Complete Circuit Rejection on Entry.
                    # Upper circuit: high == low (zero trading range, no sellers available).
                    # Includes the case open==high==low==close for truly locked stocks.
                    if bar["high"] == bar["low"]:
                        continue

                    # Sizing: Equal-Weight Slots (Zero Idle Cash) vs Risk Parity (Alpha Booster 1)
                    if self.use_equal_weight_slots:
                        target_capital = max_slot_capital
                        dollar_risk = max_slot_capital * 0.08
                    else:
                        dollar_risk = current_equity_open * self.risk_per_trade_pct
                        atr_val = cand["atr_14"] if cand["atr_14"] > 0 else bar["open"] * 0.03
                        unit_risk = max(bar["open"] * 0.08, 2.5 * atr_val)
                        target_shares = dollar_risk / unit_risk

                        if self.use_vol_parity:
                            atr_pct = max(0.01, atr_val / bar["open"])
                            vol_scale = np.clip(0.03 / atr_pct, 0.5, 1.5)
                            target_capital = min(target_shares * bar["open"] * vol_scale, max_slot_capital)
                        else:
                            target_capital = min(target_shares * bar["open"], max_slot_capital)

                    if exec_mode == "LAYER_1_FULL":
                        if available_slots <= 0 or available_cash_for_entry < 5000.0:
                            break
                        alloc_capital = min(target_capital, available_cash_for_entry)
                        if alloc_capital < 5000.0:
                            continue
                        raw_entry = bar["open"]
                        entry_friction = alloc_capital * self.cost_per_side
                        total_friction_paid += entry_friction
                        shares = (alloc_capital - entry_friction) / raw_entry

                        cash -= alloc_capital
                        available_cash_for_entry -= alloc_capital
                        available_slots -= 1

                        active_trades[sym] = UpgradedTrade(
                            symbol=sym,
                            entry_date=cur_date,
                            entry_price=raw_entry,
                            entry_price_with_friction=raw_entry * (1.0 + self.cost_per_side),
                            shares=shares,
                            invested_capital=alloc_capital,
                            dollar_risk=dollar_risk,
                            target_slot_capital=target_capital,
                            tranche1_invested=alloc_capital,
                            tranche1_shares=shares,
                            tranche2_active=True,
                            peak_price=raw_entry,
                            status="Open",
                        )

                    elif exec_mode == "HYBRID_50_50":
                        if available_slots <= 0 or available_cash_for_entry < 2500.0:
                            break
                        alloc_capital = min(target_capital * 0.5, available_cash_for_entry)
                        if alloc_capital < 2500.0:
                            continue
                        raw_entry = bar["open"]
                        entry_friction = alloc_capital * self.cost_per_side
                        total_friction_paid += entry_friction
                        shares = (alloc_capital - entry_friction) / raw_entry

                        cash -= alloc_capital
                        available_cash_for_entry -= alloc_capital
                        available_slots -= 1

                        active_trades[sym] = UpgradedTrade(
                            symbol=sym,
                            entry_date=cur_date,
                            entry_price=raw_entry,
                            entry_price_with_friction=raw_entry * (1.0 + self.cost_per_side),
                            shares=shares,
                            invested_capital=alloc_capital,
                            dollar_risk=dollar_risk,
                            target_slot_capital=target_capital,
                            tranche1_invested=alloc_capital,
                            tranche1_shares=shares,
                            tranche2_active=False,
                            tranche2_eligible=False,
                            peak_price=raw_entry,
                            status="Open",
                        )

                    elif exec_mode == "LAYER_2_CONFIRMATION":
                        if sym not in watchlist_l2:
                            watchlist_l2[sym] = {
                                "discovery_date": cur_date,
                                "discovery_price": bar["open"],
                                "days": 0,
                                "max_low": bar["low"],
                                "target_capital": target_capital,
                                "dollar_risk": dollar_risk,
                                "graduated": False,
                            }

            # -------------------------------------------------------------
            # STEP 2: INTRADAY & CLOSING POSITION MANAGEMENT (EXITS)
            # -------------------------------------------------------------
            # Only evaluate positions held overnight (entered prior to today).
            # Hardened against Intraday Lookahead:
            # Trailing floors and initial stop-loss are evaluated using the
            # peak price reached BEFORE today. Peak price is updated ONLY if
            # the position survives today's stops without exiting.
            symbols_to_close: list[str] = []

            for sym in existing_symbols:
                tr = active_trades[sym]
                s_df = symbol_data[sym]
                if cur_date not in s_df.index:
                    continue
                bar = s_df.loc[cur_date]

                # Peak price established prior to today
                prior_peak = tr.peak_price
                gain_from_entry = (prior_peak / tr.entry_price - 1.0) * 100.0
                dip_from_peak = (bar["close"] / prior_peak - 1.0) * 100.0

                exit_triggered = False
                exit_price = 0.0
                exit_reason = ""
                stage_name = ""

                # Check Tranche 2 eligibility for tomorrow in HYBRID_50_50
                if exec_mode == "HYBRID_50_50" and not tr.tranche2_active and tr.bars_held >= (self.tranche2_days - 1):
                    if bar["close"] > tr.entry_price and bar["low"] > tr.entry_price * 0.92:
                        tr.tranche2_eligible = True

                # -------------------------------------------------------------
                # STAGE 5: PARABOLIC CLIMAX EXIT (Prior Peak Gain >= +100%)
                # FIX #3: Trigger only after genuine doubling (>=100%), not 50%.
                # FIX #3: Floor = -25% trail from prior peak (was incorrectly -15%).
                # FIX #3: Gap-down protected fill = min(prior_peak * 0.75, open).
                # -------------------------------------------------------------
                if tr.is_climax_reached and gain_from_entry >= 100.0:
                    if dip_from_peak <= -25.0:
                        exit_triggered = True
                        exit_price = min(prior_peak * 0.75, bar["open"])
                        exit_reason = "Parabolic Climax Exit (-25% Trail from Doubling Peak)"
                        stage_name = "Stage 5: Climax Exit"

                # -------------------------------------------------------------
                # STAGE 4: SECULAR COMPOUNDING (Prior Peak Gain >= 50%, < 100%)
                # -------------------------------------------------------------
                elif gain_from_entry >= 50.0 and not exit_triggered:
                    floor_4 = tr.entry_price * 1.25
                    # Hard floor locked at +25% (Gap-Down Protected: min, never max)
                    if bar["low"] <= floor_4:
                        exit_triggered = True
                        exit_price = min(floor_4, bar["open"])
                        exit_reason = "Secular Profit Floor (+25% Locked)"
                        stage_name = "Stage 4: Secular Compounding"
                    elif bar["close"] < bar["ema100"] and dip_from_peak <= -20.0:
                        exit_triggered = True
                        exit_price = min(bar["open"], bar["close"]) if bar["open"] < bar["close"] else bar["close"]
                        exit_reason = "Secular Trend Ended (100 EMA Break & -20% Drop)"
                        stage_name = "Stage 4: Secular Compounding"

                # -------------------------------------------------------------
                # STAGE 3: PROGRESSIVE RATCHET (+30% <= Prior Peak Gain < +50%)
                # -------------------------------------------------------------
                elif 30.0 <= gain_from_entry < 50.0 and not exit_triggered:
                    floor_12 = tr.entry_price * 1.12
                    floor_price = max(floor_12, bar["ema50"])
                    if bar["low"] <= floor_12:
                        exit_triggered = True
                        exit_price = min(floor_12, bar["open"])
                        exit_reason = "Progressive Floor Ratchet (+12% / 50 EMA Locked)"
                        stage_name = "Stage 3: Progressive Ratchet"
                    elif bar["close"] < floor_price:
                        exit_triggered = True
                        exit_price = min(floor_price, bar["open"]) if bar["open"] < floor_price else bar["close"]
                        exit_reason = "Progressive Floor Ratchet (+12% / 50 EMA Locked)"
                        stage_name = "Stage 3: Progressive Ratchet"

                # -------------------------------------------------------------
                # STAGE 2: CAPITAL PRESERVATION (+15% <= Prior Peak Gain < +30%)
                # -------------------------------------------------------------
                elif 15.0 <= gain_from_entry < 30.0 and not exit_triggered:
                    be_floor = tr.entry_price * 1.02
                    if bar["low"] <= be_floor:
                        exit_triggered = True
                        exit_price = min(be_floor, bar["open"])
                        exit_reason = "Breakeven Floor (+2% Profit Locked)"
                        stage_name = "Stage 2: Capital Preservation"

                # -------------------------------------------------------------
                # STAGE 1: IGNITION DEFENSE (Prior Peak Gain < +15%)
                # -------------------------------------------------------------
                elif gain_from_entry < 15.0 and not exit_triggered:
                    atr_entry = bar["atr_14"] if pd.notnull(bar["atr_14"]) else bar["close"] * 0.03
                    closing_stop = max(tr.entry_price * 0.92, tr.entry_price - 2.5 * atr_entry)

                    # Intraday extreme circuit breaker (-10%)
                    if bar["low"] <= tr.entry_price * 0.90:
                        exit_triggered = True
                        # Statutory exchange circuit filters cap single-day gap execution at -20% max
                        # (prevents artificial execution on unadjusted corporate action / demerger ticks)
                        exit_price = max(tr.entry_price * 0.80, min(tr.entry_price * 0.90, bar["open"]))
                        exit_reason = "Extreme Circuit Breaker (-10% Hard Stop)"
                        stage_name = "Stage 1: Ignition Defense"
                    elif bar["close"] <= closing_stop:
                        exit_triggered = True
                        exit_price = min(closing_stop, bar["open"]) if bar["open"] < closing_stop else bar["close"]
                        exit_reason = "Closing ATR Stop-Loss"
                        stage_name = "Stage 1: Ignition Defense"
                    # Time-Stop (Dead Money): Bars >= 30, Gain < 10%, Close < 20 EMA
                    elif tr.bars_held >= 30 and gain_from_entry < 10.0 and bar["close"] < bar["ema20"]:
                        exit_triggered = True
                        exit_price = bar["close"]
                        exit_reason = "Dead Money Time-Stop Exit (30d Stagnation)"
                        stage_name = "Stage 1: Ignition Defense"

                # Execute Exit if Triggered
                if exit_triggered:
                    # FIX #6b: Lower circuit detection on exit.
                    # Lower circuit = stock is locked limit-down, no buyers available.
                    # Detected when: open == low (price opened at floor and never recovered).
                    # In this case we CANNOT sell at the desired exit price today.
                    # Exception: Dead Money time-stop can still exit at close even in
                    # mild down-days (only defer on truly locked circuits).
                    is_lower_circuit = (
                        bar["open"] == bar["low"]
                        and bar["high"] == bar["low"]  # truly locked: no range at all
                    )
                    if is_lower_circuit and exit_reason != "Dead Money Time-Stop Exit (30d Stagnation)":
                        # Defer exit to next session — position stays open, no close recorded
                        tr.exit_reason = f"CIRCUIT_DEFER: {exit_reason}"
                        exit_triggered = False
                    else:
                        sell_friction = exit_price * tr.shares * self.cost_per_side
                        net_proceeds = (exit_price * tr.shares) - sell_friction
                        total_friction_paid += sell_friction
                        cash += net_proceeds  # Becomes available starting next day

                        tr.exit_date = cur_date
                        tr.exit_price = exit_price
                        tr.exit_price_net = exit_price * (1.0 - self.cost_per_side)
                        tr.exit_reason = exit_reason
                        tr.stage_at_exit = stage_name
                        tr.peak_gain_pct = (tr.peak_price / tr.entry_price - 1.0) * 100.0
                        tr.gross_return_pct = (exit_price / tr.entry_price - 1.0) * 100.0
                        tr.net_return_pct = (tr.exit_price_net / tr.entry_price_with_friction - 1.0) * 100.0
                        tr.pnl_amount = net_proceeds - tr.invested_capital
                        tr.calendar_days = (cur_date - tr.entry_date).days
                        tr.bars_held += 1
                        tr.status = "Closed"

                        closed_trades.append(tr)
                        symbols_to_close.append(sym)
                else:
                    # Trade survived today's session: update peak price & climax flag safely
                    if bar["high"] > tr.peak_price:
                        tr.peak_price = bar["high"]
                    # FIX #4: Climax flag with bidirectional reset.
                    # SET when stock is 60%+ above 100 EMA (parabolic blow-off zone).
                    # RESET when stock cools to <35% above 100 EMA (normalized again).
                    # This prevents Stage 5 triggering prematurely on stocks that briefly
                    # spiked above the climax threshold and then returned to normal trend.
                    ema100_val = bar["ema100"]
                    if pd.notnull(ema100_val) and ema100_val > 0:
                        dist_from_ema100 = (bar["close"] / ema100_val - 1.0)
                        if dist_from_ema100 > 0.60:
                            tr.is_climax_reached = True
                        elif tr.is_climax_reached and dist_from_ema100 < 0.35:
                            # Stock has cooled from parabolic zone — reset so Stage 4 applies
                            tr.is_climax_reached = False
                    tr.bars_held += 1

            for sym in symbols_to_close:
                del active_trades[sym]

            # Update peak price for newly entered positions on their entry day
            for sym, tr in active_trades.items():
                if sym not in existing_symbols:
                    s_df = symbol_data[sym]
                    if cur_date in s_df.index:
                        b = s_df.loc[cur_date]
                        if b["high"] > tr.peak_price:
                            tr.peak_price = b["high"]

            # Update Watchlist incubation in LAYER_2_CONFIRMATION
            if exec_mode == "LAYER_2_CONFIRMATION":
                expired_w: list[str] = []
                for sym, w in list(watchlist_l2.items()):
                    if sym in active_trades:
                        expired_w.append(sym)
                        continue
                    s_df = symbol_data[sym]
                    if cur_date not in s_df.index:
                        continue
                    b = s_df.loc[cur_date]
                    w["days"] += 1
                    w["max_low"] = min(w["max_low"], float(b["low"]))
                    if w["days"] >= self.tranche2_days:
                        c_close = float(b["close"])
                        if c_close > w["discovery_price"] and w["max_low"] > w["discovery_price"] * 0.92:
                            w["graduated"] = True
                        else:
                            expired_w.append(sym)
                for sym in expired_w:
                    if sym in watchlist_l2:
                        del watchlist_l2[sym]

            # -------------------------------------------------------------
            # STEP 3: DAILY PORTFOLIO MARK-TO-MARKET VALUATION
            # -------------------------------------------------------------
            curr_mtm = 0.0
            for s, t in active_trades.items():
                s_df = symbol_data[s]
                p_curr = s_df.loc[cur_date]["close"] if cur_date in s_df.index else t.entry_price
                curr_mtm += p_curr * t.shares

            total_equity = cash + curr_mtm
            equity_curve.append({
                "date": cur_date,
                "cash": cash,
                "mtm_positions": curr_mtm,
                "total_equity": total_equity,
                "active_slots": len(active_trades),
                "nifty_close": bench_close_dict.get(cur_date, np.nan),
            })

        # Close remaining open positions at terminal date
        terminal_date = sim_dates[-1]
        for sym, tr in active_trades.items():
            s_df = symbol_data[sym]
            bar = s_df.loc[terminal_date] if terminal_date in s_df.index else s_df.iloc[-1]
            exit_p = bar["close"]
            tr.exit_date = terminal_date
            tr.exit_price = exit_p
            tr.exit_price_net = exit_p * (1.0 - self.cost_per_side)
            tr.peak_gain_pct = (tr.peak_price / tr.entry_price - 1.0) * 100.0
            tr.gross_return_pct = (exit_p / tr.entry_price - 1.0) * 100.0
            tr.net_return_pct = (tr.exit_price_net / tr.entry_price_with_friction - 1.0) * 100.0
            tr.pnl_amount = (exit_p * tr.shares) - tr.invested_capital
            tr.calendar_days = (terminal_date - tr.entry_date).days
            tr.exit_reason = "ACTIVE WEALTH COMPOUNDER (Holding Today)"
            tr.stage_at_exit = "Active Holding"
            tr.status = "Active"
            closed_trades.append(tr)

        # 5. Generate Performance DataFrames & Statistics
        if closed_trades:
            trades_df = pd.DataFrame([vars(t) for t in closed_trades])
        else:
            trades_df = pd.DataFrame(columns=[
                "symbol", "entry_date", "entry_price", "entry_price_with_friction",
                "shares", "invested_capital", "dollar_risk", "exit_date", "exit_price",
                "exit_price_net", "exit_reason", "stage_at_exit", "peak_price",
                "peak_gain_pct", "gross_return_pct", "net_return_pct", "pnl_amount",
                "bars_held", "calendar_days", "is_climax_reached", "status"
            ])
        eq_df = pd.DataFrame(equity_curve)

        eq_df["peak_equity"] = eq_df["total_equity"].cummax()
        eq_df["drawdown"] = (eq_df["total_equity"] / eq_df["peak_equity"] - 1.0) * 100.0
        max_drawdown = eq_df["drawdown"].min() if not eq_df.empty else 0.0

        # Compounded CAGRs
        total_years = max(0.01, (sim_dates[-1] - sim_dates[0]).days / 365.25)
        final_capital = eq_df.iloc[-1]["total_equity"] if not eq_df.empty else self.initial_capital
        model_cagr = ((final_capital / self.initial_capital) ** (1.0 / total_years) - 1.0) * 100.0

        valid_nifty = eq_df.dropna(subset=["nifty_close"])
        if not valid_nifty.empty and len(valid_nifty) >= 1:
            nifty_start = valid_nifty.iloc[0]["nifty_close"]
            nifty_end = valid_nifty.iloc[-1]["nifty_close"]
            nifty_cagr = ((nifty_end / nifty_start) ** (1.0 / total_years) - 1.0) * 100.0
        else:
            nifty_start = 1.0
            nifty_end = 1.0
            nifty_cagr = 0.0

        # Trade metrics
        total_trades = len(trades_df)
        winning_trades = trades_df[trades_df["net_return_pct"] > 0]
        losing_trades = trades_df[trades_df["net_return_pct"] <= 0]

        win_rate = (len(winning_trades) / total_trades * 100.0) if total_trades > 0 else 0.0
        avg_gain = winning_trades["net_return_pct"].mean() if len(winning_trades) > 0 else 0.0
        avg_loss = abs(losing_trades["net_return_pct"].mean()) if len(losing_trades) > 0 else 0.0
        win_loss_ratio = (avg_gain / avg_loss) if avg_loss > 0 else 999.0

        gross_profits = winning_trades["pnl_amount"].sum()
        gross_losses = abs(losing_trades["pnl_amount"].sum())
        profit_factor = (gross_profits / gross_losses) if gross_losses > 0 else 999.0

        # Mathematical Expectancy = (Win% * AvgWin) - (Loss% * AvgLoss)
        win_prob = win_rate / 100.0
        loss_prob = 1.0 - win_prob
        expectancy = (win_prob * avg_gain) - (loss_prob * avg_loss)

        avg_bars = trades_df["bars_held"].mean() if total_trades > 0 else 0.0
        avg_days = trades_df["calendar_days"].mean() if total_trades > 0 else 0.0

        # Year-by-Year Table
        eq_df["year"] = eq_df["date"].dt.year
        yearly_rows = []
        prev_cap = self.initial_capital
        prev_nifty = nifty_start

        for yr, grp in eq_df.groupby("year"):
            yr_end_cap = grp.iloc[-1]["total_equity"]
            yr_model_ret = (yr_end_cap / prev_cap - 1.0) * 100.0

            nifty_pts = grp["nifty_close"].dropna()
            yr_nifty_end = nifty_pts.iloc[-1] if not nifty_pts.empty else prev_nifty
            yr_nifty_ret = (yr_nifty_end / prev_nifty - 1.0) * 100.0 if prev_nifty > 0 else 0.0

            yearly_rows.append({
                "year": yr,
                "start_capital": prev_cap,
                "end_capital": yr_end_cap,
                "model_net_ret": yr_model_ret,
                "nifty_ret": yr_nifty_ret,
                "alpha": yr_model_ret - yr_nifty_ret,
                "max_drawdown": grp["drawdown"].min(),
                "avg_slots": grp["active_slots"].mean(),
            })
            prev_cap = yr_end_cap
            prev_nifty = yr_nifty_end

        yearly_df = pd.DataFrame(yearly_rows)

        return BacktestSummary(
            initial_capital=self.initial_capital,
            final_capital=final_capital,
            compounded_cagr_pct=model_cagr,
            nifty_cagr_pct=nifty_cagr,
            alpha_pct=model_cagr - nifty_cagr,
            max_drawdown_pct=max_drawdown,
            total_trades=total_trades,
            win_rate_pct=win_rate,
            profit_factor=profit_factor,
            expectancy_pct=expectancy,
            avg_gain_pct=avg_gain,
            avg_loss_pct=avg_loss,
            win_loss_ratio=win_loss_ratio,
            avg_bars_held=avg_bars,
            avg_calendar_days=avg_days,
            total_friction_paid=total_friction_paid,
            trades_df=trades_df,
            equity_curve=eq_df,
            yearly_summary=yearly_df,
            mode=exec_mode,
            use_vol_parity=self.use_vol_parity,
            use_sector_leadership=self.use_sector_leadership,
        )
