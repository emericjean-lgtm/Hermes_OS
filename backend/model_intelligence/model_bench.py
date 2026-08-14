"""A measured battery for judging a local model's real qualities (HOS-104).

``agentic_probe`` answers one question — can this model do real tool work —
and stays the only judge of that. It says nothing about the qualities that
decide whether a model is *usable* here: how much VRAM it really takes,
whether it silently spills to CPU, whether it can emit an exact JSON
schema, whether it finds a fact buried at 128k, and how fast it does any
of it.

Two rules shape every check below.

**Every verdict is mechanically checkable.** No model grades another
model, and nothing is scored on impression. A JSON answer either parses
and matches the schema or it does not; a needle is either recovered
verbatim or it is not. This is the same refusal that runs through the rest
of the project: the model's own account of its performance is not
evidence.

**Numbers come from the runtime, not from a stopwatch here.** Throughput
is read off Ollama's own ``eval_count``/``eval_duration``, and VRAM off
``/api/ps``, because a wall-clock measurement taken in this process
includes queueing and HTTP and would flatter or punish a model for
reasons that have nothing to do with it.

Context is set per request through ``options.num_ctx``, which the *native*
endpoints honour — unlike the OpenAI-compatible ``/v1`` surface Hermes
Agent uses, where the only real lever is a Modelfile. See docs and
CLAUDE.md: that asymmetry is why the agentic leg of the battery needs a
tagged model while every other leg does not.
"""
from __future__ import annotations

import json
import random
import re
import string
import time
from dataclasses import dataclass, field, asdict
from collections.abc import Sequence
from typing import Any, Callable, Optional

import requests

OLLAMA = "http://localhost:11434"

#: Long enough that a wrong answer means the model genuinely lost the fact,
#: short enough that one battery does not take an afternoon.
_NEEDLE_DEPTHS = (0.05, 0.5, 0.95)

#: Pinned, not inherited. Ollama 0.32.10 changed its own default from 1.1 to
#: 1.0, which would have moved every measurement in this file without a line
#: of it changing — the campaign would have compared models against each
#: other across a silent runtime change.
#:
#: 1.0 (no penalty) is the right value for a bench. A repetition penalty
#: taxes tokens that recur, and code is made of recurring tokens:
#: indentation, delimiters, the same identifier on five lines. Penalising
#: them measures the sampler, not the model.
REPEAT_PENALTY = 1.0


@dataclass
class CheckResult:
    """One dimension's outcome. ``score`` is 0..1, ``detail`` says why."""

    name: str
    score: float
    detail: str
    measured: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return asdict(self)


# ── the runtime, asked directly ──────────────────────────────────────────

def generate(model: str, prompt: str, *, num_ctx: int,
             timeout_s: float = 900.0, **options: Any) -> dict:
    """One turn, with the context window this call actually wants.

    Uses ``/api/chat`` and returns the assistant's **answer** in
    ``response``, with any reasoning kept separately under ``thinking``.

    That distinction is the whole reason this does not call
    ``/api/generate``. Asked for a sentence of exactly seven words,
    Muse-Glimmer replied « La mer murmure doucement sous la lune » — seven
    words — after 1726 characters of visible reasoning. ``/api/generate``
    merges the two, so the word count came to 316 and a model that had
    obeyed the instruction scored zero. LFM2.5 failed the same check the
    same way, which is what made the number suspect: two models with
    nothing in common do not fail identically.

    Grading the reasoning would measure verbosity, not obedience.
    """
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {"num_ctx": num_ctx, "temperature": 0.0,
                    "repeat_penalty": REPEAT_PENALTY, **options},
    }
    http = requests.post(f"{OLLAMA}/api/chat", json=body, timeout=timeout_s)
    http.raise_for_status()
    payload = http.json()
    message = payload.get("message") or {}
    # Older builds, and models with no reasoning channel, put everything in
    # content — the fallback is then simply the whole answer.
    payload["response"] = message.get("content", "") or ""
    payload["thinking"] = message.get("thinking", "") or ""
    return payload


