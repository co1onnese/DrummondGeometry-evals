"""Integration tests for dashboard end-to-end workflows."""

import pytest
import pandas as pd
from unittest.mock import Mock, patch, MagicMock, AsyncMock
from datetime import datetime


class TestRealtimeWorkflow:
    """Test real-time data streaming workflow."""

    @pytest.mark.asyncio
    async def test_websocket_to_dashboard_integration(self):
        """Test WebSocket server sending data to dashboard client."""
        from dgas.dashboard.websocket_server import WebSocketServer, EventType

        # Create server
        server = WebSocketServer(host="127.0.0.1", port=8768)

        # Mock WebSocket connections
        ws1 = Mock()
        ws1.send_json = AsyncMock()
        ws2 = Mock()
        ws2.send_json = AsyncMock()

        # Add clients
        await server._add_client("dashboard1", ws1)
        await server._add_client("dashboard2", ws2)

        # Broadcast prediction event
        event = {
            "type": EventType.PREDICTION,
            "data": {
                "symbol": "AAPL",
                "confidence": 0.85,
                "signal": "BUY"
            },
            "timestamp": datetime.now().isoformat()
        }

        await server.broadcast_event(event)

        # Verify both clients received the event
        ws1.send_json.assert_called_once_with(event)
        ws2.send_json.assert_called_once_with(event)

    @pytest.mark.asyncio
    async def test_alert_rule_to_notification_workflow(self):
        """Test alert rule triggering notification."""
        from dgas.dashboard.services.notification_service import (
            NotificationService,
            NotificationType,
            Priority
        )
        from dgas.dashboard.utils.alert_rules import (
            AlertRuleManager,
            RuleCondition
        )

        # Create services
        notification_service = NotificationService()
        alert_manager = AlertRuleManager()

        # Add a rule for high confidence predictions
        rule = AlertRule(
            name="High Confidence Alert",
            condition=RuleCondition.CONFIDENCE_GREATER,
            threshold=0.8,
            notification_type=NotificationType.PREDICTION,
            priority=Priority.HIGH,
            enabled=True
        )
        alert_manager.add_rule(rule)

        # Simulate incoming data
        data = {
            "type": "prediction",
            "symbol": "AAPL",
            "confidence": 0.92
        }

        # Check if rule triggers
        notifications = alert_manager.check_data(data)

        # Verify notification was created
        assert len(notifications) > 0
        assert notifications[0].type == NotificationType.PREDICTION
        assert notifications[0].priority == Priority.HIGH

        # Add to notification service
        notification_service.add_notification(notifications[0])

        # Verify it's in the service
        assert len(notification_service.notifications) == 1
        assert notification_service.get_unread_count() == 1


class TestDashboardCreationWorkflow:
    """Test custom dashboard creation workflow."""

    def test_widget_creation_and_layout(self):
        """Test creating widgets and arranging them in layout."""
        from dgas.dashboard.widgets.base import (
            WidgetConfig,
            WidgetRegistry,
            WidgetType,
            GridPosition
        )
        from dgas.dashboard.layout.manager import DashboardLayout

        # Create widget registry
        registry = WidgetRegistry()

        # Create widgets
        metric_config = WidgetConfig(
            id="metric_1",
            type=WidgetType.METRIC,
            title="Total Predictions",
            data_source="predictions",
            grid_position=GridPosition(row=0, col=0, width=3, height=2),
            config={"format": "number"}
        )

        chart_config = WidgetConfig(
            id="chart_1",
            type=WidgetType.CHART,
            title="Price Chart",
            data_source="market_data",
            grid_position=GridPosition(row=0, col=3, width=6, height=4),
            config={"chart_type": "line"}
        )

        table_config = WidgetConfig(
            id="table_1",
            type=WidgetType.TABLE,
            title="Signals",
            data_source="signals",
            grid_position=GridPosition(row=4, col=0, width=12, height=6),
            config={"paginate": True}
        )

        # Create widgets from registry
        metric_widget = registry.create_widget("metric", metric_config)
        chart_widget = registry.create_widget("chart", chart_config)
        table_widget = registry.create_widget("table", table_config)

        # Create layout
        layout = DashboardLayout(
            id="test_layout",
            name="Test Dashboard",
            description="Integration test layout",
            widgets=[metric_config, chart_config, table_config],
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat()
        )

        # Verify layout
        assert len(layout.widgets) == 3
        assert layout.get_widget("metric_1") is not None
        assert layout.get_widget("chart_1") is not None
        assert layout.get_widget("table_1") is not None

    def test_save_and_load_dashboard(self):
        """Test saving and loading dashboard layout."""
        from dgas.dashboard.layout.manager import LayoutManager

        # Create manager
        manager = LayoutManager(storage_path="/tmp/test_layouts")

        # Create layout
        layout = manager.create_layout(
            name="Save Load Test",
            description="Testing save and load"
        )

        # Mock save
        with patch('builtins.open', MagicMock()), \
             patch('json.dump') as mock_json:

            manager.save_layout(layout)

            # Verify save was called
            mock_json.assert_called()

        # Mock load
        layout_data = {
            "id": "loaded_layout",
            "name": "Loaded Layout",
            "description": "Testing load",
            "widgets": [],
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }

        with patch('builtins.open', MagicMock()), \
             patch('json.load', return_value=layout_data):

            loaded_layout = manager.load_layout("loaded_layout")
            assert loaded_layout is not None
            assert loaded_layout.name == "Loaded Layout"


