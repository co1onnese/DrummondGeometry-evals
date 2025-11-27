# Drummond Geometry Implementation Improvement Plan

**Document Version:** 1.0  
**Date:** 2024  
**Author:** Senior Quant Developer Review  
**Status:** Implementation Ready

---

## Executive Summary

This document outlines the implementation plan to address five priority improvements identified during a comprehensive code review comparing the DGAS implementation against the documented Drummond Geometry methodology. These improvements will enhance signal accuracy, reduce false signals, and better align the system with the original Drummond Geometry principles.

---

## Table of Contents

1. [Priority 1: Drummond Line Termination Detection](#priority-1-drummond-line-termination-detection)
2. [Priority 2: Exhaust-Based Exit Signals](#priority-2-exhaust-based-exit-signals)
3. [Priority 3: Congestion State Tracking Fix](#priority-3-congestion-state-tracking-fix)
4. [Priority 4: Tiered Signal Confidence System](#priority-4-tiered-signal-confidence-system)
5. [Priority 5: Envelope Calculation Validation](#priority-5-envelope-calculation-validation)
6. [Implementation Timeline](#implementation-timeline)
7. [Testing Strategy](#testing-strategy)
8. [Risk Assessment](#risk-assessment)

---

## Priority 1: Drummond Line Termination Detection

### Background

Drummond Geometry's core innovation is the projection of two-bar trendlines forward to identify "termination points" where price energy is expected to exhaust. While the current implementation calculates these lines (`drummond_lines.py`), it does not detect when price approaches or reaches these projected levels.

### Current State

- `DrummondLineCalculator` generates support/resistance lines from consecutive bar highs/lows
- `aggregate_zones()` clusters nearby projected prices into zones
- **Gap:** No pattern detector fires when price interacts with these projected levels

### Implementation Plan

#### 1.1 Add New Pattern Type

**File:** `src/dgas/calculations/patterns.py`

```python
class PatternType(Enum):
    # ... existing patterns ...
    TERMINATION_APPROACH = "termination_approach"
    TERMINATION_TOUCH = "termination_touch"
```

#### 1.2 Create Termination Detection Function

**File:** `src/dgas/calculations/patterns.py`

Add new function `detect_termination_events()`:

```python
@dataclass(frozen=True)
class TerminationConfig:
    """Configuration for termination detection."""
    approach_threshold_pct: float = 0.5  # Within 0.5% of projected level
    touch_threshold_pct: float = 0.1     # Within 0.1% = touch
    min_zone_strength: int = 2           # Minimum lines in zone
    lookback_bars: int = 5               # How far back to check lines
    require_momentum_fade: bool = True   # Require slowing momentum at approach


def detect_termination_events(
    intervals: Sequence[IntervalData],
    drummond_zones: Sequence[DrummondZone],
    pldot: Sequence[PLDotSeries] | None = None,
    config: TerminationConfig | None = None,
) -> List[PatternEvent]:
    """
    Detect when price approaches or touches projected Drummond line terminations.
    
    This is a core Drummond Geometry concept: projected trendlines identify
    levels where price "energy" is expected to terminate (reverse or consolidate).
    
    Args:
        intervals: OHLCV bars
        drummond_zones: Aggregated Drummond line zones
        pldot: Optional PLdot series for momentum confirmation
        config: Detection configuration
        
    Returns:
        List of termination pattern events
    """
    cfg = config or TerminationConfig()
    events: List[PatternEvent] = []
    
    # Build price and slope lookups
    close_map = {bar.timestamp: float(bar.close) for bar in intervals}
    high_map = {bar.timestamp: float(bar.high) for bar in intervals}
    low_map = {bar.timestamp: float(bar.low) for bar in intervals}
    slope_map = {p.timestamp: float(p.slope) for p in (pldot or [])}
    
    ordered_intervals = sorted(intervals, key=lambda b: b.timestamp)
    
    for i, bar in enumerate(ordered_intervals):
        close = float(bar.close)
        high = float(bar.high)
        low = float(bar.low)
        
        for zone in drummond_zones:
            if zone.strength < cfg.min_zone_strength:
                continue
                
            zone_level = float(zone.center_price)
            zone_upper = float(zone.upper_price)
            zone_lower = float(zone.lower_price)
            
            # Calculate distance as percentage
            distance_pct = abs(close - zone_level) / zone_level * 100 if zone_level != 0 else float('inf')
            
            # Check for touch (price penetrated zone)
            touched = (low <= zone_upper and high >= zone_lower)
            
            # Check for approach
            approaching = distance_pct <= cfg.approach_threshold_pct
            
            if not (touched or approaching):
                continue
                
            # Determine direction (approaching from above or below)
            direction = 1 if close > zone_level else -1
            
            # Optional: Check for momentum fade
            if cfg.require_momentum_fade and pldot:
                slope = slope_map.get(bar.timestamp, 0)
                # Momentum should be fading (slope decreasing in magnitude or reversing)
                if i > 0:
                    prev_bar = ordered_intervals[i-1]
                    prev_slope = slope_map.get(prev_bar.timestamp, 0)
                    momentum_fading = abs(slope) < abs(prev_slope) or (slope * prev_slope < 0)
                    if not momentum_fading:
                        continue
            
            # Create pattern event
            pattern_type = PatternType.TERMINATION_TOUCH if touched else PatternType.TERMINATION_APPROACH
            
            events.append(PatternEvent(
                pattern_type=pattern_type,
                direction=-direction,  # Reversal direction (opposite to approach)
                start_timestamp=bar.timestamp,
                end_timestamp=bar.timestamp,
                strength=zone.strength,
            ))
    
    return events
```

#### 1.3 Integrate into TimeframeBuilder

**File:** `src/dgas/calculations/timeframe_builder.py`

Update `build_timeframe_data()` to include termination detection:

```python
from .patterns import detect_termination_events

def build_timeframe_data(...) -> TimeframeData:
    # ... existing code ...
    
    # Add termination detection
    termination_events = detect_termination_events(
        intervals=intervals,
        drummond_zones=drummond_zones,
        pldot=pldot_series,
    )
    
    # Combine with other pattern events
    all_patterns = list(pattern_events) + termination_events
    
    return TimeframeData(
        # ... existing fields ...
        pattern_events=tuple(all_patterns),
    )
```

#### 1.4 Use in Signal Generation

**File:** `src/dgas/prediction/engine.py`

Update `_has_supporting_pattern()` to include termination patterns:

```python
def _has_supporting_pattern(self, analysis: MultiTimeframeAnalysis, direction: TrendDirection) -> bool:
    required_direction = 1 if direction == TrendDirection.UP else -1

    def matches(event: PatternEvent) -> bool:
        return (
            event.direction == required_direction
            and event.pattern_type in {
                PatternType.PLDOT_PUSH,
                PatternType.C_WAVE,
                PatternType.PLDOT_REFRESH,
                PatternType.TERMINATION_TOUCH,  # NEW
                PatternType.TERMINATION_APPROACH,  # NEW
            }
            and event.strength >= self.required_pattern_strength
        )
    # ... rest of method
```

#### 1.5 Acceptance Criteria

- [ ] `PatternType.TERMINATION_APPROACH` and `TERMINATION_TOUCH` added to enum
- [ ] `detect_termination_events()` function implemented and tested
- [ ] Termination events included in `TimeframeData.pattern_events`
- [ ] Signal generator considers termination patterns for entries
- [ ] Unit tests cover approach vs. touch detection
- [ ] Integration test validates end-to-end signal generation with termination

---

## Priority 2: Exhaust-Based Exit Signals

### Background

The Exhaust pattern (price extends far beyond envelope, then reverses) is detected but not used to generate exit signals. This is a critical risk management feature - exhausts warn of potential reversals.

### Current State

- `detect_exhaust()` correctly identifies exhaust patterns
- Exhaust patterns are stored in `TimeframeData.pattern_events`
- **Gap:** No logic generates EXIT signals when exhaust detected against position

### Implementation Plan

#### 2.1 Add Exit Signal Generation Method

**File:** `src/dgas/prediction/engine.py`

Add new method to `SignalGenerator`:

```python
def generate_exit_signals(
    self,
    symbol: str,
    htf_data: TimeframeData,
    trading_tf_data: TimeframeData,
    current_position_direction: Optional[int],  # 1 for long, -1 for short, None for no position
) -> List[GeneratedSignal]:
    """
    Generate exit signals based on exhaust patterns and adverse conditions.
    
    Exit signals are generated when:
    1. Exhaust pattern detected opposite to position direction
    2. HTF trend reverses against position
    3. Confluence zone breached in adverse direction
    
    Args:
        symbol: Market symbol
        htf_data: Higher timeframe data
        trading_tf_data: Trading timeframe data
        current_position_direction: Current position direction (1=long, -1=short)
        
    Returns:
        List of exit signals
    """
    if current_position_direction is None:
        return []
    
    exit_signals: List[GeneratedSignal] = []
    analysis = self.coordinator.analyze(htf_data, trading_tf_data)
    
    # Check for exhaust patterns against position
    for pattern in trading_tf_data.pattern_events:
        if pattern.pattern_type != PatternType.EXHAUST:
            continue
            
        # Exhaust direction is the reversal direction
        # If we're long and exhaust signals DOWN reversal, exit
        if current_position_direction == 1 and pattern.direction == -1:
            exit_signals.append(self._create_exit_signal(
                symbol=symbol,
                signal_type=SignalType.EXIT_LONG,
                analysis=analysis,
                reason="Exhaust pattern detected - bearish reversal warning",
                pattern=pattern,
            ))
        elif current_position_direction == -1 and pattern.direction == 1:
            exit_signals.append(self._create_exit_signal(
                symbol=symbol,
                signal_type=SignalType.EXIT_SHORT,
                analysis=analysis,
                reason="Exhaust pattern detected - bullish reversal warning",
                pattern=pattern,
            ))
    
    # Check for HTF trend reversal against position
    if current_position_direction == 1 and analysis.htf_trend == TrendDirection.DOWN:
        if float(analysis.htf_trend_strength) >= 0.6:
            exit_signals.append(self._create_exit_signal(
                symbol=symbol,
                signal_type=SignalType.EXIT_LONG,
                analysis=analysis,
                reason="HTF trend reversed to bearish",
            ))
    elif current_position_direction == -1 and analysis.htf_trend == TrendDirection.UP:
        if float(analysis.htf_trend_strength) >= 0.6:
            exit_signals.append(self._create_exit_signal(
                symbol=symbol,
                signal_type=SignalType.EXIT_SHORT,
                analysis=analysis,
                reason="HTF trend reversed to bullish",
            ))
    
    return exit_signals


def _create_exit_signal(
    self,
    symbol: str,
    signal_type: SignalType,
    analysis: MultiTimeframeAnalysis,
    reason: str,
    pattern: Optional[PatternEvent] = None,
) -> GeneratedSignal:
    """Create an exit signal with appropriate metadata."""
    current_pldot = analysis.pldot_overlay.ltf_pldot_value
    
    return GeneratedSignal(
        symbol=symbol,
        signal_timestamp=analysis.timestamp,
        signal_type=signal_type,
        entry_price=current_pldot,  # Exit at current level
        stop_loss=current_pldot,    # N/A for exits
        target_price=current_pldot, # N/A for exits
        confidence=0.8 if pattern else 0.6,
        signal_strength=float(analysis.signal_strength),
        timeframe_alignment=float(analysis.alignment.alignment_score),
        risk_reward_ratio=0.0,
        htf_trend=analysis.htf_trend,
        trading_tf_state=analysis.alignment.trading_tf_state.value,
        confluence_zones_count=len(analysis.confluence_zones),
        pattern_context={
            "exit_reason": reason,
            "triggering_pattern": pattern.pattern_type.value if pattern else None,
            "pattern_strength": pattern.strength if pattern else None,
        },
        htf_timeframe=analysis.htf_timeframe,
        trading_timeframe=analysis.trading_timeframe,
    )
```

#### 2.2 Integrate with Backtesting Engine

**File:** `src/dgas/backtesting/portfolio_engine.py`

Update `_check_exits()` to call exhaust-based exit logic:

```python
def _check_exits(self, timestep: PortfolioTimestep, current_prices: Dict[str, Decimal]) -> None:
    """Check and execute exits on existing positions."""
    for symbol, portfolio_position in list(self._position_manager.positions.items()):
        # ... existing stop/target checks ...
        
        # NEW: Check for pattern-based exits
        if symbol in self._indicator_cache:
            indicators = self._indicator_cache[symbol]
            htf_data = indicators.get('htf_data')
            trading_data = indicators.get('trading_data')
            
            if htf_data and trading_data:
                position_direction = 1 if portfolio_position.position.side == PositionSide.LONG else -1
                exit_signals = self._signal_generator.generate_exit_signals(
                    symbol=symbol,
                    htf_data=htf_data,
                    trading_tf_data=trading_data,
                    current_position_direction=position_direction,
                )
                
                if exit_signals:
                    # Execute the exit
                    exit_price = current_prices.get(symbol, portfolio_position.position.entry_price)
                    self._execute_exit(symbol, exit_price, timestep.timestamp, "pattern_exit")
```

#### 2.3 Acceptance Criteria

- [ ] `generate_exit_signals()` method added to `SignalGenerator`
- [ ] Exit signals generated for exhaust patterns against position
- [ ] Exit signals generated for HTF trend reversal against position
- [ ] Backtesting engine calls exit signal generation
- [ ] Exit signals properly logged and tracked
- [ ] Unit tests for each exit condition
- [ ] Backtest comparison: with vs. without exhaust exits (measure drawdown reduction)

---

## Priority 3: Congestion State Tracking Fix

### Background

The current state classifier may lose track of the "prior trend direction" during extended congestion phases. This can cause incorrect classification of congestion exits vs. reversals.

### Current State

- `MarketStateClassifier.classify()` tracks `last_trend_direction`
- Direction updated on TREND and REVERSAL states
- **Gap:** During long congestion, the original trend direction before congestion may be overwritten

### Implementation Plan

#### 3.1 Add Congestion Entry Tracking to StateSeries

**File:** `src/dgas/calculations/states.py`

Extend `StateSeries` dataclass:

```python
@dataclass(frozen=True)
class StateSeries:
    """Single point-in-time market state classification."""
    timestamp: datetime
    state: MarketState
    trend_direction: TrendDirection
    bars_in_state: int
    previous_state: MarketState | None
    pldot_slope_trend: str
    confidence: Decimal
    state_change_reason: str | None = None
    
    # NEW FIELDS
    trend_at_congestion_entrance: TrendDirection | None = None  # Preserved through congestion
    bars_in_congestion: int = 0  # Total bars since entering congestion
```

#### 3.2 Update Classifier Logic

**File:** `src/dgas/calculations/states.py`

Update `MarketStateClassifier.classify()`:

```python
def classify(self, intervals: Sequence[IntervalData], pldot_series: Sequence[PLDotSeries]) -> List[StateSeries]:
    # ... existing setup ...
    
    # NEW: Track trend at congestion entrance
    trend_at_congestion_entrance: TrendDirection | None = None
    bars_in_congestion = 0
    
    for i, series in enumerate(ordered_pldot):
        # ... existing position calculation ...
        
        state, direction, reason = self._apply_state_rules(
            recent_positions,
            prev_state,
            last_trend_direction,
            bars_in_state,
            pldot_slope_trend
        )
        
        # NEW: Track congestion entrance
        if state == MarketState.CONGESTION_ENTRANCE and prev_state == MarketState.TREND:
            trend_at_congestion_entrance = last_trend_direction
            bars_in_congestion = 1
        elif state in [MarketState.CONGESTION_ACTION, MarketState.CONGESTION_ENTRANCE]:
            bars_in_congestion += 1
        elif state in [MarketState.TREND, MarketState.REVERSAL, MarketState.CONGESTION_EXIT]:
            # Exiting congestion - reset tracking
            if state == MarketState.CONGESTION_EXIT:
                # Preserve for this bar, then reset
                pass
            else:
                trend_at_congestion_entrance = None
                bars_in_congestion = 0
        
        # ... existing tracking updates ...
        
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
        
        prev_state = state
    
    return results
```

#### 3.3 Update State Rules to Use Preserved Trend

**File:** `src/dgas/calculations/states.py`

Update `_apply_state_rules()` to accept and use `trend_at_congestion_entrance`:

```python
def _apply_state_rules(
    self,
    recent_positions: List[int],
    previous_state: MarketState | None,
    prior_trend_direction: TrendDirection | None,
    bars_in_state: int,
    pldot_slope_trend: str,
    trend_at_congestion_entrance: TrendDirection | None = None,  # NEW PARAMETER
) -> tuple[MarketState, TrendDirection, str]:
    """Apply Drummond 3-bar state detection rules."""
    
    # ... existing 3-bar checks ...
    
    if all_above:
        if previous_state == MarketState.TREND and prior_trend_direction == TrendDirection.UP:
            return (MarketState.TREND, TrendDirection.UP, "Trend continuation")
        elif previous_state in [MarketState.CONGESTION_ACTION, MarketState.CONGESTION_ENTRANCE]:
            # USE PRESERVED TREND instead of prior_trend_direction
            original_trend = trend_at_congestion_entrance or prior_trend_direction
            
            if original_trend == TrendDirection.UP:
                return (MarketState.CONGESTION_EXIT, TrendDirection.UP, "Congestion exit to uptrend")
            elif original_trend == TrendDirection.DOWN:
                return (MarketState.REVERSAL, TrendDirection.UP, "Reversal to uptrend")
            else:
                return (MarketState.TREND, TrendDirection.UP, "New uptrend from congestion")
        # ... rest of method with similar updates for all_below ...
```

#### 3.4 Acceptance Criteria

- [ ] `trend_at_congestion_entrance` field added to `StateSeries`
- [ ] `bars_in_congestion` field added for monitoring
- [ ] Classifier preserves trend through extended congestion
- [ ] Exit vs. reversal classification uses preserved trend
- [ ] Unit test: 10+ bar congestion followed by exit in original direction = CONGESTION_EXIT
- [ ] Unit test: 10+ bar congestion followed by exit opposite direction = REVERSAL
- [ ] Existing tests continue to pass

---

## Priority 4: Tiered Signal Confidence System

### Background

The current signal generator requires multiple strict criteria (alignment, patterns, zones) which may filter out valid setups. Drummond methodology suggests that strong confluence zones alone can be high-probability.

### Current State

- Single signal generation path with strict requirements
- All signals must meet same criteria
- **Gap:** No mechanism for lower-confidence signals that still have value

### Implementation Plan

#### 4.1 Define Signal Tiers

**File:** `src/dgas/prediction/engine.py`

Add signal tier enumeration and configuration:

```python
class SignalTier(Enum):
    """Signal confidence tiers."""
    TIER_1_HIGH = "tier_1_high"      # Full confluence: HTF + pattern + zone
    TIER_2_MEDIUM = "tier_2_medium"  # Partial: HTF + zone OR HTF + pattern
    TIER_3_LOW = "tier_3_low"        # Minimal: Strong zone only


@dataclass
class TieredSignalConfig:
    """Configuration for tiered signal generation."""
    # Tier 1 (High Confidence) - Current strict requirements
    tier_1_min_alignment: float = 0.6
    tier_1_min_signal_strength: float = 0.5
    tier_1_require_pattern: bool = True
    tier_1_min_zone_weight: float = 2.5
    
    # Tier 2 (Medium Confidence) - Relaxed requirements
    tier_2_min_alignment: float = 0.5
    tier_2_min_signal_strength: float = 0.4
    tier_2_require_pattern: bool = False  # Zone can substitute for pattern
    tier_2_min_zone_weight: float = 3.0   # Higher zone weight required
    
    # Tier 3 (Low Confidence) - Zone-only signals
    tier_3_min_zone_weight: float = 4.0   # Very strong zone required
    tier_3_min_htf_alignment: float = 0.4  # HTF must not conflict
    
    # Position sizing multipliers by tier
    tier_1_position_multiplier: float = 1.0
    tier_2_position_multiplier: float = 0.5
    tier_3_position_multiplier: float = 0.25
```

#### 4.2 Update Signal Generation

**File:** `src/dgas/prediction/engine.py`

Update `SignalGenerator` to support tiered generation:

```python
class SignalGenerator:
    def __init__(
        self,
        coordinator: MultiTimeframeCoordinator,
        tiered_config: TieredSignalConfig | None = None,
        # ... existing parameters ...
    ):
        self.tiered_config = tiered_config or TieredSignalConfig()
        # ... existing init ...
    
    def generate_signals(
        self,
        symbol: str,
        htf_data: TimeframeData,
        trading_tf_data: TimeframeData,
        ltf_data: Optional[TimeframeData] = None,
        include_lower_tiers: bool = True,  # NEW PARAMETER
    ) -> List[GeneratedSignal]:
        """Generate trading signals with optional tiered confidence."""
        
        analysis = self.coordinator.analyze(htf_data, trading_tf_data, ltf_data)
        
        # Try Tier 1 first (existing strict logic)
        tier_1_signals = self._generate_tier_1_signals(symbol, analysis, trading_tf_data)
        if tier_1_signals:
            return tier_1_signals
        
        if not include_lower_tiers:
            return []
        
        # Try Tier 2
        tier_2_signals = self._generate_tier_2_signals(symbol, analysis, trading_tf_data)
        if tier_2_signals:
            return tier_2_signals
        
        # Try Tier 3
        tier_3_signals = self._generate_tier_3_signals(symbol, analysis, trading_tf_data)
        return tier_3_signals
    
    def _generate_tier_1_signals(self, symbol: str, analysis: MultiTimeframeAnalysis, trading_tf_data: TimeframeData) -> List[GeneratedSignal]:
        """Generate Tier 1 (high confidence) signals - existing strict logic."""
        # ... existing generate_signals logic moved here ...
        pass
    
    def _generate_tier_2_signals(self, symbol: str, analysis: MultiTimeframeAnalysis, trading_tf_data: TimeframeData) -> List[GeneratedSignal]:
        """Generate Tier 2 (medium confidence) signals."""
        cfg = self.tiered_config
        
        # Check relaxed alignment
        if float(analysis.alignment.alignment_score) < cfg.tier_2_min_alignment:
            return []
        
        if float(analysis.signal_strength) < cfg.tier_2_min_signal_strength:
            return []
        
        if not analysis.alignment.trade_permitted:
            return []
        
        # Check for strong zone (can substitute for pattern)
        strong_zone = None
        for zone in analysis.confluence_zones:
            if float(zone.weighted_strength) >= cfg.tier_2_min_zone_weight:
                strong_zone = zone
                break
        
        if strong_zone is None:
            return []
        
        direction = self._determine_direction(analysis)
        if direction is None:
            return []
        
        # ... create signal with tier_2 metadata ...
        signal = self._create_tiered_signal(
            symbol=symbol,
            analysis=analysis,
            trading_tf_data=trading_tf_data,
            zone=strong_zone,
            direction=direction,
            tier=SignalTier.TIER_2_MEDIUM,
        )
        
        return [signal] if signal else []
    
    def _generate_tier_3_signals(self, symbol: str, analysis: MultiTimeframeAnalysis, trading_tf_data: TimeframeData) -> List[GeneratedSignal]:
        """Generate Tier 3 (low confidence) signals - zone only."""
        cfg = self.tiered_config
        
        # HTF must not conflict
        if float(analysis.alignment.alignment_score) < cfg.tier_3_min_htf_alignment:
            return []
        
        # Require very strong zone
        very_strong_zone = None
        for zone in analysis.confluence_zones:
            if float(zone.weighted_strength) >= cfg.tier_3_min_zone_weight:
                very_strong_zone = zone
                break
        
        if very_strong_zone is None:
            return []
        
        # Determine direction from zone type
        direction = TrendDirection.UP if very_strong_zone.zone_type == "support" else TrendDirection.DOWN
        
        # ... create signal with tier_3 metadata ...
        signal = self._create_tiered_signal(
            symbol=symbol,
            analysis=analysis,
            trading_tf_data=trading_tf_data,
            zone=very_strong_zone,
            direction=direction,
            tier=SignalTier.TIER_3_LOW,
        )
        
        return [signal] if signal else []
```

#### 4.3 Update GeneratedSignal Dataclass

**File:** `src/dgas/prediction/engine.py`

Add tier information to signal:

```python
@dataclass(frozen=True)
class GeneratedSignal:
    # ... existing fields ...
    
    # NEW FIELDS
    signal_tier: SignalTier = SignalTier.TIER_1_HIGH
    position_size_multiplier: float = 1.0
```

#### 4.4 Acceptance Criteria

- [ ] `SignalTier` enum added
- [ ] `TieredSignalConfig` dataclass added
- [ ] `generate_signals()` supports tiered generation
- [ ] Tier 2 signals generated when Tier 1 criteria not met but strong zone exists
- [ ] Tier 3 signals generated for very strong zones without pattern
- [ ] Signal tier included in `GeneratedSignal`
- [ ] Position size multiplier reflects tier
- [ ] Backtest comparison: Tier 1 only vs. All tiers (measure signal count vs. win rate)

---

## Priority 5: Envelope Calculation Validation

### Background

The current envelope implementation uses PLdot standard deviation, which is reasonable but may not match all Drummond implementations. Some use the 3-bar high-low range.

### Current State

- `EnvelopeCalculator` uses `pldot_range` method (PLdot std dev)
- Alternative methods (`atr`, `percentage`) exist but are marked as legacy
- **Gap:** No empirical validation of which method best matches Drummond methodology

### Implementation Plan

#### 5.1 Add Range-Based Envelope Method

**File:** `src/dgas/calculations/envelopes.py`

Add new envelope method:

```python
class EnvelopeCalculator:
    def __init__(self, method: str = "pldot_range", ...):
        if method not in {"atr", "percentage", "pldot_range", "hlc_range"}:  # ADD NEW METHOD
            raise ValueError("method must be 'atr', 'percentage', 'pldot_range', or 'hlc_range'")
        # ...
    
    def from_intervals(self, intervals: Sequence[IntervalData], pldot: Sequence[PLDotSeries]) -> List[EnvelopeSeries]:
        # ... existing setup ...
        
        if self.method == "pldot_range":
            # Existing: 3-period standard deviation of PLdot values
            pldot_volatility = df["value"].rolling(window=self.period, min_periods=self.period).std()
            offset = pldot_volatility * self.multiplier
            
        elif self.method == "hlc_range":
            # NEW: 3-period high-low range method
            # This measures the actual price range over the PLdot period
            high_low_range = df["high"] - df["low"]
            avg_range = high_low_range.rolling(window=self.period, min_periods=self.period).mean()
            offset = avg_range * self.multiplier
            
        elif self.method == "atr":
            # ... existing ATR method ...
        # ...
```

#### 5.2 Create Validation Script

**File:** `scripts/validate_envelope_methods.py`

Create script to compare envelope methods:

```python
"""
Validate envelope calculation methods against historical data.

This script compares different envelope methods to determine which best
captures the Drummond Geometry concept of "expected energy range."

Metrics:
1. Containment rate: % of closes within envelope
2. Extreme touch rate: % of bars touching envelope extremes
3. Reversal accuracy: % of envelope touches that lead to reversals
"""

import pandas as pd
from decimal import Decimal
from typing import Dict, List

from dgas.calculations.envelopes import EnvelopeCalculator
from dgas.calculations.pldot import PLDotCalculator
from dgas.data.repository import fetch_market_data
from dgas.db import get_connection


def validate_envelope_methods(
    symbol: str,
    interval: str,
    methods: List[str] = ["pldot_range", "hlc_range", "atr"],
    lookback_days: int = 90,
) -> Dict[str, Dict[str, float]]:
    """Compare envelope methods and return metrics."""
    
    results = {}
    
    with get_connection() as conn:
        bars = fetch_market_data(conn, symbol, interval, limit=lookback_days * 24)
    
    pldot_calc = PLDotCalculator()
    pldot_series = pldot_calc.from_intervals(bars)
    
    for method in methods:
        env_calc = EnvelopeCalculator(method=method, period=3, multiplier=1.5)
        envelopes = env_calc.from_intervals(bars, pldot_series)
        
        # Calculate metrics
        containment_rate = calculate_containment_rate(bars, envelopes)
        touch_rate = calculate_extreme_touch_rate(bars, envelopes)
        reversal_accuracy = calculate_reversal_accuracy(bars, envelopes)
        
        results[method] = {
            "containment_rate": containment_rate,
            "extreme_touch_rate": touch_rate,
            "reversal_accuracy": reversal_accuracy,
        }
    
    return results


def calculate_containment_rate(bars, envelopes) -> float:
    """Calculate % of closes within envelope."""
    # Implementation
    pass


def calculate_extreme_touch_rate(bars, envelopes) -> float:
    """Calculate % of bars touching envelope extremes."""
    # Implementation
    pass


def calculate_reversal_accuracy(bars, envelopes) -> float:
    """Calculate % of envelope touches that lead to reversals."""
    # Implementation
    pass


if __name__ == "__main__":
    # Run validation on multiple symbols
    symbols = ["AAPL.US", "MSFT.US", "SPY.US", "QQQ.US"]
    
    for symbol in symbols:
        print(f"\n=== {symbol} ===")
        results = validate_envelope_methods(symbol, "30m")
        for method, metrics in results.items():
            print(f"{method}: {metrics}")
```

#### 5.3 Acceptance Criteria

- [ ] `hlc_range` envelope method added
- [ ] Validation script created and runnable
- [ ] Metrics calculated for multiple symbols
- [ ] Results documented with recommendation
- [ ] Default method updated if validation shows better alternative

---

## Implementation Timeline

| Priority | Task | Estimated Effort | Dependencies |
|----------|------|------------------|--------------|
| 1 | Drummond Line Termination Detection | 3-4 days | None |
| 2 | Exhaust-Based Exit Signals | 2-3 days | None |
| 3 | Congestion State Tracking Fix | 2 days | None |
| 4 | Tiered Signal Confidence | 3-4 days | Priority 1 (for pattern types) |
| 5 | Envelope Validation | 2 days | None |

**Total Estimated Effort:** 12-15 days

**Recommended Order:**
1. Priority 3 (State Tracking) - Foundation fix
2. Priority 1 (Termination Detection) - High value new feature
3. Priority 2 (Exit Signals) - Risk management
4. Priority 4 (Tiered Signals) - Signal volume
5. Priority 5 (Envelope Validation) - Optimization

---

## Testing Strategy

### Unit Tests

Each priority item requires unit tests covering:
- Happy path functionality
- Edge cases (empty data, single bar, etc.)
- Error conditions
- Boundary conditions (threshold values)

### Integration Tests

- End-to-end signal generation with new features
- Backtest runs comparing before/after metrics
- Multi-symbol validation

### Regression Tests

- All existing tests must continue to pass
- Performance benchmarks should not degrade significantly

### Validation Tests

- Compare signal accuracy before/after changes
- Measure drawdown impact of exit signals
- Track signal count changes with tiered system

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Breaking existing functionality | Medium | High | Comprehensive regression tests |
| Performance degradation | Low | Medium | Profiling before/after |
| Over-generation of signals | Medium | Medium | Careful threshold calibration |
| Increased complexity | High | Low | Clear documentation, modular design |
| Backtest overfitting | Medium | High | Out-of-sample validation |

---

## Appendix: File Change Summary

| File | Changes |
|------|---------|
| `src/dgas/calculations/patterns.py` | Add `TERMINATION_*` patterns, `detect_termination_events()` |
| `src/dgas/calculations/states.py` | Add `trend_at_congestion_entrance`, update classifier |
| `src/dgas/calculations/envelopes.py` | Add `hlc_range` method |
| `src/dgas/calculations/timeframe_builder.py` | Include termination events |
| `src/dgas/prediction/engine.py` | Add exit signals, tiered generation |
| `src/dgas/backtesting/portfolio_engine.py` | Call exit signal generation |
| `scripts/validate_envelope_methods.py` | New validation script |
| `tests/calculations/test_patterns.py` | New termination tests |
| `tests/calculations/test_states.py` | New congestion tracking tests |
| `tests/prediction/test_engine.py` | New exit and tier tests |

---

*End of Implementation Plan*