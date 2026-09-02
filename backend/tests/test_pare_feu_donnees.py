"""Ce qui a le droit de partir chez un tiers (HOS-227).

## La fuite, mesurée avant d'écrire une ligne

`_build_messages` assemble un prompt et le donne au runtime. Quand ce
runtime est distant, tout part. Mesuré sur une mission liée à un
workspace :

    You have real filesystem access to the workspace at
    'C:\\Users\\emeri\\Skill360 Industry' via workspace_list/...

Le nom de l'utilisateur et celui de son client, dans **chaque** prompt
cloud. Pas un scénario : le comportement du jour où ce module a été
écrit.

Six fragments partaient, de sensibilités différentes — instructions
système (qui portent le chemin absolu), objectif de mission, journal de
projet relu depuis `.hermes/`, résultats amont (du texte produit par un
modèle, qui peut citer un fichier), manifeste, titre.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.security.pare_feu import (
    JETON_CAVIARDE,
    JETON_WORKSPACE,
    PolitiqueCloud,
    Sensibilite,
    Verdict,
    examiner,
    examiner_le_texte,
)

B = chr(92)
RACINE = "C:" + B + "Users" + B + "emeri" + B + "Skill360 Industry"


def _prompt_reel(racine: str = RACINE) -> list[dict]:
    """Le vrai prompt, construit par le vrai assembleur.

    Écrit contre `_build_messages` et non recopié à la main : un
    pare-feu calibré sur un prompt imaginaire protège un prompt
    imaginaire.
    """
    from backend.execution.task_executor import RealTaskExecutor

    tache = SimpleNamespace(task_id="t1", title="Corriger le port",
                            assigned_agent="atlas", assigned_skills=[],
                            assigned_tools=[])
    affectation = SimpleNamespace(agent_id="atlas", skill_ids=[], tool_ids=[])
    return RealTaskExecutor()._build_messages(
        tache, affectation, workspace=("p1", racine))


# ═══ La fuite d'origine ══════════════════════════════════════════════

def test_le_prompt_reel_porte_bien_la_racine():
    """Le test qui rendrait tous les autres vides s'il tombait.

    Si `_build_messages` cesse d'insérer la racine, ce fichier ne mesure
    plus rien — et il vaut mieux l'apprendre ici que de croire protéger.
    """
    assemble = " ".join(m["content"] for m in _prompt_reel())
    assert "emeri" in assemble
    assert "Skill360" in assemble


def test_la_racine_ne_part_plus():
    decision = examiner(_prompt_reel(), racines=[RACINE])
    envoye = " ".join(m["content"] for m in decision.messages)
    assert "emeri" not in envoye
    assert "Skill360" not in envoye
    assert JETON_WORKSPACE in envoye


def test_le_chemin_relatif_reste():
    """C'est lui, le travail.

    Un pare-feu qui retirerait aussi `src/app.py` protégerait en rendant
    le prompt inutile — donc en faisant désactiver le cloud, donc en ne
    protégeant plus rien.
    """
    texte, _ = examiner_le_texte("system", f"lis {RACINE}/src/app.py", [RACINE])
    assert texte == f"lis {JETON_WORKSPACE}/src/app.py"


@pytest.mark.parametrize("ecriture", [
    RACINE,
    RACINE.replace(B, "/"),
    repr(RACINE),
])
def test_les_trois_ecritures_de_la_racine_sont_couvertes(ecriture):
    """Antislash, slash, et la forme échappée d'un `repr()`.

    La troisième est exactement ce que `_build_messages` insère.
    """
    texte, constats = examiner_le_texte("system", f"at {ecriture} ok", [RACINE])
    assert "emeri" not in texte, ecriture
    assert constats


def test_une_racine_non_declaree_est_quand_meme_reduite():
    """Le dernier recours, quand l'appelant n'a pas passé la racine.

    Il ne masque que le dossier d'utilisateur — une expression
    régulière ne peut pas deviner où une racine s'arrête. C'est
    précisément pourquoi l'appelant la passe.
    """
    texte, constats = examiner_le_texte("system", f"at {RACINE} ok")
    assert "emeri" not in texte
    assert JETON_WORKSPACE in texte
    assert any(c.motif == "chemin d'utilisateur" for c in constats)


@pytest.mark.parametrize("chemin", ["/home/emeric/projet", "/Users/emeric/projet"])
def test_les_racines_unix_aussi(chemin):
    texte, _ = examiner_le_texte("system", f"at {chemin} ok")
    assert "emeric" not in texte


# ═══ Les identifiants : refus, pas caviardage ════════════════════════

def test_un_identifiant_fait_refuser_l_envoi():
    """Et **pas** « retirer la clé et envoyer le reste ».

    Un identifiant dans un prompt veut dire que le contexte assemblé
    contient du matériel qui n'aurait pas dû y entrer — vraisemblablement
    le fichier d'où il vient. Retirer la clé et envoyer le fichier autour
    serait la moitié d'une protection.
    """
    decision = examiner([{"role": "user",
                          "content": "OPENAI_API_KEY=sk-abcdefghijklmnop1234"}])
    assert decision.verdict is Verdict.REFUSE
    assert decision.envoyable is False


def test_un_envoi_refuse_ne_porte_aucun_message():
    """Pour qu'un appelant distrait qui enverrait quand même n'envoie rien."""
    decision = examiner([{"role": "user", "content": "token=abcd1234efgh5678"}])
    assert decision.messages == []


@pytest.mark.parametrize("charge", [
    "Authorization: Bearer abcdefghijklmnopqrst",
    "sk-abcdefghijklmnopqrstuvwx",
    "ghp_abcdefghijklmnopqrstuvwxyz01",
    "api_key: 9f8e7d6c5b4a3210",
])
def test_les_formes_d_identifiant_du_depot_sont_vues(charge):
    """Les motifs viennent d'`audit_log.redact`, réutilisé.

    C'est le plus proche d'un `secret_scanner` que ce dépôt possède
    (§17.1), et ses motifs sont délibérément conservateurs. En écrire un
    second, divergent, serait pire que le réutiliser.
    """
    assert examiner([{"role": "user", "content": charge}]).verdict is Verdict.REFUSE


def test_le_rapport_ne_cite_jamais_la_valeur():
    """Un rapport de fuite qui cite le secret est une seconde fuite.

    C'est la règle de HOS-218, et elle vaut ici pour la même raison :
    le rapport voyage — événement, journal, interface.
    """
    decision = examiner([{"role": "user",
                          "content": "OPENAI_API_KEY=sk-abcdefghijklmnop1234"}])
    rapport = " ".join(c.apercu for c in decision.constats) + decision.raison
    assert "sk-abcdefghijklmnop1234" not in rapport


# ═══ L'interne : caviardé, pas refusé ════════════════════════════════

def test_une_adresse_et_une_machine_interne_sont_caviardees():
    """Les refuser rendrait le cloud inutilisable pour toute mission
    liée à un workspace, donc désarmerait le pare-feu.

    C'est la leçon du canary (HOS-218) et celle de la portée
    d'approbation (HOS-224) : une protection insupportable à l'usage
    finit débranchée.
    """
    decision = examiner([{"role": "user",
                          "content": "écris à paul@client.fr via 192.168.1.40"}])
    assert decision.verdict is Verdict.CAVIARDE
    assert decision.envoyable is True
    envoye = decision.messages[0]["content"]
    assert "paul@client.fr" not in envoye
    assert "192.168.1.40" not in envoye
    assert JETON_CAVIARDE in envoye


def test_l_adresse_de_boucle_locale_n_est_pas_caviardee():
    """Hermes écoute dessus.

    Elle apparaît dans des messages d'erreur normaux, et la caviarder
    rendrait un diagnostic illisible sans rien protéger — le genre de
    bruit qui fait débrancher une alarme.
    """
    decision = examiner([{"role": "user", "content": "backend sur 127.0.0.1:8010"}])
    assert decision.verdict is Verdict.AUTORISE
    assert "127.0.0.1" in decision.messages[0]["content"]


def test_du_texte_ordinaire_passe_intact():
    """Un pare-feu qui refuse tout est un pare-feu qu'on désarme."""
    decision = examiner([{"role": "user", "content": "Corrige le port du serveur"}])
    assert decision.verdict is Verdict.AUTORISE
    assert decision.messages[0]["content"] == "Corrige le port du serveur"


