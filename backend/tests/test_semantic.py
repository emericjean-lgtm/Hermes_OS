from __future__ import annotations

from chromadb import EmbeddingFunction

from backend.memory.semantic import DocumentStore, chunk_text


class FakeEmbeddingFunction(EmbeddingFunction):
    """Deterministic, network-free stand-in for OllamaEmbeddingFunction —
    real embedding calls need a live Ollama server (see manual check in
    the session log), which this sandbox doesn't have. Same-ish text
    gets a same-ish vector so semantic search results stay meaningful."""

    def __init__(self) -> None:
        pass

    def __call__(self, input):
        return [[float(len(t) % 11), float(sum(map(ord, t)) % 17)] for t in input]

    @staticmethod
    def name() -> str:
        return "fake"

    def get_config(self) -> dict:
        return {}

    @staticmethod
    def build_from_config(config: dict) -> "FakeEmbeddingFunction":
        return FakeEmbeddingFunction()


def test_chunk_text_splits_long_text_with_overlap():
    text = " ".join(f"word{i}" for i in range(600))
    chunks = chunk_text(text, chunk_size=512, overlap=64)
    assert len(chunks) == 2
    first_words = chunks[0].split()
    second_words = chunks[1].split()
    assert len(first_words) == 512
    # Overlap: the last 64 words of chunk 1 == the first 64 words of chunk 2.
    assert first_words[-64:] == second_words[:64]


def test_chunk_text_short_text_is_a_single_chunk():
    assert chunk_text("just a few words") == ["just a few words"]


def test_chunk_text_empty_text_returns_no_chunks():
    assert chunk_text("") == []
    assert chunk_text("   ") == []


def test_document_store_add_and_search_roundtrip():
    store = DocumentStore(FakeEmbeddingFunction())
    store.add_document("doc-0", "Hermes Ollama is a local AI copilot", {"source": "test"})
    store.add_document("doc-1", "The RX 6800 has 16GB of VRAM", {"source": "test"})

    results = store.search("Hermes Ollama is a local AI copilot", n_results=1)

    assert len(results) == 1
    assert results[0]["id"] == "doc-0"
    assert results[0]["metadata"] == {"source": "test"}
    assert results[0]["distance"] == 0.0


def test_document_store_search_respects_n_results():
    store = DocumentStore(FakeEmbeddingFunction())
    for i in range(5):
        # ChromaDB 1.x rejects an empty metadata dict, hence {"i": i}.
        store.add_document(f"doc-{i}", f"document number {i}", {"i": i})

    assert len(store.search("document", n_results=2)) == 2
