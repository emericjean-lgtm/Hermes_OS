"""Quels fournisseurs distants sont configurés, et le goulet (HOS-226).

## Le goulet

`task_executor` compare `runtime == "openrouter"` et `service_registry`
fabriquait une fonction de chat qui savait, en dur, quel client
construire. Ajouter un fournisseur demandait de toucher aux deux.

Ce module remplace la chaîne littérale par une question — « ce runtime
est-il un fournisseur distant configuré ? » — et rend l'objet capable de
répondre. C'est aussi l'endroit où le **pare-feu de données** du jalon
suivant se posera : un seul passage par lequel quelque chose part chez un
tiers.

## Pourquoi ici et pas dans un paquet `backend/cloud/`

Une première version de HOS-226 en créait un. C'était un cinquième
système parallèle : le RAL a déjà `adapters/hermes_ollama.py`, et un
fournisseur distant **est** un runtime — il répond à `chat` comme
Ollama. Ce qu'il a en plus est une **capacité** (`CloudCapability` :
catalogue, prix, quota), pas une hiérarchie à part.

## Pas de découverte automatique

Les fournisseurs sont enregistrés explicitement. Un mécanisme qui
scannerait un dossier rendrait la question « à qui Hermes peut-il
envoyer mes données ? » dépendante du contenu d'un répertoire — et le
jalon 11 la pose sérieusement.

**Un fournisseur sans clé n'est pas enregistré**, il n'est pas
enregistré-mais-indisponible. La différence compte : le second se lit
comme une panne, et on cherche à la réparer.
"""

from __future__ import annotations

import logging
import threading
import typing
from typing import Any

logger = logging.getLogger("hermes_os.ral.fournisseurs")


class FournisseurIndisponible(RuntimeError):
    """Le fournisseur distant n'a pas pu servir la requête.

    Distincte d'une erreur locale : celle-ci a un repli — le local — et
    l'autre n'en a pas. `RealTaskExecutor` s'appuie déjà sur cette
    distinction, portée jusqu'ici par `OpenRouterUnavailableError`.
    """


class QuotaEpuise(FournisseurIndisponible):
    """Le quota est épuisé. Sous-classe, et c'est voulu.

    Un appelant qui ne connaît que `FournisseurIndisponible` se replie
    correctement ; celui qui distingue peut attendre au lieu de basculer.
    Deux exceptions sœurs auraient fait qu'oublier d'attraper la seconde
    laisse échouer une escalade qui devait se replier.
    """


@typing.runtime_checkable
class Fournisseur(typing.Protocol):
    """Un runtime distant : du chat, un catalogue, un quota.

    `Protocol` et non classe de base : les adaptateurs enveloppent des
    clients qui existent déjà — `OpenRouterClient` a 287 lignes et neuf
    gardes — et leur imposer un héritage forcerait à les réécrire pour
    satisfaire une forme.
    """

    name: str

    async def chat(self, messages: list[dict[str, Any]], *, model: str,
                   num_ctx: int | None = None) -> Any: ...

    async def modeles(self) -> list[Any]: ...

    async def quota(self, *, reserve: int = 0) -> Any: ...

    async def fermer(self) -> None: ...



_verrou = threading.RLock()
_fournisseurs: dict[str, Fournisseur] = {}
_amorce = False


def enregistrer(instance: Fournisseur) -> None:
    """Déclarer un fournisseur utilisable.

    Écrase un homonyme plutôt que de lever : le cas réel est un
    rechargement de configuration, et refuser laisserait l'ancien objet —
    donc l'ancienne clé — en service après que l'utilisateur en a changé.
    """
    identifiant = getattr(instance, "name", "") or ""
    if not identifiant:
        raise ValueError("un fournisseur doit porter un identifiant")
    with _verrou:
        _fournisseurs[identifiant] = instance


def fournisseur(identifiant: str) -> Fournisseur | None:
    """Le fournisseur pour cet identifiant, ou None.

    `None` remplace la comparaison littérale : un appelant demande
    l'objet et se replie s'il n'y en a pas, au lieu de tester un nom.
    """
    _amorcer_une_fois()
    with _verrou:
        return _fournisseurs.get((identifiant or "").strip().lower())


def fournisseurs() -> dict[str, Fournisseur]:
    _amorcer_une_fois()
    with _verrou:
        return dict(_fournisseurs)


def disponible(identifiant: str) -> bool:
    """Ce runtime est-il un fournisseur cloud configuré ?

    La question que `task_executor` posait en comparant une chaîne.
    """
    return fournisseur(identifiant) is not None


def reinitialiser() -> None:
    """Vider le registre. Pour les tests, et pour un rechargement.

    Remet aussi le drapeau d'amorçage : sans ça, un test qui vide le
    registre le laisserait vide pour tous les suivants, et une garde
    passerait sur rien.
    """
    global _amorce
    with _verrou:
        _fournisseurs.clear()
        _amorce = False


def _amorcer_une_fois() -> None:
    """Enregistrer ce que la configuration rend disponible.

    Paresseux plutôt qu'à l'import : lire la configuration au moment de
    l'import ferait dépendre l'ordre des imports du contenu de
    l'environnement, ce qui se débogue mal et se teste plus mal encore.
    """
    global _amorce
    with _verrou:
        if _amorce:
            return
        _amorce = True

    try:
        from backend.ral.adapters.openrouter import RuntimeOpenRouter

        instance = RuntimeOpenRouter.depuis_la_configuration()
        if instance is not None:
            enregistrer(instance)
    except Exception:  # pragma: no cover - configuration illisible
        logger.warning("amorçage des fournisseurs cloud impossible",
                       exc_info=True)


__all__ = ["Fournisseur", "FournisseurIndisponible", "QuotaEpuise",
           "disponible", "enregistrer", "fournisseur", "fournisseurs",
           "reinitialiser"]
