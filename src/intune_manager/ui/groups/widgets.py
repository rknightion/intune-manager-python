from __future__ import annotations

import re
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Iterable, List

from PySide6.QtCore import QItemSelectionModel, QModelIndex, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QSplitter,
    QTabWidget,
    QTableView,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from intune_manager.data import DirectoryGroup, GroupMember
from intune_manager.services import ServiceErrorEvent, ServiceRegistry
from intune_manager.services.groups import GroupMembershipEvent
from intune_manager.services.base import MutationStatus
from intune_manager.ui.components import (
    CommandAction,
    InlineStatusMessage,
    PageScaffold,
    ProgressDialog,
    ToastLevel,
    UIContext,
    stage_groups,
    make_toolbar_button,
)
from intune_manager.utils import (
    CancellationError,
    CancellationTokenSource,
    get_logger,
)
from intune_manager.utils.errors import ErrorSeverity, describe_exception

from .controller import GroupController
from .models import GroupFilterProxyModel, GroupTableModel, _group_type_label


logger = get_logger(__name__)


def _toast_level_for(severity: ErrorSeverity) -> ToastLevel:
    try:
        return ToastLevel(severity.value)
    except ValueError:  # pragma: no cover - defensive mapping fallback
        return ToastLevel.ERROR


class GroupDetailPane(QWidget):
    """Display selected group metadata and membership."""

    members_next_requested = Signal()
    members_prev_requested = Signal()
    membersRefreshRequested = Signal()
    ownersRefreshRequested = Signal()

    def __init__(self, *, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        self._title_label = QLabel("Select a group")
        title_font = self._title_label.font()
        title_font.setPointSizeF(title_font.pointSizeF() + 2)
        title_font.setWeight(QFont.Weight.DemiBold)
        self._title_label.setFont(title_font)
        layout.addWidget(self._title_label)

        self._description_label = QLabel()
        self._description_label.setWordWrap(True)
        self._description_label.setStyleSheet("color: palette(mid);")
        layout.addWidget(self._description_label)

        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(6)

        self._fields: dict[str, QLabel] = {}
        for key, label in [
            ("type", "Type"),
            ("mail", "Mail"),
            ("security", "Security enabled"),
            ("mail_enabled", "Mail enabled"),
            ("membership_rule", "Membership rule"),
        ]:
            value_label = QLabel("—")
            value_label.setWordWrap(True)
            self._fields[key] = value_label
            form.addRow(f"{label}:", value_label)

        layout.addLayout(form)

        members_label = QLabel("Members")
        members_label.setStyleSheet("font-weight: 600;")
        layout.addWidget(members_label)

        member_controls = QHBoxLayout()
        member_controls.setContentsMargins(0, 0, 0, 0)
        member_controls.setSpacing(6)

        self._member_refresh_button = QToolButton()
        self._member_refresh_button.setText("Refresh")
        self._member_refresh_button.clicked.connect(
            lambda: self.membersRefreshRequested.emit()
        )
        member_controls.addWidget(self._member_refresh_button)

        self._member_prev_button = QToolButton()
        self._member_prev_button.setText("Previous")
        self._member_prev_button.setEnabled(False)
        self._member_prev_button.clicked.connect(
            lambda: self.members_prev_requested.emit()
        )
        member_controls.addWidget(self._member_prev_button)

        self._member_next_button = QToolButton()
        self._member_next_button.setText("Next")
        self._member_next_button.setEnabled(False)
        self._member_next_button.clicked.connect(
            lambda: self.members_next_requested.emit()
        )
        member_controls.addWidget(self._member_next_button)

        member_controls.addStretch()

        self._member_page_label = QLabel("Members not loaded.")
        self._member_page_label.setStyleSheet("color: palette(mid);")
        member_controls.addWidget(self._member_page_label)

        layout.addLayout(member_controls)

        self._members_list = QListWidget()
        self._members_list.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        layout.addWidget(self._members_list, stretch=1)
        self._members_list.currentItemChanged.connect(
            self._handle_member_selection_changed
        )

        self._member_detail_label = QLabel("Select a member to view details.")
        self._member_detail_label.setStyleSheet("color: palette(mid);")
        self._member_detail_label.setWordWrap(True)
        layout.addWidget(self._member_detail_label)

        self._member_status_label = QLabel("Load members to view membership details.")
        self._member_status_label.setStyleSheet("color: palette(mid);")
        layout.addWidget(self._member_status_label)

        self._member_lookup: dict[str, GroupMember] = {}

        owners_label = QLabel("Owners")
        owners_label.setStyleSheet("font-weight: 600;")
        layout.addWidget(owners_label)

        owner_controls = QHBoxLayout()
        owner_controls.setContentsMargins(0, 0, 0, 0)
        owner_controls.setSpacing(6)
        self._owner_refresh_button = QToolButton()
        self._owner_refresh_button.setText("Refresh")
        self._owner_refresh_button.clicked.connect(
            lambda: self.ownersRefreshRequested.emit()
        )
        owner_controls.addWidget(self._owner_refresh_button)
        owner_controls.addStretch()
        layout.addLayout(owner_controls)

        self._owners_list = QListWidget()
        self._owners_list.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        layout.addWidget(self._owners_list, stretch=1)

        self._owner_status_label = QLabel("Load owners to view ownership details.")
        self._owner_status_label.setStyleSheet("color: palette(mid);")
        layout.addWidget(self._owner_status_label)

        layout.addStretch()

    def display_group(self, group: DirectoryGroup | None) -> None:
        if group is None:
            self._title_label.setText("Select a group")
            self._description_label.setText("")
            for field in self._fields.values():
                field.setText("—")
            self.clear_members()
            return

        self._title_label.setText(group.display_name)
        self._description_label.setText(group.description or "")
        self._set_field("type", _group_type_label(group))
        self._set_field("mail", group.mail or group.mail_nickname)
        self._set_field("security", "Yes" if group.security_enabled else "No")
        self._set_field("mail_enabled", "Yes" if group.mail_enabled else "No")
        self._set_field("membership_rule", group.membership_rule or "—")
        self.clear_members()
        self.clear_owners()

    def clear_members(self) -> None:
        self._members_list.clear()
        placeholder = QListWidgetItem("Membership not loaded.")
        placeholder.setFlags(Qt.ItemFlag.NoItemFlags)
        self._members_list.addItem(placeholder)
        self._member_status_label.setText("Load members to view membership details.")
        self._member_detail_label.setText("Select a member to view details.")
        self._member_lookup.clear()
        self._update_member_controls(page_index=None, has_more=False, total_loaded=None)

    def clear_owners(self) -> None:
        self._owners_list.clear()
        placeholder = QListWidgetItem("Owner list not loaded.")
        placeholder.setFlags(Qt.ItemFlag.NoItemFlags)
        self._owners_list.addItem(placeholder)
        self._owner_status_label.setText("Load owners to view ownership details.")

    @staticmethod
    def _format_age(timestamp: datetime | None) -> str:
        if timestamp is None:
            return "never"
        reference = datetime.now(UTC)
        if timestamp.tzinfo is None:
            normalised = timestamp.replace(tzinfo=UTC)
        else:
            normalised = timestamp.astimezone(UTC)
        delta = reference - normalised
        if delta < timedelta(seconds=90):
            return "moments ago"
        minutes = delta.total_seconds() / 60
        if minutes < 90:
            count = max(int(minutes), 1)
            return f"{count} minute{'s' if count != 1 else ''} ago"
        hours = minutes / 60
        if hours < 36:
            count = max(int(hours), 1)
            return f"{count} hour{'s' if count != 1 else ''} ago"
        return normalised.astimezone().strftime("%Y-%m-%d %H:%M")

    def set_members(
        self,
        members: Iterable[GroupMember],
        *,
        loading: bool = False,
        page_index: int | None = None,
        has_more: bool | None = None,
        total_loaded: int | None = None,
        refreshed_at: datetime | None = None,
    ) -> None:
        self._members_list.clear()
        if loading:
            placeholder = QListWidgetItem("Loading members…")
            placeholder.setFlags(Qt.ItemFlag.NoItemFlags)
            self._members_list.addItem(placeholder)
            self._member_status_label.setText("Fetching members from Microsoft Graph…")
            self._member_detail_label.setText("Fetching members…")
            self._update_member_controls(
                page_index=None, has_more=False, total_loaded=None
            )
            return

        members_list = list(members)
        self._member_lookup = {
            member.id: member for member in members_list if member.id
        }
        if not members_list:
            placeholder = QListWidgetItem("No members found.")
            placeholder.setFlags(Qt.ItemFlag.NoItemFlags)
            self._members_list.addItem(placeholder)
            if refreshed_at:
                age = self._format_age(refreshed_at)
                self._member_status_label.setText(
                    f"Group has no members. Loaded {age}."
                )
            else:
                self._member_status_label.setText("Group has no members.")
            self._member_detail_label.setText("Group has no members.")
            self._update_member_controls(
                page_index=page_index,
                has_more=has_more or False,
                total_loaded=total_loaded,
            )
            return

        for member in members_list:
            name = (
                member.display_name
                or member.user_principal_name
                or member.mail
                or member.id
            )
            detail = member.user_principal_name or member.mail or ""
            text = name if not detail else f"{name} — {detail}"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, member.id)
            self._members_list.addItem(item)
        summary = [f"{len(members_list)} members in page"]
        if total_loaded is not None:
            summary.append(f"{total_loaded} loaded")
        if refreshed_at:
            summary.append(f"Loaded {self._format_age(refreshed_at)}")
        self._member_status_label.setText(" • ".join(summary))
        first_item = self._members_list.item(0)
        if first_item is not None and first_item.flags() & Qt.ItemFlag.ItemIsSelectable:
            self._members_list.setCurrentItem(first_item)
            self._update_member_detail(first_item.data(Qt.ItemDataRole.UserRole))
        else:
            self._member_detail_label.setText("Select a member to view details.")
        self._update_member_controls(
            page_index=page_index, has_more=has_more or False, total_loaded=total_loaded
        )

    def _handle_member_selection_changed(
        self,
        current: QListWidgetItem | None,
        previous: QListWidgetItem | None,
    ) -> None:
        if current is None:
            self._member_detail_label.setText("Select a member to view details.")
            return
        member_id = current.data(Qt.ItemDataRole.UserRole)
        self._update_member_detail(member_id)

    def _update_member_controls(
        self,
        *,
        page_index: int | None,
        has_more: bool,
        total_loaded: int | None,
    ) -> None:
        if page_index is None:
            self._member_prev_button.setEnabled(False)
            self._member_next_button.setEnabled(False)
            self._member_page_label.setText("Members not loaded.")
            return

        page_number = page_index + 1
        summary_parts = [f"Page {page_number}"]
        if total_loaded is not None:
            summary_parts.append(f"{total_loaded} loaded")
        if has_more:
            summary_parts.append("more available")
        self._member_page_label.setText(" • ".join(summary_parts))
        self._member_prev_button.setEnabled(page_index > 0)
        self._member_next_button.setEnabled(has_more)

    def _update_member_detail(self, member_id: str | None) -> None:
        if not member_id:
            self._member_detail_label.setText("Select a member to view details.")
            return
        member = self._member_lookup.get(member_id)
        if member is None:
            self._member_detail_label.setText(
                "Member details unavailable (not cached)."
            )
            return
        detail_lines = []
        if member.display_name:
            detail_lines.append(f"Name: {member.display_name}")
        if member.user_principal_name:
            detail_lines.append(f"UPN: {member.user_principal_name}")
        if member.mail:
            detail_lines.append(f"Mail: {member.mail}")
        detail_lines.append(f"Object ID: {member.id}")
        self._member_detail_label.setText("\n".join(detail_lines))

    def set_owners(
        self,
        owners: Iterable[GroupMember],
        *,
        loading: bool = False,
        refreshed_at: datetime | None = None,
    ) -> None:
        self._owners_list.clear()
        if loading:
            placeholder = QListWidgetItem("Loading owners…")
            placeholder.setFlags(Qt.ItemFlag.NoItemFlags)
            self._owners_list.addItem(placeholder)
            self._owner_status_label.setText("Fetching owners from Microsoft Graph…")
            return

        owners_list = list(owners)
        if not owners_list:
            placeholder = QListWidgetItem("No owners recorded.")
            placeholder.setFlags(Qt.ItemFlag.NoItemFlags)
            self._owners_list.addItem(placeholder)
            if refreshed_at:
                self._owner_status_label.setText(
                    f"Group has no owners. Loaded {self._format_age(refreshed_at)}."
                )
            else:
                self._owner_status_label.setText("Group has no owners.")
            return

        for owner in owners_list:
            name = (
                owner.display_name
                or owner.user_principal_name
                or owner.mail
                or owner.id
            )
            detail = owner.user_principal_name or owner.mail or ""
            text = name if not detail else f"{name} — {detail}"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, owner.id)
            self._owners_list.addItem(item)
        summary = [f"{len(owners_list)} owners loaded"]
        if refreshed_at:
            summary.append(f"Loaded {self._format_age(refreshed_at)}")
        self._owner_status_label.setText(" • ".join(summary))

    def selected_member_id(self) -> str | None:
        item = self._members_list.currentItem()
        if item is None:
            return None
        return item.data(Qt.ItemDataRole.UserRole)

    def _set_field(self, key: str, value: object | None) -> None:
        label = self._fields.get(key)
        if label:
            label.setText(str(value) if value not in {None, ""} else "—")


