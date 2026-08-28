"""
Relecture automatique des fichiers d'interface.

Pourquoi ce module existe : le bouton SAUVEGARDER est reste inerte
pendant plusieurs versions. Le code compilait, les 87 tests passaient, et
rien ne signalait que la methode appelee avait disparu lors d'une
reecriture. Ni Python ni les tests unitaires ne voient ce defaut, parce
que l'erreur ne se produit qu'au moment ou un doigt appuie sur le bouton.

Les deux controles ci-dessous lisent le code sans l'executer, donc sans
Kivy et sans ecran. Ils tournent en une seconde dans la meme commande que
les autres tests.

Ils ne remplacent pas un essai sur telephone : ils attrapent la faute
betement mecanique, celle qu'on ne voit plus a l'oeil dans un fichier de
mille huit cents lignes.
"""

import ast
import builtins
import os

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Noms fournis par Python lui-meme dans tout module.
DUNDERS = {"__file__", "__name__", "__doc__", "__package__", "__spec__",
           "__loader__", "__builtins__"}

# Methodes heritees de Kivy : elles existent bien, mais dans une classe
# mere que ce controle ne lit pas. A completer si un widget en utilise
# une nouvelle ; l'echec du test dira laquelle.
KIVY = {
    "bind", "unbind", "fbind", "funbind", "dispatch", "setter", "getter",
    "add_widget", "remove_widget", "clear_widgets", "collide_point",
    "open", "dismiss", "to_widget", "to_window", "to_local", "to_parent",
    "get_parent_window", "export_to_png", "walk", "walk_reverse",
    "on_touch_down", "on_touch_move", "on_touch_up", "canvas",
    "register_event_type", "create_property", "property", "trigger_action",
}


def _lire(nom):
    with open(os.path.join(RACINE, nom), encoding="utf-8") as f:
        return ast.parse(f.read())


def noms_inconnus(fichier):
    """Noms utilises mais definis nulle part : import oublie ou faute.

    C'est ce controle qui avait attrape l'absence de `Line` dans les
    imports, alors que la moitie des boutons s'en servaient.
    """
    arbre = _lire(fichier)
    definis = set(dir(builtins)) | DUNDERS
    for n in ast.walk(arbre):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef,
                          ast.ClassDef)):
            definis.add(n.name)
        elif isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store):
            definis.add(n.id)
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            for a in n.names:
                definis.add((a.asname or a.name).split(".")[0])
        elif isinstance(n, ast.arg):
            definis.add(n.arg)
        elif isinstance(n, ast.ExceptHandler) and n.name:
            definis.add(n.name)
        elif isinstance(n, ast.Global):
            definis.update(n.names)
    manquants = {}
    for n in ast.walk(arbre):
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load):
            if n.id not in definis:
                manquants.setdefault(n.id, n.lineno)
    return sorted((l, nom) for nom, l in manquants.items())


def _membres(cls, classes, vus=None):
    """Tout ce que la classe connait : ses methodes, ses attributs, et
    ce qu'elle herite des classes du meme fichier."""
    vus = vus or set()
    if cls.name in vus:
        return set()
    vus.add(cls.name)
    out = set()
    for n in cls.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out.add(n.name)
        elif isinstance(n, ast.Assign):
            for t in n.targets:
                if isinstance(t, ast.Name):
                    out.add(t.id)
    for n in ast.walk(cls):
        if (isinstance(n, ast.Attribute) and isinstance(n.ctx, ast.Store)
                and isinstance(n.value, ast.Name)
                and n.value.id == "self"):
            out.add(n.attr)
    for b in cls.bases:
        nom = b.id if isinstance(b, ast.Name) else getattr(b, "attr", None)
        if nom in classes:
            out |= _membres(classes[nom], classes, vus)
    return out


def methodes_fantomes(fichier):
    """self.quelquechose() appele alors que rien ne le definit.

    Le defaut du bouton SAUVEGARDER, exactement.
    """
    arbre = _lire(fichier)
    classes = {n.name: n for n in ast.walk(arbre)
               if isinstance(n, ast.ClassDef)}
    soucis = set()
    for nom, cls in classes.items():
        connus = _membres(cls, classes) | KIVY
        for n in ast.walk(cls):
            if (isinstance(n, ast.Call)
                    and isinstance(n.func, ast.Attribute)
                    and isinstance(n.func.value, ast.Name)
                    and n.func.value.id == "self"
                    and n.func.attr not in connus):
                soucis.add((n.lineno, nom, n.func.attr))
    return sorted(soucis)


