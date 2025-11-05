# Drummond Geometry Python Data Models

## Executive Summary

This document defines comprehensive Python data models and class specifications for implementing Drummond Geometry indicators and analysis tools. The models are designed to capture the sophisticated technical analysis methodology developed by Charles Drummond over five decades, focusing on the PLdot (Point and Line dot), envelope systems, trend line calculations, market state classification, and multi-timeframe coordination.

The data models incorporate the core mathematical foundations, trading patterns, signal generation, and validation requirements necessary for building a robust Drummond Geometry implementation. The design emphasizes type safety, data integrity, extensibility, and alignment with the methodology's forward-looking, predictive characteristics.

---

## 1. Core Data Structures

### 1.1 OHLCV Data Structure

```python
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, Union, Dict, Any
from enum import Enum

@dataclass(frozen=True)
class OHLCV:
    """
    Core OHLCV (Open, High, Low, Close, Volume) data structure.
    
    Represents a single bar/candle of price action data with additional metadata.
    Uses Decimal for precise price calculations to avoid floating-point errors.
    """
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Optional[Decimal] = None
    symbol: Optional[str] = None
    timeframe: Optional[str] = None
    
    def __post_init__(self):
        """Validate OHLCV data integrity after initialization."""
        if self.high < self.low:
            raise ValueError(f"High ({self.high}) cannot be less than Low ({self.low})")
        if self.open < self.low or self.open > self.high:
            raise ValueError(f"Open ({self.open}) outside High-Low range")
        if self.close < self.low or self.close > self.high:
            raise ValueError(f"Close ({self.close}) outside High-Low range")
        if self.timestamp.tzinfo != timezone.utc:
            raise ValueError("All timestamps must be in UTC timezone")
    
    @property
    def price_range(self) -> Decimal:
        """Return the total price range (high - low) of the bar."""
        return self.high - self.low
    
    @property
    def body_high(self) -> Decimal:
        """Return the higher of open and close."""
        return max(self.open, self.close)
    
    @property
    def body_low(self) -> Decimal:
        """Return the lower of open and close."""
        return min(self.open, self.close)
    
    @property
    def body_size(self) -> Decimal:
        """Return the size of the price body (abs(close - open))."""
        return abs(self.close - self.open)
    
    @property
    def upper_shadow(self) -> Decimal:
        """Return the size of the upper shadow (high - body_high)."""
        return self.high - self.body_high
    
    @property
    def lower_shadow(self) -> Decimal:
        """Return the size of the lower shadow (body_low - low)."""
        return self.body_low - self.low
    
    @classmethod
    def from_float_values(cls, timestamp: datetime, open: float, high: float, 
                         low: float, close: float, volume: Optional[float] = None,
                         **kwargs) -> 'OHLCV':
        """Factory method to create OHLCV from float values."""
        return cls(
            timestamp=timestamp,
            open=Decimal(str(open)),
            high=Decimal(str(high)),
            low=Decimal(str(low)),
            close=Decimal(str(close)),
            volume=Decimal(str(volume)) if volume is not None else None,
            **kwargs
        )
```

### 1.2 DataPoint Class

```python
from dataclasses import dataclass
from typing import Generic, TypeVar, List, Optional

T = TypeVar('T')

@dataclass
class DataPoint(Generic[T]):
    """
    Generic data point wrapper for time series data.
    
    Wraps any data value with timestamp and metadata, providing
    a foundation for time series analysis with Drummond Geometry.
    """
    timestamp: datetime
    value: T
    source: Optional['OHLCV'] = None
    metadata: Optional[Dict[str, Any]] = None
    is_projected: bool = False  # Indicates if this is a forward projection
    
    def __post_init__(self):
        """Validate data point after initialization."""
        if self.timestamp.tzinfo != timezone.utc:
            raise ValueError("Data point timestamp must be in UTC timezone")
    
    @property
    def age_seconds(self) -> float:
        """Return the age of this data point in seconds."""
        return (datetime.now(timezone.utc) - self.timestamp).total_seconds()
    
    def to_tuple(self) -> tuple:
        """Convert to timestamp-value tuple for compatibility with time series libraries."""
        return (self.timestamp, self.value)
```

### 1.3 CalculatedIndicator Interface

```python
from abc import ABC, abstractmethod
from typing import Protocol, List
from decimal import Decimal

class CalculatedIndicator(Protocol):
    """
    Protocol for all calculated indicators in Drummond Geometry.
    
    Ensures consistent interface across all indicator implementations.
    """
    
    @property
    @abstractmethod
    def latest_value(self) -> Optional[DataPoint]:
        """Return the most recent calculated value."""
        ...
    
    @property
    @abstractmethod
    def all_values(self) -> List[DataPoint]:
        """Return all calculated values in chronological order."""
        ...
    
    @abstractmethod
    def calculate(self, ohlcv_data: List[OHLCV]) -> List[DataPoint]:
        """
        Calculate indicator values from OHLCV data.
        
        Args:
            ohlcv_data: List of OHLCV data points in chronological order
            
        Returns:
            List of calculated DataPoint values
        """
        ...
```

---

## 2. Core Drummond Geometry Indicators

### 2.1 PLDot Class

```python
from dataclasses import dataclass
from typing import List, Optional
from enum import Enum

class MarketState(Enum):
    """Enumeration of the five types of trading in Drummond Geometry."""
    TREND_BULLISH = "trend_bullish"
    TREND_BEARISH = "trend_bearish"
    CONGESTION_ENTRANCE = "congestion_entrance"
    CONGESTION_ACTION = "congestion_action"
    CONGESTION_EXIT = "congestion_exit"
    TREND_REVERSAL = "trend_reversal"

@dataclass
class PLDotMetadata:
    """Metadata associated with a PLdot calculation."""
    bar_count_used: int = 3
    calculation_method: str = "average_of_averages"
    displacement: int = 1
    market_state: Optional[MarketState] = None
    confidence: Optional[Decimal] = None  # 0.0 to 1.0
    energy_level: Optional[Decimal] = None  # -1.0 to 1.0
    
@dataclass
class PLDot(DataPoint[Decimal]):
    """
    The core PLdot (Point and Line dot) indicator.
    
    Formula: [Avg(H(1),L(1),C(1)) + Avg(H(2),L(2),C(2)) + Avg(H(3),L(3),C(3))] / 3
    
    Represents market consensus as a short-term moving average based on
    three bars of data. Projects forward one bar to provide predictive levels.
    """
    metadata: PLDotMetadata = None
    
    @classmethod
    def calculate_from_ohlcv(cls, ohlcv_data: List[OHLCV], 
                           displacement: int = 1) -> List['PLDot']:
        """
        Calculate PLdot values from OHLCV data.
        
        Args:
            ohlcv_data: List of OHLCV data points in chronological order
            displacement: Number of bars forward to project (typically 1)
            
        Returns:
            List of PLdot values with projections
        """
        if len(ohlcv_data) < 3:
            raise ValueError("At least 3 OHLCV points required for PLdot calculation")
        
        pl_dots = []
        
        for i in range(2, len(ohlcv_data)):
            # Calculate average for each of the last 3 bars
            bar_averages = []
            for j in range(max(0, i-2), i+1):
                bar = ohlcv_data[j]
                avg = (bar.high + bar.low + bar.close) / 3
                bar_averages.append(avg)
            
            # Average the three bar averages
            pldot_value = sum(bar_averages) / len(bar_averages)
            
            # Project to future bar
            future_timestamp = ohlcv_data[i].timestamp + (
                ohlcv_data[i].timestamp - ohlcv_data[max(0, i-1)].timestamp
            )
            
            metadata = PLDotMetadata(displacement=displacement)
            
            pldot = PLDot(
                timestamp=future_timestamp,
                value=pldot_value,
                is_projected=True,
                metadata=metadata
            )
            pl_dots.append(pldot)
        
        return pl_dots
    
    def is_trending_up(self, previous_pldots: List['PLDot']) -> bool:
        """
        Determine if market is trending upward based on PLdot progression.
        
        Requires at least 3 consecutive rising PLdot values for trend confirmation.
        """
        if len(previous_pldots) < 2:
            return False
        
        recent_values = [p.value for p in recent_pldots[-3:]]
        return len(recent_values) >= 3 and all(
            recent_values[i] < recent_values[i+1] 
            for i in range(len(recent_values)-1)
        )
    
    def is_trending_down(self, previous_pldots: List['PLDot']) -> bool:
        """Determine if market is trending downward."""
        if len(previous_pldots) < 2:
            return False
        
        recent_values = [p.value for p in previous_pldots[-3:]]
        return len(recent_values) >= 3 and all(
            recent_values[i] > recent_values[i+1] 
            for i in range(len(recent_values)-1)
        )
    
    def is_in_congestion(self, tolerance: Decimal = Decimal('0.001')) -> bool:
        """Determine if market is in congestion (horizontal PLdot movement)."""
        # Implementation would require historical context
        # This is a placeholder for the congestion logic
        return False
```

### 2.2 EnvelopeBands Class

```python
from dataclasses import dataclass
from decimal import Decimal
from typing import List, Optional, Union

class EnvelopeMethod(Enum):
    """Methods for calculating envelope boundaries."""
    ATR_BASED = "atr_based"
    PERCENTAGE_BASED = "percentage_based"
    STANDARD_DEVIATION = "standard_deviation"
    DRUMMOND_CUSTOM = "drummond_custom"

@dataclass
class EnvelopeBands:
    """
    Trading envelope bands around the PLdot.
    
    Provides dynamic support and resistance levels based on recent volatility
    and PLdot calculations. Forms the foundation for C-wave identification
    and breakout analysis.
    """
    timestamp: datetime
    top: Decimal
    bottom: Decimal
    center: Decimal  # Usually the PLdot value
    method: EnvelopeMethod
    atr_value: Optional[Decimal] = None
    percentage: Optional[Decimal] = None
    standard_deviation: Optional[Decimal] = None
    
    @classmethod
    def calculate_atr_based(cls, pldot: PLDot, ohlcv_data: List[OHLCV], 
                          atr_multiplier: Decimal = Decimal('2.0'),
                          atr_period: int = 14) -> 'EnvelopeBands':
        """
        Calculate envelope bands using Average True Range (ATR) method.
        
        Args:
            pldot: The PLdot value to center the envelope on
            ohlcv_data: Historical OHLCV data for ATR calculation
            atr_multiplier: Multiplier for ATR (typically 2.0)
            atr_period: Period for ATR calculation
            
        Returns:
            EnvelopeBands object with calculated top and bottom
        """
        if len(ohlcv_data) < atr_period:
            raise ValueError(f"Need at least {atr_period} bars for ATR calculation")
        
        # Calculate ATR
        true_ranges = []
        for i in range(1, min(len(ohlcv_data), atr_period + 1)):
            current = ohlcv_data[-i]
            previous = ohlcv_data[-i-1]
            
            tr1 = current.high - current.low
            tr2 = abs(current.high - previous.close)
            tr3 = abs(current.low - previous.close)
            
            true_ranges.append(max(tr1, tr2, tr3))
        
        atr = sum(true_ranges) / len(true_ranges)
        envelope_distance = atr * atr_multiplier
        
        return cls(
            timestamp=pldot.timestamp,
            top=pldot.value + envelope_distance,
            bottom=pldot.value - envelope_distance,
            center=pldot.value,
            method=EnvelopeMethod.ATR_BASED,
            atr_value=atr
        )
    
    @classmethod
    def calculate_percentage_based(cls, pldot: PLDot, 
                                 percentage: Decimal = Decimal('0.02')) -> 'EnvelopeBands':
        """
        Calculate envelope bands using fixed percentage method.
        
        Args:
            pldot: The PLdot value to center the envelope on
            percentage: Percentage distance from center (e.g., 0.02 for 2%)
            
        Returns:
            EnvelopeBands object with calculated top and bottom
        """
        distance = pldot.value * percentage
        
        return cls(
            timestamp=pldot.timestamp,
            top=pldot.value + distance,
            bottom=pldot.value - distance,
            center=pldot.value,
            method=EnvelopeMethod.PERCENTAGE_BASED,
            percentage=percentage
        )
    
    @property
    def width(self) -> Decimal:
        """Return the total width of the envelope."""
        return self.top - self.bottom
    
    @property
    def is_price_above_top(self, price: Decimal) -> bool:
        """Check if price is above the envelope top."""
        return price > self.top
    
    @property
    def is_price_below_bottom(self, price: Decimal) -> bool:
        """Check if price is below the envelope bottom."""
        return price < self.bottom
    
    @property
    def is_price_inside(self, price: Decimal) -> bool:
        """Check if price is inside the envelope."""
        return self.bottom <= price <= self.top
    
    def distance_to_top(self, price: Decimal) -> Decimal:
        """Calculate distance from price to envelope top."""
        return self.top - price
    
    def distance_to_bottom(self, price: Decimal) -> Decimal:
        """Calculate distance from price to envelope bottom."""
        return price - self.bottom
```

