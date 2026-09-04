"""FastAPI routes for the Mission Graph Engine (HOS-041).

This surface used to be a DAG container and nothing more: it required the caller
to supply ``nodes`` and ``edges``, never asked the Mission Planner to decompose a
described goal, and ``/start`` only flipped the status label to ``running``
because nothing ever drove ``GraphExecutor.execute_step()``. A mission created
here reported ``nodes: 0`` and stayed at 0% forever, silently, while
``/api/v1/autonomous`` executed for real.

Both surfaces now run the same pipeline (R-002 P1): the planner produces the DAG,
and the graph executor walks it with its ``execute_node`` hook bound to the
shared ``MissionExecutor``.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from collections import OrderedDict
from typing import Any, Optional

from fastapi import APIRouter, Body

from backend.mission.graph_executor import GraphExecutor
from backend.mission.mission_models import (
    Mission,
    MissionEdge,
    MissionNode,
    MissionPriority,
    MissionStatus,
    MissionType,
    NodeStatus,
    build_mission_report,
)

logger = logging.getLogger("hermes_os.mission.routes")

router = APIRouter(prefix="/missions", tags=["missions"])

_executor: Optional[GraphExecutor] = None
_planner: Optional[Any] = None
_memory_manager: Optional[Any] = None
_evolution_engine: Optional[Any] = None
_aegis_engine: Optional[Any] = None
#: Les missions que ce routeur expose (M-8, HOS-120).
#:
#: C'était un `dict` nu, sans verrou et sans borne. Deux défauts réels :
#:
#: * **sans verrou** — `register_mission` est appelé depuis l'orchestrateur
#:   autonome, qui exécute ses nœuds dans un pool de fils, pendant que les
#:   routes HTTP lisent le même dict. Un `dict` Python ne corrompt pas sa
#:   structure sous le GIL, mais « lire pendant qu'on écrit » n'en reste
#:   pas moins une lecture sur un état que personne ne coordonne ;
#: * **sans borne** — chaque mission y restait pour la durée du processus.
#:   Un serveur qui tourne des semaines les garde toutes, avec leurs nœuds
#:   et leurs `result_summary`.
#:
#: La persistance, elle, **reste à faire** : au redémarrage la liste est
#: vide, et c'est écrit ici plutôt que sous-entendu.
#:
#: 200 n'est pas une mesure. C'est un ordre de grandeur : bien au-delà de ce
#: qu'une session d'usage produit, bien en deçà de ce qui pèse.
MAX_MISSIONS_EN_MEMOIRE = 200

#: Statuts depuis lesquels plus rien ne bougera. Ce sont les seules missions
#: qu'on s'autorise à évincer : évincer une mission `running` la rendrait
#: introuvable *pendant* qu'elle s'exécute, et l'exécuteur continuerait de
#: la faire avancer dans le vide. Une borne qui casse ce qui tourne est
#: pire que l'absence de borne.
STATUTS_TERMINAUX = frozenset({
    MissionStatus.COMPLETED,
    MissionStatus.FAILED,
    MissionStatus.CANCELLED,
})


class _RegistreMissions:
    """Un cache borné devant une base durable, avec la forme d'un dict.

    L'API imite celle du `dict` qu'il remplace, pour que les appelants — y
    compris les tests qui font `monkeypatch.setitem` ou `.clear()` — n'aient
    pas à connaître son existence.

    ## Ce qui a changé en HOS-245 (dette M-8)

    L'`OrderedDict` était **toute** la mémoire du système : au redémarrage
    il était vide, et au-delà de 200 missions le FIFO en effaçait
    définitivement — pendant que le processus tournait toujours.

    Or HOS-221 avait rendu le registre des **runs** durable, et HOS-240 lui
    avait ajouté une réconciliation. Un run posé `PERDU` désignait donc une
    mission qui n'existait plus : le journal survivait, son sujet non.

    La source de vérité est désormais `MagasinMissions`, dans la même base
    que les runs. L'`OrderedDict` reste devant, borné, et **l'éviction ne
    perd plus rien** : elle libère de la mémoire, la ligne reste.
    """

    def __init__(self, maximum: int = MAX_MISSIONS_EN_MEMOIRE,
                 magasin: Any = None) -> None:
        self._verrou = threading.RLock()
        self._maximum = maximum
        #: Ordonné par insertion : c'est ce qui fait de l'éviction un FIFO
        #: sans avoir à porter d'horodatage.
        self._missions: "OrderedDict[str, Mission]" = OrderedDict()
        self._magasin_injecte = magasin
        self._magasin_resolu = magasin is not None
        #: Le cache n'est rempli depuis la base qu'une fois, au premier
        #: parcours — pas à la construction, qui a lieu à l'import.
        self._hydrate = False

    @property
    def _magasin(self) -> Any:
        """Construit à la première utilisation, jamais à l'import.

        Le construire au niveau du module créerait la base d'état au seul
        fait d'importer `mission.routes` — y compris dans un test qui ne
        veut pas y toucher, et avant que `HERMES_DATA_DIR` ait pu être posé
        par un `monkeypatch`.

        Un échec ne fait pas tomber le service : Hermes continue avec le
        seul cache, comme avant HOS-245, et le dit. Une correction de
        persistance qui empêcherait de créer une mission serait un recul.
        """
        with self._verrou:
            if not self._magasin_resolu:
                self._magasin_resolu = True
                try:
                    from backend.mission.persistance import MagasinMissions

                    self._magasin_injecte = MagasinMissions()
                except Exception:
                    logger.warning(
                        "missions non persistées : le magasin durable n'a pas "
                        "pu s'ouvrir — elles disparaîtront au redémarrage",
                        exc_info=True)
                    self._magasin_injecte = None
            return self._magasin_injecte

    def __setitem__(self, mission_id: str, mission: Mission) -> None:
        # Écriture d'abord, cache ensuite : si la base refuse, on ne veut
        # pas d'une mission visible en mémoire et absente du disque.
        magasin = self._magasin
        if magasin is not None:
            try:
                magasin.enregistrer(mission)
            except Exception:
                logger.warning("mission %s non persistée", mission_id,
                               exc_info=True)
        with self._verrou:
            self._missions[mission_id] = mission
            self._missions.move_to_end(mission_id)
            self._evincer()

    def persister(self, mission: Mission) -> None:
        """Écrire une **mutation** d'une mission déjà connue (HOS-252).

        Deux différences avec `__setitem__`, et une seule raison pour les
        deux : ici, un échec d'écriture doit se voir.

        `__setitem__` sert la **création** et avale l'échec du magasin —
        « une correction de persistance qui empêcherait de créer une
        mission serait un recul », et c'est toujours vrai. Mais il met
        alors le cache à jour quand même : la mémoire affirme une
        persistance qui n'a pas eu lieu, et c'est exactement le défaut que
        HOS-252 corrige. Une mutation déterminante — démarrage, nœud
        terminal, fin, annulation — est ce dont dépendent le budget
        missionnel et la reprise ; l'écrire à moitié est pire que ne pas
        l'écrire.

        Donc : **le disque d'abord, le cache seulement s'il a accepté, et
        l'erreur remonte à l'appelant.** Le cache ne prétend jamais qu'une
        mutation est durable alors qu'elle ne l'est pas.
        """
        magasin = self._magasin
        if magasin is not None:
            magasin.enregistrer(mission)
        with self._verrou:
            self._missions[mission.mission_id] = mission
            self._missions.move_to_end(mission.mission_id)
            self._evincer()

    def _evincer(self) -> None:
        """Sous verrou uniquement. **Ne touche que le cache** (HOS-245).

        Ne retire que des missions terminées, de la plus ancienne à la plus
        récente. Si toutes celles qui restent sont encore actives, la borne
        est dépassée et on la laisse l'être : le journal le dit, ce qui vaut
        mieux qu'une mission en cours qui disparaît.

        Depuis HOS-245 la ligne reste en base : une mission évincée se
        relit. C'était le second visage de la dette M-8 — au-delà de 200
        missions, on en perdait définitivement sans même redémarrer.
        """
        if len(self._missions) <= self._maximum:
            return
        for mission_id, mission in list(self._missions.items()):
            if len(self._missions) <= self._maximum:
                return
            if mission.status in STATUTS_TERMINAUX:
                del self._missions[mission_id]
        if len(self._missions) > self._maximum:
            logger.warning(
                "registre des missions à %d entrées pour une borne de %d — "
                "aucune mission terminée à évincer, elles sont toutes encore "
                "actives", len(self._missions), self._maximum)

    def _relire(self, mission_id: str) -> Optional[Mission]:
        """Chercher en base une mission absente du cache, et l'y remettre.

        C'est le chemin qu'emprunte une mission évincée par le FIFO, ou
        créée avant le dernier redémarrage.
        """
        magasin = self._magasin
        if magasin is None:
            return None
        try:
            mission = magasin.lire(mission_id)
        except Exception:  # pragma: no cover - base illisible
            logger.warning("lecture de la mission %s impossible", mission_id,
                           exc_info=True)
            return None
        if mission is not None:
            with self._verrou:
                self._missions[mission_id] = mission
                self._missions.move_to_end(mission_id)
                self._evincer()
        return mission

    def __getitem__(self, mission_id: str) -> Mission:
        with self._verrou:
            if mission_id in self._missions:
                return self._missions[mission_id]
        mission = self._relire(mission_id)
        if mission is None:
            raise KeyError(mission_id)
        return mission

    def __delitem__(self, mission_id: str) -> None:
        """Retirer une mission — **sans jamais toucher ses runs** (T-21).

        Une suppression *voulue*, contrairement à l'éviction : elle emporte
        la ligne du magasin en plus de l'entrée de cache. `_evincer` ne
        libère que la mémoire ; ici la mission disparaît pour de bon.

        ## Ce qui n'est pas supprimé, et pourquoi

        **Les runs de cette mission restent.** `de_la_mission()` continue
        de les rendre, avec leur objectif, leur modèle, leur runtime, leur
        fournisseur, leur workspace, leur tentative et leur contrat — le
        run porte son propre instantané depuis HOS-219, précisément pour
        rester lisible sans son sujet.

        Aucune cascade ne doit être ajoutée. Le Ledger existe parce que,
        la nuit du 29 au 30 août, la trace disparaissait : un journal
        d'audit dont les lignes s'effacent avec leur sujet n'est plus un
        journal. `Registre` n'expose d'ailleurs aucune suppression, et
        `MagasinMissions.supprimer` ne touche que la table `missions` —
        les deux moitiés du contrat, chacune de son côté.

        Un run dont la mission a disparu n'en devient ni perdu ni douteux :
        l'absence de mission n'est ni une `Cause`, ni une condition de
        réconciliation. Celle-ci décide sur la seule preuve qui vaut — le
        processus porteur existe-t-il encore.

        ## Ce que cette primitive n'est pas

        **Pas une fonctionnalité produit.** Aucune route, aucun service ne
        l'appelle : mesuré en passe 21, zéro appelant de production. Elle
        sert aux tests et à un geste d'opérateur délibéré. Ajouter un
        `DELETE /missions/{id}` demanderait d'abord de décider d'une
        politique de rétention — ce qui n'est pas fait, et l'absence de
        porte est aujourd'hui ce qui protège.
        """
        present = False
        with self._verrou:
            if mission_id in self._missions:
                del self._missions[mission_id]
                present = True
        magasin = self._magasin
        if magasin is not None:
            if not present and magasin.lire(mission_id) is None:
                raise KeyError(mission_id)
            magasin.supprimer(mission_id)
        elif not present:
            raise KeyError(mission_id)

    def __contains__(self, mission_id: object) -> bool:
        with self._verrou:
            if mission_id in self._missions:
                return True
        return isinstance(mission_id, str) and self._relire(mission_id) is not None

    def __len__(self) -> int:
        """La taille du **plan de travail**, cohérente avec `values()`.

        Une première version de HOS-245 rendait ici le total en base. Elle
        rendait l'objet incohérent — `len(r)` et `len(r.values())` ne
        disaient plus la même chose — et faisait fuir chaque test dans le
        suivant, puisque tous les registres non injectés partagent une
        table. Deux défauts pour une seule ligne trop ambitieuse.

        Le total durable existe, et il a son propre nom : `total()`. Les
        confondre était l'erreur.
        """
        self._hydrater()
        with self._verrou:
            return len(self._missions)

    def total(self) -> int:
        """Combien de missions Hermes a gardées, cache ou non.

        Distinct de `len()` : celui-ci décrit ce qu'on a sous la main,
        celui-là ce qu'on a conservé. Un compteur de console qui plafonne
        à la borne mentirait ; un `len()` qui contredit `values()` aussi.
        """
        magasin = self._magasin
        if magasin is not None:
            try:
                return magasin.nombre()
            except Exception:  # pragma: no cover
                pass
        with self._verrou:
            return len(self._missions)

    def get(self, mission_id: str, defaut: Any = None) -> Any:
        try:
            return self[mission_id]
        except KeyError:
            return defaut

    def pop(self, mission_id: str, *defaut: Any) -> Any:
        try:
            mission = self[mission_id]
        except KeyError:
            if defaut:
                return defaut[0]
            raise
        del self[mission_id]
        return mission

    def clear(self) -> None:
        """Vide le cache **et** la base.

        Les tests l'appellent entre deux cas ; ne vider que le cache
        laisserait chaque test hériter des missions du précédent, et la
        suite deviendrait dépendante de son ordre.
        """
        with self._verrou:
            self._missions.clear()
            # Vider puis relister ne doit pas ressusciter ce qu'on vient
            # d'effacer : l'hydratation est refaite, sur une base vide.
            self._hydrate = False
        magasin = self._magasin
        if magasin is not None:
            try:
                magasin.vider()
            except Exception:  # pragma: no cover
                logger.warning("magasin des missions non vidé", exc_info=True)

    def values(self) -> list[Mission]:
        """Une *copie*, pas une vue — le **plan de travail** courant.

        Les routes de liste itèrent dessus pendant que l'orchestrateur
        autonome enregistre ses missions depuis son pool de fils ; une vue
        lèverait `RuntimeError: dictionary changed size during iteration`
        au premier chevauchement, et de façon intermittente.

        ## Pourquoi le cache, et non toute la base (HOS-245)

        Une première version de ce jalon relisait la base entière ici. Le
        test `test_lister_pendant_qu_on_enregistre_ne_leve_pas` l'a
        immédiatement démasquée : il appelle `values()` deux mille fois
        pendant qu'un autre fil écrit sans discontinuer, et chaque appel
        désérialisait le JSON de **toutes** les missions accumulées. Le
        fichier passait de quelques secondes à plus de dix minutes.

        Ce registre est borné par construction — 200 — et c'est ce qu'il a
        toujours promis. Ce que HOS-245 corrige n'est pas cette borne mais
        la **perte** : le cache est désormais hydraté depuis la base au
        premier accès, si bien qu'après un redémarrage la liste n'est plus
        vide, et toute mission, même évincée, reste lisible par son
        identifiant. L'historique complet se lit par `MagasinMissions`,
        qui pagine.
        """
        self._hydrater()
        with self._verrou:
            return list(self._missions.values())

    def items(self) -> list[tuple[str, Mission]]:
        self._hydrater()
        with self._verrou:
            return list(self._missions.items())

    def _hydrater(self) -> None:
        """Remplir le cache depuis la base, une seule fois.

        Sans cela, un redémarrage laissait la console vide alors que les
        missions étaient bien sur le disque : la persistance aurait été
        invisible, ce qui revient presque à ne pas l'avoir.
        """
        with self._verrou:
            if self._hydrate:
                return
            self._hydrate = True
        magasin = self._magasin
        if magasin is None:
            return
        try:
            recentes = magasin.tous()[:self._maximum]
        except Exception:  # pragma: no cover
            logger.warning("hydratation du cache des missions impossible",
                           exc_info=True)
            return
        with self._verrou:
            # Les plus anciennes d'abord : `tous()` rend les plus récentes
            # en tête, et l'ordre d'insertion est ce qui fait le FIFO.
            for mission in reversed(recentes):
                if mission.mission_id not in self._missions:
                    self._missions[mission.mission_id] = mission
            self._evincer()


_missions = _RegistreMissions()

#: Safety valve on the DAG walk. execute_step() runs every currently-ready node,
#: so a well-formed graph needs at most one pass per dependency level; this bounds
#: a graph that somehow never reaches a terminal state.
MAX_EXECUTION_PASSES = 100


def create_mission_routes(executor: GraphExecutor) -> APIRouter:
    global _executor
    _executor = executor
    return router


def set_mission_planner(planner: Any) -> None:
    """Inject the Mission Planner.

    Called from the planner's own route binder rather than this one: binders run
    inline as each service is built, and the planner is built after the graph
    executor it depends on, so pulling it in from here would both fail and create
    a dependency cycle.
    """
    global _planner
    _planner = planner


def set_memory_manager(mm: Any) -> None:
    """Inject the memory manager so terminal missions write an episode.

    Same injection pattern as set_mission_planner(), for the same reason:
    /autonomous fed episodic memory from mission one (AutonomousMemoryLoop)
    while /missions never did, so a mission run through this router left
    episodic.total unmoved no matter how many missions completed here —
    both surfaces share one execution engine since R-002 P1, but recording
    the outcome was never wired for this one."""
    global _memory_manager
    _memory_manager = mm


def set_evolution_engine(ee: Any) -> None:
    """Inject the Evolution Engine so a completed mission feeds real
    metrics into it (HOS-068) — before this, only AutonomousMemoryLoop did
    this for autonomous goals; a mission run through this router never
    reached it at all."""
    global _evolution_engine
    _evolution_engine = ee


def register_mission(mission: Mission) -> None:
    """Make a mission built elsewhere visible through this router's own
    list/get/graph/progress/report endpoints (HOS-068).

    AutonomousOrchestrator's real DAG path (HOS-067) builds a Mission via
    the same MissionPlanner this router uses, but that mission never
    reached this module's own ``_missions`` dict — the only thing
    ``create_mission()`` ever populated it. A mission started from
    Autonomous was therefore invisible to ``GET /missions`` even though it
    ran on the exact same GraphExecutor. One call from the orchestrator
    after ``build_mission()`` closes that gap without merging the two
    entry points into one.
    """
    _missions[mission.mission_id] = mission


def persist_mission(mission: Mission) -> None:
    """Rendre durable une mutation déterminante d'une mission (HOS-252).

    Injectée dans `GraphExecutor` par le bootstrap plutôt qu'importée par
    lui : `mission/graph_executor.py` n'a aucune raison de connaître le
    routeur, et le lui faire connaître inverserait la dépendance entre la
    couche d'exécution et la couche HTTP.

    C'est le **même** magasin que la création — `MagasinMissions`, via le
    registre. Aucun second stockage, aucun second cache canonique.
    """
    _missions.persister(mission)


def get_mission_by_id(mission_id: str) -> Optional[Mission]:
    """Public accessor onto this router's own in-memory ``_missions``
    dict — used by execution/task_executor.py's bootstrap wiring
    (core/bootstrap/service_registry.py's ``_workspace_project_for``) to
    resolve a task's owning Mission and, from there, its bound
    ``context.project_id`` for real filesystem tool calls. A plain
    function rather than exporting ``_missions`` itself, so this module
    stays the only place that dict is ever mutated."""
    return _missions.get(mission_id)


def _get_aegis_engine() -> Any:
    """Lazy singleton, same construction as every other ad-hoc AegisEngine
    in this codebase (agents/aegis.py, model_intelligence/routes.py,
    autonomous_guard.py's wiring) — no shared bootstrap-level Aegis service
    exists yet to reuse instead."""
    global _aegis_engine
    if _aegis_engine is None:
        from backend.core.config import get_settings, load_security_config
        from backend.security.aegis_engine import AegisEngine
        from backend.security.permission_matrix import PermissionMatrix

        settings = get_settings()
        _aegis_engine = AegisEngine(
            PermissionMatrix(load_security_config()), settings.allowed_paths_list,
        )
    return _aegis_engine


def _check_mission_security(mission: Mission) -> Optional[dict[str, Any]]:
    """Risk-based Aegis gate before a mission may start (HOS-068) — mirrors
    AutonomousOrchestrator's own gate exactly. Before this,
    ``/missions/{id}/start`` had no security check of any kind.

    Only checked when the mission is bound to a real project
    (local_path/repository) — a plain mission with no real-world footprint
    proceeds exactly as it did before this existed, for the same reason
    Autonomous doesn't gate every goal: the individual risky actions a
    task's tools take (file writes, git, network) are already separately
    gated at the point of use, so blocking every mission by default would
    be friction with no matching risk.

    Returns None to let the caller proceed, or a response dict to return
    immediately instead (mission status is already updated either way).
    """
    if not (mission.context.local_path or mission.context.repository):
        return None

    from backend.projects.store import active_validated_project_roots
    from backend.security.aegis_engine import ActionRequest, Verdict

    engine = _get_aegis_engine()
    # Same dynamic whitelist AegisAgent uses for chat/MCP/file_tools
    # (agents/aegis.py's _dynamic_allowed_paths, this repo's single real
    # source of "which projects are currently authorized") — a Mission
    # bound to a validated workspace must be granted access by the exact
    # same rule a chat session bound to it would be.
    extra_paths = active_validated_project_roots()

    if mission.context.local_path:
        path_decision = engine.evaluate(ActionRequest(
            action_type="file_read",
            description=f"mission {mission.mission_id} local_path",
            target_path=mission.context.local_path,
        ), extra_allowed_paths=extra_paths)
        if path_decision.verdict != Verdict.ALLOW:
            mission.status = MissionStatus.FAILED
            return {
                "mission_id": mission.mission_id,
                "status": mission.status.value,
                "error": f"local_path denied by Aegis: {path_decision.reason}",
            }

    decision = engine.evaluate(ActionRequest(
        action_type="mission_execute",
        description=f"start mission {mission.mission_id}",
        target_path=mission.context.local_path or None,
    ), extra_allowed_paths=extra_paths)
    if decision.verdict == Verdict.DENY:
        mission.status = MissionStatus.FAILED
        return {
            "mission_id": mission.mission_id,
            "status": mission.status.value,
            "error": f"blocked by Aegis: {decision.reason}",
        }
    if decision.verdict == Verdict.REQUIRE_HUMAN_VALIDATION:
        # A real human-in-the-loop signal, not a fabricated pause. Resuming
        # doesn't re-check Aegis — a deliberate choice mirroring Autonomous:
        # once a human has acted (via /resume), that act *is* the approval.
        mission.status = MissionStatus.PAUSED
        return {
            "mission_id": mission.mission_id,
            "status": mission.status.value,
            "reason": decision.reason,
        }
    return None


def _record_episode(mission: Mission) -> None:
    """Best-effort write-back once a mission reaches a terminal status.

    Mirrors AutonomousMemoryLoop.process_report()'s episodic write: never
    raises past this point, since a learning write must not fail (or
    retroactively un-complete) a mission that already finished."""
    if _memory_manager is None:
        return

    from backend.memory.memory_models import EpisodicMemory

    duration = 0.0
    if mission.started_at is not None and mission.completed_at is not None:
        duration = (mission.completed_at - mission.started_at).total_seconds()

    agents_used = sorted({n.preferred_agent for n in mission.nodes if n.preferred_agent})
    runtimes_used = sorted({n.preferred_runtime for n in mission.nodes if n.preferred_runtime})

    try:
        _memory_manager.record_episode(EpisodicMemory(
            mission_id=mission.mission_id,
            mission_title=mission.title,
            mission_type=mission.type.value,
            success=mission.status == MissionStatus.COMPLETED,
            total_nodes=mission.total_nodes(),
            completed_nodes=mission.completed_nodes(),
            failed_nodes=mission.failed_nodes(),
            duration_seconds=duration,
            agents_used=agents_used,
            runtimes_used=runtimes_used,
            tags=list(mission.context.tags),
        ))
    except Exception:
        logger.warning(
            "episodic write-back failed for mission %s", mission.mission_id,
            exc_info=True,
        )

    # HOS-068: beyond episodic memory, mirroring what AutonomousMemoryLoop
    # already does for autonomous goals — a mission run through this
    # router never fed either of these before.
    if mission.status == MissionStatus.COMPLETED:
        _record_procedure(mission)
    _feed_evolution_engine(mission)


def _record_procedure(mission: Mission) -> None:
    """Store the real sequence of completed task titles as a procedure —
    only called for a genuinely COMPLETED mission, so "derived_from" is
    honest: a strategy that worked, not one that was merely attempted."""
    if _memory_manager is None:
        return

    from backend.memory.memory_models import ProceduralMemory

    ordered = sorted(mission.nodes, key=lambda n: n.completed_at or mission.created_at)
    try:
        _memory_manager.store_procedure(ProceduralMemory(
            name=mission.title or mission.mission_id,
            description=mission.objective or mission.description,
            category="workflow",
            steps=[n.title for n in ordered if n.title],
            derived_from_missions=[mission.mission_id],
            success_rate=1.0,
            usage_count=1,
            tags=list(mission.context.tags) + [mission.type.value],
        ))
    except Exception:
        logger.warning(
            "procedural write-back failed for mission %s", mission.mission_id,
            exc_info=True,
        )


def _feed_evolution_engine(mission: Mission) -> None:
    """Real, measured metrics only — success/duration as they actually
    happened, the same signal AutonomousMemoryLoop already sends for
    goals."""
    if _evolution_engine is None:
        return

    from backend.evolution.evolution_models import SystemMetrics

    duration_s = 0.0
    if mission.started_at is not None and mission.completed_at is not None:
        duration_s = (mission.completed_at - mission.started_at).total_seconds()

    try:
        _evolution_engine.ingest_metrics(SystemMetrics(
            agent_success_rate=1.0 if mission.status == MissionStatus.COMPLETED else 0.5,
            agent_avg_duration_ms=duration_s * 1000.0,
            mission_avg_duration_s=duration_s,
        ))
    except Exception:
        logger.warning(
            "evolution engine feed failed for mission %s", mission.mission_id,
            exc_info=True,
        )


def _plan_nodes(mission: Mission, payload: dict) -> tuple[list[MissionNode], list[MissionEdge]]:
    """Decompose the mission's description into a DAG via the Mission Planner.

    Only used when the caller supplied no explicit graph. Returns empty lists if
    no planner is wired or planning yields nothing, so the caller can report the
    situation instead of pretending a graph exists.
    """
    if _planner is None:
        logger.warning("no mission planner wired; mission %s has no graph",
                       mission.mission_id)
        return [], []

    from backend.mission.planner.planner_models import PlanningRequest

    request = PlanningRequest(
        user_request=mission.description or mission.title,
        objective=mission.objective or mission.title,
        context=payload.get("context", {}) or {},
        repository=payload.get("repository", "") or "",
        branch=payload.get("branch", "") or "",
        specification=payload.get("specification", "") or "",
        preferred_runtime=payload.get("preferred_runtime", "") or "",
        tags=list(payload.get("tags", []) or []),
    )

    try:
        result = _planner.plan(request)
        planned = _planner.build_mission(
            result, title=mission.title, objective=mission.objective)
    except Exception:
        logger.warning("planning failed for mission %s",
                       mission.mission_id, exc_info=True)
        return [], []

    return list(planned.nodes), list(planned.edges)


@router.post("")
async def create_mission(payload: dict = Body(...)):
    """Create a mission, decomposing its description into a DAG when needed."""
    mission = Mission(
        title=payload.get("title", ""),
        description=payload.get("description", ""),
        objective=payload.get("objective", ""),
        type=MissionType(payload.get("type", "custom")),
        priority=MissionPriority(payload.get("priority", "normal")),
    )
    # Project binding (HOS-068) — read here (not only threaded into
    # PlanningRequest via _plan_nodes) so it's still known after planning,
    # for _check_mission_security() and the report/detail views.
    mission.context.local_path = payload.get("local_path", "") or ""
    mission.context.repository = payload.get("repository", "") or ""
    mission.context.branch = payload.get("branch", "") or ""
    # Workspace/Filesystem tool layer — project_id, when given, names a
    # real Project (backend/projects/). Once ACTIVE + validated, its
    # root_path is what execution/task_executor.py's RealTaskExecutor
    # resolves relative paths against for real filesystem tool calls
    # during this mission's task execution (see
    # _workspace_project_for in core/bootstrap/service_registry.py).
    # Independent of local_path/repository above — those are the older,
    # unstructured HOS-068 binding this doesn't replace.
    mission.context.project_id = payload.get("project_id", "") or ""

    nodes_data = payload.get("nodes", [])
    nodes = [
        MissionNode(
            title=n.get("title", ""),
            description=n.get("description", ""),
            type=n.get("type", "task"),
            depends_on=n.get("depends_on", []),
            preferred_runtime=n.get("preferred_runtime", ""),
            required_skills=n.get("required_skills", []),
        )
        for n in nodes_data
    ]

    edges_data = payload.get("edges", [])
    edges = [
        MissionEdge(source_id=e["source_id"], target_id=e["target_id"])
        for e in edges_data
    ]

    # An explicit graph wins; otherwise the planner decomposes the goal. This is
    # the step that used to be missing entirely.
    planned = False
    if not nodes:
        nodes, edges = _plan_nodes(mission, payload)
        planned = bool(nodes)

    issues: list[str] = []
    if _executor:
        issues = _executor.build_graph(mission, nodes, edges) or []

    _missions[mission.mission_id] = mission

    return {
        "mission_id": mission.mission_id,
        "title": mission.title,
        "status": mission.status.value,
        "nodes": mission.total_nodes(),
        "edges": len(mission.edges),
        "planned": planned,
        "validation_issues": issues,
    }


@router.get("")
async def list_missions():
    return {
        "missions": [
            {
                "mission_id": m.mission_id,
                "title": m.title,
                "status": m.status.value,
                "progress": m.progress_pct(),
                "nodes": m.total_nodes(),
                # True when the real decomposition failed and this mission
                # ran a generic, request-independent task template instead
                # — surfaced in the list too, not just the report, so it's
                # visible before opening a mission that turns out to be noise.
                "plan_is_generic": m.metadata.get("decomposition_method") == "generic_fallback",
            }
            for m in _missions.values()
        ],
        "total": len(_missions),
    }


@router.get("/{mission_id}")
async def get_mission(mission_id: str):
    mission = _missions.get(mission_id)
    if mission is None:
        return {"error": "Mission not found"}

    progress = _executor.get_progress(mission) if _executor else {}
    return {
        "mission_id": mission.mission_id,
        "title": mission.title,
        "description": mission.description,
        "objective": mission.objective,
        "type": mission.type.value,
        "priority": mission.priority.value,
        "status": mission.status.value,
        "progress": progress,
        "nodes": mission.total_nodes(),
        "edges": len(mission.edges),
        "local_path": mission.context.local_path,
        "repository": mission.context.repository,
        "branch": mission.context.branch,
        "project_id": mission.context.project_id,
        "created_at": mission.created_at.isoformat(),
        "decomposition_method": mission.metadata.get("decomposition_method", "llm"),
        "plan_is_generic": mission.metadata.get("decomposition_method") == "generic_fallback",
    }


@router.get("/{mission_id}/graph")
async def get_graph(mission_id: str):
    mission = _missions.get(mission_id)
    if mission is None or _executor is None:
        return {"error": "Mission or executor not found"}

    return _executor.get_graph_data(mission)


async def _run_mission_steps(mission: Mission) -> int:
    """Drive execute_step() until terminal, paused, or no more ready nodes.

    Yields to the event loop between passes (HOS-068, ``await
    asyncio.sleep(0)``) so a concurrent ``/pause`` request can actually be
    processed mid-run. Before this, the whole walk ran inside one ``async
    def`` handler with no ``await`` point in the loop body — FastAPI's
    single event loop could not service *any* other request, including
    ``/pause``, until the mission finished or got stuck, which made
    ``/pause`` structurally unable to interrupt anything.
    """
    terminal = (MissionStatus.COMPLETED, MissionStatus.FAILED,
                MissionStatus.CANCELLED)
    executed = 0
    passes = 0
    while (mission.status not in terminal
           and mission.status != MissionStatus.PAUSED
           and passes < MAX_EXECUTION_PASSES):
        stepped = _executor.execute_step(mission)
        passes += 1
        if stepped == 0:
            # No node was ready: either the graph is finished or it is blocked.
            break
        executed += stepped
        await asyncio.sleep(0)

    if passes >= MAX_EXECUTION_PASSES:
        logger.warning("mission %s hit the %d-pass ceiling", mission.mission_id,
                       MAX_EXECUTION_PASSES)

    if mission.status in terminal:
        _record_episode(mission)
        # HOS-100: the mission finished, but if the filesystem contradicted
        # its own success report GraphExecutor left a brief behind. Run it
        # once more with that evidence rather than only labelling the
        # failure — this is the half of the loop HOS-099 stopped short of.
        executed += await _run_retry_if_suggested(mission)

    return executed


async def _run_retry_if_suggested(mission: Mission) -> int:
    """Re-run a mission whose result the workspace contradicted.

    Driven from here rather than from GraphExecutor because this is the
    function that owns the execution walk: a re-run needs the same pass
    ceiling, the same yielding to the event loop so ``/pause`` still works,
    and the same episode recording. Hiding it inside a completion handler
    would give it none of those.

    The brief reaches the agent through ``mission.objective``, which
    service_registry's ``_mission_brief_for`` already forwards to Hermes
    Agent — no new plumbing, and it means every node of the retry sees the
    evidence, not just the first.
    """
    # La préparation vit dans retry_policy (HOS-118) : l'orchestrateur
    # autonome a la même à faire, et deux copies auraient divergé. Ce qui
    # reste ici est la marche — celle-ci cède la main à la boucle
    # d'événements pour que `/pause` réponde encore, ce dont l'autre
    # appelant n'a pas besoin.
    from backend.mission.retry_policy import preparer_reprise

    if not preparer_reprise(mission, executor=_executor):
        return 0
    return await _run_mission_steps(mission)


@router.post("/{mission_id}/start")
async def start_mission(mission_id: str):
    """Start the mission and walk its DAG through the shared execution engine.

    ``start_mission()`` only marks the mission running and announces the root
    nodes; the work happens in ``execute_step()``, which no caller ever invoked.
    """
    mission = _missions.get(mission_id)
    if mission is None or _executor is None:
        return {"error": "Mission or executor not found"}

    security_response = _check_mission_security(mission)
    if security_response is not None:
        return security_response

    ok = _executor.start_mission(mission)
    if not ok:
        return {"error": f"Cannot start mission in status {mission.status.value}"}

    executed = await _run_mission_steps(mission)

    return {
        "mission_id": mission_id,
        "status": mission.status.value,
        "nodes_executed": executed,
        "progress": _executor.get_progress(mission),
    }


@router.post("/{mission_id}/pause")
async def pause_mission(mission_id: str):
    """Pause a running mission (HOS-068).

    Genuinely interruptible, not cosmetic: a concurrent ``/start`` call's
    stepping loop checks ``mission.status`` between every pass (see
    ``_run_mission_steps``), so setting it here actually stops the walk
    before its next step — not merely a status label a background process
    ignores.
    """
    mission = _missions.get(mission_id)
    if mission is None:
        return {"error": "Mission not found"}
    if mission.status != MissionStatus.RUNNING:
        return {"error": f"Cannot pause mission in status {mission.status.value}"}
    mission.status = MissionStatus.PAUSED
    return {"mission_id": mission_id, "status": mission.status.value}


@router.post("/{mission_id}/resume")
async def resume_mission(mission_id: str):
    """Resume a paused mission — actually continues the DAG walk (unlike
    Autonomous's current pause/resume, which only flips the status flag;
    see AutonomousOrchestrator.resume_goal()'s own note on that gap) since
    the mission's DAG state (which nodes are done/ready) lives on the
    Mission/MissionNode objects themselves, not in a stack frame that was
    already unwound."""
    mission = _missions.get(mission_id)
    if mission is None or _executor is None:
        return {"error": "Mission or executor not found"}
    if mission.status != MissionStatus.PAUSED:
        return {"error": f"Cannot resume mission in status {mission.status.value}"}
    mission.status = MissionStatus.RUNNING
    if mission.started_at is None:
        # A mission the Aegis gate paused (_check_mission_security) never
        # reached _executor.start_mission() — the only other place that
        # sets this — so without it build_mission_report() reports
        # total_duration_ms: 0.0 even after a resumed mission genuinely ran.
        from datetime import datetime, timezone

        mission.started_at = datetime.now(timezone.utc)

    executed = await _run_mission_steps(mission)

    return {
        "mission_id": mission_id,
        "status": mission.status.value,
        "nodes_executed": executed,
        "progress": _executor.get_progress(mission),
    }


@router.get("/{mission_id}/report")
async def get_report(mission_id: str):
    """Final mission report (HOS-068) — derived from the mission's own
    real, already-measured state; see build_mission_report()."""
    mission = _missions.get(mission_id)
    if mission is None:
        return {"error": "Mission not found"}
    return build_mission_report(mission).to_dict()


@router.post("/{mission_id}/cancel")
async def cancel_mission(mission_id: str):
    mission = _missions.get(mission_id)
    if mission is None or _executor is None:
        return {"error": "Mission or executor not found"}

    _executor.cancel_mission(mission)
    if mission.status == MissionStatus.CANCELLED:
        _record_episode(mission)
    return {"mission_id": mission_id, "status": mission.status.value}


@router.get("/{mission_id}/progress")
async def get_progress(mission_id: str):
    mission = _missions.get(mission_id)
    if mission is None or _executor is None:
        return {"error": "Mission or executor not found"}

    return _executor.get_progress(mission)
