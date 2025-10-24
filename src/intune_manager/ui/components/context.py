from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable

from .commands import CommandRegistry
from .notifications import ToastLevel
from .theme import ThemeManager


RunAsyncCallable = Callable[[Awaitable[object]], None]
ShowNotificationCallable = Callable[[str, ToastLevel, int], None]
SetBusyCallable = Callable[[str | None], None]
ShowBannerCallable = Callable[[str, ToastLevel], None]


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
