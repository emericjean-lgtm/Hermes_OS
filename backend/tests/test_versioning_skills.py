# -*- coding: utf-8 -*-
"""Le versioning des Skills : le ledger de mutations de l'agent, LU (G-42, HOS-303).

## Le defaut que §10 nommait

G-35 (HOS-283) concluait : *« le ledger de l'agent
(`.curator_ledger.jsonl`) [porterait le versioning et le rollback], mais il
n'existe pas sur cette installation, et aucune RPC ne l'expose »*. Remesure
le 2026-09-12 : `tools/skill_ledger.py` existe reellement chez l'agent
depuis son commit `693641aa8b` (17 aout) — un JSONL en ajout seul, une
ligne par mutation, avant/apres content-addressed. Le fichier ne porte
simplement encore aucune entree sur cette installation : aucune mutation
n'a eu lieu depuis que l'agent le tient.

## Ce que ces gardes tiennent

Chaque entree que ce module rend EST une ligne ecrite par l'agent — jamais
un horodatage ou un hash fabrique en remplacement d'une vraie version. Le
diff de fichiers (`ajoute`/`supprime`/`modifie`) se derive directement des
`before`/`after` de l'entree, jamais d'une declaration.

Le declenchement du rollback reste DEFER, meme motif que G-35 pour
l'installation : la lecture est possible, l'ecriture demande un
approbateur qu'aucune RPC ne joint encore.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parents[2]


@pytest.fixture
def foyer(tmp_path, monkeypatch):
    """Un `HERMES_HOME` a nous, avec un dossier `skills/` vide."""
    import importlib

    from backend.skills import registre

    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    importlib.reload(registre)
    skills = tmp_path / "skills"
    skills.mkdir(parents=True)
    yield skills
    monkeypatch.delenv("HERMES_HOME", raising=False)
    importlib.reload(registre)


def _v():
    import importlib

    from backend.skills import versioning

    return importlib.reload(versioning)


def _ecrire_ledger(skills: Path, entrees: list[dict]) -> None:
    lignes = [json.dumps(e, ensure_ascii=False) for e in entrees]
    skills.joinpath(".curator_ledger.jsonl").write_text(
        "\n".join(lignes) + ("\n" if lignes else ""), encoding="utf-8")


def _entree(id_: str, action: str, skill: str, *, ts: str = "2026-09-12T10:00:00+00:00",
            actor: str = "user", before: list[dict] | None = None,
            after: list[dict] | None = None, evidence: dict | None = None) -> dict:
    return {"id": id_, "ts": ts, "actor": actor, "action": action, "skill": skill,
            "evidence": evidence or {}, "before": before or [], "after": after or []}


# ── La lecture, dans l'ordre que l'agent ecrit ─────────────────────────

def test_le_ledger_absent_se_lit_comme_tel_et_non_comme_une_panne(foyer):
    """Trois situations rendraient un ecran vide : jamais aucune mutation,
    fichier illisible, ou Hermes OS qui regarde au mauvais endroit. Le
    booleen separe la premiere des deux autres — meme distinction que
    `gouvernance.dossier_lisible`."""
    v = _v()
    vue = v.vue()
    assert vue["ledger_lisible"] is False
    assert vue["entrees"] == []
    assert vue["total"] == 0


def test_les_entrees_sortent_de_la_plus_recente_a_la_plus_ancienne(foyer):
    """Le fichier est ecrit en ajout seul : la plus recente est la
    DERNIERE ligne du fichier, pas la premiere."""
    _ecrire_ledger(foyer, [
        _entree("un", "created", "g42-a", ts="2026-09-12T10:00:00+00:00"),
        _entree("deux", "edited", "g42-a", ts="2026-09-12T10:05:00+00:00"),
        _entree("trois", "created", "g42-b", ts="2026-09-12T10:10:00+00:00"),
    ])
    v = _v()
    assert [e.id for e in v.entrees()] == ["trois", "deux", "un"]
    assert v.vue()["ledger_lisible"] is True
    assert v.vue()["total"] == 3


def test_le_filtre_par_skill_porte_sur_le_nom_exact(foyer):
    _ecrire_ledger(foyer, [
        _entree("un", "created", "g42-a"),
        _entree("deux", "created", "g42-b"),
    ])
    v = _v()
    assert [e.id for e in v.entrees(skill="g42-b")] == ["deux"]


def test_la_limite_s_applique_apres_le_tri(foyer):
    _ecrire_ledger(foyer, [
        _entree("un", "created", "g42-a", ts="2026-09-12T10:00:00+00:00"),
        _entree("deux", "created", "g42-a", ts="2026-09-12T10:05:00+00:00"),
    ])
    v = _v()
    assert [e.id for e in v.entrees(limite=1)] == ["deux"]


def test_une_ligne_malformee_est_ignoree_pas_les_autres(foyer):
    """Meme posture que `gouvernance.journal()` : une ligne corrompue ne
    doit pas faire echouer la lecture des autres."""
    lignes = [
        json.dumps(_entree("bonne", "created", "g42-a")),
        "{ pas du json",
        json.dumps(["pas un objet"]),
    ]
    foyer.joinpath(".curator_ledger.jsonl").write_text(
        "\n".join(lignes) + "\n", encoding="utf-8")
    v = _v()
    assert [e.id for e in v.entrees()] == ["bonne"]


def test_get_entree_par_id_rend_none_si_absent(foyer):
    _ecrire_ledger(foyer, [_entree("un", "created", "g42-a")])
    v = _v()
    assert v.entree("un").skill == "g42-a"
    assert v.entree("n-existe-pas") is None
    assert v.entree("") is None


# ── Le diff, derive des octets et non declare ──────────────────────────

def test_un_fichier_seulement_dans_after_est_ajoute(foyer):
    _ecrire_ledger(foyer, [_entree(
        "un", "created", "g42-a",
        after=[{"path": "a/SKILL.md", "sha256": "h1"}])])
    fichiers = _v().entree("un").fichiers
    assert len(fichiers) == 1
    assert fichiers[0].chemin == "a/SKILL.md" and fichiers[0].etat == "ajoute"


def test_un_fichier_seulement_dans_before_est_supprime(foyer):
    _ecrire_ledger(foyer, [_entree(
        "un", "delete", "g42-a",
        before=[{"path": "a/SKILL.md", "sha256": "h1"}])])
    fichiers = _v().entree("un").fichiers
    assert fichiers[0].etat == "supprime"


def test_un_fichier_avec_une_empreinte_differente_est_modifie(foyer):
    _ecrire_ledger(foyer, [_entree(
        "un", "edited", "g42-a",
        before=[{"path": "a/SKILL.md", "sha256": "h1"}],
        after=[{"path": "a/SKILL.md", "sha256": "h2"}])])
    fichiers = _v().entree("un").fichiers
    assert fichiers[0].etat == "modifie"


def test_un_fichier_avec_la_meme_empreinte_est_inchange(foyer):
    """Present des deux cotes, meme sha256 : rien n'a change pour CE
    fichier, meme si l'entree en touche d'autres. Le confondre avec un
    ajout fabriquerait un changement qui n'a pas eu lieu."""
    _ecrire_ledger(foyer, [_entree(
        "un", "edited", "g42-a",
        before=[{"path": "a/SKILL.md", "sha256": "h1"},
                {"path": "a/notes.md", "sha256": "h9"}],
        after=[{"path": "a/SKILL.md", "sha256": "h1"},
               {"path": "a/notes.md", "sha256": "hA"}])])
    fichiers = {f.chemin: f.etat for f in _v().entree("un").fichiers}
    assert fichiers["a/SKILL.md"] == "inchange"
    assert fichiers["a/notes.md"] == "modifie"


