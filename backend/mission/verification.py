"""Did the mission actually change anything? (HOS-092)

Every defect found while making Hermes Agent the mission brain produced a
*successful* mission: the tool loop bypass, the emptied CLI toolsets, the
objective lost in decomposition, the 4k served context, the 180s timeout.
Five distinct causes, five green reports, and in each case an empty
workspace. The common failure was not any of the five — it was that
"completed" meant "every node returned some text", and text is exactly what
a language model produces when it cannot do the work.

This module answers a different question, and answers it without asking the
agent: compare the workspace before and after. A filesystem diff is ground
truth. It needs no cooperation from the model, cannot be talked out of its
answer, and would have caught all five.

Deliberately *not* a pass/fail judge of the objective. Deciding whether
"alpha/beta/gamma" is the right content for a given goal is a semantic
question this layer has no business answering, and pretending otherwise
would just move the fabrication one level up. It reports what physically
changed; whether that satisfies the objective stays with the operator and
the mission's own validation.
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("hermes_os.mission.verification")

#: Files bigger than this are compared by size and mtime rather than hash.
#: Hashing a multi-gigabyte artifact to answer "did anything change" would
#: cost more than the answer is worth.
_HASH_LIMIT_BYTES = 8 * 1024 * 1024

#: Directories whose churn says nothing about whether the mission did its
#: work. Without this, any mission in a git repo or a Python project looks
#: productive because a cache directory moved.
#:
#: `.hermes` en fait partie depuis HOS-123 : c'est là que vit le journal de
#: projet, et il est écrit *après* la mission qu'il décrit. Sans cette
#: ligne, une mission qui n'aurait rien fait d'autre qu'écrire sa propre
#: trace verrait `touched_anything` à vrai au passage suivant et passerait
#: pour productive. Le journal mesure le travail ; il ne doit jamais
#: compter comme du travail.
_IGNORED_DIRS = frozenset({
    ".git", "__pycache__", ".venv", "venv", "node_modules", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", ".next", "dist", "build", ".idea", ".vscode",
    ".hermes",
})


@dataclass(frozen=True)
class WorkspaceSnapshot:
    """What the workspace looked like at one instant."""

    root: str
    entries: dict[str, str] = field(default_factory=dict)

    @property
    def file_count(self) -> int:
        return len(self.entries)


@dataclass(frozen=True)
class WorkspaceDiff:
    """What physically changed between two snapshots."""

    created: tuple[str, ...] = ()
    modified: tuple[str, ...] = ()
    deleted: tuple[str, ...] = ()

    @property
    def touched_anything(self) -> bool:
        return bool(self.created or self.modified or self.deleted)

    def summary(self) -> str:
        if not self.touched_anything:
            return "no file was created, modified or deleted"
        parts = []
        for label, items in (("created", self.created), ("modified", self.modified),
                             ("deleted", self.deleted)):
            if items:
                shown = ", ".join(sorted(items)[:5])
                more = f" (+{len(items) - 5} more)" if len(items) > 5 else ""
                parts.append(f"{len(items)} {label}: {shown}{more}")
        return "; ".join(parts)


def _fingerprint(path: Path) -> str:
    """Cheap, collision-resistant enough to answer "did this change".

    Size and mtime alone miss a same-length rewrite within the filesystem's
    timestamp granularity — precisely the "agent rewrote the file with
    different content" case this exists to catch — so small files are
    hashed.
    """
    try:
        stat = path.stat()
    except OSError:
        return "unreadable"
    if stat.st_size > _HASH_LIMIT_BYTES:
        return f"size:{stat.st_size}:mtime:{int(stat.st_mtime)}"
    try:
        return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return f"size:{stat.st_size}:mtime:{int(stat.st_mtime)}"


def snapshot(root: str) -> WorkspaceSnapshot:
    """Fingerprint every file under ``root``.

    Never raises: this runs around a mission, and a snapshot that fails must
    not be able to fail the mission itself. An unreadable tree yields an
    empty snapshot, which shows up as "nothing changed" rather than as a
    crash — visible, and honest about having learned nothing.
    """
    base = Path(root)
    entries: dict[str, str] = {}
    try:
        if not base.is_dir():
            return WorkspaceSnapshot(root=root)
        for path in base.rglob("*"):
            if any(part in _IGNORED_DIRS for part in path.parts):
                continue
            if not path.is_file():
                continue
            try:
                relative = str(path.relative_to(base))
            except ValueError:  # pragma: no cover - symlink escaping the root
                continue
            entries[relative] = _fingerprint(path)
    except OSError:
        logger.debug("snapshot of %r failed", root, exc_info=True)
    return WorkspaceSnapshot(root=root, entries=entries)


def diff(before: WorkspaceSnapshot, after: WorkspaceSnapshot) -> WorkspaceDiff:
    """What changed between two snapshots of the same workspace."""
    before_keys, after_keys = set(before.entries), set(after.entries)
    return WorkspaceDiff(
        created=tuple(sorted(after_keys - before_keys)),
        deleted=tuple(sorted(before_keys - after_keys)),
        modified=tuple(sorted(
            k for k in before_keys & after_keys
            if before.entries[k] != after.entries[k]
        )),
    )


@dataclass(frozen=True)
class MissionVerification:
    """Whether a mission's claimed success is backed by a real change."""

    mission_id: str
    reported_success: bool
    workspace: Optional[str]
    changes: WorkspaceDiff
    #: False when there was nothing to compare — no bound workspace, or a
    #: snapshot that could not be taken. Absence of measurement is not
    #: evidence of absence of work, and conflating the two would flag every
    #: workspace-less mission as a false success.
    measured: bool = True
    #: Ce que les propres tests du workspace disent de ce qui a été produit
    #: (HOS-119). `None` = aucun runner applicable, ou il n'a pas tourné —
    #: **jamais** « les tests passent ».
    #:
    #: `changes` répond à « le workspace a-t-il changé ? ». Mesuré : oui,
    #: six fichiers — et les tests écrits par la mission ne passaient pas,
    #: parce qu'elle avait nommé le module `calculatrice.py` en important
    #: `calculator`. Le rapport annonçait 6/6 réussi. Un artefact qui ne
    #: tient pas debout contre lui-même n'est pas un livrable.
    tests: Optional[dict] = None
    #: Ce que la mission avait **annoncé** écrire, confronté au disque
    #: (HOS-122). `None` = aucune tâche n'a déclaré de livrable — jamais
    #: « tout est là ».
    #:
    #: `changes` répond à « le workspace a-t-il changé ? », `tests` à « ce
    #: qui est là tient-il debout ? ». Celui-ci répond à la troisième
    #: question, que ni l'un ni l'autre ne pose : « est-ce que c'est ce
    #: qu'on avait dit ? ». Mesuré sur Skills360 : sept tâches, 7/7, et
    #: deux fichiers de tests au même nom de base dont l'un testait une API
    #: qui n'existait pas.
    manifeste: Optional[dict] = None
    #: Les boucles d'import entre les modules du livrable (HOS-124).
    #: `None` = rien à analyser. Une boucle *démontrée fatale* contredit un
    #: succès annoncé ; une boucle non démontrée est signalée sans l'être.
    #:
    #: Mesuré : `organization.py` et `workshop.py` s'importaient
    #: mutuellement — `ImportError: cannot import name 'Organization' from
    #: partially initialized module`. La porte de syntaxe ne voyait rien,
    #: les deux fichiers compilent parfaitement.
    imports: Optional[dict] = None

    @property
    def imports_boucles(self) -> bool:
        """Une boucle d'import démontrée fatale."""
        from backend.mission import imports_locaux

        return imports_locaux.contredit(self.imports)

    @property
    def manifeste_manque(self) -> bool:
        """Un livrable a été annoncé et n'est pas sur le disque.

        Comme `tests_echouent`, trois états qui ne se confondent pas :
        aucun manifeste, manifeste tenu, manifeste troué. Seul le dernier
        contredit un succès annoncé.
        """
        from backend.mission import manifeste as _manifeste

        return _manifeste.contredit(self.manifeste)

    @property
    def tests_echouent(self) -> bool:
        """Les tests ont réellement tourné et ont réellement échoué.

        Les trois états ne se confondent pas : pas de runner applicable,
        runner refusé ou non exécuté, et échec constaté. Seul le troisième
        contredit un succès annoncé — traiter les deux premiers comme un
        échec fabriquerait des faux négatifs, ce qui coûte aussi cher que
        l'inverse.
        """
        tests = self.tests or {}
        return bool(tests.get("ran")) and tests.get("passed") is False

    @property
    def verified(self) -> bool:
        """A successful mission that touched nothing is not verified.

        The inverse is not asserted: a mission that failed while still
        writing files is reported as it happened, not retroactively passed.

        Des tests qui échouent retirent la vérification (HOS-119) : écrire
        des fichiers est nécessaire, ça n'a jamais suffi.
        """
        return (self.measured and self.reported_success
                and self.changes.touched_anything and not self.tests_echouent
                and not self.manifeste_manque and not self.imports_boucles)

    @property
    def contradicted(self) -> bool:
        """Reported success, changed nothing — the exact false positive that
        hid five separate defects. Only ever claimed when we actually
        looked.

        Contredit aussi quand le workspace a bien changé mais que ses tests
        échouent : le rapport affirme alors une réussite que le projet
        lui-même dément. C'est la même famille de mensonge, constatée par
        un autre instrument — et elle déclenche donc la même reprise.

        Et quand un livrable annoncé manque (HOS-122) : une mission qui a
        écrit six fichiers dont aucun n'est celui qu'elle avait promis n'a
        pas fait le travail, quoi qu'en dise le compteur de tâches.
        """
        if not (self.measured and self.reported_success):
            return False
        return (not self.changes.touched_anything or self.tests_echouent
                or self.manifeste_manque or self.imports_boucles)

    def as_dict(self) -> dict:
        return {
            "mission_id": self.mission_id,
            "reported_success": self.reported_success,
            "measured": self.measured,
            "verified": self.verified,
            "contradicted": self.contradicted,
            "workspace": self.workspace,
            "created": list(self.changes.created),
            "modified": list(self.changes.modified),
            "deleted": list(self.changes.deleted),
            "summary": self.changes.summary(),
            "tests": self.tests,
            "manifeste": self.manifeste,
            "imports": self.imports,
            "tests_echouent": self.tests_echouent,
        }


