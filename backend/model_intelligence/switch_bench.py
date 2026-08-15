"""Le prix d'une bascule de modèle, mesuré (HOS-114).

Sur 16 Go et `OLLAMA_MAX_LOADED_MODELS=1`, un seul modèle est résident :
servir une tâche avec un autre modèle veut dire décharger celui qui est là
puis charger le nouveau. Le routeur arbitrait jusqu'ici sans connaître ce
prix — il changeait de modèle dès qu'un « meilleur » existait, que la
tâche en ait besoin ou non.

Ce module le chiffre. Il ne juge aucune compétence : c'est une mesure de
coût, pas un axe du catalogue, et elle ne va donc pas dans le
`BenchStore`.

## Pourquoi `load_duration` et non l'horloge murale

Ollama rapporte lui-même le temps passé à charger, séparé du temps
d'inférence. Vérifié avant de s'en servir : à froid 4,47 s contre 0,29 s à
chaud sur lfm2.5, 19,38 contre 0,51 sur gpt-oss — un ordre de grandeur, et
la somme colle à l'horloge murale du même appel. Un chiffre rapporté qui
ne bougerait pas entre les deux cas n'aurait rien mesuré.

## Ce que la bascule coûte de plus qu'un chargement à froid

Mesuré : décharger le modèle en place ajoute ~1,8 s au chargement du
suivant. La bascule vaut donc *à peu près* le chargement du modèle cible,
et ce dernier domine largement — 20 s pour gpt-oss, 6 s pour lfm2.5.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Optional

#: Assez court pour ne rien mesurer d'autre que le chargement, assez concret
#: pour que le modèle réponde au lieu de partir en raisonnement.
AMORCE = "Reponds par le seul mot: ok"


@dataclass(frozen=True)
class CoutBascule:
    model: str
    num_ctx: int
    #: Chargement mesuré par Ollama, en secondes, modèle absent de la VRAM.
    froid_s: float
    #: Le même appel, modèle déjà résident. Doit être proche de zéro : c'est
    #: le témoin qui prouve que `froid_s` mesure bien un chargement.
    chaud_s: float

    @property
    def credible(self) -> bool:
        """Un écart d'au moins un ordre de grandeur entre froid et chaud.

        Sans lui la mesure ne distingue pas les deux cas, et un routeur qui
        s'y fierait arbitrerait sur du bruit.
        """
        return self.froid_s >= 10 * max(self.chaud_s, 1e-6)

    def as_dict(self) -> dict[str, Any]:
        return {"model": self.model, "num_ctx": self.num_ctx,
                "froid_s": round(self.froid_s, 2),
                "chaud_s": round(self.chaud_s, 2),
                "credible": self.credible}


def _secondes_de_chargement(payload: dict) -> float:
    """`load_duration` est en nanosecondes ; absent, c'est zéro."""
    return float(payload.get("load_duration") or 0) / 1e9


def mesurer(
    model: str,
    num_ctx: int,
    *,
    generate: Callable[..., dict],
    unload: Callable[[str], None],
    pause_s: float = 0.0,
) -> CoutBascule:
    """Le coût de chargement de `model`, à froid puis à chaud.

    `generate` et `unload` sont injectés : ce module se teste sans Ollama,
    et le banc réel lui passe ceux de `model_bench`.
    """
    unload(model)
    if pause_s:
        time.sleep(pause_s)
    froid = _secondes_de_chargement(generate(model, AMORCE, num_ctx=num_ctx))
    chaud = _secondes_de_chargement(generate(model, AMORCE, num_ctx=num_ctx))
    return CoutBascule(model=model, num_ctx=num_ctx, froid_s=froid, chaud_s=chaud)


def campagne(
    modeles: Iterable[tuple[str, int]],
    *,
    generate: Callable[..., dict],
    unload: Callable[[str], None],
    on_result: Optional[Callable[[CoutBascule], None]] = None,
) -> list[CoutBascule]:
    """Un modèle à la fois, sans exception.

    Deux chargements concurrents sur 16 Go mesureraient la contention, pas
    le chargement — c'est la règle qui vaut pour toutes les campagnes de ce
    dépôt.
    """
    resultats: list[CoutBascule] = []
    for model, num_ctx in modeles:
        cout = mesurer(model, num_ctx, generate=generate, unload=unload)
        resultats.append(cout)
        if on_result is not None:
            on_result(cout)
    return resultats
