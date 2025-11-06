# Drummond Geometry Implementation Remediation Plan
## Phase 2B: Complete Core Methodology

**Status:** REQUIRED BEFORE PRODUCTION
**Estimated Timeline:** 12-16 weeks (3-4 months)
**Difficulty:** High (requires deep understanding of Drummond methodology)

---

## Executive Summary

This plan details the work required to transform the current partial implementation into a production-ready Drummond Geometry trading system. The plan is divided into 6 major work streams, each with specific deliverables and acceptance criteria.

---

## Work Stream 1: Market State Detection System
**Duration:** 2-3 weeks | **Priority:** CRITICAL | **Dependencies:** None

### Objective
Implement the 5-state classification system that is the foundation of all Drummond trading decisions.

### Specification Reference
> "The trader identifies the current market state based on a set of clear, unambiguous rules concerning the price's relationship to the PLdot line:
> 1. Trend Trading: Three consecutive bars close on same side of PLdot
> 2. Congestion Entrance: First bar closes on opposite side after trend
> 3. Congestion Action: Alternating closes without new 3-bar trend
> 4. Congestion Exit: Market resuming original trend
> 5. Trend Reversal: Three consecutive bars close on opposite side from prior trend"

### Technical Implementation

#### 1.1 Create Market State Module

**File:** `src/dgas/calculations/market_state.py`

