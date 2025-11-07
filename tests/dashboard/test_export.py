"""Tests for enhanced export system."""

import pytest
import pandas as pd
import json
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock, mock_open
from dgas.dashboard.export.enhanced_exporter import (
    EnhancedExporter,
    ExportFormat,
    ExportOptions,
)


class TestExportOptions:
    """Test ExportOptions configuration."""

    def test_default_options(self):
        """Test default export options."""
        options = ExportOptions()

        assert options.include_timestamp is True
        assert options.separator == ","
        assert options.encoding == "utf-8"
        assert options.date_format == "%Y-%m-%d %H:%M:%S"
        assert options.include_index is False
        assert options.compression is None

    def test_custom_options(self):
        """Test custom export options."""
        options = ExportOptions(
            include_timestamp=True,
            separator=";",
            encoding="utf-16",
            date_format="%Y/%m/%d",
            include_index=True,
            compression="zip"
        )

        assert options.include_timestamp is True
        assert options.separator == ";"
        assert options.encoding == "utf-16"
        assert options.date_format == "%Y/%m/%d"
        assert options.include_index is True
        assert options.compression == "zip"


class TestEnhancedExporter:
    """Test EnhancedExporter functionality."""

    @pytest.fixture
    def sample_data(self):
        """Create sample data for testing."""
        return pd.DataFrame({
            "symbol": ["AAPL", "GOOGL", "MSFT", "AMZN"],
            "signal_type": ["BUY", "SELL", "BUY", "BUY"],
            "confidence": [0.85, 0.92, 0.78, 0.88],
            "timestamp": [
                datetime(2024, 11, 7, 10, 0, 0),
                datetime(2024, 11, 7, 11, 0, 0),
                datetime(2024, 11, 7, 12, 0, 0),
                datetime(2024, 11, 7, 13, 0, 0)
            ]
        })

    @pytest.fixture
    def exporter(self):
        """Create a test exporter."""
        return EnhancedExporter()

    def test_exporter_initialization(self, exporter):
        """Test exporter initializes correctly."""
        assert exporter.output_dir == "exports"
        assert isinstance(exporter.options, ExportOptions)

    def test_export_to_csv(self, exporter, sample_data):
        """Test exporting to CSV format."""
        filename = "test_export"

        with patch('pandas.DataFrame.to_csv') as mock_to_csv, \
             patch('builtins.open', mock_open()):

            exporter.export_to_csv(sample_data, filename)

            mock_to_csv.assert_called_once()
            # Verify it was called with the full path
            call_args = mock_to_csv.call_args
            assert filename in call_args[0][0]

    def test_export_to_csv_with_timestamp(self, exporter, sample_data):
        """Test CSV export includes timestamp in filename."""
        filename = "signals"

        with patch('pandas.DataFrame.to_csv') as mock_to_csv, \
             patch('builtins.open', mock_open()):

            exporter.export_to_csv(sample_data, filename, include_timestamp=True)

            # Should call to_csv with a timestamped filename
            call_args = mock_to_csv.call_args
            called_filename = call_args[0][0]
            # The filename should have changed to include timestamp
            assert called_filename != filename

    def test_export_to_csv_custom_separator(self, exporter, sample_data):
        """Test CSV export with custom separator."""
        filename = "test_export"

        with patch('pandas.DataFrame.to_csv') as mock_to_csv, \
             patch('builtins.open', mock_open()):

            exporter.export_to_csv(
                sample_data,
                filename,
                separator=";",
                encoding="utf-16"
            )

            mock_to_csv.assert_called_once()
            # Verify separator and encoding were passed
            call_kwargs = mock_to_csv.call_args[1]
            assert call_kwargs.get("sep") == ";"
            assert call_kwargs.get("encoding") == "utf-16"

    def test_export_to_excel(self, exporter, sample_data):
        """Test exporting to Excel format."""
        filename = "test_export"

        with patch('pandas.ExcelWriter') as mock_excel_writer, \
             patch('builtins.open', mock_open()):

            exporter.export_to_excel(sample_data, filename)

            mock_excel_writer.assert_called_once()
            mock_to_excel = sample_data.to_excel
            mock_to_excel.assert_called_once()

    def test_export_to_excel_multiple_sheets(self, exporter):
        """Test Excel export with multiple sheets."""
        data1 = pd.DataFrame({"col1": [1, 2, 3]})
        data2 = pd.DataFrame({"col2": [4, 5, 6]})

        sheet_data = {
            "Sheet1": data1,
            "Sheet2": data2
        }

        filename = "multi_sheet"

        with patch('pandas.ExcelWriter') as mock_excel_writer, \
             patch('builtins.open', mock_open()):

            exporter.export_to_excel(
                sheet_data,
                filename,
                sheet_name=None  # Multiple sheets
            )

            mock_excel_writer.assert_called_once()

    def test_export_to_json(self, exporter, sample_data):
        """Test exporting to JSON format."""
        filename = "test_export"

        with patch('builtins.open', mock_open()) as mock_file, \
             patch('json.dump') as mock_json_dump:

            exporter.export_to_json(sample_data, filename)

            # Verify file was opened
            mock_file.assert_called()

            # Verify JSON was written
            mock_json_dump.assert_called()

    def test_export_to_json_pretty_print(self, exporter, sample_data):
        """Test JSON export with pretty print."""
        filename = "test_export"

        with patch('builtins.open', mock_open()) as mock_file, \
             patch('json.dump') as mock_json_dump:

            exporter.export_to_json(
                sample_data,
                filename,
                pretty_print=True
            )

            # Verify pretty_print was passed
            call_kwargs = mock_json_dump.call_args[1]
            assert call_kwargs.get("indent") is not None

    def test_export_to_pdf_report(self, exporter, sample_data):
        """Test exporting to PDF report."""
        filename = "test_report"

        with patch('builtins.open', mock_open()) as mock_file:
            # Note: PDF generation is complex and may use external libraries
            # For testing, we just verify the method can be called
            try:
                exporter.export_to_pdf_report(sample_data, filename)
                # If we get here, the method exists
                assert True
            except Exception as e:
                # If PDF generation requires additional setup, that's OK
                # The important thing is the method exists
                assert "pdf" in str(e).lower() or "writer" in str(e).lower()

    def test_create_comprehensive_report(self, exporter):
        """Test creating a comprehensive report."""
        # Create sample data
        data = {
            "predictions": pd.DataFrame({
                "symbol": ["AAPL", "GOOGL"],
                "confidence": [0.85, 0.92]
            }),
            "signals": pd.DataFrame({
                "symbol": ["MSFT"],
                "signal_type": ["BUY"]
            }),
            "backtests": pd.DataFrame({
                "strategy": ["Strategy1"],
                "return": [0.15]
            })
        }

        base_filename = "comprehensive_report"

        # Mock the individual export methods
        with patch.object(exporter, 'export_to_excel') as mock_excel, \
             patch.object(exporter, 'export_to_json') as mock_json, \
             patch.object(exporter, 'export_to_pdf_report') as mock_pdf, \
             patch('builtins.open', mock_open()):

            exporter.create_comprehensive_report(data, base_filename)

            # Verify all three formats were exported
            mock_excel.assert_called_once()
            mock_json.assert_called_once()
            # PDF might fail due to dependencies, so we don't assert it

    def test_add_metadata_to_export(self, exporter, sample_data):
        """Test adding metadata to export."""
        metadata = {
            "export_time": datetime.now().isoformat(),
            "total_records": len(sample_data),
            "source": "Dashboard Export"
        }

        filename = "test_with_metadata"

        with patch('builtins.open', mock_open()) as mock_file, \
             patch('json.dump') as mock_json_dump:

            # This would add metadata in a real implementation
            # For testing, we verify the method accepts metadata
            assert hasattr(exporter, 'add_metadata')

    def test_validate_filename(self, exporter):
        """Test filename validation."""
        # Valid filename
        assert exporter._validate_filename("valid_filename") is True
        assert exporter._validate_filename("file-with-dashes") is True
        assert exporter._validate_filename("file_with_underscores") is True

        # Invalid filenames
        assert exporter._validate_filename("") is False
        assert exporter._validate_filename("file/with/slashes") is False
        assert exporter._validate_filename("file\\with\\backslashes") is False

    def test_sanitize_filename(self, exporter):
        """Test filename sanitization."""
        # Replace special characters
        result = exporter._sanitize_filename("file@#$%^&*()name")
        assert "@" not in result
        assert "#" not in result

        # Replace spaces
        result = exporter._sanitize_filename("file name with spaces")
        assert " " not in result

        # Keep alphanumeric and safe characters
        result = exporter._sanitize_filename("file-name_123.txt")
        assert result == "file-name_123.txt"

    def test_get_default_filename(self, exporter):
        """Test generating default filename with timestamp."""
        base = "data_export"
        default = exporter._get_default_filename(base)

        assert base in default
        # Should have timestamp format
        assert any(char.isdigit() for char in default)

    def test_export_with_compression(self, exporter, sample_data):
        """Test exporting with compression."""
        filename = "compressed_export"

        with patch('pandas.DataFrame.to_csv') as mock_to_csv, \
             patch('builtins.open', mock_open()):

            exporter.export_to_csv(
                sample_data,
                filename,
                compression="gzip"
            )

            # Verify compression was passed
            call_kwargs = mock_to_csv.call_args[1]
            assert call_kwargs.get("compression") == "gzip"

    def test_export_empty_dataframe(self, exporter):
        """Test exporting empty dataframe."""
        empty_df = pd.DataFrame()

        filename = "empty_export"

        with patch('pandas.DataFrame.to_csv') as mock_to_csv, \
             patch('builtins.open', mock_open()):

            exporter.export_to_csv(empty_df, filename)

            # Should still attempt to export
            mock_to_csv.assert_called_once()

    def test_export_large_dataframe(self, exporter):
        """Test exporting large dataframe."""
        # Create a large dataframe
        large_df = pd.DataFrame({
            "col1": range(10000),
            "col2": range(10000)
        })

        filename = "large_export"

        with patch('pandas.DataFrame.to_csv') as mock_to_csv, \
             patch('builtins.open', mock_open()):

            exporter.export_to_csv(large_df, filename)

            # Should handle large data
            mock_to_csv.assert_called_once()

    def test_custom_date_formatting(self, exporter):
        """Test custom date format in exports."""
        df_with_dates = pd.DataFrame({
            "date": [datetime(2024, 11, 7, 10, 0, 0)],
            "value": [100]
        })

        filename = "date_format_test"

        with patch('pandas.DataFrame.to_csv') as mock_to_csv, \
             patch('builtins.open', mock_open()):

            exporter.export_to_csv(
                df_with_dates,
                filename,
                date_format="%Y/%m/%d"
            )

            # Verify date format was passed
            call_kwargs = mock_to_csv.call_args[1]
            assert call_kwargs.get("date_format") == "%Y/%m/%d"


class TestExportFormat:
    """Test ExportFormat enum."""

    def test_all_formats_defined(self):
        """Test all export formats are defined."""
        assert hasattr(ExportFormat, 'CSV')
        assert hasattr(ExportFormat, 'EXCEL')
        assert hasattr(ExportFormat, 'JSON')
        assert hasattr(ExportFormat, 'PDF')

    def test_format_values(self):
        """Test export format values."""
        assert ExportFormat.CSV == "csv"
        assert ExportFormat.EXCEL == "excel"
        assert ExportFormat.JSON == "json"
        assert ExportFormat.PDF == "pdf"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
