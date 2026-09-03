"""Qui décide du runtime et du modèle, et qui le sait après (HOS-242).

## Ce que la cartographie a mesuré

13 constructions réelles de `OllamaClient` en production, dans 8
fichiers. Cinq sont de l'**infrastructure** — `/api/ps`, `list_local_models`,
`unload_model` — et ne comportent aucune décision de routage : rien à
router quand on demande à Ollama ce qu'il détient. Une est le **RAL
lui-même** (`sds/runtime.py` enregistre le constructeur `ollama` dans la
Factory). Les sept autres sont sur un chemin d'inférence.

## Ce qui n'était pas un défaut

`RealTaskExecutor` lit le runtime servi **dans la réponse**, pas dans la
demande. `_make_cloud_chat` passe par le pare-feu de données puis par le
courtier avant tout envoi distant. La gouvernance est en place.

## Ce qui en était un

`metadata["provider"]` valait `"ollama"` ou `"openrouter"` — c'est-à-dire
le **runtime**, jamais le fournisseur. Or OpenRouter n'exécute rien : il
route vers un hébergeur amont qu'il nomme dans sa propre réponse. Trois
fournisseurs pouvaient servir le même modèle avec trois latences, et
Hermes les appelait tous « openrouter ».

Et le repli distant → local était muet. Sans clé configurée — le défaut
mesuré en J17 — le routeur recommandait le cloud, `_runtime_for` rendait
« hermes-agent », et rien ne le disait. Le registre inscrivait le runtime
demandé : l'opérateur croyait avoir payé du cloud.

## La limite de ces gardes

Le champ `provider` d'OpenRouter est lu **défensivement** : aucune clé
n'étant configurée sur cette installation, il n'a pas été observé sur une
réponse réelle. Son absence n'invente rien — c'est tout ce que ces gardes
peuvent promettre, et elles le disent.
"""

from __future__ import annotations

import ast
import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.config.config_models import DatabaseConfig
from backend.execution.task_executor import RealTaskExecutor
from backend.ral.capabilities import ChatResponse
from backend.runs.registre import Registre, Statut
from backend.storage.database_manager import DatabaseManager

RACINE = Path(__file__).resolve().parents[2]


def _tache(titre="écrire un test", runtime="", identifiant="t1"):
    return SimpleNamespace(task_id=identifiant, title=titre, retries=0,
                           assigned_runtime=runtime, mission_id="",
                           task_type="implementation", assigned_tools=[])


def _chat_qui_rapporte(**meta):
    """Un runtime qui déclare ce qu'il a vraiment fait."""
    async def _chat(*, messages, model, **_):
        return ChatResponse(content="fait", metadata={"model": model, **meta})
    return _chat


# ═══ §15 — la décision est réellement consommée ══════════════════════

def test_le_modele_choisi_par_le_decideur_est_celui_qui_est_appele():
    """Le test qu'un `assert routeur.choisit(...) == ...` ne remplace pas.

    Ce qui compte n'est pas que le décideur sache choisir, mais que son
    choix **arrive jusqu'à l'appel**. Le décideur est ici une fonction
    qui trace ce qu'on lui demande ; l'inférence est un faux runtime qui
    rapporte ce qu'il a reçu. Entre les deux, le vrai `execute()`.
    """
    demandes, appeles = [], []

    def decideur(task):
        demandes.append(task.title)
        return "qwen3.6-35b-a3b"

    async def _chat(*, messages, model, **_):
        appeles.append(model)
        return ChatResponse(content="fait",
                            metadata={"model": model, "provider": "ollama",
                                      "fournisseur": "local"})

    executeur = RealTaskExecutor(model_for=decideur, chat=_chat,
                                 default_model="jamais-celui-la")
    resultat = executeur.execute(_tache(), SimpleNamespace(runtime_id="ollama"))

    assert demandes == ["écrire un test"]      # le décideur a été consulté
    assert appeles == ["qwen3.6-35b-a3b"]      # …et son choix appelé
    assert resultat.model == "qwen3.6-35b-a3b"
    assert "jamais-celui-la" not in appeles


