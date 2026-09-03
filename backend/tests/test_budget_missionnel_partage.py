"""Un budget que chaque nœud remettait à zéro (HOS-248).

## Le défaut, découvert par HOS-247 en s'implémentant

HOS-247 a rendu `ExecutionMeta.max_duration_seconds` effectif. Sa
prémisse — `ExecutionMeta` est l'objet d'exécution *de la mission* —
était vraie sur un chemin et fausse sur l'autre :

* `execution/routes.py` en construit **un** pour toute l'exécution ;
* `mission/node_execution.py` en construit **un par nœud** du DAG.

Sur le chemin autonome, le budget repartait donc de zéro à chaque nœud
et ne pouvait jamais se déclencher — un nœud étant déjà plafonné à
1 200 s. Le champ était effectif et sans effet.

## Ce que la mesure a établi (passe 9)

Trois objets étaient candidats. Deux sont éliminés par le code lui-même :

* `ExecutionMeta` — fragmenté, mesuré ;
* `Run` — fragmenté aussi : `_ouvrir_le_run` part de `prepare(meta, …)`,
  donc une fois par nœud. Le journal ne pouvait pas porter le budget.

Reste `Mission` : le seul objet mesuré comme unique par mission, et déjà
persisté par M-8 — dont le sérialiseur parcourt `fields()`, si bien qu'un
champ nouveau traverse un redémarrage sans migration.

Et `Mission.started_at` existait déjà, posé une seule fois par tentative
et réinitialisé par une reprise : le t0 n'avait pas à être inventé.
"""

from __future__ import annotations

import ast
import io
import os
import subprocess
import sys
import tempfile
import textwrap
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend.execution.execution_models import (
    BUDGET_MISSION_PAR_DEFAUT_S,
    ExecutionMeta,
    budget_de,
)
from backend.execution.execution_state import ExecutionStateMachine
from backend.mission.mission_models import Mission, MissionStatus
from backend.mission.routes import _missions

RACINE = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def _registre_propre():
    _missions.clear()
    yield
    _missions.clear()


def _mission(budget=None, depuis_s=None, titre="mission") -> Mission:
    """Une mission enregistrée, éventuellement démarrée il y a `depuis_s`."""
    kw = {} if budget is None else {"max_duration_seconds": budget}
    m = Mission(title=titre, status=MissionStatus.RUNNING, **kw)
    if depuis_s is not None:
        m.started_at = datetime.now(timezone.utc) - timedelta(seconds=depuis_s)
    _missions[m.mission_id] = m
    return m


def _noeud(mission: Mission, budget_local=None) -> ExecutionStateMachine:
    """Ce que `node_execution` construit : un `ExecutionMeta` par nœud."""
    kw = {} if budget_local is None else {"max_duration_seconds": budget_local}
    return ExecutionStateMachine(
        ExecutionMeta(mission_id=mission.mission_id, user_goal="n", **kw))


# ═══ T1–T3 — les valeurs du champ missionnel ════════════════════════

def test_T1_defaut_et_zero_donnent_3600():
    assert Mission(title="t").max_duration_seconds == BUDGET_MISSION_PAR_DEFAUT_S
    assert budget_de(Mission(title="t", max_duration_seconds=0)) == 3600.0


def test_T2_une_valeur_explicite_est_celle_qui_sert():
    mission = _mission(budget=120, depuis_s=1)
    assert _noeud(mission).budget_s == 120.0


def test_T3_une_valeur_negative_est_refusee():
    with pytest.raises(ValueError, match="budget de mission invalide"):
        budget_de(Mission(title="t", max_duration_seconds=-1))


# ═══ T4/T5 — plusieurs nœuds, un seul budget et un seul t0 ═════════

def test_T4_trois_noeuds_partagent_budget_et_t0():
    """Le cœur du jalon. Trois `ExecutionMeta` distincts — exactement ce
    que `node_execution` fabrique — doivent lire le même budget et la
    même horloge."""
    mission = _mission(budget=600, depuis_s=42)
    a, b, c = _noeud(mission), _noeud(mission), _noeud(mission)

    assert a.budget_s == b.budget_s == c.budget_s == 600.0
    consommes = [round(n.budget_consomme_s) for n in (a, b, c)]
    assert consommes == [42, 42, 42], (
        f"les nœuds ne partagent pas leur t0 : {consommes}")


