# Phase 4 - Week 3: Prediction Scheduler Implementation Plan

## Overview

Week 3 focuses on implementing the **Prediction Scheduler** - the component that orchestrates periodic execution of the prediction pipeline with market-hours awareness. This is the "brain" that automates signal generation during trading hours.

## Objectives

1. Implement market hours awareness (US trading sessions)
2. Create scheduler for interval-based prediction execution
3. Add graceful startup/shutdown with state persistence
4. Implement error handling and recovery mechanisms
5. Write comprehensive unit tests
6. Update documentation

## Components to Implement

### 1. Market Hours Manager (`prediction/scheduler.py`)

**Purpose:** Determine when the market is open and calculate next trading sessions.

**Classes:**

#### `TradingSession` (dataclass, frozen)
```python
@dataclass(frozen=True)
class TradingSession:
    """Trading session configuration."""
    market_open: time           # e.g., 09:30:00
    market_close: time          # e.g., 16:00:00
    timezone: str               # e.g., "America/New_York"
    trading_days: List[str]     # e.g., ["MON", "TUE", "WED", "THU", "FRI"]

    # US market holidays (simplified - use trading_calendars in production)
    market_holidays: List[date] = field(default_factory=list)
```

#### `MarketHoursManager`
```python
class MarketHoursManager:
    """Manage market hours and trading sessions."""

    def __init__(self, session: TradingSession):
        """Initialize with trading session config."""

    def is_market_open(self, dt: Optional[datetime] = None) -> bool:
        """
        Check if market is open at given time (or now).

        Returns True if:
        - Day is in trading_days (weekday check)
        - Time is between market_open and market_close
        - Date is not a market holiday
        """

    def next_market_open(self, from_dt: Optional[datetime] = None) -> datetime:
        """
        Calculate next market open time.

        If market is currently open, returns current session open.
        Otherwise, returns next session open (next trading day at market_open).
        """

    def next_market_close(self, from_dt: Optional[datetime] = None) -> datetime:
        """Calculate next market close time."""

    def is_trading_day(self, dt: datetime) -> bool:
        """Check if given date is a trading day (not weekend/holiday)."""

    def get_session_intervals(
        self,
        interval: str = "30min",
        session_date: Optional[date] = None,
    ) -> List[datetime]:
        """
        Generate list of interval timestamps for a trading session.

        Example for interval="30min":
        [09:30, 10:00, 10:30, 11:00, ..., 15:30, 16:00]
        """
```

**Key Implementation Details:**
- Use `zoneinfo` (Python 3.9+) for timezone handling
- Convert all times to UTC internally for consistency
- Handle edge cases: weekends, holidays, after-hours
- Validate session config (market_open < market_close)

---

### 2. Scheduler Configuration (`prediction/scheduler.py`)

#### `SchedulerConfig` (dataclass)
```python
@dataclass
class SchedulerConfig:
    """Configuration for prediction scheduler."""

    # Execution settings
    interval: str = "30min"                      # Update frequency
    symbols: List[str] = field(default_factory=list)  # Watchlist
    enabled_timeframes: List[str] = field(default_factory=lambda: ["4h", "1h", "30min"])

    # Signal filtering
    min_confidence: float = 0.6
    min_signal_strength: float = 0.5
    min_alignment: float = 0.6
    enabled_patterns: Optional[List[str]] = None  # None = all patterns

    # Performance settings
    max_symbols_per_cycle: int = 50              # Limit for performance
    timeout_seconds: int = 180                   # Max cycle duration

    # Market hours
    trading_session: TradingSession = field(
        default_factory=lambda: TradingSession(
            market_open=time(9, 30),
            market_close=time(16, 0),
            timezone="America/New_York",
            trading_days=["MON", "TUE", "WED", "THU", "FRI"],
        )
    )

    # Operational
    run_on_startup: bool = False                 # Execute immediately on start
    persist_state: bool = True                   # Save scheduler state to DB
```

---

### 3. Prediction Scheduler (`prediction/scheduler.py`)

