"""Pourquoi un run a échoué, et ce que ça change (HOS-225).

## Le manque

HOS-221 a donné onze causes à `registre.Cause` et **n'en a renseigné
aucune**, avec cette raison, écrite dans le code :

> classer un échec depuis un message d'erreur demande la taxonomie qui
> fait l'objet de son propre jalon. Deviner maintenant produirait des
> étiquettes fausses — et une étiquette fausse coûte plus cher qu'une
> case vide, parce qu'on la croit.

Voici ce jalon. La contrainte n'a pas changé : **une étiquette fausse
coûte plus cher qu'une case vide.** Ce module ne classe donc que sur des
indices qu'il peut nommer, et `INCONNUE` est un résultat courant, normal
et honnête — pas un aveu d'échec.

## Ce que le retry fait aujourd'hui, et pourquoi c'est faux

`_resolve_model` change de modèle **à toute reprise**, quelle que soit la
cause. C'est le bon remède pour exactement un cas sur onze :

- **manque de VRAM** — il faut un modèle *plus petit*, ou attendre ; un
  autre modèle de même taille rate pareil ;
- **fenêtre de contexte fermée** — `done_reason == "length"`. CLAUDE.md
  le dit déjà : « une réponse tronquée n'est pas une erreur de
  raisonnement et ne doit pas se noter comme telle ». Changer de modèle
  ne répare rien ; il faut plus de contexte ou moins de prompt ;
- **quota dépassé** — réessayer tout de suite chez le même fournisseur
  échoue par construction ;
- **refus de politique ou de sécurité** — il ne faut **pas** réessayer.
  Une boucle de reprise sur une action refusée est précisément ce que
  `approvals.py` décrit comme le comportement à ne pas produire.

## La règle de classement

Un indice est un fait vérifiable : un code HTTP, un `done_reason`, un
motif qui n'apparaît que dans un message généré par ce dépôt. Une cause
n'est retenue que si l'indice qui la porte est enregistré à côté, dans
`Classement.indice` — sans quoi une classification fausse serait
indébogable, et on ne saurait pas si le tort vient du modèle ou de
l'instrument.

C'est la leçon centrale du dépôt appliquée à sa propre instrumentation :
cinq des huit défauts de mesure trouvés pendant la construction du
catalogue produisaient de **faux échecs**, et aucun n'a été trouvé en
relisant du code.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from backend.runs.registre import Cause


@dataclass(frozen=True)
class Classement:
    """Une cause, et ce qui permet de l'affirmer."""

    cause: Cause
    #: Le fait qui a décidé. Vide seulement quand la cause est INCONNUE —
    #: et une cause connue sans indice serait un défaut de ce module.
    indice: str = ""

    @property
    def classe(self) -> bool:
        return self.cause is not Cause.INCONNUE


@dataclass(frozen=True)
class Remede:
    """Ce qu'il faut changer pour que la reprise ne rate pas pareil.

    Quatre leviers indépendants plutôt qu'une consigne unique : un manque
    de VRAM demande un modèle plus petit *et* une attente, un quota
    demande un autre fournisseur *sans* changer de modèle. Les fondre en
    « réessayer autrement » redonnerait le comportement d'aujourd'hui.
    """

    reessayer: bool
    explication: str
    #: Un modèle différent. Vrai seulement quand c'est le modèle qui a
    #: échoué — pas à chaque reprise, comme aujourd'hui.
    changer_de_modele: bool = False
    #: Un modèle **plus petit**, ce qui n'est pas la même demande.
    reduire_le_modele: bool = False
    #: Plus de contexte servi, ou moins de prompt.
    elargir_le_contexte: bool = False
    changer_de_fournisseur: bool = False
    #: Un délai avant la reprise, en secondes. Zéro = tout de suite.
    attendre_s: float = 0.0

    # Pas de plafond de tentatives par cause, et c'est un retrait
    # délibéré. Une première version en portait un, à 2 par défaut : il
    # **rétrécissait** silencieusement le budget que l'opérateur avait
    # configuré dans `max_retries_per_task`, et un test existant l'a dit
    # tout de suite (une mission réglée sur 2 reprises n'en obtenait plus
    # qu'une).
    #
    # Aucune mesure ne dit qu'un manque de VRAM mérite moins de
    # tentatives qu'un échec quelconque. L'opinion de ce module est
    # binaire — on reprend ou on ne reprend pas — et le combien reste au
    # budget de la mission, qui est le seul chiffre que quelqu'un ait
    # décidé.


