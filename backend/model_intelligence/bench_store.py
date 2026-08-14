"""Conserver ce que les campagnes ont mesuré (HOS-107).

Les échelles de contexte, les plafonds de code, la vision, la VRAM réelle —
tout cela a coûté des heures de GPU et vivait dans des fichiers temporaires.
Une campagne dure une à deux heures ; la refaire parce que le résultat a
disparu est le genre de perte que ce projet évite ailleurs par principe.

Deux décisions de forme.

**Une mesure par (modèle, axe), remplacée à chaque nouvelle campagne.**
Pas d'historique : un catalogue sert à décider maintenant, et une mesure
ancienne obtenue sous d'autres conditions (autre version d'Ollama, autre
quantification) est plus trompeuse qu'utile. Le champ ``measured_at`` dit
quand, et ``runtime_version`` sous quoi — de quoi savoir qu'il faut
remesurer sans garder le vieux verdict à portée de main.

**Le détail brut est conservé tel quel.** Le score agrégé sert au routage,
mais l'onglet Modèles doit pouvoir montrer *pourquoi* un modèle plafonne à
un niveau — quel test a cassé, avec quel message. Un chiffre sans son
justificatif redevient une opinion.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any, Optional

from sqlalchemy import Float, String, Text, delete, select
from sqlalchemy.orm import Mapped, mapped_column

from backend.memory.db import Base

logger = logging.getLogger("hermes_os.model_intelligence.bench_store")

#: Les axes du catalogue. Un modèle non mesuré sur un axe n'a pas de ligne
#: — « non mesuré » et « zéro » doivent rester distincts, comme partout
#: ailleurs dans ce projet.
AXES = ("capacite", "code", "vision", "agentique", "extraction", "long_contexte")


class BenchResultRow(Base):
    """Une mesure : un modèle, un axe, un score, et de quoi le justifier."""

    __tablename__ = "model_bench_result"

    model: Mapped[str] = mapped_column(String(200), primary_key=True)
    axis: Mapped[str] = mapped_column(String(32), primary_key=True)
    #: 0..1 pour un taux de réussite ; None quand l'axe se juge autrement
    #: (le code rend un palier, pas un pourcentage).
    score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    #: Verdict lisible : « mythique », « 3/3 », « 256k »…
    verdict: Mapped[str] = mapped_column(String(64), default="")
    #: Le détail brut de la campagne, tel qu'elle l'a produit.
    detail_json: Mapped[str] = mapped_column(Text, default="{}")
    measured_at: Mapped[float] = mapped_column(Float, default=0.0)
    runtime_version: Mapped[str] = mapped_column(String(32), default="")


class BenchStore:
    """Les mesures du catalogue, dans la base SQLite du projet."""

    def __init__(self, session_factory: Any = None) -> None:
        if session_factory is None:
            from backend.core.config import get_settings
            from backend.memory.db import init_db, make_engine, make_session_factory

            engine = make_engine(get_settings().sqlite_path)
            init_db(engine)
            session_factory = make_session_factory(engine)
        self._session_factory = session_factory
        self._lock = threading.RLock()

    # ── écriture ────────────────────────────────────────────────────────

    def record(self, model: str, axis: str, *, verdict: str,
               score: Optional[float] = None, detail: Any = None,
               runtime_version: str = "") -> None:
        """Enregistrer une mesure, en remplaçant la précédente s'il y en a.

        Écrit dès qu'une campagne rend un axe plutôt qu'à la fin : une
        campagne interrompue garde ce qu'elle a déjà obtenu. C'est la leçon
        d'un banc d'essai perdu après quarante-cinq minutes.
        """
        if axis not in AXES:
            raise ValueError(f"axe inconnu : {axis!r} — attendus {AXES}")
        with self._lock, self._session_factory() as db:
            row = db.get(BenchResultRow, (model, axis))
            if row is None:
                row = BenchResultRow(model=model, axis=axis)
                db.add(row)
            row.score = score
            row.verdict = verdict
            row.detail_json = json.dumps(detail if detail is not None else {},
                                         ensure_ascii=False, default=str)
            row.measured_at = time.time()
            row.runtime_version = runtime_version
            db.commit()

    def forget(self, model: str) -> int:
        """Oublier toutes les mesures d'un modèle — après sa suppression."""
        with self._lock, self._session_factory() as db:
            result = db.execute(
                delete(BenchResultRow).where(BenchResultRow.model == model))
            db.commit()
            return int(result.rowcount or 0)

    # ── lecture ─────────────────────────────────────────────────────────

    def for_model(self, model: str) -> dict[str, dict[str, Any]]:
        with self._session_factory() as db:
            rows = db.execute(
                select(BenchResultRow).where(BenchResultRow.model == model)
            ).scalars()
            return {r.axis: _to_dict(r) for r in rows}

    def catalogue(self) -> list[dict[str, Any]]:
        """Le catalogue entier, un objet par modèle, pour l'onglet Modèles."""
        with self._session_factory() as db:
            rows = list(db.execute(select(BenchResultRow)).scalars())
        par_modele: dict[str, dict[str, Any]] = {}
        for row in rows:
            entry = par_modele.setdefault(
                row.model, {"model": row.model, "axes": {}, "measured_at": 0.0})
            entry["axes"][row.axis] = _to_dict(row)
            entry["measured_at"] = max(entry["measured_at"], row.measured_at)
        # Les axes non mesurés sont absents plutôt que nuls : l'UI doit
        # pouvoir écrire « non mesuré » et non « 0 ».
        return sorted(par_modele.values(), key=lambda e: -e["measured_at"])

    def best_for(self, axis: str) -> Optional[str]:
        """Le modèle le mieux noté sur un axe, ou None si aucun n'est mesuré."""
        with self._session_factory() as db:
            rows = [r for r in db.execute(
                select(BenchResultRow).where(BenchResultRow.axis == axis)
            ).scalars() if r.score is not None]
        return max(rows, key=lambda r: r.score).model if rows else None


def _to_dict(row: BenchResultRow) -> dict[str, Any]:
    try:
        detail = json.loads(row.detail_json or "{}")
    except ValueError:
        detail = {}
    return {"score": row.score, "verdict": row.verdict, "detail": detail,
            "measured_at": row.measured_at, "runtime_version": row.runtime_version}