class GroupCreateDialog(QDialog):
    """Simple dialog for creating a new group."""

    def __init__(self, *, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Create group")
        self.resize(420, 260)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(8)

        self._name_input = QLineEdit()
        self._description_input = QLineEdit()
        self._type_combo = QComboBox()
        self._type_combo.addItems(["Security", "Microsoft 365", "Dynamic"])

        form.addRow("Display name", self._name_input)
        form.addRow("Description", self._description_input)
        form.addRow("Type", self._type_combo)

        layout.addLayout(form)

        self._button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        self._button_box.accepted.connect(self._handle_accept)
        self._button_box.rejected.connect(self.reject)

        layout.addWidget(self._button_box)

        self._payload: dict[str, object] | None = None

    def _handle_accept(self) -> None:
        name = self._name_input.text().strip()
        if not name:
            QMessageBox.warning(
                self, "Missing name", "Please provide a display name for the group."
            )
            return
        nickname = re.sub(r"[^a-zA-Z0-9]", "", name).lower() or "group"
        description = self._description_input.text().strip() or None
        group_type = self._type_combo.currentText()

        payload: dict[str, object] = {
            "displayName": name,
            "description": description,
            "mailNickname": nickname,
        }

        if group_type == "Security":
            payload.update(
                {
                    "mailEnabled": False,
                    "securityEnabled": True,
                    "groupTypes": [],
                },
            )
        elif group_type == "Microsoft 365":
            payload.update(
                {
                    "mailEnabled": True,
                    "securityEnabled": False,
                    "groupTypes": ["Unified"],
                },
            )
        else:
            payload.update(
                {
                    "mailEnabled": False,
                    "securityEnabled": False,
                    "groupTypes": ["DynamicMembership"],
                },
            )

        self._payload = {
            key: value for key, value in payload.items() if value is not None
        }
        self.accept()

    def payload(self) -> dict[str, object] | None:
        return self._payload


class MembershipRuleDialog(QDialog):
    """Dialog for editing a group's dynamic membership rule."""

    def __init__(self, rule: str | None, *, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Edit membership rule")
        self.resize(560, 360)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)

        info = QLabel(
            "Rules use the Azure AD dynamic membership syntax. Refer to the Intune documentation for supported operators.",
            parent=self,
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: palette(mid);")
        layout.addWidget(info)

        self._editor = QPlainTextEdit(parent=self)
        self._editor.setPlaceholderText('(device.deviceOSType -eq "Windows")')
        self._editor.setPlainText(rule or "")
        layout.addWidget(self._editor, stretch=1)

        self._button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.Save
        )
        self._button_box.accepted.connect(self.accept)
        self._button_box.rejected.connect(self.reject)
        layout.addWidget(self._button_box)

    def rule(self) -> str | None:
        text = self._editor.toPlainText().strip()
        return text or None


class GroupsWidget(PageScaffold):
    """Directory group explorer with membership tooling."""

    def __init__(
        self,
        services: ServiceRegistry,
        *,
        context: UIContext,
        parent: QWidget | None = None,
    ) -> None:
        self._services = services
        self._context = context
        self._controller = GroupController(services)
        self._refresh_token_source: CancellationTokenSource | None = None
        self._refresh_in_progress = False

        self._refresh_button = make_toolbar_button(
            "Refresh", tooltip="Refresh groups from Microsoft Graph."
        )
        self._force_refresh_button = make_toolbar_button(
            "Force refresh", tooltip="Bypass cache and refetch groups."
        )
        self._add_member_button = make_toolbar_button(
            "Add member", tooltip="Add a member by object ID."
        )
        self._remove_member_button = make_toolbar_button(
            "Remove member", tooltip="Remove the selected member from the group."
        )
        self._edit_rule_button = make_toolbar_button(
            "Edit rule",
            tooltip="Edit the dynamic membership rule for the selected group.",
        )
        self._create_group_button = make_toolbar_button(
            "Create", tooltip="Create a new group."
        )
        self._delete_group_button = make_toolbar_button(
            "Delete", tooltip="Delete the selected group."
        )
        self._send_assignments_button = make_toolbar_button(
            "Assignments",
            tooltip="Stage the selected group for the assignment centre.",
        )

        actions: List[QToolButton] = [
            self._refresh_button,
            self._force_refresh_button,
            self._add_member_button,
            self._remove_member_button,
            self._edit_rule_button,
            self._create_group_button,
            self._delete_group_button,
            self._send_assignments_button,
        ]

        super().__init__(
            "Groups",
            subtitle="Discover tenant groups, inspect membership, and manage roster changes.",
            actions=actions,
            parent=parent,
        )

        self._model = GroupTableModel()
        self._proxy = GroupFilterProxyModel()
        self._proxy.setSourceModel(self._model)

        self._selected_group: DirectoryGroup | None = None
        self._selected_group_ids: set[str] = set()
        self._command_unregister: Callable[[], None] | None = None
        self._group_lookup: dict[str, DirectoryGroup] = {}
        self._group_parents: dict[str, set[str]] = {}
        self._group_children: dict[str, list[str]] = {}
        self._hierarchy_loaded = False
        self._hierarchy_loading = False
        self._tree_item_map: dict[str, QTreeWidgetItem] = {}
        self._member_page_size = 100
        self._member_pages: list[list[GroupMember]] = []
        self._member_page_index = -1
        self._member_total_loaded = 0
        self._member_stream = None
        self._member_group_id: str | None = None

        self._build_filters()
        self._build_body()

        self._refresh_button.clicked.connect(self._handle_refresh_clicked)
        self._force_refresh_button.clicked.connect(self._handle_force_refresh_clicked)
        self._add_member_button.clicked.connect(self._handle_add_member_clicked)
        self._remove_member_button.clicked.connect(self._handle_remove_member_clicked)
        self._edit_rule_button.clicked.connect(self._handle_edit_rule_clicked)
        self._create_group_button.clicked.connect(self._handle_create_group_clicked)
        self._delete_group_button.clicked.connect(self._handle_delete_group_clicked)
        self._send_assignments_button.clicked.connect(
            self._handle_send_to_assignments_clicked
        )

        self._controller.register_callbacks(
            refreshed=self._handle_groups_refreshed,
            error=self._handle_service_error,
            membership=self._handle_membership_event,
        )

        self._register_commands()
        self._load_cached_groups()
        self._update_action_buttons()

        if self._services.groups is None:
            self._handle_service_unavailable()

        self.destroyed.connect(lambda *_: self._cleanup())

    # ----------------------------------------------------------------- UI setup

    def _build_filters(self) -> None:
        filters = QWidget()
        layout = QHBoxLayout(filters)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Search groups…")
        self._search_input.textChanged.connect(self._handle_search_changed)
        layout.addWidget(self._search_input, stretch=2)

        self._type_combo = QComboBox()
        self._type_combo.currentIndexChanged.connect(self._handle_type_changed)
        layout.addWidget(self._type_combo)

        self._mail_combo = QComboBox()
        self._mail_combo.currentIndexChanged.connect(self._handle_mail_changed)
        layout.addWidget(self._mail_combo)

        self._summary_label = QLabel()
        self._summary_label.setStyleSheet("color: palette(mid);")
        layout.addWidget(self._summary_label, stretch=1)

        self.body_layout.addWidget(filters)

    def _build_body(self) -> None:
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setSizes([640, 360])

        # Table view setup
        table_container = QWidget()
        table_layout = QVBoxLayout(table_container)
        table_layout.setContentsMargins(0, 0, 0, 0)
        table_layout.setSpacing(0)

        self._table = QTableView()
        self._table.setModel(self._proxy)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._table.setAlternatingRowColors(True)
        self._table.setSortingEnabled(True)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table_layout.addWidget(self._table)

        # Tree view setup
        tree_container = QWidget()
        tree_layout = QVBoxLayout(tree_container)
        tree_layout.setContentsMargins(0, 0, 0, 0)
        tree_layout.setSpacing(0)

        self._group_tree = QTreeWidget()
        self._group_tree.setHeaderHidden(True)
        self._group_tree.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self._group_tree.setAlternatingRowColors(True)
        tree_layout.addWidget(self._group_tree)

        self._view_tabs = QTabWidget()
        self._view_tabs.setDocumentMode(True)
        self._view_tabs.addTab(table_container, "Table view")
        self._view_tabs.addTab(tree_container, "Hierarchy view")
        self._view_tabs.currentChanged.connect(lambda *_: self._update_summary())

        left_container = QWidget()
        left_layout = QVBoxLayout(left_container)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)
        self._list_message = InlineStatusMessage(parent=left_container)
        left_layout.addWidget(self._list_message)
        left_layout.addWidget(self._view_tabs)

        splitter.addWidget(left_container)

        self._detail_pane = GroupDetailPane(parent=splitter)
        self._detail_pane.members_next_requested.connect(
            self._handle_members_next_requested
        )
        self._detail_pane.members_prev_requested.connect(
            self._handle_members_prev_requested
        )
        self._detail_pane.membersRefreshRequested.connect(
            self._handle_members_refresh_requested
        )
        self._detail_pane.ownersRefreshRequested.connect(
            self._handle_owners_refresh_requested
        )
        splitter.addWidget(self._detail_pane)

        self.body_layout.addWidget(splitter, stretch=1)

        if selection_model := self._table.selectionModel():
            selection_model.selectionChanged.connect(self._handle_selection_changed)
        self._group_tree.itemSelectionChanged.connect(
            self._handle_tree_selection_changed
        )

        self._proxy.modelReset.connect(self._refresh_filtered_views)
        self._proxy.rowsInserted.connect(lambda *_: self._refresh_filtered_views())
        self._proxy.rowsRemoved.connect(lambda *_: self._refresh_filtered_views())
        self._model.modelReset.connect(self._refresh_filtered_views)

    # ---------------------------------------------------------------- Commands

    def _register_commands(self) -> None:
        action = CommandAction(
            id="groups.refresh",
            title="Refresh groups",
            callback=self._start_refresh,
            category="Groups",
            description="Refresh tenant groups from Microsoft Graph.",
            shortcut="Ctrl+Shift+G",
        )
        self._command_unregister = self._context.command_registry.register(action)

    def focus_search(self) -> None:
        self._search_input.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self._search_input.selectAll()

    # ----------------------------------------------------------------- Data flow

    def _load_cached_groups(self) -> None:
        self._list_message.clear()
        groups = self._controller.list_cached()
        self._model.set_groups(groups)
        self._update_group_lookup(groups)
        self._apply_filter_options(groups)
        self._refresh_filtered_views()
        if groups:
            self._table.selectRow(0)
        self._group_tree.setEnabled(True)
        self._group_parents.clear()
        self._group_children.clear()
        self._hierarchy_loaded = False
        self._schedule_hierarchy_refresh()

    def _handle_groups_refreshed(
        self,
        groups: Iterable[DirectoryGroup],
        from_cache: bool,
    ) -> None:
        self._list_message.clear()
        self._finish_refresh(mark_finished=True)
        groups_list = list(groups)
        selected_id = self._selected_group.id if self._selected_group else None
        self._model.set_groups(groups_list)
        self._update_group_lookup(groups_list)
        self._apply_filter_options(groups_list)
        self._group_parents.clear()
        self._group_children.clear()
        self._hierarchy_loaded = False
        self._refresh_filtered_views()
        self._group_tree.setEnabled(True)
        if selected_id:
            self._reselect_group(selected_id)
        elif groups_list:
            self._table.selectRow(0)
        if not from_cache:
            self._context.show_notification(
                f"Loaded {len(groups_list):,} groups.",
                level=ToastLevel.SUCCESS,
            )
        self._schedule_hierarchy_refresh()

    def _finish_refresh(self, *, mark_finished: bool = False) -> None:
        if not self._refresh_in_progress and self._refresh_token_source is None:
            return
        if self._refresh_token_source is not None:
            self._refresh_token_source.dispose()
            self._refresh_token_source = None
        self._refresh_in_progress = False
        self._context.clear_busy()
        self._refresh_button.setEnabled(True)
        self._force_refresh_button.setEnabled(True)

    def _handle_service_error(self, event: ServiceErrorEvent) -> None:
        self._finish_refresh()
        descriptor = describe_exception(event.error)
        detail_lines = [descriptor.detail]
        if descriptor.transient:
            detail_lines.append(
                "This issue appears transient. Retry after a short wait."
            )
        if descriptor.suggestion:
            detail_lines.append(f"Suggested action: {descriptor.suggestion}")
        detail_text = "\n\n".join(detail_lines)
        level = _toast_level_for(descriptor.severity)
        self._list_message.display(descriptor.headline, level=level, detail=detail_text)
        toast_message = descriptor.headline
        if descriptor.transient:
            toast_message = f"{descriptor.headline} Retry after a short wait."
        self._context.show_notification(
            toast_message,
            level=level,
            duration_ms=8000,
        )

    def _handle_membership_event(self, event: GroupMembershipEvent) -> None:
        if not self._selected_group or self._selected_group.id != event.group_id:
            return

        if event.status is MutationStatus.PENDING:
            verb = "Adding" if event.action == "add" else "Removing"
            self._context.set_busy(f"{verb} member…")
            return

        if event.status is MutationStatus.SUCCEEDED:
            self._context.set_busy("Refreshing members…")
            self._start_member_stream(event.group_id)
            self._detail_pane.set_members([], loading=True)
            self._context.run_async(self._fetch_next_member_page_async(event.group_id))
            return

        if event.status is MutationStatus.FAILED:
            self._context.clear_busy()
            detail = str(event.error) if event.error else "Unknown error"
            verb = "add" if event.action == "add" else "remove"
            self._context.show_notification(
                f"Failed to {verb} member: {detail}",
                level=ToastLevel.ERROR,
                duration_ms=10000,
            )

    # ----------------------------------------------------------------- Actions

    def _handle_refresh_clicked(self) -> None:
        self._start_refresh(force=False)

    def _handle_force_refresh_clicked(self) -> None:
        self._start_refresh(force=True)

    def _start_refresh(self, *, force: bool = False) -> None:
        if self._services.groups is None:
            self._list_message.display(
                "Group service unavailable. Configure Microsoft Graph dependencies to refresh directory groups.",
                level=ToastLevel.WARNING,
            )
            self._context.show_notification(
                "Group service not configured. Configure tenant services to continue.",
                level=ToastLevel.WARNING,
            )
            return
        self._list_message.clear()
        if self._refresh_token_source is not None:
            return
        token_source = CancellationTokenSource()
        self._refresh_token_source = token_source
        self._refresh_in_progress = True
        self._context.set_busy("Refreshing groups…", blocking=False)
        self._refresh_button.setEnabled(False)
        self._force_refresh_button.setEnabled(False)
        self._context.run_async(
            self._refresh_async(force=force, token_source=token_source)
        )

    async def _refresh_async(
        self, *, force: bool, token_source: CancellationTokenSource
    ) -> None:
        token = token_source.token
        try:
            await self._controller.refresh(force=force, cancellation_token=token)
            # Also refresh members/owners for the selected group
            if self._selected_group and self._selected_group.id:
                try:
                    members = await self._controller.refresh_members(
                        self._selected_group.id, cancellation_token=token
                    )
                    self._detail_pane.set_members(
                        members,
                        refreshed_at=self._controller.member_freshness(
                            self._selected_group.id
                        ),
                    )
                    owners = await self._controller.refresh_owners(
                        self._selected_group.id, cancellation_token=token
                    )
                    self._detail_pane.set_owners(
                        owners,
                        refreshed_at=self._controller.owner_freshness(
                            self._selected_group.id
                        ),
                    )
                except Exception as exc:  # noqa: BLE001
                    self._context.show_notification(
                        f"Failed to refresh membership: {exc}",
                        level=ToastLevel.WARNING,
                    )
        except CancellationError:
            self._finish_refresh()
            self._context.show_notification(
                "Group refresh cancelled.", level=ToastLevel.INFO
            )
        except Exception:  # noqa: BLE001
            raise

    def _handle_members_refresh_requested(self) -> None:
        """Handle refresh members request from detail pane."""
        if self._selected_group and self._selected_group.id:
            self._context.set_busy("Refreshing members…")
            self._context.run_async(self._refresh_members_async(self._selected_group.id))

    def _handle_owners_refresh_requested(self) -> None:
        """Handle refresh owners request from detail pane."""
        if self._selected_group and self._selected_group.id:
            self._context.set_busy("Refreshing owners…")
            self._context.run_async(self._refresh_owners_async(self._selected_group.id))

    async def _refresh_members_async(self, group_id: str) -> None:
        """Refresh members for a specific group."""
        try:
            members = await self._controller.refresh_members(group_id)
            if self._selected_group and self._selected_group.id == group_id:
                self._detail_pane.set_members(
                    members,
                    refreshed_at=self._controller.member_freshness(group_id),
                )
            self._context.clear_busy()
            self._context.show_notification(
                f"Refreshed {len(members)} members.", level=ToastLevel.SUCCESS
            )
        except Exception as exc:  # noqa: BLE001
            self._context.clear_busy()
            self._context.show_notification(
                f"Failed to refresh members: {exc}",
                level=ToastLevel.ERROR,
            )

    async def _refresh_owners_async(self, group_id: str) -> None:
        """Refresh owners for a specific group."""
        try:
            owners = await self._controller.refresh_owners(group_id)
            if self._selected_group and self._selected_group.id == group_id:
                self._detail_pane.set_owners(
                    owners,
                    refreshed_at=self._controller.owner_freshness(group_id),
                )
            self._context.clear_busy()
            self._context.show_notification(
                f"Refreshed {len(owners)} owners.", level=ToastLevel.SUCCESS
            )
        except Exception as exc:  # noqa: BLE001
            self._context.clear_busy()
            self._context.show_notification(
                f"Failed to refresh owners: {exc}",
                level=ToastLevel.ERROR,
            )

    def _handle_add_member_clicked(self) -> None:
        group = self._selected_group
        if group is None:
            self._context.show_notification(
                "Select a group before adding members.",
                level=ToastLevel.WARNING,
            )
            return
        member_id, ok = QInputDialog.getText(
            self,
            "Add member",
            "Enter the object ID (user/group/device) to add:",
        )
        member_id = member_id.strip()
        if not ok or not member_id:
            return
        self._context.set_busy("Adding group member…")
        self._context.run_async(self._add_member_async(group.id, member_id))

    async def _add_member_async(self, group_id: str, member_id: str) -> None:
        try:
            await self._controller.add_member(group_id, member_id)
            self._context.show_notification("Member added.", level=ToastLevel.SUCCESS)
        except Exception as exc:  # noqa: BLE001
            self._context.show_notification(
                f"Failed to add member: {exc}",
                level=ToastLevel.ERROR,
                duration_ms=8000,
            )
        finally:
            self._context.clear_busy()

    def _handle_edit_rule_clicked(self) -> None:
        group = self._selected_group
        if group is None:
            self._context.show_notification(
                "Select a group before editing membership rules.",
                level=ToastLevel.WARNING,
            )
            return
        if not self._is_dynamic_group(group):
            self._context.show_notification(
                "Membership rules are available for dynamic groups only.",
                level=ToastLevel.INFO,
            )
            return
        dialog = MembershipRuleDialog(group.membership_rule, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        rule = dialog.rule()
        current_rule = (group.membership_rule or "").strip() or None
        if rule == current_rule:
            self._context.show_notification(
                "Membership rule unchanged.", level=ToastLevel.INFO
            )
            return
        self._context.set_busy("Updating membership rule…")
        self._context.run_async(self._update_rule_async(group.id, rule))

    async def _update_rule_async(self, group_id: str, rule: str | None) -> None:
        try:
            await self._controller.update_membership_rule(group_id, rule)
            if self._selected_group and self._selected_group.id == group_id:
                self._selected_group = self._selected_group.model_copy(
                    update={"membership_rule": rule}
                )
                self._detail_pane.display_group(self._selected_group)
            self._context.show_notification(
                "Membership rule updated.", level=ToastLevel.SUCCESS
            )
        except Exception as exc:  # noqa: BLE001
            self._context.show_notification(
                f"Failed to update membership rule: {exc}",
                level=ToastLevel.ERROR,
                duration_ms=8000,
            )
        finally:
            self._context.clear_busy()

    def _handle_remove_member_clicked(self) -> None:
        group = self._selected_group
        if group is None:
            self._context.show_notification(
                "Select a group before removing members.",
                level=ToastLevel.WARNING,
            )
            return
        member_id = self._detail_pane.selected_member_id()
        if not member_id:
            self._context.show_notification(
                "Select a member from the list to remove.",
                level=ToastLevel.WARNING,
            )
            return
        confirm = QMessageBox.question(
            self,
            "Remove member",
            "Remove the selected member from this group?",
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        self._context.set_busy("Removing member…")
        self._context.run_async(self._remove_member_async(group.id, member_id))

    async def _remove_member_async(self, group_id: str, member_id: str) -> None:
        try:
            await self._controller.remove_member(group_id, member_id)
            self._context.show_notification("Member removed.", level=ToastLevel.SUCCESS)
        except Exception as exc:  # noqa: BLE001
            self._context.show_notification(
                f"Failed to remove member: {exc}",
                level=ToastLevel.ERROR,
                duration_ms=8000,
            )
        finally:
            self._context.clear_busy()

    def _handle_send_to_assignments_clicked(self) -> None:
        if not self._selected_group_ids:
            self._context.show_notification(
                "Select at least one group to stage for the assignment centre.",
                level=ToastLevel.WARNING,
            )
            return
        staged: list[tuple[str, str]] = []
        for group_id in self._selected_group_ids:
            group = self._group_lookup.get(group_id)
            if group is None:
                continue
            name = group.display_name or group.mail or group.mail_nickname or group_id
            staged.append((group_id, name))
        if not staged:
            self._context.show_notification(
                "Unable to stage the selected group(s); missing identifiers.",
                level=ToastLevel.ERROR,
            )
            return
        stage_groups(staged)
        command = self._context.command_registry.get(
            "assignments.consume-staged-groups"
        )
        if command is not None:
            command.callback()
            self._context.show_notification(
                f"Staged {len(staged)} group(s) for the assignment centre.",
                level=ToastLevel.SUCCESS,
            )
        else:
            self._context.show_notification(
                "Assignments centre not available. Groups staged for later.",
                level=ToastLevel.INFO,
            )

    def _handle_create_group_clicked(self) -> None:
        if self._services.groups is None:
            self._context.show_notification(
                "Group service not configured.",
                level=ToastLevel.WARNING,
            )
            return
        dialog = GroupCreateDialog(parent=self)
        if dialog.exec() != QDialog.Accepted:
            return
        payload = dialog.payload()
        if payload is None:
            return
        self._context.set_busy("Creating group…")
        self._context.run_async(self._create_group_async(payload))

    async def _create_group_async(self, payload: dict[str, object]) -> None:
        try:
            await self._controller.create_group(payload)
            self._context.show_notification("Group created.", level=ToastLevel.SUCCESS)
            await self._controller.refresh(force=True)
        except Exception as exc:  # noqa: BLE001
            self._context.show_notification(
                f"Failed to create group: {exc}",
                level=ToastLevel.ERROR,
                duration_ms=8000,
            )
        finally:
            self._context.clear_busy()

    def _handle_delete_group_clicked(self) -> None:
        group = self._selected_group
        if group is None:
            self._context.show_notification(
                "Select a group before deleting.",
                level=ToastLevel.WARNING,
            )
            return
        confirm = QMessageBox.question(
            self,
            "Delete group",
            f"Delete group {group.display_name}? This action cannot be undone.",
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        self._context.set_busy("Deleting group…")
        self._context.run_async(self._delete_group_async(group.id))

    async def _delete_group_async(self, group_id: str) -> None:
        try:
            await self._controller.delete_group(group_id)
            self._context.show_notification("Group deleted.", level=ToastLevel.SUCCESS)
            await self._controller.refresh(force=True)
        except Exception as exc:  # noqa: BLE001
            self._context.show_notification(
                f"Failed to delete group: {exc}",
                level=ToastLevel.ERROR,
                duration_ms=8000,
            )
        finally:
            self._context.clear_busy()

    # ----------------------------------------------------------------- Filters

    def _handle_search_changed(self, text: str) -> None:
        self._proxy.set_search_text(text)
        self._refresh_filtered_views()

    def _handle_type_changed(self, index: int) -> None:  # noqa: ARG002
        group_type = self._type_combo.currentData()
        self._proxy.set_type_filter(group_type)
        self._refresh_filtered_views()

    def _handle_mail_changed(self, index: int) -> None:  # noqa: ARG002
        mail_state = self._mail_combo.currentData()
        self._proxy.set_mail_filter(mail_state)
        self._refresh_filtered_views()

    def _apply_filter_options(self, groups: Iterable[DirectoryGroup]) -> None:
        types = sorted({_group_type_label(group) for group in groups}, key=str.lower)
        mail_states = ["Mail enabled", "Mail disabled"]
        self._populate_combo(self._type_combo, "All types", types)
        self._populate_combo(
            self._mail_combo,
            "Mail state",
            ["enabled", "disabled"],
            display_labels=mail_states,
        )

    def _populate_combo(
        self,
        combo: QComboBox,
        placeholder: str,
        values: List[str],
        *,
        display_labels: List[str] | None = None,
    ) -> None:
        current = combo.currentData()
        combo.blockSignals(True)
        combo.clear()
        combo.addItem(placeholder, None)
        for idx, value in enumerate(values):
            label = display_labels[idx] if display_labels else value or "Unknown"
            combo.addItem(label, value.lower() if value else None)
        if current:
            index = combo.findData(current)
            combo.setCurrentIndex(index if index != -1 else 0)
        else:
            combo.setCurrentIndex(0)
        combo.blockSignals(False)

    def _refresh_filtered_views(self) -> None:
        self._rebuild_group_tree()
        visible_groups = self._current_filtered_groups()
        visible_ids = {
            group.id for group in visible_groups if getattr(group, "id", None)
        }
        if self._selected_group_ids and not (self._selected_group_ids & visible_ids):
            self._selected_group_ids.clear()
            self._apply_group_selection([])
        elif self._selected_group_ids:
            self._selected_group_ids &= visible_ids
            self._set_table_selection(self._selected_group_ids)
            self._set_tree_selection(self._selected_group_ids)
            if (
                self._selected_group
                and self._selected_group.id not in self._selected_group_ids
            ):
                group = next(
                    (g for g in visible_groups if g.id in self._selected_group_ids),
                    None,
                )
                if group is not None:
                    self._apply_group_selection([group])
        self._update_summary()

    def _current_filtered_groups(self) -> list[DirectoryGroup]:
        groups: list[DirectoryGroup] = []
        for row in range(self._proxy.rowCount()):
            source_index = self._proxy.mapToSource(self._proxy.index(row, 0))
            group = self._model.group_at(source_index.row())
            if group is not None:
                groups.append(group)
        return groups

    def _update_group_lookup(self, groups: Iterable[DirectoryGroup]) -> None:
        self._group_lookup = {
            group.id: group for group in groups if getattr(group, "id", None)
        }

    def _schedule_hierarchy_refresh(self) -> None:
        if self._services.groups is None or not self._group_lookup:
            return
        if self._hierarchy_loading:
            return
        self._context.run_async(self._load_group_hierarchy_async())

    async def _load_group_hierarchy_async(self) -> None:
        if self._hierarchy_loading:
            return
        group_ids = [group_id for group_id in self._group_lookup.keys() if group_id]
        if not group_ids:
            return
        self._hierarchy_loading = True
        try:
            mapping = await self._controller.member_of_map(group_ids)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to load group hierarchy", exc_info=exc)
            self._hierarchy_loaded = False
            return
        finally:
            self._hierarchy_loading = False

        parents: dict[str, set[str]] = {}
        for group_id in group_ids:
            entries = mapping.get(group_id, []) if mapping else []
            parents[group_id] = {parent for parent in entries if parent}

        children: dict[str, list[str]] = {}
        for child_id, parent_ids in parents.items():
            for parent_id in parent_ids:
                if parent_id not in self._group_lookup:
                    continue
                children.setdefault(parent_id, []).append(child_id)

        for parent_id, child_list in children.items():
            child_list.sort(
                key=lambda gid: (
                    (
                        self._group_lookup.get(gid).display_name
                        if self._group_lookup.get(gid)
                        else gid
                    )
                    or ""
                ).lower(),
            )

        self._group_parents = parents
        self._group_children = children
        self._hierarchy_loaded = True
        logger.debug(
            "Fetched group hierarchy",
            groups=len(group_ids),
            parent_edges=sum(len(values) for values in parents.values()),
        )
        self._refresh_filtered_views()

    def _rebuild_group_tree(self) -> None:
        groups = self._current_filtered_groups()
        self._group_tree.blockSignals(True)
        self._group_tree.clear()
        self._tree_item_map.clear()

        if not groups:
            placeholder = QTreeWidgetItem(["No groups match current filters."])
            placeholder.setFlags(Qt.ItemFlag.NoItemFlags)
            self._group_tree.addTopLevelItem(placeholder)
            self._group_tree.blockSignals(False)
            return

        if self._hierarchy_loaded and self._group_children:
            self._populate_hierarchy_tree(groups)
        else:
            self._populate_type_tree(groups)

        self._group_tree.blockSignals(False)
        if self._selected_group_ids:
            self._set_tree_selection(self._selected_group_ids)

    def _populate_type_tree(self, groups: Iterable[DirectoryGroup]) -> None:
        categories: dict[str, QTreeWidgetItem] = {}
        for group in groups:
            group_id = getattr(group, "id", None)
            if not group_id:
                continue
            type_label = _group_type_label(group)
            parent = categories.get(type_label)
            if parent is None:
                parent = QTreeWidgetItem([type_label])
                parent.setFlags(Qt.ItemFlag.ItemIsEnabled)
                categories[type_label] = parent
                self._group_tree.addTopLevelItem(parent)
            item = self._create_tree_item_for_group(group)
            parent.addChild(item)
            self._tree_item_map[group_id] = item

        for parent in categories.values():
            parent.setExpanded(True)

    def _populate_hierarchy_tree(self, groups: Iterable[DirectoryGroup]) -> None:
        visible_lookup = {
            group.id: group for group in groups if getattr(group, "id", None)
        }
        visible_ids = set(visible_lookup.keys())
        if not visible_ids:
            return

        parent_map = {
            group_id: {
                parent
                for parent in self._group_parents.get(group_id, set())
                if parent in visible_ids
            }
            for group_id in visible_ids
        }
        child_map: dict[str, list[str]] = {}
        for parent_id, children in self._group_children.items():
            filtered = [child for child in children if child in visible_ids]
            if filtered:
                child_map[parent_id] = filtered

        def sort_key(group_id: str) -> tuple[str, str]:
            group = visible_lookup.get(group_id)
            label = (
                group.display_name
                or group.mail
                or group.mail_nickname
                or group_id
                or ""
            )
            return (label.lower(), group_id)

        roots = [group_id for group_id in visible_ids if not parent_map.get(group_id)]
        if not roots:
            roots = list(visible_ids)
        roots.sort(key=sort_key)

        for root_id in roots:
            group = visible_lookup.get(root_id)
            if group is None:
                continue
            root_item = self._create_tree_item_for_group(group)
            self._group_tree.addTopLevelItem(root_item)
            self._tree_item_map[root_id] = root_item
            self._populate_hierarchy_children(
                root_item,
                root_id,
                visible_lookup,
                child_map,
                sort_key,
                path={root_id},
            )
            root_item.setExpanded(True)

    def _populate_hierarchy_children(
        self,
        parent_item: QTreeWidgetItem,
        parent_id: str,
        lookup: dict[str, DirectoryGroup],
        child_map: dict[str, list[str]],
        sort_key,
        *,
        path: set[str],
    ) -> None:
        children = child_map.get(parent_id, [])
        for child_id in sorted(children, key=sort_key):
            if child_id in path:
                continue
            group = lookup.get(child_id)
            if group is None:
                continue
            child_item = self._create_tree_item_for_group(group)
            parent_item.addChild(child_item)
            self._tree_item_map[child_id] = child_item
            new_path = set(path)
            new_path.add(child_id)
            self._populate_hierarchy_children(
                child_item,
                child_id,
                lookup,
                child_map,
                sort_key,
                path=new_path,
            )
            child_item.setExpanded(True)

    def _create_tree_item_for_group(self, group: DirectoryGroup) -> QTreeWidgetItem:
        group_id = getattr(group, "id", None)
        display = (
            group.display_name
            or group.mail
            or group.mail_nickname
            or group_id
            or "Unnamed group"
        )
        item = QTreeWidgetItem([display])
        if group_id:
            item.setData(0, Qt.ItemDataRole.UserRole, group_id)
        tooltip_parts = []
        if group.description:
            tooltip_parts.append(group.description)
        if group.mail:
            tooltip_parts.append(f"Mail: {group.mail}")
        tooltip = "\n".join(part for part in tooltip_parts if part)
        if tooltip:
            item.setToolTip(0, tooltip)
        return item

    def _set_tree_selection(self, group_ids: Iterable[str]) -> None:
        self._group_tree.blockSignals(True)
        self._group_tree.clearSelection()
        first_item: QTreeWidgetItem | None = None
        for group_id in group_ids:
            item = self._tree_item_map.get(group_id)
            if item is None:
                continue
            item.setSelected(True)
            if first_item is None:
                first_item = item
        if first_item is not None:
            self._group_tree.scrollToItem(first_item)
        self._group_tree.blockSignals(False)

    def _set_table_selection(self, group_ids: Iterable[str]) -> None:
        selection_model = self._table.selectionModel()
        if selection_model is None:
            return
        selection_model.blockSignals(True)
        selection_model.clearSelection()
        first_proxy: QModelIndex | None = None
        for group_id in group_ids:
            row = self._row_for_group_id(group_id)
            if row is None:
                continue
            proxy_index = self._proxy.mapFromSource(self._model.index(row, 0))
            if proxy_index.isValid():
                selection_model.select(
                    proxy_index,
                    QItemSelectionModel.SelectionFlag.Select
                    | QItemSelectionModel.SelectionFlag.Rows,
                )
                if first_proxy is None:
                    first_proxy = proxy_index
        if first_proxy is not None:
            self._table.scrollTo(first_proxy)
        selection_model.blockSignals(False)

    def _row_for_group_id(self, group_id: str) -> int | None:
        for row in range(self._model.rowCount()):
            group = self._model.group_at(row)
            if group is not None and group.id == group_id:
                return row
        return None

    # ----------------------------------------------------------------- Selection

    def _handle_selection_changed(self, *_: object) -> None:
        selection_model = self._table.selectionModel()
        if selection_model is None:
            return
        indexes = selection_model.selectedRows()
        groups: list[DirectoryGroup] = []
        ids: set[str] = set()
        for proxy_index in indexes:
            source_index = self._proxy.mapToSource(proxy_index)
            group = self._model.group_at(source_index.row())
            if group is None or not getattr(group, "id", None):
                continue
            groups.append(group)
            ids.add(group.id)
        if indexes:
            self._set_tree_selection(ids)
        else:
            self._set_tree_selection(set())
        self._apply_group_selection(groups)

    def _handle_tree_selection_changed(self) -> None:
        items = self._group_tree.selectedItems()
        groups: list[DirectoryGroup] = []
        ids: set[str] = set()
        for item in items:
            group_id = item.data(0, Qt.ItemDataRole.UserRole)
            if not group_id:
                continue
            group = self._group_lookup.get(group_id)
            if group is None:
                continue
            groups.append(group)
            ids.add(group_id)
        if items:
            self._set_table_selection(ids)
        else:
            self._set_table_selection(set())
        self._apply_group_selection(groups)

    def _apply_group_selection(self, groups: list[DirectoryGroup]) -> None:
        previous_id = self._selected_group.id if self._selected_group else None
        self._selected_group_ids = {
            group.id for group in groups if getattr(group, "id", None)
        }
        next_group = groups[0] if groups else None
        self._selected_group = next_group

        if next_group is None:
            self._member_group_id = None
            self._detail_pane.display_group(None)
            self._detail_pane.clear_members()
            self._detail_pane.clear_owners()
        else:
            self._detail_pane.display_group(next_group)
            if previous_id != next_group.id:
                self._prepare_member_state_for_group(next_group)
                # Auto-load members from cache
                members = self._controller.load_members_from_cache(next_group.id)
                if members:
                    self._detail_pane.set_members(
                        members,
                        refreshed_at=self._controller.member_freshness(next_group.id),
                    )
                else:
                    self._detail_pane.clear_members()
            # Auto-load owners from cache
            owner_cache = self._controller.load_owners_from_cache(next_group.id)
            if owner_cache:
                self._detail_pane.set_owners(
                    owner_cache,
                    refreshed_at=self._controller.owner_freshness(next_group.id),
                )
            else:
                self._detail_pane.clear_owners()

        self._update_action_buttons()
        self._update_summary()

    def _prepare_member_state_for_group(self, group: DirectoryGroup) -> None:
        group_id = getattr(group, "id", None)
        self._member_stream = None
        self._member_pages = []
        self._member_total_loaded = 0
        self._member_page_index = -1
        self._member_group_id = group_id

        if not group_id:
            self._detail_pane.clear_members()
            return

        cached = self._controller.cached_members(group_id)
        cached_stream = self._controller.cached_member_stream(group_id)
        if cached_stream is not None:
            self._member_stream = cached_stream
        if cached:
            self._member_pages = [
                cached[index : index + self._member_page_size]
                for index in range(0, len(cached), self._member_page_size)
            ]
            self._member_total_loaded = len(cached)
            self._display_member_page(0)
        else:
            self._detail_pane.clear_members()

    def _display_member_page(self, index: int) -> None:
        if not (0 <= index < len(self._member_pages)):
            self._detail_pane.clear_members()
            return
        page = self._member_pages[index]
        has_more = False
        if index < len(self._member_pages) - 1:
            has_more = True
        elif self._member_stream is not None and self._member_stream.has_more:
            has_more = True
        self._member_page_index = index
        refreshed_at = (
            self._controller.member_freshness(self._member_group_id)
            if self._member_group_id
            else None
        )
        self._detail_pane.set_members(
            page,
            page_index=index,
            has_more=has_more,
            total_loaded=self._member_total_loaded or len(page),
            refreshed_at=refreshed_at,
        )

    def _start_member_stream(self, group_id: str) -> None:
        self._member_stream = self._controller.member_stream(
            group_id, page_size=self._member_page_size
        )
        self._member_group_id = group_id
        self._member_pages = []
        self._member_page_index = -1
        self._member_total_loaded = 0
        self._controller.cache_members(group_id, [], append=False)

    async def _fetch_next_member_page_async(self, group_id: str) -> None:
        stream = self._member_stream
        if stream is None or self._member_group_id != group_id:
            self._start_member_stream(group_id)
            stream = self._member_stream
        if stream is None:
            return
        try:
            page = await stream.next_page()
            if self._member_group_id != group_id:
                return
            if page:
                self._member_pages.append(page)
                self._member_total_loaded += len(page)
                self._controller.cache_members(group_id, page, append=True)
                self._display_member_page(len(self._member_pages) - 1)
            elif not self._member_pages:
                self._detail_pane.set_members(
                    [],
                    page_index=0,
                    has_more=False,
                    total_loaded=0,
                    refreshed_at=self._controller.member_freshness(group_id),
                )
            else:
                current_index = (
                    self._member_page_index
                    if self._member_page_index >= 0
                    else len(self._member_pages) - 1
                )
                self._display_member_page(max(0, current_index))
        except Exception as exc:  # noqa: BLE001
            self._context.show_notification(
                f"Failed to load members: {exc}",
                level=ToastLevel.ERROR,
                duration_ms=8000,
            )
        finally:
            self._context.clear_busy()

    def _handle_members_next_requested(self) -> None:
        group_id = self._member_group_id
        if not group_id:
            return
        next_index = self._member_page_index + 1
        if next_index < len(self._member_pages):
            self._display_member_page(next_index)
            return
        if self._member_stream is not None and self._member_stream.has_more:
            self._context.set_busy("Loading additional members…")
            self._context.run_async(self._fetch_next_member_page_async(group_id))

    def _handle_members_prev_requested(self) -> None:
        if self._member_page_index <= 0:
            return
        self._display_member_page(self._member_page_index - 1)

    def _reselect_group(self, group_id: str) -> None:
        if not group_id:
            return
        self._set_table_selection({group_id})
        self._set_tree_selection({group_id})
        group = self._group_lookup.get(group_id)
        if group is not None:
            self._apply_group_selection([group])

    # ----------------------------------------------------------------- Helpers

    def _update_summary(self) -> None:
        total = self._model.rowCount()
        visible = self._proxy.rowCount()
        stale = self._services.groups is not None and self._controller.is_cache_stale()
        parts = [f"{visible:,} groups shown"]
        if visible != total:
            parts.append(f"{total:,} cached")
        if stale:
            parts.append("Cache stale — refresh recommended")
        selected = len(self._selected_group_ids)
        if selected:
            parts.append(f"{selected:,} selected")
        view_label = "Hierarchy" if self._view_tabs.currentIndex() == 1 else "Table"
        parts.append(f"View: {view_label}")
        self._summary_label.setText(" · ".join(parts))

    def _update_action_buttons(self) -> None:
        service_available = self._services.groups is not None
        group_selected = self._selected_group is not None
        dynamic_group = self._is_dynamic_group(self._selected_group)

        self._refresh_button.setEnabled(service_available)
        self._force_refresh_button.setEnabled(service_available)
        self._add_member_button.setEnabled(service_available and group_selected)
        self._remove_member_button.setEnabled(service_available and group_selected)
        self._edit_rule_button.setEnabled(service_available and dynamic_group)
        self._create_group_button.setEnabled(service_available)
        self._delete_group_button.setEnabled(service_available and group_selected)
        self._send_assignments_button.setEnabled(group_selected)

    def _is_dynamic_group(self, group: DirectoryGroup | None) -> bool:
        if group is None:
            return False
        if (group.membership_rule or "").strip():
            return True
        group_types = group.group_types or []
        return any(
            value.lower() == "dynamicmembership" for value in group_types if value
        )

    def _handle_service_unavailable(self) -> None:
        self._table.setEnabled(False)
        self._group_tree.setEnabled(False)
        self._detail_pane.display_group(None)
        self._list_message.display(
            "Group service unavailable. Configure Microsoft Graph dependencies to load directory groups.",
            level=ToastLevel.WARNING,
        )
        self._context.show_banner(
            "Group service unavailable — configure Microsoft Graph dependencies to continue.",
            level=ToastLevel.WARNING,
        )
        self._update_action_buttons()

    def _cleanup(self) -> None:
        self._finish_refresh()
        if self._command_unregister:
            try:
                self._command_unregister()
            except Exception:  # pragma: no cover - defensive unregister
                pass
            self._command_unregister = None
        self._controller.dispose()


__all__ = ["GroupsWidget"]
