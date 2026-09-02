"""Ce qui a le droit de partir chez un tiers (HOS-227).

## La fuite, mesurée avant d'écrire une ligne

`RealTaskExecutor._build_messages` assemble un prompt et le donne au
runtime. Quand ce runtime est distant, tout part. Mesuré sur une mission
liée à un workspace :

    You have real filesystem access to the workspace at
    'C:\\Users\\emeri\\Skill360 Industry' via workspace_list/...

Le nom de l'utilisateur et celui de son client, dans **chaque** prompt
cloud. Ce n'est pas un scénario, c'est le comportement d'aujourd'hui.

Six fragments partent, de sensibilités différentes : les instructions
système (qui portent le chemin absolu), l'objectif de mission écrit par
l'utilisateur, le **journal de projet** relu depuis `.hermes/`, les
**résultats amont** — du texte produit par un modèle, qui peut citer le
contenu d'un fichier — le manifeste des livrables, et le titre.

## Ce que « refusé par défaut » peut vouloir dire, et ce qu'il ne peut pas

La décision §8.1 du cahier dit que le cloud est refusé par défaut, avec
l'asymétrie qui la fonde : classer trop haut coûte une gêne visible et
réversible ; classer trop bas envoie un secret chez un tiers,
définitivement, sans que personne le sache.

Appliquée **littéralement à du texte quelconque**, cette règle refuserait
tout : on ne peut pas démontrer qu'une phrase en prose n'est pas
sensible. Un pare-feu qui refuse tout est un pare-feu qu'on désarme dans
la semaine — la leçon du canary (HOS-218) et celle de la portée
d'approbation (HOS-224).

Le refus par défaut s'applique donc **là où il a un sens** :

1. **Au niveau du projet.** `politique_du_projet()` peut valoir
   `JAMAIS`, et alors rien de ce projet ne sort, quelle que soit la
   recommandation du routeur. C'est le vrai levier, à la bonne
   granularité : l'utilisateur sait si son dépôt client a le droit
   d'aller chez un tiers, le classificateur ne le saura jamais.
2. **Au niveau du constat.** Ce qui est **démontré** sensible est
   caviardé ou refusé — jamais laissé passer parce qu'on hésite.

Et comme partout ici, un constat **nomme son indice**. Un caviardage
qu'on ne peut pas expliquer est un caviardage qu'on désactive.

## Contexte nécessaire ≠ contenu autorisé

C'est la distinction qui donne son intérêt au caviardage plutôt qu'au
refus. Le modèle a besoin de savoir **qu'il existe** une racine de
workspace ; il n'a pas besoin de savoir qu'elle est chez `emeri`. Le
chemin est donc remplacé par un jeton stable — `<WORKSPACE>` — qui garde
la phrase utile et retire ce qui identifie.

Les chemins relatifs, eux, passent : ce sont eux le travail.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable

logger = logging.getLogger("hermes_os.security.pare_feu")

#: Le catalogue d'événements, **à côté de son producteur**.
#:
#: `collect_known_topics()` (bootstrap/event_wiring) assemble la liste
#: blanche depuis ces dictionnaires-là, et non depuis
#: `event_topics.BASELINE_TOPICS`. Un topic déclaré seulement dans le
#: second passe à l'exécution mais fait tomber
#: `test_topics_publies_sont_autorises` — c'est ce qui est arrivé ici, et
#: c'est le même patron que les huit catalogues rebranchés en HOS-181.
PARE_FEU_EVENTS: dict[str, str] = {
    "decision": "cloud.pare_feu",
}

#: Le jeton qui remplace une racine absolue. Stable entre deux appels :
#: un jeton qui changerait ferait croire au modèle qu'il change de
#: dossier entre deux tours.
JETON_WORKSPACE = "<WORKSPACE>"
JETON_CAVIARDE = "[CAVIARDÉ]"


class Sensibilite(str, Enum):
    """Trois niveaux. Un quatrième ne changerait pas ce qu'on en fait."""

    PUBLIC = "public"
    #: Identifiant, chemin d'utilisateur, adresse, machine interne. Part
    #: **caviardé** : le refuser rendrait le cloud inutilisable pour
    #: toute mission liée à un workspace, donc désarmerait le pare-feu.
    INTERNE = "interne"
    #: Un secret démontré. Ne part pas.
    SECRET = "secret"


class Verdict(str, Enum):
    AUTORISE = "autorise"
    #: Part, amputé de ce qui est démontré sensible.
    CAVIARDE = "caviarde"
    #: Ne part pas sans un accord humain. Passe par la file de HOS-224,
    #: avec son empreinte canonique et sa portée.
    APPROBATION = "approbation"
    REFUSE = "refuse"


