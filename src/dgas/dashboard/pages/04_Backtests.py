"""Backtests page for dashboard.

Displays backtest results, performance metrics, and strategy analysis.
"""

from __future__ import annotations

import streamlit as st

from dgas.dashboard.components.charts import (
    create_performance_metrics_chart,
    create_equity_curve_chart,
    create_bar_chart,
    create_histogram,
    format_percentage,
    format_number,
)
try:
    from dgas.dashboard.components.database import fetch_backtest_results
except KeyError as e:
    # Handle Streamlit cache KeyError by re-importing
    import importlib
    import sys
    # Clear the module from cache if it exists
    module_name = 'dgas.dashboard.components.database'
    if module_name in sys.modules:
        del sys.modules[module_name]
    # Re-import
    importlib.import_module(module_name)
    from dgas.dashboard.components.database import fetch_backtest_results
from dgas.dashboard.components.utils import (
    format_timestamp,
    download_dataframe,
    create_filter_panel,
    apply_filters_to_dataframe,
    safe_float,
)


def render() -> None:
    """Render the Backtests page."""
    st.header("Backtest Analysis")
    st.markdown("Performance analysis of trading strategies and backtest results.")

    # Sidebar controls
    st.sidebar.subheader("Filters")
    limit = st.sidebar.slider(
        "Max Results",
        min_value=5,
        max_value=100,
        value=20,
        help="Maximum number of backtests to display",
    )

    symbol_filter = st.sidebar.selectbox(
        "Symbol Filter",
        options=["All"] + [],
        index=0,
        help="Filter by symbol",
    )

    # Load data
    try:
        if symbol_filter == "All":
            backtests = fetch_backtest_results(limit=limit)
        else:
            backtests = fetch_backtest_results(limit=limit, symbol=symbol_filter)
    except Exception as e:
        st.error(f"Error loading backtest results: {e}")
        return

    if backtests.empty:
        st.info("No backtest results found for the selected criteria.")
        return

    # Key metrics
    st.subheader("Performance Summary")
    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:
        st.metric(
            "Total Backtests",
            len(backtests),
            help="Number of backtests",
        )

    with col2:
        if "total_return" in backtests.columns:
            avg_return = backtests["total_return"].mean()
            st.metric(
                "Avg Return",
                format_percentage(avg_return / 100),
                help="Average return across all backtests",
            )

    with col3:
        if "sharpe_ratio" in backtests.columns:
            avg_sharpe = backtests["sharpe_ratio"].mean()
            st.metric(
                "Avg Sharpe",
                f"{avg_sharpe:.2f}",
                help="Average Sharpe ratio",
            )

    with col4:
        if "max_drawdown" in backtests.columns:
            avg_dd = backtests["max_drawdown"].mean()
            st.metric(
                "Avg Drawdown",
                format_percentage(abs(avg_dd) / 100),
                help="Average maximum drawdown",
            )

    with col5:
        if "win_rate" in backtests.columns:
            avg_win_rate = backtests["win_rate"].mean()
            st.metric(
                "Avg Win Rate",
                format_percentage(avg_win_rate / 100),
                help="Average win rate",
            )

    st.markdown("---")

    # Tabs
    tab1, tab2, tab3, tab4, tab5 = st.tabs(
        ["Performance Overview", "Returns Analysis", "Risk Metrics", "Strategy Comparison", "Raw Data"]
    )

    with tab1:
        st.subheader("Performance Overview")

        # Performance comparison chart
        if "total_return" in backtests.columns and "sharpe_ratio" in backtests.columns:
            fig = create_performance_metrics_chart(backtests)
            st.plotly_chart(fig, use_container_width=True)

        st.markdown("---")

        # Performance distribution
        col1, col2 = st.columns(2)

        with col1:
            if "total_return" in backtests.columns:
                fig = create_histogram(
                    backtests,
                    x_col="total_return",
                    title="Return Distribution",
                    nbins=20,
                )
                st.plotly_chart(fig, use_container_width=True)

        with col2:
            if "sharpe_ratio" in backtests.columns:
                fig = create_histogram(
                    backtests,
                    x_col="sharpe_ratio",
                    title="Sharpe Ratio Distribution",
                    nbins=20,
                )
                st.plotly_chart(fig, use_container_width=True)

    with tab2:
        st.subheader("Returns Analysis")

        # Top performers
        if "total_return" in backtests.columns:
            top_performers = backtests.nlargest(10, "total_return")

            st.markdown("**Top 10 Performers**")
            col1, col2 = st.columns([2, 1])

            with col1:
                fig = create_bar_chart(
                    top_performers,
                    x_col="symbol",
                    y_col="total_return",
                    color_col="strategy_name" if "strategy_name" in top_performers.columns else None,
                    title="Top 10 Backtests by Return",
                )
                st.plotly_chart(fig, use_container_width=True)

            with col2:
                st.markdown("**Return Statistics**")
                st.metric(
                    "Best Return",
                    format_percentage(top_performers["total_return"].max() / 100),
                )
                st.metric(
                    "Avg Top 10",
                    format_percentage(top_performers["total_return"].mean() / 100),
                )
                st.metric(
                    "Median Top 10",
                    format_percentage(top_performers["total_return"].median() / 100),
                )

        st.markdown("---")

        # Returns by symbol
        if len(backtests) > 1 and "symbol" in backtests.columns:
            symbol_returns = (
                backtests.groupby("symbol")["total_return"]
                .agg(["mean", "count"])
                .reset_index()
                .rename(columns={"count": "backtest_count"})
            )

            fig = create_bar_chart(
                symbol_returns.sort_values("mean", ascending=False),
                x_col="symbol",
                y_col="mean",
                title="Average Return by Symbol",
            )
            st.plotly_chart(fig, use_container_width=True)

    with tab3:
        st.subheader("Risk Metrics")

        col1, col2, col3 = st.columns(3)

        with col1:
            st.markdown("**Drawdown Analysis**")
            if "max_drawdown" in backtests.columns:
                st.metric(
                    "Best (Min) Drawdown",
                    format_percentage(abs(backtests["max_drawdown"].min()) / 100),
                )
                st.metric(
                    "Avg Drawdown",
                    format_percentage(abs(backtests["max_drawdown"].mean()) / 100),
                )

        with col2:
            st.markdown("**Sharpe Ratio**")
            if "sharpe_ratio" in backtests.columns:
                st.metric(
                    "Best Sharpe",
                    f"{backtests['sharpe_ratio'].max():.2f}",
                )
                st.metric(
                    "Avg Sharpe",
                    f"{backtests['sharpe_ratio'].mean():.2f}",
                )

        with col3:
            st.markdown("**Win Rate**")
            if "win_rate" in backtests.columns:
                st.metric(
                    "Best Win Rate",
                    format_percentage(backtests["win_rate"].max() / 100),
                )
                st.metric(
                    "Avg Win Rate",
                    format_percentage(backtests["win_rate"].mean() / 100),
                )

        st.markdown("---")

        # Risk-return scatter
        if "total_return" in backtests.columns and "sharpe_ratio" in backtests.columns:
            st.subheader("Risk-Return Analysis")
            scatter_data = backtests.copy()

            from plotly.express import scatter
            fig = scatter(
                scatter_data,
                x="total_return",
                y="sharpe_ratio",
                color="symbol" if "symbol" in scatter_data.columns else None,
                size="max_drawdown" if "max_drawdown" in scatter_data.columns else None,
                hover_data=["strategy_name", "win_rate"],
                title="Risk vs Return",
                labels={
                    "total_return": "Total Return",
                    "sharpe_ratio": "Sharpe Ratio",
                },
            )
            fig.update_layout(height=500)
            st.plotly_chart(fig, use_container_width=True)

    with tab4:
        st.subheader("Strategy Comparison")

        if "strategy_name" in backtests.columns:
            # Strategy performance
            strategy_stats = (
                backtests.groupby("strategy_name")
                .agg(
                    {
                        "total_return": ["mean", "std", "count"],
                        "sharpe_ratio": "mean",
                        "max_drawdown": "mean",
                        "win_rate": "mean",
                    }
                )
                .round(2)
            )

            # Flatten column names
            strategy_stats.columns = [
                "avg_return",
                "return_std",
                "backtest_count",
                "avg_sharpe",
                "avg_drawdown",
                "avg_win_rate",
            ]

            strategy_stats = strategy_stats.reset_index()

            st.markdown("**Strategy Performance Summary**")
            st.dataframe(
                strategy_stats,
                use_container_width=True,
                hide_index=True,
            )

            st.markdown("---")

            # Strategy comparison charts
            col1, col2 = st.columns(2)

            with col1:
                fig = create_bar_chart(
                    strategy_stats,
                    x_col="strategy_name",
                    y_col="avg_return",
                    title="Average Return by Strategy",
                )
                st.plotly_chart(fig, use_container_width=True)

            with col2:
                fig = create_bar_chart(
                    strategy_stats,
                    x_col="strategy_name",
                    y_col="avg_sharpe",
                    title="Average Sharpe by Strategy",
                )
                st.plotly_chart(fig, use_container_width=True)

        else:
            st.info("Strategy names not available in the data.")

    with tab5:
        st.subheader("Raw Backtest Data")
        st.markdown("Complete dataset of all backtest results.")

        # Display options
        col1, col2 = st.columns(2)

        with col1:
            max_display = st.slider(
                "Max rows to display",
                min_value=10,
                max_value=len(backtests),
                value=min(50, len(backtests)),
                help="Limit the number of rows displayed",
            )

        with col2:
            show_details = st.checkbox(
                "Show all columns",
                value=False,
                help="Show all data columns",
            )

        # Data table
        display_data = backtests.copy()

        if not show_details:
            # Select key columns
            key_cols = [
                "backtest_id",
                "strategy_name",
                "symbol",
                "start_date",
                "end_date",
                "total_return",
                "sharpe_ratio",
                "max_drawdown",
                "win_rate",
                "total_trades",
            ]
            display_cols = [col for col in key_cols if col in display_data.columns]
            display_data = display_data[display_cols]

        # Sort by completion date
        if "completed_at" in display_data.columns:
            display_data = display_data.sort_values("completed_at", ascending=False)

        # Limit display
        display_data = display_data.head(max_display)

        st.dataframe(
            display_data,
            use_container_width=True,
            hide_index=True,
        )

        st.markdown(f"Showing {len(display_data)} of {len(backtests)} backtests")

        # Download
        st.markdown("---")
        download_dataframe(backtests, "backtest_results.csv")


if __name__ == "__main__":
    render()
