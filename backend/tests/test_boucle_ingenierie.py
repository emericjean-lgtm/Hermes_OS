"""La boucle : exécuter, vérifier, diagnostiquer, réparer (HOS-230).

## Ce qui existait, mesuré avant d'écrire

Deux pilotes de reprise, et aucun ne connaît de contrat :

- `node_execution` fait tourner un `while task.status == PENDING`. Il
  reprend les **pannes de runtime** et ne sait rien de ce qui devait être
  vrai à la fin.
- `retry_policy.decide` travaille au niveau de la mission, uniquement sur
  contradiction, et `graph_executor._suggest_retry` **publie** au lieu de
  relancer — avec sa raison, qui est juste.

Ce module n'annule pas ce choix : la boucle est une bibliothèque que
l'appelant pilote, jamais un relanceur caché.

## Et ce n'est pas une seconde boucle agentique

La règle qui prime sur tout : Hermes Agent est le cerveau. Cette
boucle-ci ne raisonne pas, ne choisit aucun outil et n'appelle aucun
modèle — elle enchaîne deux fonctions que l'appelant lui donne et décide
de continuer ou non, sur des verdicts et des causes mesurés ailleurs.
"""

from __future__ import annotations

import pytest

from backend.mission.boucle import Arret, Boucle, TOURS_PAR_DEFAUT
from backend.mission.relais import Phase, Relais
from backend.runs.contrat import Contrat, Critere, Verdict


def _relais() -> Relais:
    return Relais(mission="lune", run="r1", objectif="produire la vidéo",
                  contrat=Contrat(objectif="produire la vidéo", criteres=[
                      Critere("le fichier existe", verificateur="disque")]))


def _tenir(relais: Relais) -> None:
    """Poser le verdict qui satisfait le contrat."""
    contrat = relais.contrat
    assert contrat is not None
    contrat.enregistrer(contrat.criteres[0].identifiant, Verdict.REUSSI)


# ═══ Les six arrêts, et pourquoi ils ne se confondent pas ════════════

def test_le_contrat_tenu_arrete_la_boucle():
    tours = {"n": 0}

    def executer(relais, phase):
        tours["n"] += 1

    def verifier(relais):
        if tours["n"] >= 2:
            _tenir(relais)
            return Verdict.REUSSI
        return Verdict.ECHOUE

    issue = Boucle(executer, verifier, tours=5).tourner(_relais())
    assert issue.arret is Arret.CONTRAT_TENU
    assert issue.tenu is True
    assert issue.tours_faits == 2, "elle a continué après avoir réussi"


def test_un_verdict_reussi_ne_suffit_pas_si_le_contrat_ne_l_est_pas():
    """La conjonction du contrat prime sur le verdict du vérificateur.

    Un vérificateur qui dirait « réussi » sur un contrat à trois critères
    dont un seul est tenu clôturerait une mission inachevée.
    """
    relais = Relais(mission="m", contrat=Contrat(objectif="o", criteres=[
        Critere("a", verificateur="d"), Critere("b", verificateur="d")]))
    relais.contrat.enregistrer(relais.contrat.criteres[0].identifiant,
                               Verdict.REUSSI)

    issue = Boucle(lambda r, p: None, lambda r: Verdict.REUSSI,
                   tours=1).tourner(relais)
    assert issue.tenu is False
    assert issue.arret is Arret.BUDGET


def test_le_budget_s_epuise_sans_declarer_de_succes():
    issue = Boucle(lambda r, p: None, lambda r: Verdict.ECHOUE,
                   tours=2).tourner(_relais())
    assert issue.arret is Arret.BUDGET
    assert issue.tenu is False
    assert issue.tours_faits == 2


def test_un_inverifiable_arrete_sans_user_le_budget():
    """HOS-222 : on ne reprend pas sur une ignorance.

    Et surtout on ne la range pas du côté du succès. Boucler ici userait
    le budget à re-produire une mesure qui n'aboutit pas.
    """
    issue = Boucle(lambda r, p: None, lambda r: Verdict.INDISPONIBLE,
                   tours=5).tourner(_relais())
    assert issue.arret is Arret.INVERIFIABLE
    assert issue.tenu is False
    assert issue.tours_faits == 1


