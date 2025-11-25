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
        if value is None:
            return 0
        return int(value)

    @classmethod
    def _parse_timestamp_to_utc(cls, value: Any) -> datetime:
        """Parse timestamp from API and convert to UTC.

        EODHD API returns timestamps in Europe/Prague timezone.
        This ensures all timestamps are stored in UTC.

        Args:
            value: Timestamp value (string, datetime, int, float, etc.)

        Returns:
            UTC datetime
        """
        from datetime import timezone
        from zoneinfo import ZoneInfo

        if value is None:
            raise ValueError("Timestamp is required")

        # If it's already a datetime, ensure it's in UTC
        if isinstance(value, datetime):
            # If timezone-aware, convert to UTC
            if value.tzinfo is not None:
                return value.astimezone(timezone.utc)
            # If naive, assume it's in Europe/Prague and convert to UTC
            else:
                return value.replace(tzinfo=ZoneInfo("Europe/Prague")).astimezone(timezone.utc)

        # Handle integer/float timestamps (Unix timestamp)
        if isinstance(value, (int, float)):
            # EODHD timestamps are in seconds or milliseconds depending on endpoint
            if value > 10**12:
                value = value / 1000.0
            # Convert Unix timestamp to UTC datetime
            dt = datetime.fromtimestamp(float(value), tz=timezone.utc)
            return dt

        # If it's a string, parse and convert
        if isinstance(value, str):
            dt = datetime.fromisoformat(value)
            # If no timezone info, assume Europe/Prague
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=ZoneInfo("Europe/Prague"))
            # Convert to UTC
            return dt.astimezone(timezone.utc)

        raise TypeError(f"Unsupported timestamp type: {type(value)}")

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

        # Normalize symbol: remove .US suffix and convert to uppercase
        # EODHD API uses unified "US" exchange code, so we strip the suffix
        if symbol.endswith(".US"):
            symbol = symbol[:-3]
        symbol = symbol.upper()

        timestamp_raw = record.get("timestamp") or record.get("datetime") or record.get("date")

        # Extract OHLC values
        open_val = record.get("open")
        high_val = record.get("high")
        low_val = record.get("low")
        close_val = record.get("close")
        
        # Validate that all required OHLC values are present
        # Some API records may have None values (e.g., incomplete bars, errors)
        if open_val is None or high_val is None or low_val is None or close_val is None:
            raise ValueError(
                f"API record missing required OHLC data for {symbol}: "
                f"open={open_val}, high={high_val}, low={low_val}, close={close_val}"
            )

        data = {
            "symbol": symbol,
            "exchange": "US",  # Always use "US" as unified exchange code for EODHD
            "timestamp": cls._parse_timestamp_to_utc(timestamp_raw),
            "interval": interval,
            "open": open_val,
            "high": high_val,
            "low": low_val,
            "close": close_val,
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
        """Parse list of API records, skipping records with invalid data."""
        import logging
        logger = logging.getLogger(__name__)
        
        # Convert to list to allow multiple iterations and get total count
        records_list = list(records)
        total_records = len(records_list)
        
        result = []
        skipped = 0
        skipped_reasons = {}
        
        for rec in records_list:
            try:
                result.append(cls.from_api_record(rec, interval, symbol_override=symbol_override))
            except ValueError as e:
                # Skip records with missing/invalid OHLC data
                skipped += 1
                # Track reasons for skipping
                error_msg = str(e)
                if "missing required OHLC" in error_msg:
                    # Extract which fields are missing
                    if "open" in error_msg.lower():
                        skipped_reasons["missing_open"] = skipped_reasons.get("missing_open", 0) + 1
                    if "high" in error_msg.lower():
                        skipped_reasons["missing_high"] = skipped_reasons.get("missing_high", 0) + 1
                    if "low" in error_msg.lower():
                        skipped_reasons["missing_low"] = skipped_reasons.get("missing_low", 0) + 1
                    if "close" in error_msg.lower():
                        skipped_reasons["missing_close"] = skipped_reasons.get("missing_close", 0) + 1
                else:
                    skipped_reasons["other"] = skipped_reasons.get("other", 0) + 1
                
                # Log at debug level to avoid spam, but track skipped records
                logger.debug(f"Skipping invalid API record: {e}")
        
        if skipped > 0:
            skip_rate = (skipped / total_records * 100) if total_records > 0 else 0
            # Only warn if skip rate is significant (>5%) or absolute count is high (>100)
            if skip_rate > 5.0 or skipped > 100:
                reason_summary = ", ".join([f"{k}: {v}" for k, v in skipped_reasons.items()])
                logger.warning(
                    f"Skipped {skipped} records with invalid OHLC data out of {total_records} total "
                    f"({skip_rate:.1f}% skip rate). Reasons: {reason_summary if reason_summary else 'unknown'}"
                )
            else:
                # Lower log level for small numbers of skipped records (likely market closure)
                logger.debug(
                    f"Skipped {skipped} records with invalid OHLC data out of {total_records} total "
                    f"({skip_rate:.1f}% skip rate). This is normal for market closure periods."
                )
        
        return result


__all__ = ["IntervalData"]
