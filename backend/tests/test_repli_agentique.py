"""Un repli ne défait une décision que s'il est mieux prouvé (T-29, G-12).

## Le défaut

§6.1 (HOS-262) a rendu le routage juste : le type de tâche décide enfin du
modèle, et cinq tâches donnent trois modèles différents sur leur note
métier mesurée. `_agentic_model` annulait ensuite **la totalité** de ces
décisions — mesuré, **0 sur 5** survivait au chemin agentique.

La règle disait : « substituer un repli **connu-bon** à tout modèle non
prouvé ». Sa prémisse était fausse ici. Mesuré sur les six modèles du
catalogue :

    modèle                chat  tools  params  offload  ctx servi  mesure
    gpt-oss-20b-64k       True  True    20.9    None     None      None
    qwen3.6-35b-128k      True  True    34.7    None     None      None
    ornith-9b-256k        True  True     9.0    None     None      None
    muse-glimmer-64k      True  True    27.9    None     None      None
    gemma4-12b-256k       True  True    11.9    None     None      None
    lfm2.5-2.6b-125k      True  True     2.7    None     None      None

**Aucun n'est disqualifié** — tous passent chaque contrôle structurel. Ils
sont simplement **non sondés**, et le repli `lfm2.5-2.6b-125k` l'est
autant que les autres. La substitution échangeait donc un inconnu contre
un autre inconnu, en jetant le seul signal mesuré du système — et le
repli est de surcroît le plus faible du catalogue sur ces notes : 0,28 en
code contre 1,00 pour `gpt-oss`.

## La correction

`ModelProfile.agentic_capable` rend un booléen et écrasait la différence
entre « mesuré incapable » et « jamais mesuré ». Le prédicat du bootstrap
rend désormais les trois états, et la règle devient :

    modèle choisi     repli            décision
    prouvé capable    n'importe quoi   conservé
    prouvé incapable  prouvé capable   substitué   (le cas légitime)
    prouvé incapable  non prouvé       substitué   (le choix est exclu)
    non prouvé        prouvé capable   substitué   (la preuve l'emporte)
    non prouvé        non prouvé       **conservé** — c'était G-12

## Ce que ce fichier ne prouve pas

Qu'un modèle non sondé sache piloter la boucle d'outils. Il ne le prouve
pas, et la correction ne le prétend pas : HOS-096 tient, un modèle non
mesuré reste **non prouvé**. Ce qui change est ce qu'on en fait quand
l'autre option ne vaut pas mieux. Sonder réellement le catalogue reste le
seul moyen de trancher, et c'est hors de cette passe.
"""

from __future__ import annotations

import ast
import inspect
import io
import textwrap
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.execution.task_executor import (
    _HERMES_AGENT_FALLBACK_MODEL,
    RealTaskExecutor,
)
from backend.ral.capabilities import ChatResponse

RACINE = Path(__file__).resolve().parents[2]

ROUTE = "gpt-oss-20b-64k"        # ce que le routeur choisit sur du code
REPLI = _HERMES_AGENT_FALLBACK_MODEL


def _executeur(verdicts: dict, **kw) -> RealTaskExecutor:
    """Un exécuteur dont on pilote le verdict agentique de chaque modèle.

    `verdicts` mappe un tag sur `True` (prouvé capable), `False` (prouvé
    incapable) ou `None` (jamais sondé) — les trois états que le prédicat
    rend depuis T-29.
    """
    kw.setdefault("model_for", lambda _t: ROUTE)
    kw.setdefault("default_model", ROUTE)
    return RealTaskExecutor(
        chat=None, agentic_capable_for=lambda m: verdicts.get(m), **kw)


# ═══ La table de vérité, ligne par ligne ══════════════════════════════

def test_un_modele_prouve_capable_est_conserve():
    ex = _executeur({ROUTE: True, REPLI: True})
    assert ex._agentic_model(ROUTE, "code_generation") == ROUTE


def test_un_modele_prouve_capable_est_conserve_meme_si_le_repli_l_est():
    """La preuve du repli ne donne aucun droit sur une décision déjà
    prouvée."""
    ex = _executeur({ROUTE: True, REPLI: True})
    assert ex._agentic_model(ROUTE, "reasoning") == ROUTE


def test_un_modele_prouve_incapable_est_substitue():
    """Le cas légitime, et il doit continuer de fonctionner : le routeur a
    choisi un modèle qu'une mesure a écarté."""
    ex = _executeur({ROUTE: False, REPLI: True})
    assert ex._agentic_model(ROUTE, "code_generation") == REPLI


