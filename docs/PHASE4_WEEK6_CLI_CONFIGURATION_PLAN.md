# Phase 4 Week 6: CLI & Configuration - Implementation Plan

**Status:** Planning
**Created:** 2025-11-06
**Dependencies:** Week 1-5 ✅

---

## Executive Summary

Week 6 delivers the command-line interface and configuration system that makes the prediction system accessible to end users. This includes three main CLI commands (`predict`, `scheduler`, `monitor`) and a flexible YAML/JSON configuration system for scheduler settings.

The CLI will follow the existing patterns established in `dgas analyze` and `dgas backtest`, using Rich for formatted output and providing both interactive and scriptable modes.

---

## Context & Current State

### Completed Foundation (Weeks 1-5)
- ✅ **Database Schema** - All tables exist and ready
- ✅ **Persistence Layer** - `PredictionPersistence` with all methods
- ✅ **Prediction Engine** - `PredictionEngine` generates signals
- ✅ **Scheduler** - `PredictionScheduler` with market hours awareness
- ✅ **Notifications** - Discord and Console adapters working
- ✅ **Monitoring** - `PerformanceTracker` and `CalibrationEngine` operational

### Existing CLI Infrastructure
- ✅ `dgas/__main__.py` - Main entry point with subparser pattern
- ✅ `dgas analyze` - Multi-timeframe analysis command
- ✅ `dgas backtest` - Backtesting command
- ✅ `dgas data-report` - Data ingestion report
- ✅ Rich library integration for formatted output
- ✅ Argparse-based CLI architecture

### Week 6 Goals
1. **Predict Command** - Manual signal generation for watchlists
2. **Scheduler Command** - Daemon control (start/stop/status)
3. **Monitor Command** - View performance metrics and calibration
4. **Configuration System** - YAML/JSON config files for scheduler

---

## Day 1-2: Predict Command

### Objective
Implement `dgas predict` command for manual, on-demand signal generation.

### Use Cases

**UC1: Quick Analysis**
```bash
# Generate signals for a few symbols
$ dgas predict AAPL MSFT GOOGL --interval 30min

# Example output:
Fetching data for 3 symbols (30min interval)...
Analyzing AAPL... 2 signals generated
Analyzing MSFT... 1 signal generated
Analyzing GOOGL... 0 signals generated

╔══════════════════════════════════════════════════════════╗
║           AAPL - LONG Signal (Confidence: 75%)          ║
╠══════════════════════════════════════════════════════════╣
║  Entry: $150.25    Stop: $145.50    Target: $157.00    ║
║  R:R: 2.8          Strength: 0.68    Alignment: 0.72   ║
║  HTF Trend: UP → Drummond Buy Zone                      ║
╚══════════════════════════════════════════════════════════╝

Total: 3 signals across 3 symbols
Execution time: 12.3s
```

**UC2: Watchlist from File**
```bash
# Load symbols from file
$ dgas predict --watchlist my_watchlist.txt --interval 1h
```

**UC3: Save to Database**
```bash
# Generate and persist signals
$ dgas predict AAPL MSFT --save --interval 30min

Signals saved to database (run_id: 456)
View with: dgas monitor signals --run 456
```

**UC4: JSON Output for Automation**
```bash
# Machine-readable output
$ dgas predict AAPL --format json --interval 30min

{
  "run_id": null,
  "timestamp": "2025-11-06T14:30:00Z",
  "interval": "30min",
  "symbols_processed": 1,
  "signals_generated": 2,
  "execution_time_ms": 12345,
  "signals": [
    {
      "symbol": "AAPL",
      "signal_type": "LONG",
      "entry_price": 150.25,
      "stop_loss": 145.50,
      "target_price": 157.00,
      "confidence": 0.75,
      "signal_strength": 0.68,
      ...
    }
  ]
}
```

### Implementation Specification

#### File: `src/dgas/cli/predict.py`