def test_le_defaut_ne_sert_que_faute_de_decideur():
    """Sans décideur, l'exécuteur ne fabrique pas un choix : il prend son
    défaut, ce qui est un comportement documenté et non une décision."""
    executeur = RealTaskExecutor(chat=_chat_qui_rapporte(provider="ollama"),
                                 default_model="le-defaut")
    assert executeur.execute(_tache(), SimpleNamespace(runtime_id="ollama")
                             ).model == "le-defaut"


# ═══ §10, §11, §19 — runtime, modèle, fournisseur ════════════════════

def test_les_trois_sont_distincts_en_local():
    """`runtime = ollama`, `provider = local`, `model = …`.

    Les deux premiers valaient « ollama » et étaient indiscernables.
    """
    executeur = RealTaskExecutor(
        chat=_chat_qui_rapporte(provider="ollama", fournisseur="local"),
        model_for=lambda _t: "qwen3.6-35b-a3b")
    resultat = executeur.execute(_tache(), SimpleNamespace(runtime_id="ollama"))

    assert resultat.runtime_id == "ollama"
    assert resultat.model == "qwen3.6-35b-a3b"
    assert resultat.metadata["fournisseur"] == "local"


def test_le_fournisseur_amont_du_cloud_est_celui_de_la_reponse():
    """OpenRouter n'exécute rien : il route. Le nommer « openrouter »
    comme fournisseur perd l'hébergeur qui a réellement servi.
    """
    async def _cloud(*, messages, model, **_):
        return ChatResponse(content="fait",
                            metadata={"model": model, "provider": "openrouter",
                                      "fournisseur": "DeepInfra"})

    executeur = RealTaskExecutor(cloud_chat=_cloud,
                                 runtime_for=lambda _t: "openrouter",
                                 model_for=lambda _t: "un-modele-distant")
    resultat = executeur.execute(_tache(), SimpleNamespace(runtime_id="openrouter"))

    assert resultat.runtime_id == "openrouter"     # la surface appelée
    assert resultat.metadata["fournisseur"] == "DeepInfra"   # qui a servi


def test_un_fournisseur_non_declare_reste_vide_et_n_est_pas_deduit():
    """« On ne sait pas » ne se range pas avec « c'est le runtime ».

    Déduire le fournisseur du runtime ferait passer une supposition pour
    une mesure — et personne ne pourrait plus distinguer les deux.
    """
    executeur = RealTaskExecutor(chat=_chat_qui_rapporte(provider="ollama"))
    resultat = executeur.execute(_tache(), SimpleNamespace(runtime_id="ollama"))
    assert resultat.metadata["fournisseur"] == ""


def test_le_client_ollama_se_declare_local():
    """La source, et non l'exécuteur qui la relaie."""
    import inspect

    from backend.connectors import ollama_client

    source = inspect.getsource(ollama_client.OllamaClient.chat)
    assert '"fournisseur": "local"' in source


def test_le_client_openrouter_lit_le_champ_structure():
    """`ne parse pas une chaîne arbitraire si l'API fournit une
    information structurée` — le champ de premier niveau, pas le modèle.

    **Limite assumée** : aucune clé n'étant configurée ici, ce champ n'a
    pas été observé sur une réponse réelle. La lecture est défensive et
    son absence n'invente rien ; c'est tout ce que cette garde promet.
    """
    import inspect

    from backend.connectors import openrouter_client

    arbre = ast.parse(inspect.getsource(openrouter_client.OpenRouterClient))
    lectures = {ast.unparse(n) for n in ast.walk(arbre)
                if isinstance(n, ast.Call)
                and ast.unparse(n.func).endswith(".get")}
    assert any("'provider'" in l or '"provider"' in l for l in lectures), (
        "le fournisseur amont n'est pas lu dans la réponse d'OpenRouter")


