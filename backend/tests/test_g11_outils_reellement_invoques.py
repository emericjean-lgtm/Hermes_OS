"""G-11 : `assigned_tools` planifié, jamais invoqué (HOS-069, §7).

Le constat d'origine (`task_executor.py:31`) : `AgentCoordinator._select_tools`
recommande des outils par correspondance de mots-clés contre le catalogue de
plugins MCP (klaatcode/oh_my_pi) — un espace de noms disjoint des deux seuls
chemins d'exécution réels (Hermes Agent choisit ses propres outils par son
propre MCP ; la boucle locale de Hermes OS n'offre qu'un jeu fixe
`workspace_*`/`verification_*`). Rien n'invoque jamais cette recommandation.

Ce que rien ne disait avant cette passe : ce même champ, jamais invoqué,
atteignait quand même l'opérateur. `MissionExecutor.execute_task` le
renvoyait sous la clé `"tools"` aux côtés de `"agent"`/`"runtime"`/`"model"`
— trois champs qui rapportent, eux, ce qui a réellement servi — et
`finalize()` l'agrégeait dans `ExecutionReport.tools_used`, un champ nommé
« used » et alimenté par une recommandation jamais exécutée. Ce rapport est
le producteur documenté de `FeedbackLoop.get_memory_input`/
`get_intelligence_input` (Memory, Knowledge Graph, Runtime Intelligence).

Deux voies étaient possibles pour fermer G-11 : invoquer réellement la
recommandation, ou arrêter de la faire passer pour une mesure. La première
est fermée par construction : le faire sur le chemin hermes-agent violerait
la règle HOS-085 (Hermes OS ne choisit pas les outils du cerveau) ; le faire
sur le chemin local exigerait un second pont d'outils vers un catalogue que
ce chemin ne peut de toute façon pas exécuter — une architecture nouvelle et
disproportionnée pour une dette classée « technical debt », pas
« architectural ». La seconde est le changement minimal : `_run_tool_loop`
capture déjà `tool_calls_made` (un compte réel) ; il capture désormais aussi
les noms réellement appelés (`tools_invoked`), et `MissionExecutor` les
rapporte sous `TaskExecution.tools_used` / `ExecutionReport.tools_used` à la
place de la recommandation du coordinateur.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.config.config_models import DatabaseConfig
from backend.execution.execution_models import ExecutionMeta, TaskExecution
from backend.execution.mission_executor import MissionExecutor
from backend.execution.task_executor import RealTaskExecutor, TaskExecutionOutcome
from backend.runs.registre import Registre
from backend.storage.database_manager import DatabaseManager

from backend.tests.test_real_task_executor import (
    _FakeOllamaClientForToolLoop,
    _FakeTask,
    _ScriptedStreamChunk,
)


# ═══ Niveau MissionExecutor : le rapport ne recopie plus la recommandation ═

class _ExecuteurScripte:
    """Rend un outcome dont les métadonnées portent ce qui a *réellement*
    été invoqué — délibérément différent de ce que le coordinateur va
    recommander, pour que toute confusion entre les deux se voie."""

    def __init__(self, tools_invoked: list[str] | None) -> None:
        self._tools_invoked = tools_invoked

    def execute(self, task, assignment=None, **_):
        metadata = {"provider": "ollama"}
        if self._tools_invoked is not None:
            metadata["tools_invoked"] = self._tools_invoked
        return TaskExecutionOutcome(
            result="fait", runtime_id="ollama", model="qwen3.6-35b-a3b",
            duration_ms=12.0, metadata=metadata,
        )


@pytest.fixture
def registre(tmp_path: Path) -> Registre:
    return Registre(DatabaseManager(DatabaseConfig(name=str(tmp_path / "runs"))))


def _preparer(registre, executeur, *, titre: str) -> tuple[MissionExecutor, object]:
    moteur = MissionExecutor(task_executor=executeur, registre=registre)
    # Un outil enregistré dont le nom recoupe le titre de la tâche : c'est
    # ce que `_select_tools` va recommander — jamais ce que l'exécuteur
    # rapporte avoir réellement appelé.
    moteur._coordinator.register_tool(  # noqa: SLF001 - accès direct au double de test
        "web_search_plugin", {"category": "recherche"})
    meta = ExecutionMeta(mission_id="lune", user_goal="produire la vidéo",
                         max_retries_per_task=0)
    sm = moteur.prepare(meta, [TaskExecution(task_id="t1", title=titre,
                                             mission_id="lune")])
    moteur.run_de(meta.execution_id)
    return moteur, sm


def test_le_rapport_de_tache_montre_les_outils_reellement_invoques(registre):
    """Cas nominal : le rapport par tâche porte ce qui a tourné, pas ce
    que le coordinateur a recommandé."""
    moteur, sm = _preparer(
        registre, _ExecuteurScripte(["workspace_read"]), titre="web search docs")

    rapport_tache = moteur.execute_task(sm, "t1")

    assert rapport_tache["tools"] == ["workspace_read"]
    assert "web_search_plugin" not in rapport_tache["tools"]


def test_le_rapport_final_agrege_les_outils_reellement_invoques(registre):
    """Même mesure au niveau mission : `ExecutionReport.tools_used`
    n'est plus rempli par `assigned_tools`."""
    moteur, sm = _preparer(
        registre, _ExecuteurScripte(["workspace_read"]), titre="web search docs")
    moteur.execute_task(sm, "t1")

    rapport = moteur.finalize(sm)

    assert rapport.tools_used == ["workspace_read"]
    assert "web_search_plugin" not in rapport.tools_used


