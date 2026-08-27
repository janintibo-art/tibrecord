"""
Affichage de la forme d'onde, avec zoom et mesure precise.

Difference avec l'onde de MOC'TA BASS : ici on peut ZOOMER et se
DEPLACER. A fort grossissement on voit les echantillons un par un, et le
compteur descend au dixieme de milliseconde.

Ce module ne depend que de Kivy et du noyau audio.
"""

import math

from kivy.graphics import (Color, Line, Rectangle, RoundedRectangle,
                           Triangle)
from kivy.metrics import dp
from kivy.uix.label import Label
from kivy.uix.widget import Widget

from noyau import audio
from noyau.temps import graduations, sous_graduations

FOND = (0.06, 0.06, 0.08, 1)
GRILLE = (0.22, 0.22, 0.26, 1)
ONDE = (0.30, 0.85, 0.95, 1)
ONDE_HORS = (0.30, 0.32, 0.38, 1)
SELECTION = (0.30, 0.85, 0.95, 0.13)
POIGNEE = (0.95, 0.55, 0.15, 1)
TETE = (1.0, 0.85, 0.25, 1)
GRADUATION = (0.52, 0.54, 0.62, 1)
SOUS_GRADUATION = (0.30, 0.31, 0.37, 1)
GRADUATION_TXT = (0.66, 0.68, 0.74, 1)


