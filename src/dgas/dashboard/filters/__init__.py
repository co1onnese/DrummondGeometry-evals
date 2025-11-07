"""Filter presets package.

Provides filter preset management and UI components.
"""

from dgas.dashboard.filters.preset_manager import (
    FilterPreset,
    FilterPresetManager,
    get_manager,
    init_preset_state,
    save_current_filters_as_preset,
    load_preset_filters,
)

from dgas.dashboard.filters.preset_ui import (
    render_preset_selector,
    render_preset_manager,
    render_filter_history,
    add_to_filter_history,
)

__all__ = [
    "FilterPreset",
    "FilterPresetManager",
    "get_manager",
    "init_preset_state",
    "save_current_filters_as_preset",
    "load_preset_filters",
    "render_preset_selector",
    "render_preset_manager",
    "render_filter_history",
    "add_to_filter_history",
]
