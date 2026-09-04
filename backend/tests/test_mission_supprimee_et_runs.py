"""Une mission peut disparaître ; ce qu'elle a fait, non (T-21, HOS-253).

## D'où vient ce fichier

La passe 19 a supprimé deux missions de diagnostic par la primitive de
suppression. Leurs **huit runs** sont restés, dont un `en_cours`. La
question posée était : que signifie un run dont la mission n'existe plus ?

La passe 21 y a répondu en traçant les appels réels, et la réponse était
que le contrat était **déjà tenu par la conception** :

* pas de clé étrangère entre `runs.mission` et `missions.mission_id` ;
* `MagasinMissions.supprimer` ne touche que la table `missions` ;
* `Registre` n'expose aucune suppression, et le gel terminal vit dans le
  SQL ;
* `de_la_mission`, `reprendre` et `reconcilier` ne consultent **jamais**
  le magasin des missions ;
* le run porte son propre instantané depuis HOS-219.

Rien à construire, donc. Ce qui manquait était que personne ne l'écrive
et que rien ne le prouve. Ce fichier est la preuve.

## Ce que ces tests refusent

Qu'une absence de mission devienne un fait du run — une `Cause`, une
condition de réconciliation, un `PERDU` de complaisance. Un run perdu
doit l'être parce que son porteur est mort, jamais parce que son sujet a
été effacé.
"""

from __future__ import annotations

import ast
import inspect
import io
import textwrap
from pathlib import Path

import pytest

from backend.config.config_models import DatabaseConfig
from backend.mission.mission_models import Mission, MissionNode
from backend.mission.persistance import MagasinMissions
from backend.mission.routes import _RegistreMissions
from backend.runs.reconciliation import empreinte_du_processus, reconcilier
from backend.runs.registre import Cause, Registre, Statut, TERMINAUX
from backend.storage.database_manager import DatabaseManager

RACINE = Path(__file__).resolve().parents[2]

#: Un PID hors de toute plage possible : 2**22 dépasse le `pid_max` de
#: Linux comme la plage de Windows. Même convention que test_runs_perdus.
PROCESSUS_MORT = "4194304:1.0"


@pytest.fixture
def base(tmp_path):
    """Missions et runs dans **la même base**, comme en production.

    Deux bases séparées rendraient toute preuve d'absence de cascade
    creuse : rien ne pourrait cascader de l'une à l'autre.
    """
    config = DatabaseConfig(name=str(tmp_path / "hermes"))
    magasin = MagasinMissions(DatabaseManager(config))
    registre = Registre(DatabaseManager(config))
    return _RegistreMissions(magasin=magasin), magasin, registre


def _mission(magasin, titre="Produire une API"):
    mission = Mission(title=titre, objective=titre)
    mission.nodes = [MissionNode(node_id="n0", title="Étape")]
    magasin.enregistrer(mission)
    return mission


def _runs_pour(registre, mission, combien=3):
    return [
        registre.ouvrir(
            mission=mission.mission_id,
            objectif=f"tâche {i}",
            modele="lfm2.5-2.6b-125k",
            runtime="ollama",
            fournisseur="local",
            workspace=f"/w/{i}",
            projet="proj",
        )
        for i in range(combien)
    ]


def _forcer_l_empreinte(registre, identifiant, valeur):
    """Mentir sur le porteur — impossible par l'API publique, et voulu."""
    registre._db.execute("UPDATE runs SET processus = ? WHERE identifiant = ?",
                         (valeur, identifiant))


def _instantane(run):
    """Ce qu'un lecteur d'après coup vient chercher dans une ligne."""
    return (run.objectif, run.modele, run.runtime, run.fournisseur,
            run.workspace, run.projet, run.tentative, run.statut, run.cause)


# ═══ T-21-A — mission et runs normaux ════════════════════════════════

def test_A_les_runs_d_une_mission_sont_retrouvables(base):
    registre_missions, magasin, registre = base
    mission = _mission(magasin)
    ouverts = _runs_pour(registre, mission, 3)

    retrouves = registre.de_la_mission(mission.mission_id)

    assert [r.identifiant for r in retrouves] == [r.identifiant for r in ouverts]
    assert [r.objectif for r in retrouves] == ["tâche 0", "tâche 1", "tâche 2"]
    assert all(r.modele == "lfm2.5-2.6b-125k" for r in retrouves)
    assert magasin.lire(mission.mission_id) is not None


