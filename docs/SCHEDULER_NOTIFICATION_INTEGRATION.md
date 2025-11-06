# PredictionScheduler-Notification Integration

## Overview

This document describes the integration between the PredictionScheduler and the Notification System completed as part of Phase 4, Week 4 of the DrummondGeometry Alert System (DGAS).

**Integration Date**: November 6, 2025
**Status**: ✅ Complete
**Test Coverage**: 7/7 tests passing

## Architecture

### High-Level Flow

```
PredictionScheduler._execute_cycle()
  ↓
  1. Execute PredictionEngine.execute_prediction_cycle()
     → Returns PredictionRunResult with signals
  ↓
  2. Load NotificationConfig from environment
  ↓
  3. Initialize enabled adapters (Discord, Console)
  ↓
  4. Send notifications via NotificationRouter
     - Filters signals by channel-specific confidence thresholds
     - Sends to each enabled channel
     - Returns delivery results
  ↓
  5. Get notification metadata for each signal
     - Maps which channels each signal was sent to
     - Includes notification timestamp
  ↓
  6. Persist signals with notification metadata
     - Merges notification data into signal dictionaries
     - Saves to database via PredictionPersistence
  ↓
  7. Return PredictionRunResult with updated metrics
```

### Key Components

#### 1. **PredictionEngine Updates**

**File**: `src/dgas/prediction/engine.py`

**Changes**:
- Added `signals` field to `PredictionRunResult` dataclass
- Engine now returns actual `GeneratedSignal` objects instead of just metadata
- Enables scheduler to access signal objects for notification delivery

```python
@dataclass(frozen=True)
class PredictionRunResult:
    # ... existing fields ...
    signals: List[GeneratedSignal] = field(default_factory=list)
```

#### 2. **NotificationRouter Enhancement**

**File**: `src/dgas/prediction/notifications/router.py`

**Changes**:
- Added `get_notification_metadata()` method
- Returns dict mapping signal symbol to notification delivery details
- Used by scheduler to update signals before persistence

```python
def get_notification_metadata(
    self,
    signals: list[GeneratedSignal],
    delivery_results: dict[str, bool],
) -> dict[str, dict[str, Any]]:
    """Get notification metadata for each signal after delivery."""
    # Returns: {symbol: {notification_sent, notification_channels, notification_timestamp}}
```

#### 3. **PredictionScheduler Integration**

**File**: `src/dgas/prediction/scheduler.py`

