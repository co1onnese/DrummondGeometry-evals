"""Default multi-timeframe strategy implementation."""

from __future__ import annotations

from decimal import Decimal
from typing import Iterable

from .base import BaseStrategy, StrategyConfig, StrategyContext
from ..entities import Signal, SignalAction
from ...calculations.multi_timeframe import ConfluenceZone, MultiTimeframeAnalysis
from ...calculations.patterns import PatternEvent, PatternType
from ...calculations.states import TrendDirection


class MultiTimeframeStrategyConfig(StrategyConfig):
    name: str = "multi_timeframe"
    min_history: int = 5
    min_alignment: float = 0.6
    min_signal_strength: float = 0.55
    min_zone_weight: float = 2.5
    required_pattern_strength: int = 2
    max_risk_fraction: Decimal = Decimal("0.01")
    trailing_stop_multiple: Decimal = Decimal("1.0")
    target_rr_ratio: Decimal = Decimal("2.0")
    allow_short: bool = False


class MultiTimeframeStrategy(BaseStrategy):
    config_model = MultiTimeframeStrategyConfig

    def __init__(self, config: MultiTimeframeStrategyConfig | None = None) -> None:
        super().__init__(config or MultiTimeframeStrategyConfig())
        self._trail_state: dict[str, dict[str, Decimal]] = {}

    def on_bar(self, context: StrategyContext) -> Iterable[Signal]:
        history = context.history
        if len(history) < self.config.min_history:
            return []

        last_bar = history[-1]

        analysis = self._extract_analysis(context)
        if analysis is None:
            return []

        if not context.has_position():
            entry_signal = self._generate_entry_signal(context, last_bar.close, analysis)
            return [entry_signal] if entry_signal else []

        exit_signal = self._manage_open_position(context, last_bar.close, analysis)
        return [exit_signal] if exit_signal else []

    def _extract_analysis(self, context: StrategyContext) -> MultiTimeframeAnalysis | None:
        analysis = context.get_indicator("analysis")
        if isinstance(analysis, MultiTimeframeAnalysis):
            return analysis
        return None

    def _generate_entry_signal(
        self,
        context: StrategyContext,
        last_close: Decimal,
        analysis: MultiTimeframeAnalysis,
    ) -> Signal | None:
        direction = self._determine_direction(analysis)
        if direction is None:
            return None

        zone = self._select_zone(analysis, direction)
        if zone is None:
            return None

        if not self._has_supporting_pattern(analysis, direction):
            return None

        entry_price = zone.level
        stop_price = self._calculate_stop_from_zone(zone, direction)
        if stop_price is None:
            return None

        if direction == TrendDirection.UP and stop_price >= entry_price:
            return None
        if direction == TrendDirection.DOWN and stop_price <= entry_price:
            return None

        target_price = self._calculate_target(entry_price, stop_price, direction)
        quantity = self._position_size(context, entry_price, stop_price)
        if quantity <= 0:
            return None

        metadata = {
            "entry_zone": str(zone.level),
            "zone_weight": str(zone.weighted_strength),
            "zone_type": zone.zone_type,
            "trail_stop": str(stop_price),
        }

        self._trail_state[context.symbol] = {
            "trail": stop_price,
            "direction": Decimal("1") if direction == TrendDirection.UP else Decimal("-1"),
        }

        if direction == TrendDirection.UP:
            return Signal(SignalAction.ENTER_LONG, size=quantity, metadata=metadata)
        if direction == TrendDirection.DOWN and self.config.allow_short:
            return Signal(SignalAction.ENTER_SHORT, size=quantity, metadata=metadata)
        return None

    def _manage_open_position(
        self,
        context: StrategyContext,
        last_close: Decimal,
        analysis: MultiTimeframeAnalysis,
    ) -> Signal | None:
        position = context.position
        if position is None:
            return None

        direction = TrendDirection.UP if position.side.name == "LONG" else TrendDirection.DOWN

        trail_info = self._trail_state.get(context.symbol)
        trail_price = trail_info.get("trail") if trail_info else None

        zone = self._select_zone(analysis, direction)
        if zone is not None:
            candidate_trail = self._calculate_stop_from_zone(zone, direction)
            if trail_price is None:
                trail_price = candidate_trail
            elif candidate_trail is not None:
                if direction == TrendDirection.UP:
                    trail_price = max(trail_price, candidate_trail)
                else:
                    trail_price = min(trail_price, candidate_trail)
            self._trail_state[context.symbol] = {
                "trail": trail_price,
                "direction": Decimal("1") if direction == TrendDirection.UP else Decimal("-1"),
            }

        if trail_price is not None:
            if direction == TrendDirection.UP and last_close <= trail_price:
                self._trail_state.pop(context.symbol, None)
                return Signal(SignalAction.EXIT_LONG)
            if direction == TrendDirection.DOWN and last_close >= trail_price:
                self._trail_state.pop(context.symbol, None)
                return Signal(SignalAction.EXIT_SHORT)

        if float(analysis.alignment.alignment_score) < self.config.min_alignment:
            self._trail_state.pop(context.symbol, None)
            return Signal(SignalAction.EXIT_LONG if direction == TrendDirection.UP else SignalAction.EXIT_SHORT)

        if analysis.recommended_action in {"reduce", "wait"} or analysis.risk_level == "high":
            self._trail_state.pop(context.symbol, None)
            return Signal(SignalAction.EXIT_LONG if direction == TrendDirection.UP else SignalAction.EXIT_SHORT)

        return None

    def _determine_direction(self, analysis: MultiTimeframeAnalysis) -> TrendDirection | None:
        if float(analysis.alignment.alignment_score) < self.config.min_alignment:
            return None
        if float(analysis.signal_strength) < self.config.min_signal_strength:
            return None
        if not analysis.alignment.trade_permitted:
            return None

        if analysis.recommended_action == "long" and analysis.htf_trend == TrendDirection.UP:
            return TrendDirection.UP
        if analysis.recommended_action == "short" and analysis.htf_trend == TrendDirection.DOWN:
            return TrendDirection.DOWN
        return None

    def _select_zone(
        self,
        analysis: MultiTimeframeAnalysis,
        direction: TrendDirection,
    ) -> ConfluenceZone | None:
        desired_type = "support" if direction == TrendDirection.UP else "resistance"
        zones = [
            zone
            for zone in analysis.confluence_zones
            if zone.zone_type == desired_type and float(zone.weighted_strength) >= self.config.min_zone_weight
        ]

        if not zones:
            return None

        return zones[0]

    def _has_supporting_pattern(self, analysis: MultiTimeframeAnalysis, direction: TrendDirection) -> bool:
        def _pattern_matches(event: PatternEvent) -> bool:
            directional_ok = event.direction == (1 if direction == TrendDirection.UP else -1)
            strength_ok = event.strength >= self.config.required_pattern_strength
            type_ok = event.pattern_type in {
                PatternType.PLDOT_PUSH,
                PatternType.C_WAVE,
                PatternType.PLDOT_REFRESH,
            }
            return directional_ok and strength_ok and type_ok

        return any(
            _pattern_matches(event)
            for event in list(analysis.trading_tf_patterns) + list(analysis.htf_patterns)
        )

    def _calculate_stop_from_zone(self, zone, direction: TrendDirection) -> Decimal | None:
        buffer = max(zone.volatility, Decimal("0.001") * zone.level)
        if direction == TrendDirection.UP:
            return zone.lower_bound - buffer * self.config.trailing_stop_multiple
        return zone.upper_bound + buffer * self.config.trailing_stop_multiple

    def _calculate_target(self, entry: Decimal, stop: Decimal, direction: TrendDirection) -> Decimal:
        risk = abs(entry - stop)
        reward = risk * self.config.target_rr_ratio
        if direction == TrendDirection.UP:
            return entry + reward
        return entry - reward

    def _position_size(self, context: StrategyContext, entry: Decimal, stop: Decimal) -> Decimal:
        risk_per_unit = abs(entry - stop)
        if risk_per_unit <= 0:
            return Decimal("0")

        risk_budget = context.equity * self.config.max_risk_fraction
        max_affordable = context.cash / entry if entry > 0 else Decimal("0")
        if risk_budget <= 0 or max_affordable <= 0:
            return Decimal("0")

        units = risk_budget / risk_per_unit
        quantity = min(units, max_affordable)
        return quantity.quantize(Decimal("1"))


__all__ = ["MultiTimeframeStrategy", "MultiTimeframeStrategyConfig"]