def test_une_cause_non_reprenable_arrete_tout_de_suite():
    """Réessayer un refus de politique inonde la file d'approbation.

    C'est ce que `approvals.py` décrit déjà : « an agent retrying in a
    loop after a refusal will re-ask ».
    """
    def refuse(relais, phase):
        raise RuntimeError("'C:/etc/passwd' is outside ALLOWED_PATHS")

    issue = Boucle(refuse, lambda r: Verdict.ECHOUE, tours=5).tourner(_relais())
    assert issue.arret is Arret.CAUSE_NON_REPRENABLE
    assert issue.tours_faits == 1, "le budget a été brûlé sur un refus"


def test_une_cause_reprenable_continue_jusqu_au_budget():
    def rate(relais, phase):
        raise RuntimeError("runtime 'ollama' timed out after 900s")

    issue = Boucle(rate, lambda r: Verdict.ECHOUE, tours=3).tourner(_relais())
    assert issue.arret is Arret.BUDGET
    assert issue.tours_faits == 3


def test_sans_contrat_la_boucle_ne_tourne_pas():
    """Boucler sur rien produirait des tours qui se déclareraient
    réussis parce qu'aucun critère ne les contredit.

    C'est le `success: true` au-dessus de rien, en boucle.
    """
    issue = Boucle(lambda r, p: None, lambda r: Verdict.REUSSI).tourner(
        Relais(mission="m"))
    assert issue.arret is Arret.SANS_CONTRAT
    assert issue.tenu is False


def test_les_six_arrets_sont_distincts():
    """Les fondre en un booléen ferait chercher un défaut de budget là où
    il y a un refus assumé — l'erreur que HOS-225 a déjà eu à corriger."""
    assert len(set(Arret)) == 6


# ═══ Les phases, et ce que la réparation reçoit ══════════════════════

def test_le_premier_tour_est_une_execution_les_suivants_des_reparations():
    phases: list[Phase] = []
    issue = Boucle(lambda r, p: phases.append(p), lambda r: Verdict.ECHOUE,
                   tours=3).tourner(_relais())
    assert phases == [Phase.EXECUTION, Phase.REPARATION, Phase.REPARATION]
    assert issue.arret is Arret.BUDGET


def test_l_echec_et_sa_cause_arrivent_au_relais():
    """Sans quoi la réparation rejouerait le même prompt.

    C'est la moitié utile de `retry_policy` : rendre des preuves, pas
    relancer à l'identique (HOS-229).
    """
    relais = _relais()

    def rate(r, phase):
        raise RuntimeError("runtime 'ollama' timed out after 900s")

    Boucle(rate, lambda r: Verdict.ECHOUE, tours=2).tourner(relais)
    assert "timed out" in relais.echec
    assert relais.cause == "fournisseur"
    assert "timed out" in relais.pour(Phase.REPARATION)


def test_les_constats_de_verification_nourrissent_le_relais():
    class _Verification:
        verdict = Verdict.ECHOUE

        @staticmethod
        def resume():
            return "aucun fichier créé, modifié ou supprimé"

    relais = _relais()
    Boucle(lambda r, p: None, lambda r: _Verification(), tours=2).tourner(relais)
    assert any("aucun fichier" in p.constat for p in relais.preuves)


# ═══ La lecture du verdict ═══════════════════════════════════════════

def test_une_verification_illisible_vaut_inverifiable():
    """Jamais `REUSSI` par défaut d'information.

    Une vérification dont on ne sait pas lire le verdict est une
    vérification qu'on n'a pas.
    """
    issue = Boucle(lambda r, p: None, lambda r: object(),
                   tours=2).tourner(_relais())
    assert issue.arret is Arret.INVERIFIABLE


def test_un_objet_de_verification_porte_son_verdict():
    """Le vrai `MissionVerification` de HOS-222 en expose un."""
    class _Verification:
        verdict = Verdict.INDISPONIBLE

    issue = Boucle(lambda r, p: None, lambda r: _Verification(),
                   tours=2).tourner(_relais())
    assert issue.arret is Arret.INVERIFIABLE


