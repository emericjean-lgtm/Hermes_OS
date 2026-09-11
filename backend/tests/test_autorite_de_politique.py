# -*- coding: utf-8 -*-
"""Une seule autorite de politique, et c'est Aegis (G-37, HOS-286).

## Le diagnostic, mesure le 2026-09-11

`backend/policy/` (HOS-046) porte trois responsabilites. Les trois sont
REJETEES comme autorite, et chacune a son proprietaire reel :

    evaluation de politique -> Aegis (`config/security.yaml` +
                               `AegisEngine`, relu a chaque evaluation)
    file d'approbation      -> Aegis (`security/approvals.py`, SQLite) —
                               ferme en G-36
    journal d'audit         -> `core/audit_log.py` (§18, SQLite +
                               fichiers, redaction a l'ecriture)

Ce qui l'etablit, en chiffres :

- `set_policy_engine` n'est **jamais appele**. `set_security_engine`, si —
  `service_registry.py` y injecte `AegisSecurityAdapter`. Le seul appelant
  de `PolicyEngine.evaluate` est `autonomous_guard`, derriere
  `if self._policy_engine:`, donc mort.
- Les trois evenements que le `ServiceSpec` declare produire —
  `approval.requested`, `approval.granted`, `audit.created` — comptent
  **zero occurrence** sur le bus durable.
- Le moteur porte **dix regles en dur**, jamais evaluees, dont deux
  **contredisent** la politique en vigueur : `internet_access_allowed:
  allow` contre `network_call` qui exige « high », et
  `system_modification_denied: deny` contre `system_config` qui demande un
  humain.
- Sa file d'approbation et son journal sont **en memoire** : zero entree,
  et rien ne survit a un redemarrage.
- Le journal du §18, lui, porte **six entrees reelles** et n'avait aucun
  lecteur — le cockpit lisait l'anneau vide.

## Ce que ces gardes tiennent

Pas « `backend/policy/` ne doit pas exister » : le supprimer proprement est
une decision distincte, et il sert encore de reference documentaire. Elles
tiennent la seule propriete qui compte — **qu'il ne redevienne pas une
autorite**, ni par cablage, ni par affichage.
"""
from __future__ import annotations

import ast
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]
POLICY = RACINE / "backend" / "policy"


def _sources_backend():
    for module in (RACINE / "backend").rglob("*.py"):
        if "tests" in module.parts or module.is_relative_to(POLICY):
            continue
        yield module, module.read_text(encoding="utf-8", errors="replace")


# ── L'autorite ────────────────────────────────────────────────────────

def test_le_moteur_de_politique_n_est_cable_a_aucun_garde():
    """`set_policy_engine` doit rester sans appelant.

    L'appeler brancherait les dix regles de `backend/policy/` sur le
    chemin de decision d'`autonomous_guard`, a cote d'Aegis — deux jeux de
    regles pour les memes actions, dont deux se contredisent. C'est
    exactement la seconde autorite que cette garde interdit.

    Elle n'interdit pas d'AVOIR un second moteur : elle interdit de le
    brancher sans avoir d'abord tranche laquelle des deux politiques
    s'applique, ce que G-37 a tranche en faveur d'Aegis.
    """
    coupables = []
    for module, source in _sources_backend():
        for noeud in ast.walk(ast.parse(source)):
            if (isinstance(noeud, ast.Call)
                    and getattr(noeud.func, "attr", "") == "set_policy_engine"):
                coupables.append(str(module.relative_to(RACINE)))
    assert not coupables, (
        "`set_policy_engine` est appele par " + ", ".join(coupables) +
        " — les dix regles de backend/policy/ deviendraient une seconde "
        "autorite a cote d'Aegis, et deux d'entre elles la contredisent")


def test_aegis_reste_cable_au_garde_autonome():
    """Le pendant du precedent, et il compte autant : la garde ci-dessus
    serait satisfaite si PERSONNE n'etait cable. Ce qu'on veut est qu'Aegis
    le soit et que l'autre ne le soit pas."""
    source = (RACINE / "backend" / "core" / "bootstrap"
              / "service_registry.py").read_text(encoding="utf-8")
    assert "set_security_engine(AegisSecurityAdapter(" in source, (
        "Aegis n'est plus injecte dans le garde autonome : il n'y a plus "
        "d'autorite du tout")


def test_aucun_module_hors_policy_n_evalue_ses_regles():
    """Un appelant direct du moteur contournerait la garde ci-dessus.

    Portee : les modules qui importent `backend.policy`. `service_registry`
    en est exclu — il le CONSTRUIT et monte ses routes, ce qui n'est pas
    une decision de securite.
    """
    autorises = {"backend\\core\\bootstrap\\service_registry.py"}
    coupables = []
    for module, source in _sources_backend():
        if "backend.policy" not in source:
            continue
        if str(module.relative_to(RACINE)) in autorises:
            continue
        coupables.append(str(module.relative_to(RACINE)))
    assert not coupables, (
        "un module evalue les regles de backend/policy/ : " +
        ", ".join(coupables))


