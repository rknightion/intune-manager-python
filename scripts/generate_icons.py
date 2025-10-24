#!/usr/bin/env python3
"""
Generate platform-specific app icons from source PNG.

This script creates:
- macOS: .icns file with all required sizes (16-1024, with @2x retina)
- Windows: .ico file with multiple embedded sizes
- Linux: PNG files at standard freedesktop.org sizes

Usage:
    python scripts/generate_icons.py [--source path/to/icon.png]
"""

from __future__ import annotations

import argparse
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    print("Error: Pillow is required. Install with: pip install Pillow")
    sys.exit(1)


# Icon sizes for each platform
MACOS_SIZES = [
    ("icon_16x16.png", 16),
    ("[email protected]", 32),
    ("icon_32x32.png", 32),
    ("[email protected]", 64),
    ("icon_128x128.png", 128),
    ("[email protected]", 256),
    ("icon_256x256.png", 256),
    ("[email protected]", 512),
    ("icon_512x512.png", 512),
    ("[email protected]", 1024),
]

WINDOWS_SIZES = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]

LINUX_SIZES = [16, 32, 48, 64, 128, 256, 512]


def get_paths() -> tuple[Path, Path, Path]:
    """Get source icon path and output directory."""
    script_dir = Path(__file__).parent
    repo_root = script_dir.parent
    source = repo_root / "icon.png"
    output_dir = repo_root / "assets" / "icons"
    return source, output_dir, repo_root


def validate_source(source: Path) -> None:
    """Validate source icon exists and is suitable."""
    if not source.exists():
        print(f"Error: Source icon not found at {source}")
        sys.exit(1)

    try:
        img = Image.open(source)
        width, height = img.size
        if width < 512 or height < 512:
            print(
                f"Warning: Source icon is {width}x{height}. Recommend at least 512x512 for best quality."
            )
        if width != height:
            print(f"Warning: Source icon is not square ({width}x{height})")
        print(f"✓ Source icon: {width}x{height} {img.mode}")
    except Exception as e:
        print(f"Error: Could not open source icon: {e}")
        sys.exit(1)


def generate_macos_icns(source: Path, output_dir: Path) -> bool:
    """Generate macOS .icns file using sips and iconutil."""
    system = platform.system()

    # Check for required tools
    if not shutil.which("sips"):
        print("⚠ sips not available (macOS only). Skipping .icns generation.")
        return False
    if not shutil.which("iconutil"):
        print("⚠ iconutil not available (macOS only). Skipping .icns generation.")
        return False

    print("\n📱 Generating macOS .icns file...")

    # Create temporary iconset directory
    with tempfile.TemporaryDirectory() as tmpdir:
        iconset_dir = Path(tmpdir) / "icon.iconset"
        iconset_dir.mkdir()

        # Generate all required sizes using sips
        for filename, size in MACOS_SIZES:
            output_path = iconset_dir / filename
            try:
                subprocess.run(
                    [
                        "sips",
                        "-z",
                        str(size),
                        str(size),
                        str(source),
                        "--out",
                        str(output_path),
                    ],
                    check=True,
                    capture_output=True,
                )
                print(f"  ✓ {filename} ({size}x{size})")
            except subprocess.CalledProcessError as e:
                print(f"  ✗ Failed to generate {filename}: {e}")
                return False

        # Convert iconset to .icns
        output_icns = output_dir / "icon.icns"
        try:
            subprocess.run(
                ["iconutil", "-c", "icns", str(iconset_dir), "-o", str(output_icns)],
                check=True,
                capture_output=True,
            )
            print(f"\n✓ Created {output_icns}")
            return True
        except subprocess.CalledProcessError as e:
            print(f"✗ Failed to create .icns: {e}")
            return False


def generate_windows_ico(source: Path, output_dir: Path) -> bool:
    """Generate Windows .ico file with multiple sizes using Pillow."""
    print("\n🪟 Generating Windows .ico file...")

    try:
        img = Image.open(source)
        # Convert to RGBA to preserve transparency
        if img.mode != "RGBA":
            img = img.convert("RGBA")

        output_ico = output_dir / "icon.ico"
        img.save(str(output_ico), format="ICO", sizes=WINDOWS_SIZES)

        print(f"✓ Created {output_ico}")
        print(f"  Embedded sizes: {', '.join(f'{w}x{h}' for w, h in WINDOWS_SIZES)}")
        return True
    except Exception as e:
        print(f"✗ Failed to create .ico: {e}")
        return False


def generate_linux_pngs(source: Path, output_dir: Path) -> bool:
    """Generate Linux PNG files at standard sizes using Pillow."""
    print("\n🐧 Generating Linux PNG files...")

    try:
        img = Image.open(source)
        # Convert to RGBA to preserve transparency
        if img.mode != "RGBA":
            img = img.convert("RGBA")

        success_count = 0
        for size in LINUX_SIZES:
            output_png = output_dir / f"icon-{size}.png"
            resized = img.resize((size, size), Image.Resampling.LANCZOS)
            resized.save(str(output_png), format="PNG", optimize=True)
            print(f"  ✓ icon-{size}.png ({size}x{size})")
            success_count += 1

        # Also copy the 1024px original for reference
        output_1024 = output_dir / "icon-1024.png"
        shutil.copy2(source, output_1024)
        print("  ✓ icon-1024.png (original)")

        print(f"\n✓ Created {success_count + 1} Linux PNG files")
        return True
    except Exception as e:
        print(f"✗ Failed to create Linux PNGs: {e}")
        return False


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Generate platform-specific app icons from source PNG"
    )
    parser.add_argument(
        "--source",
        type=Path,
        help="Path to source icon (default: icon.png in repo root)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output directory (default: assets/icons/)",
    )
    args = parser.parse_args()

    # Get paths
    source, output_dir, repo_root = get_paths()
    if args.source:
        source = args.source
    if args.output:
        output_dir = args.output

    print("=" * 60)
    print("App Icon Generator")
    print("=" * 60)
    print(f"Source: {source}")
    print(f"Output: {output_dir}")
    print(f"Platform: {platform.system()}")
    print("=" * 60)

    # Validate source
    validate_source(source)

    # Ensure output directory exists
    output_dir.mkdir(parents=True, exist_ok=True)

    # Generate platform-specific icons
    results = {
        "macOS": generate_macos_icns(source, output_dir),
        "Windows": generate_windows_ico(source, output_dir),
        "Linux": generate_linux_pngs(source, output_dir),
    }

    # Summary
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    for platform_name, success in results.items():
        status = "✓" if success else "⚠"
        print(f"{status} {platform_name}: {'Success' if success else 'Skipped/Failed'}")

    # Return 0 if at least one platform succeeded
    if any(results.values()):
        print("\n✓ Icon generation completed successfully!")
        return 0
    else:
        print("\n✗ Icon generation failed for all platforms!")
        return 1


if __name__ == "__main__":
    sys.exit(main())