### 2.3 DrummondLines Class

```python
from dataclasses import dataclass
from decimal import Decimal
from typing import List, Optional, Dict
from enum import Enum

class LineType(Enum):
    """Types of Drummond Lines based on Charles Drummond's notation."""
    FIVE_ONE_UP = "5_1_up"
    FIVE_ONE_DOWN = "5_1_down"
    FIVE_TWO_UP = "5_2_up"
    FIVE_TWO_DOWN = "5_2_down"
    FIVE_THREE_UP = "5_3_up"
    FIVE_THREE_DOWN = "5_3_down"
    FIVE_NINE_UP = "5_9_up"
    FIVE_NINE_DOWN = "5_9_down"
    SIX_ONE_UP = "6_1_up"
    SIX_ONE_DOWN = "6_1_down"
    SIX_FIVE_UP = "6_5_up"
    SIX_FIVE_DOWN = "6_5_down"
    SIX_SIX_UP = "6_6_up"
    SIX_SIX_DOWN = "6_6_down"
    SIX_SEVEN_UP = "6_7_up"
    SIX_SEVEN_DOWN = "6_7_down"

@dataclass
class DrummondLine:
    """
    A two-bar trend line projecting support or resistance into the future.
    
    Represents areas of energy termination where markets are likely
    to stop their movement according to Drummond Geometry principles.
    """
    line_type: LineType
    start_timestamp: datetime
    end_timestamp: Optional[datetime] = None  # For projection end
    start_price: Decimal = Decimal('0')
    projected_price: Optional[Decimal] = None
    angle: Optional[Decimal] = None  # Slope of the line
    strength: Optional[Decimal] = None  # 0.0 to 1.0
    is_active: bool = True
    
    def __post_init__(self):
        """Validate Drummond Line data."""
        if self.start_price <= 0:
            raise ValueError("Start price must be positive")
        if self.start_timestamp.tzinfo != timezone.utc:
            raise ValueError("Start timestamp must be in UTC")
    
    @classmethod
    def calculate_five_nine_up(cls, bar1: OHLCV, bar2: OHLCV) -> 'DrummondLine':
        """
        Calculate a 5-9 up line connecting specific price points.
        
        This is one of the most important termination lines in Drummond Geometry.
        """
        # 5-9 up typically connects the high of bar1 to the low of bar2
        start_price = bar1.high
        start_timestamp = bar1.timestamp
        
        # Calculate projected price for next bar
        time_diff = bar2.timestamp - bar1.timestamp
        price_diff = bar2.low - bar1.high
        angle = price_diff / Decimal(str(time_diff.total_seconds()))
        projected_price = bar2.low + angle * Decimal(str(time_diff.total_seconds()))
        
        return cls(
            line_type=LineType.FIVE_NINE_UP,
            start_timestamp=start_timestamp,
            start_price=start_price,
            projected_price=projected_price,
            angle=angle,
            strength=Decimal('0.8')  # 5-9 lines are generally strong
        )
    
    @classmethod
    def calculate_five_nine_down(cls, bar1: OHLCV, bar2: OHLCV) -> 'DrummondLine':
        """Calculate a 5-9 down line."""
        # 5-9 down typically connects the low of bar1 to the high of bar2
        start_price = bar1.low
        start_timestamp = bar1.timestamp
        
        time_diff = bar2.timestamp - bar1.timestamp
        price_diff = bar2.high - bar1.low
        angle = price_diff / Decimal(str(time_diff.total_seconds()))
        projected_price = bar2.high + angle * Decimal(str(time_diff.total_seconds()))
        
        return cls(
            line_type=LineType.FIVE_NINE_DOWN,
            start_timestamp=start_timestamp,
            start_price=start_price,
            projected_price=projected_price,
            angle=angle,
            strength=Decimal('0.8')
        )

@dataclass
class SupportResistanceZone:
    """
    A zone of support or resistance formed by converging Drummond Lines.
    
    Represents areas where price is likely to react due to multiple
    geometric factors aligning.
    """
    zone_type: str  # "support" or "resistance"
    top_price: Decimal
    bottom_price: Decimal
    center_price: Decimal
    start_timestamp: datetime
    end_timestamp: Optional[datetime] = None
    strength: Decimal = Decimal('0.0')  # 0.0 to 1.0
    contributing_lines: List[DrummondLine] = None
    timeframe: Optional[str] = None
    
    def __post_init__(self):
        """Validate zone data."""
        if self.bottom_price > self.top_price:
            raise ValueError("Bottom price cannot be greater than top price")
        if self.strength < 0 or self.strength > 1:
            raise ValueError("Strength must be between 0.0 and 1.0")
        if self.contributing_lines is None:
            self.contributing_lines = []
    
    @property
    def width(self) -> Decimal:
        """Return the width of the zone."""
        return self.top_price - self.bottom_price
    
    @property
    def is_price_in_zone(self, price: Decimal) -> bool:
        """Check if a price is within this zone."""
        return self.bottom_price <= price <= self.top_price
    
    def strength_factor(self) -> Decimal:
        """
        Calculate strength factor based on contributing lines.
        
        More converging lines = stronger zone.
        """
        if not self.contributing_lines:
            return Decimal('0.1')  # Minimum strength
        
        avg_strength = sum(line.strength for line in self.contributing_lines) / len(self.contributing_lines)
        convergence_bonus = Decimal(str(min(len(self.contributing_lines) * 0.1, 0.5)))
        
        return min(avg_strength + convergence_bonus, Decimal('1.0'))

@dataclass
class DrummondLines:
    """
    Container for Drummond Lines calculations and support/resistance zones.
    
    Manages multiple lines and their interactions to identify key levels
    for trading decisions.
    """
    lines: List[DrummondLine] = None
    support_zones: List[SupportResistanceZone] = None
    resistance_zones: List[SupportResistanceZone] = None
    timeframe: Optional[str] = None
    
    def __post_init__(self):
        """Initialize empty lists if None."""
        if self.lines is None:
            self.lines = []
        if self.support_zones is None:
            self.support_zones = []
        if self.resistance_zones is None:
            self.resistance_zones = []
    
    def add_line(self, line: DrummondLine) -> None:
        """Add a Drummond Line to the collection."""
        self.lines.append(line)
    
    def calculate_zones(self, price_cluster_tolerance: Decimal = Decimal('0.002')) -> None:
        """
        Calculate support and resistance zones from converging lines.
        
        Args:
            price_cluster_tolerance: Price difference tolerance for considering
                                   lines to be in the same zone
        """
        # Group lines by proximity
        line_clusters = self._cluster_lines_by_price(price_cluster_tolerance)
        
        for cluster in line_clusters:
            if len(cluster) >= 2:  # Need at least 2 lines for a zone
                zone = self._create_zone_from_cluster(cluster)
                if zone:
                    if zone.zone_type == "support":
                        self.support_zones.append(zone)
                    else:
                        self.resistance_zones.append(zone)
    
    def _cluster_lines_by_price(self, tolerance: Decimal) -> List[List[DrummondLine]]:
        """Cluster lines by price proximity."""
        clusters = []
        used_lines = set()
        
        for i, line in enumerate(self.lines):
            if i in used_lines:
                continue
            
            cluster = [line]
            used_lines.add(i)
            
            for j, other_line in enumerate(self.lines[i+1:], i+1):
                if j in used_lines:
                    continue
                
                if other_line.projected_price and line.projected_price:
                    price_diff = abs(other_line.projected_price - line.projected_price)
                    if price_diff <= tolerance * line.projected_price:
                        cluster.append(other_line)
                        used_lines.add(j)
            
            clusters.append(cluster)
        
        return clusters
    
    def _create_zone_from_cluster(self, line_cluster: List[DrummondLine]) -> Optional[SupportResistanceZone]:
        """Create a support/resistance zone from a cluster of lines."""
        if not line_cluster:
            return None
        
        # Determine if cluster represents support or resistance
        avg_price = sum(line.projected_price for line in line_cluster if line.projected_price) / len(line_cluster)
        
        # This is simplified logic - real implementation would be more sophisticated
        zone_type = "resistance" if avg_price > 0 else "support"
        
        # Calculate zone boundaries
        prices = [line.projected_price for line in line_cluster if line.projected_price]
        top_price = max(prices)
        bottom_price = min(prices)
        center_price = (top_price + bottom_price) / 2
        
        return SupportResistanceZone(
            zone_type=zone_type,
            top_price=top_price,
            bottom_price=bottom_price,
            center_price=center_price,
            start_timestamp=min(line.start_timestamp for line in line_cluster),
            strength=self._calculate_cluster_strength(line_cluster),
            contributing_lines=line_cluster,
            timeframe=self.timeframe
        )
    
    def _calculate_cluster_strength(self, cluster: List[DrummondLine]) -> Decimal:
        """Calculate the strength of a cluster of lines."""
        if not cluster:
            return Decimal('0.0')
        
        # Base strength on number of lines and their individual strengths
        line_count_factor = min(Decimal(str(len(cluster) * 0.2)), Decimal('0.6'))
        avg_line_strength = sum(line.strength or Decimal('0.5') for line in cluster) / len(cluster)
        
        return min(line_count_factor + avg_line_strength, Decimal('1.0'))
```

---

## 3. Market State and Pattern Recognition

### 3.1 MarketStateClassification Class

