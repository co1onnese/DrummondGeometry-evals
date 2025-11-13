"""Main Streamlit dashboard application.

This is the entry point for the DGAS dashboard, providing navigation
and integration of all dashboard pages.
"""

from __future__ import annotations

import sys
from typing import NoReturn

import streamlit as st

# Import page modules directly using importlib
from importlib import import_module

Overview = import_module("dgas.dashboard.pages.01_Overview")
Data = import_module("dgas.dashboard.pages.02_Data")
Predictions = import_module("dgas.dashboard.pages.03_Predictions")
Backtests = import_module("dgas.dashboard.pages.04_Backtests")
SystemStatus = import_module("dgas.dashboard.pages.05_System_Status")
CustomDashboard = import_module("dgas.dashboard.pages.06_Custom_Dashboard")
from dgas.dashboard.components.utils import load_dashboard_config
from dgas.dashboard.realtime_client import (
    get_client,
    setup_realtime_client,
    render_websocket_status,
    check_for_updates,
)


def configure_page() -> None:
    """Configure Streamlit page settings."""
    st.set_page_config(
        page_title="DGAS Dashboard",
        page_icon="📊",
        layout="wide",
        initial_sidebar_state="expanded",
        menu_items={
            "Get Help": "https://github.com/dgas/dashboard",
            "Report a bug": "https://github.com/dgas/dashboard/issues",
            "About": "DGAS - Drummond Geometry Analysis System Dashboard",
        },
    )


def render_sidebar() -> str:
    """
    Render sidebar navigation and return selected page.

    Returns:
        Selected page name
    """
    with st.sidebar:
        st.title("DGAS Dashboard")
        st.markdown("---")

        # Navigation menu
        page = st.selectbox(
            "Navigation",
            options=[
                "Overview",
                "Data",
                "Predictions",
                "Backtests",
                "System Status",
                "Custom Dashboard",
            ],
            index=0,
            help="Select a page to view",
        )

        st.markdown("---")

        # Auto-refresh settings
        st.subheader("Settings")
        auto_refresh = st.checkbox(
            "Auto-refresh",
            value=False,
            help="Automatically refresh data every 30 seconds",
        )

        if auto_refresh:
            refresh_interval = st.slider(
                "Refresh interval (seconds)",
                min_value=10,
                max_value=300,
                value=30,
                step=10,
            )
            st.session_state.refresh_interval = refresh_interval
            st.experimental_rerun()

        st.markdown("---")

        # Configuration info
        st.caption("Configuration")
        try:
            config = load_dashboard_config()
            st.text(f"Symbols: {len(config.scheduler_symbols) if config.scheduler_symbols else 0}")
        except Exception as e:
            st.warning(f"Config error: {e}")

        st.markdown("---")

        # Real-time status (optional feature)
        st.subheader("Real-time Updates")
        st.caption("Optional: WebSocket server not required for dashboard operation")
        render_websocket_status()

        st.markdown("---")
        st.caption("DGAS v1.0")

    return page


def render_page(page: str) -> None:
    """
    Render selected page.

    Args:
        page: Page name to render
    """
    if page == "Overview":
        Overview.render()
    elif page == "Data":
        Data.render()
    elif page == "Predictions":
        Predictions.render()
    elif page == "Backtests":
        Backtests.render()
    elif page == "System Status":
        SystemStatus.render()
    elif page == "Custom Dashboard":
        CustomDashboard.render()


def main() -> NoReturn:
    """Main application entry point."""
    try:
        # Initialize real-time client
        setup_realtime_client()

        # Configure page
        configure_page()

        # Check for updates (polling fallback)
        check_for_updates()

        # Render sidebar and get selection
        selected_page = render_sidebar()

        # Add custom CSS
        st.markdown(
            """
            <style>
            .main .block-container {
                padding-top: 2rem;
                max-width: 1400px;
            }
            .stMetric label {
                font-size: 0.9rem;
                color: #666;
            }
            .stMetric value {
                font-size: 1.2rem;
            }
            </style>
            """,
            unsafe_allow_html=True,
        )

        # Render selected page
        render_page(selected_page)

        # Auto-refresh handling
        if st.session_state.get("refresh_interval"):
            import time
            time.sleep(st.session_state.refresh_interval)
            st.experimental_rerun()

    except Exception as e:
        st.error(f"Application error: {str(e)}")
        st.exception(e)
        sys.exit(1)


if __name__ == "__main__":
    main()
