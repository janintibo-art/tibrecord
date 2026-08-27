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