class PolitiqueCloud(str, Enum):
    """Ce qu'un projet autorise. Décidé par l'utilisateur, pas déduit."""

    #: Le défaut : ce qui est démontré sensible est retiré, le reste part.
    CAVIARDER = "caviarder"
    #: Rien ne sort de ce projet. Le vrai « refusé par défaut », à la
    #: granularité où quelqu'un peut réellement en décider.
    JAMAIS = "jamais"
    #: Chaque envoi demande un accord. Pour un projet où l'on veut voir
    #: passer avant de laisser passer.
    APPROBATION = "approbation"


@dataclass(frozen=True)
class Constat:
    """Ce qui a été trouvé, et où. Jamais un verdict sans lui."""

    motif: str
    sensibilite: Sensibilite
    fragment: str
    #: Un extrait **déjà caviardé** de ce qui a déclenché. Ne contient
    #: jamais la valeur : un rapport de fuite qui cite le secret est une
    #: seconde fuite (HOS-218).
    apercu: str = ""


@dataclass
class Decision:
    """Ce qui part, ce qui ne part pas, et pourquoi."""

    verdict: Verdict
    #: Les messages tels qu'ils doivent être envoyés. Identiques à
    #: l'entrée quand le verdict est `AUTORISE`, amputés quand il est
    #: `CAVIARDE`, et **vides** sinon — pour qu'un appelant distrait qui
    #: enverrait quand même n'envoie rien.
    messages: list[dict] = field(default_factory=list)
    constats: list[Constat] = field(default_factory=list)
    raison: str = ""

    @property
    def envoyable(self) -> bool:
        return self.verdict in (Verdict.AUTORISE, Verdict.CAVIARDE)

    def resume(self) -> str:
        if not self.constats:
            return "rien de sensible constaté"
        par_motif: dict[str, int] = {}
        for c in self.constats:
            par_motif[c.motif] = par_motif.get(c.motif, 0) + 1
        return ", ".join(f"{n}× {m}" for m, n in sorted(par_motif.items()))


# ── Les détecteurs ───────────────────────────────────────────────────

#: Une racine d'utilisateur, sous Windows comme sous Unix. Le groupe
#: capturé est **la racine**, pas le chemin entier : ce qui suit est le
#: travail, et le retirer priverait le modèle de ce dont il a besoin.
_RACINES = (
    re.compile(r"(?i)([A-Z]:[\\/]+Users[\\/]+[^\\/\s'\"]+)"),
    re.compile(r"(/home/[^/\s'\"]+)"),
    re.compile(r"(/Users/[^/\s'\"]+)"),
)

_COURRIEL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]{2,}\b")

#: Adresses privées et machines internes. `127.0.0.1` en est exclu :
#: Hermes écoute dessus, il apparaît dans des messages d'erreur normaux,
#: et le caviarder rendrait un diagnostic illisible sans rien protéger.
_ADRESSE_PRIVEE = re.compile(
    r"\b(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}"
    r"|192\.168\.\d{1,3}\.\d{1,3}"
    r"|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})\b")


def _apercu(texte: str, debut: int, fin: int) -> str:
    """Un extrait autour du constat, caviardé.

    La valeur trouvée est remplacée avant même d'entrer dans le rapport :
    un rapport de fuite qui cite le secret est une seconde fuite.
    """
    from backend.core.audit_log import redact

    marge = 24
    gauche = texte[max(0, debut - marge):debut]
    droite = texte[fin:fin + marge]
    return redact(f"…{gauche}{JETON_CAVIARDE}{droite}…").replace("\n", " ")