class Onde(Widget):
    """Forme d'onde zoomable.

    Reperes :
      fenetre  (debut, fin) en fraction du son entier : ce qu'on voit
      selection (debut, fin) en fraction du son entier : ce qu'on garde
      tete      position de lecture, en fraction, ou None
    """

    ZOOMS = (1, 2, 4, 8, 16, 32, 64, 128, 256)

    def __init__(self, on_change=None, **kw):
        super().__init__(**kw)
        self.sample = None
        self._pics = []
        self._fenetre_calculee = None
        self.fen_debut, self.fen_fin = 0.0, 1.0
        self.sel_debut, self.sel_fin = 0.0, 1.0
        self.tete = None
        self.on_change = on_change
        self.regle = None
        self._prise = None
        self.bind(pos=self.redessiner, size=self.redessiner)

    # ------------------------------------------------------------ donnees
    def charger(self, sample):
        self.sample = sample
        self.fen_debut, self.fen_fin = 0.0, 1.0
        self.sel_debut, self.sel_fin = 0.0, 1.0
        self.tete = None
        self._pics = []
        self._fenetre_calculee = None
        self.redessiner()
        if self.regle is not None:
            self.regle.redessiner()

    @property
    def zoom(self):
        largeur = max(self.fen_fin - self.fen_debut, 1e-9)
        return 1.0 / largeur

    def duree_ms(self):
        return self.sample.duration_ms if self.sample else 0.0

    def bornes_ms(self):
        d = self.duree_ms()
        return self.sel_debut * d, self.sel_fin * d

    def echantillons(self):
        """Indices d'echantillon de la selection : la mesure exacte."""
        if not self.sample:
            return 0, 0
        n = len(self.sample.data)
        return int(self.sel_debut * n), int(self.sel_fin * n)

    # ------------------------------------------------------------ zoom
    def zoomer(self, facteur):
        """Zoome autour du centre de la fenetre."""
        centre = (self.fen_debut + self.fen_fin) / 2.0
        largeur = (self.fen_fin - self.fen_debut) / facteur
        largeur = max(1e-5, min(1.0, largeur))
        self._poser_fenetre(centre - largeur / 2, centre + largeur / 2)

    def cadrer_selection(self):
        """Ajuste la fenetre a la selection, avec une marge."""
        marge = max((self.sel_fin - self.sel_debut) * 0.1, 1e-5)
        self._poser_fenetre(self.sel_debut - marge, self.sel_fin + marge)

    def tout_voir(self):
        self._poser_fenetre(0.0, 1.0)

    def _poser_fenetre(self, d, f):
        largeur = max(1e-5, min(1.0, f - d))
        d = max(0.0, min(1.0 - largeur, d))
        self.fen_debut, self.fen_fin = d, d + largeur
        self._pics = []
        self.redessiner()
        if self.regle is not None:
            self.regle.redessiner()
        if self.on_change:
            self.on_change()

    def deplacer(self, fraction):
        largeur = self.fen_fin - self.fen_debut
        self._poser_fenetre(self.fen_debut + largeur * fraction,
                            self.fen_fin + largeur * fraction)

    # ------------------------------------------------------------ pics
    def _calculer(self):
        """Min et max par colonne, sur la fenetre visible seulement."""
        if self.sample is None or self.width < 10:
            self._pics = []
            return
        cle = (round(self.fen_debut, 6), round(self.fen_fin, 6),
               int(self.width))
        if cle == self._fenetre_calculee and self._pics:
            return
        d = self.sample.data
        n = len(d)
        i0 = max(0, int(self.fen_debut * n))
        i1 = min(n, max(i0 + 1, int(self.fen_fin * n)))
        colonnes = max(40, int(self.width / dp(1.2)))
        pas = (i1 - i0) / float(colonnes)
        pics = []
        for c in range(colonnes):
            a = i0 + int(c * pas)
            b = max(a + 1, i0 + int((c + 1) * pas))
            bloc = d[a:min(b, n)]
            if bloc:
                pics.append((min(bloc), max(bloc)))
        self._pics = pics
        self._fenetre_calculee = cle

    # ------------------------------------------------------------ dessin
    def redessiner(self, *_a):
        self.canvas.clear()
        self._calculer()
        x0, y0, w, h = self.x, self.y, self.width, self.height
        mid = y0 + h / 2.0
        demi = h / 2.0 - dp(4)

        with self.canvas:
            Color(*FOND)
            RoundedRectangle(pos=(x0, y0), size=(w, h), radius=[8])

            # reperes de temps : une ligne par division visible
            Color(*GRILLE)
            for i in range(1, 8):
                x = x0 + w * i / 8.0
                Line(points=[x, y0, x, y0 + h], width=1)
            Line(points=[x0, mid, x0 + w, mid], width=1)

            if not self._pics:
                return

            # selection, ramenee aux coordonnees de la fenetre
            largeur = max(self.fen_fin - self.fen_debut, 1e-9)
            sa = (self.sel_debut - self.fen_debut) / largeur
            sb = (self.sel_fin - self.fen_debut) / largeur
            if sb > 0 and sa < 1:
                ga = x0 + max(0.0, sa) * w
                gb = x0 + min(1.0, sb) * w
                Color(*SELECTION)
                Rectangle(pos=(ga, y0), size=(max(gb - ga, 1), h))

            n = len(self._pics)
            gros = self.zoom > 40
            for i, (mn, mx) in enumerate(self._pics):
                f = i / float(n)
                x = x0 + (i + 0.5) * w / n
                dans = sa <= f <= sb
                Color(*(ONDE if dans else ONDE_HORS))
                ymin = mid + max(mn, -1.0) * demi
                ymax = mid + min(mx, 1.0) * demi
                if ymax - ymin < 1:
                    ymax = ymin + 1
                Line(points=[x, ymin, x, ymax],
                     width=dp(1.4) if gros else 1)

            # poignees
            for xs in (sa, sb):
                if not 0 <= xs <= 1:
                    continue
                xh = x0 + xs * w
                Color(*POIGNEE)
                Line(points=[xh, y0, xh, y0 + h], width=dp(2))
                RoundedRectangle(pos=(xh - dp(6), y0 + h - dp(16)),
                                 size=(dp(12), dp(16)), radius=[3])
                RoundedRectangle(pos=(xh - dp(6), y0),
                                 size=(dp(12), dp(16)), radius=[3])

        self._dessiner_tete()

    def _dessiner_tete(self):
        """Dessine la seule tete de lecture, dans un calque a part.

        Separee du reste pour que l'animation ne repeigne pas toute la
        forme d'onde : sur un telephone, ca fait la difference entre une
        barre fluide et une barre qui saccade.
        """
        self.canvas.after.clear()
        if self.tete is None or self.sample is None:
            return
        largeur = max(self.fen_fin - self.fen_debut, 1e-9)
        ft = (self.tete - self.fen_debut) / largeur
        if not 0 <= ft <= 1:
            return
        x = self.x + ft * self.width
        y0, h = self.y, self.height
        with self.canvas.after:
            Color(*TETE)
            Line(points=[x, y0, x, y0 + h], width=dp(1.6))
            Triangle(points=[x - dp(5), y0 + h, x + dp(5), y0 + h,
                             x, y0 + h - dp(7)])

    def poser_tete(self, fraction):
        """Deplace la tete de lecture. None l'efface."""
        self.tete = fraction
        self._dessiner_tete()

    # ------------------------------------------------------------ touches
    def _fraction(self, x):
        f = (x - self.x) / float(self.width or 1)
        largeur = self.fen_fin - self.fen_debut
        return max(0.0, min(1.0, self.fen_debut + f * largeur))

    def on_touch_down(self, touch):
        if not self.collide_point(*touch.pos) or self.sample is None:
            return False
        f = self._fraction(touch.x)
        self._prise = ("debut" if abs(f - self.sel_debut)
                       <= abs(f - self.sel_fin) else "fin")
        self._appliquer(f)
        return True

    def on_touch_move(self, touch):
        if self._prise is None:
            return False
        self._appliquer(self._fraction(touch.x))
        return True

    def on_touch_up(self, touch):
        if self._prise is None:
            return False
        self._prise = None
        return True

    def _appliquer(self, f):
        mini = 1e-5
        if self._prise == "debut":
            self.sel_debut = min(f, self.sel_fin - mini)
        else:
            self.sel_fin = max(f, self.sel_debut + mini)
        self.sel_debut = max(0.0, self.sel_debut)
        self.sel_fin = min(1.0, self.sel_fin)
        self.redessiner()
        if self.on_change:
            self.on_change()


