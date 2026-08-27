"""
Rangement des sons : dossiers, renommage, tri.

Ce module ne touche pas a l'affichage et n'a AUCUNE dependance : il se
teste sans micro, sans Kivy et sans Android.

Organisation sur le disque, volontairement banale : la bibliotheque est
un dossier qui contient des sous-dossiers, et des WAV dedans. Rien de
cache, rien d'invente. On peut tout reprendre avec un explorateur de
fichiers ordinaire, et rien n'est perdu si l'application disparait.

    enregistrements/
    ├── kicks/
    │   ├── kick grave.wav
    │   └── kick sec.wav
    ├── voix/
    └── prise 3.wav        <- a la racine : pas encore range
"""

import os
import time
import wave

EXTENSIONS = (".wav", ".WAV")

# Interdits par les systemes de fichiers, ou sources d'ennuis.
CARACTERES_INTERDITS = '/\\:*?"<>|\0'

RACINE = "(non range)"


# --------------------------------------------------------------- noms
def nom_propre(nom, defaut="son"):
    """Nettoie un nom saisi a la main.

    Retire l'extension, les caracteres interdits et les espaces en trop.
    Ne renvoie jamais une chaine vide : c'est la porte ouverte aux
    fichiers fantomes.
    """
    nom = (nom or "").strip()
    for ext in EXTENSIONS:
        if nom.endswith(ext):
            nom = nom[:-len(ext)]
    net = "".join(" " if c in CARACTERES_INTERDITS else c for c in nom)
    net = " ".join(net.split())
    net = net.strip(". ")
    return net or defaut


def chemin_libre(dossier, nom):
    """Renvoie un chemin qui n'ecrase rien.

    "kick" existe deja ? on propose "kick 2", puis "kick 3".
    """
    nom = nom_propre(nom)
    chemin = os.path.join(dossier, nom + ".wav")
    if not os.path.exists(chemin):
        return chemin
    for i in range(2, 1000):
        essai = os.path.join(dossier, "%s %d.wav" % (nom, i))
        if not os.path.exists(essai):
            return essai
    return os.path.join(dossier, "%s %d.wav" % (nom, int(time.time())))


# --------------------------------------------------------------- lecture
def duree_ms(chemin):
    """Duree d'un WAV, lue dans l'en-tete seulement.

    On ne charge pas le son : une bibliotheque de deux cents prises
    doit s'afficher tout de suite.
    """
    try:
        with wave.open(chemin, "rb") as w:
            rate = w.getframerate() or 1
            return w.getnframes() * 1000.0 / rate
    except Exception:  # noqa: BLE001
        return 0.0


def lister_dossiers(racine):
    """Sous-dossiers de la bibliotheque, par ordre alphabetique."""
    try:
        noms = [n for n in os.listdir(racine)
                if os.path.isdir(os.path.join(racine, n))
                and not n.startswith(".")]
    except OSError:
        return []
    return sorted(noms, key=lambda s: s.lower())


def lister_sons(dossier):
    """Les WAV d'un dossier, avec ce qu'il faut pour les afficher.

    Un fichier illisible n'est pas ecarte : il apparait avec une duree
    de zero. Mieux vaut le voir et pouvoir l'effacer que le cacher.
    """
    items = []
    try:
        noms = os.listdir(dossier)
    except OSError:
        return items
    for n in noms:
        if not n.endswith(EXTENSIONS):
            continue
        chemin = os.path.join(dossier, n)
        if not os.path.isfile(chemin):
            continue
        try:
            st = os.stat(chemin)
            taille, date = st.st_size, st.st_mtime
        except OSError:
            taille, date = 0, 0.0
        items.append({
            "nom": os.path.splitext(n)[0],
            "chemin": chemin,
            "taille": taille,
            "date": date,
            "duree_ms": duree_ms(chemin),
        })
    return items


def compter(dossier):
    """Nombre de WAV dans un dossier, sans lire les en-tetes."""
    try:
        return sum(1 for n in os.listdir(dossier)
                   if n.endswith(EXTENSIONS)
                   and os.path.isfile(os.path.join(dossier, n)))
    except OSError:
        return 0


# --------------------------------------------------------------- tri
TRIS = ("nom", "date", "duree", "taille")


def trier(items, cle="date", inverse=None):
    """Trie la liste renvoyee par lister_sons.

    Par defaut le plus recent d'abord pour la date et la duree, et
    l'ordre alphabetique pour le nom : c'est ce qu'on attend a chaque
    fois sans avoir a le demander.
    """
    if cle not in TRIS:
        cle = "date"
    if inverse is None:
        inverse = cle != "nom"
    if cle == "nom":
        return sorted(items, key=lambda i: i["nom"].lower(), reverse=inverse)
    champ = "duree_ms" if cle == "duree" else cle
    return sorted(items, key=lambda i: i.get(champ, 0), reverse=inverse)


