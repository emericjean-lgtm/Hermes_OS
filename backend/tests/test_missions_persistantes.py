"""Le journal survivait, son sujet non (HOS-245, dette M-8).

## Le défaut

HOS-221 a rendu le registre des **runs** durable ; HOS-240 lui a ajouté
une réconciliation qui pose `PERDU` au démarrage. Mais le registre des
**missions** était un `OrderedDict` en mémoire, borné à 200 avec éviction
FIFO — et rien sur disque.

Deux conséquences, mesurées avant correction :

- après un redémarrage, un run `PERDU` désignait une mission qui
  n'existait plus. On savait qu'une exécution avait été perdue, et pas ce
  qu'elle tentait de faire ;
- au-delà de 200 missions, le FIFO en effaçait définitivement **sans même
  redémarrer**.

## Ce que ces gardes tiennent

Que la mission survit, que l'éviction ne détruit plus rien, et que le lien
run → mission se résout encore après un vrai redémarrage. Les tests A, C
et D passent par de **vrais sous-processus** : une base relue dans le même
processus prouverait seulement que le cache fonctionne.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from backend.config.config_models import DatabaseConfig
from backend.mission.mission_models import (
    Mission,
    MissionContext,
    MissionEdge,
    MissionNode,
    MissionPriority,
    MissionStatus,
    MissionType,
    NodeStatus,
)
from backend.mission.persistance import MagasinMissions
from backend.mission.routes import _RegistreMissions
from backend.storage.database_manager import DatabaseManager

RACINE = Path(__file__).resolve().parents[2]


@pytest.fixture
def magasin(tmp_path: Path) -> MagasinMissions:
    return MagasinMissions(
        DatabaseManager(DatabaseConfig(name=str(tmp_path / "hermes_os"))))


def _mission(titre="une mission", statut=MissionStatus.RUNNING) -> Mission:
    return Mission(
        title=titre, objective="faire la chose", type=MissionType.DEVELOPMENT,
        priority=MissionPriority.HIGH, status=statut,
        context=MissionContext(project_id="p1", repository="o/r",
                               branch="main", local_path="C:/projet",
                               tags=["auth"]),
        nodes=[MissionNode(title="analyser", status=NodeStatus.COMPLETED,
                           required_skills=["python"]),
               MissionNode(title="écrire", status=NodeStatus.PENDING)],
        edges=[MissionEdge(source_id="a", target_id="b")],
        metadata={"origine": "cockpit"},
    )


# ═══ §6 — la mission est reconstructible, pas résumée ════════════════

def test_une_mission_se_relit_entiere(magasin):
    """Persister un sous-ensemble affichable aurait suffi à remplir la
    console et rendu la mission irrécupérable. Le DAG, le contexte, les
    énumérations et les horodatages doivent tous revenir typés.
    """
    origine = _mission()
    magasin.enregistrer(origine)
    relue = magasin.lire(origine.mission_id)

    assert relue.title == origine.title
    assert relue.objective == origine.objective
    assert relue.status is MissionStatus.RUNNING          # énumération, pas str
    assert relue.type is MissionType.DEVELOPMENT
    assert relue.priority is MissionPriority.HIGH
    assert relue.context.local_path == "C:/projet"
    assert relue.context.tags == ["auth"]
    assert [n.title for n in relue.nodes] == ["analyser", "écrire"]
    assert relue.nodes[0].status is NodeStatus.COMPLETED
    assert relue.edges[0].source_id == "a"
    assert relue.metadata == {"origine": "cockpit"}
    # Les méthodes dérivées fonctionnent : la mission est un objet, pas un
    # dictionnaire déguisé.
    assert relue.progress_pct() == 50.0
    assert relue.total_nodes() == 2


def test_un_champ_inconnu_ne_perd_pas_la_mission(magasin):
    """Une base écrite par une version ultérieure doit rester lisible.

    Refuser tout le document pour un champ ajouté depuis ferait perdre la
    mission entière — le contraire de ce que la persistance promet.
    """
    origine = _mission()
    magasin.enregistrer(origine)
    ligne = magasin._db.fetch_one(
        "SELECT document FROM missions WHERE mission_id = ?",
        (origine.mission_id,))
    brut = json.loads(dict(ligne)["document"])
    brut["champ_du_futur"] = {"quelconque": True}
    magasin._db.execute(
        "UPDATE missions SET document = ? WHERE mission_id = ?",
        (json.dumps(brut), origine.mission_id))

    relue = magasin.lire(origine.mission_id)
    assert relue is not None and relue.title == origine.title


def test_une_mission_se_reecrit(magasin):
    """Contrairement à un run, une mission évolue : c'est le dernier état
    qui fait foi. Le gel terminal de HOS-221 protège une trace close ; une
    mission n'en est pas une.
    """
    m = _mission(statut=MissionStatus.RUNNING)
    magasin.enregistrer(m)
    m.status = MissionStatus.COMPLETED
    magasin.enregistrer(m)

    assert magasin.lire(m.mission_id).status is MissionStatus.COMPLETED
    assert magasin.nombre() == 1          # réécrite, pas dupliquée


# ═══ Test B — l'éviction ne perd plus rien ══════════════════════════

def test_l_eviction_libere_la_memoire_sans_rien_detruire(tmp_path):
    """Le second visage de M-8 : au-delà de la borne, on perdait des
    missions **sans même redémarrer**.
    """
    registre = _RegistreMissions(maximum=3, magasin=MagasinMissions(
        DatabaseManager(DatabaseConfig(name=str(tmp_path / "hermes_os")))))
    identifiants = []
    for i in range(6):
        m = _mission(f"mission {i}", statut=MissionStatus.COMPLETED)
        registre[m.mission_id] = m
        identifiants.append(m.mission_id)

    assert len(registre._missions) == 3          # le plan de travail est borné
    assert len(registre) == 3                    # …et `len` le dit
    assert registre.total() == 6                 # le durable les a toutes
    assert identifiants[0] not in registre._missions
    assert identifiants[0] in registre           # relue depuis la base
    assert registre[identifiants[0]].title == "mission 0"


def test_une_mission_active_n_est_jamais_evincee(tmp_path):
    """Comportement d'avant HOS-245, conservé : l'éviction ne prend que
    des missions terminées, et dépasse la borne plutôt que d'emporter une
    mission en cours."""
    registre = _RegistreMissions(maximum=2, magasin=MagasinMissions(
        DatabaseManager(DatabaseConfig(name=str(tmp_path / "hermes_os")))))
    for i in range(5):
        m = _mission(f"active {i}", statut=MissionStatus.RUNNING)
        registre[m.mission_id] = m

    assert len(registre._missions) == 5


def test_une_suppression_voulue_emporte_la_ligne(tmp_path):
    """`del` est l'intention d'un appelant ; l'éviction ne l'est pas. Les
    confondre rendrait la persistance inutile ou la suppression
    impossible."""
    magasin = MagasinMissions(
        DatabaseManager(DatabaseConfig(name=str(tmp_path / "hermes_os"))))
    registre = _RegistreMissions(maximum=10, magasin=magasin)
    m = _mission()
    registre[m.mission_id] = m
    del registre[m.mission_id]

    assert m.mission_id not in registre
    assert magasin.lire(m.mission_id) is None

    with pytest.raises(KeyError):
        del registre["jamais-vue"]


def test_vider_le_registre_vide_aussi_la_base(tmp_path):
    """Les tests appellent `clear()` entre deux cas. Ne vider que le cache
    ferait hériter chaque test des missions du précédent."""
    magasin = MagasinMissions(
        DatabaseManager(DatabaseConfig(name=str(tmp_path / "hermes_os"))))
    registre = _RegistreMissions(maximum=10, magasin=magasin)
    registre[_mission().mission_id] = _mission()
    registre.clear()

    assert len(registre) == 0
    assert registre.total() == 0
    assert magasin.nombre() == 0


def test_le_cache_prime_sur_la_base_pour_une_mission_vivante(tmp_path):
    """Entre deux écritures, la mémoire est plus fraîche que le disque.

    Rendre la version disque ferait clignoter le statut d'une mission en
    cours dans la console.
    """
    magasin = MagasinMissions(
        DatabaseManager(DatabaseConfig(name=str(tmp_path / "hermes_os"))))
    registre = _RegistreMissions(maximum=10, magasin=magasin)
    m = _mission(statut=MissionStatus.RUNNING)
    registre[m.mission_id] = m
    m.status = MissionStatus.COMPLETED            # muté sans réécriture

    rendue = registre.values()[0]
    assert rendue.status is MissionStatus.COMPLETED
    assert rendue is m


def test_sans_magasin_le_registre_fonctionne_comme_avant():
    """Une panne de persistance ne doit pas empêcher de créer une mission.

    Une correction qui rendrait Hermes inutilisable quand sa base est
    illisible serait un recul sur le défaut qu'elle corrige.
    """
    registre = _RegistreMissions(maximum=2, magasin=None)
    registre._magasin_resolu = True               # magasin indisponible
    m = _mission()
    registre[m.mission_id] = m

    assert registre[m.mission_id] is m
    assert len(registre) == 1
    assert registre.total() == 1                 # sans magasin, les deux coïncident
    registre.clear()
    assert len(registre) == 0


# ═══ Tests A, C, D, E, F — de vrais redémarrages ════════════════════

def _dans_un_processus(script: str, racine_etat: Path) -> str:
    """Exécuter du code dans un **vrai** processus Python neuf.

    Une base relue dans le même processus ne prouverait que le
    fonctionnement du cache : c'est exactement ce que HOS-240 a appris en
    tuant un vrai processus avec `os._exit`.
    """
    env = dict(os.environ, HERMES_DATA_DIR=str(racine_etat))
    fils = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(script)],
        capture_output=True, text=True, timeout=300, env=env, cwd=str(RACINE))
    assert fils.returncode == 0, fils.stderr[-3000:]
    return fils.stdout.strip()


PREAMBULE = """
    import sys
    sys.path.insert(0, %r)
    from backend.mission.routes import _RegistreMissions
    from backend.mission.mission_models import (
        Mission, MissionContext, MissionNode, MissionStatus, MissionType)
