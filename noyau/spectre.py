"""
Analyse en bandes de frequences, pour l'affichage du spectre.

Sorti de l'interface pour deux raisons. D'abord la meme analyse sert
deux fois : le spectre fige du son entier, et le spectre anime qui suit
la lecture. Ensuite elle devient testable : une sinusoide a 440 Hz doit
allumer la bande qui contient 440 Hz, et ca se verifie sans ecran.

L'algorithme est Goertzel : le calcul d'UNE frequence precise, la ou une
FFT calcule toutes. Pour dix-huit bandes sur une petite fenetre, c'est
moins de travail qu'une FFT en Python pur, et il n'y a aucune dependance.

Cout mesure : dix-huit bandes sur 1536 echantillons, environ 1 ms ici,
donc 5 a 10 ms sur telephone. A douze images par seconde, ca laisse de
la marge.
"""

import math

NB_BANDES = 18
F_MIN = 55.0
PLANCHER_DB = 52.0
FENETRE_LECTURE = 1536


def frequences(rate, nb=NB_BANDES, f_min=F_MIN):
    """Les centres de bandes, repartis en logarithme de 55 Hz au haut
    du spectre utile. C'est la repartition de l'oreille : une octave
    par a peu pres deux bandes, du grave a l'aigu."""
    f_max = min(16000.0, rate * 0.44)
    if nb < 2 or f_max <= f_min:
        return [f_min] * max(1, nb)
    return [f_min * ((f_max / f_min) ** (i / float(nb - 1)))
            for i in range(nb)]


def _goertzel(data, rate, freq):
    if not data or rate <= 0:
        return 0.0
    n = len(data)
    k = int(0.5 + n * freq / float(rate))
    omega = 2.0 * math.pi * k / float(n)
    coeff = 2.0 * math.cos(omega)
    q0 = q1 = q2 = 0.0
    for x in data:
        q0 = x + coeff * q1 - q2
        q2, q1 = q1, q0
    return max(q1 * q1 + q2 * q2 - coeff * q1 * q2, 1e-20)


def bandes(data, rate, nb=NB_BANDES):
    """Niveaux 0..1 de chaque bande pour un bloc d'echantillons.

    Fenetre de Hann puis Goertzel par bande, normalisation sur la bande
    la plus forte et plancher a -52 dB : exactement la mise a l'echelle
    de l'affichage fige, pour que le passage fige/anime ne saute pas.
    """
    bloc = list(data)
    if len(bloc) < 16:
        return [0.0] * nb
    # Un bloc silencieux doit donner des barres a zero : sans ce garde,
    # la normalisation sur le maximum amplifierait le bruit de fond en
    # un spectre plein, du silence affiche comme du fracas.
    crete = max(abs(v) for v in bloc)
    if crete < 1e-4:
        return [0.0] * nb
    den = max(1, len(bloc) - 1)
    for i in range(len(bloc)):
        bloc[i] *= 0.5 - 0.5 * math.cos(2.0 * math.pi * i / den)
    puissances = [_goertzel(bloc, rate, f) for f in frequences(rate, nb)]
    mx = max(puissances)
    vals = []
    for p in puissances:
        db = 10.0 * math.log10(max(p / mx, 1e-12))
        vals.append(max(0.0, min(1.0, (db + PLANCHER_DB) / PLANCHER_DB)))
    return vals


def bandes_du_sample(sample, nb=NB_BANDES, taille=3072):
    """Spectre du milieu du son : la vue figee de l'editeur."""
    if sample is None or not sample.data or not sample.rate:
        return [0.0] * nb
    n = min(taille, len(sample.data))
    centre = len(sample.data) // 2
    debut = max(0, centre - n // 2)
    return bandes(sample.data[debut:debut + n], sample.rate, nb)


def bandes_a_la_position(sample, fraction, nb=NB_BANDES,
                         taille=FENETRE_LECTURE):
    """Spectre autour d'un point du son : la vue qui suit la lecture.

    La fenetre est centree sur la position, plus courte que la vue
    figee : pendant la lecture on veut voir les coups arriver, pas une
    moyenne qui les etale.
    """
    if sample is None or not sample.data or not sample.rate:
        return [0.0] * nb
    n = len(sample.data)
    centre = int(max(0.0, min(1.0, fraction)) * n)
    demi = min(taille, n) // 2
    debut = max(0, min(centre - demi, n - 2 * demi))
    return bandes(sample.data[debut:debut + 2 * demi], sample.rate, nb)


def lisser(anciennes, nouvelles, retombee=0.72):
    """Montee immediate, descente amortie.

    C'est ce qui fait qu'un spectre a l'air vivant : les barres sautent
    sur le coup puis retombent doucement, comme les aiguilles d'un vrai
    vu-metre. Sans lissage, l'affichage papillote.
    """
    if not anciennes or len(anciennes) != len(nouvelles):
        return list(nouvelles)
    return [max(n, a * retombee) for a, n in zip(anciennes, nouvelles)]