# ── Les surfaces sans producteur ──────────────────────────────────────

def test_le_cockpit_ne_lit_aucune_surface_sans_producteur():
    """Les trois endpoints de `backend/policy/` decrivent des magasins que
    rien n'alimente. Les afficher n'est pas neutre : l'ecran montre alors
    une file vide, un journal vide et une politique qui ne s'applique pas —
    trois affirmations fausses, et d'autant plus credibles qu'elles ont la
    forme de vraies donnees.

    Mesure : le Dashboard a annonce « File d'approbation vide » pendant
    qu'Aegis portait 206 demandes du 2026-08-10 au 2026-09-02.
    """
    src = RACINE / "frontend" / "src"
    coupables = []
    for fichier in list(src.rglob("*.ts")) + list(src.rglob("*.tsx")):
        if fichier.name.endswith(".test.ts") or fichier.name.endswith(".test.tsx"):
            continue
        texte = fichier.read_text(encoding="utf-8", errors="replace")
        for motif in ('fetchJSON<unknown>("/approval")', '`/audit${'):
            if motif in texte:
                coupables.append(f"{fichier.relative_to(RACINE)} -> {motif}")
    assert not coupables, (
        "le cockpit lit une surface sans producteur : " + ", ".join(coupables))


def test_l_ecran_de_gouvernance_lit_les_trois_autorites_reelles():
    """Le pendant : ecarter les mauvaises sources ne suffit pas, il faut
    que les bonnes soient lues. Sans cette moitie, un ecran vide passerait
    la garde ci-dessus."""
    ecran = (RACINE / "frontend" / "src" / "features" / "governance"
             / "governance-center.tsx").read_text(encoding="utf-8")
    # L'APPEL, pas le nom. Trouve par mutation : remplacer
    # `useAutonomy()` par un objet fige `as ReturnType<typeof useAutonomy>`
    # laissait le nom dans le fichier et la garde verte, pendant que
    # l'ecran n'interrogeait plus rien.
    for hook, quoi in (("useApprovals", "la file d'Aegis"),
                       ("useAutonomy", "la matrice Aegis"),
                       ("useAuditLog", "le journal du §18")):
        assert f"{hook}()" in ecran, f"{quoi} n'est pas lue : `{hook}()` absent"

    client = (RACINE / "frontend" / "src" / "services"
              / "client.ts").read_text(encoding="utf-8")
    assert '"/security/approvals"' in client
    assert '"/security/autonomy"' in client
    assert "`/logs${" in client


def test_le_journal_lu_est_celui_qui_porte_des_ecritures():
    """`core/audit_log.py` a de vrais ecrivains — un tour de chat en
    enregistre un. L'anneau de `backend/policy/` n'en a qu'un seul,
    `PolicyEngine.evaluate`, qui n'est jamais appele."""
    chat = (RACINE / "backend" / "api" / "routes"
            / "chat.py").read_text(encoding="utf-8")
    assert "audit_log" in chat, (
        "le journal du §18 n'a plus d'ecrivain : le rebrancher dessus "
        "afficherait un journal vide, ce que G-37 corrigeait")


# ── La politique affichee est celle qui s'applique ────────────────────

def test_la_matrice_servie_est_celle_qu_aegis_relit():
    """La route ne doit pas recopier la matrice : elle doit la demander a
    `PermissionMatrix`, la meme instance qu'`AegisEngine` interroge. Une
    copie divergerait au premier changement de `config/security.yaml`."""
    source = (RACINE / "backend" / "api" / "routes"
              / "security.py").read_text(encoding="utf-8")
    debut = source.index("async def get_autonomy(")
    corps = source[debut:source.index("\nclass ", debut)]
    assert "_matrice().known_categories()" in corps
    assert "_matrice().get_category(" in corps
    assert "action_categories" not in corps, (
        "la route relit le YAML au lieu de demander a la matrice")


