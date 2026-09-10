r"""Ce que l'agent a fait de ses Skills, rattaché au Run qui l'a demandé
(G-33, HOS-281).

L'observateur — un plugin Hermes Agent, `integrations/hermes-agent/
observateur-skills/` — note chaque mutation de Skill dans son propre état,
sous `HERMES_HOME/plugin-data/`. Ce module la **lit**, et résout son
`client_turn_id` en Run par la relation que Hermes OS a lui-même
enregistrée (G-32).

    agent            plugin                     Hermes OS
    ─────            ──────                     ─────────
    mutation  ──→  fait + client_turn_id  ──→  run_du_tour(T) → run_id

## Trois lectures, un seul propriétaire

C'est la troisième fois que Hermes OS lit le disque de l'agent, et la
posture est la même qu'en HOS-274 (`registre.py`, les compétences) et
HOS-275 (`provenance.py`, leur origine) : **lire, jamais écrire, jamais
copier**. Le fait appartient au plugin, la relation `T → R` appartient au
bus de Hermes OS, et rien n'est recopié de l'un dans l'autre.

## Ce qui n'est pas rattaché, et le reste

Un fait sans `client_turn_id` — un tour hors Run, un agent non patché — a
`run` à `None`. Un `client_turn_id` que Hermes OS n'a pas frappé, ou dont
la relation a passé les sept jours de rétention du bus, aussi. Les trois
appellent la même conduite : ne rien associer. `rattache` les distingue de
l'absence de fait, jamais de l'affirmation.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("hermes_os.skills.observations")

#: Le nom du plugin, tel que son manifeste le déclare. Le dossier d'état
#: que l'agent lui donne en dérive (`agent-plugin-<nom>-<empreinte>`), et
#: l'empreinte n'est pas reproductible ici : on cherche par motif plutôt
#: que de la recalculer, ce qui coupleraient les deux implémentations.
NOM_DU_PLUGIN = "hermes-os-observateur-skills"

#: Le préfixe des clefs de fait, décidé par le plugin (HOS-279 : une clef
#: par fait, parce que `get` puis `set` perdait un fait sur deux quand deux
#: tours concurrents émettaient).
PREFIXE_FAIT = "fait-"


@dataclass(frozen=True)
class Observation:
    """Une mutation de Skill vue par l'agent, et le Run qui l'a demandée."""

    action: str
    skill: str
    provenance: str
    turn_id: str
    #: `None` quand rien ne rattache — jamais une supposition.
    run: Optional[str]
    observe_a: float

    @property
    def rattachee(self) -> bool:
        return self.run is not None


def _dossiers_d_etat() -> list[Path]:
    """Les `state.json` du plugin, s'il en a écrit."""
    from backend.skills.registre import racine_des_competences

    foyer = racine_des_competences().parent
    base = foyer / "plugin-data"
    if not base.is_dir():
        return []
    return sorted(p / "state.json" for p in base.iterdir()
                  if p.is_dir() and NOM_DU_PLUGIN in p.name
                  and (p / "state.json").exists())


def faits_bruts() -> list[dict[str, Any]]:
    """Les faits notés par l'observateur, du plus ancien au plus récent.

    Vide quand le plugin n'est pas installé, pas activé, ou n'a rien vu :
    trois situations qui se lisent pareil d'ici, et qui doivent toutes se
    lire « aucune observation », jamais « aucune mutation ».
    """
    faits: list[dict[str, Any]] = []
    for chemin in _dossiers_d_etat():
        try:
            etat = json.loads(chemin.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            logger.debug("etat du plugin illisible : %s", chemin, exc_info=True)
            continue
        if not isinstance(etat, dict):
            continue
        faits.extend(v for c, v in sorted(etat.items())
                     if c.startswith(PREFIXE_FAIT) and isinstance(v, dict))
    return faits


async def observations(limite: int = 200) -> list[Observation]:
    """Les mutations observées, chacune rattachée à son Run quand elle l'est.

    La résolution passe par `correlation.run_du_tour`, qui ne reconnaît que
    les étiquettes que Hermes OS a frappées. Une étiquette étrangère — un
    autre client ACP, un rejeu — n'est associée à rien.

    Les étiquettes sont résolues **une fois chacune** : un Run émet
    plusieurs tours, un tour plusieurs Skills, et rejouer le bus par fait
    coûterait le parcours autant de fois qu'il y a de mutations.
    """
    from backend.runs.correlation import run_du_tour

    bruts = faits_bruts()[-limite:]
    runs: dict[str, Optional[str]] = {}
    for fait in bruts:
        etiquette = str(fait.get("client_turn_id") or "")
        if etiquette and etiquette not in runs:
            runs[etiquette] = await run_du_tour(etiquette)

    return [Observation(
        action=str(fait.get("action") or ""),
        skill=str(fait.get("skill_name") or ""),
        provenance=str(fait.get("provenance") or ""),
        turn_id=str(fait.get("client_turn_id") or ""),
        run=runs.get(str(fait.get("client_turn_id") or "")),
        observe_a=float(fait.get("observe_a") or 0.0),
    ) for fait in bruts]


async def par_run(limite: int = 200) -> dict[str, list[Observation]]:
    """Les observations rattachées, groupées par Run.

    Les non rattachées sont **écartées** plutôt que rangées sous une clef
    « inconnu » : une telle clef se lirait comme un Run et finirait
    affichée à côté des vrais.
    """
    groupes: dict[str, list[Observation]] = {}
    for o in await observations(limite):
        if o.run:
            groupes.setdefault(o.run, []).append(o)
    return groupes