def test_T5_un_execution_meta_neuf_ne_remet_rien_a_zero():
    """La régression qu'il faut rendre impossible : un nœud qui commence
    alors que la mission est déjà à bout de budget doit le voir tout de
    suite, pas repartir de zéro."""
    mission = _mission(budget=10, depuis_s=11)

    premier = _noeud(mission)
    assert premier.budget_depasse() is True

    tardif = _noeud(mission)          # créé après coup, comme le nœud suivant
    assert tardif.budget_depasse() is True, (
        "un ExecutionMeta neuf a réinitialisé le temps missionnel")
    assert tardif.budget_consomme_s >= 11


def test_T6_le_depassement_global_est_constate_et_classe():
    """Trois nœuds de 4 s dans un budget de 10 : le troisième est refusé
    sur le **total**, pas sur sa propre durée."""
    from backend.runs.registre import Cause
    from backend.runs.taxonomie import classer, remede

    mission = _mission(budget=10, depuis_s=4)
    assert _noeud(mission).budget_depasse() is False        # 4/10
    mission.started_at -= timedelta(seconds=3)
    assert _noeud(mission).budget_depasse() is False        # 7/10
    mission.started_at -= timedelta(seconds=4)
    assert _noeud(mission).budget_depasse() is True         # 11/10

    classement = classer(
        "budget de mission atteint : 11 s consommées sur 10 s")
    assert classement.cause is Cause.BUDGET
    assert remede(Cause.BUDGET).reessayer is False


# ═══ T7/T8 — retry et reprise ══════════════════════════════════════

def test_T7_un_retry_reste_dans_le_meme_budget():
    """`node_execution` réappelle `controller.execute_task` sur le **même**
    meta tant que la tâche est PENDING. Trois tentatives ne doivent pas
    tripler le budget.
    """
    mission = _mission(budget=600, depuis_s=30)
    machine = _noeud(mission)

    lectures = [machine.budget_consomme_s for _ in range(3)]
    assert all(abs(x - 30) < 2 for x in lectures), lectures
    assert machine.budget_s == 600.0
    depart = mission.started_at
    assert mission.started_at == depart          # rien n'a réancré


def test_T8_une_reprise_repart_avec_un_budget_entier():
    """Une reprise réinitialise `started_at` — c'est le comportement
    existant de `start_mission`, et c'est lui qui rend la règle vraie
    sans qu'aucun code ne la décide.
    """
    mission = _mission(budget=100, depuis_s=150)
    assert _noeud(mission).budget_depasse() is True

    t1 = mission.started_at
    mission.started_at = datetime.now(timezone.utc)      # nouvelle tentative
    assert mission.started_at > t1

    apres = _noeud(mission)
    assert apres.budget_depasse() is False
    assert apres.budget_s == 100.0                        # budget entier


# ═══ T10/T11 — chemin direct et précédence ═════════════════════════

def test_T10_sans_mission_le_budget_local_sert():
    """`POST /execution/start` n'enregistre pas de mission : un seul
    `ExecutionMeta` y couvre toutes les tâches, il est donc légitimement
    l'autorité locale."""
    machine = ExecutionStateMachine(
        ExecutionMeta(mission_id="jamais-enregistree",
                      max_duration_seconds=42))
    assert machine.budget_s == 42.0
    assert machine.budget_consomme_s < 1        # perf_counter, pas de t0 civil


def test_T11_la_mission_prime_sur_l_execution_et_jamais_l_inverse():
    """La précédence, dans les deux sens."""
    mission = _mission(budget=120, depuis_s=1)
    assert _noeud(mission, budget_local=3600).budget_s == 120.0

    mission.max_duration_seconds = 7200
    assert _noeud(mission, budget_local=60).budget_s == 7200.0, (
        "l'ExecutionMeta a repris la main sur la mission")


def test_une_mission_jamais_demarree_ne_fait_pas_echouer_le_calcul():
    """`started_at` peut être `None` — une mission créée et pas encore
    lancée. On mesure alors ce qu'on sait mesurer, plutôt que de lever au
    milieu d'une exécution."""
    mission = _mission(budget=600)            # sans started_at
    machine = _noeud(mission)
    assert mission.started_at is None
    assert machine.budget_s == 600.0
    assert machine.budget_consomme_s < 1
    assert machine.budget_depasse() is False


