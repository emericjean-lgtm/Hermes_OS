"""OpenRouter comme runtime du RAL, pas comme cas particulier (HOS-226).

## Ce que cet adaptateur **n'est pas**

Une réécriture. `OpenRouterClient` fait 287 lignes, ses formes d'endpoint
ont été confrontées à l'API réelle (HOS-066C) et il porte neuf gardes —
compteurs d'usage, 429 traduit en quota, SSE, échec en cours de flux, non-200
avant le flux. Ce fichier l'enveloppe.

Ce qu'il ajoute, ce sont les deux choses que le protocole demande et que
le client ne fait pas : le **catalogue avec ses prix**, et l'**état du
quota**. Elles existaient — dans `cloud_catalog.py` — mêlées à la
population du `ModelProfiler`. Ce module les expose sous leur forme
neutre sans toucher au catalogue, qui garde son rôle : peupler le
profileur.

Deux chemins vers `/models` et `/key` ne sont pas une duplication de
logique mais une duplication de **requête**, et elles ne se contredisent
pas : ce sont deux lectures du même état côté fournisseur.

## Une correction au passage

`cloud_catalog._is_free_pricing` compare `pricing["prompt"] == "0"` — une
égalité de **chaîne**. OpenRouter rend `"0"` aujourd'hui ; il rend
`"0.0"` pour certaines entrées, et un flottant sur d'autres endpoints.
Ici la comparaison est numérique, et un prix illisible est traité comme
**payant** — le sens de lecture qui ne fait pas dépenser par erreur.
"""

from __future__ import annotations

import logging
from typing import Any

from backend.ral.capabilities import (
    ChatResponse,
    EtatDuQuota,
    ModeleCloud,
)
from backend.ral.fournisseurs import FournisseurIndisponible, QuotaEpuise

logger = logging.getLogger("hermes_os.cloud.openrouter")

IDENTIFIANT = "openrouter"


def _prix(valeur: Any) -> float | None:
    """Un prix, ou None quand il n'est pas lisible.

    `None` et `0.0` ne disent pas la même chose : le premier est « je ne
    sais pas », le second « c'est gratuit ». Les confondre ferait passer
    un modèle payant pour gratuit sur une réponse mal formée.
    """
    if valeur is None:
        return None
    try:
        return float(valeur)
    except (TypeError, ValueError):
        return None


