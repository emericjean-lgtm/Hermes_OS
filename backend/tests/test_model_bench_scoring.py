"""The graders that decide a model's verdict (HOS-104).

A benchmark is only worth its checkers. One that accepts a malformed JSON
object, or finds a needle that is not there, produces a confident number
that is wrong — the exact failure this project exists to remove, applied
to the instrument instead of the system under test.

Only the pure scoring functions are exercised here. The parts that talk to
Ollama are the instrument, not the judgement.
"""
from __future__ import annotations

import pytest

from backend.model_intelligence.model_bench import (
    MAX_OFFLOAD_RATIO,
    build_haystack,
    choose_tier,
    score_forbidden_letter,
    score_needle,
    score_structured_json,
    score_word_count,
)


# ── JSON structuré ───────────────────────────────────────────────────────

VALID = '{"name": "reboot", "priority": 2, "tags": ["ops"], "done": false}'


def test_a_conforming_object_passes():
    ok, why = score_structured_json(VALID)
    assert ok, why


def test_a_fenced_object_passes():
    """Models fence JSON constantly. Rejecting that would measure a
    formatting habit rather than the ability to honour a schema."""
    assert score_structured_json(f"Voici :\n```json\n{VALID}\n```")[0]


def test_prose_around_the_object_is_tolerated():
    assert score_structured_json(f"Bien sûr ! {VALID} J'espère que cela convient.")[0]


def test_a_missing_key_fails():
    ok, why = score_structured_json('{"name": "x", "priority": 1, "tags": []}')
    assert not ok
    assert "done" in why


def test_an_extra_key_fails():
    """A tool call with an invented field fails too — so must this."""
    ok, why = score_structured_json(
        '{"name": "x", "priority": 1, "tags": [], "done": true, "owner": "me"}')
    assert not ok
    assert "owner" in why


def test_a_wrong_type_fails():
    ok, why = score_structured_json(
        '{"name": "x", "priority": "haute", "tags": [], "done": true}')
    assert not ok
    assert "priority" in why


def test_a_boolean_is_not_an_integer():
    """json.loads gives True for `true`, and isinstance(True, int) is True
    in Python — so the naive check passes a booleanpriority. It must not."""
    ok, why = score_structured_json(
        '{"name": "x", "priority": true, "tags": [], "done": true}')
    assert not ok
    assert "priority" in why


def test_invalid_json_fails():
    assert not score_structured_json('{"name": "x", "priority": 1,}')[0]


def test_no_object_at_all_fails():
    assert not score_structured_json("Je ne peux pas produire de JSON.")[0]


def test_a_json_array_is_not_an_object():
    assert not score_structured_json('[{"name": "x"}]')[0]


def test_a_reasoning_model_narrating_around_its_answer_still_passes():
    """The incident that produced this test.

    The first extractor took raw[find("{") : rfind("}")+1] — a greedy span.
    A model that narrates before *and* after its answer made that span
    cover the object plus trailing commentary, json.loads raised "Extra
    data", and a flawless object scored zero. Measured on LFM2.5-2.6B:
    0/5, with a conforming object present in every single response.
    """
    raw = (
        "The user wants a JSON response with four keys. Provide something like:\n\n"
        f"{VALID}\n\n"
        "Check: name is a string, priority an integer {see above}, done boolean."
    )

    ok, why = score_structured_json(raw)

    assert ok, why


def test_the_conforming_object_wins_over_a_malformed_neighbour():
    """Models often sketch a wrong draft, then correct it. Scoring the
    first candidate found would punish exactly the self-correction the
    agentic loop depends on."""
    raw = f'Ébauche : {{"name": "x"}}\n\nVersion finale :\n{VALID}'

    assert score_structured_json(raw)[0]


def test_braces_inside_strings_do_not_break_extraction():
    obj = '{"name": "reboot {node}", "priority": 1, "tags": ["a"], "done": false}'

    assert score_structured_json(obj)[0]


def test_a_response_whose_only_object_is_wrong_still_fails():
    """The tolerance above must not become a way to pass by accident."""
    ok, why = score_structured_json(
        'Voici : {"name": "x", "priority": "haute", "tags": [], "done": true} — voilà.')

    assert not ok
    assert "priority" in why


