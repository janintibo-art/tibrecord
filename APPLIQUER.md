# Patch 09 — remplace le patch 08, depend de la v0.3.0

CORRIGE LE PLANTAGE du bouton ENREGISTRER.

Cause : noyau/enregistrement.py du depot etait la version d'origine,
sans la methode instantane(). Le main.py, lui, l'appelait a 24 images
par seconde pendant la capture. Le patch 05 contenait bien le fichier
corrige, mais il n'a jamais atterri dans le depot.

Ce zip contient noyau/enregistrement.py. C'est le fichier essentiel.

Contient aussi tout le patch 08 (acces aux fichiers du telephone) :
inutile d'appliquer le 08 separement.

Tests attendus : 116.
