from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable, Dict, Iterable, List, Optional


CommandCallback = Callable[[], object | Awaitable[object] | None]


@dataclass(slots=True)
class CommandAction:
    """Represents a palette command with metadata for discovery."""

    id: str
    title: str
    callback: CommandCallback
    category: str | None = None
    description: str | None = None
    shortcut: str | None = None


class CommandRegistry:
    """Register and query application-level commands."""

    def __init__(self) -> None:
        self._commands: Dict[str, CommandAction] = {}

    def register(self, action: CommandAction) -> Callable[[], None]:
        self._commands[action.id] = action

        def unregister() -> None:
            self._commands.pop(action.id, None)

        return unregister

    def unregister(self, action_id: str) -> None:
        self._commands.pop(action_id, None)

    def actions(self) -> List[CommandAction]:
        return sorted(self._commands.values(), key=lambda action: action.title.lower())

    def search(self, query: str) -> List[CommandAction]:
        if not query:
            return self.actions()
        lowered = query.lower()
        matches: List[CommandAction] = []
        for action in self._commands.values():
            haystack = [
                action.title.lower(),
                (action.category or "").lower(),
                (action.description or "").lower(),
            ]
            if any(lowered in field for field in haystack if field):
                matches.append(action)
        matches.sort(key=lambda action: action.title.lower())
        return matches

    def get(self, action_id: str) -> Optional[CommandAction]:
        return self._commands.get(action_id)

    def __iter__(self) -> Iterable[CommandAction]:
        return iter(self.actions())


__all__ = ["CommandAction", "CommandRegistry", "CommandCallback"]