class TestFilterPresetWorkflow:
    """Test filter preset save/load workflow."""

    def test_create_and_apply_preset(self):
        """Test creating a filter preset and applying it."""
        from dgas.dashboard.filters.preset_manager import FilterPresetManager

        # Create manager
        manager = FilterPresetManager(storage_path="/tmp/test_presets")

        # Create preset
        preset = manager.create_preset(
            name="High Confidence AAPL",
            description="Filter for high confidence AAPL predictions",
            page="predictions",
            filters={
                "symbol": "AAPL",
                "min_confidence": 0.8,
                "days": 7
            },
            tags=["AAPL", "high-confidence"]
        )

        # Verify preset was created
        assert preset.id in manager.presets
        assert preset.name == "High Confidence AAPL"
        assert preset.filters["symbol"] == "AAPL"
        assert preset.filters["min_confidence"] == 0.8

        # Get preset
        retrieved = manager.get_preset(preset.id)
        assert retrieved is not None
        assert retrieved.name == "High Confidence AAPL"

        # Search presets
        results = manager.search_presets("AAPL")
        assert len(results) >= 1
        assert any(p.name == "High Confidence AAPL" for p in results)

    def test_export_import_presets(self):
        """Test exporting and importing presets."""
        from dgas.dashboard.filters.preset_manager import FilterPresetManager

        # Create manager
        manager = FilterPresetManager(storage_path="/tmp/test_presets")

        # Create presets
        manager.create_preset(
            "Preset 1",
            "Description 1",
            "predictions",
            {"min_confidence": 0.8},
            ["tag1"]
        )

        manager.create_preset(
            "Preset 2",
            "Description 2",
            "signals",
            {"days": 7},
            ["tag2"]
        )

        # Export
        export_data = manager.export_presets()
        assert "presets" in export_data
        assert len(export_data["presets"]) >= 2

        # Create new manager and import
        new_manager = FilterPresetManager(storage_path="/tmp/test_presets2")
        import_count = new_manager.import_presets(export_data)

        assert import_count >= 2
        assert len(new_manager.presets) >= 2


class TestExportWorkflow:
    """Test multi-format export workflow."""

    def test_export_same_data_multiple_formats(self):
        """Test exporting the same data to multiple formats."""
        from dgas.dashboard.export.enhanced_exporter import EnhancedExporter

        # Create sample data
        data = pd.DataFrame({
            "symbol": ["AAPL", "GOOGL", "MSFT"],
            "signal_type": ["BUY", "SELL", "BUY"],
            "confidence": [0.85, 0.92, 0.78]
        })

        # Create exporter
        exporter = EnhancedExporter()

        # Mock exports
        with patch('pandas.DataFrame.to_csv') as mock_csv, \
             patch('pandas.ExcelWriter') as mock_excel, \
             patch('builtins.open', MagicMock()), \
             patch('json.dump') as mock_json:

            # Export to all formats
            exporter.export_to_csv(data, "signals")
            exporter.export_to_excel(data, "signals")
            exporter.export_to_json(data, "signals")

            # Verify all were called
            mock_csv.assert_called_once()

        print("Multi-format export test passed")

    def test_comprehensive_report_generation(self):
        """Test generating a comprehensive report."""
        from dgas.dashboard.export.enhanced_exporter import EnhancedExporter

        # Create comprehensive data
        data = {
            "predictions": pd.DataFrame({
                "symbol": ["AAPL", "GOOGL"],
                "confidence": [0.85, 0.92]
            }),
            "signals": pd.DataFrame({
                "symbol": ["MSFT"],
                "signal_type": ["BUY"]
            }),
            "backtests": pd.DataFrame({
                "strategy": ["Strategy1"],
                "return": [0.15]
            })
        }

        # Create exporter
        exporter = EnhancedExporter()

        # Mock comprehensive report
        with patch.object(exporter, 'export_to_excel') as mock_excel, \
             patch.object(exporter, 'export_to_json') as mock_json, \
             patch.object(exporter, 'export_to_pdf_report') as mock_pdf, \
             patch('builtins.open', MagicMock()):

            exporter.create_comprehensive_report(data, "report")

            # Verify all components were exported
            mock_excel.assert_called_once()
            mock_json.assert_called_once()

        print("Comprehensive report test passed")


