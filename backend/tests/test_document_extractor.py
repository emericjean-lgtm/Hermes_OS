"""§13 — text extraction from document files.

Runs without Ollama, ChromaDB or Aegis: the extractor deliberately knows
about none of them, which is the whole reason it is a separate module.
The pypdf/python-docx paths are skipped when the library isn't installed,
and the "library missing" behaviour is tested by simulating the import
failure — so this file passes either way, which is the point of making
those dependencies optional.
"""
from __future__ import annotations

import builtins

import pytest

from backend.documents.extractor import (
    ExtractedDocument,
    MissingExtractorDependencyError,
    UnsupportedDocumentError,
    extract_text,
    supported_suffixes,
)


# ── plain-text family: no dependency at all ──────────────────────────
@pytest.mark.parametrize(
    ("name", "body"),
    [
        ("notes.md", "# Titre\n\nDu contenu."),
        ("data.json", '{"clef": "valeur"}'),
        ("conf.yaml", "clef: valeur\n"),
        ("script.py", "def f():\n    return 1\n"),
        ("plain.txt", "juste du texte"),
    ],
)
def test_text_family_extracts_verbatim(tmp_path, name, body):
    p = tmp_path / name
    p.write_text(body, encoding="utf-8")

    result = extract_text(p)

    assert isinstance(result, ExtractedDocument)
    assert result.text == body
    assert result.format == name.rsplit(".", 1)[1]
    assert result.warnings == ()


def test_accented_cp1252_file_still_decodes(tmp_path):
    """Windows-authored files are the common case on this machine —
    failing to index them would be a silent, recurring data loss."""
    p = tmp_path / "accents.txt"
    p.write_bytes("déjà vu, coût, œuf".encode("cp1252"))

    result = extract_text(p)

    assert "déjà vu" in result.text
    assert "coût" in result.text


def test_utf8_bom_is_stripped(tmp_path):
    p = tmp_path / "bom.md"
    p.write_bytes(b"\xef\xbb\xbf# Titre")

    assert extract_text(p).text == "# Titre"


def test_caller_supplied_bytes_win_over_disk(tmp_path):
    """The MCP tool reads through Aegis and passes the bytes in; the
    extractor must not go behind that and re-read the file itself."""
    p = tmp_path / "a.txt"
    p.write_text("sur le disque", encoding="utf-8")

    assert extract_text(p, data=b"fourni par l'appelant").text == "fourni par l'appelant"


def test_bytes_path_does_not_require_an_existing_file(tmp_path):
    assert extract_text(tmp_path / "jamais-cree.md", data=b"ok").text == "ok"


# ── refusals ─────────────────────────────────────────────────────────
@pytest.mark.parametrize("name", ["capture.png", "photo.JPEG", "scan.tiff"])
def test_images_are_refused_and_point_at_the_vision_agent(tmp_path, name):
    p = tmp_path / name
    p.write_bytes(b"\x89PNG\r\n")

    with pytest.raises(UnsupportedDocumentError, match="analyze_image"):
        extract_text(p)


def test_legacy_doc_names_the_fix(tmp_path):
    p = tmp_path / "vieux.doc"
    p.write_bytes(b"\xd0\xcf\x11\xe0")

    with pytest.raises(UnsupportedDocumentError, match="Convert it to .docx"):
        extract_text(p)


def test_unknown_extension_lists_what_is_supported(tmp_path):
    p = tmp_path / "chose.xyz"
    p.write_bytes(b"...")

    with pytest.raises(UnsupportedDocumentError, match="Supported:"):
        extract_text(p)


def test_missing_file():
    with pytest.raises(FileNotFoundError):
        extract_text("/nulle/part/absent.md")


def test_supported_suffixes_excludes_images():
    suffixes = supported_suffixes()
    assert ".pdf" in suffixes and ".docx" in suffixes and ".md" in suffixes
    assert not suffixes & {".png", ".jpg"}


# ── optional dependencies ────────────────────────────────────────────
def _simulate_missing(monkeypatch, blocked: str):
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == blocked or name.startswith(f"{blocked}."):
            raise ImportError(f"simulated: no {blocked}")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)


def test_pdf_without_pypdf_says_what_to_install(tmp_path, monkeypatch):
    _simulate_missing(monkeypatch, "pypdf")
    p = tmp_path / "doc.pdf"
    p.write_bytes(b"%PDF-1.4")

    with pytest.raises(MissingExtractorDependencyError, match="pip install pypdf"):
        extract_text(p)


def test_docx_without_python_docx_says_what_to_install(tmp_path, monkeypatch):
    _simulate_missing(monkeypatch, "docx")
    p = tmp_path / "doc.docx"
    p.write_bytes(b"PK\x03\x04")

    with pytest.raises(MissingExtractorDependencyError, match="pip install python-docx"):
        extract_text(p)


def test_missing_dependency_is_not_an_unsupported_format(tmp_path, monkeypatch):
    """"install one package" and "will never work" must stay
    distinguishable — they call for different reactions."""
    _simulate_missing(monkeypatch, "pypdf")
    p = tmp_path / "doc.pdf"
    p.write_bytes(b"%PDF-1.4")

    with pytest.raises(MissingExtractorDependencyError):
        extract_text(p)
    assert not issubclass(MissingExtractorDependencyError, UnsupportedDocumentError)


# ── real PDF / DOCX, only when the libraries are present ─────────────
# importorskip lives inside the test, not at module scope: at module
# scope it skips the whole file, silently taking the 15 dependency-free
# tests above with it.
def test_real_pdf_round_trip(tmp_path):
    pytest.importorskip("pypdf", reason="pypdf not installed")
    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    target = tmp_path / "blank.pdf"
    with target.open("wb") as fh:
        writer.write(fh)

    result = extract_text(target)

    # A blank page has no text layer: the warning is the useful output.
    assert result.format == "pdf"
    assert result.units == 1
    assert any("no text layer" in w for w in result.warnings)


def test_real_docx_extracts_paragraphs_and_tables(tmp_path):
    docx = pytest.importorskip("docx", reason="python-docx not installed")

    document = docx.Document()
    document.add_paragraph("Premier paragraphe.")
    document.add_paragraph("")  # blank ones must not become empty lines
    document.add_paragraph("Second paragraphe.")
    table = document.add_table(rows=1, cols=2)
    table.rows[0].cells[0].text = "Clef"
    table.rows[0].cells[1].text = "Valeur"
    target = tmp_path / "doc.docx"
    document.save(target)

    result = extract_text(target)

    assert result.format == "docx"
    assert "Premier paragraphe." in result.text
    assert "Second paragraphe." in result.text
    # Tables live outside .paragraphs — dropping them would silently lose
    # the structured half of most specs and reports.
    assert "Clef | Valeur" in result.text
    assert "\n\n" not in result.text