```python
from dataclasses import dataclass
from typing import List, Optional
from decimal import Decimal

@dataclass
class MarketStateClassification:
    """
    Classification of market state based on Drummond Geometry rules.
    
    Identifies the current type of trading and provides confidence levels
    for state transitions.
    """
    current_state: MarketState
    confidence: Decimal  # 0.0 to 1.0
    consecutive_closes: int = 0
    consecutive_side: Optional[str] = None  # "above" or "below" PLdot
    state_duration_bars: int = 0
    pldot_slope: Optional[Decimal] = None
    transition_probability: Optional[Decimal] = None  # Probability of next state
    
    @classmethod
    def classify_from_data(cls, ohlcv_data: List[OHLCV], 
                         pldots: List[PLDot]) -> List['MarketStateClassification']:
        """
        Classify market state from OHLCV and PLdot data.
        
        Returns a list of state classifications for each bar.
        """
        classifications = []
        
        for i, (bar, pldot) in enumerate(zip(ohlcv_data[2:], pldots)):
            classification = cls._classify_single_state(bar, pldot, ohlcv_data, pldots, i)
            classifications.append(classification)
        
        return classifications
    
    @classmethod
    def _classify_single_state(cls, bar: OHLCV, pldot: PLDot, 
                             ohlcv_data: List[OHLCV], 
                             pldots: List[PLDot], 
                             index: int) -> 'MarketStateClassification':
        """Classify market state for a single bar."""
        # Determine if bar closed above or below PLdot
        closed_above = bar.close > pldot.value
        consecutive_side = "above" if closed_above else "below"
        
        # Count consecutive closes on same side
        consecutive_closes = cls._count_consecutive_closes(ohlcv_data, pldots, index, consecutive_side)
        
        # Calculate PLdot slope
        pldot_slope = cls._calculate_pldot_slope(pldots, index)
        
        # Classify state based on rules
        current_state = cls._determine_market_state(consecutive_closes, consecutive_side, pldot_slope)
        
        # Calculate confidence based on signal strength
        confidence = cls._calculate_confidence(consecutive_closes, pldot_slope, bar, pldot)
        
        return cls(
            current_state=current_state,
            confidence=confidence,
            consecutive_closes=consecutive_closes,
            consecutive_side=consecutive_side,
            pldot_slope=pldot_slope
        )
    
    @classmethod
    def _count_consecutive_closes(cls, ohlcv_data: List[OHLCV], 
                                pldots: List[PLDot], 
                                current_index: int, 
                                side: str) -> int:
        """Count consecutive closes on the same side of PLdot."""
        count = 0
        for i in range(current_index, -1, -1):
            if i >= len(ohlcv_data) or i >= len(pldots):
                break
                
            bar = ohlcv_data[i]
            pldot = pldots[i]
            
            is_above = bar.close > pldot.value
            
            if (side == "above" and is_above) or (side == "below" and not is_above):
                count += 1
            else:
                break
        
        return count
    
    @classmethod
    def _calculate_pldot_slope(cls, pldots: List[PLDot], index: int) -> Optional[Decimal]:
        """Calculate the slope of PLdot movement."""
        if index < 1:
            return None
        
        current_pldot = pldots[index]
        previous_pldot = pldots[index - 1]
        
        # Assume equal time intervals for simplicity
        return current_pldot.value - previous_pldot.value
    
    @classmethod
    def _determine_market_state(cls, consecutive_closes: int, 
                              side: str, 
                              pldot_slope: Optional[Decimal]) -> MarketState:
        """Determine market state based on classification criteria."""
        if consecutive_closes >= 3:
            if side == "above":
                return MarketState.TREND_BULLISH if pldot_slope and pldot_slope > 0 else MarketState.CONGESTION_ACTION
            else:
                return MarketState.TREND_BEARISH if pldot_slope and pldot_slope < 0 else MarketState.CONGESTION_ACTION
        elif consecutive_closes == 1:
            # First close on opposite side could indicate congestion entrance
            return MarketState.CONGESTION_ENTRANCE
        else:
            return MarketState.CONGESTION_ACTION
    
    @classmethod
    def _calculate_confidence(cls, consecutive_closes: int, 
                            pldot_slope: Optional[Decimal], 
                            bar: OHLCV, 
                            pldot: PLDot) -> Decimal:
        """Calculate confidence in the state classification."""
        confidence = Decimal('0.5')  # Base confidence
        
        # Higher confidence with more consecutive closes
        if consecutive_closes >= 3:
            confidence += Decimal('0.3')
        elif consecutive_closes == 2:
            confidence += Decimal('0.2')
        elif consecutive_closes == 1:
            confidence += Decimal('0.1')
        
        # Higher confidence with strong PLdot slope in trend direction
        if pldot_slope is not None:
            slope_strength = abs(pldot_slope) / pldot.value if pldot.value > 0 else Decimal('0')
            if slope_strength > Decimal('0.001'):  # Significant slope
                confidence += Decimal('0.2')
        
        return min(confidence, Decimal('1.0'))
```

### 3.2 TradingPattern Classes

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional, Dict, Any
from decimal import Decimal

@dataclass
class PatternMetadata:
    """Metadata for trading patterns."""
    pattern_type: str
    timeframe: str
    strength: Decimal  # 0.0 to 1.0
    reliability: Decimal  # 0.0 to 1.0
    expected_duration: Optional[int] = None  # Expected duration in bars
    typical_targets: Optional[List[Decimal]] = None
    stop_loss_levels: Optional[List[Decimal]] = None

class TradingPattern(ABC):
    """Abstract base class for all Drummond Geometry trading patterns."""
    
    def __init__(self, metadata: PatternMetadata):
        self.metadata = metadata
        self.confidence: Decimal = Decimal('0.0')
        self.is_active: bool = False
    
    @abstractmethod
    def identify_pattern(self, ohlcv_data: List[OHLCV], 
                        pldots: List[PLDot], 
                        envelopes: List[EnvelopeBands]) -> bool:
        """
        Identify if this pattern exists in the given data.
        
        Returns True if pattern is identified.
        """
        pass
    
    @abstractmethod
    def get_entry_signals(self) -> List[Dict[str, Any]]:
        """Return potential entry signals from this pattern."""
        pass
    
    @abstractmethod
    def get_exit_targets(self) -> List[Dict[str, Any]]:
        """Return potential exit targets from this pattern."""
        pass

@dataclass
class PLDotPushPattern(TradingPattern):
    """
    PLdot Push Pattern - Occurs in strong trending markets.
    
    Characterized by consecutive closes outside the envelope in the trend direction
    with a steadily sloping PLdot line.
    """
    push_direction: str = "up"  # "up" or "down"
    consecutive_envelope_breaks: int = 0
    envelope_breach_size: List[Decimal] = None
    min_breach_threshold: Decimal = Decimal('0.001')  # 0.1% breach minimum
    
    def __post_init__(self):
        super().__init__(PatternMetadata(
            pattern_type="pldot_push",
            timeframe="",
            strength=Decimal('0.8'),
            reliability=Decimal('0.9')
        ))
        if self.envelope_breach_size is None:
            self.envelope_breach_size = []
    
    def identify_pattern(self, ohlcv_data: List[OHLCV], 
                        pldots: List[PLDot], 
                        envelopes: List[EnvelopeBands]) -> bool:
        """Identify PLdot push pattern."""
        if len(ohlcv_data) < 5 or len(pldots) < 5 or len(envelopes) < 3:
            return False
        
        # Look for consecutive envelope breaks
        breaches = 0
        breach_sizes = []
        consecutive_count = 0
        
        for i in range(-5, 0):  # Check last 5 bars
            bar_idx = len(ohlcv_data) + i
            pldot_idx = len(pldots) + i
            envelope_idx = len(envelopes) + i
            
            if (bar_idx < 0 or pldot_idx < 0 or envelope_idx < 0 or 
                envelope_idx >= len(envelopes)):
                continue
            
            bar = ohlcv_data[bar_idx]
            pldot = pldots[pldot_idx]
            envelope = envelopes[envelope_idx]
            
            # Check if bar closed outside envelope
            if bar.close > envelope.top:
                # Bullish breach
                if i == -1 or (breaches > 0 and self.push_direction == "up"):
                    breaches += 1
                    breach_sizes.append((bar.close - envelope.top) / pldot.value)
                    consecutive_count += 1
                else:
                    consecutive_count = 0
            elif bar.close < envelope.bottom:
                # Bearish breach
                if i == -1 or (breaches > 0 and self.push_direction == "down"):
                    breaches += 1
                    breach_sizes.append((envelope.bottom - bar.close) / pldot.value)
                    consecutive_count += 1
                else:
                    consecutive_count = 0
        
        # Update pattern state
        self.consecutive_envelope_breaks = consecutive_count
        self.envelope_breach_size = breach_sizes[-consecutive_count:] if consecutive_count > 0 else []
        
        # Confirm pattern requires at least 3 consecutive breaches
        is_identified = consecutive_count >= 3
        self.is_active = is_identified
        
        if is_identified:
            self.confidence = min(Decimal(str(consecutive_count * 0.3)), Decimal('1.0'))
        
        return is_identified
    
    def get_entry_signals(self) -> List[Dict[str, Any]]:
        """Get potential entry signals for PLdot push."""
        if not self.is_active:
            return []
        
        return [{
            "type": "breakout_entry",
            "direction": "long" if self.push_direction == "up" else "short",
            "confidence": self.confidence,
            "trigger": "consecutive_envelope_breaks",
            "break_count": self.consecutive_envelope_breaks
        }]
    
    def get_exit_targets(self) -> List[Dict[str, Any]]:
        """Get potential exit targets for PLdot push."""
        if not self.is_active:
            return []
        
        targets = []
        
        # Primary target: PLdot refresh level
        targets.append({
            "type": "pldot_refresh",
            "target_type": "support_resistance",
            "priority": 1
        })
        
        # Secondary target: Opposite envelope boundary
        targets.append({
            "type": "envelope_opposite",
            "target_type": "profit_target",
            "priority": 2
        })
        
        return targets

@dataclass
class PLDotRefreshPattern(TradingPattern):
    """
    PLdot Refresh Pattern - Occurs when price returns to PLdot after extension.
    
    Characterized by significant distance from PLdot followed by convergence,
    often after exhaustion moves.
    """
    max_distance_reached: Decimal = Decimal('0')
    current_distance: Decimal = Decimal('0')
    refresh_direction: str = "toward_pldot"
    is_partial_refresh: bool = False
    target_pldot_value: Optional[Decimal] = None
    
    def __post_init__(self):
        super().__init__(PatternMetadata(
            pattern_type="pldot_refresh",
            timeframe="",
            strength=Decimal('0.7'),
            reliability=Decimal('0.8')
        ))
    
    def identify_pattern(self, ohlcv_data: List[OHLCV], 
                        pldots: List[PLDot], 
                        envelopes: List[EnvelopeBands]) -> bool:
        """Identify PLdot refresh pattern."""
        if len(ohlcv_data) < 10 or len(pldots) < 10:
            return False
        
        # Find maximum distance from PLdot in recent history
        max_distance = Decimal('0')
        max_distance_bar_idx = None
        
        for i in range(-10, 0):
            bar_idx = len(ohlcv_data) + i
            pldot_idx = len(pldots) + i
            
            if bar_idx < 0 or pldot_idx < 0:
                continue
            
            bar = ohlcv_data[bar_idx]
            pldot = pldots[pldot_idx]
            
            distance = abs(bar.close - pldot.value) / pldot.value
            
            if distance > max_distance:
                max_distance = distance
                max_distance_bar_idx = bar_idx
        
        # Check if price is now moving toward PLdot
        current_bar = ohlcv_data[-1]
        current_pldot = pldots[-1]
        current_distance = abs(current_bar.close - current_pldot.value) / current_pldot.value
        
        # Determine if price is moving toward PLdot
        moving_toward = False
        if len(ohlcv_data) >= 2:
            previous_bar = ohlcv_data[-2]
            previous_pldot = pldots[-2]
            previous_distance = abs(previous_bar.close - previous_pldot.value) / previous_pldot.value
            moving_toward = current_distance < previous_distance
        
        # Update pattern state
        self.max_distance_reached = max_distance
        self.current_distance = current_distance
        self.target_pldot_value = current_pldot.value
        
        # Confirm refresh pattern requires significant extension followed by convergence
        min_extension_threshold = Decimal('0.02')  # 2% minimum extension
        is_identified = (max_distance >= min_extension_threshold and moving_toward)
        self.is_active = is_identified
        
        if is_identified:
            # Confidence based on magnitude of extension and rate of refresh
            extension_confidence = min(max_distance / Decimal('0.05'), Decimal('1.0'))  # Cap at 5%
            refresh_confidence = Decimal('0.7') if moving_toward else Decimal('0.3')
            self.confidence = (extension_confidence + refresh_confidence) / 2
        
        return is_identified
    
    def get_entry_signals(self) -> List[Dict[str, Any]]:
        """Get potential entry signals for PLdot refresh."""
        if not self.is_active:
            return []
        
        return [{
            "type": "refresh_entry",
            "direction": "counter_trend",
            "confidence": self.confidence,
            "trigger": "pldot_convergence",
            "max_extension": self.max_distance_reached,
            "current_distance": self.current_distance
        }]
    
    def get_exit_targets(self) -> List[Dict[str, Any]]:
        """Get potential exit targets for PLdot refresh."""
        if not self.is_active:
            return []
        
        return [{
            "type": "pldot_reach",
            "target_type": "primary_target",
            "target_value": self.target_pldot_value,
            "priority": 1
        }, {
            "type": "envelope_return",
            "target_type": "secondary_target",
            "priority": 2
        }]

