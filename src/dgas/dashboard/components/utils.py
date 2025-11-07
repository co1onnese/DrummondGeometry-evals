"""Utility functions for Streamlit dashboard.

Provides helper functions for common operations.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import streamlit as st

from dgas.config import load_settings


def get_config_file_path() -> Optional[Path]:
    """
    Get configuration file path from query params or default locations.

    Returns:
        Path to config file or None
    """
    # Check query parameters
    if "config" in st.query_params:
        return Path(st.query_params["config"])

    # Check environment variable
    if "DGAS_CONFIG" in os.environ:
        return Path(os.environ["DGAS_CONFIG"])

    # Auto-detect
    return None


@st.cache_resource
def load_dashboard_config() -> Any:
    """
    Load configuration for dashboard.

    Returns:
        UnifiedSettings instance
    """
    config_file = get_config_file_path()
    return load_settings(config_file=config_file)


def get_symbols() -> List[str]:
    """
    Get list of symbols from configuration.

    Returns:
        List of symbol strings
    """
    settings = load_dashboard_config()
    return settings.scheduler_symbols or []


def create_dataframe_from_query_results(results: List[tuple], columns: List[str]) -> pd.DataFrame:
    """
    Create DataFrame from query results.

    Args:
        results: Query results
        columns: Column names

    Returns:
        DataFrame
    """
    if not results:
        return pd.DataFrame(columns=columns)

    return pd.DataFrame(results, columns=columns)


def safe_float(value: Any, default: float = 0.0) -> float:
    """
    Safely convert value to float.

    Args:
        value: Value to convert
        default: Default value if conversion fails

    Returns:
        Float value
    """
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_int(value: Any, default: int = 0) -> int:
    """
    Safely convert value to int.

    Args:
        value: Value to convert
        default: Default value if conversion fails

    Returns:
        Integer value
    """
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def format_timestamp(ts: Any) -> str:
    """
    Format timestamp for display.

    Args:
        ts: Timestamp object or string

    Returns:
        Formatted timestamp string
    """
    if ts is None:
        return "N/A"

    if isinstance(ts, str):
        ts = pd.to_datetime(ts)

    return ts.strftime("%Y-%m-%d %H:%M:%S") if hasattr(ts, "strftime") else str(ts)


def filter_dataframe(
    df: pd.DataFrame,
    filters: Dict[str, Any],
) -> pd.DataFrame:
    """
    Apply filters to DataFrame.

    Args:
        df: Input DataFrame
        filters: Dictionary of column -> filter value

    Returns:
        Filtered DataFrame
    """
    if df.empty:
        return df

    filtered_df = df.copy()

    for col, value in filters.items():
        if col not in df.columns or value is None or value == "":
            continue

        if isinstance(value, str):
            # String filter (case-insensitive)
            filtered_df = filtered_df[
                filtered_df[col].astype(str).str.contains(value, case=False, na=False)
            ]
        elif isinstance(value, (int, float)):
            # Numeric filter
            filtered_df = filtered_df[filtered_df[col] == value]

    return filtered_df


def paginate_dataframe(df: pd.DataFrame, page_size: int = 20) -> tuple[pd.DataFrame, int]:
    """
    Paginate DataFrame.

    Args:
        df: Input DataFrame
        page_size: Number of rows per page

    Returns:
        Tuple of (paginated DataFrame, total pages)
    """
    if df.empty:
        return df, 0

    total_pages = (len(df) + page_size - 1) // page_size

    if "page" not in st.session_state:
        st.session_state.page = 1

    col1, col2, col3 = st.columns([1, 2, 1])

    with col1:
        if st.button("◀ Previous", disabled=st.session_state.page <= 1):
            st.session_state.page -= 1

    with col2:
        st.selectbox(
            "Page",
            options=list(range(1, total_pages + 1)),
            index=st.session_state.page - 1,
            key="page_selector",
            label_visibility="collapsed",
        )
        st.session_state.page = st.session_state.page_selector

    with col3:
        if st.button("Next ▶", disabled=st.session_state.page >= total_pages):
            st.session_state.page += 1

    start_idx = (st.session_state.page - 1) * page_size
    end_idx = start_idx + page_size

    return df.iloc[start_idx:end_idx], total_pages


def download_dataframe(
    df: pd.DataFrame,
    filename: str = "data.csv",
    format: str = "csv",
) -> None:
    """
    Create download button for DataFrame.

    Args:
        df: DataFrame to download
        filename: Download filename
        format: File format ('csv' or 'xlsx')
    """
    if df.empty:
        st.warning("No data to download")
        return

    if format == "csv":
        csv = df.to_csv(index=False)
        st.download_button(
            label=f"Download {filename}",
            data=csv,
            file_name=filename,
            mime="text/csv",
        )
    elif format == "xlsx":
        # Note: Would need openpyxl for this
        csv = df.to_csv(index=False)
        st.download_button(
            label=f"Download {filename}",
            data=csv,
            file_name=filename.replace(".xlsx", ".csv"),
            mime="text/csv",
        )


def validate_date_range(start_date: Any, end_date: Any) -> tuple[Any, Any]:
    """
    Validate and normalize date range.

    Args:
        start_date: Start date
        end_date: End date

    Returns:
        Tuple of (start_date, end_date)
    """
    if start_date and end_date:
        if pd.to_datetime(start_date) > pd.to_datetime(end_date):
            # Swap dates
            return end_date, start_date

    return start_date, end_date


def get_color_for_value(value: float, threshold: float = 0.0) -> str:
    """
    Get color for value (e.g., for performance metrics).

    Args:
        value: Numeric value
        threshold: Threshold for color change

    Returns:
        Color string
    """
    if value > threshold:
        return "green"
    elif value < 0:
        return "red"
    else:
        return "gray"


def create_filter_panel(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Create interactive filter panel.

    Args:
        df: DataFrame to filter

    Returns:
        Dictionary of filter values
    """
    filters = {}

    with st.expander("Filters", expanded=False):
        col1, col2 = st.columns(2)

        with col1:
            # Symbol filter
            if "symbol" in df.columns:
                symbols = ["All"] + sorted(df["symbol"].unique().tolist())
                selected_symbol = st.selectbox("Symbol", symbols, key="symbol_filter")
                filters["symbol"] = None if selected_symbol == "All" else selected_symbol

        with col2:
            # Date range filter
            if "timestamp" in df.columns:
                date_col = pd.to_datetime(df["timestamp"])
                date_range = st.date_input(
                    "Date Range",
                    value=(date_col.min().date(), date_col.max().date()),
                    key="date_filter",
                )
                filters["date_range"] = date_range

    return filters


