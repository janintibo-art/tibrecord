"""
Graduations de temps : choix du pas et mise en forme.

Sorti de l'affichage exprès. Ces deux fonctions decident de ce qu'on
lit sous la forme d'onde, c'est-a-dire de la precision avec laquelle on
peut couper. Elles doivent donc etre testables sans Kivy et sans ecran.
"""

import math


def pas_lisible(duree_ms, cibles=6):
    """Choisit un pas de graduation rond pour la duree visible.

    On ne veut pas de reperes a 0,37 s : l'oeil ne s'en sert pas. On
    prend dans la suite 1, 2, 5, 10, 20, 50... le pas qui donne a peu
    pres le nombre de reperes voulu.
    """
    if duree_ms <= 0:
        return 1.0
    cibles = max(1, int(cibles))
    brut = duree_ms / float(cibles)
    magnitude = 10.0 ** math.floor(math.log10(brut))
    for mult in (1, 2, 5):
        pas = magnitude * mult
        if pas >= brut:
            return pas
    return magnitude * 10


def decimales(pas_ms):
    """Nombre de chiffres apres la virgule qui a un sens pour ce pas."""
    if pas_ms >= 1000:
        return 0
    if pas_ms >= 100:
        return 1
    if pas_ms >= 10:
        return 2
    if pas_ms >= 1:
        return 3
    return 4


def horloge_precise(ms, total_ms=None):
    """Compteur de lecture : m:ss.mmm, toujours au meme nombre de
    chiffres pour que l'affichage ne saute pas d'un dixieme a l'autre.

    Avec total_ms, renvoie "0:01.234 / 0:02.975".
    """
    def _un(v):
        v = max(0.0, v) / 1000.0
        m = int(v // 60)
        return "%d:%06.3f" % (m, v - m * 60)
    if total_ms is None:
        return _un(ms)
    return "%s / %s" % (_un(ms), _un(total_ms))


def etiquette_temps(ms, pas_ms):
    """Format adapte au pas ET a la position dans le son.

    Deux pieges evites ici : afficher des millisecondes quand les
    reperes sont espaces de dix secondes, et afficher "185000 ms" quand
    on zoome fort a trois minutes du debut.
    """
    deci = decimales(pas_ms)
    s = ms / 1000.0
    if s >= 60:
        m = int(s // 60)
        reste = s - m * 60
        if deci == 0:
            return "%d:%02d" % (m, int(round(reste)))
        return "%d:%0*.*f" % (m, deci + 3, deci, reste)
    return "%.*f s" % (deci, s)


def graduations(debut_ms, fin_ms, cibles=6):
    """Liste des instants a graduer entre debut et fin, pas compris.

    Renvoie (temps_ms, etiquette) pour chaque repere visible.
    """
    visible = fin_ms - debut_ms
    if visible <= 0:
        return []
    pas = pas_lisible(visible, cibles)
    premier = math.floor(debut_ms / pas) * pas
    reperes = []
    t = premier
    # Garde-fou : une fenetre absurde ne doit pas figer l'affichage.
    for _ in range(10000):
        if t > fin_ms + pas * 0.001:
            break
        if t >= debut_ms - pas * 0.001:
            reperes.append((t, etiquette_temps(t, pas)))
        t += pas
    return reperes


def sous_graduations(debut_ms, fin_ms, cibles=6, divisions=5):
    """Petits traits entre deux reperes chiffres.

    Sans eux on ne lit que "1 s" et "2 s", et l'oeil doit deviner le
    milieu. Avec quatre traits intermediaires, on situe un point au
    cinquieme de seconde sans calculer.
    """
    visible = fin_ms - debut_ms
    if visible <= 0:
        return []
    pas = pas_lisible(visible, cibles) / float(max(2, divisions))
    premier = math.floor(debut_ms / pas) * pas
    petits = []
    t = premier
    for _ in range(10000):
        if t > fin_ms + pas * 0.001:
            break
        if t >= debut_ms - pas * 0.001:
            petits.append(t)
        t += pas
    return petits
