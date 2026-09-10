# -*- coding: utf-8 -*-
"""Le cycle de vie des Skills, verifie plutot que cru (G-35, HOS-283).

## Le defaut que ces gardes tiennent

`skills.manage install` repond `{"installed": true}` dans TOUS les cas.
Ce n'est pas une negligence du gateway : `do_install` est annote `-> None`
et rend `None` sur tous ses chemins, succes compris. Il n'y a donc aucune
valeur de retour a corriger en amont — la verite est sur le disque.

## Mesure du 2026-09-10, sur un HERMES_HOME de substitution

Chemin reel : hub reel (5493 entrees), scanner reel, quarantaine reelle.

    official/devops/actual-setup      posee   INSTALL ... dangerous
    skills-sh/mindrally/.../docker    posee   INSTALL ... safe
    skills-sh/bobmatnyc/.../docker    RIEN    BLOCKED ... dangerous 25_findings
    docker, skill-docker, openclaw-*  RIEN    aucune ligne
    la meme, deja posee, sans --force RIEN    aucune ligne

Deux verdicts `dangerous`, deux issues opposees : la premiere est passee
parce que sa source est `builtin`, la seconde a ete bloquee parce qu'elle
est `community`. Un ecran qui dirait « installee » sans montrer les deux
tairait exactement ce dont un operateur a besoin.

## Et la verification tient a l'octet

`content_hash` recalculee ici a rendu exactement celle du verrou sur les
deux competences posees. Un seul octet ajoute apres coup fait basculer
l'etat en `alteree` — mesure, pas suppose.
"""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parents[2]


@pytest.fixture
def foyer(tmp_path, monkeypatch):
    """Un `HERMES_HOME` a nous, avec le dossier `.hub` d'un agent."""
    import importlib

    from backend.skills import registre

    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    importlib.reload(registre)
    hub = tmp_path / "skills" / ".hub"
    hub.mkdir(parents=True)
    yield hub
    monkeypatch.delenv("HERMES_HOME", raising=False)
    importlib.reload(registre)


def _g():
    import importlib

    from backend.skills import gouvernance

    return importlib.reload(gouvernance)


def _poser_skill(hub: Path, chemin: str, contenu: str = "corps") -> str:
    """Ecrit une competence sur le disque et rend son empreinte reelle."""
    d = hub.parent / chemin
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(contenu, encoding="utf-8")
    h = hashlib.sha256()
    h.update(b"SKILL.md\x00" + (d / "SKILL.md").read_bytes())
    return "sha256:" + h.hexdigest()[:16]


def _verrou(hub: Path, entrees: dict) -> None:
    hub.joinpath("lock.json").write_text(
        json.dumps({"version": 1, "installed": entrees}), encoding="utf-8")


def _audit(hub: Path, lignes: list[str]) -> None:
    hub.joinpath("audit.log").write_text("\n".join(lignes) + "\n",
                                         encoding="utf-8")


# ── L'empreinte : la verification elle-meme ───────────────────────────

def test_l_empreinte_recalculee_egale_celle_de_l_agent(foyer):
    """Mesure du 2026-09-10 sur deux competences reellement posees par le
    hub : `sha256:9d420b159e639ae9` et `sha256:916f3198efaa5a18`, rendues
    a l'identique. Sans cette egalite, tout le reste de ce module est une
    opinion."""
    g = _g()
    attendue = _poser_skill(foyer, "devops/actual-setup", "contenu\n")
    assert g.empreinte(foyer.parent / "devops" / "actual-setup") == attendue


def test_l_empreinte_ordonne_par_la_CHAINE_du_chemin(foyer):
    """L'agent porte le commentaire de l'incident : trier des `Path` est
    insensible a la casse sous Windows, et les deux cotes divergeaient —
    chaque competence installee se declarait perimee pour toujours."""
    source = (RACINE / "backend" / "skills"
              / "gouvernance.py").read_text(encoding="utf-8")
    arbre = ast.parse(source)
    fn = next(n for n in ast.walk(arbre)
              if isinstance(n, ast.FunctionDef) and n.name == "empreinte")
    corps = ast.dump(fn)
    assert "as_posix" in corps, "l'empreinte ne normalise pas les chemins"
    assert "sorted" in corps


