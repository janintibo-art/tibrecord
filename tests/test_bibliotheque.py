"""Tests du rangement des sons. Aucun micro, aucun affichage."""

import os
import shutil
import tempfile
import unittest

from noyau import audio, bibliotheque as bib


def poser_wav(dossier, nom, duree_ms=100.0, rate=44100):
    """Ecrit un vrai WAV : les durees lues doivent etre les vraies."""
    n = int(duree_ms * rate / 1000.0)
    s = audio.Sample([0.0] * n, rate, nom)
    chemin = os.path.join(dossier, nom + ".wav")
    audio.write_wav(chemin, s)
    return chemin


class TestNoms(unittest.TestCase):

    def test_nom_vide_donne_un_defaut(self):
        self.assertEqual(bib.nom_propre(""), "son")
        self.assertEqual(bib.nom_propre("   "), "son")

    def test_caracteres_interdits_retires(self):
        self.assertNotIn("/", bib.nom_propre("kick/grave"))
        self.assertNotIn(":", bib.nom_propre("prise:1"))

    def test_extension_retiree(self):
        self.assertEqual(bib.nom_propre("kick.wav"), "kick")

    def test_espaces_reduits(self):
        self.assertEqual(bib.nom_propre("  kick   grave  "), "kick grave")


class TestBibliotheque(unittest.TestCase):

    def setUp(self):
        self.racine = tempfile.mkdtemp(prefix="biblio_test_")

    def tearDown(self):
        shutil.rmtree(self.racine, ignore_errors=True)

    # ---------------------------------------------------------- lecture
    def test_duree_lue_dans_l_entete(self):
        c = poser_wav(self.racine, "prise", duree_ms=250.0)
        self.assertAlmostEqual(bib.duree_ms(c), 250.0, delta=1.0)

    def test_fichier_illisible_ne_fait_pas_planter(self):
        c = os.path.join(self.racine, "casse.wav")
        with open(c, "wb") as f:
            f.write(b"pas un wav")
        self.assertEqual(bib.duree_ms(c), 0.0)
        self.assertEqual(len(bib.lister_sons(self.racine)), 1)

    def test_lister_ignore_les_non_wav(self):
        poser_wav(self.racine, "bon")
        with open(os.path.join(self.racine, "note.txt"), "w") as f:
            f.write("x")
        noms = [i["nom"] for i in bib.lister_sons(self.racine)]
        self.assertEqual(noms, ["bon"])

    def test_dossier_absent_renvoie_une_liste_vide(self):
        absent = os.path.join(self.racine, "nexiste_pas")
        self.assertEqual(bib.lister_sons(absent), [])
        self.assertEqual(bib.lister_dossiers(absent), [])

    # ---------------------------------------------------------- dossiers
    def test_creer_puis_lister_un_dossier(self):
        bib.creer_dossier(self.racine, "kicks")
        self.assertEqual(bib.lister_dossiers(self.racine), ["kicks"])

    def test_creer_deux_fois_ne_casse_rien(self):
        a = bib.creer_dossier(self.racine, "voix")
        b = bib.creer_dossier(self.racine, "voix")
        self.assertEqual(a, b)
        self.assertEqual(len(bib.lister_dossiers(self.racine)), 1)

    def test_renommer_un_dossier(self):
        bib.creer_dossier(self.racine, "kiks")
        bib.renommer_dossier(self.racine, "kiks", "kicks")
        self.assertEqual(bib.lister_dossiers(self.racine), ["kicks"])

    def test_renommer_sur_un_dossier_existant_est_refuse(self):
        bib.creer_dossier(self.racine, "kicks")
        bib.creer_dossier(self.racine, "voix")
        with self.assertRaises(FileExistsError):
            bib.renommer_dossier(self.racine, "voix", "kicks")
        self.assertEqual(len(bib.lister_dossiers(self.racine)), 2)

    def test_supprimer_un_dossier_plein_est_refuse(self):
        d = bib.creer_dossier(self.racine, "kicks")
        poser_wav(d, "kick")
        self.assertFalse(bib.supprimer_dossier(self.racine, "kicks"))
        self.assertEqual(bib.lister_dossiers(self.racine), ["kicks"])

    def test_supprimer_un_dossier_vide_fonctionne(self):
        bib.creer_dossier(self.racine, "vide")
        self.assertTrue(bib.supprimer_dossier(self.racine, "vide"))
        self.assertEqual(bib.lister_dossiers(self.racine), [])

    # ---------------------------------------------------------- fichiers
    def test_renommer_un_son(self):
        c = poser_wav(self.racine, "prise 1")
        neuf = bib.renommer(c, "kick grave")
        self.assertTrue(os.path.exists(neuf))
        self.assertFalse(os.path.exists(c))
        self.assertEqual(os.path.basename(neuf), "kick grave.wav")

    def test_renommer_n_ecrase_jamais(self):
        poser_wav(self.racine, "kick")
        c = poser_wav(self.racine, "autre")
        neuf = bib.renommer(c, "kick")
        self.assertEqual(os.path.basename(neuf), "kick 2.wav")
        self.assertEqual(len(bib.lister_sons(self.racine)), 2)

    def test_deplacer_vers_un_dossier(self):
        c = poser_wav(self.racine, "kick")
        d = bib.creer_dossier(self.racine, "kicks")
        neuf = bib.deplacer(c, d)
        self.assertEqual(bib.compter(d), 1)
        self.assertEqual(bib.compter(self.racine), 0)
        self.assertTrue(os.path.exists(neuf))

    def test_deplacer_n_ecrase_jamais(self):
        d = bib.creer_dossier(self.racine, "kicks")
        poser_wav(d, "kick")
        c = poser_wav(self.racine, "kick")
        bib.deplacer(c, d)
        self.assertEqual(bib.compter(d), 2)

    def test_deplacer_dans_son_propre_dossier_ne_fait_rien(self):
        c = poser_wav(self.racine, "kick")
        self.assertEqual(bib.deplacer(c, self.racine), c)
        self.assertEqual(bib.compter(self.racine), 1)

    def test_supprimer_un_son(self):
        c = poser_wav(self.racine, "kick")
        self.assertTrue(bib.supprimer(c))
        self.assertEqual(bib.compter(self.racine), 0)

    def test_supprimer_un_absent_renvoie_faux(self):
        self.assertFalse(bib.supprimer(
            os.path.join(self.racine, "fantome.wav")))

    def test_chemin_libre_numerote(self):
        poser_wav(self.racine, "kick")
        c = bib.chemin_libre(self.racine, "kick")
        self.assertEqual(os.path.basename(c), "kick 2.wav")

    # ---------------------------------------------------------- tri
    def test_tri_par_nom_est_alphabetique(self):
        for n in ("charley", "kick", "basse"):
            poser_wav(self.racine, n)
        items = bib.trier(bib.lister_sons(self.racine), "nom")
        self.assertEqual([i["nom"] for i in items],
                         ["basse", "charley", "kick"])

    def test_tri_par_duree_met_le_plus_long_devant(self):
        poser_wav(self.racine, "court", duree_ms=50.0)
        poser_wav(self.racine, "long", duree_ms=500.0)
        items = bib.trier(bib.lister_sons(self.racine), "duree")
        self.assertEqual(items[0]["nom"], "long")

    def test_tri_inconnu_ne_plante_pas(self):
        poser_wav(self.racine, "kick")
        self.assertEqual(len(bib.trier(bib.lister_sons(self.racine), "?")), 1)

    def test_recherche_sans_casse(self):
        poser_wav(self.racine, "Kick Grave")
        poser_wav(self.racine, "charley")
        items = bib.chercher(bib.lister_sons(self.racine), "kick")
        self.assertEqual(len(items), 1)

    def test_recherche_vide_ne_filtre_rien(self):
        poser_wav(self.racine, "kick")
        poser_wav(self.racine, "charley")
        items = bib.chercher(bib.lister_sons(self.racine), "")
        self.assertEqual(len(items), 2)

    # ---------------------------------------------------------- resume
    def test_resume_compte_la_racine_et_les_dossiers(self):
        poser_wav(self.racine, "libre")
        d = bib.creer_dossier(self.racine, "kicks")
        poser_wav(d, "kick 1")
        poser_wav(d, "kick 2")
        lignes = dict((n, c) for n, c, _ in bib.resume(self.racine))
        self.assertEqual(lignes[bib.RACINE], 1)
        self.assertEqual(lignes["kicks"], 2)

    def test_affichage_des_durees(self):
        self.assertEqual(bib.duree_courte(3800.0), "3.8 s")
        self.assertEqual(bib.duree_courte(95000.0), "1:35")

    def test_affichage_des_tailles(self):
        self.assertEqual(bib.taille_courte(512), "512 o")
        self.assertTrue(bib.taille_courte(2 * 1024 * 1024).endswith("Mo"))


if __name__ == "__main__":
    unittest.main()
