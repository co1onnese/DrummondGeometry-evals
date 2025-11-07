"""Metric widget for displaying key performance indicators.

Shows metrics like totals, averages, and counts.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import streamlit as st
import pandas as pd

from dgas.dashboard.widgets.base import BaseWidget, WidgetConfig
from dgas.dashboard.components.database import (
    fetch_system_overview,
    fetch_data_inventory,
    fetch_predictions,
    fetch_backtest_results,
    fetch_system_status,
)
from dgas.dashboard.components.charts import format_number, format_percentage, format_currency


class MetricWidget(BaseWidget):
    """Widget for displaying metric cards."""

    @property
    def widget_type(self) -> str:
        """Widget type identifier."""
        return "metric"

    def fetch_data(self) -> Dict[str, Any]:
        """Fetch metric data."""
        data_source = self.config.data_source
        properties = self.config.properties or {}

        if data_source == "system_overview":
            data = fetch_system_overview()
            metric_key = properties.get("metric_key", "total_symbols")
            return {
                "value": data.get(metric_key, 0),
                "label": properties.get("label", "Total"),
                "format": properties.get("format", "number"),
                "delta": properties.get("delta"),
                "help": properties.get("help"),
            }

        elif data_source == "predictions":
            predictions = fetch_predictions(days=properties.get("days", 7))
            if not predictions.empty:
                # Get specific metric
                metric_type = properties.get("metric_type", "count")
                if metric_type == "count":
                    value = len(predictions)
                elif metric_type == "avg_confidence":
                    value = predictions["confidence"].mean()
                elif metric_type == "high_confidence_count":
                    value = len(predictions[predictions["confidence"] > 0.8])
                else:
                    value = len(predictions)

                return {
                    "value": value,
                    "label": properties.get("label", "Predictions"),
                    "format": properties.get("format", "number"),
                    "delta": properties.get("delta"),
                    "help": properties.get("help"),
                }
            return {"value": 0, "label": "No Data", "format": "number"}

        elif data_source == "backtests":
            backtests = fetch_backtest_results(limit=properties.get("limit", 10))
            if not backtests.empty:
                metric_type = properties.get("metric_type", "count")
                if metric_type == "count":
                    value = len(backtests)
                elif metric_type == "avg_return":
                    value = backtests["total_return"].mean()
                elif metric_type == "avg_sharpe":
                    value = backtests["sharpe_ratio"].mean()
                else:
                    value = len(backtests)

                return {
                    "value": value,
                    "label": properties.get("label", "Backtests"),
                    "format": properties.get("format", "number"),
                    "delta": properties.get("delta"),
                    "help": properties.get("help"),
                }
            return {"value": 0, "label": "No Data", "format": "number"}

        elif data_source == "system_status":
            status = fetch_system_status()
            if "data_coverage" in status:
                metric_key = properties.get("metric_key", "symbols_24h")
                value = status["data_coverage"].get(metric_key, 0)
                return {
                    "value": value,
                    "label": properties.get("label", "Data Coverage"),
                    "format": properties.get("format", "number"),
                    "delta": properties.get("delta"),
                    "help": properties.get("help"),
                }
            return {"value": 0, "label": "No Data", "format": "number"}

        else:
            return {"value": 0, "label": "Unknown Source", "format": "number"}

    def render(self) -> None:
        """Render the metric widget."""
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

        # Render metric
        if self.data:
            value = self.data["value"]
            label = self.data["label"]
            format_type = self.data.get("format", "number")
            delta = self.data.get("delta")
            help_text = self.data.get("help")

            # Format value
            if format_type == "number":
                display_value = format_number(value)
            elif format_type == "percentage":
                display_value = format_percentage(value / 100)
            elif format_type == "currency":
                display_value = format_currency(value)
            else:
                display_value = str(value)

            # Display metric
            st.metric(
                label=label,
                value=display_value,
                delta=delta,
                help=help_text,
            )

            # Render data source info
            self.render_data_source_info()
        else:
            st.info("No data available")

    def get_config_options(self) -> Dict[str, Any]:
        """
        Get configuration options for this widget type.

        Returns:
            Dictionary of configuration options
        """
        return {
            "data_sources": self.get_data_source_options(),
            "formats": ["number", "percentage", "currency"],
            "metric_keys": {
                "system_overview": ["total_symbols", "total_data_bars", "predictions_24h", "signals_24h"],
                "predictions": ["count", "avg_confidence", "high_confidence_count"],
                "backtests": ["count", "avg_return", "avg_sharpe"],
                "system_status": ["symbols_24h"],
            },
        }


# Register widget
from dgas.dashboard.widgets.base import WidgetRegistry
WidgetRegistry.register("metric", MetricWidget)
