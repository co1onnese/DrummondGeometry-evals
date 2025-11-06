"""Two-bar Drummond line calculations and zone aggregation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Iterable, List, Sequence

from ..data.models import IntervalData


@dataclass(frozen=True)
class DrummondLine:
    start_timestamp: datetime
    end_timestamp: datetime
    start_price: Decimal
    end_price: Decimal
    projected_timestamp: datetime
    projected_price: Decimal
    slope: Decimal
    line_type: str  # "support" or "resistance"


@dataclass(frozen=True)
class DrummondZone:
    center_price: Decimal
    lower_price: Decimal
    upper_price: Decimal
    line_type: str
    strength: int


class DrummondLineCalculator:
    """Compute two-bar support and resistance lines per Drummond methodology."""

    def __init__(self, projection_gap: int = 1) -> None:
        if projection_gap < 1:
            raise ValueError("projection_gap must be positive")
        self.projection_gap = projection_gap

    def from_intervals(self, intervals: Sequence[IntervalData]) -> List[DrummondLine]:
        if len(intervals) < 2:
            return []

        lines: List[DrummondLine] = []
        for i in range(1, len(intervals)):
            prev_bar = intervals[i - 1]
            curr_bar = intervals[i]

            project_index = min(i + self.projection_gap, len(intervals) - 1)
            projected_bar = intervals[project_index]

            # Resistance line through highs
            resistance_line = self._build_line(
                prev_bar.timestamp,
                curr_bar.timestamp,
                prev_bar.high,
                curr_bar.high,
                projected_bar.timestamp,
                "resistance",
            )
            lines.append(resistance_line)

            # Support line through lows
            support_line = self._build_line(
                prev_bar.timestamp,
                curr_bar.timestamp,
                prev_bar.low,
                curr_bar.low,
                projected_bar.timestamp,
                "support",
            )
            lines.append(support_line)

        return lines

    def _build_line(
        self,
        start_ts: datetime,
        end_ts: datetime,
        start_price: Decimal,
        end_price: Decimal,
        projected_ts: datetime,
        line_type: str,
    ) -> DrummondLine:
        start_price_dec = Decimal(str(start_price))
        end_price_dec = Decimal(str(end_price))
        price_delta = end_price_dec - start_price_dec

        slope = price_delta
        projected_price = end_price_dec + price_delta

        return DrummondLine(
            start_timestamp=start_ts,
            end_timestamp=end_ts,
            start_price=start_price_dec,
            end_price=end_price_dec,
            projected_timestamp=projected_ts,
            projected_price=projected_price,
            slope=price_delta,
            line_type=line_type,
        )


def aggregate_zones(lines: Iterable[DrummondLine], tolerance: float = 0.5) -> List[DrummondZone]:
    grouped: List[DrummondZone] = []
    sorted_lines = sorted(lines, key=lambda line: float(line.projected_price))

    current_group: List[DrummondLine] = []
    for line in sorted_lines:
        if not current_group:
            current_group.append(line)
            continue

        last_price = float(current_group[-1].projected_price)
        if abs(float(line.projected_price) - last_price) <= tolerance and line.line_type == current_group[-1].line_type:
            current_group.append(line)
        else:
            grouped.append(_build_zone(current_group))
            current_group = [line]

    if current_group:
        grouped.append(_build_zone(current_group))

    return grouped


def _build_zone(lines: List[DrummondLine]) -> DrummondZone:
    prices = [float(line.projected_price) for line in lines]
    lower = min(prices)
    upper = max(prices)
    center = (lower + upper) / 2
    return DrummondZone(
        center_price=Decimal(str(round(center, 6))),
        lower_price=Decimal(str(round(lower, 6))),
        upper_price=Decimal(str(round(upper, 6))),
        line_type=lines[0].line_type,
        strength=len(lines),
    )


__all__ = ["DrummondLineCalculator", "DrummondLine", "DrummondZone", "aggregate_zones"]
