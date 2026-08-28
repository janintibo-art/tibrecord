"""
Decoupe automatique : trouver les frappes dans une prise, et en faire
des sons separes.

C'est le geste pour lequel ce projet existe : enregistrer dix coups de
percussion d'affilee, et repartir avec dix fichiers propres, sans poser
vingt fois les poignees a la main.

La methode, en trois temps :

1. L'ENVELOPPE : le son est resume en une valeur de crete toutes les
   huit millisecondes. Trois mille points pour trente secondes, au lieu
   d'un million trois cent mille echantillons.

2. LE PLANCHER : le bruit de fond est estime sur l'enveloppe elle-meme
   (vingtieme centile). Le seuil de detection est place ENTRE ce
   plancher et la crete la plus forte, regle par la sensibilite. C'est
   ce qui rend la detection independante du niveau d'enregistrement :
   une prise faible et une prise forte donnent les memes coupes.

3. L'HYSTERESE : une frappe commence quand l'enveloppe DEPASSE le seuil
   haut, et ne finit que quand elle reste SOUS le seuil bas assez
   longtemps. Sans ce double seuil, chaque tremblement de la queue d'un
   kick declencherait une fausse frappe.
"""

from .audio import Sample

FENETRE_MS = 8.0
PRE_MS = 10.0
SILENCE_MS = 90.0
ECART_MIN_MS = 60.0
FONDU_MS = 4.0


def enveloppe(data, rate, fenetre_ms=FENETRE_MS):
    """Crete par fenetre : le resume du son, trois mille fois plus
    court que lui."""
    fen = max(8, int(fenetre_ms * rate / 1000.0))
    out = []
    for i in range(0, max(0, len(data) - fen + 1), fen):
        bloc = data[i:i + fen]
        out.append(max(abs(v) for v in bloc))
    return out


def _percentile(valeurs, part):
    tri = sorted(valeurs)
    if not tri:
        return 0.0
    return tri[min(len(tri) - 1, int(part * (len(tri) - 1)))]


def detecter_frappes(sample, sensibilite=0.5, silence_ms=SILENCE_MS,
                     pre_ms=PRE_MS, ecart_min_ms=ECART_MIN_MS):
    """Les frappes de la prise : liste de (debut_ms, fin_ms).

    sensibilite 0..1 : basse, seules les frappes franches ; haute, les
    coups faibles aussi. Le pre_ms recule chaque debut de quelques
    millisecondes pour ne pas raboter l'attaque, la partie du son qui
    fait le caractere d'une percussion.
    """
    rate = sample.rate
    env = enveloppe(sample.data, rate)
    if not env:
        return []
    fen_ms = FENETRE_MS
    plancher = _percentile(env, 0.20)
    crete = max(env)
    # Une frappe, c'est quelque chose qui DEPASSE nettement le bruit.
    # Sans cette exigence de dynamique, une prise de bruit seul se
    # decoupe en dizaines de fausses frappes : le seuil, place dans les
    # fluctuations du bruit, se fait franchir en permanence.
    if crete < plancher * 3.0 or crete <= plancher + 1e-6:
        return []
    sensibilite = max(0.0, min(1.0, sensibilite))
    # Sensibilite haute -> seuil pres du plancher, pour attraper les
    # coups faibles ; basse -> pres de la crete, frappes franches
    # seulement.
    haut = plancher + (crete - plancher) * (0.65 - 0.62 * sensibilite)
    bas = plancher + (haut - plancher) * 0.45
    silence_fen = max(1, int(silence_ms / fen_ms))
    ecart_min_fen = max(1, int(ecart_min_ms / fen_ms))

    segments = []
    i, n = 0, len(env)
    dernier_debut = -ecart_min_fen
    while i < n:
        if env[i] > haut and i - dernier_debut >= ecart_min_fen:
            debut = i
            dernier_debut = i
            # avancer jusqu'au vrai silence : sous le seuil bas pendant
            # silence_fen fenetres d'affilee
            j = i + 1
            calme = 0
            while j < n:
                if env[j] > haut and j - debut >= ecart_min_fen:
                    break  # la frappe suivante commence : on coupe la
                calme = calme + 1 if env[j] < bas else 0
                if calme >= silence_fen:
                    break
                j += 1
            fin = j if calme < silence_fen else j - silence_fen + 1
            a_ms = max(0.0, debut * fen_ms - pre_ms)
            b_ms = min(sample.duration_ms, (fin + 1) * fen_ms)
            if b_ms - a_ms >= fen_ms:
                segments.append((a_ms, b_ms))
            # REARMEMENT STRICT : pas de nouvelle frappe tant que
            # l'enveloppe n'est pas redescendue sous le seuil bas, sans
            # aucune exception. La queue d'un coup ondule autour du
            # seuil haut ; toute porte de sortie ici la transforme en
            # fausse deuxieme frappe. Deux coups si serres qu'ils se
            # touchent sans redescendre forment UN son : c'est le bon
            # decoupage pour un roulement.
            i = j
            while i < n and env[i] >= bas:
                i += 1
        else:
            i += 1
    return segments


def extraire(sample, a_ms, b_ms, fondu_ms=FONDU_MS):
    """Un segment, avec un micro-fondu aux deux bouts.

    Chaque fichier decoupe doit etre propre TOUT SEUL : s'il demarre en
    pleine oscillation, il cliquera dans le sampler qui le rejouera.
    """
    rate = sample.rate
    a = max(0, int(a_ms * rate / 1000.0))
    b = min(len(sample.data), int(b_ms * rate / 1000.0))
    data = list(sample.data[a:b])
    k = min(int(fondu_ms * rate / 1000.0), len(data) // 2)
    for i in range(k):
        t = (i + 1) / float(k + 1)
        data[i] *= t
        data[len(data) - 1 - i] *= t
    return Sample(data, rate, sample.name)


def decouper(sample, segments, fondu_ms=FONDU_MS):
    """Tous les segments, extraits et fondus, dans l'ordre."""
    return [extraire(sample, a, b, fondu_ms) for a, b in segments]