# ── L'acteur : borne, jamais devine ─────────────────────────────────────

def test_un_acteur_valide_est_rendu_tel_quel(foyer):
    _ecrire_ledger(foyer, [_entree("un", "created", "g42-a", actor="curator")])
    assert _v().entree("un").acteur == "curator"


def test_un_acteur_hors_de_la_liste_est_acteur_inconnu(foyer):
    """`tools/skill_ledger.py::_VALID_ACTORS` = {curator, agent, user}.
    Une valeur hors de cette liste — main manuelle, format futur — ne doit
    pas etre rangee dans l'une des trois : ce serait fabriquer un acteur."""
    _ecrire_ledger(foyer, [_entree("un", "created", "g42-a", actor="robot-x")])
    assert _v().entree("un").acteur == "acteur_inconnu"


# ── Le lien rollback / consolidation : jamais devine hors de l'evidence ─

def test_une_entree_de_rollback_porte_sa_cible(foyer):
    _ecrire_ledger(foyer, [_entree(
        "deux", "rollback", "g42-a", evidence={"rollback_target": "un"})])
    assert _v().entree("deux").rollback_de == "un"
    assert _v().entree("deux").absorbe_dans is None


def test_une_entree_ordinaire_ne_porte_ni_lien(foyer):
    _ecrire_ledger(foyer, [_entree("un", "created", "g42-a")])
    e = _v().entree("un")
    assert e.rollback_de is None and e.absorbe_dans is None


