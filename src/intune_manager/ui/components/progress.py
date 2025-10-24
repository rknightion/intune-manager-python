from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from intune_manager.utils import CancellationTokenSource, ProgressUpdate


class ProgressDialog(QDialog):
    """Reusable modal progress dialog with optional cancellation support."""

    def __init__(
        self,
        *,
        title: str,
        parent: QWidget | None = None,
        message: str | None = None,
        token_source: CancellationTokenSource | None = None,
        cancel_text: str = "Cancel",
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setWindowModality(Qt.WindowModality.WindowModal)

        self._token_source = token_source
        self._cancelled = False

        self._label = QLabel(message or "", self)
        self._label.setWordWrap(True)

        self._progress = QProgressBar(self)
        self._progress.setRange(0, 0)
        self._progress.setValue(0)

        self._buttons = QDialogButtonBox(self)
        self._cancel_button = QPushButton(cancel_text, self)
        self._buttons.addButton(
            self._cancel_button, QDialogButtonBox.ButtonRole.RejectRole
        )
        self._cancel_button.clicked.connect(self.cancel)  # type: ignore[arg-type]

        layout = QVBoxLayout(self)
        layout.addWidget(self._label)
        layout.addWidget(self._progress)
        layout.addWidget(self._buttons)

        if token_source is None:
            self._cancel_button.setVisible(False)

    # ------------------------------------------------------------------ Public API

    def update_progress(self, update: ProgressUpdate) -> None:
        """Update the dialog with a new progress snapshot."""

        total = update.total or 0
        if total <= 0:
            self._progress.setRange(0, 0)
        else:
            self._progress.setRange(0, total)
            self._progress.setValue(update.completed + update.failed)

        if update.current:
            self._label.setText(update.current)

    def set_message(self, message: str) -> None:
        """Update the descriptive text independently of progress."""

        self._label.setText(message)

    def cancel(self) -> None:
        """Trigger cancellation and close the dialog."""

        if self._cancelled:
            return
        self._cancelled = True
        if self._token_source is not None:
            self._token_source.cancel(reason="User cancelled operation")
        self.reject()

    def reject(self) -> None:  # noqa: D401 - Qt override
        if self._cancelled or self._token_source is None:
            super().reject()
            return
        # Route close events through cancel path to propagate token cancellation.
        self.cancel()

    def mark_finished(self) -> None:
        """Disable cancellation once the underlying operation completes."""

        self._cancel_button.setEnabled(False)
        self._cancel_button.setVisible(False)
        self._progress.setRange(0, 1)
        self._progress.setValue(1)

    def is_cancelled(self) -> bool:
        return self._cancelled


__all__ = ["ProgressDialog"]
