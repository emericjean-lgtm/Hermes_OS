"""Pending human approvals — the queue §23's "vue sécurité" needs.

Until now Aegis worked purely as "refuse and tell the caller": a
require_human_validation verdict went back to whoever asked, and nothing
was kept. That is safe, but it means there is no such thing as a list of
things awaiting your approval, and no way to say yes to one after the
fact — the caller is long gone by the time a human looks.

This adds that queue, deliberately narrowly:

  - **One-shot.** An approval is consumed the first time it is used. It
    cannot become a standing permission by accident.
  - **Time-limited.** It expires (default 15 minutes), so an approval
    forgotten in the queue does not authorise anything tomorrow.
  - **Fingerprinted exactly.** The approval matches one action_type +
    target_path + description triple and nothing else. Descriptions here
    are code-generated and deterministic (`Write to {path}`, `Commit on
    {branch} in {repo}`), so a legitimate retry reproduces the same
    fingerprint while a *different* action cannot borrow the approval.

The engine (security/aegis_engine.py) stays DB-free and pure by design,
so this is consulted from AegisAgent, not from the engine.

Approving here does **not** replay the action. Nothing re-executes on the
user's behalf: the approval simply means the next identical attempt is
allowed through once. Replaying arbitrary stored actions would need a
dispatcher able to re-run anything, which is exactly the kind of
machinery a security gate should not own.

One deliberate consequence, verified in use: **a refusal is per-attempt,
not permanent.** Refusing leaves a `refused` row as the record of that
decision, but a later retry of the same action queues a fresh `pending`
one — because "no, not now" is not the same statement as "never, and
stop asking". The dedup above only prevents duplicate *pending* rows, so
an agent retrying in a loop after a refusal will re-ask. That is the
intended trade-off (a refusal must not silently become a permanent
block a user can't undo), but it means the queue is a work list, not an
audit log: read it as "what is being asked of me now", with the decided
rows as history beside it.
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from sqlalchemy import DateTime, Integer, String, Text, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from backend.memory.db import Base
from backend.core.event_hub import get_event_hub
from backend.security.empreinte import (
    canoniser_chemin,
    canoniser_discriminants,
    couvre,
)

# --------------------------------------------------------------------
"""La demande d'accord humain déposée dans la file (HOS-181)."""
APPROVAL_EVENTS: dict[str, str] = {
    "request": "validation.request",
}

DEFAULT_TTL_MINUTES = 15

#: Les deux portees. `action` est l'existant : une action exacte, une
#: fois. `arborescence` couvre un `action_type` sous une racine.
PORTEE_ACTION = "action"
PORTEE_ARBORESCENCE = "arborescence"

#: Une portee vit moins longtemps qu'un accord exact : elle autorise
#: davantage, donc elle doit se perimer plus vite. Cinq minutes couvrent
#: la rafale d'ecritures d'une meme tache sans couvrir la suivante.
TTL_PORTEE_MINUTES = 5

#: Et elle est plafonnee en nombre d'usages. Sans plafond, « oui pour ce
#: dossier » deviendrait une permission permanente que personne n'a
#: decidee — exactement ce que le module refusait de creer par accident.
MAX_USAGES_PORTEE = 50


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REFUSED = "refused"
    # Approved and then actually used — kept distinct from APPROVED so the
    # queue can show that consent was spent, not merely granted.
    USED = "used"


