from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

import asyncio

from intune_manager.data import MobileAppAssignment
from intune_manager.graph.client import GraphClientFactory
from intune_manager.graph.requests import (
    BETA_VERSION,
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
from intune_manager.graph.errors import GraphAPIError, GraphErrorCategory
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

        requests: list[GraphRequest] = []
        payload_assignments = [
            _normalized_assignment_payload(assignment) for assignment in diff.to_create
        ] + [
            _normalized_assignment_payload(update.desired) for update in diff.to_update
        ]
        if payload_assignments:
            requests.append(mobile_app_assign_request(app_id, payload_assignments))

        for assignment in diff.to_delete:
            if not assignment.id:
                continue
            requests.append(mobile_app_assignment_delete_request(app_id, assignment.id))

        if not requests:
            logger.debug("Assignment diff contained no actionable requests", app_id=app_id)
            return

        await self._execute_batch_with_retry(
            requests,
            cancellation_token=cancellation_token,
        )
        logger.debug(
            "Assignments applied via batch",
            app_id=app_id,
            created=len(diff.to_create),
            updated=len(diff.to_update),
            deleted=len(diff.to_delete),
        )

    async def apply_diffs(
        self,
        app_diffs: Iterable[tuple[str, AssignmentDiff]],
        *,
        cancellation_token: CancellationToken | None = None,
    ) -> None:
        """Apply assignment diffs for multiple apps using batched /batch requests."""

        requests: list[GraphRequest] = []
        app_by_request: dict[str, str] = {}
        last_error_messages: list[str] = []

        for app_id, diff in app_diffs:
            if cancellation_token:
                cancellation_token.raise_if_cancelled()
            if diff.is_noop:
                continue
            payload_assignments = [
                _normalized_assignment_payload(assignment) for assignment in diff.to_create
            ] + [
                _normalized_assignment_payload(update.desired) for update in diff.to_update
            ]
            if payload_assignments:
                req = mobile_app_assign_request(app_id, payload_assignments)
                requests.append(req)
            for assignment in diff.to_delete:
                if not assignment.id:
                    continue
                requests.append(
                    mobile_app_assignment_delete_request(app_id, assignment.id)
                )

        if not requests:
            logger.debug("No assignment changes to apply across apps")
            return

        # Chunk to Graph batch limit (20 requests per batch)
        errors: list[str] = []
        last_error_messages: list[str] = []
        idx = 0
        while idx < len(requests):
            chunk = requests[idx : idx + 20]
            # Assign stable IDs for mapping responses to apps
            for offset, req in enumerate(chunk, start=1):
                req_id = f"{idx+offset}"
                req.request_id = req_id
                app_id = _app_id_from_request(req)
                if app_id:
                    app_by_request[req_id] = app_id

            try:
                responses = await self._execute_batch_with_retry(
                    chunk,
                    cancellation_token=cancellation_token,
                )
            except GraphAPIError as exc:
                last_error_messages.append(str(exc))
                raise

            for response in responses:
                status = int(response.get("status", 0))
                if status >= 400:
                    req_id = response.get("id")
                    app_id = app_by_request.get(req_id, "unknown app")
                    body = response.get("body")
                    message = f"{app_id} failed ({status}): {body or response}"
                    logger.error("Assignment batch item failed", app_id=app_id, status=status, body=body)
                    errors.append(message)
            idx += 20

        if errors:
            logger.error("Assignment batch failed", errors=errors)
            raise GraphAPIError(
                message="; ".join(errors or last_error_messages or ["Batch assignment failed"]),
                category=GraphErrorCategory.UNKNOWN,
            )

    async def _execute_batch_with_retry(
        self,
        requests: list[GraphRequest],
        *,
        max_retries: int = 2,
        cancellation_token: CancellationToken | None = None,
    ) -> list[dict[str, Any]]:
        """Execute assignment Graph requests via /batch with basic retry on 429/503."""

        attempt = 0
        pending: list[GraphRequest] = list(requests)
        delay = 0.0
        successes: list[dict[str, Any]] = []
        last_errors: list[str] = []

        while pending:
            if cancellation_token:
                cancellation_token.raise_if_cancelled()
            if delay > 0:
                await asyncio.sleep(delay)
            # Ensure stable IDs for mapping responses
            for idx, req in enumerate(pending, start=1):
                if req.request_id is None:
                    req.request_id = str(idx)

            result = await self._client_factory.execute_batch(
                pending,
                api_version=BETA_VERSION,
                cancellation_token=cancellation_token,
            )

            raw_responses = result.get("responses", []) if isinstance(result, dict) else []
            responses = {resp.get("id"): resp for resp in raw_responses}
            retry: list[GraphRequest] = []
            retry_after_seconds = 0.0
            errors: list[str] = []

            for req in pending:
                resp = responses.get(req.request_id)
                if resp is None:
                    errors.append(f"No batch response for request {req.request_id}")
                    continue
                status = int(resp.get("status", 0))
                if status in (429, 503):
                    headers = resp.get("headers") or {}
                    retry_header = headers.get("Retry-After") or headers.get(
                        "retry-after"
                    )
                    try:
                        retry_after_seconds = max(
                            retry_after_seconds, float(retry_header or 0.0)
                        )
                    except ValueError:
                        retry_after_seconds = max(retry_after_seconds, 0.0)
                    retry.append(req)
                    continue
                if status >= 400:
                    body = resp.get("body")
                    errors.append(
                        f"{req.method} {req.url} failed with {status}: {body or resp}"
                    )
                else:
                    successes.append(resp)
            if errors:
                last_errors = errors
                logger.error("Batch request failed", errors=errors)
                raise GraphAPIError(
                    message="; ".join(errors),
                    category=GraphErrorCategory.UNKNOWN,
                )

            if not retry:
                return successes

            attempt += 1
            if attempt > max_retries:
                raise GraphAPIError(
                    message=(
                        f"Batch assignment retries exhausted ({len(retry)} request(s) still failing). "
                        f"Errors: {'; '.join(last_errors)}"
                    ),
                    category=GraphErrorCategory.RATE_LIMIT,
                    status_code=429,
                )
            delay = max(retry_after_seconds, min(2**attempt, 10.0))
            pending = retry

        return successes

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


def _app_id_from_request(request: GraphRequest) -> str | None:
    """Extract mobile app ID from request URL (assign/assignments endpoints)."""

    url = request.url or ""
    if "/mobileApps/" not in url:
        return None
    tail = url.split("/mobileApps/", maxsplit=1)[-1]
    return tail.split("/", maxsplit=1)[0] or None


def _normalized_assignment_payload(assignment: MobileAppAssignment) -> dict[str, Any]:
    payload = assignment.to_graph()
    if not payload.get("id"):
        payload.pop("id", None)
    return payload


__all__ = [
    "AssignmentService",
    "AssignmentDiff",
    "AssignmentUpdate",
    "AssignmentAppliedEvent",
]
