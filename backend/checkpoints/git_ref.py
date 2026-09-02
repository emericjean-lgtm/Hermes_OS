"""Un point de reprise comme référence git, sans toucher au dépôt (HOS-223).

## L'idée reprise d'Agent OS

Un checkpoint est un **commit détaché** rangé sous
`refs/hermes/checkpoints/<id>`. Git sait déjà tout ce qu'il faut : le
stockage par contenu déduplique, l'objet est immuable, la référence le
protège du ramasse-miettes, et `.gitignore` est honoré gratuitement — un
`node_modules/` de 400 Mio n'entre pas dans le point de reprise sans
qu'on ait à écrire une seule règle.

## Ce qui rend la chose non triviale

**Le dépôt de l'utilisateur ne doit rien sentir.** Ni son index, ni sa
branche courante, ni son `HEAD`, ni son stash. Un point de reprise qui
mettrait en scène `git add -A` sur l'index réel détruirait le travail en
cours de quelqu'un — et le ferait au moment précis où il s'apprêtait à
lancer une mission risquée.

D'où `GIT_INDEX_FILE` sur un fichier temporaire : `git add -A` y écrit,
`git write-tree` en fabrique un arbre, et l'index réel n'est jamais
ouvert. C'est la pièce d'Agent OS qui vaut d'être reprise telle quelle.

## Ce qui change par rapport à eux

Le commit prend `HEAD` pour **parent** quand il existe. Détaché sans
parent, un checkpoint n'est diffable contre rien : `git log` ne le
raconte pas, et `git diff HEAD refs/hermes/checkpoints/<id>` demande de
connaître les deux bouts. Avec un parent, on lit d'où il vient.

## Et la restauration

Restaurer, c'est effacer. `git checkout-index` réécrit ce qui était dans
le point de reprise, mais **ne supprime pas** ce qui est apparu depuis :
une restauration qui laisserait les fichiers créés après ne restaurerait
rien du tout, elle mélangerait deux états. On calcule donc la différence
entre l'arbre du point de reprise et un arbre de l'état courant, et on
traite les trois cas séparément.

Ce module **prépare et applique** ; il ne décide pas. La décision — la
restauration passe-t-elle par Aegis, faut-il un aperçu — appartient à
`checkpoint.py`, qui est le seul à savoir ce qu'on est en train de
reprendre.
"""

from __future__ import annotations

import logging
import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger("hermes_os.checkpoints.git")

#: Le même délai que `git_tools`. Une commande git qui n'a pas répondu en
#: deux minutes sur un dépôt local est bloquée, pas lente.
DELAI_S = 120

#: L'espace de noms. Sous `refs/` mais hors de `refs/heads` et
#: `refs/tags` : ces références n'apparaissent donc ni dans `git branch`,
#: ni dans `git tag`, ni dans un `git push` par défaut. Le dépôt de
#: l'utilisateur reste tel qu'il le connaît.
PREFIXE = "refs/hermes/checkpoints/"


class GitIndisponible(RuntimeError):
    """Ni git, ni un dépôt git. L'appelant se rabat sur autre chose."""


class GitEchoue(RuntimeError):
    """Une commande git a refusé. Jamais avalé : voir le module."""