# ═══ La politique de projet : le vrai « refusé par défaut » ══════════

def test_un_projet_en_jamais_n_envoie_rien():
    """Le vrai levier, à la granularité où quelqu'un peut en décider.

    L'utilisateur sait si son dépôt client a le droit d'aller chez un
    tiers ; le classificateur ne le saura jamais.
    """
    decision = examiner([{"role": "user", "content": "bonjour"}],
                        politique=PolitiqueCloud.JAMAIS)
    assert decision.verdict is Verdict.REFUSE
    assert decision.messages == []
    assert "jamais" in decision.raison


def test_un_projet_en_approbation_ne_part_pas_seul():
    decision = examiner([{"role": "user", "content": "bonjour"}],
                        politique=PolitiqueCloud.APPROBATION)
    assert decision.verdict is Verdict.APPROBATION
    assert decision.envoyable is False


def test_un_secret_prime_sur_la_politique_d_approbation():
    """On ne demande pas s'il faut envoyer un identifiant.

    Le proposer à l'approbation ferait exister un chemin où un humain
    pressé laisse partir une clé.
    """
    decision = examiner([{"role": "user", "content": "token=abcd1234efgh5678"}],
                        politique=PolitiqueCloud.APPROBATION)
    assert decision.verdict is Verdict.REFUSE


