"""Le type de tâche décide du modèle, et une substitution se voit (§6.1).

## Le défaut, mesuré sur le catalogue réel

`AdaptiveRouter` est l'autorité de sélection du chemin mission. Ses
profils portent des notes **par type de tâche**, versées depuis le magasin
de mesures (HOS-144) et fortement discriminantes :

    gpt-oss-20b-64k      code_generation 1.00
    lfm2.5-2.6b-125k     code_generation 0.28

Il recommandait pourtant `lfm2.5-2.6b-125k` — le plus petit modèle du
catalogue — pour **les cinq** types de tâche essayés, motif « Low VRAM
footprint ».

La cause n'était ni le classement ni les notes. `rank_models` filtre sur
`predict_vram_usage`, qui multipliait l'empreinte **mesurée** par
`task.complexity + 1.0`, soit 1,3 à 2,0. Et `task.complexity` est le
**nombre de mots du titre de la tâche** (`_infer_complexity` : >30 mots
→ 0,8 ; >15 → 0,5 ; sinon 0,3).

La longueur d'une phrase décidait donc si un modèle tenait sur la carte :

    modèle               déclaré   « prédit »   plafond   verdict
    gpt-oss-20b-64k       13 342     17 344     15 000    éliminé
    qwen3.6-35b-128k      14 008     18 210     15 000    éliminé
    muse-glimmer-64k      13 373     17 384     15 000    éliminé
    ornith-9b-256k        13 824     17 971     15 000    éliminé
    gemma4-12b-256k       12 533     16 292     15 000    éliminé
    lfm2.5-2.6b-125k       2 099      2 728     15 000    seul retenu

Le classement, lui, était juste : sans ce filtre, `gpt-oss` sort à 0,672
contre 0,434 pour `lfm2.5`.

## Pourquoi le multiplicateur était faux

Le cache KV est alloué à la taille de la **fenêtre**, pas à celle du
prompt. A-18 l'a mesuré : 2,02 Gio à `num_ctx` 16384 et 4,33 à 131072 —
c'est le contexte servi qui compte, et il est déjà dans le chiffre
déclaré. R-6 a mesuré ce que l'usage ajoute : entre un cache vide et un
cache rempli de 3 210 jetons, 14,954 → 15,115 Gio, soit **+1 %**. Le
multiplicateur en inventait jusqu'à +100 %.

## Ce que ce fichier ne prouve pas

Que le modèle choisi soit celui qui **s'exécute**. Sur le chemin
agentique, `_agentic_model` substitue tout modèle non prouvé, et le
magasin de sondes est vide sur cette machine : les cinq décisions sont
remplacées par `_HERMES_AGENT_FALLBACK_MODEL`. C'est délibéré (HOS-096) et
consigné en G-12 ; ce que cette passe corrige est que la substitution
**se voie** dans la trace.
"""

from __future__ import annotations

import ast
import inspect
import io
import textwrap
from pathlib import Path

import pytest

from backend.model_intelligence.model_intelligence_models import (
    ModelProfile,
    TaskContext,
    TaskType,
)
from backend.model_intelligence.model_predictor import ModelPredictor

RACINE = Path(__file__).resolve().parents[2]

#: Empreintes déclarées de `config/models.yaml`, en mégaoctets.
GROS = 13342      # gpt-oss-20b-64k
PETIT = 2099      # lfm2.5-2.6b-125k


def _profil(model_id: str, vram_mb: int, notes: dict) -> ModelProfile:
    return ModelProfile(
        model_id=model_id, name=model_id,
        parameters_b=20.0 if vram_mb > 8000 else 2.6,
        vram_required_mb=vram_mb,
        context_window=65536,
        task_scores=notes,
        declares_tools=True,
    )


def _catalogue() -> list[ModelProfile]:
    return [
        _profil("gros-competent", GROS, {"code_generation": 1.0, "reasoning": 1.0}),
        _profil("petit-mediocre", PETIT, {"code_generation": 0.28, "reasoning": 0.75}),
    ]


def _tache(mots: int, plafond_mb: int = 15000) -> TaskContext:
    """Une tâche dont on pilote la **longueur du titre** — c'est-à-dire, sur
    l'ancien chemin, sa consommation VRAM supposée."""
    from backend.model_intelligence.adaptive_router import AdaptiveRouter

    complexite = AdaptiveRouter()._infer_complexity(" ".join(["mot"] * mots))
    return TaskContext(task_type=TaskType.CODE_GENERATION,
                       complexity=complexite, max_vram_mb=plafond_mb)


# ═══ 1 — l'empreinte prédite est l'empreinte déclarée ════════════════

def test_1_la_vram_predite_est_celle_qui_est_declaree():
    """Aucune marge inventée : c'est le chiffre du catalogue, celui-là même
    que l'admission retient depuis A-18."""
    predicteur = ModelPredictor()
    for profil in _catalogue():
        for mots in (3, 20, 50):
            predit = predicteur.predict_vram_usage(profil, _tache(mots))
            assert predit == profil.vram_required_mb, (
                f"{profil.model_id} : {predit} Mo prédits pour "
                f"{profil.vram_required_mb} Mo déclarés, sur un titre de "
                f"{mots} mots")


