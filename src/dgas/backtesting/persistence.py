"""Persistence helpers for backtest results."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Iterable, Mapping

from psycopg import Connection
from psycopg.types.json import Json

from ..data.repository import get_symbol_id
from ..db import get_connection
from .entities import BacktestResult, Trade
from .metrics import PerformanceSummary


def persist_backtest(
    result: BacktestResult,
    performance: PerformanceSummary,
    *,
    metadata: Mapping[str, Any] | None = None,
    conn: Connection | None = None,
) -> int:
    """Persist backtest results and trades. Returns generated backtest_id."""

    if conn is None:
        with get_connection() as owned_conn:
            return persist_backtest(result, performance, metadata=metadata, conn=owned_conn)

    try:
        with conn.cursor() as cur:
            symbol_id = get_symbol_id(conn, result.symbol)
            if symbol_id is None:
                raise ValueError(f"Symbol {result.symbol} not found in market_symbols; ingest data first.")

            start_time = result.equity_curve[0].timestamp if result.equity_curve else None
            end_time = result.equity_curve[-1].timestamp if result.equity_curve else None

            cur.execute(
                """
                INSERT INTO backtest_results (
                    strategy_name,
                    symbol_id,
                    start_date,
                    end_date,
                    initial_capital,
                    commission_rate,
                    final_capital,
                    total_return,
                    annualized_return,
                    volatility,
                    sharpe_ratio,
                    max_drawdown,
                    max_drawdown_duration,
                    total_trades,
                    winning_trades,
                    losing_trades,
                    win_rate,
                    avg_win,
                    avg_loss,
                    profit_factor,
                    test_config,
                    completed_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
                RETURNING backtest_id
                """,
                (
                    result.strategy_name,
                    symbol_id,
                    start_time.date() if start_time else None,
                    end_time.date() if end_time else None,
                    result.starting_cash,
                    result.config.commission_rate,
                    result.ending_equity,
                    performance.total_return,
                    performance.annualized_return,
                    performance.volatility,
                    performance.sharpe_ratio,
                    performance.max_drawdown,
                    performance.max_drawdown_duration,
                    performance.total_trades,
                    performance.winning_trades,
                    performance.losing_trades,
                    performance.win_rate,
                    performance.avg_win,
                    performance.avg_loss,
                    performance.profit_factor,
                    Json(_build_test_config(result, metadata)),
                    datetime.now(timezone.utc),
                ),
            )
            backtest_id = cur.fetchone()[0]

            if result.trades:
                _persist_trades(cur, backtest_id, symbol_id, result.trades)

        conn.commit()
        return int(backtest_id)
    except Exception:
        conn.rollback()
        raise


def _build_test_config(result: BacktestResult, metadata: Mapping[str, Any] | None) -> Mapping[str, Any]:
    base = asdict(result.config)
    # Convert Decimal values to float for JSON serialization
    base = {k: (float(v) if isinstance(v, Decimal) else v) for k, v in base.items()}
    base.update(result.metadata)
    if metadata:
        # Also convert any Decimal values in metadata
        metadata_clean = {k: (float(v) if isinstance(v, Decimal) else v) for k, v in metadata.items()}
        base.update(metadata_clean)
    return base


def _persist_trades(cur, backtest_id: int, symbol_id: int, trades: Iterable[Trade]) -> None:
    rows = []
    for trade in trades:
        duration_hours = int((trade.exit_time - trade.entry_time).total_seconds() // 3600)
        notional = trade.entry_price * trade.quantity if trade.entry_price != 0 else Decimal("0")
        return_pct = (trade.net_profit / notional) if notional != 0 else None

        rows.append(
            (
                backtest_id,
                symbol_id,
                trade.entry_time,
                trade.exit_time,
                trade.entry_price,
                trade.exit_price,
                abs(trade.quantity),
                "long" if trade.side.name.lower() == "long" else "short",
                trade.gross_profit,
                trade.net_profit,
                return_pct,
                duration_hours,
            )
        )

    cur.executemany(
        """
        INSERT INTO backtest_trades (
            backtest_id,
            symbol_id,
            entry_timestamp,
            exit_timestamp,
            entry_price,
            exit_price,
            position_size,
            trade_type,
            gross_profit_loss,
            net_profit_loss,
            return_percentage,
            trade_duration_hours
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
        )
        """,
        rows,
    )


__all__ = ["persist_backtest"]
