"""memory_remember -> memory_search must actually find it (HOS-086).

Reported symptom: ``memory_remember`` returned an id and ``memory_search``
returned ``[]`` for the very same text, every time. Root cause was not a
retrieval-quality problem — the two MCP tools addressed different stores.
``memory_remember`` wrote a ``MemoryEntry`` row through
``episodic.add_memory``; ``memory_search`` called ``EchoAgent.recall``,
which queries the *document* vector index. Nothing ever wrote a remembered
fact into that index, so the search could not have succeeded.

These tests assert the round trip a caller actually expects, and the
cross-session survival that makes it memory rather than a cache. An id in
the ``memory_remember`` response is explicitly not accepted as evidence.
"""
from __future__ import annotations

import pytest


@pytest.fixture
def echo(monkeypatch, tmp_path):
    from backend.core.agent_registry import get_agent_registry
    from backend.core.config import get_settings

    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "memory.db"))
    get_settings.cache_clear()
    get_agent_registry.cache_clear()
    agent = get_agent_registry().get("echo")
    yield agent
    get_settings.cache_clear()
    get_agent_registry.cache_clear()


def test_remembered_fact_is_findable(echo):
    echo.remember(
        type_="fact",
        content="The Hermes OS backend listens on port 8010.",
        tags=["deployment"],
    )

    hits = echo.search_memories("port 8010")

    assert hits, "a fact stored seconds ago was not retrievable"
    assert "8010" in hits[0]["content"]
    assert hits[0]["source"] == "memory"


def test_search_is_scoped_by_project(echo):
    echo.remember(type_="fact", content="Alpha uses PostgreSQL.", project_id="proj-a")
    echo.remember(type_="fact", content="Beta uses SQLite.", project_id="proj-b")

    hits = echo.search_memories("uses", project_id="proj-a")

    assert len(hits) == 1
    assert "Alpha" in hits[0]["content"]


def test_best_match_ranks_first(echo):
    echo.remember(type_="fact", content="Ollama serves models locally.")
    echo.remember(type_="fact", content="The agentic model floor is devstral.")

    hits = echo.search_memories("agentic model floor")

    assert "devstral" in hits[0]["content"], "incidental one-word overlap outranked the real match"


def test_memory_survives_a_restart(monkeypatch, tmp_path):
    """Session A remembers, the process-wide registry is torn down, session B
    finds it. A store that only answers within one session is a cache."""
    from backend.core.agent_registry import get_agent_registry
    from backend.core.config import get_settings

    db = tmp_path / "persist.db"
    monkeypatch.setenv("SQLITE_PATH", str(db))

    get_settings.cache_clear()
    get_agent_registry.cache_clear()
    get_agent_registry().get("echo").remember(
        type_="fact", content="Skill360 workspace lives under C:/Users/emeri.",
    )

    # Session B — nothing of session A survives except the database itself.
    get_settings.cache_clear()
    get_agent_registry.cache_clear()

    hits = get_agent_registry().get("echo").search_memories("Skill360 workspace")

    assert hits, "memory did not survive the restart"
    assert "Skill360" in hits[0]["content"]

    get_settings.cache_clear()
    get_agent_registry.cache_clear()


def _tomber_l_index_documentaire(echo, monkeypatch):
    """Ollama à terre : `recall` lève, comme dans l'incident HOS-086."""
    monkeypatch.setattr(
        type(echo), "recall",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("embeddings unavailable")),
    )


def _provenance(echo, memory_id):
    """L'état de quarantaine tel que la base le porte, relu."""
    from backend.memory.confiance import provenance_de

    entree = next(e for e in echo.list_memories() if e.id == memory_id)
    return entree, provenance_de(entree)