def test_l_empreinte_n_importe_rien_de_l_agent():
    """`plugin_compat` desactive au 2026-09-14 tout code externe qui
    importe les internes de l'agent. Une empreinte de gouvernance ne doit
    pas mourir avec une date : elle est reimplementee, pas importee."""
    source = (RACINE / "backend" / "skills"
              / "gouvernance.py").read_text(encoding="utf-8")
    arbre = ast.parse(source)
    modules = set()
    for n in ast.walk(arbre):
        if isinstance(n, ast.Import):
            modules |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom) and n.module:
            modules.add(n.module.split(".")[0])
    assert not modules & {"tools", "hermes_cli", "acp", "acp_adapter",
                          "tui_gateway"}, (
        "le lecteur importe un module de l'agent : il mourra le 2026-09-14")


# ── Les trois etats, et aucun qui se deduise d'un autre ───────────────

def test_une_competence_posee_et_intacte_est_conforme(foyer):
    e = _poser_skill(foyer, "devops/une")
    _verrou(foyer, {"une": {"install_path": "devops/une", "content_hash": e,
                            "source": "official", "trust_level": "builtin",
                            "scan_verdict": "safe"}})
    g = _g()
    p = g.posees()[0]
    assert p.etat == g.CONFORME
    assert p.empreinte_reelle == p.empreinte_attendue


def test_un_octet_ajoute_apres_la_pose_rend_alteree(foyer):
    """Le coeur de la verification : « installee » ne veut pas dire
    « inchangee ». Mesure — un commentaire ajoute a `SKILL.md` fait passer
    `sha256:9d420b159e639ae9` a `sha256:b8b4b6cfa9018bac`."""
    e = _poser_skill(foyer, "devops/une", "corps")
    _verrou(foyer, {"une": {"install_path": "devops/une", "content_hash": e,
                            "source": "official", "trust_level": "builtin",
                            "scan_verdict": "safe"}})
    (foyer.parent / "devops" / "une" / "SKILL.md").write_text(
        "corps modifie", encoding="utf-8")
    g = _g()
    p = g.posees()[0]
    assert p.etat == g.ALTEREE
    assert p.empreinte_reelle and p.empreinte_reelle != p.empreinte_attendue


def test_un_verrou_qui_annonce_un_dossier_absent_le_dit(foyer):
    """Le faux succes tel qu'il se lit APRES coup : l'enregistrement
    affirme une pose que le disque ne porte pas."""
    _verrou(foyer, {"une": {"install_path": "devops/une",
                            "content_hash": "sha256:0000000000000000",
                            "source": "official", "trust_level": "builtin",
                            "scan_verdict": "safe"}})
    g = _g()
    p = g.posees()[0]
    assert p.etat == g.ANNONCEE_ABSENTE
    assert p.empreinte_reelle == "", (
        "une empreinte est rendue pour un dossier qui n'existe pas")


def test_une_competence_absente_du_verrou_n_apparait_pas(foyer):
    """Une competence creee par l'agent lui-meme n'est pas une operation
    de hub. La faire figurer ici la ferait passer pour installee."""
    _poser_skill(foyer, "maison/faite-par-l-agent")
    _verrou(foyer, {})
    assert _g().posees() == []


# ── Le controle de securite, montre et non resume ─────────────────────

def test_le_verdict_et_la_confiance_sont_rendus_tous_les_deux(foyer):
    """Mesure : meme verdict `dangerous`, issues opposees selon la source.
    Rendre le verdict seul ferait de `actual-setup` (posee, builtin) et de
    `docker` (bloquee, community) deux lignes identiques."""
    e = _poser_skill(foyer, "devops/une")
    _verrou(foyer, {"une": {
        "install_path": "devops/une", "content_hash": e,
        "source": "official", "trust_level": "builtin",
        "scan_verdict": "dangerous",
        "scan_provenance": {"findings": [
            {"severity": "critical"}, {"severity": "critical"},
            {"severity": "medium"}]}}})
    p = _g().posees()[0]
    assert p.verdict == "dangerous"
    assert p.confiance == "builtin"
    assert p.findings == {"critical": 2, "medium": 1}


