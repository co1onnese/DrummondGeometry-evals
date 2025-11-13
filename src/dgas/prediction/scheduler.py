"""
Prediction scheduler with market-hours awareness.

This module provides automated scheduling of prediction cycles during market hours,
with support for interval alignment, catch-up on startup, and graceful shutdown.
"""

from __future__ import annotations

import logging
import signal
import threading
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED

from ..data.exchange_calendar import ExchangeCalendar
from ..settings import Settings, get_settings
from .engine import PredictionEngine, PredictionRunResult
from .persistence import PredictionPersistence


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TradingSession:
    """
    Trading session configuration for an exchange.

    Defines the standard market hours and trading days. Actual hours
    may vary on specific dates (half-days, special closures).
    """
    market_open: time = time(9, 30)      # Standard open time (local)
    market_close: time = time(16, 0)      # Standard close time (local)
    timezone: str = "America/New_York"    # IANA timezone
    trading_days: List[str] = field(default_factory=lambda: ["MON", "TUE", "WED", "THU", "FRI"])

    def __post_init__(self):
        """Validate session configuration."""
        if self.market_open >= self.market_close:
            raise ValueError(f"market_open ({self.market_open}) must be before market_close ({self.market_close})")

        # Validate timezone
        try:
            ZoneInfo(self.timezone)
        except Exception as e:
            raise ValueError(f"Invalid timezone '{self.timezone}': {e}") from e


@dataclass
class SchedulerConfig:
    """Configuration for prediction scheduler."""

    # Execution settings
    interval: str = "30min"  # Update frequency
    symbols: List[str] = field(default_factory=list)  # Watchlist
    enabled_timeframes: List[str] = field(default_factory=lambda: ["4h", "1h", "30min"])

    # Exchange settings
    exchange_code: str = "US"  # Exchange for calendar data
    trading_session: TradingSession = field(default_factory=TradingSession)

    # Signal filtering
    min_confidence: float = 0.6
    min_signal_strength: float = 0.5
    min_alignment: float = 0.6
    enabled_patterns: Optional[List[str]] = None  # None = all patterns

    # Performance settings
    max_symbols_per_cycle: int = 50  # Limit for performance
    timeout_seconds: int = 180  # Max cycle duration

    # Data freshness coordination
    wait_for_fresh_data: bool = True  # Wait for data collection to complete
    max_wait_minutes: int = 5  # Maximum time to wait for fresh data (0 = skip if stale)
    freshness_threshold_minutes: int = 15  # Maximum data age to consider fresh

    # Operational
    run_on_startup: bool = True  # Execute immediately on start
    catch_up_on_startup: bool = True  # Analyze missed intervals
    persist_state: bool = True  # Save scheduler state to DB


