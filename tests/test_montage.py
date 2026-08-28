"""Tests du montage. Le test central est celui du CLIC : une coupe
brute fait sauter le signal, une jointure fondue non. On le mesure au
lieu de l'ecouter."""

import math
import unittest

from noyau import audio, montage


def deux_plateaux(rate=44100, ms=200.0):
    """Moitie a +0,5, moitie a -0,5 : la coupe la plus clicante
    possible, faite expres pour piéger une jointure."""
    n = int(ms * rate / 1000)
    data = [0.5] * (n // 2) + [-0.5] * (n - n // 2)
    return audio.Sample(data, rate, "plateaux")


def sinus(freq=440.0, ms=300.0, rate=44100):
    n = int(ms * rate / 1000)
    return audio.Sample(
        [0.6 * math.sin(2 * math.pi * freq * i / rate) for i in range(n)],
        rate, "sinus")


class TestClic(unittest.TestCase):
    """La raison d'etre du module."""

    def test_la_coupe_brute_clique_et_la_jointure_fondue_non(self):
        s = deux_plateaux()
        n = len(s.data)
        # coupe brute : on retire le quart central sans fondu
        brute = s.data[:3 * n // 8] + s.data[5 * n // 8:]
        saut_brut = montage.marche_maximale(brute, autour=3 * n // 8)
        # meme coupe, jointure fondue
        duree = s.duration_ms
        propre = montage.supprimer(s, duree * 3 / 8, duree * 5 / 8)
        saut_propre = montage.marche_maximale(propre.data,
                                              autour=3 * n // 8)
        self.assertGreater(saut_brut, 0.9, "le piege ne piege plus")
        self.assertLess(saut_propre, 0.25,
                        "la jointure clique : saut %.2f" % saut_propre)

    def test_l_insertion_ne_clique_pas_non_plus(self):
        s = deux_plateaux()
        morceau = audio.Sample([0.5] * 2000, s.rate, "bout")
        out = montage.inserer(s, s.duration_ms * 0.75, morceau)
        p = int(len(s.data) * 0.75)
        self.assertLess(montage.marche_maximale(out.data, autour=p), 0.25)


class TestCopierSupprimer(unittest.TestCase):

    def test_copier_prend_la_bonne_portion(self):
        s = sinus()
        out = montage.copier(s, 100.0, 200.0)
        self.assertAlmostEqual(out.duration_ms, 100.0, delta=1.0)
        a = int(100.0 * s.rate / 1000)
        self.assertEqual(out.data[0], s.data[a])

    def test_supprimer_retire_la_bonne_duree(self):
        s = sinus(ms=300.0)
        out = montage.supprimer(s, 100.0, 200.0)
        self.assertAlmostEqual(out.duration_ms, 200.0, delta=8.0)

    def test_bornes_inversees_acceptees(self):
        s = sinus()
        a = montage.copier(s, 200.0, 100.0)
        b = montage.copier(s, 100.0, 200.0)
        self.assertEqual(a.data, b.data)

    def test_bornes_hors_du_son_ramenees_dedans(self):
        s = sinus(ms=100.0)
        out = montage.copier(s, -50.0, 900.0)
        self.assertEqual(len(out.data), len(s.data))

    def test_tout_supprimer_est_refuse(self):
        s = sinus(ms=100.0)
        with self.assertRaises(ValueError):
            montage.supprimer(s, 0.0, 100.0)

    def test_l_original_jamais_touche(self):
        s = sinus()
        avant = list(s.data)
        montage.supprimer(s, 50.0, 120.0)
        montage.inserer(s, 30.0, montage.copier(s, 0.0, 40.0))
        montage.boucler(s, 0.0, 50.0, fois=3)
        self.assertEqual(list(s.data), avant)


class TestCouperColler(unittest.TestCase):

    def test_couper_rend_les_deux_parts(self):
        s = sinus(ms=300.0)
        reste, portion = montage.couper(s, 100.0, 200.0)
        self.assertAlmostEqual(portion.duration_ms, 100.0, delta=1.0)
        self.assertAlmostEqual(reste.duration_ms, 200.0, delta=8.0)

    def test_couper_puis_coller_rend_la_duree_moins_les_fondus(self):
        """Le contrat exact : chaque jointure fondue CONSOMME son
        recouvrement. Couper (1 jointure) puis recoller (2 jointures)
        raccourcit donc de trois fondus, ni plus ni moins."""
        s = sinus(ms=300.0)
        reste, portion = montage.couper(s, 100.0, 200.0)
        recolle = montage.inserer(reste, 100.0, portion)
        attendu = s.duration_ms - 3 * montage.FONDU_MS
        self.assertAlmostEqual(recolle.duration_ms, attendu, delta=1.0)

    def test_inserer_au_debut_et_a_la_fin(self):
        s = sinus(ms=100.0)
        bout = montage.copier(s, 0.0, 30.0)
        debut = montage.inserer(s, 0.0, bout)
        fin = montage.inserer(s, 100.0, bout)
        self.assertGreater(debut.duration_ms, s.duration_ms)
        self.assertGreater(fin.duration_ms, s.duration_ms)

    def test_inserer_un_morceau_vide_ne_change_rien(self):
        s = sinus(ms=100.0)
        vide = audio.Sample([], s.rate, "vide")
        out = montage.inserer(s, 50.0, vide)
        self.assertEqual(out.data, list(s.data))


class TestBoucler(unittest.TestCase):

    def test_trois_fois_environ_trois_durees(self):
        s = sinus(ms=200.0)
        out = montage.boucler(s, 0.0, 100.0, fois=3)
        self.assertAlmostEqual(out.duration_ms, 300.0, delta=20.0)

    def test_la_boucle_se_repete_vraiment(self):
        """Le milieu de la deuxieme passe doit etre IDENTIQUE au milieu
        de la premiere. La periode reelle n'est pas la portion : c'est
        la portion MOINS le recouvrement du fondu, puisque chaque
        repetition demarre dans la queue de la precedente."""
        s = sinus(ms=200.0)
        out = montage.boucler(s, 0.0, 100.0, fois=2)
        k = int(montage.FONDU_MS * s.rate / 1000.0)
        periode = int(100.0 * s.rate / 1000.0) - k
        i = periode // 2
        self.assertAlmostEqual(out.data[i], out.data[i + periode],
                               delta=1e-9)

    def test_une_fois_rend_la_portion(self):
        s = sinus(ms=200.0)
        out = montage.boucler(s, 50.0, 150.0, fois=1)
        self.assertAlmostEqual(out.duration_ms, 100.0, delta=1.0)


if __name__ == "__main__":
    unittest.main()
