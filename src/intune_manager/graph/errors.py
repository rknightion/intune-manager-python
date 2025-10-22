from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Sequence


class GraphErrorCategory(str, Enum):
    PERMISSION = "permission"
    CONFLICT = "conflict"
    VALIDATION = "validation"
    RATE_LIMIT = "rate_limit"
    NETWORK = "network"
    AUTHENTICATION = "authentication"
    UNKNOWN = "unknown"


@dataclass(slots=True)
class GraphAPIError(Exception):
    message: str
    category: GraphErrorCategory = GraphErrorCategory.UNKNOWN
    status_code: int | None = None
    code: str | None = None
    retry_after: str | None = None
    inner_error: Exception | None = None

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.message

    @property
    def recovery_suggestion(self) -> str | None:
        if self.category is GraphErrorCategory.AUTHENTICATION:
            return "Sign out and sign back in with an account that has access."
        if self.category is GraphErrorCategory.PERMISSION:
            return "Request the required Microsoft Graph permissions from your administrator."
        if self.category is GraphErrorCategory.RATE_LIMIT:
            if self.retry_after:
                return f"Microsoft Graph throttled the request. The app will retry after {self.retry_after} seconds."
            return "Microsoft Graph throttled the request. The app will retry using exponential backoff."
        if self.category is GraphErrorCategory.NETWORK:
            return "Check your internet connection and try again."
        if self.category is GraphErrorCategory.CONFLICT:
            return "The operation conflicts with existing data. Refresh and verify the latest state."
        if self.category is GraphErrorCategory.VALIDATION:
            return "The request payload is invalid. Review fields and try again."
        return None

    @property
    def required_permissions(self) -> Sequence[str] | None:
        if self.category is GraphErrorCategory.PERMISSION:
            return [
                "DeviceManagementApps.ReadWrite.All",
                "DeviceManagementManagedDevices.ReadWrite.All",
                "Group.Read.All",
            ]
        return None

    @property
    def help_url(self) -> str | None:
        if self.category is GraphErrorCategory.RATE_LIMIT:
            return "https://learn.microsoft.com/graph/throttling"
        if self.category is GraphErrorCategory.PERMISSION:
            return "https://learn.microsoft.com/graph/permissions-reference"
        if self.category is GraphErrorCategory.AUTHENTICATION:
            return "https://learn.microsoft.com/azure/active-directory/develop/troubleshoot-common-errors"
        if self.category is GraphErrorCategory.UNKNOWN:
            return None
        return "https://learn.microsoft.com/graph/errors"

    @property
    def is_retriable(self) -> bool:
        if self.category in {GraphErrorCategory.RATE_LIMIT, GraphErrorCategory.NETWORK}:
            return True
        if self.status_code and 500 <= self.status_code <= 599:
            return True
        return False


class RateLimitError(GraphAPIError):
    def __init__(
        self, message: str = "Rate limited", retry_after: str | None = None
    ) -> None:
        super().__init__(
            message=message,
            category=GraphErrorCategory.RATE_LIMIT,
            retry_after=retry_after,
        )


class AuthenticationError(GraphAPIError):
    def __init__(self, message: str = "Authentication failed") -> None:
        super().__init__(message=message, category=GraphErrorCategory.AUTHENTICATION)


class PermissionError(GraphAPIError):
    def __init__(self, message: str = "Insufficient permissions") -> None:
        super().__init__(message=message, category=GraphErrorCategory.PERMISSION)


__all__ = [
    "GraphAPIError",
    "GraphErrorCategory",
    "RateLimitError",
    "AuthenticationError",
    "PermissionError",
]
