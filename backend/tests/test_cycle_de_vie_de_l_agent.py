"""Qui possède un processus que Hermes Agent démarre ? (HOS-246)

## Ce qui a été mesuré

12 processus de l'agent tournaient sur la machine de développement, dont
40 avec un répertoire courant sous `hermes_os_scratch`. Le premier
soupçon — « la campagne de tests fuit » — était **faux**, et le compte
lui-même l'était aussi : la mesure filtrait sur la *ligne de commande*, et
attrapait trois shells qui mentionnaient simplement « hermes-agent ».
Huitième faux positif de sous-chaîne de ce chantier.

Mesuré correctement, sur l'exécutable :

- **le processus CLI de l'agent ne fuit pas.** Observé sur un vrai
  déroulement : un agent apparaît, travaille, disparaît, un autre le
  remplace, et le compte reste stable. `hermes_agent_cli` attend
  `proc.communicate()` et **tue** le processus quand le budget expire ;
- **ce que l'agent démarre, personne ne le possède.** Les 40 processus
  résiduels sont des `bash -lic "… python app.py"` et les serveurs qu'ils
  lancent, écoutant sur le port 8000, dans
  `hermes_os_scratch/unbound/standalone`, vivants depuis 37 heures.

## L'ambiguïté, documentée et non tranchée

Hermes Agent est le cerveau : il peut légitimement démarrer un serveur de
développement, et le tuer serait détruire le travail qu'on lui a demandé.
Mais rien ne le possède ensuite — ni Hermes OS, qui ne possède que le
processus CLI, ni l'agent, qui sort.

Ce jalon **ne construit pas de faucheur**. Inventer un système qui tue des
processus dans le dossier de travail d'un utilisateur serait à la fois une
architecture nouvelle et un risque de détruire un serveur qu'il veut. La
décision revient au propriétaire du dépôt.

Ce fichier tient donc ce qui **est** démontré : le contrat du processus
CLI, celui-là même qui a été mesuré sain.
"""

from __future__ import annotations

import ast
import inspect
import io
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]


def _corps_de(fonction) -> ast.AST:
    import textwrap

    return ast.parse(textwrap.dedent(inspect.getsource(fonction)))


# ═══ Le contrat mesuré : un agent qui dépasse son budget est tué ════

def test_un_agent_qui_depasse_son_budget_est_tue_et_attendu():
    """La garde du seul contrat que la mesure a démontré.

    Sur un vrai déroulement, les processus CLI apparaissent et
    disparaissent à compte constant. Ce que le code doit garantir, et que
    rien ne tenait jusqu'ici : sur expiration du budget, le processus est
    **tué**, puis **attendu** — sans quoi il resterait zombie et le
    descripteur ne serait jamais rendu.
    """
    from backend.ral.adapters import hermes_agent_cli

    source = io.open(RACINE / "backend" / "ral" / "adapters" /
                     "hermes_agent_cli.py", encoding="utf-8").read()
    arbre = ast.parse(source)

    gestionnaires = [n for n in ast.walk(arbre)
                     if isinstance(n, ast.ExceptHandler)
                     and "TimeoutError" in ast.unparse(n.type or ast.Constant(""))]
    assert gestionnaires, "aucun traitement du dépassement de budget"

    tueurs = [g for g in gestionnaires
              if ".kill()" in ast.unparse(g) and ".wait()" in ast.unparse(g)]
    assert tueurs, (
        "le dépassement de budget ne tue pas le processus de l'agent, ou ne "
        "l'attend pas après l'avoir tué — un processus zombie resterait")


def test_le_lancement_attend_la_sortie_du_processus():
    """`communicate()` ne rend la main qu'à la mort du processus.

    Un `wait_for` sur autre chose laisserait l'agent tourner derrière la
    tâche qui l'a demandé.
    """
    source = io.open(RACINE / "backend" / "ral" / "adapters" /
                     "hermes_agent_cli.py", encoding="utf-8").read()
    arbre = ast.parse(source)

    attentes = [ast.unparse(n) for n in ast.walk(arbre)
                if isinstance(n, ast.Call)
                and ast.unparse(n.func).endswith("wait_for")]
    assert attentes, "plus aucune attente bornée du processus de l'agent"
    assert any("communicate" in a for a in attentes), (
        "l'attente ne porte plus sur `communicate()` — le processus "
        "pourrait survivre à la tâche")


