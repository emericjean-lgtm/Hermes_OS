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


#: L'incident, en configuration minimale. `conversation` prefere `standard`
#: mais accepte `swift` comme repli bon marche et `orchestrator` comme
#: alternative plus chere : la liste est ordonnee par coût, pas par qualite.
REUTILISATION = {
    "roles": {
        "standard": {"model": "std:1b", "tier": "standard", "vram_gb": 6},
        "swift": {"model": "swift:1b", "tier": "turbo", "vram_gb": 2},
        "orchestrator": {"model": "orch:1b", "tier": "quality", "vram_gb": 13},
        "bizarre": {"model": "biz:1b", "tier": "inconnu", "vram_gb": 2},
    },
    "routing": {"conversation": ["standard", "swift", "orchestrator"],
                "etrange": ["standard", "bizarre"]},
}


def test_un_modele_resident_plus_faible_ne_prend_pas_la_conversation():
    """L'incident que cette regle empeche.

    Avec OLLAMA_MAX_LOADED_MODELS=1, un seul modele est resident. Une
    extraction servie par `swift` le laissait charge, et la conversation
    suivante lui revenait — 2,6 Md au lieu du modele standard, sans autre
    trace qu'un motif « already loaded ». La qualite de la reponse dependait
    de l'ordre d'arrivee des taches.
    """
    decision = ModelRouter(REUTILISATION).select_model(
        "conversation", loaded_models=["swift:1b"], available_vram_gb=8)

    assert decision.role == "standard"
    assert "fits available VRAM" in decision.reason


def test_un_modele_resident_plus_fort_est_reutilise():
    """Le symetrique, et c'est pour lui que la regle existe : reutiliser
    l'orchestrateur est une montee en gamme gratuite, pas une degradation.
    Le bloquer ferait payer un rechargement pour un moins bon resultat."""
    decision = ModelRouter(REUTILISATION).select_model(
        "conversation", loaded_models=["orch:1b"], available_vram_gb=8)

    assert decision.role == "orchestrator"
    assert "already loaded" in decision.reason


def test_un_resident_de_meme_niveau_est_reutilise():
    decision = ModelRouter(REUTILISATION).select_model(
        "conversation", loaded_models=["std:1b"], available_vram_gb=8)

    assert decision.role == "standard"
    assert "already loaded" in decision.reason


def test_si_rien_ne_tient_en_vram_le_resident_l_emporte_quand_meme():
    """Quand tout va deborder, un modele deja en place bat un modele qu'il
    faudrait charger pour le voir deborder aussi — le rechargement coûte
    11 a 27 s mesurees, et n'achete rien ici."""
    decision = ModelRouter(REUTILISATION).select_model(
        "conversation", loaded_models=["swift:1b"], available_vram_gb=1)

    assert decision.role == "swift"
    assert "already loaded" in decision.reason


def test_un_tier_inconnu_ne_donne_pas_le_raccourci():
    """La regle ne fait qu'autoriser une reutilisation. Face a un tier
    qu'elle ne sait pas comparer, elle doit refuser plutot que supposer :
    deviner dans le sens permissif reintroduirait la degradation silencieuse
    qu'elle existe pour empecher."""
    decision = ModelRouter(REUTILISATION).select_model(
        "etrange", loaded_models=["biz:1b"], available_vram_gb=8)

    assert decision.role == "standard"


def test_unknown_task_type_raises(models_config):
    router = ModelRouter(models_config)
    with pytest.raises(UnknownTaskTypeError):
        router.select_model("not_a_real_task_type")


def test_model_for_role_resolves_directly(models_config):
    router = ModelRouter(models_config)
    assert router.model_for_role("security") == models_config["roles"]["security"]["model"]
