"""
Unit tests for configuration validators.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from dgas.config.validators import (
    expand_env_vars,
    expand_env_vars_in_dict,
    validate_config_file,
)


class TestExpandEnvVars:
    """Test expand_env_vars function."""

    def test_expand_braces_syntax(self, monkeypatch):
        """Test ${VAR} syntax expansion."""
        monkeypatch.setenv("TEST_VAR", "test_value")
        result = expand_env_vars("${TEST_VAR}")
        assert result == "test_value"

    def test_expand_dollar_syntax(self, monkeypatch):
        """Test $VAR syntax expansion."""
        monkeypatch.setenv("TEST_VAR", "test_value")
        result = expand_env_vars("$TEST_VAR")
        assert result == "test_value"

    def test_expand_multiple_vars(self, monkeypatch):
        """Test multiple variables in one string."""
        monkeypatch.setenv("HOST", "localhost")
        monkeypatch.setenv("PORT", "5432")
        result = expand_env_vars("postgresql://${HOST}:${PORT}/db")
        assert result == "postgresql://localhost:5432/db"

    def test_expand_mixed_syntax(self, monkeypatch):
        """Test mixing ${VAR} and $VAR syntax."""
        monkeypatch.setenv("HOME", "/home/user")
        monkeypatch.setenv("FILE", "config.yaml")
        result = expand_env_vars("$HOME/${FILE}")
        assert result == "/home/user/config.yaml"

    def test_missing_variable_raises_error(self):
        """Test that missing env var raises KeyError."""
        with pytest.raises(KeyError, match="NONEXISTENT_VAR"):
            expand_env_vars("${NONEXISTENT_VAR}")

    def test_no_expansion_needed(self):
        """Test string without variables."""
        result = expand_env_vars("simple string")
        assert result == "simple string"

    def test_empty_string(self):
        """Test empty string."""
        result = expand_env_vars("")
        assert result == ""


class TestExpandEnvVarsInDict:
    """Test expand_env_vars_in_dict function."""

    def test_expand_string_values(self, monkeypatch):
        """Test expanding variables in string values."""
        monkeypatch.setenv("DB_URL", "postgresql://localhost/db")
        data = {"url": "${DB_URL}"}
        result = expand_env_vars_in_dict(data)
        assert result == {"url": "postgresql://localhost/db"}

    def test_expand_nested_dict(self, monkeypatch):
        """Test expanding variables in nested dictionaries."""
        monkeypatch.setenv("HOST", "localhost")
        monkeypatch.setenv("PORT", "5432")
        data = {
            "database": {
                "host": "${HOST}",
                "port": "${PORT}",
            }
        }
        result = expand_env_vars_in_dict(data)
        assert result == {
            "database": {
                "host": "localhost",
                "port": "5432",
            }
        }

    def test_expand_list_values(self, monkeypatch):
        """Test expanding variables in list values."""
        monkeypatch.setenv("SYMBOL1", "AAPL")
        monkeypatch.setenv("SYMBOL2", "MSFT")
        data = {"symbols": ["${SYMBOL1}", "${SYMBOL2}"]}
        result = expand_env_vars_in_dict(data)
        assert result == {"symbols": ["AAPL", "MSFT"]}

    def test_preserve_non_string_values(self):
        """Test that non-string values are preserved."""
        data = {
            "string": "value",
            "number": 42,
            "boolean": True,
            "null": None,
            "list": [1, 2, 3],
        }
        result = expand_env_vars_in_dict(data)
        assert result == data

    def test_missing_var_keeps_original(self):
        """Test that missing variables keep original value."""
        data = {"url": "${NONEXISTENT}"}
        result = expand_env_vars_in_dict(data)
        assert result == {"url": "${NONEXISTENT}"}


class TestValidateConfigFile:
    """Test validate_config_file function."""

    def test_valid_yaml_file(self, tmp_path):
        """Test validation of valid YAML file."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("key: value\n")

        # Should not raise
        validate_config_file(config_file)

    def test_valid_json_file(self, tmp_path):
        """Test validation of valid JSON file."""
        config_file = tmp_path / "config.json"
        config_file.write_text('{"key": "value"}')

        # Should not raise
        validate_config_file(config_file)

    def test_nonexistent_file(self, tmp_path):
        """Test that missing file raises FileNotFoundError."""
        config_file = tmp_path / "nonexistent.yaml"

        with pytest.raises(FileNotFoundError, match="not found"):
            validate_config_file(config_file)

    def test_directory_not_file(self, tmp_path):
        """Test that directory raises ValueError."""
        with pytest.raises(ValueError, match="not a file"):
            validate_config_file(tmp_path)

    def test_invalid_extension(self, tmp_path):
        """Test that invalid extension raises ValueError."""
        config_file = tmp_path / "config.txt"
        config_file.write_text("data")

        with pytest.raises(ValueError, match="Invalid config file extension"):
            validate_config_file(config_file)

    def test_unreadable_file(self, tmp_path):
        """Test that unreadable file raises PermissionError."""
        import os
        import sys

        # Skip test if running as root (root can read everything)
        if os.geteuid() == 0:
            pytest.skip("Cannot test permission errors as root")

        config_file = tmp_path / "config.yaml"
        config_file.write_text("key: value\n")
        config_file.chmod(0o000)

        try:
            with pytest.raises(PermissionError, match="Cannot read"):
                validate_config_file(config_file)
        finally:
            # Restore permissions for cleanup
            config_file.chmod(0o644)
