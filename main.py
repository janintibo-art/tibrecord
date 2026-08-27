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
from kivy.graphics import Color, RoundedRectangle, Triangle
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.filechooser import FileChooserListView
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.progressbar import ProgressBar
from kivy.uix.scrollview import ScrollView
from kivy.uix.slider import Slider
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput

from noyau import __version__, audio, enregistrement
from onde import Onde, horloge, position_texte

# ---------------------------------------------------------------- palette
FOND = (0.055, 0.055, 0.07, 1)
PANNEAU = (0.10, 0.10, 0.13, 1)
CYAN = (0.16, 0.80, 0.86, 1)
CYAN_S = (0.08, 0.38, 0.42, 1)
ROUGE = (0.88, 0.24, 0.24, 1)
VERT = (0.16, 0.62, 0.35, 1)
GRIS = (0.19, 0.19, 0.23, 1)
GRIS_CHOIX = (0.27, 0.27, 0.33, 1)
TEXTE = (0.90, 0.90, 0.92, 1)
TEXTE_2 = (0.62, 0.62, 0.68, 1)

IS_ANDROID = "ANDROID_ARGUMENT" in os.environ
TMP = tempfile.mkdtemp(prefix="tibrecord_")


# --------------------------------------------------------------------------
def dossier_travail():
    if IS_ANDROID:
        return os.environ.get("ANDROID_PRIVATE") or "/sdcard/Download"
    return os.getcwd()


def dossier_sons():
    d = os.path.join(dossier_travail(), "enregistrements")
    os.makedirs(d, exist_ok=True)
    return d


_LECTEUR = {"son": None}


def arreter_lecture():
    son = _LECTEUR.get("son")
    if son is not None:
        try:
            son.stop()
            son.unload()
        except Exception:  # noqa: BLE001
            pass
        _LECTEUR["son"] = None


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
    return son


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
class Bouton(Button):
    """Bouton a coins arrondis."""

    def __init__(self, couleur=GRIS, rayon=8, **kw):
        kw.setdefault("background_normal", "")
        kw.setdefault("background_color", (0, 0, 0, 0))
        kw.setdefault("color", TEXTE)
        super().__init__(**kw)
        self.couleur = couleur
        with self.canvas.before:
            self._c = Color(*couleur)
            self._r = RoundedRectangle(radius=[rayon])
        self.bind(pos=self._maj, size=self._maj, state=self._maj)
        self._maj()

    def _maj(self, *_a):
        self._r.pos, self._r.size = self.pos, self.size
        c = self.couleur
        if self.state == "down":
            c = tuple(min(1.0, v * 1.35) for v in c[:3]) + (c[3],)
        elif self.disabled:
            c = tuple(v * 0.45 for v in c[:3]) + (c[3],)
        self._c.rgba = c

    def set_couleur(self, couleur):
        self.couleur = couleur
        self._maj()


class Choix(Spinner):
    """Liste deroulante avec un chevron, pour qu'on voie que c'est un choix."""

    def __init__(self, **kw):
        kw.setdefault("background_normal", "")
        kw.setdefault("background_color", (0, 0, 0, 0))
        kw.setdefault("color", TEXTE)
        super().__init__(**kw)
        with self.canvas.before:
            self._fond = Color(*GRIS_CHOIX)
            self._rect = RoundedRectangle(radius=[8])
        with self.canvas.after:
            Color(*CYAN)
            self._fleche = Triangle(points=[0, 0, 0, 0, 0, 0])
        self.bind(pos=self._maj, size=self._maj)
        self._maj()

    def _maj(self, *_a):
        self._rect.pos, self._rect.size = self.pos, self.size
        l = dp(9)
        x, y = self.right - dp(14), self.center_y + l * 0.35
        self._fleche.points = [x - l / 2, y, x + l / 2, y, x, y - l * 0.75]


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

        cadre = Panneau(orientation="vertical", size_hint_y=None,
                        height=dp(250), padding=dp(6))
        self.onde = Onde(on_change=self._maj_mesures)
        cadre.add_widget(self.onde)
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
        b_st.bind(on_release=lambda *_: arreter_lecture())
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
        except Exception as e:  # noqa: BLE001
            self.journal("Lecture impossible : %s" % e)

    def sauver(self):
        if self.sample is None:
            return
        NomPopup("Nom du fichier", self.lbl_nom.text.replace(".wav", ""),
                 self._faire_sauver).open()

    def _faire_sauver(self, nom):
        try:
            net = "".join(c if c.isalnum() or c in "-_ " else "_"
                          for c in nom).strip() or "son"
            chemin = os.path.join(dossier_sons(), net + ".wav")
            audio.write_wav(chemin, self.sample)
            self.journal("Ecrit : %s" % chemin)
        except Exception as e:  # noqa: BLE001
            self.journal("Ecriture impossible : %s" % e)


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
  Le compteur affiche le temps ET le numero d'echantillon.

  Rogner      reduit le son a la selection
  Normaliser  amene la crete a -0,3 dB
  Fondus      evite les clics au debut et a la fin
  Traiter     applique un preset complet
  Annuler     revient en arriere, 12 etapes

  Enregistrer ecrit un WAV mono 16 bits 44,1 kHz.

OU SONT LES FICHIERS
  Dans le sous-dossier enregistrements/ du dossier de l'application.
  Le chemin exact s'affiche dans le journal a chaque ecriture.

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
    ONGLETS = ("ENREG.", "EDIT.", "TUTO")

    def __init__(self, **kw):
        super().__init__(orientation="vertical", spacing=dp(6),
                         padding=dp(8), **kw)
        self.add_widget(Label(
            text="[b]Tibrecord[/b]  [size=12sp]v%s[/size]" % __version__,
            markup=True, size_hint_y=None, height=dp(32), color=CYAN))

        barre = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(4))
        self.tabs = []
        for i, nom in enumerate(self.ONGLETS):
            b = Bouton(text=nom, font_size=dp(12), rayon=6)
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
        self.ecrans = [
            self._fabriquer("ENREG.", EcranEnreg, self.journal,
                            self._apres_capture),
            self.ec_edit,
            self._fabriquer("TUTO", EcranTuto),
        ]
        self.afficher(0)

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

    @mainthread
    def journal(self, txt):
        lignes = self.log.text.split("\n")
        if len(lignes) > 200:
            self.log.text = "\n".join(lignes[-120:])
        self.log.text += txt + "\n"

    def afficher(self, i):
        arreter_lecture()
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