```python
"""CLI command for manual signal generation."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ..prediction import PredictionEngine, PredictionPersistence
from ..prediction.engine import GeneratedSignal
from ..settings import get_settings

console = Console()


def run_predict_command(
    *,
    symbols: Sequence[str],
    watchlist_file: Path | None,
    interval: str,
    timeframes: Sequence[str] | None,
    min_confidence: float,
    save_to_db: bool,
    send_notifications: bool,
    output_format: str,
) -> int:
    """
    Execute prediction cycle for specified symbols.

    Args:
        symbols: List of ticker symbols (or empty if using watchlist)
        watchlist_file: Optional file with one symbol per line
        interval: Interval for signal generation (e.g., "30min")
        timeframes: Timeframes for analysis (defaults to ["4h", "1h", "30min"])
        min_confidence: Minimum confidence filter (0.0-1.0)
        save_to_db: Whether to persist results
        send_notifications: Whether to send via notification channels
        output_format: Output format (summary, detailed, json)

    Returns:
        Exit code (0 for success)
    """
    # Load symbols
    all_symbols = _load_symbols(symbols, watchlist_file)
    if not all_symbols:
        console.print("[red]Error: No symbols provided[/red]")
        return 1

    # Use default timeframes if not specified
    if timeframes is None:
        timeframes = ["4h", "1h", interval]

    # Initialize engine
    settings = get_settings()
    persistence = PredictionPersistence(settings)
    engine = PredictionEngine(persistence=persistence, settings=settings)

    # Execute prediction
    console.print(
        f"[cyan]Analyzing {len(all_symbols)} symbols ({interval} interval)...[/cyan]"
    )

    with console.status("[bold green]Generating signals..."):
        result = engine.execute_prediction_cycle(
            symbols=all_symbols,
            interval=interval,
            timeframes=timeframes,
            persist_results=save_to_db,
        )

    # Filter by confidence
    filtered_signals = [
        s for s in result.signals if s.confidence >= min_confidence
    ]

    # Send notifications if requested
    if send_notifications and filtered_signals:
        _send_notifications(filtered_signals, result)

    # Display results
    if output_format == "summary":
        _display_summary(result, filtered_signals)
    elif output_format == "detailed":
        _display_detailed(result, filtered_signals)
    elif output_format == "json":
        _display_json(result, filtered_signals)

    return 0


def _load_symbols(
    symbols: Sequence[str], watchlist_file: Path | None
) -> list[str]:
    """Load symbols from CLI args or watchlist file."""
    all_symbols = list(symbols)

    if watchlist_file:
        if not watchlist_file.exists():
            console.print(f"[red]Error: Watchlist file not found: {watchlist_file}[/red]")
            return []

        with watchlist_file.open() as f:
            file_symbols = [
                line.strip() for line in f if line.strip() and not line.startswith("#")
            ]
        all_symbols.extend(file_symbols)
        console.print(f"[cyan]Loaded {len(file_symbols)} symbols from {watchlist_file}[/cyan]")

    return all_symbols


def _display_summary(result, signals):
    """Display summary output."""
    console.print(f"\n[green]✓[/green] Processed {result.symbols_processed} symbols")
    console.print(f"[green]✓[/green] Generated {len(signals)} signals")
    console.print(f"[cyan]Execution time: {result.execution_time_ms / 1000:.1f}s[/cyan]\n")

    if not signals:
        console.print("[yellow]No signals met confidence threshold[/yellow]")
        return

    for signal in signals:
        panel = _create_signal_panel(signal)
        console.print(panel)


def _display_detailed(result, signals):
    """Display detailed output with all signal metadata."""
    _display_summary(result, signals)

    # Additional performance details
    console.print("\n[bold]Performance Breakdown:[/bold]")
    table = Table()
    table.add_column("Stage", style="cyan")
    table.add_column("Time (ms)", justify="right")

    table.add_row("Data Fetch", str(result.data_fetch_ms))
    table.add_row("Indicator Calc", str(result.indicator_calc_ms))
    table.add_row("Signal Generation", str(result.signal_generation_ms))
    table.add_row("Total", str(result.execution_time_ms))

    console.print(table)


def _display_json(result, signals):
    """Display JSON output for scripting."""
    output = {
        "run_id": result.run_id,
        "timestamp": result.timestamp.isoformat(),
        "interval": result.interval if hasattr(result, 'interval') else None,
        "symbols_processed": result.symbols_processed,
        "signals_generated": len(signals),
        "execution_time_ms": result.execution_time_ms,
        "signals": [_signal_to_dict(s) for s in signals],
    }
    console.print(json.dumps(output, indent=2))


def _create_signal_panel(signal: GeneratedSignal) -> Panel:
    """Create a rich panel for a signal."""
    signal_type = signal.signal_type.value
    color = "green" if signal_type == "LONG" else "red"

    content = f"""
[{color}]{signal.symbol} - {signal_type}[/{color}] (Confidence: {signal.confidence:.0%})

Entry: ${signal.entry_price}    Stop: ${signal.stop_loss}    Target: ${signal.target_price}
R:R: {signal.risk_reward_ratio:.1f}    Strength: {signal.signal_strength:.2f}    Alignment: {signal.timeframe_alignment:.2f}
HTF Trend: {signal.htf_trend.value} → {signal.trading_tf_state}
    """.strip()

    return Panel(content, border_style=color)


def _signal_to_dict(signal: GeneratedSignal) -> dict:
    """Convert signal to dictionary."""
    return {
        "symbol": signal.symbol,
        "signal_type": signal.signal_type.value,
        "signal_timestamp": signal.signal_timestamp.isoformat(),
        "entry_price": float(signal.entry_price),
        "stop_loss": float(signal.stop_loss),
        "target_price": float(signal.target_price),
        "confidence": signal.confidence,
        "signal_strength": signal.signal_strength,
        "timeframe_alignment": signal.timeframe_alignment,
        "risk_reward_ratio": signal.risk_reward_ratio,
        "htf_trend": signal.htf_trend.value,
        "trading_tf_state": signal.trading_tf_state,
        "pattern_context": signal.pattern_context,
    }


def _send_notifications(signals, result):
    """Send signals via configured notification channels."""
    from ..prediction.notifications import NotificationConfig, NotificationRouter
    from ..prediction.notifications.adapters import DiscordAdapter, ConsoleAdapter

    try:
        config = NotificationConfig.from_env()
        adapters = {}

        if "discord" in config.enabled_channels:
            if config.discord_bot_token and config.discord_channel_id:
                adapters["discord"] = DiscordAdapter(
                    bot_token=config.discord_bot_token,
                    channel_id=config.discord_channel_id,
                )

        if adapters:
            router = NotificationRouter(config, adapters)
            run_metadata = {
                "run_id": result.run_id or 0,
                "run_timestamp": result.timestamp.isoformat(),
                "symbols_processed": result.symbols_processed,
                "interval": result.interval if hasattr(result, 'interval') else "manual",
            }
            delivery_results = router.send_notifications(signals, run_metadata)

            for channel, success in delivery_results.items():
                if success:
                    console.print(f"[green]✓[/green] Notifications sent to {channel}")
                else:
                    console.print(f"[red]✗[/red] Failed to send to {channel}")
    except Exception as e:
        console.print(f"[yellow]Warning: Notification delivery failed: {e}[/yellow]")
```

#### CLI Integration (`dgas/__main__.py`)

```python
# Add to build_parser():
predict_parser = subparsers.add_parser(
    "predict",
    help="Generate trading signals for specified symbols",
)
predict_parser.add_argument(
    "symbols",
    nargs="*",
    help="Symbols to analyze (e.g., AAPL MSFT)",
)
predict_parser.add_argument(
    "--watchlist",
    type=Path,
    help="Load symbols from file (one per line)",
)
predict_parser.add_argument(
    "--interval",
    default="30min",
    help="Interval for signal generation (default: 30min)",
)
predict_parser.add_argument(
    "--timeframes",
    nargs="+",
    help="Timeframes for analysis (default: 4h 1h 30min)",
)
predict_parser.add_argument(
    "--min-confidence",
    type=float,
    default=0.6,
    help="Minimum confidence filter (default: 0.6)",
)
predict_parser.add_argument(
    "--save",
    action="store_true",
    help="Save signals to database",
)
predict_parser.add_argument(
    "--notify",
    action="store_true",
    help="Send signals via notification channels",
)
predict_parser.add_argument(
    "--format",
    choices=["summary", "detailed", "json"],
    default="summary",
    help="Output format (default: summary)",
)

# Add to main():
if args.command == "predict":
    from .cli.predict import run_predict_command
    return run_predict_command(
        symbols=args.symbols,
        watchlist_file=args.watchlist,
        interval=args.interval,
        timeframes=args.timeframes,
        min_confidence=args.min_confidence,
        save_to_db=args.save,
        send_notifications=args.notify,
        output_format=args.format,
    )
```

### Testing Strategy (Days 1-2)

#### Unit Tests (`tests/cli/test_predict_cli.py`)

1. **Symbol Loading Tests**
   - Test loading from CLI args
   - Test loading from watchlist file
   - Test combining both sources
   - Test invalid watchlist file

2. **Output Format Tests**
   - Test summary output formatting
   - Test detailed output with performance breakdown
   - Test JSON output structure
   - Test signal panel creation

3. **Integration Tests**
   - Mock PredictionEngine
   - Test full command execution
   - Test error handling
   - Test notification integration

---

## Day 3-4: Scheduler Command

### Objective
Implement `dgas scheduler` command for daemon lifecycle management.

### Use Cases

**UC1: Start Scheduler**
```bash
# Start with default configuration
$ dgas scheduler start

Starting prediction scheduler...
Loaded configuration from dgas.yaml
Watchlist: 25 symbols
Schedule: Every 30 minutes during market hours (9:30-16:00 ET)
Notifications: Discord enabled

Scheduler started (PID: 12345)
Logs: ~/.dgas/logs/scheduler.log
Stop with: dgas scheduler stop
```

**UC2: Stop Scheduler**
```bash
$ dgas scheduler stop

Stopping scheduler (PID: 12345)...
Waiting for current cycle to complete...
Scheduler stopped successfully
```

**UC3: Check Status**
```bash
$ dgas scheduler status

╔═══════════════════════════════════════════════════════╗
║              Scheduler Status: RUNNING               ║
╠═══════════════════════════════════════════════════════╣
║  PID: 12345                                          ║
║  Uptime: 2h 35m                                      ║
║  Last run: 2025-11-06 14:30:00 UTC (5 minutes ago)  ║
║  Next run: 2025-11-06 15:00:00 UTC (in 25 minutes)  ║
║  Total cycles: 48                                    ║
║  Signals generated: 156                              ║
║  Success rate: 98.5%                                 ║
╚═══════════════════════════════════════════════════════╝
```

