# -*- mode: python ; coding: utf-8 -*-
import platform

system = platform.system().lower()
if system == "darwin":
    suffix = "macos"
elif system == "windows":
    suffix = "windows"
else:
    suffix = "linux"

a = Analysis(
    ["src/examtopics/cli.py"],
    pathex=[],
    binaries=[],
    datas=[
        ("src/examtopics/templates", "examtopics/templates"),
    ],
    hiddenimports=[
        "typer",
        "rich",
        "httpx",
        "selectolax",
        "jinja2",
        "pydantic",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "unittest",
        "pydoc",
        "doctest",
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name=f"examtopics-{suffix}",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
