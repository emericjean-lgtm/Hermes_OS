"""Le client de ComfyUI, vu depuis Hermes OS (HOS-190).

## Ce que ce module est

Un client HTTP, et rien d'autre. Il soumet un graphe, suit une file, relit
un historique. Il ne compose pas de graphe, ne choisit pas de modèle et
n'enchaîne pas d'étapes : c'est le travail de Hermes Agent, et la règle qui
prime sur tout dans ce dépôt interdit qu'une seconde boucle agentique
s'installe sur le chemin d'une mission.

## Pourquoi ComfyUI et pas une bibliothèque de diffusion

Parce qu'il est déjà là, monté et éprouvé sur ce matériel — ROCm natif,
`gfx1030`, avec les nœuds d'attention qui contournent l'absence de Flash.
Réimplémenter un pipeline de diffusion pour refaire ce qu'il fait déjà
serait le genre de travail que ce projet évite.

## Ce qui compte vraiment ici

La VRAM. ComfyUI ignore qu'un modèle de langage occupe la carte, et
réciproquement : les deux allouent jusqu'à ce que ROCm complète en mémoire
système, **sans lever d'erreur**. Mesuré le 2026-08-27, attention à 16 384
jetons : 3 226 ms en débordement contre 187 ms sur la carte, soit dix-sept
fois le temps pour un résultat identique.

C'est pourquoi ce client expose `pic_vram_octets()` et pourquoi
`backend/studio/arbitrage.py` existe. Un rendu qui réussit n'est pas un
rendu qui a tenu sur la carte.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Optional
from urllib import error, request

logger = logging.getLogger("hermes_os.studio.comfyui")

#: Au-delà de cette fraction de la VRAM, ROCm complète en mémoire système
#: sans rien dire. Ce n'est pas une marge de confort : c'est le seuil
#: au-dessus duquel un rendu qui « réussit » a en réalité débordé.
SEUIL_DEBORDEMENT = 0.985


@dataclass(frozen=True)
class EtatComfy:
    """Ce que le serveur dit de lui-même."""

    joignable: bool
    version: str = ""
    vram_totale: int = 0
    vram_libre: int = 0
    #: Les drapeaux de lancement. Lus et non supposés : `--use-quad-cross-
    #: attention` décide du pic mémoire, et le vérifier coûte un appel.
    arguments: tuple[str, ...] = ()
    detail: str = ""

    @property
    def attention_sub_quadratique(self) -> bool:
        return "--use-quad-cross-attention" in self.arguments


@dataclass
class Rendu:
    """Le résultat d'une soumission, mesures comprises."""

    identifiant: str
    acheve: bool = False
    duree_s: float = 0.0
    fichiers: list[str] = field(default_factory=list)
    erreur: str = ""
    #: Pic de mémoire GPU **dédiée** relevé sur le processus, en octets.
    #: Zéro quand la mesure n'a pas pu être prise — jamais confondu avec
    #: « n'a rien consommé ».
    pic_vram_octets: int = 0

    def a_deborde(self, vram_totale: int) -> bool:
        """Le rendu est-il passé par la mémoire système ?

        Rend False quand le pic n'a pas pu être mesuré : affirmer
        « n'a pas débordé » sans l'avoir vu serait exactement le genre de
        succès sur parole que ce projet refuse. L'appelant doit tester
        `pic_vram_octets` avant de croire ce booléen.
        """
        if not self.pic_vram_octets or not vram_totale:
            return False
        return self.pic_vram_octets > vram_totale * SEUIL_DEBORDEMENT


