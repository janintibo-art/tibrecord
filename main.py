#!/usr/bin/env python3
"""
Tibrecord — enregistrement et travail du son au telephone.

Trois ecrans pour demarrer :
  ENREG.  capture au micro, vu-metre, minuteur
  EDIT.   forme d'onde zoomable, decoupe, traitement, ecoute
  TUTO    ce qu'il faut savoir

Sans Kivy : utiliser cli.py.
"""

import math
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
from kivy.graphics import (Color, Ellipse, Line, Rectangle,
                           RoundedRectangle, Triangle)
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
from kivy.uix.widget import Widget

from noyau import (__version__, audio, bibliotheque as bib, decoupe,
                   effets, enregistrement, montage,
                   spectre as noyau_spectre, stockage, travail,
                   vignettes)
from noyau.temps import horloge_precise, pulsation
from onde import Onde, Regle, horloge, position_texte

# ---------------------------------------------------------------- palette
# Direction visuelle : console de studio sombre, contraste net, cyan froid
# pour les actions principales et rouge reserve a l'enregistrement/danger.
FOND = (0.030, 0.033, 0.043, 1)
FOND_HAUT = (0.055, 0.064, 0.078, 1)
FOND_BAS = (0.018, 0.020, 0.028, 1)
PANNEAU = (0.080, 0.086, 0.103, 1)
PANNEAU_2 = (0.105, 0.112, 0.132, 1)
BORD = (0.19, 0.22, 0.27, 1)
CYAN = (0.12, 0.76, 0.84, 1)
CYAN_S = (0.055, 0.31, 0.36, 1)
ROUGE = (0.92, 0.20, 0.23, 1)
VERT = (0.15, 0.68, 0.40, 1)
ORANGE = (0.95, 0.58, 0.15, 1)
AMBRE = (1.00, 0.73, 0.20, 1)
GRIS = (0.155, 0.165, 0.195, 1)
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
GRIS_CHOIX = (0.205, 0.218, 0.255, 1)
TEXTE = (0.93, 0.94, 0.96, 1)
TEXTE_2 = (0.60, 0.64, 0.71, 1)

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


def texture_degrade(couleur_bas, couleur_haut, hauteur=160):
    """Texture verticale legere pour le fond general de l'application."""
    cle = ("fond", tuple(couleur_bas[:3]), tuple(couleur_haut[:3]), hauteur)
    tex = _TEXTURES.get(cle)
    if tex is not None:
        return tex
    try:
        from kivy.graphics.texture import Texture
    except Exception:  # noqa: BLE001
        return None
    tex = Texture.create(size=(1, hauteur), colorfmt="rgba")
    buf = bytearray()
    for i in range(hauteur):
        t = i / float(max(1, hauteur - 1))
        # Beaucoup de sombre en bas, une lumiere tres discrete en haut.
        t = t * t * (3.0 - 2.0 * t)
        for c in range(3):
            v = couleur_bas[c] + (couleur_haut[c] - couleur_bas[c]) * t
            buf.append(int(max(0.0, min(1.0, v)) * 255))
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


class BoutonLed(Bouton):
    """Bouton avec une petite LED ronde en haut a droite.

    Eteinte, elle reste faiblement visible : comme sur un vrai rack, on
    voit l'emplacement de la lampe, donc on sait qu'elle peut s'allumer.
    Le niveau se pose de l'exterieur, depuis une minuterie qui tourne
    deja — ce widget n'a AUCUNE horloge a lui.
    """

    def __init__(self, led=(0.25, 0.90, 0.45), **kw):
        self._led_couleur = led
        self._led_niveau = 0.0
        super().__init__(**kw)
        with self.canvas.after:
            self._c_led_fond = Color(0, 0, 0, 0.55)
            self._led_fond = Ellipse()
            self._c_led = Color(led[0], led[1], led[2], 0.12)
            self._led = Ellipse()
        self.bind(pos=self._maj_led, size=self._maj_led,
                  state=self._maj_led)
        self._maj_led()

    def led(self, niveau):
        """0 eteinte, 1 pleine. Entre les deux : la respiration."""
        self._led_niveau = max(0.0, min(1.0, float(niveau)))
        self._maj_led()

    def _maj_led(self, *_a):
        d = dp(9)
        presse = self.state == "down"
        x = self.right - d - dp(7)
        y = self.top - d - dp(7) - (dp(2) if presse else 0)
        self._led_fond.pos = (x - dp(1.5), y - dp(1.5))
        self._led_fond.size = (d + dp(3), d + dp(3))
        self._led.pos = (x, y)
        self._led.size = (d, d)
        c = self._led_couleur
        n = self._led_niveau
        self._c_led.rgba = (c[0], c[1], c[2],
                            0.12 + 0.88 * n if n > 0 else 0.12)


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
    """Carte de studio : ombre, surface, bord fin et accent optionnel."""

    def __init__(self, fond=PANNEAU, rayon=12, accent=None, **kw):
        super().__init__(**kw)
        self._rayon = rayon
        self._accent = accent
        with self.canvas.before:
            self._c_ombre = Color(0, 0, 0, 0.42)
            self._ombre = RoundedRectangle(radius=[rayon])
            self._c_fond = Color(*fond)
            self._r = RoundedRectangle(radius=[rayon])
        with self.canvas.after:
            self._c_bord = Color(*BORD)
            self._bord = Line(width=1.0)
            self._c_accent = Color(*(accent or CYAN))
            self._trait = RoundedRectangle(radius=[2])
            self._c_accent.a = 1.0 if accent else 0.0
        self.bind(pos=self._maj, size=self._maj)
        self._maj()

    def _maj(self, *_a):
        x, y = self.x, self.y
        w, h = self.width, self.height
        self._ombre.pos = (x, y - dp(2))
        self._ombre.size = (w, h + dp(2))
        self._r.pos, self._r.size = (x, y), (w, h)
        self._bord.rounded_rectangle = (x, y, w, h, self._rayon)
        self._trait.pos = (x + dp(9), y + h - dp(3))
        self._trait.size = (max(0, w - dp(18)), dp(2))


class TitreSection(Label):
    """Petit titre technique qui structure les ecrans sans les surcharger."""

    def __init__(self, titre, sous_titre="", **kw):
        texte = "[b]%s[/b]" % titre.upper()
        if sous_titre:
            texte += "\n[size=10sp][color=#7f8999]%s[/color][/size]" % sous_titre
        kw.setdefault("text", texte)
        kw.setdefault("markup", True)
        kw.setdefault("color", TEXTE)
        kw.setdefault("font_size", dp(13))
        kw.setdefault("size_hint_y", None)
        kw.setdefault("height", dp(42 if sous_titre else 28))
        kw.setdefault("halign", "left")
        kw.setdefault("valign", "middle")
        super().__init__(**kw)
        self.bind(size=lambda w, v: setattr(w, "text_size", v))


class VuMetre(BoxLayout):
    """Vu-metre segmente type rack de studio, avec memoire de crete."""

    NB = 28

    def __init__(self, **kw):
        super().__init__(**kw)
        self.niveau = 0.0
        self.crete = 0.0
        self._segments = []
        with self.canvas:
            Color(0.025, 0.028, 0.036, 1)
            self._fond = RoundedRectangle(radius=[6])
            for _ in range(self.NB):
                c = Color(0.10, 0.12, 0.14, 1)
                r = RoundedRectangle(radius=[2])
                self._segments.append((c, r))
            self._cc = Color(0.95, 0.98, 1.0, 0.92)
            self._pic = RoundedRectangle(radius=[1])
        self.bind(pos=self._maj, size=self._maj)
        self._maj()

    def poser(self, niveau_db):
        self.niveau = max(0.0, min(1.0, (niveau_db + 60.0) / 60.0))
        self.crete = max(self.crete * 0.94, self.niveau)
        self._maj()

    def vider(self):
        self.niveau = 0.0
        self.crete = 0.0
        self._maj()

    def _maj(self, *_a):
        self._fond.pos, self._fond.size = self.pos, self.size
        espace = dp(2)
        marge = dp(4)
        dispo = max(1, self.width - marge * 2 - espace * (self.NB - 1))
        sw = max(dp(2), dispo / float(self.NB))
        h = max(dp(4), self.height - marge * 2)
        allumes = int(round(self.niveau * self.NB))
        for i, (c, r) in enumerate(self._segments):
            f = (i + 1) / float(self.NB)
            actif = i < allumes
            if f > 0.93:
                base = ROUGE
            elif f > 0.78:
                base = ORANGE
            else:
                base = VERT
            if actif:
                c.rgba = base
            else:
                c.rgba = (base[0] * 0.15, base[1] * 0.15,
                          base[2] * 0.15, 0.72)
            r.pos = (self.x + marge + i * (sw + espace), self.y + marge)
            r.size = (sw, h)
        x = self.x + marge + max(0.0, min(1.0, self.crete)) * max(1, self.width - 2 * marge)
        self._pic.pos = (max(self.x + marge, min(self.right - marge - dp(2), x - dp(1))),
                         self.y + dp(2))
        self._pic.size = (dp(2), max(dp(2), self.height - dp(4)))


class Molette(Widget):
    """Potentiometre tactile style rack.

    Glisser verticalement sur la molette pour modifier la valeur. Le widget
    ne depend d'aucune extension Kivy et reste donc leger pour Android.
    """

    def __init__(self, minimum=0.0, maximum=1.0, value=0.0,
                 callback=None, **kw):
        super().__init__(**kw)
        self.minimum = float(minimum)
        self.maximum = float(maximum)
        self.value = float(value)
        self.callback = callback
        self._touch_y = None
        self._touch_value = None
        with self.canvas:
            self._c_ombre = Color(0, 0, 0, 0.55)
            self._ombre = Ellipse()
            self._c_bague = Color(0.20, 0.23, 0.28, 1)
            self._bague = Ellipse()
            self._c_corps = Color(0.10, 0.11, 0.13, 1)
            self._corps = Ellipse()
            self._c_arc_fond = Color(0.24, 0.27, 0.32, 0.9)
            self._arc_fond = Line(width=dp(2.2))
            self._c_arc = Color(*CYAN)
            self._arc = Line(width=dp(2.6))
            self._c_trait = Color(0.92, 0.96, 1.0, 1)
            self._trait = Line(width=dp(2.0))
            self._c_reflet = Color(1, 1, 1, 0.08)
            self._reflet = Ellipse()
        self.bind(pos=self._maj, size=self._maj)
        self._maj()

    def poser(self, value, emettre=True):
        self.value = max(self.minimum, min(self.maximum, float(value)))
        self._maj()
        if emettre and self.callback:
            self.callback(self.value)

    def fraction(self):
        d = self.maximum - self.minimum
        return 0.0 if d <= 0 else (self.value - self.minimum) / d

    def _maj(self, *_a):
        d = min(self.width, self.height) * 0.78
        cx, cy = self.center
        x, y = cx - d / 2.0, cy - d / 2.0
        self._ombre.pos = (x, y - dp(2))
        self._ombre.size = (d, d)
        self._bague.pos = (x, y)
        self._bague.size = (d, d)
        m = d * 0.10
        self._corps.pos = (x + m, y + m)
        self._corps.size = (d - 2 * m, d - 2 * m)
        self._reflet.pos = (x + d * 0.27, y + d * 0.56)
        self._reflet.size = (d * 0.22, d * 0.13)

        r = d * 0.47
        # Course classique de potentiometre : minimum en bas a gauche,
        # maximum en bas a droite, avec une zone morte sous la molette.
        self._arc_fond.circle = (cx, cy, r, -45, 225)
        angle = 225.0 - 270.0 * self.fraction()
        self._arc.circle = (cx, cy, r, angle, 225)
        a = math.radians(angle)
        r0, r1 = d * 0.22, d * 0.39
        self._trait.points = [cx + math.cos(a) * r0,
                              cy + math.sin(a) * r0,
                              cx + math.cos(a) * r1,
                              cy + math.sin(a) * r1]

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            self._touch_y = touch.y
            self._touch_value = self.value
            touch.grab(self)
            return True
        return super().on_touch_down(touch)

    def on_touch_move(self, touch):
        if touch.grab_current is self and self._touch_y is not None:
            amplitude = max(dp(90), self.height * 1.7)
            delta = (touch.y - self._touch_y) / float(amplitude)
            self.poser(self._touch_value + delta * (self.maximum - self.minimum))
            return True
        return super().on_touch_move(touch)

    def on_touch_up(self, touch):
        if touch.grab_current is self:
            touch.ungrab(self)
            self._touch_y = None
            self._touch_value = None
            return True
        return super().on_touch_up(touch)


