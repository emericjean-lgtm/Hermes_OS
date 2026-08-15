"""Résumer le passé d'une conversation au lieu de le couper (§12, HOS-120).

Le §12 du cahier des charges exige de « résumer automatiquement le contexte
trop long » et de « tronquer intelligemment sans perte d'information
critique (résumer les parties les moins récentes plutôt que couper
brutalement) ».

`build_model_messages` faisait exactement l'inverse :

    history = session.messages[-MAX_HISTORY_MESSAGES:]

Les tours les plus anciens disparaissaient purement et simplement. Au
vingt-et-unième message, le premier — souvent celui qui pose le sujet, la
contrainte ou le fichier concerné — cessait d'exister pour le modèle, sans
que rien ne le signale. C'est le seul critère d'acceptation du §28 qui
n'avait jamais été construit.

## Ce que ce module ne fait pas

Il ne fabrique pas de résumé. `resumer()` fait **un vrai appel au modèle**
et rend `None` s'il échoue — jamais une reconstitution heuristique qui
aurait l'apparence d'un résumé sans en être un. Un contexte inventé est
pire qu'un contexte tronqué : le second se voit, le premier se lit comme
un souvenir.

L'appelant qui reçoit `None` doit retomber sur la coupe et **le dire**,
pas faire comme si de rien n'était.

## Pourquoi le plus petit modèle

Résumer n'est pas raisonner. `swift` (lfm2.5-2.6b-125k, mesuré 187,6 tok/s
et 4,5 s de chargement) tient l'extraction au même niveau que les grands —
neuf modèles sur dix atteignent le palier maximal de cet axe, c'est la
mesure qui a fait passer `extraction` et `rephrase` en tête de `swift`
dans `config/models.yaml`. Faire résumer par le modèle de conversation
coûterait sa latence à chaque fois qu'un seuil est franchi.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Optional, Sequence

logger = logging.getLogger("hermes_os.conversation.context")

#: Tours gardés mot pour mot. En deçà, rien n'est résumé : une conversation
#: courte n'a rien à compresser, et la résumer coûterait un appel modèle
#: pour rien.
TOURS_GARDES = 12

#: Il faut au moins ça d'ancien pour qu'un résumé vaille son appel. Résumer
#: deux messages produit un texte plus long que les messages eux-mêmes.
MINIMUM_A_RESUMER = 4

_INSTRUCTION = (
    "Voici le début d'une conversation entre un utilisateur et un assistant. "
    "Résume-la en faits, pour qu'un assistant qui n'a pas lu ces échanges "
    "puisse reprendre sans rien redemander.\n\n"
    "Garde impérativement : ce que l'utilisateur veut, les contraintes et "
    "préférences qu'il a exprimées, les décisions prises, les fichiers, "
    "chemins, noms et valeurs cités, et ce qui reste en suspens.\n"
    "Retire : les formules de politesse, les reformulations, les hésitations.\n\n"
    "N'invente rien. Si un point est resté indécis, écris-le comme indécis "
    "plutôt que de le trancher.\n\n"
    "Réponds par le résumé seul, sans préambule."
)


def decouper(messages: Sequence[Any], *, tours_gardes: int = TOURS_GARDES
             ) -> tuple[list[Any], list[Any]]:
    """(à résumer, à garder tel quel).

    Rend une première liste vide tant qu'il n'y a pas assez d'ancien : mieux
    vaut une conversation intégralement transmise qu'un résumé qui coûte un
    appel et n'économise rien.
    """
    if len(messages) <= tours_gardes + MINIMUM_A_RESUMER:
        return [], list(messages)
    coupe = len(messages) - tours_gardes
    return list(messages[:coupe]), list(messages[coupe:])


def _transcrire(messages: Sequence[Any]) -> str:
    lignes = []
    for message in messages:
        role = getattr(getattr(message, "role", None), "value", None) or "?"
        contenu = (getattr(message, "content", "") or "").strip()
        if contenu:
            lignes.append(f"{role}: {contenu}")
    return "\n".join(lignes)


async def resumer(
    anciens: Sequence[Any],
    *,
    chat: Callable[..., Any],
    model: str,
    num_ctx: int = 16384,
) -> Optional[str]:
    """Un appel modèle, ou `None`.

    Ne lève jamais et ne fabrique jamais : une panne de résumé doit
    dégrader la conversation, pas la casser — et surtout pas y injecter un
    passé reconstitué.
    """
    transcription = _transcrire(anciens)
    if not transcription:
        return None
    try:
        reponse = await chat(
            messages=[
                {"role": "system", "content": _INSTRUCTION},
                {"role": "user", "content": transcription},
            ],
            model=model,
            num_ctx=num_ctx,
        )
    except Exception:
        logger.warning("résumé de contexte indisponible — la conversation "
                       "sera tronquée et le dira", exc_info=True)
        return None

    texte = reponse.get("content") if isinstance(reponse, dict) else getattr(
        reponse, "content", "")
    texte = (texte or "").strip()
    if not texte:
        logger.warning("le modèle a rendu un résumé vide — traité comme une "
                       "absence de résumé, pas comme un résumé vide")
        return None
    return texte


def bloc_systeme(resume: str, nombre_resume: int) -> dict[str, str]:
    """Le résumé, présenté au modèle pour ce qu'il est.

    Étiqueté explicitement comme un résumé et non comme des tours réels :
    un modèle qui le prendrait pour une transcription pourrait citer
    l'utilisateur sur des mots qu'il n'a pas dits.
    """
    return {
        "role": "system",
        "content": (
            f"Résumé des {nombre_resume} premiers messages de cette "
            f"conversation (ce n'est pas une transcription, ne cite personne "
            f"à partir de ce texte) :\n\n{resume}"
        ),
    }


def bloc_troncature(nombre_perdu: int) -> dict[str, str]:
    """Ce qu'on dit quand le résumé n'a pas pu être produit.

    Le silence était le comportement précédent : les messages
    disparaissaient et le modèle répondait comme s'ils n'avaient jamais
    existé. Annoncer le trou permet au moins de redemander.
    """
    return {
        "role": "system",
        "content": (
            f"{nombre_perdu} message(s) plus anciens de cette conversation "
            "ne sont pas disponibles et n'ont pas pu être résumés. Si la "
            "question porte dessus, dis-le et demande à l'utilisateur de "
            "rappeler l'élément manquant plutôt que de supposer."
        ),
    }
