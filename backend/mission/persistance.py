"""Les missions survivent au redémarrage (HOS-245, dette M-8).

## Le défaut : le journal survivait, son sujet non

HOS-221 a rendu le **registre des runs** durable, et HOS-240 lui a ajouté
une réconciliation au démarrage. Mais le registre des **missions** est
resté un `OrderedDict` en mémoire, borné à 200 avec éviction FIFO.

Un run posé `PERDU` par la réconciliation désignait donc une mission qui
n'existait plus. Et pas seulement après un redémarrage : au-delà de 200
missions, le FIFO évinçait pendant que le processus tournait toujours.
La trace survivait ; ce qu'elle décrit disparaissait.

## Ce que ce module n'est pas

Pas une seconde base : la table vit dans `hermes_os.db`, exactement là où
vivent déjà les `runs`, et par le même `DatabaseManager`. Deux fichiers
d'état auraient reproduit le défaut de HOS-237 — une base vivante, une
base morte, et rien pour dire laquelle fait foi.

Pas non plus un second registre : `_RegistreMissions` reste la seule API
que les appelants connaissent. Ce module est ce qu'il y a *derrière*, et
l'`OrderedDict` devient un cache.

## Pourquoi un document JSON, et pas vingt colonnes

Une mission porte un DAG : `nodes`, `edges`, un `context`, des
métadonnées libres, quatre horodatages et trois énumérations. La
normaliser en tables donnerait quatre tables et des jointures pour
reconstruire un objet que personne n'interroge par morceaux.

Le document JSON garantit ce que la consigne exige : la mission est
**reconstructible**, pas réduite à un sous-ensemble affichable. Les
colonnes scalaires à côté ne dupliquent pas le document par confort —
elles existent pour les seules questions qu'on pose vraiment en SQL :
« quelles missions, dans quel état, pour quel projet, dans quel ordre ».
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import fields, is_dataclass
from datetime import datetime
from typing import Any, Optional

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS missions (
    mission_id TEXT PRIMARY KEY,
    titre TEXT NOT NULL DEFAULT '',
    statut TEXT NOT NULL DEFAULT '',
    type TEXT NOT NULL DEFAULT '',
    priorite TEXT NOT NULL DEFAULT '',
    projet TEXT NOT NULL DEFAULT '',
    cree_le TEXT NOT NULL DEFAULT '',
    maj_le TEXT,
    document TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS missions_statut ON missions(statut, cree_le);
CREATE INDEX IF NOT EXISTS missions_projet ON missions(projet, cree_le);
"""


def _en_brut(valeur: Any) -> Any:
    """Descendre un dataclass jusqu'à du JSON, énumérations comprises.

    `dataclasses.asdict` ferait presque la même chose, mais il ne sait pas
    convertir une `datetime` et rendrait un objet que `json.dumps` refuse.
    """
    if isinstance(valeur, datetime):
        return valeur.isoformat()
    if hasattr(valeur, "value") and hasattr(valeur, "name"):  # Enum
        return valeur.value
    if is_dataclass(valeur) and not isinstance(valeur, type):
        return {c.name: _en_brut(getattr(valeur, c.name)) for c in fields(valeur)}
    if isinstance(valeur, (list, tuple)):
        return [_en_brut(v) for v in valeur]
    if isinstance(valeur, dict):
        return {str(c): _en_brut(v) for c, v in valeur.items()}
    return valeur


def _en_objet(classe: Any, brut: Any) -> Any:
    """Reconstruire un dataclass depuis son document.

    Les champs absents gardent leur défaut, et les champs inconnus sont
    **ignorés** : une base écrite par une version antérieure doit se
    relire, et une version antérieure ne doit pas s'étrangler sur un champ
    ajouté depuis. C'est la même tolérance que
    `memory.db._add_missing_columns` applique aux colonnes.
    """
    if not isinstance(brut, dict):
        return brut
    connus = {c.name: c for c in fields(classe)}
    valeurs: dict[str, Any] = {}
    for nom, valeur in brut.items():
        champ = connus.get(nom)
        if champ is None:
            continue
        valeurs[nom] = _convertir(champ.type, valeur)
    return classe(**valeurs)


def _convertir(annotation: Any, valeur: Any) -> Any:
    """Rendre à une valeur brute le type que son champ déclare."""
    from backend.mission.mission_models import (
        MissionContext,
        MissionEdge,
        MissionNode,
        MissionPriority,
        MissionStatus,
        MissionType,
        NodeStatus,
    )

    texte = annotation if isinstance(annotation, str) else getattr(
        annotation, "__name__", str(annotation))

    if valeur is None:
        return None
    for nom, enumeration in (("MissionStatus", MissionStatus),
                             ("MissionPriority", MissionPriority),
                             ("MissionType", MissionType),
                             ("NodeStatus", NodeStatus)):
        if nom in texte:
            try:
                return enumeration(valeur)
            except ValueError:
                # Un statut écrit par une version qui en connaissait un de
                # plus : le refuser ferait perdre toute la mission pour un
                # champ. Le défaut du dataclass reprend la main.
                logger.warning("statut de mission inconnu %r — ignoré", valeur)
                return None
    if "MissionContext" in texte:
        return _en_objet(MissionContext, valeur)
    if "MissionNode" in texte:
        return [_en_objet(MissionNode, v) for v in (valeur or [])]
    if "MissionEdge" in texte:
        return [_en_objet(MissionEdge, v) for v in (valeur or [])]
    if "datetime" in texte and isinstance(valeur, str):
        try:
            return datetime.fromisoformat(valeur)
        except ValueError:
            return None
    return valeur


