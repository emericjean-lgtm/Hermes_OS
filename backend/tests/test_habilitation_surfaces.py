"""A-4 — les trois surfaces rendent la **meme** decision (HOS-292).

HTTP (`api/routes/files.py`), MCP (`mcp_server/server.py`) et le chat
(`tools/workspace_chat_tools.py`) sont trois adaptateurs minces sur
`tools/file_tools.py`, qui interroge Aegis. Aucun ne doit obtenir plus
que les autres — c'est la seule raison pour laquelle on peut dire qu'il
n'y a qu'une autorite de securite.

Le defaut mesure le 2026-09-11 se voyait le mieux depuis MCP, parce que
c'est la surface ou le `project_id` est un **argument du modele** :
`files_read(chemin)` sans `project_id` rendait le contenu d'un workspace
que l'appel n'avait jamais nomme. Les tests d'octroi vivent dans
`test_habilitation_workspace.py` ; ici on prouve que chaque porte
d'entree applique la meme regle.
"""
from __future__ import annotations

import pytest

from backend.agents.aegis import AegisAgent
from backend.core.config import get_settings
from backend.core.message_bus import get_message_bus
from backend.core.router import ModelRouter
from backend.projects.store import get_project_store
from backend.security import approvals
from backend.tools import file_tools


@pytest.fixture
def surface(monkeypatch, fake_ollama_client, models_config, security_config, tmp_path):
    """Aegis reel + deux projets actifs et valides, et les adaptateurs MCP
    et chat branches dessus. `ALLOWED_PATHS` vise un dossier tiers."""
    statique = tmp_path / "_statique"
    statique.mkdir()

    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("ALLOWED_PATHS", str(statique))
    get_settings.cache_clear()
    get_message_bus.cache_clear()
    get_project_store.cache_clear()
    monkeypatch.setattr("backend.agents.aegis.load_security_config", lambda: security_config)

    aegis = AegisAgent(fake_ollama_client, ModelRouter(models_config), models_config)

    import backend.mcp_server.server as mcp
    monkeypatch.setattr(mcp, "_aegis", lambda: aegis)
    monkeypatch.setattr("backend.tools.workspace_chat_tools._aegis", lambda: aegis)

    racine_a = tmp_path / "ws-a"
    racine_a.mkdir()
    racine_b = tmp_path / "ws-b"
    racine_b.mkdir()
    (racine_b / "secret.txt").write_text("LE SECRET DE B")

    magasin = get_project_store()
    a = magasin.validate(magasin.create(name="a", root_path=str(racine_a)).id)
    b = magasin.validate(magasin.create(name="b", root_path=str(racine_b)).id)

    try:
        yield {"aegis": aegis, "mcp": mcp, "a": a, "b": b,
               "racine_a": racine_a, "racine_b": racine_b}
    finally:
        get_settings.cache_clear()
        get_message_bus.cache_clear()
        get_project_store.cache_clear()


# -- MCP : la surface ou le project_id vient du modele ---------------


def test_mcp_sans_project_id_ne_lit_pas_un_workspace_non_nomme(surface):
    """Le defaut d'origine, sur la surface ou il a ete mesure."""
    s = surface
    with pytest.raises(PermissionError):
        s["mcp"].files_read(str(s["racine_b"] / "secret.txt"))


def test_mcp_avec_le_bon_project_id_lit_reellement(surface):
    s = surface
    contenu = s["mcp"].files_read(
        str(s["racine_b"] / "secret.txt"), project_id=s["b"].id)
    assert contenu == "LE SECRET DE B"


def test_mcp_avec_le_project_id_d_un_autre_projet_est_refuse(surface):
    """Le modele nomme A et vise B : c'est la forme la plus directe de
    l'usurpation de portee, puisque `project_id` est litteralement un
    argument que le modele ecrit."""
    s = surface
    with pytest.raises(PermissionError):
        s["mcp"].files_read(str(s["racine_b"] / "secret.txt"), project_id=s["a"].id)


def test_mcp_et_file_tools_rendent_le_meme_verdict(surface):
    """Parite : MCP n'est qu'un adaptateur. S'il divergeait de
    `file_tools`, il y aurait deux autorites."""
    s = surface
    cible = str(s["racine_b"] / "secret.txt")
    for project_id in (None, s["a"].id, s["b"].id):
        via_mcp = _issue(lambda: s["mcp"].files_read(cible, project_id=project_id))
        via_outil = _issue(
            lambda: file_tools.read_file(s["aegis"], cible, project_id=project_id))
        assert via_mcp == via_outil, project_id


