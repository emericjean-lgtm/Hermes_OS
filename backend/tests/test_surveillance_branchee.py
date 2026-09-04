"""Le témoin est posé, et la sortie est regardée (A-2, HOS-256).

## Ce que l'audit J25 a mesuré

`security/surveillance_flux.py` était implémenté, testé, et déclaré
✅ *Fait* au ROADMAP sous HOS-218. Traçage complet — imports absolus et
relatifs, instanciations, appels, décorateurs, chaînes, `getattr`,
imports dynamiques, hooks de démarrage, injections : **zéro référence de
production**. Le module n'était cité que par son propre fichier de test.

Ce n'était pas une protection : c'était du code.

## Ce que la mesure a montré de pire

`hermes_agent_cli` lance le sous-processus avec `os.environ.copy()` —
**tout** l'environnement du parent, chaque secret de la machine — plus un
`OPENAI_API_KEY` explicite. Sa sortie était décodée et analysée pour en
extraire un identifiant de session, et **rien n'y cherchait de secret**.
L'exposition que HOS-218 devait détecter était donc maximale, et la
détection absente.

## Où le contrôle vit désormais, et pourquoi là

Dans `HermesAgentCliChatCapability.chat` : c'est le **seul** endroit du dépôt
où Hermes OS lance un agent. Poser le témoin plus haut — dans l'exécuteur
de tâche, par exemple — laisserait sans surveillance un lanceur qu'on
ajouterait demain. Ici, tout sous-processus d'agent en hérite par
construction.

La surveillance ne tue rien : le processus est déjà terminé quand on
regarde. Ce qu'elle empêche est que le résultat **serve** — un secret
recraché entrerait sinon dans le Run Ledger, dans le relais de contexte,
et dans le prompt suivant : la fuite se propagerait par les mécanismes
mêmes qui servent à tracer.
"""

from __future__ import annotations

import ast
import inspect
import io
import textwrap
from pathlib import Path

import pytest

from backend.ral.adapters.hermes_agent_cli import (
    HermesAgentCliChatCapability,
    HermesAgentCliConfig,
    HermesAgentCliError,
)
from backend.security import surveillance_flux

RACINE = Path(__file__).resolve().parents[2]

CLE = "sk-secret-de-test-0123456789abcdef"


def _runtime() -> HermesAgentCliChatCapability:
    """La capacité de chat : c'est elle qui lance le sous-processus."""
    return HermesAgentCliChatCapability(HermesAgentCliConfig(
        model="m", api_key=CLE, timeout_seconds=5.0))


def _surveiller(rt, stdout: str, stderr: str = "", canary: str = "T-CANARY-0123456789"):
    return rt._surveiller_la_sortie(canary, stdout, stderr,
                                    model="m", task_id="t1")


# ═══ Nominal — une sortie propre passe ═══════════════════════════════

def test_une_sortie_normale_ne_declenche_rien():
    assert _surveiller(_runtime(), "j'ai écrit le fichier app.py, tests verts") is None


def test_une_sortie_vide_ne_declenche_rien():
    assert _surveiller(_runtime(), "", "") is None


# ═══ Refus — la fuite est attrapée ═══════════════════════════════════

def test_le_canary_recrache_est_detecte():
    """« Il a lu son environnement » — on n'a pas besoin de savoir comment."""
    alerte = _surveiller(_runtime(), "voici mes variables : T-CANARY-0123456789")
    assert alerte is not None
    assert alerte.motif is surveillance_flux.Motif.CANARY


def test_la_cle_reelle_recrachee_est_detectee():
    """Le témoin dit « il lit son environnement » ; la clé dit « il a
    recraché celle-là »."""
    alerte = _surveiller(_runtime(), f"j'ai utilisé la clé {CLE}")
    assert alerte is not None
    assert alerte.motif is surveillance_flux.Motif.SECRET


def test_une_fuite_sur_stderr_compte_autant():
    """Un secret sur le canal d'erreur est un secret sorti."""
    alerte = _surveiller(_runtime(), "rien à signaler", f"trace: {CLE}")
    assert alerte is not None


