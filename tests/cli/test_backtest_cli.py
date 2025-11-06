from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import json
import pytest

from dgas.backtesting import (
    BacktestBar,
    BacktestDataset,
    BacktestResult,
    PerformanceSummary,
    PortfolioSnapshot,
    PositionSide,
    SimulationConfig,
    Trade,
)
from dgas.cli.backtest import console, run_backtest_command
from dgas.data.models import IntervalData


def _fake_run_result(symbol: str) -> tuple[BacktestDataset, BacktestResult, PerformanceSummary]:
    start = datetime(2023, 1, 1, tzinfo=timezone.utc)
    dataset = BacktestDataset(
        symbol=symbol,
        interval="1h",
        bars=[
            BacktestBar(bar=_interval(symbol, start, "100")),
            BacktestBar(bar=_interval(symbol, start.replace(hour=1), "101")),
        ],
    )

    result = BacktestResult(
        symbol=symbol,
        strategy_name="multi_timeframe",
        config=SimulationConfig(initial_capital=Decimal("100000")),
        trades=[
            Trade(
                symbol=symbol,
                side=PositionSide.LONG,
                quantity=Decimal("1"),
                entry_time=start,
                exit_time=start.replace(hour=1),
                entry_price=Decimal("100"),
                exit_price=Decimal("101"),
                gross_profit=Decimal("1"),
                net_profit=Decimal("1"),
                commission_paid=Decimal("0"),
            )
        ],
        equity_curve=[
            PortfolioSnapshot(timestamp=start, equity=Decimal("100000"), cash=Decimal("100000")),
            PortfolioSnapshot(timestamp=start.replace(hour=1), equity=Decimal("101000"), cash=Decimal("101000")),
        ],
        starting_cash=Decimal("100000"),
        ending_cash=Decimal("101000"),
        ending_equity=Decimal("101000"),
        metadata={},
    )

    performance = PerformanceSummary(
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

    return dataset, result, performance


def _interval(symbol: str, timestamp: datetime, price: str) -> IntervalData:
    return IntervalData(
        symbol=symbol,
        exchange="NASDAQ",
        timestamp=timestamp.isoformat(),
        interval="1h",
        open=Decimal(price),
        high=Decimal(price),
        low=Decimal(price),
        close=Decimal(price),
        adjusted_close=Decimal(price),
        volume=1,
    )


class StubRunner:
    def __init__(self, result):
        self.result = result
        self.last_request = None

    def run(self, request):
        self.last_request = request
        return [self.result]


@pytest.fixture
def stub_run(monkeypatch: pytest.MonkeyPatch):
    dataset, result, performance = _fake_run_result("AAPL")

    from dgas.backtesting.runner import BacktestRunResult

    run_result = BacktestRunResult(
        symbol="AAPL",
        dataset=dataset,
        result=result,
        performance=performance,
        persisted_id=42,
    )

    stub_runner = StubRunner(run_result)
    monkeypatch.setattr("dgas.cli.backtest.BacktestRunner", lambda: stub_runner)
    return stub_runner


def test_run_backtest_command_summary_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stub_run: StubRunner) -> None:
    md_calls = []
    json_calls = []
    monkeypatch.setattr("dgas.cli.backtest.export_markdown", lambda run, path: md_calls.append(path))
    monkeypatch.setattr("dgas.cli.backtest.export_json", lambda run, path: json_calls.append(path))

    report_dir = tmp_path / "reports"
    json_dir = tmp_path / "json"

    with console.capture() as capture:
        exit_code = run_backtest_command(
            symbols=["AAPL"],
            interval="1h",
            strategy="multi_timeframe",
            strategy_params={"risk": "0.5"},
            start="2023-01-01",
            end="2023-01-02",
            initial_capital=Decimal("50000"),
            commission_rate=Decimal("0.0001"),
            slippage_bps=Decimal("0.0"),
            risk_free_rate=Decimal("0.01"),
            persist=True,
            output_format="summary",
            report_path=report_dir,
            json_path=json_dir,
            limit_bars=100,
        )

    output = capture.get()
    assert exit_code == 0
    assert "Backtest Summary" in output
    assert "AAPL" in output
    assert stub_run.last_request.simulation_config.initial_capital == Decimal("50000")
    assert stub_run.last_request.strategy_params["risk"] == "0.5"
    assert stub_run.last_request.limit == 100

    assert len(md_calls) == 1
    assert len(json_calls) == 1
    assert md_calls[0].suffix == ".md"
    assert json_calls[0].suffix == ".json"


def test_run_backtest_command_json_output(monkeypatch: pytest.MonkeyPatch, stub_run: StubRunner) -> None:
    with console.capture() as capture:
        exit_code = run_backtest_command(
            symbols=["AAPL"],
            interval="1h",
            strategy="multi_timeframe",
            strategy_params={},
            start=None,
            end=None,
            initial_capital=Decimal("100000"),
            commission_rate=Decimal("0"),
            slippage_bps=Decimal("0"),
            risk_free_rate=Decimal("0"),
            persist=False,
            output_format="json",
            report_path=None,
            json_path=None,
            limit_bars=None,
        )

    output = capture.get()
    assert exit_code == 0
    parsed = json.loads(output)
    assert parsed[0]["symbol"] == "AAPL"
    assert parsed[0]["performance"]["total_return"] == pytest.approx(0.01)
