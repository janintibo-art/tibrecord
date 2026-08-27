"""
Ou sont les fichiers sur Android, et lesquels on a le droit de lire.

Depuis Android 10, une application ne lit plus librement le telephone.
Trois generations de permissions coexistent et un meme code se comporte
differemment selon l'appareil. Ce module regroupe ce qui peut se decider
sans Kivy et sans Android, pour que la logique soit testable.

La regle qui a regle le probleme sur le projet precedent, et qu'on garde
ici : **lire depuis n'importe ou, ecrire chez soi.** Le dossier prive de
l'application est le seul endroit ou l'ecriture est garantie, quelle que
soit la version d'Android et le constructeur.
"""

import os

IS_ANDROID = "ANDROID_ARGUMENT" in os.environ

# Volumes qui ne sont pas des cartes SD, malgre leur presence dans
# /storage. Les ecarter evite de proposer des raccourcis morts.
PAS_DES_CARTES = {"emulated", "self", "container", "sdcard0", "knox-emulated"}


def dossier_prive():
    """Le dossier de l'application : ecriture toujours permise.

    ANDROID_PRIVATE pointe vers /data/user/0/<paquet>/files. Invisible
    depuis un gestionnaire de fichiers, mais toujours accessible.
    """
    if IS_ANDROID:
        return os.environ.get("ANDROID_PRIVATE") or "/sdcard/Download"
    return os.getcwd()


def lisible(chemin):
    """Le dossier existe-t-il ET peut-on en lister le contenu ?

    os.path.isdir() ne suffit pas : un dossier peut exister et refuser
    d'etre lu. C'est le cas courant depuis Android 11.
    """
    try:
        os.listdir(chemin)
        return True
    except Exception:  # noqa: BLE001
        return False


def inscriptible(chemin):
    """Sonde l'ecriture avec un vrai fichier du type vise.

    Le refus arrive parfois au dernier moment : creer le dossier reussit,
    ecrire un fichier sans extension reussit, et le .wav echoue. Un test
    naif donne donc un faux positif ; on ecrit donc un vrai petit WAV.
    """
    temoin = os.path.join(chemin, "_test_ecriture_tibrecord.wav")
    try:
        with open(temoin, "wb") as f:
            f.write(b"RIFF\x00\x00\x00\x00WAVE")
        os.remove(temoin)
        return True
    except Exception:  # noqa: BLE001
        try:
            os.remove(temoin)
        except Exception:  # noqa: BLE001
            pass
        return False


def cartes_sd():
    """Volumes amovibles montes, du type /storage/XXXX-XXXX."""
    out = []
    for base in ("/storage", "/mnt/media_rw"):
        try:
            noms = sorted(os.listdir(base))
        except Exception:  # noqa: BLE001
            continue
        for n in noms:
            if n in PAS_DES_CARTES or n.startswith("."):
                continue
            chemin = os.path.join(base, n)
            if os.path.isdir(chemin) and chemin not in [c for _, c in out]:
                out.append(("Carte SD", chemin))
    return out


def raccourcis():
    """Endroits utiles du telephone, detectes et jamais codes en dur.

    Renvoie (nom, chemin, lisible). On garde les dossiers illisibles dans
    la liste : les griser previent avant l'echec, alors que les cacher
    laisse croire qu'ils n'existent pas.
    """
    out = []
    vus = set()

    def ajouter(nom, chemin):
        if not chemin or chemin in vus:
            return
        if os.path.isdir(chemin):
            vus.add(chemin)
            out.append((nom, chemin, lisible(chemin)))

    ajouter("Mes sons", os.path.join(dossier_prive(), "enregistrements"))
    if IS_ANDROID:
        for nom, sous in (("Telechargements", "Download"),
                          ("Musique", "Music"),
                          ("Documents", "Documents"),
                          ("Enregistrements", "Recordings")):
            ajouter(nom, os.path.join("/sdcard", sous))
        ajouter("Stockage interne", "/sdcard")
    else:
        maison = os.path.expanduser("~")
        for nom, sous in (("Telechargements", "Downloads"),
                          ("Musique", "Music"),
                          ("Documents", "Documents")):
            ajouter(nom, os.path.join(maison, sous))
        ajouter("Dossier personnel", maison)
    for nom, chemin in cartes_sd():
        ajouter(nom, chemin)
    return out