**UC4: Configuration File**
```bash
# Start with specific config file
$ dgas scheduler start --config my_config.yaml

# Example config file (my_config.yaml):
scheduler:
  interval: "30min"
  watchlist:
    - AAPL
    - MSFT
    - GOOGL
  timeframes:
    - "4h"
    - "1h"
    - "30min"

  filters:
    min_confidence: 0.65
    min_signal_strength: 0.5
    min_alignment: 0.6

  exchange: "US"
  market_hours:
    open: "09:30"
    close: "16:00"
    timezone: "America/New_York"

notifications:
  enabled_channels:
    - discord
    - console
  min_confidence: 0.7
  discord:
    bot_token: "${DISCORD_BOT_TOKEN}"
    channel_id: "${DISCORD_CHANNEL_ID}"
```

### Implementation Specification

#### File: `src/dgas/cli/scheduler.py`

```python
"""CLI command for scheduler daemon management."""

from __future__ import annotations

import os
import signal
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ..prediction import PredictionPersistence, PredictionScheduler, SchedulerConfig
from ..settings import get_settings

console = Console()

# PID file location
PID_FILE = Path.home() / ".dgas" / "scheduler.pid"
LOG_DIR = Path.home() / ".dgas" / "logs"


def run_scheduler_command(
    *,
    action: str,
    config_file: Path | None,
    daemon: bool,
    force: bool,
) -> int:
    """
    Manage prediction scheduler lifecycle.

    Args:
        action: Command action (start, stop, status, restart)
        config_file: Optional configuration file
        daemon: Run in background (daemon mode)
        force: Force stop even if scheduler is running

    Returns:
        Exit code
    """
    if action == "start":
        return _start_scheduler(config_file, daemon)
    elif action == "stop":
        return _stop_scheduler(force)
    elif action == "status":
        return _show_status()
    elif action == "restart":
        _stop_scheduler(force)
        time.sleep(2)
        return _start_scheduler(config_file, daemon)
    else:
        console.print(f"[red]Unknown action: {action}[/red]")
        return 1


def _start_scheduler(config_file: Path | None, daemon: bool) -> int:
    """Start the scheduler."""
    # Check if already running
    if PID_FILE.exists():
        with open(PID_FILE) as f:
            pid = int(f.read().strip())

        if _is_process_running(pid):
            console.print(f"[yellow]Scheduler already running (PID: {pid})[/yellow]")
            console.print("Stop it first with: dgas scheduler stop")
            return 1
        else:
            # Stale PID file
            console.print("[yellow]Removing stale PID file[/yellow]")
            PID_FILE.unlink()

    # Load configuration
    config = _load_scheduler_config(config_file)

    # Create log directory
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOG_DIR / "scheduler.log"

    console.print("[cyan]Starting prediction scheduler...[/cyan]")
    console.print(f"Configuration: {config_file or 'default'}")
    console.print(f"Watchlist: {len(config.symbols)} symbols")
    console.print(f"Schedule: Every {config.interval} during market hours")

    if daemon:
        # Fork to background
        pid = os.fork()
        if pid > 0:
            # Parent process
            PID_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(PID_FILE, "w") as f:
                f.write(str(pid))

            console.print(f"\n[green]✓[/green] Scheduler started (PID: {pid})")
            console.print(f"Logs: {log_file}")
            console.print(f"Stop with: dgas scheduler stop")
            return 0
        else:
            # Child process - run scheduler
            _run_scheduler_loop(config, log_file)
            return 0
    else:
        # Run in foreground
        console.print("\n[cyan]Running in foreground (Ctrl+C to stop)...[/cyan]\n")

        # Save PID for status command
        PID_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(PID_FILE, "w") as f:
            f.write(str(os.getpid()))

        try:
            _run_scheduler_loop(config, log_file)
        except KeyboardInterrupt:
            console.print("\n[yellow]Scheduler stopped by user[/yellow]")
            PID_FILE.unlink(missing_ok=True)
            return 0


def _stop_scheduler(force: bool) -> int:
    """Stop the scheduler."""
    if not PID_FILE.exists():
        console.print("[yellow]Scheduler is not running[/yellow]")
        return 0

    with open(PID_FILE) as f:
        pid = int(f.read().strip())

    if not _is_process_running(pid):
        console.print("[yellow]Scheduler process not found (removing stale PID file)[/yellow]")
        PID_FILE.unlink()
        return 0

    console.print(f"Stopping scheduler (PID: {pid})...")

    # Send SIGTERM for graceful shutdown
    try:
        os.kill(pid, signal.SIGTERM)

        if not force:
            console.print("Waiting for current cycle to complete...")
            # Wait up to 60 seconds for graceful shutdown
            for _ in range(60):
                time.sleep(1)
                if not _is_process_running(pid):
                    break
            else:
                console.print("[yellow]Timeout waiting for scheduler, force stopping...[/yellow]")
                os.kill(pid, signal.SIGKILL)

        console.print("[green]✓[/green] Scheduler stopped")
        PID_FILE.unlink(missing_ok=True)
        return 0

    except ProcessLookupError:
        console.print("[yellow]Process already stopped[/yellow]")
        PID_FILE.unlink(missing_ok=True)
        return 0
    except Exception as e:
        console.print(f"[red]Error stopping scheduler: {e}[/red]")
        return 1


def _show_status() -> int:
    """Show scheduler status."""
    if not PID_FILE.exists():
        console.print("[yellow]Scheduler is not running[/yellow]")
        console.print("\nStart with: dgas scheduler start")
        return 0

    with open(PID_FILE) as f:
        pid = int(f.read().strip())

    if not _is_process_running(pid):
        console.print("[red]Scheduler process not found (PID file is stale)[/red]")
        console.print("\nRemove stale file with: dgas scheduler stop")
        return 1

    # Get scheduler state from database
    settings = get_settings()
    persistence = PredictionPersistence(settings)

    try:
        state = persistence.get_scheduler_state()
        recent_runs = persistence.get_recent_runs(limit=10, status=None)

        # Calculate uptime
        if recent_runs:
            first_run = recent_runs[-1]["run_timestamp"]
            uptime = datetime.now(timezone.utc) - first_run
        else:
            uptime = timedelta(0)

        # Create status panel
        panel_content = f"""
[bold green]Status: {state['status']}[/bold green]
PID: {pid}
Uptime: {_format_timedelta(uptime)}

Last run: {_format_datetime(state['last_run_timestamp'])}
Next run: {_format_datetime(state['next_scheduled_run'])}

Total cycles: {len(recent_runs)}
Success rate: {_calculate_success_rate(recent_runs):.1f}%
        """.strip()

        console.print(Panel(panel_content, title="Scheduler Status", border_style="green"))

        # Show recent runs
        if recent_runs:
            console.print("\n[bold]Recent Runs:[/bold]")
            table = Table()
            table.add_column("Time", style="cyan")
            table.add_column("Status")
            table.add_column("Symbols", justify="right")
            table.add_column("Signals", justify="right")
            table.add_column("Duration", justify="right")

            for run in recent_runs[:5]:
                status_style = "green" if run["status"] == "SUCCESS" else "red"
                table.add_row(
                    _format_datetime(run["run_timestamp"], short=True),
                    f"[{status_style}]{run['status']}[/{status_style}]",
                    str(run["symbols_processed"]),
                    str(run["signals_generated"]),
                    f"{run['execution_time_ms'] / 1000:.1f}s",
                )

            console.print(table)

        return 0

    except Exception as e:
        console.print(f"[red]Error retrieving status: {e}[/red]")
        return 1


def _run_scheduler_loop(config: SchedulerConfig, log_file: Path):
    """Main scheduler loop."""
    # Setup logging to file
    import logging
    logging.basicConfig(
        filename=log_file,
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Initialize scheduler
    settings = get_settings()
    persistence = PredictionPersistence(settings)

    from ..prediction import PredictionEngine, MarketHoursManager

    engine = PredictionEngine(persistence=persistence, settings=settings)
    market_hours = MarketHoursManager(config.exchange_code, config.trading_session)

    scheduler = PredictionScheduler(
        config=config,
        engine=engine,
        persistence=persistence,
        market_hours=market_hours,
        settings=settings,
    )

    # Start scheduler
    scheduler.start()

    # Keep running until signal
    try:
        while True:
            time.sleep(60)
    except (KeyboardInterrupt, SystemExit):
        scheduler.stop()


def _load_scheduler_config(config_file: Path | None) -> SchedulerConfig:
    """Load scheduler configuration from file or defaults."""
    if config_file is None:
        # Check for default config file
        default_config = Path("dgas.yaml")
        if default_config.exists():
            config_file = default_config

    if config_file and config_file.exists():
        # Load from YAML (Day 7 implementation)
        # For now, return defaults
        console.print(f"[yellow]Config file support coming in Day 7, using defaults[/yellow]")

    # Return default configuration
    return SchedulerConfig(
        symbols=["AAPL", "MSFT", "GOOGL"],  # Default watchlist
        interval="30min",
    )


def _is_process_running(pid: int) -> bool:
    """Check if process is running."""
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _format_timedelta(td: timedelta) -> str:
    """Format timedelta as human-readable string."""
    hours, remainder = divmod(int(td.total_seconds()), 3600)
    minutes, seconds = divmod(remainder, 60)

    if hours > 0:
        return f"{hours}h {minutes}m"
    elif minutes > 0:
        return f"{minutes}m {seconds}s"
    else:
        return f"{seconds}s"


def _format_datetime(dt: datetime | None, short: bool = False) -> str:
    """Format datetime for display."""
    if dt is None:
        return "Never"

    now = datetime.now(timezone.utc)
    diff = now - dt

    if short:
        return dt.strftime("%H:%M")

    if diff.total_seconds() < 3600:
        mins = int(diff.total_seconds() / 60)
        return f"{mins} minutes ago"
    elif diff.total_seconds() < 86400:
        hours = int(diff.total_seconds() / 3600)
        return f"{hours} hours ago"
    else:
        return dt.strftime("%Y-%m-%d %H:%M UTC")


def _calculate_success_rate(runs: list) -> float:
    """Calculate success rate from runs."""
    if not runs:
        return 0.0

    successful = len([r for r in runs if r["status"] == "SUCCESS"])
    return (successful / len(runs)) * 100
```

