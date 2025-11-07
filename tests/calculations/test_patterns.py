from datetime import datetime, timedelta, timezone
from decimal import Decimal

from dgas.calculations.envelopes import EnvelopeSeries
from dgas.calculations.patterns import (
    CWaveConfig,
    ExhaustConfig,
    PLDotRefreshConfig,
    PatternType,
    detect_c_wave,
    detect_congestion_oscillation,
    detect_exhaust,
    detect_pldot_push,
    detect_pldot_refresh,
)
from dgas.calculations.pldot import PLDotSeries
from dgas.data.models import IntervalData


def _make_interval(ts: datetime, close: float, high: float, low: float, volume: int = 1) -> IntervalData:
    payload = {
        "code": "AAPL",
        "exchange_short_name": "US",
        "timestamp": int(ts.timestamp()),
        "open": close,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }
    return IntervalData.from_api_record(payload, interval="30m")


def _pldot_series(ts: datetime, value: float, slope: float) -> PLDotSeries:
    return PLDotSeries(
        timestamp=ts,
        value=Decimal(str(value)),
        projected_timestamp=ts + timedelta(minutes=30),
        projected_value=Decimal(str(value)),
        slope=Decimal(str(slope)),
        displacement=1,
    )


def _envelope_series(ts: datetime, center: float, width: float, position: float) -> EnvelopeSeries:
    upper = center + width / 2
    lower = center - width / 2
    return EnvelopeSeries(
        timestamp=ts,
        center=Decimal(str(center)),
        upper=Decimal(str(upper)),
        lower=Decimal(str(lower)),
        width=Decimal(str(width)),
        position=Decimal(str(position)),
        method="atr",
    )


def test_detect_pldot_push():
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    intervals = []
    series = []
    for i in range(5):
        ts = base + timedelta(minutes=30 * i)
        intervals.append(_make_interval(ts, close=10 + i, high=11 + i, low=9 + i))
        series.append(_pldot_series(ts, value=8 + i * 0.4, slope=0.6))

    events = detect_pldot_push(intervals, series)
    assert events
    assert events[0].pattern_type == PatternType.PLDOT_PUSH


def test_detect_pldot_refresh():
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    intervals = []
    series = []
    for i in range(5):
        ts = base + timedelta(minutes=30 * i)
        if i < 2:
            close = 12
        elif i < 4:
            close = 9
        else:
            close = 10
        intervals.append(_make_interval(ts, close=close, high=close + 1, low=close - 1))
        series.append(_pldot_series(ts, value=10, slope=0.0))

    events = detect_pldot_refresh(intervals, series, tolerance=0.5)
    assert events
    assert events[0].pattern_type == PatternType.PLDOT_REFRESH


def test_detect_pldot_refresh_respects_return_speed():
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    intervals = []
    pldot_series = []

    for i in range(6):
        ts = base + timedelta(minutes=30 * i)
        close = 12 if i < 5 else 10
        intervals.append(_make_interval(ts, close=close, high=close + 1, low=close - 1))
        pldot_series.append(_pldot_series(ts, value=10, slope=0.0))

    config = PLDotRefreshConfig(base_tolerance=0.5, max_return_bars=3)
    events = detect_pldot_refresh(intervals, pldot_series, config=config)

    assert len(events) == 0


def test_detect_pldot_refresh_confirmation_hook():
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    intervals = []
    pldot_series = []

    for i in range(5):
        ts = base + timedelta(minutes=30 * i)
        close = 12 if i < 3 else 10
        intervals.append(_make_interval(ts, close=close, high=close + 1, low=close - 1))
        pldot_series.append(_pldot_series(ts, value=10, slope=0.0))

    def _reject_confirmation(ts: datetime, direction: int) -> bool:  # pragma: no cover - simple callback
        return False

    config = PLDotRefreshConfig(base_tolerance=0.5, confirmation=_reject_confirmation)
    events = detect_pldot_refresh(intervals, pldot_series, config=config)

    assert len(events) == 0


