"""Tests for dashboard layout management."""

import pytest
import json
import os
from unittest.mock import Mock, patch, MagicMock
from dgas.dashboard.layout.manager import (
    DashboardLayout,
    LayoutManager,
    AutoPositioningMode,
    GridConstraint,
)


class TestGridPosition:
    """Test GridPosition functionality (imported from widgets)."""

    def test_position_creation(self):
        """Test creating a grid position."""
        from dgas.dashboard.widgets.base import GridPosition

        pos = GridPosition(row=1, col=2, width=3, height=2)
        assert pos.row == 1
        assert pos.col == 2
        assert pos.width == 3
        assert pos.height == 2

    def test_position_validation(self):
        """Test validating grid position."""
        from dgas.dashboard.widgets.base import GridPosition

        # Valid position
        valid_pos = GridPosition(row=0, col=0, width=3, height=2)
        assert valid_pos.is_valid(12, 10) is True

        # Invalid - negative values
        with pytest.raises(ValueError):
            GridPosition(row=-1, col=0, width=3, height=2)

        # Invalid - exceeds grid
        invalid_pos = GridPosition(row=0, col=0, width=15, height=2)
        assert invalid_pos.is_valid(12, 10) is False


class TestDashboardLayout:
    """Test DashboardLayout data class."""

    @pytest.fixture
    def sample_layout(self):
        """Create a sample dashboard layout."""
        from dgas.dashboard.widgets.base import GridPosition, WidgetConfig, WidgetType

        widgets = [
            WidgetConfig(
                id="metric_1",
                type=WidgetType.METRIC,
                title="Total Predictions",
                data_source="predictions",
                grid_position=GridPosition(row=0, col=0, width=3, height=2),
                config={"format": "number"}
            ),
            WidgetConfig(
                id="chart_1",
                type=WidgetType.CHART,
                title="Price Chart",
                data_source="market_data",
                grid_position=GridPosition(row=0, col=3, width=6, height=4),
                config={"chart_type": "line"}
            )
        ]

        return DashboardLayout(
            id="test_layout",
            name="Test Dashboard",
            description="A test dashboard layout",
            widgets=widgets,
            created_at="2024-11-07T00:00:00",
            updated_at="2024-11-07T00:00:00"
        )

    def test_layout_creation(self, sample_layout):
        """Test creating a dashboard layout."""
        assert sample_layout.id == "test_layout"
        assert sample_layout.name == "Test Dashboard"
        assert sample_layout.description == "A test dashboard layout"
        assert len(sample_layout.widgets) == 2
        assert sample_layout.created_at is not None

    def test_layout_to_dict(self, sample_layout):
        """Test converting layout to dictionary."""
        result = sample_layout.to_dict()

        assert result["id"] == "test_layout"
        assert result["name"] == "Test Dashboard"
        assert result["description"] == "A test dashboard layout"
        assert "widgets" in result
        assert len(result["widgets"]) == 2
        assert result["widgets"][0]["id"] == "metric_1"

    def test_layout_from_dict(self):
        """Test creating layout from dictionary."""
        data = {
            "id": "imported_layout",
            "name": "Imported Layout",
            "description": "An imported layout",
            "widgets": [],
            "created_at": "2024-11-07T00:00:00",
            "updated_at": "2024-11-07T00:00:00"
        }

        layout = DashboardLayout.from_dict(data)
        assert layout.id == "imported_layout"
        assert layout.name == "Imported Layout"
        assert layout.description == "An imported layout"
        assert len(layout.widgets) == 0

    def test_add_widget(self, sample_layout):
        """Test adding a widget to layout."""
        from dgas.dashboard.widgets.base import GridPosition, WidgetConfig, WidgetType

        initial_count = len(sample_layout.widgets)

        new_widget = WidgetConfig(
            id="table_1",
            type=WidgetType.TABLE,
            title="Signals Table",
            data_source="signals",
            grid_position=GridPosition(row=0, col=0, width=12, height=6),
            config={"columns": ["symbol", "confidence"]}
        )

        sample_layout.add_widget(new_widget)
        assert len(sample_layout.widgets) == initial_count + 1
        assert sample_layout.widgets[-1].id == "table_1"

    def test_remove_widget(self, sample_layout):
        """Test removing a widget from layout."""
        initial_count = len(sample_layout.widgets)
        widget_id = sample_layout.widgets[0].id

        sample_layout.remove_widget(widget_id)
        assert len(sample_layout.widgets) == initial_count - 1
        assert not any(w.id == widget_id for w in sample_layout.widgets)

    def test_get_widget(self, sample_layout):
        """Test getting a widget by ID."""
        widget = sample_layout.get_widget("metric_1")
        assert widget is not None
        assert widget.id == "metric_1"

        # Test non-existent widget
        widget = sample_layout.get_widget("nonexistent")
        assert widget is None

    def test_update_widget(self, sample_layout):
        """Test updating a widget in layout."""
        widget = sample_layout.get_widget("metric_1")
        old_title = widget.title

        widget.title = "Updated Predictions"
        sample_layout.update_widget(widget)

        updated_widget = sample_layout.get_widget("metric_1")
        assert updated_widget.title == "Updated Predictions"
        assert updated_widget.title != old_title


