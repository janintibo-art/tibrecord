#!/usr/bin/env python3
"""
Tibrecord — enregistrement et travail du son au telephone.

Trois ecrans pour demarrer :
  ENREG.  capture au micro, vu-metre, minuteur
  EDIT.   forme d'onde zoomable, decoupe, traitement, ecoute
  TUTO    ce qu'il faut savoir

Sans Kivy : utiliser cli.py.
"""

import os
import sys
import tempfile
import threading
import time

try:
    import kivy  # noqa: F401
except ImportError:  # pragma: no cover
    raise SystemExit(
        "Kivy n'est pas installe.\n"
        "  pip install kivy\n"
        "Sinon utilise la version console : python cli.py --help"
    )

from kivy.app import App
from kivy.clock import Clock, mainthread
from kivy.core.window import Window
from kivy.graphics import Color, Line, RoundedRectangle, Triangle
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.filechooser import FileChooserListView
from kivy.uix.image import Image as KivyImage
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.progressbar import ProgressBar
from kivy.uix.scrollview import ScrollView
from kivy.uix.slider import Slider
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput

from noyau import __version__, audio, bibliotheque as bib, enregistrement
from noyau.temps import horloge_precise
from onde import Onde, Regle, horloge, position_texte

# ---------------------------------------------------------------- palette
FOND = (0.055, 0.055, 0.07, 1)
PANNEAU = (0.10, 0.10, 0.13, 1)
CYAN = (0.16, 0.80, 0.86, 1)
CYAN_S = (0.08, 0.38, 0.42, 1)
ROUGE = (0.88, 0.24, 0.24, 1)
VERT = (0.16, 0.62, 0.35, 1)
GRIS = (0.19, 0.19, 0.23, 1)
# Rouge eteint : signale la suppression sans crier plus fort que le reste.
ROUGE_SOMBRE = (0.42, 0.16, 0.16, 1)
# Le petit ecran de temps : fond presque noir, chiffres cyan, comme un
# afficheur d'enregistreur. Il vire au jaune pendant la lecture, pour
# qu'on sache d'un coup d'oeil si le compteur defile ou s'il est fige.
ECRAN_FOND = (0.035, 0.045, 0.05, 1)
ECRAN_BORD = (0.16, 0.30, 0.32, 1)
ECRAN_TEXTE = (0.35, 0.92, 0.98, 1)
ECRAN_TEXTE_LECTURE = (1.0, 0.85, 0.25, 1)
ECRAN_TEXTE_2 = (0.42, 0.60, 0.63, 1)
GRIS_CHOIX = (0.27, 0.27, 0.33, 1)
TEXTE = (0.90, 0.90, 0.92, 1)
TEXTE_2 = (0.62, 0.62, 0.68, 1)

IS_ANDROID = "ANDROID_ARGUMENT" in os.environ
TMP = tempfile.mkdtemp(prefix="tibrecord_")


# --------------------------------------------------------------------------
def fichier_asset(nom):
    """Chemin d'une image livree avec l'application, ou None.

    Sur Android les assets sont a cote du script ; en local aussi. On
    renvoie None si l'image manque, pour que l'absence d'un logo ne
    coute jamais un ecran noir.
    """
    base = os.path.dirname(os.path.abspath(__file__))
    chemin = os.path.join(base, "assets", nom)
    return chemin if os.path.isfile(chemin) else None


def dossier_travail():
    if IS_ANDROID:
        return os.environ.get("ANDROID_PRIVATE") or "/sdcard/Download"
    return os.getcwd()


def dossier_sons():
    d = os.path.join(dossier_travail(), "enregistrements")
    os.makedirs(d, exist_ok=True)
    return d


# "debut" et "duree_ms" servent a placer la tete de lecture : Kivy ne
# donne pas de position fiable sur Android, on se repere donc a
# l'horloge, ce qui suffit tant que le son n'est pas mis en pause.
_LECTEUR = {"son": None, "debut": 0.0, "duree_ms": 0.0}


def arreter_lecture():
    son = _LECTEUR.get("son")
    if son is not None:
        try:
            son.stop()
            son.unload()
        except Exception:  # noqa: BLE001
            pass
    _LECTEUR["son"] = None
    _LECTEUR["duree_ms"] = 0.0


def jouer_sample(sample, nom="apercu"):
    arreter_lecture()
    chemin = os.path.join(TMP, "%s.wav" % nom)
    audio.write_wav(chemin, sample)
    from kivy.core.audio import SoundLoader
    son = SoundLoader.load(chemin)
    if son is None:
        raise RuntimeError("lecteur audio indisponible")
    son.volume = 1.0
    son.play()
    _LECTEUR["son"] = son
    _LECTEUR["debut"] = time.time()
    _LECTEUR["duree_ms"] = sample.duration_ms
    return son


def avancement_lecture():
    """Fraction jouee de la lecture en cours, ou None si rien ne joue."""
    if _LECTEUR.get("son") is None or _LECTEUR.get("duree_ms", 0) <= 0:
        return None
    ecoule = (time.time() - _LECTEUR["debut"]) * 1000.0
    f = ecoule / _LECTEUR["duree_ms"]
    return None if f > 1.0 else max(0.0, f)


def journal_crash(texte):
    for d in ("/sdcard/Download", dossier_travail(), tempfile.gettempdir()):
        try:
            if d and os.path.isdir(d):
                chemin = os.path.join(d, "tibrecord_crash.txt")
                with open(chemin, "w", encoding="utf-8") as f:
                    f.write(texte)
                return chemin
        except Exception:  # noqa: BLE001
            continue
    return None


def trace_complete(e=None):
    import traceback as tb
    import platform as pf
    lignes = ["Tibrecord v%s - trace de plantage" % __version__, "",
              "python  : %s" % sys.version.split()[0],
              "systeme : %s" % pf.platform(),
              "android : %s" % IS_ANDROID, ""]
    lignes.append(tb.format_exc() if e is None else "".join(
        tb.format_exception(type(e), e, e.__traceback__)))
    return "\n".join(lignes)


# --------------------------------------------------------------------------
# --------------------------------------------------------------------------
# Relief des boutons.
#
# Kivy ne sait pas faire de degrade tout seul. On fabrique donc une petite
# texture d'un pixel de large et de soixante-quatre de haut, qu'on etire sur
# le bouton. C'est leger, calcule une seule fois par couleur, et ca donne un
# vrai degrade plutot qu'un aplat.
_TEXTURES = {}


def _teinte(couleur, k):
    """Eclaircit (k > 1) ou assombrit (k < 1) une couleur."""
    return tuple(max(0.0, min(1.0, v * k)) for v in couleur[:3])


