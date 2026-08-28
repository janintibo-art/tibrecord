"""Tests des effets. Le principe : verifier le RESULTAT qu'une oreille
attendrait. Un delai de 300 ms doit produire un echo a 300 ms — ca se
mesure sans ecouter."""

import math
import time
import unittest

from noyau import audio, effets, spectre


def impulsion(rate=44100, ms=500.0):
    n = int(ms * rate / 1000)
    data = [0.0] * n
    data[0] = 0.9
    return audio.Sample(data, rate, "clic")


def sinus(freq, ms=400.0, rate=44100, ampli=0.5):
    n = int(ms * rate / 1000)
    return audio.Sample(
        [ampli * math.sin(2 * math.pi * freq * i / rate) for i in range(n)],
        rate, "sinus")


class TestDelai(unittest.TestCase):

    def test_l_echo_tombe_au_bon_moment(self):
        """Un clic puis du silence : le premier echo doit apparaitre a
        temps_ms, a un echantillon pres."""
        s = impulsion()
        out = effets.delai(s, temps_ms=200.0, reinjection=0.4, mix=0.5)
        attendu = int(200.0 * s.rate / 1000)
        fenetre = out.data[attendu - 3:attendu + 4]
        self.assertGreater(max(abs(v) for v in fenetre), 0.1)
        # entre le clic et l'echo : rien
        creux = out.data[attendu // 2 - 50:attendu // 2 + 50]
        self.assertLess(max(abs(v) for v in creux), 1e-6)

    def test_les_echos_s_eteignent(self):
        s = impulsion()
        out = effets.delai(s, temps_ms=100.0, reinjection=0.5, mix=1.0)
        retard = int(100.0 * s.rate / 1000)
        e1 = abs(out.data[retard])
        e3 = abs(out.data[3 * retard])
        self.assertGreater(e1, e3)

    def test_la_sortie_est_rallongee_de_la_queue(self):
        s = impulsion()
        out = effets.delai(s, temps_ms=150.0)
        self.assertGreater(len(out.data), len(s.data))

    def test_l_original_n_est_pas_touche(self):
        s = sinus(440.0)
        avant = list(s.data[:100])
        effets.delai(s)
        self.assertEqual(list(s.data[:100]), avant)

    def test_jamais_hors_bornes(self):
        s = sinus(200.0, ampli=0.95)
        out = effets.delai(s, reinjection=0.9, mix=1.0)
        self.assertLessEqual(max(abs(v) for v in out.data), 1.0)


class TestReverbe(unittest.TestCase):

    def test_une_queue_existe_apres_le_son(self):
        """C'est la definition d'une reverberation : le son continue
        apres que la source s'est tue."""
        s = impulsion(ms=100.0)
        out = effets.reverbe(s, taille=0.6, mix=0.5)
        queue = out.data[len(s.data) + 800:len(s.data) + 12000]
        rms = math.sqrt(sum(v * v for v in queue) / max(1, len(queue)))
        self.assertGreater(rms, 1e-4)

    def test_la_grande_salle_dure_plus_que_le_placard(self):
        s = impulsion(ms=100.0)
        petit = effets.reverbe(s, taille=0.1)
        grand = effets.reverbe(s, taille=0.9)
        self.assertGreater(len(grand.data), len(petit.data))

    def test_mix_zero_laisse_le_son_sec(self):
        s = sinus(440.0, ms=100.0)
        out = effets.reverbe(s, mix=0.0)
        for a, b in zip(s.data[:2000], out.data[:2000]):
            self.assertAlmostEqual(a, b, places=6)

    def test_jamais_hors_bornes(self):
        s = sinus(150.0, ampli=0.95)
        out = effets.reverbe(s, taille=1.0, mix=1.0)
        self.assertLessEqual(max(abs(v) for v in out.data), 1.0)


class TestTremolo(unittest.TestCase):

    def test_le_volume_ondule_a_la_bonne_vitesse(self):
        """Sur un son constant, l'enveloppe doit creuser des vallees :
        autant que de battements dans la duree."""
        s = sinus(1000.0, ms=1000.0, ampli=0.8)
        out = effets.tremolo(s, vitesse_hz=4.0, profondeur=1.0)
        bloc = int(s.rate / 100)
        enveloppe = [max(abs(v) for v in out.data[i:i + bloc])
                     for i in range(0, len(out.data) - bloc, bloc)]
        creux = sum(1 for i in range(1, len(enveloppe) - 1)
                    if enveloppe[i] < 0.1
                    and enveloppe[i] <= enveloppe[i - 1]
                    and enveloppe[i] <= enveloppe[i + 1])
        self.assertGreaterEqual(creux, 3)
        self.assertLessEqual(creux, 6)

    def test_profondeur_nulle_ne_change_rien(self):
        s = sinus(500.0, ms=100.0)
        out = effets.tremolo(s, profondeur=0.0)
        for a, b in zip(s.data, out.data):
            self.assertAlmostEqual(a, b, places=9)

    def test_meme_duree(self):
        s = sinus(500.0)
        self.assertEqual(len(effets.tremolo(s).data), len(s.data))


class TestBitcrush(unittest.TestCase):

    def test_moins_de_bits_moins_de_valeurs(self):
        s = sinus(300.0, ms=200.0, ampli=0.9)
        out = effets.bitcrush(s, bits=4)
        distinctes = {round(v, 6) for v in out.data}
        self.assertLessEqual(len(distinctes), 2 ** 4 + 1)

    def test_la_reduction_de_taux_fait_des_paliers(self):
        s = sinus(300.0, ms=50.0)
        out = effets.bitcrush(s, bits=16, reduction_taux=8)
        for i in range(0, len(out.data) - 8, 8):
            palier = out.data[i:i + 8]
            self.assertEqual(len({round(v, 9) for v in palier}), 1)

    def test_seize_bits_sans_reduction_presque_intact(self):
        s = sinus(300.0, ms=50.0)
        out = effets.bitcrush(s, bits=16, reduction_taux=1)
        ecart = max(abs(a - b) for a, b in zip(s.data, out.data))
        self.assertLess(ecart, 1.0 / 2 ** 14)


class TestVarispeed(unittest.TestCase):

    def test_deux_fois_plus_vite_deux_fois_plus_court(self):
        s = sinus(440.0, ms=400.0)
        out = effets.varispeed(s, 2.0)
        self.assertAlmostEqual(len(out.data), len(s.data) / 2, delta=2)

    def test_la_hauteur_suit_la_vitesse(self):
        """220 Hz accelere x2 doit s'entendre vers 440 Hz : on le
        verifie avec l'analyse spectrale du noyau."""
        s = sinus(220.0, ms=500.0)
        out = effets.varispeed(s, 2.0)
        freqs = spectre.frequences(out.rate)
        vals = spectre.bandes_du_sample(out)
        dominante = freqs[vals.index(max(vals))]
        self.assertGreater(dominante, 300.0)
        self.assertLess(dominante, 640.0)

    def test_facteur_un_ne_change_rien(self):
        s = sinus(440.0, ms=100.0)
        out = effets.varispeed(s, 1.0)
        self.assertEqual(len(out.data), len(s.data))


class TestInversions(unittest.TestCase):

    def test_inverser_retourne_le_son(self):
        s = audio.Sample([0.1, 0.2, 0.3, 0.4], 44100, "x")
        self.assertEqual(effets.inverser(s).data, [0.4, 0.3, 0.2, 0.1])

    def test_double_inversion_identite(self):
        s = sinus(440.0, ms=50.0)
        out = effets.inverser(effets.inverser(s))
        self.assertEqual(out.data, list(s.data))

    def test_polarite_change_le_signe_pas_le_niveau(self):
        s = sinus(440.0, ms=50.0, ampli=0.7)
        out = effets.polarite(s)
        self.assertAlmostEqual(out.data[100], -s.data[100], places=9)
        self.assertAlmostEqual(max(out.data), -min(s.data), places=9)


class TestCatalogue(unittest.TestCase):

    def test_chaque_entree_est_executable(self):
        """Le catalogue pilote l'interface : chaque effet doit tourner
        avec ses valeurs par defaut, sans exception."""
        s = sinus(440.0, ms=60.0)
        for nom, entree in effets.CATALOGUE:
            params = {cle: defaut
                      for cle, _t, _mn, _mx, defaut, _u, _d
                      in entree["params"]}
            out = effets.appliquer(nom, s, **params)
            self.assertGreater(len(out.data), 0, nom)
            self.assertLessEqual(max(abs(v) for v in out.data), 1.0, nom)

    def test_effet_inconnu_leve(self):
        with self.assertRaises(ValueError):
            effets.appliquer("Nexiste Pas", sinus(440.0, ms=20.0))

    def test_budget_mesure_pas_espere(self):
        """Le plus lourd (reverbe) doit rester dans le budget de la
        fenetre de patience : marge x10 pour le telephone comprise."""
        s = sinus(300.0, ms=1000.0)
        t = time.perf_counter()
        effets.reverbe(s)
        cout = time.perf_counter() - t
        self.assertLess(cout, 1.0,
                        "reverbe : %.2f s pour 1 s de son, trop lourd"
                        % cout)


if __name__ == "__main__":
    unittest.main()
