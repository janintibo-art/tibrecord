# Patch 17 — a poser par-dessus le patch 16

Version 0.9.0 : le MONTAGE.

Nouvelle section dans EDITION, entre l'onde et les traitements :
  Couper / Copier / Coller / Suppr. / Boucler, avec presse-papiers
  affiche sous les boutons.

Toutes les jointures sont fondues sur 6 ms : pas de clic. Le test
central le PROUVE : une coupe brute sur le pire signal possible fait
sauter le signal de 1.0, la meme coupe fondue reste sous 0.25.

Coller insere au DEBUT de la selection : la poignee gauche sert de
curseur d'insertion. Boucler repete la selection 4 fois. Tout
supprimer est refuse (erreur de selection presque certaine).

Sur les prises de plus de 15 s, le montage passe en tache de fond
avec la fenetre de patience (2 s mesurees sur 3 min de son).

Fichiers : main.py, noyau/montage.py, noyau/__init__.py,
tests/test_montage.py, tests/verificateur.py.

Tests attendus : 191.