def texture_relief(couleur, presse=False, hauteur=64):
    """Degrade vertical : clair en haut au repos, inverse quand on appuie.

    L'inversion compte autant que le degrade lui-meme : c'est elle qui
    donne la sensation que le bouton s'enfonce sous le doigt.
    """
    cle = (tuple(couleur[:3]), presse, hauteur)
    tex = _TEXTURES.get(cle)
    if tex is not None:
        return tex
    try:
        from kivy.graphics.texture import Texture
    except Exception:  # noqa: BLE001
        return None
    if presse:
        haut, bas = _teinte(couleur, 0.72), _teinte(couleur, 1.02)
    else:
        haut, bas = _teinte(couleur, 1.34), _teinte(couleur, 0.78)
    tex = Texture.create(size=(1, hauteur), colorfmt="rgba")
    buf = bytearray()
    # En OpenGL la premiere ligne du tampon est celle du BAS.
    for i in range(hauteur):
        t = i / float(hauteur - 1)
        # Courbe adoucie : la lumiere se concentre vers le haut, comme
        # sur une touche bombee, au lieu d'une rampe plate.
        t = t * t * (3.0 - 2.0 * t)
        for c in range(3):
            buf.append(int((bas[c] + (haut[c] - bas[c]) * t) * 255))
        buf.append(255)
    tex.blit_buffer(bytes(buf), colorfmt="rgba", bufferfmt="ubyte")
    tex.wrap = "clamp_to_edge"
    _TEXTURES[cle] = tex
    return tex


class Bouton(Button):
    """Bouton en relief : ombre portee, degrade, liseres.

    Quatre couches empilees, dans cet ordre : l'ombre sous le bouton, le
    corps en degrade, un lisere clair sur l'arete du haut, un contour
    sombre. Appuye, le bouton descend sur son ombre et le degrade
    s'inverse.
    """

    PROFONDEUR = 3.0  # hauteur de l'ombre visible, en dp

    def __init__(self, couleur=GRIS, rayon=10, **kw):
        kw.setdefault("background_normal", "")
        kw.setdefault("background_down", "")
        kw.setdefault("background_color", (0, 0, 0, 0))
        kw.setdefault("color", TEXTE)
        kw.setdefault("markup", True)
        super().__init__(**kw)
        self.couleur = couleur
        self.rayon = rayon
        with self.canvas.before:
            self._c_ombre = Color(0, 0, 0, 0.55)
            self._r_ombre = RoundedRectangle(radius=[rayon])
            self._c_corps = Color(1, 1, 1, 1)
            self._r_corps = RoundedRectangle(radius=[rayon])
            self._c_lustre = Color(1, 1, 1, 0.10)
            self._r_lustre = RoundedRectangle(radius=[rayon])
        with self.canvas.after:
            self._c_haut = Color(1, 1, 1, 0.20)
            self._l_haut = Line(width=1.2)
            self._c_bord = Color(0, 0, 0, 0.40)
            self._l_bord = Line(width=1.0)
        self.bind(pos=self._maj, size=self._maj, state=self._maj,
                  disabled=self._maj)
        self._maj()

    def _maj(self, *_a):
        presse = self.state == "down"
        prof = dp(self.PROFONDEUR)
        x, y, w, h = self.x, self.y, self.width, self.height
        r = self.rayon

        # L'ombre occupe toute la boite ; le corps se pose dessus, decale
        # vers le haut. Appuye, il descend : l'ombre se reduit.
        creux = prof * (0.25 if presse else 1.0)
        self._r_ombre.pos, self._r_ombre.size = (x, y), (w, h)
        self._r_ombre.radius = [r]
        self._c_ombre.a = 0.30 if presse else 0.55

        cy, ch = y + creux, max(h - creux, dp(4))
        self._r_corps.pos, self._r_corps.size = (x, cy), (w, ch)
        self._r_corps.radius = [r]

        couleur = self.couleur
        if self.disabled:
            couleur = _teinte(couleur, 0.45) + (couleur[3],)
        tex = texture_relief(couleur, presse)
        if tex is not None:
            self._r_corps.texture = tex
            self._c_corps.rgba = (1, 1, 1, couleur[3])
        else:  # sans OpenGL (tests, build Windows) : aplat, sans degrade
            self._c_corps.rgba = couleur

        # Reflet sur la moitie haute : ce qui fait "bombe" plutot que plat.
        self._r_lustre.pos = (x + dp(1), cy + ch * 0.52)
        self._r_lustre.size = (max(w - dp(2), 1), ch * 0.46)
        self._r_lustre.radius = [r * 0.8]
        self._c_lustre.a = 0.0 if presse else (0.05 if self.disabled else 0.10)

        # Arete claire en haut, contour sombre tout autour.
        self._l_haut.points = [x + r, cy + ch - dp(1),
                               x + w - r, cy + ch - dp(1)]
        self._c_haut.a = 0.06 if presse else 0.22
        self._l_bord.rounded_rectangle = (x, cy, w, ch, r)

    def set_couleur(self, couleur):
        self.couleur = couleur
        self._maj()


class Choix(Spinner):
    """Liste deroulante avec un chevron, pour qu'on voie que c'est un choix."""

    def __init__(self, **kw):
        kw.setdefault("background_normal", "")
        kw.setdefault("background_down", "")
        kw.setdefault("background_color", (0, 0, 0, 0))
        kw.setdefault("color", TEXTE)
        super().__init__(**kw)
        with self.canvas.before:
            self._c_ombre = Color(0, 0, 0, 0.55)
            self._r_ombre = RoundedRectangle(radius=[9])
            self._c_fond = Color(1, 1, 1, 1)
            self._rect = RoundedRectangle(radius=[9])
        with self.canvas.after:
            self._c_haut = Color(1, 1, 1, 0.18)
            self._l_haut = Line(width=1.2)
            self._c_bord = Color(0, 0, 0, 0.40)
            self._l_bord = Line(width=1.0)
            Color(*CYAN)
            self._fleche = Triangle(points=[0, 0, 0, 0, 0, 0])
        self.bind(pos=self._maj, size=self._maj)
        self._maj()

    def _maj(self, *_a):
        prof = dp(3.0)
        x, y, w, h = self.x, self.y, self.width, self.height
        self._r_ombre.pos, self._r_ombre.size = (x, y), (w, h)
        cy, ch = y + prof, max(h - prof, dp(4))
        self._rect.pos, self._rect.size = (x, cy), (w, ch)
        tex = texture_relief(GRIS_CHOIX)
        if tex is not None:
            self._rect.texture = tex
            self._c_fond.rgba = (1, 1, 1, 1)
        else:
            self._c_fond.rgba = GRIS_CHOIX
        self._l_haut.points = [x + dp(9), cy + ch - dp(1),
                               x + w - dp(9), cy + ch - dp(1)]
        self._l_bord.rounded_rectangle = (x, cy, w, ch, dp(9))
        l = dp(9)
        xf, yf = self.right - dp(14), self.center_y + l * 0.35 + prof / 2
        self._fleche.points = [xf - l / 2, yf, xf + l / 2, yf,
                               xf, yf - l * 0.75]


