"""Qui occupe la carte, et à quel moment (HOS-190).

## Le défaut que ce module empêche

Les 16 Gio de la RX 6800 sont indivisibles. Ollama tenant gpt-oss-20b
occupe 13,21 Gio — mesuré sur le processus, et non les 9,55 Gio que
`/api/ps` annonce, qui ne compte que les poids. Un rendu LTX-2.5 en
réclame 7,75 au pic. **Ils ne peuvent pas coexister.**

Ce chiffre de 7,75 est mesuré, et il a remplacé un raisonnement faux. La
première version de ce module comptait le **poids du fichier** — 10,73 Gio
en Q3_K_M — en supposant que les poids résident sur la carte. Ils n'y
résident pas : `--cache-none` et `--disable-smart-memory` font que ComfyUI
les diffuse depuis la RAM, et trois quantifications de 10,7 à 17,4 Go ont
donné le même pic à deux centièmes près. La conclusion tenait quand même,
mais pour la mauvaise raison — et une raison fausse se propage.

Et rien ne le dit. ROCm ne lève pas quand une allocation dépasse la VRAM :
il complète en mémoire système. Mesuré le 2026-08-27 sur l'attention à
16 384 jetons — 3 226 ms en débordement contre 187 ms sur la carte, pour un
résultat identique. Dix-sept fois le temps, aucune erreur, aucun journal.

Un rendu lancé pendant qu'une mission tourne ne produit donc pas un échec :
il produit une lenteur que personne n'attribue à la bonne cause. C'est
exactement la forme de défaut que ce dépôt passe son temps à défaire.

## Ce que ce module fait

Un verrou, un déchargement, et une vérification.

Le troisième est le seul qui compte vraiment. Décharger et *croire* que la
VRAM est libre serait reproduire l'erreur d'un cran plus haut : Ollama rend
`success: true` dès que la requête aboutit, pas quand la mémoire est
effectivement rendue. On relit donc le compteur.
"""

from __future__ import annotations

import logging
import subprocess
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Callable, Iterator, Optional

logger = logging.getLogger("hermes_os.studio.arbitrage")

#: Un seul locataire lourd à la fois. Le verrou est un objet de processus :
#: il protège contre deux rendus concurrents et contre un rendu lancé
#: pendant qu'une mission tient la carte, dans ce processus. Un script
#: lancé à côté n'est pas couvert — comme le registre de sessions ACP, et
#: pour la même raison, que `system.py` documente déjà.
_VERROU = threading.Lock()

#: Ce qu'un rendu prend réellement sur la carte, plus une marge.
#:
#: Défini **ici** et nulle part ailleurs. Il a d'abord existé en quatre
#: exemplaires — routes, file de nuit, atelier, outil MCP — et quatre
#: copies d'un même chiffre finissent par diverger ; celle qui se trompe
#: est toujours celle qu'on ne regarde pas.
#:
#: La valeur d'origine, 11,5 Gio, était le poids du fichier Q3_K_M. Le
#: raisonnement était faux : ComfyUI **diffuse** les couches depuis la RAM
#: (`--cache-none`, `--disable-smart-memory`), et le pic ne dépend donc pas
#: de la quantification. Mesuré le 2026-08-27 sur trois quantifications de
#: 10,7 à 17,4 Go : 7,59 / 7,61 / 7,59 Gio, et 7,75 sur les rendus de nuit.
#:
#: Réserver 11,5 quand il en faut 7,8 n'est pas prudent — c'est faux dans
#: l'autre sens, et la file refuserait des rendus qui tiendraient. C'est le
#: faux échec que ce dépôt traque autant que le faux succès.
BESOIN_RENDU_OCTETS = 9_663_676_416


@dataclass
class Occupation:
    """Ce qui a été libéré, et ce que la carte porte encore."""

    obtenu: bool
    modeles_decharges: list[str] = field(default_factory=list)
    vram_avant: int = 0
    vram_apres: int = 0
    #: Vrai quand le déchargement a été demandé mais que la VRAM n'a pas
    #: baissé. L'appelant doit alors renoncer plutôt que de rendre : le
    #: rendu déborderait, sans le dire.
    liberation_douteuse: bool = False
    detail: str = ""

    @property
    def libere_octets(self) -> int:
        """Ce que le déchargement a rendu, en octets.

        `vram_avant` et `vram_apres` portent la VRAM **libre** : elle
        augmente quand on décharge. La première version soustrayait dans
        l'autre sens et rendait donc toujours zéro — un chiffre qui
        n'aurait jamais alerté personne, puisqu'il ressemble à « rien
        n'a été libéré », un état plausible.
        """
        return max(0, self.vram_apres - self.vram_avant)


def vram_libre_octets(sonde: Optional[Callable[[], int]] = None) -> int:
    """La VRAM libre, en octets, ou 0 si la mesure échoue.

    Zéro signifie « non mesuré », pas « rien de libre ». Les appelants
    doivent traiter les deux différemment — c'est la même règle que pour
    un axe non mesuré dans le catalogue de modèles.
    """
    if sonde is not None:
        try:
            return int(sonde())
        except Exception:
            return 0
    try:
        import torch

        if torch.cuda.is_available():
            libre, _ = torch.cuda.mem_get_info()
            return int(libre)
    except Exception:
        logger.debug("torch indisponible pour la sonde VRAM", exc_info=True)
    return 0


