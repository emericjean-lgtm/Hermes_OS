"""Une seule autorité tranche, et elle l'écrit (HOS-243).

## Ce que la mesure a trouvé — et qui corrige la passe précédente

HOS-242 avait rapporté « deux décideurs concurrents ». La mesure était
incomplète : elle comptait les **constructions** de classes, et manquait
tout composant obtenu par un accesseur ou un attribut. Tracés cette fois
sur les appels **et** les définitions de méthodes, **huit** composants
décident d'un runtime, d'un modèle ou d'un fournisseur :

1. `AdaptiveModelRouter` — modèle, runtime, num_ctx ; chemin missionnel ;
2. `autonomous.DecisionEngine` — runtime ; il pose `assigned_runtime` sur
   les buts autonomes, et cette valeur **est** lue par l'exécuteur ;
3. `core.router.ModelRouter` — modèle par rôle (`config/models.yaml`) ;
   agents, planificateur, exécuteur natif ;
4. `RuntimeRecommender` — runtime et modèle ; planification de mission ;
5. `ral.courtier` — quel fournisseur cloud, une fois le runtime décidé ;
6. `runtime.orchestrator.DecisionPipeline` — classe des candidats pour
   l'API d'observabilité ; **rien ne s'exécute sur son classement** ;
7. `RuntimeDecisionEngine` (RAL) — runtime ; hors chemin (ci-dessous) ;
8. `sds/routes.py` — un opérateur bascule le runtime actif par HTTP ; ce
   n'est pas une décision autonome.

Le compte est monté de deux à six puis à huit au fil de trois mesures.
Chaque hausse venait du même défaut de méthode : chercher des noms de
classes plutôt que des appels, puis des appels plutôt que des définitions.

## Le défaut réel : la concurrence, pas la pluralité

Huit décideurs ne sont pas un défaut en soi — ils répondent à huit
questions, chacun avec ses propres données et ses propres mesures. Le
défaut est que **deux d'entre eux tranchaient la même requête** :

    runtime_id = _runtime_demande(assignment.runtime_id
                                  or task.assigned_runtime)   # ① ou ③
    ...
    runtime_demande = self._resolve_runtime(task)             # ①
    use_cloud = self._cloud_chat is not None and runtime_demande == "openrouter"
    if use_cloud:
        runtime_id = "openrouter"

Lequel l'emportait n'était écrit nulle part : c'était une propriété
émergente de l'ordre des lignes. `ral.arbitrage` l'écrit.

## Ce que `arbitrage` n'est pas

Pas un septième décideur. Il ne classe aucun modèle, n'interroge aucun
profil, ne mesure aucune VRAM, ne contacte rien. Il range des avis déjà
formés dans une précédence déclarée. Les six restent où ils sont.

## La pile RAL, mesurée deux fois

`RuntimeRouter`, `RuntimeDecisionEngine` et `RuntimeSelector` **sont**
appelés — contrairement à ce que HOS-242 a rapporté. Mais leurs seuls
appelants sont `ExecutionEngine` et `MissionControlAPI`, qui ne sont
construits nulle part hors des tests, et le rappel `runtime_selector` du
superviseur n'est passé par personne. Ils sont donc hors production, et
dépréciés explicitement plutôt que supprimés : ils portent leurs propres
tests, et les effacer détruirait un travail mesuré sans rien corriger.
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
from backend.ral.arbitrage import (
    MONTEE_AUTORISEE,
    Decision,
    Proposition,
    arbitrer,
)
from backend.ral.capabilities import ChatResponse
from backend.runs.registre import Registre, Statut
from backend.storage.database_manager import DatabaseManager

RACINE = Path(__file__).resolve().parents[2]


def _tache(titre="écrire un test", runtime="", identifiant="t1"):
    return SimpleNamespace(task_id=identifiant, title=titre, retries=0,
                           assigned_runtime=runtime, mission_id="",
                           task_type="implementation", assigned_tools=[])


def _chat(**meta):
    async def _c(*, messages, model, **_):
        return ChatResponse(content="fait",
                            metadata={"model": model, "provider": "ollama",
                                      "fournisseur": "local", **meta})
    return _c


# ═══ Test 1 — une demande missionnelle traverse l'autorité ═══════════

def test_une_demande_missionnelle_passe_par_l_arbitre():
    """Le chemin réel, pas `arbitrer(...) == ...`.

    Un vrai `RealTaskExecutor.execute()`, avec deux décideurs qui ont un
    avis, et l'assurance que le modèle réellement appelé est celui que
    l'arbitrage a désigné.
    """
    appeles = []

    async def _c(*, messages, model, **_):
        appeles.append(model)
        return ChatResponse(content="fait",
                            metadata={"model": model, "provider": "ollama",
                                      "fournisseur": "local"})

    executeur = RealTaskExecutor(chat=_c, model_for=lambda _t: "qwen3.6-35b-a3b",
                                 default_model="jamais")
    resultat = executeur.execute(_tache(), SimpleNamespace(runtime_id="ollama"))

    assert appeles == ["qwen3.6-35b-a3b"]
    arbitrage = resultat.metadata["arbitrage"]
    assert arbitrage["runtime"] == "ollama"
    assert arbitrage["modele"] == "qwen3.6-35b-a3b"
    assert arbitrage["source_runtime"] == "assignation explicite"


def test_l_arbitrage_voyage_dans_le_resultat():
    """Une décision qu'on ne peut pas relire n'a pas été prise devant
    témoin."""
    executeur = RealTaskExecutor(chat=_chat())
    resultat = executeur.execute(_tache(), SimpleNamespace(runtime_id="ollama"))
    for cle in ("runtime", "modele", "source_runtime", "source_modele"):
        assert cle in resultat.metadata["arbitrage"]


# ═══ Test 2 — le chemin agentique, et son exemption démontrée ═══════

def test_le_chemin_agentique_ne_decide_pas_du_meme_objet():
    """`core.router.ModelRouter` n'est **pas** une autorité concurrente.

    Il répond à « quel modèle sert le rôle *reasoning* ? » à partir de
    `config/models.yaml`, dont les tags portent les fenêtres de contexte
    servies (`qwen3.5:9b-128k`, `gemma4:12b-64k`). `AdaptiveModelRouter`
    répond à « quel modèle a le mieux réussi ce type de tâche, dans cette
    VRAM ? » à partir de profils mesurés.

    Deux questions, deux catalogues, deux chemins — et surtout : **jamais
    la même requête**. Un agent ne passe pas par `RealTaskExecutor`, et
    une tâche de mission ne demande pas de rôle.

    L'exemption tient tant que cette séparation tient. La garde
    ci-dessous la tient.
    """
    from backend.core.router import ModelRouter

    arbre = ast.parse(io.open(RACINE / "backend" / "core" / "router.py",
                              encoding="utf-8").read())
    modules = {n.module for n in ast.walk(arbre)
               if isinstance(n, ast.ImportFrom) and n.module}
    assert not any("model_intelligence" in (m or "") for m in modules), (
        "le routeur de rôles consulte les profils : les deux catalogues "
        "fusionnent, et l'exemption ne tient plus")
    assert not any("adaptive" in (m or "") for m in modules)
    assert hasattr(ModelRouter, "select_model")


def test_aucun_routeur_de_role_n_est_appele_depuis_l_executeur():
    """La frontière, tenue sur les imports du chemin missionnel.

    Si `task_executor` se mettait à demander un rôle, les deux
    catalogues décideraient la même requête et l'exemption tomberait.
    """
    arbre = ast.parse(io.open(
        RACINE / "backend" / "execution" / "task_executor.py",
        encoding="utf-8").read())
    modules = {n.module for n in ast.walk(arbre)
               if isinstance(n, ast.ImportFrom) and n.module}
    assert not any((m or "").endswith("core.router") for m in modules), (
        "l'exécuteur de tâches consulte le routeur de rôles — deux "
        "autorités trancheraient la même requête")


# ═══ Test 3 — des contraintes différentes, des décisions différentes ═

def test_deux_demandes_differentes_donnent_deux_decisions():
    joignable = arbitrer([Proposition("routeur", runtime="openrouter")],
                         cloud_joignable=True)
    injoignable = arbitrer([Proposition("routeur", runtime="openrouter")],
                           cloud_joignable=False)
    assert joignable.runtime == "openrouter"
    assert injoignable.runtime == "hermes-agent"
    assert joignable != injoignable


def test_la_precedence_est_declaree_et_non_emergente():
    """La première proposition qui propose quelque chose l'emporte.

    C'est l'ordre de la liste qui décide, et il est écrit à un seul
    endroit — au lieu d'être la position des lignes dans une fonction de
    cent lignes.
    """
    decision = arbitrer([Proposition("premier", runtime="a"),
                         Proposition("second", runtime="b")])
    assert decision.runtime == "a"
    assert decision.source_runtime == "premier"

    # Une proposition vide laisse passer la suivante — et la source le dit.
    decision = arbitrer([Proposition("premier", runtime=""),
                         Proposition("second", runtime="b")])
    assert decision.runtime == "b"
    assert decision.source_runtime == "second"


@pytest.mark.parametrize("non_choix", ["", "  ", "default", "auto", "any",
                                       "None", "Default"])
def test_un_non_choix_n_est_pas_une_decision(non_choix):
    """`agent_coordinator._select_runtime` rend littéralement `"default"`
    sur registre vide — HOS-142 a payé une nuit entière pour l'apprendre.
    Le prendre au mot ferait passer une absence de choix pour un choix.
    """
    decision = arbitrer([Proposition("coordinateur", runtime=non_choix),
                         Proposition("routeur", runtime="ollama")])
    assert decision.runtime == "ollama"
    assert decision.source_runtime == "routeur"


# ═══ Test 4 — un repli ne contourne pas l'autorité ══════════════════

def test_le_repli_passe_par_l_arbitre_et_se_nomme():
    decision = arbitrer(
        [Proposition("assignation explicite", runtime="hermes-agent"),
         Proposition("routeur", runtime="openrouter")],
        cloud_joignable=False)
    assert decision.runtime == "hermes-agent"
    assert decision.repli
    assert "routeur" in decision.repli      # qui avait demandé le cloud


def test_un_cloud_assigne_mais_injoignable_retombe_et_le_dit():
    """Cas D : le fournisseur est indisponible alors qu'il était assigné,
    pas seulement recommandé. Le repli reste autorisé, jamais muet."""
    decision = arbitrer([Proposition("assignation explicite",
                                     runtime=MONTEE_AUTORISEE)],
                        cloud_joignable=False)
    assert decision.runtime == "hermes-agent"
    assert "injoignable" in decision.repli
    assert decision.source_runtime == "repli, cloud injoignable"


def test_sans_repli_rien_n_est_invente():
    decision = arbitrer([Proposition("routeur", runtime="ollama")])
    assert decision.repli == ""
    assert "repli" not in decision.to_dict()


def test_le_routeur_ne_peut_pas_defaire_une_assignation_vers_le_bas():
    """Il peut faire **monter** vers le cloud, jamais redescendre.

    Défaire une assignation explicite serait exactement la seconde
    autorité que ce module supprime.
    """
    decision = arbitrer(
        [Proposition("assignation explicite", runtime="hermes-agent"),
         Proposition("routeur", runtime="ollama")],
        cloud_joignable=True)
    assert decision.runtime == "hermes-agent"
    assert decision.source_runtime == "assignation explicite"


# ═══ Test 5 — aucun second routeur invoqué sur le chemin ════════════

#: Les décideurs mesurés, et le chemin sur lequel chacun est autorisé.
#: Une entrée nouvelle doit être classée avant d'exister.
DECIDEURS_CONNUS = {
    # ── Sur un chemin d'inférence, et donc arbitrés ──────────────────
    "backend/model_intelligence/adaptive_router.py": "missionnel — via arbitrage",
    "backend/autonomous/decision_engine.py": "autonome — pose assigned_runtime, arbitré",
    # ── Sur un autre chemin, exemption démontrée ci-dessus ───────────
    "backend/core/router.py": "agentique — rôles de models.yaml",
    "backend/mission/planner/runtime_recommender.py": "planification — avant exécution",
    # ── Auxiliaires : décident d'autre chose que runtime/modèle ──────
    "backend/ral/courtier.py": "quel fournisseur cloud, une fois le runtime décidé",
    "backend/runtime/orchestrator/decision_pipeline.py":
        "classe des candidats pour l'API d'observabilité — rien ne s'exécute dessus",
    "backend/ral/arbitrage.py": "l'arbitre lui-même",
    # ── Action d'opérateur, pas une décision autonome ────────────────
    "backend/sds/routes.py": "POST /runtimes/{name}/select — un humain choisit",
    # ── Dépréciés : hors production, appelants non construits ────────
    "backend/ral/runtime_decision.py": "déprécié (HOS-243)",
    "backend/ral/runtime_router.py": "déprécié (HOS-243)",
    "backend/ral/runtime_selector.py": "déprécié (HOS-243)",
    "backend/ral/model_router.py": "contrat sans implémentation, déprécié",
    "backend/services/mission_control.py": "délégation ; MissionControlAPI non construite",
}

#: Les verbes par lesquels un composant décide d'un runtime ou d'un
#: modèle — **relevés sur les signatures réelles du dépôt**. La première
#: version de cette liste était devinée et manquait quatre modules ; c'est
#: la garde elle-même qui l'a montré.
VERBES_DE_DECISION = ("select_model", "select_runtime", "recommend_for_text",
                      "recommend_all", "rank_candidates", "evaluate_runtime",
                      "list_compatible")


def _definisseurs_de_decision() -> dict[str, list[str]]:
    """Les modules qui *définissent* une méthode de décision.

    **Limites, explicites :**

    - la garde lit des **définitions** de méthodes aux noms mesurés ; un
      décideur qui nommerait sa méthode autrement lui échappe ;
    - elle ne suit pas les appels dynamiques (`getattr`, dictionnaires de
      rappels) ;
    - elle ne dit pas si le décideur est *appelé*, seulement s'il existe.
      C'est délibéré : un décideur non appelé aujourd'hui est un décideur
      appelé demain, et c'est le moment de le classer.

    Ce qu'elle attrape vraiment : l'apparition d'un septième décideur, qui
    est la façon dont les six précédents sont apparus.
    """
    trouves: dict[str, list[str]] = {}
    for fichier in (RACINE / "backend").rglob("*.py"):
        if "tests" in fichier.parts:
            continue
        try:
            arbre = ast.parse(io.open(fichier, encoding="utf-8",
                                      errors="replace").read())
        except SyntaxError:  # pragma: no cover
            continue
        noms = [n.name for n in ast.walk(arbre)
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                and n.name in VERBES_DE_DECISION]
        if noms:
            trouves[str(fichier.relative_to(RACINE)).replace("\\", "/")] = noms
    return trouves


def test_aucun_septieme_decideur_non_classe():
    """Un décideur nouveau doit être classé avant d'exister.

    Sans cela, la cartographie vieillit en silence et « une seule
    autorité » redevient une affirmation invérifiable — ce qu'elle a été
    pendant deux passes.
    """
    nouveaux = set(_definisseurs_de_decision()) - set(DECIDEURS_CONNUS)
    assert not nouveaux, (
        f"décideur de routage non classé : {sorted(nouveaux)} — range-le "
        "dans DECIDEURS_CONNUS avec son chemin, ou fais-le passer par "
        "`ral.arbitrage`")


def test_la_carte_des_decideurs_ne_prend_pas_de_retard():
    """Une entrée qui ne correspond plus à rien rendrait la table
    rassurante et fausse. Les modules dépréciés sont exemptés : ils
    définissent toujours leurs méthodes, c'est leur appel qui a disparu.
    """
    reels = set(_definisseurs_de_decision())
    # `arbitrage`, `courtier`, `model_router` et `runtime_router` nomment
    # leurs méthodes autrement (`arbitrer`, `choisir`, `decide`, `chat`) :
    # la garde lit une liste de verbes mesurés, pas tous les verbes
    # possibles, et prétendre le contraire serait la rendre fausse.
    NOMMENT_AUTREMENT = ("arbitrage", "courtier", "model_router",
                         "runtime_router")
    fantomes = {c for c in DECIDEURS_CONNUS
                if c not in reels and not any(n in c for n in NOMMENT_AUTREMENT)}
    assert not fantomes, f"la table cite des modules sans décideur : {sorted(fantomes)}"


def test_l_executeur_n_appelle_qu_un_seul_arbitre():
    """Deux appels à `arbitrer` seraient deux décisions, donc aucune."""
    arbre = ast.parse(io.open(
        RACINE / "backend" / "execution" / "task_executor.py",
        encoding="utf-8").read())
    appels = [n for n in ast.walk(arbre)
              if isinstance(n, ast.Call) and ast.unparse(n.func) == "arbitrer"]
    assert len(appels) == 1, (
        f"{len(appels)} arbitrages dans task_executor — la décision "
        "redeviendrait une propriété de l'ordre des lignes")


def test_la_pile_ral_depreciee_reste_hors_production():
    """`ExecutionEngine` et `MissionControlAPI` sont ses seuls appelants,
    et ni l'un ni l'autre n'est construit hors des tests.

    La garde tient cet état : les brancher exigerait d'en faire l'arbitre,
    pas d'ajouter une seconde autorité à côté.
    """
    constructions: dict[str, list[str]] = {}
    for fichier in (RACINE / "backend").rglob("*.py"):
        if "tests" in fichier.parts:
            continue
        try:
            arbre = ast.parse(io.open(fichier, encoding="utf-8",
                                      errors="replace").read())
        except SyntaxError:  # pragma: no cover
            continue
        for noeud in ast.walk(arbre):
            if (isinstance(noeud, ast.Call)
                    and ast.unparse(noeud.func).split(".")[-1] in
                    ("ExecutionEngine", "MissionControlAPI")):
                constructions.setdefault(
                    ast.unparse(noeud.func).split(".")[-1], []).append(
                        str(fichier.relative_to(RACINE)))
    assert not constructions, (
        f"un point d'entrée déprécié est de nouveau construit : "
        f"{constructions} — il amènerait avec lui RuntimeDecisionEngine et "
        "RuntimeRouter, soit une seconde autorité de routage")


def test_les_modules_deprecies_le_disent_dans_leur_docstring():
    """Une dépréciation qui n'est écrite que dans un CHANGELOG se perd au
    premier développeur qui ouvre le fichier."""
    for module in ("runtime_router", "runtime_decision", "runtime_selector",
                   "model_router"):
        source = io.open(RACINE / "backend" / "ral" / f"{module}.py",
                         encoding="utf-8").read()
        assert "HOS-243" in source[:4000], f"{module} ne dit pas qu'il est hors chemin"


# ═══ Test 6 et 7 — la décision persiste, et se relit ════════════════

@pytest.fixture
def registre(tmp_path: Path) -> Registre:
    return Registre(DatabaseManager(DatabaseConfig(name=str(tmp_path / "runs"))))


def test_la_decision_arbitree_atteint_le_registre(registre):
    from backend.execution.mission_executor import _decision_en_json

    run = registre.ouvrir(mission="m", objectif="o", runtime="openrouter")
    registre.demarrer(run.identifiant)
    registre.constater(
        run.identifiant, runtime="ollama", modele="qwen3.6-35b-a3b",
        fournisseur="local",
        decision=_decision_en_json(
            {"runtime_demande_par_le_routeur": "openrouter",
             "fournisseur": "local"}, "qwen3.6-35b-a3b", "ollama"))
    registre.terminer(run.identifiant, Statut.REUSSI)

    trace = json.loads(registre.lire(run.identifiant).decision)
    assert trace["runtime_demande"] == "openrouter"
    assert trace["runtime_servi"] == "ollama"


def test_la_trace_survit_a_un_redemarrage(tmp_path):
    """Test 7 : relue par une **autre** instance, sur le disque."""
    base = tmp_path / "runs"
    premier = Registre(DatabaseManager(DatabaseConfig(name=str(base))))
    run = premier.ouvrir(mission="m", objectif="o")
    premier.demarrer(run.identifiant)
    premier.constater(run.identifiant, runtime="ollama",
                      decision='{"runtime_servi": "ollama"}')
    premier.terminer(run.identifiant, Statut.REUSSI)

    second = Registre(DatabaseManager(DatabaseConfig(name=str(base))))
    assert json.loads(second.lire(run.identifiant).decision) == {
        "runtime_servi": "ollama"}


# ═══ Test 8 — §4 n'a pas bougé ══════════════════════════════════════

def test_perdu_reste_productible(registre):
    """La consolidation du routage ne doit pas casser le Ledger."""
    from backend.runs.reconciliation import reconcilier

    run = registre.ouvrir(mission="m", objectif="o")
    registre.demarrer(run.identifiant)
    registre._db.execute("UPDATE runs SET processus = ? WHERE identifiant = ?",
                         ("4194304:1.0", run.identifiant))

    assert run.identifiant in reconcilier(registre).perdus
    apres = registre.lire(run.identifiant)
    assert apres.statut is Statut.PERDU
    assert apres.cause.value == "processus"


# ═══ §9 — la gouvernance n'est pas contournée ═══════════════════════

def test_l_arbitre_ne_sait_pas_joindre_un_fournisseur():
    """`cloud_joignable` est un **fait mesuré passé par l'appelant**.

    Un arbitre qui interrogerait lui-même les fournisseurs deviendrait
    une autorité de sécurité — il pourrait conclure « joignable » sans
    passer par le pare-feu de données ni par le courtier.
    """
    import inspect

    from backend.ral import arbitrage

    arbre = ast.parse(inspect.getsource(arbitrage))
    modules = {n.module for n in ast.walk(arbre)
               if isinstance(n, ast.ImportFrom) and n.module}
    interdits = {"backend.ral.fournisseurs", "backend.ral.courtier",
                 "backend.security.pare_feu", "backend.connectors.openrouter_client"}
    assert not (modules & interdits), (
        f"l'arbitre importe {modules & interdits} — il pourrait conclure "
        "à la disponibilité sans passer par la gouvernance")


def test_l_arbitre_ne_contacte_rien():
    """Aucune E/S : il range des avis, il ne les forme pas."""
    import inspect

    from backend.ral import arbitrage

    source = inspect.getsource(arbitrage)
    arbre = ast.parse(source)
    appels = {ast.unparse(n.func) for n in ast.walk(arbre)
              if isinstance(n, ast.Call)}
    assert not any(a.startswith(("httpx", "requests", "await", "open"))
                   for a in appels)
    assert "async def" not in source, (
        "un arbitre asynchrone attendrait quelque chose — donc contacterait "
        "quelque chose")


def test_l_arbitrage_precede_le_pare_feu_et_ne_le_remplace_pas():
    """L'arbitre choisit le runtime ; le pare-feu décide ce qui peut
    partir. Le second reste en aval et obligatoire.
    """
    arbre = ast.parse(io.open(
        RACINE / "backend" / "core" / "bootstrap" / "service_registry.py",
        encoding="utf-8").read())
    cloud = next(n for n in ast.walk(arbre)
                 if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                 and n.name == "_cloud_chat")
    corps = ast.unparse(cloud)
    assert "pare_feu.examiner" in corps
    assert "arbitrer" not in corps, (
        "l'arbitrage a migré dans le chemin cloud — il y aurait deux "
        "arbitrages pour une requête")