def test_une_fuite_refuse_le_resultat():
    """La surveillance ne tue pas le processus — elle empêche que sa
    sortie serve. Sans ce refus, le secret entrerait dans le Ledger.

    ## Pourquoi deux assertions et pas une

    La première version ne vérifiait que la **forme** : « un `if` sur
    `alerte` qui contient un `raise` ». Une mutation qui remplaçait
    l'examen par `alerte = None` gardait cette forme intacte et laissait
    le test vert — mesuré. La forme sans l'appel ne prouve rien : c'est
    l'appel qui fait la surveillance.
    """
    source = textwrap.dedent(inspect.getsource(HermesAgentCliChatCapability.chat))
    arbre = ast.parse(source)

    appels = {ast.unparse(n.func) for n in ast.walk(arbre)
              if isinstance(n, ast.Call)}
    assert any(a.endswith("_surveiller_la_sortie") for a in appels), (
        "`chat` n'examine pas la sortie du sous-processus")

    leve_sur_alerte = any(
        isinstance(n, ast.If) and "alerte" in ast.unparse(n.test)
        and any(isinstance(c, ast.Raise) for c in ast.walk(n))
        for n in ast.walk(arbre))
    assert leve_sur_alerte, (
        "`chat` ne refuse pas le résultat quand une alerte tombe : la "
        "fuite continuerait vers le Run Ledger et le relais de contexte")


# ═══ Le témoin est réellement posé ═══════════════════════════════════

def test_le_canary_entre_dans_l_environnement_du_sous_processus():
    """La preuve que le témoin part : sans lui dans l'environnement, il
    ne peut rien témoigner."""
    source = textwrap.dedent(inspect.getsource(HermesAgentCliChatCapability.chat))
    appels = {ast.unparse(n.func) for n in ast.walk(ast.parse(source))
              if isinstance(n, ast.Call)}
    assert any(a.endswith("fabriquer_canary") for a in appels), appels
    assert any(a.endswith("environnement_avec_canary") for a in appels), appels


def test_le_canary_porte_un_nom_de_vrai_secret():
    """Un agent qui filtre son environnement sur des noms sensibles doit
    l'attraper aussi, sinon le témoin ne témoigne de rien."""
    env = surveillance_flux.environnement_avec_canary({"PATH": "/x"}, "jeton")
    ajoutes = set(env) - {"PATH"}
    assert ajoutes, "aucune variable ajoutée"
    assert all("TOKEN" in n.upper() or "KEY" in n.upper() or "SECRET" in n.upper()
               for n in ajoutes), ajoutes


def test_deux_lancements_n_ont_pas_le_meme_temoin():
    """Un témoin constant finirait par se retrouver dans un cache, un
    journal ou un dépôt, et cesserait de témoigner."""
    assert surveillance_flux.fabriquer_canary() != surveillance_flux.fabriquer_canary()


# ═══ Anti-contournement, structurel ══════════════════════════════════

def test_tout_lancement_d_agent_passe_par_l_adaptateur_surveille():
    """Le garde-fou qui empêche de refaire A-2.

    La protection ne vaut que tant qu'il n'existe qu'un endroit où un
    agent est lancé. Un second lanceur — même correct par ailleurs —
    naîtrait sans surveillance, exactement comme les replis cloud sont
    nés sans pare-feu (A-1).
    """
    lanceurs: list[str] = []
    for f in (RACINE / "backend").rglob("*.py"):
        if "tests" in f.parts:
            continue
        src = io.open(f, encoding="utf-8", errors="replace").read()
        if "create_subprocess_exec" in src or "subprocess.Popen" in src:
            lanceurs.append(f.relative_to(RACINE).as_posix())

    autorises = {
        # Les deux lanceurs d'agent, et tous deux portent la surveillance.
        # Le second a été trouvé par ce test même, avant que HOS-218 soit
        # déclaré branché : le harnais persistant de HOS-137 lance le même
        # agent, gardé ouvert entre les tâches.
        "backend/ral/adapters/hermes_agent_cli.py",
        "backend/ral/adapters/hermes_agent_acp.py",
        # Ne lance rien : exécuté **par l'interpréteur de l'agent**, il
        # enveloppe `Popen.__init__` pour interdire aux sous-processus de
        # l'agent d'hériter du canal ACP (HOS-138).
        "backend/ral/adapters/lanceur_agent.py",
        # Lance `git`, pas un agent : aucun prompt, aucun environnement
        # d'agent, rien qu'un témoin pourrait surveiller.
        "backend/checkpoints/git_ref.py",
        "backend/tools/git_tools.py",
        # Lance les runners de vérification déclarés en liste blanche
        # (pytest, npm test) : commandes nommées, pas un agent.
        "backend/tools/verification_chat_tools.py",
        # Mesure le GPU (`rocm-smi`) et les processus : lecture seule.
        "backend/monitoring/gpu_monitor.py",
        "backend/model_intelligence/model_bench.py",
    }
    nouveaux = sorted(set(lanceurs) - autorises)
    assert nouveaux == [], (
        f"nouveau lanceur de sous-processus : {nouveaux}. S'il lance un "
        "agent, il doit porter la surveillance de flux ; sinon il doit "
        "être ajouté ici avec la raison écrite.")