class Potard(BoxLayout):
    """Molette + nom + valeur, dimensionnee pour tenir sur un telephone."""

    def __init__(self, titre, minimum, maximum, value, unite="",
                 decimals=1, callback=None, **kw):
        super().__init__(orientation="vertical", spacing=0, **kw)
        self.titre = titre
        self.unite = unite
        self.decimals = decimals
        self.callback = callback
        self.lbl_titre = Label(text="[b]%s[/b]" % titre.upper(), markup=True,
                               size_hint_y=None, height=dp(17),
                               font_size=dp(8.5), color=TEXTE_2)
        self.add_widget(self.lbl_titre)
        self.molette = Molette(minimum=minimum, maximum=maximum, value=value,
                               callback=self._change)
        self.add_widget(self.molette)
        self.lbl_valeur = Label(size_hint_y=None, height=dp(18),
                                font_size=dp(9), color=CYAN)
        self.add_widget(self.lbl_valeur)
        self._change(value, emettre=False)

    @property
    def value(self):
        return self.molette.value

    def poser(self, value, emettre=False):
        self.molette.poser(value, emettre=emettre)
        self._change(self.molette.value, emettre=emettre)

    def _change(self, value, emettre=True):
        if self.decimals <= 0:
            txt = "%d" % int(round(value))
        else:
            txt = ("%%.%df" % self.decimals) % value
        self.lbl_valeur.text = "%s%s" % (txt, self.unite)
        if emettre and self.callback:
            self.callback(value)


class VoyantRec(Widget):
    """Voyant REC anime, volontairement discret quand il est inactif.

    L'animation ne tourne QUE pendant la capture. Au repos le voyant ne
    change pas d'aspect : faire tourner une horloge a 24 images par
    seconde pour redessiner trois ellipses identiques ne se verrait pas
    a l'ecran, mais se paierait en batterie du lancement a la fermeture.
    """

    def __init__(self, **kw):
        super().__init__(**kw)
        self.actif = False
        self._phase = 0.0
        self._tic = None
        with self.canvas:
            self._c_halo = Color(ROUGE[0], ROUGE[1], ROUGE[2], 0.0)
            self._halo = Ellipse()
            self._c_led = Color(0.28, 0.10, 0.11, 1)
            self._led = Ellipse()
            self._c_reflet = Color(1, 1, 1, 0.12)
            self._reflet = Ellipse()
        self.bind(pos=self._maj, size=self._maj)
        self._maj()

    def poser(self, actif):
        self.actif = bool(actif)
        if self.actif and self._tic is None:
            self._tic = Clock.schedule_interval(self._animer, 1 / 24.0)
        elif not self.actif and self._tic is not None:
            self._tic.cancel()
            self._tic = None
            self._phase = 0.0
        self._maj()

    def _animer(self, dt):
        self._phase = (self._phase + dt * 2.4) % 1.0
        self._maj()

    def _maj(self, *_a):
        d = min(self.width, self.height)
        cx, cy = self.center
        pulse = 0.5 + 0.5 * math.sin(self._phase * math.pi * 2.0)
        hd = d * (0.90 + (0.20 * pulse if self.actif else 0.0))
        self._halo.pos = (cx - hd / 2, cy - hd / 2)
        self._halo.size = (hd, hd)
        self._c_halo.a = (0.10 + 0.18 * pulse) if self.actif else 0.0
        ld = d * 0.50
        self._led.pos = (cx - ld / 2, cy - ld / 2)
        self._led.size = (ld, ld)
        self._c_led.rgba = ROUGE if self.actif else (0.30, 0.11, 0.12, 1)
        rd = ld * 0.28
        self._reflet.pos = (cx - ld * 0.18, cy + ld * 0.04)
        self._reflet.size = (rd, rd)
        self._c_reflet.a = 0.35 if self.actif else 0.10


