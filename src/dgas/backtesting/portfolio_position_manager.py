"""Portfolio-level position management with shared capital.

Manages multiple positions across symbols sharing a common capital pool,
with portfolio-wide risk management and position sizing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional

from .entities import Position, PositionSide, Trade
from .execution.trade_executor import BaseTradeExecutor


@dataclass
class PortfolioPosition:
    """Extended position with portfolio-level context."""

    position: Position
    risk_amount: Decimal  # Portfolio risk allocated to this position
    stop_loss: Decimal | None = None  # Stop loss price
    target: Decimal | None = None  # Target price
    max_adverse_excursion: Decimal = Decimal("0")  # Worst unrealized loss
    max_favorable_excursion: Decimal = Decimal("0")  # Best unrealized profit
    metadata: Dict[str, any] = field(default_factory=dict)

    def update_excursions(self, current_price: Decimal) -> None:
        """Update max adverse and favorable excursions."""
        unrealized_pnl = self.position.unrealized_pnl(current_price)

        if unrealized_pnl < self.max_adverse_excursion:
            self.max_adverse_excursion = unrealized_pnl

        if unrealized_pnl > self.max_favorable_excursion:
            self.max_favorable_excursion = unrealized_pnl

    @property
    def symbol(self) -> str:
        return self.position.symbol

    @property
    def side(self) -> PositionSide:
        return self.position.side


@dataclass
class PortfolioState:
    """Current state of the portfolio."""

    timestamp: datetime
    cash: Decimal
    positions: Dict[str, PortfolioPosition]  # symbol -> position
    total_equity: Decimal
    total_position_value: Decimal
    available_capital: Decimal

    def get_position(self, symbol: str) -> PortfolioPosition | None:
        """Get position for symbol."""
        return self.positions.get(symbol)

    def has_position(self, symbol: str) -> bool:
        """Check if holding position in symbol."""
        return symbol in self.positions

    @property
    def position_count(self) -> int:
        """Number of open positions."""
        return len(self.positions)


class PortfolioPositionManager:
    """Manage positions across multiple symbols with shared capital."""

    def __init__(
        self,
        initial_capital: Decimal,
        max_positions: int = 20,
        max_portfolio_risk_pct: Decimal = Decimal("0.10"),  # 10% max total risk
        risk_per_trade_pct: Decimal = Decimal("0.02"),  # 2% per trade
        commission_rate: Decimal = Decimal("0.0"),
        slippage_bps: Decimal = Decimal("0.0"),
    ):
        """Initialize portfolio position manager.

        Args:
            initial_capital: Starting capital for entire portfolio
            max_positions: Maximum number of concurrent positions
            max_portfolio_risk_pct: Maximum total portfolio risk (sum of all position risks)
            risk_per_trade_pct: Risk per individual trade as % of portfolio
            commission_rate: Commission rate (decimal, e.g., 0.001 = 0.1%)
            slippage_bps: Slippage in basis points
        """
        self.initial_capital = initial_capital
        self.max_positions = max_positions
        self.max_portfolio_risk_pct = max_portfolio_risk_pct
        self.risk_per_trade_pct = risk_per_trade_pct
        self.commission_rate = commission_rate
        self.slippage_bps = slippage_bps

        # Trade executor for shared execution logic
        self.executor = BaseTradeExecutor(
            commission_rate=commission_rate,
            slippage_bps=slippage_bps,
        )

        # Current state
        self.cash = initial_capital
        self.positions: Dict[str, PortfolioPosition] = {}
        self.closed_trades: List[Trade] = []

        # Risk tracking
        self.current_portfolio_risk = Decimal("0")

    def get_current_state(self, timestamp: datetime, prices: Dict[str, Decimal]) -> PortfolioState:
        """Get current portfolio state.

        Args:
            timestamp: Current timestamp
            prices: Current prices for all symbols {symbol: price}

        Returns:
            PortfolioState snapshot
        """
        total_position_value = Decimal("0")

        for symbol, portfolio_pos in self.positions.items():
            price = prices.get(symbol, portfolio_pos.position.entry_price)
            total_position_value += portfolio_pos.position.market_value(price)

        total_equity = self.cash + total_position_value
        available_capital = total_equity - total_position_value

        return PortfolioState(
            timestamp=timestamp,
            cash=self.cash,
            positions=self.positions.copy(),
            total_equity=total_equity,
            total_position_value=total_position_value,
            available_capital=available_capital,
        )

    def can_open_position(
        self,
        symbol: str,
        risk_amount: Decimal,
    ) -> tuple[bool, str | None]:
        """Check if new position can be opened.

        Args:
            symbol: Symbol for new position
            risk_amount: Risk amount in dollars

        Returns:
            Tuple of (can_open, reason)
            - can_open: True if position can be opened
            - reason: Explanation if cannot open
        """
        # Check if already in position
        if symbol in self.positions:
            return (False, f"Already holding position in {symbol}")

        # Check position limit
        if len(self.positions) >= self.max_positions:
            return (False, f"Maximum positions reached ({self.max_positions})")

        # Check portfolio risk limit
        new_total_risk = self.current_portfolio_risk + risk_amount
        max_risk_allowed = self.initial_capital * self.max_portfolio_risk_pct

        if new_total_risk > max_risk_allowed:
            return (
                False,
                f"Portfolio risk limit exceeded "
                f"(current: {self.current_portfolio_risk:.2f}, "
                f"new: {risk_amount:.2f}, "
                f"max: {max_risk_allowed:.2f})",
            )

        # Check available capital
        if self.cash <= 0:
            return (False, "No available capital")

        return (True, None)

    def calculate_position_size(
        self,
        symbol: str,
        entry_price: Decimal,
        stop_loss: Decimal,
        direction: int,  # 1 for long, -1 for short
    ) -> tuple[Decimal, Decimal]:
        """Calculate position size based on portfolio risk.

        Args:
            symbol: Symbol to trade
            entry_price: Entry price
            stop_loss: Stop loss price
            direction: 1 for long, -1 for short

        Returns:
            Tuple of (quantity, risk_amount)
            - quantity: Number of shares/contracts
            - risk_amount: Dollar risk allocated
        """
        # Calculate risk per unit
        risk_per_unit = abs(entry_price - stop_loss)
        if risk_per_unit == 0:
            return (Decimal("0"), Decimal("0"))

        # Calculate portfolio risk budget for this trade
        current_equity = self.cash + sum(
            pos.position.market_value(pos.position.entry_price)
            for pos in self.positions.values()
        )

        risk_budget = current_equity * self.risk_per_trade_pct

        # Calculate quantity based on risk
        quantity = risk_budget / risk_per_unit

        # Ensure we don't exceed available capital
        notional_value = quantity * entry_price
        max_affordable = self.cash / entry_price if entry_price > 0 else Decimal("0")

        if quantity > max_affordable:
            quantity = max_affordable
            risk_budget = quantity * risk_per_unit

        # Round to whole shares
        quantity = quantity.quantize(Decimal("1"))

        return (quantity, risk_budget)

    def open_position(
        self,
        symbol: str,
        side: PositionSide,
        quantity: Decimal,
        entry_price: Decimal,
        entry_time: datetime,
        stop_loss: Decimal | None = None,
        target: Decimal | None = None,
        metadata: Dict[str, any] | None = None,
    ) -> PortfolioPosition:
        """Open new position.

        Args:
            symbol: Symbol to trade
            side: LONG or SHORT
            quantity: Position size
            entry_price: Entry price
            entry_time: Entry timestamp
            stop_loss: Stop loss price (optional)
            target: Target price (optional)
            metadata: Additional metadata (optional)

        Returns:
            PortfolioPosition opened

        Raises:
            ValueError: If position cannot be opened
        """
        # Calculate risk
        risk_amount = Decimal("0")
        if stop_loss is not None:
            risk_amount = abs(entry_price - stop_loss) * quantity

        # Check if can open
        can_open, reason = self.can_open_position(symbol, risk_amount)
        if not can_open:
            raise ValueError(f"Cannot open position: {reason}")

        # Open position using executor (applies slippage and calculates commission)
        position, commission = self.executor.open_position(
            symbol=symbol,
            side=side,
            quantity=quantity,
            entry_price=entry_price,
            entry_time=entry_time,
            metadata=metadata,
            stop_loss=stop_loss,
            take_profit=target,  # target parameter maps to take_profit
        )

        # Deduct capital
        notional_value = quantity * position.entry_price
        cost = notional_value + commission
        if cost > self.cash:
            raise ValueError(f"Insufficient capital: need {cost}, have {self.cash}")

        self.cash -= cost

        portfolio_position = PortfolioPosition(
            position=position,
            risk_amount=risk_amount,
            stop_loss=stop_loss,
            target=target,
            metadata=metadata or {},
        )

        self.positions[symbol] = portfolio_position
        self.current_portfolio_risk += risk_amount

        return portfolio_position

    def close_position(
        self,
        symbol: str,
        exit_price: Decimal,
        exit_time: datetime,
    ) -> Trade:
        """Close existing position.

        Args:
            symbol: Symbol to close
            exit_price: Exit price
            exit_time: Exit timestamp

        Returns:
            Trade record

        Raises:
            ValueError: If no position exists
        """
        if symbol not in self.positions:
            raise ValueError(f"No position exists for {symbol}")

        portfolio_pos = self.positions[symbol]
        position = portfolio_pos.position

        # Close position using executor (applies slippage and calculates P&L)
        trade = self.executor.close_position(
            position=position,
            exit_price=exit_price,
            exit_time=exit_time,
        )

        # Return capital
        exit_notional = position.quantity * trade.exit_price
        exit_commission = trade.commission_paid - position.entry_commission
        proceeds = exit_notional - exit_commission
        self.cash += proceeds

        # Remove position and update risk
        self.current_portfolio_risk -= portfolio_pos.risk_amount
        del self.positions[symbol]
        self.closed_trades.append(trade)

        return trade

    def update_positions(self, timestamp: datetime, prices: Dict[str, Decimal]) -> None:
        """Update all positions with current prices.

        Args:
            timestamp: Current timestamp
            prices: Current prices {symbol: price}
        """
        for symbol, portfolio_pos in self.positions.items():
            if symbol in prices:
                portfolio_pos.update_excursions(prices[symbol])


__all__ = [
    "PortfolioPositionManager",
    "PortfolioPosition",
    "PortfolioState",
]
