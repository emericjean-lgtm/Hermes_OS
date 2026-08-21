"""Hermes Agent tenu ouvert, au lieu d'être relancé à chaque tâche (HOS-137).

`hermes_agent_cli.py` lance `cli.py` en sous-processus **jeté après chaque
tâche**. Aucun état ne survit — et l'agent implémente pourtant, dans ses
134 modules :

* `context_compressor.py` / `conversation_compression.py` — compression
  automatique de la fenêtre pour les conversations longues ;
* `background_review.py` — fork l'agent après chaque tour pour évaluer ce
  qui vient d'être fait ;
* `curator.py` — maintenance des skills en tâche de fond ;
* `memory_manager.py` — orchestration des fournisseurs de mémoire ;
* `verification_stop.py` — garde de fin de tour sur les éditions de code.

Aucune des quatre premières ne peut s'appliquer à un processus qui meurt
après un tour : il n'y a ni conversation longue à compresser, ni tour
précédent à relire, ni session où le curator puisse tourner. Elles ne sont
pas absentes, elles sont **inatteignables**.

## Ce que ce module change

Une session ACP tenue ouverte, sur laquelle on envoie des tours successifs.
Mesuré le 2026-08-21, huit tours dans une même session : deux témoins
ancrés, l'un au **premier** tour et l'autre au **milieu**, tous deux
restitués au huitième. Interrogé sur son propre état, l'agent déclare
16 messages et **29 176 / 131 072 jetons (22,3 %)**.

Les deux témoins comptent, pas un seul : llama.cpp, en décalage de
contexte, conserve le début et évince le milieu. Un témoin de début aurait
donc pu survivre à une perte de mémoire réelle.

## Deux pièges, tous deux mesurés

**Le texte de la réponse n'est pas dans le résultat JSON-RPC.** Celui-ci ne
porte que `stopReason` et `usage`. Le texte arrive par des notifications
`session/update` de type `agent_message_chunk`, le raisonnement par
`agent_thought_chunk` — mesuré : 256 morceaux de pensée pour 7 de réponse
sur une question triviale. Une première sonde qui ignorait les
notifications a conclu « la session ne tient pas » alors qu'elle tenait.

**L'interpréteur est celui de l'AGENT, jamais `sys.executable`.** La lib
`acp` vit dans son venv, et les deux environnements sont séparés à dessein
depuis HOS-103 : c'est ce qui empêche un `hermes update` de changer l'arbre
de dépendances de Hermes OS.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("hermes_os.ral.acp")

#: Combien de lignes du journal de l'agent on garde sous la main. Assez pour
#: qu'un blocage soit explicable — le diagnostic du 21 août tenait dans les
#: quatre dernières —, assez peu pour ne pas retenir une session entière.
LIGNES_DE_JOURNAL = 200

#: Un tour d'agent sur du travail réel : plusieurs inférences, des appels
#: d'outils, parfois une compression. Même ordre de grandeur que
#: `_HERMES_AGENT_TIMEOUT_S`, pour la même raison mesurée.
DELAI_TOUR_S = 900.0
DELAI_ETABLISSEMENT_S = 120.0


#: Le lanceur vit à côté de ce module et s'exécute avec l'interpréteur de
#: **l'agent**, pas celui de Hermes OS.
LANCEUR = Path(__file__).with_name("lanceur_agent.py")


#: `/c/Users/x`, `/cygdrive/c/...`, `/mnt/c/...` — un lecteur Windows dans
#: la graphie POSIX. Une seule lettre, sans quoi `/etc/passwd` deviendrait
#: un lecteur `E:` et un chemin système passerait pour un disque.
_LECTEUR_POSIX = re.compile(r"^/(?:(?:cygdrive|mnt)/)?([a-zA-Z])(/.*)?$")


def _depuis_msys(chemin: str) -> str:
    """Traduit un chemin Git Bash en chemin Windows, sinon rend l'entrée.

    L'agent fait passer ses outils fichier par Git Bash sous Windows et
    produit donc naturellement `/c/Users/...`. Sans cette traduction, la
    frontière du workspace résolvait ce chemin contre la racine du lecteur
    et obtenait un `C:` suivi d'un segment `c` parasite — hors du
    workspace, donc refusé.

    Mesure du 2026-08-21 : trois refus consécutifs sur une écriture
    parfaitement légitime, dans le workspace confié. L'agent a fini par
    contourner, mais un faux refus coûte autant qu'une fuite — à ceci près
    qu'il se voit.

    La traduction ne relâche rien : `is_relative_to` s'applique ensuite au
    chemin traduit, donc la forme POSIX d'un dossier système reste refusée
    exactement comme sa forme Windows.
    """
    correspondance = _LECTEUR_POSIX.match(chemin or "")
    if not correspondance:
        return chemin
    lecteur = correspondance.group(1).upper()
    reste = (correspondance.group(2) or "").replace("/", chr(92))
    return f"{lecteur}:{reste or chr(92)}"


def _racine_agent() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", "")) / "hermes" / "hermes-agent"


@dataclass
class Tour:
    """Ce qu'un tour a produit, séparé comme l'agent le sépare."""

    texte: str = ""
    pensee: str = ""
    stop: str = ""
    #: **Cumulatif sur la session**, pas l'occupation de la fenêtre — c'est
    #: la somme des jetons d'entrée de chaque appel au fournisseur. Lu comme
    #: une occupation, il affichait 133 687 là où l'agent déclarait 29 176 :
    #: quatorzième défaut de mesure de ce projet, même famille que les
    #: treize précédents. Pour l'occupation réelle, la commande `/context`
    #: de l'agent est la source.
    jetons_entree: int = 0
    jetons_sortie: int = 0
    erreur: str = ""

    @property
    def abouti(self) -> bool:
        """`end_turn` **et** du texte.

        Ni l'un ni l'autre seul ne suffit : un tour interrompu peut porter
        du texte partiel, et un tour vide peut s'annoncer terminé.
        """
        return self.stop == "end_turn" and bool(self.texte.strip())


@dataclass
class SessionAgent:
    """Une session ACP vivante. Un processus, plusieurs tours."""

    session_id: str = ""
    cwd: str = ""
    proc: Any = None
    compteur: int = 0
    verrou: Any = field(default=None)
    #: Les dernières lignes de la sortie d'erreur de l'agent. Jeter ce flux
    #: dans `DEVNULL` a rendu invisible, une séance entière durant, un
    #: blocage que ses quatre dernières lignes expliquaient.
    journal: Any = field(default_factory=lambda: deque(maxlen=LIGNES_DE_JOURNAL))
    #: Le modèle actuellement servi par la session. Retenu pour ne pas
    #: rebasculer à chaque tour sur un modèle déjà en place : chaque bascule
    #: reconstruit l'agent côté Hermes Agent.
    modele: str = ""
    #: Vrai quand l'agent a retrouve la session demandee, faux quand il en a
    #: recree une. La difference est invisible dans le protocole et decisive
    #: pour l'appelant : une reprise garde le contexte, une recreation non.
    reprise: bool = False
    _lecteur: Any = None

    def derniers_signes(self, n: int = 4) -> str:
        """Ce que l'agent disait juste avant de se taire."""
        return " | ".join(list(self.journal)[-n:])