```python
"""Market state classification for Drummond Geometry."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import List, Sequence

from ..data.models import IntervalData
from .pldot import PLDotSeries


class TradingState(Enum):
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
class MarketStatePoint:
    """Single point-in-time market state classification."""
    timestamp: datetime
    state: TradingState
    trend_direction: TrendDirection
    bars_in_state: int
    previous_state: TradingState | None
    pldot_slope_trend: str  # "rising", "falling", "horizontal"
    confidence: Decimal
    state_change_reason: str | None = None


class MarketStateClassifier:
    """
    Classify market states using the 3-bar rule.

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
            slope_threshold: Minimum slope to consider PLdot trending
                            (vs horizontal for congestion)
        """
        self.slope_threshold = slope_threshold

    def classify_states(
        self,
        intervals: Sequence[IntervalData],
        pldot_series: Sequence[PLDotSeries]
    ) -> List[MarketStatePoint]:
        """
        Classify market state for each bar.

        Returns:
            List of state classifications, one per interval
        """
        if len(intervals) < 3 or len(pldot_series) < 3:
            raise ValueError("At least 3 bars required for state classification")

        # Align intervals with PLdot values
        aligned = self._align_data(intervals, pldot_series)

        states: List[MarketStatePoint] = []
        prior_trend_direction: TrendDirection | None = None
        bars_in_current_state = 0
        previous_state: TradingState | None = None

        for i in range(2, len(aligned)):  # Need 3 bars to start
            current_bar = aligned[i]
            prev_2_bars = aligned[i-2:i]

            # Determine position relative to PLdot for last 3 bars
            positions = [
                self._bar_position_vs_pldot(bar["interval"], bar["pldot"])
                for bar in [prev_2_bars[0], prev_2_bars[1], current_bar]
            ]

            # Get PLdot slope trend
            pldot_slope_trend = self._classify_pldot_slope(current_bar["pldot"])

            # Apply 3-bar state detection logic
            state, direction, reason = self._apply_state_rules(
                positions,
                previous_state,
                prior_trend_direction,
                bars_in_current_state
            )

            # Update counters
            if state == previous_state:
                bars_in_current_state += 1
            else:
                bars_in_current_state = 1

            # Calculate confidence
            confidence = self._calculate_confidence(
                state,
                bars_in_current_state,
                pldot_slope_trend,
                positions
            )

            state_point = MarketStatePoint(
                timestamp=current_bar["interval"].timestamp,
                state=state,
                trend_direction=direction,
                bars_in_state=bars_in_current_state,
                previous_state=previous_state,
                pldot_slope_trend=pldot_slope_trend,
                confidence=confidence,
                state_change_reason=reason if state != previous_state else None
            )

            states.append(state_point)

            # Update for next iteration
            previous_state = state
            if state == TradingState.TREND:
                prior_trend_direction = direction

        return states

    def _align_data(
        self,
        intervals: Sequence[IntervalData],
        pldot_series: Sequence[PLDotSeries]
    ) -> List[dict]:
        """Align interval data with corresponding PLdot values."""
        pldot_map = {p.timestamp: p for p in pldot_series}
        aligned = []
        for interval in intervals:
            if interval.timestamp in pldot_map:
                aligned.append({
                    "interval": interval,
                    "pldot": pldot_map[interval.timestamp]
                })
        return aligned

    def _bar_position_vs_pldot(
        self,
        interval: IntervalData,
        pldot: PLDotSeries
    ) -> str:
        """
        Determine if bar closed above or below PLdot.

        Returns:
            "above", "below", or "on" (rare)
        """
        close = interval.close
        pldot_value = pldot.value

        if close > pldot_value:
            return "above"
        elif close < pldot_value:
            return "below"
        else:
            return "on"  # Exact match - treat as previous direction

    def _classify_pldot_slope(self, pldot: PLDotSeries) -> str:
        """Classify PLdot slope as rising, falling, or horizontal."""
        slope = float(pldot.slope)

        if abs(slope) < self.slope_threshold:
            return "horizontal"
        elif slope > 0:
            return "rising"
        else:
            return "falling"

    def _apply_state_rules(
        self,
        positions: List[str],  # Last 3 bar positions vs PLdot
        previous_state: TradingState | None,
        prior_trend_direction: TrendDirection | None,
        bars_in_state: int
    ) -> tuple[TradingState, TrendDirection, str]:
        """
        Apply Drummond 3-bar state detection rules.

        Returns:
            (state, trend_direction, reason_for_state)
        """
        # Count consecutive positions
        all_above = all(p == "above" for p in positions)
        all_below = all(p == "below" for p in positions)

        # RULE 1: TREND - 3 consecutive closes on same side
        if all_above:
            if previous_state == TradingState.TREND and prior_trend_direction == TrendDirection.UP:
                return (TradingState.TREND, TrendDirection.UP, "Trend continuation")
            elif previous_state in [TradingState.CONGESTION_ACTION, TradingState.CONGESTION_ENTRANCE]:
                if prior_trend_direction == TrendDirection.UP:
                    return (TradingState.CONGESTION_EXIT, TrendDirection.UP, "Congestion exit to uptrend")
                else:
                    return (TradingState.REVERSAL, TrendDirection.UP, "Reversal to uptrend")
            else:
                return (TradingState.TREND, TrendDirection.UP, "New uptrend established")

        if all_below:
            if previous_state == TradingState.TREND and prior_trend_direction == TrendDirection.DOWN:
                return (TradingState.TREND, TrendDirection.DOWN, "Trend continuation")
            elif previous_state in [TradingState.CONGESTION_ACTION, TradingState.CONGESTION_ENTRANCE]:
                if prior_trend_direction == TrendDirection.DOWN:
                    return (TradingState.CONGESTION_EXIT, TrendDirection.DOWN, "Congestion exit to downtrend")
                else:
                    return (TradingState.REVERSAL, TrendDirection.DOWN, "Reversal to downtrend")
            else:
                return (TradingState.TREND, TrendDirection.DOWN, "New downtrend established")

        # RULE 2: CONGESTION ENTRANCE - First opposite close after trend
        if previous_state == TradingState.TREND:
            return (
                TradingState.CONGESTION_ENTRANCE,
                prior_trend_direction or TrendDirection.NEUTRAL,
                "First opposite close ends trend"
            )

        # RULE 3: CONGESTION ACTION - Alternating closes
        if previous_state in [TradingState.CONGESTION_ENTRANCE, TradingState.CONGESTION_ACTION]:
            return (
                TradingState.CONGESTION_ACTION,
                prior_trend_direction or TrendDirection.NEUTRAL,
                "Alternating closes indicate congestion"
            )

        # DEFAULT: If no clear state, assume congestion action
        return (
            TradingState.CONGESTION_ACTION,
            TrendDirection.NEUTRAL,
            "Indeterminate - defaulting to congestion"
        )

    def _calculate_confidence(
        self,
        state: TradingState,
        bars_in_state: int,
        pldot_slope: str,
        recent_positions: List[str]
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
        if state == TradingState.TREND:
            recent_direction = "up" if recent_positions[-1] == "above" else "down"
            if (recent_direction == "up" and pldot_slope == "rising") or \
               (recent_direction == "down" and pldot_slope == "falling"):
                confidence += Decimal("0.2")

        # Congestion confidence: PLdot should be horizontal
        if state in [TradingState.CONGESTION_ACTION, TradingState.CONGESTION_ENTRANCE]:
            if pldot_slope == "horizontal":
                confidence += Decimal("0.15")

        return min(confidence, Decimal("1.0"))


__all__ = [
    "TradingState",
    "TrendDirection",
    "MarketStatePoint",
    "MarketStateClassifier"
]
```

