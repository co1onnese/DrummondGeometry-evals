"""Dashboard layout management package.

Manages widget positions, grid layout, and persistence.
"""

from dgas.dashboard.layout.manager import (
    LayoutManager,
    get_manager,
    init_dashboard_state,
    get_current_layout,
    save_current_layout,
    load_dashboard,
)

__all__ = [
    "LayoutManager",
    "get_manager",
    "init_dashboard_state",
    "get_current_layout",
    "save_current_layout",
    "load_dashboard",
]