def test_le_budget_de_l_agent_est_borne_et_nomme():
    """Un budget absent rendrait l'attente réellement infinie.

    Mesuré : 900 s par tâche pour l'agent, 1200 s par étape de graphe. Ce
    sont ces deux bornes qui font qu'un `find /` lancé par l'agent finit
    par être coupé plutôt que d'attendre indéfiniment.
    """
    from backend.execution.task_executor import _HERMES_AGENT_TIMEOUT_S
    from backend.mission.graph_executor import plafond_du_noeud

    assert _HERMES_AGENT_TIMEOUT_S > 0
    assert plafond_du_noeud() > 0
    assert plafond_du_noeud() >= _HERMES_AGENT_TIMEOUT_S, (
        "le plafond de l'étape coupe avant le budget qu'il doit couvrir — "
        "c'est le défaut nommé dans `plafond_du_noeud` (2026-08-22)")


def test_le_scratch_n_est_jamais_l_arbre_de_code():
    """Une mission sans projet lié ne doit pas écrire dans Hermes OS.

    C'est ce qui rend les résidus inoffensifs : ils vivent dans `%TEMP%`,
    pas dans le dépôt.
    """
    from backend.execution.task_executor import RealTaskExecutor

    arbre = _corps_de(RealTaskExecutor._scratch_workspace)
    appels = {ast.unparse(n) for n in ast.walk(arbre) if isinstance(n, ast.Call)}
    assert any("gettempdir" in a for a in appels), (
        "le workspace de repli ne part plus de %TEMP%")
    assert not any("getcwd" in a for a in appels), (
        "le workspace de repli retombe sur le répertoire courant — "
        "c'est-à-dire l'arbre de code de Hermes OS lui-même")


# ═══ La documentation dit ce que le code fait (HOS-238) ═════════════

def test_la_politique_d_outil_n_est_plus_decrite_comme_un_no_op():
    """HOS-238 a rendu la branche WRITE réelle ; la docstring de
    `_unsandboxed_write` l'a affirmée inerte pendant huit jalons.

    Une documentation périmée sur une décision de sécurité est pire qu'une
    absence : elle fait croire qu'un contrôle manque là où il existe, et
    on finit par en écrire un second.
    """
    from backend.agents.specialized.code_intelligence import (
        code_intelligence_agent as module,
    )

    doc = inspect.getdoc(module.CodeIntelligenceAgent._unsandboxed_write) or ""
    assert "no-op" not in doc, (
        "la docstring décrit encore ToolPolicy.evaluate() comme inerte — "
        "HOS-238 l'a rendue réelle")
    assert "HOS-238" in doc, "la correction n'est pas rattachée à son jalon"


def test_la_branche_write_de_la_politique_consulte_vraiment_le_sandbox():
    """Ce que la docstring affirme désormais, vérifié sur le comportement.

    Sans cela, la correction documentaire pourrait affirmer à son tour
    quelque chose de faux — le défaut symétrique de celui qu'elle corrige.
    """
    from backend.tools.tool_models import ToolDefinition, ToolPermission, ToolRequest
    from backend.tools.tool_policy import PolicyVerdict, ToolPolicy
    from backend.tools.tool_sandbox import SandboxConfig, ToolSandbox

    sandbox = ToolSandbox()
    sandbox.configure("t1", SandboxConfig(read_only=True))
    verdict, raison = ToolPolicy(sandbox=sandbox).evaluate(
        ToolRequest(tool_id="t1", permission_level=ToolPermission.WRITE,
                    timeout_seconds=10.0),
        ToolDefinition(id="t1", name="outil", status="active"))

    assert verdict is PolicyVerdict.DENY
    assert "lecture seule" in raison


def test_la_politique_ne_provisionne_aucun_sandbox():
    """L'autre moitié de la docstring corrigée, et la raison pour laquelle
    le refus de `_unsandboxed_write` tient toujours.

    Un `ToolSandbox` sans configuration pour l'outil laisse passer
    l'écriture : la politique applique un drapeau, elle ne fabrique pas
    d'isolement.
    """
    from backend.tools.tool_models import ToolDefinition, ToolPermission, ToolRequest
    from backend.tools.tool_policy import PolicyVerdict, ToolPolicy
    from backend.tools.tool_sandbox import ToolSandbox

    verdict, _ = ToolPolicy(sandbox=ToolSandbox()).evaluate(
        ToolRequest(tool_id="jamais-configure",
                    permission_level=ToolPermission.WRITE, timeout_seconds=10.0),
        ToolDefinition(id="jamais-configure", name="outil", status="active"))

    assert verdict is PolicyVerdict.ALLOW, (
        "un sandbox non configuré refuse désormais l'écriture — si c'est "
        "voulu, le refus de `_unsandboxed_write` doit être réexaminé")
