"""Deterministic backtesting engine built on top of strategy signals."""

from __future__ import annotations

from decimal import Decimal, ROUND_DOWN
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
from .strategies.base import BaseStrategy, StrategyContext, rolling_history


BASIS_POINT = Decimal("10000")
QUANTITY_STEP = Decimal("0.0001")


class SimulationEngine:
    """Main entry point for running strategy simulations."""

    def __init__(self, config: SimulationConfig | None = None) -> None:
        self.config = config or SimulationConfig()

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

        fill_price = self._apply_slippage(base_price, side, is_entry=True)
        fallback_qty = self._default_quantity(cash, fill_price)
        quantity = self._normalize_quantity(signal.resolved_size(fallback_qty))

        if quantity <= 0:
            return trades, position, cash

        commission = self._compute_commission(quantity, fill_price)
        notional = quantity * fill_price

        if side is PositionSide.LONG:
            total_cost = notional + commission
            if cash < total_cost:
                return trades, position, cash
            cash -= total_cost
        else:
            cash += notional - commission

        position = Position(
            symbol=symbol,
            side=side,
            quantity=quantity,
            entry_price=fill_price,
            entry_time=bar.timestamp,
            entry_commission=commission,
            notes=dict(signal.metadata),
        )

        return trades, position, cash

    def _close_position(
        self,
        symbol: str,
        position: Position,
        bar: IntervalData,
        cash: Decimal,
        base_price: Decimal,
    ) -> tuple[Trade | None, Decimal]:
        fill_price = self._apply_slippage(base_price, position.side, is_entry=False)
        commission = self._compute_commission(position.quantity, fill_price)

        notional = position.quantity * fill_price

        if position.side is PositionSide.LONG:
            cash += notional - commission
        else:
            cash -= notional + commission

        gross_profit = position.direction() * position.quantity * (fill_price - position.entry_price)
        total_commission = position.entry_commission + commission
        net_profit = gross_profit - total_commission

        trade = Trade(
            symbol=symbol,
            side=position.side,
            quantity=position.quantity,
            entry_time=position.entry_time,
            exit_time=bar.timestamp,
            entry_price=position.entry_price,
            exit_price=fill_price,
            gross_profit=gross_profit,
            net_profit=net_profit,
            commission_paid=total_commission,
        )

        return trade, cash

    def _apply_slippage(self, price: Decimal, side: PositionSide, *, is_entry: bool) -> Decimal:
        if self.config.slippage_bps <= 0:
            return price

        fraction = self.config.slippage_bps / BASIS_POINT
        adjustment = price * fraction

        if side is PositionSide.LONG:
            return price + adjustment if is_entry else price - adjustment
        return price - adjustment if is_entry else price + adjustment

    def _compute_commission(self, quantity: Decimal, price: Decimal) -> Decimal:
        if self.config.commission_rate <= 0:
            return Decimal("0")
        return abs(quantity * price) * self.config.commission_rate

    def _default_quantity(self, cash: Decimal, price: Decimal) -> Decimal:
        if price <= 0:
            return Decimal("0")
        alloc = cash * self.config.max_position_fraction
        if alloc <= 0:
            return Decimal("0")
        return self._normalize_quantity(alloc / price)

    @staticmethod
    def _normalize_quantity(quantity: Decimal) -> Decimal:
        if quantity <= 0:
            return Decimal("0")
        return quantity.quantize(QUANTITY_STEP, rounding=ROUND_DOWN)


__all__ = ["SimulationEngine"]
