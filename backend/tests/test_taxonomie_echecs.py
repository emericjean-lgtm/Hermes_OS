"""Pourquoi un run a échoué, et ce que ça change (HOS-225).

## L'engagement de HOS-221, tenu ici

HOS-221 a donné onze causes à `registre.Cause` et n'en a renseigné
aucune, en écrivant pourquoi dans le code :

> Deviner maintenant produirait des étiquettes fausses — et une étiquette
> fausse coûte plus cher qu'une case vide, parce qu'on la croit.

La contrainte n'a pas changé. Ce qui change, c'est qu'un classificateur
qui **enregistre son indice** peut être contredit, alors qu'une intuition
ne peut pas l'être. Ces gardes tiennent les deux bouts : il classe quand
un fait le démontre, il dit `INCONNUE` sinon, et l'appelant retombe alors
exactement sur le comportement d'avant.

## Ce que la reprise faisait

`_resolve_model` change de modèle à **toute** reprise, quelle que soit la
cause. C'est le bon remède pour un cas sur onze — et c'est le mauvais
pour un manque de VRAM (il en faut un plus petit), pour une fenêtre de
contexte fermée (changer de modèle ne répare rien) et pour un refus de
politique (il ne faut pas reprendre du tout).
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from backend.config.config_models import DatabaseConfig
from backend.execution.execution_models import ExecutionMeta, TaskExecution
from backend.execution.mission_executor import MissionExecutor
from backend.execution.task_executor import RuntimeUnavailableError
from backend.runs.registre import Cause, Registre
from backend.runs.taxonomie import classer, remede
from backend.storage.database_manager import DatabaseManager


# ═══ Le classement ne se fait que sur des indices ════════════════════

def test_sans_message_la_cause_est_inconnue():
    """`INCONNUE` est un résultat normal, pas un aveu d'échec."""
    classement = classer("")
    assert classement.cause is Cause.INCONNUE
    assert classement.classe is False


def test_un_message_qui_ne_dit_rien_reste_inconnu():
    """La tentation est de classer « une exception Python » quelque part.

    `KeyError: 'x'` ne démontre rien : le ranger sous OUTIL serait une
    étiquette fausse, et une étiquette fausse coûte plus cher qu'une case
    vide.
    """
    assert classer("KeyError: 'x'").cause is Cause.INCONNUE


def test_toute_cause_classee_nomme_son_indice():
    """Sans indice, une classification fausse serait indébogable.

    On ne saurait pas si le tort vient du modèle ou de l'instrument —
    la question qui a coûté le plus cher sur ce projet.
    """
    for message in ("no VRAM admission for 'x' after 120s",
                    "rate limit exceeded", "connection refused"):
        classement = classer(message)
        assert classement.classe, message
        assert classement.indice, message


# ═══ Les vrais messages du dépôt ═════════════════════════════════════

@pytest.mark.parametrize(("message", "attendue"), [
    # `task_executor._attendre_l_admission_vram`
    ("no VRAM admission for 'qwen3.6-35b' (14.2GB requested) after 120s: busy",
     Cause.RESSOURCE),
    # `task_executor`, sur dépassement du budget d'appel
    ("runtime 'ollama' timed out after 900s", Cause.FOURNISSEUR),
    ("Ollama unavailable: ConnectionRefusedError(10061)", Cause.FOURNISSEUR),
    ("runtime 'ollama' returned an empty completion", Cause.MODELE),
    ("could not start the executor event loop", Cause.OUTIL),
    # La phrase du dépôt quand les deux routes ont échoué
    ("cloud runtime failed (X) and the local fallback also failed: Y",
     Cause.FOURNISSEUR),
    # `aegis_engine`
    ("'C:/etc/passwd' is outside ALLOWED_PATHS and outside the project's root",
     Cause.POLITIQUE),
    ("git_critical always requires human validation (§17.3).", Cause.POLITIQUE),
])
def test_les_messages_reels_du_depot_sont_classes(message, attendue):
    """Écrits depuis le code, pas inventés.

    Un classificateur calibré sur des messages imaginaires classe des
    messages imaginaires.
    """
    assert classer(message).cause is attendue


def test_le_catch_all_du_runtime_reste_inconnu():
    """« could not execute task » enveloppe n'importe quoi.

    Le classer donnerait une cause à toutes les erreurs non prévues, ce
    qui est exactement la façon dont une taxonomie devient du bruit.
    """
    assert classer(
        "runtime 'hermes-agent' could not execute task t1: ValueError: bad schema"
    ).cause is Cause.INCONNUE


