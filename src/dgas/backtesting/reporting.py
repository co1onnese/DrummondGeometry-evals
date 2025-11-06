"""Utilities for formatting and exporting backtest reports."""

from __future__ import annotations

import json
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable, Mapping

from rich.table import Table

from .runner import BacktestRunResult


def build_summary_table(results: Iterable[BacktestRunResult]) -> Table:
    table = Table(title="Backtest Summary", show_lines=False)
    table.add_column("Symbol", style="cyan")
    table.add_column("Strategy", style="magenta")
    table.add_column("Total Return", justify="right")
    table.add_column("Sharpe", justify="right")
    table.add_column("Max DD", justify="right")
    table.add_column("Trades", justify="right")

    for run in results:
        perf = run.performance
        table.add_row(
            run.symbol,
            run.strategy_name,
            _format_percent(perf.total_return),
            _format_number(perf.sharpe_ratio),
            _format_percent(perf.max_drawdown),
            str(perf.total_trades),
        )

    return table


def export_markdown(result: BacktestRunResult, path: Path) -> None:
    lines = [
        f"# Backtest Report - {result.symbol}",
        "",
        f"**Strategy:** {result.strategy_name}",
        f"**Total Return:** {_format_percent(result.performance.total_return)}",
        f"**Sharpe Ratio:** {_format_number(result.performance.sharpe_ratio)}",
        f"**Sortino Ratio:** {_format_number(result.performance.sortino_ratio)}",
        f"**Max Drawdown:** {_format_percent(result.performance.max_drawdown)}",
        f"**Trades:** {result.performance.total_trades}",
        "",
        "## Equity Curve",
        "| Timestamp | Equity | Cash |",
        "| --- | ---: | ---: |",
    ]

    for snapshot in result.result.equity_curve:
        lines.append(
            f"| {snapshot.timestamp.isoformat()} | ${float(snapshot.equity):,.2f} | ${float(snapshot.cash):,.2f} |"
        )

    if result.result.trades:
        lines.extend(["", "## Trades", "| Entry | Exit | Side | Qty | PnL |", "| --- | --- | --- | ---: | ---: |"])
        for trade in result.result.trades:
            lines.append(
                "| {entry} | {exit} | {side} | {qty:.4f} | ${pnl:.2f} |".format(
                    entry=trade.entry_time.isoformat(),
                    exit=trade.exit_time.isoformat(),
                    side=trade.side.value,
                    qty=float(trade.quantity),
                    pnl=float(trade.net_profit),
                )
            )

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def export_json(result: BacktestRunResult, path: Path) -> None:
    serializable = {
        "symbol": result.symbol,
        "strategy": result.strategy_name,
        "performance": _convert_decimals(asdict(result.performance)),
        "trades": [
            {
                "entry_time": trade.entry_time.isoformat(),
                "exit_time": trade.exit_time.isoformat(),
                "side": trade.side.value,
                "quantity": float(trade.quantity),
                "entry_price": float(trade.entry_price),
                "exit_price": float(trade.exit_price),
                "net_profit": float(trade.net_profit),
            }
            for trade in result.result.trades
        ],
    }

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(serializable, indent=2), encoding="utf-8")


def _format_percent(value: Decimal | None) -> str:
    if value is None:
        return "-"
    return f"{float(value) * 100:.2f}%"


def _format_number(value: Decimal | None) -> str:
    if value is None:
        return "-"
    return f"{float(value):.2f}"


def _convert_decimals(data: Mapping[str, Any]) -> Mapping[str, Any]:
    converted: dict[str, Any] = {}
    for key, value in data.items():
        if isinstance(value, Decimal):
            converted[key] = float(value)
        else:
            converted[key] = value
    return converted


__all__ = ["build_summary_table", "export_markdown", "export_json"]
