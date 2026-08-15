"""ProjectStore — owns the SQLite engine/session factory for Project
CRUD, the same way core/message_bus.py's MessageBus owns its own
(reusing the same SQLite file, see backend/memory/db.py). Not an
"agent" (like Kronos/Aegis/Echo): Projects, like the message bus and
the workflow engine, is core infrastructure with no LLM involvement, so
it isn't registered in config/agents.yaml or built through AgentRegistry
— routes and MCP tools reach it via the module-level get_project_store()
singleton instead.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from backend.core.config import get_settings
from backend.memory.db import init_db, make_engine, make_session_factory
from backend.projects import project_manager
from backend.projects.project_manager import Project, ProjectStatus, ValidationStatus


class ProjectStore:
    def __init__(self, sqlite_path: str) -> None:
        engine = make_engine(sqlite_path)
        init_db(engine)
        self._session_factory = make_session_factory(engine)

    def create(
        self,
        *,
        name: str,
        description: str = "",
        root_path: str | None = None,
        repository: str | None = None,
        branch: str | None = None,
        tags: list[str] | None = None,
    ) -> Project:
        with self._session_factory() as session:
            return project_manager.create_project(
                session, name=name, description=description, root_path=root_path,
                repository=repository, branch=branch, tags=tags,
            )

    def get(self, project_id: str) -> Project | None:
        with self._session_factory() as session:
            return project_manager.get_project(session, project_id)

    def list(
        self, *, status: ProjectStatus | str | None = None, tag: str | None = None
    ) -> list[Project]:
        with self._session_factory() as session:
            return project_manager.list_projects(session, status=status, tag=tag)

    def update(
        self,
        project_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        root_path: str | None = None,
        repository: str | None = None,
        branch: str | None = None,
        status: ProjectStatus | str | None = None,
        tags: list[str] | None = None,
    ) -> Project | None:
        with self._session_factory() as session:
            return project_manager.update_project(
                session,
                project_id,
                name=name,
                description=description,
                root_path=root_path,
                repository=repository,
                branch=branch,
                status=status,
                tags=tags,
            )

    def delete(self, project_id: str) -> bool:
        with self._session_factory() as session:
            return project_manager.delete_project(session, project_id)

    def validate(self, project_id: str) -> Project | None:
        """Really probe project.root_path on disk (see
        project_manager.validate_project_path) and persist the result —
        the only source of truth active_validated_project_roots() below
        (and therefore Aegis's dynamic whitelist) trusts."""
        with self._session_factory() as session:
            return project_manager.validate_project(session, project_id)

    def ensure_for_path(self, root_path: str, *, name: str = "") -> Project | None:
        """Le Project actif et validé qui couvre ce dossier, créé au besoin.

        Mesuré le 2026-08-15 : un objectif autonome lancé avec un
        `local_path` rapportait **6 tâches sur 6 réussies en 41 secondes et
        zéro fichier écrit**. La cause tenait en une phrase — un chemin brut
        n'est pas un `project_id`, et `_workspace_project_for` exige un
        Project *enregistré et validé*. La résolution rendait `None`, la
        tâche n'avait aucun outil, et le modèle, sommé d'écrire un fichier
        sans pouvoir le faire, a produit un appel d'outil **en texte** vers
        un chemin Linux inventé. Ce texte a été rangé comme résultat et
        compté comme réussite.

        Enregistrer plutôt qu'assouplir la résolution : toute la chaîne de
        sécurité déjà écrite et testée s'applique sans exception — sonde
        réelle du disque, `validation_status`, whitelist dynamique d'Aegis.
        Accepter un chemin brut aurait créé une seconde porte vers le
        disque à côté de celle-ci, et l'une des deux aurait fini par
        diverger.

        Rend `None` si le dossier ne passe pas la validation. L'appelant
        doit alors **refuser**, pas continuer sans outils.
        """
        cible = Path(root_path).expanduser()
        try:
            cible = cible.resolve()
        except OSError:
            return None

        for projet in self.list(status=ProjectStatus.ACTIVE):
            if not projet.root_path:
                continue
            try:
                if Path(projet.root_path).resolve() != cible:
                    continue
            except OSError:
                continue
            # Revalidé à chaque fois : un dossier autorisé la semaine
            # dernière peut avoir été supprimé, déplacé ou passé en lecture
            # seule depuis. Se fier au verdict stocké ferait accorder un
            # accès sur une mesure périmée.
            revalide = self.validate(projet.id)
            return revalide if _est_valide(revalide) else None

        cree = self.create(
            name=name or cible.name or "workspace",
            description="Créé automatiquement pour un objectif autonome (HOS-119)",
            root_path=str(cible),
        )
        valide = self.validate(cree.id)
        return valide if _est_valide(valide) else None


def _est_valide(projet: Project | None) -> bool:
    return bool(projet) and projet.validation_status == ValidationStatus.VALID.value


@lru_cache
def get_project_store() -> ProjectStore:
    return ProjectStore(get_settings().sqlite_path)


def active_validated_project_roots() -> list[str]:
    """Every ACTIVE, validation_status="valid" Project's root_path — the
    single real source of "which local folders has the user actually
    authorized right now". Both AegisAgent._dynamic_allowed_paths
    (agents/aegis.py, the Assistant chat / MCP / file_tools path) and
    Mission's pre-flight security gate (mission/routes.py's
    _check_mission_security) call this same function rather than each
    resolving it independently — a Mission bound to a validated
    workspace must be granted access by the exact same rule a chat
    session bound to it would be, not a second, potentially-drifting
    implementation of "is this project currently authorized".

    Fails closed (empty list) rather than raising if the store is
    briefly unavailable — a missing grant is safe, a crashing security
    check is not."""
    try:
        projects = get_project_store().list(status=ProjectStatus.ACTIVE)
    except Exception:
        return []
    return [
        p.root_path for p in projects
        if p.root_path and p.validation_status == ValidationStatus.VALID.value
    ]
