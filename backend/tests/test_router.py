from __future__ import annotations

import pytest

from backend.core.router import ModelRouter, UnknownTaskTypeError


def test_prefers_already_loaded_model(models_config):
    router = ModelRouter(models_config)
    # the orchestrator model is a lower-priority candidate for
    # "conversation" than standard/swift — proves "already loaded" wins
    # over priority order, not just that the top candidate got picked.
    orchestrator_model = models_config["roles"]["orchestrator"]["model"]
    decision = router.select_model("conversation", loaded_models=[orchestrator_model])
    assert decision.model == orchestrator_model
    assert "already loaded" in decision.reason


def test_default_priority_without_vram_info(models_config):
    router = ModelRouter(models_config)
    decision = router.select_model("conversation")
    assert decision.role == "standard"
    assert "no VRAM constraint" in decision.reason


#: Configuration synthétique, délibérément pas celle de production.
#:
#: Ces deux tests vérifiaient la politique VRAM du routeur en s'appuyant sur
#: les tailles réelles de `code` et `code_agentic` — 17 Go contre 14. Quand
#: HOS-108 a réaffecté les deux rôles au même modèle mesuré meilleur, les
#: tailles sont devenues identiques, le « plus petit candidat » ambigu, et
#: les tests rouges alors que le routeur n'avait pas changé d'une ligne.
#:
#: Un test de politique ne doit pas dépendre du catalogue du jour : sinon il
#: se casse à chaque mesure et finit par être corrigé au lieu d'être lu.
#: Les tests voisins gardent `models_config` à dessein — eux vérifient que
#: la configuration réelle est cohérente, ce qui est une autre question.
POLITIQUE_VRAM = {
    "roles": {
        "gros": {"model": "gros:1b", "tier": "quality", "vram_gb": 17},
        "moyen": {"model": "moyen:1b", "tier": "quality", "vram_gb": 14},
    },
    "routing": {"code_generation": ["gros", "moyen"]},
}


def test_respects_vram_budget():
    router = ModelRouter(POLITIQUE_VRAM)
    # 5 Go ne suffisent à aucun des deux candidats.
    decision = router.select_model("code_generation", available_vram_gb=5)

    assert decision.reason.startswith("no candidate fits")
    # On se rabat sur le plus petit, en le signalant.
    assert decision.role == "moyen"


def test_picks_candidate_that_fits():
    router = ModelRouter(POLITIQUE_VRAM)
    # 15 Go : seul le moyen tient, alors qu'il est second dans l'ordre de
    # priorité — c'est la contrainte VRAM qui doit l'emporter.
    decision = router.select_model("code_generation", available_vram_gb=15)

    assert decision.role == "moyen"
    assert "fits available VRAM" in decision.reason


def test_unknown_task_type_raises(models_config):
    router = ModelRouter(models_config)
    with pytest.raises(UnknownTaskTypeError):
        router.select_model("not_a_real_task_type")


def test_model_for_role_resolves_directly(models_config):
    router = ModelRouter(models_config)
    assert router.model_for_role("security") == models_config["roles"]["security"]["model"]
