"""M-8 — le registre des missions n'est plus un dict nu (HOS-120).

`mission/routes.py::_missions` était un `dict` module-level sans verrou et
sans borne. C'est le troisième état global partagé de la journée à poser le
même problème, après `autonomous/routes.py::_engine` (HOS-117).

Deux défauts distincts, et un piège dans la correction :

* **sans verrou** — `register_mission` est appelé depuis l'orchestrateur
  autonome, qui marche son graphe dans un pool de fils, pendant que
  `GET /missions` itère le même dict. Une vue (`dict.values()`) lève
  `RuntimeError: dictionary changed size during iteration` au premier
  chevauchement — de façon intermittente, donc invisible en test et
  reproductible seulement en charge ;
* **sans borne** — chaque mission y restait pour la vie du processus ;
* **le piège** — une borne naïve évincerait la plus ancienne quelle qu'elle
  soit, y compris une mission `running`. Elle deviendrait introuvable
  pendant son exécution, et l'exécuteur continuerait de la faire avancer
  dans le vide. C'est ce que ce module interdit explicitement.
"""
from __future__ import annotations

import threading

import pytest

from backend.mission.mission_models import Mission, MissionStatus
from backend.mission.routes import _RegistreMissions


def _mission(identifiant: str, statut: MissionStatus = MissionStatus.COMPLETED
             ) -> Mission:
    mission = Mission(mission_id=identifiant, title=identifiant)
    mission.status = statut
    return mission


class TestLOrdreDurable:
    """Deux missions de la même milliseconde se départagent (A-19).

    `MagasinMissions` ordonnait sur `cree_le` seul. L'horloge de Windows a
    une granularité d'environ 15,6 ms : cinq missions enregistrées
    d'affilée portent le **même** horodatage, et SQLite les rendait alors
    dans un ordre qu'il ne garantit pas.

    `_RegistreMissions` documente pourtant un FIFO — « Ordonné par
    insertion » — et son `__len__` hydrate le cache depuis ces requêtes.
    Le contrat existait, rien ne le faisait tenir : mesuré,
    `test_au_dela_la_plus_ancienne_terminee_quitte_le_cache` échouait
    **5 fois sur 20**, et 0 sur 25 une fois `rowid` ajouté au tri.
    """

    def _magasin(self, tmp_path):
        from backend.mission.persistance import MagasinMissions
        from backend.storage.database_manager import DatabaseConfig, DatabaseManager

        return MagasinMissions(
            DatabaseManager(DatabaseConfig(name=str(tmp_path / "missions"))))

    def test_l_ordre_est_celui_de_l_insertion_a_horodatage_egal(self, tmp_path):
        from datetime import datetime, timezone

        magasin = self._magasin(tmp_path)
        instant = datetime.now(timezone.utc)
        for i in range(6):
            mission = _mission(f"m{i}")
            # Le cas réel, forcé : le même horodatage pour toutes.
            mission.created_at = instant
            magasin.enregistrer(mission)

        assert magasin.identifiants() == [f"m{i}" for i in range(5, -1, -1)], (
            "à horodatage égal, l'ordre n'est plus celui de l'insertion — "
            "l'éviction du cache redevient un tirage")

    def test_l_ordre_reste_stable_d_une_lecture_a_l_autre(self, tmp_path):
        from datetime import datetime, timezone

        magasin = self._magasin(tmp_path)
        instant = datetime.now(timezone.utc)
        for i in range(6):
            mission = _mission(f"m{i}")
            mission.created_at = instant
            magasin.enregistrer(mission)

        lectures = {tuple(magasin.identifiants()) for _ in range(10)}
        assert len(lectures) == 1, (
            f"dix lectures ont rendu {len(lectures)} ordres différents")


class TestLaBorne:
    def test_en_deca_de_la_borne_rien_n_est_evince(self):
        registre = _RegistreMissions(maximum=10)
        for i in range(10):
            registre[f"m{i}"] = _mission(f"m{i}")

        assert len(registre) == 10
        assert registre.get("m0") is not None

    def test_au_dela_la_plus_ancienne_terminee_quitte_le_cache(self):
        """Réécrit en HOS-245 : l'éviction libère, elle ne détruit plus.

        Ce test affirmait `registre.get("m0") is None` — c'est-à-dire la
        perte définitive que la dette M-8 nommait. Le plan de travail
        reste borné à trois ; la mission évincée, elle, se relit.
        """
        registre = _RegistreMissions(maximum=3)
        for i in range(5):
            registre[f"m{i}"] = _mission(f"m{i}")

        assert len(registre) == 3
        assert "m0" not in registre._missions      # hors du plan de travail
        assert registre.get("m0") is not None      # …mais pas perdue
        assert registre.get("m0").mission_id == "m0"
        assert registre.get("m4") is not None
        assert registre.total() == 5               # le durable les a toutes

    def test_reenregistrer_une_mission_la_rajeunit(self):
        """Sinon une mission longue, enregistrée tôt et remise à jour tout
        du long, serait la première évincée."""
        registre = _RegistreMissions(maximum=3)
        for i in range(3):
            registre[f"m{i}"] = _mission(f"m{i}")

        registre["m0"] = _mission("m0")  # remise à jour
        registre["m3"] = _mission("m3")

        # Le rajeunissement tient : c'est `m1` qui quitte le cache, pas
        # `m0` remise à jour. Ce que HOS-245 change est seulement le sort
        # de l'évincée — elle sort du plan de travail, pas de l'existence.
        assert "m0" in registre._missions
        assert "m1" not in registre._missions
        assert registre.get("m1") is not None