def chercher(items, texte):
    """Filtre sur le nom, sans tenir compte de la casse ni des accents
    manquants. Une recherche vide ne filtre rien."""
    texte = (texte or "").strip().lower()
    if not texte:
        return list(items)
    return [i for i in items if texte in i["nom"].lower()]


# --------------------------------------------------------------- ecriture
def creer_dossier(racine, nom):
    """Cree un sous-dossier et renvoie son chemin.

    S'il existe deja, on renvoie l'existant sans rien casser : la
    personne voulait ce dossier, elle l'a.
    """
    nom = nom_propre(nom, "dossier")
    chemin = os.path.join(racine, nom)
    os.makedirs(chemin, exist_ok=True)
    return chemin


def renommer(chemin, nouveau_nom):
    """Renomme un WAV dans son dossier. Renvoie le nouveau chemin."""
    dossier = os.path.dirname(chemin)
    nom = nom_propre(nouveau_nom, os.path.splitext(
        os.path.basename(chemin))[0])
    cible = os.path.join(dossier, nom + ".wav")
    if os.path.abspath(cible) == os.path.abspath(chemin):
        return chemin
    cible = chemin_libre(dossier, nom)
    os.rename(chemin, cible)
    return cible


def deplacer(chemin, dossier_cible):
    """Deplace un WAV vers un autre dossier. Renvoie le nouveau chemin."""
    os.makedirs(dossier_cible, exist_ok=True)
    nom = os.path.splitext(os.path.basename(chemin))[0]
    if os.path.abspath(os.path.dirname(chemin)) == \
            os.path.abspath(dossier_cible):
        return chemin
    cible = chemin_libre(dossier_cible, nom)
    os.replace(chemin, cible)
    return cible


def supprimer(chemin):
    """Efface un fichier. Renvoie True si quelque chose a ete efface."""
    try:
        os.remove(chemin)
        return True
    except OSError:
        return False


def renommer_dossier(racine, ancien, nouveau):
    """Renomme un sous-dossier. Renvoie le nouveau chemin.

    Refuse d'ecraser un dossier existant : deux dossiers fusionnes par
    accident, c'est une perte de rangement impossible a defaire.
    """
    nouveau = nom_propre(nouveau, ancien)
    src = os.path.join(racine, ancien)
    dst = os.path.join(racine, nouveau)
    if os.path.abspath(src) == os.path.abspath(dst):
        return src
    if os.path.exists(dst):
        raise FileExistsError("le dossier %s existe deja" % nouveau)
    os.rename(src, dst)
    return dst


# Fichiers de service que l'application pose elle-meme dans les
# dossiers. Ils ne comptent pas comme du contenu.
FICHIERS_SERVICE = (".vignettes.json",)


def supprimer_dossier(racine, nom):
    """Efface un sous-dossier VIDE seulement.

    Volontairement strict : un dossier plein s'efface fichier par
    fichier, pour qu'on voie ce qu'on perd. Les fichiers de service que
    l'application a poses elle-meme (le cache des vignettes) ne comptent
    pas : un dossier dont on a retire tous les sons doit se supprimer.
    """
    chemin = os.path.join(racine, nom)
    try:
        for service in FICHIERS_SERVICE:
            f = os.path.join(chemin, service)
            if os.path.isfile(f):
                os.remove(f)
        os.rmdir(chemin)
        return True
    except OSError:
        return False


# --------------------------------------------------------------- resume
def resume(racine):
    """Etat de la bibliotheque : (dossier, nombre de sons, duree totale).

    La racine compte comme un dossier, sous le nom RACINE.
    """
    lignes = [(RACINE, compter(racine),
               sum(i["duree_ms"] for i in lister_sons(racine)))]
    for nom in lister_dossiers(racine):
        d = os.path.join(racine, nom)
        lignes.append((nom, compter(d),
                       sum(i["duree_ms"] for i in lister_sons(d))))
    return lignes


def duree_courte(ms):
    """3800 ms -> 3.8 s ; 95000 ms -> 1:35."""
    s = ms / 1000.0
    if s < 60:
        return "%.1f s" % s
    return "%d:%02d" % (int(s // 60), int(s % 60))


def taille_courte(octets):
    """Pour l'affichage : 1,2 Mo plutot que 1258291."""
    if octets < 1024:
        return "%d o" % octets
    if octets < 1024 * 1024:
        return "%.0f ko" % (octets / 1024.0)
    return "%.1f Mo" % (octets / (1024.0 * 1024.0))
