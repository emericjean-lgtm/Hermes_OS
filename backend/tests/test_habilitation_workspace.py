"""A-4 — l'habilitation de workspace est **nominative** (HOS-292).

Ce que ce fichier empeche de revenir, mesure le 2026-09-11 sur deux
projets tous deux actifs et valides, en lisant `ws-b/secret.txt` :

    project_id=A    -> deny   (le retrecissement fonctionnait deja)
    project_id=None -> allow  (et le contenu de B etait rendu)

La liste blanche dynamique d'Aegis etait l'**union de tous** les projets
actifs et valides, remise a *chaque* action quel que soit le projet
qu'elle nommait — ou qu'elle ne nommait pas. Un `files_read(chemin)` MCP
sans `project_id` lisait donc le workspace d'un projet qu'il n'avait
jamais nomme. C'est ce que voulait dire « portee projet validee, non
**autorisee** » : la validation prouve qu'un dossier existe, elle n'a
jamais dit *qui* peut y toucher.

`test_workspace_filesystem_layer.py` couvre l'octroi et sa revocation ;
ce fichier couvre l'**attribution** : a qui la racine est accordee, et a
qui elle ne l'est pas.
"""
from __future__ import annotations

import pytest

from backend.agents.aegis import AegisAgent
from backend.core.config import get_settings
from backend.core.message_bus import get_message_bus
from backend.core.router import ModelRouter
from backend.projects.store import get_project_store
from backend.security.aegis_engine import ActionRequest, Verdict
from backend.tools import file_tools


@pytest.fixture
def deux_workspaces(monkeypatch, fake_ollama_client, models_config, security_config, tmp_path):
    """Aegis reel, magasin reel, **deux** projets actifs et valides.

    Deux, parce que c'est le nombre a partir duquel la question se pose :
    avec un seul projet valide, l'union et l'attribution nominative
    rendent exactement le meme verdict, et tous les tests d'avant HOS-292
    tenaient dans ce point aveugle.

    `ALLOWED_PATHS` pointe vers un dossier statique **tiers** : tout acces
    aux deux workspaces doit venir de l'habilitation, jamais de la liste
    statique.
    """
    statique = tmp_path / "_statique"
    statique.mkdir()
    (statique / "config_humaine.txt").write_text("ecrit par un humain dans la config")

    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("ALLOWED_PATHS", str(statique))
    get_settings.cache_clear()
    get_message_bus.cache_clear()
    get_project_store.cache_clear()
    monkeypatch.setattr("backend.agents.aegis.load_security_config", lambda: security_config)

    aegis = AegisAgent(fake_ollama_client, ModelRouter(models_config), models_config)

    racine_a = tmp_path / "ws-a"
    racine_a.mkdir()
    racine_b = tmp_path / "ws-b"
    racine_b.mkdir()
    (racine_a / "a.txt").write_text("contenu de A")
    (racine_b / "secret.txt").write_text("LE SECRET DE B")

    magasin = get_project_store()
    a = magasin.validate(magasin.create(name="a", root_path=str(racine_a)).id)
    b = magasin.validate(magasin.create(name="b", root_path=str(racine_b)).id)

    try:
        yield {"aegis": aegis, "a": a, "b": b,
               "racine_a": racine_a, "racine_b": racine_b, "statique": statique}
    finally:
        get_settings.cache_clear()
        get_message_bus.cache_clear()
        get_project_store.cache_clear()


def _lecture(cible, project_id):
    return ActionRequest(
        action_type="file_read", description="read", target_path=str(cible),
        requesting_agent="test", project_id=project_id,
    )


@pytest.fixture(params=["/", '\\'], ids=["slash", "antislash"])
def separateur(request):
    """Les deux separateurs que Windows accepte reellement."""
    return request.param


# -- 1. L'attribution elle-meme -------------------------------------


