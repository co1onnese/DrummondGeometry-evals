"""Strategy registry used by the backtesting runner."""

from __future__ import annotations

from typing import Any, Dict, Mapping, Type

from .base import BaseStrategy, StrategyConfig
from .multi_timeframe import MultiTimeframeStrategy, MultiTimeframeStrategyConfig


STRATEGY_REGISTRY: Dict[str, Type[BaseStrategy]] = {
    "multi_timeframe": MultiTimeframeStrategy,
}


def instantiate_strategy(name: str, params: Mapping[str, Any] | None = None) -> BaseStrategy:
    """Instantiate a strategy by name using optional parameters."""

    params = params or {}
    try:
        strategy_cls = STRATEGY_REGISTRY[name]
    except KeyError:
        available = ", ".join(sorted(STRATEGY_REGISTRY)) or "<none>"
        raise ValueError(f"Unknown strategy '{name}'. Available: {available}")

    config_cls: Type[StrategyConfig] = getattr(strategy_cls, "config_model", StrategyConfig)
    config = config_cls(**params) if params else config_cls()
    return strategy_cls(config)


__all__ = ["STRATEGY_REGISTRY", "instantiate_strategy"]
