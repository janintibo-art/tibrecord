"""
Effets audio : delai, reverberation, tremolo, bit-crusher, vari-speed,
inversions.

Chaque effet est une fonction pure : elle recoit un Sample, renvoie un
NOUVEAU Sample, et ne modifie jamais l'original. C'est ce qui rend
l'apercu sans danger et l'annulation triviale.

Le CATALOGUE en bas decrit chaque effet pour l'interface : nom, molettes
(borne basse, borne haute, valeur de depart), et texte d'aide. L'ecran
se construit a partir de ce catalogue : ajouter un effet ici suffit a le
faire apparaitre dans l'application.

Tout est en Python pur, donc lent par nature : ces fonctions sont faites
pour tourner dans le fil de fond (noyau/travail.py), jamais sur le fil
d'interface.
"""

import math

from .audio import Sample


def _borner(data):
    """Ramene tout dans -1..1. Un effet ne doit jamais rendre un signal
    qui sature l'ecriture WAV derriere lui."""
    return [max(-1.0, min(1.0, v)) for v in data]


# ------------------------------------------------------------------ delai
def delai(sample, temps_ms=300.0, reinjection=0.35, mix=0.35):
    """Echo : le son revient apres `temps_ms`, de plus en plus faible.

    `reinjection` regle combien chaque echo nourrit le suivant, `mix` la
    part d'effet dans le resultat. La sortie est rallongee de la queue
    des echos, jusqu'a ce qu'ils tombent sous -60 dB.
    """
    rate = sample.rate
    n = len(sample.data)
    retard = max(1, int(temps_ms * rate / 1000.0))
    reinjection = max(0.0, min(0.95, reinjection))
    mix = max(0.0, min(1.0, mix))
    # Combien d'echos avant -60 dB ? C'est la longueur de la queue.
    if reinjection > 1e-3:
        echos = int(math.log(0.001) / math.log(reinjection)) + 1
    else:
        echos = 1
    total = n + retard * echos
    ligne = [0.0] * total
    for i, v in enumerate(sample.data):
        ligne[i] = v
    # La ligne a retard se reinjecte : chaque passage ajoute l'echo du
    # precedent, y compris des echos deja ajoutes.
    for i in range(retard, total):
        ligne[i] += ligne[i - retard] * reinjection
    sec = 1.0 - mix
    out = [0.0] * total
    for i in range(total):
        v = sample.data[i] if i < n else 0.0
        out[i] = v * sec + (ligne[i] - v) * mix
    return Sample(_borner(out), rate, sample.name)


# ----------------------------------------------------------------- reverbe
# Reverberation de Schroeder : quatre filtres en peigne en parallele,
# deux passe-tout en serie. C'est LA reverberation algorithmique
# historique : simple, previsible, et honnete pour une piece.
_PEIGNES_MS = (29.7, 37.1, 41.1, 43.7)
_PASSE_TOUT_MS = (5.0, 1.7)


def _peigne(data, retard, gain):
    out = [0.0] * len(data)
    for i in range(len(data)):
        v = data[i]
        if i >= retard:
            v += out[i - retard] * gain
        out[i] = v
    return out


def _passe_tout(data, retard, gain=0.5):
    out = [0.0] * len(data)
    for i in range(len(data)):
        x = data[i]
        y = -gain * x
        if i >= retard:
            y += data[i - retard] + gain * out[i - retard]
        out[i] = y
    return out


def reverbe(sample, taille=0.5, mix=0.3):
    """Reverberation de piece. `taille` 0..1 : du placard a la salle.

    La sortie est rallongee de la queue de reverberation, qui grandit
    avec la taille.
    """
    rate = sample.rate
    taille = max(0.0, min(1.0, taille))
    mix = max(0.0, min(1.0, mix))
    queue = int(rate * (0.25 + 1.25 * taille))
    data = list(sample.data) + [0.0] * queue
    gain = 0.72 + 0.20 * taille
    som = [0.0] * len(data)
    for ms in _PEIGNES_MS:
        retard = max(1, int(ms * (0.7 + 0.9 * taille) * rate / 1000.0))
        p = _peigne(data, retard, gain)
        for i in range(len(som)):
            som[i] += p[i]
    for i in range(len(som)):
        som[i] *= 0.25
    for ms in _PASSE_TOUT_MS:
        som = _passe_tout(som, max(1, int(ms * rate / 1000.0)))
    n = len(sample.data)
    sec = 1.0 - mix
    out = [0.0] * len(data)
    for i in range(len(data)):
        v = sample.data[i] if i < n else 0.0
        out[i] = v * sec + som[i] * mix
    return Sample(_borner(out), rate, sample.name)


# ----------------------------------------------------------------- tremolo
def tremolo(sample, vitesse_hz=5.0, profondeur=0.6):
    """Le volume ondule a `vitesse_hz`. Profondeur 1 : jusqu'au silence."""
    rate = sample.rate
    profondeur = max(0.0, min(1.0, profondeur))
    omega = 2.0 * math.pi * max(0.05, vitesse_hz) / rate
    out = [v * (1.0 - profondeur * (0.5 + 0.5 * math.sin(omega * i)))
           for i, v in enumerate(sample.data)]
    return Sample(out, rate, sample.name)


