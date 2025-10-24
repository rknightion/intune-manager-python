from __future__ import annotations

from tests.graph.mocks import GraphMockRepository
from tests.graph.schemas import load_default_registry
from tests.graph.schemas.utils import is_intune_path

KNOWN_SCHEMA_GAPS = {
    (
        "beta",
        "GET",
        "deviceManagement/virtualEndpoint/provisioningPolicies/*/retrievePolicyApplyActionResult",
    ),
    (
        "beta",
        "GET",
        "deviceManagement/virtualEndpoint/provisioningPolicies/*/retrievePolicyApplySchedule",
    ),
    (
        "beta",
        "GET",
        "deviceManagement/virtualEndpoint/cloudPCs/*/retrieveCloudPcRemoteActionResults",
    ),
    (
        "beta",
        "GET",
        "deviceManagement/virtualEndpoint/cloudPCs/*/getSupportedCloudPcRemoteActions",
    ),
    (
        "beta",
        "GET",
        "deviceManagement/virtualEndpoint/cloudPCs/*/getFrontlineCloudPcAccessState",
    ),
    (
        "beta",
        "GET",
        "deviceManagement/virtualEndpoint/cloudPCs/*/getCloudPcConnectivityHistory",
    ),
    ("beta", "GET", "deviceManagement/virtualEndpoint/retrieveScopedPermissions"),
    ("beta", "GET", "deviceManagement/virtualEndpoint/usersettings/*"),
    (
        "beta",
        "GET",
        "deviceManagement/virtualEndpoint/auditEvents/getAuditActivityTypes",
    ),
    ("beta", "GET", "deviceManagement/virtualEndpoint/cloudPCs/*/retrieveReviewStatus"),
    ("beta", "GET", "deviceManagement/monitoring/alertRecords/getPortalNotifications"),
    ("beta", "GET", "deviceManagement/managedDevices/*/getCloudPcRemoteActionResults"),
    ("beta", "GET", "deviceManagement/virtualEndpoint/cloudPCs/*/retrieveSnapshots"),
    ("beta", "GET", "deviceManagement/virtualEndpoint/deviceImages/getSourceImages"),
    ("beta", "GET", "deviceManagement/virtualEndpoint/snapshots/getSubscriptions"),
    ("beta", "GET", "deviceManagement/managedDevices/*/getCloudPcReviewStatus"),
    ("beta", "GET", "deviceManagement/virtualEndpoint/getEffectivePermissions"),
    (
        "v1.0",
        "GET",
        "deviceManagement/applePushNotificationCertificate/downloadApplePushNotificationCertificateSigningRequest",
    ),
    (
        "v1.0",
        "GET",
        "deviceManagement/detectedApps/*/managedDevices/*/windowsProtectionState/detectedMalwareState/*",
    ),
    (
        "v1.0",
        "GET",
        "deviceManagement/detectedApps/*/managedDevices/*/windowsProtectionState/detectedMalwareState",
    ),
    (
        "v1.0",
        "GET",
        "deviceAppManagement/managedAppRegistrations/getUserIdsWithFlaggedAppRegistration",
    ),
    (
        "v1.0",
        "GET",
        "deviceManagement/detectedApps/*/managedDevices/*/windowsProtectionState",
    ),
    (
        "v1.0",
        "GET",
        "deviceManagement/virtualEndpoint/auditEvents/getAuditActivityTypes",
    ),
    ("v1.0", "GET", "deviceManagement/detectedApps/*/managedDevices/*/deviceCategory"),
    ("v1.0", "GET", "deviceManagement/virtualEndpoint/deviceImages/getSourceImages"),
    ("v1.0", "GET", "deviceManagement/detectedApps/*/managedDevices/*/users/*"),
    ("v1.0", "GET", "deviceAppManagement/enterpriseCodeSigningCertificates/*"),
    ("v1.0", "GET", "deviceManagement/detectedApps/*/managedDevices/*/users"),
    ("v1.0", "GET", "deviceAppManagement/enterpriseCodeSigningCertificates"),
    ("v1.0", "GET", "deviceManagement/telecomExpenseManagementPartners/*"),
    ("v1.0", "GET", "deviceAppManagement/mobileApps/*/contentVersions/*"),
    ("v1.0", "GET", "deviceManagement/telecomExpenseManagementPartners"),
    ("v1.0", "GET", "deviceAppManagement/mobileApps/*/contentVersions"),
    ("v1.0", "GET", "deviceManagement/auditEvents/getAuditCategories"),
    ("v1.0", "GET", "deviceManagement/getEffectivePermissions"),
    (
        "v1.0",
        "DELETE",
        "deviceManagement/detectedApps/*/managedDevices/*/windowsProtectionState/detectedMalwareState/*",
    ),
    ("v1.0", "DELETE", "deviceManagement/detectedApps/*/managedDevices/*/users/*"),
    ("v1.0", "DELETE", "deviceAppManagement/enterpriseCodeSigningCertificates/*"),
    ("v1.0", "DELETE", "deviceManagement/telecomExpenseManagementPartners/*"),
    ("v1.0", "DELETE", "deviceAppManagement/mobileApps/*/contentVersions/*"),
    (
        "beta",
        "POST",
        "deviceManagement/monitoring/alertRecords/changeAlertRecordsPortalNotificationAsSent",
    ),
    (
        "beta",
        "POST",
        "deviceManagement/virtualEndpoint/reports/retrievecrossregiondisasterrecoveryreport",
    ),
    (
        "beta",
        "POST",
        "deviceManagement/virtualEndpoint/onPremisesConnections/*/UpdateAdDomainPassword",
    ),
    (
        "beta",
        "POST",
        "deviceManagement/virtualEndpoint/crossCloudGovernmentOrganizationMapping",
    ),
    (
        "beta",
        "POST",
        "deviceManagement/virtualEndpoint/reports/getSharedUseLicenseUsageReport",
    ),
    (
        "beta",
        "POST",
        "deviceManagement/monitoring/alertRecords/*/setPortalNotificationAsSent",
    ),
    ("beta", "POST", "deviceManagement/managedDevices/bulkSetCloudPcReviewStatus"),
    ("beta", "POST", "deviceManagement/managedDevices/*/setCloudPcReviewStatus"),
    ("beta", "POST", "deviceManagement/managedDevices/bulkReprovisionCloudPc"),
    ("beta", "POST", "deviceManagement/virtualEndpoint/cloudPCs/bulkResize"),
    ("beta", "POST", "deviceManagement/virtualEndpoint/cloudPCs/*/poweroff"),
    ("beta", "POST", "deviceManagement/virtualEndpoint/cloudPCs/*/poweron"),
    ("beta", "POST", "deviceManagement/virtualEndpoint/bulkAction/*/retry"),
    ("beta", "POST", "deviceManagement/managedDevices/bulkRestoreCloudPc"),
    (
        "v1.0",
        "POST",
        "deviceManagement/detectedApps/*/managedDevices/*/windowsProtectionState/detectedMalwareState",
    ),
    (
        "v1.0",
        "POST",
        "deviceManagement/detectedApps/*/managedDevices/*/users/*/removeAllDevicesFromManagement",
    ),
    ("v1.0", "POST", "deviceManagement/detectedApps/*/managedDevices/*/users"),
    ("v1.0", "POST", "deviceAppManagement/enterpriseCodeSigningCertificates"),
    ("v1.0", "POST", "deviceManagement/telecomExpenseManagementPartners"),
    ("v1.0", "POST", "deviceAppManagement/managedAppPolicies/*/assign"),
    (
        "v1.0",
        "PATCH",
        "deviceManagement/detectedApps/*/managedDevices/*/windowsProtectionState/detectedMalwareState/*",
    ),
    (
        "v1.0",
        "PATCH",
        "deviceManagement/detectedApps/*/managedDevices/*/windowsProtectionState",
    ),
    (
        "v1.0",
        "PATCH",
        "deviceManagement/detectedApps/*/managedDevices/*/deviceCategory",
    ),
    ("v1.0", "PATCH", "deviceManagement/detectedApps/*/managedDevices/*/users/*"),
    ("v1.0", "PATCH", "deviceAppManagement/enterpriseCodeSigningCertificates/*"),
    ("v1.0", "PATCH", "deviceManagement/telecomExpenseManagementPartners/*"),
    ("v1.0", "PATCH", "deviceAppManagement/mobileApps/*/contentVersions/*"),
    ("v1.0", "PATCH", "deviceManagement/softwareUpdateStatusSummary"),
}


def test_graph_mocks_align_with_openapi(
    graph_mock_repository: GraphMockRepository,
) -> None:
    registry = load_default_registry()
    missing: list[tuple[str, str, str]] = []

    for mock in graph_mock_repository.iter():
        if mock.version not in {"beta", "v1.0"}:
            continue
        path_key = mock.normalised_path()
        if not path_key or not is_intune_path(path_key):
            continue
        method = mock.method.upper()
        key = (mock.version, method, path_key)
        if key in KNOWN_SCHEMA_GAPS:
            continue
        if not registry.has_operation(mock.version, method, mock.pattern):
            missing.append((mock.version, method, mock.normalised_path()))
    assert not missing, (
        "The following mocks are missing from the canonical OpenAPI metadata; "
        "update mock dataset or OpenAPI schemas:\n"
        + "\n".join(f"{version} {method} {path}" for version, method, path in missing)
    )