#### CLI Integration

```python
# Add to build_parser():
scheduler_parser = subparsers.add_parser(
    "scheduler",
    help="Manage prediction scheduler daemon",
)
scheduler_parser.add_argument(
    "action",
    choices=["start", "stop", "status", "restart"],
    help="Scheduler action",
)
scheduler_parser.add_argument(
    "--config",
    type=Path,
    help="Configuration file (YAML or JSON)",
)
scheduler_parser.add_argument(
    "--daemon",
    action="store_true",
    default=True,
    help="Run in background (default: true)",
)
scheduler_parser.add_argument(
    "--force",
    action="store_true",
    help="Force stop without waiting for current cycle",
)

# Add to main():
if args.command == "scheduler":
    from .cli.scheduler import run_scheduler_command
    return run_scheduler_command(
        action=args.action,
        config_file=args.config,
        daemon=args.daemon,
        force=args.force,
    )
```

### Testing Strategy (Days 3-4)

#### Unit Tests (`tests/cli/test_scheduler_cli.py`)

1. **PID File Management**
   - Test PID file creation
   - Test stale PID detection
   - Test PID file cleanup

2. **Process Management**
   - Test process running check
   - Mock os.kill for stop command
   - Test graceful vs force stop

3. **Status Display**
   - Mock database queries
   - Test status formatting
   - Test uptime calculation

4. **Configuration Loading**
   - Test default configuration
   - Test config file loading (deferred to Day 7)

---

## Day 5-6: Monitor Command

### Objective
Implement `dgas monitor` command for viewing performance metrics, calibration reports, and signal history.

### Use Cases

**UC1: Performance Summary**
```bash
$ dgas monitor performance

╔══════════════════════════════════════════════════════╗
║          Performance Summary (Last 24h)             ║
╠══════════════════════════════════════════════════════╣
║  Total Cycles: 48                                   ║
║  Successful: 47 (97.9%)                             ║
║  Symbols Processed: 1,200                           ║
║  Signals Generated: 156                             ║
║                                                      ║
║  Latency (P95): 42.3s                   ✓ SLA Met  ║
║  Throughput: 28.5 symbols/s             ✓ SLA Met  ║
║  Error Rate: 0.5%                       ✓ SLA Met  ║
║  Uptime: 99.8%                          ✓ SLA Met  ║
╚══════════════════════════════════════════════════════╝
```

**UC2: Calibration Report**
```bash
$ dgas monitor calibration --days 30

╔══════════════════════════════════════════════════════╗
║         Calibration Report (Last 30 days)           ║
╠══════════════════════════════════════════════════════╣
║  Total Signals: 1,245                               ║
║  Evaluated: 1,128 (90.6%)                           ║
║                                                      ║
║  Win Rate: 62.3%                                    ║
║  Avg P&L: +1.8%                                     ║
║  Target Hit Rate: 65.2%                             ║
║  Stop Hit Rate: 34.8%                               ║
╚══════════════════════════════════════════════════════╝

By Confidence:
┏━━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━┓
┃ Confidence ┃ Win Rate  ┃  Avg P&L  ┃ Count  ┃
┡━━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━┩
│ 0.9-1.0    │   72.5%   │   +2.4%   │   142  │
│ 0.8-0.9    │   68.1%   │   +2.1%   │   318  │
│ 0.7-0.8    │   61.2%   │   +1.6%   │   445  │
│ 0.6-0.7    │   54.3%   │   +0.9%   │   223  │
└────────────┴───────────┴───────────┴────────┘

By Signal Type:
┏━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━┓
┃  Type   ┃ Win Rate  ┃  Avg P&L  ┃ Count  ┃
┡━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━┩
│ LONG    │   64.2%   │   +1.9%   │   687  │
│ SHORT   │   59.1%   │   +1.6%   │   441  │
└─────────┴───────────┴───────────┴────────┘
```

**UC3: Signal History**
```bash
$ dgas monitor signals --symbol AAPL --days 7

Recent Signals for AAPL (Last 7 days):

2025-11-06 14:30 UTC - LONG @ $150.25
  Stop: $145.50  Target: $157.00  Confidence: 75%
  Outcome: WIN (+4.5%)  ✓ Target hit after 6 hours

2025-11-05 10:00 UTC - SHORT @ $152.00
  Stop: $155.50  Target: $147.00  Confidence: 68%
  Outcome: LOSS (-2.3%)  ✗ Stop hit after 2 hours

2025-11-04 15:30 UTC - LONG @ $148.50
  Stop: $144.00  Target: $154.00  Confidence: 71%
  Outcome: NEUTRAL (+0.8%)  Neither hit (window expired)
```

