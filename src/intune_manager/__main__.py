# nuitka-project-if: {OS} == "Darwin":
#    nuitka-project: --macos-app-icon={MAIN_DIRECTORY}/../../assets/icons/icon.icns
#    nuitka-project: --include-module=keyring.backends.macOS
#    nuitka-project: --static-libpython=yes
#    nuitka-project: --lto=auto
# nuitka-project-if: {OS} == "Windows":
#    nuitka-project: --windows-icon-from-ico={MAIN_DIRECTORY}/../../assets/icons/icon.ico
#    nuitka-project: --include-module=keyring.backends.Windows
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
# nuitka-project: --nofollow-import-to=sqlalchemy.connectors
# nuitka-project: --nofollow-import-to=pymysql
# nuitka-project: --nofollow-import-to=MySQLdb
# nuitka-project: --nofollow-import-to=psycopg2
# nuitka-project: --nofollow-import-to=psycopg
# nuitka-project: --nofollow-import-to=pg8000
# nuitka-project: --nofollow-import-to=asyncpg
# nuitka-project: --nofollow-import-to=aiomysql
# nuitka-project: --nofollow-import-to=asyncmy
# nuitka-project: --nofollow-import-to=aiosqlite
# nuitka-project: --nofollow-import-to=oracledb
# nuitka-project: --nofollow-import-to=cx_Oracle
# nuitka-project: --nofollow-import-to=pyodbc
# nuitka-project: --nofollow-import-to=pymssql

# PySide6 unused Qt modules (you only use QtCore, QtGui, QtWidgets, QtCharts)
# nuitka-project: --nofollow-import-to=PySide6.QtNetwork
# nuitka-project: --nofollow-import-to=PySide6.QtQml
# nuitka-project: --nofollow-import-to=PySide6.QtQuick
# nuitka-project: --nofollow-import-to=PySide6.QtQuickWidgets
# nuitka-project: --nofollow-import-to=PySide6.QtSql
# nuitka-project: --nofollow-import-to=PySide6.QtTest
# nuitka-project: --nofollow-import-to=PySide6.QtXml
# nuitka-project: --nofollow-import-to=PySide6.QtSvg
# nuitka-project: --nofollow-import-to=PySide6.QtSvgWidgets
# nuitka-project: --nofollow-import-to=PySide6.QtPrintSupport
# nuitka-project: --nofollow-import-to=PySide6.QtOpenGL
# nuitka-project: --nofollow-import-to=PySide6.QtOpenGLWidgets
# nuitka-project: --nofollow-import-to=PySide6.QtWebEngineCore
# nuitka-project: --nofollow-import-to=PySide6.QtWebEngineWidgets
# nuitka-project: --nofollow-import-to=PySide6.QtWebChannel
# nuitka-project: --nofollow-import-to=PySide6.Qt3DCore
# nuitka-project: --nofollow-import-to=PySide6.Qt3DRender
# nuitka-project: --nofollow-import-to=PySide6.Qt3DAnimation
# nuitka-project: --nofollow-import-to=PySide6.Qt3DExtras
# nuitka-project: --nofollow-import-to=PySide6.Qt3DInput
# nuitka-project: --nofollow-import-to=PySide6.Qt3DLogic
# nuitka-project: --nofollow-import-to=PySide6.QtBluetooth
# nuitka-project: --nofollow-import-to=PySide6.QtConcurrent
# nuitka-project: --nofollow-import-to=PySide6.QtDBus
# nuitka-project: --nofollow-import-to=PySide6.QtDesigner
# nuitka-project: --nofollow-import-to=PySide6.QtHelp
# nuitka-project: --nofollow-import-to=PySide6.QtMultimedia
# nuitka-project: --nofollow-import-to=PySide6.QtMultimediaWidgets
# nuitka-project: --nofollow-import-to=PySide6.QtNfc
# nuitka-project: --nofollow-import-to=PySide6.QtPositioning
# nuitka-project: --nofollow-import-to=PySide6.QtRemoteObjects
# nuitka-project: --nofollow-import-to=PySide6.QtScxml
# nuitka-project: --nofollow-import-to=PySide6.QtSensors
# nuitka-project: --nofollow-import-to=PySide6.QtSerialPort
# nuitka-project: --nofollow-import-to=PySide6.QtStateMachine
# nuitka-project: --nofollow-import-to=PySide6.QtUiTools
# nuitka-project: --nofollow-import-to=PySide6.QtWebSockets
# nuitka-project: --nofollow-import-to=PySide6.QtHttpServer
# nuitka-project: --nofollow-import-to=PySide6.QtDataVisualization
# nuitka-project: --nofollow-import-to=PySide6.QtPdf
# nuitka-project: --nofollow-import-to=PySide6.QtPdfWidgets
# nuitka-project: --nofollow-import-to=PySide6.QtSpatialAudio
# nuitka-project: --nofollow-import-to=PySide6.QtTextToSpeech