@dataclass
class ExhaustPattern(TradingPattern):
    """
    Exhaust Pattern - Occurs when market runs out of energy and reverses sharply.
    
    Characterized by extreme extension beyond envelope followed by sharp reversal,
    often with high volume and immediate counter-trend pressure.
    """
    exhaustion_level: Decimal = Decimal('0')
    extension_multiplier: Decimal = Decimal('1.0')  # How many times normal envelope width
    reversal_speed: Optional[Decimal] = None  # Speed of reversal
    volume_surge: bool = False
    post_exhaustion_bias: str = "neutral"  # "bullish", "bearish", "neutral"
    
    def __post_init__(self):
        super().__init__(PatternMetadata(
            pattern_type="exhaust",
            timeframe="",
            strength=Decimal('0.9'),
            reliability=Decimal('0.85')
        ))
    
    def identify_pattern(self, ohlcv_data: List[OHLCV], 
                        pldots: List[PLDot], 
                        envelopes: List[EnvelopeBands]) -> bool:
        """Identify exhaustion pattern."""
        if len(ohlcv_data) < 5 or len(envelopes) < 3:
            return False
        
        # Find extreme extension beyond envelope
        max_extension = Decimal('0')
        exhaustion_bar_idx = None
        
        for i in range(-5, -1):  # Check last 4 bars
            bar_idx = len(ohlcv_data) + i
            envelope_idx = len(envelopes) + i
            
            if (bar_idx < 0 or envelope_idx < 0 or 
                bar_idx >= len(ohlcv_data) or envelope_idx >= len(envelopes)):
                continue
            
            bar = ohlcv_data[bar_idx]
            envelope = envelopes[envelope_idx]
            
            # Calculate extension beyond envelope
            if bar.close > envelope.top:
                extension = (bar.close - envelope.top) / envelope.center
            elif bar.close < envelope.bottom:
                extension = (envelope.bottom - bar.close) / envelope.center
            else:
                extension = Decimal('0')
            
            if extension > max_extension:
                max_extension = extension
                exhaustion_bar_idx = bar_idx
        
        # Check for sharp reversal after exhaustion
        reversal_detected = False
        if exhaustion_bar_idx is not None and exhaustion_bar_idx < len(ohlcv_data) - 1:
            exhaustion_bar = ohlcv_data[exhaustion_bar_idx]
            next_bar = ohlcv_data[exhaustion_bar_idx + 1]
            
            # Check if next bar moves strongly in opposite direction
            if (exhaustion_bar.close > envelopes[exhaustion_bar_idx].top and 
                next_bar.close < exhaustion_bar.close * Decimal('0.995')):  # 0.5% reversal
                reversal_detected = True
            elif (exhaustion_bar.close < envelopes[exhaustion_bar_idx].bottom and 
                  next_bar.close > exhaustion_bar.close * Decimal('1.005')):  # 0.5% reversal
                reversal_detected = True
        
        # Calculate extension multiplier
        extension_multiplier = max_extension / Decimal('0.02')  # Assuming 2% normal envelope
        
        # Update pattern state
        self.exhaustion_level = max_extension
        self.extension_multiplier = extension_multiplier
        self.reversal_speed = self._calculate_reversal_speed(exhaustion_bar_idx) if reversal_detected else None
        
        # Confirm exhaustion pattern requires significant extension plus reversal
        min_extension_threshold = Decimal('0.04')  # 4% minimum extension
        is_identified = (max_extension >= min_extension_threshold and reversal_detected)
        self.is_active = is_identified
        
        if is_identified:
            self.confidence = min(max_extension / Decimal('0.08'), Decimal('1.0'))  # Cap at 8%
            
            # Determine post-exhaustion bias
            if reversal_detected and exhaustion_bar_idx is not None:
                exhaustion_bar = ohlcv_data[exhaustion_bar_idx]
                if exhaustion_bar.close > envelopes[exhaustion_bar_idx].top:
                    self.post_exhaustion_bias = "bearish"
                else:
                    self.post_exhaustion_bias = "bullish"
        
        return is_identified
    
    def _calculate_reversal_speed(self, exhaustion_bar_idx: Optional[int]) -> Optional[Decimal]:
        """Calculate the speed of reversal after exhaustion."""
        if exhaustion_bar_idx is None or exhaustion_bar_idx >= len(ohlcv_data) - 2:
            return None
        
        exhaustion_bar = ohlcv_data[exhaustion_bar_idx]
        reversal_bar = ohlcv_data[exhaustion_bar_idx + 1]
        
        # Calculate reversal as percentage move
        if exhaustion_bar.close > 0:
            reversal = abs(reversal_bar.close - exhaustion_bar.close) / exhaustion_bar.close
            return reversal
        
        return None
    
    def get_entry_signals(self) -> List[Dict[str, Any]]:
        """Get potential entry signals for exhaustion pattern."""
        if not self.is_active:
            return []
        
        return [{
            "type": "exhaustion_reversal",
            "direction": self.post_exhaustion_bias,
            "confidence": self.confidence,
            "trigger": "extreme_extension_reversal",
            "extension_level": self.exhaustion_level,
            "extension_multiplier": self.extension_multiplier
        }]
    
    def get_exit_targets(self) -> List[Dict[str, Any]]:
        """Get potential exit targets for exhaustion pattern."""
        if not self.is_active:
            return []
        
        return [{
            "type": "pldot_convergence",
            "target_type": "primary_target",
            "priority": 1
        }, {
            "type": "envelope_midline",
            "target_type": "secondary_target", 
            "priority": 2
        }, {
            "type": "opposite_envelope",
            "target_type": "extended_target",
            "priority": 3
        }]
```

---

## 4. Signal Generation and Multi-Timeframe Analysis

### 4.1 Signal Class

```python
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import List, Optional, Dict, Any
from enum import Enum

class SignalType(Enum):
    """Types of trading signals in Drummond Geometry."""
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"
    EXIT_LONG = "exit_long"
    EXIT_SHORT = "exit_short"
    STOP_LOSS = "stop_loss"
    TAKE_PROFIT = "take_profit"

class SignalStrength(Enum):
    """Signal strength levels."""
    WEAK = "weak"
    MODERATE = "moderate"
    STRONG = "strong"
    VERY_STRONG = "very_strong"

