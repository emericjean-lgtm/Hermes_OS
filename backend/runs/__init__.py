"""Le registre des exécutions et le contrat qu'elles doivent tenir (HOS-221).

Deux modules qui répondent à deux questions que Hermes ne savait pas
trancher :

- `contrat` : **qu'est-ce qui devait être vrai à la fin ?**
- `registre` : **qu'est-ce qui a été fait, avec quoi, et pourquoi le
  premier essai a échoué ?**

La seconde a coûté une nuit de production, la première un rapport
`success: true` posé sur quatre secondes d'image.
"""

from backend.runs.contrat import (
    Contrat,
    ContratInvalide,
    Critere,
    EtatCritere,
    Genre,
    Verdict,
)
from backend.runs.registre import Cause, Registre, Run, Statut, TERMINAUX

__all__ = ["Cause", "Contrat", "ContratInvalide", "Critere", "EtatCritere",
           "Genre", "Registre", "Run", "Statut", "TERMINAUX", "Verdict"]
