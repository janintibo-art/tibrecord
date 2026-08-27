# Patch 12 — a poser par-dessus le patch 11

Version 0.4.0 : le studio mobile, etapes 1 et 2.

1. TRAITEMENTS EN ARRIERE-PLAN
   Presets et rack tournent dans un fil separe, avec une fenetre de
   patience et le temps qui defile. L'application ne se fige plus,
   Android ne la tue plus sur les longues prises.
   Un seul traitement a la fois : le deuxieme appui est refuse.

2. TRANSPORT COMPLET dans EDITION
   RETOUR / LIRE / PAUSE / STOP sous le compteur.
   PAUSE retient la position exacte, LIRE reprend de la.
   Les carres vides devant LIRE et STOP (glyphes absents de la
   police Android) sont remplaces par du texte.

Fichiers : main.py, noyau/travail.py, noyau/__init__.py,
tests/test_travail.py.

Tests attendus : 124.
