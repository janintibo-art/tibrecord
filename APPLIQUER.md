# Patch 14 — a poser par-dessus le patch 13

Version 0.6.0 : le spectre anime pendant la lecture (etape 4).

- A l'arret, l'analyseur resume le son entier comme avant.
- Pendant la lecture, il suit la position : 12 images par seconde,
  fenetre courte centree sur la tete de lecture, montee immediate et
  retombee amortie comme un vrai vu-metre.
- Le calcul vit dans noyau/spectre.py, teste : une sinusoide a 440 Hz
  doit allumer la bande de 440 Hz, le silence donne zero, et le cout
  par image est mesure par un test (budget 12 i/s).
- L'animation s'arrete a la pause, au stop, a la fin du son et au
  changement d'onglet — la lecon du voyant REC, appliquee partout.

Fichiers : main.py, noyau/spectre.py, noyau/__init__.py,
tests/test_spectre.py, tests/verificateur.py.

Tests attendus : 149.
