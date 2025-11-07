"""
Pydantic configuration schemas for DGAS.

Defines the structure and validation rules for all configuration options.
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class DatabaseConfig(BaseModel):
    """Database connection configuration."""

    url: str = Field(
        ...,
        description="Database connection URL (PostgreSQL)",
        examples=["postgresql://user:pass@localhost:5432/dgas"],
    )
    pool_size: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Connection pool size",
    )
    echo: bool = Field(
        default=False,
        description="Enable SQL query logging",
    )


class SchedulerConfig(BaseModel):
    """Prediction scheduler configuration."""

    symbols: List[str] = Field(
        default_factory=lambda: ["AAPL", "MSFT", "GOOGL"],
        description="Symbols to analyze",
        min_length=1,
    )
    cron_expression: str = Field(
        default="0 9,15 * * 1-5",
        description="Cron expression for scheduling (9 AM and 3 PM on weekdays)",
    )
    timezone: str = Field(
        default="America/New_York",
        description="Timezone for scheduler",
    )
    market_hours_only: bool = Field(
        default=True,
        description="Only run during market hours",
    )

    @field_validator("symbols")
    @classmethod
    def validate_symbols(cls, v: List[str]) -> List[str]:
        """Ensure symbols are uppercase and valid."""
        return [s.upper().strip() for s in v if s.strip()]


class PredictionConfig(BaseModel):
    """Prediction engine configuration."""

    min_confidence: float = Field(
        default=0.6,
        ge=0.0,
        le=1.0,
        description="Minimum confidence threshold for signals",
    )
    min_signal_strength: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Minimum signal strength threshold",
    )
    stop_loss_atr_multiplier: float = Field(
        default=1.5,
        gt=0.0,
        description="Stop loss ATR multiplier",
    )
    target_atr_multiplier: float = Field(
        default=2.5,
        gt=0.0,
        description="Target price ATR multiplier",
    )


class DiscordConfig(BaseModel):
    """Discord notification configuration."""

    enabled: bool = Field(
        default=True,
        description="Enable Discord notifications",
    )
    webhook_url: Optional[str] = Field(
        default=None,
        description="Discord webhook URL",
    )


class ConsoleConfig(BaseModel):
    """Console notification configuration."""

    enabled: bool = Field(
        default=True,
        description="Enable console notifications",
    )


class NotificationConfig(BaseModel):
    """Notification system configuration."""

    discord: Optional[DiscordConfig] = Field(
        default_factory=DiscordConfig,
        description="Discord notification settings",
    )
    console: Optional[ConsoleConfig] = Field(
        default_factory=ConsoleConfig,
        description="Console notification settings",
    )


class MonitoringConfig(BaseModel):
    """Monitoring and SLA configuration."""

    sla_p95_latency_ms: int = Field(
        default=60000,
        ge=1000,
        description="SLA target for P95 latency (milliseconds)",
    )
    sla_error_rate_pct: float = Field(
        default=1.0,
        ge=0.0,
        le=100.0,
        description="SLA target for error rate (percentage)",
    )
    sla_uptime_pct: float = Field(
        default=99.0,
        ge=0.0,
        le=100.0,
        description="SLA target for uptime (percentage)",
    )


class DashboardConfig(BaseModel):
    """Streamlit dashboard configuration."""

    port: int = Field(
        default=8501,
        ge=1024,
        le=65535,
        description="Dashboard server port",
    )
    theme: str = Field(
        default="light",
        description="Dashboard theme (light/dark)",
        pattern="^(light|dark)$",
    )
    auto_refresh_seconds: int = Field(
        default=30,
        ge=5,
        le=300,
        description="Auto-refresh interval (seconds)",
    )


class DGASConfig(BaseModel):
    """Root configuration for DGAS system."""

    database: DatabaseConfig = Field(
        ...,
        description="Database configuration",
    )
    scheduler: SchedulerConfig = Field(
        default_factory=SchedulerConfig,
        description="Scheduler configuration",
    )
    prediction: PredictionConfig = Field(
        default_factory=PredictionConfig,
        description="Prediction engine configuration",
    )
    notifications: NotificationConfig = Field(
        default_factory=NotificationConfig,
        description="Notification configuration",
    )
    monitoring: MonitoringConfig = Field(
        default_factory=MonitoringConfig,
        description="Monitoring configuration",
    )
    dashboard: DashboardConfig = Field(
        default_factory=DashboardConfig,
        description="Dashboard configuration",
    )

    model_config = {
        "extra": "forbid",  # Disallow extra fields
        "validate_assignment": True,  # Validate on assignment
    }