#### 1.2 Database Integration

**File:** `src/dgas/data/repository.py` (add new function)

```python
def bulk_insert_market_states(
    conn: Connection,
    symbol_id: int,
    states: Sequence[MarketStatePoint]
) -> int:
    """Persist market state classifications to database."""
    if not states:
        return 0

    records = [
        (
            symbol_id,
            state.timestamp,
            state.state.value,
            state.trend_direction.value,
            state.state.value,  # congestion_state (simplified)
            state.state.value if state.state == TradingState.REVERSAL else "none",
            float(state.confidence),
            float(state.confidence),
            float(state.confidence),
            state.bars_in_state,
            state.previous_state.value if state.previous_state else None,
            state.state_change_reason,
            None,  # volatility_index (TODO)
            None,  # momentum_score (TODO)
        )
        for state in states
    ]

    insert_sql = """
        INSERT INTO market_state (
            symbol_id, timestamp, trend_state, congestion_state,
            reversal_state, trend_confidence, congestion_confidence,
            reversal_confidence, state_duration_intervals, previous_state,
            state_change_reason, volatility_index, momentum_score
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
        )
        ON CONFLICT (symbol_id, timestamp) DO UPDATE SET
            trend_state = EXCLUDED.trend_state,
            trend_confidence = EXCLUDED.trend_confidence;
    """

    with conn.cursor() as cur:
        cur.executemany(insert_sql, records)

    return len(records)
```

#### 1.3 Unit Tests

**File:** `tests/calculations/test_market_state.py`

```python
"""Tests for market state classification."""

import pytest
from decimal import Decimal
from datetime import datetime, timezone, timedelta

from dgas.calculations.market_state import (
    MarketStateClassifier,
    TradingState,
    TrendDirection
)
from dgas.data.models import IntervalData
from dgas.calculations.pldot import PLDotSeries


def create_test_bar(
    timestamp: datetime,
    close: float,
    high: float | None = None,
    low: float | None = None
) -> IntervalData:
    """Helper to create test intervals."""
    high = high or close * 1.01
    low = low or close * 0.99
    return IntervalData(
        symbol="TEST",
        exchange="US",
        timestamp=timestamp,
        interval="1d",
        open=Decimal(str(close)),
        high=Decimal(str(high)),
        low=Decimal(str(low)),
        close=Decimal(str(close)),
        adjusted_close=None,
        volume=1000000
    )


def create_test_pldot(
    timestamp: datetime,
    value: float,
    slope: float = 0.0
) -> PLDotSeries:
    """Helper to create test PLdot values."""
    return PLDotSeries(
        timestamp=timestamp,
        value=Decimal(str(value)),
        projected_timestamp=timestamp + timedelta(days=1),
        projected_value=Decimal(str(value)),
        slope=Decimal(str(slope)),
        displacement=1
    )


class TestMarketStateClassifier:
    """Test market state detection logic."""

    def test_uptrend_detection(self):
        """Test detection of uptrend (3 closes above PLdot)."""
        classifier = MarketStateClassifier()

        base_time = datetime(2024, 1, 1, tzinfo=timezone.utc)

        # Create 3 bars closing above PLdot
        intervals = [
            create_test_bar(base_time, close=101.0),
            create_test_bar(base_time + timedelta(days=1), close=102.0),
            create_test_bar(base_time + timedelta(days=2), close=103.0),
        ]

        pldots = [
            create_test_pldot(base_time, value=100.0, slope=0.5),
            create_test_pldot(base_time + timedelta(days=1), value=100.5, slope=0.5),
            create_test_pldot(base_time + timedelta(days=2), value=101.0, slope=0.5),
        ]

        states = classifier.classify_states(intervals, pldots)

        assert len(states) == 1
        assert states[0].state == TradingState.TREND
        assert states[0].trend_direction == TrendDirection.UP
        assert states[0].bars_in_state == 1

    def test_congestion_entrance(self):
        """Test detection of congestion entrance after trend."""
        classifier = MarketStateClassifier()

        base_time = datetime(2024, 1, 1, tzinfo=timezone.utc)

        # 3 bars up, then 1 bar below PLdot
        intervals = [
            create_test_bar(base_time, close=101.0),
            create_test_bar(base_time + timedelta(days=1), close=102.0),
            create_test_bar(base_time + timedelta(days=2), close=103.0),
            create_test_bar(base_time + timedelta(days=3), close=99.0),  # Crosses below
        ]

        pldots = [
            create_test_pldot(base_time, value=100.0, slope=0.5),
            create_test_pldot(base_time + timedelta(days=1), value=100.5, slope=0.5),
            create_test_pldot(base_time + timedelta(days=2), value=101.0, slope=0.5),
            create_test_pldot(base_time + timedelta(days=3), value=101.5, slope=0.1),
        ]

        states = classifier.classify_states(intervals, pldots)

        assert len(states) == 2
        assert states[0].state == TradingState.TREND
        assert states[1].state == TradingState.CONGESTION_ENTRANCE

    def test_reversal_detection(self):
        """Test trend reversal (3 closes on opposite side)."""
        classifier = MarketStateClassifier()

        base_time = datetime(2024, 1, 1, tzinfo=timezone.utc)

        # Uptrend (3 bars), congestion (2 bars), then downtrend (3 bars)
        intervals = [
            create_test_bar(base_time, close=101.0),
            create_test_bar(base_time + timedelta(days=1), close=102.0),
            create_test_bar(base_time + timedelta(days=2), close=103.0),
            create_test_bar(base_time + timedelta(days=3), close=99.0),
            create_test_bar(base_time + timedelta(days=4), close=101.0),
            create_test_bar(base_time + timedelta(days=5), close=97.0),
            create_test_bar(base_time + timedelta(days=6), close=96.0),
            create_test_bar(base_time + timedelta(days=7), close=95.0),
        ]

        pldots = [
            create_test_pldot(t, value=100.0 + i * 0.2, slope=0.2 if i < 5 else -0.5)
            for i, t in enumerate(base_time + timedelta(days=d) for d in range(8))
        ]

        states = classifier.classify_states(intervals, pldots)

        # Should detect: TREND(up) -> CONGESTION_ENTRANCE -> CONGESTION_ACTION -> REVERSAL(down)
        reversal_states = [s for s in states if s.state == TradingState.REVERSAL]
        assert len(reversal_states) > 0
        assert reversal_states[0].trend_direction == TrendDirection.DOWN
```

