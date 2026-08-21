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


def verifier_le_harnais(*, accepte_le_mode_jetable: bool) -> bool:
    """Refuse de partir si le harnais ne servira pas — sauf accord explicite.

    Ce script construit ses services **en memoire** ; il ne sert aucun HTTP.
    Or l'agent rappelle Hermes OS par MCP pour obtenir ses outils : sans un
    backend qui ecoute, il demarre avec zero outil, et chaque tache retombe
    sur un agent jete apres usage — donc amnesique.

    Une nuit entiere dans cet etat est le pire resultat possible. Elle ne
    produit pas une erreur : elle produit un bilan **de meme forme** qu'une
    nuit reussie, ou chaque section a redecouvert le workspace. C'est
    exactement la classe de defaut que ce depot traque depuis HOS-128 — une
    mission qui n'a pas eu lieu n'est pas une mission sans mesure.

    D'ou ce refus. Soit la nuit tourne avec le harnais, soit elle ne tourne
    pas ; jamais une nuit qui croit l'avoir et ne l'a pas. `--sans-harnais`
    reste ouvert pour qui veut comparer les deux modes, et il faut alors
    l'ecrire.
    """
    from backend.ral.adapters.prerequis_harnais import verifier

    etat = verifier()
    if etat.pret:
        print("harnais : pret (session d'agent tenue ouverte par projet)")
        return True

    print(f"\nHARNAIS INDISPONIBLE : {etat.explication()}")
    if accepte_le_mode_jetable:
        print("--sans-harnais : on part quand meme, un agent par tache,")
        print("sans memoire d'une section a l'autre.")
        return True

    print("\nLa nuit tournerait en mode jetable : un agent neuf par tache,")
    print("qui redecouvre le workspace a chaque fois. Le bilan aurait la")
    print("meme forme qu'une nuit reussie — c'est pourquoi on s'arrete ici.")
    if not etat.backend_joignable:
        print("\nDemarre le backend, puis relance :")
        print("  .venv/Scripts/python.exe -m uvicorn backend.main:app "
              "--host 127.0.0.1 --port 8010")
    print("\nOu assume le mode degrade avec --sans-harnais.")
    return False


def main() -> int:
    analyseur = argparse.ArgumentParser(description=__doc__)
    analyseur.add_argument("projet", help="dossier du projet")
    analyseur.add_argument("--cahier", default="PROJECT_SPEC.md")
    analyseur.add_argument("--sans-harnais", action="store_true",
                           help="accepter de tourner en mode jetable, un "
                                "agent amnesique par tache")
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

    if not verifier_le_harnais(accepte_le_mode_jetable=args.sans_harnais):
        return 2

    from backend.core.bootstrap.bootstrap import HermesBootstrap  # noqa: E402

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

    def reparer(section, diagnostic):
        # Seconde passe : on ne redemande pas le travail, on demande la
        # correction. Le diagnostic porte la sortie reelle des tests, les
        # livrables manquants et les boucles d'import — sans quoi la passe
        # repart aussi aveugle que la premiere (HOS-136).
        print(f"  ... reparation de §{section.numero}", flush=True)
        objectif = brief_de_section(section, nom_du_cahier=args.cahier,
                                    regles=bloc, racine=str(projet),
                                    pile=contrainte_de_pile(str(projet)))
        objectif += "\n\n" + diagnostic
        goal = moteur.start_goal(objectif, {"local_path": str(projet)})
        rapport = moteur.get_report(goal.get("goal_id", "")) or {}
        return {**rapport, "statut_objectif": goal.get("status")}

    def fermer_la_session_de_campagne():
        try:
            import asyncio

            from backend.projects.store import get_project_store
            from backend.ral.adapters.sessions_de_mission import registre

            projet_enregistre = get_project_store().ensure_for_path(str(projet))
            if projet_enregistre is None:
                return
            asyncio.run(registre().fermer_projet(projet_enregistre.id))
        except Exception:
            # Une session qui survit quelques minutes de trop ne justifie
            # pas de faire echouer un cahier qui vient d'aboutir.
            pass

    def tracer(etape):
        print(f"  -> {etape.statut} (passe {etape.passes})  ({etape.qualite or 'sans verdict'})"
              + (f"  {etape.detail}" if etape.detail else ""), flush=True)

    etapes = derouler(a_faire, lancer=lancer, reparer=reparer,
                      on_etape=tracer, max_passes=2)
    # La session du harnais traverse volontairement les sections — c'est ce
    # qui donne a la section 4 ce qu'a fait la section 3. Elle ne se ferme
    # donc a aucune fin de mission : sans ce point de sortie, elle
    # attendrait sa purge d'inactivite, une demi-heure apres le dernier
    # travail utile.
    fermer_la_session_de_campagne()

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
