"""Tests for the enhanced multi-timeframe strategy."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta

from decimal import Decimal

import pytest

from dgas.backtesting.entities import Position, PositionSide, SignalAction
from dgas.backtesting.strategies.base import StrategyContext, rolling_history
from dgas.backtesting.strategies.multi_timeframe import (
    MultiTimeframeStrategy,
    MultiTimeframeStrategyConfig,
)
from dgas.calculations.multi_timeframe import (
    ConfluenceZone,
    MultiTimeframeAnalysis,
    PLDotOverlay,
    TimeframeAlignment,
)
from dgas.calculations.patterns import PatternEvent, PatternType
from dgas.calculations.states import MarketState, TrendDirection
from dgas.data.models import IntervalData


def make_interval(close: str, timestamp: datetime) -> IntervalData:
    price = Decimal(close)
    return IntervalData(
        symbol="AAPL",
        exchange="NASDAQ",
        timestamp=timestamp.isoformat(),
        interval="1h",
        open=price,
        high=price + Decimal("1"),
        low=price - Decimal("1"),
        close=price,
        adjusted_close=price,
        volume=1000,
    )


def build_analysis(now: datetime, recommended: str, zone_type: str = "support") -> MultiTimeframeAnalysis:
    alignment = TimeframeAlignment(
        timestamp=now,
        htf_state=MarketState.TREND,
        htf_direction=TrendDirection.UP if zone_type == "support" else TrendDirection.DOWN,
        htf_confidence=Decimal("0.85"),
        trading_tf_state=MarketState.TREND,
        trading_tf_direction=TrendDirection.UP if zone_type == "support" else TrendDirection.DOWN,
        trading_tf_confidence=Decimal("0.80"),
        alignment_score=Decimal("0.75"),
        alignment_type="partial",
        trade_permitted=True,
    )

    pldot_overlay = PLDotOverlay(
        timestamp=now,
        htf_timeframe="4h",
        htf_pldot_value=Decimal("100.00"),
        htf_slope=Decimal("0.01"),
        ltf_timeframe="1h",
        ltf_pldot_value=Decimal("100.00"),
        distance_percent=Decimal("0.0"),
        position="at_htf",
    )

    zone = ConfluenceZone(
        level=Decimal("100.00"),
        upper_bound=Decimal("100.40"),
        lower_bound=Decimal("99.50"),
        strength=2,
        timeframes=["4h", "1h"],
        zone_type=zone_type,
        first_touch=now,
        last_touch=now,
        weighted_strength=Decimal("3.0"),
        sources={"4h": "drummond_zone", "1h": "envelope"},
        volatility=Decimal("0.40"),
    )

    pattern = PatternEvent(
        pattern_type=PatternType.PLDOT_PUSH,
        direction=1 if zone_type == "support" else -1,
        start_timestamp=now,
        end_timestamp=now,
        strength=3,
    )

    return MultiTimeframeAnalysis(
        timestamp=now,
        htf_timeframe="4h",
        trading_timeframe="1h",
        ltf_timeframe=None,
        htf_trend=TrendDirection.UP if zone_type == "support" else TrendDirection.DOWN,
        htf_trend_strength=Decimal("0.8"),
        trading_tf_trend=TrendDirection.UP if zone_type == "support" else TrendDirection.DOWN,
        alignment=alignment,
        pldot_overlay=pldot_overlay,
        confluence_zones=[zone],
        htf_patterns=[pattern],
        trading_tf_patterns=[],
        pattern_confluence=True,
        signal_strength=Decimal("0.7"),
        risk_level="medium",
        recommended_action=recommended,
    )


def build_context(analysis: MultiTimeframeAnalysis, prices: list[str]) -> StrategyContext:
    now = analysis.timestamp
    history = rolling_history(maxlen=50)
    for idx, price in enumerate(prices):
        offset_hours = len(prices) - idx - 1
        ts = now - timedelta(hours=offset_hours)
        history.append(make_interval(price, ts))

    current_bar = make_interval(prices[-1], now)

    return StrategyContext(
        symbol="AAPL",
        bar=current_bar,
        position=None,
        cash=Decimal("100000"),
        equity=Decimal("100000"),
        indicators={"analysis": analysis},
        history=history,
    )


def test_strategy_enters_long_with_confluence():
    now = datetime.now(timezone.utc)
    analysis = build_analysis(now, "long", zone_type="support")
    context = build_context(analysis, ["99", "99.5", "100", "100.5", "101"])

    strategy = MultiTimeframeStrategy(MultiTimeframeStrategyConfig())
    signals = list(strategy.on_bar(context))

    assert len(signals) == 1
    signal = signals[0]
    assert signal.action is SignalAction.ENTER_LONG
    assert Decimal(signal.metadata["entry_zone"]) == Decimal("100.00")
    assert Decimal(signal.size) == Decimal("1000")  # Risk-based position sizing


def test_strategy_skips_without_supporting_pattern():
    now = datetime.now(timezone.utc)
    analysis = build_analysis(now, "long", zone_type="support")
    analysis = MultiTimeframeAnalysis(
        timestamp=analysis.timestamp,
        htf_timeframe=analysis.htf_timeframe,
        trading_timeframe=analysis.trading_timeframe,
        ltf_timeframe=analysis.ltf_timeframe,
        htf_trend=analysis.htf_trend,
        htf_trend_strength=analysis.htf_trend_strength,
        trading_tf_trend=analysis.trading_tf_trend,
        alignment=analysis.alignment,
        pldot_overlay=analysis.pldot_overlay,
        confluence_zones=analysis.confluence_zones,
        htf_patterns=[],
        trading_tf_patterns=[],
        pattern_confluence=False,
        signal_strength=analysis.signal_strength,
        risk_level=analysis.risk_level,
        recommended_action=analysis.recommended_action,
    )

    context = build_context(analysis, ["99", "99.5", "100", "100.5", "101"])
    strategy = MultiTimeframeStrategy(MultiTimeframeStrategyConfig())

    signals = list(strategy.on_bar(context))
    assert signals == []


def test_trailing_stop_exit_triggers():
    now = datetime.now(timezone.utc)
    analysis = build_analysis(now, "long", zone_type="support")
    context = build_context(analysis, ["100", "100.5", "101", "100.8", "99.0"])

    position = Position(
        symbol="AAPL",
        side=PositionSide.LONG,
        quantity=Decimal("1000"),
        entry_price=Decimal("100.00"),
        entry_time=now,
    )

    context = StrategyContext(
        symbol="AAPL",
        bar=context.bar,
        position=position,
        cash=Decimal("50000"),
        equity=Decimal("100000"),
        indicators={"analysis": analysis},
        history=context.history,
    )

    strategy = MultiTimeframeStrategy(MultiTimeframeStrategyConfig())
    strategy._trail_state["AAPL"] = {"trail": Decimal("99.2"), "direction": Decimal("1")}

    signals = list(strategy.on_bar(context))
    assert len(signals) == 1
    assert signals[0].action is SignalAction.EXIT_LONG
