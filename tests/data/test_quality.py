from datetime import datetime, timedelta, timezone

from dgas.data.models import IntervalData
from dgas.data.quality import analyze_intervals


def _make_interval(ts: datetime) -> IntervalData:
    payload = {
        "code": "AAPL",
        "exchange_short_name": "US",
        "timestamp": int(ts.timestamp()),
        "open": 100,
        "high": 101,
        "low": 99,
        "close": 100,
        "volume": 10,
    }
    return IntervalData.from_api_record(payload, interval="30m")


def test_analyze_intervals_detects_duplicates_and_gaps() -> None:
    base = datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc)
    intervals = [
        _make_interval(base),
        _make_interval(base + timedelta(minutes=30)),
        _make_interval(base + timedelta(minutes=90)),  # gap of 60 minutes
        _make_interval(base + timedelta(minutes=90)),  # duplicate timestamp
    ]

    report = analyze_intervals(intervals)

    assert report.total_bars == 4
    assert report.gap_count == 1
    assert report.duplicate_count == 1
    assert report.is_chronological
    assert report.notes
