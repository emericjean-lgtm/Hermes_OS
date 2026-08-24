"""Une notification JSON-RPC de plus de 64 Kio faisait perdre le tour (HOS-160).

Campagne Skill360 du 2026-08-24, §12 :

    harnais : tour non abouti [1 d'affilee] ValueError: Separator is found,
    but chunk is longer than limit
    dernier signe : API call #284 ... in=43141 out=29 total=43170

`asyncio` donne 65536 octets de tampon par defaut a ses `StreamReader`, et
`readline()` leve des qu'une ligne depasse cette taille. Le protocole ACP
transporte **une notification par ligne**, et ces notifications portent le
contenu des fichiers lus, les resultats d'outils et les reponses du modele :
quarante mille jetons de contexte produisent sans peine une ligne plus
longue.

Le tour etait perdu alors que le contenu etait la, entier, de l'autre cote
du tube.
"""
from __future__ import annotations

import asyncio
import sys

import pytest

from backend.ral.adapters.hermes_agent_acp import TAMPON_FLUX


async def _lire_une_ligne(octets: int, limite: int) -> int:
    """Combien d'octets `readline()` rend pour une ligne de cette taille."""
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-c", f"print('x' * {octets})",
        stdout=asyncio.subprocess.PIPE, limit=limite)
    try:
        return len(await proc.stdout.readline())
    finally:
        await proc.wait()


def test_la_limite_par_defaut_perd_une_grande_ligne() -> None:
    """L'incident : ce que faisait le client avant la correction.

    Ce test tient la **cause**, pas seulement le remede. Sans lui, un
    retour a la limite par defaut passerait inapercu — c'est un reglage
    invisible dont l'absence ne casse rien tant que les lignes sont
    courtes.
    """
    with pytest.raises(ValueError, match="chunk"):
        asyncio.run(_lire_une_ligne(200_000, 65536))


def test_le_tampon_du_client_lit_la_meme_ligne() -> None:
    lu = asyncio.run(_lire_une_ligne(200_000, TAMPON_FLUX))

    assert lu > 200_000


def test_le_tampon_couvre_largement_ce_qui_a_echoue() -> None:
    """Trois ordres de grandeur au-dessus de la ligne qui a fait perdre le tour.

    Et negligeable en memoire : une session d'agent occupe deja 220 Mio, et
    ce tampon est un plafond, pas une reservation.
    """
    assert TAMPON_FLUX >= 8 * 1024 * 1024


def test_le_client_passe_bien_ce_tampon_au_processus() -> None:
    """Le reglage doit atteindre `create_subprocess_exec`, pas seulement exister.

    Un module qui definirait la constante sans la transmettre serait vert
    ici et casse en production — exactement le defaut que les tests du
    garde-fou de workspace avaient laisse passer.
    """
    import inspect

    from backend.ral.adapters import hermes_agent_acp

    source = inspect.getsource(hermes_agent_acp.HermesAgentACP.ouvrir)
    assert "limit=TAMPON_FLUX" in source