class TestUneMissionEnCoursNEstJamaisEvincee:
    """Le défaut que la borne aurait introduit si on l'avait écrite comme un
    LRU ordinaire."""

    def test_une_mission_running_survit_a_la_borne(self):
        registre = _RegistreMissions(maximum=2)
        registre["longue"] = _mission("longue", MissionStatus.RUNNING)
        for i in range(5):
            registre[f"m{i}"] = _mission(f"m{i}")

        assert registre.get("longue") is not None

    def test_quand_tout_est_actif_la_borne_cede_et_le_dit(self, caplog):
        """Dépasser la borne est le moindre mal ; le taire ne l'est pas."""
        registre = _RegistreMissions(maximum=2)
        for i in range(5):
            registre[f"m{i}"] = _mission(f"m{i}", MissionStatus.RUNNING)

        assert len(registre) == 5
        assert "toutes encore" in caplog.text

    @pytest.mark.parametrize("statut", [
        MissionStatus.CREATED, MissionStatus.VALIDATED, MissionStatus.READY,
        MissionStatus.RUNNING, MissionStatus.PAUSED,
    ])
    def test_aucun_statut_non_terminal_n_est_evincable(self, statut):
        registre = _RegistreMissions(maximum=1)
        registre["vivante"] = _mission("vivante", statut)
        for i in range(4):
            registre[f"m{i}"] = _mission(f"m{i}")

        assert registre.get("vivante") is not None


class TestLeVerrou:
    def test_lister_pendant_qu_on_enregistre_ne_leve_pas(self):
        """L'incident exact : `dict.values()` rend une vue, et itérer une vue
        pendant qu'un autre fil insère lève `RuntimeError`. Le registre rend
        une copie."""
        registre = _RegistreMissions(maximum=10_000)
        for i in range(200):
            registre[f"initiale{i}"] = _mission(f"initiale{i}")

        stop = threading.Event()
        erreurs: list[BaseException] = []

        def ecrire():
            i = 0
            while not stop.is_set():
                registre[f"nouvelle{i}"] = _mission(f"nouvelle{i}")
                i += 1

        def lire():
            try:
                for _ in range(2000):
                    for mission in registre.values():
                        assert mission.mission_id
                    assert len(registre) > 0
            except BaseException as erreur:  # noqa: BLE001 - c'est le sujet
                erreurs.append(erreur)

        ecrivain = threading.Thread(target=ecrire, daemon=True)
        lecteur = threading.Thread(target=lire)
        ecrivain.start()
        lecteur.start()
        lecteur.join(timeout=30)
        stop.set()
        ecrivain.join(timeout=5)

        assert erreurs == []

    def test_le_verrou_est_reentrant(self):
        """`_evincer` s'exécute déjà sous le verrou pris par `__setitem__`.
        Un `Lock` simple s'auto-bloquerait à la première éviction."""
        registre = _RegistreMissions(maximum=1)
        registre["a"] = _mission("a")
        registre["b"] = _mission("b")  # déclenche l'éviction sous verrou

        assert len(registre) == 1


class TestLaFormeDUnDict:
    """Les appelants — routes comprises — n'ont pas été réécrits. Ils
    doivent continuer de le manipuler comme le dict qu'il remplace."""

    def test_les_operations_utilisees_par_le_code_existant(self):
        registre = _RegistreMissions()
        mission = _mission("m")

        registre["m"] = mission
        assert registre["m"] is mission
        assert registre.get("m") is mission
        assert registre.get("absente") is None
        assert "m" in registre
        assert len(registre) == 1
        assert [m.mission_id for m in registre.values()] == ["m"]
        assert [i for i, _ in registre.items()] == ["m"]

        assert registre.pop("m", None) is mission
        assert registre.pop("m", None) is None

        registre["m"] = mission
        del registre["m"]
        assert len(registre) == 0

        registre["m"] = mission
        registre.clear()
        assert len(registre) == 0

    def test_monkeypatch_setitem_fonctionne_dessus(self, monkeypatch):
        """`backend/tests/test_task_context_continuity.py` s'en sert pour
        injecter une mission — il faut `get`, `__setitem__` et `__delitem__`."""
        registre = _RegistreMissions()
        mission = _mission("m")

        monkeypatch.setitem(registre, "m", mission)
        assert registre.get("m") is mission

        monkeypatch.undo()
        assert registre.get("m") is None
