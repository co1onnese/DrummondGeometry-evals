"""Data models for EODHD responses."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Iterable, List

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _parse_timestamp(value: Any) -> datetime:
    if value is None:
        raise ValueError("timestamp is required")

    # Handle datetime objects (from database or API)
    if isinstance(value, datetime):
        # Ensure timezone is set
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value

    if isinstance(value, (int, float)):
        # EODHD timestamps are in seconds or milliseconds depending on endpoint.
        if value > 10**12:
            value = value / 1000.0
        return datetime.fromtimestamp(float(value), tz=timezone.utc)

    if isinstance(value, str):
        try:
            # EODHD returns ISO-like strings without timezone.
            dt = datetime.fromisoformat(value)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError as exc:  # pragma: no cover - defensive
            raise ValueError(f"invalid timestamp string: {value}") from exc

    raise TypeError(f"unsupported timestamp type: {type(value)!r}")


class IntervalData(BaseModel):
    """Normalized OHLCV interval."""

    symbol: str = Field(..., description="Ticker symbol, e.g. AAPL")
    exchange: str | None = Field(None, description="Exchange short name from API")
    timestamp: datetime = Field(..., description="UTC timestamp for the bar")
    interval: str = Field(..., description="Interval string such as '30m'")
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    adjusted_close: Decimal | None = None
    volume: int

    model_config = ConfigDict(frozen=True)

    @field_validator("timestamp", mode="before")
    @classmethod
    def _ensure_timestamp(cls, value: Any) -> datetime:  # noqa: D417
        return _parse_timestamp(value)

    @field_validator("open", "high", "low", "close", "adjusted_close", mode="before")
    @classmethod
    def _to_decimal(cls, value: Any) -> Decimal | None:  # noqa: D417
        if value is None:
            return None
        return Decimal(str(value))

    @field_validator("volume", mode="before")
    @classmethod
    def _to_int(cls, value: Any) -> int:  # noqa: D417
        return int(value)

    @classmethod
    def from_api_record(
        cls,
        record: Dict[str, Any],
        interval: str,
        symbol_override: str | None = None,
    ) -> "IntervalData":
        symbol = symbol_override or record.get("code") or record.get("symbol")
        if not symbol:
            raise ValueError("API record missing symbol identifier")

        data = {
            "symbol": symbol,
            "exchange": record.get("exchange_short_name"),
            "timestamp": record.get("timestamp") or record.get("datetime") or record.get("date"),
            "interval": interval,
            "open": record.get("open"),
            "high": record.get("high"),
            "low": record.get("low"),
            "close": record.get("close"),
            "adjusted_close": record.get("adjusted_close"),
            "volume": record.get("volume", 0),
        }
        return cls(**data)

    @classmethod
    def from_api_list(
        cls,
        records: Iterable[Dict[str, Any]],
        interval: str,
        symbol_override: str | None = None,
    ) -> List["IntervalData"]:
        return [cls.from_api_record(rec, interval, symbol_override=symbol_override) for rec in records]


__all__ = ["IntervalData"]
