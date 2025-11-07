"""
Configuration file loader with environment variable expansion.

Provides loading, validation, and merging of configuration from multiple sources.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from pydantic import ValidationError

from .schema import DGASConfig
from .validators import expand_env_vars_in_dict, validate_config_file

logger = logging.getLogger(__name__)


class ConfigLoader:
    """
    Load and merge configuration from multiple sources.

    Configuration sources are merged in order of precedence:
    1. CLI arguments (highest priority)
    2. Environment variables
    3. User config file (~/.config/dgas/config.yaml)
    4. System config file (/etc/dgas/config.yaml)
    5. Default values (lowest priority)
    """

    DEFAULT_CONFIG_PATHS = [
        Path("/etc/dgas/config.yaml"),  # System-wide
        Path.home() / ".config" / "dgas" / "config.yaml",  # User
        Path("./dgas.yaml"),  # Current directory
        Path("./dgas.yml"),  # Alternative extension
    ]

    def __init__(self, config_path: Optional[Path] = None):
        """
        Initialize ConfigLoader.

        Args:
            config_path: Explicit path to config file. If None, searches default paths.
        """
        self.config_path = config_path
        self._loaded_config: Optional[DGASConfig] = None

    @classmethod
    def find_config_file(cls) -> Optional[Path]:
        """
        Find the first available configuration file in default paths.

        Returns:
            Path to config file, or None if not found
        """
        for path in cls.DEFAULT_CONFIG_PATHS:
            if path.exists() and path.is_file():
                logger.info(f"Found config file: {path}")
                return path

        logger.debug("No config file found in default paths")
        return None

    def load_file(self, path: Path) -> Dict[str, Any]:
        """
        Load configuration from file.

        Supports YAML and JSON formats. Performs environment variable expansion.

        Args:
            path: Path to configuration file

        Returns:
            Configuration dictionary with env vars expanded

        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If file format is invalid
        """
        validate_config_file(path)

        logger.info(f"Loading configuration from: {path}")

        # Read file content
        with open(path, "r") as f:
            content = f.read()

        # Parse based on extension
        if path.suffix.lower() in [".yaml", ".yml"]:
            try:
                data = yaml.safe_load(content)
            except yaml.YAMLError as e:
                raise ValueError(f"Invalid YAML in {path}: {e}")
        elif path.suffix.lower() == ".json":
            try:
                data = json.loads(content)
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON in {path}: {e}")
        else:
            raise ValueError(f"Unsupported config file format: {path.suffix}")

        if data is None:
            data = {}

        if not isinstance(data, dict):
            raise ValueError(f"Config file must contain a mapping, got {type(data)}")

        # Expand environment variables
        data = expand_env_vars_in_dict(data)

        return data

    def load(self) -> DGASConfig:
        """
        Load and validate configuration.

        Searches for config file if not explicitly provided.
        Merges configuration from file with environment variables.

        Returns:
            Validated configuration object

        Raises:
            ValidationError: If configuration is invalid
            FileNotFoundError: If explicit config path doesn't exist
        """
        if self._loaded_config is not None:
            return self._loaded_config

        # Determine config file path
        if self.config_path:
            config_file = self.config_path
        else:
            config_file = self.find_config_file()

        # Load configuration data
        if config_file:
            try:
                config_data = self.load_file(config_file)
            except Exception as e:
                logger.error(f"Failed to load config from {config_file}: {e}")
                raise
        else:
            logger.info("No config file found, using defaults")
            config_data = {}

        # Validate and create configuration object
        try:
            self._loaded_config = DGASConfig(**config_data)
            logger.info("Configuration loaded and validated successfully")
            return self._loaded_config
        except ValidationError as e:
            logger.error(f"Configuration validation failed: {e}")
            raise

    def reload(self) -> DGASConfig:
        """
        Reload configuration from file.

        Returns:
            Freshly loaded configuration object
        """
        self._loaded_config = None
        return self.load()

    def save(self, config: DGASConfig, path: Path, format: str = "yaml") -> None:
        """
        Save configuration to file.

        Args:
            config: Configuration object to save
            path: Path to save configuration
            format: Output format ('yaml' or 'json')

        Raises:
            ValueError: If format is not supported
        """
        # Convert config to dict
        config_dict = config.model_dump(exclude_none=True)

        # Create parent directory if needed
        path.parent.mkdir(parents=True, exist_ok=True)

        # Write file
        with open(path, "w") as f:
            if format == "yaml":
                yaml.dump(
                    config_dict,
                    f,
                    default_flow_style=False,
                    sort_keys=False,
                )
            elif format == "json":
                json.dump(config_dict, f, indent=2)
            else:
                raise ValueError(f"Unsupported format: {format}")

        logger.info(f"Configuration saved to: {path}")

    @classmethod
    def generate_sample_config(
        cls,
        path: Path,
        template: str = "standard",
    ) -> None:
        """
        Generate a sample configuration file.

        Args:
            path: Path to save sample config
            template: Template type ('minimal', 'standard', 'advanced')

        Raises:
            ValueError: If template is not recognized
        """
        if template == "minimal":
            config_dict = {
                "database": {
                    "url": "${DATABASE_URL}",
                },
            }
        elif template == "standard":
            config_dict = {
                "database": {
                    "url": "${DATABASE_URL}",
                    "pool_size": 5,
                },
                "scheduler": {
                    "symbols": ["AAPL", "MSFT", "GOOGL"],
                    "cron_expression": "0 9,15 * * 1-5",
                    "timezone": "America/New_York",
                    "market_hours_only": True,
                },
                "notifications": {
                    "discord": {
                        "enabled": True,
                        "webhook_url": "${DISCORD_WEBHOOK_URL}",
                    },
                    "console": {
                        "enabled": True,
                    },
                },
            }
        elif template == "advanced":
            # Create full config with all options
            config = DGASConfig(
                database={"url": "${DATABASE_URL}"},
            )
            config_dict = config.model_dump(exclude_none=False)
        else:
            raise ValueError(f"Unknown template: {template}")

        # Add comments for YAML
        if path.suffix.lower() in [".yaml", ".yml"]:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w") as f:
                f.write("# DGAS Configuration File\n")
                f.write(f"# Template: {template}\n")
                f.write("# \n")
                f.write("# Environment variables:\n")
                f.write("#   DATABASE_URL - PostgreSQL connection URL\n")
                f.write("#   DISCORD_WEBHOOK_URL - Discord webhook for notifications\n")
                f.write("\n")
                yaml.dump(
                    config_dict,
                    f,
                    default_flow_style=False,
                    sort_keys=False,
                )
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w") as f:
                json.dump(config_dict, f, indent=2)

        logger.info(f"Sample configuration generated: {path}")


def load_config(config_path: Optional[Path] = None) -> DGASConfig:
    """
    Convenience function to load configuration.

    Args:
        config_path: Optional explicit path to config file

    Returns:
        Loaded and validated configuration

    Examples:
        >>> config = load_config()
        >>> config = load_config(Path("custom-config.yaml"))
    """
    loader = ConfigLoader(config_path)
    return loader.load()
