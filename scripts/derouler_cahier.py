"""Derouler un cahier des charges section par section (HOS-127).

    # 1. proposer le plan (n'execute rien)
    .venv/Scripts/python.exe scripts/derouler_cahier.py "C:/chemin/du/projet"

    # 2. relire et corriger .hermes/plan.md

    # 3. lancer
    .venv/Scripts/python.exe scripts/derouler_cahier.py "C:/chemin/du/projet" --lancer

Le premier appel ecrit le plan et s'arrete : le classement automatique se
trompe — mesure a ~30 % sur un cahier reel — et derouler quarante missions
sur un classement que personne n'a regarde ferait sauter un quart du
cahier en silence.

Compter environ dix minutes par section cochee.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))


def main() -> int:
    analyseur = argparse.ArgumentParser(description=__doc__)
    analyseur.add_argument("projet", help="dossier du projet")
    analyseur.add_argument("--cahier", default="PROJECT_SPEC.md")
    analyseur.add_argument("--lancer", action="store_true",
                           help="executer le plan au lieu de le proposer")
    args = analyseur.parse_args()

    projet = Path(args.projet).expanduser().resolve()
    cahier = projet / args.cahier
    if not cahier.is_file():
        print(f"cahier introuvable : {cahier}")
        return 2

    from backend.mission.programme import (
        CHEMIN_PLAN, bilan, bloc_de_regles, brief_de_section, classer,
        decouper, derouler, ecrire_plan, ecrire_proteges, lire_plan,
    )
    from backend.mission.pile import contrainte as contrainte_de_pile

    sections = decouper(cahier.read_text(encoding="utf-8"))
    proposees, regles = classer(sections)
    chemin_plan = projet / CHEMIN_PLAN

    cochees = lire_plan(chemin_plan)
    if cochees is None:
        ecrire_plan(chemin_plan, sections, proposees)
        proteges = ecrire_proteges(
            projet, [args.cahier, "AGENT.md", "AGENTS.md",
                     "PROJECT_STATUS.md"])
        print(f"documents proteges : {len(proteges.splitlines()) - 4} declares")
        print(f"{len(sections)} sections trouvees, {len(proposees)} proposees.")
        print(f"\nPlan ecrit : {chemin_plan}")
        print("Relis-le, corrige les cases, puis relance avec --lancer.")
        return 0

    a_faire = [s for s in sections if s.numero in cochees]
    hors_plan = [s for s in sections if s.numero not in cochees]
    bloc = bloc_de_regles(hors_plan)
    print(f"plan relu : {len(a_faire)} sections a construire, "
          f"{len(hors_plan)} en regles permanentes")
    if not args.lancer:
        for s in a_faire:
            print(f"  §{s.numero:<3d} {s.titre}")
        print("\nRelance avec --lancer pour executer.")
        return 0

    # Sans ca, Aegis refuse le dossier, chaque objectif rend
    # `status: failed` avec un rapport vide, et la file compte 26 sections
    # "faites" en zero seconde sur un disque vide (HOS-128). Pose avant le
    # bootstrap : la whitelist est lue a la construction.
    os.environ.setdefault("ALLOWED_PATHS", str(projet))
    print(f"workspace autorise : {projet}")

    from backend.core.bootstrap.bootstrap import HermesBootstrap

    boot = HermesBootstrap()
    boot.build()
    moteur = boot.container.get("autonomous_engine")
    depart = time.monotonic()

    def lancer(section):
        print(f"\n=== §{section.numero} {section.titre} ===", flush=True)
        # Relue a chaque section : la pile du projet peut naitre a la
        # troisieme section et doit contraindre la quatrieme.
        objectif = brief_de_section(section, nom_du_cahier=args.cahier,
                                    regles=bloc, racine=str(projet),
                                    pile=contrainte_de_pile(str(projet)))
        goal = moteur.start_goal(objectif, {"local_path": str(projet)})
        rapport = moteur.get_report(goal.get("goal_id", "")) or {}
        # Le statut de l'objectif voyage avec le rapport : un objectif qui
        # refuse de demarrer rend un rapport vide, indiscernable d'une
        # mission sans workspace si on ne le porte pas.
        return {**rapport, "statut_objectif": goal.get("status")}

    def tracer(etape):
        print(f"  -> {etape.statut}  ({etape.qualite or 'sans verdict'})"
              + (f"  {etape.detail}" if etape.detail else ""), flush=True)

    etapes = derouler(a_faire, lancer=lancer, on_etape=tracer)
    resultat = bilan(etapes)
    resultat["duree_reelle_s"] = round(time.monotonic() - depart)

    destination = projet / ".hermes" / "bilan.json"
    destination.write_text(json.dumps(resultat, ensure_ascii=False, indent=2),
                           encoding="utf-8")
    print(f"\n{'=' * 60}")
    print(json.dumps(resultat["par_statut"], ensure_ascii=False))
    if resultat["arret"]:
        print(f"ARRET a {resultat['arret']['section']} : {resultat['arret']['raison']}")
    print(f"duree : {resultat['duree_reelle_s']}s | bilan : {destination}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
