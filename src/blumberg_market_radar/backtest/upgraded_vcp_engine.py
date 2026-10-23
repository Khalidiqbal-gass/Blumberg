"""Upgraded VCP & Multi-Stage Secular Backtesting Engine.

Institutional-grade quantitative execution engine incorporating:
1. True Volatility Contraction Pattern (ATR_10 < ATR_30 & Close >= 0.85 * 52W_High).
2. Minimum Daily Turnover >= Rs. 3 Crores (30M) & 102.6 bps execution drag (50 bps slippage + 52.6 bps statutory).
3. Benchmark Regime Filter (NIFTY 50/500 > 50 EMA or 200 EMA).
4. Stage 1 Dynamic ATR Stop (Entry - 2.5*ATR_14 or -8% Close) + 10% Intraday Circuit Breaker + 30-Day Dead Money Time-Stop.
5. Progressive Profit Ratchets (Stage 2: +2% floor; Stage 3: +12% / 50 EMA; Stage 4: +25% floor / 100 EMA).
6. Stage 5 Parabolic Climax Blow-Off Exit (Close > 1.6 * 100 EMA -> 20 EMA or 15% peak drop).
7. Cross-Sectional Ranking (RS * RVOL) & 1% Equity ATR-Based Risk Parity Position Sizing.
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


class UpgradedVCPBacktestEngine:
    def __init__(
        self,
        initial_capital: float = 1_000_000.0,
        max_slots: int = 15,
        risk_per_trade_pct: float = 0.01,  # 1% equity risk
        min_turnover_rs: float = 30_000_000.0,  # 3 Crores
        slippage_bps_per_side: float = 50.0,  # 0.5% slippage
        statutory_bps_per_side: float = 52.6,  # STT + GST + Stamp Duty + Exchange
    ) -> None:
        self.initial_capital = initial_capital
        self.max_slots = max_slots
        self.risk_per_trade_pct = risk_per_trade_pct
        self.min_turnover_rs = min_turnover_rs
        
        # Total cost per side = 50 + 52.6 = 102.6 bps = 0.01026
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

        # 3. 52-Week (252 Trading Days) High
        df["high_52w"] = df["high"].rolling(252, min_periods=20).max()
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
        volume_ignition = (df["ret_5d"] > 0.0) & (df["rvol"] >= 1.5)
        liquidity_ok = df["turnover"] >= 30_000_000.0  # Rs 3 Crores

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
    ) -> BacktestSummary:
        """Run the full event-driven multi-stage simulation with capital constraints."""
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

        # 2. Compute Indicators per Symbol
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

        # 3. Simulation State
        cash = self.initial_capital
        active_trades: dict[str, UpgradedTrade] = {}
        closed_trades: list[UpgradedTrade] = []
        equity_curve: list[dict[str, Any]] = []
        total_friction_paid = 0.0

        for d_idx, cur_date in enumerate(sim_dates):
            # A. Evaluate Active Positions on cur_date
            symbols_to_close: list[str] = []

            for sym, tr in active_trades.items():
                s_df = symbol_data[sym]
                if cur_date not in s_df.index:
                    continue
                bar = s_df.loc[cur_date]
                
                # Update peak price
                if bar["high"] > tr.peak_price:
                    tr.peak_price = bar["high"]
                
                gain_from_entry = (tr.peak_price / tr.entry_price - 1.0) * 100.0
                curr_gain = (bar["close"] / tr.entry_price - 1.0) * 100.0
                dip_from_peak = (bar["close"] / tr.peak_price - 1.0) * 100.0

                exit_triggered = False
                exit_price = 0.0
                exit_reason = ""
                stage_name = ""

                # -------------------------------------------------------------
                # STAGE 5: PARABOLIC CLIMAX EXIT (Blow-off Top check)
                # -------------------------------------------------------------
                is_climax = (bar["close"] / bar["ema100"] - 1.0) > 0.60
                if is_climax:
                    tr.is_climax_reached = True

                if tr.is_climax_reached and gain_from_entry >= 50.0:
                    # Tighten stop: 20 EMA or 15% peak drop
                    if bar["close"] < bar["ema20"] or dip_from_peak <= -15.0:
                        exit_triggered = True
                        exit_price = max(bar["close"], tr.entry_price * 1.25)
                        exit_reason = "Parabolic Climax Exit (Blow-off Top Protection)"
                        stage_name = "Stage 5: Climax Exit"

                # -------------------------------------------------------------
                # STAGE 4: SECULAR COMPOUNDING (Peak Gain >= 50%)
                # -------------------------------------------------------------
                elif gain_from_entry >= 50.0 and not exit_triggered:
                    # Hard floor locked at +25%
                    if bar["low"] <= tr.entry_price * 1.25:
                        exit_triggered = True
                        exit_price = max(tr.entry_price * 1.25, bar["open"])
                        exit_reason = "Secular Profit Floor (+25% Locked)"
                        stage_name = "Stage 4: Secular Compounding"
                    elif bar["close"] < bar["ema100"] and dip_from_peak <= -20.0:
                        exit_triggered = True
                        exit_price = max(bar["close"], tr.entry_price * 1.25)
                        exit_reason = "Secular Trend Ended (100 EMA Break & -20% Drop)"
                        stage_name = "Stage 4: Secular Compounding"

                # -------------------------------------------------------------
                # STAGE 3: PROGRESSIVE RATCHET (+30% <= Peak Gain < +50%)
                # -------------------------------------------------------------
                elif 30.0 <= gain_from_entry < 50.0 and not exit_triggered:
                    floor_price = max(tr.entry_price * 1.12, bar["ema50"])
                    if bar["close"] < floor_price or bar["low"] <= tr.entry_price * 1.12:
                        exit_triggered = True
                        exit_price = min(floor_price, bar["open"]) if bar["open"] < floor_price else floor_price
                        exit_price = max(exit_price, tr.entry_price * 1.12)
                        exit_reason = "Progressive Floor Ratchet (+12% / 50 EMA Locked)"
                        stage_name = "Stage 3: Progressive Ratchet"

                # -------------------------------------------------------------
                # STAGE 2: CAPITAL PRESERVATION (+15% <= Peak Gain < +30%)
                # -------------------------------------------------------------
                elif 15.0 <= gain_from_entry < 30.0 and not exit_triggered:
                    be_floor = tr.entry_price * 1.02
                    if bar["low"] <= be_floor:
                        exit_triggered = True
                        exit_price = min(be_floor, bar["open"])
                        exit_reason = "Breakeven Floor (+2% Profit Locked)"
                        stage_name = "Stage 2: Capital Preservation"

                # -------------------------------------------------------------
                # STAGE 1: IGNITION DEFENSE (Peak Gain < +15%)
                # -------------------------------------------------------------
                elif gain_from_entry < 15.0 and not exit_triggered:
                    # Closing-basis stop: Max(-8%, Entry - 2.5 * ATR_14)
                    atr_entry = bar["atr_14"] if pd.notnull(bar["atr_14"]) else bar["close"] * 0.03
                    closing_stop = max(tr.entry_price * 0.92, tr.entry_price - 2.5 * atr_entry)

                    # Intraday extreme circuit breaker (-10%)
                    if bar["low"] <= tr.entry_price * 0.90:
                        exit_triggered = True
                        exit_price = min(tr.entry_price * 0.90, bar["open"])
                        exit_reason = "Extreme Circuit Breaker (-10% Hard Stop)"
                        stage_name = "Stage 1: Ignition Defense"
                    elif bar["close"] <= closing_stop:
                        exit_triggered = True
                        exit_price = bar["close"]
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
                    sell_friction = exit_price * tr.shares * self.cost_per_side
                    net_proceeds = (exit_price * tr.shares) - sell_friction
                    total_friction_paid += sell_friction
                    cash += net_proceeds

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
                    tr.bars_held += 1

            for sym in symbols_to_close:
                del active_trades[sym]

            # B. Check Previous Day Signals for Next Day (cur_date) Open Entry
            orig_idx = date_to_idx.get(cur_date, 0)
            if orig_idx > 0:
                prev_date = all_dates[orig_idx - 1]
                regime_ok = bench_regime_dict.get(prev_date, True)

                # Only evaluate entries if Benchmark Regime is Bullish (Regime Filter)
                if regime_ok:
                    candidates: list[dict[str, Any]] = []
                    for sym, s_df in symbol_data.items():
                        if sym in active_trades:
                            continue  # No overlapping trades in same symbol
                        if prev_date in s_df.index and s_df.loc[prev_date, "raw_signal"]:
                            p_row = s_df.loc[prev_date]
                            candidates.append({
                                "symbol": sym,
                                "rs_score": p_row["rs_score"],
                                "rvol": p_row["rvol"],
                                "atr_14": p_row["atr_14"],
                            })

                    # Cross-Sectional Ranking: Sort by RS * RVOL Score Descending
                    candidates.sort(key=lambda x: x["rs_score"], reverse=True)

                    for cand in candidates:
                        sym = cand["symbol"]
                        s_df = symbol_data[sym]
                        if cur_date not in s_df.index:
                            continue
                        bar = s_df.loc[cur_date]

                        # Upper Circuit Rejection: open == high == low
                        if bar["open"] == bar["high"] and bar["high"] == bar["low"]:
                            continue

                        # Check Free Slot availability
                        if len(active_trades) >= self.max_slots:
                            break

                        # Calculate Total Current Portfolio Equity
                        mtm_val = sum(
                            symbol_data[s].loc[cur_date]["close"] * t.shares
                            if cur_date in symbol_data[s].index else t.invested_capital
                            for s, t in active_trades.items()
                        )
                        current_equity = cash + mtm_val

                        # 1% Equity Risk Parity Sizing
                        dollar_risk = current_equity * self.risk_per_trade_pct
                        atr_val = cand["atr_14"] if pd.notnull(cand["atr_14"]) else bar["open"] * 0.03
                        unit_risk = max(bar["open"] * 0.08, 2.5 * atr_val)
                        target_shares = dollar_risk / unit_risk
                        target_capital = target_shares * bar["open"]

                        # Cap at max slot allocation (e.g. 1/15th of equity)
                        max_slot_capital = current_equity / self.max_slots
                        alloc_capital = min(target_capital, max_slot_capital, cash)

                        if alloc_capital < 10_000.0 or cash < alloc_capital:
                            continue

                        # Entry Execution at Day t+1 Open with Friction
                        raw_entry = bar["open"]
                        entry_friction = alloc_capital * self.cost_per_side
                        total_friction_paid += entry_friction
                        actual_invest = alloc_capital - entry_friction
                        shares = actual_invest / raw_entry
                        cash -= alloc_capital

                        entry_price_with_friction = raw_entry * (1.0 + self.cost_per_side)

                        active_trades[sym] = UpgradedTrade(
                            symbol=sym,
                            entry_date=cur_date,
                            entry_price=raw_entry,
                            entry_price_with_friction=entry_price_with_friction,
                            shares=shares,
                            invested_capital=alloc_capital,
                            dollar_risk=dollar_risk,
                            peak_price=raw_entry,
                        )

            # C. Record Daily Portfolio Mark-to-Market Equity
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

        # 4. Generate Performance DataFrames & Statistics
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

            yr_nifty_end = grp["nifty_close"].dropna().iloc[-1]
            yr_nifty_ret = (yr_nifty_end / prev_nifty - 1.0) * 100.0

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
        )
