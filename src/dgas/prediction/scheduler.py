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
        """Execute cycle only if market is open."""
        if self._shutdown_event.is_set():
            return

        if not self.market_hours.is_market_open():
            logger.debug("Market is closed, skipping prediction cycle")
            return

        # Acquire lock to prevent concurrent executions
        if not self._execution_lock.acquire(blocking=False):
            logger.warning("Prediction cycle already running, skipping this interval")
            return

        try:
            self._execute_cycle()
        except Exception as e:
            logger.error(f"Error executing prediction cycle: {e}", exc_info=True)
        finally:
            self._execution_lock.release()

    def _execute_cycle(self) -> PredictionRunResult:
        """Execute full prediction pipeline with notifications."""
        import time
        from .notifications import NotificationConfig, NotificationRouter
        from .notifications.adapters import DiscordAdapter, ConsoleAdapter

        logger.info("Executing prediction cycle")

        try:
            # Execute via engine
            result = self.engine.execute_prediction_cycle(
                symbols=self.config.symbols[:self.config.max_symbols_per_cycle],
                interval=self.config.interval,
                timeframes=self.config.enabled_timeframes,
                persist_results=False,  # We'll persist after adding notification metadata
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

                    # Initialize enabled adapters
                    adapters = {}

                    if "console" in notif_config.enabled_channels:
                        adapters["console"] = ConsoleAdapter(
                            max_signals=notif_config.console_max_signals,
                            output_format=notif_config.console_format,
                        )
                        logger.debug("Console adapter initialized")

                    if "discord" in notif_config.enabled_channels:
                        if notif_config.discord_bot_token and notif_config.discord_channel_id:
                            adapters["discord"] = DiscordAdapter(
                                bot_token=notif_config.discord_bot_token,
                                channel_id=notif_config.discord_channel_id,
                                # Note: min_confidence filtering is done by NotificationRouter
                            )
                            logger.debug("Discord adapter initialized")
                        else:
                            logger.warning("Discord enabled but token/channel ID missing")

                    # Send notifications if we have adapters and signals
                    if adapters and result.signals:
                        router = NotificationRouter(notif_config, adapters)

                        # Prepare run metadata
                        run_metadata = {
                            "run_id": result.run_id or 0,
                            "run_timestamp": result.timestamp.isoformat(),
                            "symbols_processed": result.symbols_processed,
                            "interval": self.config.interval,
                        }

                        # Send notifications
                        delivery_results = router.send_notifications(
                            signals=result.signals,
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

                        # Get notification metadata for signals
                        notification_metadata = router.get_notification_metadata(
                            signals=result.signals,
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
                        from ..prediction.engine import GeneratedSignal

                        signal_dicts = []
                        for signal in result.signals:
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