class PendingApproval(Base):
    __tablename__ = "pending_approvals"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String, index=True)
    action_type: Mapped[str] = mapped_column(String, index=True)
    description: Mapped[str] = mapped_column(Text)
    target_path: Mapped[str | None] = mapped_column(String, nullable=True)
    requesting_agent: Mapped[str] = mapped_column(String)
    reason: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String, index=True, default=ApprovalStatus.PENDING)
    task_id: Mapped[str | None] = mapped_column(String, nullable=True)
    project_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # ── HOS-224 : la portee ──────────────────────────────────────────
    #
    # Toutes nullables, et pas par commodite : `_add_missing_columns`
    # (memory/db.py) n'ajoute au demarrage que des colonnes nullables et
    # refuse bruyamment les autres. Une base existante gagne donc ces
    # colonnes sans migration, avec `None` partout — c'est-a-dire avec
    # exactement le comportement d'avant.

    #: `None` ou `"action"` : consentement exact, a usage unique — ce qui
    #: existait deja. `"arborescence"` : couvre un `action_type` sous une
    #: racine, avec un budget d'usages et une expiration plus courte.
    portee: Mapped[str | None] = mapped_column(String, nullable=True)
    #: La racine couverte, canonisee. Vide hors portee d'arborescence.
    portee_racine: Mapped[str | None] = mapped_column(String, nullable=True)
    #: Le budget d'usages. `None` = un seul, comme avant. Une portee sans
    #: budget serait une permission permanente deguisee : c'est ce que le
    #: module refusait deja de creer par accident, et lui ajouter une
    #: portee ne doit pas rouvrir cette porte.
    usages_restants: Mapped[int | None] = mapped_column(Integer, nullable=True)
    #: Ce qui distingue deux actions par ailleurs identiques, en JSON
    #: canonique. Garde lisible sur la ligne : `fingerprint` ne dit pas
    #: *ce* qui distinguait, et un humain qui relit la file en a besoin.
    discriminants: Mapped[str | None] = mapped_column(Text, nullable=True)


def fingerprint_for(action_type: str, target_path: str | None,
                    description: str = "", *,
                    discriminants: dict | None = None) -> str:
    """Identify one specific action, canonically (HOS-224).

    **`description` est ignoree.** Elle etait utilisee jusqu'ici sur la
    foi d'une hypothese — « descriptions are generated by the calling
    tool, not by a model » — vraie pour `file_tools` et `git_tools`,
    **fausse** pour l'outil MCP `aegis_check` et pour
    `POST /api/v1/security/evaluate`, ou elle vient du modele ou du corps
    de la requete. Mesure : deux reformulations de la meme action
    donnaient deux empreintes, donc un « oui » humain qui ne s'appliquait
    jamais et une seconde demande deposee sans que rien dise pourquoi.

    Le parametre reste dans la signature, ignore plutot que retire : le
    retirer forcerait a toucher tous les sites d'appel dans le meme
    commit que le changement de semantique — deux choses a relire au lieu
    d'une.

    Ce qui distinguait legitimement deux actions dans la prose passe par
    `discriminants` : `{"branch": "main"}` plutot que « Commit on main ».
    La garantie d'origine — une approbation pour *Commit on feature/x*
    n'autorise pas *Commit on main* — est donc conservee, et elle ne
    depend plus de la formulation.

    Voir `backend/security/empreinte.py` pour la canonisation du chemin,
    qui reglait le second defaut mesure : quatre ecritures du meme
    fichier donnaient quatre empreintes.
    """
    from backend.security.empreinte import empreinte

    return empreinte(action_type, target_path, discriminants=discriminants)


def _now() -> datetime:
    return datetime.now(UTC)


def _as_aware(value: datetime | None) -> datetime | None:
    """SQLite hands back naive datetimes; compare in UTC regardless."""
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def record_pending(
    session: Session,
    *,
    action_type: str,
    description: str,
    reason: str,
    target_path: str | None = None,
    requesting_agent: str = "unknown",
    task_id: str | None = None,
    project_id: str | None = None,
    discriminants: dict | None = None,
) -> PendingApproval:
    """Queue a refused action for later human decision.

    Re-refusing the same action returns the existing pending row rather
    than piling up duplicates — an agent that retries in a loop would
    otherwise flood the queue and bury the entries that matter.
    """
    fingerprint = fingerprint_for(action_type, target_path,
                                  discriminants=discriminants)
    existing = session.execute(
        select(PendingApproval).where(
            PendingApproval.fingerprint == fingerprint,
            PendingApproval.status == ApprovalStatus.PENDING,
        )
    ).scalar_one_or_none()
    if existing is not None:
        # Deliberately *not* published to §24.2: this is the same pending
        # item, not a new one. An agent retrying in a loop would otherwise
        # repeat the same validation.request on the dashboard and bury the
        # entries that matter — exactly what this dedup prevents in the
        # table.
        return existing

    entry = PendingApproval(
        id=str(uuid.uuid4()),
        fingerprint=fingerprint,
        action_type=action_type,
        description=description,
        target_path=target_path,
        requesting_agent=requesting_agent,
        reason=reason,
        status=ApprovalStatus.PENDING,
        task_id=task_id,
        project_id=project_id,
        created_at=_now(),
        portee=PORTEE_ACTION,
        discriminants=canoniser_discriminants(discriminants) or None,
    )
    session.add(entry)
    session.commit()
    session.refresh(entry)
    # After the commit, never before: a client must not be told to
    # validate something that failed to persist.
    get_event_hub().publish("validation.request", to_dict(entry))
    return entry