# ═══ §12 — le repli distant → local, explicite ═══════════════════════

def test_une_tache_cloud_sans_client_cloud_reste_tracee():
    """Cas A : le repli est **autorisé** — sans lui toute mission
    échouerait sur une installation sans clé, qui est le défaut mesuré.
    Mais autorisé n'est pas silencieux.
    """
    executeur = RealTaskExecutor(
        chat=_chat_qui_rapporte(provider="ollama", fournisseur="local"),
        runtime_for=lambda _t: "openrouter",     # demandé…
        cloud_chat=None)                          # …mais injoignable
    resultat = executeur.execute(_tache(), SimpleNamespace(runtime_id="ollama"))

    assert resultat.runtime_id == "ollama"        # servi en local
    assert resultat.metadata["runtime_demande_par_le_routeur"] == "openrouter"


def test_le_repli_du_routeur_avertit(caplog):
    """`_runtime_for` défaisait le choix du routeur sans une ligne."""
    import logging

    from backend.core.bootstrap import service_registry as sr

    source = ast.parse(io.open(
        RACINE / "backend" / "core" / "bootstrap" / "service_registry.py",
        encoding="utf-8").read())
    fonction = next(n for n in ast.walk(source)
                    if isinstance(n, ast.FunctionDef) and n.name == "_runtime_for")
    corps = ast.unparse(fonction)
    assert "logger.warning" in corps, (
        "le repli du routeur vers l'agent local est de nouveau silencieux")
    assert corps.count("logger.warning") >= 2, (
        "l'échec du routeur lui-même est encore avalé — une panne du "
        "décideur passerait pour une absence de préférence")


# ═══ §18 — modèle indisponible : la substitution se voit ════════════

def test_une_reprise_change_de_modele_et_le_dit():
    """`_resolve_model` bascule sur `local_fallback_for` dès la première
    reprise (HOS-069). La bascule est légitime — réessayer le modèle qui
    vient d'échouer ne sert à rien — mais elle ne doit pas être muette :
    c'est le modèle **de secours** qui est ensuite inscrit au registre.
    """
    appeles = []

    async def _chat(*, messages, model, **_):
        appeles.append(model)
        return ChatResponse(content="fait",
                            metadata={"model": model, "provider": "ollama",
                                      "fournisseur": "local"})

    executeur = RealTaskExecutor(
        chat=_chat, model_for=lambda _t: "celui-qui-a-echoue",
        local_fallback_for=lambda _t: "le-modele-de-secours")

    premier = _tache(); premier.retries = 0
    executeur.execute(premier, SimpleNamespace(runtime_id="ollama"))

    reprise = _tache(); reprise.retries = 1
    resultat = executeur.execute(reprise, SimpleNamespace(runtime_id="ollama"))

    assert appeles == ["celui-qui-a-echoue", "le-modele-de-secours"]
    # Et c'est le modèle réellement appelé qui remonte, pas celui demandé.
    assert resultat.model == "le-modele-de-secours"


def test_sans_modele_de_secours_la_reprise_ne_substitue_rien():
    """Aucun secours n'est inventé : la reprise repart sur le même modèle,
    ce qui est visible et discutable, plutôt que sur un modèle choisi
    par personne."""
    appeles = []

    async def _chat(*, messages, model, **_):
        appeles.append(model)
        return ChatResponse(content="fait", metadata={"model": model,
                                                      "provider": "ollama"})

    executeur = RealTaskExecutor(chat=_chat, model_for=lambda _t: "le-seul")
    reprise = _tache(); reprise.retries = 3
    executeur.execute(reprise, SimpleNamespace(runtime_id="ollama"))
    assert appeles == ["le-seul"]


# ═══ §20 — traçabilité de bout en bout, dans le registre ════════════