class MagasinMissions:
    """La source durable. `_RegistreMissions` est son cache."""

    def __init__(self, db: Any = None) -> None:
        from backend.storage.database_manager import DatabaseManager

        self._db = db or DatabaseManager()
        self._db.initialize()
        self._verrou = threading.RLock()
        conn = self._db.get_connection()
        conn.executescript(_SCHEMA)
        self._ajouter_les_colonnes_manquantes(conn)
        conn.commit()

    @staticmethod
    def _ajouter_les_colonnes_manquantes(conn) -> None:
        """`CREATE TABLE IF NOT EXISTS` ne touche pas une base existante.

        Le même mécanisme que `runs.registre` (HOS-240) et
        `memory.db._add_missing_columns`, et pour la même raison : ce dépôt
        fait évoluer ses schémas à chaud. Additif et nullable seulement.
        """
        presentes = {ligne[1] for ligne in conn.execute(
            "PRAGMA table_info(missions)")}
        for nom, type_sql in (("maj_le", "TEXT"),):
            if nom not in presentes:
                conn.execute(
                    f"ALTER TABLE missions ADD COLUMN {nom} {type_sql}")

    # ── Écriture ─────────────────────────────────────────────────────

    def enregistrer(self, mission: Any) -> None:
        """Écrire ou réécrire une mission.

        Contrairement au registre des runs, une mission **se réécrit** :
        son statut et ses nœuds évoluent pendant l'exécution, et c'est le
        dernier état qui fait foi. Le gel terminal de HOS-221 protège une
        trace d'exécution close ; une mission n'en est pas une.
        """
        document = json.dumps(_en_brut(mission), ensure_ascii=False)
        contexte = getattr(mission, "context", None)
        with self._verrou:
            self._db.execute(
                "INSERT OR REPLACE INTO missions (mission_id, titre, statut, "
                "type, priorite, projet, cree_le, maj_le, document) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (mission.mission_id,
                 getattr(mission, "title", "") or "",
                 _valeur(getattr(mission, "status", "")),
                 _valeur(getattr(mission, "type", "")),
                 _valeur(getattr(mission, "priority", "")),
                 getattr(contexte, "project_id", "") or "",
                 _horodatage(getattr(mission, "created_at", None)),
                 _horodatage(getattr(mission, "updated_at", None)),
                 document))

    def supprimer(self, mission_id: str) -> None:
        """Une suppression **voulue par l'appelant**, jamais une éviction.

        L'éviction du cache ne passe pas par ici : c'est tout l'objet de ce
        module. `_RegistreMissions._evincer` libère de la mémoire ; la
        ligne reste.
        """
        with self._verrou:
            self._db.execute("DELETE FROM missions WHERE mission_id = ?",
                             (mission_id,))

    def vider(self) -> None:
        """Pour les tests, qui appellent `_missions.clear()`.

        Sans cela, un test fuirait ses missions dans la base des suivants —
        et la suite deviendrait dépendante de son ordre d'exécution.
        """
        with self._verrou:
            self._db.execute("DELETE FROM missions")

    # ── Lecture ──────────────────────────────────────────────────────

    def lire(self, mission_id: str) -> Optional[Any]:
        ligne = self._db.fetch_one(
            "SELECT document FROM missions WHERE mission_id = ?", (mission_id,))
        return self._depuis(ligne) if ligne else None

    def tous(self) -> list[Any]:
        """Toutes les missions, les plus récentes d'abord."""
        return [m for m in (self._depuis(l) for l in self._db.fetch_all(
            "SELECT document FROM missions ORDER BY cree_le DESC")) if m]

    def identifiants(self) -> list[str]:
        return [dict(l)["mission_id"] for l in self._db.fetch_all(
            "SELECT mission_id FROM missions ORDER BY cree_le DESC")]

    def nombre(self) -> int:
        ligne = self._db.fetch_one("SELECT COUNT(*) AS n FROM missions")
        return int(dict(ligne)["n"]) if ligne else 0

    @staticmethod
    def _depuis(ligne: Any) -> Optional[Any]:
        from backend.mission.mission_models import Mission

        try:
            return _en_objet(Mission, json.loads(dict(ligne)["document"]))
        except Exception:  # pragma: no cover - document corrompu
            logger.warning("mission illisible en base — ignorée", exc_info=True)
            return None


def _valeur(brut: Any) -> str:
    return str(getattr(brut, "value", brut) or "")


def _horodatage(brut: Any) -> Optional[str]:
    return brut.isoformat() if isinstance(brut, datetime) else None


__all__ = ["MagasinMissions"]