# ── Le rollback reste DEFER, et la raison est dite ──────────────────────

def test_le_rollback_n_est_jamais_presente_comme_declenchable(foyer):
    """Le motif exact que G-26/G-35 ont pose pour l'installation : ne
    jamais afficher une capacite comme disponible si le declenchement
    n'existe pas de ce cote."""
    v = _v()
    vue = v.vue()
    assert vue["rollback_declenchable"] is False
    assert "curator rollback" in vue["rollback_absent_raison"]
    assert "RPC" in vue["rollback_absent_raison"]


# ── Ce que ce lecteur ne devient pas ────────────────────────────────────

def test_le_lecteur_n_ecrit_rien():
    """Cinquieme lecture du disque de l'agent (HOS-274, HOS-275, HOS-281,
    HOS-283, celle-ci) : lire, jamais ecrire."""
    arbre = ast.parse((RACINE / "backend" / "skills"
                       / "versioning.py").read_text(encoding="utf-8"))
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.Call):
            nom = (getattr(noeud.func, "attr", None)
                   or getattr(noeud.func, "id", None))
            assert nom not in {"write_text", "write_bytes", "mkdir", "unlink",
                               "rmtree", "replace", "touch", "chmod"}, (
                f"le lecteur appelle `{nom}`")


def test_le_lecteur_n_importe_rien_de_l_agent():
    """`plugin_compat` desactive au 2026-09-14 tout code externe qui
    importe les internes de l'agent. Ce lecteur ne depend d'aucun module
    de l'agent, seulement du format JSONL documente comme durable."""
    source = (RACINE / "backend" / "skills"
              / "versioning.py").read_text(encoding="utf-8")
    arbre = ast.parse(source)
    modules = set()
    for n in ast.walk(arbre):
        if isinstance(n, ast.Import):
            modules |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom) and n.module:
            modules.add(n.module.split(".")[0])
    assert not modules & {"tools", "hermes_cli", "acp", "acp_adapter",
                          "tui_gateway"}, (
        "le lecteur importe un module de l'agent : il mourra le 2026-09-14")


def test_aucune_route_de_versions_ne_mute():
    """Meme garde que `test_aucune_route_de_skill_ne_mute_toujours` pour la
    gouvernance : gouverner une ecriture demande un approbateur, et aucun
    n'est joignable pour le rollback."""
    source = (RACINE / "backend" / "skills"
              / "routes.py").read_text(encoding="utf-8")
    arbre = ast.parse(source)
    fautives = []
    for noeud in ast.walk(arbre):
        if not isinstance(noeud, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for deco in noeud.decorator_list:
            if not isinstance(deco, ast.Call):
                continue
            verbe = getattr(deco.func, "attr", "")
            if verbe in ("post", "put", "patch", "delete"):
                chemin = (deco.args[0].value if deco.args
                          and isinstance(deco.args[0], ast.Constant) else "")
                if "versions" in str(chemin):
                    fautives.append(f"{verbe.upper()} {chemin}")
    assert not fautives, (
        "une route de versioning mute sans approbateur : " + ", ".join(fautives))


def test_l_ecran_appelle_vraiment_la_route():
    """Une route de plus sans appelant frontend porterait le compte des
    orphelins d'une unite."""
    client = (RACINE / "frontend" / "src" / "services"
             / "client.ts").read_text(encoding="utf-8")
    assert "/skills/versions" in client

    ecran = (RACINE / "frontend" / "src" / "features" / "skills"
             / "skills-center.tsx").read_text(encoding="utf-8")
    assert "skillsClient.versions()" in ecran, (
        "la route existe et aucun ecran ne l'appelle")


def test_la_route_est_declaree_avant_le_joker_de_skill_id():
    source = (RACINE / "backend" / "skills"
              / "routes.py").read_text(encoding="utf-8")
    assert (source.index('@router.get("/versions")')
            < source.index('@router.get("/{skill_id}")'))
