"""Prediction signal strategy using PredictionEngine's SignalGenerator.

This strategy uses the production SignalGenerator from the prediction engine
to generate trading signals, ensuring backtests use the same signal generation
logic as production.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Iterable

from .base import BaseStrategy, StrategyConfig, StrategyContext
from ..entities import Signal, SignalAction
from ...calculations.multi_timeframe import TimeframeData
from ...prediction.engine import SignalGenerator, SignalType, GeneratedSignal
from ...calculations.multi_timeframe import MultiTimeframeCoordinator


class PredictionSignalStrategyConfig(StrategyConfig):
    """Configuration for prediction signal strategy."""

    name: str = "prediction_signal"
    min_history: int = 5
    min_alignment_score: float = 0.6
    min_signal_strength: float = 0.5
    stop_loss_atr_multiplier: float = 1.5
    target_rr_ratio: float = 2.0
    min_zone_weight: float = 2.5
    required_pattern_strength: int = 2
    allow_short: bool = True


class PredictionSignalStrategy(BaseStrategy):
    """Strategy that uses PredictionEngine's SignalGenerator for signal generation."""

    config_model = PredictionSignalStrategyConfig

    def __init__(self, config: PredictionSignalStrategyConfig | None = None) -> None:
        super().__init__(config or PredictionSignalStrategyConfig())
        
        # Coordinator will be created dynamically with correct timeframes
        # when we have access to portfolio config
        self._signal_generator: SignalGenerator | None = None

    def _get_signal_generator(self, htf_timeframe: str, trading_timeframe: str) -> SignalGenerator:
        """Get or create SignalGenerator with correct timeframes.
        
        Args:
            htf_timeframe: Higher timeframe (e.g., "1d")
            trading_timeframe: Trading timeframe (e.g., "30m")
            
        Returns:
            SignalGenerator instance
        """
        if self._signal_generator is None:
            # Create coordinator with correct timeframes
            coordinator = MultiTimeframeCoordinator(
                htf_timeframe=htf_timeframe,
                trading_timeframe=trading_timeframe,
            )

            self._signal_generator = SignalGenerator(
                coordinator=coordinator,
                min_alignment_score=self.config.min_alignment_score,
                min_signal_strength=self.config.min_signal_strength,
                stop_loss_atr_multiplier=self.config.stop_loss_atr_multiplier,
                target_rr_ratio=self.config.target_rr_ratio,
                min_zone_weight=self.config.min_zone_weight,
                required_pattern_strength=self.config.required_pattern_strength,
            )
        
        return self._signal_generator

    def on_bar(self, context: StrategyContext) -> Iterable[Signal]:
        """Generate signals using PredictionEngine's SignalGenerator.

        Args:
            context: Strategy context with indicators

        Returns:
            Iterable of trading signals
        """
        # Get timeframe data from indicators
        htf_data = context.get_indicator("htf_data")
        trading_tf_data = context.get_indicator("trading_tf_data")

        # If timeframe data not available, try to extract from analysis
        if htf_data is None or trading_tf_data is None:
            analysis = context.get_indicator("analysis")
            if analysis is None:
                return []

            # Cannot rebuild TimeframeData from analysis alone
            # This strategy requires PortfolioIndicatorCalculator to return TimeframeData
            return []

        # Ensure we have TimeframeData objects
        if not isinstance(htf_data, TimeframeData) or not isinstance(trading_tf_data, TimeframeData):
            return []

        # Get timeframes from the data
        htf_timeframe = htf_data.timeframe
        trading_timeframe = trading_tf_data.timeframe
        
        # Get signal generator with correct timeframes
        signal_generator = self._get_signal_generator(htf_timeframe, trading_timeframe)
        
        # Generate signals using SignalGenerator
        try:
            generated_signals = signal_generator.generate_signals(
                symbol=context.symbol,
                htf_data=htf_data,
                trading_tf_data=trading_tf_data,
                ltf_data=None,  # Lower timeframe not used in portfolio backtest
            )
        except Exception as e:
            # Log the exception for debugging
            import logging
            logger = logging.getLogger(__name__)
            logger.debug(f"{context.symbol}: Signal generation failed: {e}", exc_info=True)
            return []

        # Convert GeneratedSignal objects to backtesting Signal objects
        signals = []
        for gen_signal in generated_signals:
            signal = self._convert_generated_signal(gen_signal, context)
            if signal is not None:
                signals.append(signal)

        return signals

    def _convert_generated_signal(
        self, gen_signal: GeneratedSignal, context: StrategyContext
    ) -> Signal | None:
        """Convert GeneratedSignal to backtesting Signal.

        Args:
            gen_signal: Generated signal from SignalGenerator
            context: Strategy context

        Returns:
            Backtesting Signal or None if conversion not possible
        """
        # Map SignalType to SignalAction
        action_map = {
            SignalType.LONG: SignalAction.ENTER_LONG,
            SignalType.SHORT: SignalAction.ENTER_SHORT if self.config.allow_short else None,
            SignalType.EXIT_LONG: SignalAction.EXIT_LONG,
            SignalType.EXIT_SHORT: SignalAction.EXIT_SHORT,
        }

        action = action_map.get(gen_signal.signal_type)
        if action is None:
            return None

        # For entry signals, calculate position size based on risk
        size = None
        if action in [SignalAction.ENTER_LONG, SignalAction.ENTER_SHORT]:
            size = self._calculate_position_size(gen_signal, context)

        # Build metadata with signal details
        metadata = {
            "entry_price": str(gen_signal.entry_price),
            "stop_loss": str(gen_signal.stop_loss),
            "target_price": str(gen_signal.target_price),
            "confidence": str(gen_signal.confidence),
            "signal_strength": str(gen_signal.signal_strength),
            "timeframe_alignment": str(gen_signal.timeframe_alignment),
            "risk_reward_ratio": str(gen_signal.risk_reward_ratio),
            "htf_trend": gen_signal.htf_trend.value,
            "trading_tf_state": gen_signal.trading_tf_state,
            "confluence_zones_count": str(gen_signal.confluence_zones_count),
            "htf_timeframe": gen_signal.htf_timeframe,
            "trading_timeframe": gen_signal.trading_timeframe,
            "signal_id": f"{gen_signal.symbol}_{gen_signal.signal_timestamp.isoformat()}",
        }

        return Signal(action=action, size=size, metadata=metadata)

    def _calculate_position_size(
        self, gen_signal: GeneratedSignal, context: StrategyContext
    ) -> Decimal | None:
        """Calculate position size based on risk.

        Args:
            gen_signal: Generated signal
            context: Strategy context

        Returns:
            Position size in shares or None if cannot calculate
        """
        # Risk amount is typically set by portfolio position manager
        # Here we just return None to let the portfolio engine handle sizing
        # The portfolio engine will use risk_per_trade_pct from config
        return None


__all__ = ["PredictionSignalStrategy", "PredictionSignalStrategyConfig"]
