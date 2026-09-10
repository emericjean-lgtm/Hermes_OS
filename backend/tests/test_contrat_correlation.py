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


def test_le_plugin_observateur_reste_non_installe():
    """G-28 et G-29 l'avaient dit ; G-30 ne change rien : sans restitution
    du `turnId`, l'observateur n'aurait rien a correler."""
    for module in (RACINE / "backend").rglob("*.py"):
        if "tests" in module.parts:
            continue
        source = module.read_text(encoding="utf-8", errors="replace")
        assert "observateur-skills" not in source, module


# ── Le patch amont : ce qu'il doit faire, et ne jamais faire ──────────

PATCH = CONTRAT / "turn-id.patch"


def _ajouts(fichier: str = "") -> str:
    """Les lignes AJOUTEES par le patch, pour un fichier ou pour tous.

    Le scope par fichier n'est pas cosmetique : les hunks se suivent, et une
    extraction qui ignore la frontiere deborde sur le fichier suivant. C'est
    exactement ce qui a fait echouer la premiere version de la garde sur
    `_client_turn_id` — elle attrapait la ContextVar de `skill_provenance.py`
    et n'arrivait plus a parser la fonction.
    """
    texte = PATCH.read_text(encoding="utf-8")
    if fichier:
        d = texte.index("diff --git a/" + fichier)
        suite = texte.find(chr(10) + "diff --git ", d + 1)
        texte = texte[d:suite if suite > 0 else None]
    return chr(10).join(l[1:] for l in texte.splitlines()
                        if l.startswith("+") and not l.startswith("+++"))


def _fonction_ajoutee(fichier: str, nom: str) -> str:
    """Le texte de la fonction `nom` ajoutee dans `fichier`, seule.

    Decoupee par HUNK — la frontiere que le diff porte lui-meme. Trois
    bornes tentees avant ont echoue, chacune sur une hypothese fausse :
    `"def _bind_guarded"` est une ligne de CONTEXTE, absente des ajouts ;
    le prochain `def` en colonne 0 n'existe pas, le hunk suivant ajoutant
    des lignes a une METHODE ; et l'indentation seule ne s'arrete pas, un
    hunk voisin commencant lui aussi par des lignes indentees.
    """
    texte = PATCH.read_text(encoding="utf-8")
    debut = texte.index("diff --git a/" + fichier)
    suite = texte.find(chr(10) + "diff --git ", debut + 1)
    fichier_texte = texte[debut:suite if suite > 0 else None]

    for hunk in fichier_texte.split(chr(10) + "@@"):
        ajouts = chr(10).join(
            l[1:] for l in hunk.splitlines()
            if l.startswith("+") and not l.startswith("+++"))
        if ("def " + nom) in ajouts:
            i = ajouts.index("def " + nom)
            return ajouts[i:].rstrip()
    raise AssertionError("fonction %s introuvable dans %s" % (nom, fichier))


def test_le_patch_porte_sa_base():
    """Un diff sans son point d'application ne se rejoue pas. La base est
    `693641aa8b` (v0.21.0), et le README la nomme."""
    spec = SPEC.read_text(encoding="utf-8")
    assert "693641aa8b" in spec
    assert PATCH.exists() and PATCH.stat().st_size > 0


def test_le_patch_ne_touche_que_les_trois_fichiers_annonces():
    """« Une modification upstream minimale » se verifie sur le diff, pas
    sur la promesse."""
    entetes = [l for l in PATCH.read_text(encoding="utf-8").splitlines()
               if l.startswith("diff --git")]
    touches = sorted(l.split(" b/")[-1] for l in entetes)
    assert touches == ["acp_adapter/server.py", "tools/skill_provenance.py",
                       "tools/skill_usage.py"], touches


def test_le_patch_ne_fabrique_jamais_de_turn_id():
    """La regle centrale : l'agent transporte, il n'engendre pas. Un `uuid`
    ou un repli sur une autre identite ferait de lui l'auteur de la
    correlation — donc une seconde autorite."""
    ajouts = _ajouts()
    for fabrique in ("uuid", "uuid4", "token_hex", "randint", "time.time()"):
        assert fabrique not in ajouts, (
            f"le patch fabrique un identifiant avec `{fabrique}`")


def test_le_patch_ne_substitue_ni_task_id_ni_session_id():
    """Les deux sont EGAUX sur le chemin ACP (`run_conversation(...,
    task_id=session_id)`) et appartiennent a l'agent. Les employer comme
    turnId rendrait une correlation qui n'en est pas une.

    La garde porte sur le CORPS de l'extracteur, pas sur deux formes de
    ligne. Ecrite ligne a ligne, elle restait verte quand la substitution
    se glissait dans le `return` de `_client_turn_id` — une mutation l'a
    montre."""
    corps = _fonction_ajoutee("acp_adapter/server.py", "_client_turn_id")
    # Parse plutot que filtre ligne a ligne : la docstring cite les deux noms
    # pour expliquer pourquoi on ne les emploie PAS, et un filtre approximatif
    # confondait l'explication avec l'usage.
    fonction = ast.parse(corps).body[0]
    docstring = fonction.body[0].value if (
        fonction.body and isinstance(fonction.body[0], ast.Expr)) else None
    noms = {n.attr for n in ast.walk(fonction) if isinstance(n, ast.Attribute)}
    noms |= {n.id for n in ast.walk(fonction) if isinstance(n, ast.Name)}
    noms |= {n.value for n in ast.walk(fonction)
             if isinstance(n, ast.Constant) and isinstance(n.value, str)
             and n is not docstring}
    for identite in ("task_id", "session_id"):
        assert identite not in noms, f"l'extracteur retombe sur `{identite}`"