class ScopeTempsReel(Widget):
    """Petit oscilloscope de monitoring utilisant les derniers echantillons."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.data = []
        self.bind(pos=self.redessiner, size=self.redessiner)

    def poser(self, data):
        self.data = list(data or [])
        self.redessiner()

    def redessiner(self, *_a):
        self.canvas.clear()
        x0, y0, w, h = self.x, self.y, self.width, self.height
        with self.canvas:
            Color(0.018, 0.022, 0.030, 1)
            RoundedRectangle(pos=(x0, y0), size=(w, h), radius=[7])
            Color(0.08, 0.11, 0.14, 1)
            for i in range(1, 8):
                x = x0 + w * i / 8.0
                Line(points=[x, y0, x, y0 + h], width=1)
            for i in range(1, 4):
                y = y0 + h * i / 4.0
                Line(points=[x0, y, x0 + w, y], width=1)
            Color(0.16, 0.25, 0.28, 1)
            Line(points=[x0, y0 + h / 2, x0 + w, y0 + h / 2], width=1)
            Color(*BORD)
            Line(rounded_rectangle=(x0, y0, w, h, 7), width=1)
            if len(self.data) < 2 or w < 4:
                return
            n = min(len(self.data), max(64, int(w / max(dp(1.4), 1))))
            src = self.data[-n:]
            points = []
            gain = h * 0.43
            mid = y0 + h / 2.0
            for i, v in enumerate(src):
                x = x0 + i * w / float(max(1, n - 1))
                y = mid + max(-1.0, min(1.0, v)) * gain
                points.extend((x, y))
            Color(CYAN[0], CYAN[1], CYAN[2], 0.15)
            Line(points=points, width=dp(3.2))
            Color(*CYAN)
            Line(points=points, width=dp(1.05))


class AnalyseurSpectre(Widget):
    """Analyseur 18 bandes. Le calcul vit dans noyau/spectre.py.

    Deux entrees : charger(sample) pour la vue figee du son entier, et
    poser_niveaux(valeurs) pour la vue animee qui suit la lecture. Le
    dessin est le meme, seule la source des barres change.
    """

    NB = noyau_spectre.NB_BANDES

    def __init__(self, **kw):
        super().__init__(**kw)
        self.valeurs = [0.0] * self.NB
        self.bind(pos=self.redessiner, size=self.redessiner)

    def charger(self, sample):
        self.valeurs = noyau_spectre.bandes_du_sample(sample, self.NB)
        self.redessiner()

    def poser_niveaux(self, valeurs):
        self.valeurs = list(valeurs)
        self.redessiner()

    def redessiner(self, *_a):
        self.canvas.clear()
        x0, y0, w, h = self.x, self.y, self.width, self.height
        with self.canvas:
            Color(0.018, 0.022, 0.030, 1)
            RoundedRectangle(pos=(x0, y0), size=(w, h), radius=[7])
            Color(0.075, 0.095, 0.12, 1)
            for j in range(1, 4):
                y = y0 + h * j / 4.0
                Line(points=[x0, y, x0 + w, y], width=1)
            espace = dp(3)
            marge = dp(7)
            bw = max(dp(3), (w - 2 * marge - espace * (self.NB - 1)) / self.NB)
            for i, v in enumerate(self.valeurs):
                bh = max(dp(2), (h - dp(12)) * v)
                bx = x0 + marge + i * (bw + espace)
                by = y0 + dp(6)
                if v > 0.88:
                    col = ORANGE
                elif v > 0.68:
                    col = AMBRE
                else:
                    col = CYAN
                Color(col[0], col[1], col[2], 0.16)
                RoundedRectangle(pos=(bx, by), size=(bw, h - dp(12)), radius=[2])
                Color(*col)
                RoundedRectangle(pos=(bx, by), size=(bw, bh), radius=[2])
            Color(*BORD)
            Line(rounded_rectangle=(x0, y0, w, h, 7), width=1)



# --------------------------------------------------------------------------
class Chooser(Popup):
    """Selecteur de fichiers avec raccourcis.

    Naviguer depuis /storage au doigt est intenable : la barre de
    raccourcis en haut fait l'essentiel du travail. Les dossiers refuses
    par Android y apparaissent en gris plutot que d'etre caches :
    l'information est donnee AVANT l'echec, pas apres.
    """

    def __init__(self, callback, dossiers=False, filtres=None, start=None,
                 journal=None, **kw):
        super().__init__(
            title="Choisir un dossier" if dossiers else "Choisir un fichier",
            size_hint=(0.96, 0.94), **kw)
        self.callback, self.dossiers = callback, dossiers
        self.journal = journal
        box = BoxLayout(orientation="vertical", spacing=dp(6), padding=dp(6))

        # --- raccourcis, detectes et jamais codes en dur
        barre = ScrollView(size_hint_y=None, height=dp(42),
                           do_scroll_y=False)
        rangee = BoxLayout(size_hint_x=None, spacing=dp(5), height=dp(38))
        rangee.bind(minimum_width=rangee.setter("width"))
        for nom, chemin, ok in stockage.raccourcis():
            b = Bouton(text=nom, size_hint=(None, None),
                       width=max(dp(84), dp(9) * len(nom)), height=dp(38),
                       font_size=dp(10), rayon=7,
                       couleur=GRIS if ok else (0.13, 0.13, 0.16, 1))
            if not ok:
                b.color = (0.45, 0.45, 0.50, 1)
            b.bind(on_release=lambda w, c=chemin, o=ok: self._raccourci(c, o))
            rangee.add_widget(b)
        barre.add_widget(rangee)
        box.add_widget(barre)

        depart = start or dossier_sons()
        if not stockage.lisible(depart):
            depart = stockage.dossier_prive()
        self.chooser = FileChooserListView(
            path=depart, dirselect=dossiers, filters=filtres or ["*"])
        box.add_widget(self.chooser)

        # --- chemin tapable : dernier recours, mais debloque des
        #     situations autrement sans issue
        self.champ = TextInput(text=self.chooser.path, multiline=False,
                               size_hint_y=None, height=dp(40))
        self.champ.bind(on_text_validate=lambda *_: self._aller(
            self.champ.text.strip()))
        box.add_widget(self.champ)

        self.lbl = Label(text="", size_hint_y=None, height=dp(24),
                         font_size=dp(11), color=(0.95, 0.55, 0.35, 1),
                         shorten=True)
        self.lbl.bind(size=lambda w, v: setattr(w, "text_size", v))
        box.add_widget(self.lbl)
        if not stockage.acces_complet():
            self.lbl.text = ("Acces limite : beaucoup de dossiers seront "
                             "refuses. Bouton ACCES FICHIERS dans SONS.")

        r = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(6))
        b_no = Bouton(text="Annuler")
        b_no.bind(on_release=lambda *_: self.dismiss())
        r.add_widget(b_no)
        b_ok = Bouton(text="Choisir", couleur=CYAN)
        b_ok.bind(on_release=self._ok)
        r.add_widget(b_ok)
        box.add_widget(r)
        self.add_widget(box)

    def _raccourci(self, chemin, ok):
        if ok:
            self._aller(chemin)
            return
        if chemin.startswith("("):
            self.lbl.text = ("Aucune carte SD detectee sur cet appareil. "
                             "DIAGNOSTIC dans SONS pour en savoir plus.")
        else:
            self.lbl.text = "Android refuse ce dossier : %s" % chemin

    def _aller(self, chemin):
        if not os.path.isdir(chemin):
            self.lbl.text = "Dossier introuvable : %s" % chemin
            return
        if not stockage.lisible(chemin):
            self.lbl.text = "Android refuse la lecture de %s" % chemin
            return
        self.chooser.path = chemin
        self.champ.text = chemin
        self.lbl.text = ""

    def _ok(self, *_):
        sel = self.chooser.selection
        if self.dossiers:
            c = sel[0] if sel else self.chooser.path
            self.dismiss()
            self.callback(os.path.dirname(c) if os.path.isfile(c) else c)
            return
        if not sel:
            self.lbl.text = "Appuie d'abord sur un FICHIER dans la liste."
            return
        if os.path.isdir(sel[0]):
            self.chooser.path = sel[0]
            self.champ.text = sel[0]
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
        # Pose par Root apres construction : recoit (actif, niveau) et
        # allume la LED de l'onglet REC. Peut rester None.
        self.sur_etat_rec = None
        self.enr = enregistrement.Enregistreur()
        self._tic = None

        page = ScrollView(do_scroll_x=False)
        corps = BoxLayout(orientation="vertical", spacing=dp(8),
                          size_hint_y=None, padding=(0, 0, 0, dp(8)))
        corps.bind(minimum_height=corps.setter("height"))
        page.add_widget(corps)
        BoxLayout.add_widget(self, page)

        corps.add_widget(TitreSection(
            "Capture audio", "Monitoring temps reel et prise haute qualite"))

        etat_studio = Panneau(orientation="horizontal", size_hint_y=None,
                              height=dp(38), padding=(dp(8), dp(3)),
                              spacing=dp(5), fond=(0.045, 0.050, 0.060, 1))
        self.voyant_rec = VoyantRec(size_hint_x=None, width=dp(30))
        etat_studio.add_widget(self.voyant_rec)
        etat_studio.add_widget(Label(
            text="[b]INPUT MONITOR[/b]   [color=#6d7787]MONO / PCM 16-bit[/color]",
            markup=True, halign="left", valign="middle",
            font_size=dp(10), color=TEXTE))
        corps.add_widget(etat_studio)

        afficheur = Panneau(orientation="vertical", size_hint_y=None,
                            height=dp(100), padding=(dp(12), dp(6)),
                            spacing=0, fond=ECRAN_FOND, accent=CYAN)
        afficheur.add_widget(Label(text="TEMPS D'ENREGISTREMENT",
                                   size_hint_y=None, height=dp(22),
                                   font_size=dp(9), color=ECRAN_TEXTE_2))
        self.lbl_temps = Label(text="0:00.000", font_size=dp(42),
                               color=ECRAN_TEXTE)
        afficheur.add_widget(self.lbl_temps)
        corps.add_widget(afficheur)

        cadre = Panneau(orientation="vertical", size_hint_y=None,
                        height=dp(94), padding=(dp(10), dp(7)), spacing=dp(5))
        ligne_niveau = BoxLayout(size_hint_y=None, height=dp(22))
        ligne_niveau.add_widget(Label(text="[b]INPUT[/b]", markup=True,
                                      halign="left", font_size=dp(10),
                                      color=TEXTE_2))
        self.lbl_niveau = Label(text="-inf dB", font_size=dp(10),
                                color=TEXTE_2, halign="right")
        ligne_niveau.add_widget(self.lbl_niveau)
        cadre.add_widget(ligne_niveau)
        self.vu = VuMetre(size_hint_y=None, height=dp(36))
        cadre.add_widget(self.vu)
        cadre.add_widget(Label(text="-60        -24        -12       -6      0 dB",
                               font_size=dp(8), color=(0.42, 0.46, 0.53, 1),
                               size_hint_y=None, height=dp(16)))
        corps.add_widget(cadre)

        scope_box = Panneau(orientation="vertical", size_hint_y=None,
                            height=dp(96), padding=(dp(8), dp(5)),
                            spacing=dp(3), fond=(0.040, 0.046, 0.057, 1),
                            accent=CYAN)
        scope_box.add_widget(Label(text="LIVE WAVEFORM", size_hint_y=None,
                                   height=dp(16), halign="left",
                                   font_size=dp(9), color=TEXTE_2))
        self.scope = ScopeTempsReel()
        scope_box.add_widget(self.scope)
        corps.add_widget(scope_box)

        reglages = Panneau(orientation="vertical", size_hint_y=None,
                           height=dp(104), padding=dp(8), spacing=dp(4))
        r = BoxLayout(size_hint_y=None, height=dp(43), spacing=dp(7))
        r.add_widget(Label(text="QUALITE", size_hint_x=0.30, color=TEXTE_2,
                           font_size=dp(10), halign="left"))
        self.spin_taux = Choix(text="44100",
                               values=[str(t) for t in enregistrement.TAUX_POSSIBLES])
        r.add_widget(self.spin_taux)
        reglages.add_widget(r)

        r2 = BoxLayout(size_hint_y=None, height=dp(43), spacing=dp(7))
        r2.add_widget(Label(text="SOURCE", size_hint_x=0.30, color=TEXTE_2,
                            font_size=dp(10), halign="left"))
        self.spin_source = Choix(text="micro", values=["micro", "camera", "brut"])
        r2.add_widget(self.spin_source)
        reglages.add_widget(r2)
        corps.add_widget(reglages)

        self.b_rec = Bouton(
            text="[b]●  ENREGISTRER[/b]\n[size=10sp]Nouvelle prise audio[/size]",
            couleur=ROUGE, size_hint_y=None, height=dp(74),
            font_size=dp(16), rayon=15)
        self.b_rec.bind(on_release=lambda *_: self.basculer())
        corps.add_widget(self.b_rec)

        self.lbl_etat = Label(text="Initialisation du moteur audio...",
                              size_hint_y=None, height=dp(38),
                              font_size=dp(10), color=TEXTE_2)
        corps.add_widget(self.lbl_etat)
        corps.add_widget(BoxLayout())

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
        self.b_rec.text = "[b]ARRETER[/b]\n[size=10sp]Enregistrement en cours[/size]"
        self.b_rec.set_couleur(ROUGE_SOMBRE)
        self.lbl_temps.color = (1.0, 0.42, 0.45, 1)
        self.lbl_etat.text = "REC  •  capture active"
        self.voyant_rec.poser(True)
        self.vu.crete = 0.0
        self.scope.poser([])
        self._tic = Clock.schedule_interval(self._maj, 1 / 24.0)
        if self.sur_etat_rec:
            self.sur_etat_rec(True, 1.0)
        self.journal("Enregistrement a %s Hz." % self.spin_taux.text)

    def _maj(self, _dt):
        # La LED de l'onglet respire au rythme de CETTE minuterie, qui
        # tourne de toute facon pendant la capture : aucune horloge en
        # plus, et elle s'arrete forcement avec elle.
        if self.sur_etat_rec:
            self.sur_etat_rec(True, pulsation(time.time(), vitesse=3.2,
                                              mini=0.30))
        self.lbl_temps.text = horloge(self.enr.duree_s)
        db = self.enr.niveau_db()
        self.vu.poser(db)
        # Garde-fou : si le noyau est plus ancien que l'interface,
        # l'oscilloscope s'efface au lieu de faire perdre la prise en
        # cours. Une capture qui continue vaut mieux qu'un plantage.
        instantane = getattr(self.enr, "instantane", None)
        self.scope.poser(instantane(420) if instantane else [])
        rms_db = audio.lin_to_db(self.enr.rms_courant)
        if db > -90:
            self.lbl_niveau.text = "PK %.1f  /  RMS %.1f dB" % (db, rms_db)
        else:
            self.lbl_niveau.text = "-inf dB"
        if self.enr.derniere_erreur:
            self.lbl_etat.text = self.enr.derniere_erreur
            self.arreter()
            return False
        return True

    def arreter(self):
        if self._tic:
            self._tic.cancel()
            self._tic = None
        if self.sur_etat_rec:
            self.sur_etat_rec(False, 0.0)
        sample = self.enr.arreter()
        self.b_rec.text = "[b]●  ENREGISTRER[/b]\n[size=10sp]Nouvelle prise audio[/size]"
        self.b_rec.set_couleur(ROUGE)
        self.lbl_temps.color = ECRAN_TEXTE
        self.voyant_rec.poser(False)
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
        self._serie = travail.Serie()
        self._pause_frac = None
        self._seg = None
        self._presse_papiers = None
        self._segments = []
        self._tic_spectre = None
        self._spectre_vif = []

        page = ScrollView(do_scroll_x=False)
        corps = BoxLayout(orientation="vertical", spacing=dp(6),
                          size_hint_y=None, padding=(0, 0, 0, dp(6)))
        corps.bind(minimum_height=corps.setter("height"))
        page.add_widget(corps)
        BoxLayout.add_widget(self, page)

        corps.add_widget(TitreSection(
            "Editeur audio", "Selection precise, lecture et traitements non destructifs"))

        r_e = BoxLayout(size_hint_y=None, height=dp(50), spacing=dp(5))
        b_ret = Bouton(text="RETOUR", couleur=GRIS, font_size=dp(12),
                       size_hint_x=0.72)
        b_ret.bind(on_release=lambda *_: self.retour())
        r_e.add_widget(b_ret)
        self.b_lire = BoutonLed(text="LIRE", couleur=VERT,
                                led=(0.35, 0.95, 0.55), font_size=dp(12))
        self.b_lire.bind(on_release=lambda *_: self.lire())
        r_e.add_widget(self.b_lire)
        self.b_pause = BoutonLed(text="PAUSE",
                                 couleur=(0.72, 0.55, 0.13, 1),
                                 led=(1.0, 0.80, 0.25),
                                 font_size=dp(12), size_hint_x=0.86)
        self.b_pause.bind(on_release=lambda *_: self.pauser())
        r_e.add_widget(self.b_pause)
        b_stp = Bouton(text="STOP", couleur=GRIS, font_size=dp(12),
                       size_hint_x=0.72)
        b_stp.bind(on_release=lambda *_: self.stopper())
        r_e.add_widget(b_stp)
        corps.add_widget(r_e)

        self.lbl_nom = Label(text="(aucun son)", size_hint_y=None,
                             height=dp(24), font_size=dp(12), shorten=True,
                             color=TEXTE_2)
        corps.add_widget(self.lbl_nom)

        self.compteur = Compteur()
        corps.add_widget(self.compteur)

        cadre = Panneau(orientation="vertical", size_hint_y=None,
                        height=dp(292), padding=dp(7), spacing=dp(3),
                        fond=(0.045, 0.050, 0.062, 1), accent=CYAN)
        self.onde = Onde(on_change=self._maj_mesures)
        cadre.add_widget(self.onde)
        self.regle = Regle(self.onde, size_hint_y=None, height=dp(20))
        self.onde.regle = self.regle
        cadre.add_widget(self.regle)
        corps.add_widget(cadre)

        self.lbl_mes = Label(text="", size_hint_y=None, height=dp(44),
                             font_size=dp(11), color=TEXTE)
        corps.add_widget(self.lbl_mes)

        spectre_box = Panneau(orientation="vertical", size_hint_y=None,
                              height=dp(142), padding=(dp(7), dp(5)),
                              spacing=dp(3), fond=(0.040, 0.046, 0.057, 1),
                              accent=AMBRE)
        spectre_box.add_widget(Label(
            text="SPECTRUM ANALYZER", size_hint_y=None, height=dp(18),
            font_size=dp(9), color=TEXTE_2, halign="left"))
        self.spectre = AnalyseurSpectre()
        spectre_box.add_widget(self.spectre)
        spectre_box.add_widget(Label(
            text="55 Hz          250          1 kHz          4 kHz          16 kHz",
            size_hint_y=None, height=dp(14), font_size=dp(8),
            color=(0.42, 0.46, 0.53, 1)))
        corps.add_widget(spectre_box)

        corps.add_widget(TitreSection("Navigation dans l'onde"))
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

        corps.add_widget(TitreSection(
            "Fichier", "Ouvrir un WAV du telephone, ecrire dans SONS"))
        r0 = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(6))
        b_o = Bouton(text="OUVRIR WAV", couleur=CYAN)
        b_o.bind(on_release=lambda *_: Chooser(
            self.charger_fichier, filtres=["*.wav", "*.WAV"]).open())
        r0.add_widget(b_o)
        b_s = Bouton(text="SAUVEGARDER", couleur=VERT)
        b_s.bind(on_release=lambda *_: self.sauver())
        r0.add_widget(b_s)
        corps.add_widget(r0)

        corps.add_widget(TitreSection(
            "Rack Studio", "EQ, dynamique et saturation — glisser verticalement sur les molettes"))
        rack = Panneau(orientation="vertical", size_hint_y=None,
                       height=dp(500), padding=(dp(8), dp(7)), spacing=dp(5),
                       fond=(0.045, 0.049, 0.059, 1), accent=AMBRE)

        entete_rack = BoxLayout(size_hint_y=None, height=dp(25), spacing=dp(5))
        entete_rack.add_widget(Label(
            text="[b]TIBRECORD CHANNEL STRIP[/b]", markup=True,
            halign="left", font_size=dp(9), color=TEXTE_2))
        self.lbl_rack = Label(text="MANUEL", size_hint_x=None, width=dp(76),
                              font_size=dp(8), color=AMBRE)
        entete_rack.add_widget(self.lbl_rack)
        rack.add_widget(entete_rack)

        self.pots = {}
        def pot(cle, titre, mini, maxi, valeur, unite=" dB", decimals=1):
            p = Potard(titre, mini, maxi, valeur, unite=unite,
                       decimals=decimals, size_hint_y=None, height=dp(104))
            self.pots[cle] = p
            return p

        ligne1 = BoxLayout(size_hint_y=None, height=dp(104), spacing=dp(5))
        ligne1.add_widget(pot("input", "Input", -18.0, 18.0, 0.0))
        ligne1.add_widget(pot("low", "Low", -12.0, 12.0, 0.0))
        ligne1.add_widget(pot("mid", "Mid", -12.0, 12.0, 0.0))
        rack.add_widget(ligne1)

        ligne2 = BoxLayout(size_hint_y=None, height=dp(104), spacing=dp(5))
        ligne2.add_widget(pot("high", "High", -12.0, 12.0, 0.0))
        ligne2.add_widget(pot("threshold", "Threshold", -40.0, -4.0, -18.0))
        ligne2.add_widget(pot("ratio", "Ratio", 1.0, 10.0, 3.0,
                              unite=":1", decimals=1))
        rack.add_widget(ligne2)

        ligne3 = BoxLayout(size_hint_y=None, height=dp(104), spacing=dp(5))
        ligne3.add_widget(pot("drive", "Drive", 1.0, 4.0, 1.3,
                              unite="x", decimals=2))
        ligne3.add_widget(pot("mix", "Sat Mix", 0.0, 100.0, 25.0,
                              unite="%", decimals=0))
        ligne3.add_widget(pot("ceiling", "Output", -6.0, -0.1, -0.3))
        rack.add_widget(ligne3)

        meters = BoxLayout(orientation="vertical", size_hint_y=None,
                           height=dp(64), spacing=dp(3))
        m1 = BoxLayout(size_hint_y=None, height=dp(29), spacing=dp(6))
        m1.add_widget(Label(text="IN", size_hint_x=None, width=dp(28),
                            font_size=dp(8), color=TEXTE_2))
        self.rack_in = VuMetre()
        m1.add_widget(self.rack_in)
        meters.add_widget(m1)
        m2 = BoxLayout(size_hint_y=None, height=dp(29), spacing=dp(6))
        m2.add_widget(Label(text="OUT", size_hint_x=None, width=dp(28),
                            font_size=dp(8), color=TEXTE_2))
        self.rack_out = VuMetre()
        m2.add_widget(self.rack_out)
        meters.add_widget(m2)
        rack.add_widget(meters)

        actions_rack = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(5))
        b_reset = Bouton(text="RESET", size_hint_x=0.27, font_size=dp(9))
        b_reset.bind(on_release=lambda *_: self.reset_rack())
        actions_rack.add_widget(b_reset)
        b_prev = Bouton(text="APERCU", couleur=VERT, size_hint_x=0.33,
                        font_size=dp(10))
        b_prev.bind(on_release=lambda *_: self.apercu_rack())
        actions_rack.add_widget(b_prev)
        b_apply = Bouton(text="APPLIQUER RACK", couleur=CYAN,
                         size_hint_x=0.40, font_size=dp(10))
        b_apply.bind(on_release=lambda *_: self.appliquer_rack())
        actions_rack.add_widget(b_apply)
        rack.add_widget(actions_rack)
        corps.add_widget(rack)

        # ------------------------------------------------------ effets
        corps.add_widget(TitreSection(
            "Effets", "Choisis, regle les molettes, ecoute, applique"))
        fx = Panneau(orientation="vertical", size_hint_y=None,
                     padding=dp(8), spacing=dp(6))
        fx.bind(minimum_height=fx.setter("height"))

        r_fx0 = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(6))
        self.spin_fx = Choix(text=effets.CATALOGUE[0][0],
                             values=[n for n, _ in effets.CATALOGUE])
        self.spin_fx.bind(text=self._changer_effet)
        r_fx0.add_widget(self.spin_fx)
        fx.add_widget(r_fx0)

        self.lbl_fx = Label(text="", size_hint_y=None, height=dp(18),
                            font_size=dp(10), color=TEXTE_2)
        fx.add_widget(self.lbl_fx)

        # Les molettes changent avec l'effet : la rangee est reconstruite
        # a chaque choix, a partir du CATALOGUE du noyau. Ajouter un
        # effet la-bas suffit a le faire apparaitre ici.
        self.rangee_fx = BoxLayout(size_hint_y=None, height=dp(96),
                                   spacing=dp(8))
        fx.add_widget(self.rangee_fx)
        self.pots_fx = {}

        r_fx1 = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(6))
        b_fxp = Bouton(text="APERCU EFFET", couleur=VERT, font_size=dp(11))
        b_fxp.bind(on_release=lambda *_: self.apercu_effet())
        r_fx1.add_widget(b_fxp)
        b_fxa = Bouton(text="APPLIQUER EFFET", couleur=CYAN,
                       font_size=dp(11))
        b_fxa.bind(on_release=lambda *_: self.appliquer_effet())
        r_fx1.add_widget(b_fxa)
        fx.add_widget(r_fx1)
        corps.add_widget(fx)
        self._changer_effet(self.spin_fx, self.spin_fx.text)

        corps.add_widget(TitreSection(
            "Montage", "Couper, coller, boucler — jointures sans clic"))
        r_m = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(4))
        for txt, fn in (("Couper", self.mont_couper),
                        ("Copier", self.mont_copier),
                        ("Coller", self.mont_coller),
                        ("Suppr.", self.mont_supprimer),
                        ("Boucler", self.mont_boucler)):
            b = Bouton(text=txt, font_size=dp(10.5))
            b.bind(on_release=lambda w, f=fn: f())
            r_m.add_widget(b)
        corps.add_widget(r_m)
        self.lbl_pp = Label(text="presse-papiers : vide",
                            size_hint_y=None, height=dp(16),
                            font_size=dp(9.5), color=TEXTE_2)
        corps.add_widget(self.lbl_pp)

        corps.add_widget(TitreSection(
            "Decoupe automatique",
            "Une prise de dix coups devient dix sons, en deux gestes"))
        dec = Panneau(orientation="vertical", size_hint_y=None,
                      padding=dp(8), spacing=dp(6))
        dec.bind(minimum_height=dec.setter("height"))
        r_d0 = BoxLayout(size_hint_y=None, height=dp(96), spacing=dp(8))
        self.pot_sens = Potard("Sensib.", 0.0, 1.0, 0.5, decimals=2)
        r_d0.add_widget(self.pot_sens)
        col = BoxLayout(orientation="vertical", spacing=dp(6))
        b_det = Bouton(text="DETECTER LES FRAPPES", couleur=CYAN,
                       font_size=dp(11), size_hint_y=None, height=dp(44))
        b_det.bind(on_release=lambda *_: self.detecter_frappes())
        col.add_widget(b_det)
        self.b_dec = Bouton(text="DECOUPER EN SONS", couleur=GRIS,
                            font_size=dp(11), size_hint_y=None,
                            height=dp(44), disabled=True)
        self.b_dec.bind(on_release=lambda *_: self.decouper_en_sons())
        col.add_widget(self.b_dec)
        r_d0.add_widget(col)
        dec.add_widget(r_d0)
        self.lbl_dec = Label(text="regle la sensibilite, puis detecte",
                             size_hint_y=None, height=dp(16),
                             font_size=dp(9.5), color=TEXTE_2)
        dec.add_widget(self.lbl_dec)
        corps.add_widget(dec)

        corps.add_widget(TitreSection("Traitements rapides"))
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
        self.spin.bind(text=self._maj_preset)
        r_p.add_widget(self.spin)
        b_tr = Bouton(text="APPLIQUER", couleur=CYAN, size_hint_x=0.34)
        b_tr.bind(on_release=lambda *_: self.traiter())
        r_p.add_widget(b_tr)
        corps.add_widget(r_p)
        self.lbl_preset = Label(text="", size_hint_y=None, height=dp(42),
                                font_size=dp(10), color=TEXTE_2,
                                halign="left", valign="middle")
        self.lbl_preset.bind(size=lambda w, v: setattr(w, "text_size", v))
        corps.add_widget(self.lbl_preset)
        self._maj_preset()

    # ------------------------------------------------------------ etat
    def poser(self, sample, nom=None):
        self.sample = sample
        self.historique = []
        self._pause_frac = None
        self._seg = None
        self.onde.charger(sample)
        self.spectre.charger(sample)
        self.lbl_nom.text = nom or sample.name
        self._maj_mesures()
        self._maj_rack_metres()

    # ------------------------------------------------- decoupe automatique
    def detecter_frappes(self):
        """Cherche les frappes et les dessine sur l'onde.

        Rien n'est decoupe a ce stade : on regarde d'abord ou tombent
        les traits ambres, on ajuste la sensibilite si besoin, et
        seulement ensuite on decoupe. Voir avant d'agir.
        """
        if self.sample is None:
            self.journal("Ouvre ou enregistre un son d'abord.")
            return
        copie = self.sample.copy()
        sens = float(self.pot_sens.value)

        def calcul():
            return decoupe.detecter_frappes(copie, sensibilite=sens)

        def apres(segments):
            self._segments = segments
            duree = max(1e-9, self.sample.duration_ms)
            traits = []
            for a, b in segments:
                traits.append(a / duree)
                traits.append(b / duree)
            self.onde.poser_marqueurs(traits)
            n = len(segments)
            if n == 0:
                self.b_dec.disabled = True
                self.b_dec.set_couleur(GRIS)
                self.lbl_dec.text = ("aucune frappe nette : monte la "
                                     "sensibilite et redetecte")
                self.journal("Aucune frappe detectee.")
            else:
                self.b_dec.disabled = False
                self.b_dec.text = "DECOUPER EN %d SON%s" % (
                    n, "S" if n > 1 else "")
                self.b_dec.set_couleur(VERT)
                self.lbl_dec.text = ("les traits ambres montrent les "
                                     "coupes — redetecte pour ajuster")
                self.journal("%d frappe%s detectee%s." % (
                    n, "s" if n > 1 else "", "s" if n > 1 else ""))

        self._en_fond("Detection des frappes", calcul, apres)

    def decouper_en_sons(self):
        if self.sample is None or not self._segments:
            self.journal("Detecte les frappes d'abord.")
            return
        NomPopup("Nom des sons decoupes", "frappe",
                 self._faire_decoupe).open()

    def _faire_decoupe(self, nom):
        nom = bib.nom_propre(nom, "frappe")
        copie = self.sample.copy()
        segments = list(self._segments)

        def calcul():
            sons = decoupe.decouper(copie, segments)
            # Chaque prise decoupee a son dossier : dix kicks en vrac a
            # la racine, c'est ce que la bibliotheque sait deja ranger,
            # mais autant les livrer ranges.
            dossier = bib.creer_dossier(dossier_sons(), nom)
            chemins = []
            for i, son in enumerate(sons, 1):
                chemin = bib.chemin_libre(dossier, "%s %d" % (nom, i))
                audio.write_wav(chemin, son)
                chemins.append(chemin)
            return dossier, chemins

        def apres(resultat):
            dossier, chemins = resultat
            self.onde.poser_marqueurs([])
            self._segments = []
            self.b_dec.disabled = True
            self.b_dec.text = "DECOUPER EN SONS"
            self.b_dec.set_couleur(GRIS)
            self.lbl_dec.text = "decoupe faite — retrouve tout dans SONS"
            self.journal("%d son%s dans %s. Onglet SONS pour les voir."
                         % (len(chemins), "s" if len(chemins) > 1 else "",
                            os.path.basename(dossier)))

        self._en_fond("Decoupe en %d sons" % len(segments), calcul, apres)

    # ------------------------------------------------------------ montage
    SEUIL_FOND_S = 15.0  # au-dela, le montage passe en tache de fond

    def _poser_resultat_montage(self, resultat, message):
        self._memoriser()
        self.sample = resultat
        self.onde.charger(self.sample)
        self.spectre.charger(self.sample)
        self._maj_mesures()
        self._maj_rack_metres(self.sample)
        self.journal(message)

    def _montage(self, titre, calcul, message):
        """Execute une operation de montage, en fond si le son est long.

        Mesure : recopier les listes d'une prise de trois minutes coute
        pres de deux secondes sur telephone. En dessous du seuil, le
        direct evite une fenetre qui clignote pour rien.
        """
        if self.sample.duration_ms > self.SEUIL_FOND_S * 1000.0:
            self._en_fond(titre, calcul,
                          lambda r: self._poser_resultat_montage(
                              r, message))
            return
        try:
            self._poser_resultat_montage(calcul(), message)
        except ValueError as e:
            self.journal(str(e))
        except Exception as e:  # noqa: BLE001
            self.journal("%s impossible : %s" % (titre, e))

    def _maj_presse_papiers(self):
        pp = self._presse_papiers
        self.lbl_pp.text = "presse-papiers : vide" if pp is None else             "presse-papiers : %.2f s" % (pp.duration_ms / 1000.0)

    def mont_copier(self):
        if self.sample is None:
            self.journal("Ouvre ou enregistre un son d'abord.")
            return
        a, b = self.onde.bornes_ms()
        self._presse_papiers = montage.copier(self.sample, a, b)
        self._maj_presse_papiers()
        self.journal("Copie : %.2f s."
                     % (self._presse_papiers.duration_ms / 1000.0))

    def mont_couper(self):
        if self.sample is None:
            self.journal("Ouvre ou enregistre un son d'abord.")
            return
        a, b = self.onde.bornes_ms()
        copie = self.sample.copy()

        def calcul():
            reste, portion = montage.couper(copie, a, b)
            return reste, portion

        def apres(resultat):
            reste, portion = resultat
            self._presse_papiers = portion
            self._maj_presse_papiers()
            self._poser_resultat_montage(
                reste, "Coupe : %.2f s au presse-papiers."
                % (portion.duration_ms / 1000.0))

        if copie.duration_ms > self.SEUIL_FOND_S * 1000.0:
            self._en_fond("Couper", calcul, apres)
            return
        try:
            apres(calcul())
        except ValueError as e:
            self.journal(str(e))

    def mont_supprimer(self):
        if self.sample is None:
            self.journal("Ouvre ou enregistre un son d'abord.")
            return
        a, b = self.onde.bornes_ms()
        copie = self.sample.copy()
        self._montage("Supprimer",
                      lambda: montage.supprimer(copie, a, b),
                      "Portion supprimee, jointure fondue.")

    def mont_coller(self):
        if self.sample is None:
            self.journal("Ouvre ou enregistre un son d'abord.")
            return
        if self._presse_papiers is None or not self._presse_papiers.data:
            self.journal("Le presse-papiers est vide : Copier ou "
                         "Couper d'abord.")
            return
        a, _b = self.onde.bornes_ms()
        copie = self.sample.copy()
        pp = self._presse_papiers

        # Le collage se fait au DEBUT de la selection : la poignee
        # gauche est le curseur d'insertion, c'est elle qu'on place.
        self._montage("Coller",
                      lambda: montage.inserer(copie, a, pp),
                      "Colle a %.2f s." % (a / 1000.0))

    def mont_boucler(self):
        if self.sample is None:
            self.journal("Ouvre ou enregistre un son d'abord.")
            return
        a, b = self.onde.bornes_ms()
        copie = self.sample.copy()
        self._montage("Boucler",
                      lambda: montage.boucler(copie, a, b, fois=4),
                      "Selection bouclee 4 fois. ANNULER pour revenir.")

    # ------------------------------------------------------------ effets
    def _changer_effet(self, _w, nom):
        """Reconstruit les molettes pour l'effet choisi."""
        entree = effets.par_nom(nom)
        if entree is None:
            return
        self.lbl_fx.text = entree["desc"]
        self.rangee_fx.clear_widgets()
        self.pots_fx = {}
        params = entree["params"]
        self.rangee_fx.height = dp(96) if params else dp(20)
        if not params:
            self.rangee_fx.add_widget(Label(
                text="(aucun reglage : cet effet est tout ou rien)",
                font_size=dp(10), color=TEXTE_2))
            return
        for cle, titre, mini, maxi, defaut, unite, deci in params:
            pot = Potard(titre, float(mini), float(maxi), float(defaut),
                         unite=unite, decimals=deci)
            self.pots_fx[cle] = pot
            self.rangee_fx.add_widget(pot)

    def _params_effet(self):
        entree = effets.par_nom(self.spin_fx.text)
        out = {}
        for cle, _t, _mn, _mx, _d, _u, deci in entree["params"]:
            v = self.pots_fx[cle].value
            out[cle] = int(round(v)) if deci <= 0 else float(v)
        return out

    def apercu_effet(self):
        """L'effet sur la selection seulement, joue au retour du calcul.

        La selection et non le son entier : on juge un delai sur deux
        secondes, pas sur toute la prise, et le calcul reste court.
        """
        if self.sample is None:
            self.journal("Ouvre ou enregistre un son d'abord.")
            return
        nom = self.spin_fx.text
        bout = self._selection()
        params = self._params_effet()

        def calcul():
            return effets.appliquer(nom, bout, **params)

        def apres(resultat):
            jouer_sample(resultat, "fx_preview")
            self.journal("Apercu %s : %.1f s" % (
                nom, resultat.duration_ms / 1000.0))

        self._en_fond("Apercu %s" % nom, calcul, apres)

    def appliquer_effet(self):
        if self.sample is None:
            self.journal("Ouvre ou enregistre un son d'abord.")
            return
        nom = self.spin_fx.text
        copie = self.sample.copy()
        params = self._params_effet()

        def calcul():
            return effets.appliquer(nom, copie, **params)

        def apres(resultat):
            self._memoriser()
            self.sample = resultat
            self.onde.charger(self.sample)
            self.spectre.charger(self.sample)
            self._maj_mesures()
            self._maj_rack_metres(self.sample)
            self.journal("%s applique : %.1f s. ANNULER pour revenir."
                         % (nom, resultat.duration_ms / 1000.0))

        self._en_fond(nom, calcul, apres)

    # -------------------------------------------------- tache de fond
    def _en_fond(self, titre, calcul, apres):
        """Execute un calcul long sans figer l'ecran.

        Le calcul recoit une COPIE du son et travaille dans son fil ;
        `apres(resultat)` revient sur le fil d'interface pour poser le
        resultat. Pendant ce temps, une fenetre de patience bloque les
        appuis : deux traitements simultanes sur le meme son donneraient
        un resultat dependant de l'ordre d'arrivee.
        """
        if self._serie.occupe:
            self.journal("Un traitement est deja en cours.")
            return
        popup = PatiencePopup(titre)

        def succes(resultat):
            popup.fermer()
            try:
                apres(resultat)
            except Exception as e:  # noqa: BLE001
                self.journal("Echec apres traitement : %s" % e)

        def echec(e):
            popup.fermer()
            self.journal("%s impossible : %s" % (titre, e))

        parti = self._serie.lancer(
            calcul, succes, echec,
            lambda fn: Clock.schedule_once(fn, 0))
        if parti:
            popup.open()

    def _maj_preset(self, *_a):
        cfg = audio.PRESETS.get(self.spin.text, {})
        self.lbl_preset.text = cfg.get("desc", "")

    def _rack_cfg(self):
        return {
            "input_gain_db": self.pots["input"].value,
            "low_db": self.pots["low"].value,
            "mid_db": self.pots["mid"].value,
            "high_db": self.pots["high"].value,
            "comp_threshold_db": self.pots["threshold"].value,
            "comp_ratio": self.pots["ratio"].value,
            "sat_drive": self.pots["drive"].value,
            "sat_mix": self.pots["mix"].value / 100.0,
            "ceiling_db": self.pots["ceiling"].value,
        }

    def reset_rack(self):
        valeurs = {
            "input": 0.0, "low": 0.0, "mid": 0.0, "high": 0.0,
            "threshold": -18.0, "ratio": 3.0,
            "drive": 1.3, "mix": 25.0, "ceiling": -0.3,
        }
        for cle, valeur in valeurs.items():
            self.pots[cle].poser(valeur)
        self.lbl_rack.text = "MANUEL"
        self._maj_rack_metres()
        self.journal("Rack Studio remis a zero.")

    def _maj_rack_metres(self, sortie=None):
        if self.sample is None:
            self.rack_in.vider()
            self.rack_out.vider()
            return
        self.rack_in.vider()
        self.rack_in.poser(self.sample.peak_db())
        cible = sortie if sortie is not None else self.sample
        self.rack_out.vider()
        self.rack_out.poser(cible.peak_db())

    def apercu_rack(self):
        if self.sample is None:
            self.journal("Ouvre ou enregistre un son d'abord.")
            return
        bout = self._selection()
        cfg = self._rack_cfg()

        def calcul():
            return audio.studio_rack(bout, **cfg)

        def apres(resultat):
            test, rap = resultat
            jouer_sample(test, "rack_preview")
            self._maj_rack_metres(test)
            self.lbl_rack.text = "PREVIEW"
            self.journal("Apercu rack : RMS %+.1f dB, crete %.1f dB" % (
                rap["gain_db"], rap["apres"]["peak_db"]))

        self._en_fond("Apercu du rack", calcul, apres)

    def appliquer_rack(self):
        if self.sample is None:
            self.journal("Ouvre ou enregistre un son d'abord.")
            return
        copie = self.sample.copy()
        cfg = self._rack_cfg()

        def calcul():
            return audio.studio_rack(copie, **cfg)

        def apres(resultat):
            traite, rap = resultat
            self._memoriser()
            self.sample = traite
            self.onde.charger(self.sample)
            self.spectre.charger(self.sample)
            self._maj_mesures()
            self._maj_rack_metres(self.sample)
            self.lbl_rack.text = "APPLIQUE"
            self.journal("Rack applique : RMS %+.1f dB, sortie %.1f dB" % (
                rap["gain_db"], rap["apres"]["peak_db"]))

        self._en_fond("Rack Studio", calcul, apres)

    def sauver(self):
        if self.sample is None:
            self.journal("Aucun son a sauvegarder.")
            return
        defaut = bib.nom_propre(self.lbl_nom.text or self.sample.name, "prise")
        NomPopup("Nom du fichier WAV", defaut, self._sauver_nom).open()

    def _sauver_nom(self, nom):
        try:
            dossier = dossier_sons()
            chemin = bib.chemin_libre(dossier, nom)
            audio.write_wav(chemin, self.sample)
            self.lbl_nom.text = os.path.splitext(os.path.basename(chemin))[0]
            self.journal("Sauvegarde : %s" % chemin)
        except Exception as e:  # noqa: BLE001
            self.journal("Sauvegarde impossible : %s" % e)

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
        # Le son va changer : un point de pause note sur l'ancien son
        # tomberait n'importe ou dans le nouveau.
        self._pause_frac = None
        self._seg = None

    def annuler(self):
        if not self.historique:
            self.journal("Rien a annuler.")
            return
        self.sample = self.historique.pop()
        self.onde.charger(self.sample)
        self.spectre.charger(self.sample)
        self._maj_mesures()
        self._maj_rack_metres()
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
        self.spectre.charger(self.sample)
        self._maj_mesures()
        self._maj_rack_metres()
        self.journal("Rogne : %.0f ms conserves." % self.sample.duration_ms)

    def normaliser(self):
        if self.sample is None:
            return
        self._memoriser()
        audio.normalize_peak(self.sample, -0.3)
        self.onde.charger(self.sample)
        self.spectre.charger(self.sample)
        self._maj_rack_metres()
        self.journal("Normalise a -0,3 dB.")

    def fondus(self):
        if self.sample is None:
            return
        self._memoriser()
        audio.fade(self.sample, 3.0, 8.0)
        self.onde.charger(self.sample)
        self.spectre.charger(self.sample)
        self._maj_rack_metres()
        self.journal("Fondus appliques.")

    def traiter(self):
        if self.sample is None:
            return
        self._memoriser()
        self.sample, rap = audio.process(self.sample, self.spin.text)
        self.onde.charger(self.sample)
        self.spectre.charger(self.sample)
        self._maj_mesures()
        self._maj_rack_metres()
        self.journal("%s : %+.1f dB, RMS %.1f dB" % (
            self.spin.text, rap["gain_db"], rap["apres"]["rms_db"]))

    def lire(self):
        """Joue depuis le point de pause s'il y en a un, sinon depuis le
        debut de la selection. Toujours jusqu'a la fin de la selection."""
        if self.sample is None:
            self.journal("Ouvre ou enregistre un son d'abord.")
            return
        try:
            a = self.onde.sel_debut
            b = self.onde.sel_fin
            depart = a
            if self._pause_frac is not None and \
                    a <= self._pause_frac < b - 1e-6:
                depart = self._pause_frac
            self._pause_frac = None
            r = self.sample.rate
            n = len(self.sample.data)
            i0, i1 = int(depart * n), int(b * n)
            bout = audio.Sample(self.sample.data[i0:i1], r, "selection")
            jouer_sample(bout, "selection")
            # Kivy ne sait ni mettre en pause ni donner la position :
            # on retient donc NOUS quel segment est en train de jouer,
            # et la pause devient un arret dont on note l'endroit.
            self._seg = (depart, b)
            self.b_lire.led(1.0)
            self.b_pause.led(0.0)
            self._suivre_tete()
            self._suivre_spectre()
        except Exception as e:  # noqa: BLE001
            self.journal("Lecture impossible : %s" % e)

    def pauser(self):
        """Arrete la lecture en retenant ou elle en etait.

        Le prochain LIRE repartira de ce point exact. La tete reste
        affichee sur l'onde : c'est elle qui dit "je suis en pause ici",
        sans quoi pause et stop seraient indiscernables a l'ecran.
        """
        f = avancement_lecture()
        if f is None or self._seg is None:
            return
        a, b = self._seg
        pos = a + (b - a) * f
        arreter_lecture()
        if self._tic_tete is not None:
            self._tic_tete.cancel()
            self._tic_tete = None
        self._seg = None
        self._pause_frac = pos
        self._arreter_spectre()
        self.b_lire.led(0.0)
        self.b_pause.led(1.0)
        self.onde.poser_tete(pos)
        if self.sample is not None:
            duree = self.sample.duration_ms
            n = len(self.sample.data)
            self.compteur.afficher(pos * duree, duree, int(pos * n), n)
        self.journal("Pause.")

    def retour(self):
        """Revient au debut de la selection. Si ca jouait, ca rejoue."""
        jouait = avancement_lecture() is not None
        arreter_lecture()
        self._pause_frac = None
        self._seg = None
        if jouait:
            self.lire()
        else:
            self._arreter_tete()
            self.onde.poser_tete(self.onde.sel_debut)

    # ------------------------------------------------------------ spectre vif
    def _suivre_spectre(self):
        """Anime le spectre pendant la lecture, a douze images par
        seconde.

        Pas plus : chaque image coute une analyse Goertzel, mesuree a
        moins d'une milliseconde ici donc autour de cinq sur telephone.
        A douze images le mouvement est net et le budget est large ; a
        trente il ne resterait rien pour le reste de l'ecran.
        """
        self._arreter_spectre()
        self._spectre_vif = []
        self._tic_spectre = Clock.schedule_interval(self._maj_spectre,
                                                    1 / 12.0)

    def _arreter_spectre(self):
        if self._tic_spectre is not None:
            self._tic_spectre.cancel()
            self._tic_spectre = None

    def _maj_spectre(self, *_a):
        f = avancement_lecture()
        if f is None or self.sample is None:
            # Fin de lecture : on revient a la vue figee du son entier,
            # pour ne pas laisser a l'ecran le spectre du dernier
            # centieme de seconde.
            self._arreter_spectre()
            self.spectre.charger(self.sample)
            return False
        a, b = self._seg if self._seg else (self.onde.sel_debut,
                                            self.onde.sel_fin)
        pos = a + (b - a) * f
        vals = noyau_spectre.bandes_a_la_position(self.sample, pos,
                                                  self.spectre.NB)
        self._spectre_vif = noyau_spectre.lisser(self._spectre_vif, vals)
        self.spectre.poser_niveaux(self._spectre_vif)

    # ------------------------------------------------------- tete de lecture
    def _suivre_tete(self):
        """Lance l'animation de la barre pendant la lecture.

        Trente images par seconde : en dessous, les millisecondes
        avancent par paquets et l'oeil le voit.
        """
        if self._tic_tete is not None:
            self._tic_tete.cancel()
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
            self._seg = None
            self.b_lire.led(0.0)
            self.b_pause.led(0.0)
            self._arreter_tete()
            return False
        a, b = self._seg if self._seg else (self.onde.sel_debut,
                                            self.onde.sel_fin)
        pos = a + (b - a) * f
        self.onde.poser_tete(pos)
        self.b_lire.led(pulsation(time.time(), vitesse=4.0, mini=0.45))
        if self.sample is not None:
            duree = self.sample.duration_ms
            n = len(self.sample.data)
            self.compteur.afficher(pos * duree, duree, int(pos * n), n,
                                   en_lecture=True)

    def stopper(self):
        arreter_lecture()
        self._pause_frac = None
        self._seg = None
        self._arreter_spectre()
        self.b_lire.led(0.0)
        self.b_pause.led(0.0)
        self._arreter_tete()
        if self.sample is not None:
            self.spectre.charger(self.sample)