""" % str(RACINE)


def test_A_une_mission_survit_a_un_redemarrage(tmp_path):
    """Créer → arrêter le processus → redémarrer → la mission est là."""
    etat = tmp_path / "etat"
    identifiant = _dans_un_processus(PREAMBULE + """
    r = _RegistreMissions()
    r.clear()
    m = Mission(title="survivre au redemarrage", objective="tenir",
                type=MissionType.DEVELOPMENT, status=MissionStatus.RUNNING,
                context=MissionContext(project_id="p1", local_path="C:/projet"),
                nodes=[MissionNode(title="etape")])
    r[m.mission_id] = m
    print(m.mission_id)
    """, etat)

    lu = _dans_un_processus(PREAMBULE + f"""
    r = _RegistreMissions()
    m = r.get({identifiant!r})
    print("ABSENTE" if m is None else
          m.title + "|" + m.status.value + "|" + m.context.local_path
          + "|" + str(len(m.nodes)))
    """, etat)

    assert lu == "survivre au redemarrage|running|C:/projet|1"


def test_E_deux_processus_partagent_la_meme_base(tmp_path):
    """Deux initialisations doivent tomber sur la même racine d'état.

    Deux fichiers auraient reproduit le défaut de HOS-237 : une base
    vivante, une base morte, et rien pour dire laquelle fait foi.
    """
    etat = tmp_path / "etat"
    premier = _dans_un_processus(PREAMBULE + """
    from backend.mission.persistance import MagasinMissions
    r = _RegistreMissions(); r.clear()
    m = Mission(title="partagee"); r[m.mission_id] = m
    print(MagasinMissions()._db.db_path if hasattr(MagasinMissions()._db, "db_path")
          else "chemin inconnu")
    """, etat)

    second = _dans_un_processus(PREAMBULE + """
    r = _RegistreMissions()
    print(str(len(r)) + "|" + r.values()[0].title)
    """, etat)

    assert second == "1|partagee"
    assert str(etat) in premier or premier == "chemin inconnu"


def test_F_une_base_anterieure_se_migre_sans_perte(tmp_path):
    """Une base ouverte avant HOS-245 n'a pas la colonne `maj_le`.

    Sans migration, l'`INSERT` nommé échouerait et plus aucune mission ne
    s'enregistrerait : une correction de persistance aurait cassé la
    création. Même mécanisme que HOS-240.
    """
    from backend.mission import persistance as module

    ancien = "\n".join(l for l in module._SCHEMA.splitlines()
                       if "maj_le" not in l)
    assert "maj_le" not in ancien and "document" in ancien

    db = DatabaseManager(DatabaseConfig(name=str(tmp_path / "hermes_os")))
    db.initialize()
    conn = db.get_connection()
    conn.executescript(ancien)
    conn.execute(
        "INSERT INTO missions (mission_id, titre, statut, document) "
        "VALUES ('ancienne', 'avant HOS-245', 'running', ?)",
        (json.dumps({"mission_id": "ancienne", "title": "avant HOS-245"}),))
    conn.commit()

    magasin = MagasinMissions(db)          # migre en s'ouvrant

    colonnes = {l[1] for l in db.get_connection().execute(
        "PRAGMA table_info(missions)")}
    assert "maj_le" in colonnes
    relue = magasin.lire("ancienne")
    assert relue is not None and relue.title == "avant HOS-245"


# ═══ §8 — le lien run → mission, et la reprise ══════════════════════

def test_C_et_D_un_run_perdu_retrouve_sa_mission_apres_redemarrage(tmp_path):
    """Le trou exact que ce jalon ferme.

    Un processus crée une mission, ouvre un run dessus, puis meurt sans
    rien clore (`os._exit` ne déroule ni `finally` ni `atexit`). Au
    redémarrage : la réconciliation pose `PERDU`, **et** la mission est
    encore là — donc la reprise a un objet.
    """
    etat = tmp_path / "etat"

    # `_dans_un_processus` exige un code 0 ; ce scénario meurt volontairement,
    # donc il lance son sous-processus lui-même.
    env = dict(os.environ, HERMES_DATA_DIR=str(etat))
    fils = subprocess.run([sys.executable, "-c", textwrap.dedent(PREAMBULE + """
    import os, sys
    from backend.runs.registre import Registre
    r = _RegistreMissions(); r.clear()
    m = Mission(title="mission interrompue", objective="produire un rapport",
                status=MissionStatus.RUNNING)
    r[m.mission_id] = m
    run = Registre().ouvrir(mission=m.mission_id, objectif=m.objective)
    Registre().demarrer(run.identifiant)
    print(m.mission_id + "|" + run.identifiant); sys.stdout.flush()
    os._exit(1)
    """)], capture_output=True, text=True, timeout=300, env=env, cwd=str(RACINE))
    assert fils.returncode == 1, fils.stderr[-3000:]
    mission_id, run_id = fils.stdout.strip().splitlines()[-1].split("|")

    # Redémarrage : réconciliation, puis résolution du lien.
    resultat = _dans_un_processus(PREAMBULE + f"""
    from backend.runs.reconciliation import reconcilier
    from backend.runs.registre import Registre, Statut

    bilan = reconcilier()
    registre = Registre()
    run = registre.lire({run_id!r})
    mission = _RegistreMissions().get({mission_id!r})
    reprise = registre.reprendre(
        {run_id!r}, motif="processus disparu au redemarrage")
    print("|".join([
        run.statut.value,
        run.cause.value if run.cause else "-",
        "ABSENTE" if mission is None else mission.title,
        "" if mission is None else mission.objective,
        str(reprise.tentative),
        reprise.mission,
    ]))
    """, etat)

    statut, cause, titre, objectif, tentative, mission_du_run = resultat.split("|")
    assert statut == "perdu"                    # §4 tient
    assert cause == "processus"
    assert titre == "mission interrompue"       # …et son sujet aussi
    assert objectif == "produire un rapport"
    assert tentative == "2"                     # la reprise est possible
    assert mission_du_run == mission_id         # le lien se résout


# ═══ §9 — les gardes ════════════════════════════════════════════════

def test_il_n_existe_qu_une_seule_table_de_missions():
    """Deux tables donneraient deux vérités, dont une muette — le défaut
    exact de HOS-237 avec ses deux journaux d'événements."""
    import ast
    import io

    creations: list[str] = []
    for fichier in (RACINE / "backend").rglob("*.py"):
        if "tests" in fichier.parts:
            continue
        try:
            arbre = ast.parse(io.open(fichier, encoding="utf-8",
                                      errors="replace").read())
        except SyntaxError:  # pragma: no cover
            continue
        for noeud in ast.walk(arbre):
            if (isinstance(noeud, ast.Constant)
                    and isinstance(noeud.value, str)
                    and "CREATE TABLE" in noeud.value.upper()
                    and "missions" in noeud.value.lower()):
                creations.append(str(fichier.relative_to(RACINE)))
    assert creations == ["backend\\mission\\persistance.py".replace("\\", os.sep)], (
        f"la table des missions est créée à {len(creations)} endroits : {creations}")


