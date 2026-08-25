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
import io
import json
import os
import sys
import time
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))


def ouvrir_le_journal() -> None:
    """Fait remonter les decisions de Hermes OS sur la sortie d'erreur.

    Sans cela, une nuit de huit heures laisse un fichier d'erreur de six
    lignes : trois avertissements de demarrage et deux constats de mission
    « reported success but no file was created ». Rien sur **pourquoi**.

    Mesure du 2026-08-21 : une section a echoue trois fois de suite sans
    qu'aucune trace ne dise si le harnais avait servi, quel modele avait
    ete retenu, ni si un tour avait abouti. Le diagnostic a demande de
    compter des processus a la main, dehors, pendant que la campagne
    tournait — une donnee qu'aucun rapport ne porte et qui disparait a la
    seconde ou le processus meurt.

    Les journaux nommes ici sont ceux qui portent une **decision** : quel
    modele, quel runtime, harnais ou mode jetable, tour abouti ou non. Pas
    le detail des requetes, qui noierait le reste.
    """
    import logging

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )
    for nom in ("hermes_os.execution.task", "hermes_os.ral.acp",
                "hermes_os.ral.sessions", "hermes_os.ral.prerequis",
                "hermes_os.mission.graph_executor"):
        logging.getLogger(nom).setLevel(logging.INFO)
    # Ceux-la parlent a chaque requete HTTP et enterreraient le reste.
    for bruyant in ("httpx", "httpcore", "urllib3", "asyncio"):
        logging.getLogger(bruyant).setLevel(logging.WARNING)


class HarnaisPerdu(RuntimeError):
    """Le harnais a disparu **pendant** la campagne.

    ## L'incident

    Le 2026-08-24 a 22:00, le backend de Hermes OS s'est arrete au milieu
    d'un cahier. L'agent tire ses outils de Hermes OS par MCP : sans
    backend, il demarre avec zero outil. Le journal l'a dit a chaque tache
    qui a suivi —

        harnais indisponible : le backend de Hermes OS ne repond pas
        harnais ecarte

    — et **la file a continue**. §21 a consomme ses deux passes avec un
    agent jete apres usage, donc amnesique, puis s'est declaree bloquee sur
    des tests en echec. Le diagnostic evident etait « le code de RiskModel
    est faux » ; le vrai etait « le cerveau avait disparu depuis quatre
    heures ».

    ## Pourquoi le controle de demarrage ne suffisait pas

    `verifier_le_harnais` refuse de partir sans harnais depuis HOS-128, et
    ce refus a bien joue : la relance du lendemain s'est arretee net. Mais
    il ne s'execute qu'une fois. Un cahier de quinze heures traverse
    forcement un redemarrage, une mise a jour ou une coupure, et il n'avait
    aucun moyen de s'en apercevoir.

    C'est la meme regle que `test_hermes_agent_is_the_brain` garde dans le
    code, appliquee cette fois a la duree d'une campagne : Hermes Agent est
    le cerveau des missions, et une section sans lui n'est pas une section
    ratee — c'est une section qui n'a pas eu lieu.
    """


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


#: Les verdicts qui valent « cette section est derriere nous ».
#:
#: `reparee` manquait : §11 avait ete declaree `reparee (passe 2)
#: (verifiee)` avec vingt-cinq tests verts, et la reprise suivante l'a
#: relancee de zero. C'est le cas le plus couteux a perdre, puisque c'est
#: le seul ou la file a du s'y reprendre a deux fois pour aboutir.
ABOUTIS = ("-> faite", "-> reparee")

#: Le releve durable des sections menees a bien.
ACQUIS = "faites.txt"


def sections_deja_faites(dossier_hermes) -> set[int]:
    """Les numeros de section deja menees a bien, lus dans le journal.

    ## Pourquoi lire le journal plutot que tenir un fichier d'etat

    Une campagne dure quinze heures. Elle traverse forcement un besoin de
    la machine — liberer la carte graphique, redemarrer, simplement
    dormir — et jusqu'ici la seule facon d'arreter etait de tout perdre :
    le plan coche les sections **a traiter**, il ne dit pas lesquelles sont
    faites, et une relance repartait de §1.

    Le journal, lui, est deja ecrit au fil de l'eau, une ligne par section
    et par verdict. Le lire plutot que d'inventer un fichier d'etat a une
    consequence qui vaut la contrainte de format : **la reprise fonctionne
    sur les campagnes lancees avant qu'elle n'existe**, y compris celle qui
    tourne au moment ou ces lignes sont ecrites. Un fichier d'etat aurait
    demande d'avoir prevu.

    Deux verdicts sont retenus, `faite` et `reparee`. Le second manquait, et
    §11 en a fait les frais : declaree `reparee (passe 2) (verifiee)` avec
    vingt-cinq tests verts, elle est repartie de zero a la reprise suivante.
    Une section reparee **est** une section faite — c'est meme le seul cas
    ou la file a fourni un effort supplementaire pour y arriver, et le
    perdre est le plus couteux de tous.

    `bloquee` et `signalee` sont rejouees. La premiere a consomme ses deux
    passes sans aboutir ; la seconde a rendu un travail que la mesure
    contredit. Les sauter reviendrait a faire passer un echec pour un
    travail fini, ce que ce projet passe son temps a empecher ailleurs.
    """
    import re
    from pathlib import Path

    dossier = Path(dossier_hermes)
    faites: set[int] = set()

    # 1. Le releve durable, quand il existe.
    try:
        for ligne in io.open(dossier / ACQUIS, encoding="utf-8").read().split():
            if ligne.isdigit():
                faites.add(int(ligne))
    except OSError:
        pass

    # 2. Le journal, qui porte la meme information sous une autre forme.
    #    Les deux sont unis plutot que l'un prefere a l'autre : une relance
    #    qui redirige sa sortie vers `nuit.log` le **tronque**, et une
    #    reprise qui ne lirait que lui perdrait tout a la seconde pause.
    try:
        texte = io.open(dossier / "nuit.log", encoding="utf-8",
                        errors="replace").read()
    except OSError:
        texte = ""

    courante = None
    for ligne in texte.splitlines():
        entete = re.match(r"===\s*.(\d+)\s", ligne)
        if entete:
            courante = int(entete.group(1))
            continue
        if courante is not None and ligne.strip().startswith(ABOUTIS):
            faites.add(courante)
            courante = None
    return faites