def gpu_dedicated_bytes(process_name: str = "llama-server") -> Optional[int]:
    """Dedicated GPU memory held by the process that actually infers.

    ``/api/ps`` reports the model **weights** and nothing else. Measured on
    2026-08-13 with Muse-Glimmer-30B at 64k: ``/api/ps`` said 9.55 GiB
    while ``llama-server`` held 13.21 GiB — the missing 3.7 GiB being the
    KV cache and the compute buffers, which is most of what decides whether
    a context size fits at all.

    The gap is invisible in the direction that matters: a report of
    "9.5 GiB on a 16 GiB card" invites loading a second model that will not
    fit. Worse, ``/api/ps`` shrank slightly from 8k to 64k, which is
    physically impossible for a growing KV cache and is what exposed the
    weights-only reading in the first place.

    Windows-only, and best-effort: returns None elsewhere or when the
    counter is unavailable, in which case callers fall back to the
    runtime's own figure and should say which one they used.
    """
    try:
        import subprocess

        # The counter names its instances by pid ("pid_27124_luid_..."),
        # never by image name, so the pid has to be resolved first — a
        # match on the process name finds nothing and silently reports
        # "not measurable", which is how the first version of this failed.
        script = (
            f"$ids = (Get-Process -Name '{process_name}' -ErrorAction SilentlyContinue).Id;"
            " if (-not $ids) { exit };"
            " (Get-Counter '\\GPU Process Memory(*)\\Dedicated Usage'"
            " -ErrorAction SilentlyContinue).CounterSamples |"
            " Where-Object { $i = $_.InstanceName;"
            "   $ids | Where-Object { $i -like \"pid_${_}_*\" } } |"
            " Measure-Object CookedValue -Sum |"
            " ForEach-Object { [long]$_.Sum }"
        )
        out = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, text=True, timeout=60,
        ).stdout.strip()
        return int(out) if out.isdigit() and int(out) > 0 else None
    except Exception:
        return None


def runtime_footprint(model: str) -> dict[str, Any]:
    """What the runtime says it loaded, and how much of it missed the GPU.

    ``size`` minus ``size_vram`` is the whole point: a model that overflows
    to CPU still answers, without error, roughly ten times slower and
    erratically — which reads as an unreliable model until someone looks
    here.

    Note that both numbers describe the **weights**. Total VRAM occupancy
    comes from :func:`gpu_dedicated_bytes`; see its docstring for why the
    two differ by gigabytes.
    """
    data = requests.get(f"{OLLAMA}/api/ps", timeout=30).json()
    for entry in data.get("models", []):
        if entry.get("name", "").startswith(model.split(":")[0]) or entry.get("name") == model:
            total = int(entry.get("size") or 0)
            vram = int(entry.get("size_vram") or 0)
            return {
                "name": entry.get("name"),
                "size_bytes": total,
                "size_vram_bytes": vram,
                "cpu_offload_bytes": max(0, total - vram),
                "cpu_offload_ratio": (total - vram) / total if total else 0.0,
                "context_length": entry.get("context_length"),
            }
    return {}


def throughput_of(response: dict) -> dict[str, float]:
    """Tokens per second, from the runtime's own counters."""
    def rate(count_key: str, duration_key: str) -> float:
        count = response.get(count_key) or 0
        nanos = response.get(duration_key) or 0
        return (count / (nanos / 1e9)) if nanos else 0.0

    return {
        "prompt_tokens": response.get("prompt_eval_count") or 0,
        "prompt_tokens_per_s": round(rate("prompt_eval_count", "prompt_eval_duration"), 1),
        "output_tokens": response.get("eval_count") or 0,
        "output_tokens_per_s": round(rate("eval_count", "eval_duration"), 1),
        "total_s": round((response.get("total_duration") or 0) / 1e9, 1),
    }


# ── the checkers: pure, and therefore testable ───────────────────────────

_REQUIRED_KEYS = {"name": str, "priority": int, "tags": list, "done": bool}


def _json_candidates(raw: str) -> list[str]:
    """Every balanced ``{...}`` region in the text, outermost first.

    Written after the first version took ``raw[find("{") : rfind("}")+1]``,
    a greedy span that swallows anything between two brace-bearing regions.
    Reasoning models narrate before *and* after their answer, so that span
    covered the object plus trailing commentary and json.loads failed with
    "Extra data" — scoring a perfectly conforming object as a failure.
    Measured against LFM2.5-2.6B: 0/5 under the greedy span, and its raw
    output contained a flawless object every time.

    Whether a model wraps its answer in prose is a separate quality, and
    ``check_instructions`` is where that is judged. This function answers
    only: was a conforming object produced at all.
    """
    candidates: list[str] = []
    depth = 0
    start = -1
    in_string = False
    escaped = False
    for index, char in enumerate(raw):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            if depth == 0:
                start = index
            depth += 1
        elif char == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and start != -1:
                    candidates.append(raw[start:index + 1])
    return candidates


