"""Un test de la boucle courte ne parle a aucun service reel (HOS-112).

`VISION.md` l'affirme depuis le debut — « *Tests without network: every
module is testable with in-memory stubs. No real backend required* » —
mais rien ne le verifiait, et plusieurs tests s'en etaient affranchis sans
que personne le voie : ils n'echouaient pas, ils **pendaient**. Deux
executions de la suite se sont figees 92 et 15 minutes en attendant une
inference qui n'est jamais revenue.

Un principe que rien ne fait respecter finit par decrire le passe. Celui-ci
est desormais tenu par le code.

Ce qui reste autorise : les sockets de boucle locale vers des ports
ephemeres, dont asyncio a besoin pour son tuyau interne sous Windows. Les
tests hermetiques de ce depot passent par `httpx.ASGITransport` ou
`TestClient`, qui n'ouvrent aucune socket vers l'exterieur — la garde ne
leur coute donc rien.

Les tests marques `lent` en sont **exemptes** : leur raison d'etre est
justement d'exercer une vraie inference (voir `tests/integration/`).

## Pourquoi la garde est posee une seule fois, et non par test

Une premiere version utilisait un `monkeypatch` dans une fixture autouse,
donc retabli au demontage de chaque test. C'etait un trou : **un fil
fuite par un test survit a ce retablissement**. Un test de mission laisse
derriere lui un `ThreadPoolExecutor` qui continue d'executer des noeuds ;
libere de la garde, ce fil atteint Ollama et bloque un test tout autre,
des centaines de tests plus loin.

Le symptome etait deroutant : la pile videe au depassement montrait
`task_executor` et le pipeline de missions pendant que le test courant
etait `test_search_by_importance`, une recherche en memoire. Les deux ne
se recoupaient pas — parce que la pile n'etait pas celle du test courant,
mais celle du fil fuite.

La garde est donc installee une fois pour la session et n'est jamais
retiree ; seule son application est suspendue pendant un test `lent`.
"""
from __future__ import annotations

import os
import socket
import tempfile

import pytest

#: Ollama et Alexandrie — les deux services que ce depot appelle pour de
#: vrai. Nommer les ports plutot que bloquer toute la boucle locale laisse
#: passer le tuyau interne d'asyncio, qui utilise lui aussi 127.0.0.1.
PORTS_SERVICE = {11434, 8200}

BOUCLE_LOCALE = {"127.0.0.1", "::1", "localhost", ""}

#: Suspendue pendant un test `lent`, jamais desinstallee. Une liste plutot
#: qu'un booleen global pour rester lisible depuis les fermetures ci-dessous.
_applique = [True]


class AppelReseauInterdit(RuntimeError):
    """Ce test ouvre une vraie connexion : il n'est donc pas hermetique.

    Le doubler, ou le marquer `lent` s'il doit vraiment atteindre un
    service. Ne pas retirer la garde — c'est elle qui a rendu visible un
    defaut reste invisible pendant des semaines.
    """


def _verifier(adresse: object) -> None:
    if not _applique[0] or not isinstance(adresse, tuple) or len(adresse) < 2:
        return
    hote, port = adresse[0], adresse[1]
    if port in PORTS_SERVICE:
        raise AppelReseauInterdit(
            f"appel a un service reel ({hote}:{port}) depuis la boucle courte. "
            "Poser une doublure, ou marquer ce test `lent`."
        )
    if hote not in BOUCLE_LOCALE:
        raise AppelReseauInterdit(
            f"appel sortant vers {hote}:{port} depuis la boucle courte. "
            "Poser une doublure, ou marquer ce test `lent`."
        )


_connect = socket.socket.connect
_connect_ex = socket.socket.connect_ex


def _connect_garde(self, adresse):
    _verifier(adresse)
    return _connect(self, adresse)


def _connect_ex_garde(self, adresse):
    _verifier(adresse)
    return _connect_ex(self, adresse)


socket.socket.connect = _connect_garde
socket.socket.connect_ex = _connect_ex_garde


@pytest.fixture(autouse=True)
def _suspendre_pour_les_lents(request: pytest.FixtureRequest):
    lent = request.node.get_closest_marker("lent") is not None
    if not lent:
        yield
        return
    _applique[0] = False
    try:
        yield
    finally:
        _applique[0] = True


