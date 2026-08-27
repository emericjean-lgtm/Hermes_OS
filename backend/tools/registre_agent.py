"""Les outils que Hermes Agent peut réellement appeler (HOS-187).

## L'asymétrie, pour la seconde fois

HOS-153 avait réglé la même chose pour les compétences : l'agent portait
quatre-vingt-une `SKILL.md` et Hermes OS n'en connaissait aucune. La
réponse fut `/skills/agent`, qui lit ce que porte le cerveau et le nomme.

Les outils avaient le défaut inverse et plus trompeur. Le Tools Center
listait seize entrées d'un registre dont **aucune n'a d'exécuteur** :
`POST /tools/execute` rend `No executor registered for tool` pour les
seize, `register_executor()` est défini et appelé nulle part. Pendant ce
temps, le serveur MCP expose soixante et onze fonctions que l'agent
appelle vraiment, et aucun écran ne les montrait.

Ce n'était donc pas une panne mais une confusion de surfaces : l'écran
décrivait un catalogue que personne n'emprunte.

## Ce que ce module fait, et ce qu'il refuse

Il lit `_ALL_TOOLS` — la liste que `create_mcp_server()` enregistre
réellement — et en tire un nom, une famille et la première phrase de la
docstring. Rien d'autre : le corps d'un outil appartient au serveur MCP.

Il ne compte pas les fonctions du module, il compte celles qui sont
**enregistrées**. Un outil écrit mais absent de `_ALL_TOOLS` n'est pas
appelable, et le faire figurer ici recréerait exactement le mensonge que
ce module existe pour défaire.
"""

from __future__ import annotations

import inspect
import logging
from typing import Any

logger = logging.getLogger("hermes_os.tools.registre_agent")

#: Le premier segment du nom donne la famille — `files_read` → `files`.
#: Les noms sans préfixe forment leur propre famille plutôt que d'atterrir
#: dans un fourre-tout : `research_query` est seul de son espèce, et le
#: dire vaut mieux que de l'appeler « divers ».
def _famille(nom: str) -> str:
    tete = nom.split("_", 1)[0]
    return tete or nom


def _resume(fn: Any) -> str:
    """La première phrase de la docstring, ou rien.

    Rien, et non le nom de la fonction reformaté : une description
    fabriquée depuis le nom n'apprend au lecteur que ce qu'il voit déjà.
    """
    doc = inspect.getdoc(fn) or ""
    if not doc:
        return ""
    premiere = doc.strip().split("\n\n")[0].replace("\n", " ").strip()
    point = premiere.find(". ")
    if point > 40:
        premiere = premiere[: point + 1]
    return premiere[:240]


def outils_de_lagent() -> list[dict[str, str]]:
    """Un objet par outil réellement enregistré auprès du serveur MCP."""
    try:
        from backend.mcp_server.server import _ALL_TOOLS
    except Exception:  # pragma: no cover - serveur MCP indisponible
        logger.debug("serveur MCP indisponible", exc_info=True)
        return []

    outils = []
    for fn in _ALL_TOOLS:
        nom = getattr(fn, "__name__", "")
        if not nom:
            continue
        outils.append({
            "nom": nom,
            "famille": _famille(nom),
            "resume": _resume(fn),
        })
    return sorted(outils, key=lambda o: (o["famille"], o["nom"]))


def rapport() -> dict[str, Any]:
    """Ce que sert `GET /tools/agent`.

    Groupé par famille parce que soixante et onze lignes à plat ne se
    lisent pas, et que la famille est l'information qui répond à la vraie
    question : *de quoi cet agent est-il capable* — de fichiers, de git,
    de mémoire.
    """
    outils = outils_de_lagent()
    familles: dict[str, list[dict[str, str]]] = {}
    for o in outils:
        familles.setdefault(o["famille"], []).append(
            {"nom": o["nom"], "resume": o["resume"]}
        )

    return {
        "total": len(outils),
        "familles": [
            {"nom": nom, "total": len(membres), "outils": membres}
            for nom, membres in sorted(
                familles.items(), key=lambda kv: (-len(kv[1]), kv[0])
            )
        ],
    }
