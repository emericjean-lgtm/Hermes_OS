# -*- coding: utf-8 -*-
"""La pose d'une Skill, sous l'autorite d'Aegis (G-36, HOS-285).

## Ce que G-35 avait laisse ouvert, et ce que la mesure a tranche

La verification etait acquise. Ce qui manquait etait l'approbateur : Hermes
OS a DEUX files, et le cockpit lisait la mauvaise. Mesure du 2026-09-11 :

                          Aegis                    Policy (HOS-046)
    stockage              SQLite                   dict en memoire
    producteur reel       AegisAgent, sur le       aucun —
                          chemin de requete        `set_policy_engine`
                                                   n'est jamais appele
    survit au redemarrage oui                      non
    lu par le cockpit     NON                      oui

Les deux ne font pas la meme chose et ne sont pas fusionnees. Mais une
seule est branchee, et c'est elle qui garde les actions reelles.

## La chaine, mesuree de bout en bout

Foyer de substitution pour le disque des Skills ; Aegis, sa file SQLite, le
vrai gateway lance par le pont, le scanner de l'agent et le disque sont
reels.

    1. demande                 -> approbation_requise, disque VIDE
    2. la ligne est dans la file d'Aegis (`skill_install`)
    3. refus utilisateur       -> approbation_requise, disque VIDE
    4. accord puis nouvel essai-> posee, `docker` conforme,
                                  sha256:916f3198efaa5a18 des deux cotes
    5. provenance              -> source=skills.sh confiance=community
                                  verdict=safe ; audit : INSTALL docker
    7. processus NEUF          -> la pose ET les decisions sont la ;
                                  l'accord est passe a `used`
    8a. conflit (deja posee)   -> sans_effet, disque inchange
    8b. danger, nom libre      -> bloquee_par_le_scanner, disque VIDE,
                                  audit : BLOCKED docker 25_findings

Le 8b a d'abord rendu `sans_effet` : la competence dangereuse s'appelle
aussi `docker`, et sur un foyer ou ce nom etait pris `do_install` sort sur
« deja installee » AVANT d'atteindre le scanner. On mesurait un conflit en
croyant mesurer une securite.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from backend.security.aegis_engine import AegisDecision, Verdict
from backend.skills import installation

RACINE = Path(__file__).resolve().parents[2]


class _AegisFactice:
    def __init__(self, verdict, raison="raison"):
        self.verdict = verdict
        self.raison = raison
        self.vues: list = []

    def evaluate(self, action):
        self.vues.append(action)
        return AegisDecision(verdict=self.verdict, reason=self.raison,
                             action_type=action.action_type)


@pytest.fixture
def sans_disque(monkeypatch):
    """Un disque qui ne bouge pas, et un runtime qu'on surveille."""
    appels: list = []
    monkeypatch.setattr(installation, "_etat_du_disque", lambda: ({}, []))
    monkeypatch.setattr(installation, "_demander_au_runtime",
                        lambda i: appels.append(i))
    return appels


def _aegis(monkeypatch, verdict, raison="raison"):
    faux = _AegisFactice(verdict, raison)
    monkeypatch.setattr(installation, "_aegis", lambda: faux)
    return faux


# ── L'approbation n'est pas contournable ──────────────────────────────

def test_sans_approbation_rien_n_est_transmis_au_runtime(monkeypatch, sans_disque):
    """La garde centrale. Un `REQUIRE_HUMAN_VALIDATION` doit rendre la main
    AVANT le runtime : le refus est un refus d'ecrire, pas d'afficher."""
    _aegis(monkeypatch, Verdict.REQUIRE_HUMAN_VALIDATION)
    r = installation.installer("official/devops/actual-setup")
    assert r["statut"] == installation.APPROBATION_REQUISE
    assert sans_disque == [], "le runtime a ete sollicite sans approbation"


