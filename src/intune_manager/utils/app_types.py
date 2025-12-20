"""App type utilities for Microsoft Graph mobile app types.

This module provides utilities for parsing and categorizing mobile app types
from Microsoft Graph API @odata.type values.
"""

from __future__ import annotations


# Mapping from @odata.type suffix to simplified app type name
APP_TYPE_MAPPING = {
    # iOS
    "iosStoreApp": "Store",
    "iosLobApp": "LOB",
    "iosVppApp": "VPP",
    "managedIOSLobApp": "Managed LOB",
    "managedIOSStoreApp": "Managed Store",
    "managedIOSUniversalApp": "Managed Store",
    # Android
    "androidStoreApp": "Store",
    "androidLobApp": "LOB",
    "androidManagedStoreApp": "Managed Store",
    "managedAndroidStoreApp": "Managed Store",
    "androidForWorkApp": "For Work",
    "managedAndroidLobApp": "Managed LOB",
    "androidManagedStoreWebApp": "Web",
    # macOS
    "macOSLobApp": "LOB",
    "macOSDmgApp": "DMG",
    "macOSPkgApp": "PKG",
    "macOsVppApp": "VPP",
    "macOSOfficeSuiteApp": "Office Suite",
    "macOSMicrosoftDefenderApp": "Defender",
    "macOSMicrosoftEdgeApp": "Edge",
    # Windows
    "win32LobApp": "LOB",
    "windowsAppX": "AppX",
    "winGetApp": "WinGet",
    "windowsMobileMSI": "MSI",
    "windowsUniversalAppX": "Universal AppX",
    "windowsWebApp": "Web",
    "windowsStoreApp": "Store",
    "microsoftStoreForBusinessApp": "Store for Business",
    "officeSuiteApp": "Office Suite",
    "windowsPhone81AppX": "AppX",
    "windowsPhone81StoreApp": "Store",
    "windowsPhone81XAP": "AppX",
    # Cross-platform
    "webApp": "Web",
    "managedMobileLobApp": "Managed LOB",
}

_APP_TYPE_MAPPING_LOWER = {
    key.lower(): value for key, value in APP_TYPE_MAPPING.items()
}

# Platform compatibility: which app types are valid for which platforms
# Key: app type, Value: list of compatible platforms
PLATFORM_TYPE_COMPATIBILITY: dict[str, list[str]] = {
    "Store": ["ios", "android", "windows"],
    "LOB": ["ios", "android", "macos", "windows"],
    "VPP": ["ios", "macos"],
    "Managed LOB": ["ios", "android"],
    "Managed Store": ["ios", "android"],
    "For Work": ["android"],
    "Web": ["ios", "android", "macos", "windows", "unknown"],
    "DMG": ["macos"],
    "PKG": ["macos"],
    "Office Suite": ["macos", "windows"],
    "Defender": ["macos"],
    "Edge": ["macos", "windows"],
    "WinGet": ["windows"],
    "MSI": ["windows"],
    "AppX": ["windows"],
    "Universal AppX": ["windows"],
    "Store for Business": ["windows"],
}


def extract_app_type(odata_type: str | None) -> str | None:
    """Extract simplified app type from Graph API @odata.type value.

    Args:
        odata_type: The @odata.type value from Graph API
                   (e.g., "#microsoft.graph.iosStoreApp")

    Returns:
        Simplified app type name (e.g., "Store") or None if not recognized

    Examples:
        >>> extract_app_type("#microsoft.graph.iosStoreApp")
        "Store"
        >>> extract_app_type("#microsoft.graph.win32LobApp")
        "LOB"
        >>> extract_app_type("#microsoft.graph.iosVppApp")
        "VPP"
    """
    if not odata_type or not isinstance(odata_type, str):
        return None

    # Remove the #microsoft.graph. prefix
    type_name = odata_type.replace("#microsoft.graph.", "")

    return APP_TYPE_MAPPING.get(type_name) or _APP_TYPE_MAPPING_LOWER.get(
        type_name.lower()
    )


def get_display_name(platform: str | None, app_type: str | None) -> str:
    """Get user-friendly display name for platform + type combination.

    Args:
        platform: Platform name (e.g., "ios", "windows", "macos", "android")
        app_type: App type name (e.g., "Store", "LOB", "VPP")

    Returns:
        Combined display name (e.g., "iOS - Store", "Windows - LOB")
        If either value is None, returns just the available part

    Examples:
        >>> get_display_name("ios", "Store")
        "iOS - Store"
        >>> get_display_name("windows", "LOB")
        "Windows - LOB"
        >>> get_display_name("macos", None)
        "macOS"
        >>> get_display_name(None, "VPP")
        "VPP"
    """
    if not platform and not app_type:
        return "Unknown"

    if not platform:
        return app_type or "Unknown"

    if not app_type:
        # Capitalize platform name properly
        platform_display = {
            "ios": "iOS",
            "macos": "macOS",
            "windows": "Windows",
            "android": "Android",
            "unknown": "Unknown",
        }.get(platform.lower(), platform.title())
        return platform_display

    # Capitalize platform name properly
    platform_display = {
        "ios": "iOS",
        "macos": "macOS",
        "windows": "Windows",
        "android": "Android",
        "unknown": "Unknown",
    }.get(platform.lower(), platform.title())

    return f"{platform_display} - {app_type}"


def is_compatible(platform: str | None, app_type: str | None) -> bool:
    """Check if a platform and app type combination is valid.

    Args:
        platform: Platform name (e.g., "ios", "windows")
        app_type: App type name (e.g., "Store", "VPP")

    Returns:
        True if the combination is valid, False if incompatible,
        True if either value is None (no filter applied)

    Examples:
        >>> is_compatible("ios", "VPP")
        True
        >>> is_compatible("windows", "VPP")
        False
        >>> is_compatible("ios", "Store")
        True
        >>> is_compatible(None, "VPP")
        True
    """
    # If no filters applied, everything is compatible
    if not platform or not app_type:
        return True

    # Check compatibility mapping
    compatible_platforms = PLATFORM_TYPE_COMPATIBILITY.get(app_type, [])
    return platform.lower() in compatible_platforms


def get_all_platform_type_combinations() -> list[tuple[str, str]]:
    """Get all valid platform + type combinations.

    Returns:
        List of (platform, app_type) tuples for all valid combinations

    Examples:
        >>> combos = get_all_platform_type_combinations()
        >>> ("ios", "Store") in combos
        True
        >>> ("windows", "VPP") in combos
        False
    """
    combinations = []
    for app_type, platforms in PLATFORM_TYPE_COMPATIBILITY.items():
        for platform in platforms:
            combinations.append((platform, app_type))
    return combinations
