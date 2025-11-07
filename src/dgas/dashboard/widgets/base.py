"""Base widget class for custom dashboard widgets.

Defines the interface and common functionality for all dashboard widgets.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, Callable

import streamlit as st


@dataclass
class WidgetConfig:
    """Configuration for a widget."""
    id: str
    type: str
    title: str
    position: Dict[str, int]  # x, y, width, height
    data_source: str
    refresh_interval: int = 30  # seconds
    properties: Optional[Dict[str, Any]] = None


class BaseWidget(ABC):
    """Base class for all dashboard widgets."""

    def __init__(self, config: WidgetConfig):
        """
        Initialize widget.

        Args:
            config: Widget configuration
        """
        self.config = config
        self.data: Optional[Any] = None
        self.last_update: Optional[str] = None

    @property
    @abstractmethod
    def widget_type(self) -> str:
        """Get widget type identifier."""
        pass

    @abstractmethod
    def fetch_data(self) -> Any:
        """
        Fetch data for the widget.

        Returns:
            Widget data
        """
        pass

    @abstractmethod
    def render(self) -> None:
        """
        Render the widget in Streamlit.
        """
        pass

    def update_data(self) -> None:
        """Update widget data."""
        try:
            self.data = self.fetch_data()
            from datetime import datetime
            self.last_update = datetime.now().isoformat()
        except Exception as e:
            st.error(f"Error fetching data for widget {self.config.id}: {e}")
            self.data = None

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert widget to dictionary.

        Returns:
            Widget configuration as dict
        """
        return asdict(self.config)

    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> BaseWidget:
        """
        Create widget from dictionary.

        Args:
            config_dict: Configuration dictionary

        Returns:
            Widget instance
        """
        config = WidgetConfig(**config_dict)
        return cls(config)

    def get_data_source_options(self) -> List[str]:
        """
        Get available data sources for this widget type.

        Returns:
            List of data source names
        """
        return [
            "system_overview",
            "data_inventory",
            "predictions",
            "backtests",
            "system_status",
            "data_quality",
        ]

    def validate_config(self) -> List[str]:
        """
        Validate widget configuration.

        Returns:
            List of validation errors
        """
        errors = []

        if not self.config.id:
            errors.append("Widget ID is required")

        if not self.config.title:
            errors.append("Widget title is required")

        if not self.config.data_source:
            errors.append("Data source is required")

        if self.config.refresh_interval < 5:
            errors.append("Refresh interval must be at least 5 seconds")

        return errors

    def render_header(self) -> None:
        """Render widget header with controls."""
        col1, col2, col3 = st.columns([3, 1, 1])

        with col1:
            st.subheader(self.config.title)

        with col2:
            if st.button("🔄", key=f"refresh_{self.config.id}", help="Refresh data"):
                self.update_data()
                st.rerun()

        with col3:
            if st.button("✕", key=f"remove_{self.config.id}", help="Remove widget"):
                st.session_state.dashboard_layout = [
                    w for w in st.session_state.dashboard_layout
                    if w["id"] != self.config.id
                ]
                st.rerun()

    def render_data_source_info(self) -> None:
        """Render data source information."""
        if self.last_update:
            st.caption(
                f"Data source: {self.config.data_source} • "
                f"Last updated: {self.last_update} • "
                f"Auto-refresh: {self.config.refresh_interval}s"
            )

    def render_error(self, message: str) -> None:
        """
        Render error state.

        Args:
            message: Error message
        """
        st.error(f"Error: {message}")


class WidgetRegistry:
    """Registry for widget types."""

    _widgets: Dict[str, type] = {}

    @classmethod
    def register(cls, widget_type: str, widget_class: type) -> None:
        """
        Register a widget type.

        Args:
            widget_type: Type identifier
            widget_class: Widget class
        """
        cls._widgets[widget_type] = widget_class

    @classmethod
    def get_widget_class(cls, widget_type: str) -> Optional[type]:
        """
        Get widget class by type.

        Args:
            widget_type: Widget type

        Returns:
            Widget class or None
        """
        return cls._widgets.get(widget_type)

    @classmethod
    def get_all_types(cls) -> List[str]:
        """
        Get all registered widget types.

        Returns:
            List of widget types
        """
        return list(cls._widgets.keys())

    @classmethod
    def create_widget(cls, config: WidgetConfig) -> Optional[BaseWidget]:
        """
        Create widget from configuration.

        Args:
            config: Widget configuration

        Returns:
            Widget instance or None
        """
        widget_class = cls.get_widget_class(config.type)
        if widget_class:
            return widget_class(config)
        return None


# Widget sizes
WIDGET_SIZES = {
    "small": {"width": 1, "height": 1},
    "medium": {"width": 2, "height": 1},
    "large": {"width": 3, "height": 2},
}

# Default positions
DEFAULT_POSITIONS = [
    {"x": 0, "y": 0, "width": 2, "height": 1},
    {"x": 2, "y": 0, "width": 2, "height": 1},
    {"x": 4, "y": 0, "width": 2, "height": 1},
    {"x": 0, "y": 1, "width": 3, "height": 2},
    {"x": 3, "y": 1, "width": 3, "height": 2},
    {"x": 0, "y": 3, "width": 6, "height": 2},
]
