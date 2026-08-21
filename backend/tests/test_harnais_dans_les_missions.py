"""Qui exécute réellement une tâche de mission (HOS-138).

`_par_le_harnais` décide, à chaque tâche, entre la session vivante de la
mission et le mode jetable. La décision doit être **dite** dans tous les
cas : un repli silencieux vers un agent amnésique ressemble en tout point à
un succès, et c'est exactement ce défaut qui a laissé, des mois durant, des
missions contourner Hermes Agent — l'incident que
`test_hermes_agent_is_the_brain.py` garde sous le nom
`HERMES_AGENT_BYPASS_DETECTED`.

Deux règles y sont vérifiées, chacune payée par une mesure :

* un tour **non abouti** ne devient jamais une réponse. Le rendre ferait
  passer une session bloquée pour un modèle laconique ;
* le harnais ne s'active que si ses prérequis sont réunis. L'agent rappelle
  Hermes OS par MCP pour obtenir ses outils : backend éteint, il démarre
  avec zéro outil et le tour ne revient jamais.
"""
from __future__ import annotations

import asyncio

import pytest

from backend.execution.task_executor import RealTaskExecutor
from backend.ral.adapters.hermes_agent_acp import Tour


class _Prerequis:
    def __init__(self, pret: bool, explication: str = "backend éteint") -> None:
        self.pret = pret
        self._explication = explication

    def explication(self) -> str:
        return self._explication


class _RegistreFactice:
    def __init__(self, tour: Tour, *, disponible=(True, "")) -> None:
        self._tour = tour
        self._disponible = disponible
        self.appels: list[tuple] = []
        self.fermetures: list[str] = []

    async def disponible_pour(self, cle):
        return self._disponible

    async def tour(self, cle, workspace, texte, *, amorce="", modele="",
                   delai=0):
        self.appels.append((cle, workspace, texte, amorce, modele))
        if isinstance(self._tour, Exception):
            raise self._tour
        return self._tour

    def tours_de(self, cle):
        return len(self.appels)

    async def fermer(self, cle):
        self.fermetures.append(cle)


@pytest.fixture
def contexte():
    return {"mission_id": "m-7", "workspace": "/ws", "task_id": "t-1"}


def _executeur(**kw):
    return RealTaskExecutor(chat=lambda **_: None, harnais_actif=True, **kw)


def _appel(executeur, registre, prerequis, contexte, monkeypatch):
    import backend.ral.adapters.prerequis_harnais as pre
    import backend.ral.adapters.sessions_de_mission as sess

    monkeypatch.setattr(pre, "verifier", lambda **_: prerequis)
    monkeypatch.setattr(sess, "registre", lambda: registre)
    return asyncio.run(executeur._par_le_harnais(
        [{"role": "user", "content": "écris le fichier"}],
        model="lfm2.5-2.6b-125k", runtime_ctx=contexte))


class TestQuandLeHarnaisSert:
    def test_un_tour_abouti_devient_la_reponse(self, contexte, monkeypatch):
        registre = _RegistreFactice(
            Tour(texte="fait", stop="end_turn", jetons_entree=15638,
                 jetons_sortie=64, pensee="x" * 1670))

        reponse = _appel(_executeur(), registre, _Prerequis(True), contexte,
                         monkeypatch)

        assert reponse.content == "fait"
        assert reponse.metadata["runtime"] == "hermes-agent-acp"
        assert reponse.metadata["input_tokens"] == 15638
        # Le raisonnement est separe a la source par l'agent ; les confondre
        # a deja fait compter 316 mots la ou le modele en avait ecrit 7.
        assert reponse.metadata["reasoning_chars"] == 1670

    def test_la_mission_et_le_workspace_sont_transmis(self, contexte,
                                                      monkeypatch):
        registre = _RegistreFactice(Tour(texte="fait", stop="end_turn"))

        _appel(_executeur(), registre, _Prerequis(True), contexte, monkeypatch)

        cle, workspace, _, amorce, modele = registre.appels[0]
        assert (cle, workspace) == ("m-7", "/ws")
        assert "m-7" in amorce, "le contexte de mission doit amorcer la session"
        # Le routeur de Hermes OS choisit un modele par tache. Une session
        # qui ne l'apprend jamais ferait de ce choix une decoration —
        # regression silencieuse par rapport au mode jetable, qui relancait
        # tout et appliquait donc le modele a chaque fois.
        assert modele == "lfm2.5-2.6b-125k"