### Acceptance Criteria

- [ ] All 5 states can be correctly identified
- [ ] State transitions follow Drummond 3-bar rules
- [ ] Confidence scores are calculated and meaningful
- [ ] Unit tests achieve 90%+ coverage
- [ ] Can populate `market_state` database table
- [ ] Performance: Can classify 10,000 bars in <1 second

---

## Work Stream 2: Envelope Calculation Fix
**Duration:** 1-2 weeks | **Priority:** HIGH | **Dependencies:** None

### Objective
Replace incorrect 14-period ATR envelope with correct 3-period Drummond envelope.

### Current Problem
```python
# WRONG: Using 14-period ATR (envelopes.py:30)
def __init__(self, method: str = "atr", period: int = 14,
```

### Specification Requirement
> "Two bands are plotted around the PLdot, typically based on a **3-period moving average**."

### Implementation

#### 2.1 Research Phase (Week 1, Days 1-2)

**Task:** Determine exact Drummond envelope formula

The specification mentions "3-period moving average" but doesn't specify:
- 3-period of what? (PLdot values, price ranges, ATR?)
- How to calculate band width?

**Action Items:**
1. Review original Drummond publications (in course materials)
2. Check TradingView open-source implementations
3. Document the actual formula used

**Likely Formula (to verify):**
```python
# Hypothesis: 3-period range of PLdot values
pldot_std = pldot_values.rolling(3).std()
upper_band = pldot_value + (pldot_std * multiplier)
lower_band = pldot_value - (pldot_std * multiplier)
```

#### 2.2 Implementation (Week 1, Days 3-5)

**File:** `src/dgas/calculations/envelopes.py`

```python
# Replace the ATR calculation with correct 3-period method

def __init__(
    self,
    period: int = 3,  # CHANGED from 14 to 3
    multiplier: float = 1.5,  # Verify this value
    method: str = "pldot_range"  # New default method
) -> None:
    """
    Calculate Drummond envelope bands.

    Args:
        period: Number of PLdot values to use for range calc (default: 3)
        multiplier: Band width multiplier (default: 1.5, verify against spec)
        method: "pldot_range" (Drummond) or "atr" (legacy)
    """
    if period <= 0:
        raise ValueError("period must be positive")
    if multiplier <= 0:
        raise ValueError("multiplier must be positive")
    if method not in {"pldot_range", "atr"}:
        raise ValueError("method must be 'pldot_range' or 'atr'")

    self.period = period
    self.multiplier = multiplier
    self.method = method


def from_intervals(
    self,
    intervals: Sequence[IntervalData],
    pldot: Sequence[PLDotSeries]
) -> List[EnvelopeSeries]:
    # ... existing alignment code ...

    if self.method == "pldot_range":
        # CORRECT DRUMMOND METHOD
        # Calculate rolling standard deviation of PLdot values
        pldot_volatility = df["value"].rolling(
            window=self.period,
            min_periods=self.period
        ).std()

        offset = pldot_volatility * self.multiplier

    elif self.method == "atr":
        # LEGACY METHOD (for comparison only)
        # ... keep existing ATR code ...

    # ... rest of envelope calculation ...
```

