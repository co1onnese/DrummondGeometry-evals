"""Default multi-timeframe strategy implementation."""

from __future__ import annotations

from decimal import Decimal
from typing import Iterable

from .base import BaseStrategy, StrategyConfig, StrategyContext
from ..entities import Signal, SignalAction


class MultiTimeframeStrategyConfig(StrategyConfig):
    name: str = "multi_timeframe"
    min_history: int = 5
    exit_lookback: int = 3


class MultiTimeframeStrategy(BaseStrategy):
    config_model = MultiTimeframeStrategyConfig

    def __init__(self, config: MultiTimeframeStrategyConfig | None = None) -> None:
        super().__init__(config or MultiTimeframeStrategyConfig())

    def on_bar(self, context: StrategyContext) -> Iterable[Signal]:
        history = context.history
        if len(history) < self.config.min_history:
            return []

        last_bar = history[-1]
        prev_bar = history[-2]

        signals: list[Signal] = []

        if not context.has_position():
            if last_bar.close > prev_bar.close:
                signals.append(Signal(SignalAction.ENTER_LONG))
        else:
            lookback = min(len(history) - 1, self.config.exit_lookback)
            losses = [history[-i - 1].close for i in range(lookback)]
            if losses and last_bar.close < losses[0]:
                signals.append(Signal(SignalAction.EXIT_LONG))

        return signals


__all__ = ["MultiTimeframeStrategy", "MultiTimeframeStrategyConfig"]
