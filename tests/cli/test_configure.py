"""
Unit tests for configure CLI command.
"""

from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from dgas.cli.configure import (
    _edit_command,
    _init_command,
    _sample_command,
    _show_command,
    _validate_command,
    _wizard_advanced,
    _wizard_minimal,
    _wizard_standard,
    setup_configure_parser,
)


class TestSetupConfigureParser:
    """Test configure parser setup."""

    def test_parser_creation(self):
        """Test that configure parser is created correctly."""
        from argparse import ArgumentParser

        parser = ArgumentParser()
        subparsers = parser.add_subparsers()

        configure_parser = setup_configure_parser(subparsers)

        assert configure_parser is not None
        assert configure_parser.prog.endswith("configure")

    def test_init_subcommand(self):
        """Test init subcommand parser."""
        from argparse import ArgumentParser

        parser = ArgumentParser()
        subparsers = parser.add_subparsers()
        setup_configure_parser(subparsers)

        # Parse init command
        args = parser.parse_args(["configure", "init"])
        assert args.configure_command == "init"
        assert args.template == "standard"
        assert not args.force

    def test_show_subcommand(self):
        """Test show subcommand parser."""
        from argparse import ArgumentParser

        parser = ArgumentParser()
        subparsers = parser.add_subparsers()
        setup_configure_parser(subparsers)

        # Parse show command
        args = parser.parse_args(["configure", "show"])
        assert args.configure_command == "show"
        assert args.format == "yaml"

    def test_validate_subcommand(self):
        """Test validate subcommand parser."""
        from argparse import ArgumentParser

        parser = ArgumentParser()
        subparsers = parser.add_subparsers()
        setup_configure_parser(subparsers)

        # Parse validate command
        args = parser.parse_args(["configure", "validate"])
        assert args.configure_command == "validate"

    def test_sample_subcommand(self):
        """Test sample subcommand parser."""
        from argparse import ArgumentParser

        parser = ArgumentParser()
        subparsers = parser.add_subparsers()
        setup_configure_parser(subparsers)

        # Parse sample command
        args = parser.parse_args(["configure", "sample"])
        assert args.configure_command == "sample"
        assert args.template == "standard"

    def test_edit_subcommand(self):
        """Test edit subcommand parser."""
        from argparse import ArgumentParser

        parser = ArgumentParser()
        subparsers = parser.add_subparsers()
        setup_configure_parser(subparsers)

        # Parse edit command
        args = parser.parse_args(["configure", "edit"])
        assert args.configure_command == "edit"


class TestInitCommand:
    """Test init command implementation."""

    @patch("dgas.cli.configure.Console")
    @patch("dgas.cli.configure.Confirm.ask")
    @patch("dgas.cli.configure._wizard_standard")
    def test_init_creates_config(self, mock_wizard, mock_confirm, mock_console, tmp_path):
        """Test that init creates configuration file."""
        output_file = tmp_path / "config.yaml"

        # Mock wizard to return valid config
        mock_wizard.return_value = {
            "database": {"url": "postgresql://localhost/db"},
        }

        args = Namespace(
            output=output_file,
            template="standard",
            force=False,
        )

        result = _init_command(args)

        assert result == 0
        assert output_file.exists()

        # Verify config content
        with open(output_file) as f:
            data = yaml.safe_load(f)
        assert data["database"]["url"] == "postgresql://localhost/db"

    @patch("dgas.cli.configure.Console")
    @patch("dgas.cli.configure.Confirm.ask")
    def test_init_prompts_on_existing_file(self, mock_confirm, mock_console, tmp_path):
        """Test that init prompts when config file exists."""
        output_file = tmp_path / "config.yaml"
        output_file.write_text("existing: config\n")

        mock_confirm.return_value = False  # User says no

        args = Namespace(
            output=output_file,
            template="standard",
            force=False,
        )

        result = _init_command(args)

        assert result == 0
        # Original file should be unchanged
        assert output_file.read_text() == "existing: config\n"

    @patch("dgas.cli.configure.Console")
    @patch("dgas.cli.configure._wizard_minimal")
    def test_init_minimal_template(self, mock_wizard, mock_console, tmp_path):
        """Test init with minimal template."""
        output_file = tmp_path / "config.yaml"

        mock_wizard.return_value = {
            "database": {"url": "postgresql://localhost/db"},
        }

        args = Namespace(
            output=output_file,
            template="minimal",
            force=False,
        )

        result = _init_command(args)

        assert result == 0
        mock_wizard.assert_called_once()

    @patch("dgas.cli.configure.Console")
    @patch("dgas.cli.configure._wizard_advanced")
    def test_init_advanced_template(self, mock_wizard, mock_console, tmp_path):
        """Test init with advanced template."""
        output_file = tmp_path / "config.yaml"

        mock_wizard.return_value = {
            "database": {"url": "postgresql://localhost/db"},
            "scheduler": {"symbols": ["AAPL"]},
            "prediction": {"min_confidence": 0.7},
        }

        args = Namespace(
            output=output_file,
            template="advanced",
            force=False,
        )

        result = _init_command(args)

        assert result == 0
        mock_wizard.assert_called_once()

    @patch("dgas.cli.configure.Console")
    @patch("dgas.cli.configure._wizard_standard")
    def test_init_validation_error(self, mock_wizard, mock_console, tmp_path):
        """Test that init handles validation errors."""
        output_file = tmp_path / "config.yaml"

        # Mock wizard to return invalid config (missing required field)
        mock_wizard.return_value = {}

        args = Namespace(
            output=output_file,
            template="standard",
            force=False,
        )

        result = _init_command(args)

        assert result == 1  # Error exit code
        # File should not be created
        assert not output_file.exists()


