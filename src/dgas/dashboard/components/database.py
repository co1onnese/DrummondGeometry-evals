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


def get_db_connection():
    """
    Get database connection context manager.
    
    Note: This cannot be cached with @st.cache_resource because get_connection()
    returns a context manager (GeneratorContextManager), which cannot be
    serialized or cached by Streamlit. Each call creates a new context manager.

    Returns:
        Context manager for database connection
    """
    return get_connection()


@performance_timer
def execute_query(query: str, params: Optional[tuple] = None) -> List[Tuple]:
    """
    Execute query.

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

    # Total active symbols (normalized - count unique base symbols without .US suffix)
    # Note: %% escapes % for psycopg (so '%.US' becomes '%%.US')
    query = """
        SELECT COUNT(DISTINCT 
            CASE 
                WHEN symbol LIKE '%%.US' THEN SUBSTRING(symbol FROM 1 FOR LENGTH(symbol) - 3)
                ELSE symbol
            END
        )
        FROM market_symbols
        WHERE is_active = true
    """
    rows = execute_query(query)
    result["total_symbols"] = rows[0][0] if rows else 0

    # Total data bars
    query = "SELECT COUNT(*) FROM market_data"
    rows = execute_query(query)
    result["total_data_bars"] = rows[0][0] if rows else 0

    # Recent predictions (7 days - to account for weekends)
    query = """
        SELECT COUNT(*)
        FROM prediction_runs
        WHERE created_at > NOW() - INTERVAL '7 days'
    """
    rows = execute_query(query)
    result["predictions_24h"] = rows[0][0] if rows else 0

    # Recent signals (7 days - to account for weekends)
    query = """
        SELECT COUNT(*)
        FROM generated_signals gs
        JOIN prediction_runs pr ON pr.run_id = gs.run_id
        WHERE pr.created_at > NOW() - INTERVAL '7 days'
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

    # Data coverage (using 7 days to account for weekends when markets are closed)
    # Count distinct normalized symbols (remove .US suffix if present)
    # Note: %% escapes % for psycopg (so '%.US' becomes '%%.US')
    query = """
        SELECT COUNT(DISTINCT 
            CASE 
                WHEN s.symbol LIKE '%%.US' THEN SUBSTRING(s.symbol FROM 1 FOR LENGTH(s.symbol) - 3)
                ELSE s.symbol
            END
        )
        FROM market_symbols s
        JOIN market_data md ON md.symbol_id = s.symbol_id
        WHERE s.is_active = true
        AND md.timestamp > NOW() - INTERVAL '7 days'
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
        WHERE s.is_active = true
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
            s.symbol,
            gs.signal_type,
            gs.confidence,
            gs.entry_price,
            gs.target_price,
            gs.stop_loss,
            gs.signal_timestamp,
            gs.risk_reward_ratio,
            gs.signal_strength
        FROM generated_signals gs
        JOIN prediction_runs pr ON pr.run_id = gs.run_id
        JOIN market_symbols s ON s.symbol_id = gs.symbol_id
        WHERE pr.created_at >= %s
          AND gs.confidence >= %s
    """
    params = [since, min_confidence]

    if symbol:
        query += " AND s.symbol = %s"
        params.append(symbol)

    query += " ORDER BY gs.signal_timestamp DESC LIMIT 500"

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
            WHERE s.symbol = %s
            ORDER BY br.completed_at DESC
            LIMIT %s
        """
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

    # Convert numeric columns from Decimal/object to float
    numeric_columns = [
        "initial_capital",
        "final_capital",
        "total_return",
        "sharpe_ratio",
        "max_drawdown",
        "win_rate",
        "total_trades",
    ]
    for col in numeric_columns:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

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
        # Database stats (count only active symbols)
        query = """
            SELECT
                (SELECT COUNT(*) FROM market_symbols WHERE is_active = true) as symbols,
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

        # Recent data (using 7 days to account for weekends)
        # Count distinct normalized symbols (remove .US suffix if present)
        # Note: %% escapes % for psycopg (so '%.US' becomes '%%.US')
        query = """
            SELECT COUNT(DISTINCT 
                CASE 
                    WHEN s.symbol LIKE '%%.US' THEN SUBSTRING(s.symbol FROM 1 FOR LENGTH(s.symbol) - 3)
                    ELSE s.symbol
                END
            )
            FROM market_symbols s
            JOIN market_data md ON md.symbol_id = s.symbol_id
            WHERE s.is_active = true
            AND md.timestamp > NOW() - INTERVAL '7 days'
        """
        rows = execute_query(query)
        status["data_coverage"] = {
            "symbols_24h": rows[0][0] if rows else 0,
        }

        # Predictions (7 days - to account for weekends)
        query = """
            SELECT
                (SELECT COUNT(*) FROM prediction_runs WHERE created_at > NOW() - INTERVAL '7 days') as runs_24h,
                (SELECT COUNT(*) FROM generated_signals gs JOIN prediction_runs pr ON pr.run_id = gs.run_id WHERE pr.created_at > NOW() - INTERVAL '7 days') as signals_24h
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

        # WebSocket status (if data collection service is available)
        try:
            from dgas.data.collection_service import DataCollectionService
            from dgas.config.adapter import load_settings
            
            settings = load_settings()
            if settings.data_collection and settings.data_collection.use_websocket:
                service = DataCollectionService(settings.data_collection)
                ws_status = service.get_websocket_status()
                if ws_status:
                    status["websocket"] = {
                        "enabled": True,
                        "running": ws_status.get("running", False),
                        "connected": ws_status.get("client_connected", False),
                        "connections": ws_status.get("client_status", {}).get("connections", 0),
                        "connected_count": ws_status.get("client_status", {}).get("connected", 0),
                        "total_symbols": ws_status.get("client_status", {}).get("total_symbols", 0),
                        "messages_received": ws_status.get("client_status", {}).get("total_messages_received", 0),
                        "bars_buffered": ws_status.get("bars_buffered", 0),
                        "bars_stored": ws_status.get("stats", {}).get("bars_stored", 0),
                    }
                else:
                    status["websocket"] = {
                        "enabled": True,
                        "running": False,
                        "connected": False,
                    }
            else:
                status["websocket"] = {
                    "enabled": False,
                }
        except Exception as e:
            # WebSocket status unavailable (service not running or error)
            status["websocket"] = {
                "enabled": None,
                "error": str(e),
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
