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


def _autorise(projet: Project | None) -> bool:
    """Ce projet accorde-t-il un acces au disque *en ce moment* ?

    Le predicat unique. Il etait ecrit trois fois — ici dans
    `active_validated_project_roots`, dans
    `conversation/routes._active_validated_project_root`, et dans
    `core/bootstrap/service_registry._workspace_project_for` — trois
    copies de la meme regle a trois endroits, dont deux se decrivaient
    elles-memes comme « la meme verification, repetee ». Trois copies
    d'une regle de securite sont trois occasions de diverger.
    """
    return (
        projet is not None
        and bool(projet.root_path)
        and projet.status == ProjectStatus.ACTIVE.value
        and _est_valide(projet)
    )


def authorized_root(project_id: str | None) -> str | None:
    """La racine que ce projet autorise en ce moment, ou `None`.

    **L'habilitation est nominative** (A-4). Avant HOS-292, la validation
    d'un projet elargissait la liste blanche d'Aegis pour *toute* action,
    y compris celles qui ne nommaient aucun projet : valider A et B
    revenait a autoriser A ∪ B partout. Mesure du 2026-09-11, deux
    projets actifs et valides, lecture de `ws-b/secret.txt` :

        project_id=A    -> deny   (le retrecissement fonctionnait)
        project_id=None -> allow  (et le contenu de B etait rendu)

    Un appel MCP direct `files_read(chemin)` sans `project_id` lisait
    donc le workspace d'un projet qu'il ne nommait pas. La validation
    prouvait qu'un dossier *existe* ; elle n'a jamais dit *qui* peut y
    toucher. C'est ce que veut dire « validee, non autorisee ».

    Rend `None` plutot que de lever si le magasin est indisponible : une
    habilitation manquante est sans danger, une verification qui plante
    ne l'est pas — meme contrat que `active_validated_project_roots`.
    """
    if not project_id:
        return None
    try:
        projet = get_project_store().get(project_id)
    except Exception:
        return None
    return projet.root_path if _autorise(projet) else None


@lru_cache
def get_project_store() -> ProjectStore:
    return ProjectStore(get_settings().sqlite_path)


def active_validated_project_roots() -> list[str]:
    """Every ACTIVE, validation_status="valid" Project's root_path — the
    single real source of "which local folders has the user actually
    authorized right now" — pour l'**admission** : « ce dossier est-il un
    workspace autorise ? ». Son appelant est le controle de securite en
    amont d'une Mission (mission/routes.py's _check_mission_security).

    Ce n'est **pas** ce qui accorde une portee a une action. Depuis
    HOS-292 l'habilitation est nominative : `authorized_root` ci-dessus
    rend la racine du seul projet qu'une action nomme. Passer cette
    liste-ci a Aegis, ce que faisait `_dynamic_allowed_paths`, revenait a
    donner tous les workspaces a toute action — le defaut A-4.

    Les deux partagent le meme predicat (`_autorise`), donc un projet est
    admis et porte par la meme regle, jamais par deux implementations qui
    derivent.

    Fails closed (empty list) rather than raising if the store is
    briefly unavailable — a missing grant is safe, a crashing security
    check is not."""
    try:
        projects = get_project_store().list(status=ProjectStatus.ACTIVE)
    except Exception:
        return []
    return [p.root_path for p in projects if _autorise(p)]