# httpx unused server and CLI modules
# nuitka-project: --nofollow-import-to=httpx._main
# nuitka-project: --nofollow-import-to=uvicorn
# nuitka-project: --nofollow-import-to=starlette
# nuitka-project: --nofollow-import-to=fastapi
# nuitka-project: --nofollow-import-to=httpx_ws

# Keyring backends not used (platform-specific ones are included above)
# nuitka-project: --nofollow-import-to=keyring.backends.chainer
# nuitka-project: --nofollow-import-to=keyring.backends.fail
# nuitka-project: --nofollow-import-to=keyring.backends.null
# nuitka-project: --nofollow-import-to=keyring.backends.kwallet
# nuitka-project: --nofollow-import-to=keyring.backends.libsecret
# nuitka-project: --nofollow-import-to=keyring.backends.OS_X
# nuitka-project: --nofollow-import-to=keyring.testing
# nuitka-project: --nofollow-import-to=keyrings.alt

# MSAL optional/unused dependencies
# nuitka-project: --nofollow-import-to=msal_extensions
# nuitka-project: --nofollow-import-to=portalocker

# Pydantic optional/development modules
# nuitka-project: --nofollow-import-to=pydantic.mypy
# nuitka-project: --nofollow-import-to=pydantic.hypothesis_plugin
# nuitka-project: --nofollow-import-to=pydantic.v1
# nuitka-project: --nofollow-import-to=pydantic._internal._docs_extraction
# nuitka-project: --nofollow-import-to=pydantic._internal._git
# nuitka-project: --nofollow-import-to=pydantic.deprecated

# Loguru optional dependencies
# nuitka-project: --nofollow-import-to=loguru._cython_compiler
# nuitka-project: --nofollow-import-to=notifiers

# structlog optional dependencies
# nuitka-project: --nofollow-import-to=structlog.twisted
# nuitka-project: --nofollow-import-to=structlog.testing

# SQLModel/SQLAlchemy testing and development
# nuitka-project: --nofollow-import-to=sqlalchemy.testing
# nuitka-project: --nofollow-import-to=sqlmodel.testing

# Common unused test frameworks and development tools
# nuitka-project: --nofollow-import-to=IPython
# nuitka-project: --nofollow-import-to=ipython
# nuitka-project: --nofollow-import-to=jupyter
# nuitka-project: --nofollow-import-to=notebook
# nuitka-project: --nofollow-import-to=jupyterlab
# nuitka-project: --nofollow-import-to=matplotlib
# nuitka-project: --nofollow-import-to=numpy
# nuitka-project: --nofollow-import-to=pandas
# nuitka-project: --nofollow-import-to=scipy
# nuitka-project: --nofollow-import-to=sklearn
# nuitka-project: --nofollow-import-to=tensorflow
# nuitka-project: --nofollow-import-to=torch
# nuitka-project: --nofollow-import-to=flask
# nuitka-project: --nofollow-import-to=django

# Crypto libraries not used
# nuitka-project: --nofollow-import-to=pycrypto
# nuitka-project: --nofollow-import-to=Crypto
# nuitka-project: --nofollow-import-to=nacl
# nuitka-project: --nofollow-import-to=bcrypt

# Other common libraries not in use
# nuitka-project: --nofollow-import-to=requests
# nuitka-project: --nofollow-import-to=urllib3
# nuitka-project: --nofollow-import-to=aiohttp
# nuitka-project: --nofollow-import-to=websockets
# nuitka-project: --nofollow-import-to=redis
# nuitka-project: --nofollow-import-to=celery
# nuitka-project: --nofollow-import-to=gevent
# nuitka-project: --nofollow-import-to=greenlet
# nuitka-project: --nofollow-import-to=eventlet

