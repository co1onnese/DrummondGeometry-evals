"""Tests for prediction engine (signal generation and aggregation)."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from dgas.calculations.envelopes import EnvelopeSeries
from dgas.calculations.multi_timeframe import (
    ConfluenceZone,
    MultiTimeframeAnalysis,
    MultiTimeframeCoordinator,
    PLDotOverlay,
    TimeframeAlignment,
    TimeframeData,
    TimeframeType,
)
from dgas.calculations.patterns import PatternEvent, PatternType
from dgas.calculations.pldot import PLDotSeries
from dgas.calculations.states import MarketState, StateSeries, TrendDirection
from dgas.prediction.engine import (
    GeneratedSignal,
    SignalAggregator,
    SignalGenerator,
    SignalType,
)


class TestSignalGenerator:
    """Test SignalGenerator class."""

    def test_generate_signals_long_entry(self, sample_long_analysis, sample_timeframe_data):
        """Test generation of LONG signal."""
        coordinator = MultiTimeframeCoordinator("4h", "1h")
        generator = SignalGenerator(coordinator, min_alignment_score=0.6, min_signal_strength=0.5)

        # Mock the coordinator.analyze to return our sample analysis
        def mock_analyze(htf_data, trading_tf_data, ltf_data=None):
            return sample_long_analysis

        coordinator.analyze = mock_analyze

        htf_data, trading_data = sample_timeframe_data
        signals = generator.generate_signals("AAPL", htf_data, trading_data)

        assert len(signals) == 1
        signal = signals[0]

        assert signal.symbol == "AAPL"
        assert signal.signal_type == SignalType.LONG
        assert signal.entry_price > Decimal("0")
        assert signal.stop_loss < signal.entry_price  # Stop below entry for long
        assert signal.target_price > signal.entry_price  # Target above entry
        assert 0.0 < signal.confidence <= 1.0
        assert 0.0 < signal.signal_strength <= 1.0
        assert signal.htf_trend == TrendDirection.UP

    def test_generate_signals_short_entry(self, sample_short_analysis, sample_timeframe_data):
        """Test generation of SHORT signal."""
        coordinator = MultiTimeframeCoordinator("4h", "1h")
        generator = SignalGenerator(coordinator, min_alignment_score=0.6, min_signal_strength=0.5)

        def mock_analyze(htf_data, trading_tf_data, ltf_data=None):
            return sample_short_analysis

        coordinator.analyze = mock_analyze

        htf_data, trading_data = sample_timeframe_data
        signals = generator.generate_signals("AAPL", htf_data, trading_data)

        assert len(signals) == 1
        signal = signals[0]

        assert signal.signal_type == SignalType.SHORT
        assert signal.stop_loss > signal.entry_price  # Stop above entry for short
        assert signal.target_price < signal.entry_price  # Target below entry
        assert signal.htf_trend == TrendDirection.DOWN

    def test_generate_signals_below_alignment_threshold(self, sample_long_analysis, sample_timeframe_data):
        """Test that no signal generated when alignment below threshold."""
        coordinator = MultiTimeframeCoordinator("4h", "1h")
        generator = SignalGenerator(coordinator, min_alignment_score=0.9, min_signal_strength=0.5)

        def mock_analyze(htf_data, trading_tf_data, ltf_data=None):
            return sample_long_analysis  # Has alignment_score = 0.75

        coordinator.analyze = mock_analyze

        htf_data, trading_data = sample_timeframe_data
        signals = generator.generate_signals("AAPL", htf_data, trading_data)

        assert len(signals) == 0  # No signal due to low alignment

    def test_generate_signals_below_signal_strength_threshold(self, sample_long_analysis, sample_timeframe_data):
        """Test that no signal generated when signal strength below threshold."""
        coordinator = MultiTimeframeCoordinator("4h", "1h")
        generator = SignalGenerator(coordinator, min_alignment_score=0.6, min_signal_strength=0.9)

        def mock_analyze(htf_data, trading_tf_data, ltf_data=None):
            return sample_long_analysis  # Has signal_strength = 0.70

        coordinator.analyze = mock_analyze

        htf_data, trading_data = sample_timeframe_data
        signals = generator.generate_signals("AAPL", htf_data, trading_data)

        assert len(signals) == 0  # No signal due to low signal strength

    def test_generate_signals_trade_not_permitted(self, sample_long_analysis, sample_timeframe_data):
        """Test that no signal generated when trade not permitted by HTF."""
        coordinator = MultiTimeframeCoordinator("4h", "1h")
        generator = SignalGenerator(coordinator)

        # Modify analysis to have trade_permitted = False
        modified_alignment = TimeframeAlignment(
            timestamp=sample_long_analysis.alignment.timestamp,
            htf_state=sample_long_analysis.alignment.htf_state,
            htf_direction=sample_long_analysis.alignment.htf_direction,
            htf_confidence=sample_long_analysis.alignment.htf_confidence,
            trading_tf_state=sample_long_analysis.alignment.trading_tf_state,
            trading_tf_direction=sample_long_analysis.alignment.trading_tf_direction,
            trading_tf_confidence=sample_long_analysis.alignment.trading_tf_confidence,
            alignment_score=sample_long_analysis.alignment.alignment_score,
            alignment_type=sample_long_analysis.alignment.alignment_type,
            trade_permitted=False,  # KEY: Trade not permitted
        )

        modified_analysis = MultiTimeframeAnalysis(
            timestamp=sample_long_analysis.timestamp,
            htf_timeframe=sample_long_analysis.htf_timeframe,
            trading_timeframe=sample_long_analysis.trading_timeframe,
            ltf_timeframe=sample_long_analysis.ltf_timeframe,
            htf_trend=sample_long_analysis.htf_trend,
            htf_trend_strength=sample_long_analysis.htf_trend_strength,
            trading_tf_trend=sample_long_analysis.trading_tf_trend,
            alignment=modified_alignment,
            pldot_overlay=sample_long_analysis.pldot_overlay,
            confluence_zones=sample_long_analysis.confluence_zones,
            htf_patterns=sample_long_analysis.htf_patterns,
            trading_tf_patterns=sample_long_analysis.trading_tf_patterns,
            pattern_confluence=sample_long_analysis.pattern_confluence,
            signal_strength=sample_long_analysis.signal_strength,
            risk_level=sample_long_analysis.risk_level,
            recommended_action=sample_long_analysis.recommended_action,
        )

        def mock_analyze(htf_data, trading_tf_data, ltf_data=None):
            return modified_analysis

        coordinator.analyze = mock_analyze

        htf_data, trading_data = sample_timeframe_data
        signals = generator.generate_signals("AAPL", htf_data, trading_data)

        assert len(signals) == 0  # No signal when trade not permitted

    def test_generate_signals_requires_zone_weight(self, sample_long_analysis, sample_timeframe_data):
        coordinator = MultiTimeframeCoordinator("4h", "1h")
        generator = SignalGenerator(coordinator)

        weak_zone = replace(
            sample_long_analysis.confluence_zones[0],
            weighted_strength=Decimal("1.0"),
        )
        analysis = replace(sample_long_analysis, confluence_zones=[weak_zone])

        coordinator.analyze = lambda *_args, **_kwargs: analysis
        htf_data, trading_data = sample_timeframe_data

        signals = generator.generate_signals("AAPL", htf_data, trading_data)
        assert signals == []

    def test_generate_signals_exit_on_reduce(self, sample_long_analysis, sample_timeframe_data):
        coordinator = MultiTimeframeCoordinator("4h", "1h")
        generator = SignalGenerator(coordinator)

        exit_analysis = replace(sample_long_analysis, recommended_action="reduce")
        coordinator.analyze = lambda *_args, **_kwargs: exit_analysis

        htf_data, trading_data = sample_timeframe_data
        signals = generator.generate_signals("AAPL", htf_data, trading_data)

        assert len(signals) == 1
        assert signals[0].signal_type == SignalType.EXIT_LONG

    def test_generate_signals_requires_pattern_support(self, sample_long_analysis, sample_timeframe_data):
        coordinator = MultiTimeframeCoordinator("4h", "1h")
        generator = SignalGenerator(coordinator)

        analysis = replace(
            sample_long_analysis,
            htf_patterns=[],
            trading_tf_patterns=[],
        )
        coordinator.analyze = lambda *_args, **_kwargs: analysis

        htf_data, trading_data = sample_timeframe_data
        signals = generator.generate_signals("AAPL", htf_data, trading_data)
        assert signals == []

    def test_confidence_calculation_with_all_factors(self, sample_long_analysis, sample_timeframe_data):
        """Test confidence calculation includes all factors."""
        coordinator = MultiTimeframeCoordinator("4h", "1h")
        generator = SignalGenerator(coordinator)

        def mock_analyze(htf_data, trading_tf_data, ltf_data=None):
            return sample_long_analysis

        coordinator.analyze = mock_analyze

        htf_data, trading_data = sample_timeframe_data
        signals = generator.generate_signals("AAPL", htf_data, trading_data)

        signal = signals[0]

        # Confidence should be weighted combination
        # alignment (0.75 * 0.30) + pattern (0.20 if true) + htf_strength (0.80 * 0.25) + zones + signal_strength
        expected_min = 0.225 + 0.20 + 0.20  # Minimum from major components
        expected_max = 1.0

        assert expected_min <= signal.confidence <= expected_max

    def test_risk_reward_ratio_calculation(self, sample_long_analysis, sample_timeframe_data):
        """Test risk/reward ratio is calculated correctly."""
        coordinator = MultiTimeframeCoordinator("4h", "1h")
        generator = SignalGenerator(coordinator, target_rr_ratio=2.0)

        def mock_analyze(htf_data, trading_tf_data, ltf_data=None):
            return sample_long_analysis

        coordinator.analyze = mock_analyze

        htf_data, trading_data = sample_timeframe_data
        signals = generator.generate_signals("AAPL", htf_data, trading_data)

        signal = signals[0]

        # Calculate actual R:R
        risk = abs(signal.entry_price - signal.stop_loss)
        reward = abs(signal.target_price - signal.entry_price)
        actual_rr = float(reward / risk) if risk > 0 else 0.0

        # Should be close to target_rr_ratio (2.0)
        assert abs(signal.risk_reward_ratio - 2.0) < 0.1


class TestExitSignalGeneration:
    """Test exit signal generation from SignalGenerator."""

    def test_generate_exit_signal_on_exhaust_pattern_long(self, sample_long_analysis, sample_timeframe_data):
        """Test exit signal generated when exhaust pattern detected against LONG position."""
        coordinator = MultiTimeframeCoordinator("4h", "1h")
        generator = SignalGenerator(coordinator)

        # Add bearish exhaust pattern to analysis (signals exit from long)
        now = datetime.now(timezone.utc)
        exhaust_pattern = PatternEvent(
            pattern_type=PatternType.EXHAUST,
            direction=-1,  # Bearish exhaust
            start_timestamp=now - timedelta(hours=2),
            end_timestamp=now,
            strength=3,
        )
        
        modified_analysis = replace(
            sample_long_analysis,
            trading_tf_patterns=[exhaust_pattern],
        )

        def mock_analyze(htf_data, trading_tf_data, ltf_data=None):
            return modified_analysis

        coordinator.analyze = mock_analyze

        htf_data, trading_data = sample_timeframe_data
        signals = generator.generate_exit_signals(
            "AAPL", htf_data, trading_data, SignalType.LONG
        )

        assert len(signals) == 1
        signal = signals[0]
        assert signal.signal_type == SignalType.EXIT_LONG
        assert "exhaust_pattern" in signal.pattern_context.get("exit_reasons", [])

    def test_generate_exit_signal_on_exhaust_pattern_short(self, sample_short_analysis, sample_timeframe_data):
        """Test exit signal generated when exhaust pattern detected against SHORT position."""
        coordinator = MultiTimeframeCoordinator("4h", "1h")
        generator = SignalGenerator(coordinator)

        # Add bullish exhaust pattern to analysis (signals exit from short)
        now = datetime.now(timezone.utc)
        exhaust_pattern = PatternEvent(
            pattern_type=PatternType.EXHAUST,
            direction=1,  # Bullish exhaust
            start_timestamp=now - timedelta(hours=2),
            end_timestamp=now,
            strength=3,
        )
        
        modified_analysis = replace(
            sample_short_analysis,
            trading_tf_patterns=[exhaust_pattern],
        )

        def mock_analyze(htf_data, trading_tf_data, ltf_data=None):
            return modified_analysis

        coordinator.analyze = mock_analyze

        htf_data, trading_data = sample_timeframe_data
        signals = generator.generate_exit_signals(
            "AAPL", htf_data, trading_data, SignalType.SHORT
        )

        assert len(signals) == 1
        signal = signals[0]
        assert signal.signal_type == SignalType.EXIT_SHORT
        assert "exhaust_pattern" in signal.pattern_context.get("exit_reasons", [])

    def test_generate_exit_signal_on_htf_trend_reversal(self, sample_long_analysis, sample_timeframe_data):
        """Test exit signal generated when HTF trend reverses against position."""
        coordinator = MultiTimeframeCoordinator("4h", "1h")
        generator = SignalGenerator(coordinator)

        # Modify analysis to have HTF trend DOWN (against LONG position)
        modified_analysis = replace(
            sample_long_analysis,
            htf_trend=TrendDirection.DOWN,
            htf_patterns=[],  # Clear patterns to isolate HTF reversal test
            trading_tf_patterns=[],
        )

        def mock_analyze(htf_data, trading_tf_data, ltf_data=None):
            return modified_analysis

        coordinator.analyze = mock_analyze

        htf_data, trading_data = sample_timeframe_data
        signals = generator.generate_exit_signals(
            "AAPL", htf_data, trading_data, SignalType.LONG
        )

        assert len(signals) == 1
        signal = signals[0]
        assert signal.signal_type == SignalType.EXIT_LONG
        assert "htf_trend_reversal" in signal.pattern_context.get("exit_reasons", [])

    def test_generate_exit_signal_on_termination_touch(self, sample_long_analysis, sample_timeframe_data):
        """Test exit signal generated when termination touch detected against position."""
        coordinator = MultiTimeframeCoordinator("4h", "1h")
        generator = SignalGenerator(coordinator)

        # Add bearish termination touch pattern (signals exit from long)
        now = datetime.now(timezone.utc)
        termination_pattern = PatternEvent(
            pattern_type=PatternType.TERMINATION_TOUCH,
            direction=-1,  # Bearish termination
            start_timestamp=now - timedelta(hours=1),
            end_timestamp=now,
            strength=3,
        )
        
        modified_analysis = replace(
            sample_long_analysis,
            htf_trend=TrendDirection.UP,  # Keep HTF trend aligned to isolate termination test
            htf_patterns=[],
            trading_tf_patterns=[termination_pattern],
        )

        def mock_analyze(htf_data, trading_tf_data, ltf_data=None):
            return modified_analysis

        coordinator.analyze = mock_analyze

        htf_data, trading_data = sample_timeframe_data
        signals = generator.generate_exit_signals(
            "AAPL", htf_data, trading_data, SignalType.LONG
        )

        assert len(signals) == 1
        signal = signals[0]
        assert signal.signal_type == SignalType.EXIT_LONG
        assert "termination_touch" in signal.pattern_context.get("exit_reasons", [])

    def test_no_exit_signal_when_conditions_not_met(self, sample_long_analysis, sample_timeframe_data):
        """Test no exit signal when no exit conditions are met."""
        coordinator = MultiTimeframeCoordinator("4h", "1h")
        generator = SignalGenerator(coordinator)

        # Use sample_long_analysis which has HTF trend UP and no exit patterns
        # Clear patterns to ensure no exit conditions
        modified_analysis = replace(
            sample_long_analysis,
            htf_trend=TrendDirection.UP,
            htf_patterns=[],
            trading_tf_patterns=[],
        )

        def mock_analyze(htf_data, trading_tf_data, ltf_data=None):
            return modified_analysis

        coordinator.analyze = mock_analyze

        htf_data, trading_data = sample_timeframe_data
        signals = generator.generate_exit_signals(
            "AAPL", htf_data, trading_data, SignalType.LONG
        )

        assert len(signals) == 0

    def test_generate_exit_signal_invalid_position_type(self, sample_long_analysis, sample_timeframe_data):
        """Test that invalid position type returns empty list."""
        coordinator = MultiTimeframeCoordinator("4h", "1h")
        generator = SignalGenerator(coordinator)

        def mock_analyze(htf_data, trading_tf_data, ltf_data=None):
            return sample_long_analysis

        coordinator.analyze = mock_analyze

        htf_data, trading_data = sample_timeframe_data
        
        # Try with EXIT_LONG which is not a valid position type
        signals = generator.generate_exit_signals(
            "AAPL", htf_data, trading_data, SignalType.EXIT_LONG
        )

        assert len(signals) == 0

    def test_exit_signal_multiple_reasons(self, sample_long_analysis, sample_timeframe_data):
        """Test exit signal with multiple exit reasons."""
        coordinator = MultiTimeframeCoordinator("4h", "1h")
        generator = SignalGenerator(coordinator)

        # Add both exhaust and termination patterns, plus HTF reversal
        now = datetime.now(timezone.utc)
        exhaust_pattern = PatternEvent(
            pattern_type=PatternType.EXHAUST,
            direction=-1,
            start_timestamp=now - timedelta(hours=2),
            end_timestamp=now,
            strength=3,
        )
        termination_pattern = PatternEvent(
            pattern_type=PatternType.TERMINATION_TOUCH,
            direction=-1,
            start_timestamp=now - timedelta(hours=1),
            end_timestamp=now,
            strength=3,
        )
        
        modified_analysis = replace(
            sample_long_analysis,
            htf_trend=TrendDirection.DOWN,  # HTF reversal
            htf_patterns=[exhaust_pattern],
            trading_tf_patterns=[termination_pattern],
        )

        def mock_analyze(htf_data, trading_tf_data, ltf_data=None):
            return modified_analysis

        coordinator.analyze = mock_analyze

        htf_data, trading_data = sample_timeframe_data
        signals = generator.generate_exit_signals(
            "AAPL", htf_data, trading_data, SignalType.LONG
        )

        assert len(signals) == 1
        signal = signals[0]
        exit_reasons = signal.pattern_context.get("exit_reasons", [])
        
        # Should have multiple exit reasons
        assert len(exit_reasons) >= 2
        assert "htf_trend_reversal" in exit_reasons


class TestTieredSignalGeneration:
    """Test tiered signal generation from SignalGenerator."""

    def test_generate_high_tier_signal(self, sample_long_analysis, sample_timeframe_data):
        """Test HIGH tier signal generation with full requirements."""
        from dgas.prediction.engine import TieredSignalConfig, SignalTier
        
        coordinator = MultiTimeframeCoordinator("4h", "1h")
        tiered_config = TieredSignalConfig()
        generator = SignalGenerator(coordinator, tiered_config=tiered_config)

        # Modify analysis to meet HIGH tier criteria
        modified_analysis = replace(
            sample_long_analysis,
            alignment=replace(
                sample_long_analysis.alignment,
                alignment_score=Decimal("0.75"),  # Above HIGH threshold (0.7)
            ),
            signal_strength=Decimal("0.70"),  # Above HIGH threshold (0.65)
            confluence_zones=[
                replace(
                    sample_long_analysis.confluence_zones[0],
                    weighted_strength=Decimal("3.2"),  # Above HIGH threshold (3.0)
                )
            ],
        )

        def mock_analyze(htf_data, trading_tf_data, ltf_data=None):
            return modified_analysis

        coordinator.analyze = mock_analyze

        htf_data, trading_data = sample_timeframe_data
        signals = generator.generate_tiered_signals("AAPL", htf_data, trading_data)

        assert len(signals) == 1
        signal = signals[0]
        assert signal.tier == SignalTier.HIGH
        assert signal.position_size_multiplier == 1.0
        assert signal.signal_type == SignalType.LONG

    def test_generate_medium_tier_signal(self, sample_long_analysis, sample_timeframe_data):
        """Test MEDIUM tier signal generation without pattern requirement."""
        from dgas.prediction.engine import TieredSignalConfig, SignalTier
        
        coordinator = MultiTimeframeCoordinator("4h", "1h")
        tiered_config = TieredSignalConfig()
        generator = SignalGenerator(coordinator, tiered_config=tiered_config)

        # Modify analysis to meet MEDIUM but not HIGH tier criteria
        # MEDIUM: alignment >= 0.6, strength >= 0.5, zone >= 2.5, no pattern required
        # HIGH: alignment >= 0.7, strength >= 0.65, zone >= 3.0, pattern required
        modified_analysis = replace(
            sample_long_analysis,
            alignment=replace(
                sample_long_analysis.alignment,
                alignment_score=Decimal("0.65"),  # Between MEDIUM (0.6) and HIGH (0.7)
            ),
            signal_strength=Decimal("0.55"),  # Between MEDIUM (0.5) and HIGH (0.65)
            confluence_zones=[
                replace(
                    sample_long_analysis.confluence_zones[0],
                    weighted_strength=Decimal("2.7"),  # Between MEDIUM (2.5) and HIGH (3.0)
                )
            ],
            htf_patterns=[],  # No patterns - won't meet HIGH tier pattern requirement
            trading_tf_patterns=[],
        )

        def mock_analyze(htf_data, trading_tf_data, ltf_data=None):
            return modified_analysis

        coordinator.analyze = mock_analyze

        htf_data, trading_data = sample_timeframe_data
        signals = generator.generate_tiered_signals("AAPL", htf_data, trading_data)

        assert len(signals) == 1
        signal = signals[0]
        assert signal.tier == SignalTier.MEDIUM
        assert signal.position_size_multiplier == 0.75
        assert signal.signal_type == SignalType.LONG

    def test_generate_low_tier_signal(self, sample_long_analysis, sample_timeframe_data):
        """Test LOW tier signal generation with strong zone only."""
        from dgas.prediction.engine import TieredSignalConfig, SignalTier
        
        coordinator = MultiTimeframeCoordinator("4h", "1h")
        tiered_config = TieredSignalConfig()
        generator = SignalGenerator(coordinator, tiered_config=tiered_config)

        # Modify analysis to meet LOW but not MEDIUM tier criteria
        # LOW: alignment >= 0.5, strength >= 0.4, zone >= 3.5, no pattern required
        modified_analysis = replace(
            sample_long_analysis,
            alignment=replace(
                sample_long_analysis.alignment,
                alignment_score=Decimal("0.55"),  # Between LOW (0.5) and MEDIUM (0.6)
            ),
            signal_strength=Decimal("0.45"),  # Between LOW (0.4) and MEDIUM (0.5)
            confluence_zones=[
                replace(
                    sample_long_analysis.confluence_zones[0],
                    weighted_strength=Decimal("3.7"),  # Above LOW threshold (3.5)
                )
            ],
            htf_patterns=[],
            trading_tf_patterns=[],
        )

        def mock_analyze(htf_data, trading_tf_data, ltf_data=None):
            return modified_analysis

        coordinator.analyze = mock_analyze

        htf_data, trading_data = sample_timeframe_data
        signals = generator.generate_tiered_signals("AAPL", htf_data, trading_data)

        assert len(signals) == 1
        signal = signals[0]
        assert signal.tier == SignalTier.LOW
        assert signal.position_size_multiplier == 0.5
        assert signal.signal_type == SignalType.LONG

    def test_tiered_fallback_behavior(self, sample_long_analysis, sample_timeframe_data):
        """Test that system tries HIGH -> MEDIUM -> LOW in order."""
        from dgas.prediction.engine import TieredSignalConfig, SignalTier
        
        coordinator = MultiTimeframeCoordinator("4h", "1h")
        tiered_config = TieredSignalConfig()
        generator = SignalGenerator(coordinator, tiered_config=tiered_config)

        # Analysis that only meets LOW tier (weak alignment/strength but very strong zone)
        modified_analysis = replace(
            sample_long_analysis,
            alignment=replace(
                sample_long_analysis.alignment,
                alignment_score=Decimal("0.52"),  # Only meets LOW
            ),
            signal_strength=Decimal("0.42"),  # Only meets LOW
            confluence_zones=[
                replace(
                    sample_long_analysis.confluence_zones[0],
                    weighted_strength=Decimal("4.0"),  # Very strong zone
                )
            ],
            htf_patterns=[],
            trading_tf_patterns=[],
        )

        def mock_analyze(htf_data, trading_tf_data, ltf_data=None):
            return modified_analysis

        coordinator.analyze = mock_analyze

        htf_data, trading_data = sample_timeframe_data
        signals = generator.generate_tiered_signals("AAPL", htf_data, trading_data)

        # Should generate LOW tier signal (HIGH and MEDIUM didn't qualify)
        assert len(signals) == 1
        assert signals[0].tier == SignalTier.LOW

    def test_no_tiered_signal_when_criteria_not_met(self, sample_long_analysis, sample_timeframe_data):
        """Test no signal generated when no tier meets criteria."""
        from dgas.prediction.engine import TieredSignalConfig
        
        coordinator = MultiTimeframeCoordinator("4h", "1h")
        tiered_config = TieredSignalConfig()
        generator = SignalGenerator(coordinator, tiered_config=tiered_config)

        # Analysis that doesn't meet any tier criteria
        modified_analysis = replace(
            sample_long_analysis,
            alignment=replace(
                sample_long_analysis.alignment,
                alignment_score=Decimal("0.45"),  # Below all thresholds
            ),
            signal_strength=Decimal("0.35"),  # Below all thresholds
            confluence_zones=[
                replace(
                    sample_long_analysis.confluence_zones[0],
                    weighted_strength=Decimal("2.0"),  # Below all zone weight thresholds
                )
            ],
        )

        def mock_analyze(htf_data, trading_tf_data, ltf_data=None):
            return modified_analysis

        coordinator.analyze = mock_analyze

        htf_data, trading_data = sample_timeframe_data
        signals = generator.generate_tiered_signals("AAPL", htf_data, trading_data)

        assert len(signals) == 0

    def test_tiered_config_with_disabled_tiers(self, sample_long_analysis, sample_timeframe_data):
        """Test tier generation with some tiers disabled."""
        from dgas.prediction.engine import TieredSignalConfig, SignalTier
        
        coordinator = MultiTimeframeCoordinator("4h", "1h")
        
        # Only enable HIGH and LOW tiers, disable MEDIUM
        tiered_config = TieredSignalConfig(
            enabled_tiers=[SignalTier.HIGH, SignalTier.LOW]
        )
        generator = SignalGenerator(coordinator, tiered_config=tiered_config)

        # Analysis that would qualify for MEDIUM tier
        modified_analysis = replace(
            sample_long_analysis,
            alignment=replace(
                sample_long_analysis.alignment,
                alignment_score=Decimal("0.65"),
            ),
            signal_strength=Decimal("0.55"),
            confluence_zones=[
                replace(
                    sample_long_analysis.confluence_zones[0],
                    weighted_strength=Decimal("2.7"),
                )
            ],
            htf_patterns=[],
            trading_tf_patterns=[],
        )

        def mock_analyze(htf_data, trading_tf_data, ltf_data=None):
            return modified_analysis

        coordinator.analyze = mock_analyze

        htf_data, trading_data = sample_timeframe_data
        signals = generator.generate_tiered_signals("AAPL", htf_data, trading_data)

        # Since MEDIUM is disabled and thresholds don't meet HIGH,
        # should fall through to LOW tier (if zone is strong enough)
        # But in this case zone weight (2.7) is below LOW threshold (3.5)
        assert len(signals) == 0

    def test_fallback_to_standard_generation_without_config(self, sample_long_analysis, sample_timeframe_data):
        """Test that tiered generation falls back to standard when no config provided."""
        coordinator = MultiTimeframeCoordinator("4h", "1h")
        # No tiered_config provided
        generator = SignalGenerator(coordinator)

        def mock_analyze(htf_data, trading_tf_data, ltf_data=None):
            return sample_long_analysis

        coordinator.analyze = mock_analyze

        htf_data, trading_data = sample_timeframe_data
        signals = generator.generate_tiered_signals("AAPL", htf_data, trading_data)

        # Should fall back to standard generate_signals
        # Standard generation requires patterns, which sample_long_analysis has
        assert len(signals) == 1
        # Should not have tier information (uses standard generation)
        assert signals[0].tier is None
        assert signals[0].position_size_multiplier == 1.0  # Default


class TestSignalAggregator:
    """Test SignalAggregator class."""

    def test_aggregate_signals_no_filters(self, sample_signals):
        """Test aggregation without filters returns all signals."""
        aggregator = SignalAggregator()
        result = aggregator.aggregate_signals(sample_signals)

        assert len(result) <= len(sample_signals)  # May deduplicate
        assert len(result) > 0

    def test_aggregate_signals_min_confidence_filter(self, sample_signals):
        """Test filtering by minimum confidence."""
        aggregator = SignalAggregator()
        result = aggregator.aggregate_signals(sample_signals, min_confidence=0.8)

        assert all(s.confidence >= 0.8 for s in result)

    def test_aggregate_signals_min_alignment_filter(self, sample_signals):
        """Test filtering by minimum alignment."""
        aggregator = SignalAggregator()
        result = aggregator.aggregate_signals(sample_signals, min_alignment=0.7)

        assert all(s.timeframe_alignment >= 0.7 for s in result)

    def test_aggregate_signals_ranking(self, sample_signals):
        """Test signals are ranked by composite score."""
        aggregator = SignalAggregator()
        result = aggregator.aggregate_signals(sample_signals)

        # Verify descending order by composite score
        for i in range(len(result) - 1):
            score1 = result[i].confidence * result[i].signal_strength * result[i].timeframe_alignment
            score2 = result[i+1].confidence * result[i+1].signal_strength * result[i+1].timeframe_alignment
            assert score1 >= score2

    def test_aggregate_signals_duplicate_detection(self):
        """Test duplicate signals are removed."""
        now = datetime.now(timezone.utc)

        # Create duplicate signals for same symbol + type within time window
        signals = [
            GeneratedSignal(
                symbol="AAPL",
                signal_timestamp=now,
                signal_type=SignalType.LONG,
                entry_price=Decimal("150.00"),
                stop_loss=Decimal("148.00"),
                target_price=Decimal("155.00"),
                confidence=0.75,
                signal_strength=0.80,
                timeframe_alignment=0.85,
                risk_reward_ratio=2.5,
                htf_trend=TrendDirection.UP,
                trading_tf_state="TREND",
                confluence_zones_count=2,
                pattern_context={},
                htf_timeframe="4h",
                trading_timeframe="1h",
            ),
            GeneratedSignal(
                symbol="AAPL",
                signal_timestamp=now + timedelta(minutes=30),  # Within 60min window
                signal_type=SignalType.LONG,
                entry_price=Decimal("150.50"),
                stop_loss=Decimal("148.50"),
                target_price=Decimal("155.50"),
                confidence=0.85,  # Higher confidence
                signal_strength=0.80,
                timeframe_alignment=0.85,
                risk_reward_ratio=2.5,
                htf_trend=TrendDirection.UP,
                trading_tf_state="TREND",
                confluence_zones_count=2,
                pattern_context={},
                htf_timeframe="4h",
                trading_timeframe="1h",
            ),
        ]

        aggregator = SignalAggregator(duplicate_window_minutes=60)
        result = aggregator.aggregate_signals(signals)

        # Should keep only one (the higher confidence one)
        assert len(result) == 1
        assert result[0].confidence == 0.85

    def test_aggregate_signals_max_limit(self, sample_signals):
        """Test max_signals limit is respected."""
        aggregator = SignalAggregator()
        result = aggregator.aggregate_signals(sample_signals, max_signals=2)

        assert len(result) <= 2


# Fixtures

@pytest.fixture
def sample_timeframe_data():
    """Create sample timeframe data for testing."""
    now = datetime.now(timezone.utc)

    # Create PLdot series
    pldot_series = [
        PLDotSeries(
            timestamp=now,
            value=Decimal("150.00"),
            projected_timestamp=now + timedelta(hours=1),
            projected_value=Decimal("150.50"),
            slope=Decimal("0.005"),
            displacement=1,
        )
    ]

    # Create envelope series
    envelope_series = [
        EnvelopeSeries(
            timestamp=now,
            center=Decimal("150.00"),
            upper=Decimal("152.00"),
            lower=Decimal("148.00"),
            width=Decimal("4.00"),
            position=Decimal("0.5"),
            method="pldot_range",
        )
    ]

    # Create state series
    state_series = [
        StateSeries(
            timestamp=now,
            state=MarketState.TREND,
            trend_direction=TrendDirection.UP,
            bars_in_state=5,
            previous_state=None,
            pldot_slope_trend="rising",
            confidence=Decimal("0.85"),
            state_change_reason="",
        )
    ]

    # Create pattern events
    pattern_events = [
        PatternEvent(
            pattern_type=PatternType.PLDOT_PUSH,
            direction=1,
            start_timestamp=now - timedelta(hours=2),
            end_timestamp=now,
            strength=3,
        )
    ]

    htf_data = TimeframeData(
        timeframe="4h",
        classification=TimeframeType.HIGHER,
        pldot_series=pldot_series,
        envelope_series=envelope_series,
        state_series=state_series,
        pattern_events=pattern_events,
    )

    trading_data = TimeframeData(
        timeframe="1h",
        classification=TimeframeType.TRADING,
        pldot_series=pldot_series,
        envelope_series=envelope_series,
        state_series=state_series,
        pattern_events=pattern_events,
    )

    return htf_data, trading_data


@pytest.fixture
def sample_long_analysis():
    """Create sample multi-timeframe analysis for LONG signal."""
    now = datetime.now(timezone.utc)

    alignment = TimeframeAlignment(
        timestamp=now,
        htf_state=MarketState.TREND,
        htf_direction=TrendDirection.UP,
        htf_confidence=Decimal("0.85"),
        trading_tf_state=MarketState.TREND,
        trading_tf_direction=TrendDirection.UP,
        trading_tf_confidence=Decimal("0.80"),
        alignment_score=Decimal("0.75"),
        alignment_type="partial",
        trade_permitted=True,
    )

    pldot_overlay = PLDotOverlay(
        timestamp=now,
        htf_timeframe="4h",
        htf_pldot_value=Decimal("150.00"),
        htf_slope=Decimal("0.005"),
        ltf_timeframe="1h",
        ltf_pldot_value=Decimal("149.50"),
        distance_percent=Decimal("-0.33"),
        position="below_htf",
    )

    confluence_zones = [
        ConfluenceZone(
            level=Decimal("149.00"),
            upper_bound=Decimal("149.50"),
            lower_bound=Decimal("148.50"),
            strength=2,
            timeframes=["4h", "1h"],
            zone_type="support",
            first_touch=now - timedelta(hours=24),
            last_touch=now,
            weighted_strength=Decimal("3.2"),
            sources={"4h": "drummond_zone", "1h": "envelope_lower"},
            volatility=Decimal("0.4"),
        )
    ]

    htf_patterns = [
        PatternEvent(
            pattern_type=PatternType.PLDOT_PUSH,
            direction=1,
            start_timestamp=now - timedelta(hours=4),
            end_timestamp=now,
            strength=3,
        )
    ]

    return MultiTimeframeAnalysis(
        timestamp=now,
        htf_timeframe="4h",
        trading_timeframe="1h",
        ltf_timeframe=None,
        htf_trend=TrendDirection.UP,
        htf_trend_strength=Decimal("0.80"),
        trading_tf_trend=TrendDirection.UP,
        alignment=alignment,
        pldot_overlay=pldot_overlay,
        confluence_zones=confluence_zones,
        htf_patterns=htf_patterns,
        trading_tf_patterns=[],
        pattern_confluence=True,
        signal_strength=Decimal("0.70"),
        risk_level="medium",
        recommended_action="long",
    )


@pytest.fixture
def sample_short_analysis():
    """Create sample multi-timeframe analysis for SHORT signal."""
    now = datetime.now(timezone.utc)

    alignment = TimeframeAlignment(
        timestamp=now,
        htf_state=MarketState.TREND,
        htf_direction=TrendDirection.DOWN,
        htf_confidence=Decimal("0.85"),
        trading_tf_state=MarketState.TREND,
        trading_tf_direction=TrendDirection.DOWN,
        trading_tf_confidence=Decimal("0.80"),
        alignment_score=Decimal("0.75"),
        alignment_type="partial",
        trade_permitted=True,
    )

    pldot_overlay = PLDotOverlay(
        timestamp=now,
        htf_timeframe="4h",
        htf_pldot_value=Decimal("150.00"),
        htf_slope=Decimal("-0.005"),
        ltf_timeframe="1h",
        ltf_pldot_value=Decimal("150.50"),
        distance_percent=Decimal("0.33"),
        position="above_htf",
    )

    confluence_zones = [
        ConfluenceZone(
            level=Decimal("151.00"),
            upper_bound=Decimal("151.50"),
            lower_bound=Decimal("150.50"),
            strength=2,
            timeframes=["4h", "1h"],
            zone_type="resistance",
            first_touch=now - timedelta(hours=24),
            last_touch=now,
            weighted_strength=Decimal("3.0"),
            sources={"4h": "drummond_zone", "1h": "envelope_upper"},
            volatility=Decimal("0.35"),
        )
    ]

    htf_patterns = [
        PatternEvent(
            pattern_type=PatternType.PLDOT_PUSH,
            direction=-1,
            start_timestamp=now - timedelta(hours=4),
            end_timestamp=now,
            strength=3,
        )
    ]

    return MultiTimeframeAnalysis(
        timestamp=now,
        htf_timeframe="4h",
        trading_timeframe="1h",
        ltf_timeframe=None,
        htf_trend=TrendDirection.DOWN,
        htf_trend_strength=Decimal("0.80"),
        trading_tf_trend=TrendDirection.DOWN,
        alignment=alignment,
        pldot_overlay=pldot_overlay,
        confluence_zones=confluence_zones,
        htf_patterns=htf_patterns,
        trading_tf_patterns=[],
        pattern_confluence=False,
        signal_strength=Decimal("0.70"),
        risk_level="medium",
        recommended_action="short",
    )


@pytest.fixture
def sample_signals():
    """Create sample signals for aggregation testing."""
    now = datetime.now(timezone.utc)

    return [
        GeneratedSignal(
            symbol="AAPL",
            signal_timestamp=now,
            signal_type=SignalType.LONG,
            entry_price=Decimal("150.00"),
            stop_loss=Decimal("148.00"),
            target_price=Decimal("155.00"),
            confidence=0.85,
            signal_strength=0.80,
            timeframe_alignment=0.75,
            risk_reward_ratio=2.5,
            htf_trend=TrendDirection.UP,
            trading_tf_state="TREND",
            confluence_zones_count=2,
            pattern_context={},
            htf_timeframe="4h",
            trading_timeframe="1h",
        ),
        GeneratedSignal(
            symbol="MSFT",
            signal_timestamp=now,
            signal_type=SignalType.SHORT,
            entry_price=Decimal("300.00"),
            stop_loss=Decimal("302.00"),
            target_price=Decimal("295.00"),
            confidence=0.75,
            signal_strength=0.70,
            timeframe_alignment=0.80,
            risk_reward_ratio=2.5,
            htf_trend=TrendDirection.DOWN,
            trading_tf_state="TREND",
            confluence_zones_count=1,
            pattern_context={},
            htf_timeframe="4h",
            trading_timeframe="1h",
        ),
        GeneratedSignal(
            symbol="GOOGL",
            signal_timestamp=now,
            signal_type=SignalType.LONG,
            entry_price=Decimal("140.00"),
            stop_loss=Decimal("138.00"),
            target_price=Decimal("145.00"),
            confidence=0.65,
            signal_strength=0.60,
            timeframe_alignment=0.70,
            risk_reward_ratio=2.5,
            htf_trend=TrendDirection.UP,
            trading_tf_state="CONGESTION_EXIT",
            confluence_zones_count=1,
            pattern_context={},
            htf_timeframe="4h",
            trading_timeframe="1h",
        ),
    ]