def modeles_ollama_residents(sonde: Optional[Callable[[], list[str]]] = None) -> list[str]:
    """Les modèles qu'Ollama tient en ce moment.

    Lus depuis `/api/ps`, qui ne rapporte que les poids — ce qui suffit
    ici : on veut savoir *quoi* décharger, pas combien cela pèse.
    """
    if sonde is not None:
        try:
            return list(sonde())
        except Exception:
            return []
    try:
        import requests

        from backend.core.config import get_settings

        url = get_settings().ollama_api_url.rstrip("/")
        d = requests.get(f"{url}/api/ps", timeout=10).json()
        return [str(m.get("name") or m.get("model") or "")
                for m in (d.get("models") or []) if m.get("name") or m.get("model")]
    except Exception:
        logger.debug("Ollama injoignable pour /api/ps", exc_info=True)
        return []


def decharger(modele: str) -> bool:
    """Rendre la VRAM d'un modèle résident. Best-effort.

    `keep_alive: 0` est le signal documenté d'Ollama. Le succès de la
    requête ne prouve rien sur la mémoire : c'est l'appelant qui vérifie.
    """
    try:
        import requests

        from backend.core.config import get_settings

        url = get_settings().ollama_api_url.rstrip("/")
        r = requests.post(f"{url}/api/generate",
                          json={"model": modele, "keep_alive": 0}, timeout=30)
        return r.ok
    except Exception:
        logger.debug("déchargement de %s impossible", modele, exc_info=True)
        return False


@contextmanager
def carte_reservee(
    besoin_octets: int,
    *,
    attente_max_s: float = 0.0,
    sonde_vram: Optional[Callable[[], int]] = None,
    sonde_residents: Optional[Callable[[], list[str]]] = None,
    decharge: Optional[Callable[[str], bool]] = None,
    pause_s: float = 2.0,
) -> Iterator[Occupation]:
    """Réserver la carte pour un travail lourd, et la rendre après.

    Les quatre sondes sont injectables pour que les tests n'aient besoin
    ni d'Ollama, ni d'un GPU — et pour que le comportement en cas de
    déchargement inefficace soit éprouvable, ce qui est le cas qui compte.

    `attente_max_s` à zéro signifie « ne pas attendre » : si un autre
    travail lourd tient le verrou, on renonce immédiatement plutôt que de
    faire patienter une requête d'interface. Un appelant de fond passe une
    valeur.
    """
    obtenu = _VERROU.acquire(timeout=attente_max_s) if attente_max_s > 0 \
        else _VERROU.acquire(blocking=False)

    if not obtenu:
        yield Occupation(obtenu=False, detail="la carte est déjà réservée")
        return

    occupation = Occupation(obtenu=True)
    try:
        occupation.vram_avant = vram_libre_octets(sonde_vram)

        if occupation.vram_avant and occupation.vram_avant < besoin_octets:
            liberer = decharge or decharger
            for modele in modeles_ollama_residents(sonde_residents):
                if liberer(modele):
                    occupation.modeles_decharges.append(modele)

            if occupation.modeles_decharges:
                # Ollama rend la main avant que le pilote n'ait rendu la
                # memoire. Sans cette pause, la verification ci-dessous
                # lirait l'etat d'avant et conclurait a un echec.
                time.sleep(pause_s)

        occupation.vram_apres = vram_libre_octets(sonde_vram)

        if occupation.vram_apres and occupation.vram_apres < besoin_octets:
            occupation.liberation_douteuse = True
            occupation.detail = (
                f"{occupation.vram_apres / 2**30:.2f} Gio libres après "
                f"déchargement, {besoin_octets / 2**30:.2f} demandés"
            )
            logger.warning(
                "VRAM insuffisante après déchargement : %s. Un rendu lancé "
                "malgré cela déborderait en mémoire système sans lever "
                "d'erreur.", occupation.detail,
            )

        yield occupation
    finally:
        _VERROU.release()


def pic_gpu_du_processus(pid: int) -> Optional[int]:
    """Mémoire GPU dédiée détenue par un processus, en octets.

    Windows seulement, et au mieux. Le compteur nomme ses instances par
    pid — jamais par nom d'image — et une correspondance sur le nom ne
    trouve rien tout en rapportant « non mesurable » : c'est ainsi que la
    première version de cette méthode a échoué dans ce dépôt, côté
    `model_bench.py`.
    """
    script = (
        "(Get-Counter '\\GPU Process Memory(*)\\Dedicated Usage'"
        " -ErrorAction SilentlyContinue).CounterSamples |"
        f" Where-Object {{ $_.InstanceName -like 'pid_{pid}_*' }} |"
        " Measure-Object CookedValue -Sum |"
        " ForEach-Object { [long]$_.Sum }"
    )
    try:
        sortie = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, text=True, timeout=40,
        ).stdout.strip()
        return int(sortie) if sortie.isdigit() and int(sortie) > 0 else None
    except Exception:
        return None