class Panneau(BoxLayout):
    def __init__(self, fond=PANNEAU, rayon=10, **kw):
        super().__init__(**kw)
        with self.canvas.before:
            Color(*fond)
            self._r = RoundedRectangle(radius=[rayon])
        self.bind(pos=self._maj, size=self._maj)

    def _maj(self, *_a):
        self._r.pos, self._r.size = self.pos, self.size


class VuMetre(BoxLayout):
    """Barre de niveau, verte puis orange puis rouge."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.niveau = 0.0
        self.crete = 0.0
        with self.canvas:
            Color(0.10, 0.10, 0.13, 1)
            self._fond = RoundedRectangle(radius=[4])
            self._c = Color(*VERT)
            self._barre = RoundedRectangle(radius=[4])
            self._cc = Color(1, 1, 1, 0.8)
            self._pic = RoundedRectangle(radius=[1])
        self.bind(pos=self._maj, size=self._maj)

    def poser(self, niveau_db):
        v = max(0.0, min(1.0, (niveau_db + 60.0) / 60.0))
        self.niveau = v
        self.crete = max(self.crete * 0.94, v)
        if niveau_db > -1.0:
            self._c.rgba = ROUGE
        elif niveau_db > -8.0:
            self._c.rgba = (0.95, 0.62, 0.15, 1)
        else:
            self._c.rgba = VERT
        self._maj()

    def _maj(self, *_a):
        self._fond.pos, self._fond.size = self.pos, self.size
        self._barre.pos = self.pos
        self._barre.size = (self.width * self.niveau, self.height)
        x = self.x + self.width * self.crete
        self._pic.pos = (max(self.x, x - dp(2)), self.y)
        self._pic.size = (dp(2), self.height)


# --------------------------------------------------------------------------
class Chooser(Popup):
    def __init__(self, callback, dossiers=False, filtres=None, start=None, **kw):
        super().__init__(
            title="Choisir un dossier" if dossiers else "Choisir un fichier",
            size_hint=(0.96, 0.92), **kw)
        self.callback, self.dossiers = callback, dossiers
        box = BoxLayout(orientation="vertical", spacing=dp(6), padding=dp(6))
        self.chooser = FileChooserListView(
            path=start or dossier_sons(), dirselect=dossiers,
            filters=filtres or ["*"])
        box.add_widget(self.chooser)
        self.champ = TextInput(text=self.chooser.path, multiline=False,
                               size_hint_y=None, height=dp(40))
        self.champ.bind(on_text_validate=lambda *_: self._aller(
            self.champ.text.strip()))
        box.add_widget(self.champ)
        self.lbl = Label(text="", size_hint_y=None, height=dp(22),
                         font_size=dp(11), color=(0.95, 0.55, 0.35, 1))
        box.add_widget(self.lbl)
        r = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(6))
        b_no = Bouton(text="Annuler")
        b_no.bind(on_release=lambda *_: self.dismiss())
        r.add_widget(b_no)
        b_ok = Bouton(text="Choisir", couleur=CYAN)
        b_ok.bind(on_release=self._ok)
        r.add_widget(b_ok)
        box.add_widget(r)
        self.add_widget(box)

    def _aller(self, chemin):
        if os.path.isdir(chemin):
            self.chooser.path = chemin
        else:
            self.lbl.text = "Dossier introuvable."

    def _ok(self, *_):
        sel = self.chooser.selection
        if self.dossiers:
            c = sel[0] if sel else self.chooser.path
            self.dismiss()
            self.callback(os.path.dirname(c) if os.path.isfile(c) else c)
            return
        if not sel:
            self.lbl.text = "Appuie d'abord sur un FICHIER."
            return
        if os.path.isdir(sel[0]):
            self.chooser.path = sel[0]
            return
        self.dismiss()
        self.callback(sel[0])


class NomPopup(Popup):
    def __init__(self, titre, defaut, callback, **kw):
        super().__init__(title=titre, size_hint=(0.9, None), height=dp(190),
                         **kw)
        self.callback = callback
        box = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(10))
        self.champ = TextInput(text=defaut, multiline=False,
                               size_hint_y=None, height=dp(44),
                               font_size=dp(16))
        box.add_widget(self.champ)
        r = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(6))
        b_no = Bouton(text="Annuler")
        b_no.bind(on_release=lambda *_: self.dismiss())
        r.add_widget(b_no)
        b_ok = Bouton(text="Valider", couleur=VERT)
        b_ok.bind(on_release=self._ok)
        r.add_widget(b_ok)
        box.add_widget(r)
        self.add_widget(box)

    def _ok(self, *_):
        txt = self.champ.text.strip()
        self.dismiss()
        if txt:
            self.callback(txt)


# --------------------------------------------------------------------------
class EcranEnreg(BoxLayout):
    """Capture au micro."""

    def __init__(self, journal, sur_capture, **kw):
        super().__init__(orientation="vertical", spacing=dp(8), **kw)
        self.journal = journal
        self.sur_capture = sur_capture
        self.enr = enregistrement.Enregistreur()
        self._tic = None

        self.add_widget(Label(text="", size_hint_y=None, height=dp(6)))

        self.lbl_temps = Label(text="0:00.000", font_size=dp(40),
                               size_hint_y=None, height=dp(70), color=TEXTE)
        self.add_widget(self.lbl_temps)

        cadre = Panneau(orientation="vertical", size_hint_y=None,
                        height=dp(70), padding=dp(8), spacing=dp(6))
        self.vu = VuMetre(size_hint_y=None, height=dp(22))
        cadre.add_widget(self.vu)
        self.lbl_niveau = Label(text="-inf dB", font_size=dp(12),
                                color=TEXTE_2, size_hint_y=None,
                                height=dp(20))
        cadre.add_widget(self.lbl_niveau)
        self.add_widget(cadre)

        r = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(6))
        r.add_widget(Label(text="Qualite", size_hint_x=0.3, color=TEXTE,
                           font_size=dp(12)))
        self.spin_taux = Choix(text="44100",
                               values=[str(t) for t in
                                       enregistrement.TAUX_POSSIBLES])
        r.add_widget(self.spin_taux)
        self.add_widget(r)

        r2 = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(6))
        r2.add_widget(Label(text="Source", size_hint_x=0.3, color=TEXTE,
                            font_size=dp(12)))
        self.spin_source = Choix(text="micro",
                                 values=["micro", "camera", "brut"])
        r2.add_widget(self.spin_source)
        self.add_widget(r2)

        self.b_rec = Bouton(text="ENREGISTRER", couleur=ROUGE,
                            size_hint_y=None, height=dp(72),
                            font_size=dp(18))
        self.b_rec.bind(on_release=lambda *_: self.basculer())
        self.add_widget(self.b_rec)

        self.lbl_etat = Label(text="", size_hint_y=None, height=dp(44),
                              font_size=dp(11), color=TEXTE_2)
        self.add_widget(self.lbl_etat)
        self.add_widget(BoxLayout())

        Clock.schedule_once(lambda *_: self._verifier(), 0.6)

    def _verifier(self):
        if not IS_ANDROID:
            self.lbl_etat.text = ("Hors Android : la capture est muette.\n"
                                  "La logique reste testable.")
            return
        if not enregistrement.micro_autorise():
            enregistrement.demander_micro()
        self.lbl_etat.text = ("Micro pret." if self.enr.disponible()
                              else "Micro indisponible sur cet appareil.")

    def basculer(self):
        if self.enr.en_cours:
            self.arreter()
        else:
            self.demarrer()

    def demarrer(self):
        self.enr = enregistrement.Enregistreur(
            int(self.spin_taux.text), self.spin_source.text)
        if not self.enr.demarrer():
            return
        self.b_rec.text = "ARRETER"
        self.b_rec.set_couleur(GRIS)
        self.vu.crete = 0.0
        self._tic = Clock.schedule_interval(self._maj, 1 / 20.0)
        self.journal("Enregistrement a %s Hz." % self.spin_taux.text)

    def _maj(self, _dt):
        self.lbl_temps.text = horloge(self.enr.duree_s)
        db = self.enr.niveau_db()
        self.vu.poser(db)
        self.lbl_niveau.text = ("%.1f dB" % db) if db > -90 else "-inf dB"
        if self.enr.derniere_erreur:
            self.lbl_etat.text = self.enr.derniere_erreur
            self.arreter()
            return False
        return True

    def arreter(self):
        if self._tic:
            self._tic.cancel()
            self._tic = None
        sample = self.enr.arreter()
        self.b_rec.text = "ENREGISTRER"
        self.b_rec.set_couleur(ROUGE)
        if sample is None:
            self.journal("Rien n'a ete capture. %s"
                         % (self.enr.derniere_erreur or ""))
            return
        i = sample.info()
        self.journal("Capture : %.1f s, crete %.1f dB, RMS %.1f dB"
                     % (i["duree_ms"] / 1000.0, i["peak_db"], i["rms_db"]))
        self.sur_capture(sample)


class EcranEdit(BoxLayout):
    """Forme d'onde zoomable, decoupe, traitement, ecoute."""

    def __init__(self, journal, **kw):
        super().__init__(orientation="vertical", spacing=dp(6), **kw)
        self.journal = journal
        self.sample = None
        self.historique = []
        self._tic_tete = None

        page = ScrollView(do_scroll_x=False)
        corps = BoxLayout(orientation="vertical", spacing=dp(6),
                          size_hint_y=None, padding=(0, 0, 0, dp(6)))
        corps.bind(minimum_height=corps.setter("height"))
        page.add_widget(corps)
        BoxLayout.add_widget(self, page)

        r0 = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(6))
        b_o = Bouton(text="Ouvrir un WAV", couleur=CYAN)
        b_o.bind(on_release=lambda *_: Chooser(
            self.charger_fichier, filtres=["*.wav", "*.WAV"]).open())
        r0.add_widget(b_o)
        b_s = Bouton(text="Enregistrer", couleur=VERT)
        b_s.bind(on_release=lambda *_: self.sauver())
        r0.add_widget(b_s)
        corps.add_widget(r0)

        self.lbl_nom = Label(text="(aucun son)", size_hint_y=None,
                             height=dp(24), font_size=dp(12), shorten=True,
                             color=TEXTE_2)
        corps.add_widget(self.lbl_nom)

        self.compteur = Compteur()
        corps.add_widget(self.compteur)

        cadre = Panneau(orientation="vertical", size_hint_y=None,
                        height=dp(272), padding=dp(6), spacing=dp(2))
        self.onde = Onde(on_change=self._maj_mesures)
        cadre.add_widget(self.onde)
        self.regle = Regle(self.onde, size_hint_y=None, height=dp(20))
        self.onde.regle = self.regle
        cadre.add_widget(self.regle)
        corps.add_widget(cadre)

        self.lbl_mes = Label(text="", size_hint_y=None, height=dp(44),
                             font_size=dp(11), color=TEXTE)
        corps.add_widget(self.lbl_mes)

        r_z = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(4))
        for txt, fn in (("- zoom", lambda: self.onde.zoomer(0.5)),
                        ("+ zoom", lambda: self.onde.zoomer(2.0)),
                        ("<", lambda: self.onde.deplacer(-0.25)),
                        (">", lambda: self.onde.deplacer(0.25)),
                        ("Cadrer", self.onde.cadrer_selection),
                        ("Tout", self.onde.tout_voir)):
            b = Bouton(text=txt, font_size=dp(11))
            b.bind(on_release=lambda w, f=fn: (f(), self._maj_mesures()))
            r_z.add_widget(b)
        corps.add_widget(r_z)

        r_e = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(6))
        b_l = Bouton(text="> Lire la selection", couleur=VERT)
        b_l.bind(on_release=lambda *_: self.lire())
        r_e.add_widget(b_l)
        b_st = Bouton(text="Stop", size_hint_x=0.4)
        b_st.bind(on_release=lambda *_: self.stopper())
        r_e.add_widget(b_st)
        corps.add_widget(r_e)

        r_t = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(4))
        for txt, fn in (("Rogner", self.rogner),
                        ("Normaliser", self.normaliser),
                        ("Fondus", self.fondus),
                        ("Annuler", self.annuler)):
            b = Bouton(text=txt, font_size=dp(11))
            b.bind(on_release=lambda w, f=fn: f())
            r_t.add_widget(b)
        corps.add_widget(r_t)

        r_p = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(6))
        r_p.add_widget(Label(text="Preset", size_hint_x=0.28, color=TEXTE,
                             font_size=dp(12)))
        self.spin = Choix(text="punch", values=sorted(audio.PRESETS))
        r_p.add_widget(self.spin)
        b_tr = Bouton(text="Traiter", couleur=CYAN, size_hint_x=0.34)
        b_tr.bind(on_release=lambda *_: self.traiter())
        r_p.add_widget(b_tr)
        corps.add_widget(r_p)

    # ------------------------------------------------------------ etat
    def poser(self, sample, nom=None):
        self.sample = sample
        self.historique = []
        self.onde.charger(sample)
        self.lbl_nom.text = nom or sample.name
        self._maj_mesures()

    def charger_fichier(self, chemin):
        try:
            s = audio.read_wav(chemin)
            self.poser(s, os.path.basename(chemin))
            self.journal("Charge : %s" % os.path.basename(chemin))
        except Exception as e:  # noqa: BLE001
            self.journal("Lecture impossible : %s" % e)

    def _maj_mesures(self):
        if self.sample is None:
            self.lbl_mes.text = ""
            return
        a, b = self.onde.bornes_ms()
        e0, e1 = self.onde.echantillons()
        p = 4 if self.onde.zoom > 40 else 3
        self.lbl_mes.text = (
            "debut %s   fin %s   duree %.3f ms\n"
            "echantillons %d a %d  (%d)   zoom x%.0f" % (
                horloge(a / 1000.0, p), horloge(b / 1000.0, p), b - a,
                e0, e1, e1 - e0, self.onde.zoom))
        if self._tic_tete is None:
            # Rien ne joue : l'ecran montre ou commence la selection,
            # c'est-a-dire l'endroit exact ou la coupe se fera.
            self.compteur.afficher(a, self.sample.duration_ms, e0,
                                   len(self.sample.data))

    def _selection(self):
        a, b = self.onde.bornes_ms()
        return audio.copie_decoupee(self.sample, a, b) \
            if hasattr(audio, "copie_decoupee") else self.sample

    # ------------------------------------------------------------ outils
    def _memoriser(self):
        if self.sample is not None:
            self.historique.append(self.sample.copy())
            if len(self.historique) > 12:
                self.historique.pop(0)

    def annuler(self):
        if not self.historique:
            self.journal("Rien a annuler.")
            return
        self.sample = self.historique.pop()
        self.onde.charger(self.sample)
        self._maj_mesures()
        self.journal("Annule.")

    def rogner(self):
        if self.sample is None:
            return
        self._memoriser()
        a, b = self.onde.bornes_ms()
        n = len(self.sample.data)
        i0, i1 = int(a * self.sample.rate / 1000), int(b * self.sample.rate / 1000)
        self.sample.data = self.sample.data[max(0, i0):min(n, i1)]
        self.onde.charger(self.sample)
        self._maj_mesures()
        self.journal("Rogne : %.0f ms conserves." % self.sample.duration_ms)

    def normaliser(self):
        if self.sample is None:
            return
        self._memoriser()
        audio.normalize_peak(self.sample, -0.3)
        self.onde.charger(self.sample)
        self.journal("Normalise a -0,3 dB.")

    def fondus(self):
        if self.sample is None:
            return
        self._memoriser()
        audio.fade(self.sample, 3.0, 8.0)
        self.onde.charger(self.sample)
        self.journal("Fondus appliques.")

    def traiter(self):
        if self.sample is None:
            return
        self._memoriser()
        self.sample, rap = audio.process(self.sample, self.spin.text)
        self.onde.charger(self.sample)
        self._maj_mesures()
        self.journal("%s : %+.1f dB, RMS %.1f dB" % (
            self.spin.text, rap["gain_db"], rap["apres"]["rms_db"]))

    def lire(self):
        if self.sample is None:
            self.journal("Ouvre ou enregistre un son d'abord.")
            return
        try:
            a, b = self.onde.bornes_ms()
            r = self.sample.rate
            i0, i1 = int(a * r / 1000), int(b * r / 1000)
            bout = audio.Sample(self.sample.data[i0:i1], r, "selection")
            jouer_sample(bout, "selection")
            self._suivre_tete()
        except Exception as e:  # noqa: BLE001
            self.journal("Lecture impossible : %s" % e)

    # ------------------------------------------------------- tete de lecture
    def _suivre_tete(self):
        """Lance l'animation de la barre pendant la lecture.

        Trente images par seconde : en dessous, les millisecondes
        avancent par paquets et l'oeil le voit.
        """
        self._arreter_tete()
        self._tic_tete = Clock.schedule_interval(self._maj_tete, 1 / 30.0)

    def _arreter_tete(self):
        if self._tic_tete is not None:
            self._tic_tete.cancel()
            self._tic_tete = None
        self.onde.poser_tete(None)
        self._maj_mesures()

    def _maj_tete(self, *_a):
        f = avancement_lecture()
        if f is None:
            self._arreter_tete()
            return False
        # La lecture porte sur la selection : la tete parcourt donc la
        # selection, pas le son entier.
        a, b = self.onde.sel_debut, self.onde.sel_fin
        pos = a + (b - a) * f
        self.onde.poser_tete(pos)
        if self.sample is not None:
            duree = self.sample.duration_ms
            n = len(self.sample.data)
            self.compteur.afficher(pos * duree, duree, int(pos * n), n,
                                   en_lecture=True)

    def stopper(self):
        arreter_lecture()
        self._arreter_tete()

