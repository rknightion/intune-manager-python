from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from intune_manager.data import MobileAppAssignment
from intune_manager.graph.client import GraphClientFactory
from intune_manager.graph.requests import (
    GraphRequest,
    mobile_app_assign_request,
    mobile_app_assignment_delete_request,
)
from intune_manager.services.base import (
    EventHook,
    MutationStatus,
    ServiceErrorEvent,
    run_optimistic_mutation,
)
from intune_manager.utils import CancellationError, CancellationToken, get_logger


logger = get_logger(__name__)


@dataclass(slots=True)
class AssignmentUpdate:
    current: MobileAppAssignment
    desired: MobileAppAssignment


@dataclass(slots=True)
class AssignmentDiff:
    to_create: list[MobileAppAssignment]
    to_update: list[AssignmentUpdate]
    to_delete: list[MobileAppAssignment]

    @property
    def is_noop(self) -> bool:
        return not (self.to_create or self.to_update or self.to_delete)


@dataclass(slots=True)
class AssignmentAppliedEvent:
    app_id: str
    diff: AssignmentDiff
    status: MutationStatus
    error: Exception | None = None


class AssignmentService:
    """Handle assignment diffing, apply flows, and backup operations."""

    def __init__(self, client_factory: GraphClientFactory) -> None:
        self._client_factory = client_factory
        self.applied: EventHook[AssignmentAppliedEvent] = EventHook()
        self.errors: EventHook[ServiceErrorEvent] = EventHook()

    # ----------------------------------------------------------------- Diffing

    def diff(
        self,
        *,
        current: Iterable[MobileAppAssignment],
        desired: Iterable[MobileAppAssignment],
    ) -> AssignmentDiff:
        current_list = list(current)
        desired_list = list(desired)

        current_by_id = {
            assignment.id: assignment for assignment in current_list if assignment.id
        }
        identity_map: dict[
            tuple[str | None, str | None, str | None, str | None], MobileAppAssignment
        ] = {}
        matched_ids: set[str] = set()

        for assignment in current_list:
            identity_map[_assignment_identity(assignment)] = assignment

        to_create: list[MobileAppAssignment] = []
        to_update: list[AssignmentUpdate] = []

        for assignment in desired_list:
            if assignment.id and assignment.id in current_by_id:
                matched = current_by_id[assignment.id]
                matched_ids.add(assignment.id)
                if not _assignments_equal(matched, assignment):
                    to_update.append(
                        AssignmentUpdate(current=matched, desired=assignment)
                    )
                continue

            identity = _assignment_identity(assignment)
            matched = identity_map.get(identity)
            if matched:
                if matched.id:
                    matched_ids.add(matched.id)
                if not _assignments_equal(matched, assignment):
                    to_update.append(
                        AssignmentUpdate(current=matched, desired=assignment)
                    )
                continue

            to_create.append(assignment)

        to_delete = [
            assignment
            for assignment in current_list
            if assignment.id and assignment.id not in matched_ids
        ]
        return AssignmentDiff(
            to_create=to_create,
            to_update=to_update,
            to_delete=to_delete,
        )

    # ---------------------------------------------------------------- Apply ops

    async def apply_diff(
        self,
        app_id: str,
        diff: AssignmentDiff,
        *,
        cancellation_token: CancellationToken | None = None,
    ) -> None:
        def event_builder(
            status: MutationStatus, error: Exception | None = None
        ) -> AssignmentAppliedEvent:
            return AssignmentAppliedEvent(
                app_id=app_id,
                diff=diff,
                status=status,
                error=error,
            )

        if cancellation_token:
            cancellation_token.raise_if_cancelled()
        if diff.is_noop:
            logger.debug("Assignment diff is noop", app_id=app_id)
            self.applied.emit(event_builder(MutationStatus.SUCCEEDED, None))
            return

        async def operation() -> None:
            await self._apply(app_id, diff, cancellation_token=cancellation_token)

        try:
            await run_optimistic_mutation(
                emitter=self.applied,
                event_builder=event_builder,
                operation=operation,
            )
            logger.debug(
                "Assignment diff applied",
                app_id=app_id,
                creates=len(diff.to_create),
                updates=len(diff.to_update),
                deletes=len(diff.to_delete),
            )
        except CancellationError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to apply assignment diff", app_id=app_id)
            self.errors.emit(ServiceErrorEvent(tenant_id=None, error=exc))
            raise

    async def _apply(
        self,
        app_id: str,
        diff: AssignmentDiff,
        *,
        cancellation_token: CancellationToken | None = None,
    ) -> None:
        if cancellation_token:
            cancellation_token.raise_if_cancelled()
        if diff.is_noop:
            logger.debug("Assignment diff is noop", app_id=app_id)
            return

        payload_assignments = [
            assignment.to_graph() for assignment in diff.to_create
        ] + [update.desired.to_graph() for update in diff.to_update]

        if payload_assignments:
            request = mobile_app_assign_request(app_id, payload_assignments)
            await self._client_factory.request_json(
                request.method,
                request.url,
                json_body=request.body,
                headers=request.headers,
                api_version=request.api_version,
                cancellation_token=cancellation_token,
            )
            logger.debug(
                "Assignments upserted",
                app_id=app_id,
                created=len(diff.to_create),
                updated=len(diff.to_update),
            )

        delete_requests: list[GraphRequest] = []
        for assignment in diff.to_delete:
            if not assignment.id:
                continue
            delete_requests.append(
                mobile_app_assignment_delete_request(app_id, assignment.id),
            )

        if delete_requests:
            await self._client_factory.execute_batch(
                delete_requests,
                cancellation_token=cancellation_token,
            )
            logger.debug(
                "Assignments deleted", app_id=app_id, deleted=len(delete_requests)
            )

    # ---------------------------------------------------------------- Backups

    def export_assignments(
        self,
        assignments: Iterable[MobileAppAssignment],
    ) -> list[dict]:
        return [assignment.to_graph() for assignment in assignments]


def _assignment_identity(
    assignment: MobileAppAssignment,
) -> tuple[str | None, str | None, str | None, str | None]:
    target = assignment.target
    group_id = getattr(target, "group_id", None)
    filter_id = getattr(target, "assignment_filter_id", None)
    target_type = getattr(target, "odata_type", None)
    return (
        group_id,
        filter_id,
        target_type,
        assignment.intent,
    )


def _assignments_equal(
    a: MobileAppAssignment,
    b: MobileAppAssignment,
) -> bool:
    payload_a = a.to_graph()
    payload_b = b.to_graph()
    payload_a.pop("id", None)
    payload_b.pop("id", None)
    return payload_a == payload_b


__all__ = [
    "AssignmentService",
    "AssignmentDiff",
    "AssignmentUpdate",
    "AssignmentAppliedEvent",
]
