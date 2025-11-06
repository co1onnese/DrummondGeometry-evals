"""CLI entry for running backtests."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Mapping, Sequence

from rich.console import Console
from rich.panel import Panel

from ..backtesting import SimulationConfig
from ..backtesting.reporting import build_summary_table, export_json, export_markdown
from ..backtesting.runner import BacktestRequest, BacktestRunner

console = Console()


def run_backtest_command(
    *,
    symbols: Sequence[str],
    interval: str,
    strategy: str,
    strategy_params: Mapping[str, str],
    start: str | None,
    end: str | None,
    initial_capital: Decimal,
    commission_rate: Decimal,
    slippage_bps: Decimal,
    risk_free_rate: Decimal,
    persist: bool,
    output_format: str,
    report_path: Path | None,
    json_path: Path | None,
    limit_bars: int | None,
) -> int:
    try:
        request = BacktestRequest(
            symbols=list(symbols),
            interval=interval,
            start=_parse_datetime(start),
            end=_parse_datetime(end),
            strategy_name=strategy,
            strategy_params=dict(strategy_params),
            simulation_config=SimulationConfig(
                initial_capital=initial_capital,
                commission_rate=commission_rate,
                slippage_bps=slippage_bps,
            ),
            risk_free_rate=risk_free_rate,
            persist_results=persist,
            limit=limit_bars,
        )

        runner = BacktestRunner()
        results = runner.run(request)

        if output_format in {"summary", "detailed"}:
            table = build_summary_table(results)
            console.print(table)

        if output_format == "detailed":
            for run in results:
                console.print(
                    Panel.fit(
                        _format_detailed_panel(run),
                        title=f"{run.symbol} - {run.strategy_name}",
                        border_style="green",
                    )
                )

        if output_format == "json":
            payload = [
                {
                    "symbol": run.symbol,
                    "strategy": run.strategy_name,
                    "performance": {
                        "total_return": float(run.performance.total_return),
                        "sharpe_ratio": _maybe_float(run.performance.sharpe_ratio),
                        "max_drawdown": float(run.performance.max_drawdown),
                    },
                }
                for run in results
            ]
            console.print(json.dumps(payload, indent=2))

        if report_path is not None:
            for run in results:
                export_markdown(run, _resolve_output_path(report_path, run.symbol, ".md"))
            console.print(f"Markdown report written to {report_path}")

        if json_path is not None:
            for run in results:
                export_json(run, _resolve_output_path(json_path, run.symbol, ".json"))
            console.print(f"JSON report written to {json_path}")

        if results and results[0].persisted_id and persist:
            ids = ", ".join(str(run.persisted_id) for run in results if run.persisted_id)
            console.print(f"Persisted backtests with IDs: {ids}")

        return 0
    except Exception as exc:  # pragma: no cover - CLI guard
        console.print(f"[red]Backtest failed:[/red] {exc}")
        return 1


def _parse_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    try:
        if len(value) == 10:  # YYYY-MM-DD
            dt = datetime.fromisoformat(f"{value}T00:00:00")
        else:
            dt = datetime.fromisoformat(value)
    except ValueError as exc:  # pragma: no cover - user input
        raise ValueError(f"Invalid datetime value: {value}") from exc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _resolve_output_path(path: Path, symbol: str, suffix: str) -> Path:
    if path.suffix:
        if symbol and path.stem and len(symbol) > 0 and symbol not in path.stem:
            return path.with_name(f"{path.stem}_{symbol}{path.suffix}")
        return path
    return path / f"{symbol}{suffix}"


def _maybe_float(value: Decimal | None) -> float | None:
    return None if value is None else float(value)


def _format_detailed_panel(run: BacktestRunResult) -> str:
    perf = run.performance
    lines = [
        f"Total Return: {_format_percent(perf.total_return)}",
        f"Sharpe Ratio: {_format_number(perf.sharpe_ratio)}",
        f"Sortino Ratio: {_format_number(perf.sortino_ratio)}",
        f"Max Drawdown: {_format_percent(perf.max_drawdown)}",
        f"Trades: {perf.total_trades}",
    ]
    if run.persisted_id is not None:
        lines.append(f"Persisted ID: {run.persisted_id}")
    return "\n".join(lines)


def _format_percent(value: Decimal | None) -> str:
    if value is None:
        return "-"
    return f"{float(value) * 100:.2f}%"


def _format_number(value: Decimal | None) -> str:
    if value is None:
        return "-"
    return f"{float(value):.2f}"


__all__ = ["run_backtest_command", "console"]
