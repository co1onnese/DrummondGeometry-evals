"""Performance metric calculations for backtests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from math import sqrt
from statistics import mean, pstdev
from typing import Iterable, List, Sequence

from .entities import BacktestResult, PortfolioSnapshot, Trade


@dataclass(frozen=True)
class PerformanceSummary:
    """Aggregated performance statistics for a backtest run."""

    total_return: Decimal
    annualized_return: Decimal | None
    volatility: Decimal | None
    sharpe_ratio: Decimal | None
    sortino_ratio: Decimal | None
    max_drawdown: Decimal
    max_drawdown_duration: int
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: Decimal | None
    avg_win: Decimal | None
    avg_loss: Decimal | None
    profit_factor: Decimal | None
    net_profit: Decimal


def calculate_performance(
    result: BacktestResult,
    *,
    risk_free_rate: Decimal | float = Decimal("0"),
) -> PerformanceSummary:
    """Compute performance summary for a completed backtest."""

    total_return = _total_return(result)
    annualized_return = _annualized_return(result, total_return)

    returns = _equity_returns(result.equity_curve)
    volatility = _volatility(returns)
    sharpe = _sharpe_ratio(returns, volatility, risk_free_rate, result.equity_curve)
    sortino = _sortino_ratio(returns, risk_free_rate, result.equity_curve)

    max_dd, dd_duration = _max_drawdown(result.equity_curve)

    trade_stats = _trade_statistics(result.trades)

    return PerformanceSummary(
        total_return=total_return,
        annualized_return=annualized_return,
        volatility=volatility,
        sharpe_ratio=sharpe,
        sortino_ratio=sortino,
        max_drawdown=max_dd,
        max_drawdown_duration=dd_duration,
        total_trades=trade_stats["total_trades"],
        winning_trades=trade_stats["winning_trades"],
        losing_trades=trade_stats["losing_trades"],
        win_rate=trade_stats["win_rate"],
        avg_win=trade_stats["avg_win"],
        avg_loss=trade_stats["avg_loss"],
        profit_factor=trade_stats["profit_factor"],
        net_profit=result.ending_equity - result.starting_cash,
    )


# ---------------------------------------------------------------------------
# Return/volatility helpers
# ---------------------------------------------------------------------------


def _total_return(result: BacktestResult) -> Decimal:
    start = result.starting_cash
    if start == 0:
        return Decimal("0")
    return (result.ending_equity - start) / start


def _annualized_return(result: BacktestResult, total_return: Decimal) -> Decimal | None:
    if not result.equity_curve:
        return None
    start_time = result.equity_curve[0].timestamp
    end_time = result.equity_curve[-1].timestamp
    years = _years_between(start_time, end_time)
    if years <= 0:
        return None

    base = 1 + float(total_return)
    if base <= 0:
        return None
    value = base ** (1 / years) - 1
    return Decimal(str(value))


def _years_between(start: datetime, end: datetime) -> float:
    if end <= start:
        return 0.0
    return (end - start).total_seconds() / (365.25 * 24 * 3600)


def _equity_returns(equity_curve: List[PortfolioSnapshot]) -> List[float]:
    returns: list[float] = []
    if len(equity_curve) < 2:
        return returns

    prev_equity = float(equity_curve[0].equity)
    for snapshot in equity_curve[1:]:
        curr = float(snapshot.equity)
        if prev_equity > 0:
            returns.append((curr - prev_equity) / prev_equity)
        prev_equity = curr
    return returns


def _volatility(returns: Sequence[float]) -> Decimal | None:
    if len(returns) < 2:
        return None
    value = pstdev(returns)
    return Decimal(str(value))


def _periods_per_year(equity_curve: List[PortfolioSnapshot]) -> float:
    if len(equity_curve) < 2:
        return 0.0
    years = _years_between(equity_curve[0].timestamp, equity_curve[-1].timestamp)
    if years <= 0:
        return 0.0
    return len(equity_curve[1:]) / years


def _sharpe_ratio(
    returns: Sequence[float],
    volatility: Decimal | None,
    risk_free_rate: Decimal | float,
    equity_curve: List[PortfolioSnapshot],
) -> Decimal | None:
    if not returns or volatility is None:
        return None

    period_rf = float(risk_free_rate)
    avg_return = mean(returns)
    excess = avg_return - period_rf
    vol = float(volatility)
    if vol == 0:
        return None

    periods_per_year = _periods_per_year(equity_curve)
    if periods_per_year <= 0:
        return None

    sharpe = (excess / vol) * sqrt(periods_per_year)
    return Decimal(str(sharpe))


def _sortino_ratio(
    returns: Sequence[float],
    risk_free_rate: Decimal | float,
    equity_curve: List[PortfolioSnapshot],
) -> Decimal | None:
    if not returns:
        return None

    downside = [r for r in returns if r < 0]
    if not downside:
        return None

    downside_dev = pstdev(downside)
    if downside_dev == 0:
        return None

    avg_return = mean(returns)
    periods_per_year = _periods_per_year(equity_curve)
    if periods_per_year <= 0:
        return None

    excess = avg_return - float(risk_free_rate)
    sortino = (excess / downside_dev) * sqrt(periods_per_year)
    return Decimal(str(sortino))


def _max_drawdown(equity_curve: List[PortfolioSnapshot]) -> tuple[Decimal, int]:
    if not equity_curve:
        return (Decimal("0"), 0)

    peak = equity_curve[0].equity
    max_drawdown = Decimal("0")
    current_duration = 0
    max_duration = 0

    for snapshot in equity_curve[1:]:
        if snapshot.equity >= peak:
            peak = snapshot.equity
            current_duration = 0
            continue

        current_duration += 1
        drawdown = (snapshot.equity - peak) / peak if peak != 0 else Decimal("0")
        if drawdown < max_drawdown:
            max_drawdown = drawdown
        if current_duration > max_duration:
            max_duration = current_duration

    return max_drawdown, max_duration


# ---------------------------------------------------------------------------
# Trade statistics
# ---------------------------------------------------------------------------


def _trade_statistics(trades: Iterable[Trade]) -> dict[str, Decimal | int | None]:
    total_trades = 0
    wins: list[Decimal] = []
    losses: list[Decimal] = []

    for trade in trades:
        total_trades += 1
        if trade.net_profit > 0:
            wins.append(trade.net_profit)
        elif trade.net_profit < 0:
            losses.append(trade.net_profit)

    winning_trades = len(wins)
    losing_trades = len(losses)

    win_rate = (
        Decimal(winning_trades) / Decimal(total_trades)
        if total_trades > 0
        else None
    )

    avg_win = (sum(wins) / Decimal(len(wins))) if wins else None
    avg_loss = (sum(losses) / Decimal(len(losses))) if losses else None

    if wins and losses:
        total_wins = sum(wins)
        total_losses = abs(sum(losses))
        # Guard against division by zero
        if total_losses > 0:
            profit_factor = total_wins / total_losses
        else:
            profit_factor = Decimal("9999.9999")
    elif wins and not losses:
        # Cap infinity to max value for NUMERIC(8,4) field
        profit_factor = Decimal("9999.9999")
    else:
        profit_factor = None

    # Cap extreme values to prevent database overflow
    def _cap_decimal(value: Decimal | None, max_val: Decimal = Decimal("9999.9999")) -> Decimal | None:
        """Cap decimal values to prevent database overflow."""
        if value is None:
            return None
        # Check for infinity
        if value == Decimal("Infinity") or value > max_val:
            return max_val
        # Check for very small negative values
        if value < -max_val:
            return -max_val
        return value

    profit_factor = _cap_decimal(profit_factor)

    return {
        "total_trades": total_trades,
        "winning_trades": winning_trades,
        "losing_trades": losing_trades,
        "win_rate": win_rate,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "profit_factor": profit_factor,
    }


__all__ = ["PerformanceSummary", "calculate_performance"]
