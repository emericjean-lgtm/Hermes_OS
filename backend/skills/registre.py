r"""Les competences de Hermes Agent, lues par Hermes OS (HOS-153).

## Ce qui manquait

L'agent porte 81 `SKILL.md` repartis en quinze domaines, sous
`%LOCALAPPDATA%\hermes\hermes-agent\skills`. Hermes OS n'en connaissait
**aucune** : aucune ligne du depot ne citait ce dossier. L'agent pouvait les
lister lui-meme — `skills_list` fait partie de son toolset ACP, mesure du
2026-08-23 : 30 outils dont les trois de competences — mais un modele
n'appelle pas un outil dont rien ne lui rappelle l'existence.

C'est la meme asymetrie que pour les outils, resolue au meme endroit : le
systeme d'exploitation connait ce que porte son cerveau, et le lui rappelle
au bon moment.

## Ce que ce module ne fait pas

Il ne charge pas le contenu des competences et ne le sert pas au modele. Le
corps d'un `SKILL.md` appartient a l'agent, qui sait le charger a la demande
par `skill_view` — le dupliquer ici creerait deux verites pour un meme
fichier, et celle de Hermes OS vieillirait.

Il ne lit que l'en-tete : un nom, une description, un domaine. De quoi
**nommer** ce qui existe. Le reste est le travail de l'agent.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

logger = logging.getLogger("hermes_os.skills")

#: La racine de l'agent. Le meme absolu que `hermes_agent_cli.py` : les deux
#: environnements Python sont separes a dessein (HOS-103) et `sys.executable`
#: ne mene pas la ou vit l'agent.
_RACINE_DEFAUT = Path(
    os.environ.get("LOCALAPPDATA", "")) / "hermes" / "hermes-agent"


@dataclass(frozen=True)
class Competence:
    """Ce qu'on retient d'un `SKILL.md` : de quoi le nommer, pas le servir."""

    nom: str
    description: str
    domaine: str

    def ligne(self) -> str:
        return f"{self.nom} — {self.description}" if self.description else self.nom


def racine_des_competences(racine_agent: Optional[str] = None) -> Path:
    base = Path(racine_agent) if racine_agent else _RACINE_DEFAUT
    return base / "skills"


def _entete(source: str) -> dict:
    """Le frontmatter YAML, lu sans dependre d'un parseur YAML.

    Volontairement primitif : on ne cherche que `name:` et `description:` au
    premier niveau. Un `SKILL.md` mal forme doit rendre une competence
    incomplete, jamais faire echouer la lecture des quatre-vingts autres.
    """
    if not source.startswith("---"):
        return {}
    fin = source.find("\n---", 3)
    if fin < 0:
        return {}
    champs: dict[str, str] = {}
    for ligne in source[3:fin].splitlines():
        if not ligne or ligne.startswith((" ", "\t", "#")):
            continue  # imbrique, commentaire : hors de ce qu'on lit
        cle, sep, valeur = ligne.partition(":")
        if not sep:
            continue
        cle = cle.strip()
        if cle in ("name", "description"):
            champs[cle] = valeur.strip().strip('"').strip("'")
    return champs


def lire(racine_agent: Optional[str] = None) -> list[Competence]:
    """Toutes les competences que porte l'agent, triees par domaine.

    Une lecture disque a chaque appel, et c'est delibere : l'agent peut
    creer une competence en cours de campagne (`skill_manage`), et un cache
    ferait mentir la liste au moment exact ou elle devient interessante.
    Mesure du 2026-08-23 : 81 fichiers en 35 ms a chaud, 1,1 s au premier
    appel — le cache disque de Windows fait la difference, pas le code.
    A l'echelle d'une section de mission, les deux sont negligeables.
    """
    base = racine_des_competences(racine_agent)
    if not base.is_dir():
        logger.debug("aucun dossier de competences sous %s", base)
        return []

    trouvees: list[Competence] = []
    for fichier in sorted(base.rglob("SKILL.md")):
        try:
            source = fichier.read_text(encoding="utf-8", errors="replace")
        except OSError:
            logger.debug("competence illisible : %s", fichier, exc_info=True)
            continue
        champs = _entete(source)
        relatif = fichier.relative_to(base).parts
        trouvees.append(Competence(
            nom=champs.get("name") or fichier.parent.name,
            description=champs.get("description", ""),
            # Le domaine est le premier dossier ; une competence posee a plat
            # n'en a pas, et « (racine) » le dit plutot que de l'inventer.
            domaine=relatif[0] if len(relatif) > 1 else "(racine)",
        ))
    return trouvees


def par_domaine(competences: Optional[Iterable[Competence]] = None,
                racine_agent: Optional[str] = None) -> dict[str, list[Competence]]:
    groupes: dict[str, list[Competence]] = {}
    for c in (competences if competences is not None else lire(racine_agent)):
        groupes.setdefault(c.domaine, []).append(c)
    return groupes


def rappel_pour_brief(racine_agent: Optional[str] = None,
                      plafond: int = 15) -> str:
    """Ce qu'on glisse dans un brief de section, ou "" s'il n'y a rien.

    Nomme les **domaines**, pas les 81 competences : une liste de quatre-
    vingts lignes dans un brief coute du contexte a chaque section et se
    fait ignorer. Nommer les domaines et rappeler l'outil qui les ouvre
    suffit a ce qu'un modele aille chercher, ce qu'il ne fait jamais de
    lui-meme.
    """
    groupes = par_domaine(racine_agent=racine_agent)
    if not groupes:
        return ""
    domaines = sorted(groupes)[:plafond]
    detail = ", ".join(f"{d} ({len(groupes[d])})" for d in domaines)
    return (
        f"\n\nCOMPETENCES DISPONIBLES — tu portes "
        f"{sum(len(v) for v in groupes.values())} competences deja ecrites, "
        f"reparties en : {detail}.\n"
        f"Avant d'improviser une methode, appelle `skills_list` puis "
        f"`skill_view` sur celle qui correspond. Si la tache que tu viens de "
        f"mener n'en avait aucune et meriterait d'en devenir une, propose-la "
        f"avec `skill_manage` — la proposition remonte a l'operateur."
    )
