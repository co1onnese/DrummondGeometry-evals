"""
Unit tests for configuration loader.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from dgas.config.loader import ConfigLoader, load_config
from dgas.config.schema import DGASConfig


class TestConfigLoader:
    """Test ConfigLoader class."""

    def test_load_yaml_file(self, tmp_path, monkeypatch):
        """Test loading YAML configuration file."""
        config_file = tmp_path / "config.yaml"
        config_data = {
            "database": {
                "url": "postgresql://localhost/test",
                "pool_size": 10,
            },
            "scheduler": {
                "symbols": ["AAPL", "MSFT"],
            },
        }
        config_file.write_text(yaml.dump(config_data))

        loader = ConfigLoader(config_file)
        config = loader.load()

        assert config.database.url == "postgresql://localhost/test"
        assert config.database.pool_size == 10
        assert config.scheduler.symbols == ["AAPL", "MSFT"]

    def test_load_json_file(self, tmp_path):
        """Test loading JSON configuration file."""
        config_file = tmp_path / "config.json"
        config_data = {
            "database": {
                "url": "postgresql://localhost/test",
            },
        }
        config_file.write_text(json.dumps(config_data))

        loader = ConfigLoader(config_file)
        config = loader.load()

        assert config.database.url == "postgresql://localhost/test"

    def test_env_var_expansion(self, tmp_path, monkeypatch):
        """Test environment variable expansion."""
        monkeypatch.setenv("DB_URL", "postgresql://prod/db")
        monkeypatch.setenv("POOL_SIZE", "15")

        config_file = tmp_path / "config.yaml"
        config_data = {
            "database": {
                "url": "${DB_URL}",
                "pool_size": 15,  # Number, not env var
            },
        }
        config_file.write_text(yaml.dump(config_data))

        loader = ConfigLoader(config_file)
        config = loader.load()

        assert config.database.url == "postgresql://prod/db"

    def test_invalid_yaml(self, tmp_path):
        """Test handling of invalid YAML."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("invalid: yaml: content:")

        loader = ConfigLoader(config_file)
        with pytest.raises(ValueError, match="Invalid YAML"):
            loader.load()

    def test_invalid_json(self, tmp_path):
        """Test handling of invalid JSON."""
        config_file = tmp_path / "config.json"
        config_file.write_text('{"invalid": json,}')

        loader = ConfigLoader(config_file)
        with pytest.raises(ValueError, match="Invalid JSON"):
            loader.load()

    def test_validation_error(self, tmp_path):
        """Test handling of validation errors."""
        config_file = tmp_path / "config.yaml"
        config_data = {
            "database": {
                "url": "postgresql://localhost/db",
                "pool_size": 100,  # Too large
            },
        }
        config_file.write_text(yaml.dump(config_data))

        loader = ConfigLoader(config_file)
        with pytest.raises(ValidationError):
            loader.load()

    def test_find_config_file(self, tmp_path, monkeypatch):
        """Test finding configuration file in default paths."""
        # Change to temp directory
        monkeypatch.chdir(tmp_path)

        # Create config in current directory
        config_file = tmp_path / "dgas.yaml"
        config_data = {"database": {"url": "postgresql://localhost/db"}}
        config_file.write_text(yaml.dump(config_data))

        found = ConfigLoader.find_config_file()
        # Found path may be relative, so compare absolute paths
        assert found.resolve() == config_file.resolve()

    def test_no_config_file_uses_defaults(self, tmp_path, monkeypatch):
        """Test that missing config file uses defaults."""
        monkeypatch.chdir(tmp_path)

        loader = ConfigLoader()
        # Should raise because database.url is required
        with pytest.raises(ValidationError):
            loader.load()

    def test_reload(self, tmp_path):
        """Test reloading configuration."""
        config_file = tmp_path / "config.yaml"
        config_data = {
            "database": {"url": "postgresql://localhost/db1"},
        }
        config_file.write_text(yaml.dump(config_data))

        loader = ConfigLoader(config_file)
        config1 = loader.load()
        assert config1.database.url == "postgresql://localhost/db1"

        # Modify file
        config_data["database"]["url"] = "postgresql://localhost/db2"
        config_file.write_text(yaml.dump(config_data))

        # Reload
        config2 = loader.reload()
        assert config2.database.url == "postgresql://localhost/db2"

    def test_save_yaml(self, tmp_path):
        """Test saving configuration to YAML."""
        config = DGASConfig(database={"url": "postgresql://localhost/db"})

        output_file = tmp_path / "output.yaml"
        loader = ConfigLoader()
        loader.save(config, output_file, format="yaml")

        assert output_file.exists()

        # Load and verify
        with open(output_file) as f:
            data = yaml.safe_load(f)

        assert data["database"]["url"] == "postgresql://localhost/db"

    def test_save_json(self, tmp_path):
        """Test saving configuration to JSON."""
        config = DGASConfig(database={"url": "postgresql://localhost/db"})

        output_file = tmp_path / "output.json"
        loader = ConfigLoader()
        loader.save(config, output_file, format="json")

        assert output_file.exists()

        # Load and verify
        with open(output_file) as f:
            data = json.load(f)

        assert data["database"]["url"] == "postgresql://localhost/db"

    def test_generate_sample_minimal(self, tmp_path):
        """Test generating minimal sample config."""
        output_file = tmp_path / "sample.yaml"
        ConfigLoader.generate_sample_config(output_file, template="minimal")

        assert output_file.exists()

        with open(output_file) as f:
            content = f.read()

        assert "DATABASE_URL" in content
        assert "# DGAS Configuration File" in content

    def test_generate_sample_standard(self, tmp_path):
        """Test generating standard sample config."""
        output_file = tmp_path / "sample.yaml"
        ConfigLoader.generate_sample_config(output_file, template="standard")

        assert output_file.exists()

        with open(output_file) as f:
            data = yaml.safe_load(f)

        assert "database" in data
        assert "scheduler" in data
        assert "notifications" in data

    def test_generate_sample_advanced(self, tmp_path):
        """Test generating advanced sample config."""
        output_file = tmp_path / "sample.yaml"
        ConfigLoader.generate_sample_config(output_file, template="advanced")

        assert output_file.exists()

        with open(output_file) as f:
            data = yaml.safe_load(f)

        # Should have all sections
        assert "database" in data
        assert "scheduler" in data
        assert "prediction" in data
        assert "notifications" in data
        assert "monitoring" in data
        assert "dashboard" in data

    def test_generate_sample_invalid_template(self, tmp_path):
        """Test invalid template raises error."""
        output_file = tmp_path / "sample.yaml"
        with pytest.raises(ValueError, match="Unknown template"):
            ConfigLoader.generate_sample_config(output_file, template="invalid")


class TestLoadConfigConvenience:
    """Test load_config convenience function."""

    def test_load_config(self, tmp_path):
        """Test load_config convenience function."""
        config_file = tmp_path / "config.yaml"
        config_data = {"database": {"url": "postgresql://localhost/db"}}
        config_file.write_text(yaml.dump(config_data))

        config = load_config(config_file)

        assert isinstance(config, DGASConfig)
        assert config.database.url == "postgresql://localhost/db"