def test_la_base_des_missions_est_celle_des_runs():
    """Aucun second fichier de base : même `DatabaseManager` par défaut,
    donc même fichier que les `runs` de HOS-221."""
    import inspect

    from backend.mission import persistance
    from backend.runs import registre

    for module in (persistance, registre):
        source = inspect.getsource(module)
        assert "DatabaseManager()" in source, (
            f"{module.__name__} n'utilise pas le DatabaseManager par défaut")


def test_la_base_ne_vit_pas_dans_le_depot(tmp_path, monkeypatch):
    """La racine d'état, jamais l'arbre de code — HOS-215, HOS-237."""
    monkeypatch.setenv("HERMES_DATA_DIR", str(tmp_path))
    import backend.core.etat as etat

    etat.racine.cache_clear()
    try:
        chemin = Path(str(etat.racine()))
        assert tmp_path in chemin.parents or chemin == tmp_path
        assert RACINE not in chemin.parents
    finally:
        etat.racine.cache_clear()


def test_l_eviction_n_appelle_jamais_la_suppression():
    """La garde structurelle du cœur de M-8.

    Si `_evincer` se remettait à supprimer en base, l'éviction
    redeviendrait destructrice — et le test B ci-dessus passerait encore
    tant que la borne n'est pas atteinte dans son cas précis.
    """
    import ast
    import inspect
    import textwrap as tw

    from backend.mission.routes import _RegistreMissions as R

    arbre = ast.parse(tw.dedent(inspect.getsource(R._evincer)))
    appels = {ast.unparse(n.func) for n in ast.walk(arbre)
              if isinstance(n, ast.Call)}
    assert not any("supprimer" in a or "vider" in a for a in appels), (
        "l'éviction du cache touche à la base — une mission évincée serait "
        "de nouveau perdue")
