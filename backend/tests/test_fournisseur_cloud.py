"""Un fournisseur cloud derrière une interface (HOS-226).

## La prémisse du jalon était fausse, et le reste ne l'était pas

La roadmap annonçait « le client existe sans un seul test ». Il en a
**neuf**, réels — compteurs d'usage, 429 traduit en quota, SSE, échec en
cours de flux, non-200 avant le flux — dans `tests/`, l'arbre qui n'était
plus collecté depuis HOS-175. Quatrième fois que cette réparation change
une conclusion.

Ce qui manquait réellement, et qui est mesuré :

- **`CloudProvider` n'existait nulle part** : zéro occurrence.
- **Trois fichiers** codent `https://openrouter.ai/api/v1` en dur.
- `task_executor` et `service_registry` branchent sur la chaîne
  littérale `"openrouter"`.

## Pourquoi une interface pour une seule implémentation

Parce que le jalon suivant est le pare-feu de données, et que la décision
§8.1 du cahier — le cloud est refusé par défaut — suppose un endroit
unique où « quelque chose part chez un tiers » se constate. Sans
interface, ce contrôle serait à dupliquer par fournisseur, donc à
oublier au second.
"""

from __future__ import annotations

import httpx
import pytest

from backend.ral import fournisseurs as cloud_registre
from backend.ral.adapters.openrouter import RuntimeOpenRouter
from backend.ral.capabilities import (
    ChatCapability,
    CloudCapability,
    EtatDuQuota,
    ModeleCloud,
)
from backend.ral.fournisseurs import (
    Fournisseur,
    FournisseurIndisponible,
    QuotaEpuise,
)


def _transport(reponses: dict[str, httpx.Response]) -> httpx.MockTransport:
    def repond(requete: httpx.Request) -> httpx.Response:
        if requete.url.path not in reponses:
            return httpx.Response(404, json={"error": requete.url.path})
        return reponses[requete.url.path]

    return httpx.MockTransport(repond)


_MODELES = httpx.Response(200, json={"data": [
    {"id": "a/gratuit", "name": "A", "context_length": 65536,
     "pricing": {"prompt": "0", "completion": "0"},
     "architecture": {"output_modalities": ["text"]}},
    {"id": "b/payant", "name": "B", "context_length": 8192,
     "pricing": {"prompt": "0.5", "completion": "1.5"},
     "architecture": {"output_modalities": ["text"]}},
    # OpenRouter rend « 0 » aujourd'hui, et « 0.0 » sur certaines
    # entrées : `cloud_catalog._is_free_pricing` compare `== "0"` et
    # lit donc celle-ci comme payante, par accident.
    {"id": "c/zero-virgule", "name": "C", "context_length": 4096,
     "pricing": {"prompt": "0.0", "completion": "0.0"},
     "architecture": {"output_modalities": ["text"]}},
    {"id": "d/illisible", "name": "D", "context_length": 4096,
     "pricing": {"prompt": "gratuit", "completion": None},
     "architecture": {"output_modalities": ["text"]}},
    {"id": "e/image", "name": "E", "context_length": 4096,
     "pricing": {"prompt": "0", "completion": "0"},
     "architecture": {"output_modalities": ["image"]}},
]})


def _fournisseur(**reponses) -> RuntimeOpenRouter:
    defaut = {"/api/v1/models": _MODELES,
              "/api/v1/key": httpx.Response(
                  200, json={"data": {"limit_remaining": 42, "limit": 1000}})}
    defaut.update(reponses)
    return RuntimeOpenRouter("cle", transport=_transport(defaut))


@pytest.fixture(autouse=True)
def registre_propre():
    """Le registre est un état de processus.

    Le vider avant *et* après : un test qui le laisse peuplé fait passer
    le suivant sur la configuration du premier.
    """
    cloud_registre.reinitialiser()
    yield
    cloud_registre.reinitialiser()


# ═══ Le protocole ════════════════════════════════════════════════════

def test_l_adaptateur_satisfait_le_protocole():
    """`runtime_checkable` : la vérification porte sur les méthodes.

    Elle ne dit pas que les signatures concordent — mais elle attrape
    l'oubli d'une méthode entière, qui est l'erreur qu'on commet.
    """
    assert isinstance(_fournisseur(), Fournisseur)


