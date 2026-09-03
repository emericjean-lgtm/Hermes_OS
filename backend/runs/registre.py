"""Ce que Hermes a fait, avec quoi, et pourquoi ça a échoué (HOS-221).

## Le manque, démontré en production

La nuit du 29 au 30 août, trois fois, la question « qu'est-ce qui a été
fait, avec quel modèle, et pourquoi le premier essai a raté ? » n'avait
pas de réponse sans aller lire des fichiers JSON **écrasés à chaque
exécution**. J'ai dû écrire l'archivage du journal en pleine nuit, pendant
que la production tournait, parce que la trace disparaissait.

Un run est l'unité qui manquait : une tentative d'exécution, avec son
modèle, son runtime, son coût, son issue, et **son parent** quand c'est
une reprise.

## Ce qui est repris d'Agent OS, et ce qui ne l'est pas

**Repris : l'invariant d'état, écrit dans le SQL.**

    UPDATE runs SET statut = CASE
      WHEN statut IN (états terminaux) THEN statut
      ELSE ? END

Un état terminal ne peut pas être réécrit, et la garantie vit dans la
requête — donc aucun chemin oublié ne peut la contourner. C'est plus
solide qu'une vérification en Python, qu'il suffit d'oublier une fois.

**Pas repris : leur table `run_events`.** Hermes a déjà un bus
d'événements durable, rejouable par plage et par motif, à identifiants
idempotents. En porter un second créerait deux magasins d'événements —
l'architecture parallèle que le cahier interdit à sa propre règle 4. Le
registre porte les **runs** ; le bus porte les **événements** ; `run_id`
les relie.

**Pas repris non plus : leur propre couche SQLite.** Hermes a
`DatabaseManager` et `MigrationManager`, qui posent déjà WAL et
`foreign_keys`. Ils n'étaient utilisés par personne — comme
`approvals.py` — mais les doubler aurait fait une troisième couche de
base dans ce dépôt.

## La structuration, décidée en HOS-219

`utilisateur`, `projet` et `workspace` sont des colonnes dès maintenant :
trois colonnes coûtent trois colonnes ici, et une migration sur données
réelles six semaines plus tard.

`utilisateur` vaut `"local"` et **n'est pas une identité vérifiée**. Il ne
doit jamais servir de contrôle d'accès tant qu'il n'y a pas
d'authentification — un test le garde.
"""

from __future__ import annotations

import json
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from backend.storage.database_manager import DatabaseManager


class Statut(str, Enum):
    EN_ATTENTE = "en_attente"
    EN_COURS = "en_cours"
    REUSSI = "reussi"
    ECHOUE = "echoue"
    ABANDONNE = "abandonne"
    #: Le processus qui portait ce run a disparu sans rien dire. Distinct
    #: d'un échec : on ne sait pas ce qu'il avait fait avant de mourir.
    PERDU = "perdu"


#: Une fois là, on n'en sort plus. L'invariant est appliqué dans le SQL,
#: pas ici : cette liste sert à l'écrire et à le tester.
TERMINAUX = (Statut.REUSSI, Statut.ECHOUE, Statut.ABANDONNE, Statut.PERDU)


class Cause(str, Enum):
    """Pourquoi un run a échoué. Un retry aveugle ne sert à rien.

    Chaque cause appelle un remède différent — changer de modèle, changer
    de fournisseur, comprimer le contexte, réparer, ou s'arrêter. Les
    nommer est le préalable au jalon « taxonomie d'échecs ».
    """

    MODELE = "modele"
    FOURNISSEUR = "fournisseur"
    QUOTA = "quota"
    RESSOURCE = "ressource"
    CONTEXTE = "contexte"
    OUTIL = "outil"
    SEMANTIQUE = "semantique"
    VERIFICATION = "verification"
    POLITIQUE = "politique"
    SECURITE = "securite"
    #: Le processus porteur a disparu (HOS-240). Distincte d'`INCONNUE` :
    #: celle-ci dit « cherchée, non trouvée », celle-là nomme un fait
    #: constaté — le processus qui tenait ce run n'existe plus.
    PROCESSUS = "processus"
    INCONNUE = "inconnue"


