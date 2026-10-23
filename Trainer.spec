# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=[],
    datas=[('ui', 'ui'), ('vendor', 'vendor'), ('assets/chibi', 'assets/chibi'), ('data', 'data')],
    hiddenimports=['fastapi', 'fastapi.testclient', 'starlette.testclient', 'pydantic', 'httpx', 'anyio', 'multipart', 'typing', 'math', 'datetime', 're', 'json', 'collections', 'itertools', 'functools', 'random', 'string', 'enum'],
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
    a.binaries,
    a.datas,
    [],
    name='Trainer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/Train for python.ico',
)
