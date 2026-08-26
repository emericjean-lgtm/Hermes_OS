"""L'opérateur du Cockpit doit guetter des topics qui existent (HOS-182).

Le Cockpit affiche une figure dont la posture suit ce que fait le système :
elle lit quand un fichier est lu, elle écrit quand un fichier est écrit. La
correspondance vit dans `frontend/src/hooks/use-operateur.ts`, sous forme
d'une table topic → posture.

Une table écrite de mémoire est un écran qui ne bougera jamais, sans que
rien ne le signale — et c'est exactement ce qui s'est produit à la première
rédaction : elle guettait `mission.started`, `files_read` et
`mission/verification`, trois noms qui n'existent nulle part dans ce
backend. Les vrais sont `execution.task_started`, `filesystem.read`, et
pour la vérification : *aucun*.

Ce test franchit la frontière des deux langages parce que c'est là qu'est
le risque. Les noms d'événements sont produits par Python ; les tests
TypeScript ne peuvent que recopier cette liste, et une copie ne prouve rien
sur l'original. Ici on lit le fichier TypeScript et on confronte ses clés à
`collect_known_topics()`.

Un topic retiré du backend fait échouer ce test avec son nom ; la
réparation consiste à retirer la ligne correspondante de la table du
Cockpit, pas à réintroduire un topic mort.
"""

from __future__ import annotations

import io
import os
import re

import pytest

from backend.core.bootstrap.event_wiring import collect_known_topics

RACINE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TABLE_TS = os.path.join(RACINE, "frontend", "src", "hooks", "use-operateur.ts")

# `"topic.pointé": { etat: "posture", tenue: 1234 },`
LIGNE = re.compile(
    r'"(?P<topic>[a-z_]+\.[a-z_.]+)"\s*:\s*\{\s*etat:\s*"(?P<etat>[a-z]+)"'
)


def _table() -> dict[str, str]:
    if not os.path.exists(TABLE_TS):
        pytest.skip("frontend absent de cette copie de travail")
    source = io.open(TABLE_TS, encoding="utf-8").read()
    return {m.group("topic"): m.group("etat") for m in LIGNE.finditer(source)}


def test_chaque_topic_guette_par_le_cockpit_existe_vraiment():
    table = _table()
    assert table, (
        "aucune entrée lue dans use-operateur.ts — la forme de la table a "
        "changé et ce test ne vérifie donc plus rien"
    )

    connus = collect_known_topics()
    fantomes = sorted(t for t in table if t not in connus)

    assert not fantomes, (
        f"{len(fantomes)} topic(s) guettés par l'opérateur du Cockpit "
        "n'existent pas côté backend.\n"
        "La figure ne prendra jamais ces postures, et rien ne le dira :\n"
        + "\n".join(f"  {t}  ->  posture « {table[t]} »" for t in fantomes)
    )


def test_la_table_couvre_ce_qui_fait_une_mission():
    """Guetter les bons noms ne suffit pas s'il en manque l'essentiel.

    Un test qui n'exigerait que l'existence resterait vert sur une table
    vidée de tout ce qui compte.
    """
    familles = {t.split(".")[0] for t in _table()}
    for f in ("filesystem", "execution", "task", "autonomous", "model", "runtime"):
        assert f in familles, f"l'opérateur ne guette aucun topic {f}.*"


def test_les_ecritures_sur_disque_sont_toutes_guettees():
    """Les six opérations qui modifient le disque, sans exception.

    C'est la famille qui a motivé HOS-181 : elle était intégralement jetée
    par la liste blanche, si bien qu'aucune écriture n'était visible. En
    oublier une reviendrait à rendre ce chemin muet de nouveau, sur une
    seule opération cette fois — donc plus difficile à voir.
    """
    table = _table()
    for op in ("write", "create", "copy", "move", "delete"):
        topic = f"filesystem.{op}"
        assert topic in table, f"{topic} n'est pas guetté"
        assert table[topic] == "ecriture", (
            f"{topic} devrait produire « ecriture », pas « {table[topic]} »"
        )