def test_la_politique_jamais_n_examine_meme_pas():
    """Rien à peser quand rien ne sort.

    Et surtout : aucun contenu ne doit être parcouru, tronçonné ou
    résumé pour un envoi qui n'aura pas lieu.
    """
    decision = examiner([{"role": "user", "content": "sk-abcdefghijklmnop1234"}],
                        politique=PolitiqueCloud.JAMAIS)
    assert decision.constats == []


# ═══ Le goulet ═══════════════════════════════════════════════════════

def test_le_pare_feu_est_avant_l_envoi_pas_apres():
    """Après, c'est un constat de fuite, pas un pare-feu.

    Garde sur l'arbre syntaxique et non sur le texte : la troisième fois
    qu'une assertion de ce type s'est accrochée à une docstring dans ce
    chantier, elle a changé de méthode.
    """
    import ast
    import inspect
    import textwrap

    from backend.core.bootstrap import service_registry

    source = textwrap.dedent(inspect.getsource(service_registry._make_cloud_chat))
    arbre = ast.parse(source)
    interne = next(n for n in ast.walk(arbre)
                   if isinstance(n, ast.AsyncFunctionDef))

    appels = [n for n in ast.walk(interne) if isinstance(n, ast.Call)]
    noms = [ast.unparse(n.func) for n in appels]
    examen = next(i for i, n in enumerate(noms) if "examiner" in n)
    envoi = next(i for i, n in enumerate(noms) if n.endswith("chat"))
    assert examen < envoi, (
        "le pare-feu doit s'exécuter avant l'envoi — après, c'est un "
        "constat de fuite")


def test_le_goulet_envoie_les_messages_caviardes_pas_les_originaux():
    """L'erreur qui annulerait tout le module.

    Examiner puis envoyer `messages` au lieu de `decision.messages`
    passerait tous les tests du classificateur et ne protégerait de
    rien.
    """
    import ast
    import inspect
    import textwrap

    from backend.core.bootstrap import service_registry

    source = textwrap.dedent(inspect.getsource(service_registry._make_cloud_chat))
    interne = next(n for n in ast.walk(ast.parse(source))
                   if isinstance(n, ast.AsyncFunctionDef))
    envoi = next(n for n in ast.walk(interne)
                 if isinstance(n, ast.Call) and ast.unparse(n.func).endswith("chat"))
    premier = ast.unparse(envoi.args[0]) if envoi.args else ""
    assert "decision" in premier, (
        f"le goulet envoie {premier!r} — ce doit être les messages "
        "caviardés, pas ceux d'origine")


def test_l_evenement_de_decision_est_declare():
    from backend.core.event_topics import BASELINE_TOPICS

    assert "cloud.pare_feu" in BASELINE_TOPICS


def test_la_racine_du_workspace_atteint_le_pare_feu():
    """Sans elle, le nom du client survivait au caviardage.

    Mesuré : `<WORKSPACE>` suivi de « Skill360 Industry ».
    """
    import inspect

    from backend.execution import task_executor

    source = inspect.getsource(task_executor.RealTaskExecutor.execute)
    assert "racines_du_prompt" in source


# ═══ Le tri-état, encore ═════════════════════════════════════════════

def test_le_verdict_distingue_quatre_issues():
    """Autorisé, caviardé, à approuver, refusé.

    Fondre « caviardé » dans « autorisé » ferait disparaître du rapport
    le fait que quelque chose a été retiré — et un caviardage qu'on ne
    voit pas est un caviardage qu'on ne peut pas contester.
    """
    assert len(set(Verdict)) == 4
    assert len(set(Sensibilite)) == 3
