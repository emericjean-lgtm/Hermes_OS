# -*- coding: utf-8 -*-
"""Ou la relation Run <-> Skill se perd, et pourquoi on n'en fabrique pas
(G-29, HOS-277).

## La question

Existe-t-il une identite reellement propagee et persistante reliant
`Mission -> Run -> tache Hermes Agent -> evenement Skill` ?

## La reponse, mesuree sur v0.21.0

    PRESENT       oui   l'agent emet task_id + session_id (G-28)
    PROPAGATED    NON   c'est ici que ca casse
    CALLED        n/a
    PERSISTENT    NON
    RESTART-SAFE  NON

**Rien n'est propage vers l'agent.** La ligne de commande du mode jetable
est `--query --model --provider --base_url --max_turns [--toolsets]
--quiet --usage-file` : aucun identifiant de tache. Le `task_id` que
Hermes OS tient ne sert qu'a son propre bus d'evenements. Et
`session/prompt` ne transporte que `{sessionId, prompt}` — y ajouter un
champ serait inventer une API.

**Ce qui remonte, remonte trop tard.** `_extract_session_id` recupere le
`session_id` de l'agent depuis stdout ou le fichier d'usage — a la
**completion**, donc apres les evenements Skill du tour, et il n'est
ecrit nulle part.

**Le plafond de granularite est la session, pas le Run.** Mesure :

    cle_de_session({'project_id': 'P1', 'mission_id': 'M-alpha'}) -> 'projet:P1'
    cle_de_session({'project_id': 'P1', 'mission_id': 'M-beta'})  -> 'projet:P1'

Deux missions d'un meme projet **partagent la session**, et c'est
delibere (continuite d'un cahier de 26 sections). Un `session_id` ne
designe donc pas une mission. Et une mission porte plusieurs Runs —
`runs.tentative`, `runs.parent` — donc meme une session 1:1 avec une
mission ne designerait jamais un Run.

**Rien n'est persiste.** `SessionsDeMission._identifiants` est un
dictionnaire en memoire : une instance neuve le trouve vide. La table
`runs` porte 29 colonnes, aucune de session. `audit_log` a les colonnes
qu'il faudrait — `session_id`, `task_id`, `project_id` — et **six lignes**,
toutes de verifications manuelles d'aout, `task_id` toujours `NULL`.

## Decision

    la relation Run <-> Skill                        DEFER
    la deduire du temps, du compteur ou de l'unicite REJECT

DEFER, pas REJECT, sur la relation : rien n'est faux dans l'architecture,
il manque une identite que seul l'amont peut fournir. REJECT sur les
raccourcis, parce qu'ils sont a portee de main et produiraient des
associations confiantes et fausses.

Ces tests gardent la seconde moitie : qu'aucun module ne se mette a
associer sans preuve.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]


# ── Ce que la mesure a etabli, garde a l'endroit ou ca casse ──────────

def test_la_ligne_de_commande_ne_transporte_aucun_identifiant_de_run():
    """Le mode jetable lance l'agent sans lui dire pour quel Run.

    Si un jour Hermes OS passait `--task-id`, la relation deviendrait
    possible — et ce test rougirait, ce qui est le signal voulu : la
    decision de G-29 serait a rejuger sur une mesure neuve."""
    source = (RACINE / "backend" / "ral" / "adapters"
              / "hermes_agent_cli.py").read_text(encoding="utf-8")
    arbre = ast.parse(source)
    litteraux = {n.value for n in ast.walk(arbre)
                 if isinstance(n, ast.Constant) and isinstance(n.value, str)}
    drapeaux = {x for x in litteraux if x.startswith("--")}
    assert drapeaux == {"--query", "--model", "--provider", "--base_url",
                        "--max_turns", "--toolsets", "--quiet",
                        "--usage-file"}, sorted(drapeaux)
    assert not {d for d in drapeaux if "task" in d or "run" in d}


def test_le_prompt_acp_ne_transporte_que_la_session_et_le_texte():
    """`session/prompt` porte `{sessionId, prompt}`. Y glisser un champ
    maison serait inventer une methode que le serveur ignorerait — et
    l'ignorer en silence est pire que la refuser."""
    source = (RACINE / "backend" / "ral" / "adapters"
              / "hermes_agent_acp.py").read_text(encoding="utf-8")
    bloc = source[source.index('"session/prompt"'):]
    corps = bloc[:bloc.index("delai")]
    assert '"sessionId"' in corps and '"prompt"' in corps
    for invente in ("run_id", "runId", "task_id", "taskId", "mission"):
        assert invente not in corps, (
            f"le prompt ACP transporte `{invente}` : methode inventee")


def test_deux_missions_d_un_meme_projet_partagent_la_session():
    """Le plafond de granularite, mesure.

    Ce n'est pas un defaut a corriger : `cle_de_session` groupe par projet
    pour qu'une campagne de 26 sections garde sa continuite. Mais cela
    interdit d'attribuer un evenement Skill a UNE mission, et le test le
    fixe pour que personne ne le decouvre en aval."""
    from backend.ral.adapters.sessions_de_mission import cle_de_session

    a = cle_de_session({"project_id": "P1", "mission_id": "M-alpha"})
    b = cle_de_session({"project_id": "P1", "mission_id": "M-beta"})
    assert a == b == "projet:P1"
    assert cle_de_session({"mission_id": "M-seule"}) == "mission:M-seule"


