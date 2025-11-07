"""Tests for filter preset system."""

import pytest
import json
import os
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock
from dgas.dashboard.filters.preset_manager import (
    FilterPreset,
    FilterPresetManager,
)


class TestFilterPreset:
    """Test FilterPreset data class."""

    def test_preset_creation(self):
        """Test creating a filter preset."""
        preset = FilterPreset(
            id="preset_1",
            name="High Confidence Predictions",
            description="Filters for high confidence predictions",
            page="predictions",
            filters={
                "min_confidence": 0.8,
                "signal_type": "BUY"
            },
            tags=["high-confidence", "buy-signals"],
            created_at=datetime.now(),
            updated_at=datetime.now()
        )

        assert preset.id == "preset_1"
        assert preset.name == "High Confidence Predictions"
        assert preset.description == "Filters for high confidence predictions"
        assert preset.page == "predictions"
        assert preset.filters["min_confidence"] == 0.8
        assert "high-confidence" in preset.tags
        assert "buy-signals" in preset.tags

    def test_preset_to_dict(self):
        """Test converting preset to dictionary."""
        created_at = datetime(2024, 11, 7, 12, 0, 0)
        updated_at = datetime(2024, 11, 7, 12, 0, 0)

        preset = FilterPreset(
            id="preset_2",
            name="Recent Signals",
            description="Recent trading signals",
            page="signals",
            filters={
                "days": 7,
                "symbol": "AAPL"
            },
            tags=["recent", "AAPL"],
            created_at=created_at,
            updated_at=updated_at
        )

        result = preset.to_dict()

        assert result["id"] == "preset_2"
        assert result["name"] == "Recent Signals"
        assert result["page"] == "signals"
        assert result["filters"]["days"] == 7
        assert result["created_at"] == created_at.isoformat()
        assert result["updated_at"] == updated_at.isoformat()

    def test_preset_from_dict(self):
        """Test creating preset from dictionary."""
        data = {
            "id": "preset_3",
            "name": "Data Overview",
            "description": "Overview filters",
            "page": "data",
            "filters": {
                "exchange": "NASDAQ",
                "interval": "1d"
            },
            "tags": ["overview", "NASDAQ"],
            "created_at": "2024-11-07T12:00:00",
            "updated_at": "2024-11-07T12:00:00"
        }

        preset = FilterPreset.from_dict(data)

        assert preset.id == "preset_3"
        assert preset.name == "Data Overview"
        assert preset.page == "data"
        assert preset.filters["exchange"] == "NASDAQ"
        assert "overview" in preset.tags

    def test_preset_update(self):
        """Test updating a preset."""
        preset = FilterPreset(
            id="preset_4",
            name="Original Name",
            description="Original description",
            page="predictions",
            filters={"min_confidence": 0.5},
            tags=["original"],
            created_at=datetime.now(),
            updated_at=datetime.now()
        )

        # Update the preset
        old_name = preset.name
        preset.name = "Updated Name"
        preset.description = "Updated description"
        preset.filters["min_confidence"] = 0.7
        preset.tags.append("updated")
        preset.updated_at = datetime.now()

        assert preset.name != old_name
        assert preset.name == "Updated Name"
        assert preset.description == "Updated description"
        assert preset.filters["min_confidence"] == 0.7
        assert "updated" in preset.tags


