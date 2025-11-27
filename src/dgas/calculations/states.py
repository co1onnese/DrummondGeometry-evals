"""Market state classification according to Drummond Geometry."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Iterable, List, Sequence

from .pldot import PLDotSeries
from ..data.models import IntervalData


class MarketState(Enum):
    """Five Drummond Geometry market states."""
    TREND = "trend"
    CONGESTION_ENTRANCE = "congestion_entrance"
    CONGESTION_ACTION = "congestion_action"
    CONGESTION_EXIT = "congestion_exit"
    REVERSAL = "reversal"


class TrendDirection(Enum):
    """Trend direction classification."""
    UP = "up"
    DOWN = "down"
    NEUTRAL = "neutral"


@dataclass(frozen=True)
class StateSeries:
    """Single point-in-time market state classification."""
    timestamp: datetime
    state: MarketState
    trend_direction: TrendDirection
    bars_in_state: int
    previous_state: MarketState | None
    pldot_slope_trend: str  # "rising", "falling", "horizontal"
    confidence: Decimal
    state_change_reason: str | None = None
    # NEW: Track the trend direction when congestion was entered
    # This is preserved throughout congestion to accurately classify exit vs. reversal
    trend_at_congestion_entrance: TrendDirection | None = None
    # NEW: Total bars since entering congestion (for monitoring extended congestion)
    bars_in_congestion: int = 0


class MarketStateClassifier:
    """
    Classify market states using the Drummond 3-bar rule.

    Rules:
    - 3 consecutive closes above PLdot = uptrend
    - 3 consecutive closes below PLdot = downtrend
    - First opposite close after trend = congestion entrance
    - Alternating closes = congestion action
    - 3 bars resume trend direction = congestion exit
    - 3 bars opposite to prior trend = reversal
    """

    def __init__(self, slope_threshold: float = 0.0001) -> None:
        """
        Args:
            slope_threshold: Minimum PLdot slope to consider trending
                           (vs horizontal for congestion)
        """
        self.slope_threshold = slope_threshold

    def classify(self, intervals: Sequence[IntervalData], pldot_series: Sequence[PLDotSeries]) -> List[StateSeries]:
        """
        Classify market state for each bar based on PLdot relationship.

        Returns:
            List of state classifications, one per valid bar
        """
        if not intervals or not pldot_series:
            return []

        # Create lookup map for closes
        close_map = {bar.timestamp: bar.close for bar in intervals}
        ordered_pldot = sorted(pldot_series, key=lambda s: s.timestamp)

        results: List[StateSeries] = []

        # State tracking variables
        prev_state: MarketState | None = None
        bars_in_state = 0
        last_trend_direction: TrendDirection | None = None

        # NEW: Track trend at congestion entrance - preserved through entire congestion phase
        trend_at_congestion_entrance: TrendDirection | None = None
        bars_in_congestion = 0

        # Position tracking for 3-bar rule
        recent_positions: List[int] = []  # Track last 3 positions relative to PLdot

        for i, series in enumerate(ordered_pldot):
            close_price = close_map.get(series.timestamp)
            if close_price is None:
                continue

            # Determine position: 1=above, -1=below, 0=on PLdot
            position = _compare(close_price, series.value)
            recent_positions.append(position)
            if len(recent_positions) > 3:
                recent_positions.pop(0)

            # Classify PLdot slope
            pldot_slope_trend = self._classify_pldot_slope(series.slope)

            # Determine current state - now passing trend_at_congestion_entrance
            state, direction, reason = self._apply_state_rules(
                recent_positions,
                prev_state,
                last_trend_direction,
                bars_in_state,
                pldot_slope_trend,
                trend_at_congestion_entrance,  # NEW: Pass preserved trend
            )

            # Update tracking
            if state == prev_state:
                bars_in_state += 1
                reason = None  # No state change
            else:
                bars_in_state = 1

            # Update trend tracking
            if state == MarketState.TREND:
                last_trend_direction = direction
            elif state == MarketState.REVERSAL:
                last_trend_direction = direction

            # NEW: Track congestion entrance and duration
            # Only track congestion that follows a confirmed trend
            if state == MarketState.CONGESTION_ENTRANCE and prev_state == MarketState.TREND:
                # Entering congestion from a trend - capture the trend direction
                trend_at_congestion_entrance = last_trend_direction
                bars_in_congestion = 1
            elif state in [MarketState.CONGESTION_ACTION, MarketState.CONGESTION_ENTRANCE]:
                # Only increment if we're in "real" congestion (after a trend)
                if trend_at_congestion_entrance is not None:
                    bars_in_congestion += 1
                # If trend_at_congestion_entrance is None, we're in early indeterminate state
                # Don't track bars_in_congestion for these early states
            elif state in [MarketState.TREND, MarketState.REVERSAL, MarketState.CONGESTION_EXIT]:
                # Exiting congestion or in trend
                # Don't reset yet - we need the values for CONGESTION_EXIT classification
                pass

            # Calculate confidence
            confidence = self._calculate_confidence(
                state,
                bars_in_state,
                pldot_slope_trend,
                recent_positions,
                direction
            )

            # Create state point with new fields
            results.append(
                StateSeries(
                    timestamp=series.timestamp,
                    state=state,
                    trend_direction=direction,
                    bars_in_state=bars_in_state,
                    previous_state=prev_state if state != prev_state else None,
                    pldot_slope_trend=pldot_slope_trend,
                    confidence=confidence,
                    state_change_reason=reason if state != prev_state else None,
                    trend_at_congestion_entrance=trend_at_congestion_entrance,  # NEW
                    bars_in_congestion=bars_in_congestion,  # NEW
                )
            )

            # Reset congestion tracking after recording the exit bar
            if state in [MarketState.TREND, MarketState.REVERSAL]:
                trend_at_congestion_entrance = None
                bars_in_congestion = 0

            prev_state = state

        return results

    def _classify_pldot_slope(self, slope: Decimal) -> str:
        """Classify PLdot slope as rising, falling, or horizontal."""
        slope_float = float(slope)

        if abs(slope_float) < self.slope_threshold:
            return "horizontal"
        elif slope_float > 0:
            return "rising"
        else:
            return "falling"

    def _apply_state_rules(
        self,
        recent_positions: List[int],  # Last 3 bar positions vs PLdot
        previous_state: MarketState | None,
        prior_trend_direction: TrendDirection | None,
        bars_in_state: int,
        pldot_slope_trend: str,
        trend_at_congestion_entrance: TrendDirection | None = None,  # NEW: Preserved trend from congestion entrance
    ) -> tuple[MarketState, TrendDirection, str]:
        """
        Apply Drummond 3-bar state detection rules.

        The trend_at_congestion_entrance parameter ensures accurate classification
        of CONGESTION_EXIT vs REVERSAL even after extended congestion phases.
        During congestion, prior_trend_direction may drift, but trend_at_congestion_entrance
        preserves the original trend direction when congestion was entered.

        Returns:
            (state, trend_direction, reason_for_state)
        """
        if len(recent_positions) < 3:
            return (MarketState.CONGESTION_ACTION, TrendDirection.NEUTRAL, "Insufficient bars")

        # Check for 3 consecutive same-side closes
        all_above = all(p == 1 for p in recent_positions[-3:])
        all_below = all(p == -1 for p in recent_positions[-3:])

        # For congestion exit/reversal decisions, prefer the preserved trend from congestion entrance
        # This ensures accurate classification even after extended congestion phases
        effective_prior_trend = trend_at_congestion_entrance or prior_trend_direction

        # RULE 1: TREND - 3 consecutive closes on same side
        if all_above:
            if previous_state == MarketState.TREND and prior_trend_direction == TrendDirection.UP:
                return (MarketState.TREND, TrendDirection.UP, "Trend continuation")
            elif previous_state in [MarketState.CONGESTION_ACTION, MarketState.CONGESTION_ENTRANCE]:
                # Use effective_prior_trend for accurate exit vs reversal classification
                if effective_prior_trend == TrendDirection.UP:
                    return (MarketState.CONGESTION_EXIT, TrendDirection.UP, "Congestion exit to uptrend")
                elif effective_prior_trend == TrendDirection.DOWN:
                    # Had a downtrend before congestion, now reversing to uptrend
                    return (MarketState.REVERSAL, TrendDirection.UP, "Reversal to uptrend")
                else:
                    # No prior trend direction - this is a new trend from congestion
                    return (MarketState.TREND, TrendDirection.UP, "New uptrend from congestion")
            else:
                return (MarketState.TREND, TrendDirection.UP, "New uptrend established")

        if all_below:
            if previous_state == MarketState.TREND and prior_trend_direction == TrendDirection.DOWN:
                return (MarketState.TREND, TrendDirection.DOWN, "Trend continuation")
            elif previous_state in [MarketState.CONGESTION_ACTION, MarketState.CONGESTION_ENTRANCE]:
                # Use effective_prior_trend for accurate exit vs reversal classification
                if effective_prior_trend == TrendDirection.DOWN:
                    return (MarketState.CONGESTION_EXIT, TrendDirection.DOWN, "Congestion exit to downtrend")
                elif effective_prior_trend == TrendDirection.UP:
                    # Had an uptrend before congestion, now reversing to downtrend
                    return (MarketState.REVERSAL, TrendDirection.DOWN, "Reversal to downtrend")
                else:
                    # No prior trend direction - this is a new trend from congestion
                    return (MarketState.TREND, TrendDirection.DOWN, "New downtrend from congestion")
            else:
                return (MarketState.TREND, TrendDirection.DOWN, "New downtrend established")

        # RULE 2: CONGESTION ENTRANCE - First opposite close after trend
        if previous_state == MarketState.TREND:
            return (
                MarketState.CONGESTION_ENTRANCE,
                prior_trend_direction or TrendDirection.NEUTRAL,
                "First opposite close ends trend"
            )

        # RULE 3: CONGESTION ACTION - Alternating closes
        if previous_state in [MarketState.CONGESTION_ENTRANCE, MarketState.CONGESTION_ACTION, None]:
            return (
                MarketState.CONGESTION_ACTION,
                effective_prior_trend or TrendDirection.NEUTRAL,
                "Alternating closes indicate congestion"
            )

        # DEFAULT: Congestion action
        return (
            MarketState.CONGESTION_ACTION,
            TrendDirection.NEUTRAL,
            "Indeterminate - defaulting to congestion"
        )

    def _calculate_confidence(
        self,
        state: MarketState,
        bars_in_state: int,
        pldot_slope: str,
        recent_positions: List[int],
        direction: TrendDirection,
    ) -> Decimal:
        """
        Calculate confidence score (0.0-1.0) for state classification.

        Higher confidence when:
        - More bars in current state
        - PLdot slope aligns with trend state
        - Consistent positioning vs PLdot
        """
        confidence = Decimal("0.5")  # Base confidence

        # Increase confidence with duration in state
        duration_bonus = min(bars_in_state * 0.05, 0.3)
        confidence += Decimal(str(duration_bonus))

        # Trend confidence: PLdot slope should match
        if state == MarketState.TREND and len(recent_positions) >= 3:
            last_position = recent_positions[-1]
            if (direction == TrendDirection.UP and pldot_slope == "rising") or \
               (direction == TrendDirection.DOWN and pldot_slope == "falling"):
                confidence += Decimal("0.2")

        # Congestion confidence: PLdot should be horizontal
        if state in [MarketState.CONGESTION_ACTION, MarketState.CONGESTION_ENTRANCE]:
            if pldot_slope == "horizontal":
                confidence += Decimal("0.15")

        # Consistency bonus: all recent positions same side
        if len(recent_positions) >= 3 and len(set(recent_positions[-3:])) == 1:
            confidence += Decimal("0.1")

        return min(confidence, Decimal("1.0"))


def _compare(a: Decimal, b: Decimal) -> int:
    if a > b:
        return 1
    if a < b:
        return -1
    return 0


def _sign(value: Decimal) -> int:
    if value > 0:
        return 1
    if value < 0:
        return -1
    return 0


__all__ = ["MarketStateClassifier", "MarketState", "TrendDirection", "StateSeries"]
