"""Pont unique Hermes OS <-> Hermes Agent : négociation des capacités réelles.

## Pourquoi un pont, et pourquoi il ne décide rien

`backend/ral/adapters/hermes_agent_cli.py` lance l'agent en **un coup** par
tâche : un sous-processus, une requête, une réponse, puis il meurt. Cela
suffit pour exécuter un nœud de mission et ne suffit pour rien d'autre —
pas de session qui dure, pas d'événement pendant le tour, pas de steer, pas
d'approbation. Le pont ouvre l'autre porte : le gateway JSON-RPC de
l'agent, qui vit, parle et accepte des ordres pendant qu'il travaille.

**Le pont n'est pas une autorité.** Hermes OS garde Mission, Run Ledger,
lignage, vérification, Aegis, workspace, provenance, `ResourceManager`,
l'admission VRAM, `AdaptiveRouter` et le RAL. Le pont rapporte ce que le
runtime sait faire et relaie ; il ne choisit aucun modèle, n'admet aucune
tâche et n'ordonnance rien. C'est la seule raison pour laquelle l'ajouter
ne viole pas la règle qui prime sur tout : *Hermes Agent est le cerveau,
Hermes OS est son système d'exploitation.*

## Négocier plutôt que supposer

Ce dépôt a déjà payé cher le fait de coder un jeu de capacités au lieu de
le mesurer : la capacité `tools` annoncée par Ollama l'est jusque par un
modèle d'embedding (HOS-095), et deux listes blanches hors dépôt décidaient
en silence de ce que l'agent voyait.

Le gateway offre un discriminant net, mesuré le 2026-09-06 :

    methode.qui.nexiste.pas  ->  error -32601 "unknown method: ..."
    session.status           ->  error  4001  "session not found"

`-32601` dit **absente**. Tout le reste — résultat *ou* erreur applicative —
dit **présente**. Une erreur métier prouve que la méthode existe et a
examiné ses arguments ; c'est une présence, pas un échec.

Mesuré ainsi sur v0.21.0 : 54 méthodes présentes, 8 absentes. Et les
absences comptent autant que les présences — `session.fork`, `memory.*` et
`subagent.start` **n'existent pas** sous ces noms, alors qu'une lecture de
la documentation les aurait tous supposés là.

## Une négociation est une mesure datée

Même leçon que G-15, et pour la même raison : le résultat dépend de la
version installée, pas du nom du produit. La négociation est donc mise en
cache **sous l'empreinte du runtime** (version + commit). Mettre l'agent à
jour change l'empreinte et invalide le cache tout seul, sans que personne
n'ait à y penser — c'est précisément ce qui manquait au magasin de sondes.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import threading
import time
from collections import deque
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("hermes_os.bridge.hermes_agent")

#: JSON-RPC : « méthode inconnue ». Le seul code qui prouve une absence.
CODE_METHODE_INCONNUE = -32601

#: Ce que le pont cherche à savoir faire, groupé par surface produit. Les
#: noms sont ceux du gateway ; c'est la négociation qui dit lesquels
#: répondent réellement, jamais cette liste.
METHODES_PAR_CAPACITE: dict[str, tuple[str, ...]] = {
    "chat": ("prompt.submit", "prompt.background"),
    "sessions": ("session.list", "session.status", "session.resume",
                 "session.history", "session.save", "session.title",
                 "session.most_recent"),
    "fork": ("session.branch",),
    "steering": ("session.steer", "session.interrupt", "session.redirect"),
    "approvals": ("approval.pending", "approval.received", "approval.respond",
                  "clarify.respond", "secret.respond", "sudo.respond"),
    "tools": ("tools.list", "tools.show", "tools.configure", "toolsets.list"),
    "skills": ("skills.manage", "skills.reload"),
    "learning": ("learning.frames", "learning.detail", "learning.edit",
                 "learning.delete"),
    "delegation": ("delegation.status", "delegation.pause",
                   "subagent.steer", "subagent.interrupt",
                   "spawn_tree.list"),
    "mcp": ("mcp.catalog", "mcp.servers.list", "mcp.servers.add",
            "mcp.servers.remove", "mcp.servers.status", "mcp.servers.test",
            "reload.mcp"),
    "cron": ("cron.manage",),
    "profiles": ("profiles.list", "profiles.describe", "profiles.create",
                 "profiles.configure"),
    "groupes": ("groups.capabilities", "groups.list", "groups.create",
                "groups.state", "groups.send", "groups.disband"),
    "projects": ("projects.list", "projects.get", "projects.create",
                 "projects.tree"),
    "browser": ("browser.manage", "browser.controller.register",
                "browser.controller.result"),
    "commands": ("commands.catalog", "command.dispatch", "slash.exec"),
    "config": ("config.show", "config.get", "config.set"),
    "insights": ("insights.get", "verification.status", "usage.bars"),
    "multimodal": ("image.attach", "image.generate", "pdf.attach",
                   "voice.record", "voice.tts"),
}

#: Surfaces dont la **capacite existe dans l'agent** mais qu'aucune methode
#: du gateway n'expose. Verifie contre le registre complet — 206 methodes
#: relevees sur v0.21.0 — et non contre un nom devine.
#:
#: La distinction compte : « absente » disait jusqu'ici deux choses tres
#: differentes, « le runtime ne sait pas le faire » et « le runtime le fait
#: sans nous laisser le demander ». La seconde n'interdit pas la capacite au
#: produit ; elle interdit seulement a Hermes OS de la piloter.
SANS_RPC: dict[str, str] = {
    "memory": (
        "aucune methode `memory.*` dans le registre. La memoire existe "
        "comme **outil interne** de l'agent (`tools/memory_tool.py`, "
        "`memory_tool_store.py`) et figure dans les toolsets actifs que "
        "`groups.capabilities` publie. L'agent s'en sert ; Hermes OS ne "
        "peut ni la lire ni l'ecrire par le pont."
    ),
    "spawn_de_subagent": (
        "aucune methode ne lance un subagent. `spawn_tree.*` lit l'arbre, "
        "`subagent.steer`/`interrupt` pilotent un enfant existant, "
        "`handoff.*` transfere. Un subagent nait de l'agent lui-meme, sur "
        "sa propre decision — ce qui est coherent avec la regle qui prime "
        "sur tout : le cerveau decide, l'OS n'ordonne pas."
    ),
}


#: Les mutations que Hermes OS sait demander, et **à qui appartient l'état
#: qu'elles écrivent**. C'est la table de G-18, et elle est courte exprès.
#:
#: Mesuré le 2026-09-09 : `state.db` (114 Mio, sous le home de l'agent) est
#: écrit par les seuls gestionnaires de l'agent. `session.resume` ne le
#: touche pas — empreinte identique avant/après, seuls `-wal` et `-shm`
#: bougent, ce qui est la comptabilité de lecture de SQLite. Ce n'est donc
#: pas une mutation : c'est une **activation runtime**, et son handle meurt
#: avec le processus (`4001 session not found` après redémarrage, mesuré).
#:
#: `session.branch`, lui, écrit : contenu de `state.db` changé, nouvelle
#: clé retrouvée par un processus neuf. C'est une vraie mutation, et elle
#: est **additive** — elle n'écrase jamais la session parente.
#:
#: Une méthode absente d'ici n'est pas demandable. Pas parce que le pont
#: arbitre — il n'arbitre rien — mais parce qu'inventer un appel que le
#: runtime ne sert pas fabriquerait une API fictive, et c'est exactement ce
#: que ce dépôt appelle un orphelin.
MUTATIONS_CONNUES: dict[str, str] = {
    "session.branch": "hermes-agent:state.db",
    # Renommer : `db.set_session_title`, donc `state.db`. Additive au sens
    # ou rien n'est perdu — l'ancien titre etait de toute facon genere par
    # l'agent, et la conversation n'est pas touchee.
    "session.title": "hermes-agent:state.db",
    # Activer/desactiver un toolset ecrit `config.yaml`, que **tous** les
    # processus agent relisent — missions comprises. Contrairement a
    # `delegation.pause`, mesure comme locale au gateway, celle-ci porte.
    #
    # Additive au sens qui compte : rien n'est perdu. Le round-trip YAML
    # ajoute des cles (il materialise des defauts implicites) et n'en
    # retire aucune — verifie par diff le 2026-09-09, liste blanche MCP
    # intacte. Desactiver reste reversible par la meme methode.
    "tools.configure": "hermes-agent:config.yaml",
}


class MutationInconnue(ValueError):
    """Demandée mais absente de `MUTATIONS_CONNUES` — donc jamais relayée."""


@dataclass(frozen=True)
class CapaciteRuntime:
    """Une surface produit, et ce que le runtime en sert réellement.

    `complete` distingue « tout est là » de « une partie manque ». La
    différence n'est pas cosmétique : `delegation` sans `subagent.start`
    permet de piloter un subagent mais pas d'en lancer un, et présenter
    cela comme « délégation disponible » serait un mensonge d'interface.
    """

    nom: str
    methodes_presentes: tuple[str, ...]
    methodes_absentes: tuple[str, ...]

    @property
    def disponible(self) -> bool:
        return bool(self.methodes_presentes)

    @property
    def complete(self) -> bool:
        return self.disponible and not self.methodes_absentes

    def as_dict(self) -> dict:
        return {**asdict(self), "disponible": self.disponible,
                "complete": self.complete}


@dataclass(frozen=True)
class NegociationRuntime:
    """Ce que ce runtime-ci sait faire, à cette version-là.

    `empreinte` est la clé de fraîcheur : version + commit du checkout.
    Elle rend la négociation invalidable par une mise à jour, au lieu de
    la laisser survivre à ce qu'elle décrivait.
    """

    empreinte: str
    version: str
    commit: str
    mesure_le: float
    capacites: tuple[CapaciteRuntime, ...] = field(default_factory=tuple)
    erreur: Optional[str] = None

    @property
    def negociee(self) -> bool:
        """Une négociation qui a échoué n'est pas une négociation vide.

        Sans cette distinction, un gateway injoignable se lirait « aucune
        capacité » — c'est-à-dire exactement comme un runtime nu, alors
        que l'un est une panne et l'autre un fait.
        """
        return self.erreur is None

    def capacite(self, nom: str) -> Optional[CapaciteRuntime]:
        return next((c for c in self.capacites if c.nom == nom), None)

    def as_dict(self) -> dict:
        return {
            "empreinte": self.empreinte, "version": self.version,
            "commit": self.commit, "mesure_le": self.mesure_le,
            "negociee": self.negociee, "erreur": self.erreur,
            "capacites": [c.as_dict() for c in self.capacites],
            # Corriger la matrice ne doit pas faire **disparaitre** une
            # absence honnete : `memory` s'affichait « absente » et
            # aurait cesse d'exister a l'ecran une fois son faux nom
            # retire. Elle est donc portee ici, avec ce qui a ete cherche.
            "sans_rpc": [{"nom": n, "raison": r}
                         for n, r in sorted(SANS_RPC.items())],
        }


def _magasin() -> Path:
    """Où vit la dernière négociation.

    Sous `db/`, comme le magasin de sondes et pour la même raison :
    `preserve_set()` énumère des **dossiers**, et un fichier posé à la
    racine d'état serait effacé par la prochaine mise à jour (HOS-264).
    """
    from backend.core import etat

    return etat.racine() / "db" / "bridge_negociation.json"


class ConnexionFermee(RuntimeError):
    """Le gateway n'est pas joignable — panne, pas absence de capacité."""


