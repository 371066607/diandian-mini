# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec used by scripts/build_macos.sh and the build-macos/build-windows CI.
# code_version.txt (commit timestamp) is bundled so the app knows its own version and
# the update checker can compare against the published code patch.
import os

from PyInstaller.utils.hooks import collect_submodules

datas = [("code_version.txt", ".")] if os.path.exists("code_version.txt") else []
hiddenimports = collect_submodules("app")

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
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
    name="DiandianMini",
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
    name="DiandianMini",
)
app = BUNDLE(
    coll,
    name="DiandianMini.app",
    icon=None,
    bundle_identifier="com.diandian.mini",
)
