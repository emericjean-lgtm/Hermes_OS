"""Mettre à jour sans perdre ce que seize jalons ont construit (HOS-232, HOS-233)."""

from backend.maj.code import PRESERVE_EN_PLACE, RemplacementImpossible, SauvegardeCode
from backend.maj.mise_a_jour import (
    Etape,
    Issue,
    MiseAJour,
    MiseAJourImpossible,
    Sauvegarde,
)
from backend.maj.paquet import Paquet, PaquetInvalide
from backend.maj.sante import Rapport, verifier
from backend.maj.version import (
    VERSION,
    IncompatibiliteVersion,
    Version,
    comparer,
    lire_version_installee,
    verifier_la_compatibilite,
)

__all__ = ["Etape", "IncompatibiliteVersion", "Issue", "MiseAJour",
           "MiseAJourImpossible", "PRESERVE_EN_PLACE", "Paquet",
           "PaquetInvalide", "Rapport", "RemplacementImpossible",
           "Sauvegarde", "SauvegardeCode", "VERSION", "Version", "comparer",
           "lire_version_installee", "verifier", "verifier_la_compatibilite"]