class TestQuandOnRetombeSurLeModeJetable:
    """Chaque refus rend ``None`` — et le journalise."""

    def test_prerequis_absents(self, contexte, monkeypatch, caplog):
        registre = _RegistreFactice(Tour(texte="fait", stop="end_turn"))

        reponse = _appel(_executeur(), registre, _Prerequis(False), contexte,
                         monkeypatch)

        assert reponse is None
        assert registre.appels == [], "aucun tour ne doit partir"
        assert "backend éteint" in caplog.text

    def test_harnais_coupe(self, contexte, monkeypatch):
        registre = _RegistreFactice(Tour(texte="fait", stop="end_turn"))
        executeur = RealTaskExecutor(chat=lambda **_: None, harnais_actif=False)

        assert _appel(executeur, registre, _Prerequis(True), contexte,
                      monkeypatch) is None

    def test_sans_mission_ni_workspace(self, monkeypatch):
        registre = _RegistreFactice(Tour(texte="fait", stop="end_turn"))

        assert _appel(_executeur(), registre, _Prerequis(True),
                      {"mission_id": "", "workspace": ""}, monkeypatch) is None

    def test_un_tour_non_abouti_n_est_pas_une_reponse(self, contexte,
                                                      monkeypatch):
        """`end_turn` sans texte, ou du texte sans `end_turn`. Rendre l'un ou
        l'autre ferait passer une session bloquée pour un modèle laconique."""
        registre = _RegistreFactice(Tour(texte="", stop="end_turn"))

        assert _appel(_executeur(), registre, _Prerequis(True), contexte,
                      monkeypatch) is None

    def test_une_session_en_echec_est_fermee(self, contexte, monkeypatch):
        """Une session qui a levé ne doit pas être réutilisée telle quelle
        par la tâche suivante : on la ferme pour qu'elle se rouvre propre."""
        registre = _RegistreFactice(RuntimeError("tube fermé"))

        reponse = _appel(_executeur(), registre, _Prerequis(True), contexte,
                         monkeypatch)

        assert reponse is None
        assert registre.fermetures == ["m-7"]


class TestLeDefautVientDeLEnvironnement:
    """La suite coupe le harnais d'un seul endroit (`conftest.py`) : sans
    cela, un backend qui tourne sur le poste suffit à faire lancer un vrai
    agent par un test unitaire, qui mesure alors la machine."""

    @pytest.mark.parametrize("valeur,attendu", [
        ("0", False), ("false", False), ("non", False), ("off", False),
        ("1", True), ("", True), ("oui", True),
    ])
    def test_lecture(self, monkeypatch, valeur, attendu):
        from backend.execution.task_executor import _harnais_par_defaut

        monkeypatch.setenv("HERMES_HARNAIS", valeur)

        assert _harnais_par_defaut() is attendu

    def test_absent_vaut_actif(self, monkeypatch):
        from backend.execution.task_executor import _harnais_par_defaut

        monkeypatch.delenv("HERMES_HARNAIS", raising=False)

        assert _harnais_par_defaut() is True


class TestLesTagsDeModeleNommesDansLeCode:
    """Un tag mort reste invisible tant que personne ne l'emploie.

    `_HERMES_AGENT_FALLBACK_MODEL` a porte `lfm2.5-2.6b-128k` pendant toute
    la duree du mode jetable — un tag disparu du catalogue lors de la
    refonte HOS-104 a HOS-109, ou le modele a ete renomme en `-125k`. Le
    defaut ne se voyait pas : le mode jetable ne transmettait pas le modele
    a l'agent, qui retombait sur celui de sa propre configuration.

    Des que le harnais a commence a appliquer reellement le modele choisi,
    chaque tour a rendu `HTTP 404: model 'lfm2.5-2.6b-128k' not found`, et
    la mission n'a rien ecrit du tout.

    Ce test ne peut pas interroger Ollama — la suite est hermetique. Il
    verifie ce qu'il peut verifier sans reseau : que la constante s'accorde
    avec le catalogue versionne du depot, seule source de verite hors
    ligne.
    """

    def test_le_modele_de_repli_existe_au_catalogue(self):
        import io

        import yaml

        from backend.execution.task_executor import _HERMES_AGENT_FALLBACK_MODEL

        catalogue = yaml.safe_load(
            io.open("config/models.yaml", encoding="utf-8").read())
        connus = {spec.get("model") for spec in
                  (catalogue.get("roles") or {}).values()}

        assert _HERMES_AGENT_FALLBACK_MODEL in connus, (
            f"{_HERMES_AGENT_FALLBACK_MODEL!r} n'est affecte a aucun role du "
            f"catalogue ; connus : {sorted(c for c in connus if c)}")
