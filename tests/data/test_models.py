from decimal import Decimal

import pytest

from dgas.data.models import IntervalData


def test_interval_data_from_api_record_parses_fields() -> None:
    record = {
        "code": "AAPL",
        "exchange_short_name": "US",
        "timestamp": 1_700_000_000,
        "open": "100.5",
        "high": "101.0",
        "low": "99.5",
        "close": "100.0",
        "adjusted_close": "100.1",
        "volume": 123456,
    }

    interval = IntervalData.from_api_record(record, interval="30m")

    assert interval.symbol == "AAPL"
    assert interval.exchange == "US"
    assert interval.interval == "30m"
    assert interval.timestamp.isoformat() == "2023-11-14T22:13:20+00:00"
    assert interval.open == Decimal("100.5")
    assert interval.volume == 123456


def test_interval_data_requires_timestamp() -> None:
    record = {
        "code": "AAPL",
        "open": 1,
        "high": 1,
        "low": 1,
        "close": 1,
        "volume": 0,
    }

    with pytest.raises(ValueError):
        IntervalData.from_api_record(record, interval="30m")