def test_le_verdict_accepte_aussi_une_chaine():
    relais = _relais()

    def verifier(r):
        _tenir(r)
        return "reussi"

    assert Boucle(lambda r, p: None, verifier, tours=1).tourner(relais).tenu


# ═══ Le point de reprise : proposé, jamais appliqué ══════════════════

def test_le_point_de_reprise_est_pris_avant_le_premier_tour():
    pris: list[str] = []

    def filet(relais):
        pris.append(relais.mission)
        return "cp-1"

    issue = Boucle(lambda r, p: None, lambda r: Verdict.ECHOUE, tours=2,
                   point_de_reprise=filet).tourner(_relais())
    assert pris == ["lune"], "pris une fois par tour au lieu d'une fois"
    assert issue.checkpoint == "cp-1"


def test_la_boucle_ne_restaure_jamais_d_elle_meme():
    """Elle propose l'identifiant, l'appelant décide, et la restauration
    passe par Aegis (HOS-223).

    Une boucle qui effacerait un workspace de son propre chef serait le
    geste destructeur le moins surveillé du système.
    """
    import ast
    import inspect
    import textwrap

    from backend.mission import boucle

    source = textwrap.dedent(inspect.getsource(boucle.Boucle))
    appels = {ast.unparse(n.func) for n in ast.walk(ast.parse(source))
              if isinstance(n, ast.Call)}
    assert not any("restaur" in a for a in appels), appels


def test_un_point_de_reprise_impossible_ne_casse_pas_la_boucle():
    """L'utilisateur a demandé un travail, pas une sauvegarde.

    Même règle que `graph_executor._prendre_le_filet` (HOS-223).
    """
    def casse(relais):
        raise RuntimeError("disque plein")

    issue = Boucle(lambda r, p: None, lambda r: Verdict.ECHOUE, tours=1,
                   point_de_reprise=casse).tourner(_relais())
    assert issue.arret is Arret.BUDGET
    assert issue.checkpoint == ""


# ═══ Ce que la boucle n'est pas ══════════════════════════════════════

def test_la_boucle_n_appelle_aucun_modele():
    """La règle qui prime sur tout : Hermes Agent est le cerveau.

    Elle a déjà été violée une fois — `RealTaskExecutor` sélectionnait
    l'agent puis l'écrasait deux lignes plus bas par sa propre boucle
    d'outils. Cette boucle-ci enchaîne deux fonctions que l'appelant lui
    donne ; elle ne raisonne pas, ne choisit aucun outil, et n'importe ni
    client ni runtime.
    """
    import ast
    import inspect

    from backend.mission import boucle

    arbre = ast.parse(inspect.getsource(boucle))
    modules = {n.module for n in ast.walk(arbre)
               if isinstance(n, ast.ImportFrom) and n.module}
    interdits = [m for m in modules
                 if any(mot in m for mot in ("connectors", "ral.adapters",
                                             "ollama", "openrouter"))]
    assert not interdits, (
        f"la boucle importe {interdits} — elle ne doit appeler aucun "
        "modèle : c'est de l'ordonnancement, pas de la cognition")


def test_le_budget_par_defaut_est_celui_de_retry_policy():
    """Sur ce déploiement une passe coûte des minutes d'inférence locale,
    et un modèle qui échoue deux fois sur les mêmes preuves ne réussira
    pas à la cinquième."""
    from backend.mission.retry_policy import DEFAULT_MAX_ATTEMPTS

    assert TOURS_PAR_DEFAUT == DEFAULT_MAX_ATTEMPTS


def test_les_evenements_de_boucle_sont_declares():
    from backend.core.bootstrap.event_wiring import collect_known_topics
    from backend.core.event_topics import BASELINE_TOPICS

    connus = collect_known_topics()
    for topic in ("boucle.tour", "boucle.arret"):
        assert topic in BASELINE_TOPICS, topic
        assert topic in connus, topic