class PatiencePopup(Popup):
    """Fenetre affichee pendant un traitement en tache de fond.

    Elle ne se ferme pas d'un appui exterieur : le calcul en cours ne
    peut pas etre interrompu proprement, autant ne pas faire semblant.
    Le temps ecoule qui defile sert de preuve de vie : un ecran fige et
    un ecran qui attend se ressemblent, sauf par ce compteur.
    """

    def __init__(self, titre, **kw):
        super().__init__(title=titre, size_hint=(0.82, None),
                         height=dp(150), auto_dismiss=False, **kw)
        box = BoxLayout(orientation="vertical", spacing=dp(6),
                        padding=dp(12))
        self.lbl = Label(text="Traitement...", font_size=dp(13),
                         color=TEXTE)
        box.add_widget(self.lbl)
        self.lbl_temps = Label(text="0.0 s", font_size=dp(19), bold=True,
                               color=CYAN)
        box.add_widget(self.lbl_temps)
        self.add_widget(box)
        self._depart = time.time()
        self._tic = Clock.schedule_interval(self._maj, 1 / 5.0)

    def _maj(self, *_a):
        self.lbl_temps.text = "%.1f s" % (time.time() - self._depart)

    def fermer(self):
        if self._tic is not None:
            self._tic.cancel()
            self._tic = None
        self.dismiss()


