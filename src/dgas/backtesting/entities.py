"""Core domain entities for the backtesting engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Mapping


DecimalLike = Decimal | int | float | str


def _to_decimal(value: DecimalLike) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


class PositionSide(Enum):
    """Directional side of an open position."""

    LONG = "long"
    SHORT = "short"


class SignalAction(Enum):
    """Supported signal actions emitted by strategies."""

    ENTER_LONG = "enter_long"
    EXIT_LONG = "exit_long"
    ENTER_SHORT = "enter_short"
    EXIT_SHORT = "exit_short"
    LIQUIDATE = "liquidate"


@dataclass(frozen=True)
class Signal:
    """Strategy directive evaluated by the simulation engine."""

    action: SignalAction
    size: Decimal | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def resolved_size(self, fallback: Decimal) -> Decimal:
        return fallback if self.size is None else _to_decimal(self.size)


@dataclass
class Position:
    """Represents an open market position."""

    symbol: str
    side: PositionSide
    quantity: Decimal
    entry_price: Decimal
    entry_time: datetime
    entry_commission: Decimal = Decimal("0")
    notes: Mapping[str, Any] = field(default_factory=dict)

    def direction(self) -> Decimal:
        return Decimal("1") if self.side is PositionSide.LONG else Decimal("-1")

    def market_value(self, price: Decimal) -> Decimal:
        return self.direction() * self.quantity * price

    def unrealized_pnl(self, price: Decimal) -> Decimal:
        return self.direction() * self.quantity * (price - self.entry_price)


@dataclass(frozen=True)
class Trade:
    """Completed trade produced by the simulation."""

    symbol: str
    side: PositionSide
    quantity: Decimal
    entry_time: datetime
    exit_time: datetime
    entry_price: Decimal
    exit_price: Decimal
    gross_profit: Decimal
    net_profit: Decimal
    commission_paid: Decimal


@dataclass(frozen=True)
class PortfolioSnapshot:
    """Point-in-time account valuation used for equity curves."""

    timestamp: datetime
    equity: Decimal
    cash: Decimal


@dataclass(frozen=True)
class SimulationConfig:
    """Configuration for a single backtest run."""

    initial_capital: Decimal = Decimal("100000")
    commission_rate: Decimal = Decimal("0.0")  # applied to notional value per trade leg
    slippage_bps: Decimal = Decimal("0.0")  # basis-points applied to fills
    allow_short: bool = False
    max_position_fraction: Decimal = Decimal("1.0")  # max fraction of current equity to allocate

    def __post_init__(self) -> None:
        object.__setattr__(self, "initial_capital", _to_decimal(self.initial_capital))
        object.__setattr__(self, "commission_rate", _to_decimal(self.commission_rate))
        object.__setattr__(self, "slippage_bps", _to_decimal(self.slippage_bps))
        object.__setattr__(self, "max_position_fraction", _to_decimal(self.max_position_fraction))


@dataclass
class BacktestResult:
    """Aggregate output of a simulation run."""

    symbol: str
    strategy_name: str
    config: SimulationConfig
    trades: list[Trade]
    equity_curve: list[PortfolioSnapshot]
    starting_cash: Decimal
    ending_cash: Decimal
    ending_equity: Decimal
    metadata: Mapping[str, Any] = field(default_factory=dict)

