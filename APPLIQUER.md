# Patch 13 — a poser par-dessus le patch 12

Version 0.5.0 : mini-formes d'onde dans la bibliotheque (etape 3).

- Chaque ligne de SONS montre la silhouette du son, calculee par
  lecture decimee (6 ms au lieu de 2 s sur un WAV de 3 minutes).
- Cache .vignettes.json par dossier : rien n'est recalcule tant que
  le fichier n'a pas change. La cle est le nom du fichier : le cache
  survit au renommage du dossier.
- Le calcul des silhouettes manquantes se fait en arriere-plan : la
  liste s'affiche d'abord, les silhouettes se posent apres.
- Correction liee : le cache ne bloque plus la suppression d'un
  dossier vide de sons.

Fichiers : main.py, noyau/vignettes.py, noyau/bibliotheque.py,
noyau/__init__.py, tests/test_vignettes.py, tests/test_bibliotheque.py,
tests/verificateur.py.

Tests attendus : 138.
