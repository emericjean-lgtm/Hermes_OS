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
    """Réécrit en HOS-244 : ce test encodait la contradiction.

    Il exigeait qu'un `openrouter` **gagnant** redescende sur
    `hermes-agent` quand le cloud manque — c'est-à-dire exactement ce que
    la documentation du module interdisait. Le comportement corrigé garde
    le runtime décidé et signale qu'il ne peut pas servir.
    """
    joignable = arbitrer([Proposition("routeur", runtime="openrouter")],
                         cloud_joignable=True)
    injoignable = arbitrer([Proposition("routeur", runtime="openrouter")],
                           cloud_joignable=False)
    assert joignable.runtime == "openrouter"
    assert joignable.impossible == ""
    assert injoignable.runtime == "openrouter"      # rien n'est défait
    assert injoignable.impossible                    # …mais c'est dit
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
         Proposition("routeur", runtime="openrouter", peut_monter=True)],
        cloud_joignable=False)
    assert decision.runtime == "hermes-agent"
    assert decision.repli
    assert "routeur" in decision.repli      # qui avait demandé le cloud
    # Une recommandation défaite n'est pas un échec : elle n'engageait
    # personne, et le repli local était déjà la politique du dépôt.
    assert decision.impossible == ""


def test_une_assignation_explicite_n_est_jamais_annulee_en_silence():
    """Le défaut bloquant de HOS-243, corrigé (HOS-244).

    La version précédente rendait `hermes-agent` ici — elle **annulait
    une assignation explicite**, ce que sa propre documentation
    interdisait deux paragraphes plus haut. Une contradiction entre le
    contrat et le comportement, pas un défaut de documentation.

    Le runtime décidé est conservé ; l'impossibilité de le servir est
    nommée et laissée à l'appelant, qui a déjà un type pour cela.
    """
    decision = arbitrer([Proposition("assignation explicite",
                                     runtime=MONTEE_AUTORISEE)],
                        cloud_joignable=False)
    assert decision.runtime == MONTEE_AUTORISEE
    assert decision.source_runtime == "assignation explicite"
    assert decision.repli == ""            # rien n'a été remplacé
    assert "unavailable" in decision.impossible
    assert "assignation explicite" in decision.impossible
    assert decision.to_dict()["impossible"] == decision.impossible


def test_seul_le_decideur_de_la_tache_peut_faire_monter():
    """HOS-243 cherchait la montée sur **toutes** les propositions.

    N'importe quelle source future qui aurait nommé `openrouter` aurait
    donc hérité d'une autorité que personne ne lui avait donnée. Le droit
    est maintenant porté par la proposition, et faux par défaut.
    """
    sans_droit = arbitrer(
        [Proposition("assignation explicite", runtime="hermes-agent"),
         Proposition("une source quelconque", runtime="openrouter")],
        cloud_joignable=True)
    assert sans_droit.runtime == "hermes-agent"
    assert sans_droit.repli == ""

    avec_droit = arbitrer(
        [Proposition("assignation explicite", runtime="hermes-agent"),
         Proposition("décideur de la tâche", runtime="openrouter",
                     peut_monter=True)],
        cloud_joignable=True)
    assert avec_droit.runtime == "openrouter"


def test_l_executeur_n_accorde_le_droit_de_monter_qu_au_decideur():
    """La règle est tenue **au point d'appel réel**, pas seulement dans
    l'arbitre : une proposition mal étiquetée là-bas rouvrirait la porte
    que celle-ci ferme."""
    arbre = ast.parse(io.open(
        RACINE / "backend" / "execution" / "task_executor.py",
        encoding="utf-8").read())
    montants = []
    for noeud in ast.walk(arbre):
        if (isinstance(noeud, ast.Call)
                and ast.unparse(noeud.func) == "Proposition"
                and any(k.arg == "peut_monter"
                        and getattr(k.value, "value", False) is True
                        for k in noeud.keywords)):
            montants.append(noeud.args[0].value if noeud.args else "?")
    assert montants == ["décideur de la tâche"], (
        f"le droit de monter vers le cloud est accordé à {montants} — il "
        "est réservé au décideur de la tâche (HOS-244)")


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


# ═══ HOS-244 — l'assignation explicite, sur le chemin réel ══════════

def test_le_chemin_reel_refuse_d_annuler_une_assignation_explicite():
    """§2 : exercé par `RealTaskExecutor.execute()`, pas par `arbitrer`.

    Une tâche assignée à `openrouter`, aucun client cloud. La version
    HOS-243 exécutait la tâche **en local** et rendait un résultat : la
    mission réussissait, le registre inscrivait un modèle local, et
    l'opérateur qui avait demandé le cloud ne l'apprenait que dans un
    journal.

    Le contrat corrigé lève `RuntimeUnavailableError` — le type que ce
    module porte déjà pour « the inference layer is down », retryable et
    jamais la faute de la tâche.
    """
    from backend.execution.task_executor import RuntimeUnavailableError

    appeles = []

    async def _c(*, messages, model, **_):
        appeles.append(model)
        return ChatResponse(content="jamais", metadata={"model": model})

    executeur = RealTaskExecutor(chat=_c, cloud_chat=None,
                                 model_for=lambda _t: "un-modele")

    with pytest.raises(RuntimeUnavailableError) as leve:
        executeur.execute(_tache(runtime="openrouter"),
                          SimpleNamespace(runtime_id="openrouter"))

    assert "openrouter" in str(leve.value)
    assert "unavailable" in str(leve.value)
    assert "explicitly assigned" in str(leve.value)
    # Et surtout : rien n'a été exécuté ailleurs pendant ce temps.
    assert appeles == [], "la tâche a tourné sur un autre runtime"


