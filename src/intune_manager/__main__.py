# nuitka-project-if: {OS} == "Darwin":
#    nuitka-project: --macos-app-icon={MAIN_DIRECTORY}/../../assets/icons/icon.icns
#    nuitka-project: --lto=auto
# nuitka-project-if: {OS} == "Windows":
#    nuitka-project: --windows-icon-from-ico={MAIN_DIRECTORY}/../../assets/icons/icon.ico
#    nuitka-project: --windows-console-mode=disable
#    nuitka-project: --product-name=IntuneManager
#    nuitka-project: --file-description="Microsoft Intune Manager"
#    nuitka-project: --company-name="IntuneManager"
#    nuitka-project: --windows-console-mode=attach
#    nuitka-project: --lto=no
# nuitka-project-if: {OS} == "Linux":
#    nuitka-project: --linux-icon={MAIN_DIRECTORY}/../../assets/icons/icon-256.png
#    nuitka-project: --static-libpython=yes
#    nuitka-project: --lto=auto
# nuitka-project: --mode=app
# nuitka-project: --nofollow-import-to=*.tests
# nuitka-project: --nofollow-import-to=pytest
# nuitka-project: --nofollow-import-to=mypy
# nuitka-project: --nofollow-import-to=ruff

# nuitka-project: --python-flag=-OO

# nuitka-project: --enable-plugin=pyside6

# Qt plugin configuration - minimal set for GUI app without networking
# Required plugins:
#   platforms: Essential for window creation
#   imageformats: Only PNG/ICO for app icons (no JPEG, SVG, etc.)
# Note: 'styles' plugin excluded - Fusion style is built into QtWidgets on all platforms
# nuitka-project: --include-qt-plugins=platforms,imageformats

# nuitka-project: --output-filename=IntuneManager
# nuitka-project: --jobs=4
"""
Entry point for running intune_manager as a module.

This file enables:
- `python -m intune_manager`
- `uv run python -m intune_manager`
- Nuitka compilation with `nuitka src/intune_manager`
"""

from __future__ import annotations

from intune_manager import main

if __name__ == "__main__":
    main()
