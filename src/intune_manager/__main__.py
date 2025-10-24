# nuitka-project-if: {OS} == "Darwin":
#    nuitka-project: --macos-app-name=IntuneManager
#    nuitka-project: --macos-app-version={VERSION}
#    nuitka-project: --include-module=keyring.backends.macOS
# nuitka-project-if: {OS} == "Windows":
#    nuitka-project: --include-module=keyring.backends.Windows
#    nuitka-project: --windows-console-mode=disable
#    nuitka-project: --product-name=IntuneManager
#    nuitka-project: --product-version={VERSION}
#    nuitka-project: --file-description="Microsoft Intune Manager"
#    nuitka-project: --company-name="IntuneManager"
#    nuitka-project: --windows-uac-admin
#    nuitka-project: --onefile
#    nuitka-project: --console=disabled
# nuitka-project-if: {OS} == "Linux":
#    nuitka-project: --include-module=keyring.backends.SecretService
#    nuitka-project: --include-module=secretstorage
#    nuitka-project: --onefile
# nuitka-project: --mode=app
# nuitka-project: --nofollow-import-to=*.tests
# nuitka-project: --nofollow-import-to=pytest
# nuitka-project: --nofollow-import-to=mypy
# nuitka-project: --nofollow-import-to=ruff
# nuitka-project: --enable-plugin=pyside6
# nuitka-project: --include-qt-plugins=sensible
# nuitka-project: --lto=auto

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