def test_un_fournisseur_distant_est_un_runtime_du_ral():
    """Et non une hiérarchie parallèle.

    La première version de ce jalon créait un paquet `backend/cloud/` à
    côté du RAL — un cinquième système. Or le RAL a déjà
    `adapters/hermes_ollama.py`, et un fournisseur distant **est** un
    runtime : il répond à `chat` comme Ollama. Ce qu'il a en plus —
    catalogue, prix, quota — est une **capacité**, pas une arborescence.
    """
    fournisseur = _fournisseur()
    assert isinstance(fournisseur, ChatCapability)
    assert isinstance(fournisseur, CloudCapability)

    from pathlib import Path

    racine = Path(__file__).resolve().parents[2]
    assert not (racine / "backend" / "cloud").exists(), (
        "le paquet parallèle est revenu — un fournisseur distant est un "
        "adaptateur du RAL")


def test_un_fournisseur_sans_cle_n_existe_pas():
    """Il n'est pas « configuré mais indisponible ».

    La différence compte : le second se lit comme une panne, et on
    cherche à la réparer.
    """
    with pytest.raises(ValueError, match="n'existe pas"):
        RuntimeOpenRouter("")


def test_quota_epuise_est_une_sous_classe_d_indisponible():
    """Un appelant qui ne connaît que la seconde se replie correctement.

    Deux exceptions sœurs auraient fait qu'oublier d'attraper la seconde
    laisse échouer une escalade qui devait se replier sur le local.
    """
    assert issubclass(QuotaEpuise, FournisseurIndisponible)


# ═══ Le catalogue, et sa correction de prix ══════════════════════════

@pytest.mark.asyncio
async def test_le_catalogue_porte_les_prix():
    modeles = {m.identifiant: m for m in await _fournisseur().modeles()}
    assert modeles["b/payant"].prix_entree == 0.5
    assert modeles["b/payant"].prix_sortie == 1.5
    assert modeles["b/payant"].gratuit is False
    assert modeles["a/gratuit"].fenetre == 65536


@pytest.mark.asyncio
async def test_zero_virgule_zero_est_gratuit():
    """`_is_free_pricing` compare `pricing["prompt"] == "0"`.

    Une égalité de **chaîne** : `"0.0"` s'y lit payant par accident
    plutôt que par décision. Ici la comparaison est numérique.
    """
    modeles = {m.identifiant: m for m in await _fournisseur().modeles()}
    assert modeles["c/zero-virgule"].gratuit is True


@pytest.mark.asyncio
async def test_un_prix_illisible_compte_comme_payant():
    """Le sens de lecture qui ne fait pas dépenser par erreur.

    `None` et `0.0` ne disent pas la même chose : le premier est « je ne
    sais pas », le second « c'est gratuit ».
    """
    modeles = {m.identifiant: m for m in await _fournisseur().modeles()}
    assert modeles["d/illisible"].gratuit is False


@pytest.mark.asyncio
async def test_un_modele_non_textuel_est_marque():
    modeles = {m.identifiant: m for m in await _fournisseur().modeles()}
    assert modeles["e/image"].conversationnel is False


@pytest.mark.asyncio
async def test_un_catalogue_injoignable_rend_une_liste_vide():
    """« Aucun modèle disponible » est un état de service normal.

    Lever ferait échouer une décision de routage qui doit seulement se
    rabattre sur le local — c'est déjà le choix de
    `CloudModelCatalog.refresh`, et il est juste.
    """
    fournisseur = _fournisseur(**{"/api/v1/models": httpx.Response(503)})
    assert await fournisseur.modeles() == []


@pytest.mark.asyncio
async def test_une_entree_sans_identifiant_est_ignoree():
    """Un catalogue partiellement malformé ne doit pas être perdu entier."""
    fournisseur = _fournisseur(**{"/api/v1/models": httpx.Response(200, json={
        "data": [{"name": "sans id"}, {"id": "bon", "pricing": {}}]})})
    assert [m.identifiant for m in await fournisseur.modeles()] == ["bon"]


# ═══ Le quota, et son tri-état ═══════════════════════════════════════

@pytest.mark.asyncio
async def test_le_quota_est_lu():
    quota = await _fournisseur().quota()
    assert quota.mesure_possible is True
    assert quota.utilisable is True
    assert (quota.restant, quota.limite) == (42, 1000)