class ComfyUI:
    """Le serveur de génération, joignable ou non."""

    def __init__(self, base: str = "http://127.0.0.1:8188",
                 delai: float = 30.0) -> None:
        self.base = base.rstrip("/")
        self.delai = delai

    # ── Transport ────────────────────────────────────────────────────

    def _lire(self, chemin: str, delai: Optional[float] = None) -> Any:
        with request.urlopen(self.base + chemin,
                             timeout=delai or self.delai) as r:
            return json.loads(r.read().decode("utf-8"))

    def _poster(self, chemin: str, corps: dict) -> Any:
        req = request.Request(
            self.base + chemin, data=json.dumps(corps).encode("utf-8"),
            headers={"Content-Type": "application/json"})
        with request.urlopen(req, timeout=self.delai) as r:
            return json.loads(r.read().decode("utf-8"))

    # ── État ─────────────────────────────────────────────────────────

    def etat(self) -> EtatComfy:
        """Joignable, et dans quelle configuration.

        Ne lève pas : un Studio Center doit pouvoir afficher « ComfyUI
        n'est pas démarré » plutôt que planter, exactement comme le
        Runtime Center le fait pour Ollama.
        """
        try:
            d = self._lire("/system_stats", delai=8)
        except (error.URLError, OSError, ValueError) as e:
            return EtatComfy(joignable=False, detail=str(e)[:160])

        systeme = d.get("system") or {}
        appareils = d.get("devices") or [{}]
        premier = appareils[0]
        return EtatComfy(
            joignable=True,
            version=str(systeme.get("comfyui_version") or ""),
            vram_totale=int(premier.get("vram_total") or 0),
            vram_libre=int(premier.get("vram_free") or 0),
            arguments=tuple(str(a) for a in (systeme.get("argv") or [])),
        )

    def dossier_sortie(self) -> str:
        """Où ComfyUI écrit réellement, ou "" si on ne peut pas le savoir.

        Lu dans les arguments de lancement et non supposé : ce serveur
        écrit sur `E:` par `--output-directory`, et supposer
        `<comfy>/output` renverrait un chemin qui existe mais où rien
        n'arrive jamais — la pire des deux erreurs possibles.
        """
        args = self.etat().arguments
        try:
            return str(args[args.index("--output-directory") + 1])
        except (ValueError, IndexError):
            return ""

    def modeles(self, genre: str) -> list[str]:
        """Les fichiers qu'un chargeur voit, par genre.

        `genre` est le nom du champ dans le schéma du nœud —
        `unet_name`, `clip_name`, `vae_name`. Sert au Studio Center pour
        proposer ce qui existe au lieu d'un champ libre où l'on se
        trompe de nom.
        """
        noeuds = {
            "unet_name": "UnetLoaderGGUF",
            "clip_name": "CLIPLoaderGGUF",
            "vae_name": "VAELoader",
        }
        noeud = noeuds.get(genre)
        if not noeud:
            return []
        try:
            d = self._lire(f"/object_info/{noeud}", delai=15)
            champ = list(d.values())[0]["input"]["required"][genre][0]
            return [str(x) for x in champ] if isinstance(champ, list) else []
        except Exception:
            logger.debug("schéma %s illisible", noeud, exc_info=True)
            return []

    def file(self) -> dict[str, int]:
        try:
            d = self._lire("/queue", delai=10)
            return {
                "en_cours": len(d.get("queue_running") or []),
                "en_attente": len(d.get("queue_pending") or []),
            }
        except Exception:
            return {"en_cours": 0, "en_attente": 0}

    # ── Soumission ───────────────────────────────────────────────────

    def soumettre(self, graphe: dict) -> str:
        """Déposer un graphe et rendre son identifiant.

        Lève sur refus, en portant le message du serveur : un graphe mal
        formé produit une explication précise que l'appelant doit voir,
        pas un identifiant vide qu'il croira valide.
        """
        try:
            rep = self._poster("/prompt", {"prompt": graphe})
        except error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:800]
            raise ValueError(f"graphe refusé : {detail}") from e

        identifiant = rep.get("prompt_id")
        if not identifiant:
            raise ValueError(f"pas d'identifiant rendu : {json.dumps(rep)[:300]}")
        return str(identifiant)

    def attendre(self, identifiant: str, *, minutes: float = 45.0,
                 periode: float = 5.0,
                 sonde_vram=None) -> Rendu:
        """Suivre un rendu jusqu'à son terme.

        `sonde_vram` est appelée à chaque tour et doit rendre les octets
        de mémoire GPU dédiée du processus, ou None. Elle est injectée
        plutôt que codée ici parce qu'elle est propre à Windows, et
        qu'un test doit pouvoir la remplacer.
        """
        t0 = time.time()
        rendu = Rendu(identifiant=identifiant)
        limite = t0 + minutes * 60
        # Lu une fois, avant la boucle : c'est un appel HTTP, et il ne
        # change pas pendant un rendu.
        racine = self.dossier_sortie()

        while time.time() < limite:
            if sonde_vram is not None:
                v = sonde_vram()
                if v:
                    rendu.pic_vram_octets = max(rendu.pic_vram_octets, int(v))

            time.sleep(periode)
            try:
                hist = self._lire(f"/history/{identifiant}", delai=15)
            except Exception:
                continue

            entree = hist.get(identifiant)
            if not entree:
                continue
            etat = entree.get("status") or {}
            if etat.get("completed"):
                rendu.acheve = True
                rendu.fichiers = _fichiers_de(entree, racine)
                break
            if etat.get("status_str") == "error":
                rendu.erreur = _erreur_de(etat)
                break

        rendu.duree_s = round(time.time() - t0, 1)
        if not rendu.acheve and not rendu.erreur:
            rendu.erreur = f"non achevé après {minutes:.0f} min"
        return rendu

    def interrompre(self) -> bool:
        try:
            self._poster("/interrupt", {})
            return True
        except Exception:
            return False