#### `PredictionScheduler`
```python
class PredictionScheduler:
    """
    Orchestrate periodic prediction execution with market-hours awareness.

    Responsibilities:
    - Schedule prediction cycles at configured intervals
    - Only run during market hours
    - Graceful startup/shutdown
    - State persistence for recovery
    - Error handling without crashing
    """

    def __init__(
        self,
        config: SchedulerConfig,
        engine: PredictionEngine,
        persistence: PredictionPersistence,
        market_hours: Optional[MarketHoursManager] = None,
    ):
        """
        Initialize scheduler.

        Args:
            config: Scheduler configuration
            engine: Prediction engine for executing cycles
            persistence: Database persistence layer
            market_hours: Market hours manager (created from config if None)
        """

    def start(self, daemon: bool = False) -> None:
        """
        Start scheduler loop.

        Args:
            daemon: If True, run in background thread. If False, block in current thread.

        Behavior:
        - If daemon=True: Start thread and return immediately
        - If daemon=False: Block until stop() is called or SIGTERM/SIGINT
        - Run initial cycle if config.run_on_startup=True
        - Update scheduler_state table to RUNNING
        """

    def stop(self, wait: bool = True) -> None:
        """
        Graceful shutdown.

        Args:
            wait: If True, wait for current cycle to complete before stopping

        Behavior:
        - Set shutdown flag
        - Wait for in-flight cycle to complete (if wait=True)
        - Update scheduler_state to STOPPED
        - Close database connections
        """

    def run_once(self) -> PredictionRunResult:
        """
        Execute single prediction cycle (for testing/manual triggers).

        Does not check market hours or intervals.
        Useful for testing and manual execution.
        """

    def is_running(self) -> bool:
        """Check if scheduler is currently running."""

    def _run_loop(self) -> None:
        """
        Internal: Main scheduler loop.

        Logic:
        1. Calculate next run time based on interval and market hours
        2. Sleep until next run time
        3. Check if should run (market open, not already executing)
        4. Execute cycle via _execute_cycle()
        5. Handle errors gracefully
        6. Update state and metrics
        7. Repeat
        """

    def _execute_cycle(self) -> PredictionRunResult:
        """
        Internal: Execute full prediction pipeline.

        Steps:
        1. Update scheduler_state to RUNNING with current_run_id
        2. Call engine.execute_prediction_cycle()
        3. Handle errors and log
        4. Update scheduler_state based on result
        5. Return result
        """

    def _should_run(self) -> bool:
        """
        Check if conditions are met for running.

        Returns False if:
        - Market is closed
        - A cycle is already running
        - Scheduler is shutting down
        """

    def _calculate_next_run_time(self) -> datetime:
        """
        Calculate next execution time.

        Logic:
        - Align to interval boundaries (e.g., 09:30, 10:00, 10:30 for 30min)
        - Skip to next market open if currently after hours
        - Account for execution time (don't overlap cycles)
        """

    def _handle_cycle_error(self, error: Exception, context: dict) -> None:
        """
        Handle errors during cycle execution.

        Actions:
        - Log error with context
        - Update scheduler_state with error message
        - Optionally send alert notification
        - Don't crash scheduler
        """
```

**Key Implementation Details:**
- Use `threading.Thread` for daemon mode
- Use `threading.Event` for shutdown signaling
- Implement proper signal handling (SIGTERM, SIGINT) for clean shutdown
- Protect shared state with threading locks
- Calculate interval alignment (e.g., 30min intervals at :00 and :30)
- Prevent overlapping executions with a lock/flag
- Persist state to scheduler_state table for recovery

---

## Implementation Tasks

### Task 1: Implement TradingSession and MarketHoursManager
**Files:** `src/dgas/prediction/scheduler.py`

- [ ] Create `TradingSession` dataclass with validation
- [ ] Implement `MarketHoursManager.__init__`
- [ ] Implement `is_market_open()` with timezone handling
- [ ] Implement `next_market_open()` calculation
- [ ] Implement `next_market_close()` calculation
- [ ] Implement `is_trading_day()` (weekday + holiday check)
- [ ] Implement `get_session_intervals()` for interval generation
- [ ] Add docstrings and type hints