def _verdict_des_tests(workspace: str, reported_success: bool) -> Optional[dict]:
    """Faire tourner les propres tests du workspace, quand il en a (HOS-119).

    Trois raisons de ne rien rendre, et aucune n'est un échec :

    * la mission ne prétend pas avoir réussi — inutile de dépenser du temps
      pour confirmer un échec déjà annoncé ;
    * aucun runner ne correspond à ce qu'il y a dans le dossier — lancer
      `pytest` sur un projet JavaScript produirait un faux échec, ce qui
      coûte aussi cher qu'un faux succès ;
    * le runner n'a pas pu tourner (Aegis, dépendance absente) — on ne
      conclut pas de ce qu'on n'a pas mesuré.

    Ne lève jamais : la vérification du workspace doit rendre son verdict
    même si cette partie-ci échoue. Le contraire ferait perdre la mesure
    principale à cause de la secondaire.
    """
    if not reported_success:
        return None
    try:
        from backend.mission.runner_applicable import runner_pour

        nom = runner_pour(workspace)
        if nom is None:
            return {"ran": False, "reason": "aucun runner applicable à ce workspace"}

        from backend.core.agent_registry import get_agent_registry
        from backend.tools import verification as runners

        resultat = runners.run(get_agent_registry().get("aegis"), workspace, nom)
        return {
            "ran": resultat.ran,
            "runner": resultat.runner,
            "passed": resultat.passed,
            "exit_code": resultat.exit_code,
            "reason": resultat.reason,
            "output": (resultat.output or "")[-2000:],
        }
    except Exception as exc:  # pragma: no cover - dépend de l'environnement
        logger.debug("verdict des tests indisponible pour %r", workspace, exc_info=True)
        return {"ran": False, "reason": f"{type(exc).__name__}: {exc}"}


