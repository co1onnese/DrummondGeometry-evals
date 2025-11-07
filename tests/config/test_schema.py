"""
Unit tests for configuration schemas.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from dgas.config.schema import (
    DGASConfig,
    DatabaseConfig,
    DashboardConfig,
    MonitoringConfig,
    NotificationConfig,
    PredictionConfig,
    SchedulerConfig,
)


class TestDatabaseConfig:
    """Test DatabaseConfig schema."""

    def test_valid_config(self):
        """Test valid database configuration."""
        config = DatabaseConfig(url="postgresql://localhost/db")
        assert config.url == "postgresql://localhost/db"
        assert config.pool_size == 5
        assert config.echo is False

    def test_custom_pool_size(self):
        """Test custom pool size."""
        config = DatabaseConfig(
            url="postgresql://localhost/db",
            pool_size=10,
        )
        assert config.pool_size == 10

    def test_pool_size_validation(self):
        """Test pool size validation."""
        with pytest.raises(ValidationError):
            DatabaseConfig(url="postgresql://localhost/db", pool_size=0)

        with pytest.raises(ValidationError):
            DatabaseConfig(url="postgresql://localhost/db", pool_size=100)

    def test_missing_url(self):
        """Test that URL is required."""
        with pytest.raises(ValidationError):
            DatabaseConfig()


class TestSchedulerConfig:
    """Test SchedulerConfig schema."""

    def test_valid_config(self):
        """Test valid scheduler configuration."""
        config = SchedulerConfig()
        assert config.symbols == ["AAPL", "MSFT", "GOOGL"]
        assert config.cron_expression == "0 9,15 * * 1-5"
        assert config.timezone == "America/New_York"
        assert config.market_hours_only is True

    def test_custom_symbols(self):
        """Test custom symbols list."""
        config = SchedulerConfig(symbols=["TSLA", "NVDA"])
        assert config.symbols == ["TSLA", "NVDA"]

    def test_symbols_uppercase(self):
        """Test that symbols are converted to uppercase."""
        config = SchedulerConfig(symbols=["aapl", "msft"])
        assert config.symbols == ["AAPL", "MSFT"]

    def test_symbols_stripped(self):
        """Test that symbols are stripped of whitespace."""
        config = SchedulerConfig(symbols=[" AAPL ", "MSFT  "])
        assert config.symbols == ["AAPL", "MSFT"]

    def test_empty_symbols_filtered(self):
        """Test that empty symbols are filtered out."""
        config = SchedulerConfig(symbols=["AAPL", "", "  ", "MSFT"])
        assert config.symbols == ["AAPL", "MSFT"]


class TestPredictionConfig:
    """Test PredictionConfig schema."""

    def test_valid_config(self):
        """Test valid prediction configuration."""
        config = PredictionConfig()
        assert config.min_confidence == 0.6
        assert config.min_signal_strength == 0.5
        assert config.stop_loss_atr_multiplier == 1.5
        assert config.target_atr_multiplier == 2.5

    def test_confidence_validation(self):
        """Test confidence validation (0-1 range)."""
        with pytest.raises(ValidationError):
            PredictionConfig(min_confidence=-0.1)

        with pytest.raises(ValidationError):
            PredictionConfig(min_confidence=1.5)

        # Valid boundaries
        config = PredictionConfig(min_confidence=0.0)
        assert config.min_confidence == 0.0

        config = PredictionConfig(min_confidence=1.0)
        assert config.min_confidence == 1.0

    def test_multiplier_validation(self):
        """Test that multipliers must be positive."""
        with pytest.raises(ValidationError):
            PredictionConfig(stop_loss_atr_multiplier=0.0)

        with pytest.raises(ValidationError):
            PredictionConfig(target_atr_multiplier=-1.0)


class TestMonitoringConfig:
    """Test MonitoringConfig schema."""

    def test_valid_config(self):
        """Test valid monitoring configuration."""
        config = MonitoringConfig()
        assert config.sla_p95_latency_ms == 60000
        assert config.sla_error_rate_pct == 1.0
        assert config.sla_uptime_pct == 99.0

    def test_latency_validation(self):
        """Test latency validation."""
        with pytest.raises(ValidationError):
            MonitoringConfig(sla_p95_latency_ms=500)  # Too low

    def test_percentage_validation(self):
        """Test percentage validation."""
        with pytest.raises(ValidationError):
            MonitoringConfig(sla_error_rate_pct=-1.0)

        with pytest.raises(ValidationError):
            MonitoringConfig(sla_error_rate_pct=150.0)


class TestDashboardConfig:
    """Test DashboardConfig schema."""

    def test_valid_config(self):
        """Test valid dashboard configuration."""
        config = DashboardConfig()
        assert config.port == 8501
        assert config.theme == "light"
        assert config.auto_refresh_seconds == 30

    def test_port_validation(self):
        """Test port validation."""
        with pytest.raises(ValidationError):
            DashboardConfig(port=80)  # Too low

        with pytest.raises(ValidationError):
            DashboardConfig(port=70000)  # Too high

    def test_theme_validation(self):
        """Test theme validation."""
        with pytest.raises(ValidationError):
            DashboardConfig(theme="invalid")

        # Valid themes
        config = DashboardConfig(theme="light")
        assert config.theme == "light"

        config = DashboardConfig(theme="dark")
        assert config.theme == "dark"

    def test_refresh_validation(self):
        """Test refresh interval validation."""
        with pytest.raises(ValidationError):
            DashboardConfig(auto_refresh_seconds=1)  # Too low

        with pytest.raises(ValidationError):
            DashboardConfig(auto_refresh_seconds=500)  # Too high


class TestNotificationConfig:
    """Test NotificationConfig schema."""

    def test_valid_config(self):
        """Test valid notification configuration."""
        config = NotificationConfig()
        assert config.discord is not None
        assert config.console is not None

    def test_custom_discord_config(self):
        """Test custom Discord configuration."""
        config = NotificationConfig(
            discord={"enabled": False, "webhook_url": "https://discord.com/webhook"}
        )
        assert config.discord.enabled is False
        assert config.discord.webhook_url == "https://discord.com/webhook"


class TestDGASConfig:
    """Test root DGASConfig schema."""

    def test_valid_minimal_config(self):
        """Test valid minimal configuration."""
        config = DGASConfig(
            database={"url": "postgresql://localhost/db"}
        )
        assert config.database.url == "postgresql://localhost/db"
        assert config.scheduler is not None
        assert config.prediction is not None

    def test_valid_full_config(self):
        """Test valid full configuration."""
        config = DGASConfig(
            database={
                "url": "postgresql://localhost/db",
                "pool_size": 10,
            },
            scheduler={
                "symbols": ["AAPL", "MSFT"],
                "cron_expression": "0 10 * * 1-5",
            },
            prediction={
                "min_confidence": 0.7,
            },
            notifications={
                "discord": {
                    "enabled": True,
                    "webhook_url": "https://discord.com/webhook",
                },
            },
            monitoring={
                "sla_p95_latency_ms": 45000,
            },
            dashboard={
                "port": 8080,
                "theme": "dark",
            },
        )

        assert config.database.pool_size == 10
        assert config.scheduler.symbols == ["AAPL", "MSFT"]
        assert config.prediction.min_confidence == 0.7
        assert config.notifications.discord.webhook_url == "https://discord.com/webhook"
        assert config.monitoring.sla_p95_latency_ms == 45000
        assert config.dashboard.port == 8080

    def test_extra_fields_forbidden(self):
        """Test that extra fields are not allowed."""
        with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
            DGASConfig(
                database={"url": "postgresql://localhost/db"},
                invalid_field="value",
            )

    def test_missing_database(self):
        """Test that database config is required."""
        with pytest.raises(ValidationError):
            DGASConfig()
