"""Database utilities for Streamlit dashboard.

Provides cached database queries and connection management.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st
from psycopg import Connection

from dgas.config import load_settings
from dgas.db import get_connection
from dgas.dashboard.performance import cached_query, performance_timer


@st.cache_resource
def get_db_connection() -> Connection:
    """
    Get cached database connection.

    Returns:
        Database connection
    """
    return get_connection()


@cached_query(ttl=300, key_prefix="db")
@performance_timer
def execute_query(query: str, params: Optional[tuple] = None) -> List[Tuple]:
    """
    Execute query with caching.

    Args:
        query: SQL query string
        params: Query parameters

    Returns:
        Query results
    """
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params or ())
            return cur.fetchall()


@st.cache_data(ttl=300)
def fetch_system_overview() -> Dict[str, Any]:
    """
    Fetch system overview metrics.

    Returns:
        Dictionary with system metrics
    """
    result: Dict[str, Any] = {}

    # Total symbols
    query = "SELECT COUNT(*) FROM market_symbols"
    rows = execute_query(query)
    result["total_symbols"] = rows[0][0] if rows else 0

    # Total data bars
    query = "SELECT COUNT(*) FROM market_data"
    rows = execute_query(query)
    result["total_data_bars"] = rows[0][0] if rows else 0

    # Recent predictions (24h)
    query = """
        SELECT COUNT(*)
        FROM prediction_runs
        WHERE timestamp > NOW() - INTERVAL '24 hours'
    """
    rows = execute_query(query)
    result["predictions_24h"] = rows[0][0] if rows else 0

    # Recent signals (24h)
    query = """
        SELECT COUNT(*)
        FROM prediction_signals ps
        JOIN prediction_runs pr ON pr.run_id = ps.run_id
        WHERE pr.timestamp > NOW() - INTERVAL '24 hours'
    """
    rows = execute_query(query)
    result["signals_24h"] = rows[0][0] if rows else 0

    # Latest backtest
    query = """
        SELECT br.total_return, s.symbol
        FROM backtest_results br
        JOIN market_symbols s ON s.symbol_id = br.symbol_id
        ORDER BY br.completed_at DESC
        LIMIT 1
    """
    rows = execute_query(query)
    if rows:
        result["latest_backtest"] = {
            "return": float(rows[0][0]),
            "symbol": rows[0][1],
        }
    else:
        result["latest_backtest"] = None

    # Data coverage
    query = """
        SELECT COUNT(DISTINCT s.symbol)
        FROM market_symbols s
        JOIN market_data md ON md.symbol_id = s.symbol_id
        WHERE md.timestamp > NOW() - INTERVAL '24 hours'
    """
    rows = execute_query(query)
    result["symbols_with_recent_data"] = rows[0][0] if rows else 0

    return result


@st.cache_data(ttl=300)
def fetch_data_inventory() -> pd.DataFrame:
    """
    Fetch data inventory with statistics.

    Returns:
        DataFrame with symbol statistics
    """
    query = """
        SELECT
            s.symbol,
            s.exchange,
            COUNT(md.data_id) as bar_count,
            MIN(md.timestamp) as first_timestamp,
            MAX(md.timestamp) as last_timestamp
        FROM market_symbols s
        LEFT JOIN market_data md ON md.symbol_id = s.symbol_id
        GROUP BY s.symbol, s.exchange
        ORDER BY s.symbol
    """
    rows = execute_query(query)

    if not rows:
        return pd.DataFrame(
            columns=["symbol", "exchange", "bar_count", "first_timestamp", "last_timestamp"]
        )

    df = pd.DataFrame(
        rows,
        columns=["symbol", "exchange", "bar_count", "first_timestamp", "last_timestamp"],
    )

    return df


@st.cache_data(ttl=300)
def fetch_predictions(
    days: int = 7, symbol: Optional[str] = None, min_confidence: float = 0.0
) -> pd.DataFrame:
    """
    Fetch prediction signals.

    Args:
        days: Number of days to fetch
        symbol: Optional symbol filter
        min_confidence: Minimum confidence filter

    Returns:
        DataFrame with prediction signals
    """
    since = f"{(pd.Timestamp.now() - pd.Timedelta(days=days)).isoformat()}"

    query = """
        SELECT
            ps.symbol,
            ps.signal_type,
            ps.confidence,
            ps.entry_price,
            ps.target_price,
            ps.stop_loss,
            ps.signal_timestamp,
            ps.risk_reward_ratio,
            ps.signal_strength
        FROM prediction_signals ps
        JOIN prediction_runs pr ON pr.run_id = ps.run_id
        WHERE pr.timestamp >= %s
          AND ps.confidence >= %s
    """
    params = [since, min_confidence]

    if symbol:
        query += " AND ps.symbol = %s"
        params.append(symbol)

    query += " ORDER BY ps.signal_timestamp DESC LIMIT 500"

    rows = execute_query(query, tuple(params))

    if not rows:
        return pd.DataFrame(
            columns=[
                "symbol",
                "signal_type",
                "confidence",
                "entry_price",
                "target_price",
                "stop_loss",
                "signal_timestamp",
                "risk_reward_ratio",
                "signal_strength",
            ]
        )

    df = pd.DataFrame(
        rows,
        columns=[
            "symbol",
            "signal_type",
            "confidence",
            "entry_price",
            "target_price",
            "stop_loss",
            "signal_timestamp",
            "risk_reward_ratio",
            "signal_strength",
        ],
    )

    return df


@st.cache_data(ttl=300)
def fetch_backtest_results(limit: int = 10, symbol: Optional[str] = None) -> pd.DataFrame:
    """
    Fetch backtest results.

    Args:
        limit: Maximum number of results
        symbol: Optional symbol filter

    Returns:
        DataFrame with backtest results
    """
    query = """
        SELECT
            br.backtest_id,
            br.strategy_name,
            s.symbol,
            br.start_date,
            br.end_date,
            br.initial_capital,
            br.final_capital,
            br.total_return,
            br.sharpe_ratio,
            br.max_drawdown,
            br.win_rate,
            br.total_trades,
            br.completed_at
        FROM backtest_results br
        JOIN market_symbols s ON s.symbol_id = br.symbol_id
        ORDER BY br.completed_at DESC
        LIMIT %s
    """
    params = [limit]

    if symbol:
        query = query.replace("ORDER BY", "WHERE s.symbol = %s ORDER BY")
        params = [symbol, limit]

    rows = execute_query(query, tuple(params))

    if not rows:
        return pd.DataFrame(
            columns=[
                "backtest_id",
                "strategy_name",
                "symbol",
                "start_date",
                "end_date",
                "initial_capital",
                "final_capital",
                "total_return",
                "sharpe_ratio",
                "max_drawdown",
                "win_rate",
                "total_trades",
                "completed_at",
            ]
        )

    df = pd.DataFrame(
        rows,
        columns=[
            "backtest_id",
            "strategy_name",
            "symbol",
            "start_date",
            "end_date",
            "initial_capital",
            "final_capital",
            "total_return",
            "sharpe_ratio",
            "max_drawdown",
            "win_rate",
            "total_trades",
            "completed_at",
        ],
    )

    return df


@st.cache_data(ttl=60)  # Cache for 1 minute
def fetch_system_status() -> Dict[str, Any]:
    """
    Fetch system status information.

    Returns:
        Dictionary with system status
    """
    status: Dict[str, Any] = {}

    try:
        # Database stats
        query = """
            SELECT
                (SELECT COUNT(*) FROM market_symbols) as symbols,
                (SELECT COUNT(*) FROM market_data) as data_bars,
                (SELECT pg_size_pretty(pg_database_size(current_database()))) as db_size
        """
        rows = execute_query(query)
        if rows:
            status["database"] = {
                "symbols": rows[0][0],
                "data_bars": rows[0][1],
                "size": rows[0][2],
            }

        # Recent data
        query = """
            SELECT COUNT(DISTINCT s.symbol)
            FROM market_symbols s
            JOIN market_data md ON md.symbol_id = s.symbol_id
            WHERE md.timestamp > NOW() - INTERVAL '24 hours'
        """
        rows = execute_query(query)
        status["data_coverage"] = {
            "symbols_24h": rows[0][0] if rows else 0,
        }

        # Predictions
        query = """
            SELECT
                (SELECT COUNT(*) FROM prediction_runs WHERE timestamp > NOW() - INTERVAL '24 hours') as runs_24h,
                (SELECT COUNT(*) FROM prediction_signals ps JOIN prediction_runs pr ON pr.run_id = ps.run_id WHERE pr.timestamp > NOW() - INTERVAL '24 hours') as signals_24h
        """
        rows = execute_query(query)
        if rows:
            status["predictions"] = {
                "runs_24h": rows[0][0],
                "signals_24h": rows[0][1],
            }

        # Backtests
        query = "SELECT COUNT(*) FROM backtest_results WHERE completed_at > NOW() - INTERVAL '7 days'"
        rows = execute_query(query)
        status["backtests"] = {
            "last_7_days": rows[0][0] if rows else 0,
        }

        status["status"] = "healthy"

    except Exception as e:
        status["status"] = f"error: {e}"

    return status


@st.cache_data(ttl=300)
def fetch_data_quality_stats(interval: str = "30min") -> pd.DataFrame:
    """
    Fetch data quality statistics.

    Args:
        interval: Data interval

    Returns:
        DataFrame with quality stats
    """
    query = """
        SELECT
            s.symbol,
            s.exchange,
            COUNT(md.data_id) as bar_count,
            MIN(md.timestamp) as first_timestamp,
            MAX(md.timestamp) as last_timestamp,
            CASE
                WHEN COUNT(md.data_id) > 1 THEN
                    GREATEST(
                        0,
                        (
                            ((EXTRACT(EPOCH FROM (MAX(md.timestamp) - MIN(md.timestamp))) / 1800)::bigint + 1)
                            - COUNT(md.data_id)
                        )
                    )
                ELSE 0
            END as estimated_missing
        FROM market_symbols s
        LEFT JOIN market_data md
            ON md.symbol_id = s.symbol_id
            AND md.interval_type = %s
        GROUP BY s.symbol, s.exchange
        ORDER BY s.symbol
    """
    rows = execute_query(query, (interval,))

    if not rows:
        return pd.DataFrame(
            columns=[
                "symbol",
                "exchange",
                "bar_count",
                "first_timestamp",
                "last_timestamp",
                "estimated_missing",
            ]
        )

    df = pd.DataFrame(
        rows,
        columns=[
            "symbol",
            "exchange",
            "bar_count",
            "first_timestamp",
            "last_timestamp",
            "estimated_missing",
        ],
    )

    return df
