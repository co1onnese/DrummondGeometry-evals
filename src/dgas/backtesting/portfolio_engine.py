"""Portfolio-level backtesting engine.

Coordinates multi-symbol backtesting with shared capital pool,
ranking signals and managing positions across the entire portfolio.
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, ROUND_DOWN
from typing import Dict, List, Tuple, Optional, Any

from ..calculations.timeframe_builder import build_timeframe_data
from ..calculations.multi_timeframe import MultiTimeframeAnalysis, TimeframeType
from ..data.models import IntervalData
from .data_loader import BacktestDataset
from .entities import PortfolioSnapshot, PositionSide, SignalAction, Trade
from .indicator_loader import load_indicators_from_db
from .portfolio_data_loader import PortfolioDataLoader, PortfolioTimestep
from .portfolio_position_manager import PortfolioPositionManager, PortfolioState
from .portfolio_indicator_calculator import PortfolioIndicatorCalculator
from .signal_ranker import RankedSignal, SignalRanker
from .strategies.base import BaseStrategy, StrategyContext, rolling_history
from .signal_evaluator import SignalEvaluator


@dataclass
class PortfolioBacktestConfig:
    """Configuration for portfolio-level backtest."""

    initial_capital: Decimal = Decimal("100000")
    risk_per_trade_pct: Decimal = Decimal("0.02")  # 2% of portfolio
    max_positions: int = 20
    max_portfolio_risk_pct: Decimal = Decimal("0.10")  # 10% total
    commission_rate: Decimal = Decimal("0.0")
    slippage_bps: Decimal = Decimal("2.0")  # 2 basis points
    regular_hours_only: bool = True
    exchange_code: str = "US"
    max_signals_per_bar: int = 5  # Max new positions per timestamp
    allow_short: bool = True
    htf_interval: str = "1d"
    trading_interval: str = "30m"
    # Confidence-based filtering and sizing
    min_signal_confidence: Decimal = Decimal("0.5")  # Minimum confidence to execute signal
    confidence_scaling_enabled: bool = True  # Enable confidence-based position sizing


@dataclass
class PortfolioBacktestResult:
    """Results from portfolio-level backtest."""

    config: PortfolioBacktestConfig
    symbols: List[str]
    trades: List[Trade]
    equity_curve: List[PortfolioSnapshot]
    starting_capital: Decimal
    ending_capital: Decimal
    ending_equity: Decimal
    start_date: datetime
    end_date: datetime
    total_bars: int
    metadata: Dict[str, any] = field(default_factory=dict)

    @property
    def total_return(self) -> Decimal:
        """Calculate total return percentage."""
        if self.starting_capital == 0:
            return Decimal("0")
        return (self.ending_equity - self.starting_capital) / self.starting_capital

    @property
    def trade_count(self) -> int:
        """Number of closed trades."""
        return len(self.trades)


class PortfolioBacktestEngine:
    """Main portfolio backtesting engine."""

    def __init__(
        self,
        config: PortfolioBacktestConfig | None = None,
        strategy: BaseStrategy | None = None,
    ):
        """Initialize portfolio backtest engine.

        Args:
            config: Portfolio backtest configuration
            strategy: Trading strategy to use
        """
        self.config = config or PortfolioBacktestConfig()
        self.strategy = strategy

        # Initialize components
        self.data_loader = PortfolioDataLoader(
            regular_hours_only=self.config.regular_hours_only,
            exchange_code=self.config.exchange_code,
        )

        self.position_manager = PortfolioPositionManager(
            initial_capital=self.config.initial_capital,
            max_positions=self.config.max_positions,
            max_portfolio_risk_pct=self.config.max_portfolio_risk_pct,
            risk_per_trade_pct=self.config.risk_per_trade_pct,
            commission_rate=self.config.commission_rate,
            slippage_bps=self.config.slippage_bps,
        )

        self.signal_ranker = SignalRanker()

        # Indicator calculator for on-the-fly calculation
        self.indicator_calculator = PortfolioIndicatorCalculator(
            htf_interval=self.config.htf_interval,
            trading_interval=self.config.trading_interval,
        )

        # State tracking
        self.equity_curve: List[PortfolioSnapshot] = []
        self.history_by_symbol: Dict[str, any] = {}
        
        # Performance optimization: Limit history size to avoid recalculating everything
        # Only keep recent bars needed for indicator calculation (200 bars ≈ 100 hours at 30m)
        self.max_history_bars = 200
        
        # Signal evaluation tracking
        self.signal_evaluator = SignalEvaluator()

    def run(
        self,
        symbols: List[str],
        interval: str,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> PortfolioBacktestResult:
        """Run portfolio backtest across multiple symbols.

        Args:
            symbols: List of symbols to trade
            interval: Data interval (e.g., "30m")
            start: Start date (optional)
            end: End date (optional)

        Returns:
            PortfolioBacktestResult with complete results

        Raises:
            ValueError: If strategy not set or no data available
        """
        if self.strategy is None:
            raise ValueError("Strategy must be set before running backtest")

        print(f"\n{'='*80}")
        print(f"PORTFOLIO BACKTEST: {len(symbols)} symbols")
        print(f"Period: {start} to {end}")
        print(f"Initial Capital: ${self.config.initial_capital:,.2f}")
        print(f"Risk per Trade: {self.config.risk_per_trade_pct:.1%}")
        print(f"{'='*80}\n")

        # Load data for all symbols
        print("Loading market data...")
        bundles = self.data_loader.load_portfolio_data(symbols, interval, start, end)

        # Get data summary
        summary = self.data_loader.get_data_summary(bundles)
        print(f"Loaded {summary['symbol_count']} symbols, {summary['total_bars']:,} total bars")
        print(f"Date range: {summary['date_range'][0]} to {summary['date_range'][1]}")

        # Create synchronized timeline
        print("\nSynchronizing timeline...")
        timeline = self.data_loader.create_synchronized_timeline(bundles)
        print(f"Timeline: {len(timeline):,} unique timestamps\n")

        # Prepare strategy
        print("Preparing strategy...")
        all_bars = []
        for bundle in bundles.values():
            all_bars.extend([bar for bar in bundle.bars])
        self.strategy.prepare(all_bars)

        # Pre-load HTF data for all symbols (for indicator calculation)
        print("\nPre-loading HTF data for indicator calculation...")
        self.indicator_calculator.preload_htf_data_for_portfolio(symbols, start, end)
        cache_stats = self.indicator_calculator.get_cache_stats()
        print(f"✓ HTF cache ready: {cache_stats['total_htf_bars']:,} bars\n")

        # Initialize history for each symbol
        for symbol in symbols:
            self.history_by_symbol[symbol] = rolling_history()

        # Main backtest loop
        print(f"Running backtest...\n")
        progress_interval = max(1, len(timeline) // 20)  # Show progress 20 times

        for idx, timestep in enumerate(timeline):
            # Show progress
            if idx % progress_interval == 0 or idx == len(timeline) - 1:
                progress_pct = (idx + 1) / len(timeline) * 100
                print(f"Progress: {progress_pct:.1f}% ({idx+1:,}/{len(timeline):,} timesteps)", end="\r", flush=True)

            # Process this timestep
            self._process_timestep(timestep, idx, len(timeline))

        print(f"\n\nBacktest complete!")

        # Register all closed trades with signal evaluator
        for trade in self.position_manager.closed_trades:
            # Try to find signal_id from trade metadata if available
            # Note: Trade objects don't have metadata, so we'll match by symbol and time proximity
            self.signal_evaluator.register_trade(trade, signal_id=None)
        
        # Calculate signal accuracy metrics
        accuracy_metrics = self.signal_evaluator.calculate_metrics()
        
        # Create result
        metadata = {
            "data_summary": summary,
            "final_position_count": len(self.position_manager.positions),
            "signal_accuracy": {
                "total_signals": accuracy_metrics.total_signals,
                "executed_signals": accuracy_metrics.executed_signals,
                "win_rate": accuracy_metrics.win_rate,
                "winning_signals": accuracy_metrics.winning_signals,
                "losing_signals": accuracy_metrics.losing_signals,
                "avg_confidence_winning": accuracy_metrics.avg_confidence_winning,
                "avg_confidence_losing": accuracy_metrics.avg_confidence_losing,
                "signals_by_type": accuracy_metrics.signals_by_type,
                "win_rate_by_type": accuracy_metrics.win_rate_by_type,
                "win_rate_by_confidence_bucket": accuracy_metrics.win_rate_by_confidence_bucket,
            },
        }
        
        result = PortfolioBacktestResult(
            config=self.config,
            symbols=symbols,
            trades=self.position_manager.closed_trades,
            equity_curve=self.equity_curve,
            starting_capital=self.config.initial_capital,
            ending_capital=self.position_manager.cash,
            ending_equity=self.equity_curve[-1].equity if self.equity_curve else self.config.initial_capital,
            start_date=timeline[0].timestamp if timeline else start,
            end_date=timeline[-1].timestamp if timeline else end,
            total_bars=len(timeline),
            metadata=metadata,
        )

        return result

    def _process_timestep(self, timestep: PortfolioTimestep, idx: int, total: int) -> None:
        """Process single timestamp across all symbols.

        Args:
            timestep: Current timestep with all symbol data
            idx: Current index
            total: Total timesteps
        """
        # Get current prices
        current_prices = {
            symbol: bar.close for symbol, bar in timestep.bars.items()
        }

        # Update positions with current prices
        self.position_manager.update_positions(timestep.timestamp, current_prices)

        # Check for exits on existing positions
        self._check_exits(timestep, current_prices)

        # Record equity
        portfolio_state = self.position_manager.get_current_state(
            timestep.timestamp,
            current_prices,
        )

        self.equity_curve.append(
            PortfolioSnapshot(
                timestamp=timestep.timestamp,
                equity=portfolio_state.total_equity,
                cash=portfolio_state.cash,
            )
        )

        # Don't generate new signals on last bar
        if idx == total - 1:
            return

        # Generate entry signals for all symbols
        entry_signals = self._generate_entry_signals(timestep, portfolio_state)

        # Rank and select best signals
        if entry_signals:
            ranked_signals = self.signal_ranker.rank_signals(
                entry_signals,
                self.position_manager.positions,
            )

            # Select top signals
            max_new_positions = min(
                self.config.max_signals_per_bar,
                self.config.max_positions - len(self.position_manager.positions),
            )

            if max_new_positions > 0:
                selected_signals = self.signal_ranker.select_top_signals(
                    ranked_signals,
                    max_new_positions,
                )

                # Execute selected signals
                for ranked_signal in selected_signals:
                    self._execute_entry_signal(ranked_signal, timestep)

    def _generate_entry_signals(
        self,
        timestep: PortfolioTimestep,
        portfolio_state: PortfolioState,
    ) -> List[RankedSignal]:
        """Generate entry signals for all symbols at current timestep.

        Args:
            timestep: Current timestep
            portfolio_state: Current portfolio state

        Returns:
            List of ranked entry signals
        """
        signals = []

        # Phase 1: Prepare symbol data (update histories, filter positions)
        eligible_symbols = []
        for symbol, bar in timestep.bars.items():
            # Skip if already in position
            if portfolio_state.has_position(symbol):
                continue

            # Update history
            history = self.history_by_symbol[symbol]
            history.append(bar)
            
            # Limit history size for performance - only keep recent bars
            # This prevents recalculating indicators on ever-growing history
            if len(history) > self.max_history_bars:
                # Remove oldest bars, keeping only the most recent
                excess = len(history) - self.max_history_bars
                for _ in range(excess):
                    history.popleft()

            if len(history) < self.strategy.config.min_history:
                continue

            eligible_symbols.append((symbol, bar, history))

        # Phase 2: Calculate indicators in parallel
        indicator_results = {}

        def calculate_indicators_for_symbol(symbol_data):
            """Helper function to calculate indicators for one symbol."""
            symbol, bar, history = symbol_data
            try:
                indicators = self.indicator_calculator.calculate_indicators(
                    symbol=symbol,
                    current_bar=bar,
                    historical_bars=list(history),
                )
                return (symbol, indicators, None)
            except ValueError as e:
                return (symbol, None, str(e))

        # Calculate optimal worker count based on CPU cores and symbol count
        # Use all available CPUs for maximum parallelization
        cpu_count = os.cpu_count() or 4
        symbol_count = len(eligible_symbols)
        # Use all CPUs, but don't exceed symbol count (no point in more workers than symbols)
        # Remove the cap of 8 to use all available CPUs
        optimal_workers = min(cpu_count, symbol_count) if symbol_count > 0 else 1

        # Use ThreadPoolExecutor for parallel indicator calculation
        with ThreadPoolExecutor(max_workers=optimal_workers) as executor:
            # Submit all indicator calculation tasks
            futures = {
                executor.submit(calculate_indicators_for_symbol, symbol_data): symbol_data[0]
                for symbol_data in eligible_symbols
            }

            # Collect results as they complete
            for future in as_completed(futures):
                symbol, indicators, error = future.result()
                if indicators is not None:
                    indicator_results[symbol] = indicators

        # Get current prices for position sizing
        current_prices = {
            symbol: bar.close for symbol, bar in timestep.bars.items()
        }

        # Phase 3: Generate signals from calculated indicators (sequential)
        for symbol, bar, history in eligible_symbols:
            # Skip if indicator calculation failed
            if symbol not in indicator_results:
                continue

            indicators = indicator_results[symbol]

            # Extract confidence from analysis
            analysis = indicators.get("analysis")
            if isinstance(analysis, MultiTimeframeAnalysis):
                confidence = float(analysis.signal_strength)  # 0.0 to 1.0
            else:
                confidence = 0.5  # Default if no analysis

            # Filter by minimum confidence
            if confidence < float(self.config.min_signal_confidence):
                continue  # Skip low-confidence signals

            # Build context for strategy
            context = StrategyContext(
                symbol=symbol,
                bar=bar,
                position=None,
                cash=portfolio_state.cash,
                equity=portfolio_state.total_equity,
                indicators=indicators,
                history=history,
            )

            # Get signals from strategy
            strategy_signals = list(self.strategy.on_bar(context))

            # Convert to ranked signals
            for signal in strategy_signals:
                # Register signal with evaluator if it's from PredictionSignalStrategy
                if hasattr(self.strategy, '_get_signal_generator'):
                    # This is a PredictionSignalStrategy - register the signal
                    # Extract signal info from metadata
                    metadata = dict(signal.metadata) if signal.metadata else {}
                    signal_id = metadata.get("signal_id")
                    if signal_id:
                        # Reconstruct GeneratedSignal from metadata for evaluation
                        from dgas.prediction.engine import GeneratedSignal, SignalType
                        from dgas.calculations.states import TrendDirection
                        
                        try:
                            signal_type_str = "LONG" if signal.action == SignalAction.ENTER_LONG else "SHORT"
                            signal_type = SignalType[signal_type_str]
                            
                            gen_signal = GeneratedSignal(
                                symbol=symbol,
                                signal_timestamp=bar.timestamp,
                                signal_type=signal_type,
                                entry_price=Decimal(metadata.get("entry_price", bar.close)),
                                stop_loss=Decimal(metadata.get("stop_loss", bar.close * Decimal("0.98"))),
                                target_price=Decimal(metadata.get("target_price", bar.close * Decimal("1.02"))),
                                confidence=float(metadata.get("confidence", 0.5)),
                                signal_strength=float(metadata.get("signal_strength", 0.5)),
                                timeframe_alignment=float(metadata.get("timeframe_alignment", 0.5)),
                                risk_reward_ratio=float(metadata.get("risk_reward_ratio", 2.0)),
                                htf_trend=TrendDirection[metadata.get("htf_trend", "UP")],
                                trading_tf_state=metadata.get("trading_tf_state", "TREND"),
                                confluence_zones_count=int(metadata.get("confluence_zones_count", 0)),
                                pattern_context={},
                                htf_timeframe=metadata.get("htf_timeframe", "1d"),
                                trading_timeframe=metadata.get("trading_timeframe", "30m"),
                            )
                            self.signal_evaluator.register_signal(gen_signal)
                        except Exception:
                            # If signal reconstruction fails, skip evaluation
                            pass
                if signal.action in [SignalAction.ENTER_LONG, SignalAction.ENTER_SHORT]:
                    # Extract metadata
                    metadata = dict(signal.metadata) if signal.metadata else {}

                    # Add confidence to metadata
                    metadata["confidence"] = str(confidence)
                    if isinstance(analysis, MultiTimeframeAnalysis):
                        metadata["signal_strength"] = str(analysis.signal_strength)

                    # Get prices from metadata or use defaults
                    entry_price = bar.close
                    stop_loss = metadata.get("trail_stop") or metadata.get("stop_loss")
                    if isinstance(stop_loss, str):
                        stop_loss = Decimal(stop_loss)
                    
                    # Extract take-profit from metadata
                    take_profit = metadata.get("take_profit") or metadata.get("target")
                    if isinstance(take_profit, str):
                        take_profit = Decimal(take_profit)

                    # Calculate base position size
                    if stop_loss:
                        base_quantity, base_risk = self.position_manager.calculate_position_size(
                            symbol,
                            entry_price,
                            stop_loss,
                            1 if signal.action == SignalAction.ENTER_LONG else -1,
                            current_prices=current_prices,
                        )

                        # Scale by confidence if enabled
                        if self.config.confidence_scaling_enabled:
                            confidence_multiplier = Decimal(str(confidence))  # 0.0 to 1.0
                            adjusted_quantity = base_quantity * confidence_multiplier
                            adjusted_risk = base_risk * confidence_multiplier
                            
                            # Normalize quantity (round to whole shares)
                            adjusted_quantity = adjusted_quantity.quantize(Decimal("1"), rounding=ROUND_DOWN)
                            
                            # Use adjusted values
                            quantity = adjusted_quantity
                            risk_amount = adjusted_risk
                        else:
                            quantity = base_quantity
                            risk_amount = base_risk

                        if quantity > 0:
                            ranked_signal = RankedSignal(
                                symbol=symbol,
                                signal=signal,
                                score=Decimal("0"),  # Will be set by ranker
                                entry_price=entry_price,
                                stop_loss=stop_loss,
                                target=take_profit,
                                risk_amount=risk_amount,
                                metadata=metadata,
                            )
                            signals.append(ranked_signal)

        return signals

    def _execute_entry_signal(
        self,
        ranked_signal: RankedSignal,
        timestep: PortfolioTimestep,
    ) -> None:
        """Execute entry signal.

        Args:
            ranked_signal: Signal to execute
            timestep: Current timestep
        """
        try:
            side = PositionSide.LONG if ranked_signal.is_long else PositionSide.SHORT

            # Get current prices for equity calculation
            current_prices = {
                symbol: bar.close for symbol, bar in timestep.bars.items()
            }

            # Calculate position size
            quantity, risk_amount = self.position_manager.calculate_position_size(
                ranked_signal.symbol,
                ranked_signal.entry_price,
                ranked_signal.stop_loss or ranked_signal.entry_price * Decimal("0.98"),
                1 if ranked_signal.is_long else -1,
                current_prices=current_prices,
            )

            if quantity > 0:
                self.position_manager.open_position(
                    symbol=ranked_signal.symbol,
                    side=side,
                    quantity=quantity,
                    entry_price=ranked_signal.entry_price,
                    entry_time=timestep.timestamp,
                    stop_loss=ranked_signal.stop_loss,
                    target=ranked_signal.target,
                    metadata=ranked_signal.metadata,
                )

        except ValueError as e:
            # Position couldn't be opened (likely risk limits)
            pass

    def _check_exits(
        self,
        timestep: PortfolioTimestep,
        current_prices: Dict[str, Decimal],
    ) -> None:
        """Check and execute exits on existing positions using intraday prices.

        Args:
            timestep: Current timestep with full bar data
            current_prices: Current prices for all symbols (bar.close)
        """
        symbols_to_close: Dict[str, Decimal] = {}  # symbol -> exit_price

        for symbol, portfolio_pos in self.position_manager.positions.items():
            if symbol not in timestep.bars:
                continue

            bar = timestep.bars[symbol]
            exit_price = None

            # Check stop loss using intraday prices
            if portfolio_pos.stop_loss:
                if portfolio_pos.side == PositionSide.LONG:
                    # Stop-loss hit if low touched or went below stop-loss
                    if bar.low <= portfolio_pos.stop_loss:
                        exit_price = portfolio_pos.stop_loss
                        symbols_to_close[symbol] = exit_price
                        continue
                else:  # SHORT
                    # Stop-loss hit if high touched or went above stop-loss
                    if bar.high >= portfolio_pos.stop_loss:
                        exit_price = portfolio_pos.stop_loss
                        symbols_to_close[symbol] = exit_price
                        continue

            # Check target using intraday prices
            if portfolio_pos.target:
                if portfolio_pos.side == PositionSide.LONG:
                    # Target hit if high touched or went above target
                    if bar.high >= portfolio_pos.target:
                        exit_price = portfolio_pos.target
                        symbols_to_close[symbol] = exit_price
                        continue
                else:  # SHORT
                    # Target hit if low touched or went below target
                    if bar.low <= portfolio_pos.target:
                        exit_price = portfolio_pos.target
                        symbols_to_close[symbol] = exit_price
                        continue

        # Execute exits at appropriate prices
        for symbol, exit_price in symbols_to_close.items():
            try:
                # Exit at stop-loss/target price (slippage will be applied by executor)
                self.position_manager.close_position(
                    symbol,
                    exit_price,
                    timestep.timestamp,
                )
            except ValueError:
                pass  # Position already closed


__all__ = [
    "PortfolioBacktestEngine",
    "PortfolioBacktestConfig",
    "PortfolioBacktestResult",
]
