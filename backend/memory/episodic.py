"""Long-term memory store — cahier des charges §11.2, §24.3 (memory_long).

Rules from §11.5 applied here: every entry is dated automatically
(created_at), duplicates are rejected by content hash (not full semantic
dedup — that needs the ChromaDB side, see semantic.py), and deletion is
explicit (delete_memory), never implicit.
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Float, String, Text, or_, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from backend.memory.db import Base


class MemoryEntry(Base):
    __tablename__ = "memory_long"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    type: Mapped[str] = mapped_column(String, index=True)
    content: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String, index=True)
    tags: Mapped[str] = mapped_column(String, default="")  # comma-separated
    #: Metadonnee libre fournie par l'ecrivain (HOS-249 l'a mesuree :
    #: stockee, rendue, **jamais comparee**). Ce n'est pas une provenance
    #: et elle n'autorise rien — c'est l'agent qui l'ecrit, et un champ
    #: ecrit par celui qu'on filtre ne peut pas porter le filtre.
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    created_at: Mapped[datetime] = mapped_column(DateTime)

    # ── Provenance (HOS-249) ─────────────────────────────────────────
    #: Les quatre colonnes qui portent `backend.memory.confiance.Provenance`.
    #: Nullables : une ligne ecrite avant ce jalon n'en a aucune, et
    #: `provenance_de()` la traite alors comme `INCONNUE` — donc en
    #: quarantaine. C'est le sens de lecture qui protege, et il ne fallait
    #: rien inventer pour l'obtenir.
    #:
    #: **Aucune de ces colonnes n'est ecrite par l'agent.** Elles sont
    #: construites par Hermes OS a partir du chemin d'appel : un agent qui
    #: pourrait se declarer `HUMAIN` sortirait de quarantaine tout seul.
    origine: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    source: Mapped[str | None] = mapped_column(String, nullable=True)
    promu_par: Mapped[str | None] = mapped_column(String, nullable=True)
    verifie_le: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    @property
    def provenance(self):
        """La provenance de cette entree, reconstruite depuis ses colonnes.

        Nommee `provenance` parce que c'est l'attribut que
        `confiance.provenance_de()` cherche en premier : la meme fonction
        sert donc le chemin MCP et le Context Relay, sans seconde
        politique.

        Une ligne sans `origine` rend une `Provenance()` par defaut —
        `INCONNUE`, quarantaine. Les quatre entrees historiques sont dans
        ce cas, et le restent.
        """
        import dataclasses

        from backend.memory.confiance import Confiance, Origine, Provenance

        if not self.origine:
            return Provenance()
        try:
            origine = Origine(self.origine)
        except ValueError:          # une origine ecrite par une version
            return Provenance()      # ulterieure : prudence, pas confiance

        # La meme fabrique qu'a l'ecriture : la confiance se derive de
        # l'origine, elle ne se relit pas d'une colonne. Une colonne de
        # confiance serait modifiable sans changer l'origine — c'est-a-dire
        # promouvable sans acteur.
        base = Provenance.depuis(origine, self.source or "")
        if self.promu_par:
            return dataclasses.replace(
                base, confiance=Confiance.FIABLE,
                promu_par=self.promu_par, verifie_le=self.verifie_le)
        return base


def _hash(content: str) -> str:
    return hashlib.sha256(content.strip().encode("utf-8")).hexdigest()


def add_memory(
    session: Session,
    *,
    type_: str,
    content: str,
    tags: list[str] | None = None,
    confidence: float = 1.0,
    project_id: str | None = None,
    provenance: "object | None" = None,
) -> MemoryEntry:
    """Adds an entry, or returns the existing one if the same content
    (exact match) was already stored under the same type *and project*
    (§11.5) — the same fact remembered for two different projects is two
    entries, not a dedup hit across them."""
    content_hash = _hash(content)
    existing = session.execute(
        select(MemoryEntry).where(
            MemoryEntry.type == type_,
            MemoryEntry.content_hash == content_hash,
            MemoryEntry.project_id == project_id,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    entry = MemoryEntry(
        id=str(uuid.uuid4()),
        project_id=project_id,
        type=type_,
        content=content,
        content_hash=content_hash,
        tags=",".join(tags or []),
        confidence=confidence,
        created_at=datetime.now(UTC),
        # HOS-249 : `provenance` est un objet construit par l'appelant
        # **Hermes OS**, jamais des champs libres. Absent, l'entree reste
        # sans origine — donc `INCONNUE`, donc en quarantaine.
        origine=getattr(getattr(provenance, "origine", None), "value", None),
        source=getattr(provenance, "source", None) or None,
        promu_par=getattr(provenance, "promu_par", None),
        verifie_le=getattr(provenance, "verifie_le", None),
    )
    session.add(entry)
    session.commit()
    session.refresh(entry)
    return entry


class ProjetInconnu(ValueError):
    """Un `project_id` qui ne resout vers aucun projet (HOS-249).

    Refuser plutot que rendre une liste vide : une liste vide se lit
    « ce projet n'a rien memorise », un refus se lit « ce projet n'existe
    pas ». Confondre les deux laisse un agent croire qu'il travaille dans
    un projet vide alors qu'il s'est trompe de cle.

    C'est le contrat qu'Aegis applique deja au meme parametre :
    `REQUIRE_HUMAN_VALIDATION` sur un `project_id` non resolu, « don't
    fail open on the unexpected ».
    """


def portee_de_l_agent(stmt, project_id: str | None):
    """La portee que voit un agent, appliquee au niveau du stockage.

    Trois regles, et la premiere est celle qui manquait (HOS-249) :

    * `project_id=None` → **le niveau permanent seul** (§12), jamais tous
      les projets. `project_memory.permanent_memory` avait deja nomme le
      danger : « la confusion des deux niveaux est precisement la facon
      dont une decision prise pour un projet finit lue comme une regle
      globale » ;
    * un projet nomme → **ce projet et le permanent**. Le permanent est
      visible de partout, c'est ce qui le rend permanent ;
    * un projet inconnu → l'appelant leve `ProjetInconnu` avant d'arriver
      ici.

    Au contrat de stockage, pas dans l'appelant : une convention que
    chaque appelant reapplique est une convention qu'un appelant oubliera.
    """
    if project_id is None:
        return stmt.where(MemoryEntry.project_id.is_(None))
    return stmt.where(or_(MemoryEntry.project_id == project_id,
                          MemoryEntry.project_id.is_(None)))


def list_memories(
    session: Session, *, type_: str | None = None, project_id: str | None = None
) -> list[MemoryEntry]:
    stmt = select(MemoryEntry).order_by(MemoryEntry.created_at.desc())
    if type_:
        stmt = stmt.where(MemoryEntry.type == type_)
    if project_id is not None:
        stmt = stmt.where(MemoryEntry.project_id == project_id)
    return list(session.execute(stmt).scalars())


def search_memories(
    session: Session,
    query: str,
    *,
    limit: int = 5,
    type_: str | None = None,
    project_id: str | None = None,
) -> list[MemoryEntry]:
    """Text search over what ``add_memory`` actually stored (HOS-086).

    ``memory_remember``/``memory_search`` looked like one round trip and were
    two unrelated stores: remember wrote a MemoryEntry row here, while search
    queried the *document* vector index, so a freshly remembered fact was
    never findable — the failure the user reported as
    ``memory_remember → OK, memory_search → []``.

    Deliberately a LIKE scan over content and tags rather than an embedding
    lookup: these rows are short, explicitly-written facts, they are not
    embedded anywhere today, and inventing a second vector index for them is
    exactly the parallel-memory duplication this system is trying to shed.
    Semantic retrieval over *documents* stays where it already is.
    """
    terms = [t for t in (query or "").split() if t]
    if not terms:
        return []
    stmt = select(MemoryEntry).order_by(MemoryEntry.created_at.desc())
    if type_:
        stmt = stmt.where(MemoryEntry.type == type_)
    if project_id is not None:
        stmt = stmt.where(MemoryEntry.project_id == project_id)
    # Any term may match (OR): a caller searching "hermes deployment port"
    # should still find a memory that only mentions the port.
    stmt = stmt.where(
        or_(*[MemoryEntry.content.ilike(f"%{t}%") for t in terms]
            + [MemoryEntry.tags.ilike(f"%{t}%") for t in terms])
    )
    rows = list(session.execute(stmt).scalars())
    # Rank by how many distinct terms a row actually matches, so an exact hit
    # outranks an incidental one-word overlap; recency breaks ties via the
    # ORDER BY above (Python's sort is stable).
    lowered = [t.lower() for t in terms]

    def _score(entry: MemoryEntry) -> int:
        haystack = f"{entry.content or ''} {entry.tags or ''}".lower()
        return sum(1 for t in lowered if t in haystack)

    rows.sort(key=_score, reverse=True)
    return rows[:limit]


def search_pour_agent(
    session: Session,
    query: str,
    *,
    limit: int = 5,
    project_id: str | None = None,
) -> list[MemoryEntry]:
    """La recherche telle qu'un **agent** la voit (HOS-249).

    Deux choses de plus que `search_memories`, et une seule raison pour
    les deux : ce que l'agent lit revient dans son raisonnement.

    1. **La portee** — `portee_de_l_agent` : `None` rend le permanent
       seul, un projet nomme rend ce projet et le permanent. Jamais tous
       les projets ;
    2. **La quarantaine** — `confiance.filtrer`, la meme fonction que le
       Context Relay. Une entree sans provenance est `INCONNUE`, donc
       ecartee. Ecrire un second filtre pour MCP aurait cree deux
       politiques de securite, ce que ce depot refuse partout ailleurs.

    `search_memories` reste inchangee pour les lectures **systeme** — la
    console, les rapports — qui ont le droit de tout voir. Ce sont deux
    droits differents, pas deux implementations du meme.
    """
    from backend.memory.confiance import filtrer

    terms = [t for t in (query or "").split() if t]
    if not terms:
        return []
    stmt = select(MemoryEntry).order_by(MemoryEntry.created_at.desc())
    stmt = portee_de_l_agent(stmt, project_id)
    stmt = stmt.where(
        or_(*[MemoryEntry.content.ilike(f"%{t}%") for t in terms]
            + [MemoryEntry.tags.ilike(f"%{t}%") for t in terms])
    )
    rows = list(session.execute(stmt).scalars())
    lowered = [t.lower() for t in terms]

    def _score(entry: MemoryEntry) -> int:
        haystack = f"{entry.content or ''} {entry.tags or ''}".lower()
        return sum(1 for t in lowered if t in haystack)

    rows.sort(key=_score, reverse=True)
    # Le filtre apres le classement et **avant** la coupe : filtrer apres
    # `[:limit]` rendrait moins de resultats que demande alors que des
    # entrees valides attendaient derriere une quarantainee.
    return filtrer(rows)[:limit]


class DejaPromue(ValueError):
    """Une memoire deja sortie de quarantaine (HOS-250).

    Refuser plutot que reecrire : une seconde promotion ecraserait le nom
    du premier promoteur et sa date, c'est-a-dire la trace de la decision
    qu'on veut justement pouvoir relire apres coup.
    """


def promouvoir(session: Session, memory_id: str, *, par: str) -> MemoryEntry:
    """Sortir une memoire de quarantaine, en nommant qui l'a decide.

    ## Ce que la promotion ne fait pas

    Elle **ne change pas l'origine**. Une memoire ecrite par l'agent
    reste `AGENT` pour toujours : c'est le fait historique, et l'effacer
    rendrait impossible de repondre a « d'ou venait cette information ? »
    apres coup.

    Ce qui change est la **confiance**, et `Provenance` separait deja les
    deux — `origine` dit d'ou ca vient, `confiance` dit ce qu'on en fait.
    Il n'y avait donc aucune colonne a inventer : `promu_par` renseigne
    suffit a faire basculer la seconde en laissant la premiere intacte.

    ## Pourquoi elle leve plutot que de rendre `False`

    `MemoryManager.promouvoir()` annoncait un succes sans rien ecrire
    (HOS-249 l'a mesure : `AttributeError` avalee, puis
    `memory.promoted` publie). Une promotion qui ne promeut pas est pire
    qu'une absence de promotion : elle fait croire qu'une memoire est
    validee. Ici, un echec est une exception, et l'appelant ne peut pas
    le confondre avec un succes.

    ## Atomicite

    L'ecriture est commitee, puis la ligne est **relue** : le succes est
    conditionne a l'etat constate, pas a l'absence d'erreur.
    """
    from datetime import UTC as _UTC

    if not par or not par.strip():
        # La regle de `Provenance.promouvoir` : « une promotion sans
        # acteur nomme n'est pas une promotion ». Appliquee ici aussi,
        # pour que la persistance ne soit pas une porte plus permissive
        # que l'objet.
        from backend.memory.confiance import PromotionRefusee

        raise PromotionRefusee(
            "une promotion doit nommer qui l'a decidee : sans acteur, on "
            "ne peut pas revenir sur la decision apres coup")

    entree = session.get(MemoryEntry, memory_id)
    if entree is None:
        raise KeyError(memory_id)
    if entree.promu_par:
        raise DejaPromue(
            f"memoire {memory_id!r} deja promue par {entree.promu_par!r} "
            f"le {entree.verifie_le}")

    entree.promu_par = par.strip()
    entree.verifie_le = datetime.now(_UTC)
    session.commit()
    session.refresh(entree)

    # Le succes se constate, il ne se suppose pas.
    from backend.memory.confiance import provenance_de

    if provenance_de(entree).en_quarantaine:
        raise RuntimeError(
            f"promotion de {memory_id!r} non effective : la memoire est "
            "toujours en quarantaine apres ecriture")
    return entree


def get_memory(session: Session, memory_id: str) -> MemoryEntry | None:
    return session.get(MemoryEntry, memory_id)


def delete_memory(session: Session, memory_id: str) -> bool:
    entry = session.get(MemoryEntry, memory_id)
    if entry is None:
        return False
    session.delete(entry)
    session.commit()
    return True
