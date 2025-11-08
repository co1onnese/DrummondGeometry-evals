"""Signal ranking and prioritization for portfolio-level backtesting.

Ranks trading signals when multiple opportunities exist,
ensuring the best signals are traded first when capital is limited.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Any, Callable, Dict, List

from ..data.repository import get_symbol_id
from ..db import get_connection
from .entities import Signal, SignalAction


class RankingCriteria(Enum):
    """Signal ranking criteria."""

    SIGNAL_STRENGTH = "signal_strength"
    RISK_REWARD_RATIO = "risk_reward_ratio"
    CONFLUENCE = "confluence"
    TREND_ALIGNMENT = "trend_alignment"
    VOLATILITY = "volatility"


@dataclass
class RankedSignal:
    """Signal with ranking score and metadata."""

    symbol: str
    signal: Signal
    score: Decimal
    entry_price: Decimal
    stop_loss: Decimal | None
    target: Decimal | None
    risk_amount: Decimal
    metadata: Dict[str, Any]

    @property
    def risk_reward_ratio(self) -> Decimal | None:
        """Calculate risk/reward ratio."""
        if self.stop_loss is None or self.target is None:
            return None

        risk = abs(self.entry_price - self.stop_loss)
        reward = abs(self.target - self.entry_price)

        if risk == 0:
            return None

        return reward / risk

    @property
    def is_long(self) -> bool:
        """Check if long signal."""
        return self.signal.action == SignalAction.ENTER_LONG

    @property
    def is_short(self) -> bool:
        """Check if short signal."""
        return self.signal.action == SignalAction.ENTER_SHORT


class SignalRanker:
    """Rank and prioritize trading signals."""

    def __init__(
        self,
        criteria_weights: Dict[RankingCriteria, Decimal] | None = None,
        min_risk_reward: Decimal = Decimal("1.5"),
        max_correlated_positions: int = 3,
    ):
        """Initialize signal ranker.

        Args:
            criteria_weights: Weights for ranking criteria
                             (default: balanced weights)
            min_risk_reward: Minimum risk/reward ratio to consider
            max_correlated_positions: Max positions in correlated symbols
        """
        if criteria_weights is None:
            # Default balanced weights
            criteria_weights = {
                RankingCriteria.SIGNAL_STRENGTH: Decimal("0.30"),
                RankingCriteria.RISK_REWARD_RATIO: Decimal("0.25"),
                RankingCriteria.CONFLUENCE: Decimal("0.20"),
                RankingCriteria.TREND_ALIGNMENT: Decimal("0.15"),
                RankingCriteria.VOLATILITY: Decimal("0.10"),
            }

        self.criteria_weights = criteria_weights
        self.min_risk_reward = min_risk_reward
        self.max_correlated_positions = max_correlated_positions
        
        # Cache for sector lookups (symbol -> sector)
        self._sector_cache: Dict[str, str] = {}

    def rank_signals(
        self,
        signals: List[RankedSignal],
        existing_positions: Dict[str, Any] | None = None,
    ) -> List[RankedSignal]:
        """Rank signals by composite score.

        Args:
            signals: List of signals to rank
            existing_positions: Current open positions (optional)

        Returns:
            Sorted list of signals (highest score first)
        """
        if not signals:
            return []

        # Calculate composite scores
        scored_signals = []

        for signal in signals:
            # Filter by minimum risk/reward
            if signal.risk_reward_ratio is not None:
                if signal.risk_reward_ratio < self.min_risk_reward:
                    continue

            # Calculate composite score
            score = self._calculate_composite_score(signal)

            # Apply position diversity penalty
            if existing_positions:
                diversity_factor = self._calculate_diversity_factor(
                    signal.symbol,
                    existing_positions,
                )
                score *= diversity_factor

            scored_signals.append((score, signal))

        # Sort by score (descending)
        scored_signals.sort(key=lambda x: x[0], reverse=True)

        # Update scores in signals
        ranked_signals = []
        for score, signal in scored_signals:
            signal.score = score
            ranked_signals.append(signal)

        return ranked_signals

    def _calculate_composite_score(self, signal: RankedSignal) -> Decimal:
        """Calculate composite ranking score.

        Args:
            signal: Signal to score

        Returns:
            Composite score (0-100)
        """
        scores = {}

        # Signal strength (from analysis)
        # Metadata stores values as strings, so convert if needed
        signal_strength = signal.metadata.get("signal_strength", 0.5)
        if isinstance(signal_strength, str):
            signal_strength = float(signal_strength) if signal_strength else 0.5
        scores[RankingCriteria.SIGNAL_STRENGTH] = Decimal(str(signal_strength)) * Decimal("100")

        # Risk/reward ratio
        if signal.risk_reward_ratio:
            # Normalize to 0-100 scale (cap at 5:1)
            rr_normalized = min(signal.risk_reward_ratio / Decimal("5"), Decimal("1")) * Decimal("100")
            scores[RankingCriteria.RISK_REWARD_RATIO] = rr_normalized
        else:
            scores[RankingCriteria.RISK_REWARD_RATIO] = Decimal("0")

        # Confluence (number of confluence zones)
        # Metadata stores values as strings, so convert if needed
        confluence_count = signal.metadata.get("confluence_zones_count", 0)
        if isinstance(confluence_count, str):
            confluence_count = int(confluence_count) if confluence_count else 0
        elif not isinstance(confluence_count, (int, float)):
            confluence_count = 0
        # Normalize to 0-100 (cap at 5 zones)
        scores[RankingCriteria.CONFLUENCE] = Decimal(str(min(confluence_count / 5, 1))) * Decimal("100")

        # Trend alignment
        # Metadata stores values as strings, so convert if needed
        alignment_score = signal.metadata.get("alignment_score", 0.5)
        if isinstance(alignment_score, str):
            alignment_score = float(alignment_score) if alignment_score else 0.5
        scores[RankingCriteria.TREND_ALIGNMENT] = Decimal(str(alignment_score)) * Decimal("100")

        # Volatility (inverse - prefer lower volatility)
        # Metadata stores values as strings, so convert if needed
        volatility = signal.metadata.get("volatility", 0.02)
        if isinstance(volatility, str):
            volatility = float(volatility) if volatility else 0.02
        # Lower volatility = higher score
        volatility_score = max(Decimal("0"), Decimal("1") - (Decimal(str(volatility)) * Decimal("50")))
        scores[RankingCriteria.VOLATILITY] = volatility_score * Decimal("100")

        # Calculate weighted composite
        composite = Decimal("0")
        for criteria, weight in self.criteria_weights.items():
            if criteria in scores:
                composite += scores[criteria] * weight

        return composite

    def _get_symbol_sector(self, symbol: str) -> str:
        """Get sector for symbol from database, with caching.

        Args:
            symbol: Market symbol

        Returns:
            Sector string, or "other" if not found
        """
        # Check cache first
        if symbol in self._sector_cache:
            return self._sector_cache[symbol]

        # Load from database
        sector = "other"  # Default
        try:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT sector FROM market_symbols WHERE symbol = %s",
                        (symbol,),
                    )
                    row = cur.fetchone()
                    if row and row[0]:
                        sector = row[0] or "other"
        except Exception:
            # If database query fails, use default
            pass

        # Cache result
        self._sector_cache[symbol] = sector
        return sector

    def _calculate_diversity_factor(
        self,
        symbol: str,
        existing_positions: Dict[str, Any],
    ) -> Decimal:
        """Calculate position diversity factor.

        Penalizes adding more positions in correlated symbols (same sector).

        Args:
            symbol: Symbol being considered
            existing_positions: Current positions

        Returns:
            Diversity factor (0-1, lower = more penalty)
        """
        symbol_sector = self._get_symbol_sector(symbol)

        # Count positions in same sector
        same_sector_count = 0
        for pos_symbol in existing_positions.keys():
            pos_sector = self._get_symbol_sector(pos_symbol)
            if pos_sector == symbol_sector:
                same_sector_count += 1

        # Apply penalty if too many in same sector
        if same_sector_count >= self.max_correlated_positions:
            return Decimal("0.5")  # 50% penalty
        elif same_sector_count >= 2:
            return Decimal("0.75")  # 25% penalty

        return Decimal("1.0")  # No penalty

    def select_top_signals(
        self,
        ranked_signals: List[RankedSignal],
        max_signals: int,
        min_score: Decimal | None = None,
    ) -> List[RankedSignal]:
        """Select top N signals.

        Args:
            ranked_signals: Ranked signals (should be sorted)
            max_signals: Maximum number of signals to select
            min_score: Minimum score threshold (optional)

        Returns:
            Top signals meeting criteria
        """
        selected = []

        for signal in ranked_signals:
            if len(selected) >= max_signals:
                break

            if min_score is not None and signal.score < min_score:
                continue

            selected.append(signal)

        return selected

    def group_by_direction(
        self,
        signals: List[RankedSignal],
    ) -> Dict[str, List[RankedSignal]]:
        """Group signals by direction (long/short).

        Args:
            signals: List of ranked signals

        Returns:
            Dictionary with 'long' and 'short' signal lists
        """
        long_signals = []
        short_signals = []

        for signal in signals:
            if signal.is_long:
                long_signals.append(signal)
            elif signal.is_short:
                short_signals.append(signal)

        return {
            "long": long_signals,
            "short": short_signals,
        }


__all__ = [
    "SignalRanker",
    "RankedSignal",
    "RankingCriteria",
]
