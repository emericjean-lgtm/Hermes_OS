"""Surveiller ce qui sort d'un agent, pendant qu'il parle (HOS-218).

## Pourquoi surveiller la sortie plutôt que l'entrée

On ne peut pas énumérer tout ce qu'un agent ne doit pas dire. Mais on
peut savoir quand il dit **une chose précise** qu'il n'aurait jamais dû
voir.

C'est le canary d'Agent OS, et c'est la meilleure idée de leur code : on
plante dans l'environnement du sous-processus une fausse valeur, connue
de nous seuls, avec la forme d'un secret. Si elle réapparaît en sortie,
c'est que l'agent a lu son environnement et le recrache — donc que les
vrais secrets qui vivent à côté sont exposés de la même façon.

On n'a pas besoin de deviner comment la fuite se produit. On sait
seulement qu'elle s'est produite, et on coupe.

## Les trois autres surveillances

**Les secrets connus**, cherchés dans le flux. Avec un **report de 512
caractères** entre deux blocs : un secret coupé en deux par la
fragmentation du flux passerait sinon entre les mailles.

**Le silence.** Un agent qui ne dit plus rien n'échoue pas — il attend.
La nuit du 29 au 30 août l'a montré ailleurs : un décodage qui débordait
ne levait aucune erreur, il rampait pendant quarante minutes. Un silence
prolongé est un événement, pas une absence d'événement.

**Le coût.** Le disjoncteur reçoit le montant à chaque tour et peut
couper dessus, au même titre que sur une fuite.

## Ce que ce module ne fait pas

Il ne tue pas le processus. Il **rapporte** et appelle ce qu'on lui a
donné. La décision d'arrêter appartient à l'appelant — la même séparation
qu'entre le détecteur de dérive et la politique.
"""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Iterable

#: Assez pour qu'aucun secret réaliste ne soit coupé en deux entre deux
#: blocs du flux. Agent OS retient la même valeur, et une clé d'API
#: dépasse rarement 200 caractères.
REPORT = 512

#: Sans sortie pendant ce délai, on le dit. Ce n'est pas une erreur —
#: c'est une observation, et c'est à l'appelant de décider.
SILENCE_S = 120.0

#: Sous cette longueur, un « secret » déclenche trop souvent : « 1 »,
#: « true », un identifiant de deux caractères se retrouvent partout dans
#: une sortie normale.
LONGUEUR_MIN_SECRET = 8


class Motif(str, Enum):
    CANARY = "canary_expose"
    SECRET = "secret_expose"
    SILENCE = "silence"
    COUT = "cout_depasse"


@dataclass
class Alerte:
    motif: Motif
    detail: str = ""
    a: float = field(default_factory=time.monotonic)


def fabriquer_canary() -> str:
    """Une fausse valeur avec la forme d'un secret, unique par exécution.

    Le préfixe la rend reconnaissable dans un rapport ; le reste la rend
    impossible à deviner, donc impossible à produire par hasard. Unique
    par exécution : un canary constant finirait dans un journal, puis
    dans un rapport de bogue, et déclencherait à tort.
    """
    return "hos-canary-" + secrets.token_hex(16)


class SurveillanceFlux:
    """Regarde passer la sortie d'un agent et lève des alertes.

    Sans état partagé et sans fil d'exécution : l'appelant pousse ce
    qu'il reçoit avec `bloc()` et appelle `tic()` de temps en temps. Ça
    le rend éprouvable sans processus réel, ce qui est la seule façon
    d'avoir des tests sur une surveillance de sécurité.
    """

    def __init__(self, *, canary: str, secrets_connus: Iterable[str] = (),
                 sur_alerte: Callable[[Alerte], None] | None = None,
                 silence_s: float = SILENCE_S,
                 cout_max: float | None = None) -> None:
        self._canary = canary
        # Les valeurs trop courtes sont écartées : elles feraient sonner
        # l'alarme sur une sortie parfaitement normale, et une alarme qui
        # sonne pour rien est débranchée dans la semaine.
        self._secrets = [s for s in secrets_connus
                         if s and len(s) >= LONGUEUR_MIN_SECRET]
        self._sur_alerte = sur_alerte
        self._silence_s = silence_s
        self._cout_max = cout_max

        self._report = ""
        self._derniere_sortie = time.monotonic()
        self._silence_signale = False
        self.alertes: list[Alerte] = []

    # ── Ce que l'appelant pousse ─────────────────────────────────────

    def bloc(self, texte: str) -> Alerte | None:
        """Un morceau de sortie. Rend une alerte s'il y a de quoi couper.

        Le texte examiné est le **report plus le nouveau bloc** : un
        secret dont la moitié est arrivée au tour précédent est vu ici.
        """
        if not texte:
            return None
        self._derniere_sortie = time.monotonic()
        self._silence_signale = False

        fenetre = self._report + texte
        self._report = fenetre[-REPORT:]

        if self._canary and self._canary in fenetre:
            return self._lever(Alerte(
                Motif.CANARY,
                "la valeur témoin plantée dans l'environnement est ressortie — "
                "l'agent lit et recrache son environnement, donc les vrais "
                "secrets sont exposés de la même façon"))

        for s in self._secrets:
            if s in fenetre:
                return self._lever(Alerte(
                    Motif.SECRET,
                    # Jamais la valeur : un rapport de fuite qui contient
                    # le secret est une seconde fuite.
                    f"un secret connu de {len(s)} caractères est apparu "
                    "dans la sortie"))
        return None

    def tic(self, *, cout: float | None = None) -> Alerte | None:
        """Le temps passe, et le coût monte. À appeler périodiquement."""
        if cout is not None and self._cout_max is not None and cout > self._cout_max:
            return self._lever(Alerte(
                Motif.COUT,
                f"{cout:.4f} dépasse le plafond de {self._cout_max:.4f}"))

        silence = time.monotonic() - self._derniere_sortie
        if silence >= self._silence_s and not self._silence_signale:
            self._silence_signale = True
            return self._lever(Alerte(
                Motif.SILENCE,
                f"aucune sortie depuis {silence:.0f} s — un agent qui se tait "
                "n'échoue pas, il attend, et l'attente ressemble au travail"))
        return None

    # ── État ─────────────────────────────────────────────────────────

    @property
    def coupee(self) -> bool:
        """Une alerte de sécurité a-t-elle été levée ?

        Le silence et le coût n'y comptent pas : ce sont des observations
        qui appellent une décision, pas des fuites avérées.
        """
        return any(a.motif in (Motif.CANARY, Motif.SECRET)
                   for a in self.alertes)

    def _lever(self, alerte: Alerte) -> Alerte:
        self.alertes.append(alerte)
        if self._sur_alerte:
            self._sur_alerte(alerte)
        return alerte


def environnement_avec_canary(base: dict[str, str], canary: str,
                              nom: str = "HERMES_CANARY_TOKEN"
                              ) -> dict[str, str]:
    """L'environnement du sous-processus, avec le témoin dedans.

    Le nom ressemble à celui d'un vrai secret : un agent qui filtre son
    environnement sur des noms « sensibles » doit l'attraper aussi,
    sinon le témoin ne témoigne de rien.
    """
    env = dict(base)
    env[nom] = canary
    return env


__all__ = ["Alerte", "LONGUEUR_MIN_SECRET", "Motif", "REPORT", "SILENCE_S",
           "SurveillanceFlux", "environnement_avec_canary", "fabriquer_canary"]