class ChoixPopup(Popup):
    """Petit menu : un titre, une liste de boutons, une annulation.

    Sert au menu d'un son et au choix d'un dossier de destination.
    """

    def __init__(self, titre, options, callback, **kw):
        haut = min(dp(120) + dp(50) * len(options), dp(520))
        super().__init__(title=titre, size_hint=(0.92, None), height=haut,
                         **kw)
        self.callback = callback
        box = BoxLayout(orientation="vertical", spacing=dp(6),
                        padding=dp(10))
        sv = ScrollView(do_scroll_x=False)
        liste = BoxLayout(orientation="vertical", spacing=dp(6),
                          size_hint_y=None)
        liste.bind(minimum_height=liste.setter("height"))
        for texte, cle, couleur in options:
            b = Bouton(text=texte, couleur=couleur, size_hint_y=None,
                       height=dp(44), font_size=dp(13))
            b.bind(on_release=lambda w, c=cle: self._choisir(c))
            liste.add_widget(b)
        sv.add_widget(liste)
        box.add_widget(sv)
        b_no = Bouton(text="Annuler", size_hint_y=None, height=dp(44))
        b_no.bind(on_release=lambda *_: self.dismiss())
        box.add_widget(b_no)
        self.add_widget(box)

    def _choisir(self, cle):
        self.dismiss()
        self.callback(cle)