def test_un_refus_d_aegis_n_ecrit_rien(monkeypatch, sans_disque):
    _aegis(monkeypatch, Verdict.DENY, "hors perimetre")
    r = installation.installer("official/devops/actual-setup")
    assert r["statut"] == installation.REFUSEE
    assert sans_disque == [], "un DENY a laisse passer une demande"


def test_seul_un_ALLOW_atteint_le_runtime(monkeypatch, sans_disque):
    _aegis(monkeypatch, Verdict.ALLOW)
    installation.installer("official/devops/actual-setup")
    assert sans_disque == ["official/devops/actual-setup"]


def test_l_action_soumise_porte_l_identifiant_en_discriminant(monkeypatch,
                                                              sans_disque):
    """Sans discriminant, l'empreinte d'approbation ne hache pas la
    description (HOS-224) : approuver la pose d'une Skill autoriserait
    celle d'une autre."""
    faux = _aegis(monkeypatch, Verdict.REQUIRE_HUMAN_VALIDATION)
    installation.installer("official/devops/actual-setup")
    action = faux.vues[0]
    assert action.action_type == installation.ACTION_AEGIS
    assert ("identifiant", "official/devops/actual-setup") in action.discriminants


def test_un_identifiant_vide_ne_soumet_meme_pas(monkeypatch, sans_disque):
    faux = _aegis(monkeypatch, Verdict.ALLOW)
    assert installation.installer("  ")["statut"] == installation.REFUSEE
    assert faux.vues == [] and sans_disque == []


# ── Le resultat vient du disque, jamais de la reponse ─────────────────

def _disque(monkeypatch, avant, apres):
    etats = iter([avant, apres])
    monkeypatch.setattr(installation, "_etat_du_disque", lambda: next(etats))
    monkeypatch.setattr(installation, "_demander_au_runtime", lambda i: None)


def _posee(nom, etat="conforme"):
    return {nom: {"nom": nom, "etat": etat, "empreinte_attendue": "sha256:a",
                  "empreinte_reelle": "sha256:a" if etat == "conforme" else "sha256:b"}}


def test_une_clef_neuve_et_conforme_est_une_pose(monkeypatch):
    _aegis(monkeypatch, Verdict.ALLOW)
    _disque(monkeypatch, ({}, []), (_posee("docker"), ["t INSTALL docker"]))
    r = installation.installer("skills-sh/mindrally/skills/docker")
    assert r["statut"] == installation.POSEE
    assert r["skill"] == "docker"


def test_une_clef_neuve_qui_ne_verifie_pas_n_est_pas_une_pose(monkeypatch):
    """Le faux succes sous une autre forme : le verrou annonce, le disque
    dit autre chose. Rendre `posee` ici serait croire l'enregistrement
    plutot que l'empreinte."""
    _aegis(monkeypatch, Verdict.ALLOW)
    _disque(monkeypatch, ({}, []), (_posee("docker", "alteree"), []))
    r = installation.installer("x/docker")
    assert r["statut"] == installation.SANS_EFFET


def test_une_ligne_BLOCKED_neuve_dit_le_scanner(monkeypatch):
    """L'accord humain autorise la DEMANDE ; le scanner garde la POSE.
    Mesure : `skills-sh/bobmatnyc/.../docker`, 25 findings, disque vide."""
    _aegis(monkeypatch, Verdict.ALLOW)
    _disque(monkeypatch, ({}, []),
            ({}, ["2026-09-11T03:00:00Z BLOCKED docker"]))
    r = installation.installer("skills-sh/bobmatnyc/claude-mpm-skills/docker")
    assert r["statut"] == installation.BLOQUEE_PAR_LE_SCANNER