def horloges_non_arretees(fichier):
    """Classes qui lancent une animation sans jamais l'annuler.

    Le voyant REC tournait a 24 images par seconde du lancement a la
    fermeture. Rien ne bougeait a l'ecran ; seule la batterie le voyait.
    """
    arbre = _lire(fichier)
    coupables = []
    for cls in ast.walk(arbre):
        if not isinstance(cls, ast.ClassDef):
            continue
        lance = annule = False
        ligne = cls.lineno
        for n in ast.walk(cls):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute):
                if n.func.attr == "schedule_interval":
                    lance, ligne = True, n.lineno
                elif n.func.attr == "cancel":
                    annule = True
        if lance and not annule:
            coupables.append((ligne, cls.name))
    return sorted(coupables)


# ------------------------------------------------------------ desynchro
# Le plantage du bouton ENREGISTRER venait de la : main.py appelait
# `self.enr.instantane(420)` alors que le noyau du depot etait une
# version anterieure, sans cette methode. Les deux fichiers compilaient,
# les tests passaient, et l'application mourait au premier appui.
#
# Ce controle relie les deux : il retrouve `self.enr = enregistrement.
# Enregistreur(...)`, puis verifie que chaque `self.enr.machin` existe
# vraiment dans la classe.

MODULES_NOYAU = ("audio", "bibliotheque", "effets", "enregistrement",
                 "montage", "spectre", "stockage", "temps", "travail",
                 "vignettes")


def _classes_du_noyau():
    """Les classes du noyau et TOUT ce qu'elles exposent.

    On lit la source plutot que d'interroger la classe : un attribut cree
    dans __init__ (self.derniere_erreur, self.en_cours) n'existe pas sur
    la classe elle-meme, et hasattr le declarerait absent a tort.
    """
    out = {}
    for nom in MODULES_NOYAU:
        chemin = os.path.join(RACINE, "noyau", "%s.py" % nom)
        if not os.path.isfile(chemin):
            continue
        with open(chemin, encoding="utf-8") as f:
            arbre = ast.parse(f.read())
        classes = {n.name: n for n in ast.walk(arbre)
                   if isinstance(n, ast.ClassDef)}
        for nom_classe, cls in classes.items():
            out.setdefault(nom_classe, _membres(cls, classes))
    return out


def attributs_absents(fichier):
    """self.truc = Module.Classe(...) puis self.truc.machin inexistant.

    Renvoie (ligne, attribut, classe, membre).
    """
    arbre = _lire(fichier)
    classes = _classes_du_noyau()

    # 1) reperer les self.X = <Classe du noyau>(...)
    origine = {}
    for n in ast.walk(arbre):
        if not isinstance(n, ast.Assign) or not isinstance(n.value, ast.Call):
            continue
        f = n.value.func
        nom_classe = f.attr if isinstance(f, ast.Attribute) else (
            f.id if isinstance(f, ast.Name) else None)
        if nom_classe not in classes:
            continue
        for t in n.targets:
            if (isinstance(t, ast.Attribute)
                    and isinstance(t.value, ast.Name)
                    and t.value.id == "self"):
                origine[t.attr] = nom_classe

    # 2) verifier chaque self.X.machin
    soucis = set()
    for n in ast.walk(arbre):
        if not isinstance(n, ast.Attribute):
            continue
        base = n.value
        if not (isinstance(base, ast.Attribute)
                and isinstance(base.value, ast.Name)
                and base.value.id == "self"
                and base.attr in origine):
            continue
        nom_classe = origine[base.attr]
        if n.attr not in classes[nom_classe]:
            soucis.add((n.lineno, base.attr, nom_classe, n.attr))
    return sorted(soucis)


def fonctions_absentes(fichier):
    """audio.machin() ou stockage.machin() qui n'existe pas dans le module.

    Meme famille de defaut, un cran plus simple : l'interface appelle une
    fonction du noyau qui n'a jamais ete ecrite, ou qui a ete renommee.
    """
    import importlib
    arbre = _lire(fichier)
    alias = {}
    for n in ast.walk(arbre):
        if isinstance(n, ast.ImportFrom) and (n.module or "") == "noyau":
            for a in n.names:
                if a.name in MODULES_NOYAU:
                    alias[a.asname or a.name] = a.name
    modules = {}
    for court, vrai in alias.items():
        try:
            modules[court] = importlib.import_module("noyau.%s" % vrai)
        except Exception:  # noqa: BLE001
            continue
    soucis = set()
    for n in ast.walk(arbre):
        if (isinstance(n, ast.Attribute)
                and isinstance(n.value, ast.Name)
                and n.value.id in modules
                and not n.attr.startswith("_")
                and not hasattr(modules[n.value.id], n.attr)):
            soucis.add((n.lineno, n.value.id, n.attr))
    return sorted(soucis)