def examiner_le_texte(nom: str, texte: str,
                      racines: Iterable[str] = ()) -> tuple[str, list[Constat]]:
    """Caviarder un fragment et dire ce qu'on y a trouvé.

    L'ordre compte : les secrets d'abord, sinon une clé contenue dans un
    chemin serait déjà remplacée par le jeton de workspace et ne serait
    plus reconnue comme secret.

    `racines` porte les chemins que l'appelant **sait** être des racines
    de workspace. Une expression régulière ne peut pas deviner où une
    racine s'arrête : mesuré, la racine du projet Skill360 était réduite
    à `<WORKSPACE>` suivi du nom du client, qui survivait donc au
    caviardage. L'appelant, lui, connaît la racine exacte.
    """
    from backend.core.audit_log import redact

    constats: list[Constat] = []
    if not texte:
        return texte, constats

    # 1. Les identifiants. `audit_log.redact` est le plus proche d'un
    #    `secret_scanner` que ce dépôt possède (§17.1), et ses motifs
    #    sont délibérément conservateurs : chacun ne vise qu'une forme
    #    qui n'est *jamais* autre chose qu'un identifiant. En écrire un
    #    second, divergent, serait pire que le réutiliser.
    apres_secrets = redact(texte)
    if apres_secrets != texte:
        constats.append(Constat(
            motif="identifiant", sensibilite=Sensibilite.SECRET,
            fragment=nom, apercu="(valeur retirée avant le rapport)"))
    texte = apres_secrets

    # 2. Les racines connues de l'appelant, d'abord et en entier. Trois
    #    écritures sont couvertes : antislash, slash, et la forme
    #    échappée que produit un `repr()` de chemin Windows — qui est
    #    exactement ce que `_build_messages` insère dans le prompt.
    antislash = chr(92)
    for racine in racines or ():
        racine = (racine or "").rstrip(antislash + "/")
        if len(racine) < 4:
            continue
        variantes = {racine, racine.replace(antislash, "/"),
                     racine.replace(antislash, antislash * 2)}
        for variante in sorted(variantes, key=len, reverse=True):
            if variante and variante in texte:
                constats.append(Constat(
                    motif="racine de workspace",
                    sensibilite=Sensibilite.INTERNE, fragment=nom,
                    apercu="racine remplacée par " + JETON_WORKSPACE))
                texte = texte.replace(variante, JETON_WORKSPACE)

    # 3. Les racines d'utilisateur non déclarées, en dernier recours.
    #    Remplacées, pas supprimées : le modèle a besoin de savoir qu'il
    #    existe une racine.
    for motif in _RACINES:
        for trouve in list(motif.finditer(texte)):
            constats.append(Constat(
                motif="chemin d'utilisateur", sensibilite=Sensibilite.INTERNE,
                fragment=nom, apercu=_apercu(texte, *trouve.span(1))))
        texte = motif.sub(JETON_WORKSPACE, texte)

    # 4. Le reste.
    for motif, nom_motif in ((_COURRIEL, "adresse de courriel"),
                             (_ADRESSE_PRIVEE, "adresse réseau privée")):
        for trouve in list(motif.finditer(texte)):
            constats.append(Constat(
                motif=nom_motif, sensibilite=Sensibilite.INTERNE,
                fragment=nom, apercu=_apercu(texte, *trouve.span())))
        texte = motif.sub(JETON_CAVIARDE, texte)

    return texte, constats


def examiner(messages: Iterable[dict], *,
             politique: PolitiqueCloud = PolitiqueCloud.CAVIARDER,
             racines: Iterable[str] = (),
             ) -> Decision:
    """Décider de ce qui part, avant que ça parte.

    Le contrôle est **avant l'envoi**, jamais après : après, c'est un
    constat de fuite, pas un pare-feu.
    """
    messages = [dict(m) for m in messages]

    if politique is PolitiqueCloud.JAMAIS:
        # Le vrai « refusé par défaut » : décidé par quelqu'un, à la
        # granularité où quelqu'un peut le décider. Aucun examen n'est
        # fait — il n'y a rien à peser.
        return Decision(
            verdict=Verdict.REFUSE, messages=[],
            raison=("ce projet n'autorise aucun envoi vers un tiers "
                    "(politique « jamais »)"))

    constats: list[Constat] = []
    for message in messages:
        contenu = message.get("content")
        if not isinstance(contenu, str):
            continue
        message["content"], trouves = examiner_le_texte(
            str(message.get("role") or "message"), contenu, racines)
        constats.extend(trouves)

    secrets = [c for c in constats if c.sensibilite is Sensibilite.SECRET]
    if secrets:
        # Refus, et pas « caviarder et envoyer le reste ». Un identifiant
        # dans un prompt veut dire que le contexte assemblé contient du
        # matériel qui n'aurait pas dû y entrer — vraisemblablement le
        # fichier d'où il vient. Retirer la clé et envoyer le fichier
        # autour serait la moitié d'une protection.
        return Decision(
            verdict=Verdict.REFUSE, messages=[], constats=constats,
            raison=(f"{len(secrets)} identifiant(s) dans le contexte : le "
                    "prompt contient du matériel qui n'aurait pas dû y "
                    "entrer, pas seulement une clé à retirer"))

    if politique is PolitiqueCloud.APPROBATION:
        return Decision(
            verdict=Verdict.APPROBATION, messages=[], constats=constats,
            raison="ce projet demande un accord avant chaque envoi")

    if constats:
        return Decision(
            verdict=Verdict.CAVIARDE, messages=messages, constats=constats,
            raison=f"envoyé après caviardage : {len(constats)} constat(s)")

    return Decision(verdict=Verdict.AUTORISE, messages=messages)


__all__ = ["Constat", "Decision", "JETON_CAVIARDE", "JETON_WORKSPACE",
           "PolitiqueCloud", "Sensibilite", "Verdict", "examiner",
           "examiner_le_texte"]