def test_l_effet_affiche_suit_la_meme_regle_que_le_moteur():
    """`_effet` reproduit la comparaison d'`AegisEngine` pour l'affichage.
    Une divergence ferait dire a l'ecran l'inverse de ce qui se passera —
    et personne ne s'en apercevrait avant un refus surprise.

    Confronte au moteur, pas a elle-meme : pour chaque categorie et chaque
    niveau, le verdict d'`AegisEngine` sur une action non-path_based doit
    s'accorder avec ce que `_effet` annonce.
    """
    from backend.api.routes.security import _effet, _ORDRE_AUTONOMIE
    from backend.security.aegis_engine import AegisEngine, ActionRequest, Verdict
    from backend.security.permission_matrix import PermissionMatrix
    import yaml

    config = yaml.safe_load(
        (RACINE / "config" / "security.yaml").read_text(encoding="utf-8"))
    for niveau in _ORDRE_AUTONOMIE:
        matrice = PermissionMatrix(config)
        matrice.autonomy_level = niveau
        moteur = AegisEngine(matrice, allowed_paths=[])
        # Une categorie SANS seuil declare : aucune du fichier actuel n'est
        # dans ce cas, donc la boucle sur les categories reelles n'exerce
        # jamais cette branche — trouve par mutation. Une categorie ajoutee
        # demain sans `min_autonomy_for_auto_allow` ferait dire « autorise »
        # a l'ecran la ou le moteur demande un humain.
        from backend.security.permission_matrix import CategoryPolicy

        sans_seuil = CategoryPolicy(name="sonde", mutating=True,
                                    path_based=False,
                                    mandatory_validation=False,
                                    min_autonomy_for_auto_allow=None)
        assert _effet(sans_seuil, niveau) == "humain", (
            "une categorie sans seuil declare s'affiche autorisee")

        for nom in matrice.known_categories():
            policy = matrice.get_category(nom)
            if policy.path_based:
                continue  # le verdict depend alors d'un chemin, pas du niveau
            decision = moteur.evaluate(ActionRequest(
                action_type=nom, description="sonde"))
            attendu = ("autorise" if decision.verdict is Verdict.ALLOW
                       else "humain")
            assert _effet(policy, niveau) == attendu, (
                f"{nom} au niveau {niveau} : l'ecran dit "
                f"{_effet(policy, niveau)!r}, le moteur rend "
                f"{decision.verdict.value!r}")


def test_les_regles_de_policy_ne_sont_plus_presentees_comme_la_politique():
    """Elles ne sont evaluees nulle part, et deux d'entre elles
    contredisent la politique en vigueur. Les afficher comme « les regles »
    faisait lire a un operateur une politique qui n'existe pas."""
    ecran = (RACINE / "frontend" / "src" / "features" / "governance"
             / "governance-center.tsx").read_text(encoding="utf-8")
    assert "usePolicyRules" not in ecran.split("/* ══")[0] + "".join(
        ligne for ligne in ecran.splitlines(True)
        if not ligne.lstrip().startswith(("//", "*", "/*"))), (
        "l'ecran lit encore les regles de backend/policy/")


def test_le_module_de_politique_reste_supprime():
    """**Rescopee par G-38**, qui a retire `backend/policy/`.

    Elle lisait les dix regles pour tenir la contradiction au dossier —
    `internet_access_allowed: allow` contre `network_call` qui exige
    « high », `system_modification_denied: deny` contre `system_config` qui
    demande un humain. Ces regles n'existent plus ; ce qu'il faut garder
    est leur ABSENCE.

    Le recreer ne serait pas une erreur en soi. Le recreer **et le
    brancher** en serait une, et c'est ce que les gardes precedentes
    tiennent. Celle-ci ferme la porte un cran plus tot : le repertoire
    absent, aucune reactivation ne peut etre accidentelle.
    """
    # Deux echecs distincts, deux messages. Le premier a ete rencontre :
    # un `git stash` de mesure a fait revenir les sources le temps d'une
    # collecte, Python a compile, et le `__pycache__` est reste apres le
    # `pop`. Un message unique aurait annonce « le module est revenu » pour
    # neuf `.pyc` orphelins — vrai sur la forme, faux sur le fond.
    sources = sorted(p.name for p in POLICY.rglob("*.py")) if POLICY.exists() else []
    assert not sources, (
        "backend/policy/ est revenu : " + ", ".join(sources) + ". G-37 a "
        "mesure que ses trois responsabilites sont portees ailleurs et que "
        "deux de ses regles contredisent la politique en vigueur. Le "
        "rebrancher demande de trancher a nouveau laquelle s'applique.")
    assert not POLICY.exists(), (
        "backend/policy/ existe sans source : du bytecode orphelin, "
        "probablement laisse par un `git stash`. Rien ne l'importe, mais "
        "un repertoire mort brouille la lecture — le retirer.")

    source = (RACINE / "backend" / "core" / "bootstrap"
              / "service_registry.py").read_text(encoding="utf-8")
    assert 'key="policy_engine"' not in source, (
        "le ServiceSpec `policy_engine` est revenu")


def test_la_politique_en_vigueur_tient_encore_ce_qui_a_ete_mesure():
    """Le pendant du precedent. La suppression se justifiait par ce
    qu'Aegis dit de ces deux memes actions ; si Aegis changeait d'avis, la
    justification tomberait et devrait etre re-tranchee plutot que
    heritee."""
    import yaml

    config = yaml.safe_load(
        (RACINE / "config" / "security.yaml").read_text(encoding="utf-8"))
    cats = config["action_categories"]
    # La ou `internet_access_allowed` disait « allow », Aegis demande un
    # seuil ; la ou `system_modification_denied` disait « deny », Aegis
    # demande un humain — pas un refus.
    assert cats["network_call"]["min_autonomy_for_auto_allow"] == "high"
    assert cats["system_config"]["mandatory_validation"] is True
