"""Tests for custom dashboard widget system."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from dgas.dashboard.widgets.base import (
    BaseWidget,
    WidgetConfig,
    WidgetRegistry,
    WidgetType,
    GridPosition,
)
from dgas.dashboard.widgets.metric import MetricWidget
from dgas.dashboard.widgets.chart import ChartWidget
from dgas.dashboard.widgets.table import TableWidget


class TestWidgetConfig:
    """Test WidgetConfig data class."""

    def test_metric_config_creation(self):
        """Test creating a metric widget config."""
        config = WidgetConfig(
            id="metric_1",
            type=WidgetType.METRIC,
            title="Total Predictions",
            data_source="predictions",
            grid_position=GridPosition(row=0, col=0, width=3, height=2),
            config={"format": "number", "precision": 0}
        )

        assert config.id == "metric_1"
        assert config.type == WidgetType.METRIC
        assert config.title == "Total Predictions"
        assert config.data_source == "predictions"
        assert config.grid_position.row == 0
        assert config.grid_position.col == 0
        assert config.grid_position.width == 3
        assert config.grid_position.height == 2
        assert config.config["format"] == "number"

    def test_chart_config_creation(self):
        """Test creating a chart widget config."""
        config = WidgetConfig(
            id="chart_1",
            type=WidgetType.CHART,
            title="Price Trend",
            data_source="market_data",
            grid_position=GridPosition(row=0, col=0, width=6, height=4),
            config={"chart_type": "line", "x_column": "timestamp", "y_column": "close"}
        )

        assert config.id == "chart_1"
        assert config.type == WidgetType.CHART
        assert config.title == "Price Trend"
        assert config.data_source == "market_data"
        assert config.grid_position.width == 6
        assert config.grid_position.height == 4
        assert config.config["chart_type"] == "line"

    def test_table_config_creation(self):
        """Test creating a table widget config."""
        config = WidgetConfig(
            id="table_1",
            type=WidgetType.TABLE,
            title="Recent Signals",
            data_source="signals",
            grid_position=GridPosition(row=0, col=0, width=12, height=6),
            config={"columns": ["symbol", "signal_type", "confidence"], "paginate": True}
        )

        assert config.id == "table_1"
        assert config.type == WidgetType.TABLE
        assert config.title == "Recent Signals"
        assert config.grid_position.width == 12
        assert config.config["paginate"] is True


class TestGridPosition:
    """Test GridPosition data class."""

    def test_grid_position_creation(self):
        """Test creating a grid position."""
        pos = GridPosition(row=1, col=2, width=3, height=2)

        assert pos.row == 1
        assert pos.col == 2
        assert pos.width == 3
        assert pos.height == 2

    def test_grid_position_to_dict(self):
        """Test converting grid position to dictionary."""
        pos = GridPosition(row=0, col=0, width=4, height=3)
        result = pos.to_dict()

        assert result == {
            "row": 0,
            "col": 0,
            "width": 4,
            "height": 3
        }

    def test_grid_position_overlaps(self):
        """Test detecting grid position overlaps."""
        pos1 = GridPosition(row=0, col=0, width=6, height=4)
        pos2 = GridPosition(row=0, col=0, width=6, height=4)
        pos3 = GridPosition(row=5, col=0, width=6, height=4)
        pos4 = GridPosition(row=0, col=5, width=6, height=4)

        # Should overlap
        assert pos1.overlaps(pos2) is True

        # Should not overlap
        assert pos1.overlaps(pos3) is False
        assert pos1.overlaps(pos4) is False


class TestBaseWidget:
    """Test BaseWidget functionality."""

    @pytest.fixture
    def metric_widget(self):
        """Create a test metric widget."""
        config = WidgetConfig(
            id="test_metric",
            type=WidgetType.METRIC,
            title="Test Metric",
            data_source="test_data",
            grid_position=GridPosition(row=0, col=0, width=3, height=2),
            config={"format": "number"}
        )
        return MetricWidget(config)

    def test_widget_initialization(self, metric_widget):
        """Test widget initializes correctly."""
        assert metric_widget.config.id == "test_metric"
        assert metric_widget.config.type == WidgetType.METRIC
        assert metric_widget.config.title == "Test Metric"
        assert metric_widget.is_initialized is False

    def test_widget_initialization_method(self, metric_widget):
        """Test widget initialization method."""
        with patch('streamlit.empty') as mock_empty:
            mock_container = MagicMock()
            mock_empty.return_value = mock_container

            metric_widget.initialize()

            assert metric_widget.is_initialized is True
            mock_empty.assert_called()

    def test_get_data_source(self, metric_widget):
        """Test getting widget data source."""
        assert metric_widget.get_data_source() == "test_data"

    def test_update_title(self, metric_widget):
        """Test updating widget title."""
        new_title = "Updated Metric"
        metric_widget.update_title(new_title)
        assert metric_widget.config.title == new_title

    def test_widget_to_dict(self, metric_widget):
        """Test converting widget to dictionary."""
        result = metric_widget.to_dict()

        assert result["id"] == "test_metric"
        assert result["type"] == "metric"
        assert result["title"] == "Test Metric"
        assert result["data_source"] == "test_data"
        assert "grid_position" in result
        assert "config" in result


class TestMetricWidget:
    """Test MetricWidget functionality."""

    @pytest.fixture
    def metric_widget(self):
        """Create a test metric widget."""
        config = WidgetConfig(
            id="total_predictions",
            type=WidgetType.METRIC,
            title="Total Predictions",
            data_source="predictions",
            grid_position=GridPosition(row=0, col=0, width=3, height=2),
            config={"format": "number", "precision": 0, "prefix": ""}
        )
        return MetricWidget(config)

    def test_metric_widget_creation(self, metric_widget):
        """Test metric widget creation."""
        assert metric_widget.config.type == WidgetType.METRIC
        assert metric_widget.config.config["format"] == "number"
        assert metric_widget.config.config["precision"] == 0

    def test_render_number_format(self, metric_widget):
        """Test rendering number format."""
        value = 1234.567
        formatted = metric_widget._format_value(value, "number", 0)
        assert formatted == "1235"

    def test_render_currency_format(self, metric_widget):
        """Test rendering currency format."""
        config = WidgetConfig(
            id="test",
            type=WidgetType.METRIC,
            title="Test",
            data_source="test",
            grid_position=GridPosition(row=0, col=0, width=3, height=2),
            config={"format": "currency", "precision": 2, "prefix": "$"}
        )
        widget = MetricWidget(config)

        value = 1234.56
        formatted = widget._format_value(value, "currency", 2, prefix="$")
        assert formatted == "$1,234.56"

    def test_render_percentage_format(self, metric_widget):
        """Test rendering percentage format."""
        config = WidgetConfig(
            id="test",
            type=WidgetType.METRIC,
            title="Test",
            data_source="test",
            grid_position=GridPosition(row=0, col=0, width=3, height=2),
            config={"format": "percentage", "precision": 2, "suffix": "%"}
        )
        widget = MetricWidget(config)

        value = 0.8567
        formatted = widget._format_value(value, "percentage", 2, suffix="%")
        assert formatted == "85.67%"


class TestChartWidget:
    """Test ChartWidget functionality."""

    @pytest.fixture
    def chart_widget(self):
        """Create a test chart widget."""
        config = WidgetConfig(
            id="price_chart",
            type=WidgetType.CHART,
            title="Price Chart",
            data_source="market_data",
            grid_position=GridPosition(row=0, col=0, width=6, height=4),
            config={
                "chart_type": "line",
                "x_column": "timestamp",
                "y_column": "close",
                "color": "blue"
            }
        )
        return ChartWidget(config)

    def test_chart_widget_creation(self, chart_widget):
        """Test chart widget creation."""
        assert chart_widget.config.type == WidgetType.CHART
        assert chart_widget.config.config["chart_type"] == "line"
        assert chart_widget.config.config["x_column"] == "timestamp"
        assert chart_widget.config.config["y_column"] == "close"

    def test_supported_chart_types(self, chart_widget):
        """Test supported chart types."""
        config = WidgetConfig(
            id="test",
            type=WidgetType.CHART,
            title="Test",
            data_source="test",
            grid_position=GridPosition(row=0, col=0, width=6, height=4),
            config={"chart_type": "bar"}
        )
        widget = ChartWidget(config)

        assert widget.config.config["chart_type"] in ["line", "bar", "scatter", "pie", "histogram"]

    def test_chart_config_validation(self, chart_widget):
        """Test chart configuration validation."""
        # Valid config
        valid_config = {
            "chart_type": "line",
            "x_column": "timestamp",
            "y_column": "close"
        }
        assert chart_widget._validate_config(valid_config) is True

        # Invalid config - missing required fields
        invalid_config = {
            "chart_type": "line"
        }
        assert chart_widget._validate_config(invalid_config) is False


class TestTableWidget:
    """Test TableWidget functionality."""

    @pytest.fixture
    def table_widget(self):
        """Create a test table widget."""
        config = WidgetConfig(
            id="signals_table",
            type=WidgetType.TABLE,
            title="Signals Table",
            data_source="signals",
            grid_position=GridPosition(row=0, col=0, width=12, height=6),
            config={
                "columns": ["symbol", "signal_type", "confidence", "timestamp"],
                "paginate": True,
                "page_size": 10
            }
        )
        return TableWidget(config)

    def test_table_widget_creation(self, table_widget):
        """Test table widget creation."""
        assert table_widget.config.type == WidgetType.TABLE
        assert table_widget.config.config["paginate"] is True
        assert table_widget.config.config["page_size"] == 10
        assert "symbol" in table_widget.config.config["columns"]

    def test_table_pagination(self, table_widget):
        """Test table pagination logic."""
        total_items = 25
        page_size = 10
        num_pages = table_widget._calculate_pages(total_items, page_size)

        assert num_pages == 3

    def test_table_column_config(self, table_widget):
        """Test table column configuration."""
        columns = table_widget.config.config["columns"]
        assert len(columns) > 0
        assert all(isinstance(col, str) for col in columns)

    def test_table_csv_export(self, table_widget):
        """Test table CSV export."""
        data = [
            {"symbol": "AAPL", "signal_type": "BUY", "confidence": 0.85},
            {"symbol": "GOOGL", "signal_type": "SELL", "confidence": 0.92}
        ]

        csv_data = table_widget._generate_csv(data)
        assert "AAPL" in csv_data
        assert "GOOGL" in csv_data
        assert "BUY" in csv_data
        assert "SELL" in csv_data


class TestWidgetRegistry:
    """Test WidgetRegistry functionality."""

    def test_registry_initialization(self):
        """Test registry initializes with built-in widgets."""
        registry = WidgetRegistry()
        assert len(registry._widgets) > 0

    def test_register_widget(self):
        """Test registering a new widget type."""
        registry = WidgetRegistry()

        class CustomWidget(BaseWidget):
            pass

        registry.register("custom", CustomWidget)
        assert "custom" in registry._widgets

    def test_get_widget(self):
        """Test getting a widget from registry."""
        registry = WidgetRegistry()

        metric_class = registry.get_widget("metric")
        assert metric_class is not None
        assert issubclass(metric_class, MetricWidget)

        chart_class = registry.get_widget("chart")
        assert chart_class is not None
        assert issubclass(chart_class, ChartWidget)

    def test_get_widget_not_found(self):
        """Test getting a non-existent widget."""
        registry = WidgetRegistry()

        result = registry.get_widget("nonexistent")
        assert result is None

    def test_list_widgets(self):
        """Test listing all available widgets."""
        registry = WidgetRegistry()

        widgets = registry.list_widgets()
        assert len(widgets) > 0
        assert "metric" in widgets
        assert "chart" in widgets
        assert "table" in widgets

    def test_create_widget(self):
        """Test creating a widget from registry."""
        registry = WidgetRegistry()

        config = WidgetConfig(
            id="test",
            type=WidgetType.METRIC,
            title="Test",
            data_source="test",
            grid_position=GridPosition(row=0, col=0, width=3, height=2),
            config={}
        )

        widget = registry.create_widget("metric", config)
        assert widget is not None
        assert isinstance(widget, MetricWidget)
        assert widget.config.id == "test"


class TestWidgetType:
    """Test WidgetType enum."""

    def test_all_types_defined(self):
        """Test all widget types are defined."""
        assert hasattr(WidgetType, 'METRIC')
        assert hasattr(WidgetType, 'CHART')
        assert hasattr(WidgetType, 'TABLE')


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