# ============= DEEP DEPENDENCY EXCLUSIONS =============
# These exclude internal sub-modules from our dependencies that we don't use

# Cryptography unused modules (MSAL only needs basic JWT/SSL)
# nuitka-project: --nofollow-import-to=cryptography.hazmat.primitives.kdf
# nuitka-project: --nofollow-import-to=cryptography.hazmat.primitives.twofactor
# nuitka-project: --nofollow-import-to=cryptography.hazmat.primitives.poly1305
# nuitka-project: --nofollow-import-to=cryptography.hazmat.primitives.keywrap
# nuitka-project: --nofollow-import-to=cryptography.hazmat.backends.openssl.dh
# nuitka-project: --nofollow-import-to=cryptography.hazmat.backends.openssl.dsa
# nuitka-project: --nofollow-import-to=cryptography.hazmat.backends.openssl.x25519
# nuitka-project: --nofollow-import-to=cryptography.hazmat.backends.openssl.x448
# nuitka-project: --nofollow-import-to=cryptography.hazmat.backends.openssl.ed25519
# nuitka-project: --nofollow-import-to=cryptography.hazmat.backends.openssl.ed448
# nuitka-project: --nofollow-import-to=cryptography.hazmat.backends.openssl.poly1305
# nuitka-project: --nofollow-import-to=cryptography.hazmat.bindings.openssl._conditional
# nuitka-project: --nofollow-import-to=cryptography.fernet
# nuitka-project: --nofollow-import-to=cryptography.hazmat.primitives.serialization.pkcs7
# nuitka-project: --nofollow-import-to=cryptography.hazmat.primitives.serialization.pkcs12
# nuitka-project: --nofollow-import-to=cryptography.hazmat.primitives.serialization.ssh

# httpx/httpcore internal modules we don't use
# nuitka-project: --nofollow-import-to=httpx._main
# nuitka-project: --nofollow-import-to=httpcore._sync
# nuitka-project: --nofollow-import-to=httpcore._async.socks_proxy
# nuitka-project: --nofollow-import-to=httpcore._sync.socks_proxy
# nuitka-project: --nofollow-import-to=socksio

# HTTP/2 support (we only use HTTP/1.1 for Graph API)
# nuitka-project: --nofollow-import-to=h2
# nuitka-project: --nofollow-import-to=hpack
# nuitka-project: --nofollow-import-to=hyperframe
# nuitka-project: --nofollow-import-to=httpcore._async.http2
# nuitka-project: --nofollow-import-to=httpcore._sync.http2

# Alternative async backends (httpx defaults to anyio with asyncio backend)
# nuitka-project: --nofollow-import-to=trio
# nuitka-project: --nofollow-import-to=trio_typing
# nuitka-project: --nofollow-import-to=curio
# nuitka-project: --nofollow-import-to=anyio._backends._trio
# nuitka-project: --nofollow-import-to=anyio._backends._curio
# nuitka-project: --nofollow-import-to=sniffio._tests

# Compression libraries (unless you explicitly use them)
# nuitka-project: --nofollow-import-to=brotli
# nuitka-project: --nofollow-import-to=brotlicffi
# nuitka-project: --nofollow-import-to=zstandard.backend_c
# nuitka-project: --nofollow-import-to=zstandard.backend_cffi

# MSAL optional/unused features
# nuitka-project: --nofollow-import-to=msal.broker
# nuitka-project: --nofollow-import-to=msal.cloudshell
# nuitka-project: --nofollow-import-to=msal.managed_identity
# nuitka-project: --nofollow-import-to=msal.wstrust_request
# nuitka-project: --nofollow-import-to=msal.wstrust_response
# nuitka-project: --nofollow-import-to=msal.mex
# nuitka-project: --nofollow-import-to=msal.__main__
# nuitka-project: --nofollow-import-to=msal.region

# PyJWT unused backends
# nuitka-project: --nofollow-import-to=jwt.contrib
# nuitka-project: --nofollow-import-to=jwt.algorithms

# Charset detection fallbacks
# nuitka-project: --nofollow-import-to=charset_normalizer.cli
# nuitka-project: --nofollow-import-to=charset_normalizer.assets
# nuitka-project: --nofollow-import-to=chardet