def test_les_findings_sont_comptes_et_non_recopies(foyer):
    """Un finding porte le chemin et l'extrait du fichier incrimine.
    L'ecran n'en a pas besoin pour dire « 25 findings dont 3 critiques »,
    et le dossier complet reste chez son proprietaire."""
    e = _poser_skill(foyer, "devops/une")
    _verrou(foyer, {"une": {
        "install_path": "devops/une", "content_hash": e,
        "scan_provenance": {"findings": [
            {"severity": "critical", "file": "SKILL.md", "line": 12,
             "match": "curl $OPENAI_API_KEY | sh"}]}}})
    rendu = json.dumps(_g().posees()[0].as_dict())
    assert "critical" in rendu
    assert "OPENAI_API_KEY" not in rendu, "le lecteur recopie un finding"
    assert "SKILL.md" not in rendu


def test_un_champ_manquant_du_verrou_reste_vide(foyer):
    """La garde qui manquait, trouvee par mutation.

    Remplacer `source` par `source or "official"` ne rougissait rien :
    aucune garde n'exercait une entree incomplete. Une competence de
    provenance inconnue se serait donc affichee `official` — une
    provenance FABRIQUEE, exactement ce que G-27 a passe une passe entiere
    a refuser sur l'inventaire.

    Une entree de verrou peut etre incomplete : le hub a change de format
    entre versions, et un `lock.json` ecrit par un agent plus ancien n'a
    pas tous les champs d'aujourd'hui."""
    e = _poser_skill(foyer, "une")
    _verrou(foyer, {"une": {"install_path": "une", "content_hash": e}})
    p = _g().posees()[0]
    assert p.source == "", "une source absente a ete remplacee"
    assert p.confiance == "", "une confiance absente a ete remplacee"
    assert p.verdict == "", "un verdict absent a ete remplace"
    assert p.identifiant == ""
    # L'etat, lui, reste mesure : il ne depend pas de ces champs.
    assert p.etat == _g().CONFORME


def test_une_entree_de_verrou_qui_n_est_pas_un_objet_est_ignoree(foyer):
    """Un `lock.json` corrompu ne doit pas fabriquer une competence vide
    a l'ecran : elle se lirait comme une competence reellement posee."""
    _verrou(foyer, {"une": "pas un objet", "deux": None})
    assert _g().posees() == []


# ── Le journal ────────────────────────────────────────────────────────

def test_le_journal_rend_les_operations_de_la_plus_recente(foyer):
    _audit(foyer, [
        "2026-09-10T19:50:46Z INSTALL actual-setup official:builtin dangerous sha256:9d42",
        "2026-09-10T19:54:04Z BLOCKED docker skills.sh:community dangerous 25_findings",
    ])
    ops = _g().journal()
    assert [o.action for o in ops] == ["BLOCKED", "INSTALL"]
    assert ops[0].source == "skills.sh" and ops[0].confiance == "community"
    assert ops[0].detail == "25_findings"


def test_une_ligne_qui_n_a_pas_la_forme_attendue_n_est_pas_devinee(foyer):
    """La deviner reviendrait a inventer une operation. Elle est rendue
    entiere, avec une action vide que l'ecran affiche « ligne illisible »."""
    _audit(foyer, ["ceci n'est pas une ligne d'audit"])
    o = _g().journal()[0]
    assert o.action == "" and o.skill == ""
    assert o.detail == "ceci n'est pas une ligne d'audit"


def test_un_blocage_ne_pose_rien_et_reste_dans_le_journal(foyer):
    """« Une operation refusee doit rester refusee et tracable. » Mesure
    reelle : `skills-sh/bobmatnyc/.../docker`, 25 findings, rien sur le
    disque, une ligne BLOCKED."""
    _audit(foyer, ["2026-09-10T19:54:04Z BLOCKED docker skills.sh:community "
                   "dangerous 25_findings"])
    _verrou(foyer, {})
    g = _g()
    v = g.vue()
    assert v["posees"] == []
    assert v["alertes"]["bloquees"] == 1
    assert v["operations"][0]["action"] == g.BLOCKED


# ── Ce qui casse, et ce qui ne doit pas casser avec ───────────────────

