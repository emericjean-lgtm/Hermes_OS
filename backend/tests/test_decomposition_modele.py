"""Sept bascules de modele en quatorze minutes (HOS-155).

Campagne du 2026-08-24. La decomposition d'une section expirait au bout de
ses 90 s, et **deux sections sur trois** etaient donc construites sur un
decoupage par regles — generique, aveugle a ce que la section demande.
C'est nommement l'un des cinq defauts qui ont produit des missions
`success: True` au-dessus d'un workspace vide.

Ni le modele ni le budget n'etaient en cause. Le decompositeur interrogeait
le routeur, qui ignore `HERMES_MISSION_MODEL` et proposait un **troisieme**
modele sur une carte qui n'en tient qu'un. Les 90 s partaient a evincer et
recharger treize gigaoctets.
"""
from __future__ import annotations

from backend.mission.planner.task_decomposer import _modele_deja_charge


def test_le_decompositeur_suit_la_table_de_l_operateur(monkeypatch) -> None:
    """Le dernier endroit qui ignorait la table (HOS-153 avait fait le reste)."""
    monkeypatch.setenv(
        "HERMES_MISSION_MODEL",
        "code_review=qwen38-27b-64k,*=gpt-oss-20b-64k")

    assert _modele_deja_charge() == "gpt-oss-20b-64k"


def test_un_modele_de_planification_nomme_prime(monkeypatch) -> None:
    """Un operateur qui veut un modele precis pour decouper peut le dire."""
    monkeypatch.setenv(
        "HERMES_MISSION_MODEL",
        "planning=qwen38-27b-64k,*=gpt-oss-20b-64k")

    assert _modele_deja_charge() == "qwen38-27b-64k"


def test_sans_table_le_routeur_garde_la_main(monkeypatch) -> None:
    """Rien d'impose : le routeur decide, comme avant.

    La correction retire une cause de bascule, elle ne retire pas au
    routeur son role quand personne ne lui a rien impose.
    """
    monkeypatch.delenv("HERMES_MISSION_MODEL", raising=False)

    assert _modele_deja_charge() == ""


def test_un_nom_seul_vaut_pour_la_decomposition_aussi(monkeypatch) -> None:
    monkeypatch.setenv("HERMES_MISSION_MODEL", "gpt-oss-20b-64k")

    assert _modele_deja_charge() == "gpt-oss-20b-64k"