# Certifi - we only need the CA bundle, not the CLI
# nuitka-project: --nofollow-import-to=certifi.__main__

# Jaraco utilities (keyring dependency) - exclude unused parts
# nuitka-project: --nofollow-import-to=jaraco.text
# nuitka-project: --nofollow-import-to=jaraco.collections
# nuitka-project: --nofollow-import-to=jaraco.stream
# nuitka-project: --nofollow-import-to=jaraco.itertools
# nuitka-project: --nofollow-import-to=jaraco.logging
# nuitka-project: --nofollow-import-to=jaraco.path

# More PySide6 internal testing/development modules
# nuitka-project: --nofollow-import-to=PySide6.scripts
# nuitka-project: --nofollow-import-to=PySide6.support
# nuitka-project: --nofollow-import-to=shiboken6
# nuitka-project: --nofollow-import-to=pyside6_essentials

# Platform-specific modules (add based on your build target)
# nuitka-project-if: {OS} != "Windows":
#    nuitka-project: --nofollow-import-to=win32*
#    nuitka-project: --nofollow-import-to=pywintypes
#    nuitka-project: --nofollow-import-to=pythoncom
#    nuitka-project: --nofollow-import-to=msvcrt
#    nuitka-project: --nofollow-import-to=_winapi
#    nuitka-project: --nofollow-import-to=_winreg
#    nuitka-project: --nofollow-import-to=winreg
#    nuitka-project: --nofollow-import-to=winsound

# nuitka-project-if: {OS} != "Darwin":
#    nuitka-project: --nofollow-import-to=_scproxy
#    nuitka-project: --nofollow-import-to=_osx_support
#    nuitka-project: --nofollow-import-to=darwin
#    nuitka-project: --nofollow-import-to=Foundation
#    nuitka-project: --nofollow-import-to=AppKit
#    nuitka-project: --nofollow-import-to=CoreFoundation

# nuitka-project-if: {OS} != "Linux":
#    nuitka-project: --nofollow-import-to=gi
#    nuitka-project: --nofollow-import-to=dbus
#    nuitka-project: --nofollow-import-to=jeepney
#    nuitka-project: --nofollow-import-to=secretstorage.dhcrypto
#    nuitka-project: --nofollow-import-to=secretstorage.exceptions

# Email validation and DNS (not used)
# nuitka-project: --nofollow-import-to=email_validator
# nuitka-project: --nofollow-import-to=dnspython
# nuitka-project: --nofollow-import-to=dns

# XML processing libraries (not used)
# nuitka-project: --nofollow-import-to=lxml
# nuitka-project: --nofollow-import-to=defusedxml
# nuitka-project: --nofollow-import-to=xml.dom.pulldom
# nuitka-project: --nofollow-import-to=xml.dom.expatbuilder
# nuitka-project: --nofollow-import-to=xml.sax.saxutils
# nuitka-project: --nofollow-import-to=xml.sax.xmlreader

# Encoding/serialization formats not used
# nuitka-project: --nofollow-import-to=msgpack
# nuitka-project: --nofollow-import-to=cbor
# nuitka-project: --nofollow-import-to=cbor2
# nuitka-project: --nofollow-import-to=ujson
# nuitka-project: --nofollow-import-to=orjson
# nuitka-project: --nofollow-import-to=rapidjson
# nuitka-project: --nofollow-import-to=simplejson
# nuitka-project: --nofollow-import-to=toml
# nuitka-project: --nofollow-import-to=tomli
# nuitka-project: --nofollow-import-to=tomllib
# nuitka-project: --nofollow-import-to=configparser

# Date/time libraries not used (using standard library)
# nuitka-project: --nofollow-import-to=pytz
# nuitka-project: --nofollow-import-to=tzdata
# nuitka-project: --nofollow-import-to=dateutil
# nuitka-project: --nofollow-import-to=arrow
# nuitka-project: --nofollow-import-to=pendulum
# nuitka-project: --nofollow-import-to=babel

# CLI frameworks not used
# nuitka-project: --nofollow-import-to=click
# nuitka-project: --nofollow-import-to=typer
# nuitka-project: --nofollow-import-to=rich
# nuitka-project: --nofollow-import-to=colorama
# nuitka-project: --nofollow-import-to=termcolor
# nuitka-project: --nofollow-import-to=blessed
# nuitka-project: --nofollow-import-to=prompt_toolkit

