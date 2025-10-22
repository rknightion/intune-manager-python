from __future__ import annotations

import re
from collections.abc import Callable
from typing import Iterable, List

from PySide6.QtCore import Qt
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
    QTableView,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from intune_manager.data import DirectoryGroup, GroupMember
from intune_manager.services import ServiceErrorEvent, ServiceRegistry
from intune_manager.services.groups import GroupMembershipEvent
from intune_manager.ui.components import (
    CommandAction,
    PageScaffold,
    ToastLevel,
    UIContext,
    stage_groups,
    make_toolbar_button,
)

from .controller import GroupController
from .models import GroupFilterProxyModel, GroupTableModel, _group_type_label


class GroupDetailPane(QWidget):
    """Display selected group metadata and membership."""

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

        self._members_list = QListWidget()
        self._members_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        layout.addWidget(self._members_list, stretch=1)
        self._members_list.currentItemChanged.connect(self._handle_member_selection_changed)

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

        self._owners_list = QListWidget()
        self._owners_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
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

    def clear_owners(self) -> None:
        self._owners_list.clear()
        placeholder = QListWidgetItem("Owner list not loaded.")
        placeholder.setFlags(Qt.ItemFlag.NoItemFlags)
        self._owners_list.addItem(placeholder)
        self._owner_status_label.setText("Load owners to view ownership details.")

    def set_members(self, members: Iterable[GroupMember], *, loading: bool = False) -> None:
        self._members_list.clear()
        if loading:
            placeholder = QListWidgetItem("Loading members…")
            placeholder.setFlags(Qt.ItemFlag.NoItemFlags)
            self._members_list.addItem(placeholder)
            self._member_status_label.setText("Fetching members from Microsoft Graph…")
            self._member_detail_label.setText("Fetching members…")
            return

        members_list = list(members)
        self._member_lookup = {member.id: member for member in members_list if member.id}
        if not members_list:
            placeholder = QListWidgetItem("No members found.")
            placeholder.setFlags(Qt.ItemFlag.NoItemFlags)
            self._members_list.addItem(placeholder)
            self._member_status_label.setText("Group has no members.")
            self._member_detail_label.setText("Group has no members.")
            return

        for member in members_list:
            name = member.display_name or member.user_principal_name or member.mail or member.id
            detail = member.user_principal_name or member.mail or ""
            text = name if not detail else f"{name} — {detail}"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, member.id)
            self._members_list.addItem(item)
        self._member_status_label.setText(f"{len(members_list)} members loaded.")
        first_item = self._members_list.item(0)
        if first_item is not None and first_item.flags() & Qt.ItemFlag.ItemIsSelectable:
            self._members_list.setCurrentItem(first_item)
            self._update_member_detail(first_item.data(Qt.ItemDataRole.UserRole))
        else:
            self._member_detail_label.setText("Select a member to view details.")

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

    def _update_member_detail(self, member_id: str | None) -> None:
        if not member_id:
            self._member_detail_label.setText("Select a member to view details.")
            return
        member = self._member_lookup.get(member_id)
        if member is None:
            self._member_detail_label.setText("Member details unavailable (not cached).")
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

    def set_owners(self, owners: Iterable[GroupMember], *, loading: bool = False) -> None:
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
            self._owner_status_label.setText("Group has no owners.")
            return

        for owner in owners_list:
            name = owner.display_name or owner.user_principal_name or owner.mail or owner.id
            detail = owner.user_principal_name or owner.mail or ""
            text = name if not detail else f"{name} — {detail}"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, owner.id)
            self._owners_list.addItem(item)
        self._owner_status_label.setText(f"{len(owners_list)} owners loaded.")

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

        self._button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok)
        self._button_box.accepted.connect(self._handle_accept)
        self._button_box.rejected.connect(self.reject)

        layout.addWidget(self._button_box)

        self._payload: dict[str, object] | None = None

    def _handle_accept(self) -> None:
        name = self._name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "Missing name", "Please provide a display name for the group.")
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

        self._payload = {key: value for key, value in payload.items() if value is not None}
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

        self._button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Save)
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

        self._refresh_button = make_toolbar_button("Refresh", tooltip="Refresh groups from Microsoft Graph.")
        self._force_refresh_button = make_toolbar_button("Force refresh", tooltip="Bypass cache and refetch groups.")
        self._load_members_button = make_toolbar_button("Load members", tooltip="Load membership for the selected group.")
        self._load_owners_button = make_toolbar_button("Load owners", tooltip="Load owners for the selected group.")
        self._add_member_button = make_toolbar_button("Add member", tooltip="Add a member by object ID.")
        self._remove_member_button = make_toolbar_button("Remove member", tooltip="Remove the selected member from the group.")
        self._edit_rule_button = make_toolbar_button("Edit rule", tooltip="Edit the dynamic membership rule for the selected group.")
        self._create_group_button = make_toolbar_button("Create", tooltip="Create a new group.")
        self._delete_group_button = make_toolbar_button("Delete", tooltip="Delete the selected group.")
        self._send_assignments_button = make_toolbar_button(
            "Assignments",
            tooltip="Stage the selected group for the assignment centre.",
        )

        actions: List[QToolButton] = [
            self._refresh_button,
            self._force_refresh_button,
            self._load_members_button,
            self._load_owners_button,
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
        self._command_unregister: Callable[[], None] | None = None

        self._build_filters()
        self._build_body()

        self._refresh_button.clicked.connect(self._handle_refresh_clicked)
        self._force_refresh_button.clicked.connect(self._handle_force_refresh_clicked)
        self._load_members_button.clicked.connect(self._handle_load_members_clicked)
        self._load_owners_button.clicked.connect(self._handle_load_owners_clicked)
        self._add_member_button.clicked.connect(self._handle_add_member_clicked)
        self._remove_member_button.clicked.connect(self._handle_remove_member_clicked)
        self._edit_rule_button.clicked.connect(self._handle_edit_rule_clicked)
        self._create_group_button.clicked.connect(self._handle_create_group_clicked)
        self._delete_group_button.clicked.connect(self._handle_delete_group_clicked)
        self._send_assignments_button.clicked.connect(self._handle_send_to_assignments_clicked)

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
        splitter.setSizes([620, 380])

        table_container = QWidget()
        table_layout = QVBoxLayout(table_container)
        table_layout.setContentsMargins(0, 0, 0, 0)
        table_layout.setSpacing(0)

        self._table = QTableView()
        self._table.setModel(self._proxy)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setAlternatingRowColors(True)
        self._table.setSortingEnabled(True)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table_layout.addWidget(self._table)

        splitter.addWidget(table_container)

        self._detail_pane = GroupDetailPane(parent=splitter)
        splitter.addWidget(self._detail_pane)

        self.body_layout.addWidget(splitter, stretch=1)

        if selection_model := self._table.selectionModel():
            selection_model.selectionChanged.connect(self._handle_selection_changed)

        self._proxy.modelReset.connect(self._update_summary)
        self._proxy.rowsInserted.connect(lambda *_: self._update_summary())
        self._proxy.rowsRemoved.connect(lambda *_: self._update_summary())
        self._model.modelReset.connect(self._update_summary)

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

    # ----------------------------------------------------------------- Data flow

    def _load_cached_groups(self) -> None:
        groups = self._controller.list_cached()
        self._model.set_groups(groups)
        self._apply_filter_options(groups)
        self._update_summary()
        if groups:
            self._table.selectRow(0)

    def _handle_groups_refreshed(
        self,
        groups: Iterable[DirectoryGroup],
        from_cache: bool,
    ) -> None:
        groups_list = list(groups)
        selected_id = self._selected_group.id if self._selected_group else None
        self._model.set_groups(groups_list)
        self._apply_filter_options(groups_list)
        self._update_summary()
        if selected_id:
            self._reselect_group(selected_id)
        elif groups_list:
            self._table.selectRow(0)
        if not from_cache:
            self._context.show_notification(
                f"Loaded {len(groups_list):,} groups.",
                level=ToastLevel.SUCCESS,
            )
        self._context.clear_busy()
        self._refresh_button.setEnabled(True)
        self._force_refresh_button.setEnabled(True)

    def _handle_service_error(self, event: ServiceErrorEvent) -> None:
        self._context.clear_busy()
        self._refresh_button.setEnabled(True)
        self._force_refresh_button.setEnabled(True)
        self._context.show_notification(
            f"Group operation failed: {event.error}",
            level=ToastLevel.ERROR,
            duration_ms=8000,
        )

    def _handle_membership_event(self, event: GroupMembershipEvent) -> None:
        if self._selected_group and self._selected_group.id == event.group_id:
            self._context.run_async(self._load_members_async(event.group_id))

    # ----------------------------------------------------------------- Actions

    def _handle_refresh_clicked(self) -> None:
        self._start_refresh(force=False)

    def _handle_force_refresh_clicked(self) -> None:
        self._start_refresh(force=True)

    def _start_refresh(self, *, force: bool = False) -> None:
        if self._services.groups is None:
            self._context.show_notification(
                "Group service not configured. Configure tenant services to continue.",
                level=ToastLevel.WARNING,
            )
            return
        self._context.set_busy("Refreshing groups…")
        self._refresh_button.setEnabled(False)
        self._force_refresh_button.setEnabled(False)
        self._context.run_async(self._refresh_async(force=force))

    async def _refresh_async(self, *, force: bool) -> None:
        try:
            await self._controller.refresh(force=force)
        except Exception as exc:  # noqa: BLE001
            self._context.clear_busy()
            self._refresh_button.setEnabled(True)
            self._force_refresh_button.setEnabled(True)
            self._context.show_notification(
                f"Failed to refresh groups: {exc}",
                level=ToastLevel.ERROR,
            )

    def _handle_load_members_clicked(self) -> None:
        group = self._selected_group
        if group is None:
            self._context.show_notification(
                "Select a group before loading members.",
                level=ToastLevel.WARNING,
            )
            return
        self._detail_pane.set_members([], loading=True)
        self._context.run_async(self._load_members_async(group.id))

    async def _load_members_async(self, group_id: str) -> None:
        try:
            members = await self._controller.list_members(group_id)
            if self._selected_group and self._selected_group.id == group_id:
                self._detail_pane.set_members(members)
        except Exception as exc:  # noqa: BLE001
            self._context.show_notification(
                f"Failed to load members: {exc}",
                level=ToastLevel.ERROR,
            )

    def _handle_load_owners_clicked(self) -> None:
        group = self._selected_group
        if group is None:
            self._context.show_notification(
                "Select a group before loading owners.",
                level=ToastLevel.WARNING,
            )
            return
        self._detail_pane.set_owners([], loading=True)
        self._context.run_async(self._load_owners_async(group.id))

    async def _load_owners_async(self, group_id: str) -> None:
        try:
            owners = await self._controller.list_owners(group_id)
            if self._selected_group and self._selected_group.id == group_id:
                self._detail_pane.set_owners(owners)
        except Exception as exc:  # noqa: BLE001
            self._context.show_notification(
                f"Failed to load owners: {exc}",
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
            self._context.show_notification("Membership rule unchanged.", level=ToastLevel.INFO)
            return
        self._context.set_busy("Updating membership rule…")
        self._context.run_async(self._update_rule_async(group.id, rule))

    async def _update_rule_async(self, group_id: str, rule: str | None) -> None:
        try:
            await self._controller.update_membership_rule(group_id, rule)
            if self._selected_group and self._selected_group.id == group_id:
                self._selected_group = self._selected_group.model_copy(update={"membership_rule": rule})
                self._detail_pane.display_group(self._selected_group)
            self._context.show_notification("Membership rule updated.", level=ToastLevel.SUCCESS)
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
        selection_model = self._table.selectionModel()
        if selection_model is None:
            return
        indexes = selection_model.selectedRows()
        if not indexes:
            self._context.show_notification(
                "Select at least one group to stage for the assignment centre.",
                level=ToastLevel.WARNING,
            )
            return
        staged: list[tuple[str, str]] = []
        for proxy_index in indexes:
            source_index = self._proxy.mapToSource(proxy_index)
            group = self._model.group_at(source_index.row())
            if group is None or not group.id:
                continue
            name = group.display_name or group.mail or group.mail_nickname or group.id
            staged.append((group.id, name))
        if not staged:
            self._context.show_notification(
                "Unable to stage the selected group(s); missing identifiers.",
                level=ToastLevel.ERROR,
            )
            return
        stage_groups(staged)
        command = self._context.command_registry.get("assignments.consume-staged-groups")
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
        self._update_summary()

    def _handle_type_changed(self, index: int) -> None:  # noqa: ARG002
        group_type = self._type_combo.currentData()
        self._proxy.set_type_filter(group_type)
        self._update_summary()

    def _handle_mail_changed(self, index: int) -> None:  # noqa: ARG002
        mail_state = self._mail_combo.currentData()
        self._proxy.set_mail_filter(mail_state)
        self._update_summary()

    def _apply_filter_options(self, groups: Iterable[DirectoryGroup]) -> None:
        types = sorted({_group_type_label(group) for group in groups}, key=str.lower)
        mail_states = ["Mail enabled", "Mail disabled"]
        self._populate_combo(self._type_combo, "All types", types)
        self._populate_combo(self._mail_combo, "Mail state", ["enabled", "disabled"], display_labels=mail_states)

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

    # ----------------------------------------------------------------- Selection

    def _handle_selection_changed(self, *_: object) -> None:
        selection_model = self._table.selectionModel()
        if selection_model is None:
            return
        indexes = selection_model.selectedRows()
        if not indexes:
            self._selected_group = None
            self._detail_pane.display_group(None)
            self._update_action_buttons()
            return
        proxy_index = indexes[0]
        source_index = self._proxy.mapToSource(proxy_index)
        group = self._model.group_at(source_index.row())
        self._selected_group = group
        self._detail_pane.display_group(group)
        cached = self._controller.cached_members(group.id) if group else None
        if group and cached is not None:
            self._detail_pane.set_members(cached)
        else:
            self._detail_pane.clear_members()
        owner_cache = self._controller.cached_owners(group.id) if group else None
        if group and owner_cache is not None:
            self._detail_pane.set_owners(owner_cache)
        else:
            self._detail_pane.clear_owners()
        self._update_action_buttons()

    def _reselect_group(self, group_id: str) -> None:
        for row in range(self._model.rowCount()):
            group = self._model.group_at(row)
            if group is None or group.id != group_id:
                continue
            proxy_index = self._proxy.mapFromSource(self._model.index(row, 0))
            if proxy_index.isValid():
                self._table.selectRow(proxy_index.row())
                self._table.scrollTo(proxy_index)
            break

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
        self._summary_label.setText(" · ".join(parts))

    def _update_action_buttons(self) -> None:
        service_available = self._services.groups is not None
        group_selected = self._selected_group is not None
        dynamic_group = self._is_dynamic_group(self._selected_group)

        self._refresh_button.setEnabled(service_available)
        self._force_refresh_button.setEnabled(service_available)
        self._load_members_button.setEnabled(service_available and group_selected)
        self._load_owners_button.setEnabled(service_available and group_selected)
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
        return any(value.lower() == "dynamicmembership" for value in group_types if value)

    def _handle_service_unavailable(self) -> None:
        self._table.setEnabled(False)
        self._detail_pane.display_group(None)
        self._context.show_banner(
            "Group service unavailable — configure Microsoft Graph dependencies to continue.",
            level=ToastLevel.WARNING,
        )
        self._update_action_buttons()

    def _cleanup(self) -> None:
        if self._command_unregister:
            try:
                self._command_unregister()
            except Exception:  # pragma: no cover - defensive unregister
                pass
            self._command_unregister = None
        self._controller.dispose()


__all__ = ["GroupsWidget"]