def _erreur_de(etat: dict) -> str:
    """Le message d'erreur de ComfyUI, et le nœud qui l'a levé.

    La première version sérialisait `messages` entier et le coupait à
    600 caractères. Or ce tableau commence par `execution_start` et
    `execution_cached` : la coupe tombait donc **avant**
    `exception_message`, et l'appelant lisait un horodatage là où
    ComfyUI disait « CUDA out of memory ... VAEDecode ». Le journal
    portait la réponse et la rendait illisible.
    """
    for entree in (etat.get("messages") or []):
        if not (isinstance(entree, (list, tuple)) and len(entree) == 2):
            continue
        nom, corps = entree
        if nom != "execution_error" or not isinstance(corps, dict):
            continue
        noeud = corps.get("node_type") or "?"
        rang = corps.get("node_id")
        message = str(corps.get("exception_message") or "").strip()
        return f"{noeud}#{rang} : {message}"[:900]
    return json.dumps(etat)[:600]


def pid_du_serveur(port: int = 8188) -> Optional[int]:
    """Le processus qui sert ComfyUI, ou None.

    Cherché par le **port qu'il écoute** et non par son nom d'image : le
    serveur tourne sous `python.exe`, comme cinq autres processus de cette
    machine. C'est la leçon du compteur GPU, qui nomme ses instances par
    pid parce qu'un nom d'image ne distingue rien.

    `/system_stats` ne le donne pas — vérifié, la clé n'existe pas. Le
    port, lui, désigne sans ambiguïté celui qui répond aux requêtes, ce
    qu'une correspondance sur la ligne de commande ne garantit pas.

    Une seule implémentation, appelée par les routes comme par la file de
    nuit : deux lectures du même fait finissent par diverger, et celle qui
    se trompe est toujours celle qu'on ne regarde pas.
    """
    if not sys.platform.startswith("win"):
        return None
    script = (f"(Get-NetTCPConnection -LocalPort {int(port)} -State Listen"
              " -ErrorAction SilentlyContinue | Select-Object -First 1)"
              ".OwningProcess")
    try:
        sortie = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, text=True, timeout=20,
        ).stdout.strip()
        return int(sortie) if sortie.isdigit() else None
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def _fichiers_de(entree: dict, racine: str = "") -> list[str]:
    """Les fichiers produits, tous nœuds de sortie confondus.

    Chemins **absolus** quand `racine` est donnée. L'historique de ComfyUI
    ne rend que `{filename, subfolder, type}` — trois morceaux dont aucun
    ne désigne un fichier ouvrable. La première version ne gardait que
    `filename`, et le relecteur recevait donc `rue_sodium_00001_.mp4` :
    aucune image n'en sortait, et le plan finissait `indetermine` alors
    que le rendu était bon.

    Ce défaut-là n'a rien cassé — c'est ce qui le rend intéressant. La
    file a dit « je n'ai pas pu vérifier » au lieu de « c'est réussi »,
    ce qui est exactement le comportement voulu, et c'est pourquoi il
    fallait lire le rapport pour le voir.
    """
    fichiers: list[str] = []
    for sortie in (entree.get("outputs") or {}).values():
        for lot in sortie.values():
            if not isinstance(lot, list):
                continue
            for element in lot:
                if not isinstance(element, dict) or not element.get("filename"):
                    continue
                morceaux = [racine] if racine else []
                if element.get("subfolder"):
                    morceaux.append(str(element["subfolder"]))
                morceaux.append(str(element["filename"]))
                fichiers.append(os.path.join(*morceaux) if len(morceaux) > 1
                                else morceaux[0])
    return fichiers
