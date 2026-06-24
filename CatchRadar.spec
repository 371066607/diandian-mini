# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec used by scripts/build_macos.sh and the build-macos/build-windows CI.
# code_version.txt (commit timestamp) is bundled so the app knows its own version and
# the update checker can compare against the published code patch.
import os
import sys

from PyInstaller.utils.hooks import collect_all

datas = [("code_version.txt", ".")] if os.path.exists("code_version.txt") else []
# The QML UI is loaded from the filesystem at runtime (app/ui/qml_app.py), so the
# .qml sources must ship as data files — collect_submodules only covers .py modules.
datas += [("app/qml", "app/qml")]
hiddenimports = [
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtQml",
    "PySide6.QtQuick",
    "PySide6.QtQuickControls2",
    "PySide6.QtOpenGL",
    "PySide6.QtOpenGLWidgets",
    "PySide6.QtWidgets",
]
binaries = []
excludes = [
    # Unused in the QML desktop shell; these modules pull in very large Qt
    # frameworks (especially QtWebEngineCore) and old Widgets-only chart deps.
    "app.ui.main_window",
    "app.ui.pages",
    "app.ui.widgets.chart_widget",
    "matplotlib",
    "numpy",
    "PIL",
    "PySide6.Qt3DAnimation",
    "PySide6.Qt3DCore",
    "PySide6.Qt3DExtras",
    "PySide6.Qt3DInput",
    "PySide6.Qt3DLogic",
    "PySide6.Qt3DRender",
    "PySide6.QtCharts",
    "PySide6.QtDataVisualization",
    "PySide6.QtGraphs",
    "PySide6.QtMultimedia",
    "PySide6.QtPdf",
    "PySide6.QtPdfWidgets",
    "PySide6.QtQuick3D",
    "PySide6.QtQuick3DAssetImport",
    "PySide6.QtQuick3DAssetUtils",
    "PySide6.QtQuick3DEffects",
    "PySide6.QtQuick3DHelpers",
    "PySide6.QtQuick3DParticles",
    "PySide6.QtQuick3DRuntimeRender",
    "PySide6.QtQuick3DUtils",
    "PySide6.QtQuick3DXr",
    "PySide6.QtTextToSpeech",
    "PySide6.QtVirtualKeyboard",
    "PySide6.QtWebChannel",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineQuick",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebSockets",
    "PySide6.QtWebView",
]

# curl_cffi ships a compiled libcurl-impersonate backend + CA bundle that
# PyInstaller's import follower misses on its own; collect them so the resilient
# HTTP client (see GooglePlayService) actually works inside the packaged app.
try:
    _cc_datas, _cc_binaries, _cc_hidden = collect_all("curl_cffi")
    datas += _cc_datas
    binaries += _cc_binaries
    hiddenimports += _cc_hidden
except Exception:
    pass

exe_icon = "assets/catchradar.ico" if sys.platform.startswith("win") else None
bundle_icon = "assets/catchradar.icns" if os.path.exists("assets/catchradar.icns") else None

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)

_excluded_bundle_parts = (
    "QtWebEngine",
    "QtWebChannel",
    "QtWebSockets",
    "QtWebView",
    "QtPdf",
    "Qt3D",
    "QtQuick3D",
    "QtVirtualKeyboard",
    "QtMultimedia",
    "QtCharts",
    "QtDataVisualization",
    "QtGraphs",
    "QtLocation",
    "QtPositioning",
    "QtRemoteObjects",
    "QtScxml",
    "QtSensors",
    "QtTest",
    "QtTextToSpeech",
)


def _keep_qt_entry(entry):
    dest = entry[0] if entry else ""
    src = entry[1] if len(entry) > 1 else ""
    text = f"{dest} {src}"
    return not any(part in text for part in _excluded_bundle_parts)


a.binaries = [entry for entry in a.binaries if _keep_qt_entry(entry)]
a.datas = [entry for entry in a.datas if _keep_qt_entry(entry)]
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="CatchRadar",
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=exe_icon,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=True,
    upx=False,
    upx_exclude=[],
    name="CatchRadar",
)
app = BUNDLE(
    coll,
    name="CatchRadar.app",
    icon=bundle_icon,
    bundle_identifier="com.catchradar.app",
)
