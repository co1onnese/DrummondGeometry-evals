"""Chart utilities for Streamlit dashboard.

Provides reusable chart components using Plotly.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st


def create_metric_card(title: str, value: Any, delta: Optional[str] = None, help_text: Optional[str] = None) -> None:
    """
    Create a metric card display.

    Args:
        title: Metric title
        value: Metric value
        delta: Optional delta indicator
        help_text: Optional help text
    """
    st.metric(
        label=title,
        value=value,
        delta=delta,
        help=help_text,
    )


def create_line_chart(
    df: pd.DataFrame,
    x_col: str,
    y_col: str,
    title: str,
    color_col: Optional[str] = None,
) -> go.Figure:
    """
    Create a line chart.

    Args:
        df: DataFrame with data
        x_col: X-axis column name
        y_col: Y-axis column name
        title: Chart title
        color_col: Optional color grouping column

    Returns:
        Plotly figure
    """
    fig = px.line(
        df,
        x=x_col,
        y=y_col,
        color=color_col,
        title=title,
        markers=True,
    )

    fig.update_layout(
        height=400,
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )

    return fig


def create_bar_chart(
    df: pd.DataFrame,
    x_col: str,
    y_col: str,
    title: str,
    color_col: Optional[str] = None,
    orientation: str = "v",
) -> go.Figure:
    """
    Create a bar chart.

    Args:
        df: DataFrame with data
        x_col: X-axis column name
        y_col: Y-axis column name
        title: Chart title
        color_col: Optional color grouping column
        orientation: Chart orientation ('v' or 'h')

    Returns:
        Plotly figure
    """
    fig = px.bar(
        df,
        x=x_col,
        y=y_col,
        color=color_col,
        title=title,
        orientation=orientation,
    )

    fig.update_layout(height=400, hovermode="x unified" if orientation == "v" else "y unified")

    return fig


def create_scatter_chart(
    df: pd.DataFrame,
    x_col: str,
    y_col: str,
    size_col: Optional[str] = None,
    color_col: str = "confidence",
    title: str = "Signal Analysis",
) -> go.Figure:
    """
    Create a scatter plot.

    Args:
        df: DataFrame with data
        x_col: X-axis column name
        y_col: Y-axis column name
        size_col: Optional size column
        color_col: Color column (default: confidence)
        title: Chart title

    Returns:
        Plotly figure
    """
    # Use size parameter only if size_col is provided
    fig_kwargs = {
        "x": x_col,
        "y": y_col,
        "color": color_col,
        "title": title,
        "hover_data": ["symbol", "signal_type", "risk_reward_ratio"],
    }

    if size_col and size_col in df.columns:
        # Convert column to native Python values for Plotly
        size_values = pd.to_numeric(df[size_col], errors="coerce").fillna(0)
        # Scale values to reasonable marker sizes (5-20 pixels)
        min_size, max_size = 5, 20
        size_scaled = min_size + (size_values - size_values.min()) / (size_values.max() - size_values.min() + 0.0001) * (max_size - min_size)
        fig_kwargs["size"] = size_scaled

    fig = px.scatter(df, **fig_kwargs)

    fig.update_layout(height=500, hovermode="closest")

    return fig


def create_pie_chart(
    df: pd.DataFrame,
    names_col: str,
    values_col: str,
    title: str,
) -> go.Figure:
    """
    Create a pie chart.

    Args:
        df: DataFrame with data
        names_col: Category names column
        values_col: Values column
        title: Chart title

    Returns:
        Plotly figure
    """
    fig = px.pie(
        df,
        names=names_col,
        values=values_col,
        title=title,
    )

    fig.update_layout(height=400)

    return fig


def create_histogram(
    df: pd.DataFrame,
    x_col: str,
    title: str,
    color_col: Optional[str] = None,
    nbins: int = 30,
) -> go.Figure:
    """
    Create a histogram.

    Args:
        df: DataFrame with data
        x_col: Column to histogram
        title: Chart title
        color_col: Optional color grouping
        nbins: Number of bins

    Returns:
        Plotly figure
    """
    fig = px.histogram(
        df,
        x=x_col,
        color=color_col,
        title=title,
        nbins=nbins,
        marginal="box",
    )

    fig.update_layout(height=400, barmode="overlay")

    return fig


def create_area_chart(
    df: pd.DataFrame,
    x_col: str,
    y_col: str,
    title: str,
    color_col: Optional[str] = None,
) -> go.Figure:
    """
    Create an area chart.

    Args:
        df: DataFrame with data
        x_col: X-axis column name
        y_col: Y-axis column name
        title: Chart title
        color_col: Optional color grouping

    Returns:
        Plotly figure
    """
    fig = px.area(
        df,
        x=x_col,
        y=y_col,
        color=color_col,
        title=title,
    )

    fig.update_layout(height=400, hovermode="x unified")

    return fig


def create_data_coverage_heatmap(df: pd.DataFrame) -> go.Figure:
    """
    Create a data coverage heatmap.

    Args:
        df: DataFrame with data

    Returns:
        Plotly figure
    """
    if df.empty or "bar_count" not in df.columns:
        # Create empty figure if no data
        fig = go.Figure()
        fig.add_annotation(
            text="No data available",
            xref="paper",
            yref="paper",
            x=0.5,
            y=0.5,
            showarrow=False,
        )
        return fig

    # Calculate coverage percentage
    df = df.copy()
    df["total_bars"] = df["bar_count"]
    df["coverage_pct"] = df["bar_count"] / df["bar_count"].max() * 100

    # Create heatmap
    fig = go.Figure(
        data=go.Heatmap(
            z=[df["coverage_pct"].values],
            x=df["symbol"].values,
            y=["Coverage"],
            colorscale="Viridis",
            showscale=True,
            colorbar=dict(title="Coverage %"),
        )
    )

    fig.update_layout(
        title="Data Coverage by Symbol",
        height=200,
        xaxis_title="Symbol",
        yaxis_title="",
    )

    return fig


def create_equity_curve_chart(df: pd.DataFrame, benchmark_df: Optional[pd.DataFrame] = None) -> go.Figure:
    """
    Create equity curve chart for backtests.

    Args:
        df: DataFrame with equity curve data
        benchmark_df: Optional benchmark data

    Returns:
        Plotly figure
    """
    fig = go.Figure()

    # Add equity curve
    fig.add_trace(
        go.Scatter(
            x=df.index,
            y=df.values,
            mode="lines",
            name="Portfolio",
            line=dict(color="blue", width=2),
        )
    )

    # Add benchmark if provided
    if benchmark_df is not None and not benchmark_df.empty:
        fig.add_trace(
            go.Scatter(
                x=benchmark_df.index,
                y=benchmark_df.values,
                mode="lines",
                name="Benchmark",
                line=dict(color="gray", width=1, dash="dash"),
            )
        )

    fig.update_layout(
        title="Equity Curve",
        xaxis_title="Date",
        yaxis_title="Value",
        height=500,
        hovermode="x unified",
    )

    return fig


def create_signal_timeline(df: pd.DataFrame) -> go.Figure:
    """
    Create a timeline of signals.

    Args:
        df: DataFrame with signal data

    Returns:
        Plotly figure
    """
    if df.empty:
        fig = go.Figure()
        fig.add_annotation(
            text="No signals available",
            xref="paper",
            yref="paper",
            x=0.5,
            y=0.5,
            showarrow=False,
        )
        return fig

    # Prepare kwargs for px.scatter
    fig_kwargs = {
        "x": "signal_timestamp",
        "y": "symbol",
        "color": "signal_type",
        "hover_data": ["confidence", "risk_reward_ratio"],
        "title": "Signal Timeline",
    }

    # Handle size parameter if signal_strength column exists
    if "signal_strength" in df.columns:
        # Convert column to native Python values for Plotly
        size_values = pd.to_numeric(df["signal_strength"], errors="coerce").fillna(0)
        # Scale values to reasonable marker sizes (5-20 pixels)
        min_size, max_size = 5, 20
        size_scaled = min_size + (size_values - size_values.min()) / (size_values.max() - size_values.min() + 0.0001) * (max_size - min_size)
        fig_kwargs["size"] = size_scaled

    fig = px.scatter(df, **fig_kwargs)

    fig.update_layout(
        height=500,
        xaxis_title="Timestamp",
        yaxis_title="Symbol",
    )

    return fig


def create_performance_metrics_chart(df: pd.DataFrame) -> go.Figure:
    """
    Create performance metrics comparison chart.

    Args:
        df: DataFrame with backtest metrics

    Returns:
        Plotly figure
    """
    if df.empty:
        fig = go.Figure()
        fig.add_annotation(
            text="No backtest data available",
            xref="paper",
            yref="paper",
            x=0.5,
            y=0.5,
            showarrow=False,
        )
        return fig

    # Create subplot with multiple metrics
    fig = go.Figure()

    # Add total return bars
    fig.add_trace(
        go.Bar(
            x=df["symbol"],
            y=df["total_return"],
            name="Total Return",
            marker_color="blue",
            opacity=0.7,
        )
    )

    # Add Sharpe ratio on secondary y-axis
    if "sharpe_ratio" in df.columns:
        fig.add_trace(
            go.Scatter(
                x=df["symbol"],
                y=df["sharpe_ratio"],
                mode="markers+lines",
                name="Sharpe Ratio",
                yaxis="y2",
                line=dict(color="red"),
                marker=dict(size=8),
            )
        )

    fig.update_layout(
        title="Performance Metrics Comparison",
        xaxis_title="Symbol",
        yaxis=dict(title="Total Return", side="left"),
        yaxis2=dict(title="Sharpe Ratio", side="right", overlaying="y"),
        height=400,
        barmode="group",
    )

    return fig


def format_currency(value: float, currency: str = "$") -> str:
    """
    Format a numeric value as currency.

    Args:
        value: Numeric value
        currency: Currency symbol

    Returns:
        Formatted currency string
    """
    return f"{currency}{value:,.2f}"


def format_percentage(value: float, decimals: int = 2) -> str:
    """
    Format a numeric value as percentage.

    Args:
        value: Numeric value (0-1)
        decimals: Number of decimal places

    Returns:
        Formatted percentage string
    """
    return f"{value * 100:.{decimals}f}%"


def format_number(value: float, decimals: int = 0) -> str:
    """
    Format a numeric value with commas.

    Args:
        value: Numeric value
        decimals: Number of decimal places

    Returns:
        Formatted number string
    """
    if decimals == 0:
        return f"{int(value):,}"
    return f"{value:,.{decimals}f}"