# ── Le reglage d'exploitation ne decide pas du verdict des tests (HOS-124) ──
#
# Mesure du 2026-08-16 : passer le niveau d'autonomie a `high` — un acte
# d'exploitation legitime, prevu par `backend/security/autonomy.py` — a fait
# echouer **onze tests** repartis sur cinq fichiers. Leurs noms disent
# pourtant ce qu'ils verifient : `test_shipped_policy_requires_validation_
# at_default_autonomy`, `test_propose_write_requires_validation_at_low_
# autonomy`. Ils portent sur la **politique livree**, pas sur ce qu'un
# operateur a choisi ce matin sur cette machine.
#
# Le trou etait donc reel et anterieur : la suite lisait
# `data/autonomy_override.json`, un fichier absent du depot et que rien ne
# garantit. Le meme depot, clone sur deux machines, ne rendait pas le meme
# verdict.
#
# ## Pourquoi a l'import, et non dans une fixture
#
# Une premiere version posait une fixture `scope="session"`. Elle a ramene
# les echecs de onze a six — et les six restants passaient isolement.
# `permission_matrix.py` lit la derogation dans son `__init__` : un objet
# construit pendant la collecte, avant la premiere fixture, fige le niveau
# pour toute la session. Meme raisonnement que la garde reseau ci-dessus :
# ce qui doit valoir pour tout le processus se pose a l'import.
#
# Le fichier de l'operateur n'est ni lu ni efface : un test qui detruirait
# un reglage de production serait pire que le probleme.
# On deplace `HERMES_DATA_DIR`, on ne remplace pas `_chemin()`. Une premiere
# version substituait la fonction par un lambda rendant un chemin fixe : elle
# rendait bien `lire_derogation() is None`, et **cassait la fixture
# d'isolation de `test_autonomy_control.py`**, qui isole justement en posant
# `HERMES_DATA_DIR` sur un `tmp_path`. Ignoree, cette fixture ne separait plus
# rien : un test qui ecrivait `high` le laissait au suivant. Corriger un
# defaut d'isolation en supprimant l'isolation existante — le correctif etait
# le defaut.
#
# Le fichier de l'operateur n'est ni lu ni efface : un test qui detruirait un
# reglage de production serait pire que le probleme.
os.environ["HERMES_DATA_DIR"] = tempfile.mkdtemp(prefix="hermes_donnees_")


# ── Et une verification que cette isolation tient (HOS-252) ────────────
#
# La ligne ci-dessus isole depuis HOS-215, et rien ne le **verifiait**.
# L'ecart s'est vu au pire endroit : la passe 18 a conclu que la suite
# lente ecrivait dans la vraie base de l'utilisateur, sur la foi de deux
# missions bien reelles trouvees dans `AppData/Local/HermesOS`. Elles
# venaient de sondes autonomes, qui ne chargent aucun `conftest` — la
# suite, elle, etait isolee depuis le debut. Un diagnostic faux, et une
# passe entiere batie dessus.
#
# Cette garde rend l'erreur impossible dans les deux sens : si la suite
# pointait vraiment vers l'etat de l'utilisateur, elle s'arreterait avant
# le premier test au lieu d'ecrire ; et si quelqu'un l'affirme sans que ce
# soit vrai, la garde le contredit.
#
# Elle ne supprime rien et ne touche a aucun reglage : elle compare deux
# chemins et refuse de continuer.

def racines_confondues(racine_test, racine_reelle) -> bool:
    """La racine de test est-elle celle de l'utilisateur, ou dedans ?

    Canonicalisee des deux cotes : `resolve()` suit les liens et les
    jonctions et absolutise, `normcase` gele la casse et les separateurs —
    sans quoi `C:/Users/x/AppData` et `c:/users/x/appdata` designeraient
    le meme dossier sans se ressembler, ce qui est le cas normal sous
    Windows.

    « Dedans » compte autant qu'« egale » : ecrire dans un sous-dossier de
    l'etat reel le pollue tout autant.
    """
    from pathlib import Path

    def canonique(chemin):
        return Path(os.path.normcase(str(Path(chemin).expanduser().resolve())))

    essai, vraie = canonique(racine_test), canonique(racine_reelle)
    return essai == vraie or vraie in essai.parents


def _verifier_l_isolation() -> None:
    from backend.core.etat import _racine_systeme

    essai = os.environ["HERMES_DATA_DIR"]
    vraie = _racine_systeme()
    if racines_confondues(essai, vraie):
        raise RuntimeError(
            "la suite de tests utiliserait l'etat reel de l'utilisateur.\n"
            f"  racine de test  : {essai}\n"
            f"  racine reelle   : {vraie}\n"
            "  raison          : les deux chemins canonicalises coincident, "
            "ou la seconde contient la premiere.\n"
            "Aucun test n'est execute : une suite qui ecrit dans la base, la "
            "memoire et les instantanes de l'utilisateur les corrompt sans "
            "que rien ne le dise.")


_verifier_l_isolation()


# Le harnais (HOS-138) tient une session Hermes Agent ouverte pour toute la
# duree d'une mission. C'est le mode normal en production, et c'est
# exactement ce qu'un test unitaire ne doit pas declencher : la garde reseau
# ci-dessus autorise la boucle locale, si bien qu'un backend qui tourne sur
# le poste suffisait a faire lancer un vrai agent par
# `test_hermes_agent_is_the_brain.py` — qui bloquait alors jusqu'au timeout
# de pytest. Le test mesurait l'etat de la machine, pas le code.
#
# Un test qui veut vraiment exercer le harnais passe `harnais_actif=True` a
# l'executeur : le parametre est explicite, la variable ne fixe qu'un defaut.
os.environ["HERMES_HARNAIS"] = "0"