def test_l_echec_est_classe_fournisseur_et_reste_reprenable():
    """La politique de repli **existante** prend le relais.

    Le message est écrit pour que `backend.runs.taxonomie` le classe sans
    modification : c'est la politique déjà écrite qu'on applique là où
    elle manquait, pas une politique nouvelle.
    """
    from backend.runs.taxonomie import classer, remede

    classement = classer(
        "runtime 'openrouter' was explicitly assigned by assignation "
        "explicite but is unavailable: no cloud provider is configured")
    assert classement.classe
    assert classement.cause.value == "fournisseur"

    soin = remede(classement.cause)
    assert soin.reessayer                    # jamais la faute de la tâche
    assert soin.changer_de_fournisseur       # le remède qui correspond
    assert not soin.changer_de_modele        # le modèle n'est pas en cause


def test_une_recommandation_cloud_defaite_execute_toujours(registre):
    """Le pendant : une **recommandation** n'échoue pas.

    Elle n'engageait personne, et l'interdire ferait échouer toute
    mission sur une installation sans clé — le cas par défaut, mesuré en
    J17. La tâche tourne, le repli est nommé, et le registre reçoit ce
    qui a réellement servi.
    """
    from backend.execution.mission_executor import _decision_en_json

    async def _c(*, messages, model, **_):
        return ChatResponse(content="fait",
                            metadata={"model": model, "provider": "ollama",
                                      "fournisseur": "local"})

    executeur = RealTaskExecutor(chat=_c, cloud_chat=None,
                                 runtime_for=lambda _t: "openrouter",
                                 model_for=lambda _t: "qwen3.6-35b-a3b")
    resultat = executeur.execute(_tache(runtime="ollama"),
                                 SimpleNamespace(runtime_id="ollama"))

    assert resultat.runtime_id == "ollama"
    arbitrage = resultat.metadata["arbitrage"]
    assert "impossible" not in arbitrage
    assert "openrouter" in arbitrage["repli"]

    # …et la trace atteint le registre, relisible après coup.
    run = registre.ouvrir(mission="m", objectif="o", runtime="openrouter")
    registre.demarrer(run.identifiant)
    registre.constater(
        run.identifiant, runtime=resultat.runtime_id,
        modele=resultat.model, fournisseur=resultat.metadata["fournisseur"],
        decision=_decision_en_json(resultat.metadata, resultat.model,
                                   resultat.runtime_id))
    registre.terminer(run.identifiant, Statut.REUSSI)

    trace = json.loads(registre.lire(run.identifiant).decision)
    assert trace["runtime_demande"] == "openrouter"
    assert trace["runtime_servi"] == "ollama"
    assert "openrouter indisponible" in trace["repli"]


# ═══ HOS-244 §5 — la frontière, sur les appelants réels ═════════════

#: Les deux méthodes par lesquelles chacun des deux routeurs décide.
#: Relevées sur les signatures, pas devinées.
DECIDE_AGENTIQUE = "select_model"        # core.router.ModelRouter
DECIDE_MISSIONNEL = "recommend_for_text"  # AdaptiveModelRouter


def _appelants(methode: str) -> set[str]:
    trouves: set[str] = set()
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
                    and ast.unparse(noeud.func).endswith("." + methode)):
                trouves.add(str(fichier.relative_to(RACINE)).replace("\\", "/"))
    return trouves


def test_aucun_module_ne_consulte_les_deux_routeurs():
    """La preuve demandée : **aucun chemin actuel** n'en fait deux
    autorités successives.

    Plus forte que la garde de HOS-243, qui ne regardait que les imports
    de deux fichiers nommés. Celle-ci croise les appelants réels des deux
    méthodes de décision, dans tout le backend.

    `service_registry` **construit** un `ModelRouter` pour le
    décomposeur et l'exécuteur natif, et **appelle** `recommend_for_text`
    pour l'exécuteur de tâches. C'est une racine de composition : elle
    câble, elle ne décide pas — et elle n'apparaît donc pas dans
    l'intersection, qui porte sur les appels de décision.

    **Limite** : la garde ne suit pas un appel dynamique (`getattr`, un
    dictionnaire de rappels). Elle attrape la contamination écrite en
    clair, qui est la façon dont ces deux routeurs se sont répandus.
    """
    agentique = _appelants(DECIDE_AGENTIQUE)
    missionnel = _appelants(DECIDE_MISSIONNEL)
    assert agentique, "le routeur de rôles n'a plus d'appelant — carte périmée"
    assert missionnel, "le routeur missionnel n'a plus d'appelant"
    assert not (agentique & missionnel), (
        f"{sorted(agentique & missionnel)} consulte les deux routeurs — "
        "deux autorités trancheraient la même décision")


def test_les_deux_chemins_restent_ceux_qui_ont_ete_mesures():
    """Une frontière qui bouge sans qu'on le sache n'est plus une
    frontière. Les appelants sont figés à ce qui a été mesuré ; en
    ajouter un demande de le classer."""
    assert _appelants(DECIDE_AGENTIQUE) == {
        "backend/agents/base_agent.py",
        "backend/agents/specialized/code_intelligence/hermes_native_executor.py",
        "backend/mission/planner/task_decomposer.py",
    }
    assert _appelants(DECIDE_MISSIONNEL) == {
        "backend/core/bootstrap/service_registry.py",
        "backend/model_intelligence/routes.py",
    }