def test_un_modele_prouve_incapable_est_substitue_meme_par_un_repli_non_prouve():
    """Une mesure négative exclut le choix : mieux vaut l'inconnu que le
    connu-mauvais."""
    ex = _executeur({ROUTE: False, REPLI: None})
    assert ex._agentic_model(ROUTE, "code_generation") == REPLI


def test_un_repli_prouve_l_emporte_sur_un_modele_non_prouve():
    """La preuve bat l'absence de preuve — c'est le seul cas où un modèle
    non sondé cède."""
    ex = _executeur({ROUTE: None, REPLI: True})
    assert ex._agentic_model(ROUTE, "code_generation") == REPLI


def test_deux_inconnus_ne_se_substituent_pas():
    """**Le cœur de G-12.** Échanger un inconnu contre un autre inconnu ne
    réduit aucun risque et jette la note métier qui a fondé le choix."""
    ex = _executeur({ROUTE: None, REPLI: None})
    assert ex._agentic_model(ROUTE, "code_generation") == ROUTE, (
        "un modèle non prouvé est remplacé par un repli tout aussi non "
        "prouvé : la décision du routeur est annulée sans preuve")


def test_l_etat_reel_du_depot_conserve_la_decision():
    """Le cas mesuré : sur cette machine, aucun modèle n'est sondé."""
    ex = _executeur({})           # tout rend None
    assert ex._agentic_model(ROUTE, "code_generation") == ROUTE


# ═══ Plusieurs TaskType, plusieurs modèles ═══════════════════════════

def test_plusieurs_types_de_tache_donnent_plusieurs_modeles_engages():
    """Bout en bout de la promesse de §6.1 : le type de tâche décide, et
    la décision atteint l'exécution.

    Sans cela, §6.1 serait un classement correct sans effet — ce que G-12
    en faisait.
    """
    choix = {"code_generation": "gpt-oss-20b-64k",
             "reasoning": "qwen3.6-35b-128k",
             "documentation": "ornith-9b-256k"}
    ex = _executeur({})
    engages = {t: ex._agentic_model(m, t) for t, m in choix.items()}

    assert engages == choix, (
        f"les décisions ne survivent pas au chemin agentique : {engages}")
    assert len(set(engages.values())) == 3, (
        "trois types de tâche donnent un seul modèle engagé")


# ═══ Le modèle imposé garde sa précédence, et ses limites ════════════

def test_un_modele_impose_prouve_incapable_est_toujours_substitue(monkeypatch):
    """`HERMES_MISSION_MODEL` prime sur le routeur, jamais sur une mesure
    négative — le contrat de `modele_impose` est inchangé."""
    monkeypatch.setenv("HERMES_MISSION_MODEL", "un-modele-impose")
    ex = _executeur({"un-modele-impose": False, REPLI: True})

    assert ex._agentic_model(ROUTE, "code_generation") == REPLI


def test_un_modele_impose_non_prouve_est_conserve(monkeypatch):
    """Même règle que pour le routeur : sans preuve d'un côté ni de
    l'autre, on n'annule rien."""
    monkeypatch.setenv("HERMES_MISSION_MODEL", "un-modele-impose")
    ex = _executeur({"un-modele-impose": None, REPLI: None})

    assert ex._agentic_model(ROUTE, "code_generation") == "un-modele-impose"


# ═══ Le prédicat rend bien trois états ═══════════════════════════════

_COMPTEUR = iter(range(1000))


def _predicat(monkeypatch, *, capabilities, mesure, params="20.9B"):
    """Le vrai prédicat du bootstrap, avec Ollama et la sonde remplacés.

    Testé sur son **comportement** et non sur la forme de son code : trois
    mutations du prédicat sont restées vertes contre des assertions
    syntaxiques — la présence de `return None` était satisfaite par le
    `return None` du gestionnaire d'exception, et deux autres portaient sur
    `ModelProfile`, une couche en dessous de ce qui décide.
    """
    import httpx

    from backend.core.bootstrap import service_registry as sr

    class _Reponse:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"capabilities": capabilities,
                    "details": {"parameter_size": params},
                    "model_info": {"x.context_length": 131072}}

    class _Client:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, *a, **k):
            return _Reponse()

    monkeypatch.setattr(httpx, "Client", _Client)
    monkeypatch.setattr(sr, "_runtime_footprint_for", lambda _m: (None, None))
    monkeypatch.setattr(
        "backend.model_intelligence.agentic_probe.measured_success_for",
        lambda _m: mesure)
    # Un identifiant neuf par appel : le prédicat est `lru_cache`é — « asked
    # once per task, the answer only changes when the model itself is
    # replaced ». Réutiliser le même nom rendait la réponse du premier
    # test à tous les suivants, et trois d'entre eux passaient au vert
    # sur une valeur mémoïsée.
    return sr._agentic_capable_for("un-modele-%d" % next(_COMPTEUR))