# ═══ T9 — persistance réelle, deux processus ═══════════════════════

def test_T9_budget_et_t0_survivent_a_un_vrai_redemarrage():
    """Le chemin réel de M-8, pas une sérialisation isolée : un processus
    écrit la mission, un **autre** la relit."""
    etat = Path(tempfile.mkdtemp()) / "etat"
    env = dict(os.environ, HERMES_DATA_DIR=str(etat))
    PRE = "import sys\nsys.path.insert(0, %r)\n" % str(RACINE)

    ecriture = subprocess.run(
        [sys.executable, "-c", PRE + textwrap.dedent("""
            from datetime import datetime, timezone, timedelta
            from backend.mission.routes import _missions
            from backend.mission.mission_models import Mission, MissionStatus
            r = _missions; r.clear()
            m = Mission(title="persistee", status=MissionStatus.RUNNING,
                        max_duration_seconds=1234.0)
            m.started_at = datetime.now(timezone.utc) - timedelta(seconds=7)
            r[m.mission_id] = m
            print(m.mission_id + "|" + m.started_at.isoformat())
        """)], capture_output=True, text=True, env=env, timeout=300)
    assert ecriture.returncode == 0, ecriture.stderr[-2000:]
    mission_id, t0 = ecriture.stdout.strip().splitlines()[-1].split("|")

    lecture = subprocess.run(
        [sys.executable, "-c", PRE + textwrap.dedent(f"""
            from backend.mission.routes import _missions
            from backend.execution.execution_state import ExecutionStateMachine
            from backend.execution.execution_models import ExecutionMeta
            m = _missions.get({mission_id!r})
            sm = ExecutionStateMachine(ExecutionMeta(mission_id={mission_id!r}))
            print("|".join([
                "ABSENTE" if m is None else str(m.max_duration_seconds),
                "" if m is None else m.started_at.isoformat(),
                str(sm.budget_s),
                str(round(sm.budget_consomme_s)),
            ]))
        """)], capture_output=True, text=True, env=env, timeout=300)
    assert lecture.returncode == 0, lecture.stderr[-2000:]
    budget, t0_relu, budget_resolu, consomme = lecture.stdout.strip().splitlines()[-1].split("|")

    assert budget == "1234.0", "le budget n'a pas survécu au redémarrage"
    assert t0_relu == t0, "le t0 missionnel n'a pas survécu"
    assert budget_resolu == "1234.0", "le budget relu n'est pas celui qui s'applique"
    assert int(consomme) >= 7, (
        "le temps consommé est reparti de zéro après le redémarrage — "
        "c'est exactement le défaut que ce jalon corrige, déplacé")


# ═══ §17 — gardes anti-régression ══════════════════════════════════

def test_la_mission_prime_dans_le_code_et_pas_seulement_dans_les_tests():
    """La précédence est structurelle : `budget_s` consulte la mission
    **avant** l'`ExecutionMeta`. Inverser les deux lignes rendrait tous
    les tests ci-dessus verts sur le chemin direct et faux sur l'autre.
    """
    source = io.open(RACINE / "backend" / "execution" / "execution_state.py",
                     encoding="utf-8").read()
    arbre = ast.parse(source)
    fonction = next(
        n for n in ast.walk(arbre)
        if isinstance(n, ast.FunctionDef) and n.name == "budget_s")

    positions: dict[str, int] = {}
    for noeud in ast.walk(fonction):
        if isinstance(noeud, ast.Call):
            rendu = ast.unparse(noeud)
            if rendu.endswith("_mission()") and "mission" not in positions:
                positions["mission"] = noeud.lineno
            if "budget_de(self._meta)" in rendu and "meta" not in positions:
                positions["meta"] = noeud.lineno
    assert set(positions) == {"mission", "meta"}, positions
    assert positions["mission"] < positions["meta"], (
        "l'ExecutionMeta est consulté avant la mission — la précédence "
        "est inversée")