def test_rien_sur_le_disque_est_un_sans_effet(monkeypatch):
    """Le conflit mesure : deja posee, sans `--force`. Le runtime rend
    `installed: true` et n'ecrit ni competence ni ligne d'audit."""
    _aegis(monkeypatch, Verdict.ALLOW)
    avant = (_posee("docker"), ["t INSTALL docker"])
    _disque(monkeypatch, avant, avant)
    r = installation.installer("skills-sh/mindrally/skills/docker")
    assert r["statut"] == installation.SANS_EFFET
    assert "rien" in r["raison"]


def test_une_pose_deja_presente_n_est_pas_recomptee(monkeypatch):
    """Une competence presente AVANT n'est pas une clef neuve. La compter
    ferait passer un conflit pour une reussite."""
    _aegis(monkeypatch, Verdict.ALLOW)
    _disque(monkeypatch, (_posee("docker"), []), (_posee("docker"), []))
    assert installation.installer("x")["statut"] == installation.SANS_EFFET


def test_une_erreur_du_runtime_relit_quand_meme_le_disque(monkeypatch):
    """Un appel qui echoue APRES avoir ecrit laisserait sinon une pose
    invisible — et Hermes OS en retard sur l'etat de l'agent, qui est la
    pire des deux incoherences (services/mutations_agent)."""
    _aegis(monkeypatch, Verdict.ALLOW)
    etats = iter([({}, []), (_posee("docker"), ["t INSTALL docker"])])
    monkeypatch.setattr(installation, "_etat_du_disque", lambda: next(etats))
    monkeypatch.setattr(installation, "_demander_au_runtime",
                        lambda i: "timeout")
    r = installation.installer("x")
    assert r["statut"] == installation.POSEE
    assert r["raison"] == "timeout"


def test_le_module_ne_lit_jamais_le_booleen_du_runtime():
    """`skills.manage install` rend `installed: true` dans tous les cas, y
    compris apres un blocage du scanner. Le lire serait le faux succes que
    cette serie demonte depuis G-26."""
    source = (RACINE / "backend" / "skills"
              / "installation.py").read_text(encoding="utf-8")
    arbre = ast.parse(source)
    litteraux = {n.value for n in ast.walk(arbre)
                 if isinstance(n, ast.Constant) and isinstance(n.value, str)}
    assert "installed" not in litteraux, (
        "le module lit le booleen du runtime")


def test_le_module_n_ecrit_pas_lui_meme_sous_le_foyer_de_l_agent():
    """L'agent possede ses Skills : Hermes OS ne telecharge rien, ne scanne
    rien, n'ecrit rien. Il demande."""
    arbre = ast.parse((RACINE / "backend" / "skills"
                       / "installation.py").read_text(encoding="utf-8"))
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.Call):
            nom = (getattr(noeud.func, "attr", None)
                   or getattr(noeud.func, "id", None))
            assert nom not in {"write_text", "write_bytes", "mkdir", "unlink",
                               "rmtree", "copy2", "copytree"}, (
                f"le module appelle `{nom}`")


# ── La politique, et la file qui la porte ─────────────────────────────

def test_skill_install_exige_toujours_un_humain():
    """`mandatory_validation` — jamais auto-autorise, quel que soit
    `autonomy_level`. G-35 a mesure que le scanner laisse passer un verdict
    `dangerous` sur une source `builtin` : `actual-setup` est posee avec
    cinq findings critiques dont un `env_exfil_curl`."""
    import yaml

    config = yaml.safe_load(
        (RACINE / "config" / "security.yaml").read_text(encoding="utf-8"))
    categorie = config["action_categories"][installation.ACTION_AEGIS]
    assert categorie["mandatory_validation"] is True
    assert categorie["mutating"] is True
    # `path_based: false` : la cible est un identifiant de hub, pas un
    # chemin. La marquer `path_based` la ferait refuser faute de
    # `target_path`, avant meme d'atteindre l'humain.
    assert categorie["path_based"] is False


