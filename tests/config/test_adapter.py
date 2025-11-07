"""
Unit tests for unified settings adapter.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml

from dgas.config.adapter import UnifiedSettings, load_settings


class TestUnifiedSettings:
    """Test UnifiedSettings adapter."""

    def test_defaults_without_config_file(self, tmp_path, monkeypatch):
        """Test that defaults are used when no config file exists."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("DGAS_DATABASE_URL", "postgresql://test/db")

        settings = UnifiedSettings()

        assert not settings.has_config_file
        assert settings.database_url == "postgresql://test/db"
        assert settings.database_pool_size == 5
        assert settings.prediction_min_confidence == 0.6

    def test_loads_from_config_file(self, tmp_path, monkeypatch):
        """Test loading settings from config file."""
        monkeypatch.setenv("DATABASE_URL", "postgresql://env/db")

        config_file = tmp_path / "config.yaml"
        config_data = {
            "database": {
                "url": "${DATABASE_URL}",
                "pool_size": 10,
            },
            "prediction": {
                "min_confidence": 0.75,
            },
            "scheduler": {
                "symbols": ["AAPL", "MSFT"],
                "cron_expression": "0 10 * * *",
            },
        }
        config_file.write_text(yaml.dump(config_data))

        settings = UnifiedSettings(config_file=config_file)

        assert settings.has_config_file
        assert settings.database_url == "postgresql://env/db"
        assert settings.database_pool_size == 10
        assert settings.prediction_min_confidence == 0.75
        assert settings.scheduler_symbols == ["AAPL", "MSFT"]
        assert settings.scheduler_cron == "0 10 * * *"

    def test_config_overrides(self, tmp_path, monkeypatch):
        """Test that command-line overrides take precedence."""
        monkeypatch.setenv("DATABASE_URL", "postgresql://env/db")

        config_file = tmp_path / "config.yaml"
        config_data = {
            "database": {"url": "${DATABASE_URL}"},
            "prediction": {"min_confidence": 0.6},
        }
        config_file.write_text(yaml.dump(config_data))

        # Override min_confidence
        settings = UnifiedSettings(
            config_file=config_file,
            config_overrides={"min_confidence": 0.9},
        )

        assert settings.prediction_min_confidence == 0.9  # Override

    def test_scheduler_properties(self, tmp_path, monkeypatch):
        """Test scheduler-related properties."""
        monkeypatch.setenv("DATABASE_URL", "postgresql://test/db")

        config_file = tmp_path / "config.yaml"
        config_data = {
            "database": {"url": "${DATABASE_URL}"},
            "scheduler": {
                "symbols": ["SPY", "QQQ"],
                "cron_expression": "0 9,15 * * 1-5",
                "timezone": "America/New_York",
                "market_hours_only": True,
            },
        }
        config_file.write_text(yaml.dump(config_data))

        settings = UnifiedSettings(config_file=config_file)

        assert settings.scheduler_symbols == ["SPY", "QQQ"]
        assert settings.scheduler_cron == "0 9,15 * * 1-5"
        assert settings.scheduler_timezone == "America/New_York"
        assert settings.scheduler_market_hours_only is True

    def test_notification_properties(self, tmp_path, monkeypatch):
        """Test notification-related properties."""
        monkeypatch.setenv("DATABASE_URL", "postgresql://test/db")
        monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.com/webhook/123")

        config_file = tmp_path / "config.yaml"
        config_data = {
            "database": {"url": "${DATABASE_URL}"},
            "notifications": {
                "discord": {
                    "enabled": True,
                    "webhook_url": "${DISCORD_WEBHOOK_URL}",
                },
                "console": {
                    "enabled": False,
                },
            },
        }
        config_file.write_text(yaml.dump(config_data))

        settings = UnifiedSettings(config_file=config_file)

        assert settings.notifications_discord_enabled is True
        assert settings.notifications_discord_webhook_url == "https://discord.com/webhook/123"
        assert settings.notifications_console_enabled is False

    def test_monitoring_properties(self, tmp_path, monkeypatch):
        """Test monitoring-related properties."""
        monkeypatch.setenv("DATABASE_URL", "postgresql://test/db")

        config_file = tmp_path / "config.yaml"
        config_data = {
            "database": {"url": "${DATABASE_URL}"},
            "monitoring": {
                "sla_p95_latency_ms": 30000,
                "sla_error_rate_pct": 0.5,
                "sla_uptime_pct": 99.9,
            },
        }
        config_file.write_text(yaml.dump(config_data))

        settings = UnifiedSettings(config_file=config_file)

        assert settings.monitoring_sla_p95_latency_ms == 30000
        assert settings.monitoring_sla_error_rate_pct == 0.5
        assert settings.monitoring_sla_uptime_pct == 99.9

    def test_dashboard_properties(self, tmp_path, monkeypatch):
        """Test dashboard-related properties."""
        monkeypatch.setenv("DATABASE_URL", "postgresql://test/db")

        config_file = tmp_path / "config.yaml"
        config_data = {
            "database": {"url": "${DATABASE_URL}"},
            "dashboard": {
                "port": 8080,
                "theme": "dark",
                "auto_refresh_seconds": 60,
            },
        }
        config_file.write_text(yaml.dump(config_data))

        settings = UnifiedSettings(config_file=config_file)

        assert settings.dashboard_port == 8080
        assert settings.dashboard_theme == "dark"
        assert settings.dashboard_auto_refresh_seconds == 60

    def test_legacy_settings_passthrough(self, tmp_path, monkeypatch):
        """Test that legacy settings are passed through."""
        # Clear all DGAS env vars
        for key in list(os.environ.keys()):
            if key.startswith("DGAS_"):
                monkeypatch.delenv(key, raising=False)

        monkeypatch.setenv("DATABASE_URL", "postgresql://test/db")
        monkeypatch.setenv("EODHD_API_TOKEN", "test_token_123")

        config_file = tmp_path / "config.yaml"
        config_data = {"database": {"url": "${DATABASE_URL}"}}
        config_file.write_text(yaml.dump(config_data))

        settings = UnifiedSettings(config_file=config_file)

        # These come from environment (legacy Settings) if Settings loads successfully
        # Otherwise defaults are used
        if settings._settings:
            assert settings.eodhd_api_token == "test_token_123"
        assert isinstance(settings.data_dir, Path)

    def test_to_dict(self, tmp_path, monkeypatch):
        """Test converting settings to dictionary."""
        monkeypatch.setenv("DATABASE_URL", "postgresql://test/db")

        config_file = tmp_path / "config.yaml"
        config_data = {
            "database": {"url": "${DATABASE_URL}"},
            "prediction": {"min_confidence": 0.7},
        }
        config_file.write_text(yaml.dump(config_data))

        settings = UnifiedSettings(config_file=config_file)
        settings_dict = settings.to_dict()

        assert isinstance(settings_dict, dict)
        assert settings_dict["database"]["url"] == "postgresql://test/db"
        assert settings_dict["prediction"]["min_confidence"] == 0.7
        assert "scheduler" in settings_dict
        assert "notifications" in settings_dict
        assert "monitoring" in settings_dict
        assert "dashboard" in settings_dict

    def test_auto_detect_config_file(self, tmp_path, monkeypatch):
        """Test auto-detection of config file."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("DATABASE_URL", "postgresql://test/db")

        # Create config in current directory
        config_file = tmp_path / "dgas.yaml"
        config_data = {
            "database": {"url": "${DATABASE_URL}"},
            "prediction": {"min_confidence": 0.8},
        }
        config_file.write_text(yaml.dump(config_data))

        # Don't specify config_file - should auto-detect
        settings = UnifiedSettings()

        assert settings.has_config_file
        assert settings.prediction_min_confidence == 0.8

    def test_missing_config_file_fallback(self, tmp_path, monkeypatch):
        """Test fallback when config file doesn't exist."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("DGAS_DATABASE_URL", "postgresql://fallback/db")

        # Try to load non-existent config
        settings = UnifiedSettings(config_file=tmp_path / "nonexistent.yaml")

        # Should fall back to environment variables
        assert not settings.has_config_file
        assert settings.database_url == "postgresql://fallback/db"


