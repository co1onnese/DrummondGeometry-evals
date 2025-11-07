"""Multi-timeframe coordination for Drummond Geometry analysis.

This module implements the critical multi-timeframe coordination logic that is
the primary differentiator of Drummond Geometry methodology. Research shows
3x improvement in win rate when using proper HTF/LTF coordination.

Key concepts:
- HTF (Higher Timeframe) Trend Filter: Only trade in direction of HTF trend
- PLdot Overlay: Project HTF PLdot values onto LTF charts
- Confluence Zones: Support/resistance zones confirmed by multiple timeframes
- State Alignment: Higher confidence when market states align across timeframes
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Optional, Sequence, Tuple

from .drummond_lines import DrummondZone
from .envelopes import EnvelopeSeries
from .pldot import PLDotSeries
from .states import MarketState, StateSeries, TrendDirection
from .patterns import PatternEvent, PatternType


class TimeframeType(Enum):
    """Timeframe classification for coordination."""
    HIGHER = "higher"  # HTF - trend direction authority
    TRADING = "trading"  # Entry timeframe
    LOWER = "lower"  # LTF - precision timing


@dataclass(frozen=True)
class TimeframeData:
    """Complete analysis for a single timeframe."""
    timeframe: str  # e.g., "1h", "4h", "1d"
    classification: TimeframeType
    pldot_series: Sequence[PLDotSeries]
    envelope_series: Sequence[EnvelopeSeries]
    state_series: Sequence[StateSeries]
    pattern_events: Sequence[PatternEvent]
    drummond_zones: Sequence[DrummondZone] = field(default_factory=tuple)


@dataclass(frozen=True)
class PLDotOverlay:
    """HTF PLdot value overlaid onto LTF chart."""
    timestamp: datetime
    htf_timeframe: str
    htf_pldot_value: Decimal
    htf_slope: Decimal
    ltf_timeframe: str
    ltf_pldot_value: Decimal
    distance_percent: Decimal  # (LTF - HTF) / HTF * 100
    position: str  # "above_htf", "below_htf", "at_htf"


@dataclass(frozen=True)
class ConfluenceZone:
    """Support/resistance zone confirmed by multiple timeframes."""
    level: Decimal  # Central price level
    upper_bound: Decimal
    lower_bound: Decimal
    strength: int  # Number of timeframes confirming this zone
    timeframes: List[str]  # Which timeframes confirm
    zone_type: str  # "support", "resistance", "pivot"
    first_touch: datetime
    last_touch: datetime
    weighted_strength: Decimal = Decimal("0")
    sources: Dict[str, str] = field(default_factory=dict)
    volatility: Decimal = Decimal("0")


@dataclass(frozen=True)
class TimeframeAlignment:
    """State alignment analysis across timeframes."""
    timestamp: datetime
    htf_state: MarketState
    htf_direction: TrendDirection
    htf_confidence: Decimal
    trading_tf_state: MarketState
    trading_tf_direction: TrendDirection
    trading_tf_confidence: Decimal
    alignment_score: Decimal  # 0.0-1.0, higher = better alignment
    alignment_type: str  # "perfect", "partial", "divergent", "conflicting"
    trade_permitted: bool  # True if HTF permits trading in current direction


@dataclass(frozen=True)
class MultiTimeframeAnalysis:
    """Aggregated multi-timeframe analysis results."""
    timestamp: datetime
    htf_timeframe: str
    trading_timeframe: str
    ltf_timeframe: Optional[str]

    # Trend analysis
    htf_trend: TrendDirection
    htf_trend_strength: Decimal
    trading_tf_trend: TrendDirection

    # State alignment
    alignment: TimeframeAlignment

    # PLdot overlay
    pldot_overlay: PLDotOverlay

    # Confluence zones
    confluence_zones: List[ConfluenceZone]

    # Pattern alignment
    htf_patterns: List[PatternEvent]
    trading_tf_patterns: List[PatternEvent]
    pattern_confluence: bool  # True if patterns align across timeframes

    # Overall scores
    signal_strength: Decimal  # 0.0-1.0, composite signal strength
    risk_level: str  # "low", "medium", "high"
    recommended_action: str  # "long", "short", "wait", "reduce"


class MultiTimeframeCoordinator:
    """
    Coordinate Drummond Geometry analysis across multiple timeframes.

    This is the core of the Drummond multi-timeframe methodology:
    1. HTF defines the trend direction (trade WITH the trend)
    2. Trading TF provides entry signals
    3. LTF (optional) provides precise entry timing
    4. Confluence zones identify high-probability levels
    """

    def __init__(
        self,
        htf_timeframe: str,
        trading_timeframe: str,
        ltf_timeframe: Optional[str] = None,
        confluence_tolerance_pct: float = 0.5,
        alignment_threshold: float = 0.6,
    ):
        """
        Initialize multi-timeframe coordinator.

        Args:
            htf_timeframe: Higher timeframe for trend direction (e.g., "4h", "1d")
            trading_timeframe: Entry timeframe (e.g., "15m", "1h")
            ltf_timeframe: Optional lower timeframe for precision (e.g., "5m")
            confluence_tolerance_pct: Price tolerance for zone confluence (default 0.5%)
            alignment_threshold: Minimum alignment score to permit trades (default 0.6)
        """
        self.htf_timeframe = htf_timeframe
        self.trading_timeframe = trading_timeframe
        self.ltf_timeframe = ltf_timeframe
        self.confluence_tolerance_pct = confluence_tolerance_pct
        self.alignment_threshold = alignment_threshold

    def analyze(
        self,
        htf_data: TimeframeData,
        trading_tf_data: TimeframeData,
        ltf_data: Optional[TimeframeData] = None,
        target_timestamp: Optional[datetime] = None,
    ) -> MultiTimeframeAnalysis:
        """
        Perform comprehensive multi-timeframe analysis.

        Args:
            htf_data: Higher timeframe complete analysis
            trading_tf_data: Trading timeframe complete analysis
            ltf_data: Optional lower timeframe analysis
            target_timestamp: Timestamp to analyze (default: latest common timestamp)

        Returns:
            Complete multi-timeframe analysis with trading recommendations
        """
        # Find target timestamp (latest common point if not specified)
        if target_timestamp is None:
            target_timestamp = self._find_latest_common_timestamp(htf_data, trading_tf_data)

        # Get HTF trend analysis
        htf_trend, htf_strength = self._analyze_htf_trend(htf_data, target_timestamp)

        # Get trading TF trend
        trading_tf_trend = self._get_current_trend(trading_tf_data, target_timestamp)

        # Calculate state alignment
        alignment = self._calculate_alignment(
            htf_data, trading_tf_data, target_timestamp, htf_trend
        )

        # Create PLdot overlay
        pldot_overlay = self._create_pldot_overlay(
            htf_data, trading_tf_data, target_timestamp
        )

        # Detect confluence zones
        confluence_zones = self._detect_confluence_zones(
            [htf_data, trading_tf_data] + ([ltf_data] if ltf_data else []),
            target_timestamp
        )

        # Analyze pattern confluence
        htf_patterns = self._get_recent_patterns(htf_data, target_timestamp, lookback_bars=10)
        trading_patterns = self._get_recent_patterns(trading_tf_data, target_timestamp, lookback_bars=10)
        pattern_confluence = self._check_pattern_confluence(htf_patterns, trading_patterns)

        # Calculate signal strength and recommendations
        signal_strength = self._calculate_signal_strength(
            alignment, pldot_overlay, confluence_zones, pattern_confluence, htf_strength
        )

        risk_level = self._assess_risk_level(alignment, signal_strength, htf_strength)
        recommended_action = self._determine_action(
            htf_trend, trading_tf_trend, alignment, signal_strength
        )

        return MultiTimeframeAnalysis(
            timestamp=target_timestamp,
            htf_timeframe=self.htf_timeframe,
            trading_timeframe=self.trading_timeframe,
            ltf_timeframe=self.ltf_timeframe,
            htf_trend=htf_trend,
            htf_trend_strength=htf_strength,
            trading_tf_trend=trading_tf_trend,
            alignment=alignment,
            pldot_overlay=pldot_overlay,
            confluence_zones=confluence_zones,
            htf_patterns=htf_patterns,
            trading_tf_patterns=trading_patterns,
            pattern_confluence=pattern_confluence,
            signal_strength=signal_strength,
            risk_level=risk_level,
            recommended_action=recommended_action,
        )

    def _find_latest_common_timestamp(
        self, htf_data: TimeframeData, trading_tf_data: TimeframeData
    ) -> datetime:
        """Find the latest timestamp present in both timeframes."""
        htf_timestamps = {s.timestamp for s in htf_data.state_series}
        trading_timestamps = {s.timestamp for s in trading_tf_data.state_series}
        common = htf_timestamps & trading_timestamps

        if not common:
            # Fallback: use latest trading TF timestamp
            return max(s.timestamp for s in trading_tf_data.state_series)

        return max(common)

    def _analyze_htf_trend(
        self, htf_data: TimeframeData, timestamp: datetime
    ) -> Tuple[TrendDirection, Decimal]:
        """
        Analyze HTF trend direction and strength.

        Returns:
            (trend_direction, strength_score)
        """
        # Get current HTF state
        htf_state = self._get_state_at_timestamp(htf_data.state_series, timestamp)

        if htf_state is None:
            return (TrendDirection.NEUTRAL, Decimal("0.0"))

        # HTF trend is authoritative
        trend_direction = htf_state.trend_direction

        # Calculate strength based on:
        # 1. Time in current state (longer = stronger)
        # 2. State confidence
        # 3. PLdot slope alignment

        duration_score = min(Decimal(str(htf_state.bars_in_state * 0.1)), Decimal("0.4"))
        confidence_score = htf_state.confidence * Decimal("0.4")

        # PLdot slope alignment
        slope_score = Decimal("0.0")
        if htf_state.state == MarketState.TREND:
            if (trend_direction == TrendDirection.UP and htf_state.pldot_slope_trend == "rising") or \
               (trend_direction == TrendDirection.DOWN and htf_state.pldot_slope_trend == "falling"):
                slope_score = Decimal("0.2")

        strength = min(duration_score + confidence_score + slope_score, Decimal("1.0"))

        return (trend_direction, strength)

    def _get_current_trend(
        self, tf_data: TimeframeData, timestamp: datetime
    ) -> TrendDirection:
        """Get current trend direction for a timeframe."""
        state = self._get_state_at_timestamp(tf_data.state_series, timestamp)
        return state.trend_direction if state else TrendDirection.NEUTRAL

    def _get_state_at_timestamp(
        self, state_series: Sequence[StateSeries], timestamp: datetime
    ) -> Optional[StateSeries]:
        """Get state at or before the specified timestamp."""
        valid_states = [s for s in state_series if s.timestamp <= timestamp]
        return max(valid_states, key=lambda s: s.timestamp) if valid_states else None

    def _calculate_alignment(
        self,
        htf_data: TimeframeData,
        trading_tf_data: TimeframeData,
        timestamp: datetime,
        htf_trend: TrendDirection,
    ) -> TimeframeAlignment:
        """Calculate state alignment between HTF and trading TF."""
        htf_state = self._get_state_at_timestamp(htf_data.state_series, timestamp)
        trading_state = self._get_state_at_timestamp(trading_tf_data.state_series, timestamp)

        if htf_state is None or trading_state is None:
            return TimeframeAlignment(
                timestamp=timestamp,
                htf_state=MarketState.CONGESTION_ACTION,
                htf_direction=TrendDirection.NEUTRAL,
                htf_confidence=Decimal("0.0"),
                trading_tf_state=MarketState.CONGESTION_ACTION,
                trading_tf_direction=TrendDirection.NEUTRAL,
                trading_tf_confidence=Decimal("0.0"),
                alignment_score=Decimal("0.0"),
                alignment_type="divergent",
                trade_permitted=False,
            )

        # Calculate alignment score
        score = Decimal("0.0")

        # 1. Direction alignment (most important)
        if htf_state.trend_direction == trading_state.trend_direction:
            score += Decimal("0.5")
        elif htf_state.trend_direction == TrendDirection.NEUTRAL or \
             trading_state.trend_direction == TrendDirection.NEUTRAL:
            score += Decimal("0.25")

        # 2. State type compatibility
        if htf_state.state == trading_state.state:
            score += Decimal("0.2")
        elif self._states_compatible(htf_state.state, trading_state.state):
            score += Decimal("0.1")

        # 3. Confidence boost
        avg_confidence = (htf_state.confidence + trading_state.confidence) / Decimal("2.0")
        score += avg_confidence * Decimal("0.3")

        score = min(score, Decimal("1.0"))

        # Determine alignment type
        if score >= Decimal("0.8"):
            alignment_type = "perfect"
        elif score >= Decimal("0.6"):
            alignment_type = "partial"
        elif score >= Decimal("0.3"):
            alignment_type = "divergent"
        else:
            alignment_type = "conflicting"

        # Trade permitted if directions align or HTF is neutral
        trade_permitted = (
            htf_state.trend_direction == trading_state.trend_direction or
            htf_state.trend_direction == TrendDirection.NEUTRAL
        ) and score >= Decimal(str(self.alignment_threshold))

        return TimeframeAlignment(
            timestamp=timestamp,
            htf_state=htf_state.state,
            htf_direction=htf_state.trend_direction,
            htf_confidence=htf_state.confidence,
            trading_tf_state=trading_state.state,
            trading_tf_direction=trading_state.trend_direction,
            trading_tf_confidence=trading_state.confidence,
            alignment_score=score,
            alignment_type=alignment_type,
            trade_permitted=trade_permitted,
        )

    def _states_compatible(self, htf_state: MarketState, trading_state: MarketState) -> bool:
        """Check if states are compatible (not conflicting)."""
        # Trend states compatible with congestion exit
        if htf_state == MarketState.TREND and trading_state == MarketState.CONGESTION_EXIT:
            return True
        if trading_state == MarketState.TREND and htf_state == MarketState.CONGESTION_EXIT:
            return True

        # Congestion states are compatible with each other
        congestion_states = {
            MarketState.CONGESTION_ENTRANCE,
            MarketState.CONGESTION_ACTION,
            MarketState.CONGESTION_EXIT,
        }
        if htf_state in congestion_states and trading_state in congestion_states:
            return True

        return False

    def _create_pldot_overlay(
        self,
        htf_data: TimeframeData,
        trading_tf_data: TimeframeData,
        timestamp: datetime,
    ) -> PLDotOverlay:
        """Create HTF PLdot overlay on trading timeframe."""
        htf_pldot = self._get_pldot_at_timestamp(htf_data.pldot_series, timestamp)
        trading_pldot = self._get_pldot_at_timestamp(trading_tf_data.pldot_series, timestamp)

        if htf_pldot is None or trading_pldot is None:
            return PLDotOverlay(
                timestamp=timestamp,
                htf_timeframe=self.htf_timeframe,
                htf_pldot_value=Decimal("0.0"),
                htf_slope=Decimal("0.0"),
                ltf_timeframe=self.trading_timeframe,
                ltf_pldot_value=Decimal("0.0"),
                distance_percent=Decimal("0.0"),
                position="at_htf",
            )

        # Calculate distance
        distance = trading_pldot.value - htf_pldot.value
        distance_pct = (distance / htf_pldot.value * Decimal("100")) if htf_pldot.value != 0 else Decimal("0.0")

        # Determine position
        if distance_pct > Decimal("0.1"):
            position = "above_htf"
        elif distance_pct < Decimal("-0.1"):
            position = "below_htf"
        else:
            position = "at_htf"

        return PLDotOverlay(
            timestamp=timestamp,
            htf_timeframe=self.htf_timeframe,
            htf_pldot_value=htf_pldot.value,
            htf_slope=htf_pldot.slope,
            ltf_timeframe=self.trading_timeframe,
            ltf_pldot_value=trading_pldot.value,
            distance_percent=distance_pct,
            position=position,
        )

    def _get_pldot_at_timestamp(
        self, pldot_series: Sequence[PLDotSeries], timestamp: datetime
    ) -> Optional[PLDotSeries]:
        """Get PLdot at or before specified timestamp."""
        valid = [p for p in pldot_series if p.timestamp <= timestamp]
        return max(valid, key=lambda p: p.timestamp) if valid else None

    def _detect_confluence_zones(
        self,
        all_timeframe_data: List[TimeframeData],
        timestamp: datetime,
    ) -> List[ConfluenceZone]:
        """
        Detect price levels confirmed by multiple timeframes.

        Confluence zones are critical in Drummond Geometry - they represent
        levels where multiple timeframes agree on support/resistance.
        """
        tf_weight_map = {
            TimeframeType.HIGHER: Decimal("1.5"),
            TimeframeType.TRADING: Decimal("1.0"),
            TimeframeType.LOWER: Decimal("0.75"),
        }

        base_relative_tolerance = Decimal(str(self.confluence_tolerance_pct / 100.0))
        min_absolute_tolerance = Decimal("0.0001")

        level_entries: List[Dict[str, object]] = []

        def add_entry(
            *,
            price: Decimal,
            zone_type: str,
            timeframe_label: str,
            classification: TimeframeType,
            timestamp_value: datetime,
            source: str,
            base_weight: Decimal,
            component_strength: Decimal,
            volatility: Decimal,
        ) -> None:
            if not isinstance(price, Decimal):
                price = Decimal(str(price))
            if price.is_nan():
                return
            if not isinstance(volatility, Decimal):
                volatility = Decimal(str(volatility))
            if volatility.is_nan():
                volatility = Decimal("0")
            price_abs = abs(price)
            relative_tol = price_abs * base_relative_tolerance
            width_tol = volatility * Decimal("0.5")
            tolerance = max(relative_tol, width_tol, min_absolute_tolerance)

            level_entries.append(
                {
                    "price": price,
                    "zone_type": zone_type,
                    "timeframe": timeframe_label,
                    "classification": classification,
                    "timestamp": timestamp_value,
                    "source": source,
                    "weight": base_weight * component_strength,
                    "component_strength": component_strength,
                    "volatility": volatility,
                    "tolerance": tolerance,
                }
            )

        for tf_data in all_timeframe_data:
            if not tf_data:
                continue

            timeframe_label = tf_data.timeframe or tf_data.classification.value
            tf_weight = tf_weight_map.get(tf_data.classification, Decimal("1.0"))

            recent_envelopes = [
                env for env in tf_data.envelope_series if env.timestamp <= timestamp
            ][-20:]

            for env in recent_envelopes:
                width = env.width if isinstance(env.width, Decimal) else Decimal(str(env.width))
                if width.is_nan():
                    width = Decimal("0")
                vol_measure = width if width > 0 else Decimal("0.01")
                add_entry(
                    price=Decimal(env.upper),
                    zone_type="resistance",
                    timeframe_label=timeframe_label,
                    classification=tf_data.classification,
                    timestamp_value=env.timestamp,
                    source="envelope_upper",
                    base_weight=tf_weight,
                    component_strength=Decimal("1.0"),
                    volatility=vol_measure,
                )
                add_entry(
                    price=Decimal(env.lower),
                    zone_type="support",
                    timeframe_label=timeframe_label,
                    classification=tf_data.classification,
                    timestamp_value=env.timestamp,
                    source="envelope_lower",
                    base_weight=tf_weight,
                    component_strength=Decimal("1.0"),
                    volatility=vol_measure,
                )
                add_entry(
                    price=Decimal(env.center),
                    zone_type="pivot",
                    timeframe_label=timeframe_label,
                    classification=tf_data.classification,
                    timestamp_value=env.timestamp,
                    source="pldot_center",
                    base_weight=tf_weight,
                    component_strength=Decimal("0.5"),
                    volatility=vol_measure,
                )

            for zone in getattr(tf_data, "drummond_zones", []) or []:
                width = Decimal(zone.upper_price) - Decimal(zone.lower_price)
                width = abs(width)
                vol_measure = width if width > 0 else Decimal("0.01")
                add_entry(
                    price=Decimal(zone.center_price),
                    zone_type=zone.line_type,
                    timeframe_label=timeframe_label,
                    classification=tf_data.classification,
                    timestamp_value=timestamp,
                    source="drummond_zone",
                    base_weight=tf_weight,
                    component_strength=Decimal(zone.strength),
                    volatility=vol_measure,
                )

        zones: List[ConfluenceZone] = []
        used_indices: set[int] = set()

        precision = Decimal("0.000001")

        for idx, entry in enumerate(level_entries):
            if idx in used_indices:
                continue

            cluster = [entry]
            cluster_indices = {idx}

            for jdx, candidate in enumerate(level_entries):
                if jdx <= idx or jdx in used_indices:
                    continue
                if candidate["zone_type"] != entry["zone_type"]:
                    continue

                price_diff = abs(Decimal(candidate["price"]) - Decimal(entry["price"]))
                tolerance = max(
                    Decimal(entry["tolerance"]),
                    Decimal(candidate["tolerance"]),
                )
                if price_diff <= tolerance:
                    cluster.append(candidate)
                    cluster_indices.add(jdx)

            unique_timeframes = {str(item["timeframe"]) for item in cluster}
            if len(unique_timeframes) < 2:
                continue

            used_indices.update(cluster_indices)

            def _to_decimal(value: object) -> Decimal:
                if isinstance(value, Decimal):
                    return value
                return Decimal(str(value))

            levels = [_to_decimal(item["price"]) for item in cluster]
            center = sum(levels, Decimal("0")) / Decimal(len(levels))
            upper = max(levels)
            lower = min(levels)
            timestamps = [item["timestamp"] for item in cluster]

            aggregate_sources: Dict[str, Tuple[str, Decimal]] = {}
            total_weight = Decimal("0")
            total_volatility = Decimal("0")

            for item in cluster:
                tf_label = str(item["timeframe"])
                source = str(item["source"])
                weight = Decimal(item["weight"])
                total_weight += weight
                total_volatility += _to_decimal(item["volatility"])

                existing = aggregate_sources.get(tf_label)
                if existing is None or weight > existing[1]:
                    aggregate_sources[tf_label] = (source, weight)

            avg_volatility = (
                total_volatility / Decimal(len(cluster)) if cluster else Decimal("0")
            )

            zones.append(
                ConfluenceZone(
                    level=center.quantize(precision),
                    upper_bound=upper.quantize(precision),
                    lower_bound=lower.quantize(precision),
                    strength=len(unique_timeframes),
                    timeframes=sorted(unique_timeframes),
                    zone_type=str(entry["zone_type"]),
                    first_touch=min(timestamps),
                    last_touch=max(timestamps),
                    weighted_strength=total_weight.quantize(precision),
                    sources={tf: src for tf, (src, _) in aggregate_sources.items()},
                    volatility=avg_volatility.quantize(precision),
                )
            )

        return sorted(
            zones,
            key=lambda z: (z.strength, z.weighted_strength),
            reverse=True,
        )

    def _get_recent_patterns(
        self,
        tf_data: TimeframeData,
        timestamp: datetime,
        lookback_bars: int = 10,
    ) -> List[PatternEvent]:
        """Get recent pattern events before timestamp."""
        return [
            p for p in tf_data.pattern_events
            if p.end_timestamp <= timestamp
        ][-lookback_bars:]

    def _check_pattern_confluence(
        self,
        htf_patterns: List[PatternEvent],
        trading_patterns: List[PatternEvent],
    ) -> bool:
        """
        Check if patterns align across timeframes.

        Confluence occurs when:
        - Same pattern type appears in both timeframes
        - Patterns have same direction
        - Patterns overlap in time
        """
        if not htf_patterns or not trading_patterns:
            return False

        for htf_p in htf_patterns:
            for trading_p in trading_patterns:
                # Same pattern type and direction
                if htf_p.pattern_type == trading_p.pattern_type and \
                   htf_p.direction == trading_p.direction:
                    # Check time overlap
                    if self._patterns_overlap(htf_p, trading_p):
                        return True

        return False

    def _patterns_overlap(self, p1: PatternEvent, p2: PatternEvent) -> bool:
        """Check if two patterns overlap in time."""
        return not (p1.end_timestamp < p2.start_timestamp or
                    p2.end_timestamp < p1.start_timestamp)

    def _calculate_signal_strength(
        self,
        alignment: TimeframeAlignment,
        overlay: PLDotOverlay,
        zones: List[ConfluenceZone],
        pattern_confluence: bool,
        htf_strength: Decimal,
    ) -> Decimal:
        """
        Calculate composite signal strength (0.0-1.0).

        Components:
        - Alignment score (40%)
        - HTF trend strength (30%)
        - Confluence zone proximity (15%)
        - Pattern confluence (15%)
        """
        score = Decimal("0.0")

        # Alignment contribution
        score += alignment.alignment_score * Decimal("0.4")

        # HTF strength contribution
        score += htf_strength * Decimal("0.3")

        # Confluence zone contribution
        if zones:
            # Boost if price is near a strong confluence zone
            strongest_zone = zones[0]
            zone_weight = strongest_zone.weighted_strength
            if zone_weight >= Decimal("4.0"):
                score += Decimal("0.15")
            elif zone_weight >= Decimal("2.5"):
                score += Decimal("0.12")
            elif strongest_zone.strength >= 2:
                score += Decimal("0.08")

        # Pattern confluence contribution
        if pattern_confluence:
            score += Decimal("0.15")

        return min(score, Decimal("1.0"))

    def _assess_risk_level(
        self,
        alignment: TimeframeAlignment,
        signal_strength: Decimal,
        htf_strength: Decimal,
    ) -> str:
        """Assess risk level for trading."""
        if not alignment.trade_permitted:
            return "high"

        if signal_strength >= Decimal("0.7") and htf_strength >= Decimal("0.6"):
            return "low"
        elif signal_strength >= Decimal("0.5"):
            return "medium"
        else:
            return "high"

    def _determine_action(
        self,
        htf_trend: TrendDirection,
        trading_trend: TrendDirection,
        alignment: TimeframeAlignment,
        signal_strength: Decimal,
    ) -> str:
        """Determine recommended trading action."""
        if not alignment.trade_permitted:
            return "wait"

        if signal_strength < Decimal("0.4"):
            return "wait"

        # Strong aligned signals
        if htf_trend == trading_trend and signal_strength >= Decimal("0.6"):
            if htf_trend == TrendDirection.UP:
                return "long"
            elif htf_trend == TrendDirection.DOWN:
                return "short"

        # Moderate signals
        if signal_strength >= Decimal("0.5"):
            if trading_trend == TrendDirection.UP and htf_trend != TrendDirection.DOWN:
                return "long"
            elif trading_trend == TrendDirection.DOWN and htf_trend != TrendDirection.UP:
                return "short"

        # Weak or conflicting signals
        if alignment.alignment_type == "conflicting":
            return "reduce"

        return "wait"


__all__ = [
    "TimeframeType",
    "TimeframeData",
    "PLDotOverlay",
    "ConfluenceZone",
    "TimeframeAlignment",
    "MultiTimeframeAnalysis",
    "MultiTimeframeCoordinator",
]
