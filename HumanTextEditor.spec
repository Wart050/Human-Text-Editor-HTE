# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['C:\\Users\\1hass\\OneDrive\\Desktop\\Code\\Personal Code\\Projects\\human_editor\\Human-Text-Editor-HTE\\human_editor.py'],
    pathex=[],
    binaries=[],
    datas=[('C:\\Users\\1hass\\OneDrive\\Desktop\\Code\\Personal Code\\Projects\\human_editor\\Human-Text-Editor-HTE\\assets', 'assets')],
    hiddenimports=['keyboard'],
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
    name='HumanTextEditor',
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
    icon=['C:\\Users\\1hass\\OneDrive\\Desktop\\Code\\Personal Code\\Projects\\human_editor\\Human-Text-Editor-HTE\\assets\\icon.ico'],
)