def test_A_les_runs_d_une_autre_mission_ne_se_melangent_pas(base):
    _, magasin, registre = base
    a, b = _mission(magasin, "Alpha"), _mission(magasin, "Beta")
    _runs_pour(registre, a, 2)
    _runs_pour(registre, b, 1)

    assert len(registre.de_la_mission(a.mission_id)) == 2
    assert len(registre.de_la_mission(b.mission_id)) == 1


# ═══ T-21-B — la suppression ne cascade pas ══════════════════════════

def test_B_supprimer_la_mission_ne_touche_aucun_run(base):
    """L'absence de cascade, prouvée par comparaison avant/après.

    Pas « les runs sont encore là » — *strictement* les mêmes lignes, avec
    le même instantané, jusqu'au compte total de la table.
    """
    registre_missions, magasin, registre = base
    mission = _mission(magasin)
    ouverts = _runs_pour(registre, mission, 3)
    registre.terminer(ouverts[0].identifiant, Statut.REUSSI)

    avant = {r.identifiant: _instantane(r)
             for r in registre.de_la_mission(mission.mission_id)}
    total_avant = len(registre.non_termines()) + len(
        [r for r in registre.de_la_mission(mission.mission_id) if r.termine])

    del registre_missions[mission.mission_id]

    assert magasin.lire(mission.mission_id) is None, "la mission n'a pas été supprimée"
    apres = {r.identifiant: _instantane(r)
             for r in registre.de_la_mission(mission.mission_id)}

    assert set(apres) == set(avant), "des runs ont disparu avec leur mission"
    assert apres == avant, "un instantané de run a été modifié par la suppression"
    assert len(apres) == 3
    total_apres = len(registre.non_termines()) + len(
        [r for r in registre.de_la_mission(mission.mission_id) if r.termine])
    assert total_apres == total_avant


def test_B_l_historique_reste_lisible_sans_sa_mission(base):
    """Un run orphelin répond encore à « quoi, avec quel modèle ? »."""
    registre_missions, magasin, registre = base
    mission = _mission(magasin)
    run = _runs_pour(registre, mission, 1)[0]
    del registre_missions[mission.mission_id]

    relu = registre.lire(run.identifiant)
    assert relu.objectif == "tâche 0"
    assert relu.modele == "lfm2.5-2.6b-125k"
    assert relu.runtime == "ollama"
    assert relu.fournisseur == "local"
    assert relu.mission == mission.mission_id, (
        "l'identifiant de mission reste inscrit : c'est ce qui permet de "
        "regrouper l'historique même quand le sujet a disparu")


# ═══ T-21-C — run terminal et mission absente ════════════════════════

@pytest.mark.parametrize("statut", TERMINAUX)
def test_C_un_run_terminal_ne_bouge_pas(base, statut):
    registre_missions, magasin, registre = base
    mission = _mission(magasin)
    run = _runs_pour(registre, mission, 1)[0]
    registre.terminer(run.identifiant, statut, cause=Cause.MODELE, raison="mesuré")
    avant = _instantane(registre.lire(run.identifiant))

    del registre_missions[mission.mission_id]

    assert _instantane(registre.lire(run.identifiant)) == avant
    assert registre.lire(run.identifiant).statut is statut
    assert registre.lire(run.identifiant).cause is Cause.MODELE


# ═══ T-21-D/E/F — la réconciliation ignore la mission ════════════════

def test_D_processus_mort_donne_perdu_par_la_preuve_du_processus(base):
    registre_missions, magasin, registre = base
    mission = _mission(magasin)
    run = _runs_pour(registre, mission, 1)[0]
    registre.demarrer(run.identifiant)
    _forcer_l_empreinte(registre, run.identifiant, PROCESSUS_MORT)
    del registre_missions[mission.mission_id]

    bilan = reconcilier(registre)

    relu = registre.lire(run.identifiant)
    assert relu.statut is Statut.PERDU
    assert relu.cause is Cause.PROCESSUS
    assert run.identifiant in bilan.perdus
    assert PROCESSUS_MORT in relu.raison, (
        "la raison doit nommer le processus disparu — c'est ce qui prouve "
        "que la transition vient de la preuve du porteur, pas de l'absence "
        "de mission")
    assert "mission" not in relu.raison.lower()


