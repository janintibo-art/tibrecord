[app]
title = Tibrecord
package.name = tibrecord
package.domain = org.tibrecord

source.dir = .
source.include_exts = py,png,jpg,kv,atlas,txt,md
source.include_patterns = noyau/*.py,assets/*.png
source.exclude_dirs = tests,packaging,.github,bin,.buildozer
version = 0.1.0

requirements = python3,kivy==2.3.0

orientation = portrait
fullscreen = 0

# RECORD_AUDIO : indispensable pour le micro.
android.permissions = RECORD_AUDIO,READ_EXTERNAL_STORAGE,WRITE_EXTERNAL_STORAGE,READ_MEDIA_AUDIO,MANAGE_EXTERNAL_STORAGE
android.api = 33
android.minapi = 24
android.ndk_api = 24
android.archs = arm64-v8a
android.allow_backup = 1
android.accept_sdk_license = True

# CRUCIAL, et a laisser DANS LA SECTION [app] :
# place dans [buildozer], ce reglage est ignore EN SILENCE.
# La branche master de python-for-android compile Python 3.14, que
# Kivy 2.3 ne supporte pas. Cette release compile Python 3.11.
p4a.branch = v2024.01.21

# icone et ecran de demarrage : decommente quand les images existent
icon.filename = %(source.dir)s/assets/icon.png
presplash.filename = %(source.dir)s/assets/presplash.png
android.presplash_color = #0e0e12

[buildozer]
log_level = 2
warn_on_root = 0