def list_approvals(
    session: Session, *, status: str | None = None, project_id: str | None = None
) -> list[PendingApproval]:
    stmt = select(PendingApproval).order_by(PendingApproval.created_at.desc())
    if status is not None:
        stmt = stmt.where(PendingApproval.status == status)
    if project_id is not None:
        stmt = stmt.where(PendingApproval.project_id == project_id)
    return list(session.execute(stmt).scalars())


def get_approval(session: Session, approval_id: str) -> PendingApproval | None:
    return session.get(PendingApproval, approval_id)


def decide(
    session: Session,
    approval_id: str,
    *,
    approved: bool,
    ttl_minutes: int | None = None,
    portee: str = PORTEE_ACTION,
    portee_racine: str | None = None,
    usages: int | None = None,
) -> PendingApproval | None:
    """Record a human decision. Returns None if there is no such entry.

    Only a PENDING entry can be decided: re-approving something already
    used would silently mint a second consent from one human action.

    ## La portee (HOS-224)

    Par defaut, rien ne change : consentement exact, usage unique, quinze
    minutes. **Une portee ne s'obtient jamais par omission** — il faut la
    demander, nommer sa racine, et accepter un budget d'usages. Trente
    ecritures dans un dossier ne devaient plus demander trente clics,
    mais « oui a tout, partout, pour toujours » ne doit pas etre ce
    qu'on obtient en cliquant vite.

    Trois bornes, et les trois sont necessaires :

    * une **racine**, sans laquelle la portee couvrirait le disque ;
    * un **budget d'usages** plafonne, sans lequel elle serait une
      permission permanente ;
    * une **expiration plus courte** que celle d'un accord exact, parce
      qu'une portee oubliee autorise davantage qu'un accord oublie.
    """
    entry = session.get(PendingApproval, approval_id)
    if entry is None or entry.status != ApprovalStatus.PENDING:
        return entry

    if approved and portee == PORTEE_ARBORESCENCE:
        if not portee_racine:
            raise ValueError(
                "une portee d'arborescence exige une racine — sans elle "
                "elle couvrirait tout le disque")
        budget = MAX_USAGES_PORTEE if usages is None else int(usages)
        if budget < 1:
            raise ValueError("une portee sans usage n'autorise rien")
        entry.portee = PORTEE_ARBORESCENCE
        entry.portee_racine = canoniser_chemin(portee_racine)
        entry.usages_restants = min(budget, MAX_USAGES_PORTEE)
        defaut_ttl = TTL_PORTEE_MINUTES
    else:
        entry.portee = PORTEE_ACTION
        entry.usages_restants = 1
        defaut_ttl = DEFAULT_TTL_MINUTES

    delai = defaut_ttl if ttl_minutes is None else int(ttl_minutes)
    entry.status = ApprovalStatus.APPROVED if approved else ApprovalStatus.REFUSED
    entry.decided_at = _now()
    entry.expires_at = _now() + timedelta(minutes=delai) if approved else None
    session.commit()
    session.refresh(entry)
    return entry