#### 2.3 Add C-Wave Detection (Week 2)

```python
@dataclass(frozen=True)
class CWaveDetection:
    """Detected C-Wave pattern (envelope moving with trend)."""
    start_timestamp: datetime
    end_timestamp: datetime
    direction: Literal["up", "down"]
    strength: Decimal  # How consistently price stays at envelope
    bars_in_pattern: int


def detect_c_wave(
    envelopes: Sequence[EnvelopeSeries],
    intervals: Sequence[IntervalData],
    lookback: int = 10,
    threshold: float = 0.8  # 80% of bars must close at/beyond envelope
) -> List[CWaveDetection]:
    """
    Detect C-Wave pattern: envelope itself moving with trend.

    A C-Wave occurs when:
    - Price consistently closes at or beyond envelope boundary
    - The envelope boundary itself is sloping in direction of trend
    - Indicates very strong, sustained trend
    """
    # Implementation details...
    pass
```

### Acceptance Criteria

- [ ] Envelope period changed from 14 to 3
- [ ] Correct Drummond formula implemented
- [ ] C-Wave detection functional
- [ ] Side-by-side comparison shows significant difference from ATR method
- [ ] Unit tests verify correct band calculations
- [ ] Documentation updated with formula details

---

## Work Stream 3: Multi-Timeframe Infrastructure
**Duration:** 3-4 weeks | **Priority:** CRITICAL | **Dependencies:** WS1 (State Detection)

### Objective
Build the infrastructure to analyze multiple timeframes simultaneously and detect confluence zones.

### Specification Requirement
> "Research has suggested that trading on these aligned signals can improve success ratios by **up to three times** compared to single-timeframe analysis."

### Architecture Design

#### 3.1 Multi-Timeframe Data Model

**File:** `src/dgas/calculations/multi_timeframe.py`