def test_1_la_longueur_du_titre_ne_change_pas_la_vram():
    """Le cœur du défaut : `complexity` est un nombre de mots, et il
    décidait de la place occupée sur la carte."""
    predicteur = ModelPredictor()
    profil = _catalogue()[0]

    court = predicteur.predict_vram_usage(profil, _tache(3))
    long = predicteur.predict_vram_usage(profil, _tache(50))

    assert court == long, (
        f"un titre long fait passer l'empreinte de {court} à {long} Mo — "
        "la longueur d'une phrase ne change pas ce qu'un modèle occupe")


# ═══ 2 — le modèle compétent n'est plus éliminé ══════════════════════

def test_2_le_modele_competent_survit_au_filtre():
    """Le scénario mesuré, rejoué : 13 342 Mo déclarés sous un plafond de
    15 000 doivent passer. L'ancien calcul en annonçait 17 344."""
    predicteur = ModelPredictor()
    classement = predicteur.rank_models(_catalogue(), [], _tache(50))

    retenus = {r["model_id"] for r in classement}
    assert "gros-competent" in retenus, (
        f"le modèle compétent est éliminé du classement : {retenus}")
    assert len(classement) == 2


def test_2_le_meilleur_au_metier_est_classe_premier():
    predicteur = ModelPredictor()
    classement = predicteur.rank_models(_catalogue(), [], _tache(50))

    assert classement[0]["model_id"] == "gros-competent"
    assert classement[0]["task_score"] == pytest.approx(1.0)
    assert classement[0]["score"] > classement[1]["score"]


def test_2_le_type_de_tache_change_le_classement():
    """La question même de §6.1 : le rôle influence-t-il la sélection ?

    Deux types de tâche, deux gagnants — sinon la note par type est un
    ornement.
    """
    predicteur = ModelPredictor()
    catalogue = [
        _profil("specialiste-code", GROS, {"code_generation": 1.0, "documentation": 0.1}),
        _profil("specialiste-doc", GROS, {"code_generation": 0.1, "documentation": 1.0}),
    ]

    def gagnant(tt):
        t = TaskContext(task_type=tt, complexity=0.3, max_vram_mb=15000)
        return predicteur.rank_models(catalogue, [], t)[0]["model_id"]

    assert gagnant(TaskType.CODE_GENERATION) == "specialiste-code"
    assert gagnant(TaskType.DOCUMENTATION) == "specialiste-doc", (
        "le type de tâche ne départage pas : la note par type ne sert à rien")


# ═══ 3 — le plafond de capacité continue d'éliminer ══════════════════

def test_3_un_modele_qui_ne_tient_pas_est_toujours_ecarte():
    """Retirer la marge inventée ne doit pas retirer le filtre : un modèle
    plus gros que le plafond reste éliminé."""
    predicteur = ModelPredictor()
    classement = predicteur.rank_models(
        _catalogue(), [], _tache(3, plafond_mb=5000))

    retenus = {r["model_id"] for r in classement}
    assert retenus == {"petit-mediocre"}, (
        f"le filtre de capacité ne s'applique plus : {retenus}")


def test_3_la_capacite_vient_du_plafond_et_de_rien_d_autre():
    """Le plafond est fourni par l'appelant — au bootstrap, la VRAM
    réellement libre. Le prédicteur ne l'invente ni ne le corrige."""
    predicteur = ModelPredictor()
    profil = _catalogue()[0]

    for plafond, attendu in ((GROS - 1, False), (GROS, True), (GROS + 1, True)):
        t = TaskContext(task_type=TaskType.CODE_GENERATION,
                        complexity=0.8, max_vram_mb=plafond)
        retenu = bool(predicteur.rank_models([profil], [], t))
        assert retenu is attendu, (
            f"plafond {plafond} Mo pour {GROS} Mo déclarés : "
            f"{'retenu' if retenu else 'écarté'}")


# ═══ 4 — une seule autorité de capacité ═════════════════════════════

def test_4_le_predicteur_n_invente_aucune_marge():
    """Structurel, sur la propriété : `predict_vram_usage` ne doit
    contenir aucune arithmétique sur l'empreinte déclarée.

    L'assertion porte sur les opérateurs de l'arbre syntaxique, pas sur le
    texte : `* 1.3`, `+ 2000` ou `min(2.0, …)` sont tous des façons de
    réintroduire une seconde estimation.
    """
    source = textwrap.dedent(inspect.getsource(ModelPredictor.predict_vram_usage))
    arbre = ast.parse(source)

    operations = [n for n in ast.walk(arbre) if isinstance(n, ast.BinOp)]
    assert not operations, (
        "`predict_vram_usage` calcule à nouveau sur l'empreinte déclarée : "
        "c'est une seconde autorité de capacité")

    noms = {n.attr for n in ast.walk(arbre) if isinstance(n, ast.Attribute)}
    assert "complexity" not in noms, (
        "la complexité — un nombre de mots — est revenue dans le calcul de "
        "la VRAM")


