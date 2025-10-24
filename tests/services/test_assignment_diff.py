from __future__ import annotations

from datetime import datetime

from intune_manager.data.models.assignment import (
    AllDevicesAssignmentTarget,
    AssignmentIntent,
    AssignmentSettings,
    FilteredGroupAssignmentTarget,
    GroupAssignmentTarget,
)
from intune_manager.services.assignments import AssignmentService

from tests.factories import (
    clone_assignment_with_updates,
    make_mobile_app_assignment,
)


def _service() -> AssignmentService:
    class _DummyFactory:
        async def request_json(self, *args, **kwargs):
            raise NotImplementedError

        async def execute_batch(self, *args, **kwargs):
            raise NotImplementedError

    return AssignmentService(_DummyFactory())


def test_diff_detects_creates_updates_and_deletes() -> None:
    service = _service()
    current = [
        make_mobile_app_assignment(
            assignment_id="existing-1",
            intent=AssignmentIntent.REQUIRED,
            target=GroupAssignmentTarget(group_id="group-a"),
        ),
        make_mobile_app_assignment(
            assignment_id="existing-2",
            intent=AssignmentIntent.AVAILABLE,
            target=GroupAssignmentTarget(group_id="group-b"),
        ),
    ]

    updated = clone_assignment_with_updates(
        current[0],
        settings_overrides={"start_date_time": datetime(2024, 1, 1, 9, 0, 0)},
    )
    new_assignment = make_mobile_app_assignment(
        assignment_id="",
        intent=AssignmentIntent.REQUIRED,
        target=GroupAssignmentTarget(group_id="group-c"),
    )
    desired = [updated, new_assignment]

    diff = service.diff(current=current, desired=desired)
    assert len(diff.to_create) == 1
    assert diff.to_create[0].target.group_id == "group-c"
    assert len(diff.to_update) == 1
    assert diff.to_update[0].current.id == "existing-1"
    assert len(diff.to_delete) == 1
    assert diff.to_delete[0].id == "existing-2"


def test_diff_matches_assignments_by_identity_without_id() -> None:
    service = _service()
    current = [
        make_mobile_app_assignment(
            assignment_id="with-id",
            intent=AssignmentIntent.REQUIRED,
            target=FilteredGroupAssignmentTarget(
                group_id="group-a",
                assignment_filter_id="filter-1",
            ),
        )
    ]
    updated_target = FilteredGroupAssignmentTarget(
        group_id="group-a",
        assignment_filter_id="filter-1",
    )
    desired = [
        make_mobile_app_assignment(
            assignment_id="",
            intent=AssignmentIntent.REQUIRED,
            target=updated_target,
            settings=AssignmentSettings(
                deadline_date_time=datetime(2024, 1, 2, 9, 0, 0)
            ),
        )
    ]

    diff = service.diff(current=current, desired=desired)
    assert not diff.to_create
    assert len(diff.to_update) == 1
    assert diff.to_update[0].current.id == "with-id"
    assert not diff.to_delete


def test_diff_noop_when_assignments_equal() -> None:
    service = _service()
    assignment = make_mobile_app_assignment(
        assignment_id="noop",
        intent=AssignmentIntent.AVAILABLE,
        target=AllDevicesAssignmentTarget(),
        settings=AssignmentSettings(
            start_date_time=datetime(2024, 1, 1, 10, 0, 0),
            deadline_date_time=datetime(2024, 1, 10, 10, 0, 0),
        ),
    )

    diff = service.diff(current=[assignment], desired=[assignment])
    assert diff.is_noop
    assert not diff.to_create
    assert not diff.to_update
    assert not diff.to_delete
