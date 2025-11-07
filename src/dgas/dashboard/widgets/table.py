"""Table widget for displaying tabular data.

Shows data in a sortable, filterable table format.
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
    fetch_system_status,
)
from dgas.dashboard.components.utils import paginate_dataframe, download_dataframe


class TableWidget(BaseWidget):
    """Widget for displaying data tables."""

    @property
    def widget_type(self) -> str:
        """Widget type identifier."""
        return "table"

    def fetch_data(self) -> Dict[str, Any]:
        """Fetch table data."""
        data_source = self.config.data_source
        properties = self.config.properties or {}

        if data_source == "data_inventory":
            df = fetch_data_inventory()
            return {
                "data": df,
                "title": properties.get("title", "Data Inventory"),
                "columns": properties.get("columns", []),
            }

        elif data_source == "predictions":
            df = fetch_predictions(days=properties.get("days", 7))
            return {
                "data": df,
                "title": properties.get("title", "Predictions"),
                "columns": properties.get("columns", []),
            }

        elif data_source == "backtests":
            df = fetch_backtest_results(limit=properties.get("limit", 10))
            return {
                "data": df,
                "title": properties.get("title", "Backtest Results"),
                "columns": properties.get("columns", []),
            }

        elif data_source == "system_status":
            status = fetch_system_status()
            # Convert status to DataFrame
            status_data = []
            for key, value in status.items():
                if isinstance(value, dict):
                    for subkey, subvalue in value.items():
                        status_data.append({"Component": key, "Metric": subkey, "Value": subvalue})
                else:
                    status_data.append({"Component": "System", "Metric": key, "Value": value})

            df = pd.DataFrame(status_data)
            return {
                "data": df,
                "title": properties.get("title", "System Status"),
                "columns": properties.get("columns", []),
            }

        else:
            return {"data": pd.DataFrame(), "title": "No Data", "columns": []}

    def render(self) -> None:
        """Render the table widget."""
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

        # Render table
        if self.data and "data" in self.data and not self.data["data"].empty:
            df = self.data["data"]
            columns = self.data.get("columns", [])

            # Select columns if specified
            if columns:
                available_cols = [col for col in columns if col in df.columns]
                if available_cols:
                    df = df[available_cols]

            # Pagination
            page_size = self.config.properties.get("page_size", 20)
            paginated_df, total_pages = paginate_dataframe(df, page_size=page_size)

            # Display table
            st.dataframe(
                paginated_df,
                use_container_width=True,
                hide_index=True,
            )

            # Show pagination info
            st.caption(f"Showing {len(paginated_df)} of {len(df)} rows")

            # Download button
            st.markdown("---")
            download_dataframe(df, f"{self.config.data_source}_export.csv")

        else:
            st.info("No data available for table")

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
            "properties": {
                "predictions": ["days"],
                "backtests": ["limit"],
            },
            "page_sizes": [10, 20, 50, 100],
        }


# Register widget
from dgas.dashboard.widgets.base import WidgetRegistry
WidgetRegistry.register("table", TableWidget)