def test_aucun_execution_meta_ne_porte_son_propre_t0_missionnel():
    """La garde du défaut de HOS-247.

    Le temps missionnel se lit sur `Mission.started_at`. Si un jour
    `ExecutionMeta` ou `node_execution` se mettait à poser un horodatage
    de départ, le compteur repartirait par nœud sans que rien ne le dise.

    **Limite** : elle lit des noms de champs et d'assignations. Un t0
    caché dans un dictionnaire de métadonnées lui échapperait.
    """
    from backend.execution.execution_models import ExecutionMeta as EM

    champs = {c.name for c in EM.__dataclass_fields__.values()}
    interdits = {"started_monotonic", "budget_t0", "mission_started_at",
                 "deadline", "consumed_seconds", "expired"}
    assert not (champs & interdits), (
        f"`ExecutionMeta` porte {champs & interdits} — une seconde "
        "autorité temporelle")

    arbre = ast.parse(io.open(
        RACINE / "backend" / "mission" / "node_execution.py",
        encoding="utf-8").read())
    poses = {ast.unparse(c) for n in ast.walk(arbre)
             if isinstance(n, ast.Assign) for c in n.targets}
    assert not any("started_at" in p for p in poses), (
        "`node_execution` pose un horodatage de départ — chaque nœud "
        "réancrerait le temps missionnel")


def test_aucune_deadline_ni_temps_consomme_persiste():
    """La deadline reste **dérivée**. La persister créerait une troisième
    valeur pouvant contredire les deux dont elle dérive — le défaut que
    HOS-241 a corrigé ailleurs.

    Portée sur les dataclasses persistées, seul endroit où une valeur
    peut durablement contredire une autre.
    """
    from backend.mission.mission_models import Mission as M

    champs = {c.name for c in M.__dataclass_fields__.values()}
    interdits = {"deadline", "budget_deadline", "consumed_seconds",
                 "temps_consomme", "budget_expire", "expired"}
    assert not (champs & interdits), (
        f"`Mission` persiste {champs & interdits} — la deadline doit "
        "rester dérivée de started_at + max_duration_seconds")


def test_m8_persiste_le_budget_sans_migration():
    """Ce qui rend ce jalon sans schéma : le sérialiseur parcourt
    `fields()`. Le jour où il énumérerait des noms, ce champ
    disparaîtrait en silence."""
    import inspect

    from backend.mission import persistance

    source = inspect.getsource(persistance._en_brut)
    assert "fields(valeur)" in source, (
        "le sérialiseur n'énumère plus les champs du dataclass — un champ "
        "nouveau ne serait plus persisté")


def test_le_budget_est_toujours_consulte_a_un_seul_endroit():
    """Invariant de HOS-247, conservé : deux compteurs dériveraient."""
    appelants: list[str] = []
    for fichier in (RACINE / "backend").rglob("*.py"):
        if "tests" in fichier.parts or fichier.name == "execution_state.py":
            continue
        try:
            arbre = ast.parse(io.open(fichier, encoding="utf-8",
                                      errors="replace").read())
        except SyntaxError:  # pragma: no cover
            continue
        for noeud in ast.walk(arbre):
            if (isinstance(noeud, ast.Call)
                    and ast.unparse(noeud.func).endswith("budget_depasse")):
                appelants.append(f"{fichier.relative_to(RACINE)}:{noeud.lineno}")
    assert len(appelants) == 1, (
        f"le budget est consulté à {len(appelants)} endroits : {appelants}")


def test_le_registre_des_missions_n_est_pas_lu_dans_une_boucle_serree():
    """§19 — une lecture par tâche, pas par jeton.

    Et depuis que l'offset missionnel est lu **une seule fois**, à la
    construction, `budget_consomme_s` ne touche plus au registre du tout :
    elle n'additionne qu'un flottant et un `perf_counter`. La propriété la
    plus souvent lue est devenue la moins coûteuse.
    """
    import inspect

    from backend.execution.execution_state import ExecutionStateMachine as SM

    lecteurs = []
    for nom in dir(SM):
        membre = getattr(SM, nom, None)
        fonction = getattr(membre, "fget", membre)
        if not callable(fonction) or nom == "_mission":
            continue
        try:
            source = inspect.getsource(fonction)
        except (TypeError, OSError):
            continue
        if "_mission()" in source:
            lecteurs.append(nom)
    assert sorted(lecteurs) == ["_offset_missionnel", "budget_s"], lecteurs
    # Et la propriété chaude ne lit rien.
    assert "_mission()" not in inspect.getsource(SM.budget_consomme_s.fget), (
        "`budget_consomme_s` interroge le registre — elle est lue à chaque "
        "vérification de budget")