class TestFilterPresetManager:
    """Test FilterPresetManager functionality."""

    @pytest.fixture
    def preset_manager(self):
        """Create a test preset manager."""
        return FilterPresetManager(storage_path="/tmp/test_presets")

    def test_manager_initialization(self, preset_manager):
        """Test manager initializes correctly."""
        assert preset_manager.storage_path == "/tmp/test_presets"
        assert isinstance(preset_manager.presets, dict)
        assert isinstance(preset_manager.page_presets, dict)

    def test_create_preset(self, preset_manager):
        """Test creating a new preset."""
        preset = preset_manager.create_preset(
            name="Test Preset",
            description="A test preset",
            page="predictions",
            filters={
                "min_confidence": 0.8,
                "symbol": "AAPL"
            },
            tags=["test", "AAPL"]
        )

        assert preset.id in preset_manager.presets
        assert preset.name == "Test Preset"
        assert preset.page == "predictions"
        assert preset.filters["min_confidence"] == 0.8
        assert "test" in preset.tags

    def test_get_preset(self, preset_manager):
        """Test getting a preset by ID."""
        preset = preset_manager.create_preset(
            name="Get Test",
            description="Testing get",
            page="signals",
            filters={},
            tags=[]
        )

        retrieved = preset_manager.get_preset(preset.id)
        assert retrieved is not None
        assert retrieved.id == preset.id
        assert retrieved.name == "Get Test"

    def test_get_preset_not_found(self, preset_manager):
        """Test getting a non-existent preset."""
        result = preset_manager.get_preset("nonexistent")
        assert result is None

    def test_update_preset(self, preset_manager):
        """Test updating a preset."""
        preset = preset_manager.create_preset(
            name="Original",
            description="Original description",
            page="predictions",
            filters={"min_confidence": 0.5},
            tags=["original"]
        )

        updated = preset_manager.update_preset(
            preset.id,
            name="Updated",
            description="Updated description",
            filters={"min_confidence": 0.7},
            tags=["updated"]
        )

        assert updated is not None
        assert updated.name == "Updated"
        assert updated.description == "Updated description"
        assert updated.filters["min_confidence"] == 0.7
        assert "updated" in updated.tags

    def test_delete_preset(self, preset_manager):
        """Test deleting a preset."""
        preset = preset_manager.create_preset(
            name="Delete Test",
            description="Testing delete",
            page="data",
            filters={},
            tags=[]
        )

        preset_id = preset.id
        assert preset_id in preset_manager.presets

        result = preset_manager.delete_preset(preset_id)
        assert result is True
        assert preset_id not in preset_manager.presets

    def test_list_presets(self, preset_manager):
        """Test listing all presets."""
        # Create multiple presets
        for i in range(5):
            preset_manager.create_preset(
                name=f"Preset {i}",
                description=f"Description {i}",
                page="predictions",
                filters={},
                tags=[f"tag{i}"]
            )

        presets = preset_manager.list_presets()
        assert len(presets) >= 5

    def test_list_presets_by_page(self, preset_manager):
        """Test listing presets by page."""
        # Create presets for different pages
        preset_manager.create_preset("P1", "D1", "predictions", {}, [])
        preset_manager.create_preset("P2", "D2", "predictions", {}, [])
        preset_manager.create_preset("S1", "D3", "signals", {}, [])
        preset_manager.create_preset("D1", "D4", "data", {}, [])

        prediction_presets = preset_manager.list_presets_by_page("predictions")
        assert len(prediction_presets) >= 2
        assert all(p.page == "predictions" for p in prediction_presets)

        signal_presets = preset_manager.list_presets_by_page("signals")
        assert len(signal_presets) >= 1
        assert all(p.page == "signals" for p in signal_presets)

    def test_search_presets(self, preset_manager):
        """Test searching presets."""
        # Create presets with different names and tags
        preset_manager.create_preset(
            "High Confidence AAPL",
            "High confidence AAPL signals",
            "predictions",
            {"min_confidence": 0.8},
            ["high-confidence", "AAPL"]
        )

        preset_manager.create_preset(
            "Recent GOOGL",
            "Recent GOOGL signals",
            "predictions",
            {"days": 7},
            ["recent", "GOOGL"]
        )

        preset_manager.create_preset(
            "NASDAQ Overview",
            "NASDAQ market overview",
            "data",
            {"exchange": "NASDAQ"},
            ["overview", "NASDAQ"]
        )

        # Search by name
        results = preset_manager.search_presets("AAPL")
        assert len(results) >= 1
        assert any("AAPL" in p.name for p in results)

        # Search by tag
        results = preset_manager.search_presets("high-confidence")
        assert len(results) >= 1
        assert any("high-confidence" in p.tags for p in results)

        # Search by description
        results = preset_manager.search_presets("GOOGL")
        assert len(results) >= 1
        assert any("GOOGL" in p.description for p in results)

        # Search case-insensitive
        results = preset_manager.search_presets("NASDAQ")
        assert len(results) >= 1
        assert any("NASDAQ" in p.name or "NASDAQ" in p.description for p in results)

    def test_save_and_load_presets(self, preset_manager):
        """Test saving and loading presets from storage."""
        # Create some presets
        preset1 = preset_manager.create_preset(
            "Save Test 1",
            "Testing save 1",
            "predictions",
            {"min_confidence": 0.8},
            ["save-test"]
        )

        preset2 = preset_manager.create_preset(
            "Save Test 2",
            "Testing save 2",
            "signals",
            {"days": 7},
            ["save-test"]
        )

        with patch('builtins.open', mock_open()) as mock_file, \
             patch('json.dump') as mock_json_dump:

            preset_manager.save_presets()

            # Verify files were written
            assert mock_json_dump.call_count >= 1

        with patch('builtins.open', mock_open(read_data=json.dumps([]))), \
             patch('json.load', return_value=[]):

            # Reload in a new manager
            new_manager = FilterPresetManager(storage_path="/tmp/test_presets")
            new_manager.load_presets()

            # Verify presets were loaded
            assert len(new_manager.presets) >= 0

    def test_export_presets(self, preset_manager):
        """Test exporting presets to JSON."""
        # Create presets
        preset_manager.create_preset(
            "Export Test 1",
            "Testing export 1",
            "predictions",
            {"min_confidence": 0.8},
            ["export", "test"]
        )

        preset_manager.create_preset(
            "Export Test 2",
            "Testing export 2",
            "signals",
            {"days": 7},
            ["export", "test"]
        )

        export_data = preset_manager.export_presets()

        assert "presets" in export_data
        assert len(export_data["presets"]) >= 2
        assert all("id" in p for p in export_data["presets"])
        assert all("name" in p for p in export_data["presets"])

    def test_import_presets(self, preset_manager):
        """Test importing presets from JSON."""
        import_data = {
            "presets": [
                {
                    "id": "imported_1",
                    "name": "Imported Preset 1",
                    "description": "First imported",
                    "page": "predictions",
                    "filters": {"min_confidence": 0.9},
                    "tags": ["imported"],
                    "created_at": "2024-11-07T12:00:00",
                    "updated_at": "2024-11-07T12:00:00"
                },
                {
                    "id": "imported_2",
                    "name": "Imported Preset 2",
                    "description": "Second imported",
                    "page": "signals",
                    "filters": {"days": 30},
                    "tags": ["imported"],
                    "created_at": "2024-11-07T12:00:00",
                    "updated_at": "2024-11-07T12:00:00"
                }
            ]
        }

        imported_count = preset_manager.import_presets(import_data)

        assert imported_count == 2
        assert "imported_1" in preset_manager.presets
        assert "imported_2" in preset_manager.presets

        preset1 = preset_manager.get_preset("imported_1")
        assert preset1.name == "Imported Preset 1"
        assert preset1.filters["min_confidence"] == 0.9

    def test_get_or_create_default(self, preset_manager):
        """Test getting or creating default preset."""
        # Get default for a page
        default = preset_manager.get_or_create_default("predictions")

        assert default is not None
        assert default.page == "predictions"
        assert "Default" in default.name

    def test_get_filter_history(self, preset_manager):
        """Test getting filter history."""
        # Simulate applying filters
        preset_manager.add_to_history("predictions", {"min_confidence": 0.8})
        preset_manager.add_to_history("predictions", {"min_confidence": 0.9})
        preset_manager.add_to_history("signals", {"days": 7})

        history = preset_manager.get_filter_history("predictions")

        assert len(history) >= 2
        # History is ordered by most recent first
        assert history[0]["filters"]["min_confidence"] == 0.9

    def test_clear_history(self, preset_manager):
        """Test clearing filter history."""
        # Add to history
        preset_manager.add_to_history("predictions", {"min_confidence": 0.8})
        preset_manager.add_to_history("signals", {"days": 7})

        assert len(preset_manager.filter_history) > 0

        preset_manager.clear_history()

        assert len(preset_manager.filter_history) == 0

    def test_create_preset_with_special_characters(self, preset_manager):
        """Test creating presets with special characters in names."""
        preset = preset_manager.create_preset(
            "Test (Special) {Characters}",
            "Description with 'quotes' and \"double quotes\"",
            "predictions",
            {"min_confidence": 0.8},
            ["test", "special-chars_123"]
        )

        assert preset.name == "Test (Special) {Characters}"
        assert "'quotes'" in preset.description
        assert '"double quotes"' in preset.description
        assert "special-chars_123" in preset.tags

    def test_empty_filters(self, preset_manager):
        """Test creating preset with empty filters."""
        preset = preset_manager.create_preset(
            "Empty Filters",
            "Preset with no filters",
            "data",
            {},
            []
        )

        assert preset.filters == {}
        assert preset.tags == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