# ═══ L'ordre de la force de preuve ═══════════════════════════════════

def test_done_reason_length_prime_sur_tout():
    """L'indice le plus fort du lot : il vient du runtime, pas d'ici.

    CLAUDE.md : « une réponse tronquée n'est pas une erreur de
    raisonnement et ne doit pas se noter comme telle ». Le départage de
    code a coupé qwen3.6-35b en plein milieu pour cette raison, et l'a
    noté comme une faute.
    """
    classement = classer("returned an empty completion", done_reason="length")
    assert classement.cause is Cause.CONTEXTE


def test_un_code_http_prime_sur_le_texte():
    """Un code est un fait ; un message est une rédaction."""
    assert classer("timed out", statut_http=429).cause is Cause.QUOTA


def test_http_400_est_un_defaut_d_ici_pas_du_modele():
    """L'incident du catalogue : « 0 s par tentative ».

    C'était un HTTP 400 jamais regardé, et il s'était rangé sous « le
    modèle ne sait pas faire ».
    """
    assert classer("", statut_http=400).cause is Cause.OUTIL


def test_un_manque_de_vram_prime_sur_le_delai_depasse():
    """Les deux mots apparaissent dans le même message.

    « no VRAM admission ... after 120s » : dire « délai dépassé » ferait
    changer de fournisseur là où il faut un modèle plus petit.
    """
    assert classer("no VRAM admission for 'x' after 120s: resident model holds "
                   "9.6GB").cause is Cause.RESSOURCE


# ═══ Les remèdes, et ce qui les distingue ════════════════════════════

def test_le_manque_de_vram_demande_un_modele_plus_petit():
    """Pas « un autre modèle » : un autre de même taille échoue pareil.

    Deux leviers distincts parce que ce sont deux demandes distinctes.
    """
    soin = remede(Cause.RESSOURCE)
    assert soin.reduire_le_modele is True
    assert soin.changer_de_modele is False
    assert soin.attendre_s > 0


def test_une_fenetre_fermee_ne_se_repare_pas_en_changeant_de_modele():
    soin = remede(Cause.CONTEXTE)
    assert soin.elargir_le_contexte is True
    assert soin.changer_de_modele is False


def test_un_quota_ne_se_reessaie_pas_tout_de_suite():
    """Réessayer chez le même fournisseur échoue par construction."""
    soin = remede(Cause.QUOTA)
    assert soin.changer_de_fournisseur is True
    assert soin.attendre_s >= 60


def test_le_modele_est_le_seul_cas_ou_on_change_de_modele():
    """Ce que le code faisait à *toutes* les reprises."""
    changent = [c for c in Cause if remede(c).changer_de_modele]
    assert changent == [Cause.MODELE]


@pytest.mark.parametrize("cause", [Cause.POLITIQUE, Cause.SECURITE])
def test_un_refus_ne_se_reprend_pas(cause):
    """Une boucle de reprise sur un refus inonde la file d'approbation.

    `approvals.py` décrit déjà ce que produit l'autre choix : « an agent
    retrying in a loop after a refusal will re-ask ». La reprise
    légitime viendra de l'accord humain, pas de la boucle.
    """
    assert remede(cause).reessayer is False


def test_une_cause_inconnue_reprend_sans_rien_changer():
    """Le comportement prudent, et celui d'avant ce jalon."""
    soin = remede(Cause.INCONNUE)
    assert soin.reessayer is True
    assert not any((soin.changer_de_modele, soin.reduire_le_modele,
                    soin.elargir_le_contexte, soin.changer_de_fournisseur))


def test_toute_cause_a_un_remede_et_une_explication():
    """Un remède muet ne fait pas agir."""
    for cause in Cause:
        assert remede(cause).explication.strip(), cause


def test_la_taxonomie_ne_plafonne_pas_les_tentatives():
    """Elle dit **si** on reprend, pas combien de fois.

    Une première version portait un plafond par cause, à 2 par défaut :
    il rétrécissait silencieusement le budget configuré dans
    `max_retries_per_task`, et un test existant l'a dit tout de suite.
    Aucune mesure ne dit qu'un manque de VRAM mérite moins de tentatives
    qu'un échec quelconque.
    """
    assert not hasattr(remede(Cause.RESSOURCE), "plafond")


def test_remede_ne_leve_jamais():
    """Il est consulté sur le chemin d'un échec.

    Y lever transformerait un échec diagnosticable en échec muet.
    """
    assert remede("une chaîne qui n'est pas une cause").reessayer is True