def test_D_la_mission_presente_donne_exactement_le_meme_resultat(base):
    """La preuve que l'absence de mission ne joue aucun rôle : même
    scénario, mission conservée, résultat identique."""
    _, magasin, registre = base
    mission = _mission(magasin)
    run = _runs_pour(registre, mission, 1)[0]
    registre.demarrer(run.identifiant)
    _forcer_l_empreinte(registre, run.identifiant, PROCESSUS_MORT)

    reconcilier(registre)

    relu = registre.lire(run.identifiant)
    assert (relu.statut, relu.cause) == (Statut.PERDU, Cause.PROCESSUS)
    assert magasin.lire(mission.mission_id) is not None


def test_E_processus_vivant_reste_en_cours_meme_sans_mission(base):
    registre_missions, magasin, registre = base
    mission = _mission(magasin)
    run = _runs_pour(registre, mission, 1)[0]
    registre.demarrer(run.identifiant)
    # Le processus courant : vivant par construction, aucune simulation.
    _forcer_l_empreinte(registre, run.identifiant, empreinte_du_processus())
    del registre_missions[mission.mission_id]

    bilan = reconcilier(registre)

    assert registre.lire(run.identifiant).statut is Statut.EN_COURS
    assert bilan.perdus == []
    assert run.identifiant in bilan.vivants


def test_F_processus_indeterminable_reste_en_cours_sans_cause(base):
    registre_missions, magasin, registre = base
    mission = _mission(magasin)
    run = _runs_pour(registre, mission, 1)[0]
    registre.demarrer(run.identifiant)
    _forcer_l_empreinte(registre, run.identifiant, "empreinte illisible")
    del registre_missions[mission.mission_id]

    bilan = reconcilier(registre)

    relu = registre.lire(run.identifiant)
    assert relu.statut is Statut.EN_COURS
    assert relu.cause is None, "aucune cause ne doit être inventée"
    assert run.identifiant in bilan.indecidables
    assert bilan.perdus == []


# ═══ T-21-G — idempotence ════════════════════════════════════════════

def test_G_un_run_deja_perdu_ne_rebouge_pas(base):
    registre_missions, magasin, registre = base
    mission = _mission(magasin)
    run = _runs_pour(registre, mission, 1)[0]
    registre.demarrer(run.identifiant)
    _forcer_l_empreinte(registre, run.identifiant, PROCESSUS_MORT)
    del registre_missions[mission.mission_id]

    reconcilier(registre)
    apres_un = _instantane(registre.lire(run.identifiant))
    bilan = reconcilier(registre)

    assert _instantane(registre.lire(run.identifiant)) == apres_un
    assert bilan.perdus == [], "un run déjà arrivé ne doit plus être candidat"


# ═══ T-21-H — reprise au niveau du Ledger ═══════════════════════════

def test_H_un_run_orphelin_reste_reprenable(base):
    registre_missions, magasin, registre = base
    mission = _mission(magasin)
    parent = _runs_pour(registre, mission, 1)[0]
    registre.terminer(parent.identifiant, Statut.ECHOUE, cause=Cause.MODELE,
                      raison="le modèle a rendu du texte au lieu de code")
    del registre_missions[mission.mission_id]

    reprise = registre.reprendre(parent.identifiant,
                                 motif="modèle plus grand", modele="qwen3.6-35b")

    assert reprise.parent == parent.identifiant
    assert reprise.tentative == parent.tentative + 1
    assert reprise.mission == mission.mission_id
    assert reprise.objectif == parent.objectif
    lignee = registre.lignee(reprise.identifiant)
    assert [r.identifiant for r in lignee] == [parent.identifiant, reprise.identifiant]
    assert magasin.lire(mission.mission_id) is None, (
        "la reprise du run n'a reconstruit aucune mission")


# ═══ T-21-I — la reprise de mission refuse explicitement ════════════

def test_I_les_routes_de_mission_refusent_une_mission_absente(base):
    """Un refus nommé, jamais une liste vide.

    Le chemin réel : les routes lisent `_missions.get(...)` et rendent une
    erreur. On l'exerce sur le registre de production après suppression.
    """
    from backend.mission import routes as mission_routes

    registre_missions, magasin, registre = base
    mission = _mission(magasin)
    _runs_pour(registre, mission, 1)
    del registre_missions[mission.mission_id]

    assert registre_missions.get(mission.mission_id) is None
    assert mission.mission_id not in registre_missions

    # Et la forme du refus, telle que les routes la produisent.
    source = inspect.getsource(mission_routes.resume_mission)
    assert "Mission or executor not found" in source or "not found" in source