def score_structured_json(raw: str) -> tuple[bool, str]:
    """Did the model produce the object asked for?

    Strict on shape, forgiving on wrapping: models fence JSON in ```json
    blocks and narrate around it constantly, and rejecting that would
    measure formatting habits rather than the ability to honour a schema.
    Everything else — missing key, wrong type, extra key — fails, because
    a tool call with a wrong field name fails too.
    """
    candidates = _json_candidates(raw)
    if not candidates:
        return False, "aucun objet JSON dans la réponse"

    last_reason = ""
    for text in candidates:
        ok, reason = _score_one_object(text)
        if ok:
            return True, reason
        last_reason = reason
    return False, last_reason


def _score_one_object(text: str) -> tuple[bool, str]:
    try:
        obj = json.loads(text)
    except ValueError as exc:
        return False, f"JSON invalide : {exc}"
    if not isinstance(obj, dict):
        return False, f"racine {type(obj).__name__}, objet attendu"

    missing = sorted(set(_REQUIRED_KEYS) - set(obj))
    if missing:
        return False, f"clés manquantes : {missing}"
    extra = sorted(set(obj) - set(_REQUIRED_KEYS))
    if extra:
        return False, f"clés en trop : {extra}"
    for key, expected in _REQUIRED_KEYS.items():
        if expected is int and isinstance(obj[key], bool):
            return False, f"{key} est un booléen, entier attendu"
        if not isinstance(obj[key], expected):
            return False, f"{key} est {type(obj[key]).__name__}, {expected.__name__} attendu"
    return True, "conforme"


def score_needle(raw: str, needle: str) -> tuple[bool, str]:
    """The buried code, recovered verbatim.

    Compared case-insensitively after stripping punctuation the model may
    add around it — the question is whether the fact survived the context,
    not whether the model wrapped it in a sentence.
    """
    cleaned = re.sub(r"[^A-Za-z0-9]", "", raw).upper()
    return (needle.upper() in cleaned,
            "retrouvée" if needle.upper() in cleaned else f"absente (réponse : {raw[:80]!r})")


def score_word_count(raw: str, expected: int) -> tuple[bool, str]:
    """Exactly N words. A constraint with no room for interpretation."""
    words = [w for w in re.split(r"\s+", raw.strip()) if w]
    return (len(words) == expected,
            f"{len(words)} mot(s), {expected} demandé(s)")


def score_forbidden_letter(raw: str, letter: str) -> tuple[bool, str]:
    """A constraint the model must hold across a whole answer.

    Deliberately harder than it looks: it tests whether instruction
    following survives generation length, which is exactly what breaks
    first under aggressive quantisation.
    """
    hits = raw.lower().count(letter.lower())
    return hits == 0, f"{hits} occurrence(s) de « {letter} »"


# ── the battery ──────────────────────────────────────────────────────────

def build_haystack(needle: str, depth: float, approx_tokens: int) -> str:
    """Filler with one unique fact buried at ``depth``.

    The filler is varied, not one sentence repeated: a model can survive a
    repetitive haystack by attending to the single line that differs,
    which measures novelty detection rather than retrieval.
    """
    rng = random.Random(1789)
    subjects = ["Le rapport", "La procédure", "Le registre", "Le protocole", "Le journal"]
    verbs = ["décrit", "recense", "consigne", "détaille", "archive"]
    objects = ["les relevés mensuels", "les incidents mineurs", "les seuils de tolérance",
               "les cycles de maintenance", "les écarts observés"]
    lines: list[str] = []
    # Mesuré, pas estimé : une phrase de ce gabarit (français, un nombre à
    # trois chiffres, ponctuation) pèse ~19 tokens, pas 12. L'ancienne
    # valeur produisait 33 411 tokens pour 26 000 demandés — 28 % de trop —
    # et le prompt était rejeté par Ollama avec un 400 sur tout modèle dont
    # le Modelfile ne relevait pas le contexte au-dessus de la demande.
    # Deux modèles ont ainsi été notés 0/6 sans jamais avoir été interrogés.
    #
    # 22 plutôt que 19 : dépasser la fenêtre fait échouer la requête, la
    # sous-remplir ne coûte qu'un test un peu moins tendu. L'erreur doit
    # pencher du côté qui laisse le modèle répondre.
    while len(lines) * 22 < approx_tokens:
        lines.append(f"{rng.choice(subjects)} n°{rng.randint(100, 999)} "
                     f"{rng.choice(verbs)} {rng.choice(objects)}.")
    position = max(0, min(len(lines) - 1, int(len(lines) * depth)))
    lines.insert(position, f"Le code d'accès confidentiel est {needle}.")
    return "\n".join(lines)