@dataclass
class Signal:
    """
    Trading signal generated by Drummond Geometry analysis.
    
    Represents a recommendation for trading action with associated metadata
    including confidence levels, targets, and risk parameters.
    """
    signal_type: SignalType
    timestamp: datetime
    symbol: str
    price: Decimal
    
    # Confidence and strength metrics
    confidence: Decimal  # 0.0 to 1.0
    strength: SignalStrength
    confluence_score: Decimal = Decimal('0.0')  # Multi-timeframe confluence
    
    # Risk management
    stop_loss: Optional[Decimal] = None
    take_profit: Optional[Decimal] = None
    risk_reward_ratio: Optional[Decimal] = None
    
    # Pattern and context information
    triggering_pattern: Optional[str] = None
    market_state: Optional[MarketState] = None
    timeframe: Optional[str] = None
    
    # Multi-timeframe context
    higher_timeframe_bias: Optional[str] = None  # "bullish", "bearish", "neutral"
    lower_timeframe_confirmation: Optional[bool] = None
    
    # Metadata
    source_indicators: List[str] = None
    notes: Optional[str] = None
    expiration_time: Optional[datetime] = None
    
    def __post_init__(self):
        """Validate signal data after initialization."""
        if not (0 <= self.confidence <= 1):
            raise ValueError("Confidence must be between 0.0 and 1.0")
        if self.confidence > Decimal('1.0'):
            raise ValueError("Confidence cannot exceed 1.0")
        if self.timestamp.tzinfo != timezone.utc:
            raise ValueError("Signal timestamp must be in UTC timezone")
        if self.price <= 0:
            raise ValueError("Signal price must be positive")
        
        if self.source_indicators is None:
            self.source_indicators = []
    
    @classmethod
    def create_buy_signal(cls, symbol: str, price: Decimal, confidence: Decimal,
                        stop_loss: Optional[Decimal] = None,
                        take_profit: Optional[Decimal] = None,
                        **kwargs) -> 'Signal':
        """Create a buy signal with automatic risk-reward calculation."""
        if take_profit and stop_loss and price > 0:
            risk = price - stop_loss if stop_loss else Decimal('0')
            reward = take_profit - price if take_profit else Decimal('0')
            if risk > 0:
                risk_reward = reward / risk
            else:
                risk_reward = Decimal('0')
        else:
            risk_reward = None
        
        return cls(
            signal_type=SignalType.BUY,
            timestamp=datetime.now(timezone.utc),
            symbol=symbol,
            price=price,
            confidence=confidence,
            strength=cls._determine_strength(confidence),
            stop_loss=stop_loss,
            take_profit=take_profit,
            risk_reward_ratio=risk_reward,
            **kwargs
        )
    
    @classmethod
    def create_sell_signal(cls, symbol: str, price: Decimal, confidence: Decimal,
                         stop_loss: Optional[Decimal] = None,
                         take_profit: Optional[Decimal] = None,
                         **kwargs) -> 'Signal':
        """Create a sell signal with automatic risk-reward calculation."""
        if take_profit and stop_loss and price > 0:
            risk = stop_loss - price if stop_loss else Decimal('0')
            reward = price - take_profit if take_profit else Decimal('0')
            if risk > 0:
                risk_reward = reward / risk
            else:
                risk_reward = Decimal('0')
        else:
            risk_reward = None
        
        return cls(
            signal_type=SignalType.SELL,
            timestamp=datetime.now(timezone.utc),
            symbol=symbol,
            price=position_price,
            confidence=confidence,
            strength=cls._determine_strength(confidence),
            stop_loss=stop_loss,
            take_profit=take_profit,
            risk_reward_ratio=risk_reward,
            **kwargs
        )
    
    @classmethod
    def _determine_strength(cls, confidence: Decimal) -> SignalStrength:
        """Determine signal strength from confidence level."""
        if confidence >= Decimal('0.8'):
            return SignalStrength.VERY_STRONG
        elif confidence >= Decimal('0.6'):
            return SignalStrength.STRONG
        elif confidence >= Decimal('0.4'):
            return SignalStrength.MODERATE
        else:
            return SignalStrength.WEAK
    
    def calculate_risk_reward(self) -> Optional[Decimal]:
        """Calculate current risk-reward ratio for this signal."""
        if not self.stop_loss or not self.take_profit:
            return None
        
        if self.signal_type in [SignalType.BUY]:
            risk = self.price - self.stop_loss
            reward = self.take_profit - self.price
        elif self.signal_type in [SignalType.SELL]:
            risk = self.stop_loss - self.price
            reward = self.price - self.take_profit
        else:
            return None
        
        if risk > 0:
            return reward / risk
        return None
    
    def is_expired(self, current_time: Optional[datetime] = None) -> bool:
        """Check if signal has expired."""
        if current_time is None:
            current_time = datetime.now(timezone.utc)
        
        if self.expiration_time:
            return current_time > self.expiration_time
        
        # Default expiration: signals expire after 1 day
        return (current_time - self.timestamp).total_seconds() > 86400
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert signal to dictionary for serialization."""
        return {
            "signal_type": self.signal_type.value,
            "timestamp": self.timestamp.isoformat(),
            "symbol": self.symbol,
            "price": float(self.price),
            "confidence": float(self.confidence),
            "strength": self.strength.value,
            "confluence_score": float(self.confluence_score),
            "stop_loss": float(self.stop_loss) if self.stop_loss else None,
            "take_profit": float(self.take_profit) if self.take_profit else None,
            "risk_reward_ratio": float(self.risk_reward_ratio) if self.risk_reward_ratio else None,
            "triggering_pattern": self.triggering_pattern,
            "market_state": self.market_state.value if self.market_state else None,
            "timeframe": self.timeframe,
            "higher_timeframe_bias": self.higher_timeframe_bias,
            "lower_timeframe_confirmation": self.lower_timeframe_confirmation,
            "source_indicators": self.source_indicators,
            "notes": self.notes,
            "expiration_time": self.expiration_time.isoformat() if self.expiration_time else None
        }
```

### 4.2 Multi-TimeframeCoordination Class

```python
from dataclasses import dataclass
from typing import List, Optional, Dict, Any
from decimal import Decimal
from datetime import datetime

@dataclass
class TimeframeData:
    """Container for data from a specific timeframe."""
    timeframe: str  # e.g., "1m", "5m", "15m", "1h", "4h", "1d", "1w", "1M"
    ohlcv_data: List[OHLCV]
    pldots: List[PLDot]
    envelopes: List[EnvelopeBands]
    drummond_lines: DrummondLines
    market_states: List[MarketStateClassification]
    patterns: List[TradingPattern]
    signals: List[Signal]
    
    def __post_init__(self):
        """Sort data by timestamp and validate consistency."""
        self.ohlcv_data.sort(key=lambda x: x.timestamp)
        self.pldots.sort(key=lambda x: x.timestamp)
        self.envelopes.sort(key=lambda x: x.timestamp)
        if self.market_states:
            self.market_states.sort(key=lambda x: x.current_state)
        self.signals.sort(key=lambda x: x.timestamp)

@dataclass
class MultiTimeframeAnalysis:
    """
    Multi-timeframe analysis coordinating data across multiple timeframes.
    
    Provides the core functionality for timeframe coordination that makes
    Drummond Geometry particularly powerful for identifying high-probability setups.
    """
    symbol: str
    timeframes: Dict[str, TimeframeData]  # timeframe -> TimeframeData
    analysis_timestamp: datetime
    
    # Multi-timeframe confluence metrics
    confluence_zones: List[SupportResistanceZone] = None
    aligned_signals: List[Signal] = None
    timeframe_hierarchy: List[str] = None  # Ordered by importance
    
    def __post_init__(self):
        """Initialize empty lists and establish timeframe hierarchy."""
        if self.confluence_zones is None:
            self.confluence_zones = []
        if self.aligned_signals is None:
            self.aligned_signals = []
        if self.timeframe_hierarchy is None:
            # Establish default hierarchy (can be customized)
            self.timeframe_hierarchy = ["1M", "1w", "1d", "4h", "1h", "15m", "5m", "1m"]
        
        self._analyze_confluence()
        self._identify_aligned_signals()
    
    def _analyze_confluence(self) -> None:
        """Identify confluence zones where multiple timeframes align."""
        # Get support/resistance zones from all timeframes
        all_zones = []
        for tf_data in self.timeframes.values():
            all_zones.extend(tf_data.drummond_lines.support_zones)
            all_zones.extend(tf_data.drummond_lines.resistance_zones)
        
        # Group zones by price proximity
        confluence_clusters = self._cluster_zones_by_price(all_zones)
        
        for cluster in confluence_clusters:
            if len(cluster) >= 2:  # Need at least 2 timeframes
                confluence_zone = self._create_confluence_zone(cluster)
                if confluence_zone:
                    self.confluence_zones.append(confluence_zone)
    
    def _cluster_zones_by_price(self, zones: List[SupportResistanceZone]) -> List[List[SupportResistanceZone]]:
        """Cluster zones by price proximity to identify confluence."""
        clusters = []
        used_zones = set()
        
        for zone in zones:
            if id(zone) in used_zones:
                continue
            
            cluster = [zone]
            used_zones.add(id(zone))
            
            for other_zone in zones:
                if id(other_zone) in used_zones:
                    continue
                
                # Check price proximity (using percentage tolerance)
                price_diff_pct = abs(zone.center_price - other_zone.center_price) / zone.center_price
                tolerance = Decimal('0.005')  # 0.5% tolerance
                
                if price_diff_pct <= tolerance:
                    cluster.append(other_zone)
                    used_zones.add(id(other_zone))
            
            clusters.append(cluster)
        
        return clusters
    
    def _create_confluence_zone(self, zone_cluster: List[SupportResistanceZone]) -> Optional[SupportResistanceZone]:
        """Create a confluence zone from a cluster of zones."""
        if not zone_cluster:
            return None
        
        # Calculate combined zone boundaries
        all_prices = []
        for zone in zone_cluster:
            all_prices.extend([zone.top_price, zone.bottom_price])
        
        top_price = max(all_prices)
        bottom_price = min(all_prices)
        center_price = (top_price + bottom_price) / 2
        
        # Calculate confluence strength
        base_strength = sum(zone.strength for zone in zone_cluster) / len(zone_cluster)
        timeframe_bonus = min(Decimal(str(len(zone_cluster) * 0.1)), Decimal('0.3'))
        strength = min(base_strength + timeframe_bonus, Decimal('1.0'))
        
        # Determine zone type from majority
        support_count = sum(1 for zone in zone_cluster if zone.zone_type == "support")
        resistance_count = len(zone_cluster) - support_count
        
        zone_type = "support" if support_count > resistance_count else "resistance"
        
        return SupportResistanceZone(
            zone_type=zone_type,
            top_price=top_price,
            bottom_price=bottom_price,
            center_price=center_price,
            start_timestamp=min(zone.start_timestamp for zone in zone_cluster),
            strength=strength,
            contributing_lines=[],
            timeframe="multi_tf_confluence"
        )
    
    def _identify_aligned_signals(self) -> None:
        """Identify signals that align across multiple timeframes."""
        all_signals = []
        for tf_data in self.timeframes.values():
            all_signals.extend(tf_data.signals)
        
        # Group signals by type and proximity
        aligned_clusters = self._cluster_signals_by_alignment(all_signals)
        
        for cluster in aligned_clusters:
            if len(cluster) >= 2:  # Need at least 2 timeframes
                aligned_signal = self._create_aligned_signal(cluster)
                if aligned_signal:
                    self.aligned_signals.append(aligned_signal)
    
    def _cluster_signals_by_alignment(self, signals: List[Signal]) -> List[List[Signal]]:
        """Cluster signals that are aligned across timeframes."""
        # Simplified alignment logic - in practice would be more sophisticated
        aligned_clusters = []
        timeframes_with_signals = {}
        
        # Group signals by timeframe
        for signal in signals:
            tf = signal.timeframe
            if tf not in timeframes_with_signals:
                timeframes_with_signals[tf] = []
            timeframes_with_signals[tf].append(signal)
        
        # Create clusters from multiple timeframes
        if len(timeframes_with_signals) >= 2:
            cluster = []
            for tf, tf_signals in timeframes_with_signals.items():
                # Take the strongest signal from each timeframe
                strongest_signal = max(tf_signals, key=lambda s: s.confidence)
                cluster.append(strongest_signal)
            aligned_clusters.append(cluster)
        
        return aligned_clusters
    
    def _create_aligned_signal(self, signal_cluster: List[Signal]) -> Optional[Signal]:
        """Create an aligned signal from multiple timeframe signals."""
        if not signal_cluster:
            return None
        
        # Use the strongest signal as base
        base_signal = max(signal_cluster, key=lambda s: s.confidence)
        
        # Calculate confluence score based on number of aligned timeframes
        confluence_score = Decimal(str(len(signal_cluster) * 0.25))  # 0.25 per aligned timeframe
        
        # Combine source indicators
        all_source_indicators = []
        for signal in signal_cluster:
            all_source_indicators.extend(signal.source_indicators)
        
        return Signal(
            signal_type=base_signal.signal_type,
            timestamp=self.analysis_timestamp,
            symbol=base_signal.symbol,
            price=base_signal.price,
            confidence=min(base_signal.confidence + confluence_score, Decimal('1.0')),
            strength=Signal._determine_strength(min(base_signal.confidence + confluence_score, Decimal('1.0'))),
            confluence_score=confluence_score,
            stop_loss=base_signal.stop_loss,
            take_profit=base_signal.take_profit,
            risk_reward_ratio=base_signal.risk_reward_ratio,
            triggering_pattern=base_signal.triggering_pattern,
            market_state=base_signal.market_state,
            timeframe="multi_tf_aligned",
            higher_timeframe_bias=base_signal.higher_timeframe_bias,
            lower_timeframe_confirmation=base_signal.lower_timeframe_confirmation,
            source_indicators=list(set(all_source_indicators)),
            notes=f"Aligned across {len(signal_cluster)} timeframes"
        )
    
    def get_confluence_zones_for_price(self, price: Decimal) -> List[SupportResistanceZone]:
        """Get confluence zones that contain the given price."""
        return [zone for zone in self.confluence_zones if zone.is_price_in_zone(price)]
    
    def get_highest_confidence_signals(self, limit: int = 5) -> List[Signal]:
        """Get the highest confidence signals across all timeframes."""
        all_signals = []
        for tf_data in self.timeframes.values():
            all_signals.extend(tf_data.signals)
        
        return sorted(all_signals, key=lambda s: s.confidence, reverse=True)[:limit]
    
    def get_market_bias(self) -> str:
        """
        Determine overall market bias based on higher timeframes.
        
        Returns "bullish", "bearish", or "neutral".
        """
        if not self.timeframe_hierarchy:
            return "neutral"
        
        # Count bullish vs bearish signals in higher timeframes
        bullish_count = 0
        bearish_count = 0
        
        for tf in self.timeframe_hierarchy[:3]:  # Top 3 timeframes
            if tf in self.timeframes:
                tf_data = self.timeframes[tf]
                for signal in tf_data.signals:
                    if signal.signal_type == SignalType.BUY:
                        bullish_count += signal.confidence
                    elif signal.signal_type == SignalType.SELL:
                        bearish_count += signal.confidence
        
        if bullish_count > bearish_count * Decimal('1.2'):
            return "bullish"
        elif bearish_count > bullish_count * Decimal('1.2'):
            return "bearish"
        else:
            return "neutral"
    
    def generate_coordinated_signals(self) -> List[Signal]:
        """Generate signals that coordinate multiple timeframes."""
        coordinated_signals = []
        
        # Add aligned signals
        coordinated_signals.extend(self.aligned_signals)
        
        # Add high-confidence confluence zone signals
        for zone in self.confluence_zones:
            if zone.strength > Decimal('0.7'):  # Strong confluence
                for tf_data in self.timeframes.values():
                    recent_price = tf_data.ohlcv_data[-1].close if tf_data.ohlcv_data else None
                    if recent_price and zone.is_price_in_zone(recent_price):
                        signal_type = SignalType.BUY if zone.zone_type == "support" else SignalType.SELL
                        signal = Signal(
                            signal_type=signal_type,
                            timestamp=self.analysis_timestamp,
                            symbol="",  # Will be set by caller
                            price=recent_price,
                            confidence=zone.strength,
                            strength=Signal._determine_strength(zone.strength),
                            confluence_score=zone.strength,
                            triggering_pattern="confluence_zone",
                            timeframe="multi_tf_confluence",
                            notes=f"{zone.zone_type.title()} confluence zone"
                        )
                        coordinated_signals.append(signal)
        
        return coordinated_signals
```

---

## 5. Validation and Error Handling

### 5.1 Validation Framework

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional, Dict, Any, Tuple
from decimal import Decimal
from enum import Enum

class ValidationSeverity(Enum):
    """Severity levels for validation issues."""
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"

@dataclass
class ValidationIssue:
    """Represents a validation issue found in data or calculations."""
    severity: ValidationSeverity
    code: str
    message: str
    affected_object: Optional[str] = None
    timestamp: Optional[datetime] = None
    suggested_fix: Optional[str] = None
    
    def __post_init__(self):
        """Set timestamp if not provided."""
        if self.timestamp is None:
            self.timestamp = datetime.now(timezone.utc)

class DataValidator(ABC):
    """Abstract base class for data validation."""
    
    def __init__(self):
        self.issues: List[ValidationIssue] = []
    
    @abstractmethod
    def validate(self, data: Any) -> List[ValidationIssue]:
        """Validate data and return list of issues."""
        pass
    
    def add_issue(self, severity: ValidationSeverity, code: str, 
                  message: str, affected_object: Optional[str] = None,
                  suggested_fix: Optional[str] = None) -> None:
        """Add a validation issue."""
        issue = ValidationIssue(
            severity=severity,
            code=code,
            message=message,
            affected_object=affected_object,
            suggested_fix=suggested_fix
        )
        self.issues.append(issue)
    
    def has_errors(self) -> bool:
        """Check if any errors were found."""
        return any(issue.severity == ValidationSeverity.ERROR for issue in self.issues)
    
    def get_errors(self) -> List[ValidationIssue]:
        """Get all error-level issues."""
        return [issue for issue in self.issues if issue.severity == ValidationSeverity.ERROR]
    
    def get_warnings(self) -> List[ValidationIssue]:
        """Get all warning-level issues."""
        return [issue for issue in self.issues if issue.severity == ValidationSeverity.WARNING]

@dataclass
class OHLCVValidator(DataValidator):
    """Validator for OHLCV data."""
    
    def validate(self, ohlcv_data: List[OHLCV]) -> List[ValidationIssue]:
        """Validate OHLCV data and return issues."""
        self.issues.clear()
        
        if not ohlcv_data:
            self.add_issue(ValidationSeverity.ERROR, "EMPTY_DATA", 
                          "OHLCV data list is empty")
            return self.issues
        
        # Check data ordering
        for i in range(1, len(ohlcv_data)):
            if ohlcv_data[i].timestamp <= ohlcv_data[i-1].timestamp:
                self.add_issue(ValidationSeverity.ERROR, "INVALID_ORDERING",
                              f"Data not properly ordered at index {i}",
                              affected_object=f"OHLCV[{i}]")
        
        # Check for sufficient data
        if len(ohlcv_data) < 3:
            self.add_issue(ValidationSeverity.WARNING, "INSUFFICIENT_DATA",
                          f"Only {len(ohlcv_data)} bars available, recommend at least 20")
        
        # Validate each bar
        for i, bar in enumerate(ohlcv_data):
            self._validate_single_bar(bar, i)
        
        return self.issues
    
    def _validate_single_bar(self, bar: OHLCV, index: int) -> None:
        """Validate a single OHLCV bar."""
        # Check OHLC relationships
        if bar.high < bar.low:
            self.add_issue(ValidationSeverity.ERROR, "INVALID_RANGE",
                          f"High ({bar.high}) less than Low ({bar.low})",
                          affected_object=f"OHLCV[{index}]")
        
        if bar.open < bar.low or bar.open > bar.high:
            self.add_issue(ValidationSeverity.WARNING, "OPEN_OUTSIDE_RANGE",
                          f"Open ({bar.open}) outside High-Low range",
                          affected_object=f"OHLCV[{index}]")
        
        if bar.close < bar.low or bar.close > bar.high:
            self.add_issue(ValidationSeverity.WARNING, "CLOSE_OUTSIDE_RANGE",
                          f"Close ({bar.close}) outside High-Low range",
                          affected_object=f"OHLCV[{index}]")
        
        # Check for zero or negative prices
        if bar.open <= 0 or bar.high <= 0 or bar.low <= 0 or bar.close <= 0:
            self.add_issue(ValidationSeverity.ERROR, "NON_POSITIVE_PRICE",
                          "All OHLC prices must be positive",
                          affected_object=f"OHLCV[{index}]")
        
        # Check for extreme values (potential data errors)
        avg_price = (bar.high + bar.low + bar.close) / 3
        if bar.high > 0:
            price_ratio = bar.high / avg_price
            if price_ratio > Decimal('10'):  # High is 10x average
                self.add_issue(ValidationSeverity.WARNING, "EXTREME_HIGH",
                              f"High price ({bar.high}) is {price_ratio:.1f}x average",
                              affected_object=f"OHLCV[{index}]")
        
        # Check for missing volume if required
        if bar.volume is not None and bar.volume < 0:
            self.add_issue(ValidationSeverity.ERROR, "NEGATIVE_VOLUME",
                          "Volume cannot be negative",
                          affected_object=f"OHLCV[{index}]")

@dataclass
class PLDotValidator(DataValidator):
    """Validator for PLdot calculations and data."""
    
    def validate(self, pldots: List[PLDot], ohlcv_data: List[OHLCV]) -> List[ValidationIssue]:
        """Validate PLdot data."""
        self.issues.clear()
        
        if not pldots:
            self.add_issue(ValidationSeverity.ERROR, "EMPTY_PLDOT_DATA",
                          "PLdot data list is empty")
            return self.issues
        
        # Check PLdot-OHLCV alignment
        if len(pldots) > len(ohlcv_data) + 1:
            self.add_issue(ValidationSeverity.ERROR, "PLDOT_MISMATCH",
                          f"Too many PLdot values ({len(pldots)}) for OHLCV data ({len(ohlcv_data)})")
        
        # Validate each PLdot
        for i, pldot in enumerate(pldots):
            self._validate_single_pldot(pldot, i, ohlcv_data)
        
        # Check for calculation consistency
        self._validate_pldot_calculations(pldots, ohlcv_data)
        
        return self.issues
    
    def _validate_single_pldot(self, pldot: PLDot, index: int, ohlcv_data: List[OHLCV]) -> None:
        """Validate a single PLdot value."""
        if pldot.value <= 0:
            self.add_issue(ValidationSeverity.ERROR, "NON_POSITIVE_PLDOT",
                          f"PLdot value must be positive, got {pldot.value}",
                          affected_object=f"PLDot[{index}]")
        
        # Check if PLdot is projected (should have future timestamp)
        if pldot.is_projected:
            # Projected PLdots should have timestamps after their source data
            if index < len(ohlcv_data):
                source_bar = ohlcv_data[index]
                if pldot.timestamp <= source_bar.timestamp:
                    self.add_issue(ValidationSeverity.WARNING, "INVALID_PROJECTION",
                                  "Projected PLdot should have future timestamp",
                                  affected_object=f"PLDot[{index}]")
        
        # Validate metadata
        if pldot.metadata:
            if not 0 <= pldot.metadata.confidence <= 1:
                self.add_issue(ValidationSeverity.ERROR, "INVALID_CONFIDENCE",
                              "PLdot confidence must be between 0 and 1",
                              affected_object=f"PLDot[{index}]")
    
    def _validate_pldot_calculations(self, pldots: List[PLDot], ohlcv_data: List[OHLCV]) -> None:
        """Validate PLdot calculation accuracy."""
        # Manually recalculate a few PLdots to verify accuracy
        test_indices = [2, len(pldots)//2, len(pldots)-1] if len(pldots) >= 3 else [2 if len(pldots) > 2 else 0]
        
        for idx in test_indices:
            if idx < len(pldots) and idx < len(ohlcv_data) and idx >= 2:
                calculated_pldot = pldots[idx]
                expected_value = self._calculate_expected_pldot(ohlcv_data, idx)
                
                if abs(calculated_pldot.value - expected_value) > Decimal('0.001'):
                    self.add_issue(ValidationSeverity.ERROR, "CALCULATION_ERROR",
                                  f"PLdot calculation error at index {idx}: "
                                  f"expected {expected_value}, got {calculated_pldot.value}",
                                  affected_object=f"PLDot[{idx}]")
    
    def _calculate_expected_pldot(self, ohlcv_data: List[OHLCV], index: int) -> Decimal:
        """Calculate expected PLdot value for verification."""
        bar_averages = []
        for i in range(index-2, index+1):
            if i >= 0 and i < len(ohlcv_data):
                bar = ohlcv_data[i]
                avg = (bar.high + bar.low + bar.close) / 3
                bar_averages.append(avg)
        
        return sum(bar_averages) / len(bar_averages) if bar_averages else Decimal('0')

@dataclass
class EnvelopeValidator(DataValidator):
    """Validator for envelope calculations and data."""
    
    def validate(self, envelopes: List[EnvelopeBands], pldots: List[PLDot]) -> List[ValidationIssue]:
        """Validate envelope data."""
        self.issues.clear()
        
        if not envelopes:
            self.add_issue(ValidationSeverity.ERROR, "EMPTY_ENVELOPE_DATA",
                          "Envelope data list is empty")
            return self.issues
        
        # Validate each envelope
        for i, envelope in enumerate(envelopes):
            self._validate_single_envelope(envelope, i, pldots)
        
        # Check envelope-pldot alignment
        self._validate_envelope_pldot_alignment(envelopes, pldots)
        
        return self.issues
    
    def _validate_single_envelope(self, envelope: EnvelopeBands, index: int, pldots: List[PLDot]) -> None:
        """Validate a single envelope."""
        if envelope.top <= envelope.bottom:
            self.add_issue(ValidationSeverity.ERROR, "INVALID_ENVELOPE_ORDER",
                          f"Envelope top ({envelope.top}) must be greater than bottom ({envelope.bottom})",
                          affected_object=f"Envelope[{index}]")
        
        if envelope.top <= 0 or envelope.bottom <= 0:
            self.add_issue(ValidationSeverity.ERROR, "NON_POSITIVE_ENVELOPE",
                          "Envelope boundaries must be positive",
                          affected_object=f"Envelope[{index}]")
        
        # Check envelope width reasonableness
        if envelope.center > 0:
            width_pct = envelope.width / envelope.center
            if width_pct > Decimal('0.5'):  # 50% width seems unreasonable
                self.add_issue(ValidationSeverity.WARNING, "EXTREME_ENVELOPE_WIDTH",
                              f"Envelope width ({width_pct:.1%}) seems excessive",
                              affected_object=f"Envelope[{index}]")
    
    def _validate_envelope_pldot_alignment(self, envelopes: List[EnvelopeBands], pldots: List[PLDot]) -> None:
        """Validate alignment between envelopes and PLdots."""
        min_length = min(len(envelopes), len(pldots))
        
        for i in range(min_length):
            envelope = envelopes[i]
            pldot = pldots[i]
            
            # PLdot should be at or near center of envelope
            if envelope.center > 0:
                pldot_offset = abs(envelope.center - pldot.value) / envelope.center
                if pldot_offset > Decimal('0.01'):  # 1% offset
                    self.add_issue(ValidationSeverity.WARNING, "PLDOT_ENVELOPE_MISALIGNMENT",
                                  f"PLdot offset from envelope center: {pldot_offset:.1%}",
                                  affected_object=f"Envelope[{i}]")

@dataclass
class ComprehensiveValidator:
    """Comprehensive validator that checks all Drummond Geometry components."""
    
    def __init__(self):
        self.ohlcv_validator = OHLCVValidator()
        self.pldot_validator = PLDotValidator()
        self.envelope_validator = EnvelopeValidator()
    
    def validate_analysis(self, analysis: MultiTimeframeAnalysis) -> Dict[str, List[ValidationIssue]]:
        """Validate a complete multi-timeframe analysis."""
        results = {}
        
        # Validate each timeframe's data
        for timeframe, tf_data in analysis.timeframes.items():
            # Validate OHLCV
            ohlcv_issues = self.ohlcv_validator.validate(tf_data.ohlcv_data)
            if ohlcv_issues:
                results[f"{timeframe}_ohlcv"] = ohlcv_issues
            
            # Validate PLdots
            pldot_issues = self.pldot_validator.validate(tf_data.pldots, tf_data.ohlcv_data)
            if pldot_issues:
                results[f"{timeframe}_pldot"] = pldot_issues
            
            # Validate envelopes
            envelope_issues = self.envelope_validator.validate(tf_data.envelopes, tf_data.pldots)
            if envelope_issues:
                results[f"{timeframe}_envelope"] = envelope_issues
        
        # Validate multi-timeframe coordination
        mtf_issues = self._validate_multi_timeframe_aspects(analysis)
        if mtf_issues:
            results["multi_timeframe"] = mtf_issues
        
        return results
    
    def _validate_multi_timeframe_aspects(self, analysis: MultiTimeframeAnalysis) -> List[ValidationIssue]:
        """Validate multi-timeframe coordination aspects."""
        issues = []
        
        # Check timeframe consistency
        for timeframe, tf_data in analysis.timeframes.items():
            if not tf_data.ohlcv_data:
                issues.append(ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    code="EMPTY_TIMEFRAME",
                    message=f"No OHLCV data for timeframe {timeframe}",
                    suggested_fix="Ensure data is available for all specified timeframes"
                ))
        
        # Check confluence zone validity
        for i, zone in enumerate(analysis.confluence_zones):
            if zone.width <= 0:
                issues.append(ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    code="INVALID_CONFLUENCE_ZONE",
                    message=f"Confluence zone {i} has invalid width",
                    suggested_fix="Review zone calculation logic"
                ))
            
            if zone.strength > Decimal('1.0'):
                issues.append(ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    code="INVALID_ZONE_STRENGTH",
                    message=f"Confluence zone {i} strength exceeds 1.0",
                    suggested_fix="Review zone strength calculation"
                ))
        
        return issues
    
    def generate_validation_report(self, issues: Dict[str, List[ValidationIssue]]) -> str:
        """Generate a human-readable validation report."""
        if not issues:
            return "✅ No validation issues found. All data appears valid."
        
        report = "🔍 Drummond Geometry Validation Report\n"
        report += "=" * 50 + "\n\n"
        
        error_count = 0
        warning_count = 0
        
        for category, category_issues in issues.items():
            report += f"📊 {category.replace('_', ' ').title()}:\n"
            
            for issue in category_issues:
                if issue.severity == ValidationSeverity.ERROR:
                    report += f"  ❌ ERROR: {issue.code} - {issue.message}\n"
                    error_count += 1
                elif issue.severity == ValidationSeverity.WARNING:
                    report += f"  ⚠️  WARNING: {issue.code} - {issue.message}\n"
                    warning_count += 1
                else:
                    report += f"  ℹ️  INFO: {issue.code} - {issue.message}\n"
                
                if issue.affected_object:
                    report += f"      Affected: {issue.affected_object}\n"
                
                if issue.suggested_fix:
                    report += f"      Fix: {issue.suggested_fix}\n"
            
            report += "\n"
        
        report += "=" * 50 + "\n"
        report += f"Summary: {error_count} errors, {warning_count} warnings\n"
        
        if error_count == 0:
            report += "✅ Data validation passed with warnings only."
        else:
            report += "❌ Critical validation errors found. Please review and fix."
        
        return report
```

### 5.2 Error Handling and Recovery

```python
from contextlib import contextmanager
from typing import Callable, Any, Optional
import logging
from functools import wraps

class DrummondGeometryError(Exception):
    """Base exception for all Drummond Geometry related errors."""
    pass

class InsufficientDataError(DrummondGeometryError):
    """Raised when insufficient data is provided for calculations."""
    pass

class CalculationError(DrummondGeometryError):
    """Raised when calculation produces invalid results."""
    pass

class ValidationError(DrummondGeometryError):
    """Raised when data validation fails."""
    pass

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def handle_drummond_errors(func: Callable) -> Callable:
    """Decorator to handle Drummond Geometry specific errors."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except InsufficientDataError as e:
            logger.error(f"Insufficient data in {func.__name__}: {e}")
            return None  # Or raise a custom result
        except CalculationError as e:
            logger.error(f"Calculation error in {func.__name__}: {e}")
            return None  # Or raise a custom result
        except ValidationError as e:
            logger.error(f"Validation error in {func.__name__}: {e}")
            return None  # Or raise a custom result
        except Exception as e:
            logger.error(f"Unexpected error in {func.__name__}: {e}")
            raise  # Re-raise unexpected errors
    
    return wrapper