class Compteur(BoxLayout):
    """Petit ecran de temps, facon afficheur d'enregistreur.

    Il montre la position au millieme de seconde. Pendant la lecture il
    defile ; a l'arret il affiche le debut de la selection. Le numero
    d'echantillon est en dessous : c'est la mesure exacte, celle qui ne
    depend pas de l'arrondi de l'affichage.

    Les chiffres gardent une largeur constante (0:00.000), sinon ils
    sautent lateralement a chaque dixieme et deviennent illisibles.
    """

    def __init__(self, **kw):
        super().__init__(orientation="vertical", size_hint_y=None,
                         height=dp(62), padding=(dp(10), dp(4)), **kw)
        with self.canvas.before:
            self._c_ombre = Color(0, 0, 0, 0.5)
            self._r_ombre = RoundedRectangle(radius=[9])
            self._c_fond = Color(*ECRAN_FOND)
            self._r_fond = RoundedRectangle(radius=[9])
        with self.canvas.after:
            self._c_bord = Color(*ECRAN_BORD)
            self._l_bord = Line(width=1.1)
        self.bind(pos=self._maj_cadre, size=self._maj_cadre)

        self.lbl_temps = Label(text="0:00.000", font_size=dp(28),
                               color=ECRAN_TEXTE, bold=True,
                               size_hint_y=None, height=dp(36),
                               halign="center", valign="middle")
        self.lbl_temps.bind(size=lambda w, v: setattr(w, "text_size", v))
        self.add_widget(self.lbl_temps)

        self.lbl_detail = Label(text="", font_size=dp(11),
                                color=ECRAN_TEXTE_2, size_hint_y=None,
                                height=dp(16), halign="center",
                                valign="middle")
        self.lbl_detail.bind(size=lambda w, v: setattr(w, "text_size", v))
        self.add_widget(self.lbl_detail)
        self._maj_cadre()

    def _maj_cadre(self, *_a):
        x, y, w, h = self.x, self.y, self.width, self.height
        self._r_ombre.pos, self._r_ombre.size = (x, y - dp(2)), (w, h)
        self._r_fond.pos, self._r_fond.size = (x, y), (w, h)
        self._l_bord.rounded_rectangle = (x, y, w, h, dp(9))

    def afficher(self, ms, total_ms=None, echantillon=None,
                 total_ech=None, en_lecture=False):
        self.lbl_temps.text = horloge_precise(ms)
        self.lbl_temps.color = ECRAN_TEXTE_LECTURE if en_lecture \
            else ECRAN_TEXTE
        bouts = []
        if total_ms is not None:
            bouts.append("sur %s" % horloge_precise(total_ms))
        if echantillon is not None:
            if total_ech:
                bouts.append("ech. %d / %d" % (echantillon, total_ech))
            else:
                bouts.append("ech. %d" % echantillon)
        self.lbl_detail.text = "     ".join(bouts)

    def vider(self):
        self.lbl_temps.text = "0:00.000"
        self.lbl_temps.color = ECRAN_TEXTE
        self.lbl_detail.text = ""


