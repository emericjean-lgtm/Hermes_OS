"""Rien ne part chez un tiers sans passer par le pare-feu (A-1, HOS-255).

## Le défaut, mesuré par l'audit J25

`_make_cloud_chat` examinait bien avant d'envoyer, et son commentaire
affirmait être « le seul passage par lequel un prompt part chez un
tiers ». C'était faux :

    base_agent.py:279        self._cloud_client.chat_events(model, messages, …)
    task_decomposer.py:489   self._cloud_client.chat_events(model, messages, …)
    grep -c pare_feu  →  0   dans les deux fichiers

HOS-066C a livré un repli de résilience — tenté quand le flux local
échoue **avant d'avoir rendu un seul morceau** — et il précède HOS-227
d'assez loin pour n'avoir jamais été routé à travers lui. Le déclencheur
est une panne d'Ollama : sur ce matériel, une condition de routine.

## Pourquoi la garde est dans le client

Router les deux replis vers `_make_cloud_chat` ne tient pas : ce goulet
est non-streaming et rend une réponse complète, quand `BaseAgent`
diffuse. La garde vit donc là où est la socket — une seule autorité,
`pare_feu.examiner`, appliquée sur les deux méthodes de sortie de
`OpenRouterClient`, ce qui couvre tout appelant présent et futur.

## Ce que ce fichier ne prouve pas

Que le pare-feu *détecte* tout. Il prouve qu'on ne peut pas le
contourner. Mesuré au passage et consigné séparément : il reconnaît
`sk-…` comme secret et **ignore `sk-or-v1-…`**, le format de clé
d'OpenRouter lui-même. C'est un défaut de détection, pas de routage.
"""

from __future__ import annotations

import ast
import io
from pathlib import Path

import httpx
import pytest

from backend.connectors.openrouter_client import (
    OpenRouterClient,
    OpenRouterUnavailableError,
)

RACINE = Path(__file__).resolve().parents[2]

CLE_OPENAI = "sk-abcdef0123456789abcdef0123456789abcdef0123456789"
WORKSPACE = r"C:\Users\emeri\Skill360 Industry"


