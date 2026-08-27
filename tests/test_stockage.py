"""Tests de l'acces aux dossiers. Aucun Android, aucun Kivy."""

import os
import shutil
import tempfile
import unittest

from noyau import stockage as st


class TestLecture(unittest.TestCase):

    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="stockage_test_")

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def test_dossier_existant_est_lisible(self):
        self.assertTrue(st.lisible(self.d))

    def test_dossier_absent_n_est_pas_lisible(self):
        self.assertFalse(st.lisible(os.path.join(self.d, "nexiste_pas")))

    def test_lisible_ne_leve_jamais(self):
        for mauvais in ("", None, 12, "/proc/1/mem/impossible"):
            try:
                st.lisible(mauvais)
            except Exception as e:  # noqa: BLE001
                self.fail("lisible(%r) a leve %s" % (mauvais, e))

    def test_ecriture_sondee_avec_un_vrai_wav(self):
        """Le refus arrive parfois seulement sur l'extension visee :
        la sonde doit ecrire un vrai .wav, pas un fichier neutre."""
        self.assertTrue(st.inscriptible(self.d))
        self.assertEqual(os.listdir(self.d), [],
                         "la sonde a laisse un fichier derriere elle")

    def test_ecriture_refusee_ne_leve_pas(self):
        self.assertFalse(st.inscriptible("/nexiste/vraiment/pas"))


class TestRaccourcis(unittest.TestCase):

    def test_toujours_au_moins_un_raccourci(self):
        self.assertTrue(st.raccourcis())

    def test_forme_des_entrees(self):
        for entree in st.raccourcis():
            self.assertEqual(len(entree), 3)
            nom, chemin, ok = entree
            self.assertIsInstance(nom, str)
            self.assertIsInstance(chemin, str)
            self.assertIsInstance(ok, bool)

    def test_pas_de_doublon(self):
        chemins = [c for _, c, _ in st.raccourcis()]
        self.assertEqual(len(chemins), len(set(chemins)))

    def test_les_chemins_annonces_lisibles_existent(self):
        """Un raccourci marque lisible doit vraiment mener quelque part.
        Ceux marques non lisibles peuvent etre des reperes : la carte SD
        reste affichee meme absente, pour dire qu'on sait la gerer."""
        for _, chemin, ok in st.raccourcis():
            if ok:
                self.assertTrue(os.path.isdir(chemin), chemin)

    def test_la_carte_sd_est_toujours_proposee(self):
        noms = [n for n, _, _ in st.raccourcis()]
        self.assertTrue(any("Carte SD" in n for n in noms),
                        "la carte SD doit rester visible, meme absente")

    def test_carte_absente_est_marquee_non_lisible(self):
        for nom, chemin, ok in st.raccourcis():
            if chemin.startswith("("):
                self.assertFalse(ok, "%s annonce lisible a tort" % nom)


class TestCartes(unittest.TestCase):

    def test_pas_de_faux_volume(self):
        """/storage/emulated n'est pas une carte SD : le proposer donne
        un raccourci mort."""
        for _, chemin in st.cartes_sd():
            self.assertNotIn(os.path.basename(chemin), st.PAS_DES_CARTES)

    def test_ne_leve_pas_sans_android(self):
        self.assertIsInstance(st.cartes_sd(), list)


class TestAccesComplet(unittest.TestCase):

    def test_hors_android_pas_de_blocage(self):
        self.assertTrue(st.acces_complet())

    def test_version_zero_hors_android(self):
        self.assertEqual(st.version_android(), 0)

    def test_demande_renvoie_un_message_sans_lever(self):
        msg = st.demander_acces_complet()
        self.assertIsInstance(msg, str)
        self.assertTrue(msg)


class TestDiagnostic(unittest.TestCase):

    def test_donne_un_texte_utile(self):
        txt = st.diagnostic()
        self.assertIn("Android", txt)
        self.assertIn("Dossier de l'application", txt)
        self.assertIn("Raccourcis", txt)

    def test_ne_leve_jamais(self):
        try:
            st.diagnostic()
        except Exception as e:  # noqa: BLE001
            self.fail("diagnostic() a leve %s" % e)


if __name__ == "__main__":
    unittest.main()