@contextmanager
def safe_calculation_context(allow_partial_results: bool = False):
    """Context manager for safe calculations with fallback options."""
    try:
        yield
    except (InsufficientDataError, CalculationError) as e:
        if allow_partial_results:
            logger.warning(f"Calculation failed, allowing partial results: {e}")
        else:
            logger.error(f"Calculation failed: {e}")
            raise
    except ValidationError as e:
        logger.error(f"Validation failed: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error in calculation context: {e}")
        raise

class CalculationRecovery:
    """Utilities for recovering from calculation failures."""
    
    @staticmethod
    def try_alternative_calculation(methods: list, data: Any, *args, **kwargs) -> Any:
        """Try multiple calculation methods in sequence until one succeeds."""
        last_error = None
        
        for method in methods:
            try:
                result = method(data, *args, **kwargs)
                if result is not None:
                    logger.info(f"Successful calculation using {method.__name__}")
                    return result
            except Exception as e:
                last_error = e
                logger.warning(f"Method {method.__name__} failed: {e}")
                continue
        
        # If all methods failed, raise the last error
        if last_error:
            raise last_error
        
        return None
    
    @staticmethod
    def interpolate_missing_values(data: List[Optional[Decimal]], 
                                 interpolation_method: str = "linear") -> List[Decimal]:
        """Interpolate missing values in time series data."""
        if not data:
            return []
        
        result = []
        
        for i, value in enumerate(data):
            if value is not None:
                result.append(value)
            else:
                # Find nearest non-missing values
                prev_value = None
                next_value = None
                
                # Look backwards
                for j in range(i-1, -1, -1):
                    if data[j] is not None:
                        prev_value = data[j]
                        break
                
                # Look forwards
                for j in range(i+1, len(data)):
                    if data[j] is not None:
                        next_value = data[j]
                        break
                
                # Interpolate based on available values
                if prev_value is not None and next_value is not None:
                    if interpolation_method == "linear":
                        # Linear interpolation
                        steps = next_value - prev_value
                        step_size = steps / (j - i + (i - j))  # Simplified
                        interpolated_value = prev_value + step_size * (i - (i - (j - i)))
                        result.append(interpolated_value)
                    else:
                        # Use previous value (forward fill)
                        result.append(prev_value)
                elif prev_value is not None:
                    result.append(prev_value)
                elif next_value is not None:
                    result.append(next_value)
                else:
                    # No reference values available
                    raise ValueError("Cannot interpolate: no reference values available")
        
        return result
    
    @staticmethod
    def fallback_to_simpler_calculation(complex_calculation: Callable,
                                      simple_calculation: Callable,
                                      *args, **kwargs) -> Any:
        """Try complex calculation first, fall back to simpler version if it fails."""
        try:
            return complex_calculation(*args, **kwargs)
        except (InsufficientDataError, CalculationError) as e:
            logger.warning(f"Complex calculation failed, trying simpler version: {e}")
            try:
                return simple_calculation(*args, **kwargs)
            except Exception as fallback_error:
                logger.error(f"Both complex and simple calculations failed: {fallback_error}")
                raise fallback_error
