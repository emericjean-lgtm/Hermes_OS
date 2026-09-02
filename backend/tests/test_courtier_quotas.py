"""Quel fournisseur appeler, et lequel laisser tranquille (HOS-228).

## La cinquième prémisse fausse

La roadmap annonçait « le disjoncteur de `task_executor` et la santé de
runtime sont réels et branchés » — une ligne que j'avais moi-même
corrigée deux jalons plus tôt. Mesuré :

- `RealTaskExecutor._record_failure` incrémente `self._failures`, **lu
  une seule fois**, pour une ligne de statistiques. Rien n'ouvre de
  circuit. C'est un compteur.
- `RecoveryManager` a une vraie logique de cooldown et **n'est
  instancié nulle part** hors des tests. Cinquième orphelin.
- `has_quota`, lui, **est** consommé par `AdaptiveRouter`. Cette partie
  du diagnostic était juste.

## Le cycle que ces gardes tiennent

    429 → QUOTA → fournisseur B          et non
    429 → même fournisseur → 429 → …
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from backend.ral import courtier as module_courtier
from backend.ral import fournisseurs as registre_cloud
from backend.ral.adapters.openrouter import RuntimeOpenRouter
from backend.ral.capabilities import EtatDuQuota
from backend.ral.courtier import (
    ECARTS,
    OUVERTURE_S,
    SEUIL_DISJONCTEUR,
    Courtier,
    Etat,
)
from backend.runs.registre import Cause


@pytest.fixture
def horloge():
    """Une horloge qu'on avance à la main.

    Une garde qui dormirait deux minutes pour vérifier une ouverture de
    circuit n'est pas une garde qu'on exécute.
    """
    return [0.0]


@pytest.fixture
def courtier(horloge) -> Courtier:
    return Courtier(horloge=lambda: horloge[0])


@pytest.fixture(autouse=True)
def etat_propre():
    registre_cloud.reinitialiser()
    module_courtier.reinitialiser()
    yield
    registre_cloud.reinitialiser()
    module_courtier.reinitialiser()


# ═══ Les causes qui écartent, et celles qui n'écartent pas ═══════════

def test_un_quota_ecarte_le_fournisseur(courtier):
    """Le pool gratuit est partagé par clé et se réarme à la minute.

    Réessayer dans la seconde est garanti d'échouer.
    """
    courtier.signaler_echec("openrouter", Cause.QUOTA)
    verdict = courtier.examiner("openrouter")
    assert verdict.etat is Etat.ECARTE
    assert verdict.dans_s == pytest.approx(ECARTS[Cause.QUOTA])
    assert verdict.candidat is False


def test_l_ecart_expire(courtier, horloge):
    courtier.signaler_echec("openrouter", Cause.QUOTA)
    horloge[0] = ECARTS[Cause.QUOTA] + 1
    assert courtier.examiner("openrouter").etat is Etat.DISPONIBLE


@pytest.mark.parametrize("cause", [
    Cause.MODELE, Cause.SEMANTIQUE, Cause.VERIFICATION,
    Cause.POLITIQUE, Cause.SECURITE, Cause.CONTEXTE, Cause.OUTIL,
    Cause.INCONNUE, None,
])
def test_une_cause_non_imputable_ne_touche_pas_au_fournisseur(courtier, cause):
    """Un modèle qui rend une sortie inutilisable ne dit rien de la santé
    d'OpenRouter.

    L'écarter pour ça le retirerait du jeu pour une raison qui ne le
    concerne pas — et ferait basculer sur le local une charge que le
    cloud servait très bien.
    """
    for _ in range(SEUIL_DISJONCTEUR + 2):
        courtier.signaler_echec("openrouter", cause)
    assert courtier.examiner("openrouter").etat is Etat.DISPONIBLE


def test_les_causes_ecartantes_sont_une_liste_courte():
    """Une table qui écarterait sur tout ferait basculer sur le local au
    premier ennui, pour n'importe quelle raison."""
    assert set(ECARTS) == {Cause.QUOTA, Cause.FOURNISSEUR, Cause.RESSOURCE}


# ═══ Le disjoncteur ══════════════════════════════════════════════════

def test_trois_echecs_consecutifs_ouvrent_le_circuit(courtier):
    """Un incident isolé est un incident, deux peuvent être une
    coïncidence, trois sont un motif."""
    for _ in range(SEUIL_DISJONCTEUR - 1):
        courtier.signaler_echec("openrouter", Cause.FOURNISSEUR)
    assert courtier.examiner("openrouter").etat is Etat.ECARTE

    courtier.signaler_echec("openrouter", Cause.FOURNISSEUR)
    verdict = courtier.examiner("openrouter")
    assert verdict.etat is Etat.OUVERT
    assert verdict.dans_s == pytest.approx(OUVERTURE_S)