class TestLayoutManager:
    """Test LayoutManager functionality."""

    @pytest.fixture
    def layout_manager(self):
        """Create a test layout manager."""
        return LayoutManager(storage_path="/tmp/test_layouts")

    def test_manager_initialization(self, layout_manager):
        """Test manager initializes correctly."""
        assert layout_manager.storage_path == "/tmp/test_layouts"
        assert isinstance(layout_manager.layouts, dict)

    def test_create_layout(self, layout_manager):
        """Test creating a new layout."""
        layout = layout_manager.create_layout(
            name="New Layout",
            description="A new test layout"
        )

        assert layout.id in layout_manager.layouts
        assert layout.name == "New Layout"
        assert layout.description == "A new test layout"
        assert len(layout.widgets) == 0

    def test_save_layout(self, layout_manager):
        """Test saving a layout to storage."""
        layout = layout_manager.create_layout(
            name="Save Test",
            description="Testing save functionality"
        )

        with patch('builtins.open', mock_open()) as mock_file, \
             patch('json.dump') as mock_json_dump:

            layout_manager.save_layout(layout)

            # Verify file was opened
            mock_file.assert_called_once()

            # Verify JSON was written
            mock_json_dump.assert_called_once()

    def test_load_layout(self, layout_manager):
        """Test loading a layout from storage."""
        layout_data = {
            "id": "loaded_layout",
            "name": "Loaded Layout",
            "description": "A loaded layout",
            "widgets": [],
            "created_at": "2024-11-07T00:00:00",
            "updated_at": "2024-11-07T00:00:00"
        }

        with patch('builtins.open', mock_open(read_data=json.dumps(layout_data))), \
             patch('json.load', return_value=layout_data):

            layout = layout_manager.load_layout("loaded_layout")

            assert layout is not None
            assert layout.id == "loaded_layout"
            assert layout.name == "Loaded Layout"

    def test_delete_layout(self, layout_manager):
        """Test deleting a layout."""
        layout = layout_manager.create_layout(
            name="Delete Test",
            description="Testing delete functionality"
        )

        layout_id = layout.id
        assert layout_id in layout_manager.layouts

        result = layout_manager.delete_layout(layout_id)
        assert result is True
        assert layout_id not in layout_manager.layouts

    def test_list_layouts(self, layout_manager):
        """Test listing all layouts."""
        # Create multiple layouts
        layout_manager.create_layout("Layout 1", "Description 1")
        layout_manager.create_layout("Layout 2", "Description 2")
        layout_manager.create_layout("Layout 3", "Description 3")

        layouts = layout_manager.list_layouts()
        assert len(layouts) >= 3
        assert any(l.name == "Layout 1" for l in layouts)
        assert any(l.name == "Layout 2" for l in layouts)
        assert any(l.name == "Layout 3" for l in layouts)

    def test_get_layout(self, layout_manager):
        """Test getting a layout by ID."""
        layout = layout_manager.create_layout("Get Test", "Testing get functionality")

        retrieved = layout_manager.get_layout(layout.id)
        assert retrieved is not None
        assert retrieved.id == layout.id
        assert retrieved.name == "Get Test"

    def test_export_layout(self, layout_manager):
        """Test exporting a layout to JSON."""
        layout = layout_manager.create_layout("Export Test", "Testing export")

        from dgas.dashboard.widgets.base import GridPosition, WidgetConfig, WidgetType

        widget = WidgetConfig(
            id="export_widget",
            type=WidgetType.METRIC,
            title="Export Widget",
            data_source="test_data",
            grid_position=GridPosition(row=0, col=0, width=3, height=2),
            config={}
        )
        layout.add_widget(widget)

        export_data = layout_manager.export_layout(layout.id)

        assert "id" in export_data
        assert "name" in export_data
        assert "widgets" in export_data
        assert len(export_data["widgets"]) == 1

    def test_import_layout(self, layout_manager):
        """Test importing a layout from JSON."""
        layout_data = {
            "id": "imported_layout",
            "name": "Imported Layout",
            "description": "An imported layout",
            "widgets": [],
            "created_at": "2024-11-07T00:00:00",
            "updated_at": "2024-11-07T00:00:00"
        }

        imported_layout = layout_manager.import_layout(layout_data)

        assert imported_layout is not None
        assert imported_layout.id == "imported_layout"
        assert imported_layout.name == "Imported Layout"
        assert imported_layout.id in layout_manager.layouts


