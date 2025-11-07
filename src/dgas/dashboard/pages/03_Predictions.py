"""Predictions page for dashboard.

Displays prediction signals, performance metrics, and signal analysis.
"""

from __future__ import annotations

import streamlit as st

from dgas.dashboard.components.charts import (
    create_scatter_chart,
    create_line_chart,
    create_histogram,
    create_signal_timeline,
    format_currency,
    format_percentage,
)
from dgas.dashboard.components.database import fetch_predictions
from dgas.dashboard.components.utils import (
    format_timestamp,
    download_dataframe,
    create_filter_panel,
    apply_filters_to_dataframe,
    safe_float,
)
import pandas as pd


def render() -> None:
    """Render the Predictions page."""
    st.header("Predictions & Signals")
    st.markdown("Analysis of trading signals, predictions, and signal performance.")

    # Sidebar controls
    st.sidebar.subheader("Filters")
    days = st.sidebar.slider(
        "Time Period (days)",
        min_value=1,
        max_value=90,
        value=7,
        help="Number of days of data to display",
    )

    symbols = st.sidebar.multiselect(
        "Symbols",
        options=[],
        default=[],
        help="Filter by specific symbols",
    )

    min_confidence = st.sidebar.slider(
        "Min Confidence",
        min_value=0.0,
        max_value=1.0,
        value=0.0,
        step=0.1,
        help="Minimum confidence threshold",
    )

    signal_type = st.sidebar.selectbox(
        "Signal Type",
        options=["All", "BUY", "SELL"],
        index=0,
        help="Filter by signal type",
    )

    # Load data
    try:
        predictions = fetch_predictions(days=days, min_confidence=min_confidence)
    except Exception as e:
        st.error(f"Error loading predictions: {e}")
        return

    if predictions.empty:
        st.info("No predictions found for the selected criteria.")
        return

    # Apply additional filters
    if symbols:
        predictions = predictions[predictions["symbol"].isin(symbols)]

    if signal_type != "All":
        predictions = predictions[predictions["signal_type"] == signal_type]

    # Key metrics
    st.subheader("Signal Metrics")
    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:
        st.metric(
            "Total Signals",
            len(predictions),
            help="Total number of signals",
        )

    with col2:
        if "confidence" in predictions.columns:
            avg_confidence = predictions["confidence"].mean()
            st.metric(
                "Avg Confidence",
                f"{avg_confidence:.2f}",
                help="Average signal confidence",
            )

    with col3:
        if "signal_type" in predictions.columns:
            buy_count = len(predictions[predictions["signal_type"] == "BUY"])
            st.metric(
                "Buy Signals",
                buy_count,
                help="Number of buy signals",
            )

    with col4:
        if "signal_type" in predictions.columns:
            sell_count = len(predictions[predictions["signal_type"] == "SELL"])
            st.metric(
                "Sell Signals",
                sell_count,
                help="Number of sell signals",
            )

    with col5:
        if "risk_reward_ratio" in predictions.columns:
            avg_rr = predictions["risk_reward_ratio"].mean()
            st.metric(
                "Avg R:R",
                f"{avg_rr:.2f}",
                help="Average risk-reward ratio",
            )

    st.markdown("---")

    # Tabs
    tab1, tab2, tab3, tab4 = st.tabs(
        ["Signal Analysis", "Timeline", "Performance", "Raw Data"]
    )

    with tab1:
        st.subheader("Signal Analysis")
        col1, col2 = st.columns(2)

        with col1:
            # Confidence distribution
            if "confidence" in predictions.columns:
                fig = create_histogram(
                    predictions,
                    x_col="confidence",
                    title="Signal Confidence Distribution",
                    nbins=20,
                )
                st.plotly_chart(fig, use_container_width=True)

        with col2:
            # Risk-reward distribution
            if "risk_reward_ratio" in predictions.columns:
                fig = create_histogram(
                    predictions,
                    x_col="risk_reward_ratio",
                    title="Risk-Reward Ratio Distribution",
                    nbins=20,
                )
                st.plotly_chart(fig, use_container_width=True)

        st.markdown("---")

        # Scatter plot: confidence vs risk-reward
        st.subheader("Confidence vs Risk-Reward")
        scatter_data = predictions.copy()
        if "signal_strength" in scatter_data.columns:
            fig = create_scatter_chart(
                scatter_data,
                x_col="confidence",
                y_col="risk_reward_ratio",
                size_col="signal_strength",
                color_col="signal_type",
                title="Signal Analysis: Confidence vs Risk-Reward",
            )
            st.plotly_chart(fig, use_container_width=True)

    with tab2:
        st.subheader("Signal Timeline")
        st.markdown("Temporal view of all signals over time.")

        # Create timeline
        if "signal_timestamp" in predictions.columns:
            # Convert timestamps
            timeline_data = predictions.copy()
            timeline_data["signal_timestamp"] = timeline_data["signal_timestamp"]

            # Filter for timeline display
            if len(timeline_data) > 500:
                st.warning(
                    f"Displaying first 500 of {len(timeline_data)} signals for performance."
                )
                timeline_data = timeline_data.head(500)

            fig = create_signal_timeline(timeline_data)
            st.plotly_chart(fig, use_container_width=True)

        st.markdown("---")

        # Signal volume over time
        st.subheader("Signal Volume by Time")
        if "signal_timestamp" in predictions.columns:
            time_data = predictions.copy()
            time_data["signal_timestamp"] = pd.to_datetime(time_data["signal_timestamp"])
            time_data["date"] = time_data["signal_timestamp"].dt.date

            daily_counts = (
                time_data.groupby(["date", "signal_type"])
                .size()
                .reset_index(name="count")
            )

            fig = create_line_chart(
                daily_counts,
                x_col="date",
                y_col="count",
                color_col="signal_type",
                title="Daily Signal Volume",
            )
            st.plotly_chart(fig, use_container_width=True)

    with tab3:
        st.subheader("Signal Performance")
        st.markdown("Analysis of signal characteristics and potential performance.")

        col1, col2, col3 = st.columns(3)

        with col1:
            st.markdown("**Price Targets**")
            if "entry_price" in predictions.columns:
                st.metric(
                    "Avg Entry Price",
                    format_currency(predictions["entry_price"].mean()),
                )
            if "target_price" in predictions.columns:
                st.metric(
                    "Avg Target Price",
                    format_currency(predictions["target_price"].mean()),
                )

        with col2:
            st.markdown("**Stop Loss**")
            if "stop_loss" in predictions.columns:
                st.metric(
                    "Avg Stop Loss",
                    format_currency(predictions["stop_loss"].mean()),
                )

        with col3:
            st.markdown("**Signal Strength**")
            if "signal_strength" in predictions.columns:
                st.metric(
                    "Avg Signal Strength",
                    f"{predictions['signal_strength'].mean():.2f}",
                )

        st.markdown("---")

        # Risk-reward analysis
        st.subheader("Risk-Reward Analysis")
        if "risk_reward_ratio" in predictions.columns:
            rr_stats = predictions["risk_reward_ratio"].describe()
            col1, col2, col3, col4 = st.columns(4)

            with col1:
                st.metric("Min R:R", f"{rr_stats['min']:.2f}")
            with col2:
                st.metric("Avg R:R", f"{rr_stats['mean']:.2f}")
            with col3:
                st.metric("Median R:R", f"{rr_stats['50%']:.2f}")
            with col4:
                st.metric("Max R:R", f"{rr_stats['max']:.2f}")

    with tab4:
        st.subheader("Raw Signal Data")
        st.markdown("Complete dataset of all prediction signals.")

        # Display options
        col1, col2 = st.columns(2)

        with col1:
            max_display = st.slider(
                "Max rows to display",
                min_value=10,
                max_value=1000,
                value=100,
                help="Limit the number of rows displayed",
            )

        with col2:
            show_details = st.checkbox(
                "Show all columns",
                value=False,
                help="Show all data columns",
            )

        # Data table
        display_data = predictions.copy()

        if not show_details:
            # Select key columns
            key_cols = [
                "symbol",
                "signal_type",
                "confidence",
                "signal_timestamp",
                "entry_price",
                "target_price",
                "stop_loss",
                "risk_reward_ratio",
            ]
            display_cols = [col for col in key_cols if col in display_data.columns]
            display_data = display_data[display_cols]

        # Sort by timestamp
        if "signal_timestamp" in display_data.columns:
            display_data = display_data.sort_values("signal_timestamp", ascending=False)

        # Limit display
        display_data = display_data.head(max_display)

        st.dataframe(
            display_data,
            use_container_width=True,
            hide_index=True,
        )

        st.markdown(f"Showing {len(display_data)} of {len(predictions)} signals")

        # Download
        st.markdown("---")
        download_dataframe(predictions, f"predictions_{days}days.csv")


if __name__ == "__main__":
    render()
