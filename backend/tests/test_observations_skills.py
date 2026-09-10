# -*- coding: utf-8 -*-
"""Ce que l'agent a fait de ses Skills, rattache a son Run (G-33, HOS-281).

## La chaine, mesuree avec l'observateur reellement installe

    phase 1 (Hermes OS)  RUN-ALPHA -> ffb603fc...
                         RUN-BETA  -> 9039b9d6...
    phase 2 (agent)      g33-une   turn=ffb603fc...
                         g33-deux  turn=ffb603fc...
                         g33-trois turn=9039b9d6...
    phase 3 (NOUVEAU     g33-une  -> RUN-ALPHA
             processus)  g33-deux -> RUN-ALPHA
                         g33-trois-> RUN-BETA

**ADOPT.** L'observateur est installe sous
`%LOCALAPPDATA%\\hermes\\plugins\\hermes-os-observateur-skills`, active par
`plugins.enabled`, et `scan_plugin` rend « aucun import interne » — sa
condition de survie au retrait du 2026-09-14.

## Ce que l'agent continue de faire quand le plugin ne marche pas

Mesure des trois defaillances, avec les Skills verifiees **sur le disque** :

    plugin absent      non charge   0 fait   Skills ecrites
    plugin desactive   charge, off  0 fait   Skills ecrites
    callback qui leve  charge, on   0 fait   Skills ecrites

L'observateur ne peut pas bloquer l'agent : `_emit_skill_lifecycle` ignore
le retour du hook et isole chaque callback.

## Ce que ce lecteur ne fait pas

Il ne recopie rien. Le fait appartient au plugin, la relation `T -> R` au
bus de Hermes OS, et aucun des deux ne migre dans l'autre. C'est la
troisieme lecture du disque de l'agent — apres les competences (HOS-274) et
leur provenance (HOS-275) — et la posture est la meme.
"""
from __future__ import annotations

import ast
import asyncio
import json
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parents[2]


@pytest.fixture
def foyer(tmp_path, monkeypatch):
    """Un `HERMES_HOME` a nous, avec un etat de plugin ecrit a la main."""
    import importlib

    from backend.skills import registre

    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    importlib.reload(registre)
    d = tmp_path / "plugin-data" / "agent-plugin-hermes-os-observateur-skills-abc"
    d.mkdir(parents=True)
    yield d
    monkeypatch.delenv("HERMES_HOME", raising=False)
    importlib.reload(registre)


def _poser(dossier: Path, faits: list[dict]) -> None:
    dossier.joinpath("state.json").write_text(
        json.dumps({f"fait-{i:03d}": f for i, f in enumerate(faits)},
                   ensure_ascii=False),
        encoding="utf-8")


def _fait(**extra):
    base = {"observe_a": 1.0, "action": "created", "skill_name": "s",
            "provenance": "local", "client_turn_id": "T1"}
    base.update(extra)
    return base


def _lire(relations: dict[str, str | None], limite: int = 200):
    """Les observations, avec une resolution `T -> R` posee d'avance."""
    import importlib

    from backend.runs import correlation
    from backend.skills import observations

    importlib.reload(observations)
    appels: list[str] = []

    async def _resoudre(turn_id, jours=7):
        appels.append(turn_id)
        return relations.get(turn_id)

    reel = correlation.run_du_tour
    correlation.run_du_tour = _resoudre
    try:
        return asyncio.run(observations.observations(limite)), appels
    finally:
        correlation.run_du_tour = reel


# ── Le rattachement ───────────────────────────────────────────────────

def test_une_mutation_est_rattachee_a_son_run(foyer):
    """La raison d'etre du lecteur : `client_turn_id` -> Run."""
    _poser(foyer, [_fait(skill_name="g33-une", client_turn_id="T1")])
    obs, _ = _lire({"T1": "RUN-ALPHA"})
    assert len(obs) == 1
    assert obs[0].skill == "g33-une"
    assert obs[0].run == "RUN-ALPHA"
    assert obs[0].rattachee is True
    # L'etiquette RENDUE, et pas seulement celle qui a servi a resoudre.
    # Une mutation qui vidait `turn_id` restait verte : le rattachement se
    # fait sur le fait brut, si bien qu'un ecran affichant « quel tour a
    # produit ceci » aurait montre du vide sans qu'aucun test ne bronche.
    assert obs[0].turn_id == "T1"


def test_plusieurs_skills_d_un_meme_tour_vont_au_meme_run(foyer):
    """Mesure : `g33-une` et `g33-deux` portaient la meme etiquette."""
    _poser(foyer, [_fait(skill_name="une", client_turn_id="T1"),
                   _fait(skill_name="deux", client_turn_id="T1")])
    obs, _ = _lire({"T1": "RUN-ALPHA"})
    assert {o.run for o in obs} == {"RUN-ALPHA"}


def test_deux_runs_restent_separes(foyer):
    _poser(foyer, [_fait(skill_name="une", client_turn_id="T1"),
                   _fait(skill_name="trois", client_turn_id="T2")])
    from backend.runs import correlation
    from backend.skills import observations

    async def _resoudre(turn_id, jours=7):
        return {"T1": "RUN-ALPHA", "T2": "RUN-BETA"}.get(turn_id)

    reel = correlation.run_du_tour
    correlation.run_du_tour = _resoudre
    try:
        groupes = asyncio.run(observations.par_run())
    finally:
        correlation.run_du_tour = reel
    assert {r: sorted(o.skill for o in l) for r, l in groupes.items()} == {
        "RUN-ALPHA": ["une"], "RUN-BETA": ["trois"]}


