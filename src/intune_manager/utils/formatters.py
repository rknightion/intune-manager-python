"""Formatting utilities for displaying app metadata and statistics."""

from __future__ import annotations


def format_file_size(bytes_value: int | None) -> str:
    """Convert bytes to human-readable format (KB, MB, GB).

    Args:
        bytes_value: File size in bytes

    Returns:
        Formatted string like "125.4 MB" or "—" if None

    Examples:
        >>> format_file_size(1024)
        "1.0 KB"
        >>> format_file_size(1048576)
        "1.0 MB"
        >>> format_file_size(None)
        "—"
    """
    if bytes_value is None or bytes_value == 0:
        return "—"

    # Define units
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(bytes_value)
    unit_index = 0

    # Convert to appropriate unit
    while size >= 1024.0 and unit_index < len(units) - 1:
        size /= 1024.0
        unit_index += 1

    # Format with 1 decimal place, except for bytes
    if unit_index == 0:
        return f"{int(size)} {units[unit_index]}"
    return f"{size:.1f} {units[unit_index]}"


def format_license_count(used: int | None, total: int | None) -> str:
    """Format license usage as 'X / Y (Z%)' or '—'.

    Args:
        used: Number of licenses in use
        total: Total number of licenses

    Returns:
        Formatted string like "45 / 100 (45%)" or "—" if data missing

    Examples:
        >>> format_license_count(45, 100)
        "45 / 100 (45%)"
        >>> format_license_count(0, 50)
        "0 / 50 (0%)"
        >>> format_license_count(None, None)
        "—"
    """
    if used is None or total is None:
        return "—"

    if total == 0:
        return f"{used} / {total}"

    percentage = int((used / total) * 100)
    return f"{used} / {total} ({percentage}%)"


def format_architecture(arch_value: str | None) -> str:
    """Convert architecture enum to display text.

    Args:
        arch_value: Architecture value from Graph API (e.g., "x86,x64,arm")

    Returns:
        Formatted architecture string or "—" if None

    Examples:
        >>> format_architecture("x86,x64,arm")
        "x86, x64, ARM"
        >>> format_architecture("neutral")
        "Any"
        >>> format_architecture(None)
        "—"
    """
    if not arch_value:
        return "—"

    # Handle special cases
    if arch_value.lower() == "neutral" or arch_value.lower() == "none":
        return "Any"

    # Split and capitalize
    archs = [arch.strip() for arch in arch_value.split(",")]
    # Uppercase known architecture names
    formatted = []
    for arch in archs:
        arch_lower = arch.lower()
        if arch_lower in ("x86", "x64", "arm", "arm64"):
            formatted.append(arch.upper())
        else:
            formatted.append(arch.capitalize())

    return ", ".join(formatted)


def format_min_os(os_dict: dict[str, bool | str] | None) -> str:
    """Extract minimum OS version from complex object.

    The Graph API returns minimumSupportedOperatingSystem as a complex object
    with boolean flags for each OS version. This extracts the minimum version.

    Args:
        os_dict: Dictionary with OS version flags from Graph API

    Returns:
        Formatted minimum OS string or "—" if None

    Examples:
        >>> format_min_os({"v10_0": True, "v10_1903": True})
        "Windows 10 v1903"
        >>> format_min_os({"v8_0": True})
        "Android 8.0"
        >>> format_min_os(None)
        "—"
    """
    if not os_dict:
        return "—"

    # Try to extract the highest/latest version from the dict
    # Windows format: v10_0, v10_1507, v10_1903, etc.
    # Android format: v4_0, v8_0, etc.
    # iOS format: v8_0, v10_0, etc.

    versions = []
    for key, value in os_dict.items():
        if value is True and key.startswith("v"):
            # Extract version string
            version_str = key[1:].replace("_", ".")
            versions.append(version_str)

    if not versions:
        return "—"

    # Return the last (highest) version
    # Sort to get the latest version
    versions.sort()
    latest_version = versions[-1]

    # Try to format nicely based on detected platform
    if any(key.startswith("v10_") for key in os_dict.keys()):
        return f"Windows 10 v{latest_version}"
    elif any(key.startswith("v11_") for key in os_dict.keys()):
        return f"Windows 11 v{latest_version}"
    else:
        # Generic format for iOS/Android
        return f"v{latest_version}"


__all__ = [
    "format_file_size",
    "format_license_count",
    "format_architecture",
    "format_min_os",
]
