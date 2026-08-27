"""Tests des graduations sous la forme d'onde."""

import unittest

from noyau import temps


class TestPas(unittest.TestCase):

    def test_pas_toujours_rond(self):
        """Le pas doit rester dans la suite 1, 2, 5 fois une puissance
        de dix : c'est ce qui rend la reglette lisible."""
        for duree in (0.4, 3.7, 12.0, 380.0, 3800.0, 95000.0, 600000.0):
            pas = temps.pas_lisible(duree)
            mantisse = pas / (10.0 ** round(
                __import__("math").log10(pas) // 1))
            self.assertIn(round(mantisse, 6), (1.0, 2.0, 5.0, 10.0),
                          "pas non rond pour %s ms : %s" % (duree, pas))

    def test_nombre_de_reperes_raisonnable(self):
        for duree in (3.7, 380.0, 3800.0, 95000.0):
            n = len(temps.graduations(0.0, duree, cibles=6))
            self.assertTrue(3 <= n <= 14,
                            "%d reperes pour %s ms" % (n, duree))

    def test_duree_nulle_ne_plante_pas(self):
        self.assertEqual(temps.graduations(0.0, 0.0), [])
        self.assertEqual(temps.graduations(5.0, 1.0), [])
        self.assertGreater(temps.pas_lisible(0), 0)

    def test_le_pas_se_resserre_quand_on_zoome(self):
        large = temps.pas_lisible(3800.0)
        serre = temps.pas_lisible(38.0)
        self.assertLess(serre, large)


class TestEtiquettes(unittest.TestCase):

    def test_secondes_entieres_quand_le_pas_est_large(self):
        self.assertEqual(temps.etiquette_temps(2000.0, 1000.0), "2 s")

    def test_precision_fine_quand_on_zoome(self):
        self.assertEqual(temps.etiquette_temps(1234.0, 1.0), "1.234 s")
        self.assertEqual(temps.etiquette_temps(1234.5, 0.1), "1.2345 s")

    def test_minutes_au_dela_de_soixante_secondes(self):
        """Le piege : a trois minutes du debut, on ne veut pas lire
        185000 ms mais 3:05."""
        self.assertEqual(temps.etiquette_temps(185000.0, 50000.0), "3:05")

    def test_minutes_et_precision_ensemble(self):
        self.assertEqual(temps.etiquette_temps(185000.0, 10.0), "3:05.00")

    def test_zero_est_affiche(self):
        self.assertEqual(temps.etiquette_temps(0.0, 1000.0), "0 s")


class TestCompteur(unittest.TestCase):
    """Le compteur de lecture doit garder une largeur constante :
    sinon les chiffres dansent pendant que le son defile."""

    def test_toujours_le_meme_nombre_de_caracteres(self):
        largeurs = {len(temps.horloge_precise(v))
                    for v in (0.0, 5.0, 999.0, 1234.0, 59999.0)}
        self.assertEqual(len(largeurs), 1)

    def test_millisecondes_affichees(self):
        self.assertEqual(temps.horloge_precise(1234.0), "1.234"[:0] + "0:01.234")

    def test_minutes(self):
        self.assertTrue(temps.horloge_precise(185000.0).startswith("3:05"))

    def test_avec_total(self):
        txt = temps.horloge_precise(1000.0, 2000.0)
        self.assertIn("/", txt)

    def test_negatif_ramene_a_zero(self):
        self.assertEqual(temps.horloge_precise(-50.0), "0:00.000")


class TestSousGraduations(unittest.TestCase):

    def test_plus_nombreuses_que_les_grandes(self):
        g = temps.graduations(0.0, 3800.0)
        p = temps.sous_graduations(0.0, 3800.0)
        self.assertGreater(len(p), len(g))

    def test_dans_la_fenetre(self):
        for t in temps.sous_graduations(1000.0, 2000.0):
            self.assertGreaterEqual(t, 1000.0 - 1e-6)
            self.assertLessEqual(t, 2000.0 + 1e-6)

    def test_fenetre_vide(self):
        self.assertEqual(temps.sous_graduations(0.0, 0.0), [])


class TestGraduations(unittest.TestCase):

    def test_reperes_dans_la_fenetre(self):
        for t, _ in temps.graduations(1000.0, 2000.0):
            self.assertGreaterEqual(t, 1000.0 - 1e-6)
            self.assertLessEqual(t, 2000.0 + 1e-6)

    def test_reperes_alignes_sur_le_pas(self):
        """Zoome loin dans le son, les reperes restent sur des valeurs
        rondes : 3,2 s et non 3,17 s."""
        rep = temps.graduations(3170.0, 3270.0)
        pas = temps.pas_lisible(100.0)
        for t, _ in rep:
            self.assertAlmostEqual(t / pas, round(t / pas), places=6)

    def test_fenetre_absurde_ne_fige_pas(self):
        self.assertLess(len(temps.graduations(0.0, 1e12)), 10001)


if __name__ == "__main__":
    unittest.main()
