from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable, Protocol

from .commands import CommandRegistry
from .notifications import ToastLevel
from .theme import ThemeManager


RunAsyncCallable = Callable[[Awaitable[object]], None]


class ShowNotificationCallable(Protocol):
    """Protocol for showing toast notifications with keyword-only parameters."""

    def __call__(
        self, text: str, /, *, level: ToastLevel = ..., duration_ms: int | None = ...
    ) -> None: ...


class SetBusyCallable(Protocol):
    def __call__(self, message: str | None = ..., *, blocking: bool = ...) -> None: ...


class ShowBannerCallable(Protocol):
    def __call__(
        self,
        message: str,
        level: ToastLevel = ...,
        *,
        action_label: str | None = ...,
        on_action: Callable[[], None] | None = ...,
    ) -> None:
        ...


@dataclass(slots=True)
class UIContext:
    """Shared UI affordances available to feature modules."""

    show_notification: ShowNotificationCallable
    set_busy: SetBusyCallable
    clear_busy: Callable[[], None]
    run_async: RunAsyncCallable
    command_registry: CommandRegistry
    theme_manager: ThemeManager
    show_banner: ShowBannerCallable
    clear_banner: Callable[[], None]


__all__ = [
    "UIContext",
    "RunAsyncCallable",
    "ShowNotificationCallable",
    "SetBusyCallable",
    "ShowBannerCallable",
]
