"""Overview page for dashboard.

Displays system summary, key metrics, and recent activity.
"""

from __future__ import annotations

import streamlit as st

from dgas.dashboard.components.charts import (
    create_metric_card,
    create_bar_chart,
    create_pie_chart,
)
from dgas.dashboard.components.database import (
    fetch_system_overview,
    fetch_data_inventory,
    fetch_predictions,
    fetch_backtest_results,
)
from dgas.dashboard.components.utils import (
    format_number,
    format_percentage,
    download_dataframe,
    create_filter_panel,
    apply_filters_to_dataframe,
)
from dgas.dashboard.components.notifications import (
    show_new_notifications,
    render_notification_summary,
)
from dgas.dashboard.utils.alert_rules import check_signal, check_prediction, check_backtest


def render() -> None:
    """Render the Overview page."""
    st.header("System Overview")
    st.markdown("Key metrics and recent activity across the DGAS system.")

    # Show new notifications
    show_new_notifications()

    # Load data first
    try:
        system_overview = fetch_system_overview()
        data_inventory = fetch_data_inventory()
        recent_predictions = fetch_predictions(days=7)
        recent_backtests = fetch_backtest_results(limit=5)
    except Exception as e:
        st.error(f"Error loading data: {e}")
        return

    # Check data against alert rules (after data is loaded)
    try:
        if not recent_predictions.empty:
            # Check latest prediction
            latest_pred = recent_predictions.iloc[0].to_dict()
            check_prediction(latest_pred)

        if not recent_backtests.empty:
            # Check latest backtest
            latest_bt = recent_backtests.iloc[0].to_dict()
            check_backtest(latest_bt)
    except Exception as e:
        st.error(f"Error checking alert rules: {e}")

    # Key metrics row
    st.subheader("Key Metrics")
    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:
        create_metric_card(
            "Total Symbols",
            format_number(system_overview.get("total_symbols", 0)),
            help_text="Number of symbols in database",
        )

    with col2:
        create_metric_card(
            "Total Data Bars",
            format_number(system_overview.get("total_data_bars", 0)),
            help_text="Total market data bars",
        )

    with col3:
        create_metric_card(
            "Predictions (24h)",
            format_number(system_overview.get("predictions_24h", 0)),
            help_text="Predictions in last 24 hours",
        )

    with col4:
        create_metric_card(
            "Signals (24h)",
            format_number(system_overview.get("signals_24h", 0)),
            help_text="Trading signals in last 24 hours",
        )

    with col5:
        create_metric_card(
            "Recent Data Coverage",
            f"{system_overview.get('symbols_with_recent_data', 0)} symbols",
            help_text="Symbols with data in last 24 hours",
        )

    st.markdown("---")

    # Data coverage
    st.subheader("Data Coverage by Symbol")
    if not data_inventory.empty:
        col1, col2 = st.columns([2, 1])

        with col1:
            # Bar chart of data coverage
            chart_data = data_inventory.copy()
            fig = create_bar_chart(
                chart_data,
                x_col="symbol",
                y_col="bar_count",
                title="Data Bars by Symbol",
                color_col="exchange" if "exchange" in chart_data.columns else None,
            )
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            st.markdown("**Data Summary**")
            st.metric(
                "Total Symbols",
                len(data_inventory),
                help="Number of symbols tracked",
            )
            st.metric(
                "Total Bars",
                data_inventory["bar_count"].sum(),
                help="Total market data bars",
            )
            st.metric(
                "Avg Bars/Symbol",
                int(data_inventory["bar_count"].mean()),
                help="Average bars per symbol",
            )

    st.markdown("---")

    # Recent predictions
    st.subheader("Recent Predictions")
    if not recent_predictions.empty:
        # Filters
        filters = create_filter_panel(recent_predictions)
        filtered_predictions = apply_filters_to_dataframe(recent_predictions, filters)

        st.dataframe(
            filtered_predictions,
            use_container_width=True,
            hide_index=True,
        )

        st.markdown("Predictions breakdown:")
        col1, col2 = st.columns(2)

        with col1:
            # Signal type distribution
            if "signal_type" in filtered_predictions.columns:
                signal_dist = (
                    filtered_predictions["signal_type"]
                    .value_counts()
                    .reset_index()
                )
                # value_counts().reset_index() creates columns: [original_column_name, 'count']
                # Use the actual column names that exist in the dataframe
                names_col = signal_dist.columns[0]  # First column is the signal_type values
                values_col = signal_dist.columns[1]  # Second column is the count
                
                fig = create_pie_chart(
                    signal_dist,
                    names_col=names_col,
                    values_col=values_col,
                    title="Signal Type Distribution",
                )
                st.plotly_chart(fig, use_container_width=True)

        with col2:
            # Confidence distribution
            if "confidence" in filtered_predictions.columns:
                st.markdown("**Confidence Stats**")
                st.metric(
                    "Avg Confidence",
                    f"{filtered_predictions['confidence'].mean():.2f}",
                )
                st.metric(
                    "High Confidence (>0.8)",
                    len(filtered_predictions[filtered_predictions["confidence"] > 0.8]),
                )

        # Download
        st.markdown("---")
        download_dataframe(filtered_predictions, "recent_predictions.csv")
    else:
        st.info("No recent predictions found.")

    st.markdown("---")

    # Recent backtests
    st.subheader("Recent Backtests")
    if not recent_backtests.empty:
        # Display backtest summary
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric(
                "Total Backtests",
                len(recent_backtests),
                help="Number of recent backtests",
            )

        with col2:
            if "total_return" in recent_backtests.columns:
                avg_return = recent_backtests["total_return"].mean()
                st.metric(
                    "Avg Return",
                    format_percentage(avg_return / 100) if avg_return else "N/A",
                    help="Average return across backtests",
                )

        with col3:
            if "sharpe_ratio" in recent_backtests.columns:
                avg_sharpe = recent_backtests["sharpe_ratio"].mean()
                st.metric(
                    "Avg Sharpe Ratio",
                    f"{avg_sharpe:.2f}" if avg_sharpe else "N/A",
                    help="Average Sharpe ratio",
                )

        with col4:
            if "max_drawdown" in recent_backtests.columns:
                max_dd = recent_backtests["max_drawdown"].min()
                st.metric(
                    "Max Drawdown",
                    format_percentage(abs(max_dd) / 100) if max_dd else "N/A",
                    help="Largest drawdown",
                )

        # Backtest table
        st.markdown("**Backtest Results**")
        display_cols = [
            "backtest_id",
            "strategy_name",
            "symbol",
            "start_date",
            "end_date",
            "total_return",
            "sharpe_ratio",
            "max_drawdown",
        ]
        st.dataframe(
            recent_backtests[display_cols],
            use_container_width=True,
            hide_index=True,
        )

        # Download
        download_dataframe(recent_backtests, "recent_backtests.csv")
    else:
        st.info("No recent backtests found.")

    st.markdown("---")

    # Notifications section
    st.subheader("Notifications")
    tab1, tab2 = st.tabs(["Summary", "Settings"])

    with tab1:
        render_notification_summary()

    with tab2:
        from dgas.dashboard.components.notifications import render_notification_settings
        render_notification_settings()


if __name__ == "__main__":
    render()