```python
"""Multi-timeframe analysis and coordination."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import List, Sequence, Literal

from ..data.models import IntervalData
from .pldot import PLDotSeries
from .envelopes import EnvelopeSeries
from .drummond_lines import DrummondZone
from .market_state import MarketStatePoint


TimeframeName = Literal["1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w", "1mo"]


@dataclass(frozen=True)
class TimeframeData:
    """Complete analysis for a single timeframe."""
    timeframe: TimeframeName
    intervals: List[IntervalData]
    pldot: List[PLDotSeries]
    envelopes: List[EnvelopeSeries]
    zones: List[DrummondZone]
    states: List[MarketStatePoint]


@dataclass(frozen=True)
class PLDotOverlay:
    """Higher timeframe PLdot value overlaid on focus timeframe."""
    focus_timestamp: datetime  # When to display on focus chart
    htf_timestamp: datetime    # Source timestamp from HTF
    htf_timeframe: TimeframeName
    pldot_value: Decimal
    trend_direction: str


@dataclass(frozen=True)
class ConfluenceZone:
    """
    Support/resistance zone confirmed by multiple timeframes.

    These are the HIGH-PROBABILITY zones where Drummond traders
    should focus their attention.
    """
    center_price: Decimal
    lower_price: Decimal
    upper_price: Decimal
    zone_type: Literal["support", "resistance"]

    # Timeframes contributing to this zone
    contributing_timeframes: List[TimeframeName]

    # Strength metrics
    confluence_strength: int  # How many timeframes align (2-3+)
    combined_zone_strength: Decimal  # Sum of individual zone strengths

    # Context
    htf_trend_aligned: bool  # Does this align with HTF trend?
    state_context: str       # What state is market in at this zone?


@dataclass
class MultiTimeframeAnalysis:
    """
    Complete multi-timeframe analysis setup.

    This is the primary object for Drummond Geometry trading.
    """
    symbol: str

    # The three timeframes
    htf: TimeframeData        # Higher (context)
    focus: TimeframeData      # Primary (execution)
    ltf: TimeframeData        # Lower (monitoring)

    # Cross-timeframe analysis
    htf_overlays: List[PLDotOverlay]
    confluence_zones: List[ConfluenceZone]

    def get_current_htf_trend(self) -> str:
        """Return current higher timeframe trend."""
        if not self.htf.states:
            return "unknown"
        return self.htf.states[-1].trend_direction.value

    def get_nearest_confluence_zone(
        self,
        current_price: Decimal,
        zone_type: Literal["support", "resistance"] | None = None
    ) -> ConfluenceZone | None:
        """Find nearest high-probability zone for trade setup."""
        zones = self.confluence_zones
        if zone_type:
            zones = [z for z in zones if z.zone_type == zone_type]

        if not zones:
            return None

        # Sort by distance from current price
        sorted_zones = sorted(
            zones,
            key=lambda z: abs(float(z.center_price - current_price))
        )

        return sorted_zones[0]

    def is_high_probability_setup(
        self,
        signal_price: Decimal,
        signal_direction: Literal["long", "short"]
    ) -> tuple[bool, str]:
        """
        Validate if a signal is high-probability.

        Returns:
            (is_valid, reason)
        """
        # Check HTF trend alignment
        htf_trend = self.get_current_htf_trend()
        if signal_direction == "long" and htf_trend == "down":
            return (False, "Counter to HTF downtrend")
        if signal_direction == "short" and htf_trend == "up":
            return (False, "Counter to HTF uptrend")

        # Check for confluence zone nearby
        zone_type = "support" if signal_direction == "long" else "resistance"
        nearest_zone = self.get_nearest_confluence_zone(signal_price, zone_type)

        if not nearest_zone:
            return (False, "No confluence zone nearby")

        # Check distance to zone
        distance_pct = abs(
            float(signal_price - nearest_zone.center_price) /
            float(nearest_zone.center_price)
        ) * 100

        if distance_pct > 2.0:  # More than 2% away
            return (False, f"Too far from confluence zone ({distance_pct:.1f}%)")

        # Check confluence strength
        if nearest_zone.confluence_strength < 2:
            return (False, "Weak confluence (only 1 timeframe)")

        # All checks passed
        return (True, f"High-probability: {nearest_zone.confluence_strength}TF confluence at {zone_type}")
```

#### 3.2 Timeframe Coordination Logic

