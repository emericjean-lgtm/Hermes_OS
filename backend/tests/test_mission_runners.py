"""Une mission peut lancer les tests du projet (HOS-116).

Elle savait écrire un fichier et ne savait pas vérifier qu'il marchait :
son meilleur rapport possible était « j'ai écrit », jamais « j'ai écrit et
ça passe ». C'est exactement la distinction que `MissionVerification`
cherche à établir, et dont la boucle de reprise (HOS-099/100) dépend —
une vérification qui échoue déclenche une seconde tentative, encore
faut-il pouvoir échouer sur autre chose que l'absence d'artefact.

Le chemin concerné est celui du runtime Ollama explicite. Hermes Agent
reste le cerveau des missions et apporte ses propres outils ; ce n'est pas
lui qu'on outille ici.
"""
from __future__ import annotations

import pytest

from backend.execution.task_executor import RealTaskExecutor


class _Client:
    """Un faux OllamaClient : le modèle demande un outil, puis conclut."""

    def __init__(self, appels: list[dict]):
        self._appels = appels
        self.tools_vus: list[list[dict]] = []
        self._tour = 0

    async def chat_events(self, model, messages, tools=None, **kwargs):
        self.tools_vus.append(list(tools or []))
        self._tour += 1
        if self._tour == 1 and self._appels:
            yield _Chunk("tool_calls", tool_calls=self._appels)
        else:
            yield _Chunk("content", text="terminé")


class _Chunk:
    def __init__(self, kind, text="", tool_calls=None):
        self.kind = kind
        self.text = text
        self.tool_calls = tool_calls


@pytest.fixture
def executeur(monkeypatch):
    ex = RealTaskExecutor()
    return ex


def _appel(nom: str, arguments: dict | None = None) -> dict:
    return {"function": {"name": nom, "arguments": arguments or {}}}


class TestLesOutilsOfferts:
    @pytest.mark.asyncio
    async def test_une_tache_voit_les_fichiers_et_les_runners(self, executeur, monkeypatch):
        client = _Client([])
        monkeypatch.setattr(
            "backend.connectors.ollama_client.OllamaClient", lambda *a, **k: client)

        await executeur._run_tool_loop(  # noqa: SLF001
            [{"role": "user", "content": "salut"}], "m", 8192, "p", "C:/ws")

        noms = {t["function"]["name"] for t in client.tools_vus[0]}
        assert "workspace_write" in noms
        assert "verification_run" in noms
        assert "verification_runners" in noms

    @pytest.mark.asyncio
    async def test_le_renommage_est_offert_lui_aussi(self, executeur, monkeypatch):
        """Hérité de HOS-115 : l'exécuteur partage `workspace_tool_schemas`
        avec le chat, donc les missions ont gagné les huit opérations
        manquantes sans une ligne de plus."""
        client = _Client([])
        monkeypatch.setattr(
            "backend.connectors.ollama_client.OllamaClient", lambda *a, **k: client)

        await executeur._run_tool_loop(  # noqa: SLF001
            [{"role": "user", "content": "salut"}], "m", 8192, "p", "C:/ws")

        noms = {t["function"]["name"] for t in client.tools_vus[0]}
        assert {"workspace_move", "workspace_delete", "workspace_search"} <= noms


class TestLeBonExecuteur:
    @pytest.mark.asyncio
    async def test_un_appel_verification_va_au_module_verification(
        self, executeur, monkeypatch
    ):
        """Sans l'aiguillage par préfixe, tout partait vers l'exécuteur de
        fichiers, qui aurait répondu « Unknown tool » — un outil offert au
        modèle et impossible à utiliser."""
        client = _Client([_appel("verification_runners")])
        monkeypatch.setattr(
            "backend.connectors.ollama_client.OllamaClient", lambda *a, **k: client)

        recus: list[str] = []

        async def _faux(nom, args, *, project_id, project_root):
            recus.append(nom)
            return "pytest (test) — la suite Python"

        monkeypatch.setattr(
            "backend.tools.verification_chat_tools.execute_verification_tool", _faux)

        await executeur._run_tool_loop(  # noqa: SLF001
            [{"role": "user", "content": "lance les tests"}], "m", 8192, "p", "C:/ws")

        assert recus == ["verification_runners"]

    @pytest.mark.asyncio
    async def test_un_appel_workspace_va_toujours_a_l_executeur_de_fichiers(
        self, executeur, monkeypatch
    ):
        client = _Client([_appel("workspace_read", {"path": "a.txt"})])
        monkeypatch.setattr(
            "backend.connectors.ollama_client.OllamaClient", lambda *a, **k: client)

        recus: list[str] = []

        async def _faux(nom, args, *, project_id, project_root):
            recus.append(nom)
            return "contenu"

        monkeypatch.setattr(
            "backend.tools.workspace_chat_tools.execute_workspace_tool", _faux)

        await executeur._run_tool_loop(  # noqa: SLF001
            [{"role": "user", "content": "lis"}], "m", 8192, "p", "C:/ws")

        assert recus == ["workspace_read"]