class TestShowCommand:
    """Test show command implementation."""

    @patch("dgas.cli.configure.Console")
    def test_show_yaml_format(self, mock_console, tmp_path):
        """Test show command with YAML format."""
        config_file = tmp_path / "config.yaml"
        config_data = {"database": {"url": "postgresql://localhost/db"}}
        config_file.write_text(yaml.dump(config_data))

        args = Namespace(
            config=config_file,
            format="yaml",
        )

        result = _show_command(args)

        assert result == 0

    @patch("dgas.cli.configure.Console")
    def test_show_json_format(self, mock_console, tmp_path):
        """Test show command with JSON format."""
        config_file = tmp_path / "config.yaml"
        config_data = {"database": {"url": "postgresql://localhost/db"}}
        config_file.write_text(yaml.dump(config_data))

        args = Namespace(
            config=config_file,
            format="json",
        )

        result = _show_command(args)

        assert result == 0

    @patch("dgas.cli.configure.Console")
    def test_show_missing_config(self, mock_console, tmp_path, monkeypatch):
        """Test show command with missing config file."""
        monkeypatch.chdir(tmp_path)

        args = Namespace(
            config=None,
            format="yaml",
        )

        # Should return error since no config file exists
        result = _show_command(args)

        assert result == 1


class TestValidateCommand:
    """Test validate command implementation."""

    @patch("dgas.cli.configure.Console")
    def test_validate_valid_config(self, mock_console, tmp_path):
        """Test validate command with valid config."""
        config_file = tmp_path / "config.yaml"
        config_data = {
            "database": {"url": "postgresql://localhost/db"},
            "scheduler": {"symbols": ["AAPL"]},
        }
        config_file.write_text(yaml.dump(config_data))

        args = Namespace(
            config_file=config_file,
        )

        result = _validate_command(args)

        assert result == 0

    @patch("dgas.cli.configure.Console")
    def test_validate_invalid_config(self, mock_console, tmp_path):
        """Test validate command with invalid config."""
        config_file = tmp_path / "config.yaml"
        # Invalid: pool_size too large
        config_data = {
            "database": {
                "url": "postgresql://localhost/db",
                "pool_size": 100,  # Max is 50
            }
        }
        config_file.write_text(yaml.dump(config_data))

        args = Namespace(
            config_file=config_file,
        )

        result = _validate_command(args)

        assert result == 1  # Validation error


class TestSampleCommand:
    """Test sample command implementation."""

    @patch("dgas.cli.configure.Console")
    def test_sample_creates_file(self, mock_console, tmp_path):
        """Test that sample command creates file."""
        output_file = tmp_path / "sample.yaml"

        args = Namespace(
            output=output_file,
            template="standard",
        )

        result = _sample_command(args)

        assert result == 0
        assert output_file.exists()

    @patch("dgas.cli.configure.Console")
    @patch("dgas.cli.configure.Confirm.ask")
    def test_sample_prompts_on_existing_file(self, mock_confirm, mock_console, tmp_path):
        """Test that sample prompts when file exists."""
        output_file = tmp_path / "sample.yaml"
        output_file.write_text("existing\n")

        mock_confirm.return_value = False  # User says no

        args = Namespace(
            output=output_file,
            template="standard",
        )

        result = _sample_command(args)

        assert result == 0
        # File should remain unchanged
        assert output_file.read_text() == "existing\n"

    @patch("dgas.cli.configure.Console")
    def test_sample_minimal_template(self, mock_console, tmp_path):
        """Test sample with minimal template."""
        output_file = tmp_path / "sample.yaml"

        args = Namespace(
            output=output_file,
            template="minimal",
        )

        result = _sample_command(args)

        assert result == 0
        assert output_file.exists()

        # Check content
        with open(output_file) as f:
            content = f.read()
        assert "DATABASE_URL" in content

    @patch("dgas.cli.configure.Console")
    def test_sample_advanced_template(self, mock_console, tmp_path):
        """Test sample with advanced template."""
        output_file = tmp_path / "sample.yaml"

        args = Namespace(
            output=output_file,
            template="advanced",
        )

        result = _sample_command(args)

        assert result == 0
        assert output_file.exists()

        # Check content has all sections
        with open(output_file) as f:
            data = yaml.safe_load(f)
        assert "database" in data
        assert "scheduler" in data
        assert "prediction" in data
        assert "monitoring" in data
        assert "dashboard" in data