**Validation:**
- Market open/close times are correctly localized to timezone
- Weekends are correctly identified as non-trading days
- Holidays are correctly excluded (if configured)
- Interval generation produces correct timestamps

---

### Task 2: Implement SchedulerConfig
**Files:** `src/dgas/prediction/scheduler.py`

- [ ] Create `SchedulerConfig` dataclass with defaults
- [ ] Add validation (interval format, positive numbers, etc.)
- [ ] Include default TradingSession for US markets
- [ ] Add factory methods if needed (e.g., `from_dict()`)

---

### Task 3: Implement PredictionScheduler Core
**Files:** `src/dgas/prediction/scheduler.py`

- [ ] Implement `__init__` with dependency injection
- [ ] Implement `start()` with daemon/blocking modes
- [ ] Implement `stop()` with graceful shutdown
- [ ] Implement `run_once()` for manual execution
- [ ] Implement `is_running()` state check
- [ ] Add signal handlers for SIGTERM/SIGINT

**Threading Considerations:**
- Use `threading.Event` for shutdown signaling
- Use `threading.Lock` for protecting execution state
- Ensure thread safety for all shared state

---

### Task 4: Implement Scheduler Loop Logic
**Files:** `src/dgas/prediction/scheduler.py`

- [ ] Implement `_run_loop()` main scheduler loop
- [ ] Implement `_execute_cycle()` pipeline orchestration
- [ ] Implement `_should_run()` conditions check
- [ ] Implement `_calculate_next_run_time()` interval alignment
- [ ] Implement `_handle_cycle_error()` error recovery
- [ ] Add state persistence (scheduler_state table updates)

**Key Logic:**
- Calculate sleep duration until next interval
- Check market hours before each execution
- Handle execution timeout (optional)
- Log all state transitions

---

### Task 5: Update Module Exports
**Files:** `src/dgas/prediction/__init__.py`

- [ ] Export `TradingSession`
- [ ] Export `MarketHoursManager`
- [ ] Export `SchedulerConfig`
- [ ] Export `PredictionScheduler`
- [ ] Update `__all__` list

---

### Task 6: Write Unit Tests
**Files:** `tests/prediction/test_scheduler.py`

**Test Classes:**

#### `TestTradingSession`
- [ ] Test creation with valid parameters
- [ ] Test validation (market_open < market_close)
- [ ] Test immutability (frozen=True)

#### `TestMarketHoursManager`
- [ ] Test `is_market_open()` during trading hours
- [ ] Test `is_market_open()` outside trading hours
- [ ] Test `is_market_open()` on weekends
- [ ] Test `is_market_open()` on holidays
- [ ] Test `next_market_open()` during session
- [ ] Test `next_market_open()` after hours
- [ ] Test `next_market_open()` on weekends
- [ ] Test `next_market_close()` calculation
- [ ] Test `is_trading_day()` for various dates
- [ ] Test `get_session_intervals()` for 30min
- [ ] Test `get_session_intervals()` for 1h
- [ ] Test timezone conversion (UTC ↔ ET)

#### `TestSchedulerConfig`
- [ ] Test creation with defaults
- [ ] Test creation with custom values
- [ ] Test validation of interval format
- [ ] Test validation of numeric constraints

#### `TestPredictionScheduler`
- [ ] Test initialization with dependencies
- [ ] Test `run_once()` executes cycle
- [ ] Test `start()` begins scheduler loop (mock)
- [ ] Test `stop()` graceful shutdown
- [ ] Test `is_running()` state tracking
- [ ] Test market hours check (skip when closed)
- [ ] Test interval alignment calculation
- [ ] Test error handling (cycle failures)
- [ ] Test state persistence to DB
- [ ] Test concurrent execution prevention
- [ ] Test shutdown signal handling (SIGTERM)

**Test Strategy:**
- Mock `PredictionEngine` to avoid actual data fetching
- Mock `PredictionPersistence` for database operations
- Use fixed datetimes for deterministic tests
- Test both daemon and blocking modes
- Test edge cases (midnight rollover, DST changes)

