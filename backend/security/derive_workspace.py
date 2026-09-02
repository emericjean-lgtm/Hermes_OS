"""Un workspace ne doit pas réécrire ce qui gouverne l'agent (HOS-217).

## La menace

Hermes ouvre un workspace pour y travailler. Ce workspace contient des
fichiers qui **gouvernent l'agent lui-même** : `CLAUDE.md` porte des
instructions que l'agent lit comme des consignes, `.mcp.json` déclare des
serveurs d'outils, `.claude/settings.json` porte des permissions,
`.claude/hooks/` exécute du code à des moments choisis.

Deux façons dont ça tourne mal, et aucune n'exige un attaquant :

**Un dépôt cloné arrive avec les siens.** On ouvre un projet trouvé en
ligne ; il apporte un `.mcp.json` qui déclare un serveur d'outils, ou un
hook qui s'exécute. Rien ne le signale, et l'agent hérite d'outils que
personne ne lui a donnés.

**L'agent modifie les siens en cours de route.** Il travaille dans le
workspace, écrit des fichiers, et écrit aussi — par obligeance ou par
consigne trouvée dans le dépôt — dans les fichiers qui le gouvernent. Il
élargit ses propres permissions.

Agent OS garde ça sous `m8-hostile-config`, avec une table de lignes de
base comparée à chaque run.

## Ce que ce module fait, et ne fait pas

Il **relève** l'empreinte des fichiers gouvernants et **compare**. Il ne
décide pas quoi en faire : bloquer, demander une approbation ou
seulement consigner relève de la politique, et cette décision appartient
à `AegisEngine`, pas à un détecteur.

C'est la même séparation que partout ici : mesurer, puis laisser
quelqu'un d'autre trancher sur la mesure.

## Ce qu'il refuse de deviner

Un fichier illisible n'est pas un fichier absent. Une empreinte qu'on n'a
pas pu prendre est rapportée comme **inconnue**, jamais comme
« inchangée » — c'est la même règle que le tri-état ailleurs : un « je ne
sais pas » ne se range pas avec les « c'est bon ».
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

#: Les fichiers et dossiers qui gouvernent le comportement de l'agent.
#: Énumérés plutôt que devinés : cette liste est la définition de la
#: surface d'attaque, elle doit être lisible et discutable.
GOUVERNANTS = (
    "CLAUDE.md",
    "AGENTS.md",
    ".mcp.json",
    ".claude/settings.json",
    ".claude/settings.local.json",
    ".claude/hooks",
    ".claude/skills",
    ".claude/agents",
    ".cursorrules",
    ".github/copilot-instructions.md",
)

#: Au-delà, on ne lit pas : un fichier de gouvernance fait quelques
#: kilooctets. Un « CLAUDE.md » de cent mégaoctets est en soi le signal.
TAILLE_MAX = 1 << 20  # 1 Mio


class Etat(str, Enum):
    INCHANGE = "inchange"
    MODIFIE = "modifie"
    AJOUTE = "ajoute"
    RETIRE = "retire"
    #: L'empreinte n'a pas pu être prise. Ni « inchangé », ni « modifié ».
    INCONNU = "inconnu"


@dataclass
class Ecart:
    chemin: str
    etat: Etat
    detail: str = ""


@dataclass
class LigneDeBase:
    """L'empreinte des fichiers gouvernants, à un instant donné."""

    racine: str = ""
    pris_le: str = ""
    empreintes: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"racine": self.racine, "pris_le": self.pris_le,
                "empreintes": dict(self.empreintes)}

    @classmethod
    def from_dict(cls, d: dict) -> "LigneDeBase":
        return cls(racine=d.get("racine", ""), pris_le=d.get("pris_le", ""),
                   empreintes=dict(d.get("empreintes") or {}))


def _empreinte_fichier(chemin: Path) -> str:
    """Le contenu, haché. `inconnu:` quand on n'a pas pu lire."""
    try:
        if chemin.stat().st_size > TAILLE_MAX:
            return f"trop-gros:{chemin.stat().st_size}"
        return "sha256:" + hashlib.sha256(chemin.read_bytes()).hexdigest()
    except OSError as e:
        return f"inconnu:{type(e).__name__}"


