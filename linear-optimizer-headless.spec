# -*- mode: python ; coding: utf-8 -*-


# The editable linear_optimizer_mos.txt stays next to the EXE and is never
# bundled into it. Copy client/linear_optimizer_mos.example.txt after build.
a = Analysis(
    ['client/mos_optimizer_runner.py'],
    pathex=['client'],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['PyQt5'],
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
    name='mos-optimizer-runner',
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
