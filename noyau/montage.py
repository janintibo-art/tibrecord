"""
Montage : couper, copier, coller, supprimer, boucler.

Le piege du montage numerique tient en un mot : le CLIC. Couper un son
en plein milieu d'une oscillation cree une marche dans le signal, et
cette marche s'entend comme un claquement sec. Toutes les jointures de
ce module sont donc faites en fondu enchaine de quelques millisecondes :
la fin d'un morceau s'eteint pendant que le debut du suivant s'allume.

Toutes les fonctions sont pures : elles recoivent un Sample, renvoient
du neuf, et ne modifient jamais l'original. Les positions sont en
millisecondes, bornees d'office : demander plus long que le son n'est
pas une erreur, c'est "jusqu'au bout".
"""

from .audio import Sample

FONDU_MS = 6.0


def _bornes(sample, a_ms, b_ms):
    """Convertit et assainit : a <= b, dans le son."""
    n = len(sample.data)
    rate = sample.rate
    a = int(min(a_ms, b_ms) * rate / 1000.0)
    b = int(max(a_ms, b_ms) * rate / 1000.0)
    return max(0, min(a, n)), max(0, min(b, n))


def _joindre(gauche, droite, rate, fondu_ms=FONDU_MS):
    """Colle deux bouts avec un fondu enchaine sur la jointure.

    Les `k` derniers echantillons de gauche et les `k` premiers de
    droite se recouvrent : l'un descend pendant que l'autre monte.
    C'est ce recouvrement qui remplace la marche par une pente.
    """
    k = int(fondu_ms * rate / 1000.0)
    k = min(k, len(gauche), len(droite))
    if k <= 0:
        return list(gauche) + list(droite)
    out = list(gauche[:len(gauche) - k])
    for i in range(k):
        t = (i + 1) / float(k + 1)
        out.append(gauche[len(gauche) - k + i] * (1.0 - t)
                   + droite[i] * t)
    out.extend(droite[k:])
    return out


def copier(sample, a_ms, b_ms):
    """La portion, telle quelle. Le presse-papiers du montage."""
    a, b = _bornes(sample, a_ms, b_ms)
    return Sample(list(sample.data[a:b]), sample.rate, sample.name)


def supprimer(sample, a_ms, b_ms, fondu_ms=FONDU_MS):
    """Le son sans la portion, jointure fondue.

    Refuse de tout supprimer : un son vide casserait tout ce qui suit
    (affichage, lecture, sauvegarde) pour un geste qui etait presque
    surement une erreur de selection.
    """
    a, b = _bornes(sample, a_ms, b_ms)
    if a >= b:
        return Sample(list(sample.data), sample.rate, sample.name)
    if a <= 0 and b >= len(sample.data):
        raise ValueError("la selection couvre tout le son : "
                         "rien ne resterait")
    data = _joindre(sample.data[:a], sample.data[b:], sample.rate,
                    fondu_ms)
    return Sample(data, sample.rate, sample.name)


def couper(sample, a_ms, b_ms, fondu_ms=FONDU_MS):
    """Supprime ET renvoie la portion : (reste, portion)."""
    portion = copier(sample, a_ms, b_ms)
    reste = supprimer(sample, a_ms, b_ms, fondu_ms)
    return reste, portion


def inserer(sample, position_ms, morceau, fondu_ms=FONDU_MS):
    """Insere `morceau` a la position, les deux jointures fondues."""
    if not morceau.data:
        return Sample(list(sample.data), sample.rate, sample.name)
    n = len(sample.data)
    p = max(0, min(int(position_ms * sample.rate / 1000.0), n))
    gauche = _joindre(sample.data[:p], morceau.data, sample.rate,
                      fondu_ms)
    data = _joindre(gauche, sample.data[p:], sample.rate, fondu_ms)
    return Sample(data, sample.rate, sample.name)


def boucler(sample, a_ms, b_ms, fois=2, fondu_ms=FONDU_MS):
    """La portion repetee `fois` fois, jointures fondues.

    C'est l'outil qui transforme deux secondes propres en un motif :
    on selectionne le passage, on boucle, on ecoute si ca tourne rond.
    """
    fois = max(1, min(64, int(fois)))
    portion = copier(sample, a_ms, b_ms)
    if not portion.data:
        return portion
    data = list(portion.data)
    for _ in range(fois - 1):
        data = _joindre(data, portion.data, sample.rate, fondu_ms)
    return Sample(data, sample.rate, sample.name)


def marche_maximale(data, autour=None, largeur=64):
    """La plus grande difference entre deux echantillons voisins.

    C'est LA mesure du clic : une jointure propre garde cette marche du
    meme ordre que le signal, une coupe brute la fait sauter. Sert aux
    tests, et a rien d'autre — mais c'est elle qui prouve que le fondu
    fait son travail.
    """
    if autour is None:
        debut, fin = 1, len(data)
    else:
        debut = max(1, autour - largeur)
        fin = min(len(data), autour + largeur)
    pire = 0.0
    for i in range(debut, fin):
        saut = abs(data[i] - data[i - 1])
        if saut > pire:
            pire = saut
    return pire
