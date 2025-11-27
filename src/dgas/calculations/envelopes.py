"""Envelope band calculations for Drummond Geometry."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Iterable, List, Sequence

import pandas as pd

from ..data.models import IntervalData
from .pldot import PLDotSeries


@dataclass(frozen=True)
class EnvelopeSeries:
    timestamp: datetime
    center: Decimal
    upper: Decimal
    lower: Decimal
    width: Decimal
    position: Decimal
    method: str


class EnvelopeCalculator:
    """Compute Drummond Geometry envelope bands around PLdot.

    The default ``pldot_range`` method mirrors Charles Drummond's guidance: it
    measures the short-term ``PLdot`` volatility (three-bar sample standard
    deviation) and projects adaptive envelopes that represent the market's
    expected energy range. This forward-looking approach preserves the
    methodology's emphasis on probabilities rather than fixed-width bands.

    Available methods:
    - ``pldot_range``: 3-period standard deviation of PLdot values (default)
    - ``hlc_range``: 3-period high-low range of the bars that form PLdot
    - ``atr``: Average True Range based envelope (legacy)
    - ``percentage``: Fixed percentage envelope (legacy)

    The ``hlc_range`` method provides an alternative that uses the actual
    price range of the 3-bar period forming the PLdot, rather than statistical
    volatility. This can be useful for comparison and validation against the
    standard ``pldot_range`` method.

    Recommended configuration is ``pldot_range`` with a three-bar window and
    1.5x multiplier.
    """

    VALID_METHODS = {"atr", "percentage", "pldot_range", "hlc_range"}

    def __init__(self, method: str = "pldot_range", period: int = 3, multiplier: float = 1.5, percent: float = 0.02) -> None:
        if method not in self.VALID_METHODS:
            raise ValueError(f"method must be one of {self.VALID_METHODS}")
        if period <= 0:
            raise ValueError("period must be positive")
        if multiplier <= 0:
            raise ValueError("multiplier must be positive")
        if percent <= 0:
            raise ValueError("percent must be positive")

        self.method = method
        self.period = period
        self.multiplier = multiplier
        self.percent = percent

    def from_intervals(self, intervals: Sequence[IntervalData], pldot: Sequence[PLDotSeries]) -> List[EnvelopeSeries]:
        if not intervals or not pldot:
            return []

        df = pd.DataFrame(
            {
                "timestamp": [row.timestamp for row in intervals],
                "high": [float(row.high) for row in intervals],
                "low": [float(row.low) for row in intervals],
                "close": [float(row.close) for row in intervals],
            }
        ).sort_values("timestamp")

        df.set_index("timestamp", inplace=True)

        pldot_df = pd.DataFrame(
            {
                "timestamp": [row.timestamp for row in pldot],
                "value": [float(row.value) for row in pldot],
            }
        ).set_index("timestamp")

        df = df.join(pldot_df, how="inner")
        if df.empty:
            return []

        if self.method == "pldot_range":
            # DRUMMOND METHOD: 3-period standard deviation of PLdot values
            # This is the correct Drummond Geometry envelope calculation
            pldot_volatility = df["value"].rolling(
                window=self.period,
                min_periods=self.period
            ).std()
            offset = pldot_volatility * self.multiplier

        elif self.method == "hlc_range":
            # HLC RANGE METHOD: Uses the 3-bar high-low range
            # Alternative Drummond envelope calculation using price range
            # instead of PLdot volatility. Some practitioners prefer this
            # as it directly measures the price excursion of the PLdot period.
            rolling_high = df["high"].rolling(
                window=self.period,
                min_periods=self.period
            ).max()
            rolling_low = df["low"].rolling(
                window=self.period,
                min_periods=self.period
            ).min()
            hlc_range = rolling_high - rolling_low
            # Use half the range as offset (so total width = range * multiplier)
            offset = (hlc_range / 2) * self.multiplier

        elif self.method == "atr":
            # LEGACY ATR METHOD: For comparison only
            true_range = pd.concat(
                [
                    (df["high"] - df["low"]),
                    (df["high"] - df["close"].shift(1)).abs(),
                    (df["low"] - df["close"].shift(1)).abs(),
                ],
                axis=1,
            ).max(axis=1)
            atr = true_range.rolling(window=self.period, min_periods=1).mean()
            offset = atr * self.multiplier

        else:  # percentage
            offset = df["value"] * self.percent

        upper = df["value"] + offset
        lower = df["value"] - offset
        width = upper - lower
        close = df["close"]
        position = ((close - lower) / width).clip(lower=0.0, upper=1.0)

        results: List[EnvelopeSeries] = []
        for timestamp, center, upper_val, lower_val, width_val, position_val in zip(
            df.index,
            df["value"],
            upper,
            lower,
            width,
            position,
        ):
            results.append(
                EnvelopeSeries(
                    timestamp=timestamp.to_pydatetime(),
                    center=Decimal(str(round(center, 6))),
                    upper=Decimal(str(round(upper_val, 6))),
                    lower=Decimal(str(round(lower_val, 6))),
                    width=Decimal(str(round(width_val, 6))),
                    position=Decimal(str(round(position_val, 6))),
                    method=self.method,
                )
            )

        return results


__all__ = ["EnvelopeCalculator", "EnvelopeSeries"]
