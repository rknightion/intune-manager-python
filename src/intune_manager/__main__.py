# nuitka-project-if: {OS} == "Darwin":
#    nuitka-project: --macos-app-icon={MAIN_DIRECTORY}/../../assets/icons/icon.icns
#    nuitka-project: --include-module=keyring.backends.macOS
#    nuitka-project: --include-module=keyring.backends.macOS.api
#    nuitka-project: --nofollow-import-to=keyring.backends.Windows
#    nuitka-project: --nofollow-import-to=keyring.backends.SecretService
#    nuitka-project: --nofollow-import-to=keyring.backends.kwallet
#    nuitka-project: --nofollow-import-to=keyring.backends.libsecret
#    nuitka-project: --nofollow-import-to=keyring.backends.null
#    nuitka-project: --nofollow-import-to=keyring.backends.chainer
#    nuitka-project: --nofollow-import-to=keyring.backends.fail
#    nuitka-project: --static-libpython=yes
#    nuitka-project: --lto=auto
# nuitka-project-if: {OS} == "Windows":
#    nuitka-project: --windows-icon-from-ico={MAIN_DIRECTORY}/../../assets/icons/icon.ico
#    nuitka-project: --include-module=keyring.backends.Windows
#    # Keyring on Windows prefers pywin32-ctypes; pull in the bits it imports.
#    nuitka-project: --include-module=win32ctypes.pywin32
#    nuitka-project: --include-module=win32ctypes.pywin32.win32cred
#    nuitka-project: --include-module=win32ctypes.pywin32.pywintypes
#    # Trim other backends:
#    nuitka-project: --nofollow-import-to=keyring.backends.macOS
#    nuitka-project: --nofollow-import-to=keyring.backends.SecretService
#    nuitka-project: --nofollow-import-to=keyring.backends.kwallet
#    nuitka-project: --nofollow-import-to=keyring.backends.libsecret
#    nuitka-project: --nofollow-import-to=keyring.backends.null
#    nuitka-project: --nofollow-import-to=keyring.backends.chainer
#    nuitka-project: --nofollow-import-to=keyring.backends.fail
#    nuitka-project: --windows-console-mode=disable
#    nuitka-project: --product-name=IntuneManager
#    nuitka-project: --file-description="Microsoft Intune Manager"
#    nuitka-project: --company-name="IntuneManager"
#    nuitka-project: --windows-console-mode=attach
#    nuitka-project: --lto=no
# nuitka-project-if: {OS} == "Linux":
#    nuitka-project: --linux-icon={MAIN_DIRECTORY}/../../assets/icons/icon-256.png
#    nuitka-project: --include-module=keyring.backends.SecretService
#    nuitka-project: --include-module=secretstorage
#    # Trim other backends:
#    nuitka-project: --nofollow-import-to=keyring.backends.Windows
#    nuitka-project: --nofollow-import-to=keyring.backends.macOS
#    nuitka-project: --nofollow-import-to=keyring.backends.kwallet
#    nuitka-project: --nofollow-import-to=keyring.backends.null
#    nuitka-project: --nofollow-import-to=keyring.backends.chainer
#    nuitka-project: --nofollow-import-to=keyring.backends.fail
#    nuitka-project: --static-libpython=yes
#    nuitka-project: --lto=auto
# nuitka-project: --mode=app
# nuitka-project: --nofollow-import-to=*.tests
# nuitka-project: --nofollow-import-to=pytest
# nuitka-project: --nofollow-import-to=mypy
# nuitka-project: --nofollow-import-to=ruff
# nuitka-project: --nofollow-import-to=sqlalchemy.dialects.oracle
# nuitka-project: --nofollow-import-to=sqlalchemy.dialects.mysql
# nuitka-project: --nofollow-import-to=sqlalchemy.dialects.postgresql
# nuitka-project: --nofollow-import-to=sqlalchemy.dialects.mssql
# nuitka-project: --nofollow-import-to=sqlalchemy.dialects.firebird
# nuitka-project: --nofollow-import-to=sqlalchemy.dialects.sybase
# nuitka-project: --nofollow-import-to=pymysql
# nuitka-project: --nofollow-import-to=MySQLdb
# nuitka-project: --nofollow-import-to=psycopg2
# nuitka-project: --nofollow-import-to=psycopg
# nuitka-project: --nofollow-import-to=pg8000
# nuitka-project: --nofollow-import-to=asyncpg
# nuitka-project: --nofollow-import-to=aiomysql
# nuitka-project: --nofollow-import-to=oracledb
# nuitka-project: --nofollow-import-to=cx_Oracle
# nuitka-project: --nofollow-import-to=pymssql
# nuitka-project: --nofollow-import-to=sqlalchemy.ext.automap
# nuitka-project: --nofollow-import-to=sqlalchemy.ext.baked
# nuitka-project: --nofollow-import-to=sqlalchemy.ext.horizontal_shard
# nuitka-project: --nofollow-import-to=sqlalchemy.ext.indexable
# nuitka-project: --nofollow-import-to=sqlalchemy.ext.instrumentation
# nuitka-project: --nofollow-import-to=sqlalchemy.ext.mypy
# nuitka-project: --nofollow-import-to=sqlalchemy.ext.orderinglist
# nuitka-project: --nofollow-import-to=sqlalchemy.ext.serializer


# httpx transports we don't use
# nuitka-project: --nofollow-import-to=httpx._transports.asgi
# nuitka-project: --nofollow-import-to=httpx._transports.wsgi

# httpcore backends we don't use
# nuitka-project: --nofollow-import-to=httpcore._backends.trio
# nuitka-project: --nofollow-import-to=cryptography.hazmat.decrepit
# nuitka-project: --nofollow-import-to=cryptography.hazmat.backends.openssl.dh
# nuitka-project: --nofollow-import-to=cryptography.hazmat.backends.openssl.dsa
# nuitka-project: --nofollow-import-to=cryptography.hazmat.backends.openssl.x25519
# nuitka-project: --nofollow-import-to=cryptography.hazmat.backends.openssl.x448
# nuitka-project: --nofollow-import-to=cryptography.hazmat.backends.openssl.ed25519
# nuitka-project: --nofollow-import-to=cryptography.hazmat.backends.openssl.ed448
# nuitka-project: --nofollow-import-to=cryptography.hazmat.backends.openssl.poly1305
# nuitka-project: --nofollow-import-to=cryptography.hazmat.primitives.kdf
# nuitka-project: --nofollow-import-to=cryptography.hazmat.primitives.twofactor
# nuitka-project: --nofollow-import-to=cryptography.hazmat.primitives.poly1305
# nuitka-project: --nofollow-import-to=cryptography.hazmat.primitives.keywrap
# nuitka-project: --nofollow-import-to=cryptography.hazmat.primitives.serialization.pkcs7
# nuitka-project: --nofollow-import-to=cryptography.hazmat.primitives.serialization.pkcs12
# nuitka-project: --nofollow-import-to=cryptography.hazmat.primitives.serialization.ssh
# nuitka-project: --nofollow-import-to=cryptography.fernet

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