class TestPerformanceIntegration:
    """Test performance monitoring integration."""

    def test_query_caching_integration(self):
        """Test query execution with caching."""
        from dgas.dashboard.performance.optimizer import (
            PerformanceMonitor,
            CacheManager,
            cached_query
        )

        # Create monitor and cache
        monitor = PerformanceMonitor()
        cache = CacheManager(max_size=10, default_ttl=300)

        # Mock query function
        call_count = 0

        def mock_query():
            nonlocal call_count
            call_count += 1
            return {"result": f"data_{call_count}"}

        # First call - should execute
        result1 = cache.get_or_compute("key1", mock_query, ttl=300)
        assert result1["result"] == "data_1"
        assert call_count == 1

        # Second call - should use cache
        result2 = cache.get_or_compute("key1", mock_query, ttl=300)
        assert result2["result"] == "data_1"
        assert call_count == 1  # Not incremented

        print("Query caching integration test passed")

    def test_performance_monitoring_integration(self):
        """Test performance monitoring with database queries."""
        from dgas.dashboard.performance.optimizer import performance_timer

        monitor = PerformanceMonitor()

        @performance_timer(monitor)
        def sample_database_query():
            # Simulate query execution
            time.sleep(0.01)
            return pd.DataFrame({"col1": [1, 2, 3]})

        # Execute query
        result = sample_database_query()
        assert len(result) == 3

        # Verify performance was recorded
        assert len(monitor.query_times) >= 1

        # Get summary
        summary = monitor.get_performance_summary()
        assert summary["total_queries"] >= 1
        assert summary["average_time"] > 0

        print("Performance monitoring integration test passed")


class TestEndToEndWorkflow:
    """Test complete end-to-end workflows."""

    def test_complete_dashboard_workflow(self):
        """Test complete dashboard creation and usage workflow."""
        from dgas.dashboard.widgets.base import WidgetConfig, WidgetType, GridPosition
        from dgas.dashboard.layout.manager import LayoutManager
        from dgas.dashboard.filters.preset_manager import FilterPresetManager
        from dgas.dashboard.export.enhanced_exporter import EnhancedExporter

        # 1. Create layout
        layout_manager = LayoutManager(storage_path="/tmp/test_e2e")
        layout = layout_manager.create_layout(
            name="E2E Test Dashboard",
            description="End-to-end test"
        )

        # 2. Create widgets (via config)
        metric_config = WidgetConfig(
            id="e2e_metric",
            type=WidgetType.METRIC,
            title="Test Metric",
            data_source="test_data",
            grid_position=GridPosition(row=0, col=0, width=3, height=2),
            config={}
        )
        layout.add_widget(metric_config)

        # 3. Save layout
        with patch('builtins.open', MagicMock()), \
             patch('json.dump') as mock_json:
            layout_manager.save_layout(layout)
            mock_json.assert_called()

        # 4. Create filter preset
        preset_manager = FilterPresetManager(storage_path="/tmp/test_e2e")
        preset = preset_manager.create_preset(
            name="E2E Preset",
            description="End-to-end test preset",
            page="predictions",
            filters={"min_confidence": 0.8},
            tags=["e2e"]
        )

        # 5. Export data
        exporter = EnhancedExporter()
        data = pd.DataFrame({
            "symbol": ["AAPL"],
            "value": [100]
        })

        with patch('pandas.DataFrame.to_csv') as mock_csv, \
             patch('builtins.open', MagicMock()):
            exporter.export_to_csv(data, "e2e_export")
            mock_csv.assert_called()

        # 6. Verify all components work together
        assert layout.id in layout_manager.layouts
        assert preset.id in preset_manager.presets
        assert len(layout.widgets) == 1
        assert preset.filters["min_confidence"] == 0.8

        print("Complete E2E workflow test passed")

    def test_realtime_notification_workflow(self):
        """Test real-time event triggering notification."""
        from dgas.dashboard.websocket_server import WebSocketServer, EventType
        from dgas.dashboard.services.notification_service import NotificationService
        from dgas.dashboard.utils.alert_rules import AlertRuleManager, RuleCondition

        # 1. Set up alert rule
        alert_manager = AlertRuleManager()
        alert_manager.add_rule(
            AlertRule(
                name="High Confidence",
                condition=RuleCondition.CONFIDENCE_GREATER,
                threshold=0.8,
                notification_type="prediction",
                priority="high",
                enabled=True
            )
        )

        # 2. Set up notification service
        notification_service = NotificationService()

        # 3. Simulate high confidence prediction
        data = {
            "type": "prediction",
            "symbol": "AAPL",
            "confidence": 0.92
        }

        # 4. Check if rule triggers
        notifications = alert_manager.check_data(data)
        assert len(notifications) > 0

        # 5. Add to service
        for notif in notifications:
            notification_service.add_notification(notif)

        # 6. Verify
        assert len(notification_service.notifications) > 0
        assert notification_service.get_unread_count() > 0

        print("Real-time notification workflow test passed")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
