"""Un `project_id` qui ne resout pas ne doit pas court-circuiter la
frontiere de chemin (HOS-292, absorbe pendant A-4).

Mesure du 2026-09-11, `ALLOWED_PATHS` reduit a un seul dossier, cible
**hors** de toute liste blanche :

    project_id=None              -> deny
    project_id=''                -> require_human_validation
    project_id='inexistant-xyz'  -> require_human_validation
    puis un seul accord humain   -> allow

`_resolve_decision` rendait REQUIRE_HUMAN_VALIDATION *sans jamais appeler
le moteur* quand le projet etait introuvable, et `_apply_human_consent`
transforme un REQUIRE_HUMAN_VALIDATION approuve en ALLOW. Un projet qui
n'existe pas ouvrait donc n'importe quel chemin du disque au premier
« oui ». Le commentaire de `_apply_human_consent` promettait pourtant
l'inverse — « A DENY is never upgraded: those come from the hard
boundaries » — et il disait vrai : la frontiere n'etait simplement jamais
consultee, donc il n'y avait pas de DENY a ne pas relever.

Le `''` compte double : c'est ce que **MCP** transmet pour un argument
`project_id` omis, mesure sur une vraie session streamable-HTTP. Tout
appel MCP non nomme deposait donc un accord en attente au lieu d'etre
refuse — et polluait la file de validation de l'operateur.

Ce que ce fichier ne change pas : un identifiant inconnu sur un chemin
*legitime* reste suspect et continue d'escalader. On ne veut pas taire la
suspicion, on veut qu'elle ne serve pas d'echelle.
"""
from __future__ import annotations

import pytest

from backend.agents.aegis import AegisAgent
from backend.core.config import get_settings
from backend.core.message_bus import get_message_bus
from backend.core.router import ModelRouter
from backend.projects.store import get_project_store
from backend.security import approvals
from backend.security.aegis_engine import ActionRequest, Verdict


@pytest.fixture
def aegis(monkeypatch, fake_ollama_client, models_config, security_config, tmp_path):
    statique = tmp_path / "statique"
    statique.mkdir()
    (statique / "legitime.txt").write_text("dans la liste blanche")
    ailleurs = tmp_path / "tres_loin"
    ailleurs.mkdir()
    (ailleurs / "prive.txt").write_text("HORS DE TOUTE LISTE BLANCHE")

    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("ALLOWED_PATHS", str(statique))
    get_settings.cache_clear()
    get_message_bus.cache_clear()
    get_project_store.cache_clear()
    monkeypatch.setattr("backend.agents.aegis.load_security_config", lambda: security_config)

    agent = AegisAgent(fake_ollama_client, ModelRouter(models_config), models_config)
    try:
        yield agent, statique, ailleurs
    finally:
        get_settings.cache_clear()
        get_message_bus.cache_clear()
        get_project_store.cache_clear()


def _lire(agent, cible, pid):
    return agent.evaluate(ActionRequest(
        action_type="file_read", description="read", target_path=str(cible),
        requesting_agent="test", project_id=pid))


@pytest.mark.parametrize("pid", [None, "", "inexistant-xyz"])
def test_un_chemin_hors_liste_blanche_est_refuse_quel_que_soit_le_projet(aegis, pid):
    agent, _statique, ailleurs = aegis
    assert _lire(agent, ailleurs / "prive.txt", pid).verdict is Verdict.DENY


@pytest.mark.parametrize("pid", [None, "", "inexistant-xyz"])
def test_un_refus_de_frontiere_ne_depose_aucun_accord_a_signer(aegis, pid):
    """Ce qui rendait l'escalade possible : l'action etait mise en file.
    Proposer a l'operateur d'autoriser un chemin hors de toute liste
    blanche, c'est fabriquer l'echelle et la lui tendre."""
    agent, _statique, ailleurs = aegis
    _lire(agent, ailleurs / "prive.txt", pid)
    with agent._session_factory() as session:  # noqa: SLF001 - introspection de test
        assert approvals.list_approvals(session, status="pending") == []


def test_meme_approuve_de_force_un_chemin_hors_frontiere_reste_refuse(aegis):
    """Le scenario complet d'origine, rejoue : on accorde tout ce qui
    traine, puis on redemande. La frontiere dure n'est pas negociable."""
    agent, _statique, ailleurs = aegis
    _lire(agent, ailleurs / "prive.txt", "inexistant-xyz")
    with agent._session_factory() as session:  # noqa: SLF001
        for entree in approvals.list_approvals(session, status="pending"):
            approvals.decide(session, entree.id, approved=True)

    assert _lire(agent, ailleurs / "prive.txt",
                 "inexistant-xyz").verdict is Verdict.DENY


def test_la_suspicion_est_conservee_sur_un_chemin_legitime(aegis):
    """Le contrat qu'on ne veut PAS perdre : sur un chemin que le moteur
    aurait laisse passer, un identifiant de projet inconnu continue
    d'escalader plutot que de se taire (§17.3)."""
    agent, statique, _ailleurs = aegis
    decision = _lire(agent, statique / "legitime.txt", "inexistant-xyz")
    assert decision.verdict is Verdict.REQUIRE_HUMAN_VALIDATION
    assert "does not resolve" in decision.reason


def test_un_projet_vide_n_est_pas_un_projet_inconnu(aegis):
    """`''` (ce que MCP transmet pour un argument omis) doit se comporter
    comme `None` — aucune habilitation — et non comme un identifiant
    inconnu, qui lui est suspect."""
    agent, statique, _ailleurs = aegis
    vide = _lire(agent, statique / "legitime.txt", "")
    aucun = _lire(agent, statique / "legitime.txt", None)
    assert vide.verdict is aucun.verdict is Verdict.ALLOW