# File watching/monitoring not used
# nuitka-project: --nofollow-import-to=watchdog
# nuitka-project: --nofollow-import-to=watchfiles
# nuitka-project: --nofollow-import-to=inotify
# nuitka-project: --nofollow-import-to=pyinotify

# Profiling/debugging tools
# nuitka-project: --nofollow-import-to=cProfile
# nuitka-project: --nofollow-import-to=profile
# nuitka-project: --nofollow-import-to=pstats
# nuitka-project: --nofollow-import-to=tracemalloc
# nuitka-project: --nofollow-import-to=timeit
# nuitka-project: --nofollow-import-to=pdb
# nuitka-project: --nofollow-import-to=bdb
# nuitka-project: --nofollow-import-to=trace
# nuitka-project: --nofollow-import-to=inspect

# Standard library test modules
# nuitka-project: --nofollow-import-to=unittest
# nuitka-project: --nofollow-import-to=doctest
# nuitka-project: --nofollow-import-to=test
# nuitka-project: --nofollow-import-to=tests
# nuitka-project: --nofollow-import-to=lib2to3

# Deprecated/legacy modules
# nuitka-project: --nofollow-import-to=imp
# nuitka-project: --nofollow-import-to=optparse
# nuitka-project: --nofollow-import-to=asyncore
# nuitka-project: --nofollow-import-to=asynchat
# nuitka-project: --nofollow-import-to=smtpd
# nuitka-project: --nofollow-import-to=distutils

# nuitka-project: --enable-plugin=pyside6

# Qt plugin configuration - minimal set for GUI app without networking
# Required plugins:
#   platforms: Essential for window creation
#   imageformats: Only PNG/ICO for app icons (no JPEG, SVG, etc.)
# Note: 'styles' plugin excluded - Fusion style is built into QtWidgets on all platforms
# nuitka-project: --include-qt-plugins=platforms,imageformats

# Explicitly exclude unused Qt plugins to reduce binary size
# nuitka-project: --noinclude-qt-plugins=tls
# nuitka-project: --noinclude-qt-plugins=networkinformation
# nuitka-project: --noinclude-qt-plugins=sqldrivers
# nuitka-project: --noinclude-qt-plugins=iconengines
# nuitka-project: --noinclude-qt-plugins=generic
# nuitka-project: --noinclude-qt-plugins=platforminputcontexts
# nuitka-project: --noinclude-qt-plugins=platformthemes
# nuitka-project: --noinclude-qt-plugins=wayland*
# nuitka-project: --noinclude-qt-plugins=xcbglintegrations
# nuitka-project: --noinclude-qt-plugins=egldeviceintegrations
# nuitka-project: --noinclude-qt-plugins=canbus
# nuitka-project: --noinclude-qt-plugins=designer
# nuitka-project: --noinclude-qt-plugins=qmltooling
# nuitka-project: --noinclude-qt-plugins=qmllint
# nuitka-project: --noinclude-qt-plugins=scenegraph
# nuitka-project: --noinclude-qt-plugins=sensors
# nuitka-project: --noinclude-qt-plugins=position
# nuitka-project: --noinclude-qt-plugins=multimedia
# nuitka-project: --noinclude-qt-plugins=mediaservice
# nuitka-project: --noinclude-qt-plugins=audio
# nuitka-project: --noinclude-qt-plugins=printsupport
# nuitka-project: --noinclude-qt-plugins=texttospeech
# nuitka-project: --noinclude-qt-plugins=virtualkeyboard
# Exclude unnecessary image format plugins (keep only what we use)
# nuitka-project: --noinclude-qt-plugins=imageformats/qjpeg
# nuitka-project: --noinclude-qt-plugins=imageformats/qgif
# nuitka-project: --noinclude-qt-plugins=imageformats/qsvg
# nuitka-project: --noinclude-qt-plugins=imageformats/qtiff
# nuitka-project: --noinclude-qt-plugins=imageformats/qwebp
# nuitka-project: --noinclude-qt-plugins=imageformats/qpdf
# nuitka-project: --noinclude-qt-plugins=imageformats/qwbmp
# nuitka-project: --noinclude-qt-plugins=imageformats/qtga

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