def apply_filters_to_dataframe(
    df: pd.DataFrame,
    filters: Dict[str, Any],
) -> pd.DataFrame:
    """
    Apply filters from filter panel to DataFrame.

    Args:
        df: DataFrame to filter
        filters: Filter dictionary

    Returns:
        Filtered DataFrame
    """
    if df.empty:
        return df

    filtered_df = df.copy()

    # Symbol filter
    if "symbol" in filters and filters["symbol"] is not None:
        filtered_df = filtered_df[filtered_df["symbol"] == filters["symbol"]]

    # Date range filter
    if "date_range" in filters and filters["date_range"] is not None:
        date_col = pd.to_datetime(filtered_df["timestamp"])
        start_date, end_date = filters["date_range"]
        filtered_df = filtered_df[
            (date_col.dt.date >= start_date) & (date_col.dt.date <= end_date)
        ]

    return filtered_df


def show_error_message(error: Exception) -> None:
    """
    Display error message in Streamlit.

    Args:
        error: Exception object
    """
    st.error(f"Error: {str(error)}")
    with st.expander("Error Details"):
        st.exception(error)


def show_success_message(message: str) -> None:
    """
    Display success message in Streamlit.

    Args:
        message: Success message
    """
    st.success(message)


def show_warning_message(message: str) -> None:
    """
    Display warning message in Streamlit.

    Args:
        message: Warning message
    """
    st.warning(message)


def show_info_message(message: str) -> None:
    """
    Display info message in Streamlit.

    Args:
        message: Info message
    """
    st.info(message)