class _Connexion:
    """Un gateway vivant, et une seule façon de lui parler.

    Le pont ne pouvait que **négocier** : il ouvrait un gateway, posait ses
    questions, le tuait. Six secondes par question, et aucune session ne
    survivait — donc ni steer, ni approbation, ni événement pendant le
    tour. C'est la moitié du produit que ce projet appelle « agentique ».

    Cette connexion garde le processus ouvert, corrèle les réponses par
    identifiant, et met les événements de côté dans une file bornée. Elle
    porte le témoin de flux comme l'adaptateur le porte : ce processus-ci
    est un **agent**, et A-2 dit qu'un lanceur d'agent sans surveillance
    est un lanceur de trop.
    """

    #: Assez pour tenir un tour d'outils bavard sans laisser la mémoire
    #: croître si personne ne lit — les événements sont un flux, pas un
    #: journal, et le Run Ledger reste la seule mémoire durable.
    EVENEMENTS_MAX = 500

    def __init__(self, cfg, delai_demarrage: float, delai_reponse: float) -> None:
        self._cfg = cfg
        self._delai_demarrage = delai_demarrage
        self._delai_reponse = delai_reponse
        self._processus: Optional[subprocess.Popen] = None
        self._garde = None
        self._fuite: list = []
        self._reponses: dict[int, dict] = {}
        self._attentes: dict[int, threading.Event] = {}
        self._evenements: deque = deque(maxlen=self.EVENEMENTS_MAX)
        self._compteur = 0
        self._pret = threading.Event()
        self._verrou_ecriture = threading.Lock()

    # ── Cycle de vie ──────────────────────────────────────────────────

    def ouvrir(self) -> None:
        from backend.security import surveillance_flux

        racine = Path(self._cfg.hermes_home) / "hermes-agent"
        env = os.environ.copy()
        env.update({"HERMES_HOME": self._cfg.hermes_home, "PYTHONUTF8": "1",
                    "PYTHONUNBUFFERED": "1"})
        canary = surveillance_flux.fabriquer_canary()
        env = surveillance_flux.environnement_avec_canary(env, canary)
        self._garde = surveillance_flux.SurveillanceFlux(
            canary=canary,
            secrets_connus=[getattr(self._cfg, "api_key", "") or ""],
        )
        self._processus = subprocess.Popen(
            [self._cfg.python_exe, "-m", "tui_gateway.entry"],
            cwd=str(racine), env=env, stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
            encoding="utf-8", errors="replace", bufsize=1)
        threading.Thread(target=self._lire, daemon=True).start()
        self._pret.wait(timeout=self._delai_demarrage)
        self._verifier_fuite()

    def _lire(self) -> None:
        flux = self._processus.stdout  # type: ignore[union-attr]
        for ligne in flux:
            alerte = self._garde.bloc(ligne) if self._garde else None
            if alerte is not None:
                self._fuite.append(alerte)
                self._pret.set()
                for attente in list(self._attentes.values()):
                    attente.set()
                return
            try:
                message = json.loads(ligne)
            except ValueError:
                continue
            if message.get("params", {}).get("type") == "gateway.ready":
                self._pret.set()
            identifiant = message.get("id")
            if identifiant is not None:
                self._reponses[identifiant] = message
                attente = self._attentes.get(identifiant)
                if attente is not None:
                    attente.set()
            elif message.get("method") == "event":
                self._evenements.append(message.get("params") or {})

    def vivante(self) -> bool:
        return (self._processus is not None
                and self._processus.poll() is None
                and not self._fuite)

    def fermer(self) -> None:
        processus, self._processus = self._processus, None
        if processus is None:
            return
        try:
            processus.terminate()
            try:
                processus.wait(timeout=10)
            except subprocess.TimeoutExpired:
                processus.kill()
        except OSError:
            pass

    # ── Parler ────────────────────────────────────────────────────────

    def _verifier_fuite(self) -> None:
        if self._fuite:
            alerte = self._fuite[0]
            raise RuntimeError(
                f"fuite detectee sur la sortie du gateway : "
                f"{alerte.motif.value} — {alerte.detail}")

    def appeler(self, methode: str, params: Optional[dict] = None,
                timeout: Optional[float] = None) -> dict:
        """Une requête JSON-RPC, et la réponse qui lui correspond.

        Rend le message entier — `result` **ou** `error`. Ne lève pas sur
        une erreur applicative : `4001 session not found` est une réponse,
        et c'est à l'appelant d'en faire ce qu'il veut. Ne lève que quand
        il n'y a pas de réponse du tout.
        """
        if self._processus is None or self._processus.poll() is not None:
            raise ConnexionFermee("le gateway n'est pas ouvert")
        self._verifier_fuite()
        with self._verrou_ecriture:
            self._compteur += 1
            identifiant = self._compteur
            attente = threading.Event()
            self._attentes[identifiant] = attente
            try:
                self._processus.stdin.write(json.dumps({  # type: ignore[union-attr]
                    "jsonrpc": "2.0", "id": identifiant,
                    "method": methode, "params": params or {}}) + chr(10))
                self._processus.stdin.flush()  # type: ignore[union-attr]
            except (OSError, ValueError) as exc:
                self._attentes.pop(identifiant, None)
                raise ConnexionFermee(f"ecriture impossible : {exc}") from exc
        try:
            attente.wait(timeout=timeout or self._delai_reponse)
        finally:
            self._attentes.pop(identifiant, None)
        self._verifier_fuite()
        message = self._reponses.pop(identifiant, None)
        if message is None:
            raise ConnexionFermee(
                f"aucune reponse a {methode!r} en "
                f"{timeout or self._delai_reponse:.0f}s")
        return message

    def evenements(self) -> list:
        """Vide la file. Un événement lu ne l'est qu'une fois."""
        vus = list(self._evenements)
        self._evenements.clear()
        return vus


