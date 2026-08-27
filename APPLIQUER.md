# Patch 10 — a poser par-dessus le patch 09

Le patch 09 a corrige noyau/enregistrement.py. Le controle d'accord
noyau-interface a ensuite trouve LE MEME defaut sur un autre fichier :

  main.py appelle audio.studio_rack()  ->  absent de noyau/audio.py

Trois fichiers du depot etaient restes en version ancienne :

  noyau/audio.py              sans eq3() ni studio_rack()
  tests/test_audio.py         25 tests au lieu de 29
  tests/test_enregistrement.py  11 tests au lieu de 12

Ce zip contient ces trois fichiers, et rien d'autre.

Tests attendus apres application : 116.
