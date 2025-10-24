from __future__ import annotations

import pytest

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWizard

from intune_manager.data.models.application import MobileApp
from intune_manager.data.models.assignment import (
    AllDevicesAssignmentTarget,
    AssignmentIntent,
    GroupAssignmentTarget,
    MobileAppAssignment,
)
from intune_manager.data.models.group import DirectoryGroup
from intune_manager.services.assignments import (
    AssignmentDiff,
    AssignmentService,
    AssignmentUpdate,
    MutationStatus,
)
from intune_manager.services.registry import ServiceRegistry
from intune_manager.ui.assignments.controller import AssignmentCenterController
from intune_manager.ui.assignments.bulk_wizard import BulkAssignmentWizard

from tests.factories import make_mobile_app_assignment
from tests.stubs import FakeGraphClientFactory


def _with_enum_intent(assignment: MobileAppAssignment) -> MobileAppAssignment:
    return assignment.model_copy(update={"intent": AssignmentIntent(assignment.intent)})


@pytest.mark.asyncio
async def test_bulk_assignment_retry_and_success_flow() -> None:
    factory = FakeGraphClientFactory()
    service = AssignmentService(factory)
    controller = AssignmentCenterController(ServiceRegistry(assignments=service))

    current = _with_enum_intent(
        make_mobile_app_assignment(
            assignment_id="existing",
            intent=AssignmentIntent.REQUIRED,
            target=AllDevicesAssignmentTarget(),
        )
    )
    desired = _with_enum_intent(
        make_mobile_app_assignment(
            assignment_id="existing",
            intent=AssignmentIntent.AVAILABLE,
            target=AllDevicesAssignmentTarget(),
        )
    )
    additional = _with_enum_intent(
        make_mobile_app_assignment(
            assignment_id="",
            intent=AssignmentIntent.REQUIRED,
            target=AllDevicesAssignmentTarget(),
        )
    )
    diff = AssignmentDiff(
        to_create=[additional],
        to_update=[AssignmentUpdate(current=current, desired=desired)],
        to_delete=[],
    )

    events: list = []
    errors: list = []
    controller.register_callbacks(
        applied=lambda event: events.append(event),
        error=lambda event: errors.append(event),
    )

    assign_path = "/deviceAppManagement/mobileApps/app-1/assign"
    factory.set_request_json_response(
        "POST", assign_path, Exception("simulated failure")
    )

    with pytest.raises(Exception, match="simulated failure"):
        await controller.apply_diff("app-1", diff)

    assert errors, "Expected error event after failed apply"
    statuses = [event.status for event in events]
    assert statuses[:2] == [MutationStatus.PENDING, MutationStatus.FAILED]

    factory.set_request_json_response("POST", assign_path, {"status": "ok"})
    await controller.apply_diff("app-1", diff)

    statuses = [event.status for event in events]
    assert statuses[-2:] == [MutationStatus.PENDING, MutationStatus.SUCCEEDED]
    assert factory.recorded_requests


def _make_group_target(group_id: str) -> GroupAssignmentTarget:
    return GroupAssignmentTarget(group_id=group_id)


@pytest.mark.asyncio
async def test_bulk_wizard_conflict_resolution(qt_app) -> None:  # noqa: ARG001
    app_id = "app-1"
    group_id = "group-1"

    current = _with_enum_intent(
        make_mobile_app_assignment(
            assignment_id="assign-1",
            intent=AssignmentIntent.REQUIRED,
            target=_make_group_target(group_id),
        )
    )
    desired = _with_enum_intent(
        make_mobile_app_assignment(
            assignment_id="assign-1",
            intent=AssignmentIntent.AVAILABLE,
            target=_make_group_target(group_id),
        )
    )

    diff = AssignmentDiff(
        to_create=[],
        to_update=[AssignmentUpdate(current=current, desired=desired)],
        to_delete=[],
    )

    wizard = BulkAssignmentWizard(
        diffs={app_id: diff},
        apps={
            app_id: MobileApp.from_graph(
                {"id": app_id, "displayName": "Contoso Portal"}
            )
        },
        group_lookup={
            group_id: DirectoryGroup.from_graph(
                {"id": group_id, "displayName": "Contoso Group"}
            )
        },
        desired_assignments=[desired],
    )

    descriptors = wizard.conflict_descriptors()
    assert len(descriptors) == 1
    assert descriptors[0].group_label == "Contoso Group"

    filtered = wizard.filtered_diffs()[app_id]
    assert len(filtered.to_update) == 1

    wizard.set_conflict_choice(app_id, "assign-1", False)
    filtered_after = wizard.filtered_diffs()
    assert app_id not in filtered_after


