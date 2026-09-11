r"""Demander la pose d'une Skill, sous l'autorité d'Aegis (G-36, HOS-285).

## Ce que G-35 avait laissé ouvert

La vérification était acquise — `gouvernance.py` recalcule l'empreinte et
confronte le verrou au disque. Ce qui manquait était l'**approbateur** :
Hermes OS a deux files, et le cockpit lisait la mauvaise.

Mesuré le 2026-09-11, et c'est ce qui décide laquelle porte l'approbation
d'une Skill :

                          Aegis                    Policy (HOS-046)
    stockage              SQLite `PendingApproval` dict en mémoire
    producteur réel       `AegisAgent` sur le        aucun —
                          chemin de requête          `set_policy_engine`
                                                     n'est jamais appelé
    survit au redémarrage oui                        non
    sémantique            jeton de passage, une      demande de workflow,
                          fois, 15 min, empreinte    multi-approbateurs,
                          exacte                     délégation

Les deux ne font pas la même chose, et ce module ne les fusionne pas. Mais
une seule est **branchée**, et c'est celle qui garde les actions réelles :
l'approbation d'une pose de Skill lui revient.

## Le contrat d'Aegis, et ce qu'il impose à l'appelant

Aegis n'est pas une file de travaux : « Approving here does **not** replay
the action ». Une approbation autorise **la prochaine tentative
identique**, une fois. L'enchaînement produit est donc :

    1. demande      -> REQUIRE_HUMAN_VALIDATION, rien n'est posé,
                       la ligne apparaît dans la file d'Aegis
    2. l'humain décide dans le cockpit
    3. on redemande -> l'approbation est consommée, Aegis rend ALLOW,
                       et c'est seulement là que quelque chose s'écrit

Ce n'est pas une contrainte subie : une file qui rejouerait des actions
stockées aurait besoin d'un répartiteur capable de tout réexécuter, ce
qu'une barrière de sécurité ne doit pas posséder.

## Pourquoi le résultat ne vient pas de la réponse

`skills.manage install` rend `{"installed": true}` dans tous les cas —
`do_install` est annoté `-> None` et rend `None` sur chacun de ses chemins,
succès compris (mesure G-35). Il n'y a donc rien à croire dans la réponse.

Le verdict est tiré d'un **diff du disque** pris de part et d'autre de la
demande : une clef neuve dans `.hub/lock.json` dont le dossier vérifie son
empreinte, une ligne `BLOCKED` neuve dans `.hub/audit.log`, ou rien du
tout. Il n'est déduit ni de l'identifiant demandé, ni d'un nom calculé, ni
d'un booléen.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger("hermes_os.skills.installation")

#: Le type d'action soumis à Aegis. Déclaré dans `config/security.yaml`
#: avec `mandatory_validation: true` : poser une Skill fait entrer du code
#: tiers que l'agent exécutera, et G-35 a mesuré que le scanner laisse
#: passer un verdict `dangerous` quand la source est `builtin`.
ACTION_AEGIS = "skill_install"

#: Les issues possibles, bornées. Aucune ne se déduit d'une autre, et
#: aucune ne vient de la réponse du runtime.
POSEE = "posee"
BLOQUEE_PAR_LE_SCANNER = "bloquee_par_le_scanner"
SANS_EFFET = "sans_effet"
APPROBATION_REQUISE = "approbation_requise"
REFUSEE = "refusee"
INDISPONIBLE = "indisponible"


def _aegis():
    from backend.core.agent_registry import get_agent_registry

    return get_agent_registry().get("aegis")


def _tracer(topic: str, charge: dict) -> None:
    """Le journal de Hermes OS, jamais celui de l'agent.

    Même posture que `services/mutations_agent` : tracer sa propre demande
    n'est pas posséder l'état de l'agent, c'est répondre de ses actes.
    Best-effort — une trace qui échoue n'annule pas une pose déjà faite.
    """
    try:
        from backend.core.event_hub import get_event_hub

        get_event_hub().publish(topic, charge)
    except Exception:  # noqa: BLE001
        logger.debug("trace %s impossible", topic, exc_info=True)


def _etat_du_disque() -> tuple[dict[str, dict], list[str]]:
    """Ce que le disque porte : le verrou indexé par nom, et le journal.

    Les deux sont lus par `gouvernance`, qui est déjà le lecteur unique du
    dossier `.hub` de l'agent. En ouvrir un second ici ferait exactement la
    seconde vérité que cette série refuse depuis HOS-274.
    """
    from backend.skills import gouvernance

    posees = {p.nom: p.as_dict() for p in gouvernance.posees()}
    journal = [o.as_dict() for o in gouvernance.journal()]
    return posees, [f"{o['horodatage']} {o['action']} {o['skill']}"
                    for o in journal]


def _verdict_du_diff(avant: tuple, apres: tuple) -> dict[str, Any]:
    """Ce qui s'est réellement passé, lu sur le disque.

    L'ordre des tests n'est pas indifférent. Une clef neuve **vérifiée**
    prime : c'est le seul cas où quelque chose a été posé. Vient ensuite
    une ligne `BLOCKED` neuve, qui dit un refus du scanner. Reste
    `SANS_EFFET`, qui couvre tout ce dont l'agent ne garde aucune trace —
    nom introuvable, déjà posée sans `--force` — et que G-35 a mesuré
    comme parfaitement silencieux.
    """
    posees_avant, journal_avant = avant
    posees_apres, journal_apres = apres

    neuves = [n for n in posees_apres if n not in posees_avant]
    lignes = [l for l in journal_apres if l not in journal_avant]

    for nom in neuves:
        entree = posees_apres[nom]
        if entree["etat"] == "conforme":
            return {"statut": POSEE, "skill": nom, "verifiee": entree}
        # Une clef neuve dont le dossier ne vérifie pas son empreinte n'est
        # pas une pose réussie : c'est le faux succès sous une autre forme.
        return {"statut": SANS_EFFET, "skill": nom, "verifiee": entree,
                "raison": f"le verrou annonce {nom}, le disque dit "
                          f"« {entree['etat']} »"}

    for ligne in lignes:
        if " BLOCKED " in f" {ligne} ":
            return {"statut": BLOQUEE_PAR_LE_SCANNER, "journal": lignes}

    return {"statut": SANS_EFFET, "journal": lignes,
            "raison": "rien n'a été écrit : ni compétence, ni ligne d'audit"}


def _demander_au_runtime(identifiant: str) -> Optional[str]:
    """Transmettre la demande à son propriétaire. Rend une erreur, ou `None`.

    L'agent possède ses Skills : Hermes OS ne télécharge rien, ne scanne
    rien et n'écrit rien sous `%LOCALAPPDATA%\\hermes`. Il demande, par la
    méthode que le runtime expose — `skills.manage`, mesurée présente
    parmi les 206 du registre (G-19).
    """
    from backend.api.routes.bridge import pont

    try:
        reponse = pont().demander_mutation(
            "skills.manage",
            {"action": "install", "query": identifiant},
            timeout=300)
    except Exception as exc:  # noqa: BLE001 - un refus est un résultat
        return f"{type(exc).__name__}: {exc}"
    if "error" in reponse:
        erreur = reponse["error"]
        return f"refus du runtime ({erreur.get('code')}): {erreur.get('message')}"
    return None


def installer(identifiant: str) -> dict[str, Any]:
    """Demander la pose d'une Skill, et rendre ce qui s'est **vraiment** passé.

    Trois portes, dans cet ordre, et aucune ne s'enjambe :

    1. **Aegis.** Un `DENY` ou un `REQUIRE_HUMAN_VALIDATION` rend la main
       sans que rien ne soit transmis au runtime. Le refus est donc un
       refus d'écrire, pas un refus d'afficher.
    2. **Le runtime.** Lui seul récupère, met en quarantaine, scanne et
       pose. Son scanner n'est ni contourné ni rejoué.
    3. **Le disque.** Le résultat rendu ici est celui du diff, jamais
       celui de la réponse.
    """
    identifiant = (identifiant or "").strip()
    if not identifiant:
        return {"statut": REFUSEE, "raison": "identifiant vide"}

    from backend.security.aegis_engine import ActionRequest, Verdict

    action = ActionRequest(
        action_type=ACTION_AEGIS,
        description=f"Install skill {identifiant}",
        requesting_agent="hermes-os.cockpit",
        # L'empreinte d'approbation ne hache pas la description : sans ce
        # discriminant, approuver la pose d'une Skill autoriserait celle
        # d'une autre (HOS-224).
        discriminants=(("identifiant", identifiant),),
    )
    _tracer("skills.installation.demandee", {"identifiant": identifiant})

    try:
        decision = _aegis().evaluate(action)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Aegis injoignable", exc_info=True)
        return {"statut": INDISPONIBLE,
                "raison": f"Aegis injoignable : {type(exc).__name__}: {exc}"}

    if decision.verdict is Verdict.REQUIRE_HUMAN_VALIDATION:
        # `_apply_human_consent` vient de déposer la ligne dans la file
        # d'Aegis. Rien n'est transmis au runtime.
        _tracer("skills.installation.en_attente",
                {"identifiant": identifiant, "raison": decision.reason})
        return {"statut": APPROBATION_REQUISE, "raison": decision.reason,
                "action_type": ACTION_AEGIS}
    if decision.verdict is not Verdict.ALLOW:
        _tracer("skills.installation.refusee",
                {"identifiant": identifiant, "raison": decision.reason})
        return {"statut": REFUSEE, "raison": decision.reason}

    avant = _etat_du_disque()
    erreur = _demander_au_runtime(identifiant)
    apres = _etat_du_disque()

    if erreur is not None:
        # Même en erreur, on relit le disque : un appel qui échoue après
        # avoir écrit laisserait sinon une pose invisible.
        resultat = _verdict_du_diff(avant, apres)
        if resultat["statut"] == SANS_EFFET:
            return {"statut": INDISPONIBLE, "raison": erreur}
        return {**resultat, "raison": erreur}

    resultat = _verdict_du_diff(avant, apres)
    _tracer("skills.installation.resultat",
            {"identifiant": identifiant, "statut": resultat["statut"]})
    return resultat
