# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec used by scripts/build_macos.sh and the build-macos/build-windows CI.
# code_version.txt (commit timestamp) is bundled so the app knows its own version and
# the update checker can compare against the published code patch.
import os

from PyInstaller.utils.hooks import collect_all, collect_submodules

datas = [("code_version.txt", ".")] if os.path.exists("code_version.txt") else []
# The QML UI is loaded from the filesystem at runtime (app/ui/qml_app.py), so the
# .qml sources must ship as data files — collect_submodules only covers .py modules.
datas += [("app/qml", "app/qml")]
hiddenimports = collect_submodules("app")
binaries = []

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

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="CatchRadar",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="CatchRadar",
)
app = BUNDLE(
    coll,
    name="CatchRadar.app",
    icon=None,
    bundle_identifier="com.catchradar.app",
)
