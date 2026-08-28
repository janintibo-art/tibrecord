"""Tests de la decoupe automatique. La prise de test est fabriquee :
on SAIT ou sont les frappes, la detection doit les retrouver."""

import math
import random
import time
import unittest

from noyau import audio, decoupe


def prise(positions_ms, duree_ms=4000.0, rate=44100, amplis=None,
          bruit=0.004, graine=7):
    """Une fausse prise de percussions : des frappes qui claquent aux
    positions donnees, un leger bruit de fond partout."""
    rnd = random.Random(graine)
    n = int(duree_ms * rate / 1000)
    data = [rnd.uniform(-bruit, bruit) for _ in range(n)]
    for k, pos in enumerate(positions_ms):
        a = int(pos * rate / 1000)
        ampli = amplis[k] if amplis else 0.8
        longueur = int(0.12 * rate)  # 120 ms de queue
        for i in range(longueur):
            if a + i >= n:
                break
            data[a + i] += (ampli * math.exp(-i / (longueur * 0.25))
                            * math.sin(i / 11.0))
    return audio.Sample(data, rate, "prise")


class TestDetection(unittest.TestCase):

    def test_dix_frappes_donnent_dix_segments(self):
        """Le geste fondateur du projet : dix coups, dix sons."""
        positions = [200.0 + k * 350.0 for k in range(10)]
        s = prise(positions)
        segs = decoupe.detecter_frappes(s)
        self.assertEqual(len(segs), 10,
                         "trouve %d segments : %s" % (len(segs), segs))

    def test_les_debuts_tombent_sur_les_frappes(self):
        positions = [300.0, 900.0, 1700.0]
        s = prise(positions)
        segs = decoupe.detecter_frappes(s)
        self.assertEqual(len(segs), 3)
        for (a, _b), pos in zip(segs, positions):
            self.assertLess(abs(a - pos), 25.0,
                            "debut %.0f ms pour une frappe a %.0f" % (a, pos))

    def test_le_debut_precede_la_frappe_jamais_l_inverse(self):
        """Le pre-roll doit GARDER l'attaque : commencer apres la
        frappe raboterait le caractere du son."""
        s = prise([500.0])
        (a, _b), = decoupe.detecter_frappes(s)
        self.assertLessEqual(a, 500.0)

    def test_une_frappe_faible_est_prise_en_sensibilite_haute(self):
        positions = [300.0, 1000.0, 1800.0]
        s = prise(positions, amplis=[0.8, 0.09, 0.8])
        basse = decoupe.detecter_frappes(s, sensibilite=0.1)
        haute = decoupe.detecter_frappes(s, sensibilite=0.95)
        self.assertLess(len(basse), 3)
        self.assertEqual(len(haute), 3)

    def test_le_niveau_d_enregistrement_ne_change_pas_les_coupes(self):
        """La meme prise, forte ou faible, doit donner le meme nombre
        de frappes : le seuil est relatif, pas absolu."""
        positions = [250.0, 950.0, 1600.0, 2400.0]
        fort = prise(positions)
        faible = audio.Sample([v * 0.12 for v in fort.data], fort.rate,
                              "faible")
        self.assertEqual(len(decoupe.detecter_frappes(fort)),
                         len(decoupe.detecter_frappes(faible)))

    def test_le_silence_ne_donne_aucune_frappe(self):
        s = audio.Sample([0.0] * 44100, 44100, "rien")
        self.assertEqual(decoupe.detecter_frappes(s), [])

    def test_le_bruit_seul_ne_donne_aucune_frappe(self):
        s = prise([], duree_ms=2000.0)
        self.assertEqual(decoupe.detecter_frappes(s), [])

    def test_segments_ordonnes_et_disjoints(self):
        s = prise([200.0 + k * 300.0 for k in range(8)])
        segs = decoupe.detecter_frappes(s)
        for k in range(1, len(segs)):
            self.assertLessEqual(segs[k - 1][1], segs[k][0] + 1e-6)
        for a, b in segs:
            self.assertLess(a, b)
            self.assertGreaterEqual(a, 0.0)
            self.assertLessEqual(b, s.duration_ms + 1e-6)


class TestExtraction(unittest.TestCase):

    def test_dix_frappes_dix_fichiers(self):
        positions = [200.0 + k * 350.0 for k in range(10)]
        s = prise(positions)
        sons = decoupe.decouper(s, decoupe.detecter_frappes(s))
        self.assertEqual(len(sons), 10)
        for son in sons:
            self.assertGreater(son.duration_ms, 50.0)
            self.assertLess(son.duration_ms, 600.0)

    def test_chaque_son_contient_sa_frappe(self):
        s = prise([400.0, 1200.0])
        sons = decoupe.decouper(s, decoupe.detecter_frappes(s))
        for son in sons:
            self.assertGreater(max(abs(v) for v in son.data), 0.3)

    def test_les_bords_sont_fondus(self):
        """Chaque fichier doit etre propre TOUT SEUL : il demarre et
        finit en douceur, pas en pleine oscillation."""
        s = prise([400.0])
        (son,) = decoupe.decouper(s, decoupe.detecter_frappes(s))
        self.assertLess(abs(son.data[0]), 0.02)
        self.assertLess(abs(son.data[-1]), 0.02)

    def test_l_original_n_est_pas_touche(self):
        s = prise([400.0, 1200.0])
        avant = list(s.data[:500])
        decoupe.decouper(s, decoupe.detecter_frappes(s))
        self.assertEqual(list(s.data[:500]), avant)


class TestBudget(unittest.TestCase):

    def test_trente_secondes_analysees_dans_le_budget(self):
        """Mesure, pas espoir : 30 s de prise doivent s'analyser assez
        vite pour la fenetre de patience, marge telephone comprise."""
        s = prise([300.0 + k * 700.0 for k in range(40)],
                  duree_ms=30000.0)
        t = time.perf_counter()
        segs = decoupe.detecter_frappes(s)
        cout = time.perf_counter() - t
        self.assertEqual(len(segs), 40)
        self.assertLess(cout, 1.5,
                        "%.2f s pour analyser 30 s de prise" % cout)


if __name__ == "__main__":
    unittest.main()
