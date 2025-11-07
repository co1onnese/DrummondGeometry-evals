"""Custom Dashboard Builder page.

Allows users to create and customize their own dashboards.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Dict, List, Any, Optional

import streamlit as st

from dgas.dashboard.widgets import (
    BaseWidget,
    WidgetConfig,
    WidgetRegistry,
)
from dgas.dashboard.layout import (
    get_manager,
    init_dashboard_state,
    get_current_layout,
    save_current_layout,
    load_dashboard,
    LayoutManager,
)


def render_widget_gallery() -> None:
    """Render widget gallery for adding new widgets."""
    st.subheader("Widget Gallery")

    widget_types = {
        "metric": "📊 Metric Card",
        "chart": "📈 Chart",
        "table": "📋 Data Table",
    }

    st.markdown("Click a widget type to add it to your dashboard:")

    # Create columns for widget types
    cols = st.columns(len(widget_types))

    for i, (widget_type, title) in enumerate(widget_types.items()):
        with cols[i]:
            st.markdown(f"### {title}")
            st.markdown("---")

            # Add description
            descriptions = {
                "metric": "Display KPIs and metrics with value, delta, and format options",
                "chart": "Create various charts: line, bar, scatter, pie, histogram",
                "table": "Show tabular data with pagination and export",
            }
            st.write(descriptions[widget_type])

            if st.button(f"Add {title}", key=f"add_{widget_type}", type="primary"):
                # Get layout manager
                manager = get_manager()

                # Create new widget config
                widget_id = f"{widget_type}_{int(time.time() * 1000)}"
                position = manager.auto_position_widget(st.session_state.dashboard_layout)

                new_widget = {
                    "id": widget_id,
                    "type": widget_type,
                    "title": f"New {title}",
                    "position": position,
                    "data_source": "system_overview",
                    "refresh_interval": 60,
                    "properties": {},
                }

                # Add to layout
                st.session_state.dashboard_layout.append(new_widget)
                st.success(f"Added {title} to dashboard!")
                st.rerun()

    st.markdown("---")


def render_widget_configuration(widget: Dict[str, Any]) -> None:
    """
    Render configuration panel for a widget.

    Args:
        widget: Widget configuration dictionary
    """
    st.subheader(f"Configure: {widget['title']}")

    with st.form(key=f"config_{widget['id']}"):
        # Basic properties
        title = st.text_input("Title", value=widget.get("title", ""))
        data_source = st.selectbox(
            "Data Source",
            options=[
                "system_overview",
                "data_inventory",
                "predictions",
                "backtests",
                "system_status",
                "data_quality",
            ],
            index=0,
        )
        refresh_interval = st.slider(
            "Refresh Interval (seconds)",
            min_value=5,
            max_value=3600,
            value=widget.get("refresh_interval", 60),
            step=5,
        )

        st.markdown("---")

        # Widget-specific properties
        widget_type = widget.get("type")
        if widget_type == "metric":
            st.markdown("**Metric Configuration**")
            col1, col2 = st.columns(2)

            with col1:
                metric_key = st.selectbox(
                    "Metric",
                    options=[
                        "total_symbols",
                        "total_data_bars",
                        "predictions_24h",
                        "signals_24h",
                    ],
                    index=0,
                )
                label = st.text_input("Label", value=widget.get("properties", {}).get("label", "Metric"))
                help_text = st.text_input(
                    "Help Text",
                    value=widget.get("properties", {}).get("help", ""),
                    help="Optional help text to display",
                )

            with col2:
                format_type = st.selectbox(
                    "Format",
                    options=["number", "percentage", "currency"],
                    index=0,
                )
                delta = st.text_input(
                    "Delta",
                    value=widget.get("properties", {}).get("delta", ""),
                    help="Optional delta to display",
                )

            # Update properties
            widget["properties"] = {
                "metric_key": metric_key,
                "label": label,
                "format": format_type,
                "delta": delta,
                "help": help_text,
            }

        elif widget_type == "chart":
            st.markdown("**Chart Configuration**")
            col1, col2 = st.columns(2)

            with col1:
                chart_type = st.selectbox(
                    "Chart Type",
                    options=["line", "bar", "scatter", "pie", "histogram"],
                    index=1,
                )
                title_input = st.text_input(
                    "Chart Title",
                    value=widget.get("properties", {}).get("title", ""),
                )

            with col2:
                days = st.number_input(
                    "Days (for predictions)",
                    min_value=1,
                    max_value=90,
                    value=7,
                    help="Used for predictions data source",
                )
                limit = st.number_input(
                    "Limit (for backtests)",
                    min_value=5,
                    max_value=100,
                    value=20,
                    help="Used for backtests data source",
                )

            # Update properties
            widget["properties"] = {
                "chart_type": chart_type,
                "title": title_input,
                "days": days,
                "limit": limit,
            }

        elif widget_type == "table":
            st.markdown("**Table Configuration**")
            col1, col2 = st.columns(2)

            with col1:
                page_size = st.selectbox(
                    "Page Size",
                    options=[10, 20, 50, 100],
                    index=1,
                )
                title_input = st.text_input(
                    "Table Title",
                    value=widget.get("properties", {}).get("title", ""),
                )

            # Update properties
            widget["properties"] = {
                "title": title_input,
                "page_size": page_size,
            }

        st.markdown("---")

        # Position (read-only, for now)
        st.markdown("**Position**")
        pos = widget.get("position", {})
        st.info(
            f"Grid: {pos.get('x', 0)},{pos.get('y', 0)} "
            f"Size: {pos.get('width', 2)}x{pos.get('height', 1)}"
        )

        # Submit button
        col1, col2 = st.columns(2)
        with col1:
            submitted = st.form_submit_button("Save Changes", type="primary")
        with col2:
            if st.form_submit_button("Cancel"):
                st.rerun()

        if submitted:
            # Update widget
            widget["title"] = title
            widget["data_source"] = data_source
            widget["refresh_interval"] = refresh_interval

            st.success("Widget updated!")
            st.rerun()


def render_dashboard_layout(layout: List[Dict[str, Any]]) -> None:
    """
    Render the dashboard layout with widgets.

    Args:
        layout: Widget layout list
    """
    st.subheader("Dashboard Layout")

    if not layout:
        st.info("No widgets yet. Add some from the widget gallery above!")
        return

    # Create grid layout using columns
    # We'll use a simple approach: render widgets in a vertical flow
    for widget_config in layout:
        with st.container():
            # Create widget instance
            try:
                widget_class = WidgetRegistry.get_widget_class(widget_config["type"])
                if widget_class:
                    config = WidgetConfig(**widget_config)
                    widget = widget_class(config)

                    # Render widget
                    widget.render()
                else:
                    st.error(f"Unknown widget type: {widget_config['type']}")
            except Exception as e:
                st.error(f"Error rendering widget: {e}")

            st.markdown("---")


def render_dashboard_management() -> None:
    """Render dashboard management panel."""
    st.subheader("Dashboard Management")

    manager = get_manager()

    # Save/Load section
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**Save Dashboard**")
        save_name = st.text_input("Dashboard Name", value=st.session_state.get("dashboard_name", ""))
        if st.button("Save", key="save_dashboard"):
            if save_name:
                if save_current_layout(save_name):
                    st.session_state.dashboard_name = save_name
                    st.success(f"Saved dashboard: {save_name}")
                else:
                    st.error("Failed to save dashboard")
            else:
                st.error("Please enter a dashboard name")

    with col2:
        st.markdown("**Load Dashboard**")
        dashboard_list = manager.get_dashboard_list()
        if dashboard_list:
            load_name = st.selectbox("Select Dashboard", options=dashboard_list)
            col_a, col_b = st.columns(2)
            with col_a:
                if st.button("Load", key="load_dashboard"):
                    if load_dashboard(load_name):
                        st.success(f"Loaded dashboard: {load_name}")
                        st.rerun()
                    else:
                        st.error("Failed to load dashboard")
            with col_b:
                if st.button("Delete", key="delete_dashboard"):
                    if manager.delete_dashboard(load_name):
                        st.success(f"Deleted dashboard: {load_name}")
                        st.rerun()
                    else:
                        st.error("Failed to delete dashboard")
        else:
            st.info("No saved dashboards")

    st.markdown("---")

    # Export/Import section
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**Export Dashboard**")
        current_name = st.session_state.get("dashboard_name", "default")
        if st.button("Export to JSON"):
            export_path = Path(f"dashboard_{current_name}_{int(time.time())}.json")
            if manager.export_dashboard(current_name, export_path):
                st.success(f"Exported to {export_path}")
                # Offer download
                with open(export_path, "r") as f:
                    st.download_button(
                        label="Download Export",
                        data=f.read(),
                        file_name=str(export_path),
                        mime="application/json",
                    )
            else:
                st.error("Failed to export dashboard")

    with col2:
        st.markdown("**Import Dashboard**")
        uploaded_file = st.file_uploader("Choose a file", type="json")
        if uploaded_file is not None:
            import_name = st.text_input("Dashboard Name", value=uploaded_file.name.replace(".json", ""))
            if st.button("Import", key="import_dashboard"):
                # Save uploaded file temporarily
                temp_path = Path(f"temp_{uploaded_file.name}")
                with open(temp_path, "wb") as f:
                    f.write(uploaded_file.getvalue())

                # Import
                result = manager.import_dashboard(temp_path, import_name)
                if result:
                    st.success(f"Imported dashboard: {result}")
                    load_dashboard(result)
                    st.rerun()
                else:
                    st.error("Failed to import dashboard")

                # Clean up
                temp_path.unlink(missing_ok=True)


def render() -> None:
    """Render the Custom Dashboard Builder page."""
    st.header("Custom Dashboard Builder")
    st.markdown(
        "Create and customize your own dashboard by adding widgets, "
        "configuring data sources, and arranging the layout."
    )

    # Initialize state
    init_dashboard_state()

    # Tabs for different views
    tab1, tab2, tab3 = st.tabs(["Dashboard", "Widget Gallery", "Manage"])

    with tab1:
        st.markdown("### Your Custom Dashboard")
        layout = get_current_layout()
        render_dashboard_layout(layout)

    with tab2:
        render_widget_gallery()
        st.markdown("---")
        st.markdown(
            "After adding widgets, go to the Dashboard tab to configure them. "
            "Click the refresh (🔄) button on any widget to configure its properties."
        )

    with tab3:
        render_dashboard_management()
        st.markdown("---")
        st.markdown(
            "Save your custom dashboard to load it later. Export/import allows you to "
            "share dashboards between different installations."
        )

    # Edit mode toggle
    st.sidebar.subheader("Dashboard Settings")
    if st.sidebar.checkbox("Enable Edit Mode", value=st.session_state.get("edit_mode", False)):
        st.session_state.edit_mode = True
        st.sidebar.info("Edit mode enabled - Click refresh on widgets to configure")
    else:
        st.session_state.edit_mode = False
        st.sidebar.info("Edit mode disabled")

    # Current dashboard info
    st.sidebar.markdown("---")
    st.sidebar.subheader("Current Dashboard")
    st.sidebar.write(f"Name: {st.session_state.get('dashboard_name', 'default')}")
    st.sidebar.write(f"Widgets: {len(st.session_state.get('dashboard_layout', []))}")

    # Clear dashboard
    if st.sidebar.button("Clear All Widgets", type="secondary"):
        st.session_state.dashboard_layout = []
        st.rerun()


if __name__ == "__main__":
    render()
