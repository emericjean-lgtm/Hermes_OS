"""Le prix d'une bascule (HOS-114).

Ce que ces tests protègent : une mesure de coût qui ne mesurerait rien.
`load_duration` est un chiffre *rapporté* par Ollama, pas constaté par
nous — s'il ne distinguait pas un chargement d'une absence de chargement,
le routeur arbitrerait sur du bruit tout en croyant arbitrer sur une
mesure.
"""
from __future__ import annotations

import pytest

from backend.model_intelligence.switch_bench import CoutBascule, campagne, mesurer


def _ollama(par_appel: list[float]):
    """Un faux Ollama qui rend les `load_duration` qu'on lui dicte."""
    restants = list(par_appel)
    appels: list[tuple[str, int]] = []

    def generate(model, prompt, *, num_ctx, **kwargs):
        appels.append((model, num_ctx))
        return {"load_duration": int(restants.pop(0) * 1e9)}

    generate.appels = appels  # type: ignore[attr-defined]
    return generate


def _unload_mouchard():
    vus: list[str] = []

    def unload(model: str) -> None:
        vus.append(model)

    unload.vus = vus  # type: ignore[attr-defined]
    return unload


class TestMesure:
    def test_le_froid_et_le_chaud_sont_rendus_separement(self):
        cout = mesurer("m", 8192, generate=_ollama([4.47, 0.29]),
                       unload=_unload_mouchard())

        assert cout.froid_s == pytest.approx(4.47)
        assert cout.chaud_s == pytest.approx(0.29)

    def test_le_modele_est_decharge_avant_la_mesure_a_froid(self):
        """Sans cela « à froid » mesurerait l'état où la machine se trouvait,
        c'est-à-dire rien de reproductible."""
        unload = _unload_mouchard()
        mesurer("m", 8192, generate=_ollama([4.0, 0.2]), unload=unload)

        assert unload.vus == ["m"]

    def test_le_contexte_demande_est_celui_qui_est_servi(self):
        """Un coût mesuré à un autre contexte que celui du Modelfile
        décrirait un modèle que personne ne sert."""
        generate = _ollama([4.0, 0.2])
        mesurer("m", 65536, generate=generate, unload=_unload_mouchard())

        assert {ctx for _, ctx in generate.appels} == {65536}

    def test_une_absence_de_load_duration_vaut_zero_et_non_une_erreur(self):
        def generate(model, prompt, *, num_ctx, **kwargs):
            return {}

        cout = mesurer("m", 8192, generate=generate, unload=_unload_mouchard())
        assert cout.froid_s == 0.0 and cout.chaud_s == 0.0


class TestCredibilite:
    """Le témoin. Mesuré en réel : 4,47 s contre 0,29 s sur lfm2.5, 19,38
    contre 0,51 sur gpt-oss — un ordre de grandeur dans les deux cas."""

    def test_un_ecart_d_un_ordre_de_grandeur_est_credible(self):
        assert CoutBascule("m", 8192, froid_s=4.47, chaud_s=0.29).credible

    def test_un_chiffre_identique_a_froid_et_a_chaud_ne_l_est_pas(self):
        """Le cas qui doit alerter : `load_duration` rapporterait alors la
        même chose que le modèle soit chargé ou non, donc rien."""
        assert not CoutBascule("m", 8192, froid_s=3.0, chaud_s=3.0).credible

    def test_deux_zeros_ne_passent_pas_pour_une_mesure(self):
        assert not CoutBascule("m", 8192, froid_s=0.0, chaud_s=0.0).credible

    def test_le_verdict_accompagne_le_chiffre(self):
        """Publier le coût sans dire s'il est croyable laisserait un
        consommateur s'en servir sans le savoir."""
        assert CoutBascule("m", 8192, froid_s=19.38, chaud_s=0.51).as_dict()["credible"] is True


class TestCampagne:
    def test_chaque_modele_est_mesure_une_fois_et_dans_l_ordre(self):
        generate = _ollama([4.0, 0.2, 20.0, 0.5])
        resultats = campagne(
            [("petit", 16384), ("gros", 65536)],
            generate=generate, unload=_unload_mouchard(),
        )

        assert [r.model for r in resultats] == ["petit", "gros"]
        assert [r.froid_s for r in resultats] == [4.0, 20.0]

    def test_les_resultats_sont_rendus_au_fil_de_l_eau(self):
        """Une campagne interrompue doit laisser ce qu'elle a déjà obtenu —
        la leçon d'un banc perdu après quarante-cinq minutes."""
        vus: list[str] = []
        campagne(
            [("a", 8192), ("b", 8192)],
            generate=_ollama([1.0, 0.1, 2.0, 0.1]),
            unload=_unload_mouchard(),
            on_result=lambda c: vus.append(c.model),
        )

        assert vus == ["a", "b"]