@pytest.mark.asyncio
async def test_la_reserve_garde_les_dernieres_requetes():
    """Une rafale de tâches peu importantes ne doit pas épuiser le quota
    juste avant celle qui en avait vraiment besoin."""
    assert (await _fournisseur().quota(reserve=50)).utilisable is False


@pytest.mark.asyncio
async def test_un_quota_non_mesurable_n_est_pas_utilisable():
    """La règle tri-état de HOS-222, appliquée à une ressource payante.

    On ne dépense pas sur une mesure qu'on n'a pas.
    """
    quota = await _fournisseur(**{"/api/v1/key": httpx.Response(500)}).quota()
    assert quota.mesure_possible is False
    assert quota.utilisable is False
    assert quota.detail


@pytest.mark.asyncio
async def test_une_reponse_sans_limit_remaining_est_inconnue():
    quota = await _fournisseur(**{
        "/api/v1/key": httpx.Response(200, json={"data": {}})}).quota()
    assert quota.mesure_possible is False


@pytest.mark.asyncio
async def test_une_cle_sans_plafond_n_est_pas_inconnue():
    """Cas réel chez OpenRouter, et il n'est **pas** « on ne sait pas ».

    La réponse a été lue ; elle dit qu'il n'y a pas de plafond. Le ranger
    sous « inconnu » interdirait le cloud à qui en a payé l'accès
    illimité.
    """
    quota = await _fournisseur(**{"/api/v1/key": httpx.Response(
        200, json={"data": {"limit": None, "limit_remaining": None}})}).quota()
    assert quota.mesure_possible is True
    assert quota.utilisable is True


def test_l_etat_inconnu_n_est_jamais_utilisable():
    assert EtatDuQuota.inconnu("x").utilisable is False


# ═══ La traduction des erreurs ═══════════════════════════════════════

@pytest.mark.asyncio
async def test_un_429_devient_un_quota_epuise():
    fournisseur = RuntimeOpenRouter("cle", transport=_transport(
        {"/api/v1/chat/completions": httpx.Response(
            429, json={"error": {"message": "rate limited"}})}))
    with pytest.raises(QuotaEpuise):
        await fournisseur.chat([{"role": "user", "content": "x"}], model="m")


@pytest.mark.asyncio
async def test_une_autre_erreur_reste_une_indisponibilite():
    """Et **pas** un quota : les deux appellent des remèdes différents.

    C'est la même distinction que la taxonomie de HOS-225 tient côté
    exécution — attendre ou basculer ne sont pas le même geste.
    """
    fournisseur = RuntimeOpenRouter("cle", transport=_transport(
        {"/api/v1/chat/completions": httpx.Response(500, text="boom")}))
    with pytest.raises(FournisseurIndisponible) as leve:
        await fournisseur.chat([{"role": "user", "content": "x"}], model="m")
    assert not isinstance(leve.value, QuotaEpuise)


@pytest.mark.asyncio
async def test_une_reponse_reelle_traverse_l_adaptateur():
    """L'adaptateur enveloppe, il ne réinterprète pas.

    Les compteurs d'usage réels d'OpenRouter — ceux que
    `RealTaskExecutor` préfère à son estimation par caractères — doivent
    arriver intacts.
    """
    fournisseur = RuntimeOpenRouter("cle", transport=_transport(
        {"/api/v1/chat/completions": httpx.Response(200, json={
            "model": "a/gratuit",
            "choices": [{"message": {"content": "bonjour"}}],
            "usage": {"prompt_tokens": 11, "completion_tokens": 7}})}))
    reponse = await fournisseur.chat([{"role": "user", "content": "x"}],
                                     model="a/gratuit")
    assert reponse.content == "bonjour"
    assert reponse.metadata["prompt_tokens"] == 11
    assert reponse.metadata["completion_tokens"] == 7
    assert reponse.metadata["provider"] == "openrouter"


# ═══ Le registre ═════════════════════════════════════════════════════

def test_un_fournisseur_enregistre_se_retrouve():
    cloud_registre.enregistrer(_fournisseur())
    assert cloud_registre.fournisseur("openrouter") is not None
    assert cloud_registre.disponible("openrouter") is True


def test_un_identifiant_inconnu_rend_none():
    """`None` remplace la comparaison littérale : l'appelant demande
    l'objet et se replie s'il n'y en a pas, au lieu de tester un nom."""
    assert cloud_registre.fournisseur("un-autre-nuage") is None
    assert cloud_registre.disponible("un-autre-nuage") is False