def test_I_aucune_route_ne_reconstruit_une_mission(base):
    """Garde N4 : aucun chemin de reprise ne fabrique une `Mission`."""
    from backend.runs import registre as module_registre

    source = textwrap.dedent(inspect.getsource(module_registre.Registre.reprendre))
    appels = {ast.unparse(n.func) for n in ast.walk(ast.parse(source))
              if isinstance(n, ast.Call)}
    assert not any("Mission" in a for a in appels), appels


# ═══ T-21-J — Mission Control ════════════════════════════════════════

def test_J_la_vue_rend_les_runs_orphelins(base, monkeypatch):
    """La vraie vue, sur une mission absente."""
    from backend.services import vue_operations

    registre_missions, magasin, registre = base
    mission = _mission(magasin)
    _runs_pour(registre, mission, 2)
    del registre_missions[mission.mission_id]

    monkeypatch.setattr("backend.runs.registre.Registre", lambda *a, **k: registre)
    bloc = vue_operations.runs_de_la_mission(mission.mission_id)

    assert bloc["disponible"] is True
    assert len(bloc["donnees"]) == 2
    assert all(r["mission"] == mission.mission_id for r in bloc["donnees"])
    assert {r["objectif"] for r in bloc["donnees"]} == {"tâche 0", "tâche 1"}


def test_J_la_vue_ne_consulte_aucun_magasin_de_missions():
    """Garde N5, complétant celle de `test_vue_operations`."""
    from backend.services import vue_operations

    source = inspect.getsource(vue_operations)
    arbre = ast.parse(source)
    modules = {n.module for n in ast.walk(arbre)
               if isinstance(n, ast.ImportFrom) and n.module}
    assert not any("mission.persistance" in m or "mission.routes" in m
                   for m in modules), modules


# ═══ Gardes négatives ════════════════════════════════════════════════

def _appels_de(fonction):
    source = textwrap.dedent(inspect.getsource(fonction))
    return {ast.unparse(n.func) for n in ast.walk(ast.parse(source))
            if isinstance(n, ast.Call)}


def test_N1_la_suppression_n_appelle_rien_qui_touche_aux_runs():
    """Garde N1 : une cascade ajoutée à `__delitem__` rend ce test rouge."""
    appels = _appels_de(_RegistreMissions.__delitem__)
    interdits = [a for a in appels
                 if any(m in a.lower() for m in ("run", "registre", "ledger"))]
    assert interdits == [], (
        f"la suppression d'une mission touche au Ledger : {interdits}")


def test_N1_le_magasin_ne_supprime_que_la_table_des_missions():
    source = io.open(RACINE / "backend" / "mission" / "persistance.py",
                     encoding="utf-8").read()
    suppressions = [l.strip() for l in source.splitlines()
                    if "DELETE FROM" in l.upper()]
    assert suppressions, "aucune suppression trouvée — l'ancre a bougé"
    assert all("missions" in l for l in suppressions), suppressions
    assert not any("runs" in l for l in suppressions), suppressions


def test_N2_la_reconciliation_ne_consulte_jamais_les_missions():
    """Garde N2 : une condition « si la mission est absente » la rendrait
    rouge."""
    source = io.open(RACINE / "backend" / "runs" / "reconciliation.py",
                     encoding="utf-8").read()
    arbre = ast.parse(source)
    modules = {n.module for n in ast.walk(arbre)
               if isinstance(n, ast.ImportFrom) and n.module}
    assert not any(m.startswith("backend.mission") for m in modules), modules

    appels = _appels_de(reconcilier)
    suspects = [a for a in appels if "mission" in a.lower()]
    assert suspects == [], (
        f"la réconciliation consulte les missions : {suspects}. Elle doit "
        "décider sur la seule preuve du processus porteur.")


def test_N3_aucune_cause_pour_une_mission_absente():
    """Garde N3 : le vocabulaire des causes est clos.

    Une cause nouvelle est une décision architecturale, pas un effet de
    bord. Celle-ci s'ajoute délibérément à la liste quand elle est prise.
    """
    attendues = {"modele", "fournisseur", "quota", "ressource", "contexte",
                 "outil", "semantique", "verification", "politique",
                 "securite", "processus", "budget", "inconnue"}
    assert {c.value for c in Cause} == attendues
    assert not any(m in c.value for c in Cause
                   for m in ("mission", "orphelin", "reference"))


