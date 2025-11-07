from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from dgas.backtesting.data_loader import load_dataset
from dgas.calculations.multi_timeframe import MultiTimeframeAnalysis
from dgas.data.models import IntervalData


def _make_interval(ts: datetime, close: Decimal, interval: str) -> IntervalData:
    return IntervalData(
        symbol="AAPL",
        exchange="NASDAQ",
        timestamp=ts.isoformat(),
        interval=interval,
        open=close,
        high=close + Decimal("1"),
        low=close - Decimal("1"),
        close=close,
        adjusted_close=close,
        volume=1,
    )


@pytest.fixture
def synthetic_data():
    now = datetime(2025, 1, 1, tzinfo=timezone.utc)
    trading_interval = "1h"
    htf_interval = "4h"

    trading_bars = [
        _make_interval(now - timedelta(hours=3 - idx), Decimal("100") + Decimal(idx), trading_interval)
        for idx in range(4)
    ]
    htf_bars = [
        _make_interval(now - timedelta(hours=12 - 4 * idx), Decimal("100") + Decimal("0.5") * idx, htf_interval)
        for idx in range(4)
    ]
    return trading_interval, htf_interval, trading_bars, htf_bars


def test_load_dataset_includes_multi_timeframe_analysis(monkeypatch, synthetic_data):
    trading_interval, htf_interval, trading_bars, htf_bars = synthetic_data

    def fake_load(symbol, interval, *, start=None, end=None, limit=None, conn=None):
        if interval == trading_interval:
            return trading_bars
        if interval == htf_interval:
            return htf_bars
        return []

    monkeypatch.setattr("dgas.backtesting.data_loader.load_ohlcv", fake_load)

    dataset = load_dataset(
        "AAPL",
        trading_interval,
        include_indicators=True,
        htf_interval=htf_interval,
    )

    assert dataset.bars
    indicators = dataset.bars[-1].indicators
    assert "analysis" in indicators
    assert isinstance(indicators["analysis"], MultiTimeframeAnalysis)
