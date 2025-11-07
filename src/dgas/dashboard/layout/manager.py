"""Layout manager for custom dashboards.

Manages widget positions, grid layout, and dashboard persistence.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import streamlit as st

from dgas.dashboard.widgets.base import WidgetConfig, DEFAULT_POSITIONS, WIDGET_SIZES

logger = logging.getLogger(__name__)


class LayoutManager:
    """Manages dashboard layout and widget positions."""

    # Grid configuration
    GRID_COLUMNS = 12
    ROW_HEIGHT = 100  # pixels

    def __init__(self, storage_path: Optional[Path] = None):
        """
        Initialize layout manager.

        Args:
            storage_path: Path to store dashboard layouts
        """
        self.storage_path = storage_path or Path.home() / ".dgas" / "dashboards"
        self.storage_path.mkdir(parents=True, exist_ok=True)

    def get_dashboard_list(self) -> List[str]:
        """
        Get list of saved dashboards.

        Returns:
            List of dashboard names
        """
        dashboards = []
        for file in self.storage_path.glob("*.json"):
            dashboards.append(file.stem)
        return sorted(dashboards)

    def save_dashboard(self, name: str, layout: List[Dict[str, Any]]) -> bool:
        """
        Save dashboard layout.

        Args:
            name: Dashboard name
            layout: Widget layout list

        Returns:
            True if successful
        """
        try:
            filepath = self.storage_path / f"{name}.json"
            data = {
                "name": name,
                "layout": layout,
                "grid_columns": self.GRID_COLUMNS,
                "saved_at": datetime.utcnow().isoformat() + "Z",
            }

            with open(filepath, "w") as f:
                json.dump(data, f, indent=2)

            logger.info(f"Saved dashboard: {name}")
            return True
        except Exception as e:
            logger.error(f"Error saving dashboard: {e}")
            return False

    def load_dashboard(self, name: str) -> Optional[List[Dict[str, Any]]]:
        """
        Load dashboard layout.

        Args:
            name: Dashboard name

        Returns:
            Widget layout or None
        """
        try:
            filepath = self.storage_path / f"{name}.json"
            if not filepath.exists():
                return None

            with open(filepath, "r") as f:
                data = json.load(f)

            return data.get("layout", [])
        except Exception as e:
            logger.error(f"Error loading dashboard: {e}")
            return None

    def delete_dashboard(self, name: str) -> bool:
        """
        Delete dashboard layout.

        Args:
            name: Dashboard name

        Returns:
            True if successful
        """
        try:
            filepath = self.storage_path / f"{name}.json"
            if filepath.exists():
                filepath.unlink()
            logger.info(f"Deleted dashboard: {name}")
            return True
        except Exception as e:
            logger.error(f"Error deleting dashboard: {e}")
            return False

    def export_dashboard(self, name: str, export_path: Path) -> bool:
        """
        Export dashboard to file.

        Args:
            name: Dashboard name
            export_path: Export file path

        Returns:
            True if successful
        """
        layout = self.load_dashboard(name)
        if layout is None:
            return False

        try:
            with open(export_path, "w") as f:
                json.dump(layout, f, indent=2)
            return True
        except Exception as e:
            logger.error(f"Error exporting dashboard: {e}")
            return False

    def import_dashboard(self, import_path: Path, name: Optional[str] = None) -> Optional[str]:
        """
        Import dashboard from file.

        Args:
            import_path: Import file path
            name: Optional name (uses file name if not provided)

        Returns:
            Dashboard name or None
        """
        try:
            with open(import_path, "r") as f:
                layout = json.load(f)

            dashboard_name = name or import_path.stem
            self.save_dashboard(dashboard_name, layout)

            return dashboard_name
        except Exception as e:
            logger.error(f"Error importing dashboard: {e}")
            return None

    def get_default_layout(self) -> List[Dict[str, Any]]:
        """
        Get default dashboard layout.

        Returns:
            Default widget layout
        """
        import time
        timestamp = str(int(time.time() * 1000))

        return [
            {
                "id": f"metric_{timestamp}_1",
                "type": "metric",
                "title": "Total Symbols",
                "position": {"x": 0, "y": 0, "width": 2, "height": 1},
                "data_source": "system_overview",
                "refresh_interval": 60,
                "properties": {
                    "metric_key": "total_symbols",
                    "label": "Total Symbols",
                    "format": "number",
                },
            },
            {
                "id": f"metric_{timestamp}_2",
                "type": "metric",
                "title": "Data Bars",
                "position": {"x": 2, "y": 0, "width": 2, "height": 1},
                "data_source": "system_overview",
                "refresh_interval": 60,
                "properties": {
                    "metric_key": "total_data_bars",
                    "label": "Total Bars",
                    "format": "number",
                },
            },
            {
                "id": f"metric_{timestamp}_3",
                "type": "metric",
                "title": "Recent Predictions",
                "position": {"x": 4, "y": 0, "width": 2, "height": 1},
                "data_source": "system_overview",
                "refresh_interval": 60,
                "properties": {
                    "metric_key": "predictions_24h",
                    "label": "Predictions (24h)",
                    "format": "number",
                },
            },
            {
                "id": f"chart_{timestamp}_1",
                "type": "chart",
                "title": "Data Inventory",
                "position": {"x": 0, "y": 1, "width": 6, "height": 2},
                "data_source": "data_inventory",
                "refresh_interval": 300,
                "properties": {
                    "chart_type": "bar",
                    "title": "Data Inventory",
                },
            },
            {
                "id": f"table_{timestamp}_1",
                "type": "table",
                "title": "Recent Predictions",
                "position": {"x": 0, "y": 3, "width": 6, "height": 2},
                "data_source": "predictions",
                "refresh_interval": 300,
                "properties": {
                    "title": "Recent Predictions",
                    "page_size": 10,
                },
            },
        ]

    def auto_position_widget(self, layout: List[Dict[str, Any]]) -> Dict[str, int]:
        """
        Calculate automatic position for new widget.

        Args:
            layout: Current layout

        Returns:
            Position dictionary
        """
        if not layout:
            return DEFAULT_POSITIONS[0]

        # Simple algorithm: place in next available slot
        grid = [[False for _ in range(self.GRID_COLUMNS)] for _ in range(10)]

        # Mark occupied cells
        for widget in layout:
            pos = widget.get("position", {})
            x, y = pos.get("x", 0), pos.get("y", 0)
            width, height = pos.get("width", 2), pos.get("height", 1)

            for row in range(y, y + height):
                if row < len(grid):
                    for col in range(x, x + width):
                        if col < self.GRID_COLUMNS:
                            grid[row][col] = True

        # Find first available position
        for row in range(10):
            for col in range(self.GRID_COLUMNS):
                if not grid[row][col]:
                    return {"x": col, "y": row, "width": 2, "height": 1}

        # If no space, add new row
        return {"x": 0, "y": len(layout) // 6, "width": 2, "height": 1}

    def validate_layout(self, layout: List[Dict[str, Any]]) -> List[str]:
        """
        Validate widget layout.

        Args:
            layout: Widget layout to validate

        Returns:
            List of validation errors
        """
        errors = []

        for i, widget in enumerate(layout):
            if "id" not in widget:
                errors.append(f"Widget {i}: Missing ID")
            if "type" not in widget:
                errors.append(f"Widget {i}: Missing type")
            if "title" not in widget:
                errors.append(f"Widget {i}: Missing title")
            if "position" not in widget:
                errors.append(f"Widget {i}: Missing position")
            if "data_source" not in widget:
                errors.append(f"Widget {i}: Missing data_source")

            # Check position
            position = widget.get("position", {})
            x, y = position.get("x", 0), position.get("y", 0)
            width, height = position.get("width", 2), position.get("height", 1)

            if x < 0 or y < 0:
                errors.append(f"Widget {i}: Invalid position (negative)")

            if x + width > self.GRID_COLUMNS:
                errors.append(f"Widget {i}: Position exceeds grid width")

        return errors

    def get_widget_by_id(self, layout: List[Dict[str, Any]], widget_id: str) -> Optional[Dict[str, Any]]:
        """
        Get widget by ID.

        Args:
            layout: Widget layout
            widget_id: Widget ID

        Returns:
            Widget or None
        """
        for widget in layout:
            if widget.get("id") == widget_id:
                return widget
        return None

    def remove_widget(self, layout: List[Dict[str, Any]], widget_id: str) -> List[Dict[str, Any]]:
        """
        Remove widget from layout.

        Args:
            layout: Widget layout
            widget_id: Widget ID to remove

        Returns:
            Updated layout
        """
        return [w for w in layout if w.get("id") != widget_id]

    def update_widget(self, layout: List[Dict[str, Any]], widget_id: str, updates: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Update widget in layout.

        Args:
            layout: Widget layout
            widget_id: Widget ID
            updates: Updates to apply

        Returns:
            Updated layout
        """
        for widget in layout:
            if widget.get("id") == widget_id:
                widget.update(updates)
                break
        return layout