# ── aiguille ─────────────────────────────────────────────────────────────

def test_the_needle_is_found_inside_a_sentence():
    assert score_needle("Le code d'accès est ABCD1234.", "ABCD1234")[0]


def test_the_needle_is_found_despite_added_punctuation():
    assert score_needle("« ABCD-1234 »", "ABCD1234")[0]


def test_a_different_code_is_not_the_needle():
    ok, why = score_needle("Le code est WXYZ9999.", "ABCD1234")
    assert not ok
    assert "WXYZ9999" in why


def test_a_refusal_is_not_a_find():
    assert not score_needle("Je ne trouve pas de code dans ce texte.", "ABCD1234")[0]


# ── contraintes vérifiables ──────────────────────────────────────────────

@pytest.mark.parametrize("text,expected,ok", [
    ("un deux trois quatre cinq six sept", 7, True),
    ("  un deux trois quatre cinq six sept  ", 7, True),
    ("un deux trois quatre cinq six", 7, False),
    ("un deux trois quatre cinq six sept huit", 7, False),
])
def test_word_count_is_exact(text, expected, ok):
    assert score_word_count(text, expected)[0] is ok


def test_a_forbidden_letter_is_caught_in_any_case():
    ok, why = score_forbidden_letter("Un ordinateur Est utilE.", "e")
    assert not ok
    assert "3" in why


def test_an_answer_without_the_forbidden_letter_passes():
    assert score_forbidden_letter("Un ordinatur fait tout.", "e")[0]


# ── le foin lui-même ─────────────────────────────────────────────────────

def test_the_haystack_contains_the_needle_exactly_once():
    text = build_haystack("ABCD1234", 0.5, approx_tokens=600)

    assert text.count("ABCD1234") == 1


@pytest.mark.parametrize("depth", [0.05, 0.5, 0.95])
def test_the_needle_lands_where_it_was_asked_to(depth):
    text = build_haystack("ABCD1234", depth, approx_tokens=1200)
    lines = text.splitlines()
    position = next(i for i, line in enumerate(lines) if "ABCD1234" in line)

    assert abs(position / len(lines) - depth) < 0.1, (
        f"aiguille à {position / len(lines):.0%} au lieu de {depth:.0%}"
    )


# ── le palier de contexte retenu ─────────────────────────────────────────

def _tier(num_ctx: int, offload: float | None = 0.0, **extra):
    return {"num_ctx": num_ctx, "cpu_offload_ratio": offload, **extra}


def test_the_largest_fitting_tier_wins():
    """Le but de toute la campagne : garder le plus grand contexte qui
    tient entièrement en VRAM."""
    retained = choose_tier([
        _tier(32768), _tier(65536), _tier(131072), _tier(262144, offload=0.31),
    ])

    assert retained == 131072


def test_a_spilling_tier_is_never_retained():
    """Un modèle qui déborde répond quand même, sans erreur, plusieurs fois
    plus lentement et de façon erratique — mesuré sur Muse-Glimmer Q3_K_XL,
    21 % de débordement donnaient 13 tok/s. Le retenir serait inscrire au
    catalogue un modèle qui semble marcher."""
    assert choose_tier([_tier(32768, offload=0.21), _tier(65536, offload=0.25)]) is None


def test_a_tier_that_failed_to_load_is_not_retained():
    """Un modèle entraîné jusqu'à 128k refusera 256k. C'est une réponse, pas
    une panne de la campagne — mais ce palier ne doit pas être retenu."""
    retained = choose_tier([
        _tier(65536), _tier(131072), _tier(262144, offload=None, error="HTTP 500"),
    ])

    assert retained == 131072


def test_no_tier_fits_returns_none_rather_than_the_least_bad():
    """Rapporter le moins mauvais ferait entrer au catalogue un modèle qui
    déborde à tous les paliers."""
    assert choose_tier([_tier(32768, offload=0.4), _tier(65536, offload=0.6)]) is None


def test_a_trace_of_offload_is_tolerated():
    """La mesure a du bruit ; exiger exactement zéro écarterait des paliers
    utilisables."""
    assert choose_tier([_tier(65536, offload=MAX_OFFLOAD_RATIO)]) == 65536
    assert choose_tier([_tier(65536, offload=MAX_OFFLOAD_RATIO + 0.01)]) is None