def _git(depot: str, args: list[str], *, index: str | None = None) -> str:
    """Lancer un argv git fixe, éventuellement sur un index de côté.

    Même discipline que `backend/tools/git_tools._run` — argv littéral,
    `shell=False` explicite, délai borné. Fonction distincte plutôt qu'un
    paramètre ajouté là-bas : `GIT_INDEX_FILE` est exactement ce qu'on ne
    veut jamais voir traîner dans les outils que l'agent appelle.
    """
    env = dict(os.environ)
    if index is not None:
        env["GIT_INDEX_FILE"] = index
    # Un dépôt dont la configuration désactiverait les hooks ou en
    # ajouterait n'a pas à s'exécuter ici : on ne fait que lire et
    # fabriquer des objets.
    env["GIT_OPTIONAL_LOCKS"] = "0"
    try:
        fini = subprocess.run(  # noqa: S603 - argv fixe, shell=False
            ["git", *args], cwd=depot, capture_output=True, text=True,
            shell=False, timeout=DELAI_S, encoding="utf-8", errors="replace",
            env=env,
        )
    except FileNotFoundError as exc:
        raise GitIndisponible("git n'est pas sur le PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise GitEchoue(f"git {' '.join(args)} bloqué après {DELAI_S} s") from exc
    if fini.returncode != 0:
        raise GitEchoue(
            f"git {' '.join(args)} a échoué ({fini.returncode}) : "
            f"{fini.stderr.strip()}")
    return fini.stdout


def est_un_depot(racine: str) -> bool:
    """Y a-t-il un dépôt git ici ?

    Demandé à git plutôt que testé sur `.git` : un worktree lié porte un
    **fichier** `.git`, et un sous-dossier de dépôt n'en porte aucun tout
    en étant parfaitement versionné.
    """
    try:
        sortie = _git(racine, ["rev-parse", "--is-inside-work-tree"])
    except (GitIndisponible, GitEchoue, OSError):
        return False
    return sortie.strip() == "true"


def _tete(depot: str) -> str | None:
    """Le commit courant, ou None dans un dépôt sans le moindre commit."""
    try:
        return _git(depot, ["rev-parse", "HEAD"]).strip()
    except GitEchoue:
        return None


def _arbre_de_l_etat(depot: str) -> str:
    """Fabriquer un arbre de l'état actuel du disque, index intact.

    Tout passe par un `GIT_INDEX_FILE` temporaire. C'est la pièce
    centrale : sans elle, `git add -A` écraserait l'index de
    l'utilisateur — c'est-à-dire son travail en cours, au moment précis
    où il lance une mission risquée.
    """
    with tempfile.TemporaryDirectory(prefix="hermes_index_") as dossier:
        index = str(Path(dossier) / "index")
        # `-A` prend créations, modifications et suppressions ; les
        # fichiers ignorés restent dehors, ce qui est le comportement
        # voulu et gratuit.
        _git(depot, ["add", "-A", "--", "."], index=index)
        return _git(depot, ["write-tree"], index=index).strip()


def prendre(depot: str, message: str) -> str:
    """Fabriquer le point de reprise et le protéger du ramasse-miettes.

    Rend l'identifiant de commit. La référence est ce qui empêche
    `git gc` de le collecter : un objet non référencé disparaît, et un
    point de reprise disparu est pire qu'absent — on croyait l'avoir.
    """
    arbre = _arbre_de_l_etat(depot)
    parent = _tete(depot)
    args = ["commit-tree", arbre, "-m", message]
    if parent:
        args += ["-p", parent]
    commit = _git(depot, args).strip()
    _git(depot, ["update-ref", PREFIXE + commit[:12], commit])
    return commit


def supprimer(depot: str, commit: str) -> None:
    """Retirer la référence. L'objet redevient collectable."""
    try:
        _git(depot, ["update-ref", "-d", PREFIXE + commit[:12]])
    except GitEchoue:
        logger.debug("référence de checkpoint %s déjà absente", commit[:12])


def existe(depot: str, commit: str) -> bool:
    try:
        _git(depot, ["cat-file", "-e", commit + "^{commit}"])
        return True
    except (GitEchoue, GitIndisponible):
        return False


@dataclass(frozen=True)
class Ecart:
    """Ce qu'une restauration ferait, avant de le faire.

    Trois listes plutôt qu'une : elles n'appellent pas les mêmes gestes,
    et surtout la troisième **efface**. Les fondre dans un compteur
    « 12 fichiers touchés » cacherait la seule qui soit destructive.
    """

    #: Présents au point de reprise, modifiés depuis. Réécrits.
    a_restaurer: tuple[str, ...] = ()
    #: Présents au point de reprise, disparus depuis. Recréés.
    a_recreer: tuple[str, ...] = ()
    #: Absents du point de reprise, apparus depuis. **Supprimés.**
    a_supprimer: tuple[str, ...] = ()

    @property
    def vide(self) -> bool:
        return not (self.a_restaurer or self.a_recreer or self.a_supprimer)

    def resume(self) -> str:
        if self.vide:
            return "le workspace est déjà dans l'état du point de reprise"
        return (f"{len(self.a_restaurer)} à réécrire, "
                f"{len(self.a_recreer)} à recréer, "
                f"{len(self.a_supprimer)} à supprimer")


def ecart(depot: str, commit: str) -> Ecart:
    """Ce qui sépare le disque du point de reprise.

    Calculé entre deux **arbres**, pas entre un arbre et l'index : le
    second demanderait de lire l'index de l'utilisateur, qu'on s'interdit
    de toucher — et il ne verrait pas les fichiers non suivis.
    """
    courant = _arbre_de_l_etat(depot)
    sortie = _git(depot, ["diff-tree", "-r", "--name-status", "--no-renames",
                          "-z", commit + "^{tree}", courant])
    # `-z` : les chemins avec un espace ou un accent ne se découpent pas
    # correctement autrement, et un chemin mal découpé serait un fichier
    # qu'on n'aurait pas restauré, sans que rien le dise.
    morceaux = [m for m in sortie.split("\0") if m]
    reecrire: list[str] = []
    recreer: list[str] = []
    supprimer_: list[str] = []
    for etat, chemin in zip(morceaux[::2], morceaux[1::2]):
        # Le sens est celui du point de reprise **vers** le courant :
        # « A » veut dire apparu depuis, donc à supprimer pour revenir.
        if etat.startswith("A"):
            supprimer_.append(chemin)
        elif etat.startswith("D"):
            recreer.append(chemin)
        else:
            reecrire.append(chemin)
    return Ecart(tuple(sorted(reecrire)), tuple(sorted(recreer)),
                 tuple(sorted(supprimer_)))


def restaurer(depot: str, commit: str) -> Ecart:
    """Remettre le workspace dans l'état du point de reprise.

    Ne touche ni `HEAD`, ni la branche courante, ni l'index de
    l'utilisateur : seuls les fichiers du répertoire de travail changent.
    Le dépôt reste sur la branche où il était, avec l'historique qu'il
    avait — ce qui compte, parce qu'une restauration arrive après un
    incident, et qu'un incident n'est pas le moment de découvrir que sa
    branche a bougé.
    """
    fait = ecart(depot, commit)
    with tempfile.TemporaryDirectory(prefix="hermes_index_") as dossier:
        index = str(Path(dossier) / "index")
        _git(depot, ["read-tree", commit + "^{tree}"], index=index)
        if fait.a_restaurer or fait.a_recreer:
            _git(depot, ["checkout-index", "-f", "-a"], index=index)

    racine = Path(depot)
    for chemin in fait.a_supprimer:
        cible = racine / chemin
        try:
            cible.unlink()
        except OSError:
            logger.warning("suppression impossible pendant la restauration : %s",
                           cible, exc_info=True)
    return fait


__all__ = ["DELAI_S", "Ecart", "GitEchoue", "GitIndisponible", "PREFIXE",
           "ecart", "est_un_depot", "existe", "prendre", "restaurer",
           "supprimer"]