# Global manager instance
_manager_instance: Optional[LayoutManager] = None


def get_manager() -> LayoutManager:
    """
    Get the global layout manager instance.

    Returns:
        Manager instance
    """
    global _manager_instance

    if _manager_instance is None:
        _manager_instance = LayoutManager()

    return _manager_instance


# Streamlit integration helpers

def init_dashboard_state() -> None:
    """Initialize dashboard state in Streamlit."""
    if "dashboard_layout" not in st.session_state:
        st.session_state.dashboard_layout = get_manager().get_default_layout()

    if "dashboard_name" not in st.session_state:
        st.session_state.dashboard_name = "default"

    if "edit_mode" not in st.session_state:
        st.session_state.edit_mode = False


def get_current_layout() -> List[Dict[str, Any]]:
    """
    Get current dashboard layout.

    Returns:
        Current layout
    """
    init_dashboard_state()
    return st.session_state.dashboard_layout


def save_current_layout(name: str) -> bool:
    """
    Save current dashboard layout.

    Args:
        name: Dashboard name

    Returns:
        True if successful
    """
    init_dashboard_state()
    manager = get_manager()
    return manager.save_dashboard(name, st.session_state.dashboard_layout)


def load_dashboard(name: str) -> bool:
    """
    Load dashboard layout.

    Args:
        name: Dashboard name

    Returns:
        True if successful
    """
    init_dashboard_state()
    manager = get_manager()
    layout = manager.load_dashboard(name)
    if layout is not None:
        st.session_state.dashboard_layout = layout
        st.session_state.dashboard_name = name
        return True
    return False


if __name__ == "__main__":
    # Test the manager
    manager = LayoutManager()

    # Test default layout
    layout = manager.get_default_layout()
    print(f"Default layout: {len(layout)} widgets")

    # Test validation
    errors = manager.validate_layout(layout)
    print(f"Validation errors: {errors}")

    # Test save/load
    manager.save_dashboard("test", layout)
    loaded = manager.load_dashboard("test")
    print(f"Loaded layout: {len(loaded) if loaded else 0} widgets")