```

---

## 6. Usage Examples and Integration

### 6.1 Complete Analysis Example

```python
from decimal import Decimal
from datetime import datetime, timedelta, timezone
from typing import List

def example_drummond_analysis():
    """Complete example of Drummond Geometry analysis."""
    
    # Generate sample OHLCV data
    ohlcv_data = generate_sample_ohlcv_data("EURUSD", 100)
    
    # Validate OHLCV data
    validator = OHLCVValidator()
    issues = validator.validate(ohlcv_data)
    if validator.has_errors():
        print("❌ OHLCV validation errors found!")
        for error in validator.get_errors():
            print(f"  {error.message}")
        return
    
    print("✅ OHLCV data validation passed")
    
    # Calculate PLdots
    pldots = PLDot.calculate_from_ohlcv(ohlcv_data)
    print(f"📊 Calculated {len(pldots)} PLdot values")
    
    # Calculate envelopes
    envelopes = []
    for pldot in pldots:
        envelope = EnvelopeBands.calculate_percentage_based(pldot, Decimal('0.02'))
        envelopes.append(envelope)
    print(f"📈 Generated {len(envelopes)} envelope bands")
    
    # Calculate Drummond Lines
    drummond_lines = DrummondLines(timeframe="1h")
    
    # Add some sample lines
    if len(ohlcv_data) >= 2:
        line1 = DrummondLine.calculate_five_nine_up(ohlcv_data[-2], ohlcv_data[-1])
        drummond_lines.add_line(line1)
        print(f"📉 Added Drummond Line: {line1.line_type.value}")
    
    drummond_lines.calculate_zones()
    print(f"🎯 Generated {len(drummond_lines.support_zones)} support zones, "
          f"{len(drummond_lines.resistance_zones)} resistance zones")
    
    # Classify market states
    market_states = MarketStateClassification.classify_from_data(ohlcv_data, pldots)
    current_state = market_states[-1] if market_states else None
    if current_state:
        print(f"📋 Current market state: {current_state.current_state.value} "
              f"(confidence: {current_state.confidence:.1%})")
    
    # Identify patterns
    patterns = []
    
    # PLdot Push pattern
    push_pattern = PLDotPushPattern(PatternMetadata(
        pattern_type="pldot_push",
        timeframe="1h",
        strength=Decimal('0.8'),
        reliability=Decimal('0.9')
    ))
    if push_pattern.identify_pattern(ohlcv_data, pldots, envelopes):
        patterns.append(push_pattern)
        print("🚀 PLdot Push pattern detected!")
    
    # PLdot Refresh pattern
    refresh_pattern = PLDotRefreshPattern(PatternMetadata(
        pattern_type="pldot_refresh",
        timeframe="1h",
        strength=Decimal('0.7'),
        reliability=Decimal('0.8')
    ))
    if refresh_pattern.identify_pattern(ohlcv_data, pldots, envelopes):
        patterns.append(refresh_pattern)
        print("🔄 PLdot Refresh pattern detected!")
    
    # Generate signals
    signals = []
    
    if push_pattern.is_active:
        entry_signals = push_pattern.get_entry_signals()
        for signal_data in entry_signals:
            signal = Signal(
                signal_type=SignalType.BUY if signal_data["direction"] == "long" else SignalType.SELL,
                timestamp=datetime.now(timezone.utc),
                symbol="EURUSD",
                price=ohlcv_data[-1].close,
                confidence=signal_data["confidence"],
                strength=Signal._determine_strength(signal_data["confidence"]),
                triggering_pattern="pldot_push",
                timeframe="1h",
                notes=f"PLdot Push: {signal_data['break_count']} consecutive breaks"
            )
            signals.append(signal)
    
    print(f"💡 Generated {len(signals)} trading signals")
    
    # Create timeframe data container
    tf_data = TimeframeData(
        timeframe="1h",
        ohlcv_data=ohlcv_data,
        pldots=pldots,
        envelopes=envelopes,
        drummond_lines=drummond_lines,
        market_states=market_states,
        patterns=patterns,
        signals=signals
    )
    
    # Multi-timeframe analysis (simplified - single timeframe)
    mtf_analysis = MultiTimeframeAnalysis(
        symbol="EURUSD",
        timeframes={"1h": tf_data},
        analysis_timestamp=datetime.now(timezone.utc)
    )
    
    print(f"🎯 Identified {len(mtf_analysis.confluence_zones)} confluence zones")
    print(f"📈 Market bias: {mtf_analysis.get_market_bias()}")
    
    # Generate comprehensive signals
    coordinated_signals = mtf_analysis.generate_coordinated_signals()
    print(f"🎪 Generated {len(coordinated_signals)} coordinated signals")
    
    # Display highest confidence signals
    top_signals = mtf_analysis.get_highest_confidence_signals(limit=3)
    print("\n🏆 Top Trading Signals:")
    for i, signal in enumerate(top_signals, 1):
        print(f"{i}. {signal.signal_type.value.upper()} at {signal.price} "
              f"(confidence: {signal.confidence:.1%}, strength: {signal.strength.value})")
        if signal.stop_loss:
            print(f"   Stop Loss: {signal.stop_loss}")
        if signal.take_profit:
            print(f"   Take Profit: {signal.take_profit}")
        if signal.confluence_score > 0:
            print(f"   Confluence Score: {signal.confluence_score:.1%}")
    
    return mtf_analysis