class EcranBiblio(BoxLayout):
    """Bibliotheque : ranger, retrouver, renommer les prises.

    La bibliotheque n'est rien d'autre que le dossier enregistrements/
    et ses sous-dossiers. Aucun fichier d'index : si l'application
    disparait, les sons restent lisibles par n'importe quoi.
    """

    def __init__(self, journal, ouvrir_dans_edit, **kw):
        super().__init__(orientation="vertical", spacing=dp(6), **kw)
        self.journal = journal
        self.ouvrir_dans_edit = ouvrir_dans_edit
        self.dossier_courant = bib.RACINE
        self.tri = "date"
        self.recherche = ""

        r0 = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(6))
        self.spin_dossier = Choix(text=bib.RACINE, values=[bib.RACINE])
        self.spin_dossier.bind(text=self._changer_dossier)
        r0.add_widget(self.spin_dossier)
        b_new = Bouton(text="+ Dossier", couleur=CYAN, size_hint_x=0.38,
                       font_size=dp(12))
        b_new.bind(on_release=lambda *_: self.nouveau_dossier())
        r0.add_widget(b_new)
        self.add_widget(r0)

        r1 = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(6))
        self.champ = TextInput(hint_text="chercher", multiline=False,
                               font_size=dp(14), size_hint_x=0.5)
        self.champ.bind(text=self._changer_recherche)
        r1.add_widget(self.champ)
        self.spin_tri = Choix(text="date", values=list(bib.TRIS),
                              size_hint_x=0.28, font_size=dp(12))
        self.spin_tri.bind(text=self._changer_tri)
        r1.add_widget(self.spin_tri)
        b_maj = Bouton(text="Actualiser", size_hint_x=0.32, font_size=dp(11))
        b_maj.bind(on_release=lambda *_: self.rafraichir())
        r1.add_widget(b_maj)
        self.add_widget(r1)

        self.lbl_etat = Label(text="", size_hint_y=None, height=dp(22),
                              font_size=dp(11), color=TEXTE_2)
        self.add_widget(self.lbl_etat)

        sv = ScrollView(do_scroll_x=False)
        self.liste = BoxLayout(orientation="vertical", spacing=dp(4),
                               size_hint_y=None, padding=(0, 0, dp(4), 0))
        self.liste.bind(minimum_height=self.liste.setter("height"))
        sv.add_widget(self.liste)
        self.add_widget(sv)

        r2 = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(6))
        b_ren = Bouton(text="Renommer le dossier", font_size=dp(11))
        b_ren.bind(on_release=lambda *_: self.renommer_dossier())
        r2.add_widget(b_ren)
        b_sup = Bouton(text="Supprimer le dossier", font_size=dp(11),
                       couleur=ROUGE_SOMBRE)
        b_sup.bind(on_release=lambda *_: self.supprimer_dossier())
        r2.add_widget(b_sup)
        self.add_widget(r2)

        self.rafraichir()

    # ------------------------------------------------------------ chemins
    def racine(self):
        return dossier_sons()

    def chemin_dossier(self):
        if self.dossier_courant == bib.RACINE:
            return self.racine()
        return os.path.join(self.racine(), self.dossier_courant)

    # ------------------------------------------------------------ etat
    def _changer_dossier(self, _w, valeur):
        self.dossier_courant = valeur
        self.rafraichir()

    def _changer_tri(self, _w, valeur):
        self.tri = valeur
        self.rafraichir()

    def _changer_recherche(self, _w, valeur):
        self.recherche = valeur
        self.rafraichir()

    def rafraichir(self):
        """Relit le disque et redessine la liste.

        On relit a chaque fois plutot que de garder un cache : c'est le
        seul moyen de voir tout de suite une prise qui vient d'etre
        enregistree.
        """
        racine = self.racine()
        dossiers = [bib.RACINE] + bib.lister_dossiers(racine)
        self.spin_dossier.values = dossiers
        if self.dossier_courant not in dossiers:
            self.dossier_courant = bib.RACINE
            self.spin_dossier.text = bib.RACINE

        items = bib.lister_sons(self.chemin_dossier())
        total = len(items)
        items = bib.chercher(items, self.recherche)
        items = bib.trier(items, self.tri)

        self.liste.clear_widgets()
        if not items:
            self.liste.add_widget(Label(
                text="(aucun son ici)" if not self.recherche
                else "(rien qui corresponde)",
                size_hint_y=None, height=dp(60), font_size=dp(12),
                color=TEXTE_2))
        for it in items:
            self.liste.add_widget(self._ligne(it))

        duree = sum(i["duree_ms"] for i in items)
        vu = "%d son%s" % (len(items), "s" if len(items) > 1 else "")
        if len(items) != total:
            vu += " sur %d" % total
        self.lbl_etat.text = "%s   %s" % (vu, bib.duree_courte(duree))

    def _ligne(self, item):
        b = Bouton(text="%s\n[size=10sp]%s   %s[/size]" % (
            item["nom"], bib.duree_courte(item["duree_ms"]),
            bib.taille_courte(item["taille"])),
            markup=True, halign="left", size_hint_y=None, height=dp(52),
            font_size=dp(13))
        b.bind(size=lambda w, v: setattr(w, "text_size",
                                         (v[0] - dp(16), v[1])))
        b.bind(on_release=lambda w, i=item: self.menu(i))
        return b

    # ------------------------------------------------------------ menu
    def menu(self, item):
        ChoixPopup(item["nom"], [
            ("Ouvrir dans EDIT.", "ouvrir", CYAN),
            ("Ecouter", "ecouter", VERT),
            ("Renommer", "renommer", GRIS),
            ("Deplacer vers...", "deplacer", GRIS),
            ("Supprimer", "supprimer", ROUGE_SOMBRE),
        ], lambda cle: self._action(cle, item)).open()

    def _action(self, cle, item):
        if cle == "ouvrir":
            self.ouvrir(item)
        elif cle == "ecouter":
            self.ecouter(item)
        elif cle == "renommer":
            NomPopup("Nouveau nom", item["nom"],
                     lambda n: self.renommer(item, n)).open()
        elif cle == "deplacer":
            self.choisir_destination(item)
        elif cle == "supprimer":
            ChoixPopup("Supprimer %s ?" % item["nom"],
                       [("Oui, supprimer", "oui", ROUGE_SOMBRE)],
                       lambda _c: self.supprimer(item)).open()

    # ------------------------------------------------------------ actions
    def ouvrir(self, item):
        try:
            s = audio.read_wav(item["chemin"])
            self.ouvrir_dans_edit(s, item["nom"])
            self.journal("Ouvert : %s" % item["nom"])
        except Exception as e:  # noqa: BLE001
            self.journal("Lecture impossible : %s" % e)

    def ecouter(self, item):
        try:
            jouer_sample(audio.read_wav(item["chemin"]), "biblio")
        except Exception as e:  # noqa: BLE001
            self.journal("Ecoute impossible : %s" % e)

    def renommer(self, item, nom):
        try:
            neuf = bib.renommer(item["chemin"], nom)
            self.journal("Renomme : %s" % os.path.basename(neuf))
            self.rafraichir()
        except Exception as e:  # noqa: BLE001
            self.journal("Renommage impossible : %s" % e)

    def choisir_destination(self, item):
        cibles = [(bib.RACINE, bib.RACINE, GRIS)]
        for n in bib.lister_dossiers(self.racine()):
            cibles.append((n, n, GRIS))
        cibles.append(("+ Nouveau dossier", "__neuf__", CYAN))
        ChoixPopup("Deplacer vers", cibles,
                   lambda c: self._deplacer_vers(item, c)).open()

    def _deplacer_vers(self, item, cible):
        if cible == "__neuf__":
            NomPopup("Nom du dossier", "",
                     lambda n: self._deplacer_vers(item, n)).open()
            return
        try:
            dest = self.racine() if cible == bib.RACINE \
                else bib.creer_dossier(self.racine(), cible)
            bib.deplacer(item["chemin"], dest)
            self.journal("%s -> %s" % (item["nom"], cible))
            self.rafraichir()
        except Exception as e:  # noqa: BLE001
            self.journal("Deplacement impossible : %s" % e)

    def supprimer(self, item):
        if bib.supprimer(item["chemin"]):
            self.journal("Supprime : %s" % item["nom"])
        else:
            self.journal("Suppression impossible : %s" % item["nom"])
        self.rafraichir()

    # ------------------------------------------------------------ dossiers
    def nouveau_dossier(self):
        NomPopup("Nom du dossier", "", self._creer_dossier).open()

    def _creer_dossier(self, nom):
        try:
            bib.creer_dossier(self.racine(), nom)
            self.journal("Dossier cree : %s" % bib.nom_propre(nom, "dossier"))
            self.rafraichir()
            self.spin_dossier.text = bib.nom_propre(nom, "dossier")
        except Exception as e:  # noqa: BLE001
            self.journal("Creation impossible : %s" % e)

    def renommer_dossier(self):
        if self.dossier_courant == bib.RACINE:
            self.journal("Choisis d'abord un dossier a renommer.")
            return
        NomPopup("Nouveau nom du dossier", self.dossier_courant,
                 self._renommer_dossier).open()

    def _renommer_dossier(self, nom):
        try:
            bib.renommer_dossier(self.racine(), self.dossier_courant, nom)
            self.journal("Dossier renomme : %s" % bib.nom_propre(nom))
            self.dossier_courant = bib.nom_propre(nom)
            self.spin_dossier.text = self.dossier_courant
            self.rafraichir()
        except FileExistsError:
            self.journal("Un dossier porte deja ce nom.")
        except Exception as e:  # noqa: BLE001
            self.journal("Renommage impossible : %s" % e)

    def supprimer_dossier(self):
        if self.dossier_courant == bib.RACINE:
            self.journal("Le dossier principal ne peut pas etre supprime.")
            return
        n = bib.compter(self.chemin_dossier())
        if n:
            self.journal(
                "%s contient encore %d son(s) : deplace-les d'abord."
                % (self.dossier_courant, n))
            return
        if bib.supprimer_dossier(self.racine(), self.dossier_courant):
            self.journal("Dossier supprime : %s" % self.dossier_courant)
            self.dossier_courant = bib.RACINE
            self.spin_dossier.text = bib.RACINE
        self.rafraichir()