class Regle(Widget):
    """Bande de temps sous la forme d'onde.

    Elle suit exactement la fenetre de l'onde : quand on zoome, les
    graduations se resserrent et les nombres se precisent. C'est ce qui
    permet de dire "je coupe a 1,2 s" en regardant l'ecran, sans
    calculer.
    """

    def __init__(self, onde, **kw):
        super().__init__(**kw)
        self.onde = onde
        self._etiquettes = []
        self.bind(pos=self.redessiner, size=self.redessiner)

    def redessiner(self, *_a):
        self.canvas.clear()
        x0, y0, w, h = self.x, self.y, self.width, self.height
        with self.canvas:
            Color(*FOND)
            Rectangle(pos=(x0, y0), size=(w, h))
            Color(*GRILLE)
            Line(points=[x0, y0 + h - 1, x0 + w, y0 + h - 1], width=1)

        for lbl in self._etiquettes:
            self.remove_widget(lbl)
        self._etiquettes = []

        o = self.onde
        if o is None or o.sample is None or w < 10:
            return

        duree = o.duree_ms()
        t0, t1 = o.fen_debut * duree, o.fen_fin * duree
        visible = max(t1 - t0, 1e-9)
        cibles = max(3, int(w / dp(74)))
        reperes = graduations(t0, t1, cibles)
        petits = sous_graduations(t0, t1, cibles)

        with self.canvas:
            # Petits traits d'abord : ils passent sous les grands.
            Color(*SOUS_GRADUATION)
            for t in petits:
                x = x0 + (t - t0) / visible * w
                Line(points=[x, y0 + h, x, y0 + h - dp(3)], width=1)
            Color(*GRADUATION)
            for t, _ in reperes:
                x = x0 + (t - t0) / visible * w
                Line(points=[x, y0 + h, x, y0 + h - dp(7)], width=dp(1.2))

        # Le canvas ne dessine pas de texte : il faut de vrais Label.
        for t, texte in reperes:
            x = x0 + (t - t0) / visible * w
            lbl = Label(text=texte, font_size=dp(9), color=GRADUATION_TXT,
                        size_hint=(None, None),
                        size=(dp(60), max(h - dp(7), dp(10))),
                        halign="center", valign="middle")
            lbl.text_size = lbl.size
            lbl.pos = (x - dp(30), y0)
            self.add_widget(lbl)
            self._etiquettes.append(lbl)


def horloge(secondes, precision=3):
    """0:01.234 — et au dixieme de ms quand on zoome fort."""
    if secondes < 0:
        secondes = 0
    m = int(secondes // 60)
    r = secondes % 60
    return "%d:%0*.*f" % (m, precision + 3, precision, r)


def position_texte(onde, fraction):
    """Temps et numero d'echantillon a une position donnee."""
    if onde.sample is None:
        return "-"
    d = onde.duree_ms() / 1000.0
    n = len(onde.sample.data)
    precision = 4 if onde.zoom > 40 else 3
    return "%s  |  ech. %d" % (horloge(fraction * d, precision),
                               int(fraction * n))