class HermesAgentBridge:
    """Le pont. Un seul par processus, et il ne décide rien.

    `config` est injectable pour que les tests n'aient pas à lancer de
    gateway ; `_lancer` l'est pour la même raison. Rien d'autre n'est
    paramétrable : un pont qu'on peut faire mentir sur ce que le runtime
    répond ne prouve plus rien.
    """

    #: Le gateway charge MCP, les skills et les métadonnées de modèle avant
    #: de répondre. Mesuré ~6 s à froid ; on laisse de la marge sans laisser
    #: une panne bloquer un appel d'interface.
    DELAI_DEMARRAGE_S = 25.0
    DELAI_REPONSE_S = 45.0

    def __init__(self, config: Any = None, lanceur=None) -> None:
        self._config = config
        self._lancer = lanceur or self._lancer_gateway
        self._verrou = threading.Lock()
        self._connexion: Optional[_Connexion] = None
        self._verrou_connexion = threading.Lock()

    # ── Parler au runtime ─────────────────────────────────────────────

    def connexion(self) -> _Connexion:
        """La connexion partagée, ouverte à la demande et rouverte si morte.

        Une seule par processus : deux gateways, c'est deux fois les skills
        chargées, deux découvertes MCP et deux fois la mémoire — pour un
        runtime qui n'a de toute façon qu'un seul état sur le disque.
        """
        with self._verrou_connexion:
            if self._connexion is not None and self._connexion.vivante():
                return self._connexion
            if self._connexion is not None:
                self._connexion.fermer()
            connexion = _Connexion(self._cfg(), self.DELAI_DEMARRAGE_S,
                                   self.DELAI_REPONSE_S)
            connexion.ouvrir()
            self._connexion = connexion
            return connexion

    def appeler(self, methode: str, params: Optional[dict] = None,
                timeout: Optional[float] = None) -> dict:
        """Relaie un appel au runtime. **Ne décide rien.**

        Le pont ne filtre pas les méthodes : la liste de ce qui est
        appelable vient de la négociation, et c'est l'appelant — un service
        Hermes OS, avec ses propres autorités — qui choisit quoi appeler.
        Un pont qui arbitrerait ici serait la seconde autorité que la règle
        interdit.
        """
        return self.connexion().appeler(methode, params, timeout)

    def demander_mutation(self, methode: str,
                          params: Optional[dict] = None,
                          timeout: Optional[float] = None) -> dict:
        """Demande au **propriétaire** de l'état d'écrire. Ne l'écrit pas.

        C'est toute la réponse de G-18 en une méthode : Hermes OS n'ouvre
        jamais `state.db`, il demande à l'agent de le faire, par l'API que
        l'agent expose pour ça. Le pont est la couture — il vérifie que la
        demande correspond à une mutation connue, et relaie.

        Il ne décide pas *si* la mutation est souhaitable : cette
        question-là appartient à l'appelant, avec ses propres autorités.
        Un pont qui trancherait ici serait la troisième autorité que le
        contrat interdit.
        """
        if methode not in MUTATIONS_CONNUES:
            raise MutationInconnue(
                f"{methode!r} n'est pas une mutation connue ; les mutations "
                f"demandables sont {sorted(MUTATIONS_CONNUES)}")
        return self.appeler(methode, params, timeout)

    def evenements(self) -> list:
        connexion = self._connexion
        return connexion.evenements() if connexion is not None else []

    def fermer(self) -> None:
        with self._verrou_connexion:
            if self._connexion is not None:
                self._connexion.fermer()
                self._connexion = None

    # ── Empreinte du runtime ──────────────────────────────────────────

    def _cfg(self):
        if self._config is None:
            from backend.ral.adapters.hermes_agent_cli import HermesAgentCliConfig

            self._config = HermesAgentCliConfig()
        return self._config

    def empreinte_runtime(self) -> tuple[str, str, str]:
        """(empreinte, version, commit) de l'agent **installé**.

        Lue sur le disque plutôt que demandée au gateway : il faut pouvoir
        décider s'il vaut la peine de le lancer avant de l'avoir lancé.
        """
        racine = Path(self._cfg().hermes_home) / "hermes-agent"
        version = "inconnue"
        try:
            for ligne in (racine / "pyproject.toml").read_text(
                    encoding="utf-8", errors="replace").splitlines():
                if ligne.startswith("version"):
                    version = ligne.split("=", 1)[1].strip().strip('"')
                    break
        except OSError:
            pass
        commit = "inconnu"
        try:
            sortie = subprocess.run(
                ["git", "-C", str(racine), "rev-parse", "HEAD"],
                capture_output=True, text=True, timeout=15)
            if sortie.returncode == 0:
                commit = sortie.stdout.strip()[:12]
        except (OSError, subprocess.SubprocessError):
            pass
        return f"{version}+{commit}", version, commit

    # ── Négociation ───────────────────────────────────────────────────

    def negocier(self, *, forcer: bool = False) -> NegociationRuntime:
        """Ce que ce runtime sait faire, mesuré ou relu du cache.

        Le cache n'est servi que si son empreinte est **celle du runtime
        installé maintenant**. Une mise à jour de l'agent le périme donc
        d'elle-même, ce qui est tout l'intérêt.
        """
        empreinte, version, commit = self.empreinte_runtime()
        if not forcer:
            connue = self._relire(empreinte)
            if connue is not None:
                return connue
        with self._verrou:
            if not forcer:
                connue = self._relire(empreinte)
                if connue is not None:
                    return connue
            resultat = self._mesurer(empreinte, version, commit)
            if resultat.negociee:
                self._ecrire(resultat)
            return resultat

    def _mesurer(self, empreinte: str, version: str,
                 commit: str) -> NegociationRuntime:
        attendues = [m for methodes in METHODES_PAR_CAPACITE.values()
                     for m in methodes]
        try:
            reponses = self._lancer(attendues)
        except Exception as exc:  # noqa: BLE001 - une panne est un résultat
            logger.warning("negociation impossible : %s", exc)
            return NegociationRuntime(
                empreinte=empreinte, version=version, commit=commit,
                mesure_le=time.time(), erreur=f"{type(exc).__name__}: {exc}")

        capacites = []
        for nom, methodes in METHODES_PAR_CAPACITE.items():
            presentes = tuple(m for m in methodes if reponses.get(m) is True)
            absentes = tuple(m for m in methodes if reponses.get(m) is not True)
            capacites.append(CapaciteRuntime(nom, presentes, absentes))
        return NegociationRuntime(
            empreinte=empreinte, version=version, commit=commit,
            mesure_le=time.time(), capacites=tuple(capacites))

    # ── Transport ─────────────────────────────────────────────────────

    def _lancer_gateway(self, methodes: list[str]) -> dict[str, bool]:
        """Interroge le vrai gateway. Rend {methode: presente}.

        Une méthode restée sans réponse n'est **pas** comptée présente :
        on ne sait pas, et « on ne sait pas » ne s'arrondit pas vers le
        haut. C'est la même règle tri-état que le verdict agentique.

        ## Le témoin, parce que ceci lance un agent

        `test_tout_lancement_d_agent_passe_par_l_adaptateur_surveille` a
        fait rougir la suite dès le premier essai, et il avait raison : ce
        `Popen` lance le **vrai** gateway de Hermes Agent avec
        `os.environ.copy()`, c'est-à-dire tous les secrets de la machine,
        et rien n'examinait sa sortie. C'est exactement A-2/HOS-218, un
        cran plus loin — un second lanceur né sans surveillance, comme les
        replis cloud étaient nés sans pare-feu (A-1).

        Le témoin est donc posé ici comme il l'est dans l'adaptateur, et la
        sortie du gateway passe par la même `SurveillanceFlux`. Une fuite
        n'est pas une négociation : elle lève, et la négociation échoue.
        """
        from backend.security import surveillance_flux

        cfg = self._cfg()
        racine = Path(cfg.hermes_home) / "hermes-agent"
        env = os.environ.copy()
        env.update({"HERMES_HOME": cfg.hermes_home, "PYTHONUTF8": "1",
                    "PYTHONUNBUFFERED": "1"})
        canary = surveillance_flux.fabriquer_canary()
        env = surveillance_flux.environnement_avec_canary(env, canary)
        garde = surveillance_flux.SurveillanceFlux(
            canary=canary,
            secrets_connus=[getattr(cfg, "api_key", "") or ""],
        )

        processus = subprocess.Popen(
            [cfg.python_exe, "-m", "tui_gateway.entry"], cwd=str(racine),
            env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, encoding="utf-8",
            errors="replace", bufsize=1)

        reponses: dict[int, dict] = {}
        pret = threading.Event()
        fuite: list = []

        def lire() -> None:
            for ligne in processus.stdout:  # type: ignore[union-attr]
                alerte = garde.bloc(ligne)
                if alerte is not None:
                    fuite.append(alerte)
                    pret.set()
                    return
                try:
                    message = json.loads(ligne)
                except ValueError:
                    continue
                if message.get("params", {}).get("type") == "gateway.ready":
                    pret.set()
                if "id" in message:
                    reponses[message["id"]] = message

        threading.Thread(target=lire, daemon=True).start()
        try:
            pret.wait(timeout=self.DELAI_DEMARRAGE_S)
            for identifiant, methode in enumerate(methodes, start=1):
                processus.stdin.write(json.dumps({  # type: ignore[union-attr]
                    "jsonrpc": "2.0", "id": identifiant,
                    "method": methode, "params": {}}) + "\n")
                processus.stdin.flush()  # type: ignore[union-attr]
                time.sleep(0.1)
            limite = time.monotonic() + self.DELAI_REPONSE_S
            while (time.monotonic() < limite
                   and len(reponses) < len(methodes)
                   and not fuite):
                # `not fuite` : une fuite doit couper tout de suite. Sans
                # cette condition, un gateway qui recrache le temoin faisait
                # quand meme attendre les 45 s du delai — on aurait laisse
                # tourner, quarante-cinq secondes durant, un processus dont
                # on savait deja qu'il exfiltrait.
                time.sleep(0.25)
        finally:
            processus.terminate()
            try:
                processus.wait(timeout=10)
            except subprocess.TimeoutExpired:
                processus.kill()

        if fuite:
            # Ne pas « négocier quand même » : une sortie qui porte le témoin
            # a vu ce qu'elle n'aurait pas dû voir, et un résultat tiré de
            # là ne vaut rien. L'appelant transforme cette levée en
            # `negociee = False`, qui dit « panne » et non « pas de
            # capacité ».
            raise RuntimeError(
                f"fuite detectee sur la sortie du gateway : "
                f"{fuite[0].motif.value} — {fuite[0].detail}")
        return {m: self._presente(reponses.get(i))
                for i, m in enumerate(methodes, start=1)}

    @staticmethod
    def _presente(message: Optional[dict]) -> bool:
        """Une erreur applicative prouve la présence ; `-32601` l'infirme.

        Sans réponse du tout, on ne conclut pas — la méthode est comptée
        absente parce qu'on ne peut pas s'en servir, pas parce qu'on sait
        qu'elle n'existe pas.
        """
        if message is None:
            return False
        erreur = message.get("error")
        if erreur is None:
            return True
        return erreur.get("code") != CODE_METHODE_INCONNUE

    # ── Persistance ───────────────────────────────────────────────────

    def _relire(self, empreinte: str) -> Optional[NegociationRuntime]:
        try:
            brut = json.loads(_magasin().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if brut.get("empreinte") != empreinte:
            return None
        try:
            return NegociationRuntime(
                empreinte=brut["empreinte"], version=brut["version"],
                commit=brut["commit"], mesure_le=float(brut["mesure_le"]),
                capacites=tuple(
                    CapaciteRuntime(c["nom"], tuple(c["methodes_presentes"]),
                                    tuple(c["methodes_absentes"]))
                    for c in brut.get("capacites") or ()),
            )
        except (KeyError, TypeError, ValueError):
            return None

    def _ecrire(self, resultat: NegociationRuntime) -> None:
        try:
            chemin = _magasin()
            chemin.parent.mkdir(parents=True, exist_ok=True)
            chemin.write_text(json.dumps(resultat.as_dict(), indent=2),
                              encoding="utf-8")
        except OSError:
            logger.debug("persistance de la negociation impossible",
                         exc_info=True)
