"""Donner — ou refuser — un verdict agentique aux modeles du catalogue.

    .venv/Scripts/python.exe scripts/sonder_modeles.py ornith-9b-256k
    .venv/Scripts/python.exe scripts/sonder_modeles.py --catalogue

## Pourquoi cet outil existe

`agentic_probe.probe()` mesure, mais **ne persiste rien** : jusqu'a HOS-142,
`save_result()` n'etait appele que par les tests. Un verdict etait donc
perdu aussitot obtenu, et le magasin ne pouvait se remplir que par un script
ad hoc que personne n'avait garde.

Consequence, mesuree le 2026-08-21 : le magasin ne contenait plus que des
**tags morts** — `lfm2.5-2.6b-128k`, `qwen3.5:9b-128k`, `gemma4:12b-64k`.
La refonte du catalogue (HOS-104 a HOS-109) avait renomme les modeles, et
aucune mesure ne portait plus un nom existant.

Or `ModelProfile.agentic_capable` traite un modele non mesure comme **non
prouve**, deliberement (HOS-096) : deviner s'etait revele faux une fois sur
deux. Tous les modeles du catalogue etaient donc juges incapables, et
`_agentic_model` substituait systematiquement le repli de 2,6 Md — note
`code 28`, le plus faible du catalogue — quel que soit le choix du routeur.

Une campagne entiere tournait ainsi sur le plus petit modele disponible.
C'est tres probablement ce qui plafonnait les deroules de cahier a 4,4
sections de profondeur moyenne.

## Ce que la sonde fait, et ce qu'elle ne fait pas

Elle execute une **vraie tache agentique** par l'agent installe, le long du
chemin qu'une mission emprunte, et lit le verdict sur le disque. Un succes
signifie que ce chemin-la fonctionne, pas qu'un harnais simplifie
fonctionne.

Trois essais au minimum, et c'est un choix paye : le succes agentique n'est
pas deterministe sur ce materiel — le meme modele et le meme prompt donnent
deux outils appeles en 45 s, ou aucun en 305 s. Un essai unique promeut un
narrateur au rang de cerveau de mission.

**Un modele a la fois.** La sonde prend un verrou exclusif : sur 16 Go de
VRAM, deux mesures simultanees mesurent la contention, pas les modeles.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.model_intelligence.agentic_probe import (  # noqa: E402
    load_results,
    measured_success_for,
    probe,
    save_result,
)

#: Assez pour qu'un aleas ne decide pas, assez peu pour qu'une campagne de
#: verification tienne dans une pause. `measured_success_for` exige de toute
#: facon une majorite, pas l'unanimite.
ESSAIS_PAR_DEFAUT = 3


def _modeles_du_catalogue() -> list[str]:
    """Les modeles reellement affectes a un role, sans doublon.

    Lus depuis `config/models.yaml` : c'est lui qui decide quels modeles le
    routeur peut choisir, donc les seuls dont le verdict change quelque
    chose.
    """
    from backend.core.config import load_models_config

    vus: list[str] = []
    for spec in (load_models_config().get("roles") or {}).values():
        nom = str(spec.get("model") or "").strip()
        if nom and nom not in vus:
            vus.append(nom)
    return vus


def sonder(modele: str, essais: int) -> tuple[int, int]:
    """Sonde `modele` et **enregistre** chaque essai. Rend (succes, essais)."""
    print(f"\n=== {modele} ===", flush=True)
    print(f"  verdict avant : {measured_success_for(modele)}", flush=True)
    succes = 0
    for n in range(1, essais + 1):
        depart = time.monotonic()
        try:
            resultat = probe(modele)
        except Exception as erreur:  # noqa: BLE001 - un echec EST une mesure
            print(f"  essai {n}/{essais} : sonde impossible "
                  f"({type(erreur).__name__}: {erreur})", flush=True)
            continue
        # L'enregistrement est le point de tout l'exercice : sans lui, le
        # verdict meurt avec le processus.
        save_result(resultat)
        succes += bool(resultat.success)
        print(f"  essai {n}/{essais} : {resultat.success} "
              f"en {time.monotonic() - depart:.0f}s", flush=True)
    print(f"  verdict apres : {measured_success_for(modele)}", flush=True)
    return succes, essais


def main() -> int:
    analyseur = argparse.ArgumentParser(description=__doc__)
    analyseur.add_argument("modeles", nargs="*",
                           help="tags a sonder ; vide avec --catalogue")
    analyseur.add_argument("--catalogue", action="store_true",
                           help="sonder tous les modeles affectes a un role")
    analyseur.add_argument("--essais", type=int, default=ESSAIS_PAR_DEFAUT)
    args = analyseur.parse_args()

    modeles = list(args.modeles)
    if args.catalogue:
        modeles = [m for m in _modeles_du_catalogue() if m not in modeles] + modeles
    if not modeles:
        analyseur.error("nommer au moins un modele, ou passer --catalogue")

    print(f"{len(modeles)} modele(s), {args.essais} essais chacun, "
          f"un a la fois (verrou exclusif)")
    for modele in modeles:
        sonder(modele, args.essais)

    print("\n=== MAGASIN ===")
    for nom, entree in sorted(load_results().items()):
        taux = entree.get("success_rate")
        print(f"  {nom:24} {entree.get('successes', 0)}/{entree.get('trials', 0)}"
              + (f"  ({taux:.0%})" if isinstance(taux, (int, float)) else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
