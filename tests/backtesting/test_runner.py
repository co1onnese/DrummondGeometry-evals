from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from dgas.backtesting import (
    BacktestBar,
    BacktestDataset,
    BacktestRequest,
    BacktestResult,
    BacktestRunner,
    PortfolioSnapshot,
    PositionSide,
    SimulationConfig,
    Trade,
)
from dgas.backtesting.metrics import PerformanceSummary
from dgas.data.models import IntervalData


def _interval_data(timestamp: datetime, close: str) -> IntervalData:
    return IntervalData(
        symbol="AAPL",
        exchange="NASDAQ",
        timestamp=timestamp.isoformat(),
        interval="1h",
        open=Decimal(close),
        high=Decimal(close),
        low=Decimal(close),
        close=Decimal(close),
        adjusted_close=Decimal(close),
        volume=1,
    )


def _backtest_result(start: datetime) -> BacktestResult:
    snapshots = [
        PortfolioSnapshot(timestamp=start, equity=Decimal("100000"), cash=Decimal("100000")),
        PortfolioSnapshot(timestamp=start.replace(hour=3), equity=Decimal("101000"), cash=Decimal("101000")),
    ]
    trades = [
        Trade(
            symbol="AAPL",
            side=PositionSide.LONG,
            quantity=Decimal("1"),
            entry_time=start,
            exit_time=start.replace(hour=3),
            entry_price=Decimal("100"),
            exit_price=Decimal("101"),
            gross_profit=Decimal("1"),
            net_profit=Decimal("1"),
            commission_paid=Decimal("0"),
        )
    ]
    return BacktestResult(
        symbol="AAPL",
        strategy_name="stub",
        config=SimulationConfig(initial_capital=Decimal("100000")),
        trades=trades,
        equity_curve=snapshots,
        starting_cash=Decimal("100000"),
        ending_cash=Decimal("101000"),
        ending_equity=Decimal("101000"),
        metadata={}
    )


class StubEngine:
    def __init__(self, result: BacktestResult) -> None:
        self.result = result
        self.calls: list[tuple[BacktestDataset, object]] = []

    def run(self, dataset: BacktestDataset, strategy) -> BacktestResult:  # pragma: no cover - simple forwarder
        self.calls.append((dataset, strategy))
        strategy.prepare([bar.bar for bar in dataset.bars])
        return self.result


class StubStrategy:
    def __init__(self) -> None:
        self.prepared = False

    def prepare(self, data) -> None:
        self.prepared = True

    def on_bar(self, context):  # pragma: no cover - no signals
        return []


class StubPerformance(PerformanceSummary):
    def __init__(self) -> None:
        super().__init__(
            total_return=Decimal("0.01"),
            annualized_return=None,
            volatility=None,
            sharpe_ratio=None,
            sortino_ratio=None,
            max_drawdown=Decimal("0"),
            max_drawdown_duration=0,
            total_trades=1,
            winning_trades=1,
            losing_trades=0,
            win_rate=Decimal("1"),
            avg_win=Decimal("1"),
            avg_loss=None,
            profit_factor=None,
            net_profit=Decimal("1000"),
        )


def test_backtest_runner_executes_strategy_and_persists(monkeypatch: pytest.MonkeyPatch) -> None:
    start = datetime(2023, 1, 1, tzinfo=timezone.utc)
    bars = [
        BacktestBar(bar=_interval_data(start, "100")),
        BacktestBar(bar=_interval_data(start.replace(hour=1), "101")),
    ]
    dataset = BacktestDataset(symbol="AAPL", interval="1h", bars=bars)

    monkeypatch.setattr("dgas.backtesting.runner.load_dataset", lambda *args, **kwargs: dataset)

    stub_strategy = StubStrategy()
    monkeypatch.setattr("dgas.backtesting.runner.instantiate_strategy", lambda *args, **kwargs: stub_strategy)

    test_result = _backtest_result(start)
    engine = StubEngine(test_result)

    performance = StubPerformance()
    monkeypatch.setattr("dgas.backtesting.runner.calculate_performance", lambda _result, **_: performance)

    persist_calls: list[tuple[BacktestResult, PerformanceSummary]] = []
    monkeypatch.setattr(
        "dgas.backtesting.runner.persist_backtest",
        lambda result, perf, metadata=None: persist_calls.append((result, perf)) or 99,
    )

    monkeypatch.setattr("dgas.backtesting.runner.get_symbol_id", lambda conn, symbol: 7)
    monkeypatch.setattr("dgas.backtesting.runner.get_connection", lambda: _DummyContextManager())

    runner = BacktestRunner(engine=engine)
    request = BacktestRequest(
        symbols=["AAPL"],
        interval="1h",
        start=start,
        end=start.replace(hour=2),
        strategy_name="stub",
        simulation_config=SimulationConfig(initial_capital=Decimal("100000")),
        risk_free_rate=Decimal("0"),
        persist_results=True,
    )

    results = runner.run(request)

    assert len(results) == 1
    run = results[0]
    assert run.symbol == "AAPL"
    assert run.result is test_result
    assert run.performance is performance
    assert run.persisted_id == 99
    assert stub_strategy.prepared
    assert persist_calls[0][0] is test_result


def test_backtest_runner_skips_persistence_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    start = datetime(2023, 1, 1, tzinfo=timezone.utc)
    data = BacktestDataset(
        symbol="AAPL",
        interval="1h",
        bars=[
            BacktestBar(bar=_interval_data(start, "100")),
            BacktestBar(bar=_interval_data(start.replace(hour=1), "101")),
        ],
    )

    monkeypatch.setattr("dgas.backtesting.runner.load_dataset", lambda *args, **kwargs: data)
    monkeypatch.setattr("dgas.backtesting.runner.instantiate_strategy", lambda *args, **kwargs: StubStrategy())

    engine = StubEngine(_backtest_result(start))
    monkeypatch.setattr("dgas.backtesting.runner.calculate_performance", lambda _result, **_: StubPerformance())

    called = {"value": False}

    def _persist(*args, **kwargs):  # pragma: no cover - should not execute
        called["value"] = True
        return 0

    monkeypatch.setattr("dgas.backtesting.runner.persist_backtest", _persist)

    runner = BacktestRunner(engine=engine)
    request = BacktestRequest(
        symbols=["AAPL"],
        interval="1h",
        persist_results=False,
    )

    results = runner.run(request)
    assert results[0].persisted_id is None
    assert not called["value"]


class _DummyContextManager:
    def __enter__(self):  # pragma: no cover - simple stub
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):  # pragma: no cover
        return False