**UC4: Dashboard Mode (Live Updating)**
```bash
$ dgas monitor dashboard

[Updates every 30 seconds with latest stats]

╔══════════════════════════════════════════════════════╗
║           Real-Time Prediction Dashboard            ║
╠══════════════════════════════════════════════════════╣
║  Scheduler Status: RUNNING                          ║
║  Last Cycle: 2 minutes ago                          ║
║  Next Cycle: in 28 minutes                          ║
║                                                      ║
║  Today's Stats:                                     ║
║    Cycles: 12                                       ║
║    Signals: 34                                      ║
║    Avg Latency: 38.2s                               ║
║                                                      ║
║  Recent Signals:                                    ║
║    14:30 - AAPL LONG @ $150.25 (75%)                ║
║    14:30 - MSFT SHORT @ $380.00 (68%)               ║
║    14:00 - GOOGL LONG @ $142.50 (72%)               ║
╚══════════════════════════════════════════════════════╝

Press Ctrl+C to exit
```

### Implementation Specification

#### File: `src/dgas/cli/monitor.py`

```python
"""CLI command for monitoring and calibration reports."""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table

from ..prediction import PredictionPersistence
from ..prediction.monitoring import CalibrationEngine, PerformanceTracker
from ..settings import get_settings

console = Console()


def run_monitor_command(
    *,
    subcommand: str,
    symbol: str | None,
    days: int,
    run_id: int | None,
    dashboard: bool,
) -> int:
    """
    Display monitoring data and calibration reports.

    Args:
        subcommand: Monitor subcommand (performance, calibration, signals, dashboard)
        symbol: Optional symbol filter
        days: Lookback period in days
        run_id: Optional specific run ID
        dashboard: Live updating dashboard mode

    Returns:
        Exit code
    """
    settings = get_settings()
    persistence = PredictionPersistence(settings)

    if subcommand == "performance":
        return _show_performance(persistence, days)
    elif subcommand == "calibration":
        return _show_calibration(persistence, days)
    elif subcommand == "signals":
        return _show_signals(persistence, symbol, days, run_id)
    elif subcommand == "dashboard":
        return _show_dashboard(persistence)
    else:
        console.print(f"[red]Unknown subcommand: {subcommand}[/red]")
        return 1


def _show_performance(persistence: PredictionPersistence, days: int) -> int:
    """Show performance summary."""
    tracker = PerformanceTracker(persistence)
    summary = tracker.get_performance_summary(lookback_hours=days * 24)

    # Create performance panel
    sla_status = "[green]✓ SLA Met[/green]" if summary.sla_compliant else "[red]✗ SLA Violated[/red]"

    panel_content = f"""
[bold]Total Cycles:[/bold] {summary.total_cycles}
[bold]Successful:[/bold] {summary.successful_cycles} ({summary.uptime_pct:.1f}%)
[bold]Symbols Processed:[/bold] {summary.total_symbols_processed:,}
[bold]Signals Generated:[/bold] {summary.total_signals_generated:,}

[bold cyan]Latency Metrics:[/bold cyan]
  Avg: {summary.avg_latency_ms / 1000:.1f}s
  P50: {summary.p50_latency_ms / 1000:.1f}s
  P95: {summary.p95_latency_ms / 1000:.1f}s  [{'green' if summary.p95_latency_ms <= 60000 else 'red'}]Target: ≤60s[/]
  P99: {summary.p99_latency_ms / 1000:.1f}s

[bold cyan]Throughput:[/bold cyan]
  {summary.avg_throughput:.1f} symbols/second

[bold cyan]Reliability:[/bold cyan]
  Error Rate: {summary.error_rate:.1f}%  [{'green' if summary.error_rate <= 1.0 else 'red'}]Target: ≤1%[/]
  Uptime: {summary.uptime_pct:.1f}%  [{'green' if summary.uptime_pct >= 99.0 else 'red'}]Target: ≥99%[/]

[bold]SLA Status:[/bold] {sla_status}
    """.strip()

    console.print(Panel(
        panel_content,
        title=f"Performance Summary (Last {days} days)",
        border_style="green" if summary.sla_compliant else "red"
    ))

    # Show violations if any
    if summary.sla_violations:
        console.print("\n[bold red]SLA Violations:[/bold red]")
        for key, violation in summary.sla_violations.items():
            console.print(f"  • {violation['message']}")

    return 0


def _show_calibration(persistence: PredictionPersistence, days: int) -> int:
    """Show calibration report."""
    engine = CalibrationEngine(persistence)

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)

    report = engine.get_calibration_report(date_range=(start, end))

    # Main panel
    panel_content = f"""
[bold]Total Signals:[/bold] {report.total_signals:,}
[bold]Evaluated:[/bold] {report.evaluated_signals:,} ({report.evaluated_signals / report.total_signals * 100 if report.total_signals > 0 else 0:.1f}%)

[bold cyan]Overall Performance:[/bold cyan]
  Win Rate: {report.win_rate:.1%}
  Avg P&L: {report.avg_pnl_pct:+.2f}%
  Target Hit Rate: {report.target_hit_rate:.1%}
  Stop Hit Rate: {report.stop_hit_rate:.1%}
    """.strip()

    console.print(Panel(
        panel_content,
        title=f"Calibration Report (Last {days} days)",
        border_style="green"
    ))

    # By confidence table
    if report.by_confidence:
        console.print("\n[bold]By Confidence:[/bold]")
        table = Table()
        table.add_column("Confidence", style="cyan")
        table.add_column("Win Rate", justify="right")
        table.add_column("Avg P&L", justify="right")
        table.add_column("Count", justify="right")

        for bucket, metrics in sorted(report.by_confidence.items()):
            table.add_row(
                bucket,
                f"{metrics['win_rate']:.1%}",
                f"{metrics['avg_pnl']:+.2f}%",
                str(int(metrics['count'])),
            )

        console.print(table)

    # By signal type table
    if report.by_signal_type:
        console.print("\n[bold]By Signal Type:[/bold]")
        table = Table()
        table.add_column("Type", style="cyan")
        table.add_column("Win Rate", justify="right")
        table.add_column("Avg P&L", justify="right")
        table.add_column("Count", justify="right")

        for signal_type, metrics in report.by_signal_type.items():
            table.add_row(
                signal_type,
                f"{metrics['win_rate']:.1%}",
                f"{metrics['avg_pnl']:+.2f}%",
                str(int(metrics['count'])),
            )

        console.print(table)

    return 0


def _show_signals(
    persistence: PredictionPersistence,
    symbol: str | None,
    days: int,
    run_id: int | None,
) -> int:
    """Show signal history."""
    if run_id:
        # Show signals from specific run
        signals = persistence.get_recent_signals(limit=1000)
        signals = [s for s in signals if s["run_id"] == run_id]
        title = f"Signals from Run #{run_id}"
    elif symbol:
        signals = persistence.get_recent_signals(
            symbol=symbol,
            lookback_hours=days * 24,
            limit=100,
        )
        title = f"Recent Signals for {symbol} (Last {days} days)"
    else:
        signals = persistence.get_recent_signals(
            lookback_hours=days * 24,
            limit=50,
        )
        title = f"Recent Signals (Last {days} days)"

    console.print(f"\n[bold]{title}[/bold]\n")

    if not signals:
        console.print("[yellow]No signals found[/yellow]")
        return 0

    for signal in signals:
        _print_signal(signal)
        console.print()

    console.print(f"[cyan]Total: {len(signals)} signals[/cyan]")
    return 0


def _show_dashboard(persistence: PredictionPersistence) -> int:
    """Show live updating dashboard."""
    console.print("[cyan]Starting dashboard (Ctrl+C to exit)...[/cyan]\n")

    def generate_dashboard():
        """Generate dashboard content."""
        # Get scheduler state
        state = persistence.get_scheduler_state()

        # Get recent runs
        recent_runs = persistence.get_recent_runs(limit=1)
        today_runs = [
            r for r in persistence.get_recent_runs(limit=100)
            if r["run_timestamp"].date() == datetime.now(timezone.utc).date()
        ]

        # Get recent signals
        recent_signals = persistence.get_recent_signals(lookback_hours=1, limit=5)

        # Build dashboard
        status_color = "green" if state["status"] == "RUNNING" else "yellow"

        content = f"""
[bold {status_color}]Scheduler Status: {state['status']}[/bold {status_color}]
Last Cycle: {_format_time_ago(state['last_run_timestamp'])}
Next Cycle: {_format_time_until(state['next_scheduled_run'])}

[bold cyan]Today's Stats:[/bold cyan]
  Cycles: {len(today_runs)}
  Signals: {sum(r['signals_generated'] for r in today_runs)}
  Avg Latency: {sum(r['execution_time_ms'] for r in today_runs) / len(today_runs) / 1000 if today_runs else 0:.1f}s

[bold cyan]Recent Signals:[/bold cyan]
        """.strip()

        for signal in recent_signals[:3]:
            signal_time = signal['signal_timestamp'].strftime("%H:%M")
            content += f"\n  {signal_time} - {signal['symbol']} {signal['signal_type']} @ ${signal['entry_price']} ({signal['confidence']:.0%})"

        return Panel(
            content,
            title="Real-Time Prediction Dashboard",
            border_style="green"
        )

    try:
        with Live(generate_dashboard(), refresh_per_second=0.5, console=console) as live:
            while True:
                time.sleep(30)  # Update every 30 seconds
                live.update(generate_dashboard())
    except KeyboardInterrupt:
        console.print("\n[yellow]Dashboard stopped[/yellow]")
        return 0


def _print_signal(signal: dict):
    """Print formatted signal."""
    timestamp = signal["signal_timestamp"].strftime("%Y-%m-%d %H:%M UTC")
    signal_type = signal["signal_type"]
    color = "green" if signal_type == "LONG" else "red"

    console.print(f"[{color}]{timestamp} - {signal_type} @ ${signal['entry_price']}[/{color}]")
    console.print(f"  Stop: ${signal['stop_loss']}  Target: ${signal['target_price']}  Confidence: {signal['confidence']:.0%}")

    if signal["outcome"]:
        outcome_color = "green" if signal["outcome"] == "WIN" else "red" if signal["outcome"] == "LOSS" else "yellow"
        console.print(f"  Outcome: [{outcome_color}]{signal['outcome']}[/{outcome_color}] ({signal['pnl_pct']:+.1f}%)")


def _format_time_ago(dt: datetime | None) -> str:
    """Format time ago."""
    if dt is None:
        return "Never"

    diff = datetime.now(timezone.utc) - dt
    minutes = int(diff.total_seconds() / 60)

    if minutes < 60:
        return f"{minutes} minutes ago"
    else:
        hours = minutes // 60
        return f"{hours} hours ago"


def _format_time_until(dt: datetime | None) -> str:
    """Format time until."""
    if dt is None:
        return "Not scheduled"

    diff = dt - datetime.now(timezone.utc)
    minutes = int(diff.total_seconds() / 60)

    if minutes < 0:
        return "Overdue"
    elif minutes < 60:
        return f"in {minutes} minutes"
    else:
        hours = minutes // 60
        return f"in {hours} hours"
```