def test_an_empty_ladder_returns_none():
    assert choose_tier([]) is None


def test_the_served_context_wins_over_the_requested_one():
    """Ollama rabote au maximum du modèle sans le dire.

    Mesuré : LFM2.5-2.6B interrogé à 256k en sert 125k, gpt-oss:20b en sert
    131072, Hermes-4-14B 40960. La première version de cette fonction
    retenait la valeur demandée et aurait inscrit « LFM2.5 : 256k » au
    catalogue — un contexte que le modèle n'a jamais accordé, et dans
    lequel le routage aurait envoyé des tâches deux fois trop longues.
    """
    retained = choose_tier([
        _tier(131072, context_length=128000),
        _tier(262144, context_length=128000),
    ])

    assert retained == 128000


def test_the_heavy_profile_tolerates_some_spill_when_speed_holds():
    """Un gros modèle réservé au code complexe, appelé rarement, peut
    déborder un peu si le débit reste utilisable."""
    retained = choose_tier(
        [_tier(65536, offload=0.16, context_length=65536, output_tokens_per_s=39.6)],
        profile="heavy")

    assert retained == 65536


def test_the_heavy_profile_still_rejects_a_slow_model():
    """Le taux de débordement seul ne prédit rien. Mesuré le 13/08 :
    qwen3-coder:30b à 31 % tenait 39,6 tok/s, deepseek-r1:32b à 48 %
    tombait à 5,7. C'est le débit qui décide."""
    assert choose_tier(
        [_tier(65536, offload=0.18, context_length=65536, output_tokens_per_s=5.7)],
        profile="heavy") is None


def test_the_heavy_profile_still_requires_the_64k_floor():
    """En dessous, les schémas d'outils sont tronqués et l'agent répond
    qu'il n'a pas d'outils (CLAUDE.md). Aucune tolérance là-dessus."""
    assert choose_tier(
        [_tier(32768, offload=0.10, context_length=32768, output_tokens_per_s=80)],
        profile="heavy") is None


def test_the_strict_profile_stays_strict():
    """Le profil par défaut ne bouge pas : un modèle d'usage courant qui
    déborde de 16 % reste écarté."""
    assert choose_tier(
        [_tier(65536, offload=0.16, context_length=65536, output_tokens_per_s=39.6)]
    ) is None


def test_a_runtime_that_reports_no_served_context_falls_back():
    """Tous les runtimes ne rapportent pas context_length. La valeur
    demandée est alors la seule disponible — on la prend, plutôt que
    d'écarter une mesure par ailleurs valide."""
    assert choose_tier([_tier(65536)]) == 65536


def test_the_haystack_stays_under_the_requested_budget():
    """L'incident qui a produit ce test.

    L'estimation était de 12 tokens par phrase ; la mesure donne ~19. Un
    foin demandé à 26 000 tokens en pesait 33 411 — 28 % de trop — et
    Ollama rejetait la requête avec un 400 sur tout modèle dont le
    Modelfile ne relevait pas le contexte au-dessus de la demande.
    qwen3.6-35b et ornith-9b ont été notés 0/6 en long contexte sans avoir
    jamais été interrogés.

    Approximation à 4 caractères par token — grossière, mais elle borde
    largement l'erreur de 28 % qui a causé l'incident.
    """
    demande = 26000
    texte = build_haystack("ABCD1234", 0.5, approx_tokens=demande)

    tokens_estimes = len(texte) / 4
    assert tokens_estimes <= demande, (
        f"le foin pèse ~{tokens_estimes:.0f} tokens pour {demande} demandés — "
        "il débordera la fenêtre et la requête sera rejetée"
    )


def test_the_filler_is_varied_rather_than_one_repeated_line():
    """A haystack of identical sentences can be solved by spotting the line
    that differs, which measures novelty detection, not retrieval."""
    lines = build_haystack("ABCD1234", 0.5, approx_tokens=2400).splitlines()
    filler = [line for line in lines if "ABCD1234" not in line]

    assert len(set(filler)) > len(filler) * 0.5, "le foin est trop répétitif"