def test_assigned_tools_et_tools_used_restent_deux_champs_distincts(registre):
    """Garde de non-régression : si `tools_used` était de nouveau alimenté
    par `assigned_tools`, ce test échouerait — les deux listes sont
    délibérément différentes ici."""
    moteur, sm = _preparer(
        registre, _ExecuteurScripte(["workspace_read"]), titre="web search docs")
    moteur.execute_task(sm, "t1")

    task = moteur._scheduler.get_task("t1")  # noqa: SLF001 - lecture directe pour la mesure

    assert task.assigned_tools == ["web_search_plugin"]
    assert task.tools_used == ["workspace_read"]
    assert task.assigned_tools != task.tools_used


def test_aucune_metadonnee_d_outils_ne_fabrique_une_liste(registre):
    """Cas limite : quand l'exécuteur ne rapporte rien (le chemin
    hermes-agent, où Hermes OS n'observe pas ce que le cerveau a appelé),
    le rapport reste honnêtement vide — jamais repêché depuis
    `assigned_tools`, ce qui reproduirait exactement G-11."""
    moteur, sm = _preparer(
        registre, _ExecuteurScripte(None), titre="web search docs")

    rapport_tache = moteur.execute_task(sm, "t1")
    rapport = moteur.finalize(sm)

    assert rapport_tache["tools"] == []
    assert rapport.tools_used == []


# ═══ Niveau RealTaskExecutor : la boucle locale capture les noms réels ═══

@pytest.mark.asyncio
async def test_la_boucle_d_outils_locale_rapporte_les_noms_reels_appeles(
    monkeypatch, tmp_path,
):
    """`_run_tool_loop` (le seul chemin où Hermes OS possède réellement sa
    propre boucle — HOS-085) doit dire quels outils il a appelés, pas
    combien seulement : `tool_calls_made` existait déjà, `tools_invoked`
    est ce que G-11 ajoute pour que `MissionExecutor` ait quelque chose de
    vrai à rapporter."""
    from backend.core.agent_registry import get_agent_registry
    from backend.core.config import get_settings
    from backend.projects.store import get_project_store

    get_agent_registry()

    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("ALLOWED_PATHS", str(tmp_path / "_unrelated"))
    (tmp_path / "_unrelated").mkdir()
    get_settings.cache_clear()
    get_project_store.cache_clear()

    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "AGENTS.md").write_text("Real agent instructions.")
    project = get_project_store().create(name="ws", root_path=str(workspace))
    get_project_store().validate(project.id)

    _FakeOllamaClientForToolLoop.instances.clear()
    monkeypatch.setattr(
        "backend.connectors.ollama_client.OllamaClient", _FakeOllamaClientForToolLoop,
    )

    executor = RealTaskExecutor(
        workspace_project_for=lambda task: (project.id, str(workspace)),
    )
    outcome = executor.execute(_FakeTask(mission_id="m-1", assigned_runtime="ollama"))

    assert outcome.metadata.get("tools_invoked") == ["workspace_read"]

    get_settings.cache_clear()
    get_project_store.cache_clear()


@pytest.mark.asyncio
async def test_un_outil_appele_deux_fois_ne_compte_qu_une_fois_dans_les_noms(
    monkeypatch, tmp_path,
):
    """`tools_invoked` liste des outils, pas des appels : un `workspace_exists`
    répété deux fois avant la lecture doit apparaître une seule fois, tandis
    que `tool_calls_made` — un compte, pas un ensemble — continue de
    refléter les trois appels réels."""
    from backend.core.agent_registry import get_agent_registry
    from backend.core.config import get_settings
    from backend.projects.store import get_project_store

    get_agent_registry()

    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("ALLOWED_PATHS", str(tmp_path / "_unrelated"))
    (tmp_path / "_unrelated").mkdir()
    get_settings.cache_clear()
    get_project_store.cache_clear()

    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "AGENTS.md").write_text("Real agent instructions.")
    project = get_project_store().create(name="ws", root_path=str(workspace))
    get_project_store().validate(project.id)

    class _ClientDeuxOutils:
        instances: list = []

        def __init__(self, *a, **kw):
            self.round = 0
            _ClientDeuxOutils.instances.append(self)

        def chat_events(self, model, messages, **kwargs):
            self.round += 1
            current = self.round

            async def _gen():
                if current == 1:
                    yield _ScriptedStreamChunk(
                        "tool_calls", tool_calls=[
                            {"function": {"name": "workspace_exists", "arguments": {"path": "AGENTS.md"}}},
                        ],
                    )
                elif current == 2:
                    yield _ScriptedStreamChunk(
                        "tool_calls", tool_calls=[
                            {"function": {"name": "workspace_exists", "arguments": {"path": "AGENTS.md"}}},
                        ],
                    )
                elif current == 3:
                    yield _ScriptedStreamChunk(
                        "tool_calls", tool_calls=[
                            {"function": {"name": "workspace_read", "arguments": {"path": "AGENTS.md"}}},
                        ],
                    )
                else:
                    yield _ScriptedStreamChunk("content", text="done")
            return _gen()

        async def aclose(self):
            pass

    monkeypatch.setattr(
        "backend.connectors.ollama_client.OllamaClient", _ClientDeuxOutils,
    )

    executor = RealTaskExecutor(
        workspace_project_for=lambda task: (project.id, str(workspace)),
    )
    outcome = executor.execute(_FakeTask(mission_id="m-2", assigned_runtime="ollama"))

    assert outcome.metadata.get("tools_invoked") == ["workspace_exists", "workspace_read"]
    assert outcome.metadata.get("tool_calls_made") == 3

    get_settings.cache_clear()
    get_project_store.cache_clear()
