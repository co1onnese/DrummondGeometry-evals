"""Pattern detection primitives for Drummond Geometry."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
from enum import Enum
import statistics
from typing import Callable, List, Sequence

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


@dataclass(frozen=True)
class PLDotRefreshConfig:
    base_tolerance: float = 0.1
    volatility_lookback: int = 5
    volatility_multiplier: float = 1.0
    min_far_bars: int = 2
    max_return_bars: int = 4
    min_extension: float = 0.05
    confirmation: Callable[[datetime, int], bool] | None = None


@dataclass(frozen=True)
class ExhaustConfig:
    extension_threshold: float = 2.0
    min_extension_bars: int = 2
    max_recovery_bars: int = 3
    min_reversion_ratio: float = 0.4
    slope_reversal_limit: float = 0.0


@dataclass(frozen=True)
class CWaveConfig:
    min_bars: int = 3
    upper_position_threshold: float = 0.9
    lower_position_threshold: float = 0.1
    min_slope: float = 0.0
    min_slope_acceleration: float = 0.0
    min_envelope_expansion: float = 0.0
    require_volume_confirmation: bool = False
    volume_multiplier: float = 1.2
    volume_lookback: int = 3


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


def detect_pldot_refresh(
    intervals: Sequence[IntervalData],
    pldot: Sequence[PLDotSeries],
    tolerance: float | None = None,
    config: PLDotRefreshConfig | None = None,
) -> List[PatternEvent]:
    close_map = {bar.timestamp: bar.close for bar in intervals}
    ordered = sorted(pldot, key=lambda s: s.timestamp)

    cfg = config or PLDotRefreshConfig()
    if tolerance is not None:
        cfg = replace(cfg, base_tolerance=tolerance)

    max_return_bars = max(cfg.max_return_bars, cfg.min_far_bars)

    far_sequence: List[tuple[PLDotSeries, float]] = []
    direction = 0
    max_diff = 0.0
    events: List[PatternEvent] = []

    for idx, series in enumerate(ordered):
        close_price = close_map.get(series.timestamp)
        if close_price is None:
            continue

        dynamic_tolerance = cfg.base_tolerance
        if cfg.volatility_multiplier > 0 and cfg.volatility_lookback > 1:
            window_start = max(0, idx - cfg.volatility_lookback + 1)
            window = [float(entry.value) for entry in ordered[window_start : idx + 1]]
            if len(window) >= cfg.volatility_lookback:
                volatility = statistics.pstdev(window[-cfg.volatility_lookback :])
                dynamic_tolerance += volatility * cfg.volatility_multiplier

        diff = abs(float(close_price - series.value))
        side = _compare(close_price, series.value)

        if diff > dynamic_tolerance and side != 0:
            if far_sequence and side != direction:
                far_sequence = []
                max_diff = 0.0
            far_sequence.append((series, diff))
            direction = side
            max_diff = max(max_diff, diff)
            continue

        if far_sequence and direction != 0:
            bars_away = len(far_sequence)
            if (
                bars_away >= cfg.min_far_bars
                and bars_away <= max_return_bars
                and max_diff >= cfg.min_extension
            ):
                event_direction = -direction
                if cfg.confirmation is None or cfg.confirmation(series.timestamp, event_direction):
                    streak = [entry for entry, _ in far_sequence] + [series]
                    events.append(_build_event(PatternType.PLDOT_REFRESH, streak, event_direction))
            far_sequence = []
            direction = 0
            max_diff = 0.0
        else:
            far_sequence = []
            direction = 0
            max_diff = 0.0

    return events


def detect_exhaust(
    intervals: Sequence[IntervalData],
    pldot: Sequence[PLDotSeries],
    envelopes: Sequence[EnvelopeSeries],
    extension_threshold: float = 2.0,
    config: ExhaustConfig | None = None,
) -> List[PatternEvent]:
    cfg = config or ExhaustConfig()
    if extension_threshold != cfg.extension_threshold:
        cfg = replace(cfg, extension_threshold=extension_threshold)

    close_map = {bar.timestamp: bar.close for bar in intervals}
    slope_map = {p.timestamp: p.slope for p in pldot}
    ordered_envelopes = sorted(envelopes, key=lambda e: e.timestamp)

    events: List[PatternEvent] = []
    extension_bars: List[tuple[datetime, Decimal, Decimal | None, EnvelopeSeries]] = []
    direction = 0
    recovery_counter = 0

    for envelope in ordered_envelopes:
        close_price = close_map.get(envelope.timestamp)
        if close_price is None:
            continue

        width = float(envelope.width)
        if width <= 0:
            extension_bars = []
            direction = 0
            recovery_counter = 0
            continue

        upper = float(envelope.upper)
        lower = float(envelope.lower)
        close_f = float(close_price)

        side = 0
        extension_ratio = 0.0
        if close_f > upper:
            side = 1
            extension_ratio = (close_f - upper) / width
        elif close_f < lower:
            side = -1
            extension_ratio = (lower - close_f) / width

        if side != 0 and extension_ratio >= cfg.extension_threshold:
            if direction not in (0, side):
                extension_bars = []
            extension_bars.append((envelope.timestamp, close_price, slope_map.get(envelope.timestamp), envelope))
            direction = side
            recovery_counter = 0
            continue

        if direction != 0:
            recovery_counter += 1
            is_inside = (direction == 1 and close_f <= upper) or (direction == -1 and close_f >= lower)
            if (
                is_inside
                and len(extension_bars) >= cfg.min_extension_bars
                and recovery_counter <= cfg.max_recovery_bars
                and _passes_exhaust_filters(
                    extension_bars,
                    close_price,
                    envelope,
                    slope_map.get(envelope.timestamp),
                    direction,
                    cfg,
                )
            ):
                events.append(
                    PatternEvent(
                        pattern_type=PatternType.EXHAUST,
                        direction=-direction,
                        start_timestamp=extension_bars[0][0],
                        end_timestamp=envelope.timestamp,
                        strength=len(extension_bars),
                    )
                )
                extension_bars = []
                direction = 0
                recovery_counter = 0
            elif recovery_counter > cfg.max_recovery_bars:
                extension_bars = []
                direction = 0
                recovery_counter = 0
        else:
            extension_bars = []
            recovery_counter = 0

    return events


def _passes_exhaust_filters(
    extension_bars: Sequence[tuple[datetime, Decimal, Decimal | None, EnvelopeSeries]],
    reentry_close: Decimal,
    reentry_envelope: EnvelopeSeries,
    reentry_slope: Decimal | None,
    direction: int,
    config: ExhaustConfig,
) -> bool:
    if not extension_bars:
        return False

    width = float(reentry_envelope.width)
    if width <= 0:
        return False

    closes = [float(close) for _, close, _, _ in extension_bars]
    extreme = max(closes) if direction == 1 else min(closes)
    reentry_close_f = float(reentry_close)
    if direction == 1:
        reversion = (extreme - reentry_close_f) / width
    else:
        reversion = (reentry_close_f - extreme) / width
    if reversion < config.min_reversion_ratio:
        return False

    slope_limit = config.slope_reversal_limit
    if slope_limit is not None:
        last_slope = extension_bars[-1][2]
        if last_slope is not None and float(last_slope) * direction <= slope_limit:
            # Extension should show momentum in its direction
            return False
        if reentry_slope is not None and float(reentry_slope) * direction > slope_limit:
            # Reentry slope must fade or reverse
            return False

    return True


def detect_c_wave(
    envelopes: Sequence[EnvelopeSeries],
    config: CWaveConfig | None = None,
    pldot: Sequence[PLDotSeries] | None = None,
    intervals: Sequence[IntervalData] | None = None,
) -> List[PatternEvent]:
    cfg = config or CWaveConfig()

    slope_map: dict[datetime, float] = {}
    if pldot:
        slope_map = {series.timestamp: float(series.slope) for series in pldot}

    ordered_intervals: List[IntervalData] | None = None
    volume_index: dict[datetime, int] | None = None
    if intervals:
        ordered_intervals = sorted(intervals, key=lambda bar: bar.timestamp)
        volume_index = {bar.timestamp: idx for idx, bar in enumerate(ordered_intervals)}

    ordered = sorted(envelopes, key=lambda e: e.timestamp)
    events: List[PatternEvent] = []
    streak: List[EnvelopeSeries] = []
    direction = 0

    for entry in ordered:
        position = float(entry.position)
        if position >= cfg.upper_position_threshold:
            curr_dir = 1
        elif position <= cfg.lower_position_threshold:
            curr_dir = -1
        else:
            curr_dir = 0

        if curr_dir != 0:
            if direction in (0, curr_dir):
                streak.append(entry)
                direction = curr_dir
            else:
                if _qualifies_c_wave(streak, direction, cfg, slope_map, ordered_intervals, volume_index):
                    events.append(_build_envelope_event(PatternType.C_WAVE, streak, direction))
                streak = [entry]
                direction = curr_dir
        else:
            if _qualifies_c_wave(streak, direction, cfg, slope_map, ordered_intervals, volume_index):
                events.append(_build_envelope_event(PatternType.C_WAVE, streak, direction))
            streak = []
            direction = 0

    if _qualifies_c_wave(streak, direction, cfg, slope_map, ordered_intervals, volume_index):
        events.append(_build_envelope_event(PatternType.C_WAVE, streak, direction))

    return events


def _qualifies_c_wave(
    streak: Sequence[EnvelopeSeries],
    direction: int,
    config: CWaveConfig,
    slope_map: dict[datetime, float],
    ordered_intervals: Sequence[IntervalData] | None,
    volume_index: dict[datetime, int] | None,
) -> bool:
    if not streak or direction == 0:
        return False
    if len(streak) < config.min_bars:
        return False

    slopes_required = config.min_slope > 0 or config.min_slope_acceleration > 0
    if slopes_required and not slope_map:
        return False

    if slope_map:
        slope_values = [slope_map.get(entry.timestamp) for entry in streak if entry.timestamp in slope_map]
        if slopes_required and len(slope_values) < len(streak):
            return False
        if slope_values:
            avg_slope = sum(slope_values) / len(slope_values)
            if avg_slope * direction < config.min_slope:
                return False
            acceleration = (slope_values[-1] - slope_values[0]) * direction
            if acceleration < config.min_slope_acceleration:
                return False
    elif slopes_required:
        return False

    widths = [float(entry.width) for entry in streak]
    if not widths or widths[0] <= 0:
        if config.min_envelope_expansion > 0:
            return False
        expansion_ratio = 0.0
    else:
        expansion_ratio = (widths[-1] - widths[0]) / widths[0]
    if expansion_ratio < config.min_envelope_expansion:
        return False

    if config.require_volume_confirmation:
        if ordered_intervals is None or volume_index is None:
            return False
        first_index = volume_index.get(streak[0].timestamp)
        if first_index is None:
            return False
        lookback_start = max(0, first_index - config.volume_lookback)
        pre_slice = ordered_intervals[lookback_start:first_index]
        if not pre_slice:
            return False
        pre_avg = sum(int(bar.volume) for bar in pre_slice) / len(pre_slice)

        streak_indices = [volume_index.get(entry.timestamp) for entry in streak]
        if any(idx is None for idx in streak_indices):
            return False
        assert streak_indices  # for type checker
        streak_volumes = [int(ordered_intervals[idx].volume) for idx in streak_indices if idx is not None]
        if not streak_volumes:
            return False
        streak_avg = sum(streak_volumes) / len(streak_volumes)
        if pre_avg > 0 and streak_avg < pre_avg * config.volume_multiplier:
            return False

    return True


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
    "PLDotRefreshConfig",
    "ExhaustConfig",
    "CWaveConfig",
    "detect_pldot_push",
    "detect_pldot_refresh",
    "detect_exhaust",
    "detect_c_wave",
    "detect_congestion_oscillation",
]