def _random_needle() -> str:
    rng = random.Random()
    return "".join(rng.choice(string.ascii_uppercase) for _ in range(4)) + \
           "".join(rng.choice(string.digits) for _ in range(4))


def check_structured_json(model: str, num_ctx: int, trials: int = 5) -> CheckResult:
    prompt = (
        "Réponds UNIQUEMENT par un objet JSON, sans texte autour, avec "
        "exactement ces quatre clés :\n"
        '  "name": une chaîne\n  "priority": un entier\n'
        '  "tags": une liste de chaînes\n  "done": un booléen\n'
        "Il décrit une tâche de maintenance de serveur."
    )
    passed, details = 0, []
    for _ in range(trials):
        try:
            raw = generate(model, prompt, num_ctx=num_ctx)["response"]
        except Exception as exc:
            details.append(f"appel échoué : {exc}")
            continue
        ok, why = score_structured_json(raw)
        passed += ok
        details.append(why)
    return CheckResult(
        "json_structuré", passed / trials,
        f"{passed}/{trials} conformes — " + "; ".join(details[:3]),
        {"trials": trials, "passed": passed},
    )


def check_needle(model: str, num_ctx: int) -> CheckResult:
    """Retrieval at three depths of a context filling the declared window."""
    results, measured = [], {}
    # 80% of the window, leaving room for the question and the answer.
    haystack_tokens = int(num_ctx * 0.8)
    for depth in _NEEDLE_DEPTHS:
        needle = _random_needle()
        prompt = (
            build_haystack(needle, depth, haystack_tokens)
            + "\n\nQuestion : quel est le code d'accès confidentiel mentionné "
              "ci-dessus ? Réponds uniquement par le code."
        )
        try:
            response = generate(model, prompt, num_ctx=num_ctx)
            ok, why = score_needle(response.get("response", ""), needle)
            measured[f"profondeur_{int(depth * 100)}%"] = {
                "trouvé": ok,
                "tokens_prompt": response.get("prompt_eval_count"),
                "détail": why,
            }
        except Exception as exc:
            ok = False
            measured[f"profondeur_{int(depth * 100)}%"] = {"trouvé": False, "détail": str(exc)}
        results.append(ok)
    return CheckResult(
        "aiguille_dans_le_foin", sum(results) / len(results),
        f"{sum(results)}/{len(results)} profondeurs retrouvées à {num_ctx // 1024}k",
        measured,
    )


def check_instructions(model: str, num_ctx: int) -> CheckResult:
    """Two constraints a grader can verify without judgement."""
    checks: list[tuple[str, Callable[[str], tuple[bool, str]]]] = [
        ("Écris une phrase d'exactement sept mots sur la mer. "
         "Réponds uniquement par la phrase.",
         lambda raw: score_word_count(raw, 7)),
        ("Décris un ordinateur en deux phrases complètes sans jamais employer "
         "la lettre « e ». Réponds uniquement par les deux phrases.",
         lambda raw: score_forbidden_letter(raw, "e")),
    ]
    passed, details = 0, []
    for prompt, checker in checks:
        try:
            raw = generate(model, prompt, num_ctx=num_ctx)["response"]
        except Exception as exc:
            details.append(f"appel échoué : {exc}")
            continue
        ok, why = checker(raw)
        passed += ok
        details.append(why)
    return CheckResult(
        "suivi_d_instruction", passed / len(checks),
        f"{passed}/{len(checks)} — " + "; ".join(details), {},
    )


