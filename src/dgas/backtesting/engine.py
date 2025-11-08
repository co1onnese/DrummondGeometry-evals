"""Deterministic backtesting engine built on top of strategy signals."""

from __future__ import annotations

from decimal import Decimal
from typing import Iterable

from ..data.models import IntervalData
from .data_loader import BacktestDataset
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
from .execution.trade_executor import BaseTradeExecutor
from .strategies.base import BaseStrategy, StrategyContext, rolling_history


class SimulationEngine:
    """Main entry point for running strategy simulations."""

    def __init__(self, config: SimulationConfig | None = None) -> None:
        self.config = config or SimulationConfig()
        self.executor = BaseTradeExecutor(
            commission_rate=self.config.commission_rate,
            slippage_bps=self.config.slippage_bps,
        )

    def run(self, dataset: BacktestDataset, strategy: BaseStrategy) -> BacktestResult:
        bars = list(dataset.bars)
        if len(bars) < 2:
            raise ValueError("Backtesting requires at least two bars of data")

        strategy.prepare([bundle.bar for bundle in bars])

        cash = self.config.initial_capital
        position: Position | None = None
        trades: list[Trade] = []
        equity_curve: list[PortfolioSnapshot] = []
        pending_signals: list[Signal] = []
        history = rolling_history()

        for idx, bundle in enumerate(bars):
            bar = bundle.bar

            # Execute signals queued from the previous bar at current open.
            if pending_signals:
                executed, position, cash = self._execute_signals(
                    dataset.symbol,
                    pending_signals,
                    bar,
                    position,
                    cash,
                    price_field="open",
                )
                trades.extend(executed)
                pending_signals = []

            history.append(bar)

            # Check stop-loss/take-profit BEFORE strategy signal generation
            # This ensures stops are checked using intraday prices (bar.high/bar.low)
            if position:
                exit_signal, exit_price = self._check_stop_loss_take_profit(position, bar)
                if exit_signal:
                    # Close position at the appropriate exit price (stop-loss/take-profit or bar.close)
                    trade, cash = self._close_position(
                        dataset.symbol,
                        position,
                        bar,
                        cash,
                        exit_price if exit_price is not None else bar.close,
                    )
                    if trade:
                        trades.append(trade)
                    position = None
                    # Record equity after closing position
                    equity = cash
                    equity_curve.append(
                        PortfolioSnapshot(
                            timestamp=bar.timestamp,
                            equity=equity,
                            cash=cash,
                        )
                    )
                    # Skip strategy signal generation since we already exited
                    continue

            market_value = position.market_value(bar.close) if position else Decimal("0")
            equity = cash + market_value
            equity_curve.append(
                PortfolioSnapshot(
                    timestamp=bar.timestamp,
                    equity=equity,
                    cash=cash,
                )
            )

            # Do not generate new signals on the final bar (no next open to execute).
            if idx == len(bars) - 1:
                continue

            context = StrategyContext(
                symbol=dataset.symbol,
                bar=bar,
                position=position,
                cash=cash,
                equity=equity,
                indicators=bundle.indicators,
                history=history,
            )

            new_signals = list(strategy.on_bar(context))
            if new_signals:
                pending_signals.extend(new_signals)

        # Liquidate any residual position at the final bar's close.
        if position is not None:
            final_bar = bars[-1].bar
            executed, position, cash = self._execute_signals(
                dataset.symbol,
                [Signal(SignalAction.LIQUIDATE)],
                final_bar,
                position,
                cash,
                price_field="close",
            )
            trades.extend(executed)
            equity = cash
            if equity_curve and equity_curve[-1].timestamp == final_bar.timestamp:
                equity_curve[-1] = PortfolioSnapshot(final_bar.timestamp, equity, cash)
            else:
                equity_curve.append(PortfolioSnapshot(final_bar.timestamp, equity, cash))

        ending_cash = cash
        ending_equity = equity_curve[-1].equity if equity_curve else cash

        return BacktestResult(
            symbol=dataset.symbol,
            strategy_name=strategy.name,
            config=self.config,
            trades=trades,
            equity_curve=equity_curve,
            starting_cash=self.config.initial_capital,
            ending_cash=ending_cash,
            ending_equity=ending_equity,
            metadata={},
        )

    # ------------------------------------------------------------------
    # Execution helpers
    # ------------------------------------------------------------------

    def _execute_signals(
        self,
        symbol: str,
        signals: Iterable[Signal],
        bar: IntervalData,
        position: Position | None,
        cash: Decimal,
        *,
        price_field: str,
    ) -> tuple[list[Trade], Position | None, Decimal]:
        trades: list[Trade] = []
        base_price = getattr(bar, price_field)

        for signal in signals:
            if signal.action == SignalAction.ENTER_LONG:
                new_trades, position, cash = self._enter_position(
                    symbol, PositionSide.LONG, signal, bar, position, cash, base_price
                )
                trades.extend(new_trades)
            elif signal.action == SignalAction.ENTER_SHORT:
                new_trades, position, cash = self._enter_position(
                    symbol, PositionSide.SHORT, signal, bar, position, cash, base_price
                )
                trades.extend(new_trades)
            elif signal.action == SignalAction.EXIT_LONG:
                if position and position.side is PositionSide.LONG:
                    trade, cash = self._close_position(symbol, position, bar, cash, base_price)
                    if trade:
                        trades.append(trade)
                    position = None
            elif signal.action == SignalAction.EXIT_SHORT:
                if position and position.side is PositionSide.SHORT:
                    trade, cash = self._close_position(symbol, position, bar, cash, base_price)
                    if trade:
                        trades.append(trade)
                    position = None
            elif signal.action == SignalAction.LIQUIDATE:
                if position:
                    trade, cash = self._close_position(symbol, position, bar, cash, base_price)
                    if trade:
                        trades.append(trade)
                    position = None

        return trades, position, cash

    def _enter_position(
        self,
        symbol: str,
        side: PositionSide,
        signal: Signal,
        bar: IntervalData,
        position: Position | None,
        cash: Decimal,
        base_price: Decimal,
    ) -> tuple[list[Trade], Position | None, Decimal]:
        trades: list[Trade] = []

        if side is PositionSide.SHORT and not self.config.allow_short:
            return trades, position, cash

        if position:
            if position.side is side:
                return trades, position, cash
            # flip direction by closing existing position first
            trade, cash = self._close_position(symbol, position, bar, cash, base_price)
            if trade:
                trades.append(trade)
            position = None

        # Calculate quantity
        fallback_qty = self._default_quantity(cash, base_price)
        quantity = self.executor.normalize_quantity(signal.resolved_size(fallback_qty))

        if quantity <= 0:
            return trades, position, cash

        # Open position using executor
        position, commission = self.executor.open_position(
            symbol=symbol,
            side=side,
            quantity=quantity,
            entry_price=base_price,
            entry_time=bar.timestamp,
            metadata=dict(signal.metadata),
        )

        # Update cash
        notional = quantity * position.entry_price
        if side is PositionSide.LONG:
            total_cost = notional + commission
            if cash < total_cost:
                return trades, position, cash
            cash -= total_cost
        else:
            cash += notional - commission

        return trades, position, cash

    def _close_position(
        self,
        symbol: str,
        position: Position,
        bar: IntervalData,
        cash: Decimal,
        exit_price: Decimal,
    ) -> tuple[Trade | None, Decimal]:
        """Close a position at a specific exit price.

        Args:
            symbol: Symbol being traded
            position: Position to close
            bar: Current bar (for timestamp)
            cash: Current cash
            exit_price: Exit price (before slippage)

        Returns:
            Tuple of (Trade, updated_cash)
        """
        # Close position using executor (applies slippage)
        trade = self.executor.close_position(
            position=position,
            exit_price=exit_price,
            exit_time=bar.timestamp,
        )

        # Update cash
        notional = position.quantity * trade.exit_price
        exit_commission = trade.commission_paid - position.entry_commission

        if position.side is PositionSide.LONG:
            cash += notional - exit_commission
        else:
            cash -= notional + exit_commission

        return trade, cash

    def _check_stop_loss_take_profit(
        self,
        position: Position,
        bar: IntervalData,
    ) -> tuple[Signal | None, Decimal | None]:
        """Check if stop-loss or take-profit was hit during the bar using intraday prices.

        Args:
            position: Current position
            bar: Current bar with high/low prices

        Returns:
            Tuple of (exit_signal, exit_price)
            - exit_signal: Signal to exit if level hit, None otherwise
            - exit_price: Price at which to exit (stop-loss/take-profit level), None if not hit
        """
        if not position.stop_loss and not position.take_profit:
            return None, None

        exit_signal = None
        exit_price = None

        if position.side == PositionSide.LONG:
            # Check stop-loss: price touched or went below
            if position.stop_loss and bar.low <= position.stop_loss:
                exit_signal = Signal(SignalAction.EXIT_LONG)
                exit_price = position.stop_loss
                return exit_signal, exit_price

            # Check take-profit: price touched or went above
            if position.take_profit and bar.high >= position.take_profit:
                exit_signal = Signal(SignalAction.EXIT_LONG)
                exit_price = position.take_profit
                return exit_signal, exit_price

        else:  # SHORT
            # Check stop-loss: price touched or went above
            if position.stop_loss and bar.high >= position.stop_loss:
                exit_signal = Signal(SignalAction.EXIT_SHORT)
                exit_price = position.stop_loss
                return exit_signal, exit_price

            # Check take-profit: price touched or went below
            if position.take_profit and bar.low <= position.take_profit:
                exit_signal = Signal(SignalAction.EXIT_SHORT)
                exit_price = position.take_profit
                return exit_signal, exit_price

        return None, None

    def _default_quantity(self, cash: Decimal, price: Decimal) -> Decimal:
        """Calculate default position quantity based on available cash."""
        if price <= 0:
            return Decimal("0")
        alloc = cash * self.config.max_position_fraction
        if alloc <= 0:
            return Decimal("0")
        return self.executor.normalize_quantity(alloc / price)


__all__ = ["SimulationEngine"]