```python
class MultiTimeframeCoordinator:
    """Coordinate analysis across multiple timeframes."""

    def __init__(
        self,
        htf_timeframe: TimeframeName,
        focus_timeframe: TimeframeName,
        ltf_timeframe: TimeframeName
    ) -> None:
        """
        Initialize coordinator with timeframe structure.

        Example:
            coordinator = MultiTimeframeCoordinator(
                htf_timeframe="1w",    # Weekly
                focus_timeframe="1d",  # Daily
                ltf_timeframe="1h"     # Hourly
            )
        """
        self.htf_timeframe = htf_timeframe
        self.focus_timeframe = focus_timeframe
        self.ltf_timeframe = ltf_timeframe

    def build_analysis(
        self,
        symbol: str,
        htf_intervals: List[IntervalData],
        focus_intervals: List[IntervalData],
        ltf_intervals: List[IntervalData]
    ) -> MultiTimeframeAnalysis:
        """
        Build complete multi-timeframe analysis.

        This is the main entry point for creating a full
        Drummond Geometry analysis.
        """
        # Calculate all components for each timeframe
        htf_data = self._analyze_timeframe(htf_intervals, self.htf_timeframe)
        focus_data = self._analyze_timeframe(focus_intervals, self.focus_timeframe)
        ltf_data = self._analyze_timeframe(ltf_intervals, self.ltf_timeframe)

        # Overlay HTF PLdot on focus timeframe
        htf_overlays = self._create_htf_overlays(
            htf_pldot=htf_data.pldot,
            focus_intervals=focus_intervals
        )

        # Detect confluence zones
        confluence_zones = self._detect_confluence_zones(
            htf_zones=htf_data.zones,
            focus_zones=focus_data.zones,
            htf_state=htf_data.states[-1] if htf_data.states else None
        )

        return MultiTimeframeAnalysis(
            symbol=symbol,
            htf=htf_data,
            focus=focus_data,
            ltf=ltf_data,
            htf_overlays=htf_overlays,
            confluence_zones=confluence_zones
        )

    def _analyze_timeframe(
        self,
        intervals: List[IntervalData],
        timeframe: TimeframeName
    ) -> TimeframeData:
        """Run full analysis on single timeframe."""
        from .pldot import PLDotCalculator
        from .envelopes import EnvelopeCalculator
        from .drummond_lines import DrummondLineCalculator, aggregate_zones
        from .market_state import MarketStateClassifier

        # Calculate PLdot
        pldot_calc = PLDotCalculator(displacement=1)
        pldot = pldot_calc.from_intervals(intervals)

        # Calculate envelopes
        envelope_calc = EnvelopeCalculator(period=3, method="pldot_range")
        envelopes = envelope_calc.from_intervals(intervals, pldot)

        # Calculate Drummond lines and zones
        line_calc = DrummondLineCalculator(projection_gap=1)
        lines = line_calc.from_intervals(intervals)
        zones = aggregate_zones(lines, tolerance=0.5)  # TODO: Make tolerance dynamic

        # Classify market states
        state_classifier = MarketStateClassifier()
        states = state_classifier.classify_states(intervals, pldot)

        return TimeframeData(
            timeframe=timeframe,
            intervals=intervals,
            pldot=pldot,
            envelopes=envelopes,
            zones=zones,
            states=states
        )

    def _create_htf_overlays(
        self,
        htf_pldot: List[PLDotSeries],
        focus_intervals: List[IntervalData]
    ) -> List[PLDotOverlay]:
        """
        Overlay HTF PLdot values onto focus timeframe chart.

        For each HTF PLdot bar, create entries for all focus timeframe
        bars that fall within that HTF bar's time period.
        """
        overlays: List[PLDotOverlay] = []

        for htf_bar in htf_pldot:
            # Find all focus bars within this HTF bar's time period
            # (This requires understanding HTF bar boundaries)
            htf_start = htf_bar.timestamp
            htf_end = htf_bar.projected_timestamp

            for focus_bar in focus_intervals:
                if htf_start <= focus_bar.timestamp < htf_end:
                    overlays.append(PLDotOverlay(
                        focus_timestamp=focus_bar.timestamp,
                        htf_timestamp=htf_start,
                        htf_timeframe=self.htf_timeframe,
                        pldot_value=htf_bar.value,
                        trend_direction=self._slope_to_direction(htf_bar.slope)
                    ))

        return overlays

    def _detect_confluence_zones(
        self,
        htf_zones: List[DrummondZone],
        focus_zones: List[DrummondZone],
        htf_state: MarketStatePoint | None
    ) -> List[ConfluenceZone]:
        """
        Identify zones where HTF and focus timeframes align.

        These are the magic zones with 3x better probability.
        """
        confluence_zones: List[ConfluenceZone] = []

        for focus_zone in focus_zones:
            overlapping_htf = []

            # Check each HTF zone for overlap with this focus zone
            for htf_zone in htf_zones:
                if htf_zone.line_type != focus_zone.line_type:
                    continue  # Support doesn't align with resistance

                # Check for price overlap (within 2% tolerance)
                overlap_pct = self._calculate_zone_overlap(focus_zone, htf_zone)
                if overlap_pct > 0.5:  # >50% overlap
                    overlapping_htf.append((htf_zone, overlap_pct))

            if overlapping_htf:
                # This is a confluence zone!
                combined_strength = (
                    focus_zone.strength +
                    sum(htf.strength for htf, _ in overlapping_htf)
                )

                htf_trend_aligned = False
                if htf_state:
                    trend_dir = htf_state.trend_direction.value
                    if (trend_dir == "up" and focus_zone.line_type == "support") or \
                       (trend_dir == "down" and focus_zone.line_type == "resistance"):
                        htf_trend_aligned = True

                confluence_zones.append(ConfluenceZone(
                    center_price=focus_zone.center_price,
                    lower_price=focus_zone.lower_price,
                    upper_price=focus_zone.upper_price,
                    zone_type=focus_zone.line_type,
                    contributing_timeframes=[
                        self.focus_timeframe,
                        self.htf_timeframe
                    ],
                    confluence_strength=1 + len(overlapping_htf),
                    combined_zone_strength=Decimal(str(combined_strength)),
                    htf_trend_aligned=htf_trend_aligned,
                    state_context=htf_state.state.value if htf_state else "unknown"
                ))

        # Sort by strength (strongest first)
        confluence_zones.sort(
            key=lambda z: (z.confluence_strength, float(z.combined_zone_strength)),
            reverse=True
        )

        return confluence_zones

    def _calculate_zone_overlap(
        self,
        zone1: DrummondZone,
        zone2: DrummondZone
    ) -> float:
        """
        Calculate percentage overlap between two price zones.

        Returns:
            0.0 (no overlap) to 1.0 (complete overlap)
        """
        # Find overlapping range
        overlap_lower = max(float(zone1.lower_price), float(zone2.lower_price))
        overlap_upper = min(float(zone1.upper_price), float(zone2.upper_price))

        if overlap_lower >= overlap_upper:
            return 0.0  # No overlap

        overlap_size = overlap_upper - overlap_lower
        zone1_size = float(zone1.upper_price - zone1.lower_price)

        return overlap_size / zone1_size if zone1_size > 0 else 0.0

    @staticmethod
    def _slope_to_direction(slope: Decimal) -> str:
        """Convert PLdot slope to trend direction string."""
        if slope > Decimal("0.0001"):
            return "rising"
        elif slope < Decimal("-0.0001"):
            return "falling"
        else:
            return "horizontal"
```