class HistoriquePopup(Popup):
    """Toutes les lignes du journal, la plus recente en haut.

    La barre d'etat ne montre que la derniere information, ce qui garde
    l'ecran calme. Mais un message d'erreur chasse le precedent : sans
    cette fenetre, la ligne qu'on cherche est perdue au moment ou on en
    a besoin.
    """

    def __init__(self, lignes, titre="Journal", recent_en_haut=True, **kw):
        super().__init__(title=titre, size_hint=(0.94, 0.85), **kw)
        box = BoxLayout(orientation="vertical", spacing=dp(8),
                        padding=dp(10))
        sv = ScrollView(do_scroll_x=False)
        if not lignes:
            texte = "(rien encore)"
        else:
            texte = "\n".join(reversed(lignes) if recent_en_haut else lignes)
        lbl = Label(text=texte, size_hint_y=None, halign="left",
                    valign="top", font_size=dp(11), color=TEXTE)
        lbl.bind(texture_size=lambda i, v: setattr(i, "height", v[1]),
                 width=lambda i, v: setattr(i, "text_size", (v, None)))
        sv.add_widget(lbl)
        box.add_widget(sv)
        b = Bouton(text="Fermer", size_hint_y=None, height=dp(46))
        b.bind(on_release=lambda *_: self.dismiss())
        box.add_widget(b)
        self.add_widget(box)


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


