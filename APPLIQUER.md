# Patch 18 — a poser par-dessus le patch 17

VERSION 1.0.0 : la decoupe automatique. La feuille de route d'origine
est complete.

Le geste fondateur : enregistrer dix coups d'affilee, repartir avec
dix WAV propres.

1. DETECTER LES FRAPPES : enveloppe + plancher de bruit + double
   seuil avec rearmement strict. Les coupes s'affichent en traits
   ambres SUR L'ONDE avant toute decoupe. Molette de sensibilite.
2. DECOUPER EN N SONS : chaque frappe devient un WAV (attaque
   gardee par pre-roll, bords fondus), range dans un dossier de la
   bibliotheque au nom choisi. Silhouettes calculees au passage.

La detection est independante du niveau d'enregistrement (seuils
relatifs, teste). Le bruit seul ne declenche rien (dynamique minimale
exigee, teste). Une queue de kick ne declenche pas de fausse frappe
(rearmement strict, teste).

Fichiers : main.py, onde.py, noyau/decoupe.py, noyau/__init__.py,
tests/test_decoupe.py, tests/verificateur.py.

Tests attendus : 204.
