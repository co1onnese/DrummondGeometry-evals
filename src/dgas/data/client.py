"""HTTP client for the EODHD API."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

import requests

from ..settings import Settings, get_settings
from .errors import (
    EODHDAuthError,
    EODHDError,
    EODHDParsingError,
    EODHDRequestError,
    EODHDRateLimitError,
)
from .models import IntervalData
from .rate_limiter import RateLimiter

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class EODHDConfig:
    api_token: str
    base_url: str = "https://eodhd.com/api"
    requests_per_minute: int = 80
    timeout: float = 30.0
    max_retries: int = 3
    session: Optional[requests.Session] = None

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "EODHDConfig":
        settings = settings or get_settings()
        if not settings.eodhd_api_token:
            raise ValueError("EODHD_API_TOKEN is not configured")
        return cls(
            api_token=settings.eodhd_api_token,
            requests_per_minute=settings.eodhd_requests_per_minute,
        )


class EODHDClient:
    """Synchronous client for retrieving data from EODHD."""

    def __init__(self, config: EODHDConfig) -> None:
        self._config = config
        self._session = config.session or requests.Session()
        self._rate_limiter = RateLimiter(config.requests_per_minute, 60.0)

    def close(self) -> None:
        self._session.close()

    def fetch_intraday(
        self,
        symbol: str,
        start: str | None = None,
        end: str | None = None,
        interval: str = "30m",
        limit: int = 50000,
        exchange: str = "US",
    ) -> List[IntervalData]:
        params: Dict[str, Any] = {
            "api_token": self._config.api_token,
            "fmt": "json",
            "interval": interval,
            "limit": limit,
        }
        if start is not None:
            params["from"] = _coerce_time_param(start)
        if end is not None:
            params["to"] = _coerce_time_param(end)

        # EODHD API requires {SYMBOL}.{EXCHANGE} format for US stocks
        # Add .US suffix if exchange is US and symbol doesn't already have it
        if exchange == "US" and not symbol.endswith(".US"):
            api_symbol = f"{symbol}.US"
        else:
            api_symbol = symbol

        path = f"intraday/{api_symbol}"
        payload = self._request(path, params)
        if not isinstance(payload, list):
            raise EODHDParsingError("unexpected response format from intraday endpoint")
        return IntervalData.from_api_list(payload, interval, symbol_override=symbol)

    def fetch_eod(
        self,
        symbol: str,
        start: str | None = None,
        end: str | None = None,
        exchange: str = "US",
    ) -> List[IntervalData]:
        params: Dict[str, Any] = {
            "api_token": self._config.api_token,
            "fmt": "json",
        }
        if start is not None:
            params["from"] = _coerce_date_param(start)
        if end is not None:
            params["to"] = _coerce_date_param(end)

        # EODHD API requires {SYMBOL}.{EXCHANGE} format for US stocks
        # Add .US suffix if exchange is US and symbol doesn't already have it
        if exchange == "US" and not symbol.endswith(".US"):
            api_symbol = f"{symbol}.US"
        else:
            api_symbol = symbol

        path = f"eod/{api_symbol}"
        payload = self._request(path, params)
        if not isinstance(payload, list):
            raise EODHDParsingError("unexpected response format from eod endpoint")
        return IntervalData.from_api_list(payload, "1d", symbol_override=symbol)

    def fetch_live_ohlcv(
        self,
        symbol: str,
        interval: str = "5m",
        exchange: str = "US",
    ) -> List[IntervalData]:
        """
        Fetch live/realtime OHLCV data for today.
        
        Uses EODHD's realtime endpoint for same-day data.
        This is faster and more up-to-date than historical intraday.
        
        Note: EODHD API only supports 1m, 5m, and 1h intervals.
        If 30m is requested, this will fetch 5m data (caller should aggregate).
        
        Args:
            symbol: Stock symbol
            interval: Data interval (1m, 5m, 1h) - default 5m
            exchange: Exchange code (default: "US")
            
        Returns:
            List of IntervalData for today
        """
        # EODHD API only supports 1m, 5m, 1h
        # If 30m requested, use 5m (caller should aggregate)
        if interval == "30m":
            interval = "5m"
        params: Dict[str, Any] = {
            "api_token": self._config.api_token,
            "fmt": "json",
            "interval": interval,
        }
        
        # EODHD API requires {SYMBOL}.{EXCHANGE} format for US stocks
        # Add .US suffix if exchange is US and symbol doesn't already have it
        if exchange == "US" and not symbol.endswith(".US"):
            api_symbol = f"{symbol}.US"
        else:
            api_symbol = symbol
        
        # Use realtime endpoint for live data
        path = f"real-time/{api_symbol}"
        payload = self._request(path, params)
        
        # Realtime endpoint may return single object or list
        if isinstance(payload, dict):
            # Single bar - convert to list
            payload = [payload]
        elif not isinstance(payload, list):
            raise EODHDParsingError("unexpected response format from realtime endpoint")
        
        return IntervalData.from_api_list(payload, interval, symbol_override=symbol)

    def list_exchange_symbols(self, exchange: str = "US") -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {
            "api_token": self._config.api_token,
            "fmt": "json",
        }
        path = f"exchange-symbols/{exchange}"
        payload = self._request(path, params)
        if not isinstance(payload, list):
            raise EODHDParsingError("unexpected response for exchange symbols")
        return payload

    def _request(self, path: str, params: Dict[str, Any]) -> Any:
        url = f"{self._config.base_url.rstrip('/')}/{path.lstrip('/')}"
        backoff = 1.0

        for attempt in range(1, self._config.max_retries + 1):
            self._rate_limiter.acquire()

            try:
                response = self._session.get(url, params=params, timeout=self._config.timeout)
            except requests.RequestException as exc:  # pragma: no cover - network failure
                if attempt == self._config.max_retries:
                    raise EODHDRequestError(f"request failed after retries: {exc}") from exc
                LOGGER.warning("Network error contacting EODHD (attempt %s/%s)", attempt, self._config.max_retries)
                time.sleep(backoff)
                backoff *= 2
                continue

            if response.status_code == 200:
                payload = response.json()
                # Log empty responses for debugging
                if isinstance(payload, list) and len(payload) == 0:
                    LOGGER.warning(
                        f"EODHD API returned empty array for {path} with params {params}. "
                        f"URL was: {url}. Response text: {response.text[:200]}"
                    )
                return payload

            if response.status_code == 401:
                raise EODHDAuthError("EODHD API authentication failed")

            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After")
                wait_seconds = float(retry_after) if retry_after else backoff
                LOGGER.warning("Rate limited by EODHD, sleeping for %.2f seconds", wait_seconds)
                time.sleep(wait_seconds)
                backoff = min(backoff * 2, 60)
                if attempt == self._config.max_retries:
                    raise EODHDRateLimitError("rate limited after maximum retries")
                continue

            if 500 <= response.status_code < 600:
                if attempt == self._config.max_retries:
                    raise EODHDRequestError(
                        f"EODHD server error ({response.status_code}) after retries"
                    )
                LOGGER.warning(
                    "EODHD server error %s on %s (attempt %s/%s)",
                    response.status_code,
                    url,
                    attempt,
                    self._config.max_retries,
                )
                time.sleep(backoff)
                backoff = min(backoff * 2, 60)
                continue

            # Log the full URL and response for debugging
            LOGGER.error(
                f"Unexpected EODHD response: {response.status_code} for {url} with params {params}. "
                f"Response: {response.text[:500]}"
            )
            raise EODHDRequestError(
                f"Unexpected EODHD response: {response.status_code} - {response.text[:200]}"
            )

        raise EODHDError("Exhausted retries without success")


def _coerce_time_param(value: Any) -> int:
    """Convert various input types to epoch seconds for intraday requests."""

    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, datetime):
        return int(value.timestamp())
    if isinstance(value, date):
        dt = datetime.combine(value, datetime.min.time(), tzinfo=timezone.utc)
        return int(dt.timestamp())
    if isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(f"Unable to parse datetime string '{value}'") from exc
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    raise TypeError(f"Unsupported intraday time parameter type: {type(value)!r}")


def _coerce_date_param(value: Any) -> str:
    """Ensure date parameters for EOD endpoint are ISO date strings."""

    if isinstance(value, str):
        return value
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    raise TypeError(f"Unsupported date parameter type: {type(value)!r}")


__all__ = ["EODHDClient", "EODHDConfig"]
