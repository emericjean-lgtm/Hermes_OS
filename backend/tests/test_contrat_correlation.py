# -*- coding: utf-8 -*-
"""Le contrat de correlation, et l'abstention qui le protege (G-30, HOS-278).

## Ce que la mesure a etabli sur le runtime installe

`PromptRequest` d'ACP v0.11.2 porte `_meta`, *reserve par le protocole pour
que clients et agents attachent des metadonnees a leurs interactions*. Et le
routeur le **deplie en arguments nommes** vers le handler :

    params = {k: getattr(model_obj, k) for k in model.model_fields if k != "field_meta"}
    if meta := getattr(model_obj, "field_meta", None):
        params.update(meta)
    return await func(**params)

Mesure du 2026-09-10, `_meta: {"hermes": {"turnId": "run-42#tour-3"}}` :

    kwargs recus : {"message_id": null, "hermes": {"turnId": "run-42#tour-3"}}

Le transport existe donc, nativement, et l'agent l'ignore. Il manque la
**restitution** dans `on_skill_lifecycle` : trois lignes a trois coutures
qui existent deja (`acp_adapter/server.py`, `agent/turn_context.py`,
`tools/skill_usage.py`).

    le transport, cote ACP          ADOPT    natif, mesure
    la restitution                  ADAPT    trois points amont
    le contrat complet, aujourd'hui bloque   non livrable ici
    la meme chose cote Gateway      REJECT   canal privilegie
    un registre propre a Hermes OS  REJECT   seconde verite

## Pourquoi Hermes OS n'envoie rien

Poser `_meta` sans que l'agent le restitue livrerait **la moitie d'un
contrat**, et la moitie suivante serait tentee de deviner le reste. Ces
tests gardent l'abstention, et la specification qui la justifie.

## Ce que la mesure a corrige au passage

Sur le chemin ACP, le `task_id` de l'agent **est** son `session_id` —
`run_conversation(..., task_id=session_id)`. Un evenement Skill de chat ou
de mission porte donc deux fois la meme valeur, et aucune n'est granulaire
au tour. G-29 disait que `task_id` n'etait pas un `run_id` ; G-30 ajoute
qu'il n'est meme pas un identifiant de tour.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]
CONTRAT = RACINE / "integrations" / "hermes-agent" / "contrat-correlation"
SPEC = CONTRAT / "README.md"
ACP = RACINE / "backend" / "ral" / "adapters" / "hermes_agent_acp.py"


# ── L'abstention ──────────────────────────────────────────────────────

def test_hermes_os_n_envoie_de_metadonnee_que_pour_un_run_lie():
    """L'abstention de G-30 est **levee**, et remplacee par une condition.

    G-30 et G-31 gardaient : « Hermes OS ne pose pas `_meta` », parce que
    l'agent ne restituait rien puis parce que le patch etait local. G-32 a
    branche l'identite d'un Run reel sur le contrat, et la chaine est
    demontree de bout en bout. Le contrat n'est donc plus « jamais » mais
    « seulement pour un Run lie » — et sans Run, la requete doit rester
    octet pour octet celle d'avant.

    Le contrat precedent n'etait ni faux ni casse : il etait perime.
    """
    from backend.ral.adapters import hermes_agent_acp as acp

    source = ACP.read_text(encoding="utf-8")
    arbre = ast.parse(source)
    litteraux = {n.value for n in ast.walk(arbre)
                 if isinstance(n, ast.Constant) and isinstance(n.value, str)}
    assert "_meta" in litteraux and "turnId" in litteraux, (
        "l'adaptateur ne pose plus l'etiquette : la chaine G-32 est rompue")
    # Et la condition : ni `messageId`, qui est UNSTABLE et repondrait a une
    # autre question (« ce message a-t-il ete enregistre »).
    for hors_contrat in ("messageId", "message_id"):
        assert hors_contrat not in litteraux, (
            f"l'adaptateur emploie `{hors_contrat}`, marque UNSTABLE par ACP")


def test_une_seule_source_frappe_les_etiquettes():
    """Un second point de frappe produirait des etiquettes qu'aucune relation
    n'enregistre — donc des tours corrélables cote agent et introuvables
    ici. La garde remplace celle de G-30, qui interdisait toute frappe."""
    autorises = {"backend/runs/correlation.py"}
    coupables = []
    for module in (RACINE / "backend").rglob("*.py"):
        if "tests" in module.parts:
            continue
        rel = module.relative_to(RACINE).as_posix()
        if rel in autorises:
            continue
        source = module.read_text(encoding="utf-8", errors="replace")
        arbre = ast.parse(source)
        appels = {getattr(n.func, "attr", None) or getattr(n.func, "id", None)
                  for n in ast.walk(arbre) if isinstance(n, ast.Call)}
        if "frapper" in appels:
            coupables.append(rel)
    assert not coupables, (
        "une seconde source frappe des etiquettes : " + ", ".join(coupables))


def test_le_contrat_ne_contient_aucun_code_executable():
    """Le contrat est une demande amont et son patch. Un module Python ici
    deviendrait, a la premiere relecture distraite, une implementation
    Hermes OS — la seconde autorite que tout ce chantier refuse.

    Ecrite `== ["README.md"]`, la garde a rougi quand `turn-id.patch` est
    arrive : elle comptait des fichiers au lieu de nommer ce qu'elle
    interdit. Un patch n'est pas executable."""
    fichiers = sorted(p.name for p in CONTRAT.iterdir())
    assert fichiers == ["README.md", "turn-id.patch"], fichiers
    assert not [p for p in CONTRAT.iterdir() if p.suffix == ".py"]


