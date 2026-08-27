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
    # main.py cherche les images a cote de lui : on les met a la racine
    # du paquet, pas seulement dans un sous-dossier de donnees.
    hiddenimports=['noyau', 'noyau.audio', 'noyau.batch',
                   'noyau.bibliotheque', 'noyau.enregistrement',
                   'noyau.temps', 'onde'],
    hookspath=[],
    runtime_hooks=[],
    excludes=['numpy', 'scipy', 'matplotlib', 'tkinter'],
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# L'icone est a cote de ce fichier, pas dans le dossier courant : le
# workflow lance pyinstaller depuis la racine du depot.
_ici = os.path.dirname(os.path.abspath(SPEC)) if "SPEC" in dir() \
    else os.path.abspath("packaging")
_icone = os.path.join(_ici, "tibrecord.ico")

exe = EXE(
    pyz, a.scripts, a.binaries, a.zipfiles, a.datas,
    *[Tree(p) for p in (sdl2.dep_bins + glew.dep_bins)],
    name="Tibrecord",
    icon=_icone if os.path.isfile(_icone) else None,
    debug=False, strip=False, upx=False, console=False,
)