# --------------------------------------------------------------- bitcrush
def bitcrush(sample, bits=8, reduction_taux=1):
    """Lo-fi : moins de bits, et un echantillon garde sur `reduction_taux`.

    Huit bits sonnent 'vieille console' ; quatre, 'telephone casse'.
    """
    bits = max(2, min(16, int(bits)))
    pas = max(1, int(reduction_taux))
    niveaux = float(2 ** (bits - 1))
    out = [0.0] * len(sample.data)
    tenu = 0.0
    for i, v in enumerate(sample.data):
        if i % pas == 0:
            tenu = round(v * niveaux) / niveaux
        out[i] = tenu
    return Sample(_borner(out), sample.rate, sample.name)


# --------------------------------------------------------------- varispeed
def varispeed(sample, facteur=1.0):
    """La bande magnetique : hauteur et duree liees.

    facteur 2.0 : une octave plus haut, deux fois plus court.
    facteur 0.5 : une octave plus bas, deux fois plus long.
    Interpolation lineaire : suffisante a l'oreille pour cet usage.
    """
    facteur = max(0.25, min(4.0, float(facteur)))
    n = len(sample.data)
    if n < 2 or abs(facteur - 1.0) < 1e-9:
        return Sample(list(sample.data), sample.rate, sample.name)
    sortie = int(n / facteur)
    out = [0.0] * sortie
    for i in range(sortie):
        pos = i * facteur
        j = int(pos)
        frac = pos - j
        if j + 1 < n:
            out[i] = sample.data[j] * (1.0 - frac) + \
                sample.data[j + 1] * frac
        else:
            out[i] = sample.data[min(j, n - 1)]
    return Sample(out, sample.rate, sample.name)


# --------------------------------------------------------------- inversions
def inverser(sample):
    """Le son a l'envers, du dernier echantillon au premier."""
    return Sample(list(reversed(sample.data)), sample.rate, sample.name)


def polarite(sample):
    """Miroir vertical : chaque valeur change de signe.

    Inaudible seul, mais decisif pour aligner deux prises qui
    s'annulent, ou preparer un crossfade propre.
    """
    return Sample([-v for v in sample.data], sample.rate, sample.name)


# ---------------------------------------------------------------- catalogue
# nom -> description, parametres [(cle, titre, mini, maxi, defaut,
# unite, decimales)], fonction(sample, **params)
CATALOGUE = (
    ("Delai", {
        "desc": "Echo qui se repete et s'eteint.",
        "params": [("temps_ms", "Temps", 40.0, 900.0, 300.0, " ms", 0),
                   ("reinjection", "Repet.", 0.0, 0.9, 0.35, "", 2),
                   ("mix", "Mix", 0.0, 1.0, 0.35, "", 2)],
        "fonction": delai,
    }),
    ("Reverbe", {
        "desc": "Une piece autour du son, du placard a la salle.",
        "params": [("taille", "Taille", 0.0, 1.0, 0.5, "", 2),
                   ("mix", "Mix", 0.0, 1.0, 0.3, "", 2)],
        "fonction": reverbe,
    }),
    ("Tremolo", {
        "desc": "Le volume ondule, comme un ampli d'epoque.",
        "params": [("vitesse_hz", "Vitesse", 0.5, 14.0, 5.0, " Hz", 1),
                   ("profondeur", "Prof.", 0.0, 1.0, 0.6, "", 2)],
        "fonction": tremolo,
    }),
    ("Bitcrush", {
        "desc": "Lo-fi : moins de bits, son de vieille console.",
        "params": [("bits", "Bits", 2, 16, 8, "", 0),
                   ("reduction_taux", "Reduc.", 1, 16, 1, "x", 0)],
        "fonction": bitcrush,
    }),
    ("Vari-speed", {
        "desc": "La bande : plus vite = plus aigu et plus court.",
        "params": [("facteur", "Vitesse", 0.25, 4.0, 1.0, "x", 2)],
        "fonction": varispeed,
    }),
    ("Inversion", {
        "desc": "Le son a l'envers.",
        "params": [],
        "fonction": inverser,
    }),
    ("Polarite", {
        "desc": "Miroir vertical du signal, pour aligner deux prises.",
        "params": [],
        "fonction": polarite,
    }),
)


def par_nom(nom):
    """L'entree du catalogue, ou None."""
    for n, e in CATALOGUE:
        if n == nom:
            return e
    return None


def appliquer(nom, sample, **params):
    """Applique l'effet `nom` avec ses parametres. Leve si inconnu :
    un nom d'effet faux est un bug d'interface, pas un cas d'usage."""
    entree = par_nom(nom)
    if entree is None:
        raise ValueError("effet inconnu : %s" % nom)
    return entree["fonction"](sample, **params)
