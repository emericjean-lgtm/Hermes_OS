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


class TestLaBorne:
    def test_en_deca_de_la_borne_rien_n_est_evince(self):
        registre = _RegistreMissions(maximum=10)
        for i in range(10):
            registre[f"m{i}"] = _mission(f"m{i}")

        assert len(registre) == 10
        assert registre.get("m0") is not None

    def test_au_dela_la_plus_ancienne_terminee_part(self):
        registre = _RegistreMissions(maximum=3)
        for i in range(5):
            registre[f"m{i}"] = _mission(f"m{i}")

        assert len(registre) == 3
        assert registre.get("m0") is None
        assert registre.get("m1") is None
        assert registre.get("m4") is not None

    def test_reenregistrer_une_mission_la_rajeunit(self):
        """Sinon une mission longue, enregistrée tôt et remise à jour tout
        du long, serait la première évincée."""
        registre = _RegistreMissions(maximum=3)
        for i in range(3):
            registre[f"m{i}"] = _mission(f"m{i}")

        registre["m0"] = _mission("m0")  # remise à jour
        registre["m3"] = _mission("m3")

        assert registre.get("m0") is not None
        assert registre.get("m1") is None


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