class _Transport(httpx.MockTransport):
    """Un OpenRouter qui note ce qu'on lui a réellement envoyé."""

    def __init__(self, flux: bool = False) -> None:
        self.recu: list[dict] = []
        self.appels = 0

        def repondre(requete: httpx.Request) -> httpx.Response:
            import json

            self.appels += 1
            self.recu.append(json.loads(requete.content.decode()))
            if flux:
                corps = (b'data: {"choices":[{"delta":{"content":"ok"}}]}\n\n'
                         b"data: [DONE]\n\n")
                return httpx.Response(200, content=corps,
                                      headers={"content-type": "text/event-stream"})
            return httpx.Response(200, json={
                "choices": [{"message": {"content": "ok"}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            })

        super().__init__(repondre)


def _client(flux: bool = False) -> tuple[OpenRouterClient, _Transport]:
    t = _Transport(flux)
    return OpenRouterClient("cle-de-test", transport=t), t


async def _diffuser(client, **kw):
    morceaux = []
    async for c in client.chat_events("m", **kw):
        morceaux.append(c)
    return morceaux


# ═══ A — le chemin nominal passe par le pare-feu ═════════════════════

@pytest.mark.asyncio
async def test_A_un_envoi_normal_traverse_le_pare_feu():
    client, t = _client()
    await client.chat([{"role": "user", "content": "additionne deux entiers"}],
                      model="m")
    assert t.appels == 1
    assert t.recu[0]["messages"][0]["content"] == "additionne deux entiers"


# ═══ B/H — le repli d'une panne locale y passe aussi ═════════════════

@pytest.mark.asyncio
async def test_B_le_repli_d_un_agent_passe_par_le_pare_feu(monkeypatch):
    """Le vrai chemin de `BaseAgent.respond_events` : le flux local
    échoue **avant** d'avoir rendu un morceau, et le nuage prend le
    relais. C'est ce chemin-là qui envoyait sans filtre."""
    client, t = _client(flux=True)

    morceaux = await _diffuser(
        client, messages=[{"role": "system",
                           "content": f"workspace at '{WORKSPACE}'"}])

    assert morceaux, "le repli n'a rien diffusé"
    assert t.appels == 1
    envoye = t.recu[0]["messages"][0]["content"]
    assert WORKSPACE not in envoye, (
        "le chemin du workspace est parti tel quel : c'est exactement la "
        "fuite que HOS-227 décrit dans sa propre docstring")


@pytest.mark.asyncio
async def test_H_une_exception_locale_ne_cree_pas_de_sortie_non_filtree():
    """Le repli est déclenché par une exception ; l'exception ne doit pas
    être un chemin privilégié."""
    client, t = _client(flux=True)
    with pytest.raises(OpenRouterUnavailableError):
        await _diffuser(client, messages=[{"role": "user", "content": CLE_OPENAI}])
    assert t.appels == 0


# ═══ C/D/E — refus : rien ne sort ════════════════════════════════════

@pytest.mark.asyncio
async def test_C_un_refus_du_pare_feu_n_envoie_rien():
    client, t = _client()
    with pytest.raises(OpenRouterUnavailableError) as capture:
        await client.chat([{"role": "user", "content": CLE_OPENAI}], model="m")
    assert "pare-feu" in str(capture.value)
    assert t.appels == 0, "une requête est partie malgré le refus"


@pytest.mark.asyncio
async def test_D_une_donnee_secrete_ne_quitte_jamais_hermes():
    client, t = _client()
    with pytest.raises(OpenRouterUnavailableError):
        await client.chat(
            [{"role": "system", "content": "contexte"},
             {"role": "user", "content": f"ma clé est {CLE_OPENAI}"}], model="m")
    assert t.recu == []


@pytest.mark.asyncio
async def test_E_le_chemin_de_workspace_est_caviarde_quand_les_racines_sont_connues():
    client, t = _client()
    await client.chat([{"role": "system", "content": f"travaille dans {WORKSPACE}"}],
                      model="m", racines=[WORKSPACE])
    envoye = t.recu[0]["messages"][0]["content"]
    assert WORKSPACE not in envoye
    assert "<WORKSPACE>" in envoye


@pytest.mark.asyncio
async def test_E_sans_racines_le_chemin_est_caviarde_par_motif():
    """Un appelant qui ne connaît pas les racines — un repli d'agent —
    obtient moins de précision, jamais zéro protection."""
    client, t = _client()
    await client.chat([{"role": "system", "content": f"travaille dans {WORKSPACE}"}],
                      model="m")
    assert WORKSPACE not in t.recu[0]["messages"][0]["content"]


# ═══ F — l'appel direct ne contourne pas ═════════════════════════════

@pytest.mark.asyncio
async def test_F_appeler_le_client_directement_ne_contourne_pas():
    """C'est la forme exacte du défaut : détenir un client et l'appeler
    soi-même, sans passer par le goulet."""
    client, t = _client(flux=True)
    with pytest.raises(OpenRouterUnavailableError):
        await _diffuser(client, messages=[{"role": "user", "content": CLE_OPENAI}])
    assert t.appels == 0


@pytest.mark.asyncio
async def test_F_chat_stream_herite_de_la_garde():
    """`chat_stream` délègue à `chat_events` : la garde vaut pour lui
    sans qu'on l'y répète."""
    client, t = _client(flux=True)
    with pytest.raises(OpenRouterUnavailableError):
        async for _ in client.chat_stream("m", [{"role": "user", "content": CLE_OPENAI}]):
            pass
    assert t.appels == 0


# ═══ G — changer de fournisseur ne contourne pas ═════════════════════

@pytest.mark.asyncio
async def test_G_l_adaptateur_ral_passe_par_le_meme_client():
    """Le fournisseur du goulet construit ce même client : la garde le
    couvre sans qu'il ait à la connaître."""
    from backend.ral.adapters.openrouter import RuntimeOpenRouter

    t = _Transport()
    f = RuntimeOpenRouter("cle-de-test", transport=t)

    with pytest.raises(Exception) as capture:
        await f.chat([{"role": "user", "content": CLE_OPENAI}], model="m")
    assert t.appels == 0, "l'adaptateur a laissé partir un secret"
    assert "pare-feu" in str(capture.value)


# ═══ Anti-contournement, structurel ══════════════════════════════════

#: Les seuls fichiers de production autorisés à parler à OpenRouter.
#:
#: `openrouter_client.py` porte la garde ; `adapters/openrouter.py` la
#: traverse en construisant ce client. Toute autre sortie devrait passer
#: par l'un des deux — ajouter une entrée ici est un acte délibéré, et
#: c'est le but.
SORTIES_AUTORISEES = {
    "backend/connectors/openrouter_client.py",
    "backend/ral/adapters/openrouter.py",
    # Exception nommée : le banc de modèles fait son propre appel httpx
    # (« own httpx call, no wrapper client »), et n'envoie que des prompts
    # **constants** définis dans son propre module — `_PROMPTS_BY_TASK_TYPE`
    # et `_DEFAULT_PROMPT`. Aucune donnée d'Hermes OS ne s'y trouve, donc
    # rien que le pare-feu aurait à examiner. Si un jour ce module envoie
    # autre chose qu'un littéral, cette ligne devra être retirée.
    "backend/model_intelligence/benchmark_scheduler.py",
    # Exception nommée : le catalogue ne fait que des `GET /models` et une
    # lecture de crédits — il lit ce qu'OpenRouter propose, il n'envoie
    # aucun message. Rien à examiner : le pare-feu filtre des prompts, et
    # il n'y en a pas.
    "backend/model_intelligence/cloud_catalog.py",
}


def _fichiers_touchant_openrouter() -> set[str]:
    """Tout module de production qui nomme l'hôte ou le client OpenRouter
    d'une façon qui pourrait aboutir à un envoi."""
    trouves: set[str] = set()
    for f in (RACINE / "backend").rglob("*.py"):
        if "tests" in f.parts:
            continue
        src = io.open(f, encoding="utf-8", errors="replace").read()
        if "openrouter.ai" in src or "OpenRouterClient(" in src:
            trouves.add(f.relative_to(RACINE).as_posix())
    return trouves


def test_aucune_sortie_cloud_hors_des_fichiers_autorises():
    """Le garde-fou qui empêche de refaire A-1.

    Assertion volontairement structurelle : deux tests « le pare-feu a
    été appelé » n'auraient pas attrapé le défaut, parce que le défaut
    était un **troisième chemin** que personne n'avait pensé à tester.
    """
    trouves = _fichiers_touchant_openrouter()
    nouveaux = sorted(trouves - SORTIES_AUTORISEES)
    assert nouveaux == [], (
        f"nouveau chemin de sortie cloud : {nouveaux}. Soit il passe par "
        "`OpenRouterClient` — et alors il hérite du pare-feu —, soit il "
        "doit être ajouté à SORTIES_AUTORISEES avec la raison écrite.")


def test_les_deux_sorties_du_client_filtrent():
    """`chat` et `chat_events` appellent `_filtrer`. `chat_stream` délègue
    à `chat_events`, donc n'a pas à l'appeler lui-même."""
    source = io.open(RACINE / "backend/connectors/openrouter_client.py",
                     encoding="utf-8").read()
    arbre = ast.parse(source)
    for methode in ("chat", "chat_events"):
        noeud = next(n for n in ast.walk(arbre)
                     if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                     and n.name == methode)
        appels = {ast.unparse(c.func) for c in ast.walk(noeud)
                  if isinstance(c, ast.Call)}
        assert any(a.endswith("_filtrer") for a in appels), (
            f"{methode}() n'appelle pas le pare-feu")


def test_le_pare_feu_reste_une_seule_autorite():
    """Aucun second filtre : `_filtrer` délègue à `pare_feu.examiner`."""
    source = io.open(RACINE / "backend/connectors/openrouter_client.py",
                     encoding="utf-8").read()
    arbre = ast.parse(source)
    noeud = next(n for n in ast.walk(arbre)
                 if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                 and n.name == "_filtrer")
    appels = {ast.unparse(c.func) for c in ast.walk(noeud)
              if isinstance(c, ast.Call)}
    assert any("pare_feu.examiner" in a for a in appels), appels


def test_le_goulet_garde_son_role():
    """Le courtier, le quota et la publication restent au goulet : la
    garde du client ne les a pas absorbés."""
    source = io.open(RACINE / "backend/core/bootstrap/service_registry.py",
                     encoding="utf-8").read()
    for attendu in ("pare_feu.examiner", "_publier_la_decision",
                    "courtier", "broker.choisir"):
        assert attendu in source, f"{attendu} a disparu du goulet"
