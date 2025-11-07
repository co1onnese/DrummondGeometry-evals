"""
Configure command for DGAS CLI.

Provides interactive configuration wizard and config file management.
"""

from __future__ import annotations

import logging
import os
import sys
from argparse import ArgumentParser, Namespace
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import ValidationError
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, FloatPrompt, IntPrompt, Prompt
from rich.syntax import Syntax
from rich.table import Table

from dgas.config import DGASConfig
from dgas.config.loader import ConfigLoader

logger = logging.getLogger(__name__)


def setup_configure_parser(subparsers) -> ArgumentParser:
    """
    Set up the configure subcommand parser.

    Args:
        subparsers: The subparsers object from argparse

    Returns:
        The configure subparser
    """
    parser = subparsers.add_parser(
        "configure",
        help="Manage DGAS configuration",
        description="Create, edit, validate, and view configuration files",
    )

    configure_subparsers = parser.add_subparsers(dest="configure_command")

    # Init command
    init_parser = configure_subparsers.add_parser(
        "init",
        help="Interactive configuration wizard",
    )
    init_parser.add_argument(
        "--output",
        type=Path,
        default=Path.home() / ".config" / "dgas" / "config.yaml",
        help="Output path for configuration file",
    )
    init_parser.add_argument(
        "--template",
        choices=["minimal", "standard", "advanced"],
        default="standard",
        help="Configuration template (default: standard)",
    )
    init_parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing configuration file",
    )
    init_parser.set_defaults(func=_init_command)

    # Show command
    show_parser = configure_subparsers.add_parser(
        "show",
        help="Display current configuration",
    )
    show_parser.add_argument(
        "--config",
        type=Path,
        help="Path to config file (default: auto-detect)",
    )
    show_parser.add_argument(
        "--format",
        choices=["yaml", "json"],
        default="yaml",
        help="Output format (default: yaml)",
    )
    show_parser.set_defaults(func=_show_command)

    # Validate command
    validate_parser = configure_subparsers.add_parser(
        "validate",
        help="Validate configuration file",
    )
    validate_parser.add_argument(
        "config_file",
        type=Path,
        nargs="?",
        help="Path to config file (default: auto-detect)",
    )
    validate_parser.set_defaults(func=_validate_command)

    # Sample command
    sample_parser = configure_subparsers.add_parser(
        "sample",
        help="Generate sample configuration file",
    )
    sample_parser.add_argument(
        "--output",
        type=Path,
        default=Path("dgas-sample.yaml"),
        help="Output path for sample configuration",
    )
    sample_parser.add_argument(
        "--template",
        choices=["minimal", "standard", "advanced"],
        default="standard",
        help="Sample template (default: standard)",
    )
    sample_parser.set_defaults(func=_sample_command)

    # Edit command
    edit_parser = configure_subparsers.add_parser(
        "edit",
        help="Edit configuration with $EDITOR",
    )
    edit_parser.add_argument(
        "--config",
        type=Path,
        help="Path to config file (default: auto-detect)",
    )
    edit_parser.set_defaults(func=_edit_command)

    return parser


def _init_command(args: Namespace) -> int:
    """
    Interactive configuration wizard.

    Args:
        args: Parsed command line arguments

    Returns:
        Exit code (0 for success, non-zero for error)
    """
    console = Console()

    # Check if config file exists
    if args.output.exists() and not args.force:
        console.print(f"[yellow]Configuration file already exists: {args.output}[/yellow]")
        if not Confirm.ask("Overwrite existing configuration?", default=False):
            console.print("[cyan]Configuration unchanged[/cyan]")
            return 0

    console.print(Panel.fit(
        "[bold cyan]DGAS Configuration Wizard[/bold cyan]\n"
        "This wizard will help you create a configuration file.",
        border_style="cyan"
    ))

    try:
        if args.template == "minimal":
            config_dict = _wizard_minimal(console)
        elif args.template == "standard":
            config_dict = _wizard_standard(console)
        else:  # advanced
            config_dict = _wizard_advanced(console)

        # Validate configuration
        console.print("\n[cyan]Validating configuration...[/cyan]")
        config = DGASConfig(**config_dict)

        # Save configuration
        loader = ConfigLoader()
        loader.save(config, args.output, format="yaml")

        console.print(f"\n[green]✓ Configuration saved to: {args.output}[/green]")
        console.print("\n[cyan]Next steps:[/cyan]")
        console.print("  1. Set required environment variables (DATABASE_URL, etc.)")
        console.print("  2. Validate configuration: dgas configure validate")
        console.print("  3. Start scheduler: dgas scheduler start")

        return 0

    except ValidationError as e:
        console.print(f"\n[red]Configuration validation failed:[/red]")
        console.print(str(e))
        return 1
    except Exception as e:
        console.print(f"\n[red]Error: {e}[/red]")
        logger.exception("Configuration wizard failed")
        return 1