class MarketHoursManager:
    """
    Manage market hours and trading calendar with database backend.

    Uses ExchangeCalendar to query trading days, holidays, and special hours
    from the database (populated from EODHD API).
    """

    def __init__(
        self,
        exchange_code: str,
        session: TradingSession,
        calendar: Optional[ExchangeCalendar] = None,
    ):
        """
        Initialize market hours manager.

        Args:
            exchange_code: Exchange identifier (e.g., "US")
            session: Trading session configuration
            calendar: ExchangeCalendar instance (creates new if None)
        """
        self.exchange_code = exchange_code
        self.session = session
        self.calendar = calendar or ExchangeCalendar()
        self.tz = ZoneInfo(session.timezone)

        # Ensure calendar is synced
        try:
            self.calendar.sync_exchange_calendar(exchange_code, force_refresh=False)
        except Exception as e:
            logger.warning(f"Failed to sync exchange calendar on init: {e}")

    def is_market_open(self, dt: Optional[datetime] = None) -> bool:
        """
        Check if market is open at given time (or now).

        Args:
            dt: Datetime to check (UTC). If None, uses current time.

        Returns:
            True if market is currently open
        """
        if dt is None:
            dt = datetime.now(timezone.utc)

        # Convert to exchange local time
        local_dt = dt.astimezone(self.tz)
        check_date = local_dt.date()
        check_time = local_dt.time()

        # Check if trading day
        try:
            if not self.calendar.is_trading_day(self.exchange_code, check_date):
                return False
        except Exception as e:
            logger.warning(f"Error checking trading day: {e}")
            # Fall back to simple weekday check
            if local_dt.weekday() >= 5:  # Weekend
                return False

        # Get market hours for this specific day
        try:
            hours = self.calendar.get_trading_hours(self.exchange_code, check_date)
            if hours is None:
                return False
            market_open, market_close = hours
        except Exception as e:
            logger.warning(f"Error getting trading hours: {e}")
            # Fall back to session defaults
            market_open = self.session.market_open
            market_close = self.session.market_close

        # Check if current time is within trading hours
        return market_open <= check_time <= market_close

    def next_market_open(self, from_dt: Optional[datetime] = None) -> datetime:
        """
        Calculate next market open time.

        Args:
            from_dt: Starting datetime (UTC). If None, uses current time.

        Returns:
            Next market open datetime (UTC)
        """
        if from_dt is None:
            from_dt = datetime.now(timezone.utc)

        local_dt = from_dt.astimezone(self.tz)
        check_date = local_dt.date()

        # If market is currently open, return current session open
        if self.is_market_open(from_dt):
            try:
                hours = self.calendar.get_trading_hours(self.exchange_code, check_date)
                if hours:
                    market_open = hours[0]
                else:
                    market_open = self.session.market_open
            except Exception:
                market_open = self.session.market_open

            return datetime.combine(check_date, market_open, tzinfo=self.tz).astimezone(timezone.utc)

        # Otherwise, find next trading day
        for days_ahead in range(10):  # Check up to 10 days ahead
            candidate_date = check_date + timedelta(days=days_ahead + 1)

            try:
                if self.calendar.is_trading_day(self.exchange_code, candidate_date):
                    hours = self.calendar.get_trading_hours(self.exchange_code, candidate_date)
                    market_open = hours[0] if hours else self.session.market_open

                    return datetime.combine(candidate_date, market_open, tzinfo=self.tz).astimezone(timezone.utc)
            except Exception:
                # Fall back to weekday check
                if candidate_date.weekday() < 5:
                    return datetime.combine(
                        candidate_date,
                        self.session.market_open,
                        tzinfo=self.tz
                    ).astimezone(timezone.utc)

        # Fallback: next weekday
        days_to_add = (7 - check_date.weekday()) % 7 or 1
        next_date = check_date + timedelta(days=days_to_add)
        return datetime.combine(next_date, self.session.market_open, tzinfo=self.tz).astimezone(timezone.utc)

    def next_market_close(self, from_dt: Optional[datetime] = None) -> datetime:
        """
        Calculate next market close time.

        Args:
            from_dt: Starting datetime (UTC). If None, uses current time.

        Returns:
            Next market close datetime (UTC)
        """
        if from_dt is None:
            from_dt = datetime.now(timezone.utc)

        local_dt = from_dt.astimezone(self.tz)
        check_date = local_dt.date()
        check_time = local_dt.time()

        # Get today's hours
        try:
            hours = self.calendar.get_trading_hours(self.exchange_code, check_date)
            if hours and check_time < hours[1]:
                # Market close is later today
                return datetime.combine(check_date, hours[1], tzinfo=self.tz).astimezone(timezone.utc)
        except Exception:
            pass

        # Market already closed today, get next trading day's close
        next_open = self.next_market_open(from_dt)
        next_date = next_open.astimezone(self.tz).date()

        try:
            hours = self.calendar.get_trading_hours(self.exchange_code, next_date)
            market_close = hours[1] if hours else self.session.market_close
        except Exception:
            market_close = self.session.market_close

        return datetime.combine(next_date, market_close, tzinfo=self.tz).astimezone(timezone.utc)

    def is_trading_day(self, dt: datetime) -> bool:
        """
        Check if given date is a trading day.

        Args:
            dt: Datetime to check

        Returns:
            True if it's a trading day (not weekend/holiday)
        """
        local_dt = dt.astimezone(self.tz)
        check_date = local_dt.date()

        try:
            return self.calendar.is_trading_day(self.exchange_code, check_date)
        except Exception as e:
            logger.warning(f"Error checking trading day: {e}")
            # Fallback to simple weekday check
            return local_dt.weekday() < 5