def test_la_surveillance_reste_une_seule_autorite():
    """Aucun second détecteur : l'adaptateur délègue au module."""
    source = io.open(RACINE / "backend/ral/adapters/hermes_agent_cli.py",
                     encoding="utf-8").read()
    arbre = ast.parse(source)
    noeud = next(n for n in ast.walk(arbre)
                 if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                 and n.name == "_surveiller_la_sortie")
    appels = {ast.unparse(c.func) for c in ast.walk(noeud)
              if isinstance(c, ast.Call)}
    assert any("surveillance_flux.SurveillanceFlux" in a for a in appels), appels


def test_le_module_n_est_plus_orphelin():
    """La mesure qui a produit A-2, rejouée : elle doit désormais trouver
    un consommateur de production."""
    consommateurs: list[str] = []
    for f in (RACINE / "backend").rglob("*.py"):
        if "tests" in f.parts or f.name == "surveillance_flux.py":
            continue
        src = io.open(f, encoding="utf-8", errors="replace").read()
        if "surveillance_flux" in src:
            consommateurs.append(f.relative_to(RACINE).as_posix())
    assert consommateurs, (
        "aucun module de production n'utilise `surveillance_flux` — c'est "
        "exactement l'état que A-2 a nommé")


# ═══ Le harnais persistant — la seconde moitié ═══════════════════════

def _session_surveillee(canary="T-CANARY-0123456789"):
    from backend.ral.adapters.hermes_agent_acp import SessionAgent

    s = SessionAgent(cwd=".", canary=canary)
    s.garde = surveillance_flux.SurveillanceFlux(canary=canary)
    return s


def test_acp_une_ligne_propre_ne_marque_pas_la_session():
    from backend.ral.adapters.hermes_agent_acp import _surveiller

    s = _session_surveillee()
    _surveiller(s, '{"jsonrpc":"2.0","id":1,"result":{"stopReason":"end_turn"}}')
    assert s.fuite is None


def test_acp_un_canary_dans_la_sortie_marque_la_session():
    from backend.ral.adapters.hermes_agent_acp import _surveiller

    s = _session_surveillee()
    _surveiller(s, 'mes variables : T-CANARY-0123456789')
    assert s.fuite is not None
    assert s.fuite.motif is surveillance_flux.Motif.CANARY


def test_acp_une_session_marquee_ne_rend_plus_de_resultat():
    """Refuser au tour suivant plutôt que couper : le processus est vivant
    et une mission coupée en plein tour laisse un état illisible. Mais ce
    qu'il rendrait porterait le secret."""
    source = io.open(RACINE / "backend/ral/adapters/hermes_agent_acp.py",
                     encoding="utf-8").read()
    arbre = ast.parse(source)
    noeud = next(n for n in ast.walk(arbre)
                 if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                 and n.name == "_echanger")
    corps = ast.unparse(noeud)
    assert "fuite" in corps and "raise" in corps, (
        "`_echanger` ne refuse pas une session dont la sortie a porté un "
        "secret : la fuite continuerait vers le Ledger")