def _maintenant() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Run:
    """Une tentative d'exécution, et ce qu'elle est devenue."""

    identifiant: str = field(default_factory=lambda: uuid.uuid4().hex)
    mission: str = ""
    #: La reprise dont ce run descend. C'est ce qui rend la lignée
    #: lisible : « le run C a réussi après que A et B ont échoué ».
    parent: Optional[str] = None
    tentative: int = 1

    objectif: str = ""
    agent: str = ""
    modele: str = ""
    runtime: str = ""
    fournisseur: str = ""
    workspace: str = ""

    #: Champs de **traçabilité**, pas d'identité vérifiée (HOS-219).
    utilisateur: str = "local"
    projet: str = ""

    statut: Statut = Statut.EN_ATTENTE
    cause: Optional[Cause] = None
    raison: str = ""
    motif_de_reprise: str = ""

    jetons_entree: int = 0
    jetons_sortie: int = 0
    cout: float = 0.0

    contrat: str = ""
    #: Comment ce run a été routé, en JSON compact (HOS-242) : ce que le
    #: routeur a demandé, ce qui a réellement servi, le fournisseur, et le
    #: repli quand les deux diffèrent. Vide tant que rien n'a tourné —
    #: « on ne sait pas » et non « aucun repli ».
    decision: str = ""
    cree_le: str = field(default_factory=_maintenant)
    demarre_le: Optional[str] = None
    fini_le: Optional[str] = None

    @property
    def termine(self) -> bool:
        return self.statut in TERMINAUX

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["statut"] = self.statut.value
        d["cause"] = self.cause.value if self.cause else None
        return d


