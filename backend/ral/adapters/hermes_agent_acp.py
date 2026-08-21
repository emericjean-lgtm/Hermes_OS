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
Mesuré le 2026-08-21 : deux prompts dans une même session, jetons d'entrée
**13 121 puis 26 273** — le contexte s'accumule, et le second tour se
souvient du premier.

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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("hermes_os.ral.acp")

#: Un tour d'agent sur du travail réel : plusieurs inférences, des appels
#: d'outils, parfois une compression. Même ordre de grandeur que
#: `_HERMES_AGENT_TIMEOUT_S`, pour la même raison mesurée.
DELAI_TOUR_S = 900.0
DELAI_ETABLISSEMENT_S = 120.0


def _racine_agent() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", "")) / "hermes" / "hermes-agent"


@dataclass
class Tour:
    """Ce qu'un tour a produit, séparé comme l'agent le sépare."""

    texte: str = ""
    pensee: str = ""
    stop: str = ""
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

    async def ouvrir(self, cwd: str) -> SessionAgent:
        ok, raison = self.disponible()
        if not ok:
            raise RuntimeError(raison)
        proc = await asyncio.create_subprocess_exec(
            str(self._python), "-m", "acp_adapter", cwd=str(self._racine),
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        session = SessionAgent(cwd=cwd, proc=proc)
        session.verrou = asyncio.Lock()
        self._session = session

        await self._echanger(session, "initialize", {
            "protocolVersion": 1,
            "clientCapabilities": {"fs": {"readTextFile": False,
                                          "writeTextFile": False}},
        }, DELAI_ETABLISSEMENT_S, [])
        reponse = await self._echanger(session, "session/new",
                                       {"cwd": cwd, "mcpServers": []},
                                       DELAI_ETABLISSEMENT_S, [])
        session.session_id = (reponse.get("result") or {}).get("sessionId", "")
        if not session.session_id:
            raise RuntimeError("l'agent n'a pas rendu de sessionId")
        logger.info("session ACP ouverte : %s (%s)", session.session_id, cwd)
        return session

    async def tour(self, texte: str, *, delai: float = DELAI_TOUR_S) -> Tour:
        """Un tour, dans le contexte accumulé."""
        if self._session is None or not self._session.session_id:
            raise RuntimeError("aucune session ouverte")
        return await self._prompt(self._session, texte, delai)

    async def fermer(self) -> None:
        session, self._session = self._session, None
        if session is None or session.proc is None:
            return
        try:
            session.proc.terminate()
            await asyncio.wait_for(session.proc.wait(), timeout=10)
        except (asyncio.TimeoutError, ProcessLookupError):
            try:
                session.proc.kill()
            except ProcessLookupError:
                pass

    # -- plomberie ---------------------------------------------------

    async def _echanger(self, session: SessionAgent, methode: str,
                        params: dict, delai: float, collecte: list) -> dict:
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
            if recu.get("id") == identifiant:
                return recu
            if recu.get("method") and recu.get("id") is not None:
                # **Une requête, pas une notification.** L'agent interroge
                # le client — `session/request_permission` avant toute
                # écriture — et attend une réponse. La traiter comme une
                # notification bloque le tour indéfiniment : mesuré, le
                # tour « crée un fichier » n'est jamais revenu.
                await self._repondre(session, recu)
                continue
            # Notification. Le texte de la réponse ne voyage QUE par là :
            # le résultat JSON-RPC ne porte que stopReason et usage.
            collecte.append(recu)


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

        for brut in vises:
            if not brut:
                continue
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
                    return f"{brut!r} -> {resolu} hors de {racine}"
            except (OSError, ValueError):
                return f"chemin non résoluble : {brut!r}"
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
        pas. La frontière est **ici**, et nulle part ailleurs : rien en
        aval ne repassera par Aegis, puisque l'agent écrit par ses propres
        outils.

        Un chemin qu'on ne sait pas situer est refusé. Ne pas savoir n'est
        pas une raison d'autoriser.
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
                      delai: float) -> Tour:
        collecte: list = []
        async with session.verrou:
            try:
                reponse = await self._echanger(
                    session, "session/prompt",
                    {"sessionId": session.session_id,
                     "prompt": [{"type": "text", "text": texte}]},
                    delai, collecte)
            except Exception as erreur:  # noqa: BLE001 - un tour ne casse rien
                return Tour(erreur=f"{type(erreur).__name__}: {erreur}")
        return self.lire(reponse, collecte)

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
            maj = (notification.get("params") or {}).get("update") or {}
            genre = maj.get("sessionUpdate")
            contenu = maj.get("content") or {}
            fragment = contenu.get("text", "") if isinstance(contenu, dict) else ""
            if genre == "agent_message_chunk":
                morceaux.append(fragment)
            elif genre == "agent_thought_chunk":
                pensees.append(fragment)
        return Tour(
            texte="".join(morceaux),
            pensee="".join(pensees),
            stop=str(resultat.get("stopReason") or ""),
            jetons_entree=int(usage.get("inputTokens") or 0),
            jetons_sortie=int(usage.get("outputTokens") or 0),
            erreur=str((reponse.get("error") or {}).get("message", "")),
        )
