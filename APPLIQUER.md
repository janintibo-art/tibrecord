# Patch 08 — depend de la v0.3.0

Corrige l'acces aux fichiers du telephone. Ne touche PAS a
l'enregistrement : le plantage du bouton REC n'est pas encore
diagnostique, il faut la ligne d'erreur exacte.

Fichiers : main.py, noyau/stockage.py, noyau/__init__.py,
tests/test_stockage.py.

buildozer.spec n'est pas dans le zip : seule la ligne de version
change, par une commande a part.

Tests attendus : 112 (96 + 16 nouveaux).
