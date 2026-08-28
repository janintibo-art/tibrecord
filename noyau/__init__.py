"""Tibrecord : enregistrement et travail du son au telephone."""

__version__ = "0.8.0"
APP_NAME = "Tibrecord"

from . import (audio, batch, bibliotheque, effets,  # noqa: F401,E402
               enregistrement,
               spectre, stockage, temps, travail, vignettes)
