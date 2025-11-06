"""Backtesting engine interfaces."""

from .data_loader import BacktestBar, BacktestDataset, assemble_bars, load_dataset, load_indicator_snapshots, load_ohlcv
from .engine import SimulationEngine
from .entities import (
    BacktestResult,
    PortfolioSnapshot,
    Position,
    PositionSide,
    Signal,
    SignalAction,
    SimulationConfig,
    Trade,
)
from .strategies import BaseStrategy, StrategyConfig, StrategyContext, rolling_history
from .metrics import PerformanceSummary, calculate_performance
from .persistence import persist_backtest
from .reporting import build_summary_table, export_json, export_markdown
from .runner import BacktestRequest, BacktestRunResult, BacktestRunner

__all__ = [
    "SimulationEngine",
    "SimulationConfig",
    "BacktestResult",
    "PortfolioSnapshot",
    "Trade",
    "Position",
    "PositionSide",
    "Signal",
    "SignalAction",
    "BacktestBar",
    "BacktestDataset",
    "load_dataset",
    "load_ohlcv",
    "load_indicator_snapshots",
    "assemble_bars",
    "BaseStrategy",
    "StrategyConfig",
    "StrategyContext",
    "rolling_history",
    "PerformanceSummary",
    "calculate_performance",
    "persist_backtest",
    "BacktestRequest",
    "BacktestRunResult",
    "BacktestRunner",
    "build_summary_table",
    "export_markdown",
    "export_json",
]
