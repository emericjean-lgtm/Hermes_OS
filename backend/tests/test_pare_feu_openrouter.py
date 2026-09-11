"""Le pare-feu reconnaît la clé d'OpenRouter lui-même (A-10, HOS-290).

## Le défaut, mesuré avant d'écrire une ligne

A-1 (HOS-255) a rendu le pare-feu **inévitable** : `chat` et
`chat_events` l'appellent en première instruction, donc tout appelant y
passe. Ce fichier-ci ne rejoue pas ce routage — `test_pare_feu_inevitable`
le fait. Il ferme le défaut que A-1 avait mesuré **au passage** et
consigné sans le corriger : le pare-feu reconnaissait `sk-…` et laissait
passer `sk-or-v1-…`, le format de clé d'OpenRouter.

La cause est d'un caractère. Le motif de `audit_log._SECRET_PATTERNS`
était `\\bsk-[A-Za-z0-9]{16,}\\b`, et `-` n'est pas dans la classe : après
`sk-`, le moteur lit `or`, bute sur le tiret, et `{16,}` échoue. Un
pare-feu aveugle à la clé de son propre fournisseur.

Relevé au commit `25ddb52`, avant correctif, sur `pare_feu.examiner` :

    sk-<32 alnum>                 → REFUSE      (A-1, déjà correct)
    sk-or-v1-<64 hex>             → AUTORISE    ← le défaut
    … aux 8 placements essayés    → AUTORISE

## Ce que ce fichier prouve, et à quel niveau

L'échelle du §0 veut la preuve au niveau `ACTUALLY USED`, pas
`PRESENT` : `redact("sk-or-v1-…") != texte` ne démontrerait rien sur le
chemin réel. Les cas ci-dessous passent donc par `OpenRouterClient`
avec un transport qui **compte les requêtes réellement émises**, et
l'assertion qui compte est `transport.appels == 0`.

## Une seule autorité

Le correctif est une ligne de `audit_log._SECRET_PATTERNS`. Ni second
scanner, ni détecteur OpenRouter dédié, ni règle dans `pare_feu` : ce
module délègue déjà à `redact` en le nommant « le plus proche d'un
`secret_scanner` que ce dépôt possède », et en écrire un second,
divergent, serait pire que le réutiliser.

**Aucune valeur réelle ici.** Les clés sont fabriquées dans ce fichier.
"""

from __future__ import annotations

import httpx
import pytest

from backend.connectors.openrouter_client import (
    OpenRouterClient,
    OpenRouterUnavailableError,
)
from backend.core.audit_log import redact
from backend.security import pare_feu

# ── Matériel synthétique ─────────────────────────────────────────────
#
# Fabriqué ici, caractère par caractère. Rien n'est lu depuis
# l'environnement, un fichier de configuration ou un magasin : un test
# qui a besoin d'un vrai secret pour prouver qu'il protège les secrets
# est un test qui en fait fuiter un.
_HEX64 = "0123456789abcdef" * 4

#: La forme réelle d'OpenRouter : `sk-or-v1-` + 64 hexadécimaux.
CLE_OPENROUTER = "sk-or-v1-" + _HEX64
#: La forme qu'A-1 couvrait déjà. Sa présence ici est une garde de
#: non-régression : élargir un motif casse facilement ce qu'il prenait.
CLE_OPENAI = "sk-" + "A1b2C3d4E5f6G7h8" * 2
#: Un autre fournisseur, même grammaire. Couvert par effet de bord du
#: correctif, et vérifié plutôt que supposé.
CLE_ANTHROPIC = "sk-ant-api03-" + _HEX64