@pytest.fixture
def registre(tmp_path: Path) -> Registre:
    return Registre(DatabaseManager(DatabaseConfig(name=str(tmp_path / "runs"))))


def test_le_registre_repond_aux_six_questions(registre):
    """run_id / runtime / model / provider / décision / repli.

    Toutes dans une seule ligne, relisibles longtemps après que les
    événements du bus ont défilé.
    """
    from backend.execution.mission_executor import _decision_en_json

    run = registre.ouvrir(mission="m", objectif="o", runtime="openrouter")
    registre.demarrer(run.identifiant)

    decision = _decision_en_json(
        {"runtime_demande_par_le_routeur": "openrouter",
         "fournisseur": "local"},
        "qwen3.6-35b-a3b", "ollama")
    registre.constater(run.identifiant, runtime="ollama",
                       modele="qwen3.6-35b-a3b", fournisseur="local",
                       decision=decision)
    registre.terminer(run.identifiant, Statut.REUSSI)

    lu = registre.lire(run.identifiant)
    assert lu.runtime == "ollama"
    assert lu.modele == "qwen3.6-35b-a3b"
    assert lu.fournisseur == "local"
    trace = json.loads(lu.decision)
    assert trace["runtime_demande"] == "openrouter"
    assert trace["runtime_servi"] == "ollama"
    assert "openrouter indisponible" in trace["repli"]


def test_sans_ecart_aucun_repli_n_est_invente(registre):
    """Un routeur qui n'a pas été défait n'a pas de repli à déclarer."""
    from backend.execution.mission_executor import _decision_en_json

    trace = json.loads(_decision_en_json(
        {"runtime_demande_par_le_routeur": "ollama", "fournisseur": "local"},
        "qwen3.6-35b-a3b", "ollama"))
    assert "repli" not in trace


def test_une_decision_sans_fait_reste_vide():
    """Rien de connu, rien d'écrit : `{}` se lirait « décision vide »."""
    from backend.execution.mission_executor import _decision_en_json

    assert _decision_en_json({}, "", "") == ""


def test_une_reprise_ne_herite_pas_du_routage_de_son_parent(registre):
    """Elle sera routée pour elle-même — la reprise change de modèle,
    c'est même sa raison d'être (`local_fallback_for`).
    """
    parent = registre.ouvrir(mission="m", objectif="o")
    registre.demarrer(parent.identifiant)
    registre.constater(parent.identifiant, modele="celui-qui-a-echoue",
                       fournisseur="local", decision='{"runtime_servi":"ollama"}')
    registre.terminer(parent.identifiant, Statut.ECHOUE)

    reprise = registre.reprendre(parent.identifiant, motif="modele inadapte")

    assert reprise.decision == ""
    assert reprise.modele == ""
    assert reprise.fournisseur == ""
    assert reprise.parent == parent.identifiant     # la lignée, elle, tient


# ═══ §16 — anti-contournement ═══════════════════════════════════════

#: Les huit fichiers qui construisent un `OllamaClient` au HEAD de ce
#: jalon, chacun classé. Une construction nouvelle ailleurs fait échouer
#: la garde : elle demande qu'on la classe, pas qu'on l'évite.
CONSTRUCTEURS_CONNUS = {
    # Infrastructure — introspection et VRAM, aucune décision à prendre.
    "backend/api/routes/system.py": "D",
    "backend/runtime/resources/routes.py": "D",
    # Le RAL lui-même : la Factory enregistre le constructeur `ollama`.
    "backend/sds/runtime.py": "RAL",
    # Inférence — la décision vient d'un décideur injecté.
    "backend/execution/task_executor.py": "A+D",
    "backend/conversation/response_generator.py": "B",
    "backend/core/agent_registry.py": "B",
    "backend/core/bootstrap/service_registry.py": "A+B",
    "backend/integrations/hermes_agent/adapter.py": "C",
}