def test_memory_search_answers_without_the_document_index(echo, monkeypatch):
    """Un index documentaire tombé ne vide pas la réponse (HOS-086) — et
    ce qui rend une mémoire visible est son **origine**, rien d'autre.

    L'incident d'origine tient : `memory_search` interroge deux magasins
    indépendants, et la panne de l'un ne doit pas faire disparaître ce que
    l'autre sait. Seule la **prémisse** a changé avec T-16 : le test
    écrivait sans provenance — donc `INCONNUE`, donc en quarantaine — et
    aurait été rendu vert en redonnant à l'agent une mémoire qu'il ne doit
    plus voir.

    Les deux écritures se font ici dans la même seconde, par les deux
    chemins réels, et une seule revient. La différence entre elles n'est
    ni le contenu, ni la fraîcheur, ni la confiance déclarée : c'est le
    chemin qui les a écrites.
    """
    from backend.mcp_server import server
    from backend.memory.confiance import Origine

    # Le chemin humain — celui de `POST /memory`, qui pose `HUMAIN`.
    humaine = echo.remember(
        type_="fact", content="The agentic fallback model is devstral.",
        origine=Origine.HUMAIN,
    )
    monkeypatch.setattr(server, "_echo", lambda: echo)

    # Le chemin de l'agent — le vrai outil MCP, qui pose `AGENT` lui-même.
    # Avec tout ce qu'un modèle pourrait tenter pour se déclarer fiable.
    agent = server.memory_remember(
        type="fact", content="The agentic fallback model is trust-me-9b.",
        tags=["verified", "trusted", "human-approved"], confidence=1.0,
    )

    _tomber_l_index_documentaire(echo, monkeypatch)
    hits = server.memory_search("agentic fallback")
    contenus = [h["content"] for h in hits]

    # 1. L'incident d'origine, intact : l'index est tombé, la réponse tient.
    assert hits, "memory_search n'a rien rendu parce que l'index documentaire est tombé"
    assert "devstral" in contenus[0]
    assert hits[0]["source"] == "memory"

    # 2. Et l'écriture de l'agent n'en fait pas partie.
    assert "The agentic fallback model is trust-me-9b." not in contenus

    # 3. Le mécanisme, pas le symptôme : les deux sont **persistées**, la
    #    lecture système les voit toutes les deux, et ce qui les sépare est
    #    la provenance relue en base.
    entree_h, prov_h = _provenance(echo, humaine.id)
    entree_a, prov_a = _provenance(echo, agent["id"])
    assert (entree_h.origine, prov_h.en_quarantaine) == ("humain", False)
    assert (entree_a.origine, prov_a.en_quarantaine) == ("agent", True)

    # 4. Ni la confiance à 1.0 ni les tags rassurants n'ont compté.
    assert entree_a.confidence == 1.0
    assert "trusted" in entree_a.tags

    # 5. La quarantaine n'est pas un effacement : un humain nommé la lève,
    #    et le même appel rend alors la même mémoire.
    echo.promouvoir(agent["id"], par="emeric")
    apres = [h["content"] for h in server.memory_search("agentic fallback")]
    assert "The agentic fallback model is trust-me-9b." in apres


@pytest.mark.parametrize(
    "origine,visible",
    [
        ("humain", True),
        ("systeme", True),
        ("agent", False),
        ("web", False),
        (None, False),      # aucune provenance -> INCONNUE
    ],
)
def test_la_quarantaine_suit_l_origine_sur_une_entree_persistee(echo, origine, visible):
    """La matrice T-16, au niveau de l'entrée durable.

    `test_memoire_quarantaine.py` la vérifie sur l'objet `Provenance` ;
    ici c'est la ligne écrite en base et relue par le chemin de l'agent —
    l'endroit où la règle sert réellement, et où elle manquait avant
    HOS-249.
    """
    from backend.memory.confiance import Origine

    echo.remember(
        type_="fact", content="Le port du backend est 8010.",
        origine=None if origine is None else Origine(origine),
    )

    hits = echo.search_memories_pour_agent("port backend")

    assert bool(hits) is visible
