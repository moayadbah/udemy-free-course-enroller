# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec: bundle the Udemy Course Enroller GUI into one file.

Build:   pyinstaller udemy_enroller_gui.spec
Output:  dist/UdemyCourseEnroller        (Linux)
         dist/UdemyCourseEnroller.exe    (Windows)
         dist/UdemyCourseEnroller.app    (macOS, wrapped into a .dmg by CI)

Pinned for PyInstaller 6.x (see requirements-build.txt).
"""
import sys

from PyInstaller.utils.hooks import collect_all, collect_submodules

datas = []
binaries = []
hiddenimports = []

# Packages that ship data files or use dynamic imports PyInstaller can miss.
for pkg in (
    "selenium",
    "webdriver_manager",
    "cloudscraper",
    "ruamel.yaml",
    "aiohttp",
    "bs4",
    "price_parser",
    "certifi",
):
    pkg_datas, pkg_binaries, pkg_hidden = collect_all(pkg)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hidden

# Our own package is imported lazily / via re-exec, so pull every submodule in.
hiddenimports += collect_submodules("udemy_enroller")

a = Analysis(
    ["gui.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="UdemyCourseEnroller",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # UPX-packed binaries frequently trip antivirus false positives
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # windowed GUI app
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

# On macOS, wrap the executable in a .app bundle so it can be shipped in a .dmg.
if sys.platform == "darwin":
    app = BUNDLE(
        exe,
        name="UdemyCourseEnroller.app",
        icon=None,
        bundle_identifier="com.moayadbah.udemycourseenroller",
        info_plist={"NSHighResolutionCapable": True},
    )