def _constructeurs_ollama() -> dict[str, int]:
    """Les constructions réelles, sur l'arbre syntaxique.

    **Limite** : un `OllamaClient` obtenu autrement qu'en l'appelant —
    passé en paramètre, sorti d'un conteneur — n'est pas vu. Cette garde
    tient l'apparition d'un nouveau *point de construction*, ce qui est
    la façon dont les sept précédents sont apparus, et rien de plus.
    """
    trouves: dict[str, int] = {}
    for fichier in (RACINE / "backend").rglob("*.py"):
        if "tests" in fichier.parts:
            continue
        try:
            arbre = ast.parse(io.open(fichier, encoding="utf-8",
                                      errors="replace").read())
        except SyntaxError:  # pragma: no cover
            continue
        n = sum(1 for noeud in ast.walk(arbre)
                if isinstance(noeud, ast.Call)
                and ast.unparse(noeud.func).endswith("OllamaClient"))
        if n:
            trouves[str(fichier.relative_to(RACINE)).replace("\\", "/")] = n
    return trouves


def test_aucun_nouveau_point_de_construction_non_classe():
    """Un neuvième fichier qui parlerait à Ollama en direct doit être
    classé avant d'exister — sans quoi la cartographie vieillit en
    silence et « le RAL est canonique » redevient une affirmation.
    """
    nouveaux = set(_constructeurs_ollama()) - set(CONSTRUCTEURS_CONNUS)
    assert not nouveaux, (
        f"construction directe d'OllamaClient non classée : {sorted(nouveaux)} "
        "— range-la dans CONSTRUCTEURS_CONNUS avec sa catégorie, ou fais-la "
        "passer par un décideur")


def test_la_cartographie_ne_prend_pas_de_retard_sur_le_code():
    """Une entrée qui ne correspond plus à rien rendrait la table
    rassurante et fausse."""
    disparus = set(CONSTRUCTEURS_CONNUS) - set(_constructeurs_ollama())
    assert not disparus, (
        f"la table cite des fichiers qui ne construisent plus rien : "
        f"{sorted(disparus)}")


def test_l_executeur_ne_code_en_dur_aucun_nom_de_modele():
    """Le seul modèle nommé dans `task_executor` doit être le repli
    mesuré de HOS-095/096, et il doit rester une constante nommée.

    Un tag glissé dans une branche d'exécution serait une décision de
    routage prise hors du décideur — et invisible.
    """
    arbre = ast.parse(io.open(
        RACINE / "backend" / "execution" / "task_executor.py",
        encoding="utf-8").read())

    constantes: list[str] = []
    for noeud in ast.walk(arbre):
        if not isinstance(noeud, ast.Assign):
            continue
        cible = ast.unparse(noeud.targets[0])
        if not (isinstance(noeud.value, ast.Constant)
                and isinstance(noeud.value.value, str)):
            continue
        valeur = noeud.value.value
        # Un **tag** de modele, pas une famille : `runtime_id = "ollama"`
        # contient « llama » et faisait echouer cette garde. Septieme faux
        # positif de sous-chaine sur ce chantier, cette fois dans la garde
        # elle-meme. Un tag porte toujours une taille ou une version.
        if not any(c.isdigit() for c in valeur):
            continue
        if any(m in valeur.lower() for m in
               ("qwen", "gemma", "lfm", "devstral", "llama", "mistral")):
            constantes.append(cible)
    assert constantes == ["_HERMES_AGENT_FALLBACK_MODEL"], (
        f"des tags de modèles sont posés hors du repli mesuré : {constantes}")


def test_le_repli_mesure_reste_une_constante_documentee():
    """HOS-095/096 l'a choisi sur trois essais contre quatre candidats, et
    la constante a déjà bougé deux fois sur mesure. Ces gardes ne le
    suppriment pas : elles exigent qu'il reste nommé et unique.
    """
    from backend.execution.task_executor import _HERMES_AGENT_FALLBACK_MODEL

    assert _HERMES_AGENT_FALLBACK_MODEL == "lfm2.5-2.6b-125k"


