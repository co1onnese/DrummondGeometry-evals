from datetime import datetime, timedelta, timezone

from dgas.calculations.drummond_lines import (
    DrummondLineCalculator,
    aggregate_zones,
)
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


def _sample_intervals():
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    return [
        _make_interval(base + timedelta(minutes=30 * i), 10 + i, 8 + i, 9 + i)
        for i in range(5)
    ]


def test_drummond_lines_basic():
    intervals = _sample_intervals()
    calc = DrummondLineCalculator()
    lines = calc.from_intervals(intervals)

    assert len(lines) == (len(intervals) - 1) * 2
    first_resistance = lines[0]
    assert first_resistance.line_type == "resistance"
    assert first_resistance.projected_timestamp == intervals[2].timestamp


def test_zone_aggregation():
    intervals = _sample_intervals()
    calc = DrummondLineCalculator()
    lines = calc.from_intervals(intervals)

    zones = aggregate_zones(lines, tolerance=0.5)
    assert zones
    total_strength = sum(zone.strength for zone in zones)
    assert total_strength == len(lines)
