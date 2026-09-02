"""Memory Manager — central orchestrator for HOS-047.

All other Hermes layers access memory through this single facade.
Coordinates working, episodic, semantic, procedural, document memory,
knowledge graph, embeddings, retrieval, and experience learning.
"""

from __future__ import annotations

import threading
from typing import Any, Callable, Optional

from backend.memory.confiance import (Origine, Provenance,
                                      filtrer, provenance_de)
from backend.memory.document_memory import DocumentMemoryStore
from backend.memory.embedding_index import EmbeddingIndex
from backend.memory.episodic_memory import EpisodicMemoryStore
from backend.memory.experience_manager import ExperienceManager
from backend.memory.knowledge_graph import KnowledgeGraph
from backend.memory.memory_models import (
    DocumentMemory,
    EpisodicMemory,
    KnowledgeEdge,
    KnowledgeNode,
    ProceduralMemory,
    SearchResult,
    SemanticMemory,
    WorkingMemory,
)
from backend.memory.procedural_memory import ProceduralMemoryStore
from backend.memory.retrieval_engine import RetrievalEngine
from backend.memory.semantic_memory import SemanticMemoryStore
from backend.memory.working_memory import WorkingMemoryStore


class MemoryManager:
    """Central memory orchestrator.

    Integrates all memory types with a unified API.
    All Hermes subsystems access memory through this facade.
    """

    def __init__(self, on_event: Optional[Callable] = None) -> None:
        self._lock = threading.RLock()
        self._on_event = on_event

        # Memory stores
        self._working = WorkingMemoryStore(on_event=on_event)
        self._episodic = EpisodicMemoryStore(on_event=on_event)
        self._semantic = SemanticMemoryStore(on_event=on_event)
        self._procedural = ProceduralMemoryStore(on_event=on_event)
        self._documents = DocumentMemoryStore(on_event=on_event)

        # Knowledge
        self._graph = KnowledgeGraph(on_event=on_event)
        self._embeddings = EmbeddingIndex(on_event=on_event)

        # Intelligence
        self._retrieval = RetrievalEngine(
            episodic=self._episodic,
            semantic=self._semantic,
            procedural=self._procedural,
            documents=self._documents,
            graph=self._graph,
            embeddings=self._embeddings,
            on_event=on_event,
        )
        self._experience = ExperienceManager(episodic=self._episodic, on_event=on_event)

    # ── Working Memory ───────────────────────────────────────

    def create_working_memory(self, mission_id: str, agent_id: str) -> WorkingMemory:
        return self._working.create(mission_id, agent_id)

    def get_working_memory(self, mission_id: str) -> Optional[WorkingMemory]:
        return self._working.get_by_mission(mission_id)

    def clear_working_memory(self, mission_id: str) -> bool:
        return self._working.clear(mission_id)

    # ── Episodic ─────────────────────────────────────────────

    # ── Confiance : d'où vient un souvenir (HOS-216) ─────────
    #
    # Ce n'est pas de la qualité de données, c'est la défense contre
    # l'injection de prompt. Un texte lu sur le web ou dans un dépôt
    # cloné peut être écrit *pour* l'agent ; s'il entre en mémoire et
    # ressort comme un fait, l'attaque est installée.
    #
    # On ne juge pas le contenu — un filtre sur les formulations se
    # contourne en changeant de formulation. On juge la **provenance**.

    def marquer(self, souvenir: Any, origine: "Origine | str",
                source: str = "") -> Any:
        """Attacher une provenance à un souvenir avant de l'écrire.

        Une origine non humaine part en quarantaine quoi qu'il arrive :
        l'appelant déclare d'où ça vient, il ne choisit pas la confiance.
        """
        provenance = Provenance.depuis(origine, source)
        try:
            souvenir.provenance = provenance
        except AttributeError:
            meta = getattr(souvenir, "metadata", None)
            if isinstance(meta, dict):
                meta["provenance"] = provenance
        return souvenir

    def promouvoir(self, souvenir: Any, par: str) -> Any:
        """Sortir un souvenir de quarantaine, en nommant qui l'a décidé."""
        promue = provenance_de(souvenir).promouvoir(par)
        try:
            souvenir.provenance = promue
        except AttributeError:
            meta = getattr(souvenir, "metadata", None)
            if isinstance(meta, dict):
                meta["provenance"] = promue
        if self._on_event:
            self._on_event("memory.promoted", {
                "par": par, "origine": promue.origine.value})
        return souvenir

    def record_episode(self, episode: EpisodicMemory, *,
                       origine: "Origine | str" = Origine.SYSTEME,
                       source: str = "") -> EpisodicMemory:
        """Un épisode : ce que Hermes a observé de sa propre exécution.

        `SYSTEME` par défaut, et c'est justifié : un relevé « la mission
        42 a pris 1 365 s, tuile 128, retenue » est **observé**, pas lu
        quelque part. Un appelant qui enregistre le récit d'un modèle
        doit déclarer `AGENT`.
        """
        self.marquer(episode, origine, source)
        return self._episodic.record(episode)

    def get_episode(self, mission_id: str) -> Optional[EpisodicMemory]:
        return self._episodic.get_by_mission(mission_id)

    def find_similar_missions(self, tags: list[str], mission_type: str = "", limit: int = 10) -> list[EpisodicMemory]:
        return self._episodic.find_similar(tags, mission_type, limit)

    # ── Semantic ─────────────────────────────────────────────

    def store_concept(self, concept: SemanticMemory, *,
                      origine: "Origine | str" = Origine.INCONNUE,
                      source: str = "") -> SemanticMemory:
        """Un concept : du contenu, donc un vecteur possible.

        Pas de défaut confortable ici : `INCONNUE` part en quarantaine.
        Un concept vient toujours de quelque part, et l'appelant est le
        seul à savoir d'où.
        """
        self.marquer(concept, origine, source)
        return self._semantic.store(concept)

    def search_concepts(self, query: str, limit: int = 10) -> list[SemanticMemory]:
        return self._semantic.search(query, limit)

    # ── Procedural ───────────────────────────────────────────

    def store_procedure(self, procedure: ProceduralMemory, *,
                        origine: "Origine | str" = Origine.SYSTEME,
                        source: str = "") -> ProceduralMemory:
        """Une procédure dérivée d'exécutions observées."""
        self.marquer(procedure, origine, source)
        return self._procedural.store(procedure)

    def find_procedures(self, query: str, limit: int = 10) -> list[ProceduralMemory]:
        return self._procedural.search(query, limit)

    # ── Documents ────────────────────────────────────────────

    def index_document(self, doc: DocumentMemory, *,
                       origine: "Origine | str" = Origine.DOCUMENT,
                       source: str = "") -> DocumentMemory:
        """Un document importé : contenu extérieur, donc quarantaine.

        C'est le vecteur d'injection le plus direct — un PDF, une page,
        un fichier de dépôt. Le défaut ne peut pas être confortable.
        """
        self.marquer(doc, origine, source)
        # Also index in embeddings
        self._embeddings.index(doc.document_id, doc.title + " " + doc.content[:1000])
        return self._documents.index(doc)

    def search_docs(self, query: str, limit: int = 10) -> list[DocumentMemory]:
        return self._documents.search(query, limit)

    # ── Knowledge Graph ──────────────────────────────────────

    def add_graph_node(self, node: KnowledgeNode) -> KnowledgeNode:
        return self._graph.add_node(node)

    def add_graph_edge(self, source_id: str, target_id: str, relation: str) -> Optional[KnowledgeEdge]:
        return self._graph.add_edge(source_id, target_id, relation)

    def get_graph_neighbors(self, node_id: str, relation: str = "") -> list[KnowledgeNode]:
        return self._graph.get_neighbors(node_id, relation)

    def traverse_graph(self, start_id: str, max_depth: int = 3) -> dict:
        return self._graph.traverse(start_id, max_depth)

    # ── Search ───────────────────────────────────────────────

    #: Où retrouver l'objet qu'un `SearchResult` désigne, par type.
    #: Un résultat porte `source_type` + `source_id` mais **pas** la
    #: provenance de ce qu'il désigne : filtrer directement dessus les
    #: éliminait tous, ce qui est fermé mais inutile.
    _MAGASINS = {
        "episodic": "_episodic",
        "semantic": "_semantic",
        "procedural": "_procedural",
        "document": "_documents",
    }

    def _provenance_du_resultat(self, r: SearchResult) -> "Provenance":
        """Remonter du résultat à l'objet, pour lire sa provenance.

        Un type de source inconnu — le graphe, par exemple — rend la
        provenance par défaut, donc la quarantaine. C'est le bon sens de
        lecture : ce qu'on ne sait pas résoudre ne devient pas fiable.
        """
        nom = self._MAGASINS.get(getattr(r, "source_type", ""))
        if not nom:
            return Provenance()
        magasin = getattr(self, nom, None)
        for attribut in vars(magasin or ()).values():
            if isinstance(attribut, dict):
                objet = attribut.get(getattr(r, "source_id", ""))
                if objet is not None:
                    return provenance_de(objet)
        return Provenance()

    def _filtrer_resultats(self, resultats: list[SearchResult], *,
                           inclure_quarantaine: bool) -> list[SearchResult]:
        if inclure_quarantaine:
            return resultats
        return [r for r in resultats
                if not self._provenance_du_resultat(r).en_quarantaine]

    def search(self, query: str, limit: int = 20,
               memory_types: Optional[list[str]] = None, *,
               inclure_quarantaine: bool = False) -> list[SearchResult]:
        """Chercher, sans servir la quarantaine par défaut.

        `inclure_quarantaine` est nommé et faux par défaut : un appelant
        qui veut du contenu non vérifié doit le dire, et ça se lit à la
        relecture. C'est la propriété exacte que gardent les tests
        d'injection.
        """
        return self._filtrer_resultats(
            self._retrieval.search(query, limit, memory_types),
            inclure_quarantaine=inclure_quarantaine)

    def search_experiences(self, query: str, limit: int = 10, *,
                           inclure_quarantaine: bool = False) -> list[SearchResult]:
        return self._filtrer_resultats(
            self._retrieval.search_experiences(query, limit),
            inclure_quarantaine=inclure_quarantaine)

    # ── Experience ───────────────────────────────────────────

    def learn_from_mission(self, episode: EpisodicMemory) -> list[str]:
        return self._experience.learn_from_mission(episode)

    def recommend_for_mission(self, mission_type: str, tags: list[str]) -> dict:
        return self._experience.recommend_for_new_mission(mission_type, tags)

    def get_best_practices(self, mission_type: str = "", limit: int = 10) -> list[str]:
        return self._experience.get_best_practices(mission_type, limit)

    # ── Index ────────────────────────────────────────────────

    def index_text(self, entity_id: str, text: str) -> list[float]:
        return self._embeddings.index(entity_id, text)

    # ── Stats ────────────────────────────────────────────────

    def stats(self) -> dict:
        return {
            "working": self._working.stats(),
            "episodic": self._episodic.stats(),
            "semantic": self._semantic.stats(),
            "procedural": self._procedural.stats(),
            "documents": self._documents.stats(),
            "graph": self._graph.stats(),
            "embeddings": {"count": self._embeddings.count()},
        }