def test_detect_c_wave():
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    envelopes = [
        _envelope_series(base + timedelta(minutes=30 * i), center=10 + i * 0.5, width=2, position=0.95)
        for i in range(4)
    ]
    events = detect_c_wave(envelopes)
    assert events
    assert events[0].pattern_type == PatternType.C_WAVE


def test_detect_c_wave_with_slope_and_expansion_filters():
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    envelopes = [
        _envelope_series(
            base + timedelta(minutes=30 * i),
            center=10 + i * 0.4,
            width=2.0 + i * 0.4,
            position=0.95,
        )
        for i in range(4)
    ]
    pldot_series = [
        _pldot_series(base + timedelta(minutes=30 * i), value=Decimal("10") + Decimal("0.3") * i, slope=0.05 + 0.02 * i)
        for i in range(4)
    ]

    config = CWaveConfig(
        min_bars=3,
        min_slope=0.04,
        min_slope_acceleration=0.03,
        min_envelope_expansion=0.1,
    )
    events = detect_c_wave(envelopes, config=config, pldot=pldot_series)

    assert events
    assert events[0].pattern_type == PatternType.C_WAVE


def test_detect_c_wave_requires_volume_confirmation():
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    lookback_intervals: list[IntervalData] = []
    for offset, volume in zip(range(3, 0, -1), [90, 100, 110]):
        ts = base - timedelta(minutes=30 * offset)
        lookback_intervals.append(_make_interval(ts, close=10.0, high=10.5, low=9.5, volume=volume))

    streak_envelopes = []
    pldot_series = []
    intervals = lookback_intervals[:]

    for i in range(4):
        ts = base + timedelta(minutes=30 * i)
        envelopes_entry = _envelope_series(ts, center=10 + i * 0.3, width=2.0 + i * 0.3, position=0.95)
        streak_envelopes.append(envelopes_entry)
        pldot_series.append(_pldot_series(ts, value=Decimal("10") + Decimal("0.2") * i, slope=0.05 + 0.02 * i))

        interval = _make_interval(
            ts,
            close=10.0 + i * 0.4,
            high=10.5 + i * 0.4,
            low=9.5 + i * 0.4,
            volume=200 + i * 50,
        )
        intervals.append(interval)

    config = CWaveConfig(
        min_bars=3,
        min_slope=0.04,
        min_slope_acceleration=0.02,
        min_envelope_expansion=0.05,
        require_volume_confirmation=True,
        volume_multiplier=1.2,
        volume_lookback=3,
    )

    events = detect_c_wave(streak_envelopes, config=config, pldot=pldot_series, intervals=intervals)

    assert events
    assert events[0].pattern_type == PatternType.C_WAVE


def test_detect_c_wave_rejects_when_volume_fails():
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    lookback_intervals: list[IntervalData] = []
    for offset in range(3, 0, -1):
        ts = base - timedelta(minutes=30 * offset)
        lookback_intervals.append(_make_interval(ts, close=10.0, high=10.5, low=9.5, volume=210))

    streak_envelopes = []
    pldot_series = []
    intervals = lookback_intervals[:]

    for i in range(4):
        ts = base + timedelta(minutes=30 * i)
        streak_envelopes.append(_envelope_series(ts, center=10, width=2.0 + i * 0.2, position=0.95))
        pldot_series.append(_pldot_series(ts, value=Decimal("10") + Decimal("0.2") * i, slope=0.05 + 0.01 * i))
        interval = _make_interval(
            ts,
            close=10.0 + i * 0.2,
            high=10.5 + i * 0.2,
            low=9.5 + i * 0.2,
            volume=180,
        )
        intervals.append(interval)

    config = CWaveConfig(
        min_bars=3,
        require_volume_confirmation=True,
        volume_multiplier=1.3,
        volume_lookback=3,
    )

    events = detect_c_wave(streak_envelopes, config=config, pldot=pldot_series, intervals=intervals)

    assert len(events) == 0