class _Transport(httpx.MockTransport):
    """Un OpenRouter qui note ce qu'on lui a réellement envoyé.

    `appels` est la mesure qui décide : une requête partie est une fuite,
    quelle que soit l'exception levée ensuite.
    """

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
                return httpx.Response(
                    200, content=corps,
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


# ═══ A — le détecteur, au niveau où le défaut vivait ═════════════════

@pytest.mark.parametrize("nom,texte", [
    ("nue", CLE_OPENROUTER),
    ("en début de message", CLE_OPENROUTER + " est la clé"),
    ("au milieu", "avant " + CLE_OPENROUTER + " après"),
    ("en fin", "la clé est " + CLE_OPENROUTER),
    ("entre guillemets", 'key="' + CLE_OPENROUTER + '"'),
    ("après deux-points", "OPENROUTER_KEY: " + CLE_OPENROUTER),
    ("suivie d'un point", "utilise " + CLE_OPENROUTER + "."),
    ("dans une URL", "https://exemple/?k=" + CLE_OPENROUTER),
    ("dans un bloc JSON", '{"api_key": "' + CLE_OPENROUTER + '"}'),
    ("précédée d'un retour ligne", "clé :\n" + CLE_OPENROUTER),
])
def test_A_la_cle_openrouter_est_reconnue_ou_qu_elle_soit(nom, texte):
    """Huit placements étaient autorisés avant le correctif. La position
    ne doit rien changer : un secret en fin de prompt part aussi bien
    qu'un secret au début."""
    assert redact(texte) != texte, f"clé OpenRouter non détectée {nom}"
    assert CLE_OPENROUTER not in redact(texte), (
        "la valeur survit au caviardage")


def test_A_le_verdict_du_pare_feu_est_un_refus():
    """Détecter ne suffit pas : le pare-feu doit en tirer REFUSE, et
    rendre `messages` vide — pour qu'un appelant distrait qui enverrait
    quand même n'envoie rien."""
    d = pare_feu.examiner([{"role": "user", "content": CLE_OPENROUTER}])
    assert d.verdict is pare_feu.Verdict.REFUSE
    assert d.envoyable is False
    assert d.messages == []


def test_A_le_rapport_ne_cite_jamais_la_valeur():
    """Un rapport de fuite qui cite le secret est une seconde fuite
    (HOS-218). La règle vaut aussi pour le nouveau motif."""
    d = pare_feu.examiner([{"role": "user", "content": CLE_OPENROUTER}])
    trace = d.raison + " " + d.resume() + " " + " ".join(
        c.apercu for c in d.constats)
    assert CLE_OPENROUTER not in trace
    assert _HEX64 not in trace


# ═══ B — le chemin réel « chat » ═════════════════════════════════════

@pytest.mark.asyncio
async def test_B_chat_refuse_la_cle_openrouter_sans_rien_emettre():
    """La preuve qui compte : `appels == 0`. Le refus doit intervenir
    **avant** l'émission, sinon c'est un constat de fuite."""
    client, t = _client()
    with pytest.raises(OpenRouterUnavailableError) as capture:
        await client.chat([{"role": "user", "content": CLE_OPENROUTER}],
                          model="m")
    assert "pare-feu" in str(capture.value)
    assert t.appels == 0, "une requête est partie malgré le refus"
    assert t.recu == []


@pytest.mark.asyncio
async def test_B_chat_refuse_meme_noyee_dans_un_contexte_realiste():
    """La structure réelle d'un prompt : un `system`, un `user`, et le
    secret dans le second. Un pare-feu qui n'examinerait que le premier
    message laisserait passer exactement ça."""
    client, t = _client()
    with pytest.raises(OpenRouterUnavailableError):
        await client.chat([
            {"role": "system", "content": "Tu es un agent de développement."},
            {"role": "user",
             "content": "voici ma config :\nOPENROUTER_API_KEY="
                        + CLE_OPENROUTER + "\nrésume-la"},
        ], model="m")
    assert t.appels == 0


# ═══ C — le chemin réel « chat_events » ══════════════════════════════

@pytest.mark.asyncio
async def test_C_chat_events_refuse_la_cle_openrouter_sans_rien_emettre():
    """Le chemin de repli de `BaseAgent` : celui qui, avant A-1,
    n'était filtré par rien."""
    client, t = _client(flux=True)
    with pytest.raises(OpenRouterUnavailableError) as capture:
        await _diffuser(client,
                        messages=[{"role": "user", "content": CLE_OPENROUTER}])
    assert "pare-feu" in str(capture.value)
    assert t.appels == 0
    assert t.recu == []


@pytest.mark.asyncio
async def test_C_chat_stream_herite_du_refus():
    """`chat_stream` délègue à `chat_events` : il hérite du motif neuf
    sans qu'on l'y répète."""
    client, t = _client(flux=True)
    with pytest.raises(OpenRouterUnavailableError):
        async for _ in client.chat_stream(
                "m", [{"role": "user", "content": CLE_OPENROUTER}]):
            pass
    assert t.appels == 0


@pytest.mark.asyncio
async def test_C_l_adaptateur_ral_refuse_aussi():
    """Le fournisseur du goulet construit ce même client."""
    from backend.ral.adapters.openrouter import RuntimeOpenRouter

    t = _Transport()
    f = RuntimeOpenRouter("cle-de-test", transport=t)
    with pytest.raises(Exception) as capture:
        await f.chat([{"role": "user", "content": CLE_OPENROUTER}], model="m")
    assert t.appels == 0
    assert "pare-feu" in str(capture.value)


# ═══ D — non-régression A-1 ══════════════════════════════════════════

@pytest.mark.asyncio
async def test_D_la_forme_deja_couverte_reste_refusee():
    """Élargir un motif casse facilement ce qu'il prenait déjà."""
    client, t = _client()
    with pytest.raises(OpenRouterUnavailableError):
        await client.chat([{"role": "user", "content": CLE_OPENAI}], model="m")
    assert t.appels == 0


def test_D_un_autre_fournisseur_de_meme_grammaire_est_pris():
    """`sk-ant-api03-…` a la même forme. Vérifié, pas supposé."""
    assert redact(CLE_ANTHROPIC) != CLE_ANTHROPIC


# ═══ E — les faux positifs restent autorisés ═════════════════════════

@pytest.mark.parametrize("nom,texte", [
    ("le préfixe cité en prose", "le préfixe sk-or identifie OpenRouter"),
    ("le format documenté", "le format d'OpenRouter est sk-or-v1-<hex>"),
    ("un mot composé", "un profil risk-reward intéressant"),
    ("un sk- trop court", "identifiant sk-abc123 dans le ticket"),
    ("une clé tronquée", "extrait : sk-or-v1-0123abcd (tronqué)"),
    ("une phrase parlant de clés", "ne colle jamais ta clé OpenRouter ici"),
    ("un nom de variable seul", "lis OPENROUTER_API_KEY dans l'environnement"),
])
def test_E_les_textes_legitimes_ne_sont_pas_caviardes(nom, texte):
    """Un pare-feu qui refuse tout est un pare-feu qu'on désarme dans la
    semaine. Ces sept textes sont ceux qu'un développeur écrit vraiment
    en parlant d'OpenRouter — s'ils bloquaient, la règle serait retirée
    et le trou rouvert."""
    assert redact(texte) == texte, f"faux positif : {nom}"


@pytest.mark.asyncio
async def test_E_un_message_legitime_part_bien():
    """Le cas passant, sur le chemin réel : le message traverse et
    arrive intact au fournisseur."""
    client, t = _client()
    message = "explique le format des clés d'API sans en citer une"
    reponse = await client.chat([{"role": "user", "content": message}],
                                model="m")
    assert t.appels == 1, "le message légitime n'est jamais parti"
    assert t.recu[0]["messages"][0]["content"] == message, (
        "le pare-feu a modifié un message qu'il autorisait")
    assert reponse.content == "ok"


@pytest.mark.asyncio
async def test_E_un_flux_legitime_part_bien():
    """Même chose sur `chat_events` : autoriser doit laisser le flux
    intact, pas seulement ne pas lever."""
    client, t = _client(flux=True)
    message = "décris la structure d'un message OpenRouter"
    morceaux = await _diffuser(
        client, messages=[{"role": "user", "content": message}])
    assert t.appels == 1
    assert t.recu[0]["messages"][0]["content"] == message
    assert any(m.kind == "content" for m in morceaux)
