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

        assert asyncio.run(system._modeles_installes()) is None

    def test_une_reponse_devient_un_ensemble(self, monkeypatch):
        import asyncio

        from backend.api.routes import system

        class _Client:
            def __init__(self, *a, **k):
                pass

            async def list_local_models(self):
                return [{"name": "lfm2.5-2.6b-125k:latest"},
                        {"name": "gemma4-12b-256k:latest"}]

            async def aclose(self):
                return None

        monkeypatch.setattr("backend.connectors.ollama_client.OllamaClient",
                            _Client)

        installes = asyncio.run(system._modeles_installes())

        assert _est_installe("lfm2.5-2.6b-125k", installes)
        assert not _est_installe("ornith-9b-256k", installes)