# ------------------------------------------------------------ acces complet
def version_android():
    """Numero d'API Android, ou 0 hors Android."""
    if not IS_ANDROID:
        return 0
    try:
        from jnius import autoclass
        return int(autoclass("android.os.Build$VERSION").SDK_INT)
    except Exception:  # noqa: BLE001
        return 0


def acces_complet():
    """L'application a-t-elle l'acces a tous les fichiers ?

    Avant Android 11 la question ne se pose pas : les permissions
    ordinaires suffisent, donc on repond oui.
    """
    if not IS_ANDROID:
        return True
    if version_android() < 30:
        return True
    try:
        from jnius import autoclass
        return bool(autoclass("android.os.Environment")
                    .isExternalStorageManager())
    except Exception:  # noqa: BLE001
        return False


def demander_acces_complet():
    """Ouvre l'ecran systeme ou l'utilisateur bascule l'interrupteur.

    Cette permission ne s'accorde PAS par une boite de dialogue
    ordinaire : c'est la raison pour laquelle elle etait declaree dans
    le manifeste sans jamais etre accordee.

    Renvoie un message a afficher, jamais une exception : echouer a
    ouvrir un ecran de reglages ne doit pas arreter l'application.
    """
    if not IS_ANDROID:
        return "Hors Android : rien a demander."
    if version_android() < 30:
        return "Android %d : les permissions ordinaires suffisent." % \
            version_android()
    if acces_complet():
        return "Acces a tous les fichiers deja accorde."
    try:
        from jnius import autoclass
        Intent = autoclass("android.content.Intent")
        Settings = autoclass("android.provider.Settings")
        Uri = autoclass("android.net.Uri")
        activite = autoclass("org.kivy.android.PythonActivity").mActivity
        intent = Intent(
            Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION,
            Uri.parse("package:" + activite.getPackageName()))
        activite.startActivity(intent)
        return ("Ecran systeme ouvert : active l'interrupteur, "
                "puis reviens dans Tibrecord.")
    except Exception as e:  # noqa: BLE001
        return "Impossible d'ouvrir l'ecran systeme : %s" % e


def diagnostic():
    """Etat complet de l'acces, en clair.

    Mesurer avant de corriger : sans ce releve, toute correction se fait
    a l'aveugle et on essaie trois hypotheses au hasard.
    """
    lignes = []
    api = version_android()
    lignes.append("Android : %s" % ("API %d" % api if api else "non (bureau)"))
    lignes.append("Acces a tous les fichiers : %s"
                  % ("OUI" if acces_complet() else "NON"))
    prive = dossier_prive()
    lignes.append("Dossier de l'application : %s" % prive)
    lignes.append("  lecture %s, ecriture %s"
                  % ("OK" if lisible(prive) else "REFUSEE",
                     "OK" if inscriptible(prive) else "REFUSEE"))
    lignes.append("")
    lignes.append("Raccourcis :")
    for nom, chemin, ok in raccourcis():
        lignes.append("  %-18s %-28s %s"
                      % (nom, chemin, "lisible" if ok else "REFUSE"))
    cartes = cartes_sd()
    lignes.append("")
    if cartes:
        lignes.append("Volumes amovibles :")
        for nom, chemin in cartes:
            lignes.append("  %s %s : %s"
                          % (nom, chemin,
                             "lisible" if lisible(chemin) else "REFUSE"))
    else:
        lignes.append("Aucun volume amovible detecte.")
    if api >= 30 and not acces_complet():
        lignes.append("")
        lignes.append("Beaucoup de dossiers seront refuses tant que")
        lignes.append("l'acces a tous les fichiers n'est pas accorde.")
        lignes.append("Utilise le bouton ACCES FICHIERS.")
    return "\n".join(lignes)