# ── La specification dit ce qu'elle doit dire ─────────────────────────

def test_la_specification_porte_sa_mesure():
    """Une decision sans sa mesure se rejuge de memoire. Celle-ci porte le
    relevé exact du runtime, pour qu'un lecteur puisse le refaire.

    Le repere du relevé est `message_id`, qui n'apparait QUE dans la sortie
    observee. Ecrite sur `{"hermes": {"turnId": ...}}`, la garde restait
    verte quand le resultat disparaissait : la meme chaine figure dans la
    ligne d'ENTREE de la mesure, juste au-dessus. Une mesure sans son
    resultat n'est plus une mesure."""
    spec = SPEC.read_text(encoding="utf-8")
    for repere in ("params.update(meta)",
                   "PROTOCOL_VERSION = 1",
                   "run_conversation(..., task_id=session_id)"):
        assert repere in spec, f"la specification ne porte pas `{repere}`"
    assert '"message_id": null' in spec, (
        "la specification enonce la mesure sans en garder le releve")


def test_la_specification_nomme_les_trois_points_amont():
    """« Une modification upstream minimale, clairement localisee » : si
    elle n'est pas localisee, elle n'est pas minimale."""
    spec = SPEC.read_text(encoding="utf-8")
    for couture in ("acp_adapter/server.py", "agent/turn_context.py",
                    "tools/skill_usage.py"):
        assert couture in spec, f"la couture `{couture}` n'est pas nommee"


def test_la_specification_traite_les_neuf_cas_de_falsification():
    """Une proposition qui ne repond pas a ses cas limites n'est pas une
    proposition, c'est une intention."""
    spec = SPEC.read_text(encoding="utf-8")
    for cas in ("deux Runs dans la même session",
                "plusieurs Skills dans un même Run",
                "deux tâches Agent simultanées",
                "événement Skill sans `turnId`",
                "Run sans événement Skill",
                "redémarrage entre les étapes",
                "`turnId` inconnu ou étranger",
                "session reprise",
                "runtime sans support"):
        assert cas in spec, f"le cas « {cas} » n'est pas traite"


def test_la_specification_distingue_les_cinq_identites():
    """Le brief l'exigeait explicitement : ne pas confondre `task_id`
    agent, `session_id` agent, `turnId` client, `run_id` et `mission_id`.
    Chacune doit avoir son proprietaire ecrit."""
    spec = SPEC.read_text(encoding="utf-8")
    for identite in ("`task_id` de l'agent", "`session_id` de l'agent",
                     "`turnId`", "`run_id`", "`mission_id`"):
        assert identite in spec, f"`{identite}` n'a pas de proprietaire ecrit"
    assert "Hermes Agent" in spec and "Hermes OS" in spec