class RuntimeOpenRouter:
    """Le runtime distant. Un client neuf par appel, comme le fait déjà
    `service_registry._make_cloud_chat` — et pour la même raison : une
    connexion gardée ouverte entre deux missions se fait couper par le
    pair sans que rien le dise.

    Satisfait `ChatCapability` **et** `CloudCapability` : c'est un
    runtime au même titre que `HermesOllamaRuntime`, avec en plus les
    trois choses qu'un distant a et qu'un local n'a pas — un prix, un
    quota partagé, un catalogue qui change sans qu'on l'ait décidé.
    """

    name = IDENTIFIANT

    def __init__(self, cle: str, *, base_url: str | None = None,
                 transport: Any = None, timeout: float = 15.0) -> None:
        if not cle:
            raise ValueError(
                "un fournisseur cloud sans clé n'est pas un fournisseur "
                "indisponible : il n'existe pas")
        self._cle = cle
        self._base_url = base_url
        self._transport = transport
        self._timeout = timeout

    @classmethod
    def depuis_la_configuration(cls) -> "RuntimeOpenRouter | None":
        """`None` quand la clé n'est pas configurée.

        Le même contrat que `OpenRouterClient.from_settings` : « pas
        configuré » se répond identiquement partout plutôt que par trois
        gardes légèrement différentes qui divergent.
        """
        from backend.core.config import get_settings

        cle = get_settings().openrouter_api_key
        return cls(cle) if cle else None

    # ── Chat ─────────────────────────────────────────────────────────

    def _client(self):
        from backend.connectors.openrouter_client import OpenRouterClient

        kwargs: dict[str, Any] = {}
        if self._base_url:
            kwargs["base_url"] = self._base_url
        if self._transport is not None:
            kwargs["transport"] = self._transport
        return OpenRouterClient(self._cle, **kwargs)

    async def chat(self, messages: list[dict[str, Any]], *, model: str,
                   num_ctx: int | None = None) -> ChatResponse:
        """Traduit les erreurs du client vers celles du protocole.

        La hiérarchie est conservée — quota reste une sous-classe
        d'indisponible — de sorte qu'un appelant qui ne connaît que la
        seconde se replie correctement au lieu de laisser passer.
        """
        from backend.connectors.openrouter_client import (
            OpenRouterQuotaExhaustedError,
            OpenRouterUnavailableError,
        )

        client = self._client()
        try:
            return await client.chat(messages, model=model, num_ctx=num_ctx)
        except OpenRouterQuotaExhaustedError as exc:
            raise QuotaEpuise(str(exc)) from exc
        except OpenRouterUnavailableError as exc:
            raise FournisseurIndisponible(str(exc)) from exc
        finally:
            try:
                await client.aclose()
            except Exception:  # pragma: no cover - fermeture au mieux
                pass

    # ── Catalogue et quota ───────────────────────────────────────────

    def _http(self):
        import httpx

        from backend.connectors.openrouter_client import DEFAULT_BASE_URL

        return httpx.AsyncClient(
            base_url=self._base_url or DEFAULT_BASE_URL,
            timeout=self._timeout, transport=self._transport,
            headers={"Authorization": f"Bearer {self._cle}"})

    async def modeles(self) -> list[ModeleCloud]:
        """Le catalogue, ou une liste vide.

        Vide plutôt que levé : « aucun modèle disponible » est un état de
        service normal, et lever ferait échouer une décision de routage
        qui doit seulement se rabattre sur le local. C'est déjà le choix
        de `CloudModelCatalog.refresh`, et il est juste.
        """
        try:
            async with self._http() as client:
                reponse = await client.get("/models")
                reponse.raise_for_status()
                entrees = (reponse.json() or {}).get("data") or []
        except Exception:
            logger.warning("catalogue OpenRouter injoignable", exc_info=True)
            return []

        catalogue: list[ModeleCloud] = []
        for entree in entrees:
            identifiant = str(entree.get("id") or "").strip()
            if not identifiant:
                continue
            tarifs = entree.get("pricing") or {}
            entree_prix = _prix(tarifs.get("prompt"))
            sortie_prix = _prix(tarifs.get("completion"))
            modalites = ((entree.get("architecture") or {})
                         .get("output_modalities") or ["text"])
            catalogue.append(ModeleCloud(
                identifiant=identifiant,
                fournisseur=self.name,
                nom=str(entree.get("name") or identifiant),
                fenetre=int(entree.get("context_length") or 0),
                # Un prix illisible compte comme **payant**. Le sens de
                # lecture qui ne fait pas dépenser par erreur, et celui
                # que `_is_free_pricing` n'a pas : il compare `== "0"`,
                # donc `"0.0"` s'y lit payant par accident plutôt que
                # par décision.
                gratuit=(entree_prix == 0.0 and sortie_prix == 0.0),
                prix_entree=entree_prix or 0.0,
                prix_sortie=sortie_prix or 0.0,
                conversationnel="text" in modalites,
            ))
        return catalogue

    async def quota(self, *, reserve: int = 0) -> EtatDuQuota:
        """Ce qui reste sur la clé.

        `reserve` garde de côté les dernières requêtes de la journée,
        comme `CloudModelCatalog` : une rafale de tâches peu importantes
        ne doit pas épuiser le quota juste avant celle qui en avait
        vraiment besoin.

        Un quota non mesurable rend `utilisable=False`. On ne dépense pas
        sur une mesure qu'on n'a pas — c'est la règle tri-état de
        HOS-222 appliquée à une ressource payante.
        """
        try:
            async with self._http() as client:
                reponse = await client.get("/key")
                reponse.raise_for_status()
                donnees = (reponse.json() or {}).get("data") or {}
        except Exception as exc:
            return EtatDuQuota.inconnu(self.name, f"/key : {exc}")

        restant = donnees.get("limit_remaining")
        if restant is None:
            # Une clé sans limite est un cas réel chez OpenRouter, et il
            # n'est **pas** « inconnu » : la réponse a été lue, elle dit
            # qu'il n'y a pas de plafond.
            if "limit" in donnees and donnees.get("limit") is None:
                return EtatDuQuota(fournisseur=self.name,
                                   utilisable=True,
                                   detail="clé sans plafond déclaré")
            return EtatDuQuota.inconnu(
                self.name, "la réponse ne porte pas limit_remaining")

        restant = int(restant)
        limite = donnees.get("limit")
        return EtatDuQuota(
            fournisseur=self.name,
            utilisable=restant > reserve,
            restant=restant,
            limite=int(limite) if limite is not None else None,
            detail=(f"{restant} restant(s), réserve de {reserve}"
                    if restant <= reserve else ""),
        )

    async def fermer(self) -> None:
        """Rien à fermer : un client neuf par appel, fermé par lui."""
        return None


__all__ = ["IDENTIFIANT", "RuntimeOpenRouter"]