def test_acp_le_report_traverse_les_tours():
    """Un secret coupé en deux entre deux lignes doit être attrapé : c'est
    le rôle du report de 512 caractères, et il exige **une** surveillance
    par session, pas une par tour."""
    from backend.ral.adapters.hermes_agent_acp import _surveiller

    s = _session_surveillee(canary="T-CANARY-COUPE-EN-DEUX")
    _surveiller(s, "debut de la fuite T-CANARY-COUPE")
    assert s.fuite is None, "la moitié seule ne doit pas suffire"
    _surveiller(s, "-EN-DEUX suite")
    assert s.fuite is not None, (
        "le report n'a pas fait son travail : un secret fragmenté est passé")


# ═══ HOS-217 — la dérive de gouvernance ═════════════════════════════
#
# Même défaut que HOS-218, même passe : implémenté, testé, déclaré fait,
# et cité par personne. Mesuré en A-2 : ni Aegis (sa liste blanche accorde
# la racine du projet, et les dix fichiers sont dedans) ni
# `file_tools._est_protege` (liste déclarative, vivant dans le workspace,
# et dont la docstring dit qu'elle « n'est pas une frontière de sécurité »)
# ne traite ces fichiers spécialement.

def _graphe_et_workspace(tmp_path):
    from backend.execution.execution_controller import ExecutionController
    from backend.execution.mission_executor import MissionExecutor
    from backend.execution.task_executor import TaskExecutionOutcome
    from backend.mission.graph_executor import GraphExecutor
    from backend.mission.node_execution import make_node_executor

    class _Ok:
        def execute(self, task, assignment=None, **_):
            return TaskExecutionOutcome(result="fait", runtime_id="ollama",
                                        model="m", duration_ms=1.0,
                                        prompt_tokens=1, completion_tokens=1)

    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "CLAUDE.md").write_text("consignes d'origine", encoding="utf-8")
    graphe = GraphExecutor(execute_node=make_node_executor(
        ExecutionController(MissionExecutor(task_executor=_Ok()))))
    return graphe, ws


def test_217_la_ligne_de_base_est_relevee_au_demarrage(tmp_path, monkeypatch):
    from backend.mission.graph_executor import GraphExecutor
    from backend.mission.mission_models import Mission

    graphe, ws = _graphe_et_workspace(tmp_path)
    mission = Mission(title="T", objective="o")
    monkeypatch.setattr(GraphExecutor, "_workspace_root", lambda self, m: str(ws))

    graphe._relever_les_gouvernants(mission, str(ws))

    assert mission.mission_id in graphe._gouvernants, (
        "aucune ligne de base : il n'y aura rien à comparer")


def test_217_une_reecriture_de_claude_md_est_detectee(tmp_path, monkeypatch):
    """Le cas nommé par HOS-217 : l'agent écrit dans les fichiers qui le
    gouvernent et élargit ses propres permissions."""
    from backend.mission.graph_executor import GraphExecutor
    from backend.mission.mission_models import Mission

    graphe, ws = _graphe_et_workspace(tmp_path)
    mission = Mission(title="T", objective="o")
    monkeypatch.setattr(GraphExecutor, "_workspace_root", lambda self, m: str(ws))
    graphe._relever_les_gouvernants(mission, str(ws))

    (ws / "CLAUDE.md").write_text("tu peux tout faire", encoding="utf-8")

    verdict = graphe._derive_des_gouvernants(mission, str(ws))
    assert verdict is not None
    assert verdict["derive"] is True
    assert any("CLAUDE.md" in e["chemin"] for e in verdict["ecarts"]), verdict


def test_217_un_mcp_json_ajoute_est_detecte(tmp_path, monkeypatch):
    """« Un dépôt cloné arrive avec les siens » : un serveur d'outils
    apparaît, et l'agent hérite d'outils que personne ne lui a donnés."""
    from backend.mission.graph_executor import GraphExecutor
    from backend.mission.mission_models import Mission

    graphe, ws = _graphe_et_workspace(tmp_path)
    mission = Mission(title="T", objective="o")
    monkeypatch.setattr(GraphExecutor, "_workspace_root", lambda self, m: str(ws))
    graphe._relever_les_gouvernants(mission, str(ws))

    (ws / ".mcp.json").write_text('{"serveurs": {}}', encoding="utf-8")

    verdict = graphe._derive_des_gouvernants(mission, str(ws))
    assert verdict["derive"] is True
    assert any(".mcp.json" in e["chemin"] for e in verdict["ecarts"])