def test_N4_le_ledger_n_expose_aucune_suppression():
    """Un journal d'audit dont les lignes s'effacent n'est pas un journal."""
    publiques = {n for n in dir(Registre) if not n.startswith("_")}
    assert not any(m in n for n in publiques
                   for m in ("supprim", "delete", "purge", "vider")), publiques


# ═══ Redémarrage — deux vrais processus ══════════════════════════════

def test_l_historique_survit_a_un_redemarrage(tmp_path):
    """Le seul test qui prouve vraiment la durabilité : deux interpréteurs.

    Le premier crée, supprime la mission et meurt ; le second n'hérite de
    rien d'autre que du fichier. Aucun dictionnaire simulé, aucun cache
    partagé — c'est le disque qui répond.
    """
    import json
    import os
    import subprocess
    import sys

    base = str(tmp_path / "hermes")
    depot = str(RACINE)

    ecrire = textwrap.dedent(f'''
        import json, sys
        sys.path.insert(0, {depot!r})
        from backend.config.config_models import DatabaseConfig
        from backend.mission.mission_models import Mission
        from backend.mission.persistance import MagasinMissions
        from backend.mission.routes import _RegistreMissions
        from backend.runs.registre import Registre, Statut
        from backend.storage.database_manager import DatabaseManager

        config = DatabaseConfig(name={base!r})
        magasin = MagasinMissions(DatabaseManager(config))
        registre = Registre(DatabaseManager(config))
        cache = _RegistreMissions(magasin=magasin)

        m = Mission(title="Produire une API", objective="Produire une API")
        magasin.enregistrer(m)
        ids = []
        for i in range(3):
            r = registre.ouvrir(mission=m.mission_id, objectif="tache %d" % i,
                                modele="lfm2.5-2.6b-125k", runtime="ollama",
                                fournisseur="local", workspace="/w", projet="p")
            ids.append(r.identifiant)
        registre.terminer(ids[0], Statut.REUSSI)

        del cache[m.mission_id]
        assert magasin.lire(m.mission_id) is None
        print(json.dumps({{"mission": m.mission_id, "runs": ids}}))
    ''')

    relire = textwrap.dedent(f'''
        import json, sys
        sys.path.insert(0, {depot!r})
        from backend.config.config_models import DatabaseConfig
        from backend.mission.persistance import MagasinMissions
        from backend.runs.registre import Registre
        from backend.storage.database_manager import DatabaseManager

        config = DatabaseConfig(name={base!r})
        magasin = MagasinMissions(DatabaseManager(config))
        registre = Registre(DatabaseManager(config))
        mid = sys.argv[1]
        runs = registre.de_la_mission(mid)
        print(json.dumps({{
            "mission_presente": magasin.lire(mid) is not None,
            "runs": [{{"id": r.identifiant, "objectif": r.objectif,
                      "modele": r.modele, "runtime": r.runtime,
                      "statut": r.statut.value}} for r in runs],
        }}))
    ''')

    env = {**os.environ, "HERMES_DATA_DIR": str(tmp_path / "etat")}
    p1 = subprocess.run([sys.executable, "-c", ecrire], capture_output=True,
                        text=True, env=env, timeout=180)
    assert p1.returncode == 0, p1.stderr[-1500:]
    ecrit = json.loads(p1.stdout.strip().splitlines()[-1])

    p2 = subprocess.run([sys.executable, "-c", relire, ecrit["mission"]],
                        capture_output=True, text=True, env=env, timeout=180)
    assert p2.returncode == 0, p2.stderr[-1500:]
    relu = json.loads(p2.stdout.strip().splitlines()[-1])

    assert relu["mission_presente"] is False
    assert [r["id"] for r in relu["runs"]] == ecrit["runs"], (
        "des runs ont disparu entre les deux processus")
    assert [r["objectif"] for r in relu["runs"]] == ["tache 0", "tache 1", "tache 2"]
    assert all(r["modele"] == "lfm2.5-2.6b-125k" for r in relu["runs"])
    assert relu["runs"][0]["statut"] == "reussi"