class TestEditCommand:
    """Test edit command implementation."""

    @patch("dgas.cli.configure.Console")
    @patch("subprocess.run")
    def test_edit_opens_editor(self, mock_run, mock_console, tmp_path, monkeypatch):
        """Test that edit opens editor."""
        config_file = tmp_path / "config.yaml"
        config_data = {"database": {"url": "postgresql://localhost/db"}}
        config_file.write_text(yaml.dump(config_data))

        monkeypatch.setenv("EDITOR", "vim")
        mock_run.return_value = MagicMock(returncode=0)

        args = Namespace(
            config=config_file,
        )

        result = _edit_command(args)

        assert result == 0
        mock_run.assert_called_once()
        # Verify vim was called with config file
        call_args = mock_run.call_args[0][0]
        assert call_args[0] == "vim"
        assert str(config_file) in call_args

    @patch("dgas.cli.configure.Console")
    def test_edit_missing_config(self, mock_console, tmp_path, monkeypatch):
        """Test edit with missing config file."""
        monkeypatch.chdir(tmp_path)

        args = Namespace(
            config=None,
        )

        result = _edit_command(args)

        assert result == 1  # No config file found

    @patch("dgas.cli.configure.Console")
    @patch("subprocess.run")
    def test_edit_validation_after_edit(self, mock_run, mock_console, tmp_path):
        """Test that edit validates config after editing."""
        config_file = tmp_path / "config.yaml"
        config_data = {"database": {"url": "postgresql://localhost/db"}}
        config_file.write_text(yaml.dump(config_data))

        mock_run.return_value = MagicMock(returncode=0)

        args = Namespace(
            config=config_file,
        )

        result = _edit_command(args)

        assert result == 0  # Valid config


class TestWizardFunctions:
    """Test wizard helper functions."""

    @patch("dgas.cli.configure.Prompt.ask")
    def test_wizard_minimal(self, mock_prompt):
        """Test minimal wizard."""
        from rich.console import Console

        mock_prompt.return_value = "postgresql://localhost/db"

        console = Console()
        result = _wizard_minimal(console)

        assert "database" in result
        assert result["database"]["url"] == "postgresql://localhost/db"

    @patch("dgas.cli.configure.Prompt.ask")
    @patch("dgas.cli.configure.IntPrompt.ask")
    @patch("dgas.cli.configure.Confirm.ask")
    def test_wizard_standard(self, mock_confirm, mock_int_prompt, mock_prompt):
        """Test standard wizard."""
        from rich.console import Console

        # Mock prompts
        mock_prompt.side_effect = [
            "postgresql://localhost/db",  # db_url
            "AAPL,MSFT",  # symbols
            "0 9 * * 1-5",  # cron
            "America/New_York",  # timezone
            "${DISCORD_WEBHOOK_URL}",  # discord webhook
        ]
        mock_int_prompt.return_value = 5  # pool_size
        mock_confirm.side_effect = [True, True]  # market_hours, discord_enabled

        console = Console()
        result = _wizard_standard(console)

        assert "database" in result
        assert "scheduler" in result
        assert "notifications" in result
        assert result["scheduler"]["symbols"] == ["AAPL", "MSFT"]

    @patch("dgas.cli.configure.Prompt.ask")
    @patch("dgas.cli.configure.IntPrompt.ask")
    @patch("dgas.cli.configure.FloatPrompt.ask")
    @patch("dgas.cli.configure.Confirm.ask")
    @patch("dgas.cli.configure._wizard_standard")
    def test_wizard_advanced(
        self, mock_standard, mock_confirm, mock_float, mock_int, mock_prompt
    ):
        """Test advanced wizard."""
        from rich.console import Console

        # Mock standard wizard
        mock_standard.return_value = {
            "database": {"url": "postgresql://localhost/db"},
            "scheduler": {"symbols": ["AAPL"]},
        }

        # Mock additional prompts
        mock_float.side_effect = [
            0.6,  # min_confidence
            0.5,  # min_signal_strength
            1.5,  # stop_loss_atr
            2.5,  # target_atr
            1.0,  # sla_error_rate
            99.0,  # sla_uptime
        ]
        mock_int.side_effect = [
            60000,  # sla_latency
            8501,  # port
            30,  # refresh
        ]
        mock_prompt.return_value = "light"  # theme

        console = Console()
        result = _wizard_advanced(console)

        assert "database" in result
        assert "prediction" in result
        assert "monitoring" in result
        assert "dashboard" in result
        assert result["prediction"]["min_confidence"] == 0.6
        assert result["dashboard"]["port"] == 8501
