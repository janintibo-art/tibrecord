# Patch 15 — a poser par-dessus le patch 14

Version 0.7.0 : les LED (etape 5).

- LIRE porte une LED verte qui respire pendant la lecture.
- PAUSE porte une LED ambre, fixe tant qu'on est en pause.
- L'onglet REC porte une LED rouge qui bat pendant la capture :
  visible depuis n'importe quel ecran, elle empeche d'oublier un
  enregistrement qui tourne.
- Eteintes, les LED restent faiblement visibles, comme les lampes
  d'un vrai rack.

AUCUNE horloge ajoutee : les LED respirent depuis les minuteries qui
tournent deja (tete de lecture a 30 i/s, vu-metre REC a 24 i/s), et
s'arretent donc forcement avec elles.

Fichiers : main.py, noyau/temps.py (pulsation), noyau/__init__.py,
tests/test_temps.py.

Tests attendus : 152.
