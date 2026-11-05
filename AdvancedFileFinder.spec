# -*- mode: python ; coding: utf-8 -*-
# PyInstaller recipe.  Build with build_exe.bat (folder build) or build_exe.bat onefile.
import os
from PyInstaller.utils.hooks import collect_data_files

ONEFILE = os.environ.get("AFF_ONEFILE") == "1"
NAME = "AdvancedFileFinder"
ICON = "assets/app.ico" if os.path.exists("assets/app.ico") else None
VERSION = "build/version_info.txt" if os.path.exists("build/version_info.txt") else None

datas = collect_data_files("customtkinter")                      # themes, fonts, icons of the widget library
datas += [("assets/app.ico", "assets"), ("assets/app.png", "assets")] if ICON else []
hidden = []
try:                                                              # optional drag & drop support
    datas += collect_data_files("tkinterdnd2")                    # bundled tkdnd native libraries
    hidden.append("tkinterdnd2")
except Exception:
    pass

a = Analysis(
    ["run_app.py"], pathex=["."], datas=datas, hiddenimports=hidden, hookspath=[],
    excludes=["pytest", "pyinstaller", "unittest", "pydoc", "test", "numpy", "pandas", "matplotlib"],
    noarchive=False,
)
pyz = PYZ(a.pure)

if ONEFILE:
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name=NAME, console=False, icon=ICON,
              version=VERSION, upx=False, runtime_tmpdir=None)
else:
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name=NAME, console=False, icon=ICON,
              version=VERSION, upx=False)
    coll = COLLECT(exe, a.binaries, a.datas, upx=False, name=NAME)
