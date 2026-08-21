"""Ce que le harnais exige pour fonctionner, vérifié et non supposé (HOS-138).

La relation entre Hermes OS et Hermes Agent n'est pas à sens unique. Hermes
OS lance l'agent — et **l'agent rappelle Hermes OS** par MCP pour obtenir
ses outils. C'est une boucle, et elle a une conséquence que rien
n'énonçait :

    un agent lancé pendant que le backend est éteint est un agent sans
    outils.

Mesuré le 2026-08-21, dans le journal de l'agent :

    [INFO] tools.file_tools: Creating new local environment for task...
    [WARNING] tools.mcp_tool: MCP server 'hermes-ollama' failed initial
             connection after 3 attempts
    [WinError 1225] Le système distant a refusé la connexion réseau
    [INFO] tools.mcp_tool: MCP: registered 0 tool(s) from 0 server(s)

Le tour ne revenait jamais. Cette fonction transforme ce blocage muet en
une phrase lisible avant qu'il ne se produise — même intention que
`context_guard.py`, qui vérifie au démarrage le contexte réellement servi
par Ollama plutôt que de le supposer.

## Pourquoi une vérification et pas un démarrage automatique

Démarrer le backend depuis ici en ferait un effet de bord invisible : deux
instances pourraient se disputer le port, et un opérateur qui a arrêté son
serveur exprès le verrait revenir sans l'avoir demandé. On constate, on le
dit, et on laisse décider.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger("hermes_os.ral.prerequis")

#: Court : on veut savoir si quelque chose écoute, pas attendre un service
#: lent. Un backend qui met plus de trois secondes à répondre sur `/health`
#: a un problème que ce module n'a pas vocation à masquer.
DELAI_SONDE_S = 3.0


@dataclass(frozen=True)
class Prerequis:
    """L'état de ce dont le harnais a besoin.

    `pret` n'est vrai que si **tout** l'est. Les champs individuels
    existent pour que l'appelant dise *ce qui* manque, pas seulement
    qu'il manque quelque chose — un message « le harnais est indisponible »
    envoie chercher au mauvais endroit.
    """

    agent_installe: bool = False
    backend_joignable: bool = False
    mcp_declare: bool = False
    detail: str = ""

    @property
    def pret(self) -> bool:
        return self.agent_installe and self.backend_joignable and self.mcp_declare

    def explication(self) -> str:
        """Ce qu'il faut faire, pas seulement ce qui ne va pas."""
        if self.pret:
            return ""
        manques = []
        if not self.agent_installe:
            manques.append("Hermes Agent n'est pas installé là où on l'attend")
        if not self.mcp_declare:
            manques.append(
                "la configuration de l'agent ne déclare aucun serveur MCP "
                "vers Hermes OS — l'agent démarrera sans outils")
        if not self.backend_joignable:
            manques.append(
                "le backend de Hermes OS ne répond pas ; l'agent le "
                "rappelle par MCP pour obtenir ses outils, et reste bloqué "
                "à créer son environnement quand il ne le trouve pas")
        return " ; ".join(manques) + (f" ({self.detail})" if self.detail else "")


def _racine_hermes() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", "")) / "hermes"


def _mcp_declare(chemin_config: Optional[Path] = None) -> tuple[bool, str]:
    """La configuration de l'agent pointe-t-elle vers Hermes OS ?

    Lue en texte plutôt que via un analyseur YAML : ce module doit pouvoir
    répondre même si la configuration est légèrement malformée, et une
    dépendance de plus pour lire trois lignes serait mal placée.
    """
    config = chemin_config or (_racine_hermes() / "config.yaml")
    try:
        texte = config.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False, f"configuration illisible : {config}"
    if "mcp_servers" not in texte:
        return False, "aucune section mcp_servers"
    return True, ""


def _backend_joignable(url: str) -> tuple[bool, str]:
    try:
        import requests

        reponse = requests.get(url, timeout=DELAI_SONDE_S)
        # N'importe quelle reponse HTTP prouve que quelque chose ecoute.
        # Exiger un 200 rejetterait un backend qui redirige — mesuré, /mcp
        # rend 307.
        return True, f"HTTP {reponse.status_code}"
    except Exception as erreur:  # noqa: BLE001 - toute panne est un « non »
        return False, f"{type(erreur).__name__}"


def verifier(*, url_sante: str = "http://127.0.0.1:8010/health",
             racine_agent: Optional[str] = None,
             chemin_config: Optional[str] = None) -> Prerequis:
    """L'état réel, mesuré. Ne lève jamais."""
    racine = Path(racine_agent) if racine_agent else (
        _racine_hermes() / "hermes-agent")
    agent = (racine / "acp_adapter").is_dir() and \
        (racine / "venv" / "Scripts" / "python.exe").is_file()

    mcp, motif_mcp = _mcp_declare(
        Path(chemin_config) if chemin_config else None)
    backend, motif_backend = _backend_joignable(url_sante)

    details = [m for m in (motif_mcp, motif_backend if not backend else "") if m]
    etat = Prerequis(agent_installe=agent, backend_joignable=backend,
                     mcp_declare=mcp, detail=" / ".join(details))
    if not etat.pret:
        logger.warning("harnais indisponible : %s", etat.explication())
    return etat
