"""RAG must be able to say "nothing relevant" (HOS-097).

A vector index always has a nearest neighbour. Without a floor, asking
"chocolate cake recipe" against a corpus about Hermes OS returns the passage
about the agentic fallback model — ranked first, with nothing in the result
to say it is nonsense. Feed that to a language model and it becomes
hallucination fuel with a citation attached.

This is the retrieval-shaped version of the failure this whole campaign has
been about: a system that answers rather than admitting it has no answer.

The threshold is measured, not chosen. Against real fixtures with
qwen3-embedding:0.6b, on-topic questions scored 0.683-0.949 and off-topic
ones 1.272-1.514; MAX_RELEVANT_DISTANCE sits inside that gap.

These tests use a stub embedding function so they assert the *policy* and
run without Ollama — the distances above came from the live measurement, and
a live index is exercised separately in test_documents_endpoint.py.
"""
from __future__ import annotations

import pytest

from backend.memory.semantic import MAX_RELEVANT_DISTANCE, DocumentStore


class _FakeCollection:
    """Returns whatever distances a test asks for."""

    def __init__(self, hits):
        self._hits = hits
        self.added: list[dict] = []

    def add(self, ids, documents, metadatas):
        self.added.append({"ids": ids, "documents": documents, "metadatas": metadatas})

    def query(self, query_texts, n_results, where=None):
        ids, docs, metas, dists = zip(*self._hits) if self._hits else ((), (), (), ())
        return {
            "ids": [list(ids)], "documents": [list(docs)],
            "metadatas": [list(metas)], "distances": [list(dists)],
        }


def _store(hits) -> DocumentStore:
    store = DocumentStore.__new__(DocumentStore)
    store._collection = _FakeCollection(hits)  # noqa: SLF001
    return store


def test_relevant_passages_are_returned():
    store = _store([("a", "port 8010", {}, 0.68), ("b", "fallback model", {}, 0.95)])

    assert len(store.search("which port")) == 2


def test_irrelevant_passages_are_not_returned_as_answers():
    """The measured off-topic band. Returning these is worse than returning
    nothing: the caller cannot tell an answer from the index's best guess."""
    store = _store([("b", "the agentic fallback model is lfm2.5", {}, 1.351)])

    assert store.search("chocolate cake recipe") == []


def test_the_floor_sits_between_the_measured_bands():
    """Neither an awkwardly phrased on-topic query nor a slightly less
    absurd off-topic one should flip sides."""
    assert 0.949 < MAX_RELEVANT_DISTANCE < 1.272


def test_a_mixed_result_set_keeps_only_what_passes():
    store = _store([
        ("a", "relevant", {}, 0.70),
        ("b", "borderline but out", {}, 1.30),
        ("c", "also relevant", {}, 0.90),
    ])

    assert [h["id"] for h in store.search("q")] == ["a", "c"]


def test_the_raw_ranking_stays_reachable():
    """Needed to diagnose why nothing passed the floor — otherwise an empty
    result is indistinguishable from an empty index."""
    store = _store([("b", "far away", {}, 1.351)])

    assert len(store.search("q", max_distance=None)) == 1


def test_an_unscored_hit_is_kept():
    """No distance is not evidence of irrelevance; dropping it silently
    would hide an index problem behind an empty result."""
    store = _store([("a", "no distance reported", {}, None)])

    assert len(store.search("q")) == 1


def test_empty_metadata_is_accepted():
    """Chroma rejects an empty dict outright, making "no metadata" — an
    ordinary case — an error every caller has to know about."""
    store = _store([])

    store.add_document("doc-1", "text", {})

    assert store._collection.added[0]["metadatas"] == [{"doc_id": "doc-1"}]  # noqa: SLF001


def test_supplied_metadata_is_preserved():
    store = _store([])

    store.add_document("doc-1", "text", {"project_id": "p1"})

    assert store._collection.added[0]["metadatas"] == [{"project_id": "p1"}]  # noqa: SLF001
