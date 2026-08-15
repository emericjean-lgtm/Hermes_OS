"""Changer le niveau d'autonomie sans toucher à config/security.yaml (HOS-115).

Les quatre niveaux du §17.5 existent depuis le début et Aegis les applique
— mais rien ne permettait d'en changer sans éditer un fichier à la main et
redémarrer. Un garde-fou qu'on ne peut pas régler pendant qu'on travaille
se règle une fois pour toutes, au niveau le plus permissif dont on a eu
besoin un jour.

## Pourquoi un fichier séparé plutôt qu'une réécriture du YAML

`config/security.yaml` porte des dizaines de lignes de commentaires qui
expliquent *pourquoi* chaque catégorie est ce qu'elle est — le genre de
texte qu'un sérialiseur YAML détruit sans le dire. Le fichier reste donc
la valeur de référence, écrite par un humain ; ce module ne stocke que la
dérogation, dans un JSON d'une ligne.

Il est lisible et modifiable sans la base de données, délibérément : si
quelque chose va assez mal pour qu'on veuille resserrer l'autonomie, on ne
veut pas dépendre du reste du système pour y arriver.

## Ce que ce module ne fait pas

Il ne contourne rien. `mandatory_validation` reste obligatoire à tous les
niveaux — §17.3 —, et le niveau le plus permissif ne rend pas
auto-autorisée une suppression de fichier ou une migration de données. Le
curseur ne joue que sur les catégories qui déclarent un
`min_autonomy_for_auto_allow`.
"""
from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import Optional

logger = logging.getLogger("hermes_os.security.autonomy")

#: L'ordre du §17.5, du plus prudent au plus permissif. `AegisEngine` a le
#: même dans `_AUTONOMY_ORDER` ; celui-ci sert à valider une entrée avant
#: qu'elle n'arrive jusque-là, pour qu'un niveau inventé soit refusé au
#: bord plutôt que traité comme rang 0 en silence.
NIVEAUX: tuple[str, ...] = ("low", "medium", "high", "full")

#: Ce que chaque niveau change réellement, pour l'afficher à côté du
#: sélecteur. Écrit ici et non dans le frontend : la conséquence d'un choix
#: de sécurité appartient au module qui l'applique, pas à celui qui le
#: dessine.
EFFETS: dict[str, str] = {
    "low": "Tout ce qui modifie demande une validation humaine.",
    "medium": "L'écriture, la copie et les runners passent seuls ; "
              "suppression, déplacement et secrets restent à valider.",
    "high": "Tout ce qui déclare un seuil passe seul ; les catégories à "
            "validation obligatoire (§17.3) restent bloquées.",
    "full": "Identique à « high » côté seuils — §17.3 ne se contourne "
            "jamais, quel que soit le niveau.",
}

_verrou = threading.Lock()


def _chemin() -> Path:
    """Le fichier de dérogation, à côté des autres données du projet."""
    return Path(os.environ.get("HERMES_DATA_DIR", "data")) / "autonomy_override.json"


def lire_derogation() -> Optional[str]:
    """Le niveau choisi à l'exécution, ou None si personne n'en a choisi.

    Ne lève jamais : un fichier illisible doit ramener à la valeur du
    `security.yaml`, c'est-à-dire au réglage écrit par un humain, et non
    empêcher le démarrage. Un garde-fou dont la panne bloque le système
    finit par être retiré.
    """
    chemin = _chemin()
    try:
        niveau = json.loads(chemin.read_text(encoding="utf-8")).get("autonomy_level")
    except (OSError, ValueError, AttributeError):
        return None
    if niveau in NIVEAUX:
        return str(niveau)
    if niveau is not None:
        logger.warning("dérogation d'autonomie ignorée : niveau inconnu %r", niveau)
    return None


def ecrire_derogation(niveau: str) -> str:
    """Enregistrer un niveau, après l'avoir validé.

    Rend le niveau écrit, pour que l'appelant rapporte ce qui est
    réellement en vigueur plutôt que ce qu'il a demandé.
    """
    if niveau not in NIVEAUX:
        raise ValueError(
            f"niveau d'autonomie inconnu : {niveau!r} — attendus {list(NIVEAUX)}"
        )
    chemin = _chemin()
    with _verrou:
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_text(
            json.dumps({"autonomy_level": niveau}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    logger.info("niveau d'autonomie porté à %r", niveau)
    return niveau


def effacer_derogation() -> None:
    """Revenir à la valeur de `config/security.yaml`."""
    with _verrou:
        try:
            _chemin().unlink()
        except FileNotFoundError:
            pass
