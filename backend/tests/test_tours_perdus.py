"""Quatre heures a rejouer la meme experience (HOS-153).

Campagne Skill360 du 2026-08-23. Qwen3.8-27B tenait le code avec un budget
de 3600 s par tour, et §7 a perdu quatre tours consecutifs a la seconde
pres — 03:47:59, 04:47:59, 05:47:59, 06:47:59 — sans jamais rendre la main.
14 598 s, 59 % de la nuit, zero livrable.

Le defaut n'etait pas la lenteur du modele : c'etait que rien ne comptait
les repetitions. Ces tests tiennent les deux moities de la correction — le
registre compte, l'executeur en tire une consequence.
"""
from __future__ import annotations

import backend.execution.task_executor as te
from backend.ral.adapters.sessions_de_mission import (
    PLAFOND_TOURS_PERDUS,
    SessionsDeMission,
)


class _Registre:
    """Un registre reduit a ce que la regle interroge."""

    def __init__(self, perdus: int) -> None:
        self._perdus = perdus

    def tours_perdus_de(self, cle: str) -> int:
        return self._perdus


def test_le_registre_compte_les_tours_perdus_consecutifs() -> None:
    """Ce qui compte est la repetition, pas le total."""
    registre = SessionsDeMission()
    registre._entrees["mission:x"] = type(
        "E", (), {"tours": 0, "tours_perdus": 0})()

    assert registre.noter("mission:x", abouti=False) == 1
    assert registre.noter("mission:x", abouti=False) == 2
    # Un tour qui aboutit efface l'ardoise : deux echecs separes par une
    # reussite ne sont pas une reproduction.
    assert registre.noter("mission:x", abouti=True) == 0
    assert registre.noter("mission:x", abouti=False) == 1


def test_noter_une_session_inconnue_ne_leve_pas() -> None:
    """Une session purgee entre le tour et sa notation reste un cas normal."""
    assert SessionsDeMission().noter("mission:disparue", abouti=False) == 0


def test_sous_le_plafond_le_modele_impose_est_conserve() -> None:
    """Un tour perdu peut etre une coupure reseau, pas un verdict.

    La nuit de l'incident, l'agent a bien vu des `APIConnectionError` :
    retirer le travail au premier accroc punirait le reseau, pas le modele.
    """
    obtenu = te._apres_des_tours_perdus(
        "qwen38-27b-64k", "mission:x", _Registre(PLAFOND_TOURS_PERDUS - 1))
    assert obtenu == "qwen38-27b-64k"


def test_au_plafond_la_suite_passe_au_modele_de_secours(monkeypatch) -> None:
    """L'incident lui-meme : §7 aurait du basculer au lieu de se repeter."""
    monkeypatch.setenv(
        "HERMES_MISSION_MODEL",
        "code_review=qwen38-27b-64k,*=gpt-oss-20b-64k")

    obtenu = te._apres_des_tours_perdus(
        "qwen38-27b-64k", "mission:x", _Registre(PLAFOND_TOURS_PERDUS))

    assert obtenu == "gpt-oss-20b-64k", (
        "au plafond de tours perdus, la section doit etre confiee au modele "
        "que l'operateur a designe pour tout le reste")


def test_sans_table_aucune_retrogradation_inventee(monkeypatch) -> None:
    """Faute de `*`, il n'y a rien vers quoi retrograder — et on le dit.

    Substituer un modele choisi au hasard serait pire que de se repeter :
    la campagne changerait de cerveau sans que personne l'ait decide.
    """
    monkeypatch.delenv("HERMES_MISSION_MODEL", raising=False)

    obtenu = te._apres_des_tours_perdus(
        "qwen38-27b-64k", "mission:x", _Registre(PLAFOND_TOURS_PERDUS + 3))

    assert obtenu == "qwen38-27b-64k"


def test_le_modele_de_secours_ne_se_remplace_pas_lui_meme(monkeypatch) -> None:
    """Quand c'est deja le modele de secours qui s'enlise, rien a faire."""
    monkeypatch.setenv("HERMES_MISSION_MODEL", "*=gpt-oss-20b-64k")

    obtenu = te._apres_des_tours_perdus(
        "gpt-oss-20b-64k", "mission:x", _Registre(PLAFOND_TOURS_PERDUS))

    assert obtenu == "gpt-oss-20b-64k"
