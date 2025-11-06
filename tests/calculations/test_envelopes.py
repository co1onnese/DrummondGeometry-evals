from datetime import datetime, timedelta, timezone

from dgas.calculations.envelopes import EnvelopeCalculator
from dgas.calculations.pldot import PLDotCalculator
from dgas.data.models import IntervalData


def _make_interval(ts: datetime, high: float, low: float, close: float) -> IntervalData:
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


def _sample_data():
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    intervals = [
        _make_interval(base + timedelta(minutes=30 * i), 10 + i, 8 + i, 9 + i)
        for i in range(20)
    ]
    pldot_calc = PLDotCalculator()
    pldot = pldot_calc.from_intervals(intervals)
    return intervals, pldot


def test_envelope_percentage_method():
    intervals, pldot = _sample_data()
    calc = EnvelopeCalculator(method="percentage", percent=0.05)
    envelopes = calc.from_intervals(intervals, pldot)

    assert envelopes
    first = envelopes[-1]
    assert first.upper > first.center
    assert first.lower < first.center
    assert first.width == first.upper - first.lower


def test_envelope_atr_method():
    intervals, pldot = _sample_data()
    calc = EnvelopeCalculator(method="atr", period=5, multiplier=1.5)
    envelopes = calc.from_intervals(intervals, pldot)

    assert envelopes
    last = envelopes[-1]
    assert last.upper > last.center
    assert last.lower < last.center
    assert 0 <= float(last.position) <= 1


def test_envelope_pldot_range_method():
    """Test the default Drummond method: pldot_range (3-period std dev)."""
    intervals, pldot = _sample_data()
    # Default method is pldot_range with period=3, multiplier=1.5
    calc = EnvelopeCalculator(method="pldot_range", period=3, multiplier=1.5)
    envelopes = calc.from_intervals(intervals, pldot)

    assert envelopes
    # Should have envelopes for all intervals with PLdot
    assert len(envelopes) > 0
    
    # Check properties of last envelope
    last = envelopes[-1]
    assert last.upper > last.center
    assert last.lower < last.center
    assert last.width == last.upper - last.lower
    assert 0 <= float(last.position) <= 1
    assert last.method == "pldot_range"
    
    # The pldot_range method should produce narrower bands than ATR
    # (since it's based on 3-period std dev vs 14-period ATR)
    atr_calc = EnvelopeCalculator(method="atr", period=14, multiplier=2.0)
    atr_envelopes = atr_calc.from_intervals(intervals, pldot)
    if atr_envelopes:
        # pldot_range should generally be narrower (more responsive)
        # Note: This may vary, but the 3-period std dev should be tighter
        pldot_width = float(last.width)
        atr_width = float(atr_envelopes[-1].width)
        # For trending data, pldot_range should be narrower
        assert pldot_width <= atr_width * 1.5  # Allow some variance


def test_envelope_default_method():
    """Test that default constructor uses pldot_range method."""
    intervals, pldot = _sample_data()
    # No method specified - should default to pldot_range
    calc = EnvelopeCalculator()
    envelopes = calc.from_intervals(intervals, pldot)

    assert envelopes
    assert envelopes[-1].method == "pldot_range"
    assert calc.method == "pldot_range"
    assert calc.period == 3  # Default period
    assert calc.multiplier == 1.5  # Default multiplier