class MiniOnde(Widget):
    """Silhouette d'un son : de petites barres verticales.

    Assez pour distinguer un kick d'une voix d'une nappe, sans lire le
    nom. Le dessin est statique : aucun recalcul tant que les pics ne
    changent pas.
    """

    def __init__(self, pics=None, **kw):
        super().__init__(**kw)
        self.pics = pics or []
        self.bind(pos=self.redessiner, size=self.redessiner)

    def poser(self, pics):
        self.pics = pics or []
        self.redessiner()

    def redessiner(self, *_a):
        self.canvas.clear()
        x0, y0, w, h = self.x, self.y, self.width, self.height
        with self.canvas:
            Color(0.030, 0.036, 0.046, 1)
            RoundedRectangle(pos=(x0, y0), size=(w, h), radius=[6])
            if not self.pics:
                # Pas encore calculee : un trait au milieu, pour dire
                # "ca vient" sans faire croire a un son muet.
                Color(0.20, 0.23, 0.28, 1)
                Line(points=[x0 + dp(4), y0 + h / 2,
                             x0 + w - dp(4), y0 + h / 2], width=1)
                return
            n = len(self.pics)
            mid = y0 + h / 2.0
            demi = h / 2.0 - dp(2)
            Color(0.18, 0.72, 0.80, 1)
            for i, v in enumerate(self.pics):
                x = x0 + dp(3) + (w - dp(6)) * (i + 0.5) / n
                haut = max(dp(1), min(1.0, v) * demi)
                Line(points=[x, mid - haut, x, mid + haut], width=dp(1.3))


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
        self._vignettes = {}
        self._calcul_vignettes = travail.Serie()

        self.add_widget(TitreSection(
            "Bibliotheque", "Retrouver, classer et rouvrir les prises enregistrees"))

        r0 = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(6))
        self.spin_dossier = Choix(text=bib.RACINE, values=[bib.RACINE])
        self.spin_dossier.bind(text=self._changer_dossier)
        r0.add_widget(self.spin_dossier)
        b_new = Bouton(text="+  DOSSIER", couleur=CYAN, size_hint_x=0.38,
                       font_size=dp(12))
        b_new.bind(on_release=lambda *_: self.nouveau_dossier())
        r0.add_widget(b_new)
        self.add_widget(r0)

        r1 = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(6))
        self.champ = TextInput(hint_text="Rechercher un son...", multiline=False,
                               font_size=dp(13), size_hint_x=0.5,
                               background_normal="", background_active="",
                               background_color=(0.10, 0.11, 0.13, 1),
                               foreground_color=TEXTE,
                               hint_text_color=(0.45, 0.49, 0.56, 1),
                               cursor_color=CYAN, padding=(dp(10), dp(10)))
        self.champ.bind(text=self._changer_recherche)
        r1.add_widget(self.champ)
        self.spin_tri = Choix(text="date", values=list(bib.TRIS),
                              size_hint_x=0.28, font_size=dp(12))
        self.spin_tri.bind(text=self._changer_tri)
        r1.add_widget(self.spin_tri)
        b_maj = Bouton(text="ACTUALISER", size_hint_x=0.32, font_size=dp(11))
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
        b_ren = Bouton(text="RENOMMER DOSSIER", font_size=dp(11))
        b_ren.bind(on_release=lambda *_: self.renommer_dossier())
        r2.add_widget(b_ren)
        b_sup = Bouton(text="SUPPRIMER DOSSIER", font_size=dp(11),
                       couleur=ROUGE_SOMBRE)
        b_sup.bind(on_release=lambda *_: self.supprimer_dossier())
        r2.add_widget(b_sup)
        self.add_widget(r2)

        # Acces au stockage : la permission "tous les fichiers" ne
        # s'accorde que dans un ecran systeme dedie, jamais par une boite
        # de dialogue ordinaire. Sans ce bouton elle reste declaree dans
        # le manifeste mais jamais accordee, et les dossiers du telephone
        # restent vides.
        r3 = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(6))
        self.b_acces = Bouton(text="ACCES FICHIERS", font_size=dp(11),
                              couleur=CYAN_S)
        self.b_acces.bind(on_release=lambda *_: self.demander_acces())
        r3.add_widget(self.b_acces)
        b_diag = Bouton(text="DIAGNOSTIC", font_size=dp(11))
        b_diag.bind(on_release=lambda *_: self.voir_diagnostic())
        r3.add_widget(b_diag)
        self.add_widget(r3)

        self.rafraichir()

    # ------------------------------------------------------------ stockage
    def demander_acces(self):
        msg = stockage.demander_acces_complet()
        self.journal(msg)
        self.maj_bouton_acces()

    def voir_diagnostic(self):
        """Mesurer avant de corriger : sans ce releve, on essaie trois
        hypotheses au hasard."""
        HistoriquePopup(stockage.diagnostic().split("\n"),
                        titre="Diagnostic du stockage",
                        recent_en_haut=False).open()

    def maj_bouton_acces(self):
        if stockage.acces_complet():
            self.b_acces.text = "ACCES FICHIERS OK"
            self.b_acces.set_couleur(VERT)
        else:
            self.b_acces.text = "ACCES FICHIERS"
            self.b_acces.set_couleur(CYAN_S)

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

        dossier = self.chemin_dossier()
        items = bib.lister_sons(dossier)
        total = len(items)

        # Les silhouettes du cache arrivent tout de suite, sans lire un
        # seul WAV. Ce qui manque part en arriere-plan : la liste
        # s'affiche d'abord, les silhouettes se posent apres.
        self._vignettes, manquants = vignettes.pour_items(dossier, items)
        if manquants and not self._calcul_vignettes.occupe:
            self._calcul_vignettes.lancer(
                lambda d=dossier, m=list(manquants): vignettes.completer(d, m),
                lambda _n: self.rafraichir(),
                lambda e: self.journal("Vignettes : %s" % e),
                lambda fn: Clock.schedule_once(fn, 0))

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

        if hasattr(self, "b_acces"):
            self.maj_bouton_acces()
        duree = sum(i["duree_ms"] for i in items)
        vu = "%d son%s" % (len(items), "s" if len(items) > 1 else "")
        if len(items) != total:
            vu += " sur %d" % total
        self.lbl_etat.text = "%s   %s" % (vu, bib.duree_courte(duree))

    def _ligne(self, item):
        rangee = BoxLayout(size_hint_y=None, height=dp(60), spacing=dp(5))
        mini = MiniOnde(self._vignettes.get(item["chemin"]),
                        size_hint_x=None, width=dp(78))
        # La silhouette repond au doigt comme le reste de la ligne :
        # une zone morte au milieu d'une rangee surprend toujours.
        mini.on_touch_down = (lambda t, i=item, m=mini:
                              m.collide_point(*t.pos)
                              and (self.menu(i) or True))
        rangee.add_widget(mini)
        b = Bouton(text=(
            "[color=#63dce7][b]WAV[/b][/color]   [b]%s[/b]\n"
            "[size=10sp][color=#7f8999]DUREE  %s     TAILLE  %s[/color][/size]"
            % (item["nom"], bib.duree_courte(item["duree_ms"]),
               bib.taille_courte(item["taille"]))),
            couleur=(0.085, 0.095, 0.116, 1), markup=True, halign="left",
            font_size=dp(13), rayon=9)
        b.bind(size=lambda w, v: setattr(w, "text_size",
                                         (v[0] - dp(16), v[1])))
        b.bind(on_release=lambda w, i=item: self.menu(i))
        rangee.add_widget(b)
        return rangee

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