class HermesAgentACP:
    """Client ACP minimal : ouvrir, envoyer des tours, fermer.

    Volontairement mince. Il ne réimplémente rien de ce que l'agent fait —
    c'est tout l'objet du chantier : les fonctionnalités vivent là-bas, ce
    module ne fait que tenir la porte ouverte.
    """

    def __init__(self, racine: Optional[str] = None) -> None:
        self._racine = Path(racine) if racine else _racine_agent()
        self._python = self._racine / "venv" / "Scripts" / "python.exe"
        self._session: Optional[SessionAgent] = None

    def disponible(self) -> tuple[bool, str]:
        """Peut-on seulement démarrer ? Et sinon, pourquoi.

        Rendu comme un couple pour que l'appelant puisse **dire** pourquoi
        il retombe sur le mode jetable, au lieu de le faire en silence.
        """
        if not self._python.is_file():
            return False, f"interpréteur de l'agent absent : {self._python}"
        if not (self._racine / "acp_adapter").is_dir():
            return False, f"acp_adapter absent sous {self._racine}"
        return True, ""

    async def ouvrir(self, cwd: str, *, reprendre: str = "") -> SessionAgent:
        """Ouvre une session, en reprenant `reprendre` si c'est possible.

        L'agent persiste ses sessions sur disque : une session survit donc
        au processus qui l'a servie, et `session/resume` la retrouve. Sans
        cela, un agent qui meurt à la section 18 d'un cahier emporte tout le
        contexte de la campagne — et le harnais ne vaudrait plus, à cet
        instant précis, que le mode jetable qu'il remplace.

        `session/resume` recrée une session neuve quand l'identifiant est
        introuvable. C'est le bon comportement et il est voulu ici : perdre
        le contexte est regrettable, refuser de travailler serait pire.
        """
        ok, raison = self.disponible()
        if not ok:
            raise RuntimeError(raison)
        proc = await asyncio.create_subprocess_exec(
            # Jamais `-m acp_adapter` directement : le lanceur interdit aux
            # sous-processus de l'agent d'hériter du canal ACP, sans quoi le
            # premier outil fichier de chaque mission bloque pour toujours.
            # Voir `lanceur_agent.py` pour la mesure.
            str(self._python), str(LANCEUR), str(self._racine),
            cwd=str(self._racine),
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            # Le workspace confié, pour le garde-fou `pre_tool_call` de
            # `config/hooks/garde_workspace.py`. Le terminal de l'agent ne
            # demande aucune permission : sans cette référence, le hook n'a
            # rien à quoi comparer et se tait.
            env={**os.environ, "HERMES_OS_WORKSPACE": str(Path(cwd).resolve())},
        )
        session = SessionAgent(cwd=cwd, proc=proc)
        session.verrou = asyncio.Lock()
        session._lecteur = asyncio.create_task(self._suivre_journal(session))
        self._session = session

        await self._echanger(session, "initialize", {
            "protocolVersion": 1,
            "clientCapabilities": {"fs": {"readTextFile": False,
                                          "writeTextFile": False}},
        }, DELAI_ETABLISSEMENT_S, [])
        if reprendre:
            reponse = await self._echanger(
                session, "session/resume",
                {"cwd": cwd, "sessionId": reprendre, "mcpServers": []},
                DELAI_ETABLISSEMENT_S, [])
            # `session/resume` peut rendre un identifiant different du
            # demande : c'est alors qu'il n'a pas retrouve l'ancien et en a
            # cree un neuf. On lit donc ce qu'il rend, sans jamais supposer
            # que c'est celui qu'on a demande.
            rendu = (reponse.get("result") or {}).get("sessionId", "") or reprendre
            session.session_id = rendu
            session.reprise = (rendu == reprendre)
            logger.info("session ACP %s : %s (%s)",
                        "reprise" if session.reprise else "recreee", rendu, cwd)
            if session.session_id:
                return session
            logger.warning("reprise de %s sans identifiant : on repart a neuf",
                           reprendre)

        reponse = await self._echanger(session, "session/new",
                                       {"cwd": cwd, "mcpServers": []},
                                       DELAI_ETABLISSEMENT_S, [])
        session.session_id = (reponse.get("result") or {}).get("sessionId", "")
        if not session.session_id:
            raise RuntimeError("l'agent n'a pas rendu de sessionId")
        logger.info("session ACP ouverte : %s (%s)", session.session_id, cwd)
        return session

    async def tour(self, texte: str, *, delai: float = DELAI_TOUR_S,
                   au_fil_de_l_eau: Any = None) -> Tour:
        """Un tour, dans le contexte accumulé.

        `au_fil_de_l_eau(genre, fragment)` est appelé pour chaque morceau
        reçu, `genre` valant `"reponse"` ou `"pensee"`. Sans lui, le tour
        n'est rendu qu'à la fin — acceptable pour une tâche de mission,
        pas pour une conversation, où l'attente muette d'une minute est
        indiscernable d'une panne.
        """
        if self._session is None or not self._session.session_id:
            raise RuntimeError("aucune session ouverte")
        return await self._prompt(self._session, texte, delai,
                                  au_fil_de_l_eau=au_fil_de_l_eau)

    async def choisir_modele(self, modele: str) -> bool:
        """Change le modèle **sans perdre le contexte** de la session.

        Le routeur de Hermes OS choisit un modèle par tâche ; une session
        ouverte au premier modèle et jamais informée ensuite ferait de ce
        choix une décoration. `session/set_model` est la méthode que l'agent
        expose déjà pour cela — on ne réimplémente rien.

        Ce qui rend l'opération sûre est côté agent, et vaut d'être écrit
        ici parce que rien ne le laisse deviner : `set_session_model`
        reconstruit `state.agent` mais **ne touche pas à `state.history`**.
        Le contexte accumulé traverse donc le changement de modèle — ce qui
        est exactement ce qu'on veut d'une mission qui alterne un petit
        modèle d'exécution et un plus grand pour une étape difficile.

        Rend `False` plutôt que de lever : un changement de modèle refusé
        dégrade la tâche, il ne l'annule pas.
        """
        session = self._session
        if session is None or not session.session_id:
            raise RuntimeError("aucune session ouverte")
        if not modele or modele == session.modele:
            return True
        async with session.verrou:
            try:
                await self._echanger(
                    session, "session/set_model",
                    {"sessionId": session.session_id, "modelId": modele},
                    DELAI_ETABLISSEMENT_S, [])
            except Exception as erreur:  # noqa: BLE001 - dégrade, n'annule pas
                logger.warning("modèle %r refusé par l'agent : %s", modele, erreur)
                return False
        session.modele = modele
        logger.info("session %s : modèle basculé sur %s",
                    session.session_id, modele)
        return True

    async def fermer(self) -> None:
        session, self._session = self._session, None
        if session is None or session.proc is None:
            return
        if session._lecteur is not None:
            session._lecteur.cancel()
        try:
            session.proc.terminate()
            await asyncio.wait_for(session.proc.wait(), timeout=10)
        except (asyncio.TimeoutError, ProcessLookupError):
            try:
                session.proc.kill()
            except ProcessLookupError:
                pass

    # -- plomberie ---------------------------------------------------

    @staticmethod
    async def _suivre_journal(session: SessionAgent) -> None:
        """Draine la sortie d'erreur de l'agent, sans jamais la jeter.

        Deux raisons, la seconde apprise le 21 août :

        1. un tube que personne ne vide finit par se remplir, et l'agent
           bloque alors sur sa propre journalisation ;
        2. c'est la seule source qui explique un blocage. `MCP: registered
           0 tool(s)` disait tout, et partait dans `DEVNULL`.
        """
        flux = session.proc.stderr
        if flux is None:
            return
        while True:
            ligne = await flux.readline()
            if not ligne:
                return
            texte = ligne.decode("utf-8", "replace").rstrip()
            if texte:
                session.journal.append(texte)
                logger.debug("agent: %s", texte)

    async def _echanger(self, session: SessionAgent, methode: str,
                        params: dict, delai: float, collecte: list, *,
                        au_fil_de_l_eau: Any = None) -> dict:
        session.compteur += 1
        identifiant = session.compteur
        message = {"jsonrpc": "2.0", "id": identifiant,
                   "method": methode, "params": params}
        session.proc.stdin.write((json.dumps(message) + "\n").encode())
        await session.proc.stdin.drain()

        boucle = asyncio.get_running_loop()
        echeance = boucle.time() + delai
        while True:
            restant = echeance - boucle.time()
            if restant <= 0:
                raise asyncio.TimeoutError(
                    f"{methode} sans réponse en {delai:.0f}s")
            ligne = await asyncio.wait_for(
                session.proc.stdout.readline(), timeout=restant)
            if not ligne:
                raise RuntimeError(f"{methode} : flux fermé par l'agent")
            try:
                recu = json.loads(ligne.decode("utf-8", "replace"))
            except json.JSONDecodeError:
                continue
            if recu.get("method") and recu.get("id") is not None:
                # **Une requête, pas une notification.** L'agent interroge
                # le client — `session/request_permission` avant toute
                # écriture — et attend une réponse. La traiter comme une
                # notification bloque le tour indéfiniment : mesuré, le
                # tour « crée un fichier » n'est jamais revenu.
                #
                # Testé AVANT l'identifiant, et l'ordre est tout. Les deux
                # sens numérotent dans le même espace — l'agent à partir de
                # 0, nous à partir de 1 — si bien qu'une demande de
                # permission finit par porter l'identifiant du tour en
                # cours. Testé après, on la prenait pour notre réponse :
                # le tour rendait la main sans `stopReason`, tandis que
                # l'agent attendait pour toujours une permission qui ne
                # venait plus. Mesuré le 2026-08-21 — le fichier était bien
                # écrit, la tâche suivante recevait « Redirected the active
                # turn », et rien dans le protocole ne le disait.
                await self._repondre(session, recu)
                continue
            if recu.get("id") == identifiant:
                return recu
            # Notification. Le texte de la réponse ne voyage QUE par là :
            # le résultat JSON-RPC ne porte que stopReason et usage.
            collecte.append(recu)
            if au_fil_de_l_eau is not None:
                genre, fragment = self.morceau(recu)
                if genre and fragment:
                    try:
                        au_fil_de_l_eau(genre, fragment)
                    except Exception:  # noqa: BLE001 - un observateur ne
                        # casse pas le tour qu'il observe : le client peut
                        # avoir raccroché, le travail lui continue.
                        logger.debug("observateur de flux en échec",
                                     exc_info=True)


    @staticmethod
    def _hors_workspace(session: SessionAgent, params: dict) -> str:
        """Le chemin visé sort-il du workspace ? Et lequel.

        Rend une chaîne vide quand tout est dedans, le motif du refus
        sinon — pour que le journal dise **quoi** a été refusé.

        Les chemins arrivent sous la forme que le modèle a produite, y
        compris `/Users/emeri/note.txt` : rooté, sans lettre de lecteur.
        `Path.is_absolute()` rend `False` là-dessus sous Windows, donc un
        test naïf le prendrait pour un chemin relatif et le croirait dans
        le workspace. C'est exactement le piège qui a coûté cinq
        correctifs côté Hermes OS (HOS-129 à 133) — on le traite ici en
        résolvant **contre la racine du lecteur**, jamais contre le
        workspace.
        """
        try:
            racine = Path(session.cwd).resolve()
        except (OSError, ValueError):
            return "workspace de la session illisible"

        vises: list[str] = []
        appel = params.get("toolCall") or {}
        for bloc in (appel.get("content") or []):
            if isinstance(bloc, dict) and bloc.get("path"):
                vises.append(str(bloc["path"]))
        for cle in ("path", "locations"):
            valeur = appel.get(cle)
            if isinstance(valeur, str):
                vises.append(valeur)
            elif isinstance(valeur, list):
                vises.extend(str((v or {}).get("path", "")) for v in valeur
                             if isinstance(v, dict) and v.get("path"))

        for recu in vises:
            if not recu:
                continue
            # Traduit AVANT toute décision : la vérification porte ensuite
            # sur le chemin réel, jamais sur la graphie.
            brut = _depuis_msys(recu)
            candidat = Path(brut)
            try:
                if candidat.is_absolute():
                    resolu = candidat.resolve()
                elif brut.startswith(("/", "\\")):
                    # Rooté sans lecteur : le système le résoudra contre le
                    # lecteur courant, pas contre le workspace.
                    resolu = Path(racine.anchor) / brut.lstrip("/\\")
                else:
                    resolu = (racine / candidat).resolve()
                if not resolu.is_relative_to(racine):
                    return f"{recu!r} -> {resolu} hors de {racine}"
            except (OSError, ValueError):
                return f"chemin non résoluble : {recu!r}"
        return ""

    async def _repondre(self, session: SessionAgent, requete: dict) -> None:
        """Répondre aux requêtes que l'agent adresse au client.

        La seule qui bloque aujourd'hui est `session/request_permission` :
        l'agent la pose avant chaque écriture et attend. Sans réponse, le
        tour ne revient jamais — c'est ce qui a fait passer l'intégration
        ACP pour « bloquée » pendant des jours.

        **Le chemin est vérifié avant d'accorder, et c'est indispensable.**
        La première version accordait aveuglément, au motif que « le
        workspace est déjà contraint par le `cwd` de la session ». Mesuré
        le 2026-08-21 : session ouverte sur un dossier temporaire, l'agent
        a demandé à écrire `/Users/emeri/note.txt`, et le fichier est
        apparu à la racine du profil utilisateur — **hors du workspace** —
        pendant que le dossier confié restait vide.

        Le `cwd` d'une session ACP *oriente* l'agent ; il ne le contraint
        pas. Rien en aval ne repassera par Aegis, puisque l'agent écrit par
        ses propres outils.

        Un chemin qu'on ne sait pas situer est refusé. Ne pas savoir n'est
        pas une raison d'autoriser.

        ## Ce que cette frontière ne couvre pas

        Une version antérieure de ce commentaire affirmait que la frontière
        était « ici, et nulle part ailleurs ». **C'était faux**, et la
        mesure l'a démenti le 2026-08-21 : trois demandes `write_file` vers
        un chemin hors workspace, trois refus — puis, mot pour mot dans la
        réponse de l'agent :

            The write was blocked by the ACP client.
            Let me try using the terminal directly.

        Le fichier est apparu hors du workspace.

        `session/request_permission` ne porte que sur les **éditions de
        fichiers** (`kind: "edit"`). Le terminal de l'agent, lui, ne demande
        aucune permission : il exécute. Refuser ici détourne donc l'agent
        vers un chemin non gardé, sans rien empêcher.

        Ce n'est pas une régression du harnais — le mode jetable donnait
        déjà le même terminal à l'agent. C'est une propriété de Hermes
        Agent, conçu pour tourner avec la confiance de son utilisateur.

        La seule contrainte réelle est un backend d'exécution isolé
        (`terminal.backend: docker`), qui est une décision d'exploitation.
        À défaut, `config/hooks/` pose un garde-fou côté agent : il attrape
        les erreurs franches, il n'arrête pas qui cherche à sortir.
        """
        methode = requete.get("method", "")
        if methode.endswith("request_permission"):
            params = requete.get("params") or {}
            dehors = self._hors_workspace(session, params)
            if dehors:
                logger.warning("permission refusée : %s", dehors)
                resultat = {"outcome": {"outcome": "cancelled"}}
            else:
                choix = ""
                for option in (params.get("options") or []):
                    identifiant_option = (option or {}).get("optionId", "")
                    if identifiant_option == "allow_always":
                        choix = identifiant_option
                        break
                    if identifiant_option == "allow_once" and not choix:
                        choix = identifiant_option
                resultat = ({"outcome": {"outcome": "selected",
                                         "optionId": choix}} if choix
                            else {"outcome": {"outcome": "cancelled"}})
        else:
            # Une requête qu'on ne sait pas traiter : répondre une erreur
            # plutôt que se taire. Le silence bloque l'agent ; une erreur
            # le laisse décider.
            resultat = None

        reponse = {"jsonrpc": "2.0", "id": requete.get("id")}
        if resultat is None:
            reponse["error"] = {"code": -32601,
                                "message": f"methode non geree : {methode}"}
        else:
            reponse["result"] = resultat
        session.proc.stdin.write((json.dumps(reponse) + "\n").encode())

    async def _prompt(self, session: SessionAgent, texte: str,
                      delai: float, *, au_fil_de_l_eau: Any = None) -> Tour:
        collecte: list = []
        async with session.verrou:
            try:
                reponse = await self._echanger(
                    session, "session/prompt",
                    {"sessionId": session.session_id,
                     "prompt": [{"type": "text", "text": texte}]},
                    delai, collecte, au_fil_de_l_eau=au_fil_de_l_eau)
            except Exception as erreur:  # noqa: BLE001 - un tour ne casse rien
                # Le motif seul ne dit rien d'un tour qui expire : « aucune
                # réponse en 900 s » n'oriente vers rien. Ce que l'agent
                # disait juste avant, si.
                signes = session.derniers_signes()
                return Tour(erreur=f"{type(erreur).__name__}: {erreur}"
                                   + (f" — dernier signe de l'agent : {signes}"
                                      if signes else ""))
        return self.lire(reponse, collecte)

    @staticmethod
    def morceau(notification: dict) -> tuple[str, str]:
        """Ce qu'une notification porte : `(genre, texte)`.

        Partagé par le flux au fil de l'eau et par l'assemblage final, pour
        qu'ils ne puissent pas diverger. Les avoir écrits deux fois aurait
        laissé le direct montrer autre chose que ce que la conversation
        garde — et c'est le direct que l'utilisateur croit.

        `genre` vaut `"reponse"`, `"pensee"`, ou `""` pour tout le reste :
        une session émet aussi des mises à jour d'outils et de plan, qui ne
        sont ni l'une ni l'autre.
        """
        maj = (notification.get("params") or {}).get("update") or {}
        contenu = maj.get("content") or {}
        fragment = contenu.get("text", "") if isinstance(contenu, dict) else ""
        genre = maj.get("sessionUpdate")
        if genre == "agent_message_chunk":
            return "reponse", fragment
        if genre == "agent_thought_chunk":
            return "pensee", fragment
        return "", ""

    @staticmethod
    def lire(reponse: dict, notifications: list) -> Tour:
        """Assembler le tour à partir du résultat **et** des notifications.

        Les deux sont nécessaires et aucun ne suffit : le résultat porte
        `stopReason` et `usage`, les notifications portent le texte. Lire
        seulement le premier faisait conclure qu'une session vivante ne
        retenait rien.
        """
        resultat = reponse.get("result") or {}
        usage = resultat.get("usage") or {}
        morceaux: list[str] = []
        pensees: list[str] = []
        for notification in notifications:
            genre, fragment = HermesAgentACP.morceau(notification)
            if genre == "reponse":
                morceaux.append(fragment)
            elif genre == "pensee":
                pensees.append(fragment)
        return Tour(
            texte="".join(morceaux),
            pensee="".join(pensees),
            stop=str(resultat.get("stopReason") or ""),
            jetons_entree=int(usage.get("inputTokens") or 0),
            jetons_sortie=int(usage.get("outputTokens") or 0),
            erreur=str((reponse.get("error") or {}).get("message", "")),
        )
