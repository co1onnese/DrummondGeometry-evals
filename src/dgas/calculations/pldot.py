"""PLdot calculation utilities."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Iterable, List, Sequence

import pandas as pd

from ..data.models import IntervalData


@dataclass(frozen=True)
class PLDotSeries:
    timestamp: datetime
    value: Decimal
    projected_timestamp: datetime
    projected_value: Decimal
    slope: Decimal
    displacement: int


class PLDotCalculator:
    """Calculate PLdot values from OHLCV data."""

    def __init__(self, displacement: int = 1) -> None:
        if displacement < 1:
            raise ValueError("PLdot displacement must be >= 1")
        self.displacement = displacement

    def from_intervals(self, intervals: Sequence[IntervalData]) -> List[PLDotSeries]:
        if len(intervals) < 3:
            raise ValueError("At least 3 intervals are required to compute PLdot")

        df = pd.DataFrame(
            {
                "timestamp": [row.timestamp for row in intervals],
                "high": [float(row.high) for row in intervals],
                "low": [float(row.low) for row in intervals],
                "close": [float(row.close) for row in intervals],
            }
        )

        df.sort_values("timestamp", inplace=True)
        df.set_index("timestamp", inplace=True)

        avg = (df["high"] + df["low"] + df["close"]) / 3.0
        rolling = avg.rolling(window=3, min_periods=3).mean()

        results: List[PLDotSeries] = []
        timestamps = df.index.to_series().reset_index(drop=True)
        pl_values = rolling.reset_index(drop=True)
        slopes = pl_values.diff()

        for idx, value in pl_values.items():
            if pd.isna(value):
                continue
            target_idx = idx + self.displacement
            if target_idx >= len(timestamps):
                break
            projected_timestamp = timestamps.iloc[target_idx].to_pydatetime()
            current_timestamp = timestamps.iloc[idx].to_pydatetime()
            slope_value = slopes.iloc[idx]
            slope_decimal = Decimal(str(round(slope_value, 6))) if pd.notna(slope_value) else Decimal("0")
            projected_value = Decimal(str(round(value, 6)))
            results.append(
                PLDotSeries(
                    timestamp=current_timestamp,
                    value=Decimal(str(round(value, 6))),
                    projected_timestamp=projected_timestamp,
                    projected_value=projected_value,
                    slope=slope_decimal,
                    displacement=self.displacement,
                )
            )

        return results


__all__ = ["PLDotCalculator", "PLDotSeries"]