#### CLI Integration

```python
# Add to build_parser():
monitor_parser = subparsers.add_parser(
    "monitor",
    help="View performance metrics and calibration reports",
)
monitor_parser.add_argument(
    "subcommand",
    choices=["performance", "calibration", "signals", "dashboard"],
    help="Monitor subcommand",
)
monitor_parser.add_argument(
    "--symbol",
    help="Filter by symbol (for signals subcommand)",
)
monitor_parser.add_argument(
    "--days",
    type=int,
    default=7,
    help="Lookback period in days (default: 7)",
)
monitor_parser.add_argument(
    "--run",
    type=int,
    dest="run_id",
    help="Show signals from specific run ID",
)

# Add to main():
if args.command == "monitor":
    from .cli.monitor import run_monitor_command
    return run_monitor_command(
        subcommand=args.subcommand,
        symbol=args.symbol,
        days=args.days,
        run_id=args.run_id,
        dashboard=args.subcommand == "dashboard",
    )
```

### Testing Strategy (Days 5-6)

#### Unit Tests (`tests/cli/test_monitor_cli.py`)

1. **Performance Display**
   - Mock PerformanceTracker
   - Test SLA status formatting
   - Test violation display

2. **Calibration Report**
   - Mock CalibrationEngine
   - Test table formatting
   - Test confidence/type grouping display

3. **Signal History**
   - Mock signal queries
   - Test symbol filtering
   - Test run ID filtering
   - Test signal formatting

4. **Dashboard Mode**
   - Mock persistence queries
   - Test time formatting
   - Test live updates (difficult, may defer)

---

## Day 7: Configuration System

### Objective
Implement YAML/JSON configuration file support for scheduler settings.

### Configuration File Format

**Example: `dgas.yaml`**
```yaml
# DGAS Prediction Scheduler Configuration

scheduler:
  # Execution settings
  interval: "30min"  # Update frequency: 5min, 15min, 30min, 1h

  # Watchlist
  watchlist:
    - AAPL
    - MSFT
    - GOOGL
    - TSLA
    - NVDA

  # Or load from file:
  # watchlist_file: "watchlist.txt"

  # Analysis timeframes
  timeframes:
    - "4h"   # Higher timeframe for trend
    - "1h"   # Trading timeframe
    - "30min"  # Entry timeframe

  # Signal filtering
  filters:
    min_confidence: 0.65      # Minimum signal confidence
    min_signal_strength: 0.50  # Minimum pattern strength
    min_alignment: 0.60       # Minimum timeframe alignment
    enabled_patterns: null    # null = all patterns, or list specific ones

  # Exchange settings
  exchange: "US"
  market_hours:
    open: "09:30"
    close: "16:00"
    timezone: "America/New_York"
    trading_days:
      - MON
      - TUE
      - WED
      - THU
      - FRI

  # Performance settings
  max_symbols_per_cycle: 50
  timeout_seconds: 180

  # Operational
  run_on_startup: true
  catch_up_on_startup: true
  persist_state: true

# Notification settings
notifications:
  enabled_channels:
    - discord
    - console

  # Filtering
  min_confidence: 0.70  # Only notify high-confidence signals

  # Discord configuration
  discord:
    bot_token: "${DISCORD_BOT_TOKEN}"  # Environment variable
    channel_id: "${DISCORD_CHANNEL_ID}"
    max_signals_per_message: 10

  # Console configuration
  console:
    max_signals: 20
    output_format: "rich"  # rich, plain, json

# Monitoring settings (optional)
monitoring:
  performance_tracking: true
  sla_thresholds:
    p95_latency_ms: 60000
    error_rate_pct: 1.0
    uptime_pct: 99.0

  calibration:
    evaluation_window_hours: 24
    auto_calibrate: false  # Run batch calibration automatically
    calibration_schedule: "0 0 * * *"  # Daily at midnight (cron format)
```