def verify(
    mission_id: str,
    reported_success: bool,
    workspace: Optional[str],
    before: Optional[WorkspaceSnapshot],
    after: Optional[WorkspaceSnapshot],
    mission: Any = None,
) -> MissionVerification:
    """Confront a mission's own verdict with the filesystem's.

    A mission bound to no workspace has nothing to confront, so its reported
    result stands unchallenged rather than being failed for lacking evidence
    it was never in a position to produce.
    """
    if workspace is None or before is None or after is None:
        return MissionVerification(
            mission_id=mission_id, reported_success=reported_success,
            workspace=workspace, changes=WorkspaceDiff(), measured=False,
        )
    from backend.mission import imports_locaux as _imports
    from backend.mission import manifeste as _manifeste

    result = MissionVerification(
        mission_id=mission_id, reported_success=reported_success,
        workspace=workspace, changes=diff(before, after),
        tests=_verdict_des_tests(workspace, reported_success),
        manifeste=_manifeste.verdict(mission, workspace) if mission is not None
                  else None,
        imports=_imports.verdict(workspace),
    )
    if result.contradicted:
        logger.warning(
            "mission %s reported success but %s in %r — the result is the "
            "model's account of the work, not evidence of it",
            mission_id, result.changes.summary(), workspace,
        )
    return result