def test_la_pose_est_declaree_dans_les_mutations_connues():
    """Une methode absente de `MUTATIONS_CONNUES` n'est pas demandable."""
    from backend.bridge.hermes_agent_bridge import MUTATIONS_CONNUES

    assert "skills.manage" in MUTATIONS_CONNUES
    assert "skills" in MUTATIONS_CONNUES["skills.manage"]


def test_le_cockpit_lit_la_file_d_aegis_et_non_celle_de_policy():
    """Le defaut que G-36 ferme. Le cockpit lisait `/approval`, servie par
    `backend/policy/` — un dictionnaire en memoire dont
    `set_policy_engine` n'est jamais appele. Il annoncait « file
    d'approbation vide » par construction, pendant qu'Aegis accumulait des
    demandes reelles : mesure du 2026-09-11, 206 lignes `pending` du
    2026-08-10 au 2026-09-02, qu'aucun ecran ne pouvait montrer."""
    client = (RACINE / "frontend" / "src" / "services"
              / "client.ts").read_text(encoding="utf-8")
    debut = client.index("export const governanceClient")
    bloc = client[debut:debut + 2000]
    assert '"/security/approvals"' in bloc, (
        "le client ne lit pas la file d'Aegis")
    assert 'approvals: () => fetchJSON<unknown>("/approval")' not in bloc, (
        "le client lit encore la file sans producteur")


def test_approuver_envoie_un_accord_et_rejeter_un_refus():
    """La garde qui manquait, trouvee par mutation.

    Le composant est gardé cote ecran (`governance-center.test.tsx` verifie
    que « Approuver » appelle bien la mutation d'approbation). Mais la
    decision REELLEMENT appliquee se joue un etage plus bas : les deux
    methodes du client visent la meme route et ne different que par un
    booleen. Inverser ce booleen donne un bouton indiscernable d'un bouton
    correct — jusqu'au jour ou une pose refusee s'installe.

    Aucun test d'ecran ne peut l'attraper : il simule justement le client.
    """
    client = (RACINE / "frontend" / "src" / "services"
              / "client.ts").read_text(encoding="utf-8")
    debut = client.index("export const governanceClient")
    bloc = client[debut:debut + 2500]

    def corps(nom: str) -> str:
        i = bloc.index(f"  {nom}: (id: string) =>")
        j = bloc.index("}),", i)
        return bloc[i:j]

    assert "approved: true" in corps("approve"), (
        "`approve` n'envoie pas un accord")
    assert "approved: false" in corps("reject"), (
        "`reject` n'envoie pas un refus")
    assert "approved: false" not in corps("approve"), (
        "`approve` envoie un refus : le bouton applique l'inverse de ce "
        "qu'il annonce")


def test_personne_ne_declenche_une_pose_sans_passer_par_le_module():
    """Le vrai joint est la route. Une seconde voie d'installation
    contournerait Aegis sans que rien ne le dise."""
    routes = (RACINE / "backend" / "skills"
              / "routes.py").read_text(encoding="utf-8")
    arbre = ast.parse(routes)
    for noeud in ast.walk(arbre):
        if not isinstance(noeud, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        verbes = {getattr(d.func, "attr", "") for d in noeud.decorator_list
                  if isinstance(d, ast.Call)}
        if not verbes & {"post", "put", "patch", "delete"}:
            continue
        appels = {getattr(c.func, "attr", None) for c in ast.walk(noeud)
                  if isinstance(c, ast.Call)}
        if "installer" in appels:
            continue
        assert "demander_mutation" not in appels, (
            f"`{noeud.name}` demande une mutation sans passer par "
            "`installation.installer`")


def test_les_topics_de_pose_sont_declares():
    """Un evenement non declare est livre quand meme, avec un
    avertissement, et aucun client ne peut le filtrer."""
    from backend.core.event_topics import SUBSYSTEM_TOPICS

    for suffixe in ("demandee", "en_attente", "refusee", "resultat"):
        assert f"skills.installation.{suffixe}" in SUBSYSTEM_TOPICS