class EcranTuto(BoxLayout):
    TEXTE = """Tibrecord

ENREG.
  Appuie sur ENREGISTRER. Le minuteur et le vu-metre suivent la prise.
  Vise entre -12 et -6 dB : au-dela le rouge signale l'ecretage.
  Qualite : 44100 Hz par defaut. Descendre economise de la place.
  Source : micro ordinaire, camera (plus directif) ou brut (sans
  traitement du telephone, quand l'appareil le permet).

EDIT.
  La forme d'onde se ZOOME : jusqu'a voir les echantillons un par un.
  Les deux poignees orange delimitent la selection.
  Sous l'onde, la reglette donne le temps. Les grands traits sont
  chiffres, les petits marquent les cinquiemes. Elle se resserre quand
  tu zoomes : de la minute au dixieme de milliseconde.
  Le petit ecran en haut donne la position au millieme de seconde.
  A l'arret il montre le debut de la selection, donc l'endroit exact
  de la coupe. Pendant la lecture il passe au jaune et defile, en
  meme temps que la barre sur l'onde.
  Le compteur du bas affiche la selection entiere et les numeros
  d'echantillon.

  Rogner      reduit le son a la selection
  Normaliser  amene la crete a -0,3 dB
  Fondus      evite les clics au debut et a la fin
  Traiter     applique un preset complet
  Annuler     revient en arriere, 12 etapes

  Enregistrer ecrit un WAV mono 16 bits 44,1 kHz.

BIBLIO.
  Tes prises rangees. Choisis un dossier en haut, cherche par nom,
  trie par date, nom, duree ou taille.
  Appuie sur un son pour l'ouvrir dans EDIT., l'ecouter, le renommer,
  le deplacer dans un dossier ou le supprimer.
  + Dossier cree un rangement : kicks, voix, ambiances...
  Un dossier ne se supprime que s'il est vide : on ne perd pas dix
  prises d'un seul appui.

OU SONT LES FICHIERS
  Dans le sous-dossier enregistrements/ du dossier de l'application,
  et dans ses sous-dossiers pour ce qui est range.
  Ce sont de vrais fichiers WAV : aucun catalogue cache, rien a
  exporter. Le chemin exact s'affiche dans le journal a chaque
  ecriture.

SI CA PLANTE
  L'application affiche la trace en vert au lieu de disparaitre, et
  l'ecrit dans tibrecord_crash.txt. Envoie-la pour signaler un probleme.
"""

    def __init__(self, **kw):
        super().__init__(orientation="vertical", **kw)
        sv = ScrollView()
        lbl = Label(text=self.TEXTE, size_hint_y=None, halign="left",
                    valign="top", font_size=dp(12), color=TEXTE,
                    padding=(dp(8), dp(8)))
        lbl.bind(texture_size=lambda i, v: setattr(i, "height", v[1]),
                 width=lambda i, v: setattr(i, "text_size", (v, None)))
        sv.add_widget(lbl)
        self.add_widget(sv)