#: Les indices, dans l'ordre où ils sont examinés. Chaque entrée est un
#: motif, la cause qu'il démontre, et le nom de l'indice qui sera
#: enregistré. L'ordre compte : les motifs les plus spécifiques d'abord,
#: parce que « timed out » apparaît aussi dans des messages de quota.
_MOTIFS: tuple[tuple[re.Pattern[str], Cause, str], ...] = (
    # Émis par `task_executor._attendre_l_admission_vram` : le message le
    # plus explicite du dépôt, et le seul qui nomme la VRAM.
    (re.compile(r"no vram admission", re.I), Cause.RESSOURCE,
     "message d'admission VRAM"),
    (re.compile(r"\b(out of memory|oom|cuda out of memory|insufficient "
                r"memory)\b", re.I), Cause.RESSOURCE, "message de mémoire"),

    (re.compile(r"\b(rate limit|too many requests|quota exceeded|"
                r"insufficient[_ ]quota|credit)\b", re.I), Cause.QUOTA,
     "message de quota"),

    (re.compile(r"\b(context length|maximum context|context window|"
                r"token limit|prompt is too long|reduce the length)\b", re.I),
     Cause.CONTEXTE, "message de fenêtre de contexte"),

    # Émis par `aegis`/`approvals`/`file_tools` sur un refus.
    (re.compile(r"\b(outside allowed_paths|permission denied|not authorised|"
                r"not authorized|refus(é|e)|requires human validation|"
                r"protected branch)\b", re.I), Cause.POLITIQUE,
     "message de refus de politique"),
    (re.compile(r"\b(canary|secret leak|fuite de secret|derive de workspace|"
                r"dérive de workspace)\b", re.I), Cause.SECURITE,
     "message de sécurité"),

    # La phrase du dépôt lui-même, dans `task_executor` : les deux routes
    # ont échoué. Sans ambiguïté, et donc classable — contrairement au
    # catch-all « could not execute task », qui ne dit rien de la raison
    # et reste volontairement INCONNUE.
    (re.compile(r"the local fallback also failed", re.I), Cause.FOURNISSEUR,
     "cloud et repli local tous deux en échec"),

    (re.compile(r"\b(connection refused|connection error|connection reset|"
                r"unavailable|unreachable|service unavailable|bad gateway|"
                r"name or service not known)\b", re.I), Cause.FOURNISSEUR,
     "message d'indisponibilité du fournisseur"),

    # `runtime 'x' timed out after Ns` — examiné **après** VRAM et quota,
    # qui produisent aussi des délais dépassés et disent pourquoi.
    (re.compile(r"\btimed? ?out\b", re.I), Cause.FOURNISSEUR,
     "délai de runtime dépassé"),

    (re.compile(r"\b(returned an empty completion|empty response)\b", re.I),
     Cause.MODELE, "réponse vide"),

    (re.compile(r"\b(no such tool|unknown tool|tool call failed|"
                r"could not start the executor event loop)\b", re.I),
     Cause.OUTIL, "message d'outil"),
)

#: Les codes HTTP qui **démontrent** une cause. Un code est un fait, pas
#: une interprétation : il passe donc avant les motifs de texte.
#:
#: 400 y figure à cause d'un incident précis. La campagne du catalogue
#: comptait « 0 s par tentative » : c'était un HTTP 400 jamais regardé,
#: et il s'était rangé sous « le modèle ne sait pas faire ».
_CODES: dict[int, tuple[Cause, str]] = {
    400: (Cause.OUTIL, "HTTP 400 — la requête est malformée, pas le modèle"),
    401: (Cause.POLITIQUE, "HTTP 401"),
    403: (Cause.POLITIQUE, "HTTP 403"),
    404: (Cause.OUTIL, "HTTP 404"),
    408: (Cause.FOURNISSEUR, "HTTP 408"),
    413: (Cause.CONTEXTE, "HTTP 413 — charge trop grosse"),
    429: (Cause.QUOTA, "HTTP 429"),
    500: (Cause.FOURNISSEUR, "HTTP 500"),
    502: (Cause.FOURNISSEUR, "HTTP 502"),
    503: (Cause.FOURNISSEUR, "HTTP 503"),
    504: (Cause.FOURNISSEUR, "HTTP 504"),
}


