"""Rich console table output for signals."""

from __future__ import annotations

import structlog
from typing import Any
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from dgas.prediction.engine import GeneratedSignal, SignalType
from ..router import NotificationAdapter

logger = structlog.get_logger(__name__)


class ConsoleAdapter(NotificationAdapter):
    """Rich console table output for signals."""

    def __init__(
        self,
        max_signals: int = 10,
        output_format: str = "summary",
    ):
        """
        Initialize console adapter.

        Args:
            max_signals: Maximum number of signals to display
            output_format: "summary" or "detailed"
        """
        self.max_signals = max_signals
        self.output_format = output_format
        self.console = Console()
        self.logger = logger.bind(component="console_adapter")

    def send(
        self,
        signals: list[GeneratedSignal],
        metadata: dict[str, Any],
    ) -> bool:
        """Display signals in formatted Rich table."""
        if not signals:
            self.console.print("[yellow]No signals generated this cycle.[/yellow]")
            return True

        # Limit signals if configured
        display_signals = signals[: self.max_signals]

        if self.output_format == "summary":
            self._display_summary_table(display_signals, metadata)
        else:
            self._display_detailed_table(display_signals, metadata)

        # Show truncation warning if needed
        if len(signals) > self.max_signals:
            self.console.print(
                f"\n[dim]... and {len(signals) - self.max_signals} more signals "
                f"(showing top {self.max_signals})[/dim]"
            )

        return True

    def format_message(
        self,
        signals: list[GeneratedSignal],
    ) -> str:
        """Not used for console (uses Rich directly)."""
        return ""

    def _display_summary_table(
        self,
        signals: list[GeneratedSignal],
        metadata: dict[str, Any],
    ) -> None:
        """Display signals in compact summary table."""

        # Create title panel
        run_time = metadata.get("run_timestamp", "Unknown")
        title = Panel(
            f"[bold cyan]🎯 Trading Signals Generated[/bold cyan]\n" f"[dim]{run_time}[/dim]",
            border_style="cyan",
        )
        self.console.print(title)

        # Create table
        table = Table(title="Signal Summary", show_header=True, header_style="bold magenta")

        table.add_column("Symbol", style="cyan", width=8)
        table.add_column("Type", style="bold", width=6)
        table.add_column("Entry", justify="right", style="green", width=10)
        table.add_column("Stop", justify="right", style="red", width=10)
        table.add_column("Target", justify="right", style="blue", width=10)
        table.add_column("Conf", justify="right", width=8)
        table.add_column("R:R", justify="right", width=6)
        table.add_column("Align", justify="right", width=6)

        for signal in signals:
            # Color signal type
            signal_type_text = self._format_signal_type(signal.signal_type)

            # Color confidence
            conf_text = self._format_confidence(signal.confidence)

            # Color alignment
            align_text = self._format_alignment(signal.timeframe_alignment)

            table.add_row(
                signal.symbol,
                signal_type_text,
                f"${float(signal.entry_price):.2f}",
                f"${float(signal.stop_loss):.2f}",
                f"${float(signal.target_price):.2f}",
                conf_text,
                f"{signal.risk_reward_ratio:.2f}",
                align_text,
            )

        self.console.print(table)

    def _display_detailed_table(
        self,
        signals: list[GeneratedSignal],
        metadata: dict[str, Any],
    ) -> None:
        """Display signals with full details."""

        for i, signal in enumerate(signals, 1):
            # Create signal panel
            signal_type_color = "green" if signal.signal_type == SignalType.LONG else "red"

            title = (
                f"[{signal_type_color}]Signal {i}/{len(signals)}: "
                f"{signal.symbol} {signal.signal_type.value}[/{signal_type_color}]"
            )

            content = (
                f"[bold]Entry:[/bold] ${float(signal.entry_price):.2f}  "
                f"[bold]Stop:[/bold] ${float(signal.stop_loss):.2f}  "
                f"[bold]Target:[/bold] ${float(signal.target_price):.2f}\n"
                f"[bold]Confidence:[/bold] {self._format_confidence(signal.confidence)}  "
                f"[bold]Strength:[/bold] {signal.signal_strength:.1%}  "
                f"[bold]Alignment:[/bold] {self._format_alignment(signal.timeframe_alignment)}\n"
                f"[bold]HTF Trend:[/bold] {signal.htf_trend.value} ({signal.htf_timeframe})  "
                f"[bold]Trading TF:[/bold] {signal.trading_tf_state} ({signal.trading_timeframe})\n"
                f"[bold]R:R:[/bold] {signal.risk_reward_ratio:.2f}  "
                f"[bold]Confluence Zones:[/bold] {signal.confluence_zones_count}"
            )

            # Add pattern context if available
            if signal.pattern_context and "patterns" in signal.pattern_context:
                patterns = signal.pattern_context["patterns"]
                if patterns:
                    pattern_names = ", ".join([p["type"] for p in patterns[:3]])
                    content += f"\n[bold]Patterns:[/bold] {pattern_names}"

            panel = Panel(
                content,
                title=title,
                border_style=signal_type_color,
            )
            self.console.print(panel)

    def _format_signal_type(self, signal_type: SignalType) -> str:
        """Format signal type with color."""
        if signal_type == SignalType.LONG:
            return "[green]LONG[/green]"
        elif signal_type == SignalType.SHORT:
            return "[red]SHORT[/red]"
        elif signal_type == SignalType.EXIT_LONG:
            return "[yellow]EXIT_L[/yellow]"
        else:
            return "[yellow]EXIT_S[/yellow]"

    def _format_confidence(self, confidence: float) -> str:
        """Format confidence with color."""
        if confidence >= 0.8:
            return f"[bold green]{confidence:.1%}[/bold green]"
        elif confidence >= 0.6:
            return f"[yellow]{confidence:.1%}[/yellow]"
        else:
            return f"[dim]{confidence:.1%}[/dim]"

    def _format_alignment(self, alignment: float) -> str:
        """Format alignment with color."""
        if alignment >= 0.7:
            return f"[bold green]{alignment:.1%}[/bold green]"
        elif alignment >= 0.5:
            return f"[yellow]{alignment:.1%}[/yellow]"
        else:
            return f"[dim]{alignment:.1%}[/dim]"
