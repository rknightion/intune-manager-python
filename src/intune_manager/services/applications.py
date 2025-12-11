from __future__ import annotations

import base64
import csv
import io
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from intune_manager.data import (
    AttachmentCache,
    AttachmentMetadata,
    MobileApp,
    MobileAppAssignment,
    MobileAppRepository,
)
from intune_manager.data.models.application import MobileAppPlatform
from intune_manager.data.validation import GraphResponseValidator
from intune_manager.graph import GraphAPIError, GraphErrorCategory
from intune_manager.graph.client import GraphClientFactory
from intune_manager.graph.requests import (
    BETA_VERSION,
    mobile_app_assignments_request,
    mobile_app_icon_request,
    mobile_app_install_summary_report_request,
)
from intune_manager.services.base import EventHook, RefreshEvent, ServiceErrorEvent
from intune_manager.utils import CancellationError, CancellationToken, get_logger
from intune_manager.utils.app_types import (
    PLATFORM_TYPE_COMPATIBILITY,
    extract_app_type,
)
from urllib.parse import urlparse, parse_qs


logger = get_logger(__name__)


@dataclass(slots=True)
class InstallSummaryEvent:
    app_id: str
    summary: dict[str, Any]


class ApplicationService:
    """Manage Intune mobile applications, assignments metadata, and icon cache."""

    def __init__(
        self,
        client_factory: GraphClientFactory,
        repository: MobileAppRepository,
        attachments: AttachmentCache,
    ) -> None:
        self._client_factory = client_factory
        self._repository = repository
        self._attachments = attachments
        self._default_ttl = timedelta(minutes=20)
        self._validator = GraphResponseValidator("mobile_apps")

        self.refreshed: EventHook[RefreshEvent[list[MobileApp]]] = EventHook()
        self.errors: EventHook[ServiceErrorEvent] = EventHook()
        self.install_summary: EventHook[InstallSummaryEvent] = EventHook()
        self.icon_cached: EventHook[AttachmentMetadata] = EventHook()
        self._install_summary_cache: dict[str, tuple[dict[str, Any], datetime]] = {}
        self._summary_ttl = timedelta(minutes=15)

    # ------------------------------------------------------------------ Queries

    def list_cached(self, tenant_id: str | None = None) -> list[MobileApp]:
        apps = self._repository.list_all(tenant_id=tenant_id)
        logger.debug(
            "Application cache read",
            tenant_id=tenant_id,
            count=len(apps),
        )
        return apps

    def is_cache_stale(self, tenant_id: str | None = None) -> bool:
        return self._repository.is_cache_stale(tenant_id=tenant_id)

    def count_cached(self, tenant_id: str | None = None) -> int:
        return self._repository.cached_count(tenant_id=tenant_id)

    def last_refresh(self, tenant_id: str | None = None) -> datetime | None:
        return self._repository.last_refresh(tenant_id=tenant_id)

    # ----------------------------------------------------------------- Actions

    async def refresh(
        self,
        tenant_id: str | None = None,
        *,
        force: bool = False,
        include_assignments: bool = True,
        include_categories: bool = True,
        cancellation_token: CancellationToken | None = None,
    ) -> list[MobileApp]:
        logger.info(
            "Applications refresh started",
            tenant_id=tenant_id,
            force=force,
            cache_stale=self.is_cache_stale(tenant_id=tenant_id),
        )
        if cancellation_token:
            cancellation_token.raise_if_cancelled()
        cached = self.list_cached(tenant_id=tenant_id)
        needs_metadata_refresh = any(
            app.platform_type is None
            or app.platform_type is MobileAppPlatform.UNKNOWN
            or app.app_type is None
            for app in cached
        )
        if not force and not self.is_cache_stale(tenant_id=tenant_id) and not needs_metadata_refresh:
            logger.info(
                "Applications returning cached data",
                tenant_id=tenant_id,
                count=len(cached),
            )
            self.refreshed.emit(
                RefreshEvent(
                    tenant_id=tenant_id,
                    items=cached,
                    from_cache=True,
                ),
            )
            return cached
        if needs_metadata_refresh:
            logger.info(
                "Application cache missing metadata; forcing refresh",
                tenant_id=tenant_id,
            )

        expands: list[str] = []
        if include_assignments:
            expands.append("assignments")
        if include_categories:
            expands.append("categories")
        params = {"$expand": ",".join(expands)} if expands else None

        logger.info(
            "Fetching applications from Graph API",
            tenant_id=tenant_id,
            params=params,
        )
        try:
            apps: list[MobileApp] = []
            self._validator.reset()
            invalid_count = 0
            async for item in self._client_factory.iter_collection(
                "GET",
                "/deviceAppManagement/mobileApps",
                params=params,
                cancellation_token=cancellation_token,
            ):
                if cancellation_token:
                    cancellation_token.raise_if_cancelled()
                payload = item if isinstance(item, dict) else {"value": item}
                raw_odata = payload.get("@odata.type")

                # Debug logging to investigate missing platformType
                if len(apps) < 3:  # Only log first few apps
                    logger.debug(
                        "Graph API app payload fields",
                        app_id=payload.get("id"),
                        display_name=payload.get("displayName"),
                        odata_type=raw_odata,
                        has_platform_type="platformType" in payload,
                        platform_type_value=payload.get("platformType"),
                    )

                model = self._validator.parse(MobileApp, payload)
                if model is None:
                    invalid_count += 1
                    continue

                model = self._hydrate_missing_metadata(model)

                # Ensure app_type/platform populated even if cached payload omits @odata.type
                updates: dict[str, Any] = {}
                if raw_odata:
                    if model.app_type is None:
                        inferred_type = extract_app_type(raw_odata)
                        if inferred_type:
                            updates["app_type"] = inferred_type
                    if model.platform_type is None:
                        lower = raw_odata.lower()
                        platform = None
                        if "ios" in lower:
                            platform = "ios"
                        elif "macos" in lower or "macosx" in lower:
                            platform = "macOS"
                        elif any(key in lower for key in ("windows", "win32", "win10")):
                            platform = "windows"
                        elif "android" in lower:
                            platform = "android"
                        elif "web" in lower:
                            platform = "unknown"
                        if platform:
                            updates["platform_type"] = platform

                if updates:
                    model = model.model_copy(update=updates)

                apps.append(model)

            if cancellation_token:
                cancellation_token.raise_if_cancelled()
            self._repository.replace_all(
                apps,
                tenant_id=tenant_id,
                expires_in=self._default_ttl,
            )
            logger.info(
                "Applications refresh completed",
                tenant_id=tenant_id,
                count=len(apps),
                invalid_count=invalid_count,
            )
            self.refreshed.emit(
                RefreshEvent(
                    tenant_id=tenant_id,
                    items=apps,
                    from_cache=False,
                ),
            )
            if invalid_count:
                logger.warning(
                    "Application refresh skipped invalid payloads",
                    tenant_id=tenant_id,
                    invalid=invalid_count,
                )
            return apps
        except CancellationError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "Failed to refresh mobile applications", tenant_id=tenant_id
            )
            self.errors.emit(ServiceErrorEvent(tenant_id=tenant_id, error=exc))
            raise

    async def fetch_install_summary(
        self,
        app_id: str,
        *,
        tenant_id: str | None = None,
        force: bool = False,
        cancellation_token: CancellationToken | None = None,
    ) -> dict[str, Any]:
        if cancellation_token:
            cancellation_token.raise_if_cancelled()
        if not force:
            cached = self._install_summary_cache.get(app_id)
            if cached:
                payload, timestamp = cached
                now = datetime.now(UTC)
                if timestamp.tzinfo is None:
                    timestamp = timestamp.replace(tzinfo=UTC)
                if now - timestamp < self._summary_ttl:
                    self.install_summary.emit(
                        InstallSummaryEvent(app_id=app_id, summary=payload)
                    )
                    logger.debug("Install summary served from cache", app_id=app_id)
                    return payload

        request = mobile_app_install_summary_report_request(app_id)
        summary = await self._client_factory.request_json(
            request.method,
            request.url,
            json_body=request.body,
            headers=request.headers,
            api_version=request.api_version,
            cancellation_token=cancellation_token,
        )
        summary = self._parse_install_summary_report(summary, app_id)
        event = InstallSummaryEvent(app_id=app_id, summary=summary)
        self.install_summary.emit(event)
        self._install_summary_cache[app_id] = (summary, datetime.now(UTC))
        logger.debug(
            "Fetched install summary",
            app_id=app_id,
            tenant_id=tenant_id,
        )
        return summary

    def _parse_install_summary_report(
        self,
        payload: dict[str, Any],
        app_id: str,
    ) -> dict[str, Any]:
        encoded = payload.get("value")
        if not encoded:
            raise GraphAPIError(
                message="Install summary report returned no data",
                category=GraphErrorCategory.VALIDATION,
            )
        try:
            decoded = base64.b64decode(encoded)
        except Exception as exc:  # noqa: BLE001
            raise GraphAPIError(
                message="Failed to decode install summary report payload",
                category=GraphErrorCategory.VALIDATION,
            ) from exc

        try:
            text = decoded.decode("utf-8-sig")
        except Exception as exc:  # noqa: BLE001
            raise GraphAPIError(
                message="Install summary report payload is not valid UTF-8 text",
                category=GraphErrorCategory.VALIDATION,
            ) from exc

        reader = csv.DictReader(io.StringIO(text))
        rows = [row for row in reader if row and any(value for value in row.values())]
        if not rows:
            raise GraphAPIError(
                message="Install summary report was empty",
                category=GraphErrorCategory.VALIDATION,
            )

        # Prefer matching rows for the requested app ID when present.
        identifier_field = self._match_field(reader.fieldnames or [], ["ApplicationId"])
        filtered = rows
        if identifier_field:
            filtered = [
                row
                for row in rows
                if str(row.get(identifier_field, "")).lower() == app_id.lower()
            ] or rows
        row = filtered[0]

        summary: dict[str, Any] = {
            "source": "deviceManagement/reports/getAppsInstallSummaryReport (beta)",
            "rowsProcessed": len(rows),
        }
        for field_key, aliases in {
            "applicationId": ["ApplicationId"],
            "applicationName": ["ApplicationName", "DisplayName", "AppName"],
            "platform": ["Platform", "OS"],
            "publisher": ["Publisher", "Vendor"],
        }.items():
            value = self._extract_field(row, aliases)
            if value is not None:
                summary[field_key] = value

        count_aliases = {
            "installedDeviceCount": ["InstalledDeviceCount", "InstalledDevices"],
            "failedDeviceCount": ["FailedDeviceCount", "FailedDevices"],
            "notApplicableDeviceCount": [
                "NotApplicableDeviceCount",
                "NotApplicableDevices",
            ],
            "notInstalledDeviceCount": ["NotInstalledDeviceCount", "NotInstalledDevices"],
            "pendingInstallDeviceCount": [
                "PendingInstallDeviceCount",
                "PendingDevices",
                "PendingInstallations",
            ],
            "installedUserCount": ["InstalledUserCount", "InstalledUsers"],
            "failedUserCount": ["FailedUserCount", "FailedUsers"],
            "notApplicableUserCount": [
                "NotApplicableUserCount",
                "NotApplicableUsers",
            ],
            "notInstalledUserCount": ["NotInstalledUserCount", "NotInstalledUsers"],
            "pendingInstallUserCount": [
                "PendingInstallUserCount",
                "PendingUsers",
                "PendingUserInstalls",
            ],
        }
        for target, aliases in count_aliases.items():
            value = self._extract_int(row, aliases)
            if value is not None:
                summary[target] = value

        if len(summary) <= 2:  # Only metadata present
            summary["rawRow"] = row
            raise GraphAPIError(
                message="Install summary report did not contain expected columns",
                category=GraphErrorCategory.VALIDATION,
            )

        return summary

    @staticmethod
    def _normalize_field(name: str) -> str:
        return "".join(ch for ch in name.lower() if ch.isalnum())

    def _match_field(self, available: list[str], aliases: list[str]) -> str | None:
        normalised = {self._normalize_field(field): field for field in available if field}
        for alias in aliases:
            key = self._normalize_field(alias)
            if key in normalised:
                return normalised[key]
        return None

    def _extract_field(self, row: dict[str, Any], aliases: list[str]) -> str | None:
        field = self._match_field(list(row.keys()), aliases)
        if not field:
            return None
        value = row.get(field)
        if value is None:
            return None
        return str(value).strip()

    def _extract_int(self, row: dict[str, Any], aliases: list[str]) -> int | None:
        field = self._match_field(list(row.keys()), aliases)
        if not field:
            return None
        value = row.get(field)
        if value is None:
            return None
        try:
            return int(float(str(value).strip() or 0))
        except Exception:
            return None

    async def fetch_assignments(
        self,
        app_id: str,
        *,
        cancellation_token: CancellationToken | None = None,
    ) -> list[MobileAppAssignment]:
        if cancellation_token:
            cancellation_token.raise_if_cancelled()
        request = mobile_app_assignments_request(app_id)
        assignments: list[MobileAppAssignment] = []
        async for item in self._client_factory.iter_collection(
            request.method,
            request.url,
            cancellation_token=cancellation_token,
        ):
            if cancellation_token:
                cancellation_token.raise_if_cancelled()
            assignments.append(MobileAppAssignment.from_graph(item))
        logger.debug("Fetched app assignments", app_id=app_id, count=len(assignments))
        return assignments

    async def cache_icon(
        self,
        app_id: str,
        *,
        tenant_id: str | None = None,
        size: str = "large",
        force: bool = False,
        cancellation_token: CancellationToken | None = None,
    ) -> AttachmentMetadata | None:
        if cancellation_token:
            cancellation_token.raise_if_cancelled()
        cache_key = f"{app_id}:{size}"
        if not force:
            cached = self._attachments.get(cache_key, tenant_id=tenant_id)
            if cached:
                self.icon_cached.emit(cached)
                return cached

        blob = await self._fetch_icon_from_metadata(
            app_id, tenant_id=tenant_id, cancellation_token=cancellation_token
        )
        if blob is None:
            blob = await self._fetch_icon_via_media_endpoint(
                app_id,
                size=size,
                cancellation_token=cancellation_token,
                tenant_id=tenant_id,
            )
        if blob is None:
            return None
        metadata = self._attachments.store(
            cache_key,
            blob,
            tenant_id=tenant_id,
            category="mobile_app_icon",
        )
        self.icon_cached.emit(metadata)
        logger.debug("Cached app icon", app_id=app_id, size=len(blob))
        return metadata

    async def _fetch_icon_from_metadata(
        self,
        app_id: str,
        *,
        tenant_id: str | None = None,
        cancellation_token: CancellationToken | None = None,
    ) -> bytes | None:
        """Fetch an app icon by reading the inline largeIcon payload."""

        if cancellation_token:
            cancellation_token.raise_if_cancelled()
        path = f"/deviceAppManagement/mobileApps/{app_id}?$select=largeIcon"
        try:
            response = await self._client_factory.request_json(
                "GET",
                path,
                api_version=BETA_VERSION,
                cancellation_token=cancellation_token,
            )
        except CancellationError:
            raise
        except GraphAPIError as exc:
            if getattr(exc, "status_code", None) in (400, 404):
                logger.debug(
                    "App icon metadata not available",
                    app_id=app_id,
                    status=exc.status_code,
                )
                return None
            self.errors.emit(ServiceErrorEvent(tenant_id=tenant_id, error=exc))
            raise

        icon = response.get("largeIcon") if isinstance(response, dict) else None
        if not isinstance(icon, dict):
            return None
        encoded = icon.get("value")
        if not encoded:
            return None
        try:
            return base64.b64decode(encoded)
        except Exception:  # noqa: BLE001 - invalid/empty icon payload
            logger.debug("Failed to decode app icon payload", app_id=app_id)
            return None

    async def _fetch_icon_via_media_endpoint(
        self,
        app_id: str,
        *,
        size: str = "large",
        tenant_id: str | None = None,
        cancellation_token: CancellationToken | None = None,
    ) -> bytes | None:
        """Fetch an app icon via the legacy $value media endpoint."""

        request = mobile_app_icon_request(app_id, size=size)  # type: ignore[arg-type]
        try:
            return await self._client_factory.request_bytes(
                request.method,
                request.url,
                headers=request.headers,
                api_version=request.api_version,
                cancellation_token=cancellation_token,
            )
        except CancellationError:
            raise
        except GraphAPIError as exc:
            if getattr(exc, "status_code", None) in (404, 400):
                logger.debug(
                    "App icon not available via media endpoint",
                    app_id=app_id,
                    status=exc.status_code,
                )
                return None
            self.errors.emit(ServiceErrorEvent(tenant_id=tenant_id, error=exc))
            raise

    async def background_fetch_icons(
        self,
        apps: list[MobileApp],
        *,
        tenant_id: str | None = None,
        batch_size: int = 10,
        max_concurrent: int = 3,
        cancellation_token: CancellationToken | None = None,
    ) -> None:
        """Fetch icons in background for apps without cached icons.

        Args:
            apps: List of apps to fetch icons for
            tenant_id: Optional tenant ID for scoping
            batch_size: Number of apps to process in each batch
            max_concurrent: Maximum number of concurrent icon fetches
            cancellation_token: Optional cancellation token
        """
        import asyncio

        # Emit cached icons immediately so the UI can render without refetching
        apps_needing_icons: list[MobileApp] = []
        for app in apps:
            if not app.id:
                continue
            cached = self._attachments.get(f"{app.id}:large", tenant_id=tenant_id)
            if cached:
                self.icon_cached.emit(cached)
            else:
                apps_needing_icons.append(app)

        if not apps_needing_icons:
            logger.debug("All app icons already cached")
            return

        logger.info(
            "Starting background icon fetch",
            total_apps=len(apps),
            needs_icons=len(apps_needing_icons),
        )

        # Semaphore for rate limiting
        semaphore = asyncio.Semaphore(max_concurrent)

        async def fetch_with_limit(app: MobileApp) -> None:
            """Fetch icon with concurrency limit and error handling."""
            if cancellation_token:
                cancellation_token.raise_if_cancelled()

            async with semaphore:
                try:
                    await self.cache_icon(
                        app.id,
                        tenant_id=tenant_id,
                        force=False,
                        cancellation_token=cancellation_token,
                    )
                    # Rate limit: small delay between fetches
                    await asyncio.sleep(0.5)
                except CancellationError:
                    raise
                except Exception as exc:  # noqa: BLE001
                    # Silently log failures in background fetching
                    logger.debug(
                        "Background icon fetch failed", app_id=app.id, error=str(exc)
                    )

        # Process in batches
        for batch_start in range(0, len(apps_needing_icons), batch_size):
            if cancellation_token:
                cancellation_token.raise_if_cancelled()

            batch = apps_needing_icons[batch_start : batch_start + batch_size]
            await asyncio.gather(
                *[fetch_with_limit(app) for app in batch], return_exceptions=True
            )

        logger.info("Background icon fetch completed", fetched=len(apps_needing_icons))

    def _hydrate_missing_metadata(self, app: MobileApp) -> MobileApp:
        """Best-effort platform/type inference when Graph omits @odata.type."""

        if app.platform_type and app.platform_type is not MobileAppPlatform.UNKNOWN and app.app_type:
            return app

        inferred_platform: str | None = None
        inferred_type: str | None = None

        for url in (app.information_url, app.app_store_url):
            if not url:
                continue
            parsed = urlparse(url)
            host = parsed.netloc.lower()
            if "apps.apple.com" in host or "itunes.apple.com" in host:
                query = parse_qs(parsed.query)
                mt = ",".join(query.get("mt", []))
                if "12" in mt or "mac" in parsed.path.lower():
                    inferred_platform = "macOS"
                elif not inferred_platform:
                    inferred_platform = "ios"
                if inferred_platform == "macOS":
                    inferred_type = inferred_type or "Store"

            if "microsoft.com" in host and "store" in parsed.path.lower():
                inferred_platform = inferred_platform or "windows"
                inferred_type = inferred_type or "Store"

        updates: dict[str, Any] = {}
        if inferred_platform and app.platform_type in (None, MobileAppPlatform.UNKNOWN):
            updates["platform_type"] = inferred_platform
        if inferred_type and not app.app_type:
            updates["app_type"] = inferred_type

        if (
            "platform_type" not in updates
            and app.platform_type in (None, MobileAppPlatform.UNKNOWN)
            and app.app_type
        ):
            compatible_platforms = PLATFORM_TYPE_COMPATIBILITY.get(app.app_type)
            if isinstance(compatible_platforms, list) and len(compatible_platforms) == 1:
                updates["platform_type"] = compatible_platforms[0]

        return app.model_copy(update=updates) if updates else app


__all__ = ["ApplicationService", "InstallSummaryEvent"]
