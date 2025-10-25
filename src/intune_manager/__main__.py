# nuitka-project-if: {OS} == "Darwin":
#    nuitka-project: --macos-app-icon={MAIN_DIRECTORY}/../../assets/icons/icon.icns
#    nuitka-project: --lto=auto
#    nuitka-project: --include-module=keyring.backends.macOS
# nuitka-project-if: {OS} == "Linux":
#    nuitka-project: --linux-icon={MAIN_DIRECTORY}/../../assets/icons/icon-256.png
#    nuitka-project: --static-libpython=yes
#    nuitka-project: --lto=auto
#    nuitka-project: --include-module=keyring.backends.SecretService
#    nuitka-project: --include-module=secretstorage
# nuitka-project: --mode=app

# Generate compilation report for debugging dependency issues
# nuitka-project: --report=compilation-report.xml

# nuitka-project: --nofollow-import-to=sqlalchemy.dialects.oracle
# nuitka-project: --nofollow-import-to=sqlalchemy.dialects.postgresql
# nuitka-project: --nofollow-import-to=sqlalchemy.dialects.mysql
# nuitka-project: --nofollow-import-to=sqlalchemy.dialects.mssql

# Test frameworks - these are never needed in production
# nuitka-project: --nofollow-import-to=*.tests
# nuitka-project: --nofollow-import-to=pytest
# nuitka-project: --nofollow-import-to=mypy
# nuitka-project: --nofollow-import-to=ruff

# Development/documentation tools - safe to exclude
# nuitka-project: --nofollow-import-to=IPython
# nuitka-project: --nofollow-import-to=jupyter
# nuitka-project: --nofollow-import-to=notebook
# nuitka-project: --nofollow-import-to=sphinx

# nuitka-project: --python-flag=-OO

# nuitka-project: --enable-plugin=pyside6

# Qt plugin configuration - minimal set for GUI app without networking
# Required plugins:
#   platforms: Essential for window creation
#   imageformats: Only PNG/ICO for app icons (no JPEG, SVG, etc.)
# Note: 'styles' plugin excluded - Fusion style is built into QtWidgets on all platforms
# nuitka-project: --include-qt-plugins=sensible

# nuitka-project: --output-filename=IntuneManager

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
