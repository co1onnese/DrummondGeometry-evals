"""Tests for multi-timeframe coordination."""

from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from dgas.calculations.envelopes import EnvelopeSeries
from dgas.calculations.multi_timeframe import (
    ConfluenceZone,
    MultiTimeframeCoordinator,
    PLDotOverlay,
    TimeframeAlignment,
    TimeframeData,
    TimeframeType,
)
from dgas.calculations.patterns import PatternEvent, PatternType
from dgas.calculations.pldot import PLDotSeries
from dgas.calculations.states import MarketState, StateSeries, TrendDirection


def create_pldot_series(
    base_value: float, slope: float, count: int, start_time: datetime
) -> list[PLDotSeries]:
    """Helper to create PLdot series with consistent slope."""
    series = []
    for i in range(count):
        current_value = base_value + slope * i
        projected_value = base_value + slope * (i + 1)
        series.append(
            PLDotSeries(
                timestamp=start_time + timedelta(hours=i),
                value=Decimal(str(current_value)),
                projected_timestamp=start_time + timedelta(hours=i + 1),
                projected_value=Decimal(str(projected_value)),
                slope=Decimal(str(slope)),
                displacement=1,
            )
        )
    return series


def create_envelope_series(
    pldot_series: list[PLDotSeries], width: float
) -> list[EnvelopeSeries]:
    """Helper to create envelope series from PLdot."""
    envelopes = []
    for pldot in pldot_series:
        center = pldot.value
        half_width = Decimal(str(width / 2))
        envelopes.append(
            EnvelopeSeries(
                timestamp=pldot.timestamp,
                center=center,
                upper=center + half_width,
                lower=center - half_width,
                width=Decimal(str(width)),
                position=Decimal("0.5"),
                method="pldot_range",
            )
        )
    return envelopes


def create_state_series(
    timestamps: list[datetime],
    state: MarketState,
    direction: TrendDirection,
    confidence: float = 0.7,
) -> list[StateSeries]:
    """Helper to create state series."""
    series = []
    for i, ts in enumerate(timestamps):
        series.append(
            StateSeries(
                timestamp=ts,
                state=state,
                trend_direction=direction,
                bars_in_state=i + 1,
                previous_state=None if i == 0 else state,
                pldot_slope_trend="rising" if direction == TrendDirection.UP else "falling",
                confidence=Decimal(str(confidence)),
                state_change_reason=None,
            )
        )
    return series