def test_le_patch_omet_la_clef_quand_le_turn_id_est_absent():
    """« Absent en entree, absent en sortie ». Une chaine vide se lirait
    « correle a rien » et inviterait un consommateur a la remplir."""
    ajouts = _ajouts()
    assert '**({"client_turn_id": client_turn_id} if client_turn_id else {})' in ajouts


_POSE = re.compile(r"(?<![\w.])set_current_turn_id\(([^)]*)\)")


def _hunks_du_serveur() -> list:
    """Les hunks de `acp_adapter/server.py`, chacun reduit a ses ajouts."""
    texte = PATCH.read_text(encoding="utf-8")
    debut = texte.index("diff --git a/acp_adapter/server.py")
    suite = texte.find(chr(10) + "diff --git ", debut + 1)
    fichier = texte[debut:suite if suite > 0 else None]
    return [chr(10).join(l[1:] for l in hunk.splitlines()
                         if l.startswith("+") and not l.startswith("+++"))
            for hunk in fichier.split(chr(10) + "@@")]


def test_la_liaison_est_unique_et_posee_sur_la_pile_du_tour():
    """Ou la liaison est posee, et avec quoi. Deux defauts, une seule garde,
    parce qu'ils partagent la meme donnee.

    **Emplacement.** Lier sur le thread de la boucle — dans `prompt()` —
    placerait l'identifiant HORS du `contextvars.copy_context()` qui isole
    les tours concurrents, et deux sessions se contamineraient. La garde ne
    regarde donc pas l'en-tete du hunk (git y met le nom de la CLASSE, pas
    de la methode : les deux hunks affichent `class HermesACPAgent`) mais la
    PILE : toute liaison doit etre enregistree par `_bind_guarded(stack, ...)`,
    et cette pile n'existe que dans `_run_agent_turn`.

    **Argument.** `set_current_turn_id(client_turn_id or session_id)` rendrait
    une correlation qui n'en est pas une : sur le chemin ACP, `session_id` est
    aussi le `task_id`, et les deux appartiennent a l'agent.

    Trois versions precedentes ont ete trouvees par des mutations : l'une
    verifiait une PRESENCE et non un emplacement, l'autre ne regardait que
    l'extracteur, la troisieme comptait `reset_current_turn_id` parce qu'elle
    cherchait une sous-chaine sans frontiere de mot."""
    liaisons = []
    for ajouts in _hunks_du_serveur():
        for argument in _POSE.findall(ajouts):
            liaisons.append((argument.strip(), "_bind_guarded(stack," in ajouts))

    assert len(liaisons) == 1, (
        f"{len(liaisons)} liaison(s) : {liaisons} — une seule est attendue")
    argument, sur_la_pile = liaisons[0]
    assert sur_la_pile, (
        "la liaison n'est pas enregistree sur la pile du tour : elle est donc "
        "hors du contexte copie qui isole les tours concurrents")
    assert argument == "client_turn_id", (
        f"la liaison lie `{argument}` et non l'identifiant du client")


def test_le_patch_traite_une_metadonnee_deformee_comme_absente():
    """Un client qui envoie autre chose qu'une chaine n'a pas envoye de
    correlation. Lever ici casserait le tour ; deviner serait pire."""
    ajouts = _ajouts()
    assert "isinstance(extension, dict)" in ajouts
    assert "isinstance(turn_id, str)" in ajouts


def test_la_specification_porte_le_releve_de_la_chaine():
    """Onze cas mesures. Sans le releve, la prochaine passe les refait — ou,
    pire, les suppose."""
    spec = SPEC.read_text(encoding="utf-8")
    for repere in ("g31-c1", "g31-c2", "g31-hors-tour", "g31-x", "g31-y",
                   "clé absente quand aucun turnId",
                   "n'hérite d'aucune identité"):
        assert repere in spec, f"le releve ne porte pas `{repere}`"


def test_la_specification_dit_que_le_patch_est_local():
    """`hermes update` autostashe puis reapplique — au mieux. Presenter le
    patch comme acquis ferait croire durable ce qui ne l'est pas.

    La garde porte sur la SECTION qui traite la provenance. Ecrite sur le
    document entier, elle restait verte quand cette section affirmait
    « le patch est acquis » : la phrase « checkout local » figure aussi
    dans l'en-tete. Cinquieme fois de cette serie qu'une chaine presente
    deux fois satisfait une garde — les mutations les ont toutes trouvees,
    la relecture aucune."""
    spec = SPEC.read_text(encoding="utf-8")
    debut = spec.index("## 4 ter. La provenance")
    section = " ".join(spec[debut:spec.index("## 5.", debut)].split())
    assert "checkout local" in section, (
        "la section de provenance ne dit pas que le patch est local")
    assert "autostash" in section
    # Le README replie ses lignes : on compare sur un texte normalise plutot
    # que d'esperer que la phrase ne soit jamais coupee au meme endroit.
    plat = " ".join(spec.split())
    assert "seule fin correcte est son adoption amont" in plat
