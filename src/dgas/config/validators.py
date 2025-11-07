"""
Configuration validators and utilities.

Provides validation functions and environment variable expansion.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict


def expand_env_vars(value: str) -> str:
    """
    Expand environment variables in a string.

    Supports ${VAR_NAME} and $VAR_NAME syntax.
    Raises KeyError if variable is not found.

    Args:
        value: String potentially containing environment variable references

    Returns:
        String with environment variables expanded

    Raises:
        KeyError: If referenced environment variable is not found

    Examples:
        >>> os.environ['DATABASE_URL'] = 'postgresql://localhost/db'
        >>> expand_env_vars('${DATABASE_URL}')
        'postgresql://localhost/db'
        >>> expand_env_vars('$HOME/config')
        '/home/user/config'
    """
    # Pattern for ${VAR} syntax
    pattern = re.compile(r'\$\{([^}]+)\}')

    def replace_var(match: re.Match) -> str:
        var_name = match.group(1)
        if var_name not in os.environ:
            raise KeyError(f"Environment variable '{var_name}' not found")
        return os.environ[var_name]

    # First expand ${VAR} syntax
    result = pattern.sub(replace_var, value)

    # Then expand $VAR syntax (simple word boundaries)
    pattern = re.compile(r'\$([A-Za-z_][A-Za-z0-9_]*)')

    def replace_simple_var(match: re.Match) -> str:
        var_name = match.group(1)
        if var_name not in os.environ:
            raise KeyError(f"Environment variable '{var_name}' not found")
        return os.environ[var_name]

    result = pattern.sub(replace_simple_var, result)

    return result


def expand_env_vars_in_dict(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Recursively expand environment variables in dictionary values.

    Args:
        data: Dictionary potentially containing env var references

    Returns:
        Dictionary with all env vars expanded

    Examples:
        >>> os.environ['DB_HOST'] = 'localhost'
        >>> expand_env_vars_in_dict({'url': 'postgresql://${DB_HOST}/db'})
        {'url': 'postgresql://localhost/db'}
    """
    result = {}

    for key, value in data.items():
        if isinstance(value, str):
            try:
                result[key] = expand_env_vars(value)
            except KeyError:
                # If env var not found, keep original value
                result[key] = value
        elif isinstance(value, dict):
            result[key] = expand_env_vars_in_dict(value)
        elif isinstance(value, list):
            result[key] = [
                expand_env_vars(item) if isinstance(item, str) else item
                for item in value
            ]
        else:
            result[key] = value

    return result


def validate_config_file(path: Path) -> None:
    """
    Validate that config file exists and is readable.

    Args:
        path: Path to configuration file

    Raises:
        FileNotFoundError: If file doesn't exist
        PermissionError: If file is not readable
        ValueError: If file has invalid extension
    """
    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found: {path}")

    if not path.is_file():
        raise ValueError(f"Path is not a file: {path}")

    if not os.access(path, os.R_OK):
        raise PermissionError(f"Cannot read configuration file: {path}")

    # Check file extension
    valid_extensions = {".yaml", ".yml", ".json"}
    if path.suffix.lower() not in valid_extensions:
        raise ValueError(
            f"Invalid config file extension: {path.suffix}. "
            f"Must be one of: {', '.join(valid_extensions)}"
        )