def test_un_succes_referme_le_circuit(courtier):
    """Sans ça, un incident passager tue le fournisseur jusqu'au
    redémarrage — ce qui ressemble exactement à un fournisseur en panne,
    et se débogue mal."""
    for _ in range(SEUIL_DISJONCTEUR):
        courtier.signaler_echec("openrouter", Cause.FOURNISSEUR)
    assert courtier.examiner("openrouter").etat is Etat.OUVERT

    courtier.signaler_succes("openrouter")
    assert courtier.examiner("openrouter").etat is Etat.DISPONIBLE


def test_un_succes_remet_le_compteur_a_zero(courtier):
    """Deux échecs, un succès, deux échecs : le circuit ne doit pas
    s'ouvrir — sinon il compte des échecs séparés par des réussites."""
    for _ in range(SEUIL_DISJONCTEUR - 1):
        courtier.signaler_echec("openrouter", Cause.FOURNISSEUR)
    courtier.signaler_succes("openrouter")
    for _ in range(SEUIL_DISJONCTEUR - 1):
        courtier.signaler_echec("openrouter", Cause.FOURNISSEUR)
    assert courtier.examiner("openrouter").etat is not Etat.OUVERT


def test_le_circuit_se_referme_de_lui_meme(courtier, horloge):
    for _ in range(SEUIL_DISJONCTEUR):
        courtier.signaler_echec("openrouter", Cause.FOURNISSEUR)
    horloge[0] = OUVERTURE_S + 1
    assert courtier.examiner("openrouter").etat is Etat.DISPONIBLE


# ═══ Le quota ════════════════════════════════════════════════════════

def test_un_quota_non_mesurable_ecarte(courtier):
    """On ne dépense pas sur une mesure qu'on n'a pas.

    HOS-222 appliqué à une ressource payante, et le même choix que
    `EtatDuQuota.inconnu`.
    """
    courtier.noter_le_quota("openrouter",
                            EtatDuQuota.inconnu("openrouter", "/key : 500"))
    verdict = courtier.examiner("openrouter")
    assert verdict.etat is Etat.SANS_QUOTA
    assert "500" in verdict.raison


def test_un_quota_utilisable_laisse_passer(courtier):
    courtier.noter_le_quota("openrouter",
                            EtatDuQuota("openrouter", utilisable=True, restant=9))
    assert courtier.examiner("openrouter").etat is Etat.DISPONIBLE


def test_un_quota_perime_n_ecarte_plus(courtier, horloge):
    """Une mesure d'il y a dix minutes ne dit rien de maintenant.

    S'y fier écarterait un fournisseur dont le quota s'est réarmé
    entre-temps — et le pool gratuit se réarme à la minute.
    """
    courtier.noter_le_quota("openrouter", EtatDuQuota.inconnu("openrouter"))
    horloge[0] = 3600
    assert courtier.examiner("openrouter").etat is Etat.DISPONIBLE


# ═══ Le choix ════════════════════════════════════════════════════════

def test_choisir_saute_celui_qui_vient_de_rendre_un_429(courtier):
    """Le cycle du cahier, en une ligne."""
    courtier.signaler_echec("a", Cause.QUOTA)
    assert courtier.choisir(["a", "b"]) == "b"


def test_choisir_respecte_l_ordre_donne(courtier):
    """L'ordre vient de l'appelant — le routeur, qui sait ce que la tâche
    demande. Le courtier ne classe pas, il écarte."""
    assert courtier.choisir(["a", "b"]) == "a"


def test_choisir_rend_none_quand_tout_est_ecarte(courtier):
    """`None` plutôt qu'une exception.

    « Aucun fournisseur distant disponible » est un état normal — c'est
    même le cas le plus fréquent, aucune clé n'étant configurée par
    défaut. Lever ferait échouer une mission qui devait rester locale.
    """
    courtier.signaler_echec("a", Cause.QUOTA)
    assert courtier.choisir(["a"]) is None


def test_un_fournisseur_inconnu_est_disponible(courtier):
    """L'absence de fiche n'est pas une absence de fournisseur."""
    assert courtier.examiner("jamais-vu").etat is Etat.DISPONIBLE


def test_les_etats_sont_lisibles_pour_l_audit(courtier):
    courtier.signaler_echec("a", Cause.QUOTA)
    etats = courtier.etats()
    assert etats["a"].etat is Etat.ECARTE
    assert etats["a"].raison


# ═══ Le branchement, de bout en bout ═════════════════════════════════