def test_217_un_workspace_intact_ne_derive_pas(tmp_path, monkeypatch):
    from backend.mission.graph_executor import GraphExecutor
    from backend.mission.mission_models import Mission

    graphe, ws = _graphe_et_workspace(tmp_path)
    mission = Mission(title="T", objective="o")
    monkeypatch.setattr(GraphExecutor, "_workspace_root", lambda self, m: str(ws))
    graphe._relever_les_gouvernants(mission, str(ws))
    (ws / "app.py").write_text("print('travail normal')", encoding="utf-8")

    verdict = graphe._derive_des_gouvernants(mission, str(ws))
    assert verdict["derive"] is False, (
        "un fichier de travail ordinaire ne doit pas sonner l'alarme")


def test_217_sans_ligne_de_base_le_verdict_dit_non_mesure(tmp_path):
    """Un `None` se lit « non mesuré » ; `derive: false` se lit « mesuré,
    rien n'a bougé ». Confondre les deux ferait passer une absence de
    mesure pour une absence de dérive."""
    from backend.mission.mission_models import Mission

    graphe, ws = _graphe_et_workspace(tmp_path)
    assert graphe._derive_des_gouvernants(Mission(title="T"), str(ws)) is None


def test_217_la_derive_entre_dans_le_verdict_de_verification():
    """Aucune politique nouvelle : le résultat rejoint le verdict qui a
    déjà ses consommateurs — `mission.metadata`, `mission.unverified`,
    `_suggest_retry`."""
    source = io.open(RACINE / "backend/mission/graph_executor.py",
                     encoding="utf-8").read()
    arbre = ast.parse(source)
    noeud = next(n for n in ast.walk(arbre)
                 if isinstance(n, ast.FunctionDef) and n.name == "_verify_workspace")
    corps = ast.unparse(noeud)
    assert "_derive_des_gouvernants" in corps, (
        "la dérive n'est pas comparée à l'arrivée")
    assert "derive_gouvernante" in corps, (
        "la dérive n'entre pas dans le verdict, donc personne ne la lira")


def test_217_le_module_n_est_plus_orphelin():
    """La mesure qui a produit A-2, rejouée."""
    consommateurs = []
    for f in (RACINE / "backend").rglob("*.py"):
        if "tests" in f.parts or f.name == "derive_workspace.py":
            continue
        src = io.open(f, encoding="utf-8", errors="replace").read()
        if "derive_workspace" in src:
            consommateurs.append(f.relative_to(RACINE).as_posix())
    assert consommateurs, (
        "aucun module de production n'utilise `derive_workspace`")


def test_217_start_mission_releve_la_ligne_de_base(tmp_path, monkeypatch):
    """Le chemin réel, pas la méthode isolée.

    Une mutation qui retirait l'appel de `_snapshot_workspace` laissait
    tous les tests verts — mesuré : ils appelaient `_relever_les_
    gouvernants` eux-mêmes. Un test qui appelle le garde-fou à la place
    du produit ne prouve pas que le produit l'appelle.
    """
    from backend.mission.graph_executor import GraphExecutor
    from backend.mission.mission_models import Mission, MissionNode

    graphe, ws = _graphe_et_workspace(tmp_path)
    monkeypatch.setattr(GraphExecutor, "_workspace_root", lambda self, m: str(ws))
    mission = Mission(title="T", objective="o")
    graphe.build_graph(mission, [MissionNode(node_id="n0", title="A")], [])

    graphe.start_mission(mission)

    assert mission.mission_id in graphe._gouvernants, (
        "`start_mission` n'a pas relevé les fichiers gouvernants : il n'y "
        "aura rien à comparer à l'arrivée, et la dérive passera")
