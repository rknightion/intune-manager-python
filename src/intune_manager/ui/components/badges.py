from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QWidget


@dataclass(slots=True)
class TenantIdentity:
    display_name: str | None = None
    tenant_id: str | None = None


class TenantBadge(QFrame):
    """Compact badge displaying the active tenant."""

    def __init__(
        self,
        *,
        tenant: TenantIdentity | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("TenantBadge")
        self.setFrameShape(QFrame.Shape.Box)
        self.setStyleSheet(
            "QFrame#TenantBadge {"
            "  border-radius: 10px;"
            "  padding: 4px 12px;"
            "  margin: 2px 8px;"
            "  background-color: rgba(0, 99, 177, 0.12);"
            "  border: 1px solid rgba(0, 99, 177, 0.35);"
            "}"
            "QLabel#TenantLabel {"
            "  font-weight: 600;"
            "}"
            "QLabel#TenantId {"
            "  color: palette(mid);"
            "  font-family: 'SFMono-Regular', 'Courier New', monospace;"
            "  font-size: 11px;"
            "}"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._label = QLabel()
        self._label.setObjectName("TenantLabel")
        self._label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        layout.addWidget(self._label)

        self._id_label = QLabel()
        self._id_label.setObjectName("TenantId")
        self._id_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        layout.addWidget(self._id_label)

        layout.addStretch()
        self.set_tenant(tenant)

    def set_tenant(self, tenant: TenantIdentity | None) -> None:
        if tenant is None:
            self._label.setText("Tenant: Not configured")
            self._id_label.setVisible(False)
            return

        name = tenant.display_name or "Unnamed tenant"
        self._label.setText(name)

        if tenant.tenant_id:
            self._id_label.setText(tenant.tenant_id)
            self._id_label.setVisible(True)
        else:
            self._id_label.clear()
            self._id_label.setVisible(False)


__all__ = ["TenantBadge", "TenantIdentity"]