---

### Task 7: Update Documentation
**Files:** `src/llms.txt`, `docs/PHASE4_WEEK3_SUMMARY.md`

- [ ] Update llms.txt with scheduler architecture
- [ ] Mark Week 3 as COMPLETED in progress section
- [ ] Create Week 3 completion summary document
- [ ] Document configuration options
- [ ] Add usage examples

---

## Success Criteria

**Functional Requirements:**
- ✓ Scheduler correctly identifies market hours
- ✓ Cycles execute at configured intervals during trading hours
- ✓ Graceful startup and shutdown work correctly
- ✓ State persists to scheduler_state table
- ✓ Errors don't crash the scheduler
- ✓ run_once() works for manual execution

**Code Quality:**
- ✓ All type hints present
- ✓ Comprehensive docstrings
- ✓ Follows existing code patterns
- ✓ No breaking changes to existing code

**Testing:**
- ✓ At least 20 unit tests
- ✓ All tests passing
- ✓ Edge cases covered (weekends, holidays, DST)
- ✓ Threading safety validated

**Documentation:**
- ✓ llms.txt updated
- ✓ Week 3 summary created
- ✓ Configuration examples provided

---

## Implementation Order

1. **Start with data structures** (TradingSession, SchedulerConfig)
2. **Implement MarketHoursManager** (market awareness logic)
3. **Implement PredictionScheduler core** (initialization, state)
4. **Implement scheduler loop** (main execution logic)
5. **Add threading support** (daemon mode, shutdown)
6. **Write unit tests** (validate all components)
7. **Update documentation** (llms.txt, summary)

---

## Risks & Mitigations

**Risk 1: Timezone handling complexity**
- Mitigation: Use `zoneinfo` (standard library), test with fixed datetimes

**Risk 2: Threading bugs (race conditions, deadlocks)**
- Mitigation: Minimal shared state, use Event/Lock primitives, thorough testing

**Risk 3: Interval alignment edge cases**
- Mitigation: Comprehensive test cases for midnight rollover, DST changes

**Risk 4: Database connection pooling in threaded context**
- Mitigation: Follow existing patterns from DrummondPersistence, close connections properly

---

## Files to Create/Modify

**New Files:**
- `src/dgas/prediction/scheduler.py` (~500-600 lines)
- `tests/prediction/test_scheduler.py` (~600-800 lines)
- `docs/PHASE4_WEEK3_SUMMARY.md`

**Modified Files:**
- `src/dgas/prediction/__init__.py` (add exports)
- `src/llms.txt` (update Week 3 status)

**Total Estimated Lines:** ~1,500-1,800 lines

---

## Testing Strategy

### Unit Tests (test_scheduler.py)
- Test each class in isolation with mocked dependencies
- Use `freezegun` or manual datetime mocking for deterministic tests
- Test threading behavior with controlled scenarios

### Integration Tests (optional for Week 3)
- End-to-end test with real database (Week 4+)
- Test with actual PredictionEngine (Week 4+)

### Edge Cases to Test
- Market open/close boundary conditions
- Weekends and holidays
- Daylight Saving Time transitions
- Midnight rollover (23:59 → 00:00)
- Long-running cycles that exceed interval
- Concurrent start() calls
- Stop during active cycle
- Database connection failures
- Signal interruption (SIGTERM/SIGINT)

---

## Post-Week 3 Integration

After Week 3 completion, the scheduler will be ready for:
- **Week 4:** Integration with notification system
- **Week 5:** Integration with monitoring/calibration
- **Week 6:** CLI command for starting scheduler
- **Week 7:** End-to-end integration testing

---

**Plan Status:** READY FOR APPROVAL
**Estimated Completion Time:** Week 3 (5-7 days)
**Dependencies:** Week 1 (persistence) ✓, Week 2 (engine) ✓

---

**Next Step:** Wait for approval, then begin implementation with Task 1 (TradingSession and MarketHoursManager).