def test_la_table_des_identifiants_de_session_ne_survit_pas_au_processus():
    """Le commentaire de ce champ affirmait la survie « apres un
    redemarrage du backend ». Mesure : une instance neuve est vide.

    G-29 est venu chercher ici une clef de jointure durable ; batir dessus
    aurait pris une table volatile pour une trace."""
    from backend.ral.adapters.sessions_de_mission import SessionsDeMission

    premier = SessionsDeMission()
    premier._identifiants["projet:P1"] = "sess-agent-42"  # noqa: SLF001
    assert SessionsDeMission()._identifiants == {}  # noqa: SLF001


def test_le_ledger_ne_porte_aucune_session_d_agent():
    """29 colonnes, aucune de session. En ajouter une sans mecanisme qui la
    remplisse honnetement donnerait un `NULL` que la passe suivante
    remplirait au jugé."""
    source = (RACINE / "backend" / "runs"
              / "registre.py").read_text(encoding="utf-8")
    bloc = re.search(r"CREATE TABLE IF NOT EXISTS runs \((.*?)\n\);",
                     source, re.S).group(1)
    colonnes = [l.strip().split()[0] for l in bloc.splitlines()
                if l.strip() and not l.strip().startswith(("--", "FOREIGN"))]
    assert len(colonnes) == 29, colonnes
    assert not [c for c in colonnes if "session" in c or "skill" in c]


# ── Ce qu'aucun module ne doit se mettre a faire ──────────────────────

def _modules_du_backend():
    for module in (RACINE / "backend").rglob("*.py"):
        if "tests" not in module.parts:
            yield module


def test_aucun_module_ne_relie_une_skill_a_un_run():
    """La garde centrale. Un module qui nomme a la fois une Skill et un Run
    dans le meme littéral construit l'association que G-29 a mesuree
    impossible."""
    coupables = []
    for module in _modules_du_backend():
        source = module.read_text(encoding="utf-8", errors="replace")
        if "skill" not in source.lower():
            continue
        arbre = ast.parse(source)
        litteraux = {n.value for n in ast.walk(arbre)
                     if isinstance(n, ast.Constant) and isinstance(n.value, str)
                     and len(n.value) < 200}
        for texte in litteraux:
            bas = texte.lower()
            if ("skill" in bas and ("run_id" in bas or "source_task_id" in bas)):
                coupables.append(f"{module.relative_to(RACINE)} -> {texte[:60]}")
    assert not coupables, (
        "une relation Run <-> Skill est construite : " + ", ".join(coupables))


def test_aucun_module_ne_remplit_source_task_id():
    """La colonne existe dans `hermes.db` et elle est **vide**. La remplir
    depuis les compteurs, l'horodatage ou l'unicite d'une session serait
    exactement la fausse correlation que le brief REJETTE."""
    for module in _modules_du_backend():
        source = module.read_text(encoding="utf-8", errors="replace")
        if "source_task_id" not in source:
            continue
        arbre = ast.parse(source)
        for noeud in ast.walk(arbre):
            if isinstance(noeud, ast.Constant) and isinstance(noeud.value, str):
                bas = noeud.value.lower()
                assert not ("insert" in bas and "source_task_id" in bas), (
                    f"{module.relative_to(RACINE)} ecrit source_task_id")


def test_aucun_module_ne_devine_un_run_par_le_temps():
    """« L'evenement le plus proche dans le temps », « la seule session
    ouverte », « le dernier Run demarre » : trois raccourcis a portee de
    main qui produisent des associations confiantes et fausses.

    La garde porte sur les **identifiants du code** — noms de fonctions et
    de variables — et non sur le texte du fichier. Ecrite en balayage de
    chaines, elle accusait `backend/bridge/hermes_agent_bridge.py` a cause
    du littéral `"session.most_recent"`, qui est un nom de methode RPC dans
    la matrice de capacites. Une garde qui matche une forme accuse la
    forme ; celle-ci regarde ce que le module *fait*.
    """
    soupcons = ("plus_proche", "le_plus_recent", "derniere_session",
                "seule_session", "au_plus_pres", "closest", "most_recent",
                "nearest", "par_horodatage")
    coupables = []
    for module in _modules_du_backend():
        source = module.read_text(encoding="utf-8", errors="replace")
        if "skill" not in source.lower():
            continue
        arbre = ast.parse(source)
        noms = set()
        for noeud in ast.walk(arbre):
            if isinstance(noeud, (ast.FunctionDef, ast.AsyncFunctionDef,
                                  ast.ClassDef)):
                noms.add(noeud.name)
            elif isinstance(noeud, ast.Name):
                noms.add(noeud.id)
            elif isinstance(noeud, ast.Attribute):
                noms.add(noeud.attr)
        for mot in soupcons:
            if any(mot in n for n in noms):
                coupables.append(f"{module.relative_to(RACINE)} -> {mot}")
    assert not coupables, (
        "une heuristique temporelle approche les Skills : " + ", ".join(coupables))