def test_detect_congestion_oscillation():
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    positions = [0.3, 0.6, 0.4, 0.7, 0.35, 0.65]
    envelopes = [
        _envelope_series(base + timedelta(minutes=30 * i), center=10, width=1.5, position=pos)
        for i, pos in enumerate(positions)
    ]
    events = detect_congestion_oscillation(envelopes)
    assert events
    assert events[0].pattern_type == PatternType.CONGESTION_OSCILLATION


def test_detect_exhaust_bullish_extension():
    """Test exhaust pattern detection for bullish extension and reversal."""
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    intervals = []
    pldot_series = []
    envelopes = []
    
    center = 100.0
    width = 2.0  # Envelope width
    upper = center + width / 2  # 101.0
    lower = center - width / 2  # 99.0
    
    slopes = [0.18, 0.16, 0.12, -0.05]
    closes = [100.0, 105.0, 105.5, 100.0]
    highs = [100.5, 105.5, 106.0, 100.5]
    lows = [99.5, 104.5, 105.0, 99.5]

    for idx, slope in enumerate(slopes):
        ts = base + timedelta(minutes=30 * idx)
        intervals.append(_make_interval(ts, close=closes[idx], high=highs[idx], low=lows[idx]))
        pldot_series.append(_pldot_series(ts, value=center, slope=slope))
        position = 1.0 if idx in (1, 2) else 0.5
        envelopes.append(_envelope_series(ts, center=center, width=width, position=position))
    
    events = detect_exhaust(intervals, pldot_series, envelopes, extension_threshold=2.0)
    
    assert len(events) > 0
    exhaust = events[0]
    assert exhaust.pattern_type == PatternType.EXHAUST
    assert exhaust.direction == -1  # Bearish signal after bullish extension
    assert exhaust.strength >= 2  # At least 2 bars of extension
    assert exhaust.start_timestamp == base + timedelta(minutes=30)
    assert exhaust.end_timestamp == base + timedelta(minutes=90)


def test_detect_exhaust_bearish_extension():
    """Test exhaust pattern detection for bearish extension and reversal."""
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    intervals = []
    pldot_series = []
    envelopes = []
    
    center = 100.0
    width = 2.0
    slopes = [-0.18, -0.16, -0.12, 0.06]
    closes = [100.0, 95.0, 94.5, 100.0]
    highs = [100.5, 95.5, 95.0, 100.5]
    lows = [99.5, 94.5, 94.0, 99.5]

    for idx, slope in enumerate(slopes):
        ts = base + timedelta(minutes=30 * idx)
        intervals.append(_make_interval(ts, close=closes[idx], high=highs[idx], low=lows[idx]))
        pldot_series.append(_pldot_series(ts, value=center, slope=slope))
        position = 0.0 if idx in (1, 2) else 0.5
        envelopes.append(_envelope_series(ts, center=center, width=width, position=position))
    
    events = detect_exhaust(intervals, pldot_series, envelopes, extension_threshold=2.0)
    
    assert len(events) > 0
    exhaust = events[0]
    assert exhaust.pattern_type == PatternType.EXHAUST
    assert exhaust.direction == 1  # Bullish signal after bearish extension
    assert exhaust.strength >= 2


def test_detect_exhaust_no_extension():
    """Test that exhaust is not detected when extension threshold not met."""
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    intervals = []
    pldot_series = []
    envelopes = []
    
    center = 100.0
    width = 2.0
    
    # Price extends but not enough (only 1.0 width, threshold is 2.0)
    for i in range(4):
        ts = base + timedelta(minutes=30 * i)
        close = 102.0 if i > 0 else 100.0  # Only 1.0 above upper (not 2.0 widths)
        intervals.append(_make_interval(ts, close=close, high=close + 0.5, low=close - 0.5))
        pldot_series.append(_pldot_series(ts, value=center, slope=0.1))
        envelopes.append(_envelope_series(ts, center=center, width=width, position=0.8))
    
    events = detect_exhaust(intervals, pldot_series, envelopes, extension_threshold=2.0)
    
    # Should not detect exhaust since extension < threshold
    assert len(events) == 0


