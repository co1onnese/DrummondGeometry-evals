"""Base trade executor with shared execution logic.

Extracts common position management logic to eliminate duplication
between SimulationEngine and PortfolioPositionManager.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_DOWN

from ..entities import Position, PositionSide, Trade

BASIS_POINT = Decimal("10000")
QUANTITY_STEP = Decimal("0.0001")


@dataclass
class TradeExecutionResult:
    """Result of executing a trade."""

    trade: Trade | None
    new_position: Position | None
    cash_change: Decimal
    commission_paid: Decimal


class BaseTradeExecutor:
    """Base class for trade execution with shared logic.

    Provides unified implementation of:
    - Slippage calculation
    - Commission calculation
    - P&L calculation
    - Position opening/closing

    Subclasses can override methods to customize behavior for
    single-symbol vs portfolio contexts.
    """

    def __init__(
        self,
        commission_rate: Decimal = Decimal("0.0"),
        slippage_bps: Decimal = Decimal("0.0"),
    ):
        """Initialize trade executor.

        Args:
            commission_rate: Commission rate (decimal, e.g., 0.001 = 0.1%)
            slippage_bps: Slippage in basis points
        """
        self.commission_rate = commission_rate
        self.slippage_bps = slippage_bps

    def apply_slippage(
        self,
        price: Decimal,
        side: PositionSide,
        *,
        is_entry: bool,
    ) -> Decimal:
        """Apply slippage to a price.

        Args:
            price: Base price
            side: Position side (LONG or SHORT)
            is_entry: True for entry, False for exit

        Returns:
            Price with slippage applied
        """
        if self.slippage_bps <= 0:
            return price

        fraction = self.slippage_bps / BASIS_POINT
        adjustment = price * fraction

        if side is PositionSide.LONG:
            return price + adjustment if is_entry else price - adjustment
        return price - adjustment if is_entry else price + adjustment

    def compute_commission(
        self,
        quantity: Decimal,
        price: Decimal,
    ) -> Decimal:
        """Calculate commission for a trade.

        Args:
            quantity: Number of shares/contracts
            price: Price per unit

        Returns:
            Commission amount
        """
        if self.commission_rate <= 0:
            return Decimal("0")
        return abs(quantity * price) * self.commission_rate

    def calculate_gross_profit(
        self,
        position: Position,
        exit_price: Decimal,
    ) -> Decimal:
        """Calculate gross profit/loss for closing a position.

        Args:
            position: Position to close
            exit_price: Exit price

        Returns:
            Gross profit (positive) or loss (negative)
        """
        return position.direction() * position.quantity * (exit_price - position.entry_price)

    def calculate_net_profit(
        self,
        position: Position,
        exit_price: Decimal,
        exit_commission: Decimal,
    ) -> Decimal:
        """Calculate net profit/loss after commissions.

        Args:
            position: Position to close
            exit_price: Exit price
            exit_commission: Commission for exit trade

        Returns:
            Net profit (positive) or loss (negative)
        """
        gross_profit = self.calculate_gross_profit(position, exit_price)
        total_commission = position.entry_commission + exit_commission
        return gross_profit - total_commission

    def normalize_quantity(self, quantity: Decimal) -> Decimal:
        """Normalize quantity to valid step size.

        Args:
            quantity: Raw quantity

        Returns:
            Normalized quantity
        """
        if quantity <= 0:
            return Decimal("0")
        return quantity.quantize(QUANTITY_STEP, rounding=ROUND_DOWN)

    def open_position(
        self,
        symbol: str,
        side: PositionSide,
        quantity: Decimal,
        entry_price: Decimal,
        entry_time: datetime,
        metadata: dict | None = None,
        stop_loss: Decimal | None = None,
        take_profit: Decimal | None = None,
    ) -> tuple[Position, Decimal]:
        """Open a new position.

        Args:
            symbol: Symbol to trade
            side: LONG or SHORT
            quantity: Position size (already normalized)
            entry_price: Entry price (before slippage)
            entry_time: Entry timestamp
            metadata: Optional metadata
            stop_loss: Optional stop-loss price level
            take_profit: Optional take-profit price level
            confidence: Optional signal confidence (0.0-1.0)

        Returns:
            Tuple of (Position, commission_paid)
        """
        # Apply slippage
        fill_price = self.apply_slippage(entry_price, side, is_entry=True)

        # Calculate commission
        commission = self.compute_commission(quantity, fill_price)

        # Extract stop_loss/take_profit/confidence from metadata if not provided directly
        # Check multiple possible keys for compatibility
        confidence_value = None  # Initialize confidence variable
        if metadata:
            if stop_loss is None:
                stop_loss_str = metadata.get("stop_loss") or metadata.get("trail_stop")
                if stop_loss_str:
                    if isinstance(stop_loss_str, str):
                        stop_loss = Decimal(stop_loss_str)
                    else:
                        stop_loss = Decimal(str(stop_loss_str))
            
            if take_profit is None:
                take_profit_str = metadata.get("take_profit") or metadata.get("target")
                if take_profit_str:
                    if isinstance(take_profit_str, str):
                        take_profit = Decimal(take_profit_str)
                    else:
                        take_profit = Decimal(str(take_profit_str))
            
            # Extract confidence from metadata
            confidence_str = metadata.get("confidence")
            if confidence_str:
                if isinstance(confidence_str, str):
                    confidence_value = Decimal(confidence_str)
                else:
                    confidence_value = Decimal(str(confidence_str))

        # Create position
        position = Position(
            symbol=symbol,
            side=side,
            quantity=quantity,
            entry_price=fill_price,
            entry_time=entry_time,
            entry_commission=commission,
            stop_loss=stop_loss,
            take_profit=take_profit,
            confidence=confidence_value,
            notes=metadata or {},
        )

        return position, commission

    def close_position(
        self,
        position: Position,
        exit_price: Decimal,
        exit_time: datetime,
    ) -> Trade:
        """Close an existing position.

        Args:
            position: Position to close
            exit_price: Exit price (before slippage)
            exit_time: Exit timestamp

        Returns:
            Trade record
        """
        # Apply slippage
        fill_price = self.apply_slippage(exit_price, position.side, is_entry=False)

        # Calculate commission
        exit_commission = self.compute_commission(position.quantity, fill_price)

        # Calculate P&L
        gross_profit = self.calculate_gross_profit(position, fill_price)
        net_profit = self.calculate_net_profit(position, fill_price, exit_commission)

        # Create trade record
        trade = Trade(
            symbol=position.symbol,
            side=position.side,
            quantity=position.quantity,
            entry_time=position.entry_time,
            exit_time=exit_time,
            entry_price=position.entry_price,
            exit_price=fill_price,
            gross_profit=gross_profit,
            net_profit=net_profit,
            commission_paid=position.entry_commission + exit_commission,
        )

        return trade


__all__ = ["BaseTradeExecutor", "TradeExecutionResult", "BASIS_POINT", "QUANTITY_STEP"]