def _fournisseur_429() -> tuple[RuntimeOpenRouter, dict]:
    compteur = {"appels": 0}

    def repond(requete: httpx.Request) -> httpx.Response:
        compteur["appels"] += 1
        return httpx.Response(429, json={"error": {"message": "rate limit exceeded"}})

    return (RuntimeOpenRouter("cle", transport=httpx.MockTransport(repond)),
            compteur)


def test_un_429_n_est_pas_rejoue_sur_le_meme_fournisseur():
    """Le défaut que ce jalon existe pour supprimer.

    Sans courtier, le second appel repartait chez le fournisseur qui
    venait de dire non — et rendait le même 429.
    """
    from backend.core.bootstrap.service_registry import _make_cloud_chat

    fournisseur, compteur = _fournisseur_429()
    registre_cloud.enregistrer(fournisseur)
    chat = _make_cloud_chat()

    async def deux_essais():
        resultats = []
        for _ in range(2):
            try:
                await chat(messages=[{"role": "user", "content": "x"}], model="m")
                resultats.append("reussi")
            except Exception as exc:
                resultats.append(type(exc).__name__)
        return resultats

    resultats = asyncio.run(deux_essais())
    assert resultats[0] == "QuotaEpuise"
    assert resultats[1] == "FournisseurIndisponible"
    assert compteur["appels"] == 1, (
        "le second appel est parti quand même — le courtier n'écarte pas")


def test_un_succes_signale_le_retablissement():
    from backend.core.bootstrap.service_registry import _make_cloud_chat

    registre_cloud.enregistrer(RuntimeOpenRouter("cle", transport=httpx.MockTransport(
        lambda r: httpx.Response(200, json={
            "choices": [{"message": {"content": "ok"}}]}))))
    chat = _make_cloud_chat()

    reponse = asyncio.run(chat(messages=[{"role": "user", "content": "x"}],
                               model="m"))
    assert reponse.content == "ok"
    assert module_courtier.courtier().examiner("openrouter").etat is Etat.DISPONIBLE


def test_le_goulet_consulte_le_courtier_avant_d_appeler():
    """Garde sur l'arbre syntaxique, comme celles de HOS-227.

    Une consultation *après* l'appel ne servirait à rien : le 429 serait
    déjà parti.
    """
    import ast
    import inspect
    import textwrap

    from backend.core.bootstrap import service_registry

    source = textwrap.dedent(inspect.getsource(service_registry._make_cloud_chat))
    interne = next(n for n in ast.walk(ast.parse(source))
                   if isinstance(n, ast.AsyncFunctionDef))
    noms = [ast.unparse(n.func) for n in ast.walk(interne)
            if isinstance(n, ast.Call)]
    choix = next(i for i, n in enumerate(noms) if n.endswith("choisir"))
    envoi = next(i for i, n in enumerate(noms) if n.endswith("provider.chat"))
    assert choix < envoi


def test_les_evenements_du_courtier_sont_declares():
    """Écart **et** rétablissement.

    Un écart sans rétablissement visible ressemble à une panne
    définitive.
    """
    from backend.core.bootstrap.event_wiring import collect_known_topics
    from backend.core.event_topics import BASELINE_TOPICS

    connus = collect_known_topics()
    for topic in ("cloud.fournisseur_ecarte", "cloud.fournisseur_retabli"):
        assert topic in BASELINE_TOPICS, topic
        assert topic in connus, (
            f"{topic} absent de collect_known_topics() — la liste blanche "
            "s'assemble depuis les catalogues déclarés à côté des "
            "producteurs, pas depuis BASELINE_TOPICS (leçon HOS-227)")


# ═══ Ce qui n'a délibérément pas été réutilisé ═══════════════════════

def test_recovery_manager_reste_orphelin():
    """Il **exécute une reprise** sur un composant ; un courtier
    **s'abstient de choisir** un fournisseur.

    Deux verbes différents : le réutiliser demanderait d'enregistrer une
    action de reprise vide pour n'en garder que la comptabilité de
    cooldown, c'est-à-dire de le plier jusqu'à ce qu'il ne dise plus ce
    qu'il dit.

    Ce test tombe le jour où quelqu'un le rebranche — et c'est le moment
    de relire ce raisonnement plutôt que de le contourner.
    """
    import io
    from pathlib import Path

    racine = Path(__file__).resolve().parents[2]
    appelants = []
    for fichier in (racine / "backend").rglob("*.py"):
        if "tests" in fichier.parts or fichier.name == "recovery_manager.py":
            continue
        texte = io.open(fichier, encoding="utf-8", errors="replace").read()
        if "RecoveryManager(" in texte:
            appelants.append(str(fichier.relative_to(racine)))
    assert not appelants, appelants