def _show_command(args: Namespace) -> int:
    """
    Display current configuration.

    Args:
        args: Parsed command line arguments

    Returns:
        Exit code (0 for success, non-zero for error)
    """
    console = Console()

    try:
        # Load configuration
        loader = ConfigLoader(args.config)
        config = loader.load()

        # Display source
        if loader.config_path:
            console.print(f"[cyan]Configuration loaded from: {loader.config_path}[/cyan]\n")
        else:
            found = ConfigLoader.find_config_file()
            if found:
                console.print(f"[cyan]Configuration loaded from: {found}[/cyan]\n")
            else:
                console.print("[yellow]Using default configuration (no file found)[/yellow]\n")

        # Convert to dict and display
        config_dict = config.model_dump(exclude_none=True)

        if args.format == "yaml":
            import yaml
            yaml_str = yaml.dump(config_dict, default_flow_style=False, sort_keys=False)
            syntax = Syntax(yaml_str, "yaml", theme="monokai", line_numbers=True)
            console.print(syntax)
        else:  # json
            import json
            json_str = json.dumps(config_dict, indent=2)
            syntax = Syntax(json_str, "json", theme="monokai", line_numbers=True)
            console.print(syntax)

        return 0

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        logger.exception("Show command failed")
        return 1


def _validate_command(args: Namespace) -> int:
    """
    Validate configuration file.

    Args:
        args: Parsed command line arguments

    Returns:
        Exit code (0 for success, non-zero for error)
    """
    console = Console()

    try:
        # Load configuration
        loader = ConfigLoader(args.config_file)
        config = loader.load()

        # Display validation results
        config_file = args.config_file or ConfigLoader.find_config_file()
        console.print(f"[cyan]Validating: {config_file}[/cyan]\n")

        # Show summary
        table = Table(title="Configuration Summary", show_header=True, header_style="bold cyan")
        table.add_column("Section")
        table.add_column("Status")
        table.add_column("Details")

        table.add_row("Database", "[green]✓ Valid[/green]", f"URL: {config.database.url}")
        table.add_row(
            "Scheduler",
            "[green]✓ Valid[/green]",
            f"Symbols: {len(config.scheduler.symbols)}"
        )
        table.add_row(
            "Prediction",
            "[green]✓ Valid[/green]",
            f"Min confidence: {config.prediction.min_confidence:.0%}"
        )
        table.add_row(
            "Notifications",
            "[green]✓ Valid[/green]",
            f"Discord: {config.notifications.discord.enabled if config.notifications.discord else False}"
        )
        table.add_row(
            "Monitoring",
            "[green]✓ Valid[/green]",
            f"SLA P95: {config.monitoring.sla_p95_latency_ms}ms"
        )
        table.add_row(
            "Dashboard",
            "[green]✓ Valid[/green]",
            f"Port: {config.dashboard.port}"
        )

        console.print(table)
        console.print("\n[green]✓ Configuration is valid![/green]")

        return 0

    except ValidationError as e:
        console.print("[red]✗ Configuration validation failed:[/red]\n")
        for error in e.errors():
            field = " → ".join(str(x) for x in error["loc"])
            console.print(f"  [red]•[/red] {field}: {error['msg']}")
        return 1
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        logger.exception("Validate command failed")
        return 1


def _sample_command(args: Namespace) -> int:
    """
    Generate sample configuration file.

    Args:
        args: Parsed command line arguments

    Returns:
        Exit code (0 for success, non-zero for error)
    """
    console = Console()

    try:
        if args.output.exists():
            console.print(f"[yellow]File already exists: {args.output}[/yellow]")
            if not Confirm.ask("Overwrite?", default=False):
                return 0

        ConfigLoader.generate_sample_config(args.output, template=args.template)

        console.print(f"[green]✓ Sample configuration generated: {args.output}[/green]")
        console.print(f"\n[cyan]Template: {args.template}[/cyan]")
        console.print("\nEdit the file and set environment variables before using.")

        return 0

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        logger.exception("Sample command failed")
        return 1


def _edit_command(args: Namespace) -> int:
    """
    Edit configuration with $EDITOR.

    Args:
        args: Parsed command line arguments

    Returns:
        Exit code (0 for success, non-zero for error)
    """
    console = Console()

    try:
        # Find config file
        if args.config:
            config_file = args.config
        else:
            config_file = ConfigLoader.find_config_file()
            if not config_file:
                console.print("[yellow]No configuration file found.[/yellow]")
                console.print("Create one first: dgas configure init")
                return 1

        # Get editor
        editor = os.environ.get("EDITOR", "nano")

        console.print(f"[cyan]Opening {config_file} with {editor}...[/cyan]")

        # Open editor
        import subprocess
        result = subprocess.run([editor, str(config_file)])

        if result.returncode == 0:
            # Validate after editing
            console.print("\n[cyan]Validating configuration...[/cyan]")
            try:
                loader = ConfigLoader(config_file)
                loader.load()
                console.print("[green]✓ Configuration is valid[/green]")
                return 0
            except ValidationError as e:
                console.print("[yellow]⚠ Configuration has validation errors:[/yellow]")
                for error in e.errors():
                    field = " → ".join(str(x) for x in error["loc"])
                    console.print(f"  [red]•[/red] {field}: {error['msg']}")
                return 1
        else:
            console.print("[yellow]Editor exited with non-zero status[/yellow]")
            return 1

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        logger.exception("Edit command failed")
        return 1


