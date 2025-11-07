"""High-level orchestration for running backtests."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, Mapping

from ..data.repository import get_symbol_id
from ..db import get_connection
from . import (
    SimulationConfig,
    SimulationEngine,
    calculate_performance,
    load_dataset,
    persist_backtest,
)
from .data_loader import BacktestDataset
from .entities import BacktestResult
from .metrics import PerformanceSummary
from .strategies.registry import STRATEGY_REGISTRY, instantiate_strategy


@dataclass(frozen=True)
class BacktestRequest:
    symbols: list[str]
    interval: str
    start: datetime | None = None
    end: datetime | None = None
    strategy_name: str = "multi_timeframe"
    strategy_params: Mapping[str, Any] = field(default_factory=dict)
    simulation_config: SimulationConfig = field(default_factory=SimulationConfig)
    risk_free_rate: Decimal = Decimal("0")
    persist_results: bool = True
    limit: int | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    htf_interval: str | None = None


@dataclass(frozen=True)
class BacktestRunResult:
    symbol: str
    dataset: BacktestDataset
    result: BacktestResult
    performance: PerformanceSummary
    persisted_id: int | None

    @property
    def strategy_name(self) -> str:
        return self.result.strategy_name


class BacktestRunner:
    """Coordinate data loading, strategy execution, metrics, and persistence."""

    def __init__(self, engine: SimulationEngine | None = None) -> None:
        self.engine = engine or SimulationEngine()

    def run(self, request: BacktestRequest) -> list[BacktestRunResult]:
        if not request.symbols:
            raise ValueError("At least one symbol must be provided for backtesting")

        results: list[BacktestRunResult] = []
        for symbol in request.symbols:
            dataset = load_dataset(
                symbol,
                request.interval,
                start=request.start,
                end=request.end,
                limit=request.limit,
                htf_interval=request.htf_interval,
            )

            if not dataset.bars:
                raise ValueError(f"No market data found for {symbol} on interval {request.interval}")

            # CRITICAL FIX: Create fresh strategy instance per symbol to avoid state accumulation
            strategy = instantiate_strategy(
                request.strategy_name,
                request.strategy_params,
            )

            result = self.engine.run(dataset, strategy)
            performance = calculate_performance(result, risk_free_rate=request.risk_free_rate)

            persisted_id: int | None = None
            if request.persist_results:
                with get_connection() as conn:
                    symbol_id = get_symbol_id(conn, symbol)
                    if symbol_id is None:
                        raise ValueError(
                            f"Symbol {symbol} not registered in database. Ingest data before backtesting."
                        )
                # persist_backtest opens its own connection when conn is None
                persisted_id = persist_backtest(
                    result,
                    performance,
                    metadata=request.metadata,
                )

            results.append(
                BacktestRunResult(
                    symbol=symbol,
                    dataset=dataset,
                    result=result,
                    performance=performance,
                    persisted_id=persisted_id,
                )
            )

        return results


__all__ = [
    "BacktestRequest",
    "BacktestRunResult",
    "BacktestRunner",
    "STRATEGY_REGISTRY",
    "instantiate_strategy",
]
