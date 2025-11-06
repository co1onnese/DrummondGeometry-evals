from datetime import datetime, timezone

import pytest

from dgas.calculations.pldot import PLDotCalculator
from dgas.data.models import IntervalData


def _make_interval(ts: datetime, high: float, low: float, close: float) -> IntervalData:
    payload = {
        "code": "AAPL",
        "exchange_short_name": "US",
        "timestamp": int(ts.timestamp()),
        "open": close,
        "high": high,
        "low": low,
        "close": close,
        "volume": 1,
    }
    return IntervalData.from_api_record(payload, interval="30m")


def test_pldot_calculator_requires_three_points():
    calc = PLDotCalculator()
    ts = datetime(2024, 1, 1, tzinfo=timezone.utc)
    intervals = [_make_interval(ts, 1, 1, 1), _make_interval(ts, 1, 1, 1)]

    with pytest.raises(ValueError):
        calc.from_intervals(intervals)


def test_pldot_calculator_basic_sequence():
    calc = PLDotCalculator(displacement=1)
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    intervals = [
        _make_interval(base, 10, 8, 9),
        _make_interval(base.replace(hour=1), 11, 9, 10),
        _make_interval(base.replace(hour=2), 12, 10, 11),
        _make_interval(base.replace(hour=3), 13, 11, 12),
    ]

    results = calc.from_intervals(intervals)
    assert len(results) == 1
    assert results[0].projected_timestamp == intervals[3].timestamp
    assert round(float(results[0].value), 6) == pytest.approx(10.0)


def test_pldot_calculator_displacement_two():
    calc = PLDotCalculator(displacement=2)
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    intervals = [
        _make_interval(base, 10, 8, 9),
        _make_interval(base.replace(hour=1), 11, 9, 10),
        _make_interval(base.replace(hour=2), 12, 10, 11),
        _make_interval(base.replace(hour=3), 13, 11, 12),
        _make_interval(base.replace(hour=4), 14, 12, 13),
    ]

    results = calc.from_intervals(intervals)
    assert len(results) == 1
    assert results[0].projected_timestamp == intervals[4].timestamp