def check_footprint(model: str, num_ctx: int) -> CheckResult:
    """VRAM and throughput, at the context actually requested.

    Scored rather than merely reported: a model that leaves a fifth of
    itself on the CPU is not a slower version of the same model, it is a
    different and erratic one, and that has to show up as a failure.
    """
    response = generate(model, "Dis simplement : prêt.", num_ctx=num_ctx)
    footprint = runtime_footprint(model)
    speed = throughput_of(response)
    ratio = footprint.get("cpu_offload_ratio", 0.0)
    score = 1.0 if ratio <= 0.05 else (0.5 if ratio <= 0.20 else 0.0)
    gib = 1024 ** 3

    # The number that decides whether a context size fits — weights plus KV
    # cache plus compute buffers. See gpu_dedicated_bytes: /api/ps reports
    # only the weights, and was understating this by 3.7 GiB on a 16 GiB
    # card.
    dedicated = gpu_dedicated_bytes()
    total = (f"{dedicated / gib:.1f} Gio VRAM totale (llama-server)"
             if dedicated else "VRAM totale non mesurable ici")

    return CheckResult(
        "empreinte", score,
        f"{total}; poids {footprint.get('size_vram_bytes', 0) / gib:.1f} Gio "
        f"({ratio * 100:.0f}% sur CPU) — {speed['output_tokens_per_s']} tok/s "
        f"génération, {speed['prompt_tokens_per_s']} tok/s prompt",
        {**footprint, **speed,
         "gpu_dedicated_bytes": dedicated,
         "num_ctx_demandé": num_ctx},
    )


# ── l'échelle de contextes ───────────────────────────────────────────────

#: Paliers standards. 64k est le plancher opérationnel de ce déploiement
#: (en dessous, les schémas d'outils sont tronqués — voir CLAUDE.md) ; 32k
#: n'est mesuré que pour situer un modèle qui échouerait à 64k.
DEFAULT_TIERS: tuple[int, ...] = (32768, 65536, 131072, 262144)

#: Au-delà, des poids partent sur le CPU. Un modèle qui déborde répond
#: quand même, sans erreur, plusieurs fois plus lentement et de façon
#: erratique — mesuré sur Muse-Glimmer Q3_K_XL : 21 % de débordement à 32k
#: donnait 13 tok/s, 25 % à 64k en donnait 17,8. Plus de débordement pour
#: plus de vitesse : c'est l'erratisme, pas une pénalité proportionnelle.
MAX_OFFLOAD_RATIO = 0.02

#: Profil « lourd » : un gros modèle réservé au code complexe, appelé
#: rarement, peut déborder un peu si la vitesse reste utilisable. Trois
#: conditions cumulatives, parce que le débordement seul ne prédit rien —
#: mesuré le 13/08 : qwen3-coder:30b à 31 % tenait 39,6 tok/s tandis que
#: deepseek-r1:32b à 48 % tombait à 5,7. C'est le débit qui décide, le taux
#: n'est qu'un indice.
HEAVY_MAX_OFFLOAD_RATIO = 0.20
HEAVY_MIN_CONTEXT = 65536
HEAVY_MIN_TOKENS_PER_S = 25.0


def _fits(entry: dict[str, Any], profile: str) -> bool:
    ratio = entry.get("cpu_offload_ratio")
    if ratio is None or entry.get("error"):
        return False
    if profile == "heavy":
        served = entry.get("context_length") or entry["num_ctx"]
        return (ratio <= HEAVY_MAX_OFFLOAD_RATIO
                and served >= HEAVY_MIN_CONTEXT
                and (entry.get("output_tokens_per_s") or 0) >= HEAVY_MIN_TOKENS_PER_S)
    return ratio <= MAX_OFFLOAD_RATIO


def choose_tier(measurements: list[dict[str, Any]], *,
                profile: str = "strict") -> Optional[int]:
    """Le plus grand contexte qui tient entièrement en VRAM.

    Pas de marge de sécurité ajoutée, et c'est délibéré : llama.cpp
    préalloue le cache KV au chargement. Mesuré en remplissant un contexte
    de 128k de 4 600 à 15 400 tokens, l'occupation n'a pas bougé d'un
    octet. Une mesure prise juste après le chargement décrit donc déjà le
    pire cas, et une marge inventée ne ferait qu'écarter des paliers
    utilisables.

    Renvoie le contexte **servi**, jamais celui demandé. Ollama rabote
    silencieusement au maximum du modèle : LFM2.5-2.6B interrogé à 256k en
    sert 125k, gpt-oss:20b en sert 131072, Hermes-4-14B 40960. Retenir la
    valeur demandée inscrirait au catalogue des contextes qu'aucun de ces
    modèles n'a jamais accordés — et le routage enverrait des tâches dans
    un contexte deux fois trop grand pour elles.

    ``profile="heavy"`` relâche la contrainte pour un gros modèle réservé
    aux tâches de code complexe : appelé rarement, il peut déborder jusqu'à
    20 % **à condition** de servir au moins 64k et de tenir 25 tok/s. Le
    rôle qu'on donne à un modèle est une décision d'exploitation, pas une
    propriété du fichier — d'où un paramètre plutôt qu'un seuil global.

    Renvoie None quand aucun palier ne tient — un fait à rapporter tel
    quel, pas à rattraper avec le moins mauvais.
    """
    fitting = [m for m in measurements if _fits(m, profile)]
    # context_length manque sur les runtimes qui ne le rapportent pas ; la
    # valeur demandée est alors la seule disponible, et on le dit ainsi
    # plutôt que d'écarter la mesure.
    return max((m.get("context_length") or m["num_ctx"] for m in fitting), default=None)