class PredictionScheduler:
    """
    Orchestrate periodic prediction execution with market-hours awareness.

    Uses APScheduler for robust scheduling with support for:
    - Interval-based execution aligned to market hours
    - Catch-up on startup for missed intervals
    - Graceful shutdown
    - Error handling without crashing
    """

    def __init__(
        self,
        config: SchedulerConfig,
        engine: PredictionEngine,
        persistence: PredictionPersistence,
        market_hours: Optional[MarketHoursManager] = None,
        settings: Optional[Settings] = None,
        performance_tracker: Optional[Any] = None,  # PerformanceTracker (avoid circular import)
    ):
        """
        Initialize scheduler.

        Args:
            config: Scheduler configuration
            engine: Prediction engine for executing cycles
            persistence: Database persistence layer
            market_hours: Market hours manager (created from config if None)
            settings: Settings instance (uses get_settings() if None)
            performance_tracker: Performance tracker for metrics (created if None)
        """
        self.config = config
        self.engine = engine
        self.persistence = persistence
        self.settings = settings or get_settings()

        # Market hours manager
        if market_hours is None:
            market_hours = MarketHoursManager(
                config.exchange_code,
                config.trading_session,
            )
        self.market_hours = market_hours

        # Performance tracker (Week 5 addition)
        if performance_tracker is None:
            from .monitoring import PerformanceTracker
            performance_tracker = PerformanceTracker(persistence)
        self.performance_tracker = performance_tracker

        # APScheduler instance
        self.scheduler = BackgroundScheduler(timezone=config.trading_session.timezone)
        self.scheduler.add_listener(self._job_listener, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)

        # State
        self._is_running = False
        self._shutdown_event = threading.Event()
        self._execution_lock = threading.Lock()

        # Setup signal handlers
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

    def start(self) -> None:
        """
        Start scheduler.

        Behavior:
        - Starts APScheduler in background
        - Optionally runs catch-up for missed intervals
        - Optionally runs initial cycle if config.run_on_startup=True
        - Updates scheduler_state to RUNNING
        """
        if self._is_running:
            logger.warning("Scheduler already running")
            return

        logger.info("Starting prediction scheduler")

        # Update state to RUNNING
        if self.config.persist_state:
            self.persistence.update_scheduler_state(
                status="RUNNING",
                next_scheduled_run=None,
                current_run_id=None,
                error_message=None,
            )

        # Catch up on missed intervals if enabled
        if self.config.catch_up_on_startup:
            self._run_catch_up()

        # Add scheduled job
        self._add_scheduled_job()

        # Start APScheduler
        self.scheduler.start()
        self._is_running = True

        # Run initial cycle if configured
        if self.config.run_on_startup and not self.config.catch_up_on_startup:
            self._execute_if_market_open()

        logger.info(f"Scheduler started with {self.config.interval} interval")

    def stop(self, wait: bool = True) -> None:
        """
        Graceful shutdown.

        Args:
            wait: If True, wait for current cycle to complete before stopping
        """
        if not self._is_running:
            logger.warning("Scheduler not running")
            return

        logger.info("Stopping prediction scheduler")
        self._shutdown_event.set()

        # Stop scheduler
        self.scheduler.shutdown(wait=wait)

        # Update state to STOPPED
        if self.config.persist_state:
            self.persistence.update_scheduler_state(
                status="STOPPED",
                next_scheduled_run=None,
                current_run_id=None,
                error_message=None,
            )

        self._is_running = False
        logger.info("Scheduler stopped")

    def run_once(self) -> PredictionRunResult:
        """
        Execute single prediction cycle manually.

        This bypasses market hours checks and is useful for testing.

        Returns:
            Prediction run result

        Raises:
            RuntimeError: If a cycle is already executing
        """
        if not self._execution_lock.acquire(blocking=False):
            raise RuntimeError("A prediction cycle is already executing")

        try:
            return self._execute_cycle()
        finally:
            self._execution_lock.release()

    def is_running(self) -> bool:
        """Check if scheduler is currently running."""
        return self._is_running

    def _add_scheduled_job(self) -> None:
        """Add scheduled job to APScheduler."""
        # Parse interval
        interval_minutes = self._parse_interval_minutes(self.config.interval)

        # Create cron trigger aligned to interval boundaries
        # For 30min: trigger at :00 and :30
        # For 60min: trigger at :00
        if interval_minutes == 30:
            trigger = CronTrigger(minute="0,30", timezone=self.config.trading_session.timezone)
        elif interval_minutes == 60:
            trigger = CronTrigger(minute="0", timezone=self.config.trading_session.timezone)
        elif interval_minutes == 15:
            trigger = CronTrigger(minute="0,15,30,45", timezone=self.config.trading_session.timezone)
        elif interval_minutes == 5:
            trigger = CronTrigger(minute="*/5", timezone=self.config.trading_session.timezone)
        else:
            # For other intervals, use simple minute-based trigger
            trigger = CronTrigger(minute=f"*/{interval_minutes}", timezone=self.config.trading_session.timezone)

        self.scheduler.add_job(
            func=self._execute_if_market_open,
            trigger=trigger,
            id="prediction_cycle",
            name="Prediction Cycle",
            max_instances=1,  # Prevent overlapping executions
        )

    def _execute_if_market_open(self) -> None:
        """
        Execute cycle with data refresh always, signal generation only during market hours.
        
        This ensures data stays fresh 24/7, while signals are only generated during
        market hours when they're actionable.
        
        Checks data freshness before generating signals to ensure WebSocket data
        collection has completed. Waits for fresh data if configured.
        """
        if self._shutdown_event.is_set():
            logger.debug("Shutdown event set, skipping prediction cycle")
            return

        # Acquire lock to prevent concurrent executions
        if not self._execution_lock.acquire(blocking=False):
            logger.warning("Prediction cycle already running, skipping this interval")
            return

        try:
            market_open = self.market_hours.is_market_open()
            
            if market_open:
                # Check data freshness before generating signals
                # WebSocket collection should be providing fresh data
                freshness_threshold = self.config.freshness_threshold_minutes
                
                if self.config.wait_for_fresh_data:
                    # Wait for fresh data with timeout
                    data_fresh = self._wait_for_fresh_data(
                        max_wait_minutes=self.config.max_wait_minutes,
                        freshness_threshold_minutes=freshness_threshold,
                    )
                    
                    if not data_fresh:
                        if self.config.max_wait_minutes == 0:
                            logger.warning(
                                f"Data not fresh (threshold: {freshness_threshold}min) and max_wait=0, "
                                "skipping signal generation"
                            )
                            return
                        else:
                            logger.warning(
                                f"Data still not fresh after waiting {self.config.max_wait_minutes} minutes, "
                                "proceeding with signal generation anyway"
                            )
                    else:
                        logger.info("Data is fresh, proceeding with signal generation")
                else:
                    # Just check without waiting
                    if not self._is_data_fresh(max_age_minutes=freshness_threshold):
                        logger.warning(
                            f"Data may be stale (threshold: {freshness_threshold}min) - "
                            "WebSocket collection may not be active. Proceeding anyway."
                        )
                
                logger.info("Starting prediction cycle (market is open - signal generation only)")
                # Full cycle: signal generation only (data assumed fresh from collection service)
                self._execute_cycle()
            else:
                logger.info("Skipping prediction cycle (market is closed)")
                # Market closed: skip signal generation
                # Data collection service handles data updates 24/7 independently
                
        except Exception as e:
            logger.error(f"Error executing prediction cycle: {e}", exc_info=True)
        finally:
            self._execution_lock.release()

    def _is_data_fresh(self, max_age_minutes: int = 15) -> bool:
        """
        Check if data is fresh (recently updated by collection service).

        Args:
            max_age_minutes: Maximum age in minutes to consider fresh

        Returns:
            True if data appears fresh
        """
        from datetime import datetime, timezone
        from ..data.repository import get_latest_timestamp, ensure_market_symbol
        from ..db import get_connection

        # Check a sample of symbols (larger sample for better accuracy)
        sample_size = min(20, len(self.config.symbols))
        sample_symbols = self.config.symbols[:sample_size]

        now = datetime.now(timezone.utc)
        stale_count = 0
        fresh_count = 0
        no_data_count = 0

        try:
            with get_connection() as conn:
                for symbol in sample_symbols:
                    try:
                        symbol_id = ensure_market_symbol(conn, symbol, "US")
                        latest_ts = get_latest_timestamp(conn, symbol_id, "30m")

                        if latest_ts:
                            age_minutes = (now - latest_ts).total_seconds() / 60.0
                            if age_minutes > max_age_minutes:
                                stale_count += 1
                            else:
                                fresh_count += 1
                        else:
                            # No data - consider stale
                            no_data_count += 1
                            stale_count += 1
                    except Exception as e:
                        # Error checking - assume stale
                        logger.debug(f"Error checking freshness for {symbol}: {e}")
                        stale_count += 1

            # Consider fresh if >= 70% of sample is fresh (more strict than before)
            freshness_ratio = fresh_count / sample_size if sample_size > 0 else 0.0
            is_fresh = freshness_ratio >= 0.7
            
            logger.debug(
                f"Data freshness check: {fresh_count} fresh, {stale_count} stale, "
                f"{no_data_count} no data, ratio={freshness_ratio:.2%}, threshold={max_age_minutes}min"
            )
            
            return is_fresh
        except Exception as e:
            logger.warning(f"Error checking data freshness: {e}")
            # On error, assume fresh (don't block signal generation)
            return True

    def _wait_for_fresh_data(
        self,
        max_wait_minutes: int = 5,
        freshness_threshold_minutes: int = 15,
        check_interval_seconds: int = 10,
    ) -> bool:
        """
        Wait for data to become fresh, with timeout.

        Args:
            max_wait_minutes: Maximum time to wait (0 = don't wait, just check)
            freshness_threshold_minutes: Maximum age to consider fresh
            check_interval_seconds: How often to check freshness

        Returns:
            True if data became fresh, False if timeout
        """
        import time
        
        if max_wait_minutes == 0:
            # Just check once, don't wait
            return self._is_data_fresh(max_age_minutes=freshness_threshold_minutes)
        
        start_time = time.time()
        max_wait_seconds = max_wait_minutes * 60
        check_count = 0
        
        logger.info(
            f"Waiting for fresh data (max {max_wait_minutes}min, "
            f"threshold: {freshness_threshold_minutes}min, check every {check_interval_seconds}s)"
        )
        
        while time.time() - start_time < max_wait_seconds:
            check_count += 1
            
            if self._is_data_fresh(max_age_minutes=freshness_threshold_minutes):
                elapsed = time.time() - start_time
                logger.info(
                    f"Data is fresh after {elapsed:.1f}s ({check_count} checks)"
                )
                return True
            
            # Wait before next check
            if time.time() - start_time + check_interval_seconds < max_wait_seconds:
                time.sleep(check_interval_seconds)
        
        # Timeout
        elapsed = time.time() - start_time
        logger.warning(
            f"Timeout waiting for fresh data after {elapsed:.1f}s ({check_count} checks)"
        )
        return False

    def _execute_data_refresh_only(self) -> None:
        """
        Execute data refresh only (no signal generation).
        
        NOTE: This method is deprecated. Data refresh is now handled by the
        separate data collection service. This method is kept for backward
        compatibility but does nothing. The data collection service runs
        24/7 and keeps data fresh independently.
        """
        logger.info(
            "Data refresh skipped - handled by separate data collection service. "
            "Prediction scheduler now assumes data is fresh."
        )

    def _execute_cycle(self) -> PredictionRunResult:
        """Execute full prediction pipeline with notifications."""
        import time
        # Ensure .env is loaded before loading notification config
        # (NotificationConfig.from_env() will also load it, but this ensures it's available)
        try:
            from dotenv import load_dotenv
            from pathlib import Path
            env_path = Path(__file__).parent.parent.parent / ".env"
            if env_path.exists():
                load_dotenv(env_path)
        except ImportError:
            pass  # python-dotenv not installed
        except Exception:
            pass  # Ignore errors loading .env
        
        from .notifications import NotificationConfig, NotificationRouter
        from .notifications.adapters import DiscordAdapter, ConsoleAdapter

        logger.info("Executing prediction cycle (full cycle with signals)")

        try:
            # Execute via engine - process all symbols in batches
            all_results = []
            all_signals = []
            total_symbols_processed = 0
            total_execution_time = 0
            
            # Process symbols in batches
            for batch_start in range(0, len(self.config.symbols), self.config.max_symbols_per_cycle):
                batch_symbols = self.config.symbols[batch_start:batch_start + self.config.max_symbols_per_cycle]
                logger.info(f"Processing batch {batch_start // self.config.max_symbols_per_cycle + 1}: {len(batch_symbols)} symbols")
                
                # Execute via engine
                batch_result = self.engine.execute_prediction_cycle(
                    symbols=batch_symbols,
                    interval="30m",  # Data interval (30m bars)
                    timeframes=self.config.enabled_timeframes,
                    htf_interval="30m",  # HTF interval
                    trading_interval="30m",  # Trading interval
                    persist_results=False,  # We'll persist after adding notification metadata
                )
                
                all_results.append(batch_result)
                all_signals.extend(batch_result.signals or [])
                total_symbols_processed += batch_result.symbols_processed
                total_execution_time += batch_result.execution_time_ms
            
            # Combine results
            if all_results:
                # Use first result as base and update with combined metrics
                from dataclasses import replace
                first_result = all_results[0]
                
                # Combine all errors
                all_errors = []
                for r in all_results:
                    all_errors.extend(r.errors or [])
                
                # Sum up timing metrics
                total_data_fetch_ms = sum(r.data_fetch_ms for r in all_results)
                total_indicator_calc_ms = sum(r.indicator_calc_ms for r in all_results)
                total_signal_gen_ms = sum(r.signal_generation_ms for r in all_results)
                
                result = replace(
                    first_result,
                    symbols_processed=total_symbols_processed,
                    signals_generated=len(all_signals),
                    execution_time_ms=total_execution_time,
                    signals=all_signals,
                    errors=all_errors,
                    data_fetch_ms=total_data_fetch_ms,
                    indicator_calc_ms=total_indicator_calc_ms,
                    signal_generation_ms=total_signal_gen_ms,
                    status="SUCCESS" if total_symbols_processed > 0 else "FAILED",
                )
            else:
                # No results, create empty result
                from .engine import PredictionRunResult
                result = PredictionRunResult(
                    run_id=None,
                    timestamp=datetime.now(timezone.utc),
                    symbols_requested=len(self.config.symbols),
                    symbols_processed=0,
                    signals_generated=0,
                    execution_time_ms=0,
                    status="FAILED",
                    data_fetch_ms=0,
                    indicator_calc_ms=0,
                    signal_generation_ms=0,
                    errors=["No symbols to process"],
                    signals=[],
                )

            # Send notifications if signals were generated
            notification_ms = 0
            notification_errors = []
            notification_metadata = {}  # Map of symbol -> notification metadata

            if result.signals_generated > 0:
                logger.info(f"Sending {result.signals_generated} signals to notification channels")
                notification_start = time.time()

                try:
                    # Load notification configuration
                    notif_config = NotificationConfig.from_env()

                    # Initialize enabled adapters (Discord only - primary channel)
                    adapters = {}

                    # Discord is the primary and only notification channel
                    if "discord" in notif_config.enabled_channels:
                        if notif_config.discord_bot_token and notif_config.discord_channel_id:
                            adapters["discord"] = DiscordAdapter(
                                bot_token=notif_config.discord_bot_token,
                                channel_id=notif_config.discord_channel_id,
                                # Note: min_confidence filtering is done by NotificationRouter
                            )
                            logger.info("Discord adapter initialized - Discord is the primary notification channel")
                        else:
                            logger.error("Discord enabled but token/channel ID missing - notifications will fail!")
                    
                    # Console adapter removed - Discord is the only channel
                    # Console logging is handled by Python logging, not notifications

                    # Send notifications if we have adapters and signals
                    sorted_signals = None  # Initialize for scope
                    if adapters and result.signals:
                        router = NotificationRouter(notif_config, adapters)

                        # Sort signals by timestamp (chronological order) before sending
                        # This ensures alerts are sent in the order they were generated
                        sorted_signals = sorted(
                            result.signals,
                            key=lambda s: s.signal_timestamp
                        )

                        # Prepare run metadata
                        run_metadata = {
                            "run_id": result.run_id or 0,
                            "run_timestamp": result.timestamp.isoformat(),
                            "symbols_processed": result.symbols_processed,
                            "interval": self.config.interval,
                        }

                        # Send notifications (signals are now in chronological order)
                        delivery_results = router.send_notifications(
                            signals=sorted_signals,
                            run_metadata=run_metadata,
                        )

                        # Log delivery results
                        for channel, success in delivery_results.items():
                            if success:
                                logger.info(f"Notifications sent successfully to {channel}")
                            else:
                                error_msg = f"Failed to send notifications to {channel}"
                                logger.error(error_msg)
                                notification_errors.append(error_msg)

                        # Get notification metadata for signals (use sorted signals)
                        notification_metadata = router.get_notification_metadata(
                            signals=sorted_signals,
                            delivery_results=delivery_results,
                        )
                    else:
                        if not adapters:
                            logger.debug("No notification adapters enabled")
                        if not result.signals:
                            logger.debug("No signals to notify")

                    notification_ms = int((time.time() - notification_start) * 1000)

                except Exception as e:
                    notification_ms = int((time.time() - notification_start) * 1000)
                    error_msg = f"Notification delivery failed: {str(e)}"
                    logger.error(error_msg, exc_info=True)
                    notification_errors.append(error_msg)

            # Persist results with notification timing
            if self.config.persist_state:
                try:
                    # Update result with notification timing
                    from dataclasses import replace

                    # Save prediction run with notification metrics
                    run_id = self.persistence.save_prediction_run(
                        interval_type=self.config.interval,
                        symbols_requested=result.symbols_requested,
                        symbols_processed=result.symbols_processed,
                        signals_generated=result.signals_generated,
                        execution_time_ms=result.execution_time_ms + notification_ms,
                        status=result.status,
                        data_fetch_ms=result.data_fetch_ms,
                        indicator_calc_ms=result.indicator_calc_ms,
                        signal_generation_ms=result.signal_generation_ms,
                        notification_ms=notification_ms,
                        errors=result.errors + notification_errors,
                        run_timestamp=result.timestamp,
                    )

                    # Save signals with notification metadata
                    if result.signals:
                        # Convert signals to dicts and merge notification metadata
                        # Use sorted_signals if available (for proper ordering)
                        signals_to_save = sorted_signals if sorted_signals is not None else result.signals
                        from ..prediction.engine import GeneratedSignal

                        signal_dicts = []
                        for signal in signals_to_save:
                            # Convert signal to dict (using engine's helper method)
                            signal_dict = {
                                "symbol": signal.symbol,
                                "signal_timestamp": signal.signal_timestamp,
                                "signal_type": signal.signal_type.value,
                                "entry_price": signal.entry_price,
                                "stop_loss": signal.stop_loss,
                                "target_price": signal.target_price,
                                "confidence": signal.confidence,
                                "signal_strength": signal.signal_strength,
                                "timeframe_alignment": signal.timeframe_alignment,
                                "risk_reward_ratio": signal.risk_reward_ratio,
                                "htf_trend": signal.htf_trend.value,
                                "trading_tf_state": signal.trading_tf_state,
                                "confluence_zones_count": signal.confluence_zones_count,
                                "pattern_context": signal.pattern_context,
                            }

                            # Merge notification metadata if available
                            if signal.symbol in notification_metadata:
                                signal_dict.update(notification_metadata[signal.symbol])
                            else:
                                # Default notification metadata (not sent)
                                signal_dict.update({
                                    "notification_sent": False,
                                    "notification_channels": None,
                                    "notification_timestamp": None,
                                })

                            signal_dicts.append(signal_dict)

                        # Save to database
                        self.persistence.save_generated_signals(run_id, signal_dicts)

                    # Update result with persisted run_id
                    result = replace(result, run_id=run_id)

                    # Track performance metrics (Week 5 addition)
                    if self.performance_tracker and run_id:
                        try:
                            from .monitoring import LatencyMetrics, ThroughputMetrics

                            latency = LatencyMetrics(
                                data_fetch_ms=result.data_fetch_ms,
                                indicator_calc_ms=result.indicator_calc_ms,
                                signal_generation_ms=result.signal_generation_ms,
                                notification_ms=notification_ms,
                                total_ms=result.execution_time_ms + notification_ms,
                            )

                            throughput = ThroughputMetrics.calculate(
                                symbols_processed=result.symbols_processed,
                                signals_generated=result.signals_generated,
                                execution_time_ms=result.execution_time_ms + notification_ms,
                            )

                            self.performance_tracker.track_cycle(
                                run_id=run_id,
                                latency=latency,
                                throughput=throughput,
                                errors=result.errors + notification_errors,
                            )

                        except Exception as e:
                            logger.error(f"Performance tracking failed: {e}", exc_info=True)

                except Exception as e:
                    logger.error(f"Persistence failed: {e}", exc_info=True)

            logger.info(
                f"Prediction cycle complete: {result.symbols_processed} symbols, "
                f"{result.signals_generated} signals, {result.execution_time_ms}ms"
            )

            return result

        except Exception as e:
            logger.error(f"Prediction cycle failed: {e}", exc_info=True)

            # Update scheduler state with error
            if self.config.persist_state:
                self.persistence.update_scheduler_state(
                    status="ERROR",
                    error_message=str(e),
                )

            raise

    def _run_catch_up(self) -> None:
        """
        Run catch-up for missed intervals on startup.

        If market data is missing for current day, or scheduler starts late,
        this ensures we have analysis for the full trading day.
        """
        logger.info("Running catch-up for missed intervals")

        # Get today's market open in UTC
        now_utc = datetime.now(timezone.utc)
        now_local = now_utc.astimezone(ZoneInfo(self.config.trading_session.timezone))
        today = now_local.date()

        # Check if today is a trading day
        if not self.market_hours.is_trading_day(now_utc):
            logger.info("Today is not a trading day, skipping catch-up")
            return

        # Get market open time for today
        try:
            hours = self.market_hours.calendar.get_trading_hours(
                self.config.exchange_code,
                today
            )
            if hours is None:
                logger.info("Market not open today, skipping catch-up")
                return

            market_open_time = hours[0]
        except Exception as e:
            logger.warning(f"Error getting trading hours: {e}")
            market_open_time = self.config.trading_session.market_open

        market_open_dt = datetime.combine(
            today,
            market_open_time,
            tzinfo=ZoneInfo(self.config.trading_session.timezone)
        ).astimezone(timezone.utc)

        # If we're before market open or market is closed, no catch-up needed
        if now_utc < market_open_dt or not self.market_hours.is_market_open(now_utc):
            logger.info("Market not yet open or already closed, skipping catch-up")
            return

        # Check last successful run from database
        try:
            state = self.persistence.get_scheduler_state()
            if state and state.get("last_run_timestamp"):
                last_run = state["last_run_timestamp"]
                if last_run >= market_open_dt:
                    logger.info(f"Already have analysis since market open ({last_run}), skipping catch-up")
                    return
        except Exception as e:
            logger.warning(f"Error checking last run: {e}")

        # Execute one comprehensive cycle covering market open to now
        logger.info(f"Running catch-up cycle from market open ({market_open_dt}) to now ({now_utc})")

        try:
            result = self._execute_cycle()
            logger.info(f"Catch-up complete: {result.signals_generated} signals generated")
        except Exception as e:
            logger.error(f"Catch-up failed: {e}", exc_info=True)

    def _parse_interval_minutes(self, interval: str) -> int:
        """Parse interval string to minutes."""
        interval = interval.lower().strip()

        if interval.endswith("min"):
            return int(interval[:-3])
        elif interval.endswith("h"):
            return int(interval[:-1]) * 60
        else:
            raise ValueError(f"Invalid interval format: {interval}")

    def _job_listener(self, event):
        """Listen to APScheduler job events."""
        if event.exception:
            logger.error(f"Scheduled job error: {event.exception}")
        else:
            logger.debug("Scheduled job completed successfully")

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        logger.info(f"Received signal {signum}, initiating graceful shutdown")
        self.stop(wait=True)