# ═══ Le branchement : le registre ════════════════════════════════════

class _Echoue:
    def __init__(self, message: str) -> None:
        self.message = message

    def execute(self, task, assignment=None, **_):
        raise RuntimeUnavailableError(self.message)


@pytest.fixture
def registre(tmp_path: Path) -> Registre:
    return Registre(DatabaseManager(DatabaseConfig(name=str(tmp_path / "runs"))))


def _echouer(registre, message, *, reprises=3):
    evenements: list[tuple[str, dict]] = []
    moteur = MissionExecutor(
        task_executor=_Echoue(message), registre=registre,
        on_event=lambda t, d, **k: evenements.append((t, d)))
    meta = ExecutionMeta(mission_id="m", user_goal="o",
                         max_retries_per_task=reprises)
    sm = moteur.prepare(meta, [TaskExecution(task_id="t1", mission_id="m")])
    identifiant = moteur.run_de(meta.execution_id)
    moteur.execute_task(sm, "t1")
    moteur.finalize(sm)
    return registre.lire(identifiant), evenements


def _evenement(evenements, type_):
    return next((d for t, d in evenements if t == type_ and "cause" in d), None)


def test_la_cause_arrive_au_registre(registre):
    """La case que HOS-221 laissait vide, remplie quand un fait la porte."""
    run, _ = _echouer(registre, "no VRAM admission for 'x' after 120s")
    assert run.cause is Cause.RESSOURCE


def test_une_cause_inconnue_laisse_la_colonne_vide(registre):
    """`None` se lit « on ne sait pas ».

    Une étiquette « inconnue » en base se lirait comme un diagnostic
    posé, ce qui est faux et pire que rien.
    """
    run, _ = _echouer(registre, "KeyError: 'x'")
    assert run.cause is None


def test_la_raison_brute_survit_au_classement(registre):
    """Le classement est une lecture, jamais un remplacement."""
    run, _ = _echouer(registre, "no VRAM admission for 'x' after 120s")
    assert "no VRAM admission" in run.raison


# ═══ Le branchement : la reprise ═════════════════════════════════════

def test_une_reprise_porte_son_remede(registre):
    run, evenements = _echouer(
        registre, "no VRAM admission for 'x' (14GB requested) after 120s")
    reprise = _evenement(evenements, "execution.retry")
    assert reprise is not None
    assert reprise["cause"] == "ressource"
    assert reprise["reduire_le_modele"] is True
    assert reprise["changer_de_modele"] is False
    assert reprise["indice"]


def test_un_refus_de_politique_n_est_pas_repris(registre):
    run, evenements = _echouer(
        registre, "'C:/etc/passwd' is outside ALLOWED_PATHS")
    assert _evenement(evenements, "execution.retry") is None
    abandon = _evenement(evenements, "execution.failed")
    assert abandon["abandon"] == "cause non reprenable"


def test_l_abandon_distingue_le_plafond_du_refus(registre):
    """« Plafond atteint » et « on ne doit pas » sont deux choses.

    Les confondre ferait chercher un défaut de compteur là où il y a un
    refus assumé.
    """
    _, evenements = _echouer(registre, "KeyError: 'x'", reprises=0)
    abandon = _evenement(evenements, "execution.failed")
    assert abandon["abandon"] == "plafond de tentatives atteint"


def test_le_budget_de_la_mission_prime(registre):
    """Un `max_retries_per_task` à 0 reste zéro reprise.

    Le diagnostic ne doit pouvoir ni élargir ni rétrécir un budget que
    quelqu'un a décidé — le rétrécir était le défaut de ma première
    version, et un test existant l'a dit.
    """
    _, evenements = _echouer(registre, "no VRAM admission for 'x'", reprises=0)
    assert _evenement(evenements, "execution.retry") is None


def test_une_cause_inconnue_reprend_comme_avant(registre):
    """La réparation ne doit pas rendre le système plus timide.

    Sans indice, on retombe exactement sur le comportement d'avant ce
    jalon : reprendre une fois, sans rien changer qu'on ne saurait
    justifier.
    """
    _, evenements = _echouer(registre, "KeyError: 'x'")
    reprise = _evenement(evenements, "execution.retry")
    assert reprise is not None
    assert reprise["cause"] == "inconnue"
    assert not reprise["changer_de_modele"]
    assert not reprise["reduire_le_modele"]