def test_le_predicat_rend_None_pour_un_modele_jamais_sonde(monkeypatch):
    """« Non prouvé » doit se distinguer de « prouvé incapable » : les deux
    valaient `False`, et l'appelant substituait dans les deux cas."""
    assert _predicat(monkeypatch, capabilities=["tools", "completion"],
                     mesure=None) is None


def test_le_predicat_rend_True_pour_un_modele_prouve(monkeypatch):
    assert _predicat(monkeypatch, capabilities=["tools", "completion"],
                     mesure=True) is True


def test_le_predicat_rend_False_pour_un_modele_mesure_incapable(monkeypatch):
    assert _predicat(monkeypatch, capabilities=["tools", "completion"],
                     mesure=False) is False


def test_un_disqualifieur_reste_une_preuve_negative(monkeypatch):
    """Un modèle qu'un contrôle structurel écarte rend `False`, pas `None` :
    celui-là est une preuve négative, pas une absence de preuve.

    Sans cette distinction, un modèle d'embedding — qui annonce `tools` —
    ne serait plus jamais substitué.
    """
    assert _predicat(monkeypatch, capabilities=["tools", "embedding"],
                     mesure=None) is False


def test_le_profil_ne_declare_pas_capable_un_modele_non_sonde():
    """La couche en dessous : survivre aux disqualifieurs n'est pas une
    preuve. `gemma4:12b` les passe tous et a mesuré 0/3."""
    from backend.model_intelligence.model_intelligence_models import ModelProfile

    non_sonde = ModelProfile(
        model_id="m", name="m", parameters_b=20.0,
        declares_tools=True, chat_capable=True,
        measured_agentic_success=None)

    assert non_sonde.agentic_capable is False, (
        "un modèle jamais mesuré se déclare capable : HOS-096 est défait")


# ═══ La substitution reste observable ════════════════════════════════

def test_une_substitution_est_tracee(caplog):
    import logging

    ex = _executeur({ROUTE: False, REPLI: True})
    with caplog.at_level(logging.INFO):
        ex._agentic_model(ROUTE, "code_generation")

    assert any("substituting" in r.message for r in caplog.records), (
        "la substitution n'est plus journalisée")


def test_une_non_substitution_est_tracee_aussi(caplog):
    """« On a conservé la décision » est un fait d'exécution autant que
    « on l'a défaite » — et c'est celui qui manquait."""
    import logging

    ex = _executeur({ROUTE: None, REPLI: None})
    with caplog.at_level(logging.INFO):
        ex._agentic_model(ROUTE, "code_generation")

    messages = " ".join(r.message for r in caplog.records)
    assert "T-29" in messages or "conserve" in messages, (
        f"la conservation n'est pas tracée : {messages!r}")


def test_la_trace_du_run_porte_la_substitution_quand_elle_a_lieu():
    """Le lien avec HOS-262 : ce que le registre relira."""
    import json

    from backend.execution.mission_executor import _decision_en_json

    meta = {"runtime_demande_par_le_routeur": "hermes-agent",
            "modele_demande_par_le_routeur": ROUTE}
    trace = json.loads(_decision_en_json(meta, REPLI, "hermes-agent"))

    assert trace["modele_demande"] == ROUTE
    assert "substitution" in trace


# ═══ Aucune autorité nouvelle ════════════════════════════════════════

def test_le_repli_ne_choisit_jamais_un_modele_hors_du_repli():
    """`_agentic_model` ne rend que deux choses : ce qu'on lui a donné, ou
    le repli configuré. Choisir un troisième modèle en ferait un routeur.
    """
    ex = _executeur({ROUTE: False, REPLI: True})
    for tt in ("code_generation", "reasoning", "documentation", ""):
        assert ex._agentic_model(ROUTE, tt) in (ROUTE, REPLI)


def test_l_executeur_ne_consulte_aucun_routeur():
    """La sélection appartient à `AdaptiveRouter`, injectée par
    `model_for`. Un exécuteur qui importerait un routeur serait une
    seconde autorité sur le chemin Mission."""
    arbre = ast.parse(io.open(RACINE / "backend/execution/task_executor.py",
                              encoding="utf-8").read())
    modules = {(n.module or "") for n in ast.walk(arbre)
               if isinstance(n, ast.ImportFrom)}
    modules |= {a.name for n in ast.walk(arbre)
                if isinstance(n, ast.Import) for a in n.names}

    fautifs = [m for m in modules
               if "adaptive_router" in m or m.endswith("core.router")]
    assert not fautifs, (
        f"l'exécuteur consulte un routeur lui-même : {fautifs}")
