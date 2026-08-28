"""Tibrecord : enregistrement et travail du son au telephone."""

__version__ = "1.0.0"
APP_NAME = "Tibrecord"

from . import (audio, batch, bibliotheque, decoupe,  # noqa: F401,E402
               effets, enregistrement, montage,
               spectre, stockage, temps, travail, vignettes)
