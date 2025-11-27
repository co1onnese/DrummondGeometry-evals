"""Helper for building complete timeframe data sets."""

from __future__ import annotations

from decimal import Decimal
from typing import Sequence

from ..data.models import IntervalData
from .drummond_lines import DrummondLineCalculator, aggregate_zones
from .envelopes import EnvelopeCalculator
from .multi_timeframe import TimeframeData, TimeframeType
from .patterns import (
    detect_c_wave,
    detect_congestion_oscillation,
    detect_exhaust,
    detect_pldot_push,
    detect_pldot_refresh,
    detect_termination_events,
)
from .pldot import PLDotCalculator
from .states import MarketStateClassifier


def build_timeframe_data(
    intervals: Sequence[IntervalData],
    timeframe: str,
    classification: TimeframeType,
) -> TimeframeData:
    """Construct a :class:`TimeframeData` object from raw intervals."""

    if not intervals:
        return TimeframeData(
            timeframe=timeframe,
            classification=classification,
            pldot_series=[],
            envelope_series=[],
            state_series=[],
            pattern_events=[],
            drummond_zones=(),
        )

    pldot_calc = PLDotCalculator(displacement=1)
    pldot_series = pldot_calc.from_intervals(intervals)

    envelope_calc = EnvelopeCalculator(method="pldot_range", period=3, multiplier=1.5)
    envelope_series = envelope_calc.from_intervals(intervals, pldot_series)

    state_classifier = MarketStateClassifier(slope_threshold=0.0001)
    state_series = state_classifier.classify(intervals, pldot_series)

    patterns = []
    patterns.extend(detect_pldot_push(intervals, pldot_series))
    patterns.extend(detect_pldot_refresh(intervals, pldot_series))
    patterns.extend(detect_exhaust(intervals, pldot_series, envelope_series))
    patterns.extend(detect_c_wave(envelope_series, pldot=pldot_series, intervals=intervals))
    patterns.extend(detect_congestion_oscillation(envelope_series))

    drummond_zones = ()
    line_calc = DrummondLineCalculator()
    drummond_lines = line_calc.from_intervals(intervals)
    if drummond_lines:
        avg_range = sum(float((bar.high - bar.low)) for bar in intervals) / len(intervals)
        envelope_width = float(envelope_series[-1].width) if envelope_series else 0.0
        tolerance = max(avg_range * 0.3, envelope_width * 0.25, 0.05)
        zones = aggregate_zones(drummond_lines, tolerance=tolerance)
        drummond_zones = tuple(zones)
        
        # Detect termination events when price approaches projected Drummond line zones
        termination_events = detect_termination_events(
            intervals=intervals,
            zones=zones,
            pldot=pldot_series,
        )
        patterns.extend(termination_events)

    return TimeframeData(
        timeframe=timeframe,
        classification=classification,
        pldot_series=pldot_series,
        envelope_series=envelope_series,
        state_series=state_series,
        pattern_events=patterns,
        drummond_zones=drummond_zones,
    )


__all__ = ["build_timeframe_data"]
