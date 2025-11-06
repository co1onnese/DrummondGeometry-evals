"""Pattern detection primitives for Drummond Geometry."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Iterable, List, Sequence

from .envelopes import EnvelopeSeries
from .pldot import PLDotSeries
from ..data.models import IntervalData


class PatternType(Enum):
    PLDOT_PUSH = "pldot_push"
    PLDOT_REFRESH = "pldot_refresh"
    EXHAUST = "exhaust"
    C_WAVE = "c_wave"
    CONGESTION_OSCILLATION = "congestion_oscillation"


@dataclass(frozen=True)
class PatternEvent:
    pattern_type: PatternType
    direction: int  # 1 for bullish, -1 for bearish, 0 for neutral
    start_timestamp: datetime
    end_timestamp: datetime
    strength: int


def detect_pldot_push(intervals: Sequence[IntervalData], pldot: Sequence[PLDotSeries]) -> List[PatternEvent]:
    close_map = {bar.timestamp: bar.close for bar in intervals}
    ordered = sorted(pldot, key=lambda s: s.timestamp)

    events: List[PatternEvent] = []
    streak: List[PLDotSeries] = []
    direction = 0

    for series in ordered:
        close_price = close_map.get(series.timestamp)
        if close_price is None:
            continue

        side = _compare(close_price, series.value)
        slope_sign = _sign(series.slope)

        if side != 0 and side == slope_sign:
            if direction == side or direction == 0:
                streak.append(series)
                direction = side
            else:
                if len(streak) >= 3:
                    events.append(_build_event(PatternType.PLDOT_PUSH, streak, direction))
                streak = [series]
                direction = side
        else:
            if len(streak) >= 3:
                events.append(_build_event(PatternType.PLDOT_PUSH, streak, direction))
            streak = []
            direction = 0

    if len(streak) >= 3:
        events.append(_build_event(PatternType.PLDOT_PUSH, streak, direction))

    return events


def detect_pldot_refresh(intervals: Sequence[IntervalData], pldot: Sequence[PLDotSeries], tolerance: float = 0.1) -> List[PatternEvent]:
    close_map = {bar.timestamp: bar.close for bar in intervals}
    ordered = sorted(pldot, key=lambda s: s.timestamp)
    events: List[PatternEvent] = []

    far_sequence: List[PLDotSeries] = []
    direction = 0

    for series in ordered:
        close_price = close_map.get(series.timestamp)
        if close_price is None:
            continue

        diff = abs(float(close_price - series.value))
        if diff > tolerance:
            far_sequence.append(series)
            direction = _compare(close_price, series.value)
        else:
            if len(far_sequence) >= 2 and direction != 0:
                streak = far_sequence + [series]
                events.append(_build_event(PatternType.PLDOT_REFRESH, streak, -direction))
            far_sequence = []
            direction = 0

    return events


def detect_exhaust(
    intervals: Sequence[IntervalData],
    pldot: Sequence[PLDotSeries],
    envelopes: Sequence[EnvelopeSeries],
    extension_threshold: float = 2.0,
) -> List[PatternEvent]:
    """
    Detect exhaust patterns where price extends far beyond envelope then reverses.

    An exhaust occurs when:
    1. Price moves significantly beyond envelope (>threshold * envelope width)
    2. Then sharply reverses back toward PLdot
    3. Signals momentum depletion and potential turning point

    Args:
        intervals: Price bars
        pldot: PLdot series
        envelopes: Envelope bands
        extension_threshold: How many envelope widths price must extend (default: 2.0)

    Returns:
        List of detected exhaust patterns
    """
    # Create timestamp-aligned lookup maps
    close_map = {bar.timestamp: bar.close for bar in intervals}
    pldot_map = {p.timestamp: p.value for p in pldot}
    envelope_dict = {e.timestamp: e for e in envelopes}

    ordered_envelopes = sorted(envelopes, key=lambda e: e.timestamp)

    events: List[PatternEvent] = []
    extension_sequence: List[tuple[datetime, EnvelopeSeries, Decimal]] = []
    direction = 0  # 1=bullish extension, -1=bearish extension

    for i, envelope in enumerate(ordered_envelopes):
        close_price = close_map.get(envelope.timestamp)
        pldot_value = pldot_map.get(envelope.timestamp)

        if close_price is None or pldot_value is None:
            continue

        # Calculate how far beyond envelope the price is
        width = float(envelope.width)
        center = float(envelope.center)
        upper = float(envelope.upper)
        lower = float(envelope.lower)
        close_f = float(close_price)

        # Check for upward extension beyond upper envelope
        if close_f > upper:
            extension = (close_f - upper) / width if width > 0 else 0

            if extension >= extension_threshold:
                # Significant upward extension
                if direction == 1 or direction == 0:
                    extension_sequence.append((envelope.timestamp, envelope, close_price))
                    direction = 1
                else:
                    # Direction changed - previous was exhaust
                    extension_sequence = [(envelope.timestamp, envelope, close_price)]
                    direction = 1
            else:
                # Check for reversal (back toward PLdot)
                if len(extension_sequence) >= 2 and direction == 1:
                    # Was extended, now reversing
                    if close_f < extension_sequence[-1][2]:  # type: ignore
                        # Create exhaust event
                        events.append(
                            PatternEvent(
                                pattern_type=PatternType.EXHAUST,
                                direction=-1,  # Bearish signal after bullish extension
                                start_timestamp=extension_sequence[0][0],
                                end_timestamp=envelope.timestamp,
                                strength=len(extension_sequence),
                            )
                        )
                extension_sequence = []
                direction = 0

        # Check for downward extension beyond lower envelope
        elif close_f < lower:
            extension = (lower - close_f) / width if width > 0 else 0

            if extension >= extension_threshold:
                # Significant downward extension
                if direction == -1 or direction == 0:
                    extension_sequence.append((envelope.timestamp, envelope, close_price))
                    direction = -1
                else:
                    # Direction changed
                    extension_sequence = [(envelope.timestamp, envelope, close_price)]
                    direction = -1
            else:
                # Check for reversal
                if len(extension_sequence) >= 2 and direction == -1:
                    if close_f > extension_sequence[-1][2]:  # type: ignore
                        # Create exhaust event
                        events.append(
                            PatternEvent(
                                pattern_type=PatternType.EXHAUST,
                                direction=1,  # Bullish signal after bearish extension
                                start_timestamp=extension_sequence[0][0],
                                end_timestamp=envelope.timestamp,
                                strength=len(extension_sequence),
                            )
                        )
                extension_sequence = []
                direction = 0

        # Price within envelope - reset
        else:
            if len(extension_sequence) >= 2:
                # Create exhaust on return to envelope
                exhaust_direction = -1 if direction == 1 else 1
                events.append(
                    PatternEvent(
                        pattern_type=PatternType.EXHAUST,
                        direction=exhaust_direction,
                        start_timestamp=extension_sequence[0][0],
                        end_timestamp=envelope.timestamp,
                        strength=len(extension_sequence),
                    )
                )
            extension_sequence = []
            direction = 0

    return events


def detect_c_wave(envelopes: Sequence[EnvelopeSeries]) -> List[PatternEvent]:
    ordered = sorted(envelopes, key=lambda e: e.timestamp)
    events: List[PatternEvent] = []
    streak: List[EnvelopeSeries] = []
    direction = 0

    for entry in ordered:
        position = float(entry.position)
        center = float(entry.center)
        if position >= 0.9:
            curr_dir = 1
        elif position <= 0.1:
            curr_dir = -1
        else:
            curr_dir = 0

        if curr_dir != 0:
            if direction == 0 or curr_dir == direction:
                streak.append(entry)
                direction = curr_dir
            else:
                if len(streak) >= 3:
                    events.append(_build_envelope_event(PatternType.C_WAVE, streak, direction))
                streak = [entry]
                direction = curr_dir
        else:
            if len(streak) >= 3:
                events.append(_build_envelope_event(PatternType.C_WAVE, streak, direction))
            streak = []
            direction = 0

    if len(streak) >= 3:
        events.append(_build_envelope_event(PatternType.C_WAVE, streak, direction))

    return events


def detect_congestion_oscillation(envelopes: Sequence[EnvelopeSeries]) -> List[PatternEvent]:
    ordered = sorted(envelopes, key=lambda e: e.timestamp)
    events: List[PatternEvent] = []
    streak: List[EnvelopeSeries] = []
    last_position = None

    for entry in ordered:
        position = float(entry.position)
        if 0.2 <= position <= 0.8:
            prev_position = last_position
            if streak:
                prev_entry_position = float(streak[-1].position)
            else:
                prev_entry_position = 0.5

            if prev_position is None or (position - prev_position) * (prev_entry_position - 0.5) <= 0:
                streak.append(entry)
            else:
                if len(streak) >= 4:
                    events.append(_build_envelope_event(PatternType.CONGESTION_OSCILLATION, streak, 0))
                streak = [entry]
        else:
            if len(streak) >= 4:
                events.append(_build_envelope_event(PatternType.CONGESTION_OSCILLATION, streak, 0))
            streak = []

        last_position = position

    if len(streak) >= 4:
        events.append(_build_envelope_event(PatternType.CONGESTION_OSCILLATION, streak, 0))

    return events


def _build_event(pattern_type: PatternType, streak: List[PLDotSeries], direction: int) -> PatternEvent:
    return PatternEvent(
        pattern_type=pattern_type,
        direction=direction,
        start_timestamp=streak[0].timestamp,
        end_timestamp=streak[-1].timestamp,
        strength=len(streak),
    )


def _build_envelope_event(pattern_type: PatternType, streak: List[EnvelopeSeries], direction: int) -> PatternEvent:
    return PatternEvent(
        pattern_type=pattern_type,
        direction=direction,
        start_timestamp=streak[0].timestamp,
        end_timestamp=streak[-1].timestamp,
        strength=len(streak),
    )


def _compare(a: Decimal, b: Decimal) -> int:
    if a > b:
        return 1
    if a < b:
        return -1
    return 0


def _sign(value: Decimal) -> int:
    if value > 0:
        return 1
    if value < 0:
        return -1
    return 0


__all__ = [
    "PatternType",
    "PatternEvent",
    "detect_pldot_push",
    "detect_pldot_refresh",
    "detect_exhaust",
    "detect_c_wave",
    "detect_congestion_oscillation",
]
