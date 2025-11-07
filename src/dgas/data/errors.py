"""Custom exceptions for EODHD data access."""

class EODHDError(Exception):
    """Base class for EODHD client errors."""


class EODHDAuthError(EODHDError):
    """Raised on authentication failures."""


class EODHDRateLimitError(EODHDError):
    """Raised when rate limiting persists after retries."""


class EODHDRequestError(EODHDError):
    """Raised on non-success responses from the API."""


class EODHDParsingError(EODHDError):
    """Raised when API responses cannot be parsed into expected models."""


__all__ = [
    "EODHDError",
    "EODHDAuthError",
    "EODHDRateLimitError",
    "EODHDRequestError",
    "EODHDParsingError",
]