### Implementation Specification

#### File: `src/dgas/prediction/config.py`

```python
"""Configuration file loading for scheduler."""

from __future__ import annotations

import os
import re
from datetime import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from .scheduler import SchedulerConfig, TradingSession


class ConfigurationError(Exception):
    """Configuration validation error."""
    pass


def load_config_file(path: Path) -> Dict[str, Any]:
    """
    Load configuration from YAML or JSON file.

    Args:
        path: Path to configuration file

    Returns:
        Configuration dictionary

    Raises:
        ConfigurationError: If file cannot be loaded or parsed
    """
    if not path.exists():
        raise ConfigurationError(f"Configuration file not found: {path}")

    try:
        with open(path) as f:
            if path.suffix in {".yaml", ".yml"}:
                config = yaml.safe_load(f)
            elif path.suffix == ".json":
                import json
                config = json.load(f)
            else:
                raise ConfigurationError(f"Unsupported config format: {path.suffix}")

        # Expand environment variables
        config = _expand_env_vars(config)

        return config

    except yaml.YAMLError as e:
        raise ConfigurationError(f"YAML parsing error: {e}") from e
    except Exception as e:
        raise ConfigurationError(f"Failed to load config: {e}") from e


def scheduler_config_from_file(path: Path) -> SchedulerConfig:
    """
    Create SchedulerConfig from configuration file.

    Args:
        path: Path to YAML/JSON configuration file

    Returns:
        SchedulerConfig instance

    Raises:
        ConfigurationError: If configuration is invalid
    """
    config = load_config_file(path)

    # Extract scheduler section
    scheduler_dict = config.get("scheduler", {})

    # Load watchlist
    symbols = _load_watchlist(scheduler_dict)

    # Load timeframes
    timeframes = scheduler_dict.get("timeframes", ["4h", "1h", "30min"])

    # Load filters
    filters = scheduler_dict.get("filters", {})

    # Load trading session
    market_hours = scheduler_dict.get("market_hours", {})
    trading_session = TradingSession(
        market_open=_parse_time(market_hours.get("open", "09:30")),
        market_close=_parse_time(market_hours.get("close", "16:00")),
        timezone=market_hours.get("timezone", "America/New_York"),
        trading_days=market_hours.get("trading_days", ["MON", "TUE", "WED", "THU", "FRI"]),
    )

    # Create SchedulerConfig
    return SchedulerConfig(
        interval=scheduler_dict.get("interval", "30min"),
        symbols=symbols,
        enabled_timeframes=timeframes,
        exchange_code=scheduler_dict.get("exchange", "US"),
        trading_session=trading_session,
        min_confidence=filters.get("min_confidence", 0.6),
        min_signal_strength=filters.get("min_signal_strength", 0.5),
        min_alignment=filters.get("min_alignment", 0.6),
        enabled_patterns=filters.get("enabled_patterns"),
        max_symbols_per_cycle=scheduler_dict.get("max_symbols_per_cycle", 50),
        timeout_seconds=scheduler_dict.get("timeout_seconds", 180),
        run_on_startup=scheduler_dict.get("run_on_startup", True),
        catch_up_on_startup=scheduler_dict.get("catch_up_on_startup", True),
        persist_state=scheduler_dict.get("persist_state", True),
    )


def _load_watchlist(scheduler_dict: Dict[str, Any]) -> List[str]:
    """Load watchlist from config or file."""
    symbols = scheduler_dict.get("watchlist", [])

    # Check for watchlist file
    watchlist_file = scheduler_dict.get("watchlist_file")
    if watchlist_file:
        path = Path(watchlist_file)
        if not path.exists():
            raise ConfigurationError(f"Watchlist file not found: {watchlist_file}")

        with open(path) as f:
            file_symbols = [
                line.strip() for line in f
                if line.strip() and not line.startswith("#")
            ]
        symbols.extend(file_symbols)

    if not symbols:
        raise ConfigurationError("No symbols specified in watchlist")

    return symbols


def _parse_time(time_str: str) -> time:
    """Parse time string (HH:MM format)."""
    try:
        hour, minute = time_str.split(":")
        return time(int(hour), int(minute))
    except Exception as e:
        raise ConfigurationError(f"Invalid time format '{time_str}': {e}") from e


def _expand_env_vars(obj: Any) -> Any:
    """Recursively expand environment variables in config."""
    if isinstance(obj, dict):
        return {k: _expand_env_vars(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_expand_env_vars(item) for item in obj]
    elif isinstance(obj, str):
        # Replace ${VAR_NAME} with environment variable
        pattern = re.compile(r'\$\{([^}]+)\}')

        def replacer(match):
            var_name = match.group(1)
            value = os.environ.get(var_name)
            if value is None:
                raise ConfigurationError(f"Environment variable not set: {var_name}")
            return value

        return pattern.sub(replacer, obj)
    else:
        return obj


def validate_config(config: SchedulerConfig) -> List[str]:
    """
    Validate scheduler configuration.

    Args:
        config: SchedulerConfig to validate

    Returns:
        List of validation warnings (empty if no issues)
    """
    warnings = []

    # Check symbol count
    if len(config.symbols) > 100:
        warnings.append(f"Large watchlist ({len(config.symbols)} symbols) may impact performance")

    # Check interval
    valid_intervals = {"5min", "15min", "30min", "1h", "4h"}
    if config.interval not in valid_intervals:
        warnings.append(f"Unusual interval '{config.interval}' (typical: 30min, 1h)")

    # Check confidence thresholds
    if config.min_confidence < 0.5:
        warnings.append(f"Low confidence threshold ({config.min_confidence:.0%}) may produce many signals")

    # Check timeframes
    if len(config.enabled_timeframes) < 2:
        warnings.append("Multi-timeframe analysis works best with 2+ timeframes")

    return warnings


def create_sample_config(output_path: Path):
    """Create sample configuration file."""
    sample_config = """# DGAS Prediction Scheduler Configuration
# This is a sample configuration file with recommended defaults

scheduler:
  # Update frequency (5min, 15min, 30min, 1h, 4h)
  interval: "30min"

  # Watchlist - symbols to analyze
  watchlist:
    - AAPL
    - MSFT
    - GOOGL

  # Or load from file:
  # watchlist_file: "watchlist.txt"

  # Analysis timeframes
  timeframes:
    - "4h"   # Higher timeframe for trend
    - "1h"   # Trading timeframe
    - "30min"  # Entry timeframe

  # Signal filtering
  filters:
    min_confidence: 0.65
    min_signal_strength: 0.50
    min_alignment: 0.60

  # Exchange settings
  exchange: "US"
  market_hours:
    open: "09:30"
    close: "16:00"
    timezone: "America/New_York"

# Notification settings
notifications:
  enabled_channels:
    - console

  min_confidence: 0.70

  # Uncomment to enable Discord notifications:
  # discord:
  #   bot_token: "${DISCORD_BOT_TOKEN}"
  #   channel_id: "${DISCORD_CHANNEL_ID}"
"""

    with open(output_path, "w") as f:
        f.write(sample_config)
```

### Integration with Scheduler CLI

Update `scheduler.py` to use config loading:

```python
def _load_scheduler_config(config_file: Path | None) -> SchedulerConfig:
    """Load scheduler configuration from file or defaults."""
    if config_file is None:
        # Check for default config file
        default_configs = [
            Path("dgas.yaml"),
            Path("dgas.yml"),
            Path.home() / ".dgas" / "config.yaml",
        ]

        for path in default_configs:
            if path.exists():
                config_file = path
                break

    if config_file and config_file.exists():
        from ..prediction.config import scheduler_config_from_file, validate_config

        console.print(f"[cyan]Loading configuration from {config_file}[/cyan]")

        try:
            config = scheduler_config_from_file(config_file)

            # Validate and show warnings
            warnings = validate_config(config)
            for warning in warnings:
                console.print(f"[yellow]Warning: {warning}[/yellow]")

            console.print(f"[green]✓[/green] Configuration loaded successfully")
            return config

        except Exception as e:
            console.print(f"[red]Error loading config: {e}[/red]")
            console.print("[yellow]Using default configuration[/yellow]")

    # Return default configuration
    return SchedulerConfig(
        symbols=["AAPL", "MSFT", "GOOGL"],
        interval="30min",
    )
```

### Sample Config Generation CLI

```python
# Add to build_parser():
config_parser = subparsers.add_parser(
    "init-config",
    help="Create sample configuration file",
)
config_parser.add_argument(
    "--output",
    type=Path,
    default=Path("dgas.yaml"),
    help="Output file path (default: dgas.yaml)",
)

# Add to main():
if args.command == "init-config":
    from .prediction.config import create_sample_config

    if args.output.exists():
        console.print(f"[yellow]Warning: {args.output} already exists[/yellow]")
        if not Confirm.ask("Overwrite?"):
            return 0

    create_sample_config(args.output)
    console.print(f"[green]✓[/green] Sample configuration created: {args.output}")
    console.print("\nEdit the file and run: dgas scheduler start --config dgas.yaml")
    return 0
```

### Testing Strategy (Day 7)

#### Unit Tests (`tests/prediction/test_config.py`)

1. **Config File Loading**
   - Test YAML parsing
   - Test JSON parsing
   - Test environment variable expansion
   - Test file not found error

2. **Scheduler Config Creation**
   - Test complete config
   - Test minimal config with defaults
   - Test watchlist loading from file
   - Test invalid configurations

3. **Validation**
   - Test validation warnings
   - Test threshold checks
   - Test watchlist size warnings

4. **Sample Config Generation**
   - Test sample file creation
   - Verify sample is valid YAML

---

## Dependencies & Integration

### Required Python Packages
```toml
# Add to pyproject.toml dependencies:
pyyaml = "^6.0"  # YAML configuration support
rich = "^13.7.0"  # Already present - formatted CLI output
```

### File Structure
```
src/dgas/
├── cli/
│   ├── __init__.py
│   ├── analyze.py (existing)
│   ├── backtest.py (existing)
│   ├── predict.py (NEW)
│   ├── scheduler.py (NEW)
│   └── monitor.py (NEW)
├── prediction/
│   ├── config.py (NEW)
│   ├── scheduler.py (UPDATE - add config loading)
│   └── ...
└── __main__.py (UPDATE - add new commands)

tests/cli/
├── test_predict_cli.py (NEW)
├── test_scheduler_cli.py (NEW)
├── test_monitor_cli.py (NEW)
└── ...

tests/prediction/
├── test_config.py (NEW)
└── ...
```

### Environment Variables
```bash
# Required for notifications
DISCORD_BOT_TOKEN=your_bot_token_here
DISCORD_CHANNEL_ID=your_channel_id_here

# Required for database
DATABASE_URL=postgresql://user:pass@localhost/dgas_db
```

---

## Success Criteria

### Days 1-2: Predict Command
- [x] `dgas predict` command implemented
- [x] Symbol and watchlist file loading
- [x] Summary/detailed/JSON output formats
- [x] Database persistence option
- [x] Notification integration
- [x] CLI tests passing

### Days 3-4: Scheduler Command
- [x] `dgas scheduler start/stop/status/restart` commands
- [x] PID file management
- [x] Daemon mode (background execution)
- [x] Status display with metrics
- [x] Graceful shutdown
- [x] CLI tests passing

### Days 5-6: Monitor Command
- [x] `dgas monitor performance` - SLA metrics
- [x] `dgas monitor calibration` - Win rates and P&L
- [x] `dgas monitor signals` - Signal history
- [x] `dgas monitor dashboard` - Live updates
- [x] Rich formatted output
- [x] CLI tests passing

### Day 7: Configuration System
- [x] YAML/JSON config file loading
- [x] `SchedulerConfig.from_file()` implementation
- [x] Environment variable expansion
- [x] Configuration validation
- [x] Sample config generation (`dgas init-config`)
- [x] Tests passing

### Overall Week 6 Success
- [x] All CLI commands functional
- [x] Configuration system complete
- [x] Consistent CLI patterns and UX
- [x] Comprehensive help text
- [x] Error handling and validation
- [x] Tests passing (>85% coverage)
- [x] Documentation complete

---

## Risks & Mitigations

### Risk 1: Daemon Management Complexity
**Issue:** Process management, PID files, and signal handling can be complex and platform-dependent.

**Mitigation:**
- Use simple PID file approach (proven pattern)
- Focus on Unix/Linux (primary deployment target)
- Test graceful shutdown thoroughly
- Document Windows limitations if any

### Risk 2: Rich Output in Non-TTY Environments
**Issue:** Rich formatting may not work in scripts/cron jobs.

**Mitigation:**
- Provide JSON output format for automation
- Detect TTY and fall back to plain text
- Test in both interactive and non-interactive modes

### Risk 3: Configuration Validation
**Issue:** Invalid configurations could cause runtime failures.

**Mitigation:**
- Comprehensive validation with clear error messages
- Sample configuration with comments
- Validate on load, not just on use
- Provide helpful warnings for common issues

---

## Future Enhancements (Post-Week 6)

1. **Web Dashboard** - Browser-based monitoring UI
2. **REST API** - HTTP API for remote control
3. **Docker Integration** - Containerized deployment
4. **Systemd Integration** - Linux service management
5. **Email Notifications** - Additional notification channel
6. **Slack Integration** - Alternative to Discord
7. **Alert Rules** - Custom alerting based on metrics
8. **Config Hot-Reload** - Update config without restart

---

## Questions for Review / Approval

1. **Daemon Implementation:** Should we use `python-daemon` library or simple fork approach?
   - **Recommendation:** Simple fork (less dependencies, more control)

2. **Dashboard Refresh Rate:** 30 seconds vs configurable?
   - **Recommendation:** 30 seconds fixed (simple, adequate)

3. **Config File Location Priority:** Which defaults to check first?
   - **Recommendation:** `./dgas.yaml` → `~/.dgas/config.yaml` → defaults

4. **Notification in Predict Command:** Enable by default or opt-in?
   - **Recommendation:** Opt-in with `--notify` flag (explicit is better)

---

## Conclusion

Week 6 delivers a complete CLI interface that makes the prediction system accessible and usable. The three main commands (`predict`, `scheduler`, `monitor`) cover all user workflows, while the configuration system provides flexibility without complexity.

The implementation follows established patterns from existing CLI commands, uses Rich for great UX, and provides both interactive and automation-friendly modes.

**Status:** Ready for approval and implementation

---

**END OF PLAN**