def test_4_la_capacite_reste_au_gestionnaire_de_ressources():
    """Le prédicteur ne consulte ni la carte ni le gestionnaire : il reçoit
    un plafond et l'applique. L'autorité de capacité est ailleurs (R-3)."""
    arbre = ast.parse(io.open(
        RACINE / "backend/model_intelligence/model_predictor.py",
        encoding="utf-8").read())

    modules = {(n.module or "") for n in ast.walk(arbre)
               if isinstance(n, ast.ImportFrom)}
    modules |= {a.name for n in ast.walk(arbre)
                if isinstance(n, ast.Import) for a in n.names}
    fautifs = [m for m in modules
               if "resources" in m or "gpu" in m.lower() or "vram_physique" in m]
    assert not fautifs, (
        f"le prédicteur lit la capacité lui-même : {fautifs}")


# ═══ 5 — une substitution de modèle se voit ═════════════════════════

def test_5_la_substitution_de_modele_entre_dans_la_trace():
    """« Un fallback doit être observable » — invariant de §6.1.

    Le repli de *runtime* était tracé depuis HOS-242 ; celui de **modèle**
    ne l'était pas. Or `_agentic_model` substitue tout modèle non prouvé,
    et sur cette machine cela vise la totalité des décisions.
    """
    from backend.execution.mission_executor import _decision_en_json
    import json

    meta = {"runtime_demande_par_le_routeur": "hermes-agent",
            "modele_demande_par_le_routeur": "gpt-oss-20b-64k"}
    trace = json.loads(_decision_en_json(meta, "lfm2.5-2.6b-125k", "hermes-agent"))

    assert trace["modele"] == "lfm2.5-2.6b-125k"
    assert trace["modele_demande"] == "gpt-oss-20b-64k"
    assert "substitution" in trace
    assert "gpt-oss-20b-64k" in trace["substitution"]


def test_5_sans_substitution_la_trace_ne_l_invente_pas():
    """Une clé absente se lit « rien à signaler » ; une clé présente sur un
    non-événement se lirait comme un fait."""
    from backend.execution.mission_executor import _decision_en_json
    import json

    meta = {"runtime_demande_par_le_routeur": "ollama",
            "modele_demande_par_le_routeur": "gpt-oss-20b-64k"}
    trace = json.loads(_decision_en_json(meta, "gpt-oss-20b-64k", "ollama"))

    assert "substitution" not in trace
    assert "modele_demande" not in trace


def test_5_l_executeur_publie_le_modele_demande():
    """La trace ne peut dire la substitution que si l'exécuteur transmet la
    **valeur** que le routeur avait choisie.

    Première version : elle cherchait la clé
    `"modele_demande_par_le_routeur"` parmi les chaînes d'`execute`. Une
    mutation qui gardait la clé et vidait sa valeur laissait le test vert —
    mesuré. Une clé présente et vide ne trace rien ; c'est la valeur qui
    fait la preuve.
    """
    from types import SimpleNamespace

    from backend.execution.task_executor import RealTaskExecutor
    from backend.ral.capabilities import ChatResponse

    async def _chat(*, messages, model, **_):
        return ChatResponse(content="fait",
                            metadata={"model": model, "provider": "ollama"})

    executeur = RealTaskExecutor(chat=_chat,
                                 model_for=lambda _t: "gpt-oss-20b-64k",
                                 default_model="gpt-oss-20b-64k")
    tache = SimpleNamespace(task_id="t1", title="écrire un test",
                            description="", task_type="code_generation",
                            mission_id="m1", assigned_skills=[], errors=[])

    resultat = executeur.execute(tache, SimpleNamespace(runtime_id="ollama"))

    assert resultat.metadata["modele_demande_par_le_routeur"] == "gpt-oss-20b-64k", (
        "l'exécuteur ne transmet plus le modèle choisi par le routeur : la "
        "substitution redevient invisible")


# ═══ 6 — l'autorité de sélection reste unique par chemin ════════════

def test_6_le_chemin_mission_a_une_seule_autorite_de_selection():
    """`_model_for` interroge le routeur et rien d'autre.

    Un second choix de modèle sur ce chemin — une constante, une
    préférence lue ailleurs — ferait deux autorités pour une décision.
    """
    source = io.open(RACINE / "backend/core/bootstrap/service_registry.py",
                     encoding="utf-8").read()
    arbre = ast.parse(source)
    fonction = next(n for n in ast.walk(arbre)
                    if isinstance(n, ast.FunctionDef) and n.name == "_model_for")

    appels = {ast.unparse(n.func) for n in ast.walk(fonction)
              if isinstance(n, ast.Call)}
    assert any("recommend_for_text" in a for a in appels), (
        "`_model_for` ne consulte plus le routeur")
    assert not any("load_models_config" in a for a in appels), (
        "`_model_for` puise un modèle hors du routeur")
