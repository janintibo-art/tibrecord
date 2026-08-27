"""Tests des mini-formes d'onde. Le point central est le cache : il doit
servir les silhouettes sans lire les WAV, et se refaire quand un fichier
change."""

import json
import math
import os
import shutil
import tempfile
import unittest

from noyau import audio, bibliotheque as bib, vignettes as vig


def poser_wav(dossier, nom, forme="sinus", duree_ms=200.0):
    n = int(duree_ms * 44100 / 1000)
    if forme == "silence":
        data = [0.0] * n
    elif forme == "fort":
        data = [0.9 if i % 2 else -0.9 for i in range(n)]
    else:
        data = [0.5 * math.sin(i / 8.0) for i in range(n)]
    chemin = os.path.join(dossier, nom + ".wav")
    audio.write_wav(chemin, audio.Sample(data, 44100, nom))
    return chemin


class TestCalcul(unittest.TestCase):

    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="vig_test_")

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def test_bon_nombre_de_colonnes(self):
        c = poser_wav(self.d, "a")
        self.assertEqual(len(vig.calculer(c)), vig.COLONNES)
        self.assertEqual(len(vig.calculer(c, colonnes=16)), 16)

    def test_valeurs_entre_zero_et_un(self):
        c = poser_wav(self.d, "fort", forme="fort")
        for v in vig.calculer(c):
            self.assertGreaterEqual(v, 0.0)
            self.assertLessEqual(v, 1.0)

    def test_le_silence_est_plat_et_le_fort_est_haut(self):
        """La silhouette doit ressembler au son : c'est tout son but."""
        plat = vig.calculer(poser_wav(self.d, "s", forme="silence"))
        fort = vig.calculer(poser_wav(self.d, "f", forme="fort"))
        self.assertLess(max(plat), 0.01)
        self.assertGreater(max(fort), 0.8)

    def test_fichier_illisible_donne_none_sans_planter(self):
        c = os.path.join(self.d, "casse.wav")
        with open(c, "wb") as f:
            f.write(b"pas un wav")
        self.assertIsNone(vig.calculer(c))

    def test_fichier_absent_donne_none(self):
        self.assertIsNone(vig.calculer(os.path.join(self.d, "rien.wav")))


class TestCache(unittest.TestCase):

    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="vig_cache_")

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def _items(self):
        return bib.lister_sons(self.d)

    def test_premier_passage_tout_manque(self):
        poser_wav(self.d, "a")
        vues, manquants = vig.pour_items(self.d, self._items())
        self.assertEqual(vues, {})
        self.assertEqual(len(manquants), 1)

    def test_apres_completer_tout_est_servi(self):
        poser_wav(self.d, "a")
        poser_wav(self.d, "b")
        _, manquants = vig.pour_items(self.d, self._items())
        self.assertEqual(vig.completer(self.d, manquants), 2)
        vues, manquants = vig.pour_items(self.d, self._items())
        self.assertEqual(len(vues), 2)
        self.assertEqual(manquants, [])

    def test_le_cache_est_vraiment_utilise(self):
        """On corrompt volontairement la silhouette rangee : si elle
        revient telle quelle, c'est bien le cache qui a servi, sans
        relire le WAV."""
        c = poser_wav(self.d, "a")
        vig.completer(self.d, [c])
        cache = vig.lire_cache(self.d)
        cache["fichiers"]["a.wav"]["p"] = [77] * vig.COLONNES
        vig.ecrire_cache(self.d, cache)
        vues, _ = vig.pour_items(self.d, self._items())
        self.assertAlmostEqual(vues[c][0], 0.77, places=2)

    def test_fichier_modifie_est_recalcule(self):
        c = poser_wav(self.d, "a", forme="silence")
        vig.completer(self.d, [c])
        # le fichier change : plus long ET plus fort
        os.utime(c, (1, 1))  # force une autre date
        poser_wav(self.d, "a", forme="fort", duree_ms=400.0)
        vues, manquants = vig.pour_items(self.d, self._items())
        self.assertEqual(vues, {})
        self.assertEqual(len(manquants), 1)

    def test_cache_abime_est_reconstruit_sans_planter(self):
        poser_wav(self.d, "a")
        with open(os.path.join(self.d, vig.FICHIER_CACHE), "w") as f:
            f.write("{pas du json")
        vues, manquants = vig.pour_items(self.d, self._items())
        self.assertEqual(len(manquants), 1)
        vig.completer(self.d, manquants)
        vues, _ = vig.pour_items(self.d, self._items())
        self.assertEqual(len(vues), 1)

    def test_les_fichiers_supprimes_sont_purges(self):
        """Sans purge, le cache grossit a chaque suppression et garde
        la silhouette de sons qui n'existent plus."""
        a = poser_wav(self.d, "a")
        b = poser_wav(self.d, "b")
        vig.completer(self.d, [a, b])
        os.remove(b)
        vig.completer(self.d, [])
        cache = vig.lire_cache(self.d)
        self.assertIn("a.wav", cache["fichiers"])
        self.assertNotIn("b.wav", cache["fichiers"])

    def test_le_cache_survit_au_renommage_du_dossier(self):
        """La cle est le nom du fichier, pas le chemin : renommer le
        dossier ne doit pas faire tout recalculer."""
        poser_wav(self.d, "a")
        _, manquants = vig.pour_items(self.d, self._items())
        vig.completer(self.d, manquants)
        neuf = self.d + "_renomme"
        os.rename(self.d, neuf)
        self.d = neuf
        vues, manquants = vig.pour_items(neuf, bib.lister_sons(neuf))
        self.assertEqual(len(vues), 1)
        self.assertEqual(manquants, [])

    def test_le_json_du_cache_n_est_pas_liste_comme_un_son(self):
        poser_wav(self.d, "a")
        vig.completer(self.d, [os.path.join(self.d, "a.wav")])
        noms = [i["nom"] for i in bib.lister_sons(self.d)]
        self.assertEqual(noms, ["a"])


if __name__ == "__main__":
    unittest.main()