def generate_sample_ohlcv_data(symbol: str, bars: int) -> List[OHLCV]:
    """Generate sample OHLCV data for testing."""
    import random
    
    ohlcv_data = []
    base_price = Decimal('1.1000')  # Starting price for EURUSD
    current_time = datetime.now(timezone.utc) - timedelta(hours=bars)
    
    for i in range(bars):
        # Generate realistic price movement
        price_change = Decimal(str(random.uniform(-0.01, 0.01)))  # ±1% max change
        current_price = base_price + price_change * i * Decimal('0.1')
        
        # Calculate OHLC
        volatility = Decimal('0.002')  # 0.2% volatility
        high = current_price + volatility * Decimal(str(random.random()))
        low = current_price - volatility * Decimal(str(random.random()))
        open_price = current_price + (Decimal(str(random.random())) - Decimal('0.5')) * volatility
        close_price = current_price + (Decimal(str(random.random())) - Decimal('0.5')) * volatility
        
        # Ensure OHLC relationships are maintained
        high = max(high, open_price, close_price)
        low = min(low, open_price, close_price)
        
        bar = OHLCV(
            timestamp=current_time + timedelta(hours=i),
            open=open_price,
            high=high,
            low=low,
            close=close_price,
            volume=Decimal(str(random.randint(1000, 10000))),
            symbol=symbol,
            timeframe="1h"
        )
        
        ohlcv_data.append(bar)
    
    return ohlcv_data

# Example usage
if __name__ == "__main__":
    print("🔍 Drummond Geometry Analysis Example")
    print("=" * 50)
    
    try:
        analysis = example_drummond_analysis()
        print("\n✅ Analysis completed successfully!")
        
        # Run comprehensive validation
        validator = ComprehensiveValidator()
        issues = validator.validate_analysis(analysis)
        report = validator.generate_validation_report(issues)
        print(f"\n{report}")
        
    except Exception as e:
        print(f"\n❌ Analysis failed: {e}")
        import traceback
        traceback.print_exc()
```

### 6.2 Performance Considerations

```python
from typing import List, Optional, Dict, Any
from decimal import Decimal
from dataclasses import dataclass
from collections import defaultdict

@dataclass
class PerformanceMetrics:
    """Performance metrics for Drummond Geometry calculations."""
    calculation_time_ms: float
    memory_usage_mb: float
    data_points_processed: int
    cache_hits: int
    cache_misses: int
    validation_errors: int
    validation_warnings: int
    
    @property
    def cache_hit_rate(self) -> float:
        """Calculate cache hit rate percentage."""
        total_requests = self.cache_hits + self.cache_misses
        return (self.cache_hits / total_requests * 100) if total_requests > 0 else 0
    
    @property
    def throughput_per_second(self) -> float:
        """Calculate data points processed per second."""
        return self.data_points_processed / (self.calculation_time_ms / 1000) if self.calculation_time_ms > 0 else 0

class OptimizedPLDot:
    """
    Optimized PLdot calculation with caching and vectorization.
    
    For production use with large datasets.
    """
    
    def __init__(self, cache_size: int = 1000):
        self.cache: Dict[tuple, Decimal] = {}
        self.cache_size = cache_size
        self.metrics = PerformanceMetrics(
            calculation_time_ms=0,
            memory_usage_mb=0,
            data_points_processed=0,
            cache_hits=0,
            cache_misses=0,
            validation_errors=0,
            validation_warnings=0
        )
    
    def calculate_batch(self, ohlcv_data: List[OHLCV], 
                       batch_size: int = 100) -> List[PLDot]:
        """Calculate PLdots in batches for better performance."""
        import time
        
        start_time = time.perf_counter()
        pldots = []
        
        # Process in batches
        for i in range(2, len(ohlcv_data), batch_size):
            batch_end = min(i + batch_size, len(ohlcv_data))
            batch_pldots = self._calculate_batch_pldots(ohlcv_data[i-2:batch_end])
            pldots.extend(batch_pldots)
            
            # Update metrics
            self.metrics.data_points_processed += len(batch_pldots)
        
        # Calculate total time
        end_time = time.perf_counter()
        self.metrics.calculation_time_ms = (end_time - start_time) * 1000
        
        return pldots
    
    def _calculate_batch_pldots(self, ohlcv_batch: List[OHLCV]) -> List[PLDot]:
        """Calculate PLdots for a single batch."""
        pldots = []
        
        for i in range(2, len(ohlcv_batch)):
            # Check cache first
            cache_key = self._get_cache_key(ohlcv_batch, i)
            if cache_key in self.cache:
                self.metrics.cache_hits += 1
                pldot = self.cache[cache_key]
            else:
                self.metrics.cache_misses += 1
                pldot = self._calculate_single_pldot(ohlcv_batch, i)
                
                # Add to cache
                self._add_to_cache(cache_key, pldot)
            
            pldots.append(pldot)
        
        return pldots
    
    def _get_cache_key(self, ohlcv_data: List[OHLCV], index: int) -> tuple:
        """Generate cache key for PLdot calculation."""
        # Use a tuple of OHLCV values as cache key
        bar1 = ohlcv_data[index - 2]
        bar2 = ohlcv_data[index - 1]
        bar3 = ohlcv_data[index]
        
        return (
            float(bar1.high), float(bar1.low), float(bar1.close),
            float(bar2.high), float(bar2.low), float(bar2.close),
            float(bar3.high), float(bar3.low), float(bar3.close)
        )
    
    def _calculate_single_pldot(self, ohlcv_data: List[OHLCV], index: int) -> PLDot:
        """Calculate a single PLdot value."""
        if index < 2:
            raise InsufficientDataError("Need at least 3 bars for PLdot calculation")
        
        # Calculate averages for last 3 bars
        bar_averages = []
        for i in range(index - 2, index + 1):
            bar = ohlcv_data[i]
            avg = (bar.high + bar.low + bar.close) / 3
            bar_averages.append(avg)
        
        # Average the three bar averages
        pldot_value = sum(bar_averages) / len(bar_averages)
        
        # Create PLdot
        timestamp = ohlcv_data[index].timestamp
        
        return PLDot(
            timestamp=timestamp,
            value=pldot_value,
            is_projected=True,
            metadata=PLDotMetadata()
        )
    
    def _add_to_cache(self, key: tuple, pldot: PLDot) -> None:
        """Add PLdot to cache with size management."""
        if len(self.cache) >= self.cache_size:
            # Remove oldest entry (simple FIFO)
            oldest_key = next(iter(self.cache))
            del self.cache[oldest_key]
        
        self.cache[key] = pldot
    
    def get_performance_report(self) -> str:
        """Generate performance report."""
        return f"""
📊 Drummond Geometry Performance Report
{'=' * 50}
Calculation Time: {self.metrics.calculation_time_ms:.2f} ms
Data Points: {self.metrics.data_points_processed}
Cache Hit Rate: {self.metrics.cache_hit_rate:.1f}%
Throughput: {self.metrics.throughput_per_second:.0f} points/second
Cache Size: {len(self.cache)} / {self.cache_size}
Validation Errors: {self.metrics.validation_errors}
Validation Warnings: {self.metrics.validation_warnings}
"""

# Memory-efficient data structures
class MemoryEfficientTimeSeries:
    """Memory-efficient time series for large datasets."""
    
    def __init__(self, max_size: int = 10000):
        self.max_size = max_size
        self.timestamps: List[datetime] = []
        self.values: List[Decimal] = []
        self.metadata: List[Dict[str, Any]] = []
    
    def append(self, timestamp: datetime, value: Decimal, metadata: Optional[Dict[str, Any]] = None) -> None:
        """Append new data point, removing oldest if at capacity."""
        if len(self.timestamps) >= self.max_size:
            # Remove oldest data point
            self.timestamps.pop(0)
            self.values.pop(0)
            if self.metadata:
                self.metadata.pop(0)
        
        self.timestamps.append(timestamp)
        self.values.append(value)
        if metadata:
            self.metadata.append(metadata)
        else:
            self.metadata.append({})
    
    def get_recent(self, count: int) -> List[tuple]:
        """Get recent data points."""
        start_index = max(0, len(self.timestamps) - count)
        return [
            (self.timestamps[i], self.values[i], self.metadata[i])
            for i in range(start_index, len(self.timestamps))
        ]
    
    @property
    def size(self) -> int:
        """Get current size."""
        return len(self.timestamps)
    
    @property
    def is_full(self) -> bool:
        """Check if time series is at capacity."""
        return len(self.timestamps) >= self.max_size
```

---

## 7. Conclusion

This comprehensive Python data model specification provides a robust foundation for implementing Drummond Geometry analysis tools. The design emphasizes:

### 7.1 Key Features

- **Type Safety**: Complete type annotations and dataclasses ensure code reliability
- **Mathematical Accuracy**: Precise calculations using Decimal for financial data
- **Forward-Looking Analysis**: Projected indicators that anticipate market behavior
- **Multi-Timeframe Coordination**: Sophisticated framework for timeframe alignment
- **Pattern Recognition**: Classes for identifying key Drummond Geometry patterns
- **Signal Generation**: Comprehensive signal system with confidence levels
- **Validation Framework**: Robust error checking and data integrity verification
- **Performance Optimization**: Caching and batch processing for production use

### 7.2 Implementation Guidelines

1. **Data Validation**: Always validate OHLCV data before calculations
2. **Error Handling**: Use the comprehensive error handling framework
3. **Performance**: Consider memory usage for large datasets
4. **Testing**: Validate calculations against known good results
5. **Documentation**: Maintain clear documentation of all classes and methods

### 7.3 Extension Points

The models are designed for extensibility:
- Custom pattern recognition classes
- Additional signal types
- Alternative calculation methods
- Enhanced validation rules
- Performance optimizations
- Integration with external data sources

This specification provides the technical foundation needed to build sophisticated Drummond Geometry analysis tools while maintaining the methodology's core principles of forward-looking analysis, multi-timeframe coordination, and predictive precision.

---

**Document Version**: 1.0  
**Last Updated**: November 3, 2025  
**Authors**: MiniMax Agent  
**License**: MIT License