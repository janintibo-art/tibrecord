"""Tests de l'analyse en bandes. Une sinusoide connue doit allumer la
bonne bande : c'est le seul critere qui compte pour un spectre."""

import math
import time
import unittest

from noyau import audio, spectre


def sinus(freq, ms=200.0, rate=44100, ampli=0.6):
    n = int(ms * rate / 1000)
    return audio.Sample(
        [ampli * math.sin(2 * math.pi * freq * i / rate) for i in range(n)],
        rate, "sinus")


class TestBandes(unittest.TestCase):

    def test_une_sinusoide_allume_sa_bande(self):
        """440 Hz doit dominer dans la bande qui contient 440 Hz, pour
        chaque frequence testee du grave a l'aigu."""
        for freq in (110.0, 440.0, 2000.0, 8000.0):
            s = sinus(freq)
            vals = spectre.bandes_du_sample(s)
            freqs = spectre.frequences(s.rate)
            gagnante = vals.index(max(vals))
            attendue = min(range(len(freqs)),
                           key=lambda i: abs(freqs[i] - freq))
            self.assertLessEqual(abs(gagnante - attendue), 1,
                                 "%g Hz : bande %d au lieu de %d"
                                 % (freq, gagnante, attendue))

    def test_le_silence_donne_zero_partout(self):
        """Sans le garde de silence, la normalisation sur le maximum
        transformerait le bruit de fond en spectre plein."""
        s = audio.Sample([0.0] * 8000, 44100, "silence")
        self.assertEqual(spectre.bandes_du_sample(s), [0.0] * spectre.NB_BANDES)

    def test_valeurs_toujours_entre_zero_et_un(self):
        s = sinus(1000.0, ampli=0.95)
        for v in spectre.bandes_du_sample(s):
            self.assertGreaterEqual(v, 0.0)
            self.assertLessEqual(v, 1.0)

    def test_sample_vide_ou_absent_ne_plante_pas(self):
        self.assertEqual(spectre.bandes_du_sample(None),
                         [0.0] * spectre.NB_BANDES)
        s = audio.Sample([], 44100, "vide")
        self.assertEqual(spectre.bandes_du_sample(s),
                         [0.0] * spectre.NB_BANDES)

    def test_bon_nombre_de_bandes(self):
        self.assertEqual(len(spectre.bandes_du_sample(sinus(500.0), nb=12)),
                         12)


class TestPosition(unittest.TestCase):

    def test_le_spectre_suit_la_position(self):
        """Un son grave puis aigu : au debut la bande grave gagne, a la
        fin la bande aigue. C'est tout le sens du spectre anime."""
        rate = 44100
        n = rate  # 1 seconde
        data = [0.6 * math.sin(2 * math.pi * 150.0 * i / rate)
                for i in range(n // 2)]
        data += [0.6 * math.sin(2 * math.pi * 6000.0 * i / rate)
                 for i in range(n // 2)]
        s = audio.Sample(data, rate, "double")
        freqs = spectre.frequences(rate)
        debut = spectre.bandes_a_la_position(s, 0.2)
        fin = spectre.bandes_a_la_position(s, 0.8)
        self.assertLess(freqs[debut.index(max(debut))], 400.0)
        self.assertGreater(freqs[fin.index(max(fin))], 3000.0)

    def test_les_bords_ne_plantent_pas(self):
        s = sinus(500.0, ms=50.0)
        for f in (0.0, 1.0, -0.5, 1.5):
            vals = spectre.bandes_a_la_position(s, f)
            self.assertEqual(len(vals), spectre.NB_BANDES)

    def test_assez_rapide_pour_douze_images_par_seconde(self):
        """Le budget est mesure, pas espere : une image toutes les 83 ms,
        l'analyse doit couter tres en dessous, meme x10 sur telephone."""
        s = sinus(1000.0, ms=1000.0)
        t = time.perf_counter()
        for _ in range(10):
            spectre.bandes_a_la_position(s, 0.5)
        par_image = (time.perf_counter() - t) / 10.0 * 1000.0
        self.assertLess(par_image, 8.0,
                        "%.1f ms par image ici, trop pour le telephone"
                        % par_image)


class TestLissage(unittest.TestCase):

    def test_montee_immediate(self):
        out = spectre.lisser([0.1] * 3, [0.9] * 3)
        self.assertEqual(out, [0.9] * 3)

    def test_descente_amortie(self):
        out = spectre.lisser([1.0] * 3, [0.0] * 3, retombee=0.5)
        self.assertEqual(out, [0.5] * 3)

    def test_listes_depareillees_sans_planter(self):
        self.assertEqual(spectre.lisser([], [0.3, 0.4]), [0.3, 0.4])
        self.assertEqual(spectre.lisser([0.1], [0.3, 0.4]), [0.3, 0.4])


if __name__ == "__main__":
    unittest.main()