def test_la_specification_refuse_l_association_par_defaut():
    """La regle qui tient tout le reste : rien n'est associe « au mieux »."""
    spec = SPEC.read_text(encoding="utf-8")
    assert "Absent reste absent" in spec
    assert "aucune association n'est acceptée si le `turnId` attendu" in spec
    assert "que ce qu'il a frappé" in spec


def test_la_specification_dit_qu_elle_n_est_pas_implementee():
    """Un contrat trouve dans un depot se lit comme un contrat en vigueur."""
    spec = SPEC.read_text(encoding="utf-8")
    assert "Rien ici n'est implémenté" in spec
    assert "ADAPT" in spec and "REJECT" in spec


def test_la_specification_ne_demande_aucune_persistance_partagee():
    """La propriete qui la distingue de tout ce que G-29 a ecarte : le
    `turnId` voyage DANS l'evenement. Un contrat qui dependrait d'une table
    partagee heriterait de la table volatile, du Ledger sans colonne et de
    l'`audit_log` a six lignes."""
    spec = SPEC.read_text(encoding="utf-8")
    assert "Le contrat n'en demande aucune" in spec
    assert "dans l'événement" in spec


def test_le_gateway_est_ecarte_avec_sa_raison():
    """`_hosted_task` porte deja un `turn_id` — c'est le precedent le plus
    proche, et il faut dire pourquoi il ne sert pas : sa garde exige un
    callback APPELABLE, qui ne traverse pas JSON-RPC."""
    spec = SPEC.read_text(encoding="utf-8")
    assert "_hosted_task" in spec
    assert "bot_room" in spec
    assert "appelable" in spec


def test_l_echeance_du_14_septembre_est_tranchee():
    """G-28 avait fait de cette date un prealable. Le contrat doit dire
    s'il en depend, et pourquoi.

    La garde porte sur la SECTION, pas sur une phrase. Ecrite comme
    `"ne le touche pas" in spec`, elle restait verte quand la section etait
    videe : la meme phrase sert aussi au cas « session reprise » du tableau
    de falsification. Une mutation l'a montre — la relecture, non."""
    spec = SPEC.read_text(encoding="utf-8")
    debut = spec.index("## 7. L'échéance du 2026-09-14")
    section = spec[debut:spec.index("## 8.", debut)]
    assert "2026-09-14" in section
    assert "ne le touche pas" in section, (
        "la section ne tranche pas : elle nomme la date sans conclure")
    assert "PROTOCOL_VERSION = 1" in section or "paquet externe" in section, (
        "la section conclut sans dire sur quoi elle se fonde")


# ── Ce que le contrat ne doit pas devenir ─────────────────────────────

def test_la_specification_ne_promet_aucune_API_nouvelle():
    """Une methode inventee serait ignoree en silence par le serveur — le
    pire des echecs. Le contrat ne demande qu'un champ existant."""
    spec = SPEC.read_text(encoding="utf-8")
    assert "zéro changement de protocole" in spec
    assert "aucune méthode\nnouvelle" in spec or "aucune méthode nouvelle" in spec


def test_le_backend_ne_nomme_l_observateur_que_pour_le_lire():
    """L'abstention de G-28 est **levee** : l'observateur est installe (G-33).

    Ce qui la remplace est plus etroit et plus utile. Un seul module a le
    droit de nommer le plugin — celui qui LIT son etat. Un second qui le
    nommerait l'installerait, le configurerait ou le corrigerait, et Hermes
    OS deviendrait alors co-proprietaire d'un plugin de l'agent.

    Le contrat precedent n'etait ni faux ni casse : il etait perime.
    """
    lecteur = "backend/skills/observations.py"
    coupables = []
    for module in (RACINE / "backend").rglob("*.py"):
        if "tests" in module.parts:
            continue
        rel = module.relative_to(RACINE).as_posix()
        if rel == lecteur:
            continue
        source = module.read_text(encoding="utf-8", errors="replace")
        if "observateur-skills" in source or "hermes-os-observateur" in source:
            coupables.append(rel)
    assert not coupables, (
        "un module autre que le lecteur nomme l'observateur : "
        + ", ".join(coupables))
    assert (RACINE / lecteur).exists(), "le lecteur a disparu"