REC
  Appuie sur ENREGISTRER. Pendant la capture, l'onglet REC porte une
  LED rouge qui bat : meme depuis un autre ecran, tu vois qu'un
  enregistrement tourne. Elle s'eteint a l'arret.
  Le minuteur, le vu-metre et l'oscilloscope
  suivent la prise en direct. Peak et RMS sont visibles simultanement.
  Vise entre -12 et -6 dB : au-dela le rouge signale l'ecretage.
  Qualite : 44100 Hz par defaut. Descendre economise de la place.
  Source : micro ordinaire, camera (plus directif) ou brut (sans
  traitement du telephone, quand l'appareil le permet).

EDITION
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
  L'analyseur 18 bandes montre le contenu grave / medium / aigu.
  A l'arret il resume le son entier ; pendant la lecture il DANSE :
  il suit ce qui joue, douze images par seconde, avec des barres qui
  montent d'un coup et retombent doucement, comme un vrai vu-metre.

  Le transport est en haut, sous le compteur. LIRE et PAUSE portent
  une petite LED : verte qui respire pendant la lecture, ambre fixe
  en pause. Eteintes, elles restent faiblement visibles, comme les
  lampes d'un vrai rack.
  RETOUR  revient au debut de la selection. Si ca jouait, ca rejoue.
  LIRE    joue la selection. Apres une pause, reprend ou c'etait.
  PAUSE   arrete en retenant l'endroit exact. La tete reste posee
          sur l'onde pour le montrer.
  STOP    arrete et oublie tout.
  OUVRIR WAV et SAUVEGARDER sont plus bas, sous le titre Fichier :
  ils ne servent qu'une fois par session.

DECOUPE AUTOMATIQUE
  Le geste pour lequel Tibrecord existe : enregistre dix coups de
  percussion d'affilee, puis
  1. DETECTER LES FRAPPES — des traits ambres marquent chaque coup
     sur l'onde. Rien n'est encore decoupe : regarde ou ils tombent.
  2. Si un coup faible manque, monte la Sensibilite et redetecte.
     Si le bruit declenche, baisse-la.
  3. DECOUPER EN N SONS — donne un nom, et chaque coup devient un
     WAV propre (attaque gardee, bords fondus), range dans son
     dossier de la bibliotheque.
  La detection est independante du niveau : une prise faible et une
  prise forte donnent les memes coupes. Deux coups colles sans
  silence entre eux forment UN son : c'est le bon decoupage pour un
  roulement.

MONTAGE
  Couper   retire la selection et la met au presse-papiers.
  Copier   met la selection au presse-papiers sans toucher au son.
  Coller   insere le presse-papiers au DEBUT de la selection : la
           poignee gauche est ton curseur d'insertion.
  Suppr.   retire la selection, sans toucher au presse-papiers.
  Boucler  repete la selection quatre fois : deux secondes propres
           deviennent un motif.
  Toutes les jointures sont fondues sur 6 ms : pas de clic. Chaque
  jointure consomme donc 6 ms — c'est le prix d'une coupe propre.
  ANNULER revient en arriere, comme partout.

EFFETS
  Sous le rack : choisis un effet dans la liste, ses molettes
  apparaissent, APERCU EFFET le joue sur la selection, APPLIQUER
  EFFET transforme le son entier. ANNULER revient en arriere.
  Delai       echo qui se repete ; Temps regle l'ecart, Repet. la
              trainee, Mix le dosage.
  Reverbe     une piece autour du son ; Taille du placard a la salle.
  Tremolo     le volume ondule, comme un vieil ampli.
  Bitcrush    lo-fi : moins de bits = vieille console.
  Vari-speed  la bande magnetique : plus vite = plus aigu et plus
              court, plus lent = plus grave et plus long.
  Inversion   le son a l'envers. Essaie Inversion + Reverbe +
              Inversion : la reverberation ARRIVE avant le son.
  Polarite    miroir du signal, pour aligner deux prises.
  Delai et Reverbe rallongent le son de leur queue : c'est voulu.

LES TRAITEMENTS LONGS
  Les presets et le rack tournent en arriere-plan : une fenetre de
  patience s'affiche avec le temps qui defile, puis le resultat se
  pose. L'application ne se fige plus, meme sur une longue prise.
  Un seul traitement a la fois : le deuxieme appui est refuse tant
  que le premier n'est pas fini.

  Rogner       reduit le son a la selection
  Normaliser   amene la crete a -0,3 dB
  Fondus       evite les clics au debut et a la fin
  Traiter      applique un preset complet
  Annuler      revient en arriere, 12 etapes
  Sauvegarder  ecrit un WAV mono 16 bits 44,1 kHz dans la
               bibliotheque, sans jamais ecraser un fichier
               existant : "kick" devient "kick 2".

RACK STUDIO
  Glisse verticalement sur les molettes. INPUT regle le niveau entrant,
  LOW / MID / HIGH forment un EQ 3 bandes, THRESHOLD et RATIO pilotent
  le compresseur, DRIVE et SAT MIX ajoutent de la saturation douce,
  OUTPUT fixe le plafond du limiteur.
  APERCU traite une copie de la selection et la joue sans toucher au son.
  APPLIQUER RACK modifie le son et reste annulable avec ANNULER.

SONS
  Tes prises rangees. Chaque ligne montre la silhouette du son :
  un kick, une voix et une nappe ne se ressemblent pas, on les
  reconnait sans lire le nom.
  Les silhouettes se calculent une seule fois puis sont gardees en
  memoire dans le dossier (.vignettes.json). A la premiere ouverture
  d'un dossier plein, elles apparaissent quelques secondes apres la
  liste : c'est normal, ca ne se reproduira pas.
  Choisis un dossier en haut, cherche par nom, trie par date, nom,
  duree ou taille.
  Appuie sur un son pour l'ouvrir dans EDITION, l'ecouter, le renommer,
  le deplacer dans un dossier ou le supprimer.
  + Dossier cree un rangement : kicks, voix, ambiances...
  Un dossier ne se supprime que s'il est vide : on ne perd pas dix
  prises d'un seul appui.

ACCES AUX FICHIERS DU TELEPHONE
  Depuis Android 11, une application ne lit plus librement le
  telephone. Si des dossiers apparaissent vides ou refuses :
  onglet SONS, bouton ACCES FICHIERS. Un ecran du systeme s'ouvre,
  tu actives l'interrupteur, puis tu reviens dans Tibrecord.
  Le bouton devient vert quand c'est accorde.
  DIAGNOSTIC a cote liste ce qui est lisible et ce qui ne l'est pas :
  a regarder avant de chercher plus loin.
  Dans le selecteur de fichiers, les raccourcis du haut mènent
  directement a Mes sons, Carte SD, Telechargements, Musique,
  Documents et Stockage interne. Ceux qui sont gris sont refuses par
  Android, ou absents de l'appareil.

CARTE SD
  Deux boutons peuvent apparaitre.
  Carte SD        la racine de la carte. Souvent fermee par Android,
                  meme avec l'acces a tous les fichiers accorde.
  Carte SD (app)  le dossier reserve a Tibrecord sur la carte. Celui-la
                  est lisible ET inscriptible sans aucune permission,
                  quelle que soit la version d'Android. C'est la voie
                  fiable pour travailler depuis une carte.
  Si aucune carte n'est detectee, le bouton reste affiche en gris :
  c'est l'appareil qui n'en a pas, pas l'application qui ignore.

OU SONT LES FICHIERS
  Dans le sous-dossier enregistrements/ du dossier de l'application,
  et dans ses sous-dossiers pour ce qui est range.
  Ce sont de vrais fichiers WAV : aucun catalogue cache, rien a
  exporter. Le chemin exact s'affiche dans la barre du bas a chaque
  ecriture.

LE JOURNAL
  La barre du bas montre la derniere information. Le bouton JOURNAL,
  a sa droite, rouvre tout l'historique : c'est la qu'on retrouve un
  message d'erreur qui vient de passer.

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
    ONGLETS = ("REC", "EDITION", "SONS", "AIDE")

    def __init__(self, **kw):
        super().__init__(orientation="vertical", spacing=dp(7),
                         padding=(dp(9), dp(7), dp(9), dp(8)), **kw)
        with self.canvas.before:
            self._c_bg = Color(1, 1, 1, 1)
            self._bg = Rectangle()
            tex = texture_degrade(FOND_BAS, FOND_HAUT)
            if tex is not None:
                self._bg.texture = tex
            else:
                self._c_bg.rgba = FOND
        self.bind(pos=self._maj_fond, size=self._maj_fond)
        self._maj_fond()

        self.add_widget(self._entete())

        barre = BoxLayout(size_hint_y=None, height=dp(50), spacing=dp(5))
        self.tabs = []
        for i, nom in enumerate(self.ONGLETS):
            if nom == "REC":
                # La LED de l'onglet est le seul temoin d'une capture en
                # cours quand on est parti regarder un autre ecran : sans
                # elle, on oublie un enregistrement qui tourne.
                b = BoutonLed(text=nom, font_size=dp(11), rayon=6,
                              led=(1.0, 0.30, 0.32))
            else:
                b = Bouton(text=nom, font_size=dp(11), rayon=6)
            b.bind(on_release=lambda w, k=i: self.afficher(k))
            self.tabs.append(b)
            barre.add_widget(b)
        self.add_widget(barre)

        self.zone = BoxLayout()
        self.add_widget(self.zone)

        statut = Panneau(orientation="horizontal", size_hint_y=None,
                          height=dp(40), padding=(dp(9), dp(3)),
                          spacing=dp(6), fond=(0.040, 0.045, 0.055, 1))
        statut.add_widget(Label(text="[color=#63dce7]●[/color]  SYSTEM",
                                markup=True, size_hint_x=None, width=dp(82),
                                halign="left", valign="middle",
                                font_size=dp(9), color=TEXTE_2))
        self.log = Label(text="Pret.", halign="left", valign="middle",
                         font_size=dp(9), color=TEXTE_2, shorten=True)
        self.log.bind(size=lambda w, v: setattr(w, "text_size", v))
        statut.add_widget(self.log)
        self._historique_log = ["Pret."]
        b_hist = Bouton(text="JOURNAL", size_hint_x=None, width=dp(62),
                        font_size=dp(9), rayon=6)
        b_hist.bind(on_release=lambda *_: self.voir_journal())
        statut.add_widget(b_hist)
        self.add_widget(statut)

        self.ec_edit = self._fabriquer("EDITION", EcranEdit, self.journal)
        self.ec_biblio = self._fabriquer("SONS", EcranBiblio,
                                         self.journal, self._ouvrir_depuis)
        self.ecrans = [
            self._fabriquer("REC", EcranEnreg, self.journal,
                            self._apres_capture),
            self.ec_edit,
            self.ec_biblio,
            self._fabriquer("AIDE", EcranTuto),
        ]
        if isinstance(self.ecrans[0], EcranEnreg):
            self.ecrans[0].sur_etat_rec = self._signaler_rec
        self.afficher(0)

    def _signaler_rec(self, actif, niveau):
        """Allume ou eteint la LED de l'onglet REC."""
        tab = self.tabs[0] if self.tabs else None
        if isinstance(tab, BoutonLed):
            tab.led(niveau if actif else 0.0)

    def _maj_fond(self, *_a):
        self._bg.pos, self._bg.size = self.pos, self.size

    @staticmethod
    def _entete():
        """Le logo s'il est la, le titre ecrit sinon."""
        logo = fichier_asset("logo.png")
        if logo:
            barre = BoxLayout(size_hint_y=None, height=dp(58),
                              padding=(0, dp(3)))
            barre.add_widget(KivyImage(source=logo, allow_stretch=True,
                                       keep_ratio=True))
            v = Label(text="[b]STUDIO RECORDER[/b]\n[size=9sp]v%s[/size]" % __version__,
                      markup=True, size_hint_x=None, width=dp(112),
                      halign="right", font_size=dp(10), color=TEXTE_2)
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
        self._historique_log.append(str(txt))
        if len(self._historique_log) > 200:
            self._historique_log = self._historique_log[-120:]
        # L'interface reste calme : seule la derniere information utile est
        # visible. L'historique reste conserve en memoire pour le diagnostic.
        self.log.text = str(txt)

    def voir_journal(self):
        HistoriquePopup(list(self._historique_log)).open()

    def afficher(self, i):
        arreter_lecture()
        if isinstance(self.ec_edit, EcranEdit):
            self.ec_edit._arreter_spectre()
            self.ec_edit._arreter_tete()
        # En arrivant sur la bibliotheque on relit le disque : une prise
        # enregistree entre-temps doit apparaitre sans rien demander.
        if self.ONGLETS[i] == "SONS" and isinstance(self.ec_biblio,
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
            # L'ecran systeme d'acces complet arrive APRES les boites de
            # dialogue ordinaires : les enchainer trop vite empile deux
            # fenetres et l'utilisateur ne voit que la derniere.
            Clock.schedule_once(lambda *_: self._acces_fichiers(), 2.5)
        try:
            return Root()
        except Exception as e:  # noqa: BLE001
            return EcranErreur(trace_complete(e), "DEMARRAGE")

    @staticmethod
    def _acces_fichiers():
        """Propose l'acces complet une fois, au premier lancement.

        On ne le redemande pas a chaque ouverture : un ecran de reglages
        qui surgit sans raison est plus penible qu'utile. Le bouton
        ACCES FICHIERS de l'onglet SONS reste disponible ensuite.
        """
        try:
            if stockage.acces_complet():
                return
            temoin = os.path.join(stockage.dossier_prive(),
                                  ".acces_demande")
            if os.path.exists(temoin):
                return
            with open(temoin, "w", encoding="utf-8") as f:
                f.write("demande une fois")
            stockage.demander_acces_complet()
        except Exception:  # noqa: BLE001
            pass

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
