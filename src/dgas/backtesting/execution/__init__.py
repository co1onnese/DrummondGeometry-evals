"""Trade execution logic shared between single-symbol and portfolio engines."""

from .trade_executor import BaseTradeExecutor, TradeExecutionResult

__all__ = ["BaseTradeExecutor", "TradeExecutionResult"]
