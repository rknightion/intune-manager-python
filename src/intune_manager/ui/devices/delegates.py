from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter
from PySide6.QtWidgets import QStyleOptionViewItem, QStyledItemDelegate

from intune_manager.data import ComplianceState, ManagedDevice


@dataclass(frozen=True, slots=True)
class _BadgeDefinition:
    text: str
    color: QColor


_COMPLIANCE_STYLES: dict[ComplianceState | None, _BadgeDefinition] = {
    ComplianceState.COMPLIANT: _BadgeDefinition("Compliant", QColor("#2E7D32")),
    ComplianceState.NONCOMPLIANT: _BadgeDefinition("Not compliant", QColor("#C62828")),
    ComplianceState.IN_GRACE_PERIOD: _BadgeDefinition(
        "Grace period", QColor("#F9A825")
    ),
    ComplianceState.ERROR: _BadgeDefinition("Error", QColor("#D84315")),
    ComplianceState.CONFLICT: _BadgeDefinition("Conflict", QColor("#8E24AA")),
    ComplianceState.CONFIG_MANAGER: _BadgeDefinition(
        "Config Manager", QColor("#1565C0")
    ),
    ComplianceState.UNKNOWN: _BadgeDefinition("Unknown", QColor("#546E7A")),
    None: _BadgeDefinition("Unknown", QColor("#546E7A")),
}


def _text_color_for(background: QColor) -> QColor:
    luminance = (
        0.299 * background.red()
        + 0.587 * background.green()
        + 0.114 * background.blue()
    )
    return QColor("#000000") if luminance > 186 else QColor("#FFFFFF")


def _device_from_index(index) -> ManagedDevice | None:
    device = index.data(Qt.ItemDataRole.UserRole)
    if isinstance(device, ManagedDevice):
        return device
    return None


class DeviceSummaryDelegate(QStyledItemDelegate):
    """Render device cells with two-line summaries."""

    def paint(  # noqa: D401
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index,
    ) -> None:
        device = _device_from_index(index)
        option_copy = QStyleOptionViewItem(option)
        option_copy.text = ""
        super().paint(painter, option_copy, index)

        if device is None:
            return

        painter.save()
        painter.setRenderHint(QPainter.TextAntialiasing, True)

        name = device.device_name or "Unnamed device"
        os_label = device.operating_system or ""
        if device.os_version:
            os_label = f"{os_label} {device.os_version}".strip()
        subtitle_parts = [value for value in [os_label, device.model] if value]
        subtitle = " • ".join(subtitle_parts)

        rect = option.rect.adjusted(12, 6, -12, -8)
        palette = option.palette
        selected = bool(option.state & QStyleOptionViewItem.StateFlag.State_Selected)
        name_color = (
            palette.color(palette.ColorRole.HighlightedText)
            if selected
            else palette.color(palette.ColorRole.Text)
        )
        subtitle_color = (
            palette.color(palette.ColorRole.HighlightedText)
            if selected
            else palette.color(palette.ColorRole.Mid)
        )

        name_font = QFont(option.font)
        name_font.setBold(True)
        painter.setFont(name_font)

        metrics = QFontMetrics(name_font)
        name_text = metrics.elidedText(name, Qt.TextElideMode.ElideRight, rect.width())
        painter.setPen(name_color)
        painter.drawText(
            rect,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
            name_text,
        )

        if subtitle:
            subtitle_font = QFont(option.font)
            subtitle_font.setPointSizeF(max(subtitle_font.pointSizeF() - 1.0, 8.0))
            painter.setFont(subtitle_font)
            subtitle_metrics = QFontMetrics(subtitle_font)
            subtitle_text = subtitle_metrics.elidedText(
                subtitle, Qt.TextElideMode.ElideRight, rect.width()
            )
            subtitle_rect = QRectF(
                rect.left(),
                rect.top() + metrics.height() + 2,
                rect.width(),
                rect.height() - metrics.height() - 2,
            )
            painter.setPen(subtitle_color)
            painter.drawText(
                subtitle_rect,
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
                subtitle_text,
            )

        painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index) -> QSize:  # noqa: D401
        base = super().sizeHint(option, index)
        metrics = QFontMetrics(option.font)
        height = metrics.height() * 2 + 8
        return QSize(base.width(), max(base.height(), height))


class ComplianceBadgeDelegate(QStyledItemDelegate):
    """Display compliance state as a rounded badge."""

    def paint(  # noqa: D401
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index,
    ) -> None:
        device = _device_from_index(index)
        definition = _COMPLIANCE_STYLES.get(
            getattr(device, "compliance_state", None),
            _COMPLIANCE_STYLES[None],
        )

        option_copy = QStyleOptionViewItem(option)
        option_copy.text = ""
        super().paint(painter, option_copy, index)

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)

        palette = option.palette
        selected = bool(option.state & QStyleOptionViewItem.StateFlag.State_Selected)

        bg_color = QColor(definition.color)
        if selected:
            highlight = palette.color(palette.ColorRole.Highlight)
            bg_color = QColor(
                int((bg_color.red() + highlight.red()) / 2),
                int((bg_color.green() + highlight.green()) / 2),
                int((bg_color.blue() + highlight.blue()) / 2),
            )

        text_color = (
            palette.color(palette.ColorRole.HighlightedText)
            if selected
            else _text_color_for(bg_color)
        )

        rect = option.rect.adjusted(12, 10, -12, -10)
        metrics = QFontMetrics(option.font)
        text = metrics.elidedText(
            definition.text, Qt.TextElideMode.ElideRight, rect.width() - 16
        )
        padding_x = 12
        padding_y = 6
        badge_width = metrics.horizontalAdvance(text) + padding_x * 2
        badge_height = metrics.height() + padding_y
        badge_width = min(badge_width, rect.width())

        badge_rect = QRectF(
            rect.left(),
            rect.center().y() - badge_height / 2,
            badge_width,
            badge_height,
        )

        painter.setBrush(bg_color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(badge_rect, badge_height / 2.2, badge_height / 2.2)

        painter.setPen(text_color)
        painter.drawText(
            badge_rect,
            Qt.AlignmentFlag.AlignCenter,
            text,
        )

        painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index) -> QSize:  # noqa: D401
        base = super().sizeHint(option, index)
        metrics = QFontMetrics(option.font)
        height = metrics.height() + 14
        return QSize(base.width(), max(base.height(), height))


__all__ = ["ComplianceBadgeDelegate", "DeviceSummaryDelegate"]