class TestAutoPositioning:
    """Test auto-positioning algorithms."""

    def test_pack_left_to_right(self):
        """Test left-to-right packing algorithm."""
        from dgas.dashboard.widgets.base import GridPosition, WidgetConfig, WidgetType, AutoPositioningMode

        widgets = [
            WidgetConfig("w1", WidgetType.METRIC, "W1", "data", GridPosition(0, 0, 3, 2), {}),
            WidgetConfig("w2", WidgetType.METRIC, "W2", "data", GridPosition(0, 0, 3, 2), {}),
            WidgetConfig("w3", WidgetType.METRIC, "W3", "data", GridPosition(0, 0, 3, 2), {}),
        ]

        positions = AutoPositioningMode.PACK_LEFT_TO_RIGHT.calculate_positions(widgets, 12)

        assert positions[0].row == 0
        assert positions[0].col == 0
        assert positions[1].col == 3
        assert positions[2].col == 6

    def test_pack_top_to_bottom(self):
        """Test top-to-bottom packing algorithm."""
        from dgas.dashboard.widgets.base import GridPosition, WidgetConfig, WidgetType, AutoPositioningMode

        widgets = [
            WidgetConfig("w1", WidgetType.METRIC, "W1", "data", GridPosition(0, 0, 3, 2), {}),
            WidgetConfig("w2", WidgetType.METRIC, "W2", "data", GridPosition(0, 0, 3, 2), {}),
            WidgetConfig("w3", WidgetType.METRIC, "W3", "data", GridPosition(0, 0, 3, 2), {}),
        ]

        positions = AutoPositioningMode.PACK_TOP_TO_BOTTOM.calculate_positions(widgets, 12)

        assert positions[0].row == 0
        assert positions[0].col == 0
        assert positions[1].row == 2
        assert positions[1].col == 0
        assert positions[2].row == 4
        assert positions[2].col == 0

    def test_grid_auto_arrange(self):
        """Test grid auto-arrange algorithm."""
        from dgas.dashboard.widgets.base import GridPosition, WidgetConfig, WidgetType, AutoPositioningMode

        widgets = []
        for i in range(6):
            widgets.append(
                WidgetConfig(f"w{i}", WidgetType.METRIC, f"W{i}", "data", GridPosition(0, 0, 4, 3), {})
            )

        positions = AutoPositioningMode.GRID_AUTO_ARRANGE.calculate_positions(widgets, 12)

        # First row
        assert positions[0].row == 0
        assert positions[0].col == 0
        assert positions[1].row == 0
        assert positions[1].col == 4
        assert positions[2].row == 0
        assert positions[2].col == 8

        # Second row
        assert positions[3].row == 3
        assert positions[3].col == 0
        assert positions[4].row == 3
        assert positions[4].col == 4
        assert positions[5].row == 3
        assert positions[5].col == 8


class TestGridConstraint:
    """Test grid constraint validation."""

    def test_validate_position(self):
        """Test validating a grid position."""
        constraint = GridConstraint(max_cols=12, max_rows=10, max_width=12, max_height=10)

        # Valid position
        valid = GridPosition(row=0, col=0, width=3, height=2)
        assert constraint.validate_position(valid) is True

        # Invalid - exceeds max width
        invalid_width = GridPosition(row=0, col=0, width=15, height=2)
        assert constraint.validate_position(invalid_width) is False

        # Invalid - exceeds max height
        invalid_height = GridPosition(row=0, col=0, width=3, height=15)
        assert constraint.validate_position(invalid_height) is False

    def test_check_overlap(self):
        """Test checking for widget overlaps."""
        constraint = GridConstraint(max_cols=12, max_rows=10)

        pos1 = GridPosition(row=0, col=0, width=6, height=4)
        pos2 = GridPosition(row=0, col=0, width=6, height=4)
        pos3 = GridPosition(row=5, col=0, width=6, height=4)

        # Overlapping
        assert constraint.check_overlap(pos1, pos2) is True

        # Not overlapping
        assert constraint.check_overlap(pos1, pos3) is False

    def test_find_next_available_position(self):
        """Test finding next available position."""
        constraint = GridConstraint(max_cols=12, max_rows=10)

        occupied = [
            GridPosition(row=0, col=0, width=6, height=4),
            GridPosition(row=0, col=6, width=6, height=4),
        ]

        new_pos = GridPosition(row=0, col=0, width=3, height=2)
        next_pos = constraint.find_next_available_position(new_pos, occupied)

        assert next_pos is not None
        assert next_pos.row == 4  # First available row
        assert next_pos.col == 0  # First available column

    def test_snap_to_grid(self):
        """Test snapping position to grid."""
        constraint = GridConstraint(max_cols=12, max_rows=10, grid_size=1)

        # Already on grid
        pos1 = GridPosition(row=0, col=0, width=3, height=2)
        snapped1 = constraint.snap_to_grid(pos1)
        assert snapped1.row == 0
        assert snapped1.col == 0

        # Off grid (should snap to nearest)
        pos2 = GridPosition(row=0.5, col=0.7, width=2.9, height=1.8)
        snapped2 = constraint.snap_to_grid(pos2)
        assert snapped2.row == 1
        assert snapped2.col == 1
        assert snapped2.width == 3
        assert snapped2.height == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
