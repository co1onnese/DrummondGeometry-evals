"""Data quality analysis for market data ingestion."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Iterable, Sequence

from .models import IntervalData


INTERVAL_SECONDS = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "4h": 4 * 3600,
    "1d": 86400,
}


@dataclass
class DataQualityReport:
    symbol: str
    interval: str
    total_bars: int
    duplicate_count: int
    gap_count: int
    is_chronological: bool
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "symbol": self.symbol,
            "interval": self.interval,
            "total_bars": self.total_bars,
            "duplicate_count": self.duplicate_count,
            "gap_count": self.gap_count,
            "is_chronological": self.is_chronological,
            "notes": list(self.notes),
        }


def analyze_intervals(intervals: Sequence[IntervalData]) -> DataQualityReport:
    if not intervals:
        return DataQualityReport(
            symbol="",
            interval="",
            total_bars=0,
            duplicate_count=0,
            gap_count=0,
            is_chronological=True,
            notes=["no data"],
        )

    symbol = intervals[0].symbol
    interval = intervals[0].interval

    timestamps = [row.timestamp for row in intervals]
    is_chrono = all(earlier <= later for earlier, later in zip(timestamps, timestamps[1:]))
    duplicate_count = len(timestamps) - len(set(timestamps))

    gap_count = 0
    notes: list[str] = []
    expected_seconds = INTERVAL_SECONDS.get(interval)
    if expected_seconds:
        expected_delta = timedelta(seconds=expected_seconds)
        for earlier, later in zip(timestamps, timestamps[1:]):
            if later - earlier > expected_delta:
                gap_count += 1
    else:
        notes.append(f"gap detection disabled for interval {interval}")

    if duplicate_count:
        notes.append(f"found {duplicate_count} duplicate timestamps")
    if not is_chrono:
        notes.append("timestamps not sorted")
    if gap_count:
        notes.append(f"detected {gap_count} large gaps")

    return DataQualityReport(
        symbol=symbol,
        interval=interval,
        total_bars=len(intervals),
        duplicate_count=duplicate_count,
        gap_count=gap_count,
        is_chronological=is_chrono,
        notes=notes,
    )


def summarize_reports(reports: Iterable[DataQualityReport]) -> dict[str, object]:
    total = 0
    duplicates = 0
    gaps = 0
    issues: list[str] = []

    for report in reports:
        total += report.total_bars
        duplicates += report.duplicate_count
        gaps += report.gap_count
        issues.extend(report.notes)

    return {
        "total_bars": total,
        "duplicate_count": duplicates,
        "gap_count": gaps,
        "notes": issues,
    }


__all__ = ["DataQualityReport", "analyze_intervals", "summarize_reports"]
