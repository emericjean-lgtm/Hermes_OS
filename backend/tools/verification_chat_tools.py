"""Lancer lint / build / tests depuis une conversation (HOS-115).

Le besoin est banal — « lance les tests quand tu as fini » — et il a
longtemps ressemblé à une demande de shell. Ce n'en est pas une, et la
distinction est la raison d'être de ce module.

## Un runner nommé, jamais une commande

`config/verification.yaml` est une liste blanche, et son en-tête pose deux
règles : aucune entrée ne prend d'argument fourni par l'appelant, et
aucune n'invoque un shell ou un interpréteur sur du texte fourni par
l'appelant. Le modèle **nomme** un runner ; il ne peut ni en composer un,
ni lui passer quoi que ce soit. Élargir ce que le système sait exécuter
demande d'ajouter une entrée à ce fichier — un acte délibéré et relu.

C'est pour cela que `verification_run` est une catégorie Aegis distincte
de `system_command` : la commande ne vient pas de l'appelant.

## Ce que ce module ne masque pas

Exécuter un runner exécute le code du projet cible — conftest, scripts de
build, corps de tests. La catégorie est donc `mutating` et confinée à
`ALLOWED_PATHS`, et au niveau d'autonomie livré elle demande une
validation humaine. Un refus se rapporte comme un refus, jamais comme un
échec de test : « personne n'a approuvé » et « les tests ont échoué »
n'appellent pas la même suite.
"""
from __future__ import annotations

from typing import Any


def verification_tool_schemas() -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": "verification_runners",
                "description": (
                    "List the lint, build, typecheck and test runners you are "
                    "allowed to execute. This is a fixed whitelist — you can name "
                    "one of these and nothing else, and you cannot pass a command "
                    "or an argument. Call this before verification_run if you do "
                    "not already know which runners this project has."
                ),
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "verification_run",
                "description": (
                    "Run ONE runner from verification_runners in the active "
                    "workspace and report whether it passed. Use this to actually "
                    "check work instead of assuming it is correct. Note: a run may "
                    "come back ran=false with verdict=require_human_validation — "
                    "that means nobody approved it yet, which is NOT a test "
                    "failure. A genuine failure is ran=true with passed=false."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "runner": {
                            "type": "string",
                            "description": "Runner name, exactly as given by verification_runners.",
                        },
                    },
                    "required": ["runner"],
                },
            },
        },
    ]


def _aegis():
    from backend.core.agent_registry import get_agent_registry
    return get_agent_registry().get("aegis")


async def execute_verification_tool(
    name: str, arguments: dict[str, Any], *, project_id: str, project_root: str
) -> str:
    """Adaptateur mince sur `backend/tools/verification.py`.

    `repo_path` est le workspace actif, **jamais** un chemin fourni par le
    modèle : le runner s'exécute là où la conversation est liée, et nulle
    part ailleurs. Laisser le modèle nommer le répertoire aurait rendu la
    liste blanche décorative — on ne peut pas composer la commande, mais on
    la lancerait où l'on veut.
    """
    from backend.tools import verification

    if name == "verification_runners":
        runners = verification.list_runners()
        if not runners:
            return "Aucun runner déclaré pour ce projet."
        return "\n".join(f"{r.name} ({r.kind}) — {r.description}" for r in runners)

    if name == "verification_run":
        nom_runner = str(arguments.get("runner", "")).strip()
        if not nom_runner:
            return "Aucun runner nommé — rien n'a été lancé."
        result = verification.run(
            _aegis(), project_root, nom_runner, project_id=project_id
        )
        if not result.ran:
            return (
                f"Non exécuté ({result.verdict}) : {result.reason}. "
                "Ce n'est pas un échec des tests — personne ne les a encore "
                "autorisés."
            )
        etat = "réussi" if result.passed else "échoué"
        sortie = (result.output or "").strip()
        if len(sortie) > 4000:
            sortie = sortie[-4000:]
        expire = " (délai dépassé)" if result.timed_out else ""
        return (
            f"{result.runner} ({result.kind}) a {etat}{expire} — code {result.exit_code}, "
            f"{result.duration_seconds:.1f}s\n\n{sortie}"
        )

    return f"Unknown tool {name!r} — nothing executed."