def consume_approval(
    session: Session, *, action_type: str, target_path: str | None,
    description: str = "", discriminants: dict | None = None
) -> PendingApproval | None:
    """Spend a live approval for this exact action, if one exists.

    Returns the entry when consent applied (and marks it USED), or None —
    in which case the caller must go on refusing. An expired approval is
    not consumed and is left visible in the queue as expired-by-time
    rather than being silently deleted.
    """
    fingerprint = fingerprint_for(action_type, target_path,
                                  discriminants=discriminants)
    entry = session.execute(
        select(PendingApproval)
        .where(
            PendingApproval.fingerprint == fingerprint,
            PendingApproval.status == ApprovalStatus.APPROVED,
        )
        .order_by(PendingApproval.decided_at.desc())
    ).scalars().first()

    if entry is not None and _vivante(entry):
        return _depenser(session, entry)

    # HOS-224 : a defaut d'accord exact, une portee peut couvrir. Cherchee
    # **apres** et jamais avant : un accord exact est le consentement le
    # plus precis, et le depenser en premier evite de consommer un budget
    # de portee pour une action qui avait deja son propre « oui ».
    return _consommer_une_portee(session, action_type, target_path)


def _vivante(entry: PendingApproval) -> bool:
    """L'approbation est-elle encore utilisable ?

    Une approbation perimee n'est pas consommee et reste visible dans la
    file comme perimee, plutot que supprimee en silence : la file est une
    liste de travail, et un « oui » arrive trop tard doit se voir.
    """
    expires_at = _as_aware(entry.expires_at)
    if expires_at is not None and expires_at < _now():
        return False
    return entry.usages_restants is None or entry.usages_restants > 0


def _depenser(session: Session, entry: PendingApproval) -> PendingApproval:
    """Consommer un usage, et marquer USED quand il n'en reste plus.

    Une portee garde le statut APPROVED tant qu'il lui reste du budget :
    la passer a USED au premier usage annulerait la portee, et la laisser
    APPROVED apres epuisement la rendrait eternelle. Le compteur est ce
    qui distingue les deux, et le statut ne fait que le refleter.
    """
    if entry.usages_restants is not None:
        entry.usages_restants -= 1
    if entry.usages_restants is None or entry.usages_restants <= 0:
        entry.status = ApprovalStatus.USED
    session.commit()
    session.refresh(entry)
    return entry


def _consommer_une_portee(
    session: Session, action_type: str, target_path: str | None
) -> PendingApproval | None:
    """Une portee vivante couvre-t-elle cette action ?

    Trois conditions, toutes necessaires : **meme `action_type`** — une
    portee accordee pour ecrire n'autorise pas a supprimer ; **chemin
    sous la racine**, verifie par `empreinte.couvre` qui canonise les
    deux cotes et refuse `C:/projet-bis` sous `C:/projet` ; et **budget
    et delai encore ouverts**.

    Sans `target_path`, rien ne peut etre couvert : une portee est une
    portee *de chemin*, et l'appliquer a une action qui n'en a pas
    reviendrait a l'appliquer partout.
    """
    if not target_path:
        return None

    candidates = session.execute(
        select(PendingApproval)
        .where(
            PendingApproval.action_type == action_type,
            PendingApproval.portee == PORTEE_ARBORESCENCE,
            PendingApproval.status == ApprovalStatus.APPROVED,
        )
        .order_by(PendingApproval.decided_at.desc())
    ).scalars().all()

    for entry in candidates:
        if not _vivante(entry):
            continue
        if entry.portee_racine and couvre(entry.portee_racine, target_path):
            return _depenser(session, entry)
    return None


def to_dict(entry: PendingApproval) -> dict:
    expires_at = _as_aware(entry.expires_at)
    return {
        "id": entry.id,
        "action_type": entry.action_type,
        "description": entry.description,
        "target_path": entry.target_path,
        "requesting_agent": entry.requesting_agent,
        "reason": entry.reason,
        "status": entry.status,
        "task_id": entry.task_id,
        "project_id": entry.project_id,
        "created_at": entry.created_at.isoformat(),
        "decided_at": entry.decided_at.isoformat() if entry.decided_at else None,
        "expires_at": expires_at.isoformat() if expires_at else None,
        # La portee et son budget sont dans le rapport : un humain qui
        # relit la file doit voir qu'une ligne autorise un dossier entier
        # et combien d'usages il lui reste, pas seulement « approuve ».
        "portee": entry.portee or PORTEE_ACTION,
        "portee_racine": entry.portee_racine,
        "usages_restants": entry.usages_restants,
        "discriminants": entry.discriminants,
        "expired": bool(expires_at and expires_at < _now()),
    }