def _empreintes_sous(racine: Path, relatif: str) -> dict[str, str]:
    """Une entrée par fichier — un dossier gouvernant est relevé entier.

    Un hook ajouté dans `.claude/hooks/` doit se voir : hacher le dossier
    globalement dirait « quelque chose a changé » sans dire quoi.
    """
    cible = racine / relatif
    if not cible.exists():
        return {}
    if cible.is_file():
        return {relatif: _empreinte_fichier(cible)}

    out: dict[str, str] = {}
    for fichier in sorted(cible.rglob("*")):
        if not fichier.is_file():
            continue
        # `as_posix` : la ligne de base doit se comparer entre machines,
        # et Windows écrirait des antislashs.
        rel = fichier.relative_to(racine).as_posix()
        out[rel] = _empreinte_fichier(fichier)
    return out


def relever(racine: str | os.PathLike[str]) -> LigneDeBase:
    """Prendre l'empreinte des fichiers gouvernants d'un workspace."""
    r = Path(racine).resolve()
    empreintes: dict[str, str] = {}
    for relatif in GOUVERNANTS:
        empreintes.update(_empreintes_sous(r, relatif))
    return LigneDeBase(
        racine=str(r),
        pris_le=datetime.now(timezone.utc).isoformat(),
        empreintes=empreintes,
    )


def comparer(base: LigneDeBase, maintenant: LigneDeBase) -> list[Ecart]:
    """Ce qui a bougé depuis la ligne de base.

    L'ordre est stable — ajouts, modifications, retraits, inconnus — pour
    qu'un rapport se lise et se compare d'une exécution à l'autre.
    """
    ecarts: list[Ecart] = []
    avant, apres = base.empreintes, maintenant.empreintes

    for chemin in sorted(set(apres) - set(avant)):
        ecarts.append(Ecart(chemin, Etat.AJOUTE,
                            "n'existait pas quand la mission a commencé"))
    for chemin in sorted(set(avant) & set(apres)):
        a, b = avant[chemin], apres[chemin]
        if a == b:
            continue
        if b.startswith("inconnu:") or a.startswith("inconnu:"):
            ecarts.append(Ecart(chemin, Etat.INCONNU,
                                "empreinte non prise — ni inchangé, ni modifié"))
        else:
            ecarts.append(Ecart(chemin, Etat.MODIFIE, "contenu différent"))
    for chemin in sorted(set(avant) - set(apres)):
        ecarts.append(Ecart(chemin, Etat.RETIRE,
                            "présent au départ, absent maintenant"))
    return ecarts


def a_derive(ecarts: list[Ecart]) -> bool:
    """Y a-t-il de quoi s'arrêter ?

    Un `INCONNU` compte comme une dérive. On ne peut pas affirmer qu'un
    fichier de gouvernance est intact quand on n'a pas su le lire.
    """
    return bool(ecarts)


def resume(ecarts: list[Ecart]) -> str:
    if not ecarts:
        return "aucune dérive de configuration"
    par_etat: dict[str, int] = {}
    for e in ecarts:
        par_etat[e.etat.value] = par_etat.get(e.etat.value, 0) + 1
    detail = ", ".join(f"{n} {etat}" for etat, n in sorted(par_etat.items()))
    noms = ", ".join(e.chemin for e in ecarts[:3])
    suite = "…" if len(ecarts) > 3 else ""
    return f"{len(ecarts)} fichier(s) de gouvernance ont bougé — {detail} : {noms}{suite}"


def enregistrer(base: LigneDeBase, chemin: str | os.PathLike[str]) -> None:
    p = Path(chemin)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(base.to_dict(), indent=1, ensure_ascii=False),
                 encoding="utf-8")


def relire(chemin: str | os.PathLike[str]) -> LigneDeBase | None:
    try:
        return LigneDeBase.from_dict(
            json.loads(Path(chemin).read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, TypeError):
        return None


__all__ = ["Ecart", "Etat", "GOUVERNANTS", "LigneDeBase", "TAILLE_MAX",
           "a_derive", "comparer", "enregistrer", "relever", "relire",
           "resume"]
