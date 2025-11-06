from datetime import datetime, timedelta, timezone
from decimal import Decimal

from dgas.calculations.envelopes import EnvelopeSeries
from dgas.calculations.patterns import (
    PatternType,
    detect_c_wave,
    detect_congestion_oscillation,
    detect_exhaust,
    detect_pldot_push,
    detect_pldot_refresh,
)
from dgas.calculations.pldot import PLDotSeries
from dgas.data.models import IntervalData


def _make_interval(ts: datetime, close: float, high: float, low: float) -> IntervalData:
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


def test_detect_c_wave():
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    envelopes = [
        _envelope_series(base + timedelta(minutes=30 * i), center=10 + i * 0.5, width=2, position=0.95)
        for i in range(4)
    ]
    events = detect_c_wave(envelopes)
    assert events
    assert events[0].pattern_type == PatternType.C_WAVE


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
    
    # Keep center constant for simplicity
    # First bar: price within envelope
    ts = base
    intervals.append(_make_interval(ts, close=100.0, high=100.5, low=99.5))
    pldot_series.append(_pldot_series(ts, value=center, slope=0.1))
    envelopes.append(_envelope_series(ts, center=center, width=width, position=0.5))
    
    # Second bar: price extends above upper envelope
    # Close = 105.0, upper = 101.0, extension = (105.0 - 101.0) / 2.0 = 2.0 (meets threshold)
    ts = base + timedelta(minutes=30)
    intervals.append(_make_interval(ts, close=105.0, high=105.5, low=104.5))
    pldot_series.append(_pldot_series(ts, value=center, slope=0.1))  # Keep center same
    envelopes.append(_envelope_series(ts, center=center, width=width, position=1.0))
    
    # Third bar: still extended (above upper)
    ts = base + timedelta(minutes=60)
    intervals.append(_make_interval(ts, close=105.5, high=106.0, low=105.0))
    pldot_series.append(_pldot_series(ts, value=center, slope=0.1))  # Keep center same
    envelopes.append(_envelope_series(ts, center=center, width=width, position=1.0))
    
    # Fourth bar: price returns to within envelope (exhaust detected)
    ts = base + timedelta(minutes=90)
    intervals.append(_make_interval(ts, close=100.0, high=100.5, low=99.5))  # Back within envelope
    pldot_series.append(_pldot_series(ts, value=center, slope=0.1))  # Keep center same
    envelopes.append(_envelope_series(ts, center=center, width=width, position=0.5))
    
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
    upper = center + width / 2  # 101.0
    lower = center - width / 2  # 99.0
    
    # Keep center constant
    # First bar: within envelope
    ts = base
    intervals.append(_make_interval(ts, close=100.0, high=100.5, low=99.5))
    pldot_series.append(_pldot_series(ts, value=center, slope=-0.1))
    envelopes.append(_envelope_series(ts, center=center, width=width, position=0.5))
    
    # Second bar: extends below lower envelope
    # Close = 95.0, lower = 99.0, extension = (99.0 - 95.0) / 2.0 = 2.0 (meets threshold)
    ts = base + timedelta(minutes=30)
    intervals.append(_make_interval(ts, close=95.0, high=95.5, low=94.5))
    pldot_series.append(_pldot_series(ts, value=center, slope=-0.1))  # Keep center same
    envelopes.append(_envelope_series(ts, center=center, width=width, position=0.0))
    
    # Third bar: still extended (below lower)
    ts = base + timedelta(minutes=60)
    intervals.append(_make_interval(ts, close=94.5, high=95.0, low=94.0))
    pldot_series.append(_pldot_series(ts, value=center, slope=-0.1))  # Keep center same
    envelopes.append(_envelope_series(ts, center=center, width=width, position=0.0))
    
    # Fourth bar: price returns to within envelope (exhaust detected)
    ts = base + timedelta(minutes=90)
    intervals.append(_make_interval(ts, close=100.0, high=100.5, low=99.5))  # Back within envelope
    pldot_series.append(_pldot_series(ts, value=center, slope=-0.1))  # Keep center same
    envelopes.append(_envelope_series(ts, center=center, width=width, position=0.5))
    
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
