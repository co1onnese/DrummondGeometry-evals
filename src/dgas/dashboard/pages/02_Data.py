"""Data page for dashboard.

Displays data inventory, quality statistics, and data management tools.
"""

from __future__ import annotations

import streamlit as st

from dgas.dashboard.components.charts import (
    create_bar_chart,
    create_histogram,
    create_data_coverage_heatmap,
)
from dgas.dashboard.components.database import (
    fetch_data_inventory,
    fetch_data_quality_stats,
)
from dgas.dashboard.components.utils import (
    format_number,
    format_timestamp,
    download_dataframe,
    create_filter_panel,
    apply_filters_to_dataframe,
)


def render() -> None:
    """Render the Data page."""
    st.header("Data Management")
    st.markdown("Market data inventory, quality metrics, and coverage analysis.")

    # Tabs
    tab1, tab2, tab3 = st.tabs(["Data Inventory", "Quality Statistics", "Coverage Analysis"])

    with tab1:
        st.subheader("Data Inventory")
        st.markdown("Overview of all market data in the system.")

        try:
            data_inventory = fetch_data_inventory()
        except Exception as e:
            st.error(f"Error loading data: {e}")
            return

        if data_inventory.empty:
            st.info("No data inventory found.")
            return

        # Filters
        filters = create_filter_panel(data_inventory)
        filtered_data = apply_filters_to_dataframe(data_inventory, filters)

        # Summary metrics
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric(
                "Total Symbols",
                len(filtered_data),
                help="Number of symbols",
            )

        with col2:
            st.metric(
                "Total Bars",
                format_number(filtered_data["bar_count"].sum()),
                help="Total market data bars",
            )

        with col3:
            st.metric(
                "Avg Bars/Symbol",
                format_number(int(filtered_data["bar_count"].mean())),
                help="Average bars per symbol",
            )

        with col4:
            if "bar_count" in filtered_data.columns:
                max_bars = filtered_data["bar_count"].max()
                st.metric(
                    "Max Bars/Symbol",
                    format_number(max_bars),
                    help="Maximum bars for a single symbol",
                )

        st.markdown("---")

        # Data distribution chart
        st.subheader("Data Distribution")
        col1, col2 = st.columns(2)

        with col1:
            # Histogram of bar counts
            fig = create_histogram(
                filtered_data,
                x_col="bar_count",
                title="Distribution of Data Bars",
                nbins=20,
            )
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            # Bar chart by symbol
            if len(filtered_data) <= 50:  # Only show if not too many
                fig = create_bar_chart(
                    filtered_data.sort_values("bar_count", ascending=False).head(20),
                    x_col="symbol",
                    y_col="bar_count",
                    title="Top 20 Symbols by Bar Count",
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("Too many symbols to display. Use filters to narrow down.")

        st.markdown("---")

        # Data table
        st.subheader("Detailed Data Inventory")
        st.dataframe(
            filtered_data,
            use_container_width=True,
            hide_index=True,
        )

        # Download
        st.markdown("---")
        download_dataframe(filtered_data, "data_inventory.csv")

    with tab2:
        st.subheader("Data Quality Statistics")
        st.markdown("Analysis of data completeness and quality metrics.")

        try:
            # Interval selector
            interval = st.selectbox(
                "Data Interval",
                options=["30min", "1h", "4h", "1d"],
                index=0,
                help="Select data interval to analyze",
            )

            quality_stats = fetch_data_quality_stats(interval=interval)
        except Exception as e:
            st.error(f"Error loading quality stats: {e}")
            return

        if quality_stats.empty:
            st.info(f"No quality statistics found for {interval} interval.")
            return

        # Quality metrics
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric(
                "Total Symbols",
                len(quality_stats),
            )

        with col2:
            total_bars = quality_stats["bar_count"].sum()
            st.metric(
                "Total Bars",
                format_number(total_bars),
            )

        with col3:
            total_missing = quality_stats["estimated_missing"].sum()
            st.metric(
                "Estimated Missing",
                format_number(total_missing),
                help="Estimated number of missing bars",
            )

        with col4:
            if total_bars > 0:
                completeness = (total_bars / (total_bars + total_missing)) * 100
                st.metric(
                    "Data Completeness",
                    f"{completeness:.1f}%",
                    help="Percentage of data completeness",
                )

        st.markdown("---")

        # Quality visualization
        st.subheader("Quality Visualization")
        col1, col2 = st.columns(2)

        with col1:
            # Missing data by symbol
            if len(quality_stats) <= 50:
                fig = create_bar_chart(
                    quality_stats.sort_values("estimated_missing", ascending=False).head(20),
                    x_col="symbol",
                    y_col="estimated_missing",
                    title="Top Symbols by Missing Data",
                )
                st.plotly_chart(fig, use_container_width=True)

        with col2:
            # Coverage percentage
            quality_stats_copy = quality_stats.copy()
            quality_stats_copy["coverage_pct"] = (
                quality_stats_copy["bar_count"]
                / quality_stats_copy["bar_count"].max() * 100
            )

            fig = create_bar_chart(
                quality_stats_copy.sort_values("coverage_pct", ascending=False).head(20),
                x_col="symbol",
                y_col="coverage_pct",
                title="Top Symbols by Coverage %",
            )
            st.plotly_chart(fig, use_container_width=True)

        st.markdown("---")

        # Quality table
        st.subheader("Detailed Quality Statistics")
        quality_display = quality_stats.copy()
        quality_display["data_completeness"] = (
            quality_display["bar_count"]
            / (quality_display["bar_count"] + quality_display["estimated_missing"])
            * 100
        ).round(2)

        st.dataframe(
            quality_display,
            use_container_width=True,
            hide_index=True,
        )

        # Download
        st.markdown("---")
        download_dataframe(quality_display, f"data_quality_{interval}.csv")

    with tab3:
        st.subheader("Data Coverage Analysis")
        st.markdown("Visualization of data coverage across all symbols.")

        try:
            data_inventory = fetch_data_inventory()
        except Exception as e:
            st.error(f"Error loading data: {e}")
            return

        if data_inventory.empty:
            st.info("No data for coverage analysis.")
            return

        # Coverage heatmap
        st.markdown("**Coverage Heatmap**")
        fig = create_data_coverage_heatmap(data_inventory)
        st.plotly_chart(fig, use_container_width=True)

        st.markdown("---")

        # Coverage by exchange
        if "exchange" in data_inventory.columns:
            st.subheader("Coverage by Exchange")
            exchange_stats = (
                data_inventory.groupby("exchange")
                .agg({"bar_count": "sum", "symbol": "count"})
                .reset_index()
                .rename(columns={"symbol": "symbol_count"})
            )

            col1, col2 = st.columns(2)

            with col1:
                fig = create_bar_chart(
                    exchange_stats,
                    x_col="exchange",
                    y_col="symbol_count",
                    title="Symbols by Exchange",
                )
                st.plotly_chart(fig, use_container_width=True)

            with col2:
                fig = create_bar_chart(
                    exchange_stats,
                    x_col="exchange",
                    y_col="bar_count",
                    title="Data Bars by Exchange",
                )
                st.plotly_chart(fig, use_container_width=True)

        st.markdown("---")

        # Date range analysis
        st.subheader("Data Time Range")
        data_range = data_inventory.copy()
        data_range["first_timestamp"] = data_range["first_timestamp"]
        data_range["last_timestamp"] = data_range["last_timestamp"]

        st.dataframe(
            data_range[["symbol", "first_timestamp", "last_timestamp", "bar_count"]],
            use_container_width=True,
            hide_index=True,
        )


if __name__ == "__main__":
    render()