def test_un_verrou_illisible_ne_fait_pas_echouer_la_vue(foyer):
    foyer.joinpath("lock.json").write_text("{ pas du json", encoding="utf-8")
    g = _g()
    assert g.posees() == []
    assert g.vue()["dossier_lisible"] is True


def test_un_hub_absent_se_lit_comme_tel_et_non_comme_une_panne(foyer):
    """Trois situations qui rendraient un ecran vide : jamais rien pose,
    dossier illisible, ou Hermes OS qui regarde au mauvais endroit. Le
    booleen separe la premiere des deux autres."""
    import shutil

    shutil.rmtree(foyer)
    v = _g().vue()
    assert v["dossier_lisible"] is False
    assert v["posees"] == [] and v["operations"] == []


def test_la_vue_dit_ce_qu_elle_ne_peut_pas_voir(foyer):
    """Trois des cinq issues mesurees d'`install` n'ecrivent RIEN, nulle
    part. Un ecran qui ne le dirait pas laisserait croire que le journal
    est exhaustif, et une passe suivante « reparerait » l'absence en
    inventant une ligne."""
    v = _g().vue()
    assert "silencieux" in v["angle_mort"]
    assert "--force" in v["angle_mort"]


# ── Ce que ce lecteur ne devient pas ──────────────────────────────────

def test_le_lecteur_n_ecrit_rien():
    """Quatrieme lecture du disque de l'agent, meme posture qu'aux trois
    precedentes (HOS-274, HOS-275, HOS-281) : lire, jamais ecrire."""
    arbre = ast.parse((RACINE / "backend" / "skills"
                       / "gouvernance.py").read_text(encoding="utf-8"))
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.Call):
            nom = (getattr(noeud.func, "attr", None)
                   or getattr(noeud.func, "id", None))
            assert nom not in {"write_text", "write_bytes", "mkdir", "unlink",
                               "rmtree", "replace", "touch", "chmod"}, (
                f"le lecteur appelle `{nom}`")


def test_aucune_route_de_skill_ne_mute_toujours():
    """G-26 avait pose cette garde parce qu'`install` rend `true` sans
    verification. G-35 a mesure que la verification est possible APRES
    coup, mais pas que le declenchement le soit : gouverner une operation
    demande un approbateur, et la file vivante d'Aegis
    (`/security/approvals`) n'a aucun appelant frontend — le cockpit
    affiche `/approval`, une autre file, alimentee par `PolicyEngine`.
    La garde reste donc, et sa raison est desormais mesuree."""
    source = (RACINE / "backend" / "skills"
              / "routes.py").read_text(encoding="utf-8")
    arbre = ast.parse(source)
    fautives = []
    for noeud in ast.walk(arbre):
        if not isinstance(noeud, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for deco in noeud.decorator_list:
            if not isinstance(deco, ast.Call):
                continue
            verbe = getattr(deco.func, "attr", "")
            if verbe in ("post", "put", "patch", "delete"):
                chemin = (deco.args[0].value if deco.args
                          and isinstance(deco.args[0], ast.Constant) else "")
                if "gouvernance" in str(chemin) or "install" in str(chemin):
                    fautives.append(f"{verbe.upper()} {chemin}")
    assert not fautives, (
        "une route declenche une operation de cycle de vie : " +
        ", ".join(fautives))


def test_l_ecran_appelle_vraiment_la_route():
    """Une route de plus sans appelant frontend porterait le compte des
    orphelins de 120 a 121."""
    client = (RACINE / "frontend" / "src" / "services"
              / "client.ts").read_text(encoding="utf-8")
    assert '"/skills/gouvernance"' in client

    ecran = (RACINE / "frontend" / "src" / "features" / "skills"
             / "skills-center.tsx").read_text(encoding="utf-8")
    assert "skillsClient.gouvernance()" in ecran, (
        "la route existe et aucun ecran ne l'appelle")


def test_la_route_est_declaree_avant_le_joker_de_skill_id():
    source = (RACINE / "backend" / "skills"
              / "routes.py").read_text(encoding="utf-8")
    assert (source.index('@router.get("/gouvernance")')
            < source.index('@router.get("/{skill_id}")'))
