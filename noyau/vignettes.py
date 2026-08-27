"""
Mini-formes d'onde pour la bibliotheque.

Le but : reconnaitre une prise d'un coup d'oeil, sans lire son nom.
Un kick, une voix et une nappe n'ont pas la meme silhouette.

Deux decisions de performance, toutes deux mesurees :

1. Lecture DECIMEE. Decoder entierement un WAV de trois minutes coute
   pres de deux secondes ; en lire un echantillon sur quelques-uns par
   colonne coute six millisecondes, pour une silhouette identique a
   l'oeil. On ne lit jamais tout.

2. CACHE sur disque. Meme rapide, un calcul par fichier a chaque
   ouverture de l'onglet finirait par se sentir sur deux cents prises.
   Les silhouettes sont rangees dans un petit fichier .vignettes.json
   par dossier, et un fichier n'est recalcule que si sa date ou sa
   taille a change. La cle est le NOM du fichier, pas son chemin : le
   cache survit ainsi au renommage du dossier qui le contient.
"""

import json
import os
import wave
from array import array

COLONNES = 48
FICHIER_CACHE = ".vignettes.json"
VERSION_CACHE = 1


# --------------------------------------------------------------- calcul
def calculer(chemin, colonnes=COLONNES):
    """Silhouette d'un WAV : `colonnes` valeurs entre 0 et 1.

    Lecture decimee : environ deux cents echantillons par colonne
    suffisent pour trouver la crete visuelle. Renvoie None si le fichier
    n'est pas lisible comme WAV 16 bits — l'appelant affichera une
    vignette vide plutot que de planter.
    """
    try:
        with wave.open(chemin, "rb") as w:
            if w.getsampwidth() != 2:
                return None
            nchan = max(1, w.getnchannels())
            brut = w.readframes(w.getnframes())
    except Exception:  # noqa: BLE001
        return None
    vals = array("h")
    try:
        vals.frombytes(brut[:len(brut) - (len(brut) % 2)])
    except Exception:  # noqa: BLE001
        return None
    # On ne garde qu'un canal : pour une silhouette, la stereo n'apporte
    # rien et double le travail.
    if nchan > 1:
        vals = vals[::nchan]
    n = len(vals)
    if n == 0:
        return [0.0] * colonnes
    taille = max(1, n // colonnes)
    pas = max(1, taille // 200)
    pics = []
    for c in range(colonnes):
        bloc = vals[c * taille:(c + 1) * taille:pas]
        if not bloc:
            pics.append(0.0)
            continue
        pics.append(min(1.0, max(abs(v) for v in bloc) / 32768.0))
    return pics


# --------------------------------------------------------------- cache
def _chemin_cache(dossier):
    return os.path.join(dossier, FICHIER_CACHE)


def lire_cache(dossier):
    """Le cache du dossier, ou un cache vide s'il est absent ou abime.

    Un cache illisible n'est jamais une erreur : il sera simplement
    reconstruit. Perdre des vignettes coute six millisecondes chacune.
    """
    try:
        with open(_chemin_cache(dossier), encoding="utf-8") as f:
            d = json.load(f)
        if d.get("version") == VERSION_CACHE and \
                isinstance(d.get("fichiers"), dict):
            return d
    except Exception:  # noqa: BLE001
        pass
    return {"version": VERSION_CACHE, "fichiers": {}}


def ecrire_cache(dossier, cache):
    """Ecrit le cache. Un echec d'ecriture est silencieux : la vignette
    sera recalculee la prochaine fois, rien de plus."""
    try:
        with open(_chemin_cache(dossier), "w", encoding="utf-8") as f:
            json.dump(cache, f)
        return True
    except Exception:  # noqa: BLE001
        return False


def _a_jour(entree, item):
    return (entree is not None
            and entree.get("m") == round(item["date"], 2)
            and entree.get("t") == item["taille"])


def pour_items(dossier, items):
    """Les silhouettes disponibles tout de suite, et ce qui manque.

    Renvoie (vignettes, manquants) :
      vignettes : {chemin: [0..1, ...]} depuis le cache, sans aucune
                  lecture de WAV — c'est l'appel fait a chaque
                  affichage, il doit rester instantane
      manquants : les chemins a calculer en arriere-plan
    """
    cache = lire_cache(dossier)
    fichiers = cache["fichiers"]
    vignettes, manquants = {}, []
    for item in items:
        nom = os.path.basename(item["chemin"])
        entree = fichiers.get(nom)
        if _a_jour(entree, item):
            vignettes[item["chemin"]] = [v / 100.0 for v in entree["p"]]
        else:
            manquants.append(item["chemin"])
    return vignettes, manquants


def completer(dossier, chemins):
    """Calcule les silhouettes manquantes et met le cache a jour.

    Fait pour tourner dans un fil de fond : ne renvoie que le nombre de
    vignettes calculees, l'appelant relira le cache sur le fil
    d'interface. Les entrees des fichiers disparus sont purgees au
    passage, sinon le cache grossit a chaque suppression.
    """
    cache = lire_cache(dossier)
    fichiers = cache["fichiers"]
    faits = 0
    for chemin in chemins:
        pics = calculer(chemin)
        try:
            st = os.stat(chemin)
        except OSError:
            continue
        fichiers[os.path.basename(chemin)] = {
            "m": round(st.st_mtime, 2),
            "t": st.st_size,
            "p": [int(round(v * 100)) for v in (pics or [0.0] * COLONNES)],
        }
        faits += 1
    presents = set()
    try:
        presents = set(os.listdir(dossier))
    except OSError:
        pass
    for nom in list(fichiers):
        if nom not in presents:
            del fichiers[nom]
    ecrire_cache(dossier, cache)
    return faits