def test_aucun_rappel_de_routage_ne_retombe_en_silence():
    """La garde élargie aux **deux** modules du chemin de décision.

    `test_runtime_reellement_utilise` tient déjà les six rappels de
    `RealTaskExecutor` ; ceux-ci sont leurs fournisseurs — les closures de
    `service_registry` qui interrogent réellement le routeur. Un échec avalé
    là rend « le routeur n'a pas d'avis » et « le routeur est en panne »
    strictement indiscernables, à l'endroit précis où la distinction décide
    du modèle qui va tourner.

    **Limite** : la garde lit les gestionnaires d'exception de fonctions
    nommées. Un repli écrit sans `except` — un `if` qui retombe sur un
    défaut — lui échappe.
    """
    ROUTAGE = ("_runtime_for", "_model_for", "_local_fallback_for",
               "_num_ctx_for")
    muets = []
    for chemin in ("backend/core/bootstrap/service_registry.py",
                   "backend/execution/task_executor.py"):
        arbre = ast.parse(io.open(RACINE / chemin, encoding="utf-8").read())
        for noeud in ast.walk(arbre):
            if not isinstance(noeud, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if not (noeud.name.startswith("_resolve_") or noeud.name in ROUTAGE):
                continue
            for gestion in ast.walk(noeud):
                if not isinstance(gestion, ast.ExceptHandler):
                    continue
                corps = " ".join(ast.unparse(n) for n in gestion.body)
                if "logger.warning" not in corps and "raise" not in corps:
                    muets.append(f"{chemin}:{gestion.lineno} ({noeud.name})")
    assert not muets, (
        f"un rappel de routage retombe en silence : {muets} — une panne du "
        "décideur passerait pour une absence de préférence")


# ═══ §21 — la gouvernance reste sur le chemin ═══════════════════════

def test_le_pare_feu_precede_tout_envoi_distant():
    """Après l'envoi, ce serait un constat de fuite.

    Vérifié sur les positions de ligne : `ast.walk` est en largeur, et
    comparer des positions de parcours mesurerait la traversée.
    """
    import inspect

    from backend.core.bootstrap import service_registry as sr

    # `_cloud_chat` est une coroutine : un `ast.FunctionDef` ne la voit
    # pas, et la garde levait `StopIteration` au lieu d'echouer clairement.
    arbre = ast.parse(ast.unparse(next(
        n for n in ast.walk(ast.parse(io.open(
            RACINE / "backend" / "core" / "bootstrap" / "service_registry.py",
            encoding="utf-8").read()))
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        and n.name == "_cloud_chat")))

    lignes = {}
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.Call):
            nom = ast.unparse(noeud.func)
            for verbe, cle in (("pare_feu.examiner", "pare_feu"),
                               ("provider.chat", "envoi")):
                if nom.endswith(verbe) and cle not in lignes:
                    lignes[cle] = noeud.lineno
    assert set(lignes) == {"pare_feu", "envoi"}
    assert lignes["pare_feu"] < lignes["envoi"], (
        "le prompt part avant d'avoir été examiné")


def test_le_courtier_choisit_le_fournisseur_et_non_le_premier_venu():
    """Le RAL décide *quel* fournisseur ; l'adaptateur exécute."""
    import inspect

    from backend.core.bootstrap import service_registry as sr

    source = inspect.getsource(sr._make_cloud_chat)
    assert "courtier" in source and "choisir" in source


def test_le_registre_n_importe_pas_le_ral():
    """Un registre qui déciderait deviendrait un second routeur."""
    arbre = ast.parse(io.open(RACINE / "backend" / "runs" / "registre.py",
                              encoding="utf-8").read())
    modules = {n.module for n in ast.walk(arbre)
               if isinstance(n, ast.ImportFrom) and n.module}
    assert not any("ral" in (m or "").split(".") for m in modules)