class EcranErreur(BoxLayout):
    def __init__(self, texte, titre="PLANTAGE", **kw):
        super().__init__(orientation="vertical", spacing=dp(6),
                         padding=dp(10), **kw)
        self.chemin = journal_crash(texte)
        self.add_widget(Label(text="[b]%s[/b]" % titre, markup=True,
                              size_hint_y=None, height=dp(30),
                              color=(1, 0.45, 0.3, 1)))
        self.add_widget(Label(
            text=("Trace : %s" % self.chemin) if self.chemin else "",
            size_hint_y=None, height=dp(34), font_size=dp(10),
            color=TEXTE_2))
        sv = ScrollView()
        lbl = Label(text=texte, size_hint_y=None, halign="left",
                    valign="top", font_size=dp(10),
                    color=(0.45, 1.0, 0.45, 1))
        lbl.bind(texture_size=lambda i, v: setattr(i, "height", v[1]),
                 width=lambda i, v: setattr(i, "text_size", (v, None)))
        sv.add_widget(lbl)
        self.add_widget(sv)


# --------------------------------------------------------------------------
class Root(BoxLayout):
    ONGLETS = ("ENREG.", "EDIT.", "BIBLIO.", "TUTO")

    def __init__(self, **kw):
        super().__init__(orientation="vertical", spacing=dp(6),
                         padding=dp(8), **kw)
        self.add_widget(self._entete())

        barre = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(5))
        self.tabs = []
        for i, nom in enumerate(self.ONGLETS):
            b = Bouton(text=nom, font_size=dp(11), rayon=6)
            b.bind(on_release=lambda w, k=i: self.afficher(k))
            self.tabs.append(b)
            barre.add_widget(b)
        self.add_widget(barre)

        self.zone = BoxLayout()
        self.add_widget(self.zone)

        sv = ScrollView(size_hint_y=0.22)
        self.log = Label(text="Pret.\n", size_hint_y=None, halign="left",
                         valign="top", font_size=dp(11), color=TEXTE_2)
        self.log.bind(texture_size=lambda i, v: setattr(i, "height", v[1]),
                      width=lambda i, v: setattr(i, "text_size", (v, None)))
        sv.add_widget(self.log)
        self.add_widget(sv)

        self.ec_edit = self._fabriquer("EDIT.", EcranEdit, self.journal)
        self.ec_biblio = self._fabriquer("BIBLIO.", EcranBiblio,
                                         self.journal, self._ouvrir_depuis)
        self.ecrans = [
            self._fabriquer("ENREG.", EcranEnreg, self.journal,
                            self._apres_capture),
            self.ec_edit,
            self.ec_biblio,
            self._fabriquer("TUTO", EcranTuto),
        ]
        self.afficher(0)

    @staticmethod
    def _entete():
        """Le logo s'il est la, le titre ecrit sinon."""
        logo = fichier_asset("logo.png")
        if logo:
            barre = BoxLayout(size_hint_y=None, height=dp(46),
                              padding=(0, dp(2)))
            barre.add_widget(KivyImage(source=logo, allow_stretch=True,
                                       keep_ratio=True))
            v = Label(text="v%s" % __version__, size_hint_x=None,
                      width=dp(34), font_size=dp(10), color=TEXTE_2)
            barre.add_widget(v)
            return barre
        return Label(
            text="[b]Tibrecord[/b]  [size=12sp]v%s[/size]" % __version__,
            markup=True, size_hint_y=None, height=dp(32), color=CYAN)

    def _fabriquer(self, nom, classe, *args):
        try:
            return classe(*args)
        except Exception as e:  # noqa: BLE001
            self.journal("ECHEC de l'onglet %s : %s" % (nom, e))
            return EcranErreur(trace_complete(e), "ONGLET %s" % nom)

    def _apres_capture(self, sample):
        if isinstance(self.ec_edit, EcranEdit):
            self.ec_edit.poser(sample, "enregistrement")
            self.afficher(1)

    def _ouvrir_depuis(self, sample, nom):
        """Un son de la bibliotheque part vers l'onglet EDIT."""
        if isinstance(self.ec_edit, EcranEdit):
            self.ec_edit.poser(sample, nom)
            self.afficher(1)

    @mainthread
    def journal(self, txt):
        lignes = self.log.text.split("\n")
        if len(lignes) > 200:
            self.log.text = "\n".join(lignes[-120:])
        self.log.text += txt + "\n"

    def afficher(self, i):
        arreter_lecture()
        if isinstance(self.ec_edit, EcranEdit):
            self.ec_edit._arreter_tete()
        # En arrivant sur la bibliotheque on relit le disque : une prise
        # enregistree entre-temps doit apparaitre sans rien demander.
        if self.ONGLETS[i] == "BIBLIO." and isinstance(self.ec_biblio,
                                                       EcranBiblio):
            self.ec_biblio.rafraichir()
        self.zone.clear_widgets()
        self.zone.add_widget(self.ecrans[i])
        for j, b in enumerate(self.tabs):
            b.set_couleur(CYAN if j == i else GRIS)


class TibrecordApp(App):
    title = "Tibrecord"

    def build(self):
        Window.clearcolor = FOND

        def _hook(t, v, tr):
            try:
                import traceback as tb
                journal_crash("".join(tb.format_exception(t, v, tr)))
            except Exception:  # noqa: BLE001
                pass
            sys.__excepthook__(t, v, tr)

        sys.excepthook = _hook

        if IS_ANDROID:
            Clock.schedule_once(lambda *_: self._permissions(), 0.5)
        try:
            return Root()
        except Exception as e:  # noqa: BLE001
            return EcranErreur(trace_complete(e), "DEMARRAGE")

    @staticmethod
    def _permissions():
        try:
            from android.permissions import Permission, request_permissions
            voulues = []
            for nom in ("RECORD_AUDIO", "READ_EXTERNAL_STORAGE",
                        "WRITE_EXTERNAL_STORAGE", "READ_MEDIA_AUDIO"):
                p = getattr(Permission, nom, None)
                if p:
                    voulues.append(p)
            if voulues:
                request_permissions(voulues)
        except Exception:  # noqa: BLE001
            pass


if __name__ == "__main__":
    TibrecordApp().run()
