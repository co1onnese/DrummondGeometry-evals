"""Indicator loading from database for backtesting.

Loads pre-computed multi-timeframe analysis from database instead of
recalculating, providing 10-50× performance improvement.
"""

from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from typing import Dict, Mapping, Optional

from psycopg import Connection

from ..calculations.multi_timeframe import (
    ConfluenceZone,
    MultiTimeframeAnalysis,
    PLDotOverlay,
    TimeframeAlignment,
)
from ..calculations.states import MarketState, TrendDirection
from ..data.repository import get_symbol_id
from ..db import get_connection

logger = logging.getLogger(__name__)


def load_indicators_from_db(
    symbol: str,
    timestamp: datetime,
    htf_interval: str,
    trading_interval: str,
    conn: Connection | None = None,
) -> Optional[MultiTimeframeAnalysis]:
    """Load pre-computed multi-timeframe analysis from database.

    Args:
        symbol: Market symbol
        timestamp: Analysis timestamp
        htf_interval: Higher timeframe interval (e.g., "1d")
        trading_interval: Trading timeframe interval (e.g., "30m")
        conn: Database connection (creates new if None)

    Returns:
        MultiTimeframeAnalysis object if found, None otherwise
    """
    if conn is None:
        with get_connection() as owned_conn:
            return load_indicators_from_db(
                symbol, timestamp, htf_interval, trading_interval, conn=owned_conn
            )

    try:
        # Get symbol_id
        symbol_id = get_symbol_id(conn, symbol)
        if symbol_id is None:
            logger.debug(f"Symbol {symbol} not found in database")
            return None

        # Query multi_timeframe_analysis table
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    timestamp, htf_interval, trading_interval, ltf_interval,
                    htf_trend, htf_trend_strength, trading_tf_trend,
                    alignment_score, alignment_type, trade_permitted,
                    htf_pldot_value, trading_pldot_value, pldot_distance_percent,
                    signal_strength, risk_level, recommended_action,
                    pattern_confluence, confluence_zones_count
                FROM multi_timeframe_analysis
                WHERE symbol_id = %s
                  AND htf_interval = %s
                  AND trading_interval = %s
                  AND timestamp = %s
                LIMIT 1
                """,
                (symbol_id, htf_interval, trading_interval, timestamp),
            )

            row = cursor.fetchone()
            if row is None:
                return None

            (
                db_timestamp,
                db_htf_interval,
                db_trading_interval,
                ltf_interval,
                htf_trend_str,
                htf_trend_strength,
                trading_tf_trend_str,
                alignment_score,
                alignment_type,
                trade_permitted,
                htf_pldot_value,
                trading_pldot_value,
                pldot_distance_percent,
                signal_strength,
                risk_level,
                recommended_action,
                pattern_confluence,
                confluence_zones_count,
            ) = row

            # Load confluence zones
            confluence_zones = _load_confluence_zones(cursor, symbol_id, timestamp)

            # Reconstruct MultiTimeframeAnalysis object
            analysis = _reconstruct_analysis(
                timestamp=db_timestamp,
                htf_interval=db_htf_interval,
                trading_interval=db_trading_interval,
                ltf_interval=ltf_interval,
                htf_trend_str=htf_trend_str,
                htf_trend_strength=Decimal(str(htf_trend_strength)),
                trading_tf_trend_str=trading_tf_trend_str,
                alignment_score=Decimal(str(alignment_score)),
                alignment_type=alignment_type,
                trade_permitted=trade_permitted,
                htf_pldot_value=Decimal(str(htf_pldot_value)),
                trading_pldot_value=Decimal(str(trading_pldot_value)),
                pldot_distance_percent=Decimal(str(pldot_distance_percent)) if pldot_distance_percent else None,
                signal_strength=Decimal(str(signal_strength)),
                risk_level=risk_level,
                recommended_action=recommended_action,
                pattern_confluence=pattern_confluence,
                confluence_zones=confluence_zones,
            )

            return analysis

    except Exception as e:
        logger.warning(f"Failed to load indicators from DB for {symbol} at {timestamp}: {e}")
        return None


def load_indicators_batch(
    symbol: str,
    timestamps: list[datetime],
    htf_interval: str,
    trading_interval: str,
    conn: Connection | None = None,
) -> Dict[datetime, MultiTimeframeAnalysis]:
    """Load multiple indicator snapshots in batch.

    Args:
        symbol: Market symbol
        timestamps: List of timestamps to load
        htf_interval: Higher timeframe interval
        trading_interval: Trading timeframe interval
        conn: Database connection (creates new if None)

    Returns:
        Dictionary mapping timestamp -> MultiTimeframeAnalysis
    """
    if not timestamps:
        return {}

    if conn is None:
        with get_connection() as owned_conn:
            return load_indicators_batch(
                symbol, timestamps, htf_interval, trading_interval, conn=owned_conn
            )

    result: Dict[datetime, MultiTimeframeAnalysis] = {}

    try:
        symbol_id = get_symbol_id(conn, symbol)
        if symbol_id is None:
            return result

        with conn.cursor() as cursor:
            # Query all timestamps at once, including analysis_id for batch zone loading
            cursor.execute(
                """
                SELECT
                    analysis_id, timestamp, htf_interval, trading_interval, ltf_interval,
                    htf_trend, htf_trend_strength, trading_tf_trend,
                    alignment_score, alignment_type, trade_permitted,
                    htf_pldot_value, trading_pldot_value, pldot_distance_percent,
                    signal_strength, risk_level, recommended_action,
                    pattern_confluence, confluence_zones_count
                FROM multi_timeframe_analysis
                WHERE symbol_id = %s
                  AND htf_interval = %s
                  AND trading_interval = %s
                  AND timestamp = ANY(%s)
                ORDER BY timestamp
                """,
                (symbol_id, htf_interval, trading_interval, timestamps),
            )

            rows = cursor.fetchall()

            if not rows:
                return result

            # Extract analysis_ids for batch zone loading
            analysis_ids = [row[0] for row in rows]

            # Batch load all confluence zones for all analysis_ids in a single query
            zones_by_analysis_id = _load_confluence_zones_batch(cursor, analysis_ids)

            # Reconstruct analyses
            for row in rows:
                (
                    analysis_id,
                    db_timestamp,
                    db_htf_interval,
                    db_trading_interval,
                    ltf_interval,
                    htf_trend_str,
                    htf_trend_strength,
                    trading_tf_trend_str,
                    alignment_score,
                    alignment_type,
                    trade_permitted,
                    htf_pldot_value,
                    trading_pldot_value,
                    pldot_distance_percent,
                    signal_strength,
                    risk_level,
                    recommended_action,
                    pattern_confluence,
                    confluence_zones_count,
                ) = row

                # Get confluence zones from batch-loaded cache
                confluence_zones = zones_by_analysis_id.get(analysis_id, [])

                analysis = _reconstruct_analysis(
                    timestamp=db_timestamp,
                    htf_interval=db_htf_interval,
                    trading_interval=db_trading_interval,
                    ltf_interval=ltf_interval,
                    htf_trend_str=htf_trend_str,
                    htf_trend_strength=Decimal(str(htf_trend_strength)),
                    trading_tf_trend_str=trading_tf_trend_str,
                    alignment_score=Decimal(str(alignment_score)),
                    alignment_type=alignment_type,
                    trade_permitted=trade_permitted,
                    htf_pldot_value=Decimal(str(htf_pldot_value)),
                    trading_pldot_value=Decimal(str(trading_pldot_value)),
                    pldot_distance_percent=Decimal(str(pldot_distance_percent)) if pldot_distance_percent else None,
                    signal_strength=Decimal(str(signal_strength)),
                    risk_level=risk_level,
                    recommended_action=recommended_action,
                    pattern_confluence=pattern_confluence,
                    confluence_zones=confluence_zones,
                )

                result[db_timestamp] = analysis

    except Exception as e:
        logger.warning(f"Failed to load indicators batch from DB for {symbol}: {e}")

    return result


def _load_confluence_zones_batch(
    cursor,
    analysis_ids: list[int],
) -> Dict[int, list[ConfluenceZone]]:
    """Batch load confluence zones for multiple analysis_ids in a single query.

    Args:
        cursor: Database cursor
        analysis_ids: List of analysis_ids to load zones for

    Returns:
        Dictionary mapping analysis_id -> list of ConfluenceZone
    """
    if not analysis_ids:
        return {}

    zones_by_analysis_id: Dict[int, list[ConfluenceZone]] = {}

    try:
        # Load all zones for all analysis_ids in a single query
        cursor.execute(
            """
            SELECT
                analysis_id,
                cz.level, cz.upper_bound, cz.lower_bound, cz.strength,
                cz.timeframes, cz.zone_type, cz.first_touch, cz.last_touch
            FROM confluence_zones cz
            WHERE cz.analysis_id = ANY(%s)
            ORDER BY cz.analysis_id, cz.level
            """,
            (analysis_ids,),
        )

        for zone_row in cursor.fetchall():
            (
                analysis_id,
                level,
                upper_bound,
                lower_bound,
                strength,
                timeframes,
                zone_type,
                first_touch,
                last_touch,
            ) = zone_row

            # timeframes might be stored as array or string
            if isinstance(timeframes, list):
                tf_list = timeframes
            elif isinstance(timeframes, str):
                tf_list = [t.strip() for t in timeframes.split(",")]
            else:
                tf_list = []

            zone = ConfluenceZone(
                level=Decimal(str(level)),
                upper_bound=Decimal(str(upper_bound)),
                lower_bound=Decimal(str(lower_bound)),
                strength=int(strength),
                timeframes=tf_list,
                zone_type=zone_type,
                first_touch=first_touch,
                last_touch=last_touch,
                weighted_strength=Decimal(str(strength)),  # Use strength as default
                sources={},
                volatility=Decimal("0"),  # Not stored in DB
            )

            if analysis_id not in zones_by_analysis_id:
                zones_by_analysis_id[analysis_id] = []
            zones_by_analysis_id[analysis_id].append(zone)

    except Exception as e:
        logger.debug(f"Failed to batch load confluence zones: {e}")

    return zones_by_analysis_id


def _load_confluence_zones(
    cursor,
    symbol_id: int,
    timestamp: datetime,
    htf_interval: str | None = None,
    trading_interval: str | None = None,
) -> list[ConfluenceZone]:
    """Load confluence zones for a specific analysis timestamp.

    Uses a join to efficiently load zones without a separate query.
    This is kept for backward compatibility with single-timestamp loading.
    """
    try:
        # Load zones using join with analysis table
        if htf_interval and trading_interval:
            # More specific query if we have intervals
            cursor.execute(
                """
                SELECT
                    cz.level, cz.upper_bound, cz.lower_bound, cz.strength,
                    cz.timeframes, cz.zone_type, cz.first_touch, cz.last_touch
                FROM confluence_zones cz
                JOIN multi_timeframe_analysis mta ON cz.analysis_id = mta.analysis_id
                WHERE mta.symbol_id = %s
                  AND mta.timestamp = %s
                  AND mta.htf_interval = %s
                  AND mta.trading_interval = %s
                ORDER BY cz.level
                """,
                (symbol_id, timestamp, htf_interval, trading_interval),
            )
        else:
            # Fallback: match by symbol and timestamp only
            cursor.execute(
                """
                SELECT
                    cz.level, cz.upper_bound, cz.lower_bound, cz.strength,
                    cz.timeframes, cz.zone_type, cz.first_touch, cz.last_touch
                FROM confluence_zones cz
                JOIN multi_timeframe_analysis mta ON cz.analysis_id = mta.analysis_id
                WHERE mta.symbol_id = %s
                  AND mta.timestamp = %s
                ORDER BY cz.level
                """,
                (symbol_id, timestamp),
            )

        zones = []
        for zone_row in cursor.fetchall():
            (
                level,
                upper_bound,
                lower_bound,
                strength,
                timeframes,
                zone_type,
                first_touch,
                last_touch,
            ) = zone_row

            # timeframes might be stored as array or string
            if isinstance(timeframes, list):
                tf_list = timeframes
            elif isinstance(timeframes, str):
                tf_list = [t.strip() for t in timeframes.split(",")]
            else:
                tf_list = []

            zone = ConfluenceZone(
                level=Decimal(str(level)),
                upper_bound=Decimal(str(upper_bound)),
                lower_bound=Decimal(str(lower_bound)),
                strength=int(strength),
                timeframes=tf_list,
                zone_type=zone_type,
                first_touch=first_touch,
                last_touch=last_touch,
                weighted_strength=Decimal(str(strength)),  # Use strength as default
                sources={},
                volatility=Decimal("0"),  # Not stored in DB
            )
            zones.append(zone)

        return zones

    except Exception as e:
        logger.debug(f"Failed to load confluence zones: {e}")
        return []


def _reconstruct_analysis(
    timestamp: datetime,
    htf_interval: str,
    trading_interval: str,
    ltf_interval: Optional[str],
    htf_trend_str: str,
    htf_trend_strength: Decimal,
    trading_tf_trend_str: str,
    alignment_score: Decimal,
    alignment_type: str,
    trade_permitted: bool,
    htf_pldot_value: Decimal,
    trading_pldot_value: Decimal,
    pldot_distance_percent: Optional[Decimal],
    signal_strength: Decimal,
    risk_level: str,
    recommended_action: str,
    pattern_confluence: bool,
    confluence_zones: list[ConfluenceZone],
) -> MultiTimeframeAnalysis:
    """Reconstruct MultiTimeframeAnalysis from database columns.

    Uses sensible defaults for fields not stored in database.
    """
    # Convert trend strings to enums
    htf_trend = TrendDirection[htf_trend_str]
    trading_tf_trend = TrendDirection[trading_tf_trend_str]

    # Reconstruct TimeframeAlignment
    # Note: Some fields (htf_state, trading_tf_state, htf_confidence, trading_tf_confidence)
    # are not stored, so we use defaults
    alignment = TimeframeAlignment(
        timestamp=timestamp,
        htf_state=MarketState.TREND,  # Default - not critical for backtesting
        htf_direction=htf_trend,
        htf_confidence=htf_trend_strength,  # Use trend strength as proxy
        trading_tf_state=MarketState.TREND,  # Default
        trading_tf_direction=trading_tf_trend,
        trading_tf_confidence=Decimal("0.7"),  # Default
        alignment_score=alignment_score,
        alignment_type=alignment_type,
        trade_permitted=trade_permitted,
    )

    # Reconstruct PLDotOverlay
    # Note: htf_slope and position are not stored, so we use defaults
    if pldot_distance_percent is None:
        # Calculate from values
        if htf_pldot_value != 0:
            pldot_distance_percent = (
                (trading_pldot_value - htf_pldot_value) / htf_pldot_value * Decimal("100")
            )
        else:
            pldot_distance_percent = Decimal("0")

    # Determine position
    if pldot_distance_percent > Decimal("0.1"):
        position = "above_htf"
    elif pldot_distance_percent < Decimal("-0.1"):
        position = "below_htf"
    else:
        position = "at_htf"

    pldot_overlay = PLDotOverlay(
        timestamp=timestamp,
        htf_timeframe=htf_interval,
        htf_pldot_value=htf_pldot_value,
        htf_slope=Decimal("0"),  # Not stored - default to 0
        ltf_timeframe=trading_interval,
        ltf_pldot_value=trading_pldot_value,
        distance_percent=pldot_distance_percent,
        position=position,
    )

    # Patterns are not stored in database - use empty lists
    # This means pattern-based filtering will be less strict
    # but core signals (alignment, signal_strength) will still work
    from ..calculations.patterns import PatternEvent

    htf_patterns: list[PatternEvent] = []
    trading_tf_patterns: list[PatternEvent] = []

    # Reconstruct MultiTimeframeAnalysis
    return MultiTimeframeAnalysis(
        timestamp=timestamp,
        htf_timeframe=htf_interval,
        trading_timeframe=trading_interval,
        ltf_timeframe=ltf_interval,
        htf_trend=htf_trend,
        htf_trend_strength=htf_trend_strength,
        trading_tf_trend=trading_tf_trend,
        alignment=alignment,
        pldot_overlay=pldot_overlay,
        confluence_zones=confluence_zones,
        htf_patterns=htf_patterns,
        trading_tf_patterns=trading_tf_patterns,
        pattern_confluence=pattern_confluence,
        signal_strength=signal_strength,
        risk_level=risk_level,
        recommended_action=recommended_action,
    )


__all__ = [
    "load_indicators_from_db",
    "load_indicators_batch",
]
