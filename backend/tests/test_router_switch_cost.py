"""Une décision de routage dit ce qu'elle coûte (HOS-114).

Sur 16 Go avec `OLLAMA_MAX_LOADED_MODELS=1`, changer de modèle coûte entre
4,5 et 24,1 secondes — mesuré, pas estimé. Le routeur arbitrait sans le
savoir, et rien dans le journal d'audit ne disait ce qu'un arbitrage avait
coûté. Un choix qu'on ne peut pas chiffrer après coup ne peut pas se
corriger.

Ces tests portent sur le fait que le chiffre soit *juste et présent sur
les quatre chemins de sortie*, pas sur la valeur de la grille — celle-ci
vit dans `config/models.yaml` et se remesure avec `switch_bench.py`.
"""
from __future__ import annotations

import pytest

from backend.core.router import ModelRouter

CONFIG = {
    "roles": {
        "swift": {"model": "petit", "tier": "turbo", "vram_gb": 2, "num_ctx": 16384},
        "standard": {"model": "moyen", "tier": "standard", "vram_gb": 13, "num_ctx": 262144},
        "orchestrator": {"model": "gros", "tier": "powerful", "vram_gb": 13, "num_ctx": 65536},
    },
    "routing": {
        "conversation": ["standard", "swift", "orchestrator"],
        "classification": ["swift"],
    },
    "bascule_s": {"petit": 4.5, "moyen": 15.3, "gros": 20.9},
}


@pytest.fixture
def router() -> ModelRouter:
    return ModelRouter(CONFIG)


class TestLeCoutEstPorteParLaDecision:
    def test_un_modele_deja_resident_ne_coute_rien(self, router):
        decision = router.select_model("conversation", loaded_models=["gros"],
                                       available_vram_gb=16)

        assert decision.model == "gros"
        assert decision.switch_cost_s == 0.0

    def test_un_modele_a_charger_coute_son_prix_mesure(self, router):
        decision = router.select_model("conversation", loaded_models=[],
                                       available_vram_gb=16)

        assert decision.model == "moyen"
        assert decision.switch_cost_s == pytest.approx(15.3)

    def test_le_prix_suit_le_modele_choisi_et_non_le_premier_candidat(self, router):
        """`conversation` liste `standard` en tête, mais 3 Go de VRAM ne
        laissent passer que `swift` : c'est son prix qui doit être rapporté."""
        decision = router.select_model("conversation", loaded_models=[],
                                       available_vram_gb=3)

        assert decision.model == "petit"
        assert decision.switch_cost_s == pytest.approx(4.5)


class TestLesQuatreCheminsDeSortie:
    """`select_model` a quatre sorties. En renseigner trois livrerait un
    champ juste seulement parfois — la forme exacte du défaut
    `first_token_ms`, que ce module a déjà connu."""

    def test_chemin_residence(self, router):
        d = router.select_model("conversation", loaded_models=["moyen"], available_vram_gb=16)
        assert d.reason.startswith("model already loaded")
        assert d.switch_cost_s == 0.0

    def test_chemin_tient_en_vram(self, router):
        d = router.select_model("conversation", loaded_models=[], available_vram_gb=16)
        assert "fits available VRAM" in d.reason
        assert d.switch_cost_s > 0

    def test_chemin_rien_ne_tient(self, router):
        d = router.select_model("conversation", loaded_models=[], available_vram_gb=0.5)
        assert "downgraded to smallest" in d.reason
        assert d.switch_cost_s == pytest.approx(4.5)

    def test_chemin_sans_information_vram(self, router):
        d = router.select_model("conversation", loaded_models=[], available_vram_gb=None)
        assert "no VRAM constraint" in d.reason
        assert d.switch_cost_s == pytest.approx(15.3)


class TestUnModeleNonMesure:
    def test_vaut_zero_et_non_une_estimation(self):
        """Un zéro se repère dans le journal ; une estimation s'y
        confondrait avec une mesure. C'est la même règle que partout
        ailleurs dans ce dépôt : on ne fabrique pas un chiffre."""
        config = {**CONFIG, "bascule_s": {"petit": 4.5}}
        decision = ModelRouter(config).select_model(
            "conversation", loaded_models=[], available_vram_gb=16)

        assert decision.model == "moyen"
        assert decision.switch_cost_s == 0.0

    def test_une_grille_absente_ne_casse_pas_le_routage(self):
        config = {k: v for k, v in CONFIG.items() if k != "bascule_s"}
        decision = ModelRouter(config).select_model(
            "conversation", loaded_models=[], available_vram_gb=16)

        assert decision.model == "moyen"
        assert decision.switch_cost_s == 0.0


class TestLaGrilleReelle:
    def test_les_six_modeles_routes_ont_un_prix(self):
        """Un modèle routable sans prix mesuré rendrait le champ muet
        précisément là où il sert."""
        from backend.core.config import load_models_config

        config = load_models_config()
        grille = config.get("bascule_s") or {}
        routes = {config["roles"][r]["model"]
                  for candidats in config["routing"].values() for r in candidats}
        # L'embedding n'est pas un modèle de conversation : il ne se charge
        # pas par bascule de routage et n'a donc pas de prix ici.
        routes = {m for m in routes if "embedding" not in m}

        assert routes <= set(grille), f"sans prix mesuré : {sorted(routes - set(grille))}"
