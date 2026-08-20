# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = [('assets', 'assets')]
binaries = []
hiddenimports = ['Cocoa', 'AppKit', 'Foundation', 'objc']
for package in ('Cocoa', 'AppKit', 'Foundation', 'objc'):
    collected = collect_all(package)
    datas += collected[0]
    binaries += collected[1]
    hiddenimports += collected[2]

a = Analysis(
    ['leftover_pet_macos_full.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
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
    version='0.4.0',
    info_plist={
        'CFBundleDisplayName': '余食 LEFTOVER',
        'NSHighResolutionCapable': True,
        'LSMinimumSystemVersion': '13.0',
        'LSUIElement': True,
        'LSMultipleInstancesProhibited': True,
        'NSServices': [{
            'NSMenuItem': {'default': '喂给余食'},
            'NSMessage': 'feedToLeftover',
            'NSPortName': 'LEFTOVER',
            'NSSendTypes': ['NSFilenamesPboardType'],
            'NSSendFileTypes': ['public.item'],
            'NSRequiredContext': {'NSApplicationIdentifier': 'com.apple.finder'},
            'NSServiceDescription': '把 Finder 中选中的文件喂给余食，并移入废纸篓。',
        }],
    },
)
