"""Mettre à jour sans perdre ce que quinze jalons ont construit (HOS-232)."""

from backend.maj.version import VERSION, Version, comparer, lire_version_installee
from backend.maj.mise_a_jour import (
    Etape,
    Issue,
    MiseAJour,
    MiseAJourImpossible,
    Sauvegarde,
)

__all__ = ["Etape", "Issue", "MiseAJour", "MiseAJourImpossible", "Sauvegarde",
           "VERSION", "Version", "comparer", "lire_version_installee"]
