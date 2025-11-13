"""System Status page for dashboard.

Displays real-time system health, monitoring, and diagnostic information.
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Dict, Any

import streamlit as st
import pandas as pd

from dgas.dashboard.components.database import fetch_system_status
from dgas.dashboard.components.charts import create_line_chart, create_bar_chart


def render() -> None:
    """Render the System Status page."""
    st.header("System Status")
    st.markdown("Real-time monitoring and health checks for the DGAS system.")

    # Auto-refresh
    st.sidebar.subheader("Auto-refresh")
    auto_refresh = st.sidebar.checkbox(
        "Enable auto-refresh",
        value=False,
        help="Automatically refresh status every 30 seconds",
    )

    if auto_refresh:
        refresh_interval = st.sidebar.slider(
            "Refresh interval (seconds)",
            min_value=10,
            max_value=300,
            value=30,
            step=10,
        )
        st.sidebar.info(f"Refreshing every {refresh_interval} seconds")

        # Set up auto-refresh
        time.sleep(refresh_interval)
        st.experimental_rerun()

    # Load system status
    try:
        system_status = fetch_system_status()
    except Exception as e:
        st.error(f"Error loading system status: {e}")
        return

    # Status overview
    st.subheader("System Health")
    col1, col2, col3 = st.columns(3)

    with col1:
        status = system_status.get("status", "unknown")
        if status == "healthy":
            st.success("🟢 System Healthy", icon="✅")
        else:
            st.error(f"🔴 System Error: {status}", icon="❌")

    with col2:
        last_update = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        st.info(f"Last Updated: {last_update}")

    with col3:
        st.metric("Status", status.capitalize())

    st.markdown("---")

    # WebSocket Status (if available)
    ws_status = system_status.get("websocket")
    if ws_status:
        st.subheader("WebSocket Data Collection")
        if ws_status.get("enabled") is False:
            st.info("WebSocket collection is disabled in configuration")
        elif ws_status.get("enabled") is None:
            st.warning(f"WebSocket status unavailable: {ws_status.get('error', 'Unknown error')}")
        else:
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                if ws_status.get("connected"):
                    st.success("🟢 Connected", icon="✅")
                else:
                    st.error("🔴 Disconnected", icon="❌")
            
            with col2:
                st.metric(
                    "Connections",
                    f"{ws_status.get('connected_count', 0)}/{ws_status.get('connections', 0)}",
                    help="Active WebSocket connections"
                )
            
            with col3:
                st.metric(
                    "Symbols",
                    ws_status.get("total_symbols", 0),
                    help="Total symbols subscribed"
                )
            
            with col4:
                st.metric(
                    "Messages",
                    format(ws_status.get("messages_received", 0), ","),
                    help="Total messages received"
                )
            
            # Additional metrics
            col5, col6 = st.columns(2)
            with col5:
                st.metric(
                    "Bars Buffered",
                    ws_status.get("bars_buffered", 0),
                    help="Bars waiting to be stored"
                )
            with col6:
                st.metric(
                    "Bars Stored",
                    format(ws_status.get("bars_stored", 0), ","),
                    help="Total bars stored from WebSocket"
                )
            
            # Connection details
            if ws_status.get("client_status"):
                with st.expander("Connection Details"):
                    import json
                    st.json(ws_status.get("client_status", {}))

    st.markdown("---")

    # Database status
    st.subheader("Database Status")
    db_status = system_status.get("database", {})

    if db_status:
        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric(
                "Symbols",
                db_status.get("symbols", 0),
                help="Number of symbols in database",
            )

        with col2:
            st.metric(
                "Data Bars",
                db_status.get("data_bars", 0),
                help="Total market data bars",
            )

        with col3:
            st.metric(
                "Database Size",
                db_status.get("size", "N/A"),
                help="Total database size",
            )
    else:
        st.warning("Database status not available")

    st.markdown("---")

    # Data coverage
    st.subheader("Data Coverage")
    coverage = system_status.get("data_coverage", {})

    if coverage:
        col1, col2 = st.columns(2)

        with col1:
            symbols_24h = coverage.get("symbols_24h", 0)
            st.metric(
                "Symbols with 24h Data",
                symbols_24h,
                help="Number of symbols with recent data",
            )

        with col2:
            # Progress bar for coverage
            # Calculate percentage based on total symbols, clamp to [0.0, 1.0]
            total_symbols = db_status.get("symbols", 519)  # Default to 519 if not available
            if total_symbols > 0:
                progress_value = min(symbols_24h / total_symbols, 1.0)
            else:
                progress_value = 0.0
            st.progress(progress_value)
            st.caption(f"Data freshness indicator ({symbols_24h}/{total_symbols} symbols)")
    else:
        st.warning("Data coverage information not available")

    st.markdown("---")

    # Predictions
    st.subheader("Prediction Activity")
    predictions = system_status.get("predictions", {})

    if predictions:
        col1, col2 = st.columns(2)

        with col1:
            runs_24h = predictions.get("runs_24h", 0)
            st.metric(
                "Prediction Runs (24h)",
                runs_24h,
                help="Number of prediction runs in last 24 hours",
            )

        with col2:
            signals_24h = predictions.get("signals_24h", 0)
            st.metric(
                "Signals Generated (24h)",
                signals_24h,
                help="Number of signals in last 24 hours",
            )
    else:
        st.warning("Prediction activity not available")

    st.markdown("---")

    # Backtests
    st.subheader("Backtest Activity")
    backtests = system_status.get("backtests", {})

    if backtests:
        last_7_days = backtests.get("last_7_days", 0)
        st.metric(
            "Backtests (7 days)",
            last_7_days,
            help="Number of backtests in last 7 days",
        )
    else:
        st.warning("Backtest activity not available")

    st.markdown("---")

    # System metrics tabs
    tab1, tab2, tab3 = st.tabs(
        ["Database Metrics", "Activity Timeline", "System Diagnostics"]
    )

    with tab1:
        st.subheader("Database Metrics")
        st.markdown("Detailed database statistics and performance metrics.")

        if db_status:
            # Database stats table
            db_df = pd.DataFrame(
                [
                    {"Metric": "Total Symbols", "Value": db_status.get("symbols", 0)},
                    {"Metric": "Total Data Bars", "Value": db_status.get("data_bars", 0)},
                    {"Metric": "Database Size", "Value": db_status.get("size", "N/A")},
                ]
            )
            st.dataframe(db_df, use_container_width=True, hide_index=True)

            # Data distribution (simulated - would need actual query)
            st.markdown("**Data Distribution by Symbol (Top 10)**")
            # This would require a separate query
            st.info("Data distribution chart would be implemented with actual queries")

        else:
            st.info("No database metrics available")

    with tab2:
        st.subheader("Activity Timeline")
        st.markdown("Timeline of system activity and recent events.")

        # This would require historical data queries
        st.info(
            "Activity timeline would show:\n"
            "- Prediction runs over time\n"
            "- Signal generation trends\n"
            "- Backtest completions\n"
            "- Data ingestion events"
        )

        # Simulated activity chart
        dates = pd.date_range(start="2024-01-01", end="2024-01-30", freq="D")
        activity_data = pd.DataFrame(
            {
                "date": dates,
                "predictions": pd.Series(range(len(dates))) % 10,
                "signals": pd.Series(range(len(dates))) % 20,
            }
        )

        fig = create_line_chart(
            activity_data,
            x_col="date",
            y_col="predictions",
            color_col=None,
            title="Activity Over Time (Simulated)",
        )
        st.plotly_chart(fig, use_container_width=True)

    with tab3:
        st.subheader("System Diagnostics")
        st.markdown("System diagnostics and health check details.")

        # Health checks
        st.markdown("**Health Checks**")
        health_checks = [
            {"Component": "Database", "Status": "✅ Healthy" if db_status else "❌ Error"},
            {
                "Component": "Data Coverage",
                "Status": "✅ Healthy" if coverage else "❌ Warning",
            },
            {
                "Component": "Predictions",
                "Status": "✅ Healthy" if predictions else "❌ Warning",
            },
            {
                "Component": "Backtests",
                "Status": "✅ Healthy" if backtests else "❌ Warning",
            },
        ]

        health_df = pd.DataFrame(health_checks)
        st.dataframe(health_df, use_container_width=True, hide_index=True)

        st.markdown("---")

        # System info
        st.markdown("**System Information**")
        system_info = [
            {"Setting": "Dashboard Version", "Value": "1.0.0"},
            {"Setting": "Streamlit Version", "Value": st.__version__},
            {"Setting": "Python Version", "Value": "3.11+"},
            {"Setting": "Status Check Time", "Value": datetime.now().strftime("%Y-%m-%d %H:%M:%S")},
        ]

        info_df = pd.DataFrame(system_info)
        st.dataframe(info_df, use_container_width=True, hide_index=True)

        st.markdown("---")

        # Log viewer (simulated)
        st.markdown("**Recent Log Entries** (Simulated)")
        log_entries = [
            f"{datetime.now().strftime('%H:%M:%S')} - INFO - Dashboard loaded successfully",
            f"{datetime.now().strftime('%H:%M:%S')} - INFO - Database connection established",
            f"{datetime.now().strftime('%H:%M:%S')} - INFO - System status refreshed",
        ]

        for entry in log_entries:
            st.text(entry)

    # Manual refresh button
    st.markdown("---")
    if st.button("🔄 Refresh Status", use_container_width=True):
        st.experimental_rerun()


if __name__ == "__main__":
    render()
