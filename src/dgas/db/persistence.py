"""Database persistence for Drummond Geometry calculations."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import List, Optional, Sequence

try:
    import psycopg2
    from psycopg2.extras import execute_values
    HAS_PSYCOPG2 = True
except ImportError:
    # Fall back to psycopg (psycopg3)
    import psycopg
    HAS_PSYCOPG2 = False

from ..calculations.multi_timeframe import (
    ConfluenceZone,
    MultiTimeframeAnalysis,
)
from ..calculations.patterns import PatternEvent, PatternType
from ..calculations.states import MarketState, StateSeries, TrendDirection
from ..settings import Settings


class DrummondPersistence:
    """Handle database persistence for Drummond Geometry calculations."""

    def __init__(self, settings: Optional[Settings] = None):
        """Initialize persistence layer with database connection."""
        if settings is None:
            settings = Settings()
        self.settings = settings
        self._conn: Optional[psycopg2.extensions.connection] = None

    def _get_connection(self) -> psycopg2.extensions.connection:
        """Get or create database connection."""
        if self._conn is None or self._conn.closed:
            self._conn = psycopg2.connect(
                host=self.settings.db_host,
                port=self.settings.db_port,
                dbname=self.settings.db_name,
                user=self.settings.db_user,
                password=self.settings.db_password,
            )
        return self._conn

    def close(self) -> None:
        """Close database connection."""
        if self._conn is not None and not self._conn.closed:
            self._conn.close()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()

    # ================================================================================
    # Market State Persistence
    # ================================================================================

    def save_market_states(
        self,
        symbol: str,
        interval_type: str,
        states: Sequence[StateSeries],
    ) -> int:
        """
        Save market state classifications to database.

        Args:
            symbol: Market symbol (e.g., "AAPL")
            interval_type: Timeframe interval (e.g., "1h", "30min")
            states: Sequence of state classifications to save

        Returns:
            Number of states inserted
        """
        if not states:
            return 0

        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            # Get symbol_id
            cursor.execute(
                "SELECT symbol_id FROM market_symbols WHERE symbol = %s",
                (symbol,)
            )
            result = cursor.fetchone()
            if result is None:
                raise ValueError(f"Symbol {symbol} not found in database")
            symbol_id = result[0]

            # Prepare data for bulk insert
            values = []
            for state in states:
                values.append((
                    symbol_id,
                    interval_type,
                    state.timestamp,
                    state.state.value,
                    state.trend_direction.value,
                    state.bars_in_state,
                    state.previous_state.value if state.previous_state else None,
                    state.state_change_reason,
                    state.pldot_slope_trend,
                    float(state.confidence),
                ))

            # Bulk insert with ON CONFLICT DO UPDATE
            execute_values(
                cursor,
                """
                INSERT INTO market_states_v2 (
                    symbol_id, interval_type, timestamp,
                    state, trend_direction, bars_in_state,
                    previous_state, state_change_reason,
                    pldot_slope_trend, confidence
                ) VALUES %s
                ON CONFLICT (symbol_id, interval_type, timestamp)
                DO UPDATE SET
                    state = EXCLUDED.state,
                    trend_direction = EXCLUDED.trend_direction,
                    bars_in_state = EXCLUDED.bars_in_state,
                    previous_state = EXCLUDED.previous_state,
                    state_change_reason = EXCLUDED.state_change_reason,
                    pldot_slope_trend = EXCLUDED.pldot_slope_trend,
                    confidence = EXCLUDED.confidence
                """,
                values
            )

            conn.commit()
            return len(values)

        except Exception as e:
            conn.rollback()
            raise e
        finally:
            cursor.close()

    def get_market_states(
        self,
        symbol: str,
        interval_type: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 1000,
    ) -> List[StateSeries]:
        """
        Retrieve market state classifications from database.

        Args:
            symbol: Market symbol
            interval_type: Timeframe interval
            start_time: Optional start timestamp filter
            end_time: Optional end timestamp filter
            limit: Maximum number of records to return

        Returns:
            List of state classifications
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            # Get symbol_id
            cursor.execute(
                "SELECT symbol_id FROM market_symbols WHERE symbol = %s",
                (symbol,)
            )
            result = cursor.fetchone()
            if result is None:
                return []
            symbol_id = result[0]

            # Build query with optional time filters
            query = """
                SELECT
                    timestamp, state, trend_direction, bars_in_state,
                    previous_state, state_change_reason, pldot_slope_trend, confidence
                FROM market_states_v2
                WHERE symbol_id = %s AND interval_type = %s
            """
            params: List = [symbol_id, interval_type]

            if start_time is not None:
                query += " AND timestamp >= %s"
                params.append(start_time)

            if end_time is not None:
                query += " AND timestamp <= %s"
                params.append(end_time)

            query += " ORDER BY timestamp DESC LIMIT %s"
            params.append(limit)

            cursor.execute(query, params)

            # Convert rows to StateSeries objects
            states = []
            for row in cursor.fetchall():
                (
                    timestamp, state_str, direction_str, bars_in_state,
                    prev_state_str, reason, slope_trend, confidence
                ) = row

                states.append(
                    StateSeries(
                        timestamp=timestamp,
                        state=MarketState(state_str),
                        trend_direction=TrendDirection(direction_str),
                        bars_in_state=bars_in_state,
                        previous_state=MarketState(prev_state_str) if prev_state_str else None,
                        pldot_slope_trend=slope_trend,
                        confidence=Decimal(str(confidence)),
                        state_change_reason=reason,
                    )
                )

            return states

        finally:
            cursor.close()

    # ================================================================================
    # Pattern Event Persistence
    # ================================================================================

    def save_pattern_events(
        self,
        symbol: str,
        interval_type: str,
        patterns: Sequence[PatternEvent],
    ) -> int:
        """
        Save detected pattern events to database.

        Args:
            symbol: Market symbol
            interval_type: Timeframe interval
            patterns: Sequence of pattern events to save

        Returns:
            Number of patterns inserted
        """
        if not patterns:
            return 0

        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            # Get symbol_id
            cursor.execute(
                "SELECT symbol_id FROM market_symbols WHERE symbol = %s",
                (symbol,)
            )
            result = cursor.fetchone()
            if result is None:
                raise ValueError(f"Symbol {symbol} not found in database")
            symbol_id = result[0]

            # Prepare data for bulk insert
            values = []
            for pattern in patterns:
                values.append((
                    symbol_id,
                    interval_type,
                    pattern.pattern_type.value,
                    pattern.direction,
                    pattern.start_timestamp,
                    pattern.end_timestamp,
                    pattern.strength,
                    None,  # metadata (can be extended later)
                ))

            # Bulk insert (patterns are append-only, no updates)
            execute_values(
                cursor,
                """
                INSERT INTO pattern_events (
                    symbol_id, interval_type, pattern_type,
                    direction, start_timestamp, end_timestamp,
                    strength, metadata
                ) VALUES %s
                """,
                values
            )

            conn.commit()
            return len(values)

        except Exception as e:
            conn.rollback()
            raise e
        finally:
            cursor.close()

    def get_pattern_events(
        self,
        symbol: str,
        interval_type: str,
        pattern_type: Optional[PatternType] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 1000,
    ) -> List[PatternEvent]:
        """
        Retrieve pattern events from database.

        Args:
            symbol: Market symbol
            interval_type: Timeframe interval
            pattern_type: Optional filter by pattern type
            start_time: Optional start timestamp filter
            end_time: Optional end timestamp filter
            limit: Maximum number of records to return

        Returns:
            List of pattern events
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            # Get symbol_id
            cursor.execute(
                "SELECT symbol_id FROM market_symbols WHERE symbol = %s",
                (symbol,)
            )
            result = cursor.fetchone()
            if result is None:
                return []
            symbol_id = result[0]

            # Build query with optional filters
            query = """
                SELECT
                    pattern_type, direction, start_timestamp,
                    end_timestamp, strength
                FROM pattern_events
                WHERE symbol_id = %s AND interval_type = %s
            """
            params: List = [symbol_id, interval_type]

            if pattern_type is not None:
                query += " AND pattern_type = %s"
                params.append(pattern_type.value)

            if start_time is not None:
                query += " AND end_timestamp >= %s"
                params.append(start_time)

            if end_time is not None:
                query += " AND start_timestamp <= %s"
                params.append(end_time)

            query += " ORDER BY start_timestamp DESC LIMIT %s"
            params.append(limit)

            cursor.execute(query, params)

            # Convert rows to PatternEvent objects
            patterns = []
            for row in cursor.fetchall():
                (pattern_type_str, direction, start_ts, end_ts, strength) = row

                patterns.append(
                    PatternEvent(
                        pattern_type=PatternType(pattern_type_str),
                        direction=direction,
                        start_timestamp=start_ts,
                        end_timestamp=end_ts,
                        strength=strength,
                    )
                )

            return patterns

        finally:
            cursor.close()

    # ================================================================================
    # Multi-Timeframe Analysis Persistence
    # ================================================================================

    def save_multi_timeframe_analysis(
        self,
        symbol: str,
        analysis: MultiTimeframeAnalysis,
    ) -> int:
        """
        Save multi-timeframe analysis results to database.

        Args:
            symbol: Market symbol
            analysis: Multi-timeframe analysis result

        Returns:
            analysis_id of the saved record
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            # Get symbol_id
            cursor.execute(
                "SELECT symbol_id FROM market_symbols WHERE symbol = %s",
                (symbol,)
            )
            result = cursor.fetchone()
            if result is None:
                raise ValueError(f"Symbol {symbol} not found in database")
            symbol_id = result[0]

            # Insert main analysis record
            cursor.execute(
                """
                INSERT INTO multi_timeframe_analysis (
                    symbol_id, htf_interval, trading_interval, ltf_interval,
                    timestamp, htf_trend, htf_trend_strength, trading_tf_trend,
                    alignment_score, alignment_type, trade_permitted,
                    htf_pldot_value, trading_pldot_value, pldot_distance_percent,
                    signal_strength, risk_level, recommended_action,
                    pattern_confluence, confluence_zones_count
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
                ON CONFLICT (symbol_id, htf_interval, trading_interval, timestamp)
                DO UPDATE SET
                    htf_trend = EXCLUDED.htf_trend,
                    htf_trend_strength = EXCLUDED.htf_trend_strength,
                    trading_tf_trend = EXCLUDED.trading_tf_trend,
                    alignment_score = EXCLUDED.alignment_score,
                    alignment_type = EXCLUDED.alignment_type,
                    trade_permitted = EXCLUDED.trade_permitted,
                    htf_pldot_value = EXCLUDED.htf_pldot_value,
                    trading_pldot_value = EXCLUDED.trading_pldot_value,
                    pldot_distance_percent = EXCLUDED.pldot_distance_percent,
                    signal_strength = EXCLUDED.signal_strength,
                    risk_level = EXCLUDED.risk_level,
                    recommended_action = EXCLUDED.recommended_action,
                    pattern_confluence = EXCLUDED.pattern_confluence,
                    confluence_zones_count = EXCLUDED.confluence_zones_count
                RETURNING analysis_id
                """,
                (
                    symbol_id,
                    analysis.htf_timeframe,
                    analysis.trading_timeframe,
                    analysis.ltf_timeframe,
                    analysis.timestamp,
                    analysis.htf_trend.value,
                    float(analysis.htf_trend_strength),
                    analysis.trading_tf_trend.value,
                    float(analysis.alignment.alignment_score),
                    analysis.alignment.alignment_type,
                    analysis.alignment.trade_permitted,
                    float(analysis.pldot_overlay.htf_pldot_value),
                    float(analysis.pldot_overlay.ltf_pldot_value),
                    float(analysis.pldot_overlay.distance_percent),
                    float(analysis.signal_strength),
                    analysis.risk_level,
                    analysis.recommended_action,
                    analysis.pattern_confluence,
                    len(analysis.confluence_zones),
                )
            )

            result = cursor.fetchone()
            if result is None:
                raise ValueError("Failed to insert multi-timeframe analysis")
            analysis_id = result[0]

            # Save confluence zones
            if analysis.confluence_zones:
                self._save_confluence_zones(cursor, symbol_id, analysis_id, analysis.confluence_zones)

            conn.commit()
            return analysis_id

        except Exception as e:
            conn.rollback()
            raise e
        finally:
            cursor.close()

    def _save_confluence_zones(
        self,
        cursor,
        symbol_id: int,
        analysis_id: int,
        zones: Sequence[ConfluenceZone],
    ) -> None:
        """Save confluence zones associated with an analysis."""
        values = []
        for zone in zones:
            values.append((
                analysis_id,
                symbol_id,
                float(zone.level),
                float(zone.upper_bound),
                float(zone.lower_bound),
                zone.strength,
                zone.timeframes,
                zone.zone_type,
                zone.first_touch,
                zone.last_touch,
            ))

        execute_values(
            cursor,
            """
            INSERT INTO confluence_zones (
                analysis_id, symbol_id, level, upper_bound, lower_bound,
                strength, timeframes, zone_type, first_touch, last_touch
            ) VALUES %s
            """,
            values
        )

    def get_latest_multi_timeframe_analysis(
        self,
        symbol: str,
        htf_interval: str,
        trading_interval: str,
    ) -> Optional[dict]:
        """
        Get the most recent multi-timeframe analysis for a symbol.

        Args:
            symbol: Market symbol
            htf_interval: Higher timeframe interval
            trading_interval: Trading timeframe interval

        Returns:
            Dictionary with analysis data or None
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            # Get symbol_id
            cursor.execute(
                "SELECT symbol_id FROM market_symbols WHERE symbol = %s",
                (symbol,)
            )
            result = cursor.fetchone()
            if result is None:
                return None
            symbol_id = result[0]

            # Get latest analysis
            cursor.execute(
                """
                SELECT
                    analysis_id, timestamp, htf_trend, htf_trend_strength,
                    trading_tf_trend, alignment_score, alignment_type,
                    trade_permitted, signal_strength, risk_level,
                    recommended_action, pattern_confluence, confluence_zones_count
                FROM multi_timeframe_analysis
                WHERE symbol_id = %s
                  AND htf_interval = %s
                  AND trading_interval = %s
                ORDER BY timestamp DESC
                LIMIT 1
                """,
                (symbol_id, htf_interval, trading_interval)
            )

            row = cursor.fetchone()
            if row is None:
                return None

            (
                analysis_id, timestamp, htf_trend, htf_strength,
                trading_trend, alignment_score, alignment_type,
                trade_permitted, signal_strength, risk_level,
                recommended_action, pattern_confluence, zones_count
            ) = row

            return {
                "analysis_id": analysis_id,
                "timestamp": timestamp,
                "htf_trend": htf_trend,
                "htf_trend_strength": htf_strength,
                "trading_tf_trend": trading_trend,
                "alignment_score": alignment_score,
                "alignment_type": alignment_type,
                "trade_permitted": trade_permitted,
                "signal_strength": signal_strength,
                "risk_level": risk_level,
                "recommended_action": recommended_action,
                "pattern_confluence": pattern_confluence,
                "confluence_zones_count": zones_count,
            }

        finally:
            cursor.close()


__all__ = ["DrummondPersistence"]
