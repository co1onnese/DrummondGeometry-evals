"""
Settings adapter for bridging DGASConfig and legacy Settings.

Provides unified interface for loading configuration from:
1. Config files (YAML/JSON) via DGASConfig
2. Environment variables via Settings
3. Command line arguments (highest priority)

Precedence (highest to lowest):
1. Command line arguments
2. Config file settings
3. Environment variables
4. Default values
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from dgas.config.loader import ConfigLoader
from dgas.config.schema import DGASConfig
from dgas.settings import Settings

logger = logging.getLogger(__name__)


class UnifiedSettings:
    """
    Unified settings interface combining DGASConfig and legacy Settings.

    This adapter allows CLI commands to work with both the new config file
    system and the legacy environment variable system seamlessly.
    """

    def __init__(
        self,
        config_file: Optional[Path] = None,
        config_overrides: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize unified settings.

        Args:
            config_file: Path to configuration file (YAML/JSON). If None, will auto-detect.
            config_overrides: Dictionary of command-line overrides to apply
        """
        self._config_file = config_file
        self._config_overrides = config_overrides or {}
        self._dgas_config: Optional[DGASConfig] = None

        # Initialize legacy settings (may fail if extra env vars present)
        try:
            self._settings: Settings = Settings()
        except Exception as e:
            logger.warning(f"Could not initialize Settings from environment: {e}")
            # Create minimal settings
            self._settings = None  # type: ignore

        # Try to load config file
        self._load_config()

    def _load_config(self) -> None:
        """Load configuration file if available."""
        try:
            loader = ConfigLoader(self._config_file)

            # Check if config file exists
            config_path = self._config_file or ConfigLoader.find_config_file()

            if config_path:
                self._dgas_config = loader.load()
                logger.info(f"Loaded configuration from {config_path}")
            else:
                logger.debug("No configuration file found, using environment variables only")

        except Exception as e:
            logger.warning(f"Could not load configuration file: {e}")
            logger.debug("Falling back to environment variables only")

    @property
    def has_config_file(self) -> bool:
        """Check if a config file was successfully loaded."""
        return self._dgas_config is not None

    # Database properties
    @property
    def database_url(self) -> str:
        """Get database URL from config or environment."""
        if self._dgas_config:
            return self._dgas_config.database.url
        if self._settings:
            return self._settings.database_url
        return "postgresql://localhost/dgas"  # Default

    @property
    def database_pool_size(self) -> int:
        """Get database connection pool size."""
        if self._dgas_config:
            return self._dgas_config.database.pool_size
        return 5  # Default

    @property
    def database_echo(self) -> bool:
        """Get database echo setting."""
        if self._dgas_config:
            return self._dgas_config.database.echo
        return False

    # Scheduler properties
    @property
    def scheduler_symbols(self) -> List[str]:
        """Get symbols to track from scheduler config."""
        # Check for override
        if "symbols" in self._config_overrides:
            return self._config_overrides["symbols"]

        if self._dgas_config:
            return self._dgas_config.scheduler.symbols
        return []

    @property
    def scheduler_cron(self) -> str:
        """Get scheduler cron expression."""
        if self._dgas_config:
            return self._dgas_config.scheduler.cron_expression
        return "0 9,15 * * 1-5"  # Default: 9am and 3pm weekdays

    @property
    def scheduler_timezone(self) -> str:
        """Get scheduler timezone."""
        if self._dgas_config:
            return self._dgas_config.scheduler.timezone
        return "America/New_York"

    @property
    def scheduler_market_hours_only(self) -> bool:
        """Get market hours only setting."""
        if self._dgas_config:
            return self._dgas_config.scheduler.market_hours_only
        return True

    # Prediction properties
    @property
    def prediction_min_confidence(self) -> float:
        """Get minimum confidence threshold."""
        # Check for override
        if "min_confidence" in self._config_overrides:
            return self._config_overrides["min_confidence"]

        if self._dgas_config:
            return self._dgas_config.prediction.min_confidence
        return 0.6

    @property
    def prediction_min_signal_strength(self) -> float:
        """Get minimum signal strength threshold."""
        if self._dgas_config:
            return self._dgas_config.prediction.min_signal_strength
        return 0.5

    @property
    def prediction_stop_loss_atr_multiplier(self) -> float:
        """Get stop loss ATR multiplier."""
        if self._dgas_config:
            return self._dgas_config.prediction.stop_loss_atr_multiplier
        return 1.5

    @property
    def prediction_target_atr_multiplier(self) -> float:
        """Get target ATR multiplier."""
        if self._dgas_config:
            return self._dgas_config.prediction.target_atr_multiplier
        return 2.5

    # Notification properties
    @property
    def notifications_discord_enabled(self) -> bool:
        """Check if Discord notifications are enabled."""
        if self._dgas_config and self._dgas_config.notifications.discord:
            return self._dgas_config.notifications.discord.enabled
        return False

    @property
    def notifications_discord_webhook_url(self) -> Optional[str]:
        """Get Discord webhook URL."""
        if self._dgas_config and self._dgas_config.notifications.discord:
            return self._dgas_config.notifications.discord.webhook_url
        return None

    @property
    def notifications_console_enabled(self) -> bool:
        """Check if console notifications are enabled."""
        if self._dgas_config and self._dgas_config.notifications.console:
            return self._dgas_config.notifications.console.enabled
        return True  # Default to enabled

    # Monitoring properties
    @property
    def monitoring_sla_p95_latency_ms(self) -> int:
        """Get SLA P95 latency threshold."""
        if self._dgas_config:
            return self._dgas_config.monitoring.sla_p95_latency_ms
        return 60000

    @property
    def monitoring_sla_error_rate_pct(self) -> float:
        """Get SLA error rate percentage."""
        if self._dgas_config:
            return self._dgas_config.monitoring.sla_error_rate_pct
        return 1.0

    @property
    def monitoring_sla_uptime_pct(self) -> float:
        """Get SLA uptime percentage."""
        if self._dgas_config:
            return self._dgas_config.monitoring.sla_uptime_pct
        return 99.0

    # Dashboard properties
    @property
    def dashboard_port(self) -> int:
        """Get dashboard port."""
        if self._dgas_config:
            return self._dgas_config.dashboard.port
        return 8501

    @property
    def dashboard_theme(self) -> str:
        """Get dashboard theme."""
        if self._dgas_config:
            return self._dgas_config.dashboard.theme
        return "light"

    @property
    def dashboard_auto_refresh_seconds(self) -> int:
        """Get dashboard auto-refresh interval."""
        if self._dgas_config:
            return self._dgas_config.dashboard.auto_refresh_seconds
        return 30

    # Legacy Settings pass-through
    @property
    def eodhd_api_token(self) -> Optional[str]:
        """Get EODHD API token (from environment)."""
        if self._settings:
            return self._settings.eodhd_api_token
        return None

    @property
    def data_dir(self) -> Path:
        """Get data directory path."""
        if self._settings:
            return self._settings.data_dir
        return Path("./data")  # Default

    @property
    def eodhd_requests_per_minute(self) -> int:
        """Get EODHD rate limit."""
        if self._settings:
            return self._settings.eodhd_requests_per_minute
        return 80  # Default

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert settings to dictionary format.

        Returns:
            Dictionary containing all settings
        """
        return {
            "database": {
                "url": self.database_url,
                "pool_size": self.database_pool_size,
                "echo": self.database_echo,
            },
            "scheduler": {
                "symbols": self.scheduler_symbols,
                "cron_expression": self.scheduler_cron,
                "timezone": self.scheduler_timezone,
                "market_hours_only": self.scheduler_market_hours_only,
            },
            "prediction": {
                "min_confidence": self.prediction_min_confidence,
                "min_signal_strength": self.prediction_min_signal_strength,
                "stop_loss_atr_multiplier": self.prediction_stop_loss_atr_multiplier,
                "target_atr_multiplier": self.prediction_target_atr_multiplier,
            },
            "notifications": {
                "discord": {
                    "enabled": self.notifications_discord_enabled,
                    "webhook_url": self.notifications_discord_webhook_url,
                },
                "console": {
                    "enabled": self.notifications_console_enabled,
                },
            },
            "monitoring": {
                "sla_p95_latency_ms": self.monitoring_sla_p95_latency_ms,
                "sla_error_rate_pct": self.monitoring_sla_error_rate_pct,
                "sla_uptime_pct": self.monitoring_sla_uptime_pct,
            },
            "dashboard": {
                "port": self.dashboard_port,
                "theme": self.dashboard_theme,
                "auto_refresh_seconds": self.dashboard_auto_refresh_seconds,
            },
            "eodhd_api_token": self.eodhd_api_token,
            "data_dir": str(self.data_dir),
            "eodhd_requests_per_minute": self.eodhd_requests_per_minute,
        }


def load_settings(
    config_file: Optional[Path] = None,
    **overrides: Any,
) -> UnifiedSettings:
    """
    Convenience function to load unified settings.

    Args:
        config_file: Optional path to configuration file
        **overrides: Keyword arguments for command-line overrides

    Returns:
        UnifiedSettings instance

    Example:
        >>> settings = load_settings(config_file=Path("dgas.yaml"), min_confidence=0.7)
        >>> print(settings.prediction_min_confidence)  # 0.7 (from override)
    """
    return UnifiedSettings(config_file=config_file, config_overrides=overrides)
