"""Base classes for building backtesting strategies."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from decimal import Decimal
from typing import Deque, Iterable, Mapping, Sequence

from pydantic import BaseModel

from ...data.models import IntervalData
from ..entities import Position, Signal


class StrategyConfig(BaseModel):
    """Base configuration shared by all strategies."""

    name: str = "strategy"


@dataclass
class StrategyContext:
    """Runtime information exposed to strategy implementations."""

    symbol: str
    bar: IntervalData
    position: Position | None
    cash: Decimal
    equity: Decimal
    indicators: Mapping[str, object]
    history: Deque[IntervalData]

    def has_position(self) -> bool:
        return self.position is not None

    def current_price(self) -> Decimal:
        return self.bar.close

    def get_indicator(self, key: str, default: object | None = None) -> object | None:
        return self.indicators.get(key, default)


class BaseStrategy:
    """Interface that all backtesting strategies must implement."""

    config_model = StrategyConfig

    def __init__(self, config: StrategyConfig | None = None) -> None:
        self.config = config or self.config_model()

    @property
    def name(self) -> str:
        return self.config.name or self.__class__.__name__

    def prepare(self, data: Sequence[IntervalData]) -> None:  # pragma: no cover - hook
        """Hook executed once before the simulation starts."""

    def on_bar(self, context: StrategyContext) -> Iterable[Signal]:  # pragma: no cover - abstract
        raise NotImplementedError


def rolling_history(maxlen: int = 500) -> Deque[IntervalData]:
    return deque(maxlen=maxlen)


__all__ = ["StrategyConfig", "StrategyContext", "BaseStrategy", "rolling_history"]
