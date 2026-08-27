"""
Enregistrement au micro.

Hors Android la capture est muette : ces tests valident la mecanique
(demarrage, arret, duree, conversion) sans avoir besoin d'un micro.
"""
import os
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from noyau import audio, enregistrement  # noqa: E402


class TestEnregistreur(unittest.TestCase):
    def setUp(self):
        self.e = enregistrement.Enregistreur(taux=8000)

    def tearDown(self):
        if self.e.en_cours:
            self.e.arreter()

    def test_etat_initial(self):
        self.assertFalse(self.e.en_cours)
        self.assertEqual(self.e.duree_s, 0.0)
        self.assertIsNone(self.e.derniere_erreur)

    def test_demarrer_puis_arreter(self):
        self.assertTrue(self.e.demarrer())
        self.assertTrue(self.e.en_cours)
        time.sleep(0.3)
        s = self.e.arreter()
        self.assertFalse(self.e.en_cours)
        self.assertIsNotNone(s)
        self.assertGreater(len(s.data), 0)

    def test_double_demarrage_refuse(self):
        self.e.demarrer()
        self.assertFalse(self.e.demarrer())

    def test_arret_sans_demarrage(self):
        self.assertIsNone(self.e.arreter())

    def test_duree_coherente(self):
        self.e.demarrer()
        time.sleep(0.4)
        s = self.e.arreter()
        self.assertGreater(s.duration_ms, 200)
        self.assertLess(s.duration_ms, 900)

    def test_reechantillonnage_en_44100(self):
        self.e.demarrer()
        time.sleep(0.25)
        s = self.e.arreter()
        self.assertEqual(s.rate, audio.TARGET_RATE)

    def test_relance_repart_a_zero(self):
        """Une nouvelle prise ne s'ajoute pas a la precedente."""
        self.e.demarrer()
        time.sleep(0.5)
        premiere = self.e.arreter().duration_ms
        self.e.demarrer()
        time.sleep(0.15)
        seconde = self.e.arreter().duration_ms
        self.assertGreater(premiere, 400)
        self.assertLess(seconde, premiere / 2)

    def test_taux_possibles(self):
        for t in enregistrement.TAUX_POSSIBLES:
            self.assertGreater(t, 0)
        self.assertIn(44100, enregistrement.TAUX_POSSIBLES)

    def test_niveau_lisible(self):
        self.e.demarrer()
        time.sleep(0.2)
        self.assertLessEqual(self.e.niveau_db(), 0.1)
        self.e.arreter()

    def test_micro_indisponible_hors_android(self):
        self.assertFalse(self.e.disponible())
        self.assertFalse(enregistrement.micro_autorise())


class TestChaineComplete(unittest.TestCase):
    """Capture, puis traitement : le parcours entier."""

    def test_capture_puis_traitement(self):
        import math
        e = enregistrement.Enregistreur(taux=8000)
        e.demarrer()
        time.sleep(0.25)
        s = e.arreter()
        # on remplace le silence par un vrai signal pour tester la suite
        n = len(s.data)
        s.data = [0.05 * math.sin(2 * math.pi * 220 * i / s.rate)
                  for i in range(n)]
        avant = s.rms_db()
        s, rap = audio.process(s, "punch")
        self.assertGreater(s.rms_db(), avant + 5)
        self.assertLessEqual(s.peak_db(), 0.0)


if __name__ == "__main__":
    unittest.main()
