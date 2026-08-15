"""§13 — /documents/index, the REST face of document ingestion.

Focus is on the boundary this route owns: distinguishing *why* an
ingestion failed. "Aegis said no", "wrong format forever", "library not
installed" and "file has no text" all deserve different reactions from a
caller, so they must not collapse into one generic error.
"""
from __future__ import annotations


from backend.documents.extractor import (
    MissingExtractorDependencyError,
    UnsupportedDocumentError,
)


def test_formats_endpoint_lists_support_and_excludes_images(client):
    body = client.get("/documents/formats").json()

    assert ".pdf" in body["supported"]
    assert ".md" in body["supported"]
    assert ".png" not in body["supported"]


def test_index_a_real_text_file(client, tmp_path, monkeypatch):
    """Le fichier est réel, l'extraction aussi ; seul le vecteur est doublé.

    Ce test était le seul du fichier à atteindre le vrai `_echo`, donc la
    vraie `OllamaEmbeddingFunction`, qui ouvre son propre `httpx.Client`
    vers `/api/embeddings` — hors de portée du client factice que le
    fixture injecte. Il ne ralentissait pas : il pendait, et la suite
    entière avec lui (HOS-112).

    Ce qu'il vérifie est intact — la route extrait le texte, reconnaît le
    format, compte les caractères et rapporte des morceaux. Le stockage du
    vecteur lui-même relève de `test_semantic.py`, qui le couvre avec une
    fonction d'embedding factice ; le docstring de `conftest.py` désigne
    déjà cette répartition.
    """
    source = tmp_path / "notes.md"
    source.write_text("# Titre\n\nDu contenu indexable.", encoding="utf-8")

    monkeypatch.setattr(
        "backend.api.routes.documents.file_tools.read_bytes",
        lambda aegis, path, project_id=None: source.read_bytes(),
    )

    class EchoSansVecteur:
        def index_document(self, doc_id, text, metadata, project_id=None):
            assert text.strip(), "la route doit livrer le texte extrait"
            return 1

    monkeypatch.setattr("backend.api.routes.documents._echo", lambda: EchoSansVecteur())

    response = client.post("/documents/index", json={"path": str(source)})

    assert response.status_code == 200
    body = response.json()
    assert body["indexed"] is True
    assert body["chunks"] >= 1
    assert body["format"] == "md"
    assert body["characters"] > 0


def test_metadata_records_where_the_text_came_from(client, tmp_path, monkeypatch):
    """Without source_path a retrieved chunk can't be traced back to its
    file, which makes citation (§13) impossible."""
    source = tmp_path / "spec.md"
    source.write_text("contenu", encoding="utf-8")
    captured = {}

    monkeypatch.setattr(
        "backend.api.routes.documents.file_tools.read_bytes",
        lambda aegis, path, project_id=None: source.read_bytes(),
    )

    class FakeEcho:
        def index_document(self, doc_id, text, metadata, project_id=None):
            captured["doc_id"] = doc_id
            captured["metadata"] = metadata
            return 1

    monkeypatch.setattr("backend.api.routes.documents._echo", lambda: FakeEcho())

    client.post("/documents/index", json={"path": str(source)})

    assert captured["doc_id"] == "spec.md"  # defaults to the filename
    assert captured["metadata"]["source_path"] == str(source)
    assert captured["metadata"]["format"] == "md"


def test_aegis_refusal_is_403_not_500(client, tmp_path, monkeypatch):
    def refuse(aegis, path, project_id=None):
        raise PermissionError("path outside ALLOWED_PATHS")

    monkeypatch.setattr("backend.api.routes.documents.file_tools.read_bytes", refuse)

    response = client.post("/documents/index", json={"path": "/etc/passwd"})

    assert response.status_code == 403
    assert "ALLOWED_PATHS" in response.json()["detail"]


def test_missing_file_is_404(client, monkeypatch):
    def missing(aegis, path, project_id=None):
        raise FileNotFoundError("No such file: /tmp/absent.md")

    monkeypatch.setattr("backend.api.routes.documents.file_tools.read_bytes", missing)

    assert client.post("/documents/index", json={"path": "/tmp/absent.md"}).status_code == 404


def test_unsupported_format_is_415(client, monkeypatch):
    monkeypatch.setattr(
        "backend.api.routes.documents.file_tools.read_bytes",
        lambda aegis, path, project_id=None: b"\x89PNG",
    )

    response = client.post("/documents/index", json={"path": "/x/capture.png"})

    assert response.status_code == 415
    assert "analyze_image" in response.json()["detail"]


def test_missing_library_is_501_not_415(client, monkeypatch):
    """Distinct from 415 on purpose: 501 is fixable with a pip install,
    415 never will be. Collapsing them sends the user down the wrong path."""
    monkeypatch.setattr(
        "backend.api.routes.documents.file_tools.read_bytes",
        lambda aegis, path, project_id=None: b"%PDF-1.4",
    )

    def no_library(path, data=None):
        raise MissingExtractorDependencyError("PDF extraction needs 'pypdf'")

    monkeypatch.setattr("backend.api.routes.documents.extract_text", no_library)

    response = client.post("/documents/index", json={"path": "/x/doc.pdf"})

    assert response.status_code == 501
    assert "pypdf" in response.json()["detail"]


def test_empty_extraction_reports_why_instead_of_indexing_nothing(
    client, tmp_path, monkeypatch
):
    """A scanned PDF yields no text. Indexing it silently would create a
    document that can never match a query, with no trace of the reason."""
    monkeypatch.setattr(
        "backend.api.routes.documents.file_tools.read_bytes",
        lambda aegis, path, project_id=None: b"%PDF-1.4",
    )

    from backend.documents.extractor import ExtractedDocument

    monkeypatch.setattr(
        "backend.api.routes.documents.extract_text",
        lambda path, data=None: ExtractedDocument(
            text="   ", format="pdf", units=3, warnings=("no text layer found",)
        ),
    )

    body = client.post("/documents/index", json={"path": "/x/scan.pdf"}).json()

    assert body["indexed"] is False
    assert body["chunks"] == 0
    assert body["reason"] == "no extractable text"
    assert any("no text layer" in w for w in body["warnings"])


def test_unsupported_and_missing_dependency_are_different_types():
    assert not issubclass(MissingExtractorDependencyError, UnsupportedDocumentError)
    assert not issubclass(UnsupportedDocumentError, MissingExtractorDependencyError)