def classer(message: str = "", *, statut_http: int | None = None,
            done_reason: str | None = None,
            exception: BaseException | None = None) -> Classement:
    """Classer un échec sur des indices, ou dire qu'on ne sait pas.

    L'ordre est celui de la force de preuve :

    1. `done_reason == "length"` — Ollama affirme lui-même que la fenêtre
       s'est fermée. C'est le seul indice du lot qui vienne du runtime et
       non d'un message rédigé ici.
    2. Le code HTTP — un fait, pas une interprétation.
    3. Les motifs de texte — les moins fiables, examinés en dernier.

    Rend `INCONNUE` sans indice quand rien ne démontre rien. C'est un
    résultat normal, et `remede()` lui donne le comportement prudent.
    """
    if done_reason and str(done_reason).strip().lower() == "length":
        # CLAUDE.md : « une réponse tronquée n'est pas une erreur de
        # raisonnement et ne doit pas se noter comme telle ». Le
        # départage de code a coupé qwen3.6-35b en plein milieu pour
        # cette raison exacte, et l'a noté comme une faute.
        return Classement(Cause.CONTEXTE,
                          "done_reason=length — la fenêtre s'est fermée")

    if statut_http is not None and int(statut_http) in _CODES:
        cause, indice = _CODES[int(statut_http)]
        return Classement(cause, indice)

    texte = " ".join(filter(None, [message or "", str(exception or "")]))
    if not texte.strip():
        return Classement(Cause.INCONNUE)

    for motif, cause, indice in _MOTIFS:
        trouve = motif.search(texte)
        if trouve:
            return Classement(cause, f"{indice} : « {trouve.group(0)} »")

    return Classement(Cause.INCONNUE)


#: Un remède par cause. Écrits ici plutôt que dispersés dans les
#: appelants : c'est la table qu'on relit quand une reprise se comporte
#: mal, et elle doit tenir sur un écran.
_REMEDES: dict[Cause, Remede] = {
    Cause.RESSOURCE: Remede(
        reessayer=True, reduire_le_modele=True, attendre_s=15.0,
        explication=("la VRAM manque : un autre modèle de même taille "
                     "échouera pareil, il en faut un plus petit — ou "
                     "laisser un modèle résident se libérer")),
    Cause.CONTEXTE: Remede(
        reessayer=True, elargir_le_contexte=True,
        explication=("la fenêtre s'est fermée sur le modèle : changer de "
                     "modèle ne répare rien, il faut plus de contexte "
                     "servi ou moins de prompt")),
    Cause.QUOTA: Remede(
        reessayer=True, changer_de_fournisseur=True, attendre_s=60.0,
        explication=("le quota est dépassé : réessayer tout de suite chez "
                     "le même fournisseur échoue par construction")),
    Cause.FOURNISSEUR: Remede(
        reessayer=True, changer_de_fournisseur=True, attendre_s=10.0,
        explication="le service n'a pas répondu ; le modèle n'est pas en cause"),
    Cause.MODELE: Remede(
        reessayer=True, changer_de_modele=True,
        explication=("le modèle a produit une sortie inutilisable — le seul "
                     "cas où changer de modèle est le bon remède")),
    Cause.OUTIL: Remede(
        reessayer=True,
        explication=("un outil ou une requête est malformé : c'est un défaut "
                     "d'ici, pas du modèle, et il ne se répare pas en "
                     "réessayant plus fort")),
    Cause.SEMANTIQUE: Remede(
        reessayer=True,
        explication=("le travail est faux : la reprise doit porter les "
                     "preuves, pas relancer le même prompt")),
    Cause.VERIFICATION: Remede(
        reessayer=True,
        explication="la vérification a démenti le résultat annoncé"),
    # `reessayer=False` porte sur la reprise **automatique**, et la
    # nuance compte : une action en attente d'accord humain sera bien
    # rejouée — quand l'humain aura répondu, pas dans la milliseconde qui
    # suit. `approvals.py` décrit déjà ce que produit l'autre choix :
    # « an agent retrying in a loop after a refusal will re-ask »,
    # c'est-à-dire une file d'approbation inondée par la machine.
    Cause.POLITIQUE: Remede(
        reessayer=False,
        explication=("l'action a été refusée ou attend un accord humain : la "
                     "reprise viendra de cet accord, pas de la boucle — qui "
                     "ne ferait qu'inonder la file")),
    Cause.SECURITE: Remede(
        reessayer=False,
        explication=("un contrôle de sécurité s'est déclenché : réessayer "
                     "reviendrait à contourner ce qui vient de protéger")),
    Cause.INCONNUE: Remede(
        reessayer=True,
        explication=("aucun indice ne dit pourquoi : on reprend une fois, "
                     "sans rien changer qu'on ne saurait justifier")),
}


def remede(cause: Cause) -> Remede:
    """Ce qu'il faut changer. Prudent par défaut.

    Une cause absente de la table rend le remède d'`INCONNUE` plutôt que
    de lever : ce module est consulté sur le chemin d'un échec, et y
    lever transformerait un échec diagnosticable en échec muet.
    """
    return _REMEDES.get(cause, _REMEDES[Cause.INCONNUE])


def depuis_l_erreur(message: str = "", **indices: Any) -> tuple[Cause, Remede, str]:
    """Le raccourci des appelants : classer et choisir d'un coup."""
    classement = classer(message, **indices)
    return classement.cause, remede(classement.cause), classement.indice


__all__ = ["Classement", "Remede", "classer", "depuis_l_erreur", "remede"]