# Wizard helper functions

def _wizard_minimal(console: Console) -> Dict[str, Any]:
    """Minimal configuration wizard."""
    console.print("\n[bold]Minimal Configuration[/bold]")
    console.print("Only essential settings will be configured.\n")

    db_url = Prompt.ask(
        "Database URL",
        default="${DATABASE_URL}",
    )

    return {
        "database": {
            "url": db_url,
        },
    }


def _wizard_standard(console: Console) -> Dict[str, Any]:
    """Standard configuration wizard."""
    console.print("\n[bold]Standard Configuration[/bold]")
    console.print("Common settings for typical usage.\n")

    # Database
    console.print("[bold cyan]1. Database Configuration[/bold cyan]")
    db_url = Prompt.ask("  Database URL", default="${DATABASE_URL}")
    db_pool_size = IntPrompt.ask("  Connection pool size", default=5)

    # Scheduler
    console.print("\n[bold cyan]2. Scheduler Configuration[/bold cyan]")
    symbols_input = Prompt.ask(
        "  Symbols to track (comma-separated)",
        default="AAPL,MSFT,GOOGL"
    )
    symbols = [s.strip() for s in symbols_input.split(",")]

    cron = Prompt.ask(
        "  Schedule (cron expression)",
        default="0 9,15 * * 1-5"
    )

    timezone = Prompt.ask("  Timezone", default="America/New_York")

    market_hours = Confirm.ask("  Market hours only?", default=True)

    # Notifications
    console.print("\n[bold cyan]3. Notifications[/bold cyan]")
    discord_enabled = Confirm.ask("  Enable Discord notifications?", default=True)

    discord_webhook = None
    if discord_enabled:
        discord_webhook = Prompt.ask("  Discord webhook URL", default="${DISCORD_WEBHOOK_URL}")

    return {
        "database": {
            "url": db_url,
            "pool_size": db_pool_size,
        },
        "scheduler": {
            "symbols": symbols,
            "cron_expression": cron,
            "timezone": timezone,
            "market_hours_only": market_hours,
        },
        "notifications": {
            "discord": {
                "enabled": discord_enabled,
                "webhook_url": discord_webhook if discord_enabled else None,
            },
            "console": {
                "enabled": True,
            },
        },
    }


def _wizard_advanced(console: Console) -> Dict[str, Any]:
    """Advanced configuration wizard."""
    console.print("\n[bold]Advanced Configuration[/bold]")
    console.print("All available settings will be configured.\n")

    # Get standard config first
    config_dict = _wizard_standard(console)

    # Prediction
    console.print("\n[bold cyan]4. Prediction Engine[/bold cyan]")
    min_confidence = FloatPrompt.ask("  Minimum confidence", default=0.6)
    min_signal_strength = FloatPrompt.ask("  Minimum signal strength", default=0.5)
    stop_loss_atr = FloatPrompt.ask("  Stop loss ATR multiplier", default=1.5)
    target_atr = FloatPrompt.ask("  Target ATR multiplier", default=2.5)

    config_dict["prediction"] = {
        "min_confidence": min_confidence,
        "min_signal_strength": min_signal_strength,
        "stop_loss_atr_multiplier": stop_loss_atr,
        "target_atr_multiplier": target_atr,
    }

    # Monitoring
    console.print("\n[bold cyan]5. Monitoring & SLA[/bold cyan]")
    sla_latency = IntPrompt.ask("  SLA P95 latency (ms)", default=60000)
    sla_error_rate = FloatPrompt.ask("  SLA error rate (%)", default=1.0)
    sla_uptime = FloatPrompt.ask("  SLA uptime (%)", default=99.0)

    config_dict["monitoring"] = {
        "sla_p95_latency_ms": sla_latency,
        "sla_error_rate_pct": sla_error_rate,
        "sla_uptime_pct": sla_uptime,
    }

    # Dashboard
    console.print("\n[bold cyan]6. Dashboard[/bold cyan]")
    port = IntPrompt.ask("  Port", default=8501)
    theme = Prompt.ask("  Theme", choices=["light", "dark"], default="light")
    refresh = IntPrompt.ask("  Auto-refresh interval (seconds)", default=30)

    config_dict["dashboard"] = {
        "port": port,
        "theme": theme,
        "auto_refresh_seconds": refresh,
    }

    return config_dict
