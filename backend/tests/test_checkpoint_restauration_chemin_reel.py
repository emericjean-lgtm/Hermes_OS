# -*- coding: utf-8 -*-
"""Un opérateur peut réellement revenir en arrière (A-3, HOS-291).

## Le défaut que ces tests empêchent de revenir

A-3 est ouvert depuis HOS-223 et a été remesuré à chaque audit : `prendre`
avait **un** appelant — `GraphExecutor._prendre_le_filet`, qui pose un filet
avant que toute mission touche au disque — et `restaurer` en avait **zéro**.
Aucune route, aucun outil MCP, aucun script. Le dépôt prenait donc un point
de reprise par mission, les affichait dans le Center « Supervision », et ne
savait y revenir par aucun chemin.

`test_checkpoints.py` couvrait déjà la primitive. Ce qu'il ne pouvait pas
couvrir, parce que rien ne l'appelait, c'est le **chemin** : la route, le
faux Aegis remplacé par le vrai, la file d'accord réelle, et la reprise
après redémarrage. C'est exactement l'écart que le §0 de la roadmap nomme
entre `CALLED` et `ACTUALLY USED`.

## Le vrai Aegis, pas un double

Ces tests montent `AegisAgent` sur `config/security.yaml` réel. C'est
délibéré et c'est le cœur de la preuve : un double qui rend `ALLOW` ne
dirait rien du système livré, où `data_migration` est
`mandatory_validation` et où le premier appel **ne restaure jamais**. La
restauration est en deux temps par construction, et un test qui
l'ignorerait mesurerait un contrat que personne n'a.
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.agents.aegis import AegisAgent
from backend.checkpoints import checkpoint as cp
from backend.core import etat
from backend.core.config import get_settings
from backend.core.message_bus import get_message_bus
from backend.core.router import ModelRouter
from backend.projects.store import get_project_store
from backend.security.aegis_engine import Verdict


@pytest.fixture
def monde(monkeypatch, tmp_path, fake_ollama_client, models_config,
          security_config):
    """Une racine d'état jetable, un workspace, et le vrai Aegis.

    `HERMES_DATA_DIR` est redirigé : sans ça les points de reprise de ces
    tests s'écriraient dans la racine d'état **réelle** de la machine, à
    côté de ceux des missions de l'opérateur. Un test qui pollue le
    magasin qu'il prétend protéger est un mauvais test.
    """
    racine_etat = tmp_path / "etat"
    workspace = tmp_path / "ws"
    (workspace / "sous").mkdir(parents=True)
    (workspace / "a.txt").write_text("version 1", encoding="utf-8")
    (workspace / "sous" / "b.txt").write_text("profond", encoding="utf-8")

    monkeypatch.setenv("HERMES_DATA_DIR", str(racine_etat))
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("SNAPSHOT_DIR", str(tmp_path / "snapshots"))
    # `ALLOWED_PATHS` couvre le workspace pour que ces tests ressemblent à
    # l'installation réelle. Il ne **décide** rien ici : mesuré,
    # `data_migration` est `path_based: false`, donc la liste blanche
    # n'est pas consultée pour cette catégorie — voir
    # `test_le_seul_verrou_de_la_restauration_est_l_accord_humain`.
    monkeypatch.setenv("ALLOWED_PATHS", str(tmp_path))
    monkeypatch.setattr("backend.agents.aegis.load_security_config",
                        lambda: security_config)

    etat.racine.cache_clear()
    get_settings.cache_clear()
    get_message_bus.cache_clear()
    get_project_store.cache_clear()

    agent = AegisAgent(fake_ollama_client, ModelRouter(models_config),
                       models_config)

    app = FastAPI()
    from backend.api.routes import checkpoints as routes_checkpoints

    app.dependency_overrides = {}
    monkeypatch.setattr(routes_checkpoints, "_aegis", lambda: agent)
    app.include_router(routes_checkpoints.router, prefix="/api/v1")

    try:
        yield TestClient(app), workspace, agent
    finally:
        etat.racine.cache_clear()
        get_settings.cache_clear()
        get_message_bus.cache_clear()
        get_project_store.cache_clear()


def _accorder(agent: AegisAgent) -> str:
    """Jouer le « oui » de l'humain sur la demande en attente.

    Passe par `decide_approval`, la même méthode que
    `POST /api/v1/security/approvals/{id}` appelle : approuver en écrivant
    dans la table contournerait le chemin qu'on prétend prouver.
    """
    en_attente = [a for a in agent.list_approvals(status="pending")]
    assert len(en_attente) == 1, f"attendu une demande, vu {en_attente}"
    agent.decide_approval(en_attente[0]["id"], approved=True)
    return en_attente[0]["id"]


# ═══ Le chemin réel, de bout en bout ═════════════════════════════════

def test_le_chemin_complet_apercu_accord_restauration(monde):
    """Le geste que A-3 rendait impossible, du premier appel au disque.

    L'ordre compte et il est vérifié à chaque étape : un aperçu qui ne
    mute rien, un premier appel **refusé** qui ne mute rien non plus, un
    accord humain, puis la restauration.
    """
    client, workspace, agent = monde
    point = cp.prendre(str(workspace), motif="avant la mission",
                       avec_etat=False)

    # La mission saccage le workspace.
    (workspace / "a.txt").write_text("saccage", encoding="utf-8")
    (workspace / "apparu.txt").write_text("créé après", encoding="utf-8")

    # 1. L'aperçu ne touche à rien, et nomme ce qui sera détruit.
    vue = client.get(f"/api/v1/checkpoints/{point.identifiant}/apercu")
    assert vue.status_code == 200
    assert vue.json()["a_restaurer"] == ["a.txt"]
    assert vue.json()["a_supprimer"] == ["apparu.txt"]
    assert vue.json()["applique"] is False
    assert (workspace / "a.txt").read_text(encoding="utf-8") == "saccage"
    assert (workspace / "apparu.txt").exists()

    # 2. Premier appel : Aegis dépose un accord à décider, rien ne bouge.
    premier = client.post(
        f"/api/v1/checkpoints/{point.identifiant}/restaurer", json={})
    assert premier.status_code == 200
    assert premier.json()["restaure"] is False
    assert premier.json()["verdict"] == "require_human_validation"
    assert premier.json()["accord_a_decider"] is True
    assert (workspace / "a.txt").read_text(encoding="utf-8") == "saccage", (
        "le workspace a bougé alors qu'aucun humain n'avait décidé")

    # 3. L'humain décide.
    _accorder(agent)

    # 4. Second appel : l'accord est consommé, le workspace revient.
    second = client.post(
        f"/api/v1/checkpoints/{point.identifiant}/restaurer", json={})
    assert second.status_code == 200, second.text
    assert second.json()["restaure"] is True
    assert second.json()["verdict"] == "allow"
    assert (workspace / "a.txt").read_text(encoding="utf-8") == "version 1"
    assert (workspace / "sous" / "b.txt").read_text(encoding="utf-8") == "profond"


def test_l_accord_est_a_usage_unique(monde):
    """Un « oui » autorise **une** restauration, pas un droit permanent.

    Sans quoi un accord donné une fois transformerait la restauration en
    geste libre pour tout le reste de la session.
    """
    client, workspace, agent = monde
    point = cp.prendre(str(workspace), avec_etat=False)

    client.post(f"/api/v1/checkpoints/{point.identifiant}/restaurer", json={})
    _accorder(agent)
    assert client.post(
        f"/api/v1/checkpoints/{point.identifiant}/restaurer",
        json={}).json()["restaure"] is True

    # Le suivant repart de zéro.
    rejoue = client.post(
        f"/api/v1/checkpoints/{point.identifiant}/restaurer", json={})
    assert rejoue.json()["restaure"] is False
    assert rejoue.json()["accord_a_decider"] is True


def test_un_accord_n_autorise_que_son_point_de_reprise(monde):
    """Le défaut mesuré avant HOS-291, et la raison du discriminant.

    L'empreinte d'approbation ignore la description depuis HOS-224 : sans
    discriminant, deux points de reprise du même workspace la partagent.
    Un « oui » pour revenir cinq minutes en arrière autorisait alors de
    revenir trois semaines en arrière — sur un geste qui détruit tout ce
    qui a été fait depuis.
    """
    client, workspace, agent = monde
    recent = cp.prendre(str(workspace), motif="il y a cinq minutes",
                        avec_etat=False)
    (workspace / "a.txt").write_text("trois semaines de travail",
                                     encoding="utf-8")
    ancien = cp.prendre(str(workspace), motif="il y a trois semaines",
                        avec_etat=False)

    # L'humain accorde la restauration du **récent**.
    client.post(f"/api/v1/checkpoints/{recent.identifiant}/restaurer", json={})
    _accorder(agent)

    # Cet accord ne doit pas ouvrir l'autre.
    autre = client.post(
        f"/api/v1/checkpoints/{ancien.identifiant}/restaurer", json={})
    assert autre.json()["restaure"] is False, (
        "l'accord donné pour un point de reprise en a ouvert un autre")
    assert autre.json()["accord_a_decider"] is True


# ═══ Ce qui ne doit rien changer ═════════════════════════════════════

def test_un_point_de_reprise_inconnu_ne_change_rien(monde):
    """Un identifiant inventé rend 404 et laisse le disque tranquille."""
    client, workspace, _ = monde
    (workspace / "a.txt").write_text("intact", encoding="utf-8")

    assert client.get(
        "/api/v1/checkpoints/jamais-pris/apercu").status_code == 404
    assert client.post(
        "/api/v1/checkpoints/jamais-pris/restaurer", json={}).status_code == 404
    assert (workspace / "a.txt").read_text(encoding="utf-8") == "intact"


def test_un_point_de_reprise_abime_refuse_avant_d_ecrire(monde):
    """Une copie corrompue ne doit pas produire un troisième état.

    Ni l'ancien ni le nouveau : le pire des trois, et celui qu'on ne sait
    pas défaire. `repli_fichiers.restaurer` vérifie les empreintes
    **avant** d'écrire quoi que ce soit.
    """
    client, workspace, agent = monde
    point = cp.prendre(str(workspace), avec_etat=False)
    (workspace / "a.txt").write_text("saccage", encoding="utf-8")

    copie = etat.racine() / cp.DOSSIER / point.identifiant / "contenu" / "a.txt"
    copie.write_text("la copie a pourri", encoding="utf-8")

    client.post(f"/api/v1/checkpoints/{point.identifiant}/restaurer", json={})
    _accorder(agent)
    reponse = client.post(
        f"/api/v1/checkpoints/{point.identifiant}/restaurer", json={})

    assert reponse.status_code == 409
    assert (workspace / "a.txt").read_text(encoding="utf-8") == "saccage", (
        "une copie abîmée a tout de même été écrite dans le workspace")


def test_le_seul_verrou_de_la_restauration_est_l_accord_humain(monde,
                                                               monkeypatch):
    """Ce que la liste blanche fait ici, et ce qu'elle ne fait **pas**.

    Première sonde de cette passe : elle affirmait qu'un workspace hors
    `ALLOWED_PATHS` produirait un `DENY` dur, comme pour une écriture de
    fichier. **Faux, et c'est la sonde qui avait tort.** Mesuré :
    `data_migration` est `path_based: false` dans `config/security.yaml`,
    donc `AegisEngine` ne confronte jamais `target_path` à la liste
    blanche pour cette catégorie. Le chemin porté par la demande sert à
    l'empreinte d'approbation, pas à une frontière.

    Le contrôle réel est donc **entièrement** la validation humaine
    obligatoire — ce test le pin pour qu'on cesse de croire à une seconde
    barrière qui n'existe pas. L'écart est enregistré comme A-22 : le
    corriger en basculant la catégorie en `path_based` refuserait du même
    coup **toute** restauration d'instantané, qui passe `target_path=None`
    (mesuré : `deny`). C'est une décision de politique à part entière, pas
    un effet de bord d'A-3.
    """
    client, workspace, agent = monde
    point = cp.prendre(str(workspace), avec_etat=False)
    (workspace / "a.txt").write_text("saccage", encoding="utf-8")

    monkeypatch.setenv("ALLOWED_PATHS", str(workspace.parent / "ailleurs"))
    get_settings.cache_clear()
    agent_hors = AegisAgent(agent._ollama, agent._router, agent._models_config)
    from backend.api.routes import checkpoints as routes_checkpoints

    monkeypatch.setattr(routes_checkpoints, "_aegis", lambda: agent_hors)

    reponse = client.post(
        f"/api/v1/checkpoints/{point.identifiant}/restaurer", json={})

    # Pas un DENY : un accord à décider, comme partout ailleurs.
    assert reponse.json()["verdict"] == Verdict.REQUIRE_HUMAN_VALIDATION.value
    # Et surtout : rien n'a bougé sans qu'un humain ait dit oui.
    assert reponse.json()["restaure"] is False
    assert (workspace / "a.txt").read_text(encoding="utf-8") == "saccage"


def test_le_couple_demande_deux_accords_et_le_dit(monde):
    """Les deux moitiés ont deux empreintes, donc deux accords. Mesuré.

    Le point de reprise est identifié par `{"checkpoint": …}` et son
    instantané par `{"snapshot": …}` : l'accord donné pour l'un ne couvre
    pas l'autre. Ce test **pin** ce contrat plutôt que de le corriger,
    pour deux raisons.

    D'abord parce que l'unifier demanderait de toucher au contrôle de
    `snapshot_manager.restore_snapshot`, que d'autres appelants utilisent
    — une route et un outil MCP — donc une décision de politique à part
    entière. C'est enregistré comme A-23.

    Ensuite parce que le seul producteur réel de points de reprise,
    `GraphExecutor._prendre_le_filet`, prend `avec_etat=False` : aucun
    point de reprise de production ne porte d'instantané, et ce chemin-ci
    n'est donc atteint par personne aujourd'hui.

    Ce qui compte, et que ce test garantit : la réponse **ne ment pas**.
    Elle dit que l'état n'a pas été repris, et pourquoi.
    """
    client, workspace, agent = monde
    point = cp.prendre(str(workspace), motif="le couple", avec_etat=True)
    assert point.instantane, "sans instantané ce test ne mesure rien"

    (workspace / "a.txt").write_text("saccage", encoding="utf-8")
    client.post(f"/api/v1/checkpoints/{point.identifiant}/restaurer", json={})
    _accorder(agent)
    reponse = client.post(
        f"/api/v1/checkpoints/{point.identifiant}/restaurer", json={}).json()

    # Les fichiers sont revenus.
    assert reponse["restaure"] is True
    assert (workspace / "a.txt").read_text(encoding="utf-8") == "version 1"

    # L'état, non — et la réponse le dit, avec le geste qui débloque.
    assert reponse["etat_repris"] is False
    assert "accord distinct" in reponse["etat_non_repris"]
    assert point.instantane in reponse["etat_non_repris"]

    # Le second accord attend bien dans la file, nommé par l'instantané.
    en_attente = agent.list_approvals(status="pending")
    assert len(en_attente) == 1
    assert point.instantane in en_attente[0]["discriminants"]


# ═══ Il n'y a qu'une porte ═══════════════════════════════════════════

def test_la_vue_d_operations_reste_en_lecture(monde):
    """La restauration n'a pas ouvert une seconde porte dans la vue.

    `routes/operations.py` est en lecture seule par contrat, et deux
    gardes le tiennent. HOS-291 y ajoute un geste mutant **à côté**, sur
    son propre routeur, précisément pour ne pas faire de Mission Control
    un second chemin vers l'état.
    """
    from backend.api.routes import operations

    for route in operations.router.routes:
        assert set(getattr(route, "methods", set())) <= {"GET", "HEAD"}, (
            f"{route.path} mute depuis la vue d'opérations")


def test_toute_restauration_passe_par_aegis(monde):
    """Aucun chemin de `backend.checkpoints` ne restaure sans décision.

    Garde sur l'arbre syntaxique plutôt que sur le texte : une recherche
    de sous-chaîne s'est déjà accrochée quatre fois à un commentaire dans
    ce dépôt. Ce qui est vérifié est que `restaurer` — la seule fonction
    publique qui écrit dans le workspace — appelle `aegis.evaluate` et
    compare le verdict avant d'appeler le moindre `restaurer` de bas
    niveau.
    """
    import ast
    import inspect

    arbre = ast.parse(inspect.getsource(cp.restaurer))
    appels = [ast.unparse(n.func) for n in ast.walk(arbre)
              if isinstance(n, ast.Call)]
    assert "aegis.evaluate" in appels

    corps = ast.unparse(arbre)
    garde = corps.index("decision.verdict is not Verdict.ALLOW")
    for bas_niveau in ("git_ref.restaurer", "repli_fichiers.restaurer"):
        assert corps.index(bas_niveau) > garde, (
            f"{bas_niveau} est appelé avant le contrôle d'Aegis")
