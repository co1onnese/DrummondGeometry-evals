"""Filter preset manager for saving and loading filter configurations.

Allows users to save, load, and manage filter presets across dashboard pages.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import streamlit as st

logger = logging.getLogger(__name__)


@dataclass
class FilterPreset:
    """Filter preset data structure."""
    id: str
    name: str
    page: str
    description: str
    filters: Dict[str, Any]
    created_at: str
    updated_at: str
    tags: List[str] = None


class FilterPresetManager:
    """Manages filter presets for dashboard pages."""

    def __init__(self, storage_path: Optional[Path] = None):
        """
        Initialize preset manager.

        Args:
            storage_path: Path to store presets
        """
        self.storage_path = storage_path or Path.home() / ".dgas" / "filter_presets"
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self._presets_cache: Optional[List[FilterPreset]] = None

    def _get_presets_file(self) -> Path:
        """Get presets file path."""
        return self.storage_path / "presets.json"

    def _load_presets(self) -> List[FilterPreset]:
        """
        Load all presets from file.

        Returns:
            List of presets
        """
        if self._presets_cache is not None:
            return self._presets_cache

        presets_file = self._get_presets_file()
        if not presets_file.exists():
            self._presets_cache = []
            return self._presets_cache

        try:
            with open(presets_file, "r") as f:
                data = json.load(f)

            presets = []
            for preset_data in data:
                preset = FilterPreset(**preset_data)
                presets.append(preset)

            self._presets_cache = presets
            return presets
        except Exception as e:
            logger.error(f"Error loading presets: {e}")
            self._presets_cache = []
            return self._presets_cache

    def _save_presets(self, presets: List[FilterPreset]) -> None:
        """
        Save presets to file.

        Args:
            presets: List of presets to save
        """
        try:
            presets_file = self._get_presets_file()
            with open(presets_file, "w") as f:
                json.dump([asdict(p) for p in presets], f, indent=2)
            self._presets_cache = presets
        except Exception as e:
            logger.error(f"Error saving presets: {e}")

    def create_preset(
        self,
        name: str,
        page: str,
        filters: Dict[str, Any],
        description: str = "",
        tags: Optional[List[str]] = None,
    ) -> Optional[str]:
        """
        Create a new filter preset.

        Args:
            name: Preset name
            page: Dashboard page name
            filters: Filter configuration
            description: Optional description
            tags: Optional tags

        Returns:
            Preset ID if successful, None otherwise
        """
        import time

        preset_id = f"preset_{int(time.time() * 1000)}"
        now = datetime.now().isoformat()

        preset = FilterPreset(
            id=preset_id,
            name=name,
            page=page,
            description=description,
            filters=filters,
            created_at=now,
            updated_at=now,
            tags=tags or [],
        )

        presets = self._load_presets()
        presets.append(preset)
        self._save_presets(presets)

        logger.info(f"Created preset: {name}")
        return preset_id

    def update_preset(
        self,
        preset_id: str,
        updates: Dict[str, Any],
    ) -> bool:
        """
        Update an existing preset.

        Args:
            preset_id: Preset ID
            updates: Updates to apply

        Returns:
            True if successful
        """
        presets = self._load_presets()
        for preset in presets:
            if preset.id == preset_id:
                for key, value in updates.items():
                    if key == "filters":
                        preset.filters = value
                    elif key == "updated_at":
                        preset.updated_at = value
                    else:
                        setattr(preset, key, value)

                self._save_presets(presets)
                logger.info(f"Updated preset: {preset.name}")
                return True

        return False

    def delete_preset(self, preset_id: str) -> bool:
        """
        Delete a preset.

        Args:
            preset_id: Preset ID

        Returns:
            True if successful
        """
        presets = self._load_presets()
        original_count = len(presets)
        presets = [p for p in presets if p.id != preset_id]

        if len(presets) < original_count:
            self._save_presets(presets)
            logger.info(f"Deleted preset: {preset_id}")
            return True

        return False

    def get_preset(self, preset_id: str) -> Optional[FilterPreset]:
        """
        Get preset by ID.

        Args:
            preset_id: Preset ID

        Returns:
            Preset or None
        """
        presets = self._load_presets()
        for preset in presets:
            if preset.id == preset_id:
                return preset
        return None

    def get_presets_by_page(self, page: str) -> List[FilterPreset]:
        """
        Get all presets for a specific page.

        Args:
            page: Dashboard page name

        Returns:
            List of presets
        """
        presets = self._load_presets()
        return [p for p in presets if p.page == page]

    def search_presets(self, query: str) -> List[FilterPreset]:
        """
        Search presets by name, description, or tags.

        Args:
            query: Search query

        Returns:
            List of matching presets
        """
        query = query.lower()
        presets = self._load_presets()

        results = []
        for preset in presets:
            if query in preset.name.lower():
                results.append(preset)
            elif preset.description and query in preset.description.lower():
                results.append(preset)
            elif preset.tags and any(query in tag.lower() for tag in preset.tags):
                results.append(preset)

        return results

    def get_all_presets(self) -> List[FilterPreset]:
        """
        Get all presets.

        Returns:
            List of all presets
        """
        return self._load_presets()

    def export_presets(self, preset_ids: List[str], export_path: Path) -> bool:
        """
        Export selected presets to JSON.

        Args:
            preset_ids: List of preset IDs
            export_path: Export file path

        Returns:
            True if successful
        """
        try:
            all_presets = self._load_presets()
            selected_presets = [p for p in all_presets if p.id in preset_ids]

            export_data = {
                "exported_at": datetime.now().isoformat(),
                "presets": [asdict(p) for p in selected_presets],
            }

            with open(export_path, "w") as f:
                json.dump(export_data, f, indent=2)

            logger.info(f"Exported {len(selected_presets)} presets")
            return True
        except Exception as e:
            logger.error(f"Error exporting presets: {e}")
            return False

    def import_presets(self, import_path: Path) -> int:
        """
        Import presets from JSON.

        Args:
            import_path: Import file path

        Returns:
            Number of presets imported
        """
        try:
            with open(import_path, "r") as f:
                import_data = json.load(f)

            presets_data = import_data.get("presets", [])
            presets = [FilterPreset(**p) for p in presets_data]

            # Import with new IDs to avoid conflicts
            existing_presets = self._load_presets()
            imported_count = 0

            for preset in presets:
                # Check if preset with same name and page already exists
                if not any(
                    p.name == preset.name and p.page == preset.page
                    for p in existing_presets
                ):
                    # Create new preset with new ID
                    self.create_preset(
                        name=preset.name,
                        page=preset.page,
                        filters=preset.filters,
                        description=preset.description,
                        tags=preset.tags,
                    )
                    imported_count += 1

            logger.info(f"Imported {imported_count} presets")
            return imported_count
        except Exception as e:
            logger.error(f"Error importing presets: {e}")
            return 0


# Global manager instance
_manager_instance: Optional[FilterPresetManager] = None


def get_manager() -> FilterPresetManager:
    """
    Get the global preset manager instance.

    Returns:
        Manager instance
    """
    global _manager_instance

    if _manager_instance is None:
        _manager_instance = FilterPresetManager()

    return _manager_instance


# Streamlit integration

def init_preset_state() -> None:
    """Initialize preset state in Streamlit."""
    if "current_filters" not in st.session_state:
        st.session_state.current_filters = {}

    if "filter_history" not in st.session_state:
        st.session_state.filter_history = []


def save_current_filters_as_preset(
    name: str,
    page: str,
    description: str = "",
    tags: Optional[List[str]] = None,
) -> bool:
    """
    Save current filters as a preset.

    Args:
        name: Preset name
        page: Dashboard page name
        description: Optional description
        tags: Optional tags

    Returns:
        True if successful
    """
    init_preset_state()
    manager = get_manager()

    filters = st.session_state.current_filters.copy()
    preset_id = manager.create_preset(name, page, filters, description, tags)

    return preset_id is not None


def load_preset_filters(preset_id: str) -> bool:
    """
    Load filters from a preset.

    Args:
        preset_id: Preset ID

    Returns:
        True if successful
    """
    init_preset_state()
    manager = get_manager()

    preset = manager.get_preset(preset_id)
    if preset:
        st.session_state.current_filters = preset.filters.copy()
        return True

    return False


if __name__ == "__main__":
    # Test the manager
    manager = FilterPresetManager()

    # Test create preset
    preset_id = manager.create_preset(
        name="Recent Predictions",
        page="predictions",
        filters={"days": 7, "min_confidence": 0.8},
        description="Show recent high-confidence predictions",
        tags=["predictions", "recent", "high-confidence"],
    )
    print(f"Created preset: {preset_id}")

    # Test get presets
    presets = manager.get_presets_by_page("predictions")
    print(f"Found {len(presets)} presets for predictions page")

    # Test search
    results = manager.search_presets("recent")
    print(f"Search found {len(results)} presets")