_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    identifiant TEXT PRIMARY KEY,
    mission TEXT NOT NULL DEFAULT '',
    parent TEXT,
    tentative INTEGER NOT NULL DEFAULT 1,
    objectif TEXT NOT NULL DEFAULT '',
    agent TEXT NOT NULL DEFAULT '',
    modele TEXT NOT NULL DEFAULT '',
    runtime TEXT NOT NULL DEFAULT '',
    fournisseur TEXT NOT NULL DEFAULT '',
    workspace TEXT NOT NULL DEFAULT '',
    utilisateur TEXT NOT NULL DEFAULT 'local',
    projet TEXT NOT NULL DEFAULT '',
    statut TEXT NOT NULL DEFAULT 'en_attente',
    cause TEXT,
    raison TEXT NOT NULL DEFAULT '',
    motif_de_reprise TEXT NOT NULL DEFAULT '',
    jetons_entree INTEGER NOT NULL DEFAULT 0,
    jetons_sortie INTEGER NOT NULL DEFAULT 0,
    cout REAL NOT NULL DEFAULT 0,
    contrat TEXT NOT NULL DEFAULT '',
    cree_le TEXT NOT NULL,
    demarre_le TEXT,
    fini_le TEXT,
    processus TEXT,
    decision TEXT,
    FOREIGN KEY (parent) REFERENCES runs(identifiant)
);
CREATE INDEX IF NOT EXISTS runs_mission ON runs(mission, cree_le);
CREATE INDEX IF NOT EXISTS runs_parent ON runs(parent);
CREATE INDEX IF NOT EXISTS runs_statut ON runs(statut);
CREATE INDEX IF NOT EXISTS runs_projet ON runs(projet, cree_le);
"""


class Registre:
    """Le journal durable des exécutions.

    Sans état en mémoire : tout passe par la base, pour qu'un
    redémarrage du backend ne fasse pas disparaître la trace. C'est le
    défaut exact que la nuit du 29 au 30 août a mis en évidence.
    """

    def __init__(self, db: DatabaseManager | None = None) -> None:
        self._db = db or DatabaseManager()
        self._db.initialize()
        self._verrou = threading.RLock()
        conn = self._db.get_connection()
        conn.executescript(_SCHEMA)
        self._ajouter_les_colonnes_manquantes(conn)
        conn.commit()

    @staticmethod
    def _ajouter_les_colonnes_manquantes(conn) -> None:
        """`CREATE TABLE IF NOT EXISTS` ne fait rien sur une base existante.

        Une base ouverte avant HOS-240 n'a pas la colonne `processus`, et
        l'`INSERT` nommé de `ouvrir()` y échouerait — donc plus aucun run
        ne s'ouvrirait. Une correction d'observabilité aurait cassé
        l'exécution. C'est le mécanisme de `memory.db._add_missing_columns`,
        et pour la même raison : ce dépôt fait évoluer ses schémas à chaud.

        Additive et nullable seulement : une colonne qu'on ne saurait pas
        remplir pour les lignes déjà là ne doit pas être ajoutée en douce.
        """
        presentes = {ligne[1] for ligne in conn.execute("PRAGMA table_info(runs)")}
        for nom, type_sql in (("processus", "TEXT"), ("decision", "TEXT")):
            if nom not in presentes:
                conn.execute(f"ALTER TABLE runs ADD COLUMN {nom} {type_sql}")

    # ── Écriture ─────────────────────────────────────────────────────

    def ouvrir(self, **champs: Any) -> Run:
        """Créer un run. Il naît `en_attente`, jamais `en_cours`.

        Un run qui naîtrait déjà démarré mentirait sur son horodatage si
        la carte était occupée et qu'il attendait.
        """
        run = Run(**champs)
        with self._verrou:
            d = run.to_dict()
            # Qui porte ce run (HOS-240). Sans cette empreinte, un run
            # laissé `en_cours` par un processus mort est indiscernable
            # d'un run réellement en train de tourner ailleurs.
            from backend.runs.reconciliation import empreinte_du_processus
            d["processus"] = empreinte_du_processus()
            colonnes = ", ".join(d)
            marques = ", ".join("?" for _ in d)
            self._db.execute(
                f"INSERT INTO runs ({colonnes}) VALUES ({marques})",
                tuple(d.values()))
        return run

    def demarrer(self, identifiant: str) -> None:
        self._changer(identifiant, Statut.EN_COURS, demarre_le=_maintenant())

    def terminer(self, identifiant: str, statut: Statut, *,
                 cause: Cause | None = None, raison: str = "",
                 cout: float | None = None,
                 jetons_entree: int | None = None,
                 jetons_sortie: int | None = None) -> None:
        """Clore un run. Un état terminal ne se réécrit pas.

        La garde est dans le `CASE WHEN` de la requête, pas ici : un
        appelant qui oublierait de vérifier ne peut pas la contourner.
        """
        extra: dict[str, Any] = {"fini_le": _maintenant()}
        if cause is not None:
            extra["cause"] = cause.value
        if raison:
            extra["raison"] = raison
        for nom, valeur in (("cout", cout), ("jetons_entree", jetons_entree),
                            ("jetons_sortie", jetons_sortie)):
            if valeur is not None:
                extra[nom] = valeur
        self._changer(identifiant, statut, **extra)

    def constater(self, identifiant: str, **faits: Any) -> None:
        """Écrire ce qui s'est réellement passé, sans clore le run.

        `ouvrir()` enregistre l'**intention** : le runtime que le
        coordinateur a demandé, l'agent qu'il a choisi. Ce que l'exécution
        a réellement fait ne se sait qu'après, et diffère — une reprise
        change de modèle (`task_executor._resolve_model`), une bascule
        change de fournisseur, et le runtime qui a servi la requête est lu
        dans la réponse et non dans la demande.

        Sans cette méthode, `modele` et `fournisseur` n'étaient écrits par
        **personne** : la colonne existait depuis HOS-221, la vue
        d'opérations l'affichait, et elle valait la chaîne vide pour tous
        les runs jamais enregistrés. « Quel modèle a exécuté cette
        mission ? » était une question sans réponse.

        Le même gel terminal s'applique : un run arrivé ne se réécrit pas,
        même pour lui ajouter un fait — la trace d'un run clos est close.
        """
        inconnus = set(faits) - {"runtime", "modele", "fournisseur", "agent",
                                 "decision"}
        if inconnus:
            raise ValueError(
                f"`constater` n'écrit que des faits d'exécution ; "
                f"{sorted(inconnus)} n'en sont pas")
        faits = {n: v for n, v in faits.items() if v}
        if not faits:
            return
        self._changer_sans_statut(identifiant, **faits)

    def reprendre(self, identifiant: str, *, motif: str, **remplacements: Any) -> Run:
        """Ouvrir une reprise, rattachée à celle qui a échoué.

        Le motif est **obligatoire** : une lignée qui ne dit pas pourquoi
        elle s'est prolongée ne répond pas à la question qu'on lui posera.
        """
        if not motif.strip():
            raise ValueError(
                "une reprise doit dire pourquoi — sans motif, la lignée ne "
                "répond pas à « pourquoi le premier essai a échoué ? »")
        parent = self.lire(identifiant)
        if parent is None:
            raise KeyError(f"aucun run {identifiant!r}")

        champs = parent.to_dict()
        for jetable in ("identifiant", "statut", "cause", "raison", "cree_le",
                        "demarre_le", "fini_le", "jetons_entree",
                        "jetons_sortie", "cout", "decision", "modele",
                        "fournisseur"):
            champs.pop(jetable, None)
        champs.update(remplacements)
        champs["parent"] = parent.identifiant
        champs["tentative"] = parent.tentative + 1
        champs["motif_de_reprise"] = motif
        return self.ouvrir(**champs)

    def _changer_sans_statut(self, identifiant: str, **extra: Any) -> None:
        """Le même gel terminal, appliqué à un constat qui ne clôt rien."""
        terminaux = ", ".join(f"'{s.value}'" for s in TERMINAUX)
        fige = "CASE WHEN statut IN (" + terminaux + ") THEN {col} ELSE ? END"
        assignations = [f"{n} = " + fige.format(col=n) for n in extra]
        valeurs = list(extra.values()) + [identifiant]
        with self._verrou:
            self._db.execute(
                "UPDATE runs SET " + ", ".join(assignations) +
                " WHERE identifiant = ?", tuple(valeurs))

    def _changer(self, identifiant: str, statut: Statut, **extra: Any) -> None:
        """Écrire, sauf si le run est déjà arrivé.

        Le `CASE WHEN` s'applique à **chaque** colonne, pas seulement au
        statut. Geler l'état en laissant `cause` et `raison` réinscriptibles
        aurait donné un run figé sur `echoue` avec le motif du second
        appel — une trace pire que pas de trace, parce qu'elle a l'air
        d'en être une.
        """
        terminaux = ", ".join(f"'{s.value}'" for s in TERMINAUX)
        fige = "CASE WHEN statut IN (" + terminaux + ") THEN {col} ELSE ? END"

        assignations = ["statut = " + fige.format(col="statut")]
        valeurs: list[Any] = [statut.value]
        for nom, valeur in extra.items():
            assignations.append(f"{nom} = " + fige.format(col=nom))
            valeurs.append(valeur)
        valeurs.append(identifiant)
        with self._verrou:
            self._db.execute(
                "UPDATE runs SET " + ", ".join(assignations) +
                " WHERE identifiant = ?", tuple(valeurs))

    # ── Lecture ──────────────────────────────────────────────────────

    def lire(self, identifiant: str) -> Optional[Run]:
        ligne = self._db.fetch_one(
            "SELECT * FROM runs WHERE identifiant = ?", (identifiant,))
        return self._depuis(ligne) if ligne else None

    def de_la_mission(self, mission: str) -> list[Run]:
        return [self._depuis(l) for l in self._db.fetch_all(
            "SELECT * FROM runs WHERE mission = ? ORDER BY cree_le", (mission,))]

    def lignee(self, identifiant: str) -> list[Run]:
        """La chaîne des tentatives, de la première à celle-ci.

        C'est ce qui répond à « pourquoi le premier run a échoué » sans
        aller lire un fichier écrasé depuis.
        """
        chaine: list[Run] = []
        vus: set[str] = set()
        courant = self.lire(identifiant)
        while courant and courant.identifiant not in vus:
            vus.add(courant.identifiant)
            chaine.append(courant)
            courant = self.lire(courant.parent) if courant.parent else None
        return list(reversed(chaine))

    def en_cours(self) -> list[Run]:
        return [self._depuis(l) for l in self._db.fetch_all(
            "SELECT * FROM runs WHERE statut = ?", (Statut.EN_COURS.value,))]

    def non_termines(self) -> list[Run]:
        """Tout ce qui n'est pas arrivé — `en_attente` compris.

        Un processus tué entre `ouvrir()` et `demarrer()` laisse un run
        `en_attente` que personne ne reprendra jamais : c'est le même
        orphelin qu'un `en_cours`, et l'oublier aurait laissé la moitié
        du défaut en place.
        """
        marques = ", ".join("?" for _ in TERMINAUX)
        return [self._depuis(l) for l in self._db.fetch_all(
            f"SELECT * FROM runs WHERE statut NOT IN ({marques})",
            tuple(s.value for s in TERMINAUX))]

    def processus_de(self, identifiant: str) -> Optional[str]:
        """L'empreinte du processus qui a ouvert ce run, si elle existe."""
        ligne = self._db.fetch_one(
            "SELECT processus FROM runs WHERE identifiant = ?", (identifiant,))
        return (dict(ligne).get("processus") or None) if ligne else None

    @staticmethod
    def _depuis(ligne: dict) -> Run:
        d = dict(ligne)
        # `processus` est de la comptabilité sur qui détenait la ligne, pas
        # un fait métier du run : `Run` ne le porte pas, et le lui passer
        # ferait échouer sa construction.
        d.pop("processus", None)
        d["statut"] = Statut(d.get("statut") or "en_attente")
        d["cause"] = Cause(d["cause"]) if d.get("cause") else None
        return Run(**d)


__all__ = ["Cause", "Registre", "Run", "Statut", "TERMINAUX"]
