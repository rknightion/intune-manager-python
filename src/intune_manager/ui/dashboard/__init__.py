"""Dashboard widgets for the Intune Manager UI."""

from .controller import DashboardSnapshot, ResourceMetric, TenantStatus
from .widgets import DashboardWidget

__all__ = ["DashboardWidget", "DashboardSnapshot", "ResourceMetric", "TenantStatus"]
