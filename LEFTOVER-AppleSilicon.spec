# -*- mode: python ; coding: utf-8 -*-
a = Analysis(
    ['leftover_pet_macos_qt.py'],
    pathex=[],
    binaries=[],
    datas=[('assets', 'assets')],
    hiddenimports=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True,
    name='LEFTOVER', debug=False, strip=False, upx=False,
    console=False, target_arch='arm64', codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='LEFTOVER')
app = BUNDLE(
    coll,
    name='LEFTOVER.app',
    icon='assets/LEFTOVER.icns',
    bundle_identifier='com.watermud.leftoverpet.macos',
    version='0.3.1',
    info_plist={
        'CFBundleDisplayName': '余食 LEFTOVER',
        'NSHighResolutionCapable': True,
        'LSMinimumSystemVersion': '13.0',
        'LSUIElement': True,
    },
)
