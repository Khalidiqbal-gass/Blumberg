"""Point-in-time walk-forward backtesting simulator with realistic costs and slippage."""
from __future__ import annotations

from dataclasses import dataclass
import numpy as np
import pandas as pd


@dataclass
class BacktestResult:
    trades_df: pd.DataFrame
    equity_curve: pd.DataFrame
    total_trades: int
    win_rate_pct: float
    avg_net_return_pct: float
    profit_factor: float
    max_drawdown_pct: float
    total_net_return_pct: float


def run_point_in_time_backtest(
    features_df: pd.DataFrame,
    score_threshold: float = 65.0,
    holding_days: int = 20,
    stop_loss_pct: float = 0.08,  # 8% stop loss
    profit_target_pct: float = 0.20,  # 20% target
    cost_bps_per_side: float = 15.0,  # 15 bps slippage + STT/brokerage
) -> BacktestResult:
    """Simulate trading radar signals using next-session fills and realistic execution costs."""
    if features_df.empty:
        empty_trades = pd.DataFrame()
        empty_curve = pd.DataFrame({"date": [], "equity": []})
        return BacktestResult(
            trades_df=empty_trades,
            equity_curve=empty_curve,
            total_trades=0,
            win_rate_pct=0.0,
            avg_net_return_pct=0.0,
            profit_factor=0.0,
            max_drawdown_pct=0.0,
            total_net_return_pct=0.0,
        )

    # Reconstruct historical signal trigger dates
    # A signal triggers when: return_5d > 0 and relative_volume_20d >= 1.5 and return_20d > 0
    df = features_df.sort_values(["symbol", "date"]).copy()
    round_trip_cost = (cost_bps_per_side * 2.0) / 10_000.0

    trades: list[dict] = []

    for sym, group in df.groupby("symbol", sort=False):
        sub = group.reset_index(drop=True)
        n = len(sub)
        in_trade = False
        entry_idx = 0
        entry_price = 0.0
        entry_date = None

        for i in range(n - 1):
            row = sub.iloc[i]

            if in_trade:
                curr_price = float(sub.iloc[i]["close"])
                gross_ret = (curr_price / entry_price) - 1.0
                days_held = i - entry_idx

                hit_stop = gross_ret <= -stop_loss_pct
                hit_target = gross_ret >= profit_target_pct
                time_up = days_held >= holding_days

                if hit_stop or hit_target or time_up:
                    exit_price = curr_price
                    exit_date = sub.iloc[i]["date"]
                    net_ret = (1.0 + gross_ret) * (1.0 - round_trip_cost) - 1.0

                    reason = "STOP_LOSS" if hit_stop else ("PROFIT_TARGET" if hit_target else "TIME_EXIT")
                    trades.append({
                        "symbol": sym,
                        "entry_date": entry_date,
                        "entry_price": np.round(entry_price, 2),
                        "exit_date": exit_date,
                        "exit_price": np.round(exit_price, 2),
                        "days_held": days_held,
                        "gross_return_pct": np.round(gross_ret * 100, 2),
                        "net_return_pct": np.round(net_ret * 100, 2),
                        "exit_reason": reason,
                    })
                    in_trade = False

            else:
                # Check for signal at day i
                rvol = float(row.get("relative_volume_20d") or 1.0)
                ret_5d = float(row.get("return_5d") or 0.0)
                ret_20d = float(row.get("return_20d") or 0.0)

                signal_triggered = (rvol >= 1.5) and (ret_5d > 0.02) and (ret_20d > 0.0)

                if signal_triggered and (i + 1 < n):
                    # Next-tradable session entry (day i+1 open or close)
                    entry_idx = i + 1
                    entry_price = float(sub.iloc[entry_idx]["open"])
                    entry_date = sub.iloc[entry_idx]["date"]
                    in_trade = True

    trades_df = pd.DataFrame(trades)
    if trades_df.empty:
        empty_curve = pd.DataFrame({"date": [], "equity": []})
        return BacktestResult(
            trades_df=trades_df,
            equity_curve=empty_curve,
            total_trades=0,
            win_rate_pct=0.0,
            avg_net_return_pct=0.0,
            profit_factor=0.0,
            max_drawdown_pct=0.0,
            total_net_return_pct=0.0,
        )

    trades_df = trades_df.sort_values("exit_date").reset_index(drop=True)

    # Compute aggregate metrics
    total_trades = len(trades_df)
    win_trades = trades_df[trades_df["net_return_pct"] > 0]
    loss_trades = trades_df[trades_df["net_return_pct"] <= 0]

    win_rate = (len(win_trades) / total_trades) * 100.0 if total_trades > 0 else 0.0
    avg_net = float(trades_df["net_return_pct"].mean())

    total_gains = win_trades["net_return_pct"].sum()
    total_losses = np.abs(loss_trades["net_return_pct"].sum())
    profit_factor = (total_gains / total_losses) if total_losses > 0 else float("inf")

    # Cumulative equity curve (starting capital base 100)
    # Using compounded returns
    trades_df["compound_factor"] = 1.0 + (trades_df["net_return_pct"] / 100.0)
    trades_df["equity"] = 100.0 * np.cumprod(trades_df["compound_factor"])

    equity_series = trades_df["equity"]
    peak = equity_series.cummax()
    drawdown = (equity_series - peak) / peak
    max_dd = float(np.abs(drawdown.min())) * 100.0
    total_net = float(trades_df["equity"].iloc[-1] - 100.0)

    equity_curve = pd.DataFrame({
        "date": trades_df["exit_date"],
        "equity": np.round(trades_df["equity"], 2),
        "drawdown_pct": np.round(drawdown * 100, 2),
    })

    return BacktestResult(
        trades_df=trades_df,
        equity_curve=equity_curve,
        total_trades=total_trades,
        win_rate_pct=np.round(win_rate, 1),
        avg_net_return_pct=np.round(avg_net, 2),
        profit_factor=np.round(profit_factor, 2),
        max_drawdown_pct=np.round(max_dd, 1),
        total_net_return_pct=np.round(total_net, 2),
    )
