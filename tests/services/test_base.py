from __future__ import annotations

import pytest

from intune_manager.services.base import (
    EventHook,
    MutationStatus,
    run_optimistic_mutation,
)


def _tuple_builder(
    status: MutationStatus, error: Exception | None
) -> tuple[MutationStatus, Exception | None]:
    return (status, error)


@pytest.mark.asyncio
async def test_run_optimistic_mutation_emits_pending_and_success() -> None:
    hook: EventHook[tuple[MutationStatus, Exception | None]] = EventHook()
    emitted: list[tuple[MutationStatus, Exception | None]] = []
    hook.subscribe(emitted.append)

    async def operation() -> int:
        return 42

    result = await run_optimistic_mutation(
        emitter=hook,
        event_builder=_tuple_builder,
        operation=operation,
    )

    assert result == 42
    assert emitted == [
        (MutationStatus.PENDING, None),
        (MutationStatus.SUCCEEDED, None),
    ]


@pytest.mark.asyncio
async def test_run_optimistic_mutation_emits_failure_on_exception() -> None:
    hook: EventHook[tuple[MutationStatus, Exception | None]] = EventHook()
    emitted: list[tuple[MutationStatus, Exception | None]] = []
    hook.subscribe(emitted.append)

    async def operation() -> None:
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        await run_optimistic_mutation(
            emitter=hook,
            event_builder=_tuple_builder,
            operation=operation,
        )

    assert len(emitted) == 2
    assert emitted[0] == (MutationStatus.PENDING, None)
    failure_status, failure_error = emitted[1]
    assert failure_status is MutationStatus.FAILED
    assert isinstance(failure_error, RuntimeError)
    assert str(failure_error) == "boom"