### Acceptance Criteria

- [ ] Can load and analyze 3 timeframes simultaneously
- [ ] HTF PLdot values correctly overlay on focus chart
- [ ] Confluence zones are detected when zones align across timeframes
- [ ] Confluence strength scoring is implemented
- [ ] Can filter signals by HTF trend
- [ ] Integration tests verify multi-timeframe workflow
- [ ] Performance: Analyze 3 timeframes in <5 seconds

---

## Work Stream 4-6: [Abbreviated for length - full plan would continue...]

**Work Stream 4:** Pattern Recognition (3 weeks)
- Implement: PLdot Push, Refresh, Exhaust, C-Wave, Congestion Oscillation detectors
- Each pattern returns actionable trade setup

**Work Stream 5:** Signal Generation & Risk Management (2 weeks)
- Entry signal generator (state + pattern + confluence)
- Stop-loss calculator (envelope-based, state-aware)
- Position sizing (based on stop distance)

**Work Stream 6:** Drummond Lines Enhancement (2 weeks)
- Significant bar selection (swing highs/lows only)
- Touch counting for strength
- Dynamic zone tolerance (ATR-based)
- Line expiration logic

---

## Implementation Timeline

```
Week 1-2:   Market State Detection (WS1)
Week 3:     Envelope Fix (WS2)
Week 4-6:   Multi-Timeframe Infrastructure (WS3)
Week 7-9:   Pattern Recognition (WS4)
Week 10-11: Signal Generation (WS5)
Week 12:    Drummond Lines Enhancement (WS6)
Week 13-14: Integration, Testing, Documentation
Week 15-16: Buffer for issues and refinement

Total: 16 weeks (4 months)
```

---

## Success Metrics

Upon completion, the system must demonstrate:

1. **Correctness**
   - All 5 market states detected with >95% accuracy vs manual classification
   - Multi-timeframe confluence zones match visual analysis

2. **Completeness**
   - All database schema fields can be populated
   - No "NotImplementedError" exceptions remain

3. **Performance**
   - Process 5 years of daily data for 10 symbols in <30 seconds
   - Real-time analysis (<1 second per symbol update)

4. **Usability**
   - CLI command: `dgas analyze SPY --htf weekly --focus daily --ltf hourly`
   - Returns confluence zones and current market state
   - Exportable reports for backtesting

---

## Risk Mitigation

### Technical Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Incorrect Drummond formula interpretation | High | Critical | Validate against TradingView open-source, ask in forums |
| Multi-timeframe alignment bugs | Medium | High | Extensive unit tests with known examples |
| Performance issues with large datasets | Low | Medium | Profile early, optimize hot paths |

### Schedule Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Underestimated complexity | Medium | High | 2-week buffer in timeline |
| Dependency on external research | High | Medium | Start WS2 research immediately |
| Team capacity constraints | Medium | High | Prioritize WS1 and WS3 (most critical) |

---

## Conclusion

This plan represents the minimum work required to transform the current implementation into a production-ready Drummond Geometry system. The 16-week timeline is aggressive but achievable with focused effort.

The current system is NOT broken - it's incomplete. The foundation is solid. With these additions, it will become a powerful, theoretically-sound trading system worthy of institutional use.

**Next Steps:**
1. Review and approve this plan
2. Allocate development resources
3. Begin WS1 (Market State Detection) immediately
4. Set up weekly progress reviews

---

**Plan Version:** 1.0
**Last Updated:** 2025-01-06
**Status:** PENDING APPROVAL