def test_le_backend_n_ecrit_jamais_dans_le_dossier_des_plugins():
    """G-28 et G-29 gardaient « l'observateur n'est pas installe ». G-33 l'a
    installe, et la garde devient : Hermes OS ne s'installe pas lui-meme.

    L'installation est un geste d'exploitation, fait une fois, par les
    mecanismes de l'agent (`_set_plugin_enabled`). Un backend qui poserait
    ou reparerait le plugin au demarrage en deviendrait le mainteneur — et
    un agent mis a jour se verrait reinstaller un plugin qu'un operateur
    avait peut-etre retire exprès."""
    coupables = []
    for module in (RACINE / "backend").rglob("*.py"):
        if "tests" in module.parts:
            continue
        source = module.read_text(encoding="utf-8", errors="replace")
        if "plugins" not in source:
            continue
        arbre = ast.parse(source)
        for noeud in ast.walk(arbre):
            if not isinstance(noeud, ast.Call):
                continue
            nom = getattr(noeud.func, "attr", None) or getattr(noeud.func, "id", None)
            if nom not in {"copytree", "copy2", "copy", "write_text", "mkdir"}:
                continue
            litteraux = " ".join(
                n.value for n in ast.walk(noeud)
                if isinstance(n, ast.Constant) and isinstance(n.value, str))
            if "plugin" in litteraux.lower():
                coupables.append(f"{module.relative_to(RACINE)} -> {nom}")
    assert not coupables, (
        "le backend ecrit dans les plugins de l'agent : " + ", ".join(coupables))


def test_la_decision_et_sa_limite_sont_ecrites():
    """Une impossibilite non ecrite se redecouvre. La roadmap doit porter la
    mesure, pas seulement le verdict."""
    roadmap = (RACINE / "docs"
               / "HERMES_OS_MASTER_ROADMAP.md").read_text(encoding="utf-8")
    assert "G-29" in roadmap
    for repere in ("projet:P1", "29 colonnes", "--usage-file"):
        assert repere in roadmap, f"la roadmap ne porte pas la mesure `{repere}`"


#: Les modules qui servent les competences de **l'agent**. Le distributeur
#: de Hermes OS (`mcp_server`, `backend/skills/routes.py` cote `/skills`)
#: n'est pas dans cette liste : son entite `Skill` porte un
#: `source_task_id` qui relie une competence de Hermes OS a une tache de
#: Hermes OS. C'est une relation de Hermes OS a lui-meme, ou il EST
#: l'autorite — HOS-274 a fixe que les deux magasins ne se confondent pas,
#: et une garde qui les confondrait accuserait le mauvais.
SURFACES_DE_L_AGENT = (
    "backend/skills/registre.py",
    "backend/skills/provenance.py",
    "backend/services/vue_skills.py",
)


def test_aucune_surface_de_l_agent_ne_rend_un_identifiant_de_run():
    """Le trou qu'une mutation a trouve.

    Les gardes precedentes regardent les modules qui *calculent*. Une
    surface peut fabriquer la relation au dernier metre — rendre un
    `run_id` dans sa charge utile — sans qu'aucune d'elles ne bronche, et
    l'interface l'afficherait comme un fait.

    Mesure du 2026-09-10 : la relation n'existe pas. Aucune clef de reponse
    portant les competences de l'agent ne doit donc la nommer."""
    interdits = {"run_id", "runId", "run", "source_task_id", "mission_id",
                 "task_id", "session_id", "correlation_id"}
    coupables = []
    for chemin in SURFACES_DE_L_AGENT:
        module = RACINE / chemin
        arbre = ast.parse(module.read_text(encoding="utf-8"))
        for noeud in ast.walk(arbre):
            if not isinstance(noeud, ast.Dict):
                continue
            for cle in noeud.keys:
                if (isinstance(cle, ast.Constant)
                        and isinstance(cle.value, str)
                        and cle.value in interdits):
                    coupables.append(f"{chemin} -> {cle.value}")
    assert not coupables, (
        "une surface des competences de l'agent nomme une relation de Run : "
        + ", ".join(coupables))


def test_la_route_des_competences_de_l_agent_ne_rend_aucune_relation():
    """La meme garde, sur la route elle-meme : `GET /skills/agent` sert les
    competences de l'agent, et `_origine` en decrit la provenance. Ni l'une
    ni l'autre ne doit porter un identifiant de Run."""
    source = (RACINE / "backend" / "skills"
              / "routes.py").read_text(encoding="utf-8")
    arbre = ast.parse(source)
    interdits = {"run_id", "runId", "source_task_id", "correlation_id"}
    for noeud in ast.walk(arbre):
        if not isinstance(noeud, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if noeud.name not in ("competences_de_l_agent", "_origine"):
            continue
        for interne in ast.walk(noeud):
            if not isinstance(interne, ast.Dict):
                continue
            for cle in interne.keys:
                assert not (isinstance(cle, ast.Constant)
                            and cle.value in interdits), (
                    f"{noeud.name} rend `{cle.value}`")
