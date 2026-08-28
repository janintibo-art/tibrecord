"""Tibrecord : enregistrement et travail du son au telephone."""

__version__ = "0.9.0"
APP_NAME = "Tibrecord"

from . import (audio, batch, bibliotheque, effets,  # noqa: F401,E402
               enregistrement, montage,
               spectre, stockage, temps, travail, vignettes)