def _issue(appel):
    try:
        return ("ok", appel())
    except PermissionError:
        return ("refuse", None)


@pytest.mark.parametrize("outil,kwargs", [
    ("files_exists", {}),
    ("files_stat", {}),
    ("files_search", {"pattern": "*.txt"}),
])
def test_toutes_les_lectures_mcp_sont_gardees_identiquement(surface, outil, kwargs):
    """`files_read` n'est pas un cas particulier : exists / stat / search
    voient la meme frontiere. Une seule des trois qui l'ignorerait
    suffirait a enumerer un workspace voisin."""
    s = surface
    cible = str(s["racine_b"] / "secret.txt") if outil != "files_search" else str(s["racine_b"])
    fn = getattr(s["mcp"], outil)
    with pytest.raises(PermissionError):
        fn(cible, **kwargs)
    # Le pendant : nomme, l'outil rend un resultat *utile*, pas seulement
    # non-nul. `is not None` laisserait passer un `False` ou une liste
    # vide, c'est-a-dire une frontiere qui refuse tout.
    autorise = fn(cible, project_id=s["b"].id, **kwargs)
    if outil == "files_exists":
        assert autorise is True
    elif outil == "files_stat":
        assert autorise["size_bytes"] == len("LE SECRET DE B")
    else:
        assert [c for c in autorise if c.endswith("secret.txt")]


# -- Mutations : l'accord humain, et ce qu'il nomme ------------------


def test_une_suppression_sans_accord_ne_supprime_rien(surface):
    s = surface
    cible = s["racine_b"] / "secret.txt"
    resultat = s["mcp"].files_delete(str(cible), project_id=s["b"].id)
    assert resultat["success"] is False
    assert resultat["verdict"] == "require_human_validation"
    assert cible.exists(), "le fichier a ete supprime sans accord"


def test_une_suppression_approuvee_supprime_vraiment(surface):
    s = surface
    cible = s["racine_b"] / "secret.txt"
    premier = s["mcp"].files_delete(str(cible), project_id=s["b"].id)
    assert premier["success"] is False

    with s["aegis"]._session_factory() as session:  # noqa: SLF001 - introspection de test
        en_attente = approvals.list_approvals(session, status="pending")
        assert len(en_attente) == 1
        # L'accord nomme bien ce qui sera fait : meme chemin, meme geste.
        assert en_attente[0].target_path == str(cible)
        assert en_attente[0].action_type == "file_delete"
        approvals.decide(session, en_attente[0].id, approved=True)

    second = s["mcp"].files_delete(str(cible), project_id=s["b"].id)
    assert second["success"] is True
    assert second["verified"] is True
    assert not cible.exists()


def test_un_accord_donne_pour_b_n_autorise_pas_la_meme_action_dans_a(surface):
    """L'accord est empreinte sur le chemin canonique : approuver la
    suppression dans B ne doit rien ouvrir dans A."""
    s = surface
    dans_a = s["racine_a"] / "secret.txt"
    dans_a.write_text("homonyme dans A")
    dans_b = s["racine_b"] / "secret.txt"

    s["mcp"].files_delete(str(dans_b), project_id=s["b"].id)
    with s["aegis"]._session_factory() as session:  # noqa: SLF001
        for entree in approvals.list_approvals(session, status="pending"):
            approvals.decide(session, entree.id, approved=True)

    resultat = s["mcp"].files_delete(str(dans_a), project_id=s["a"].id)
    assert resultat["success"] is False
    assert dans_a.exists()


# -- Chat : l'execution, pas seulement l'offre -----------------------


@pytest.mark.asyncio
async def test_le_chat_sans_projet_n_execute_aucun_outil(surface):
    """L'offre de schemas etait gardee ; l'execution ne l'etait pas."""
    from backend.tools.workspace_chat_tools import SANS_WORKSPACE, execute_workspace_tool

    s = surface
    resultat = await execute_workspace_tool(
        "workspace_read", {"path": str(s["racine_b"] / "secret.txt")},
        project_id="", project_root="")
    assert resultat == SANS_WORKSPACE