def test_chaque_etiquette_n_est_resolue_qu_une_fois(foyer):
    """Un Run emet plusieurs tours, un tour plusieurs Skills. Rejouer le bus
    par fait couterait le parcours autant de fois qu'il y a de mutations."""
    _poser(foyer, [_fait(skill_name=f"s{i}", client_turn_id="T1")
                   for i in range(6)])
    obs, appels = _lire({"T1": "RUN-ALPHA"})
    assert len(obs) == 6
    assert appels == ["T1"], f"{len(appels)} rejeux du bus pour un tour"


# ── Ce qui n'est pas rattache ─────────────────────────────────────────

def test_un_fait_sans_etiquette_n_est_rattache_a_rien(foyer):
    """Un tour hors Run — le chat — ou un agent non patche."""
    _poser(foyer, [_fait(skill_name="hors", client_turn_id="")])
    obs, appels = _lire({})
    assert obs[0].run is None and obs[0].rattachee is False
    assert appels == [], "une etiquette vide a ete resolue"


def test_une_etiquette_etrangere_n_est_rattachee_a_rien(foyer):
    """Hermes OS ne reconnait que ce qu'il a frappe."""
    _poser(foyer, [_fait(client_turn_id="venue-d-ailleurs")])
    obs, _ = _lire({"T1": "RUN-ALPHA"})
    assert obs[0].run is None


def test_les_non_rattachees_ne_deviennent_pas_un_run(foyer):
    """Les ranger sous une clef « inconnu » lui donnerait l'apparence d'un
    Run, et elle finirait affichee a cote des vrais."""
    _poser(foyer, [_fait(skill_name="a", client_turn_id="T1"),
                   _fait(skill_name="b", client_turn_id=""),
                   _fait(skill_name="c", client_turn_id="etrangere")])
    from backend.runs import correlation
    from backend.skills import observations

    async def _resoudre(turn_id, jours=7):
        return "RUN-ALPHA" if turn_id == "T1" else None

    reel = correlation.run_du_tour
    correlation.run_du_tour = _resoudre
    try:
        groupes = asyncio.run(observations.par_run())
    finally:
        correlation.run_du_tour = reel
    assert list(groupes) == ["RUN-ALPHA"]
    assert [o.skill for o in groupes["RUN-ALPHA"]] == ["a"]


# ── Le plugin absent, muet ou casse ───────────────────────────────────

def test_sans_etat_de_plugin_la_lecture_est_vide_et_non_en_erreur(foyer):
    """Plugin absent, desactive, ou qui n'a rien vu : trois situations qui
    se lisent pareil d'ici. Toutes doivent dire « aucune observation »,
    jamais « aucune mutation »."""
    import importlib

    from backend.skills import observations

    importlib.reload(observations)
    assert observations.faits_bruts() == []
    assert asyncio.run(observations.observations()) == []


def test_un_etat_illisible_ne_fait_pas_echouer_la_lecture(foyer):
    foyer.joinpath("state.json").write_text("{ pas du json", encoding="utf-8")
    import importlib

    from backend.skills import observations

    importlib.reload(observations)
    assert observations.faits_bruts() == []


def test_une_clef_qui_n_est_pas_un_fait_est_ignoree(foyer):
    """Le plugin peut ranger autre chose dans son etat ; seul le prefixe
    convenu designe un fait."""
    foyer.joinpath("state.json").write_text(
        json.dumps({"fait-001": _fait(), "reglage": {"x": 1}}),
        encoding="utf-8")
    import importlib

    from backend.skills import observations

    importlib.reload(observations)
    assert len(observations.faits_bruts()) == 1


# ── Ce que le lecteur ne devient pas ──────────────────────────────────

def test_le_lecteur_n_ecrit_rien():
    """Meme garde que `registre`, `provenance` et `vue_skills` : lire l'etat
    d'un plugin de l'agent ne doit jamais devenir le tenir."""
    arbre = ast.parse((RACINE / "backend" / "skills"
                       / "observations.py").read_text(encoding="utf-8"))
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.Call):
            nom = (getattr(noeud.func, "attr", None)
                   or getattr(noeud.func, "id", None))
            assert nom not in {"write_text", "write_bytes", "mkdir", "unlink",
                               "rmtree", "replace", "open", "touch"}, (
                f"le lecteur appelle `{nom}`")


def test_le_lecteur_ne_recopie_pas_les_faits_chez_hermes_os():
    """Le fait appartient au plugin, la relation au bus. Recopier l'un dans
    l'autre creerait la seconde source de verite."""
    source = (RACINE / "backend" / "skills"
              / "observations.py").read_text(encoding="utf-8")
    arbre = ast.parse(source)
    litteraux = {n.value for n in ast.walk(arbre)
                 if isinstance(n, ast.Constant) and isinstance(n.value, str)}
    for interdit in ("INSERT", "CREATE TABLE", "publish", "sqlite"):
        assert not any(interdit in x for x in litteraux if len(x) < 300), (
            f"le lecteur ecrit `{interdit}`")