def test_sans_projet_nomme_aucun_workspace_n_est_accorde(deux_workspaces):
    """Le defaut A-4, exactement. Une action qui ne nomme aucun projet ne
    porte aucune habilitation de workspace."""
    d = deux_workspaces
    decision = d["aegis"].evaluate(_lecture(d["racine_b"] / "secret.txt", None))
    assert decision.verdict is Verdict.DENY


def test_le_contenu_de_b_n_est_pas_rendu_sans_projet_nomme(deux_workspaces):
    """La mesure d'origine allait jusqu'au bout : ce n'etait pas seulement
    un `allow`, le fichier etait reellement lu et son contenu rendu."""
    d = deux_workspaces
    with pytest.raises(PermissionError):
        file_tools.read_file(d["aegis"], str(d["racine_b"] / "secret.txt"))


def test_nommer_a_n_ouvre_pas_b(deux_workspaces):
    d = deux_workspaces
    decision = d["aegis"].evaluate(_lecture(d["racine_b"] / "secret.txt", d["a"].id))
    assert decision.verdict is Verdict.DENY


def test_nommer_b_ouvre_b(deux_workspaces):
    """Le pendant indispensable : l'habilitation nominative doit encore
    **accorder**. Une frontiere qui refuse tout serait verte et inutile."""
    d = deux_workspaces
    decision = d["aegis"].evaluate(_lecture(d["racine_b"] / "secret.txt", d["b"].id))
    assert decision.verdict is Verdict.ALLOW
    contenu = file_tools.read_file(
        d["aegis"], str(d["racine_b"] / "secret.txt"), project_id=d["b"].id)
    assert contenu == "LE SECRET DE B"


def test_chaque_projet_n_ouvre_que_le_sien(deux_workspaces):
    d = deux_workspaces
    assert d["aegis"].evaluate(
        _lecture(d["racine_a"] / "a.txt", d["a"].id)).verdict is Verdict.ALLOW
    assert d["aegis"].evaluate(
        _lecture(d["racine_a"] / "a.txt", d["b"].id)).verdict is Verdict.DENY


# -- 2. La liste blanche statique n'est pas remplacee ----------------


def test_la_liste_statique_continue_de_servir_sans_projet(deux_workspaces):
    """Contrat historique preserve : `ALLOWED_PATHS` est ecrite par un
    humain dans la configuration, elle n'est pas accordee par une
    validation, donc HOS-292 n'y touche pas. Une action anonyme la garde.
    """
    d = deux_workspaces
    cible = d["statique"] / "config_humaine.txt"
    assert d["aegis"].evaluate(_lecture(cible, None)).verdict is Verdict.ALLOW
    assert file_tools.read_file(d["aegis"], str(cible)).startswith("ecrit par un humain")


def test_la_liste_statique_survit_aussi_a_un_projet_nomme(deux_workspaces):
    """Nommer un projet **retrecit** : la racine du projet borne l'action,
    donc un chemin statique hors de cette racine est refuse. Le
    retrecissement est la regle d'origine et il ne doit pas disparaitre
    au profit de l'elargissement."""
    d = deux_workspaces
    cible = d["statique"] / "config_humaine.txt"
    assert d["aegis"].evaluate(_lecture(cible, d["a"].id)).verdict is Verdict.DENY


# -- 3. Ce qui n'autorise pas ---------------------------------------


def test_un_projet_non_valide_n_autorise_pas(deux_workspaces, tmp_path):
    d = deux_workspaces
    racine_c = tmp_path / "ws-c"
    racine_c.mkdir()
    c = get_project_store().create(name="c", root_path=str(racine_c))  # jamais valide
    assert d["aegis"].evaluate(
        _lecture(racine_c / "f.txt", c.id)).verdict is Verdict.DENY


def test_un_projet_archive_n_autorise_plus(deux_workspaces):
    d = deux_workspaces
    action = _lecture(d["racine_b"] / "secret.txt", d["b"].id)
    assert d["aegis"].evaluate(action).verdict is Verdict.ALLOW
    get_project_store().update(d["b"].id, status="archived")
    assert d["aegis"].evaluate(action).verdict is Verdict.DENY