def test_detect_exhaust_extension_insufficient_bars():
    """Test that exhaust requires at least 2 bars of extension."""
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    intervals = []
    pldot_series = []
    envelopes = []
    
    center = 100.0
    width = 2.0
    
    # Only 1 bar of extension - not enough for exhaust
    ts = base
    intervals.append(_make_interval(ts, close=100.0, high=100.5, low=99.5))
    pldot_series.append(_pldot_series(ts, value=center, slope=0.1))
    envelopes.append(_envelope_series(ts, center=center, width=width, position=0.5))
    
    ts = base + timedelta(minutes=30)
    intervals.append(_make_interval(ts, close=105.0, high=105.5, low=104.5))  # Extended
    pldot_series.append(_pldot_series(ts, value=center + 0.1, slope=0.1))
    envelopes.append(_envelope_series(ts, center=center + 0.1, width=width, position=1.0))
    
    ts = base + timedelta(minutes=60)
    intervals.append(_make_interval(ts, close=102.0, high=102.5, low=101.5))  # Reverses
    pldot_series.append(_pldot_series(ts, value=center + 0.2, slope=0.1))
    envelopes.append(_envelope_series(ts, center=center + 0.2, width=width, position=0.8))
    
    events = detect_exhaust(intervals, pldot_series, envelopes, extension_threshold=2.0)
    
    # Only 1 bar of extension - should not create exhaust event
    assert len(events) == 0


def test_detect_exhaust_requires_slope_reversal():
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    center = 100.0
    width = 2.0

    intervals = []
    pldot_series = []
    envelopes = []

    slopes = [0.18, 0.16, 0.12, 0.08]
    closes = [100.0, 105.0, 105.5, 100.0]
    highs = [100.5, 105.5, 106.0, 100.5]
    lows = [99.5, 104.5, 105.0, 99.5]

    for idx, slope in enumerate(slopes):
        ts = base + timedelta(minutes=30 * idx)
        intervals.append(_make_interval(ts, close=closes[idx], high=highs[idx], low=lows[idx]))
        pldot_series.append(_pldot_series(ts, value=center, slope=slope))
        position = 1.0 if idx in (1, 2) else 0.5
        envelopes.append(_envelope_series(ts, center=center, width=width, position=position))

    config = ExhaustConfig(extension_threshold=2.0, slope_reversal_limit=0.0)
    events = detect_exhaust(intervals, pldot_series, envelopes, config=config)

    assert len(events) == 0


def test_detect_exhaust_requires_reversion_ratio():
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    center = 100.0
    width = 2.0

    intervals = []
    pldot_series = []
    envelopes = []

    slopes = [0.2, 0.18, 0.16, -0.05]
    closes = [100.0, 105.0, 105.5, 104.8]
    highs = [100.5, 105.5, 106.0, 105.0]
    lows = [99.5, 104.5, 105.0, 104.5]

    for idx, slope in enumerate(slopes):
        ts = base + timedelta(minutes=30 * idx)
        intervals.append(_make_interval(ts, close=closes[idx], high=highs[idx], low=lows[idx]))
        pldot_series.append(_pldot_series(ts, value=center, slope=slope))
        position = 1.0 if idx in (1, 2) else 0.6
        envelopes.append(_envelope_series(ts, center=center, width=width, position=position))

    config = ExhaustConfig(extension_threshold=2.0, min_reversion_ratio=0.6)
    events = detect_exhaust(intervals, pldot_series, envelopes, config=config)

    assert len(events) == 0
