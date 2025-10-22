from __future__ import annotations

from pathlib import Path
from typing import Sequence

from PySide6.QtWidgets import QFileDialog, QMessageBox, QWidget


def show_error_dialog(
    parent: QWidget,
    title: str,
    message: str,
    *,
    details: str | None = None,
) -> None:
    dialog = QMessageBox(QMessageBox.Icon.Critical, title, message, QMessageBox.StandardButton.Close, parent)
    dialog.setInformativeText(message)
    if details:
        dialog.setDetailedText(details)
    dialog.exec()


def show_info_dialog(
    parent: QWidget,
    title: str,
    message: str,
    *,
    informative: str | None = None,
) -> None:
    dialog = QMessageBox(QMessageBox.Icon.Information, title, message, QMessageBox.StandardButton.Ok, parent)
    if informative:
        dialog.setInformativeText(informative)
    dialog.exec()


def ask_confirmation(
    parent: QWidget,
    title: str,
    question: str,
    *,
    ok_label: str = "Continue",
    cancel_label: str = "Cancel",
) -> bool:
    box = QMessageBox(parent)
    box.setWindowTitle(title)
    box.setText(question)
    box.setIcon(QMessageBox.Icon.Question)
    ok_button = box.addButton(ok_label, QMessageBox.ButtonRole.AcceptRole)
    box.addButton(cancel_label, QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(ok_button)
    box.exec()
    return box.clickedButton() is ok_button


def open_file_dialog(
    parent: QWidget,
    *,
    caption: str,
    directory: str | Path | None = None,
    name_filters: Sequence[str] | None = None,
) -> Path | None:
    dialog = QFileDialog(parent, caption)
    dialog.setFileMode(QFileDialog.FileMode.ExistingFile)
    if directory:
        dialog.setDirectory(str(directory))
    if name_filters:
        dialog.setNameFilters(list(name_filters))
    if dialog.exec():
        selected = dialog.selectedFiles()
        if selected:
            return Path(selected[0])
    return None


def save_file_dialog(
    parent: QWidget,
    *,
    caption: str,
    directory: str | Path | None = None,
    default_suffix: str | None = None,
    name_filters: Sequence[str] | None = None,
) -> Path | None:
    dialog = QFileDialog(parent, caption)
    dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
    if directory:
        dialog.setDirectory(str(directory))
    if default_suffix:
        dialog.setDefaultSuffix(default_suffix)
    if name_filters:
        dialog.setNameFilters(list(name_filters))
    if dialog.exec():
        selected = dialog.selectedFiles()
        if selected:
            return Path(selected[0])
    return None


__all__ = [
    "show_error_dialog",
    "show_info_dialog",
    "ask_confirmation",
    "open_file_dialog",
    "save_file_dialog",
]