**Changes**:
- Updated `_execute_cycle()` to send notifications after signal generation
- Loads `NotificationConfig` from environment variables
- Initializes enabled adapters (Discord, Console)
- Sends notifications via `NotificationRouter`
- Tracks notification timing separately in metrics
- Updates signals with notification metadata before persistence
- Gracefully handles notification failures (doesn't crash cycle)

**Key Code Section** (lines 489-642):
```python
def _execute_cycle(self) -> PredictionRunResult:
    """Execute full prediction pipeline with notifications."""
    # ... engine execution ...

    if result.signals_generated > 0:
        # Load notification config
        notif_config = NotificationConfig.from_env()

        # Initialize adapters
        adapters = {}
        if "console" in notif_config.enabled_channels:
            adapters["console"] = ConsoleAdapter(...)
        if "discord" in notif_config.enabled_channels:
            adapters["discord"] = DiscordAdapter(...)

        # Send notifications
        router = NotificationRouter(notif_config, adapters)
        delivery_results = router.send_notifications(signals, run_metadata)

        # Get metadata for persistence
        notification_metadata = router.get_notification_metadata(signals, delivery_results)

    # Persist with notification metadata
    if self.config.persist_state:
        # Convert signals to dicts with notification fields
        signal_dicts = [...]
        self.persistence.save_generated_signals(run_id, signal_dicts)
```

## Configuration

### Environment Variables

Notification system uses these environment variables (loaded via `NotificationConfig.from_env()`):

```bash
# Discord Configuration
DGAS_DISCORD_BOT_TOKEN="your_bot_token_here"
DGAS_DISCORD_CHANNEL_ID="your_channel_id_here"
```

### Notification Channels

**Enabled Channels** (default): `["console", "discord"]`

- **Console**: Always enabled, shows all signals (confidence ≥ 0.0)
- **Discord**: Enabled if bot token and channel ID are configured, filters signals by confidence (≥ 0.5 default)

### Filtering

Channel-specific confidence thresholds (configured in `NotificationConfig`):

- `discord_min_confidence`: 0.5 (configurable)
- Console: 0.0 (shows all signals)

Filtering is performed by `NotificationRouter._filter_signals_for_channel()`.

## Error Handling

The integration implements graceful degradation:

1. **Notification Failures Don't Crash Cycles**
   - If notification delivery fails, error is logged
   - Signals are still persisted to database
   - Cycle completes successfully

2. **Missing Configuration**
   - If Discord credentials missing → Warning logged, Discord skipped
   - If no adapters enabled → Notifications skipped entirely
   - Cycle continues normally

3. **Channel-Specific Failures**
   - Each channel's delivery is tracked separately
   - Failed channels don't affect successful ones
   - Metadata reflects actual delivery status

## Timing Metrics

Notification timing is tracked separately in performance metrics:

**Database Field**: `prediction_runs.notification_ms`

**Calculation**:
```python
notification_start = time.time()
# ... send notifications ...
notification_ms = int((time.time() - notification_start) * 1000)
```

**Total Execution Time** = data_fetch_ms + indicator_calc_ms + signal_generation_ms + **notification_ms**

## Database Schema

### Generated Signals Table

Notification metadata is persisted alongside signals:

```sql
CREATE TABLE generated_signals (
    -- ... existing fields ...
    notification_sent BOOLEAN DEFAULT FALSE,
    notification_channels TEXT[],  -- Array of channel names
    notification_timestamp TIMESTAMPTZ,
    -- ... other fields ...
);
```

### Prediction Runs Table

```sql
CREATE TABLE prediction_runs (
    -- ... existing fields ...
    notification_ms INTEGER,  -- Time spent sending notifications
    -- ... other fields ...
);
```

## Testing

### Test Suite

**File**: `tests/prediction/test_scheduler_notification_integration.py`

**Coverage**: 7 comprehensive integration tests

1. ✅ **test_execute_cycle_sends_notifications**
   - Verifies notifications are sent when signals generated
   - Checks signal metadata includes notification details

2. ✅ **test_execute_cycle_handles_notification_failure_gracefully**
   - Ensures notification failures don't crash scheduler
   - Signals still persisted with default metadata

3. ✅ **test_execute_cycle_skips_notifications_when_no_signals**
   - Verifies notification system not invoked when no signals

4. ✅ **test_execute_cycle_tracks_notification_timing**
   - Validates notification_ms tracked in metrics

5. ✅ **test_execute_cycle_filters_signals_by_confidence**
   - Confirms channel-specific confidence filtering works

6. ✅ **test_signal_dictionaries_include_notification_fields**
   - Validates all notification fields persisted correctly

7. ✅ **test_signals_without_notifications_have_default_metadata**
   - Ensures signals get default values when notifications disabled

### Test Execution

```bash
# Run integration tests
uv run pytest tests/prediction/test_scheduler_notification_integration.py -v

# Results: 7 passed in 0.84s
```

### Manual Testing

**Test Script**: `test_discord_bot.py`

Successfully tested with:
- 3 sample signals (AAPL LONG, MSFT SHORT, TSLA LONG)
- Console table display
- Discord embeds posted to real channel
- All notifications delivered successfully

## Implementation Summary

### Files Modified

1. **src/dgas/prediction/engine.py**
   - Added `signals` field to `PredictionRunResult`
   - Engine returns signal objects for notification

2. **src/dgas/prediction/scheduler.py**
   - Integrated notification system into `_execute_cycle()`
   - Added notification timing tracking
   - Implemented graceful error handling

3. **src/dgas/prediction/notifications/router.py**
   - Added `get_notification_metadata()` helper method
   - Returns notification delivery details for persistence

### Files Created

1. **tests/prediction/test_scheduler_notification_integration.py**
   - Comprehensive test suite (7 tests)
   - Covers all integration scenarios

2. **docs/SCHEDULER_NOTIFICATION_INTEGRATION.md** (this file)
   - Technical documentation
   - Architecture overview
   - Configuration guide

## Usage Examples

### Manual Prediction with Notifications

```python
from dgas.prediction.scheduler import PredictionScheduler, SchedulerConfig
from dgas.prediction.engine import PredictionEngine
from dgas.prediction.persistence import PredictionPersistence

# Configure scheduler
config = SchedulerConfig(
    interval="30min",
    symbols=["AAPL", "MSFT", "TSLA"],
    enabled_timeframes=["4h", "1h", "30min"],
    persist_state=True,
)

# Initialize components
engine = PredictionEngine()
persistence = PredictionPersistence()

# Create scheduler
scheduler = PredictionScheduler(
    config=config,
    engine=engine,
    persistence=persistence,
)

# Run single cycle (manual execution)
result = scheduler.run_once()

# Result includes:
# - Signals sent to console (always)
# - Signals sent to Discord (if configured)
# - Notification metadata persisted to database
```

### Accessing Notification Metadata

```python
# Query recent signals with notification status
signals = persistence.get_recent_signals(lookback_hours=24)

for signal in signals:
    print(f"Symbol: {signal['symbol']}")
    print(f"Notification Sent: {signal['notification_sent']}")
    print(f"Channels: {signal['notification_channels']}")
    print(f"Timestamp: {signal['notification_timestamp']}")
```

## Performance Considerations

### Notification Timing

Typical notification latency:
- **Console**: < 50ms (in-memory display)
- **Discord**: 200-500ms per signal (network + API)
- **Total**: Scales linearly with signal count

### Optimization Strategies

1. **Rate Limiting**: 1-second delay between Discord messages
2. **Batch Processing**: Console displays all signals in single table
3. **Async Potential**: Future enhancement could make Discord calls async

### Monitoring

Track notification performance via `prediction_runs.notification_ms`:

```sql
-- Average notification time per run
SELECT AVG(notification_ms) as avg_notification_ms
FROM prediction_runs
WHERE run_timestamp >= NOW() - INTERVAL '24 hours';

-- Identify slow notification runs
SELECT run_id, notification_ms, signals_generated
FROM prediction_runs
WHERE notification_ms > 1000  -- > 1 second
ORDER BY notification_ms DESC
LIMIT 10;
```

## Future Enhancements

### Potential Improvements

1. **Async Notifications**
   - Use asyncio for Discord API calls
   - Reduce total notification time

2. **Retry Logic**
   - Implement exponential backoff for transient failures
   - Queue failed notifications for retry

3. **Additional Channels**
   - Webhook support (already in architecture)
   - Desktop notifications
   - Email/SMS for high-priority signals

4. **Advanced Filtering**
   - Per-channel pattern filters
   - Symbol-specific routing
   - Time-based delivery rules

5. **Delivery Confirmation**
   - Track message IDs from Discord
   - Allow users to acknowledge/dismiss signals
   - Feedback loop for signal quality

## Troubleshooting

### Common Issues

#### 1. Discord Notifications Not Sending

**Symptoms**: Warning logged: "Discord enabled but token/channel ID missing"

**Solution**: Verify environment variables are set:
```bash
echo $DGAS_DISCORD_BOT_TOKEN
echo $DGAS_DISCORD_CHANNEL_ID
```

#### 2. Notification Timing Too High

**Symptoms**: `notification_ms` > 2000ms in prediction_runs

**Check**:
- Discord rate limiting (429 responses)
- Network latency to Discord API
- Number of signals being sent

**Solutions**:
- Reduce signal generation frequency
- Increase confidence thresholds
- Consider async notifications

#### 3. Signals Not Persisted with Notification Metadata

**Symptoms**: `notification_sent=FALSE` in database despite successful delivery

**Check**:
- Notification metadata returned by `get_notification_metadata()`
- Signal persistence code merging metadata correctly

**Debug**:
```python
# Add logging to scheduler
logger.debug(f"Notification metadata: {notification_metadata}")
logger.debug(f"Signal dicts before persist: {signal_dicts}")
```

## Conclusion

The PredictionScheduler-Notification integration provides a robust, extensible system for delivering trading signals through multiple channels with comprehensive error handling, performance tracking, and persistence.

**Key Benefits**:
- ✅ Automated signal delivery via scheduled predictions
- ✅ Multi-channel support (Console, Discord)
- ✅ Graceful degradation on failures
- ✅ Complete audit trail in database
- ✅ Configurable filtering per channel
- ✅ Comprehensive test coverage

**Status**: Production-ready, fully tested, documented.
