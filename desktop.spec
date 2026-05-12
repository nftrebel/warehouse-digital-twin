# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec для сборки десктопной версии «Цифрового двойника склада».

Сборка (запускать на целевой ОС — на Windows получится .exe, на macOS .app):
    pyinstaller desktop.spec --noconfirm
"""

import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules

PROJECT_ROOT = Path(SPECPATH).resolve()

# Данные, которые нужно положить рядом с исполняемым файлом
datas = [
    (str(PROJECT_ROOT / 'templates'), 'templates'),
    (str(PROJECT_ROOT / 'static'),    'static'),
    (str(PROJECT_ROOT / 'config'),    'config'),
    (str(PROJECT_ROOT / 'apps'),      'apps'),
]

# Django ищет management-команды и миграции через importlib — нужно явно подсказать
hiddenimports = []
hiddenimports += collect_submodules('apps')
hiddenimports += collect_submodules('config')
hiddenimports += collect_submodules('django')
hiddenimports += collect_submodules('rest_framework')
hiddenimports += [
    'django.template.defaulttags',
    'django.template.loader_tags',
    'django.contrib.staticfiles.templatetags.staticfiles',
    'django.contrib.admin.apps',
    'docx',
    'openpyxl',
]

block_cipher = None

a = Analysis(
    ['desktop.py'],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'numpy', 'pandas', 'scipy', 'PyQt5', 'PyQt6'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='WarehouseDigitalTwin',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,           # без чёрного окна консоли
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='WarehouseDigitalTwin',
)

# Сборка .app для macOS
if sys.platform == 'darwin':
    app = BUNDLE(
        coll,
        name='WarehouseDigitalTwin.app',
        icon=None,
        bundle_identifier='com.baluev.warehouse-digital-twin',
        info_plist={
            'CFBundleName': 'Warehouse Digital Twin',
            'CFBundleDisplayName': 'Цифровой двойник склада',
            'CFBundleShortVersionString': '1.0.0',
            'NSHighResolutionCapable': True,
        },
    )
