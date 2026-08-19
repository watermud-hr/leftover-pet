# -*- mode: python ; coding: utf-8 -*-
a = Analysis(
    ['clyde_pet_macos.py'],
    pathex=[],
    binaries=[],
    datas=[('clyde-assets', 'clyde-assets')],
    hiddenimports=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True,
    name='Clyde', debug=False, strip=False, upx=False,
    console=False, target_arch='arm64', codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='Clyde')
app = BUNDLE(
    coll,
    name='Clyde.app',
    icon='clyde-assets/Clyde.icns',
    bundle_identifier='com.watermud.clydepet.macos',
    version='0.1.2',
    info_plist={
        'CFBundleDisplayName': 'Clyde',
        'NSHighResolutionCapable': True,
        'LSMinimumSystemVersion': '13.0',
        'LSUIElement': True,
    },
)
