from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from dgas.backtesting import (
    BacktestResult,
    PortfolioSnapshot,
    PositionSide,
    SimulationConfig,
    Trade,
    calculate_performance,
)


def _snapshot(ts: datetime, equity: str, cash: str) -> PortfolioSnapshot:
    return PortfolioSnapshot(
        timestamp=ts,
        equity=Decimal(equity),
        cash=Decimal(cash),
    )


def _trade(
    side: PositionSide,
    entry: datetime,
    exit: datetime,
    qty: str,
    entry_price: str,
    exit_price: str,
    gross: str,
    net: str,
    commission: str,
) -> Trade:
    return Trade(
        symbol="AAPL",
        side=side,
        quantity=Decimal(qty),
        entry_time=entry,
        exit_time=exit,
        entry_price=Decimal(entry_price),
        exit_price=Decimal(exit_price),
        gross_profit=Decimal(gross),
        net_profit=Decimal(net),
        commission_paid=Decimal(commission),
    )


def test_calculate_performance_produces_expected_summary() -> None:
    start = datetime(2023, 1, 1, tzinfo=timezone.utc)
    snapshots = [
        _snapshot(start, "100000", "100000"),
        _snapshot(start.replace(month=2), "105000", "105000"),
        _snapshot(start.replace(month=3), "103000", "103000"),
        _snapshot(start.replace(month=4), "110000", "110000"),
    ]

    trades = [
        _trade(
            PositionSide.LONG,
            entry=start,
            exit=start.replace(month=2),
            qty="10",
            entry_price="100",
            exit_price="120",
            gross="2000",
            net="1800",
            commission="200",
        ),
        _trade(
            PositionSide.LONG,
            entry=start.replace(month=2, day=5),
            exit=start.replace(month=3, day=5),
            qty="5",
            entry_price="120",
            exit_price="110",
            gross="-500",
            net="-550",
            commission="50",
        ),
    ]

    result = BacktestResult(
        symbol="AAPL",
        strategy_name="multi_timeframe",
        config=SimulationConfig(initial_capital=Decimal("100000")),
        trades=trades,
        equity_curve=snapshots,
        starting_cash=Decimal("100000"),
        ending_cash=Decimal("110000"),
        ending_equity=Decimal("110000"),
        metadata={},
    )

    summary = calculate_performance(result)

    assert summary.total_return == Decimal("0.1")
    assert float(summary.max_drawdown) == pytest.approx(-0.019047619, rel=1e-6)
    assert summary.total_trades == 2
    assert summary.winning_trades == 1
    assert summary.losing_trades == 1
    assert summary.win_rate == Decimal("0.5")
    assert summary.avg_win == Decimal("1800")
    assert summary.avg_loss == Decimal("-550")
    assert summary.profit_factor == Decimal("1800") / Decimal("550")
    assert summary.net_profit == Decimal("10000")

    # Volatility, Sharpe, Sortino should be populated (not None)
    assert summary.volatility is not None
    assert summary.sharpe_ratio is not None
    # Sortino may be None if there are no downside returns in the sample
    assert summary.sortino_ratio is None or isinstance(summary.sortino_ratio, Decimal)
