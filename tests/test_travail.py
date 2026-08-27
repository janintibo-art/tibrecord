"""Tests du travail en tache de fond. Sans Kivy : le rappel vers
l'interface est remplace par une file qu'on depile a la main."""

import threading
import time
import unittest

from noyau import travail


class Scene:
    """Simule le fil d'interface : les rappels s'empilent, on les joue
    quand on veut, comme le ferait la boucle Kivy."""

    def __init__(self):
        self.rappels = []
        self.pret = threading.Event()

    def planifier(self, fn):
        self.rappels.append(fn)
        self.pret.set()

    def jouer(self, timeout=2.0):
        self.pret.wait(timeout)
        for fn in self.rappels:
            fn()
        self.rappels = []
        self.pret.clear()


class TestEnFond(unittest.TestCase):

    def test_le_resultat_arrive_par_le_planificateur(self):
        scene = Scene()
        recu = []
        travail.en_fond(lambda: 21 * 2, recu.append,
                        lambda e: self.fail(e), scene.planifier)
        scene.jouer()
        self.assertEqual(recu, [42])

    def test_l_erreur_arrive_par_le_planificateur(self):
        scene = Scene()
        erreurs = []
        travail.en_fond(lambda: 1 / 0,
                        lambda r: self.fail("aurait du echouer"),
                        erreurs.append, scene.planifier)
        scene.jouer()
        self.assertEqual(len(erreurs), 1)
        self.assertIsInstance(erreurs[0], ZeroDivisionError)

    def test_l_appelant_n_est_pas_bloque(self):
        """Tout l'interet : le fil d'interface reste libre pendant que
        le calcul tourne."""
        scene = Scene()
        depart = time.perf_counter()
        travail.en_fond(lambda: time.sleep(0.3) or "fini",
                        lambda r: None, lambda e: None, scene.planifier)
        self.assertLess(time.perf_counter() - depart, 0.1,
                        "en_fond a bloque l'appelant")
        scene.jouer()

    def test_rien_ne_touche_l_interface_depuis_le_fil(self):
        """Les rappels doivent passer par planifier, jamais en direct
        depuis le fil de calcul : c'est la regle qui evite les plantages
        indebogables."""
        scene = Scene()
        fil_du_rappel = []
        travail.en_fond(lambda: "x",
                        lambda r: fil_du_rappel.append(
                            threading.current_thread()),
                        lambda e: None, scene.planifier)
        scene.jouer()  # joue sur CE fil, comme Kivy le ferait
        self.assertEqual(fil_du_rappel, [threading.main_thread()])


class TestSerie(unittest.TestCase):

    def test_deux_travaux_a_la_fois_refuses(self):
        """Un utilisateur qui tapote deux fois attend UN resultat, pas
        deux traitements appliques l'un sur l'autre."""
        scene = Scene()
        serie = travail.Serie()
        barriere = threading.Event()
        ok1 = serie.lancer(lambda: barriere.wait(2.0),
                           lambda r: None, lambda e: None, scene.planifier)
        ok2 = serie.lancer(lambda: "jamais",
                           lambda r: None, lambda e: None, scene.planifier)
        self.assertTrue(ok1)
        self.assertFalse(ok2)
        self.assertTrue(serie.occupe)
        barriere.set()
        scene.jouer()
        self.assertFalse(serie.occupe)

    def test_disponible_apres_un_echec(self):
        """Un calcul qui echoue ne doit pas laisser le verrou ferme :
        sinon plus aucun traitement ne part jusqu'au redemarrage."""
        scene = Scene()
        serie = travail.Serie()
        serie.lancer(lambda: 1 / 0, lambda r: None, lambda e: None,
                     scene.planifier)
        scene.jouer()
        self.assertFalse(serie.occupe)
        self.assertTrue(serie.lancer(lambda: 1, lambda r: None,
                                     lambda e: None, scene.planifier))
        scene.jouer()


if __name__ == "__main__":
    unittest.main()
