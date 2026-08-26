"""Un topic publié doit être un topic autorisé (HOS-181).

`event_wiring.collect_known_topics()` porte depuis HOS-066B un commentaire
affirmant que la liste blanche « ne peut plus dériver de ses producteurs ».
Elle avait de nouveau dérivé, et plus largement qu'avant : **35 topics** que
du code réel publiait étaient jetés en silence, dont la totalité de
`filesystem.*` et la totalité de `execution.*`.

Conséquence concrète : le Cockpit ne pouvait voir ni une écriture sur disque,
ni une mission démarrer. Une interface branchée sur ce flux serait restée
muette pendant qu'une mission tournait — c'est-à-dire aurait affirmé que rien
ne se passait, ce que ce projet interdit de croire sur parole dans les deux
sens.

Le commentaire ne suffisait donc pas : il décrivait une intention, pas une
vérification. Ce test est la vérification. Il lit l'arbre syntaxique du
backend, relève tout littéral pointé passé en premier argument à une
publication, et exige qu'il soit dans la liste blanche.

Ajouter un topic sans le déclarer fait échouer ce test avec le nom du topic
et le fichier qui le publie ; la réparation consiste à l'ajouter au catalogue
de son module, pas à élargir l'exception ci-dessous.
"""

from __future__ import annotations

import ast
import io
import os

from backend.core.bootstrap.event_wiring import collect_known_topics

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Les fonctions par lesquelles un événement part réellement. `dispatch` et
# `emettre` sont incluses parce que deux modules publient sous ces noms.
PUBLICATIONS = {"publish", "_publish", "emit", "publish_event", "dispatch", "emettre"}

# Les tests publient délibérément des topics inventés pour éprouver le rejet.
DOSSIERS_IGNORES = {"__pycache__", "tests", ".venv", "node_modules"}


def _litteraux(noeud: ast.expr) -> list[str]:
    """Les chaînes qu'un premier argument peut valoir.

    Pas seulement une constante : `file_tools` publie
    ``"filesystem.write" if verified else "filesystem.verification_failed"``,
    et un scan qui ne lirait que les constantes manquerait la moitié des
    topics de ce module — c'est ainsi que six d'entre eux étaient passés
    inaperçus au premier relevé.
    """
    if isinstance(noeud, ast.Constant) and isinstance(noeud.value, str):
        return [noeud.value]
    if isinstance(noeud, ast.IfExp):
        return _litteraux(noeud.body) + _litteraux(noeud.orelse)
    return []


def _topics_publies() -> dict[str, set[str]]:
    """topic -> fichiers qui le publient."""
    trouves: dict[str, set[str]] = {}
    for dossier, sous, fichiers in os.walk(RACINE):
        sous[:] = [d for d in sous if d not in DOSSIERS_IGNORES]
        for f in fichiers:
            if not f.endswith(".py"):
                continue
            chemin = os.path.join(dossier, f)
            try:
                arbre = ast.parse(io.open(chemin, encoding="utf-8", errors="replace").read())
            except SyntaxError:  # pragma: no cover - fichier en cours d'édition
                continue
            for n in ast.walk(arbre):
                if not isinstance(n, ast.Call) or not n.args:
                    continue
                nom = n.func.attr if isinstance(n.func, ast.Attribute) else getattr(n.func, "id", "")
                if nom not in PUBLICATIONS:
                    continue
                for valeur in _litteraux(n.args[0]):
                    if "." in valeur:
                        trouves.setdefault(valeur, set()).add(os.path.relpath(chemin, RACINE))
    return trouves


def test_aucun_topic_publie_nest_jete_par_la_liste_blanche():
    autorises = collect_known_topics()
    publies = _topics_publies()

    manquants = {t: f for t, f in publies.items() if t not in autorises}

    if manquants:
        lignes = [
            f"  {t}  <- {sorted(fichiers)[0]}"
            for t, fichiers in sorted(manquants.items())
        ]
        raise AssertionError(
            f"{len(manquants)} topic(s) publiés mais absents de la liste blanche.\n"
            "Ils seront jetés par l'EventHub sans qu'aucune trace ne le dise, et "
            "toute vue branchée dessus restera muette :\n"
            + "\n".join(lignes)
            + "\n\nDéclarez-les dans le catalogue de leur module (un dict "
            "`<DOMAINE>_EVENTS`) puis enregistrez ce catalogue dans "
            "`collect_known_topics()`."
        )


def test_le_scan_voit_bien_les_topics_en_expression_conditionnelle():
    """Le scan lui-même doit être digne de foi.

    Six topics de `file_tools` sont publiés par un ternaire. Un scan qui ne
    lirait que les constantes rendrait le test précédent vert en ne regardant
    pas là où était le défaut — le pire des deux mondes.
    """
    publies = _topics_publies()
    assert "filesystem.verification_failed" in publies, (
        "le scan ne voit plus les topics publiés par une expression "
        "conditionnelle : il ne prouve donc plus rien sur file_tools"
    )
    assert "filesystem.write" in publies


def test_les_catalogues_declares_sont_tous_lus():
    """Un catalogue déclaré mais non enregistré ne sert à rien.

    C'est le mode d'échec suivant : on ajoute le dict au module producteur et
    on oublie la ligne dans `collect_known_topics()`. Le topic reste jeté, et
    le catalogue donne l'illusion contraire.
    """
    autorises = collect_known_topics()
    temoins = {
        "backend.tools.file_tools": "FILESYSTEM_EVENTS",
        "backend.execution.mission_executor": "EXECUTION_EVENTS",
        "backend.projects.project_manager": "PROJECT_EVENTS",
        "backend.integrations.alexandrie.hermes_alexandrie_adapter": "ALEXANDRIE_EVENTS",
        "backend.runtime.ktransformers.integrations.resources": "KT_EVENTS",
        "backend.security.approvals": "APPROVAL_EVENTS",
        "backend.agents.kronos": "KRONOS_EVENTS",
        "backend.api.routes.chat": "CHAT_EVENTS",
    }
    for chemin, attribut in temoins.items():
        module = __import__(chemin, fromlist=[attribut])
        catalogue = getattr(module, attribut)
        assert isinstance(catalogue, dict) and catalogue, f"{chemin}.{attribut} vide"
        absents = [v for v in catalogue.values() if v not in autorises]
        assert not absents, (
            f"{attribut} est déclaré dans {chemin} mais {absents} n'arrive pas "
            "dans la liste blanche — la ligne manque dans collect_known_topics()"
        )