@pytest.mark.usefixtures("qt_app")
def test_bulk_wizard_full_flow_generates_plan(qtbot):
    app_id = "app-1"
    group_id = "group-1"

    current = _with_enum_intent(
        make_mobile_app_assignment(
            assignment_id="assign-1",
            intent=AssignmentIntent.REQUIRED,
            target=_make_group_target(group_id),
        )
    )
    desired = _with_enum_intent(
        make_mobile_app_assignment(
            assignment_id="assign-1",
            intent=AssignmentIntent.AVAILABLE,
            target=_make_group_target(group_id),
        )
    )
    diff = AssignmentDiff(
        to_create=[],
        to_update=[AssignmentUpdate(current=current, desired=desired)],
        to_delete=[],
    )

    wizard = BulkAssignmentWizard(
        diffs={app_id: diff},
        apps={
            app_id: MobileApp.from_graph(
                {"id": app_id, "displayName": "Contoso Portal"}
            )
        },
        group_lookup={
            group_id: DirectoryGroup.from_graph(
                {"id": group_id, "displayName": "Contoso Group"}
            )
        },
        desired_assignments=[desired],
        staged_groups={group_id: "Contoso Group"},
    )

    qtbot.addWidget(wizard)
    wizard.show()
    qtbot.waitUntil(lambda: wizard.isVisible())

    # Step 1: keep default selection but ensure navigation works.
    qtbot.mouseClick(wizard.button(QWizard.NextButton), Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: wizard.currentId() == 1)

    # Step 2: leave existing group selected to avoid filtering everything out.
    qtbot.mouseClick(wizard.button(QWizard.NextButton), Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: wizard.currentId() == 2)

    # Step 3: adjust options and register conflict decision.
    settings_page = wizard.page(2)
    settings_page._notify_checkbox.setChecked(True)  # noqa: SLF001
    settings_page._skip_warnings_checkbox.setChecked(True)  # noqa: SLF001
    settings_page._retry_checkbox.setChecked(False)  # noqa: SLF001
    if settings_page._conflict_rows:  # noqa: SLF001
        row = settings_page._conflict_rows[0]  # noqa: SLF001
        row._choice.setCurrentIndex(0)  # apply desired change  # noqa: SLF001

    qtbot.mouseClick(wizard.button(QWizard.NextButton), Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: wizard.currentId() == 3)

    # Preview should reflect our diff.
    summary_model = wizard.summary_model()
    assert summary_model.rowCount() == 1

    qtbot.mouseClick(wizard.button(QWizard.FinishButton), Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: not wizard.isVisible())

    plan = wizard.result()
    assert plan is not None
    assert plan.selected_app_ids == [app_id]
    assert plan.options.notify_end_users is True
    assert plan.options.skip_warnings is True
    assert plan.options.retry_conflicts is False
    assert app_id in plan.diffs


@pytest.mark.usefixtures("qt_app")
def test_bulk_wizard_filtered_diffs_follow_selections():
    app_a = "app-a"
    app_b = "app-b"
    group_id = "group-1"

    diff_a = AssignmentDiff(
        to_create=[],
        to_update=[
            AssignmentUpdate(
                current=_with_enum_intent(
                    make_mobile_app_assignment(
                        assignment_id="assign-1",
                        intent=AssignmentIntent.REQUIRED,
                        target=_make_group_target(group_id),
                    )
                ),
                desired=_with_enum_intent(
                    make_mobile_app_assignment(
                        assignment_id="assign-1",
                        intent=AssignmentIntent.AVAILABLE,
                        target=_make_group_target(group_id),
                    )
                ),
            )
        ],
        to_delete=[],
    )
    diff_b = AssignmentDiff(
        to_create=[
            _with_enum_intent(
                make_mobile_app_assignment(
                    assignment_id="",
                    intent=AssignmentIntent.REQUIRED,
                    target=AllDevicesAssignmentTarget(),
                )
            )
        ],
        to_update=[],
        to_delete=[],
    )

    wizard = BulkAssignmentWizard(
        diffs={app_a: diff_a, app_b: diff_b},
        apps={
            app_a: MobileApp.from_graph({"id": app_a, "displayName": "Portal"}),
            app_b: MobileApp.from_graph({"id": app_b, "displayName": "Company Portal"}),
        },
        group_lookup={
            group_id: DirectoryGroup.from_graph(
                {"id": group_id, "displayName": "Contoso Group"}
            )
        },
        desired_assignments=[diff_a.to_update[0].desired],
        staged_groups={},
    )

    # Focus on a single app and enable group filtering.
    wizard.set_selected_app_ids([app_a])
    wizard.set_selected_group_ids({group_id}, filter_active=True)
    wizard.set_options(
        notify_end_users=True,
        skip_warnings=False,
        retry_conflicts=True,
    )

    wizard.rebuild_preview()
    assert wizard.summary_model().rowCount() == 1

    # Dropping the conflict should remove the diff entirely.
    wizard.set_conflict_choice(app_a, "assign-1", False)
    wizard.rebuild_preview()
    assert wizard.summary_model().rowCount() == 0
    assert wizard.filtered_diffs() == {}
