# Patch 16 — a poser par-dessus le patch 15

Version 0.8.0 : les EFFETS (etape 6, premier paquet).

Sept effets dans noyau/effets.py, tous en Python pur, tous testes sur
leur resultat audible :
  Delai, Reverbe (Schroeder), Tremolo, Bitcrush, Vari-speed,
  Inversion, Polarite.

Nouvelle section EFFETS dans EDITION, sous le rack :
  - liste deroulante, molettes qui changent selon l'effet choisi
    (construites depuis le CATALOGUE du noyau : ajouter un effet
    la-bas suffit a le faire apparaitre dans l'application)
  - APERCU EFFET : l'effet sur la selection, joue au retour
  - APPLIQUER EFFET : le son entier, en arriere-plan avec la fenetre
    de patience ; ANNULER revient en arriere

Couts mesures (3 s de son, ici) : delai 164 ms, reverbe 229 ms,
tremolo 13 ms, bitcrush 45 ms, vari-speed 17 ms. Tout passe en fond.

Fichiers : main.py, noyau/effets.py, noyau/__init__.py,
tests/test_effets.py, tests/verificateur.py.

Tests attendus : 176.
