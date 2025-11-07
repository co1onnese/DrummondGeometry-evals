"""Dashboard widgets package.

Contains customizable widgets for building dashboards.
"""

from dgas.dashboard.widgets.base import (
    BaseWidget,
    WidgetConfig,
    WidgetRegistry,
)

from dgas.dashboard.widgets.metric import MetricWidget
from dgas.dashboard.widgets.chart import ChartWidget
from dgas.dashboard.widgets.table import TableWidget

__all__ = [
    "BaseWidget",
    "WidgetConfig",
    "WidgetRegistry",
    "MetricWidget",
    "ChartWidget",
    "TableWidget",
]
