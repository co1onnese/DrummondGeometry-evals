from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import pytest

from dgas.backtesting import BacktestResult, PortfolioSnapshot, SimulationConfig, Trade, persist_backtest
from dgas.backtesting.metrics import PerformanceSummary
from dgas.backtesting.entities import PositionSide


class FakeCursor:
    def __init__(self, expected_backtest_id: int = 123) -> None:
        self.executed: list[tuple[str, tuple[Any, ...]]] = []
        self.executemany_calls: list[tuple[str, list[tuple[Any, ...]]]] = []
        self._backtest_id = expected_backtest_id

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:  # pragma: no cover - no cleanup needed
        return None

    def execute(self, sql: str, params: tuple[Any, ...]) -> None:
        self.executed.append((sql, params))

    def fetchone(self) -> tuple[int]:
        return (self._backtest_id,)

    def executemany(self, sql: str, rows: list[tuple[Any, ...]]) -> None:
        self.executemany_calls.append((sql, rows))


class FakeConnection:
    def __init__(self, cursor: FakeCursor) -> None:
        self.cursor_impl = cursor
        self.committed = False
        self.rolled_back = False

    def cursor(self) -> FakeCursor:
        return self.cursor_impl

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True


def _example_backtest_result() -> BacktestResult:
    start = datetime(2023, 1, 1, tzinfo=timezone.utc)
    snapshots = [
        PortfolioSnapshot(timestamp=start, equity=Decimal("100000"), cash=Decimal("100000")),
        PortfolioSnapshot(timestamp=start.replace(month=2), equity=Decimal("105000"), cash=Decimal("105000")),
    ]
    trades = [
        Trade(
            symbol="AAPL",
            side=PositionSide.LONG,
            quantity=Decimal("10"),
            entry_time=start,
            exit_time=start.replace(month=2),
            entry_price=Decimal("100"),
            exit_price=Decimal("105"),
            gross_profit=Decimal("500"),
            net_profit=Decimal("480"),
            commission_paid=Decimal("20"),
        )
    ]

    return BacktestResult(
        symbol="AAPL",
        strategy_name="multi_timeframe",
        config=SimulationConfig(initial_capital=Decimal("100000")),
        trades=trades,
        equity_curve=snapshots,
        starting_cash=Decimal("100000"),
        ending_cash=Decimal("105000"),
        ending_equity=Decimal("105000"),
        metadata={"note": "unit-test"},
    )


def _example_performance() -> PerformanceSummary:
    return PerformanceSummary(
        total_return=Decimal("0.05"),
        annualized_return=None,
        volatility=Decimal("0.01"),
        sharpe_ratio=Decimal("1.5"),
        sortino_ratio=None,
        max_drawdown=Decimal("-0.01"),
        max_drawdown_duration=2,
        total_trades=1,
        winning_trades=1,
        losing_trades=0,
        win_rate=Decimal("1"),
        avg_win=Decimal("480"),
        avg_loss=None,
        profit_factor=Decimal("10"),
        net_profit=Decimal("5000"),
    )


def test_persist_backtest_writes_results(monkeypatch: pytest.MonkeyPatch) -> None:
    cursor = FakeCursor(expected_backtest_id=321)
    conn = FakeConnection(cursor)

    monkeypatch.setattr("dgas.backtesting.persistence.get_symbol_id", lambda _conn, _symbol: 42)

    result = _example_backtest_result()
    summary = _example_performance()

    backtest_id = persist_backtest(result, summary, metadata={"run_id": "test-1"}, conn=conn)

    assert backtest_id == 321
    assert conn.committed and not conn.rolled_back

    insert_sql, params = cursor.executed[0]
    assert "INSERT INTO backtest_results" in insert_sql
    # Ensure JSON metadata includes strategy config overrides
    json_param = params[21]
    config_payload = getattr(json_param, "obj", json_param)
    assert config_payload["note"] == "unit-test"
    assert config_payload["run_id"] == "test-1"

    trade_sql, rows = cursor.executemany_calls[0]
    assert "INSERT INTO backtest_trades" in trade_sql
    assert len(rows) == 1
    (_, _, entry_ts, exit_ts, entry_price, exit_price, position_size, trade_type, *_rest) = rows[0]
    assert trade_type == "long"
    assert position_size == Decimal("10")
    assert exit_price == Decimal("105")
    assert entry_ts.tzinfo is not None and exit_ts.tzinfo is not None


def test_persist_backtest_raises_when_symbol_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    cursor = FakeCursor()
    conn = FakeConnection(cursor)

    monkeypatch.setattr("dgas.backtesting.persistence.get_symbol_id", lambda _conn, _symbol: None)

    with pytest.raises(ValueError, match="Symbol AAPL not found"):
        persist_backtest(_example_backtest_result(), _example_performance(), conn=conn)