def test_un_project_id_inexistant_n_autorise_pas(deux_workspaces):
    """Ni un acces, ni un refus silencieux : Aegis traite un identifiant
    inconnu en suspect (validation humaine), et surtout **pas** en
    `allow`."""
    d = deux_workspaces
    decision = d["aegis"].evaluate(
        _lecture(d["racine_b"] / "secret.txt", "projet-invente-0000"))
    assert decision.verdict is not Verdict.ALLOW


def test_un_project_id_vide_n_autorise_pas(deux_workspaces):
    d = deux_workspaces
    assert d["aegis"].evaluate(
        _lecture(d["racine_b"] / "secret.txt", "")).verdict is not Verdict.ALLOW


# -- 4. Traversees, depuis un workspace reellement accorde -----------


@pytest.mark.parametrize("evasion", [
    "../ws-b/secret.txt",
    "../../ws-b/secret.txt",
    "..\\ws-b\\secret.txt",
    "./sub/../../ws-b/secret.txt",
])
def test_une_traversee_ne_mene_pas_au_workspace_voisin(deux_workspaces, evasion):
    """Nomme A, vise B en remontant. Le projet est reellement accorde, donc
    c'est bien la traversee qui est refusee, et non l'absence d'octroi."""
    d = deux_workspaces
    cible = str((d["racine_a"] / evasion).resolve())
    assert d["aegis"].evaluate(_lecture(cible, d["a"].id)).verdict is Verdict.DENY


def test_une_traversee_non_normalisee_est_refusee(deux_workspaces, separateur):
    """Le chemin arrive **tel que l'appelant l'a ecrit**, sans `.resolve()`
    prealable — c'est le cas reel de MCP et de HTTP, qui transmettent la
    chaine du modele ou du client directement a `file_tools`.

    Trouve par mutation le 2026-09-11 : retirer le `.resolve()` de
    `_is_within_whitelist` laissait **toute** la suite verte. Les tests de
    traversee existants resolvaient le chemin eux-memes avant de le
    passer, si bien qu'aucun n'exercait la normalisation d'Aegis. Or sans
    elle la comparaison est purement lexicale, et un chemin de la forme
    `<racine_a>/../ws-b/secret.txt` est lexicalement « interieur a A »
    tout en designant B. La garde etait bonne, personne ne la tenait.

    Les deux separateurs sont essayes : Windows accepte les deux, et une
    normalisation qui n'en connaitrait qu'un serait une evasion.
    """
    d = deux_workspaces
    brut = separateur.join([str(d["racine_a"]), "..", "ws-b", "secret.txt"])
    assert d["aegis"].evaluate(_lecture(brut, d["a"].id)).verdict is Verdict.DENY
    with pytest.raises(PermissionError):
        file_tools.read_file(d["aegis"], brut, project_id=d["a"].id)


def test_une_traversee_non_normalisee_ne_passe_pas_par_la_liste_statique(
        deux_workspaces, separateur):
    """Meme attaque, visee depuis la liste blanche statique : partir d'un
    chemin autorise par la configuration et remonter vers un workspace
    voisin, sans nommer aucun projet."""
    d = deux_workspaces
    brut = separateur.join([str(d["statique"]), "..", "ws-b", "secret.txt"])
    assert d["aegis"].evaluate(_lecture(brut, None)).verdict is Verdict.DENY


def test_la_casse_ne_fait_pas_une_habilitation(deux_workspaces):
    """Sous Windows les chemins ne sont pas sensibles a la casse : une
    variante de casse de la racine de B, nommee sous A, reste refusee."""
    d = deux_workspaces
    cible = str(d["racine_b"] / "SECRET.TXT")
    assert d["aegis"].evaluate(_lecture(cible, d["a"].id)).verdict is Verdict.DENY