@pytest.mark.asyncio
async def test_le_chat_ne_croit_pas_la_racine_que_l_appelant_annonce(surface):
    """Usurpation de portee par la racine plutot que par l'identifiant :
    l'appelant nomme le projet A mais annonce la racine de B. Le serveur
    re-resout la racine depuis le magasin, donc le chemin relatif atterrit
    dans A — et A ne contient pas le secret de B."""
    from backend.tools.workspace_chat_tools import execute_workspace_tool

    s = surface
    resultat = await execute_workspace_tool(
        "workspace_read", {"path": "secret.txt"},
        project_id=s["a"].id, project_root=str(s["racine_b"]))
    assert "LE SECRET DE B" not in resultat
    # Et pas seulement « pas le secret » : le chemin a reellement atterri
    # dans A. Sans cette seconde assertion, n'importe quelle erreur ferait
    # passer le test — un refus pour une raison sans rapport ressemblerait
    # a une frontiere qui tient.
    assert str(s["racine_a"]) in resultat
    assert str(s["racine_b"]) not in resultat


@pytest.mark.asyncio
async def test_le_chat_avec_un_projet_autorise_lit_vraiment(surface):
    from backend.tools.workspace_chat_tools import execute_workspace_tool

    s = surface
    resultat = await execute_workspace_tool(
        "workspace_read", {"path": "secret.txt"},
        project_id=s["b"].id, project_root=str(s["racine_b"]))
    assert resultat == "LE SECRET DE B"


@pytest.mark.asyncio
async def test_un_runner_de_verification_exige_aussi_un_workspace(surface):
    """`repo_path` **est** le workspace : sans habilitation il n'y a pas
    de repertoire ou lancer quoi que ce soit. Sans ce controle, un
    `project_root=""` se resolvait sous le repertoire courant — la racine
    du depot Hermes OS."""
    from backend.tools.verification_chat_tools import execute_verification_tool
    from backend.tools.workspace_chat_tools import SANS_WORKSPACE

    resultat = await execute_verification_tool(
        "verification_run", {"runner": "pytest"}, project_id="", project_root="")
    assert resultat == SANS_WORKSPACE


# -- HTTP : la chaine complete, bout en bout ------------------------


def test_http_bout_en_bout_enregistrer_valider_puis_lire(client, tmp_path):
    """Le vrai chemin produit : POST /projects -> POST /validate ->
    GET /files/content. `tmp_path` est hors de `ALLOWED_PATHS`, donc le
    seul acces possible vient de l'habilitation du projet."""
    racine = tmp_path / "ws-http"
    racine.mkdir()
    (racine / "note.txt").write_text("contenu servi par HTTP")

    cree = client.post("/projects", json={"name": "ws-http", "root_path": str(racine)})
    assert cree.status_code == 200
    projet_id = cree.json()["id"]

    # Avant validation : aucune habilitation.
    avant = client.get("/files/content", params={
        "path": str(racine / "note.txt"), "project_id": projet_id})
    assert avant.status_code == 403

    valide = client.post(f"/projects/{projet_id}/validate")
    assert valide.status_code == 200
    assert valide.json()["validation_status"] == "valid"

    apres = client.get("/files/content", params={
        "path": str(racine / "note.txt"), "project_id": projet_id})
    assert apres.status_code == 200
    assert apres.json()["content"] == "contenu servi par HTTP"


def test_http_sans_project_id_ne_lit_pas_le_workspace_valide(client, tmp_path):
    """Le defaut A-4 sur la surface HTTP : le projet est valide, mais la
    requete ne le nomme pas."""
    racine = tmp_path / "ws-http2"
    racine.mkdir()
    (racine / "note.txt").write_text("contenu")
    projet_id = client.post(
        "/projects", json={"name": "ws-http2", "root_path": str(racine)}).json()["id"]
    client.post(f"/projects/{projet_id}/validate")

    reponse = client.get("/files/content", params={"path": str(racine / "note.txt")})
    assert reponse.status_code == 403


def test_http_le_listing_d_un_workspace_autorise_fonctionne(client, tmp_path):
    """La navigation du workspace — `GET /files` — passe par la meme
    autorite. Sans elle, « voir ce qu'il y a dans mon dossier » serait un
    second chemin vers le disque."""
    racine = tmp_path / "ws-http3"
    racine.mkdir()
    (racine / "un.txt").write_text("1")
    (racine / "deux.txt").write_text("2")
    projet_id = client.post(
        "/projects", json={"name": "ws-http3", "root_path": str(racine)}).json()["id"]
    client.post(f"/projects/{projet_id}/validate")

    refuse = client.get("/files", params={"path": str(racine)})
    assert refuse.status_code == 403

    liste = client.get("/files", params={"path": str(racine), "project_id": projet_id})
    assert liste.status_code == 200
    assert sorted(liste.json()) == ["deux.txt", "un.txt"]
