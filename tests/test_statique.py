"""
Relecture automatique de main.py et onde.py.

Ces tests ne lancent pas l'interface : ils lisent le code. Ils existent
parce que trois defauts reels sont passes a travers la compilation ET les
tests unitaires, et n'ont ete vus qu'a l'usage, ou pas vus du tout.

Ils tournent sans Kivy, donc ils passent aussi sur le runner GitHub.
"""

import unittest

from tests import verificateur as v

FICHIERS = ("main.py", "onde.py")


class TestNomsDefinis(unittest.TestCase):
    """Un import oublie ne se voit pas a la compilation : le nom manquant
    ne plante qu'au moment ou la ligne s'execute."""

    def test_aucun_nom_inconnu(self):
        for f in FICHIERS:
            manquants = v.noms_inconnus(f)
            self.assertEqual(
                manquants, [],
                "%s utilise des noms definis nulle part : %s" % (f, manquants))


class TestMethodesAppelees(unittest.TestCase):
    """Le defaut du bouton SAUVEGARDER : une methode supprimee lors d'une
    reecriture, un bouton qui ne fait plus rien, et rien pour le dire."""

    def test_aucune_methode_fantome(self):
        for f in FICHIERS:
            fantomes = v.methodes_fantomes(f)
            self.assertEqual(
                fantomes, [],
                "%s appelle des methodes qui n'existent pas : %s\n"
                "Si c'est une methode heritee de Kivy, ajoute-la a la "
                "liste KIVY dans tests/verificateur.py." % (f, fantomes))


class TestAnimations(unittest.TestCase):
    """Une horloge Kivy lancee et jamais annulee consomme la batterie
    silencieusement : rien ne bouge a l'ecran, personne ne le remarque."""

    def test_toute_animation_peut_s_arreter(self):
        for f in FICHIERS:
            ouvertes = v.horloges_non_arretees(f)
            self.assertEqual(
                ouvertes, [],
                "%s lance une animation sans jamais l'annuler : %s"
                % (f, ouvertes))


class TestAccordAvecLeNoyau(unittest.TestCase):
    """Le plantage du bouton ENREGISTRER : main.py appelait
    Enregistreur.instantane() alors que le noyau du depot etait une
    version anterieure, sans cette methode.

    Chaque fichier etait correct pris seul. C'est leur accord qui ne
    l'etait pas, et rien ne le verifiait."""

    def test_les_objets_du_noyau_ont_ce_qu_on_leur_demande(self):
        for f in FICHIERS:
            absents = v.attributs_absents(f)
            self.assertEqual(
                absents, [],
                "%s utilise des membres absents du noyau : %s\n"
                "Le noyau du depot est probablement plus ancien que "
                "l'interface : un patch n'a pas ete applique." % (f, absents))

    def test_les_fonctions_du_noyau_existent(self):
        for f in FICHIERS:
            absentes = v.fonctions_absentes(f)
            self.assertEqual(
                absentes, [],
                "%s appelle des fonctions absentes du noyau : %s"
                % (f, absentes))


class TestOutilLuiMeme(unittest.TestCase):
    """Un verificateur qui ne detecte plus rien ne sert a rien. On lui
    donne du code fautif pour verifier qu'il reagit encore."""

    def test_il_repere_une_methode_absente(self):
        import ast
        code = ("class A:\n"
                "    def f(self):\n"
                "        self.disparue()\n")
        arbre = ast.parse(code)
        classes = {n.name: n for n in ast.walk(arbre)
                   if isinstance(n, ast.ClassDef)}
        connus = v._membres(classes["A"], classes) | v.KIVY
        self.assertNotIn("disparue", connus)
        self.assertIn("f", connus)

    def test_il_repere_un_noyau_trop_ancien(self):
        """On lui donne le defaut reel : un appel a une methode que la
        classe du noyau ne possede pas."""
        import ast
        classes = v._classes_du_noyau()
        self.assertIn("Enregistreur", classes)
        self.assertIn("instantane", classes["Enregistreur"])
        self.assertNotIn("methode_inventee", classes["Enregistreur"])

    def test_il_voit_les_attributs_crees_dans_init(self):
        """derniere_erreur n'existe pas sur la classe, seulement sur
        l'instance : le controle doit quand meme le connaitre, sinon il
        crie au loup a chaque ligne."""
        classes = v._classes_du_noyau()
        for attendu in ("derniere_erreur", "en_cours", "rms_courant"):
            self.assertIn(attendu, classes["Enregistreur"], attendu)

    def test_il_suit_l_heritage(self):
        import ast
        code = ("class A:\n"
                "    def f(self):\n"
                "        pass\n"
                "class B(A):\n"
                "    def g(self):\n"
                "        self.f()\n")
        arbre = ast.parse(code)
        classes = {n.name: n for n in ast.walk(arbre)
                   if isinstance(n, ast.ClassDef)}
        self.assertIn("f", v._membres(classes["B"], classes))


if __name__ == "__main__":
    unittest.main()