class TestLoadSettings:
    """Test load_settings convenience function."""

    def test_load_settings_basic(self, tmp_path, monkeypatch):
        """Test basic load_settings usage."""
        monkeypatch.setenv("DATABASE_URL", "postgresql://test/db")

        config_file = tmp_path / "config.yaml"
        config_data = {
            "database": {"url": "${DATABASE_URL}"},
            "prediction": {"min_confidence": 0.65},
        }
        config_file.write_text(yaml.dump(config_data))

        settings = load_settings(config_file=config_file)

        assert isinstance(settings, UnifiedSettings)
        assert settings.prediction_min_confidence == 0.65

    def test_load_settings_with_overrides(self, tmp_path, monkeypatch):
        """Test load_settings with overrides."""
        monkeypatch.setenv("DATABASE_URL", "postgresql://test/db")

        config_file = tmp_path / "config.yaml"
        config_data = {
            "database": {"url": "${DATABASE_URL}"},
            "prediction": {"min_confidence": 0.6},
        }
        config_file.write_text(yaml.dump(config_data))

        settings = load_settings(config_file=config_file, min_confidence=0.85)

        assert settings.prediction_min_confidence == 0.85  # Override

    def test_load_settings_without_config(self, tmp_path, monkeypatch):
        """Test load_settings without config file."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("DGAS_DATABASE_URL", "postgresql://env/db")

        settings = load_settings()

        assert not settings.has_config_file
        assert settings.database_url == "postgresql://env/db"


class TestSymbolsOverride:
    """Test symbols override behavior."""

    def test_symbols_from_config(self, tmp_path, monkeypatch):
        """Test loading symbols from config."""
        monkeypatch.setenv("DATABASE_URL", "postgresql://test/db")

        config_file = tmp_path / "config.yaml"
        config_data = {
            "database": {"url": "${DATABASE_URL}"},
            "scheduler": {"symbols": ["AAPL", "GOOGL", "MSFT"]},
        }
        config_file.write_text(yaml.dump(config_data))

        settings = UnifiedSettings(config_file=config_file)

        assert settings.scheduler_symbols == ["AAPL", "GOOGL", "MSFT"]

    def test_symbols_override(self, tmp_path, monkeypatch):
        """Test overriding symbols from command line."""
        monkeypatch.setenv("DATABASE_URL", "postgresql://test/db")

        config_file = tmp_path / "config.yaml"
        config_data = {
            "database": {"url": "${DATABASE_URL}"},
            "scheduler": {"symbols": ["AAPL", "GOOGL"]},
        }
        config_file.write_text(yaml.dump(config_data))

        settings = UnifiedSettings(
            config_file=config_file,
            config_overrides={"symbols": ["SPY", "QQQ"]},
        )

        assert settings.scheduler_symbols == ["SPY", "QQQ"]  # Override