def context_ladder(model: str, tiers: Sequence[int] = DEFAULT_TIERS, *,
                   on_tier: Optional[Callable[[dict], None]] = None,
                   ) -> dict[str, Any]:
    """Monter les paliers de contexte et garder le plus haut qui tient.

    Un palier à la fois, avec déchargement entre chaque : deux tailles du
    même modèle résidentes en même temps mesureraient la contention, pas la
    capacité.

    Un palier qui refuse de charger n'est pas une panne de la campagne — un
    modèle dont le contexte d'entraînement s'arrête à 128k rejettera 256k,
    et c'est une réponse. L'erreur est consignée et l'échelle continue.
    """
    results: list[dict[str, Any]] = []
    for num_ctx in tiers:
        unload(model)
        started = time.perf_counter()
        entry: dict[str, Any] = {"num_ctx": num_ctx}
        try:
            response = generate(model, "Réponds par un mot : prêt.", num_ctx=num_ctx)
            entry["load_and_answer_s"] = round(time.perf_counter() - started, 1)
            entry.update(runtime_footprint(model))
            entry["gpu_dedicated_bytes"] = gpu_dedicated_bytes()
            entry.update(throughput_of(response))
        except Exception as exc:
            entry["error"] = f"{type(exc).__name__}: {exc}"
            entry["cpu_offload_ratio"] = None
        results.append(entry)
        if on_tier is not None:
            try:
                on_tier(entry)
            except Exception:
                logger.debug("on_tier callback failed", exc_info=True)
    unload(model)
    return {"model": model, "tiers": results, "retained_num_ctx": choose_tier(results)}


def unload(model: str) -> None:
    """Libérer la carte avant la mesure suivante."""
    try:
        requests.post(f"{OLLAMA}/api/generate",
                      json={"model": model, "prompt": "", "keep_alive": 0}, timeout=120)
    except Exception:
        pass
    time.sleep(4)


def run_battery(model: str, num_ctx: int, *,
                include_needle: bool = True,
                on_check: Optional[Callable[[CheckResult], None]] = None,
                ) -> dict[str, Any]:
    """Every non-agentic dimension, at one context size.

    The agentic verdict is deliberately absent: it belongs to
    ``agentic_probe.probe`` and needs a Modelfile-tagged model, since the
    ``/v1`` endpoint Hermes Agent uses cannot carry ``num_ctx``.

    ``on_check`` fires as each dimension finishes, so a caller can persist
    results while the run is still going. Not a convenience: a single
    needle check on a 30B at 64k took 837 s here, three of them 42 minutes,
    and a battery that only returns at the very end means an interrupted
    run — or one whose next context size turns out to be unaffordable —
    throws away everything already measured. That happened once; the
    callback is what stops it happening twice.
    """
    started = time.time()
    checks: list[CheckResult] = []

    def _run(check: Callable[[], CheckResult]) -> None:
        result = check()
        checks.append(result)
        if on_check is not None:
            try:
                on_check(result)
            except Exception:  # a reporting failure must not lose the run
                logger.debug("on_check callback failed", exc_info=True)

    _run(lambda: check_footprint(model, num_ctx))
    _run(lambda: check_structured_json(model, num_ctx))
    _run(lambda: check_instructions(model, num_ctx))
    if include_needle:
        _run(lambda: check_needle(model, num_ctx))
    return {
        "model": model,
        "num_ctx": num_ctx,
        "duration_s": round(time.time() - started, 1),
        "checks": [c.as_dict() for c in checks],
        "score_global": round(sum(c.score for c in checks) / len(checks), 3),
    }