class TestMultiTimeframeCoordinator:
    """Test suite for multi-timeframe coordination."""

    def test_basic_initialization(self):
        """Test coordinator initialization."""
        coordinator = MultiTimeframeCoordinator(
            htf_timeframe="4h",
            trading_timeframe="1h",
            ltf_timeframe="15m",
        )

        assert coordinator.htf_timeframe == "4h"
        assert coordinator.trading_timeframe == "1h"
        assert coordinator.ltf_timeframe == "15m"
        assert coordinator.confluence_tolerance_pct == 0.5
        assert coordinator.alignment_threshold == 0.6

    def test_aligned_uptrend_analysis(self):
        """Test analysis when HTF and trading TF both in uptrend."""
        start_time = datetime(2025, 1, 1, 0, 0)

        # HTF: Strong uptrend
        htf_pldot = create_pldot_series(100.0, 0.5, 10, start_time)
        htf_envelopes = create_envelope_series(htf_pldot, 2.0)
        htf_states = create_state_series(
            [p.timestamp for p in htf_pldot],
            MarketState.TREND,
            TrendDirection.UP,
            confidence=0.8,
        )

        htf_data = TimeframeData(
            timeframe="4h",
            classification=TimeframeType.HIGHER,
            pldot_series=htf_pldot,
            envelope_series=htf_envelopes,
            state_series=htf_states,
            pattern_events=[],
        )

        # Trading TF: Also uptrend
        trading_pldot = create_pldot_series(100.0, 0.3, 10, start_time)
        trading_envelopes = create_envelope_series(trading_pldot, 1.5)
        trading_states = create_state_series(
            [p.timestamp for p in trading_pldot],
            MarketState.TREND,
            TrendDirection.UP,
            confidence=0.7,
        )

        trading_data = TimeframeData(
            timeframe="1h",
            classification=TimeframeType.TRADING,
            pldot_series=trading_pldot,
            envelope_series=trading_envelopes,
            state_series=trading_states,
            pattern_events=[],
        )

        coordinator = MultiTimeframeCoordinator("4h", "1h")
        analysis = coordinator.analyze(htf_data, trading_data)

        # Verify alignment
        assert analysis.htf_trend == TrendDirection.UP
        assert analysis.trading_tf_trend == TrendDirection.UP
        assert analysis.alignment.trade_permitted is True
        assert analysis.alignment.alignment_score >= Decimal("0.6")

        # Should recommend long
        assert analysis.recommended_action == "long"
        assert analysis.risk_level in ["low", "medium"]

    def test_conflicting_trends(self):
        """Test analysis when HTF and trading TF have opposite trends."""
        start_time = datetime(2025, 1, 1, 0, 0)

        # HTF: Downtrend
        htf_pldot = create_pldot_series(100.0, -0.5, 10, start_time)
        htf_envelopes = create_envelope_series(htf_pldot, 2.0)
        htf_states = create_state_series(
            [p.timestamp for p in htf_pldot],
            MarketState.TREND,
            TrendDirection.DOWN,
            confidence=0.8,
        )

        htf_data = TimeframeData(
            timeframe="4h",
            classification=TimeframeType.HIGHER,
            pldot_series=htf_pldot,
            envelope_series=htf_envelopes,
            state_series=htf_states,
            pattern_events=[],
        )

        # Trading TF: Uptrend (counter-trend)
        trading_pldot = create_pldot_series(100.0, 0.3, 10, start_time)
        trading_envelopes = create_envelope_series(trading_pldot, 1.5)
        trading_states = create_state_series(
            [p.timestamp for p in trading_pldot],
            MarketState.TREND,
            TrendDirection.UP,
            confidence=0.6,
        )

        trading_data = TimeframeData(
            timeframe="1h",
            classification=TimeframeType.TRADING,
            pldot_series=trading_pldot,
            envelope_series=trading_envelopes,
            state_series=trading_states,
            pattern_events=[],
        )

        coordinator = MultiTimeframeCoordinator("4h", "1h")
        analysis = coordinator.analyze(htf_data, trading_data)

        # Should NOT permit trading against HTF trend
        assert analysis.htf_trend == TrendDirection.DOWN
        assert analysis.trading_tf_trend == TrendDirection.UP
        assert analysis.alignment.trade_permitted is False
        assert analysis.recommended_action in ["wait", "reduce"]

    def test_pldot_overlay(self):
        """Test PLdot overlay calculation."""
        start_time = datetime(2025, 1, 1, 0, 0)

        # HTF PLdot at 100
        htf_pldot = create_pldot_series(100.0, 0.1, 5, start_time)
        htf_envelopes = create_envelope_series(htf_pldot, 2.0)
        htf_states = create_state_series(
            [p.timestamp for p in htf_pldot],
            MarketState.TREND,
            TrendDirection.UP,
        )

        htf_data = TimeframeData(
            timeframe="4h",
            classification=TimeframeType.HIGHER,
            pldot_series=htf_pldot,
            envelope_series=htf_envelopes,
            state_series=htf_states,
            pattern_events=[],
        )

        # Trading TF PLdot at 102 (above HTF)
        trading_pldot = create_pldot_series(102.0, 0.05, 5, start_time)
        trading_envelopes = create_envelope_series(trading_pldot, 1.5)
        trading_states = create_state_series(
            [p.timestamp for p in trading_pldot],
            MarketState.TREND,
            TrendDirection.UP,
        )

        trading_data = TimeframeData(
            timeframe="1h",
            classification=TimeframeType.TRADING,
            pldot_series=trading_pldot,
            envelope_series=trading_envelopes,
            state_series=trading_states,
            pattern_events=[],
        )

        coordinator = MultiTimeframeCoordinator("4h", "1h")
        analysis = coordinator.analyze(htf_data, trading_data)

        overlay = analysis.pldot_overlay

        # Verify overlay calculation
        # Note: values will be at the latest common timestamp
        assert overlay.htf_pldot_value >= Decimal("100.0")
        assert overlay.ltf_pldot_value >= Decimal("102.0")
        assert overlay.position == "above_htf"
        assert overlay.distance_percent > Decimal("1.0")  # Should be ~2% apart

    def test_confluence_zone_detection(self):
        """Test detection of price levels confirmed by multiple timeframes."""
        start_time = datetime(2025, 1, 1, 0, 0)

        # HTF with support at ~100
        htf_pldot = create_pldot_series(100.0, 0.1, 5, start_time)
        htf_envelopes = create_envelope_series(htf_pldot, 4.0)  # Lower band at 98
        htf_states = create_state_series(
            [p.timestamp for p in htf_pldot],
            MarketState.TREND,
            TrendDirection.UP,
        )

        htf_data = TimeframeData(
            timeframe="4h",
            classification=TimeframeType.HIGHER,
            pldot_series=htf_pldot,
            envelope_series=htf_envelopes,
            state_series=htf_states,
            pattern_events=[],
        )

        # Trading TF also with support at ~100
        trading_pldot = create_pldot_series(100.2, 0.05, 5, start_time)
        trading_envelopes = create_envelope_series(trading_pldot, 3.0)  # Lower band at 98.7
        trading_states = create_state_series(
            [p.timestamp for p in trading_pldot],
            MarketState.TREND,
            TrendDirection.UP,
        )

        trading_data = TimeframeData(
            timeframe="1h",
            classification=TimeframeType.TRADING,
            pldot_series=trading_pldot,
            envelope_series=trading_envelopes,
            state_series=trading_states,
            pattern_events=[],
        )

        coordinator = MultiTimeframeCoordinator("4h", "1h", confluence_tolerance_pct=2.0)
        analysis = coordinator.analyze(htf_data, trading_data)

        # Should detect confluence zones
        assert len(analysis.confluence_zones) > 0

        # Check for support confluence near 98-99
        support_zones = [z for z in analysis.confluence_zones if z.zone_type == "support"]
        assert len(support_zones) > 0

        # Strongest zone should have 2+ timeframes
        strongest = analysis.confluence_zones[0]
        assert strongest.strength >= 2

    def test_pattern_confluence(self):
        """Test pattern alignment across timeframes."""
        start_time = datetime(2025, 1, 1, 0, 0)

        # HTF with PLdot push pattern
        htf_pldot = create_pldot_series(100.0, 0.5, 10, start_time)
        htf_envelopes = create_envelope_series(htf_pldot, 2.0)
        htf_states = create_state_series(
            [p.timestamp for p in htf_pldot],
            MarketState.TREND,
            TrendDirection.UP,
        )

        htf_pattern = PatternEvent(
            pattern_type=PatternType.PLDOT_PUSH,
            direction=1,
            start_timestamp=start_time,
            end_timestamp=start_time + timedelta(hours=5),
            strength=5,
        )

        htf_data = TimeframeData(
            timeframe="4h",
            classification=TimeframeType.HIGHER,
            pldot_series=htf_pldot,
            envelope_series=htf_envelopes,
            state_series=htf_states,
            pattern_events=[htf_pattern],
        )

        # Trading TF with same pattern type and direction
        trading_pldot = create_pldot_series(100.0, 0.3, 10, start_time)
        trading_envelopes = create_envelope_series(trading_pldot, 1.5)
        trading_states = create_state_series(
            [p.timestamp for p in trading_pldot],
            MarketState.TREND,
            TrendDirection.UP,
        )

        trading_pattern = PatternEvent(
            pattern_type=PatternType.PLDOT_PUSH,
            direction=1,
            start_timestamp=start_time + timedelta(hours=1),
            end_timestamp=start_time + timedelta(hours=6),
            strength=4,
        )

        trading_data = TimeframeData(
            timeframe="1h",
            classification=TimeframeType.TRADING,
            pldot_series=trading_pldot,
            envelope_series=trading_envelopes,
            state_series=trading_states,
            pattern_events=[trading_pattern],
        )

        coordinator = MultiTimeframeCoordinator("4h", "1h")
        analysis = coordinator.analyze(htf_data, trading_data)

        # Should detect pattern confluence
        assert analysis.pattern_confluence is True

        # Signal strength should be boosted
        assert analysis.signal_strength >= Decimal("0.6")

    def test_congestion_state_handling(self):
        """Test handling of congestion states."""
        start_time = datetime(2025, 1, 1, 0, 0)

        # HTF in congestion
        htf_pldot = create_pldot_series(100.0, 0.01, 10, start_time)  # Nearly flat
        htf_envelopes = create_envelope_series(htf_pldot, 2.0)
        htf_states = create_state_series(
            [p.timestamp for p in htf_pldot],
            MarketState.CONGESTION_ACTION,
            TrendDirection.NEUTRAL,
        )

        htf_data = TimeframeData(
            timeframe="4h",
            classification=TimeframeType.HIGHER,
            pldot_series=htf_pldot,
            envelope_series=htf_envelopes,
            state_series=htf_states,
            pattern_events=[],
        )

        # Trading TF trying to trend
        trading_pldot = create_pldot_series(100.0, 0.2, 10, start_time)
        trading_envelopes = create_envelope_series(trading_pldot, 1.5)
        trading_states = create_state_series(
            [p.timestamp for p in trading_pldot],
            MarketState.TREND,
            TrendDirection.UP,
        )

        trading_data = TimeframeData(
            timeframe="1h",
            classification=TimeframeType.TRADING,
            pldot_series=trading_pldot,
            envelope_series=trading_envelopes,
            state_series=trading_states,
            pattern_events=[],
        )

        coordinator = MultiTimeframeCoordinator("4h", "1h")
        analysis = coordinator.analyze(htf_data, trading_data)

        # HTF neutral should allow trading but with caution
        # Signal should be moderate, not strong
        assert analysis.signal_strength < Decimal("0.8")

        # May permit trading but with higher risk
        if analysis.alignment.trade_permitted:
            assert analysis.risk_level in ["medium", "high"]

    def test_signal_strength_components(self):
        """Test that signal strength calculation uses all components."""
        start_time = datetime(2025, 1, 1, 0, 0)

        # Perfect alignment scenario
        htf_pldot = create_pldot_series(100.0, 0.5, 10, start_time)
        htf_envelopes = create_envelope_series(htf_pldot, 2.0)
        htf_states = create_state_series(
            [p.timestamp for p in htf_pldot],
            MarketState.TREND,
            TrendDirection.UP,
            confidence=0.9,
        )

        htf_pattern = PatternEvent(
            pattern_type=PatternType.PLDOT_PUSH,
            direction=1,
            start_timestamp=start_time,
            end_timestamp=start_time + timedelta(hours=5),
            strength=5,
        )

        htf_data = TimeframeData(
            timeframe="4h",
            classification=TimeframeType.HIGHER,
            pldot_series=htf_pldot,
            envelope_series=htf_envelopes,
            state_series=htf_states,
            pattern_events=[htf_pattern],
        )

        trading_pldot = create_pldot_series(100.0, 0.5, 10, start_time)
        trading_envelopes = create_envelope_series(trading_pldot, 2.0)
        trading_states = create_state_series(
            [p.timestamp for p in trading_pldot],
            MarketState.TREND,
            TrendDirection.UP,
            confidence=0.9,
        )

        trading_pattern = PatternEvent(
            pattern_type=PatternType.PLDOT_PUSH,
            direction=1,
            start_timestamp=start_time,
            end_timestamp=start_time + timedelta(hours=5),
            strength=5,
        )

        trading_data = TimeframeData(
            timeframe="1h",
            classification=TimeframeType.TRADING,
            pldot_series=trading_pldot,
            envelope_series=trading_envelopes,
            state_series=trading_states,
            pattern_events=[trading_pattern],
        )

        coordinator = MultiTimeframeCoordinator("4h", "1h")
        analysis = coordinator.analyze(htf_data, trading_data)

        # Perfect alignment should have high signal strength
        assert analysis.signal_strength >= Decimal("0.7")
        assert analysis.alignment.alignment_type == "perfect"
        assert analysis.recommended_action == "long"
        assert analysis.risk_level == "low"

    def test_empty_data_handling(self):
        """Test handling of empty or minimal data."""
        start_time = datetime(2025, 1, 1, 0, 0)

        # Minimal HTF data
        htf_pldot = create_pldot_series(100.0, 0.1, 1, start_time)
        htf_envelopes = create_envelope_series(htf_pldot, 2.0)
        htf_states = create_state_series(
            [p.timestamp for p in htf_pldot],
            MarketState.CONGESTION_ACTION,
            TrendDirection.NEUTRAL,
        )

        htf_data = TimeframeData(
            timeframe="4h",
            classification=TimeframeType.HIGHER,
            pldot_series=htf_pldot,
            envelope_series=htf_envelopes,
            state_series=htf_states,
            pattern_events=[],
        )

        # Minimal trading data
        trading_pldot = create_pldot_series(100.0, 0.1, 1, start_time)
        trading_envelopes = create_envelope_series(trading_pldot, 1.5)
        trading_states = create_state_series(
            [p.timestamp for p in trading_pldot],
            MarketState.CONGESTION_ACTION,
            TrendDirection.NEUTRAL,
        )

        trading_data = TimeframeData(
            timeframe="1h",
            classification=TimeframeType.TRADING,
            pldot_series=trading_pldot,
            envelope_series=trading_envelopes,
            state_series=trading_states,
            pattern_events=[],
        )

        coordinator = MultiTimeframeCoordinator("4h", "1h")
        analysis = coordinator.analyze(htf_data, trading_data)

        # Should not crash, should return cautious recommendation
        assert analysis.recommended_action == "wait"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
