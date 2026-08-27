# -*- mode: python ; coding: utf-8 -*-
#   pyinstaller packaging/tibrecord.spec --noconfirm

import os
from kivy_deps import sdl2, glew

block_cipher = None

a = Analysis(
    ['../main.py'],
    pathex=[os.path.abspath('.')],
    binaries=[],
    datas=[('../assets', 'assets')] if os.path.isdir('assets') else [],
    hiddenimports=['noyau', 'noyau.audio', 'noyau.batch',
                   'noyau.bibliotheque', 'noyau.enregistrement',
                   'noyau.temps', 'onde'],
    hookspath=[],
    runtime_hooks=[],
    excludes=['numpy', 'scipy', 'matplotlib', 'tkinter'],
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz, a.scripts, a.binaries, a.zipfiles, a.datas,
    *[Tree(p) for p in (sdl2.dep_bins + glew.dep_bins)],
    name="Tibrecord",
    debug=False, strip=False, upx=False, console=False,
)