def test_l_identifiant_est_insensible_a_la_casse():
    cloud_registre.enregistrer(_fournisseur())
    assert cloud_registre.disponible("OpenRouter") is True


def test_un_fournisseur_sans_identifiant_est_refuse():
    class Anonyme:
        name = ""

    with pytest.raises(ValueError, match="identifiant"):
        cloud_registre.enregistrer(Anonyme())


def test_un_reenregistrement_remplace():
    """Le cas réel est un rechargement de configuration.

    Refuser laisserait l'ancien objet — donc l'ancienne clé — en service
    après que l'utilisateur en a changé.
    """
    premier = _fournisseur()
    cloud_registre.enregistrer(premier)
    second = _fournisseur()
    cloud_registre.enregistrer(second)
    assert cloud_registre.fournisseur("openrouter") is second


def test_sans_cle_aucun_fournisseur_n_est_amorce(monkeypatch):
    """Le défaut sûr : pas de clé, pas de cloud du tout."""
    from backend.core import config

    monkeypatch.setenv("OPENROUTER_API_KEY", "")
    config.get_settings.cache_clear()
    try:
        assert cloud_registre.fournisseurs() == {}
    finally:
        config.get_settings.cache_clear()


# ═══ Le branchement ══════════════════════════════════════════════════

def test_la_fabrique_de_chat_passe_par_le_registre():
    """Elle construisait un `OpenRouterClient` en dur.

    C'est aussi l'endroit où le pare-feu de données du jalon suivant se
    posera : un seul passage par lequel quelque chose part chez un
    tiers. Un test qui tombe si quelqu'un recâble le client en direct.
    """
    import ast
    import inspect
    import textwrap

    from backend.core.bootstrap import service_registry

    source = inspect.getsource(service_registry._make_cloud_chat)
    # Le **corps**, pas la docstring : celle-ci nomme
    # `OpenRouterClient` pour expliquer ce qui a changé, et une
    # assertion sur le texte entier s'y accrochait. Troisième faux
    # positif de sous-chaîne sur ce chantier — celui-là se règle en
    # regardant l'arbre syntaxique plutôt que la chaîne.
    arbre = ast.parse(textwrap.dedent(source))
    corps = [n for n in ast.walk(arbre)
             if not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant))]
    noms = {n.id for n in ast.walk(arbre) if isinstance(n, ast.Name)}
    noms |= {a.name for n in ast.walk(arbre)
             if isinstance(n, (ast.Import, ast.ImportFrom)) for a in n.names}
    modules = {n.module for n in ast.walk(arbre)
               if isinstance(n, ast.ImportFrom) and n.module}

    assert any(m.startswith("backend.ral") for m in modules), modules
    assert "OpenRouterClient" not in noms, (
        "la fabrique construit à nouveau un client en direct — le "
        "pare-feu du jalon 11 n'aurait plus de passage unique")


def test_le_choix_de_runtime_demande_au_registre():
    """« Ce runtime est-il un fournisseur configuré ? », pas « s'appelle-t-il
    openrouter ? ».

    La comparaison littérale rendait « openrouter » même sans clé, et
    l'exécuteur découvrait l'absence plus loin.
    """
    import inspect

    from backend.core.bootstrap import service_registry

    source = inspect.getsource(service_registry._make_task_executor)
    assert "_cloud.disponible" in source


def test_sans_fournisseur_la_fabrique_rend_none():
    """Cloud entièrement injoignable, quoi que recommande AdaptiveRouter.

    Le défaut sûr, et celui d'avant ce jalon.
    """
    from backend.core.bootstrap.service_registry import _make_cloud_chat

    assert _make_cloud_chat() is None


@pytest.mark.asyncio
async def test_la_fabrique_appelle_le_fournisseur_enregistre():
    from backend.core.bootstrap.service_registry import _make_cloud_chat

    cloud_registre.enregistrer(RuntimeOpenRouter("cle", transport=_transport(
        {"/api/v1/chat/completions": httpx.Response(200, json={
            "choices": [{"message": {"content": "via le registre"}}]})})))

    chat = _make_cloud_chat()
    assert chat is not None
    reponse = await chat(messages=[{"role": "user", "content": "x"}], model="m")
    assert reponse.content == "via le registre"
