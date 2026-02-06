# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller Spec-Datei für TrafficOwl
======================================
Bündelt die gesamte Anwendung als standalone macOS .app:
  - Python + alle Libraries (pygame, opencv, ultralytics, numpy, pyserial, torch...)
  - YOLO-Modell (yolo26n-seg.pt)
  - Alle PNG-Assets
  - esp_control.py + traffic_logic.py

Build:  pyinstaller TrafficOwl.spec
Output: dist/TrafficOwl.app
"""

import os
import sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# Ultralytics braucht seine cfg-Dateien und Default-YAML
ultralytics_datas = collect_data_files('ultralytics')
ultralytics_hiddenimports = collect_submodules('ultralytics')

block_cipher = None

a = Analysis(
    ['integrated_main.py'],
    pathex=[],
    binaries=[],
    datas=[
        # === Assets (PNGs) ===
        ('Interface/assets/*.png', 'Interface/assets'),

        # === YOLO-Modell (nur das verwendete) ===
        ('image-detection/models/yolo26n-seg.pt', 'image-detection/models'),

        # === Python-Module die per sys.path importiert werden ===
        ('Interface/esp_control.py', 'Interface'),
        ('Interface/traffic_logic.py', 'Interface'),
    ] + ultralytics_datas,
    hiddenimports=[
        'esp_control',
        'traffic_logic',
        'serial',
        'serial.tools',
        'serial.tools.list_ports',
        'serial.tools.list_ports_posix',
        'pygame',
        'pygame.freetype',
        'pygame.gfxdraw',
        'cv2',
        'numpy',
        'torch',
        'torchvision',
        'PIL',
        'PIL.Image',
    ] + ultralytics_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'IPython',
        'jupyter',
        'notebook',
    ],
    noarchive=False,
    optimize=0,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='TrafficOwl',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,       # Terminal-Fenster anzeigen für Debug-Logs (auf False setzen wenn alles läuft)
    target_arch=None,    # Native Architektur (arm64 auf M-Chip, x86_64 auf Intel)
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='TrafficOwl',
)

app = BUNDLE(
    coll,
    name='TrafficOwl.app',
    icon=None,           # Optional: 'icon.icns' hier eintragen
    bundle_identifier='de.fluss.trafficowl',
    info_plist={
        'NSHighResolutionCapable': True,
        'NSCameraUsageDescription': 'TrafficOwl benötigt Zugriff auf die Kamera für die Personenerkennung.',
        'CFBundleShortVersionString': '1.0.0',
        'CFBundleName': 'TrafficOwl',
    },
)
