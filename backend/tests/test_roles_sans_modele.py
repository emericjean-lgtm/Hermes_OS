"""« Non résident » et « absent » ne sont pas la même chose (HOS-139).

`OLLAMA_MAX_LOADED_MODELS` vaut 1 sur cette machine : à tout instant, tous
les rôles sauf un sont légitimement `loaded: false`. C'est le cas **normal**,
pas une anomalie.

Un rôle dont le modèle a été supprimé d'Ollama affichait exactement la même
chose. Le rôle `standard` — « conversation générale, écriture, extraction »,
le plus sollicité — est ainsi resté cassé sans que rien ne le signale,
jusqu'à ce qu'une mission le demande et reçoive un 404. La suppression était
de mon fait, et l'invisibilité est ce qui la rendait coûteuse.

`installe` répond à la question qu'aucun champ ne posait, et distingue un
troisième état : `None` quand Ollama est injoignable. « On ne sait pas »
n'est pas « absent » — afficher un rôle comme cassé faute d'avoir pu
demander serait un faux négatif, la classe de défaut qui a coûté le plus
cher à ce projet.
"""
from __future__ import annotations

import pytest

from backend.api.routes.system import _est_installe


class TestLaToleranceDeNommage:
    """Ollama rend `<nom>:latest` pour une référence sans tag. Comparer
    strictement déclarerait absent un modèle présent."""

    @pytest.mark.parametrize("tag,installes,attendu", [
        ("lfm2.5-2.6b-125k", {"lfm2.5-2.6b-125k:latest"}, True),
        ("qwen3-embedding:0.6b", {"qwen3-embedding:0.6b"}, True),
        ("ornith-9b-256k", {"gemma4-12b-256k:latest"}, False),
        ("", set(), False),
    ])
    def test_correspondance(self, tag, installes, attendu):
        assert _est_installe(tag, installes) is attendu


class TestOllamaInjoignable:
    def test_on_ne_sait_pas_n_est_pas_absent(self, monkeypatch):
        """`None` plutôt que l'ensemble vide : un ensemble vide ferait
        passer **tous** les rôles pour cassés d'un coup, sur la seule foi
        d'un Ollama momentanément muet."""
        import asyncio

        from backend.api.routes import system

        class _ClientMuet:
            def __init__(self, *a, **k):
                pass

            async def list_local_models(self):
                raise ConnectionError("Ollama injoignable")

            async def aclose(self):
                return None

        monkeypatch.setattr("backend.connectors.ollama_client.OllamaClient",
                            _ClientMuet)

        assert asyncio.run(system._modeles_ollama()) is None

    def test_une_reponse_porte_les_dicts_complets(self, monkeypatch):
        """`_modeles_ollama` rend les dicts d'Ollama tels quels, capacités
        comprises — la route en a besoin pour distinguer un modèle
        utilisable dans le chat (`completion`) d'un modèle d'embedding."""
        import asyncio

        from backend.api.routes import system

        class _Client:
            def __init__(self, *a, **k):
                pass

            async def list_local_models(self):
                return [{"name": "lfm2.5-2.6b-125k:latest", "capabilities": ["completion"]},
                        {"name": "qwen3-embedding:0.6b", "capabilities": ["embedding"]}]

            async def aclose(self):
                return None

        monkeypatch.setattr("backend.connectors.ollama_client.OllamaClient",
                            _Client)

        modeles = asyncio.run(system._modeles_ollama())
        installes = {m["name"] for m in modeles}

        assert _est_installe("lfm2.5-2.6b-125k", installes)
        assert not _est_installe("ornith-9b-256k", installes)
        assert next(m for m in modeles if m["name"] == "qwen3-embedding:0.6b")["capabilities"] == ["embedding"]


class TestLesModelesHorsCatalogue:
    """Signalement opérateur : le ModelPicker ne proposait que les rôles
    benchmarkés, jamais les autres modèles réellement installés sur
    Ollama. Un opérateur qui sait ce qu'il fait doit pouvoir en choisir un
    quand même — mais jamais un modèle d'embedding, qui ne répond à aucun
    message de chat."""

    def test_un_modele_installe_hors_role_apparait_non_benchmarke(self, monkeypatch):
        import asyncio

        from backend.api.routes import system

        async def _faux_gpu_snapshot():
            return type("S", (), {"loaded_models": []})()

        async def _faux_modeles_ollama():
            return [
                {"name": "qwen3.5-9b-256k:latest", "capabilities": ["completion", "tools"]},
                {"name": "une-autre-embedding:latest", "capabilities": ["embedding"]},
            ]

        monkeypatch.setattr(system, "get_gpu_monitor",
                            lambda: type("M", (), {"snapshot": staticmethod(_faux_gpu_snapshot)})())
        monkeypatch.setattr(system, "_modeles_ollama", _faux_modeles_ollama)

        reponse = asyncio.run(system.system_models())
        par_modele = {r["model"]: r for r in reponse["roles"]}

        assert "qwen3.5-9b-256k:latest" in par_modele, (
            "un modèle installé, capable de compléter, absent du catalogue "
            "doit quand même apparaître")
        extra = par_modele["qwen3.5-9b-256k:latest"]
        assert extra["benchmarked"] is False
        assert extra["role"] == ""

        assert "une-autre-embedding:latest" not in par_modele, (
            "un modèle d'embedding ne répond à aucun message de chat : il "
            "ne doit jamais apparaître dans le sélecteur de l'Assistant")

    def test_un_tag_deja_dans_le_catalogue_n_est_pas_duplique(self, monkeypatch):
        import asyncio

        from backend.api.routes import system
        from backend.core.config import load_models_config

        tag_standard = load_models_config()["roles"]["standard"]["model"]

        async def _faux_gpu_snapshot():
            return type("S", (), {"loaded_models": []})()

        async def _faux_modeles_ollama():
            # Ollama rend "<nom>:latest", jamais le tag nu que porte
            # config/models.yaml — c'est cette forme, pas une correspondance
            # exacte, qui a fait dupliquer chaque modèle catalogué la
            # première fois (mesuré en conditions réelles, HOS-075).
            return [{"name": f"{tag_standard}:latest", "capabilities": ["completion", "tools"]}]

        monkeypatch.setattr(system, "get_gpu_monitor",
                            lambda: type("M", (), {"snapshot": staticmethod(_faux_gpu_snapshot)})())
        monkeypatch.setattr(system, "_modeles_ollama", _faux_modeles_ollama)

        reponse = asyncio.run(system.system_models())
        occurrences = [r for r in reponse["roles"]
                      if r["model"] in (tag_standard, f"{tag_standard}:latest")]

        assert len(occurrences) == 1, (
            "le tag du rôle standard ne doit apparaître qu'une fois, pas "
            f"une deuxième fois comme modèle hors catalogue : {occurrences}")
        assert occurrences[0]["role"] == "standard"