def noter_les_acquis(dossier_hermes, faites: set[int]) -> None:
    """Figer ce qui est fait, pour que la prochaine pause ne le reperde pas.

    Ecrit avant de relancer, donc avant que la sortie ne recouvre le
    journal. Ne leve pas : perdre le releve coute une reprise depuis un
    journal plus court, pas la campagne.
    """
    from pathlib import Path

    try:
        cible = Path(dossier_hermes)
        cible.mkdir(parents=True, exist_ok=True)
        io.open(cible / ACQUIS, "w", encoding="utf-8").write(
            "# Sections menees a bien. Relu par --reprendre.\n"
            + "\n".join(str(n) for n in sorted(faites)) + "\n")
    except (OSError, ValueError):
        # `ValueError` et pas seulement `OSError` : un chemin contenant
        # un octet nul leve la premiere sous Windows. Un releve qu'on ne
        # peut pas ecrire ne doit pas emporter une campagne qui marche.
        pass


def main() -> int:
    analyseur = argparse.ArgumentParser(description=__doc__)
    analyseur.add_argument("projet", help="dossier du projet")
    analyseur.add_argument("--cahier", default="PROJECT_SPEC.md")
    analyseur.add_argument(
        "--reprendre", action="store_true",
        help="sauter les sections deja faites, lues dans "
             ".hermes/nuit.log")
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
    from backend.mission.arborescence import (
        contrainte as contrainte_d_arborescence)

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

    if args.reprendre:
        # Les regles permanentes ne sont **pas** filtrees : elles ne sont pas
        # "faites", elles sont transmises a chaque mission. Les sauter
        # priverait la reprise de la moitie du cahier.
        faites = sections_deja_faites(projet / ".hermes")
        noter_les_acquis(projet / ".hermes", faites)
        restantes = [s for s in a_faire if s.numero not in faites]
        print(f"reprise : {len(faites)} section(s) deja faite(s), "
              f"{len(restantes)} a traiter")
        a_faire = restantes
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

    ouvrir_le_journal()
    if not verifier_le_harnais(accepte_le_mode_jetable=args.sans_harnais):
        return 2

    from backend.core.bootstrap.bootstrap import HermesBootstrap  # noqa: E402

    boot = HermesBootstrap()
    boot.build()
    moteur = boot.container.get("autonomous_engine")
    depart = time.monotonic()

    def harnais_toujours_la() -> None:
        """Lever si le harnais a disparu depuis le demarrage.

        Appelee avant chaque passe, y compris les reparations : c'est
        precisement pendant une reparation que §21 a brule son dernier
        credit sans cerveau.

        `derouler` attrape ce qui leve, marque la section `bloquee` et
        arrete la file — ce qui est exactement le comportement voulu. La
        section sera rejouee a la reprise, une fois le backend revenu,
        parce que `bloquee` n'est pas un verdict acquis.
        """
        if args.sans_harnais:
            return
        from backend.ral.adapters.prerequis_harnais import verifier

        etat = verifier()
        if not etat.pret:
            raise HarnaisPerdu(etat.explication())

    def lancer(section):
        print(f"\n=== §{section.numero} {section.titre} ===", flush=True)
        harnais_toujours_la()
        # Relue a chaque section : la pile du projet peut naitre a la
        # troisieme section et doit contraindre la quatrieme.
        objectif = brief_de_section(section, nom_du_cahier=args.cahier,
                                    regles=bloc, racine=str(projet),
                                    pile=contrainte_de_pile(str(projet))
                                         + contrainte_d_arborescence(
                                             str(projet)))
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
        harnais_toujours_la()
        objectif = brief_de_section(section, nom_du_cahier=args.cahier,
                                    regles=bloc, racine=str(projet),
                                    pile=contrainte_de_pile(str(projet))
                                         + contrainte_d_arborescence(
                                             str(projet)))
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
