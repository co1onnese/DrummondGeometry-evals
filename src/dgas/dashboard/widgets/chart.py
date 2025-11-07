"""Chart widget for displaying various chart types.

Supports line, bar, scatter, pie, and histogram charts.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, List

import streamlit as st
import pandas as pd

from dgas.dashboard.widgets.base import BaseWidget, WidgetConfig
from dgas.dashboard.components.database import (
    fetch_data_inventory,
    fetch_predictions,
    fetch_backtest_results,
    fetch_data_quality_stats,
)
from dgas.dashboard.components.charts import (
    create_line_chart,
    create_bar_chart,
    create_scatter_chart,
    create_pie_chart,
    create_histogram,
)


class ChartWidget(BaseWidget):
    """Widget for displaying charts."""

    @property
    def widget_type(self) -> str:
        """Widget type identifier."""
        return "chart"

    def fetch_data(self) -> Dict[str, Any]:
        """Fetch chart data."""
        data_source = self.config.data_source
        properties = self.config.properties or {}
        chart_type = properties.get("chart_type", "bar")

        if data_source == "data_inventory":
            df = fetch_data_inventory()
            if not df.empty:
                if chart_type == "bar":
                    # Show bar count by symbol
                    return {
                        "data": df,
                        "x_col": "symbol",
                        "y_col": "bar_count",
                        "title": properties.get("title", "Data Inventory"),
                    }
                elif chart_type == "histogram":
                    return {
                        "data": df,
                        "x_col": "bar_count",
                        "title": properties.get("title", "Distribution of Bar Counts"),
                    }

        elif data_source == "predictions":
            df = fetch_predictions(days=properties.get("days", 7))
            if not df.empty:
                if chart_type == "scatter":
                    return {
                        "data": df,
                        "x_col": "confidence",
                        "y_col": "risk_reward_ratio",
                        "color_col": "signal_type",
                        "title": properties.get("title", "Signal Analysis"),
                    }
                elif chart_type == "pie":
                    signal_counts = df["signal_type"].value_counts().reset_index()
                    signal_counts.columns = ["signal_type", "count"]
                    return {
                        "data": signal_counts,
                        "names_col": "signal_type",
                        "values_col": "count",
                        "title": properties.get("title", "Signal Distribution"),
                    }
                elif chart_type == "line":
                    # Group by day
                    df["date"] = pd.to_datetime(df["signal_timestamp"]).dt.date
                    daily_counts = df.groupby(["date", "signal_type"]).size().reset_index(name="count")
                    return {
                        "data": daily_counts,
                        "x_col": "date",
                        "y_col": "count",
                        "color_col": "signal_type",
                        "title": properties.get("title", "Signal Timeline"),
                    }

        elif data_source == "backtests":
            df = fetch_backtest_results(limit=properties.get("limit", 20))
            if not df.empty:
                if chart_type == "bar":
                    return {
                        "data": df,
                        "x_col": "symbol",
                        "y_col": "total_return",
                        "title": properties.get("title", "Backtest Returns"),
                    }
                elif chart_type == "scatter":
                    return {
                        "data": df,
                        "x_col": "total_return",
                        "y_col": "sharpe_ratio",
                        "color_col": "symbol",
                        "title": properties.get("title", "Risk vs Return"),
                    }
                elif chart_type == "histogram":
                    return {
                        "data": df,
                        "x_col": "total_return",
                        "title": properties.get("title", "Return Distribution"),
                    }

        elif data_source == "data_quality":
            df = fetch_data_quality_stats(interval=properties.get("interval", "30min"))
            if not df.empty:
                return {
                    "data": df,
                    "x_col": "symbol",
                    "y_col": "bar_count",
                    "title": properties.get("title", "Data Quality"),
                }

        return {"data": pd.DataFrame(), "title": "No Data"}

    def render(self) -> None:
        """Render the chart widget."""
        # Update data if needed
        if self.data is None:
            self.update_data()

        # Validate
        errors = self.validate_config()
        if errors:
            self.render_error("; ".join(errors))
            return

        # Render header
        self.render_header()

        # Render chart
        if self.data and "data" in self.data and not self.data["data"].empty:
            chart_type = self.config.properties.get("chart_type", "bar")
            title = self.data.get("title", "Chart")
            data = self.data["data"]

            try:
                if chart_type == "line":
                    fig = create_line_chart(
                        data,
                        x_col=self.data["x_col"],
                        y_col=self.data["y_col"],
                        title=title,
                        color_col=self.data.get("color_col"),
                    )
                elif chart_type == "bar":
                    fig = create_bar_chart(
                        data,
                        x_col=self.data["x_col"],
                        y_col=self.data["y_col"],
                        title=title,
                        color_col=self.data.get("color_col"),
                    )
                elif chart_type == "scatter":
                    fig = create_scatter_chart(
                        data,
                        x_col=self.data["x_col"],
                        y_col=self.data["y_col"],
                        color_col=self.data.get("color_col"),
                        title=title,
                    )
                elif chart_type == "pie":
                    fig = create_pie_chart(
                        data,
                        names_col=self.data["names_col"],
                        values_col=self.data["values_col"],
                        title=title,
                    )
                elif chart_type == "histogram":
                    fig = create_histogram(
                        data,
                        x_col=self.data["x_col"],
                        title=title,
                    )
                else:
                    st.error(f"Unsupported chart type: {chart_type}")
                    return

                st.plotly_chart(fig, use_container_width=True)

            except Exception as e:
                st.error(f"Error rendering chart: {e}")
        else:
            st.info("No data available for chart")

        # Render data source info
        self.render_data_source_info()

    def get_config_options(self) -> Dict[str, Any]:
        """
        Get configuration options for this widget type.

        Returns:
            Dictionary of configuration options
        """
        return {
            "data_sources": self.get_data_source_options(),
            "chart_types": ["line", "bar", "scatter", "pie", "histogram"],
            "properties": {
                "predictions": ["days"],
                "backtests": ["limit"],
                "data_quality": ["interval"],
            },
        }


# Register widget
from dgas.dashboard.widgets.base import WidgetRegistry
WidgetRegistry.register("chart", ChartWidget)
