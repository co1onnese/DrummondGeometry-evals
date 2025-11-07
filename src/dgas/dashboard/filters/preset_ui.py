"""Filter preset UI components.

Provides UI for managing filter presets in Streamlit.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import streamlit as st

from dgas.dashboard.filters.preset_manager import (
    get_manager,
    init_preset_state,
    save_current_filters_as_preset,
    load_preset_filters,
)


def render_preset_selector(
    page: str,
    key_prefix: str = "preset_selector",
) -> Optional[Dict[str, Any]]:
    """
    Render preset selector dropdown.

    Args:
        page: Dashboard page name
        key_prefix: Streamlit key prefix

    Returns:
        Selected preset filters or None
    """
    init_preset_state()
    manager = get_manager()

    presets = manager.get_presets_by_page(page)

    if not presets:
        return None

    # Create options
    options = {f"{p.name} ({p.page})": p.id for p in presets}
    options["No preset"] = None

    # Selection
    selected = st.selectbox(
        "Load Preset",
        options=list(options.keys()),
        key=f"{key_prefix}_select",
    )

    if selected != "No preset":
        preset_id = options[selected]
        if load_preset_filters(preset_id):
            st.success(f"Loaded preset: {selected}")
            return st.session_state.current_filters
        else:
            st.error("Failed to load preset")
            return None

    return None


def render_preset_manager(
    page: str,
    current_filters: Dict[str, Any],
) -> None:
    """
    Render preset management panel.

    Args:
        page: Dashboard page name
        current_filters: Current filter values
    """
    init_preset_state()
    manager = get_manager()

    st.subheader("Filter Presets")

    # Tabs for different operations
    tab1, tab2, tab3 = st.tabs(["Save", "Load", "Manage"])

    with tab1:
        st.markdown("**Save Current Filters**")

        with st.form(key="save_preset_form"):
            preset_name = st.text_input("Preset Name", placeholder="e.g., Recent High-Confidence")
            description = st.text_area(
                "Description (optional)",
                placeholder="Describe when to use this preset...",
                height=100,
            )
            tags = st.text_input(
                "Tags (optional)",
                placeholder="e.g., recent, high-confidence, important",
                help="Comma-separated tags",
            )

            submitted = st.form_submit_button("Save Preset", type="primary")

            if submitted:
                if not preset_name:
                    st.error("Please enter a preset name")
                else:
                    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else None

                    if save_current_filters_as_preset(preset_name, page, description, tag_list):
                        st.success(f"Saved preset: {preset_name}")
                        st.rerun()
                    else:
                        st.error("Failed to save preset")

    with tab2:
        st.markdown("**Load Saved Preset**")

        presets = manager.get_presets_by_page(page)

        if not presets:
            st.info("No presets saved for this page")
        else:
            # Display presets
            for preset in presets:
                with st.container():
                    col1, col2, col3 = st.columns([3, 1, 1])

                    with col1:
                        st.markdown(f"**{preset.name}**")
                        if preset.description:
                            st.caption(preset.description)
                        if preset.tags:
                            st.caption("Tags: " + ", ".join(preset.tags))

                    with col2:
                        if st.button("Load", key=f"load_{preset.id}"):
                            if load_preset_filters(preset.id):
                                st.success("Preset loaded!")
                                st.rerun()

                    with col3:
                        if st.button("Delete", key=f"delete_{preset.id}"):
                            if manager.delete_preset(preset.id):
                                st.success("Preset deleted")
                                st.rerun()

    with tab3:
        st.markdown("**Manage All Presets**")

        all_presets = manager.get_all_presets()

        if not all_presets:
            st.info("No presets saved")
        else:
            # Search
            search_query = st.text_input("Search Presets", placeholder="Search by name, description, or tag")

            if search_query:
                results = manager.search_presets(search_query)
                display_presets = results
            else:
                display_presets = all_presets

            st.markdown(f"Found {len(display_presets)} presets")

            # Export/Import section
            st.markdown("---")
            st.markdown("**Import/Export**")

            col1, col2 = st.columns(2)

            with col1:
                st.markdown("**Export Presets**")
                preset_ids = st.multiselect(
                    "Select presets to export",
                    options=[p.id for p in display_presets],
                    format_func=lambda x: next((p.name for p in display_presets if p.id == x), x),
                )

                if st.button("Export Selected", disabled=len(preset_ids) == 0):
                    export_path = Path(f"filter_presets_export_{int(time.time())}.json")
                    if manager.export_presets(preset_ids, export_path):
                        with open(export_path, "r") as f:
                            st.download_button(
                                label="Download Export",
                                data=f.read(),
                                file_name=str(export_path),
                                mime="application/json",
                            )

            with col2:
                st.markdown("**Import Presets**")
                uploaded_file = st.file_uploader("Choose preset file", type="json")

                if uploaded_file is not None:
                    import_name = st.text_input("Import As", value=f"imported_{int(time.time())}")

                    if st.button("Import", key="import_presets"):
                        # Save uploaded file temporarily
                        temp_path = Path(f"temp_{uploaded_file.name}")
                        with open(temp_path, "wb") as f:
                            f.write(uploaded_file.getvalue())

                        # Import
                        imported_count = manager.import_presets(temp_path)

                        if imported_count > 0:
                            st.success(f"Imported {imported_count} presets")
                            st.rerun()
                        else:
                            st.error("Failed to import presets")

                        # Clean up
                        temp_path.unlink(missing_ok=True)

            st.markdown("---")
            st.markdown("**All Presets**")

            # Display all presets in a table
            for preset in display_presets:
                with st.expander(f"{preset.name} ({preset.page})"):
                    st.json(preset.filters)
                    st.caption(f"Created: {preset.created_at}")
                    if preset.description:
                        st.caption(f"Description: {preset.description}")
                    if preset.tags:
                        st.caption(f"Tags: {', '.join(preset.tags)}")

                    col1, col2 = st.columns(2)
                    with col1:
                        if st.button("Delete", key=f"manage_delete_{preset.id}"):
                            if manager.delete_preset(preset.id):
                                st.success("Preset deleted")
                                st.rerun()

                    with col2:
                        # Show filter details
                        st.json(preset.filters)


def render_filter_history(
    max_items: int = 10,
) -> None:
    """
    Render filter history.

    Args:
        max_items: Maximum number of history items to show
    """
    init_preset_state()

    if not st.session_state.filter_history:
        return

    st.subheader("Recent Filters")

    history = st.session_state.filter_history[-max_items:]

    for i, item in enumerate(reversed(history)):
        with st.container():
            col1, col2 = st.columns([4, 1])

            with col1:
                st.text(f"{item.get('page', 'Unknown')} - {item.get('description', 'No description')}")

            with col2:
                if st.button("Reapply", key=f"history_{i}"):
                    st.session_state.current_filters = item.get("filters", {}).copy()
                    st.success("Filters reapplied!")
                    st.rerun()

    # Clear history button
    if st.button("Clear History"):
        st.session_state.filter_history = []
        st.rerun()


def add_to_filter_history(
    page: str,
    filters: Dict[str, Any],
    description: str = "",
) -> None:
    """
    Add current filters to history.

    Args:
        page: Dashboard page name
        filters: Filter values
        description: Optional description
    """
    init_preset_state()

    history_item = {
        "page": page,
        "filters": filters,
        "description": description,
        "timestamp": time.time(),
    }

    # Add to history
    if "filter_history" not in st.session_state:
        st.session_state.filter_history = []

    st.session_state.filter_history.append(history_item)

    # Limit history size
    if len(st.session_state.filter_history) > 50:
        st.session_state.filter_history = st.session_state.filter_history[-50:]


if __name__ == "__main__":
    # Test the UI components
    st.set_page_config(page_title="Filter Presets Test")
    st.title("Filter Presets Test")

    # Test selector
    preset_filters = render_preset_selector("predictions")
    if preset_filters:
        st.json(preset_filters)

    # Test manager
    render_preset_manager("predictions", {"days": 7, "min_confidence": 0.8})

    # Test history
    render_filter_history()
