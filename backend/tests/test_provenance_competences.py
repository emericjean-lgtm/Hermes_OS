# -*- coding: utf-8 -*-
"""D'ou vient une competence, et ce qu'on refuse d'en dire (G-27, HOS-275).

## Le contrat mesure sur le runtime v0.21.0

Trois fichiers, tenus par l'agent sous `HERMES_HOME/skills`, portent tout ce
qui est reellement persistant :

    .bundled_manifest   69 entrees `nom:hash` — 69/69 encore intactes
    .hub/lock.json      VIDE : aucune competence n'est passee par le hub
    .usage.json         75 enregistrements, dont 5 `created_by: "agent"`

La chaine complete a ete demontree sur un `HERMES_HOME` de substitution :
creation au premier plan -> `created_by: None` ; creation sous
`BACKGROUND_REVIEW` -> `created_by: "agent"` ; **un nouveau processus relit
les deux**. Persistance et redemarrage acquis.

Sur l'installation reelle : 60 systeme intactes, 4 generees par l'agent,
1 conflit.

## Les trois refus

**« Utilisateur » n'est pas disponible.** `created_by: null` couvre a la fois
« creee au premier plan » et « aucune origine enregistree ». Rien ne les
separe, donc la categorie s'appelle `sans_marqueur` et n'affirme rien.

**« Apprise » et « approuvee » n'existent pas.** Aucun champ ne les porte, et
la file d'approbation n'a jamais servi (G-26).

**La correlation a un Run est impossible.** `skill_manage` transmet bien
`task_id` et `session_id`, mais `_apply` n'ecrit que `created_by` : les deux
partent dans le hook `on_skill_lifecycle`, consomme par le relais de
metriques partagees qui « emet un fait sans son identite locale ». Mesure :
**0 des 75 enregistrements** les porte, et `telemetry/shared_metrics` ne
contient aucun nom de competence — seulement des compteurs a dimensions
bucketisees.

## Le piege que ces tests fixent

`skill_usage.is_agent_created()` ne lit **jamais** `created_by` : il rend
« ni bundled ni hub ». Mesure sur la substitution — une competence creee au
premier plan (`created_by: None`) en ressort `True`, pendant que
`list_agent_created_skill_names()`, qui lit l'enregistrement, l'exclut a
juste titre. Deux fonctions voisines, deux methodes opposees. La provenance
se lit dans l'enregistrement, jamais dans une localisation.
"""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

import pytest

from backend.skills import provenance as prov

RACINE = Path(__file__).resolve().parents[2]


# ── Un foyer de substitution, pour ne rien mesurer d'invente ──────────

def _empreinte(dossier: Path) -> str:
    h = hashlib.md5()
    for chemin in sorted(p for p in dossier.rglob("*") if p.is_file()):
        h.update(str(chemin.relative_to(dossier)).encode("utf-8"))
        h.update(chemin.read_bytes())
    return h.hexdigest()


def _poser(base: Path, dossier: str, nom: str | None = None) -> Path:
    d = base / dossier
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(
        f"---\nname: {nom or dossier}\ndescription: sonde\n---\n\nCorps.\n",
        encoding="utf-8")
    return d


@pytest.fixture
def foyer(tmp_path, monkeypatch):
    """Un `HERMES_HOME` a nous, pour que rien ne touche celui de l'agent."""
    import importlib

    from backend.skills import registre

    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    importlib.reload(registre)
    (tmp_path / "skills").mkdir()
    yield tmp_path / "skills"
    monkeypatch.delenv("HERMES_HOME", raising=False)
    importlib.reload(registre)


def _ecrire_usage(base: Path, enregistrements: dict) -> None:
    (base / ".usage.json").write_text(
        json.dumps(enregistrements, ensure_ascii=False), encoding="utf-8")


# ── Ce que la provenance affirme, et sur quoi ─────────────────────────

def test_une_competence_generee_est_lue_dans_l_enregistrement(foyer):
    """`created_by: "agent"` est ECRIT par `skill_manage` quand l'origine
    d'ecriture est la revue de fond. C'est un fait enregistre, pas une
    deduction — et c'est le seul qui autorise « generee »."""
    _poser(foyer, "sonde")
    _ecrire_usage(foyer, {"sonde": {"created_by": "agent"}})
    p = prov.provenance("sonde", foyer / "sonde")
    assert p.categorie == prov.GENEREE_PAR_L_AGENT
    assert ".usage.json" in p.preuve, "la categorie doit nommer sa source"


def test_created_by_nul_ne_devient_jamais_utilisateur(foyer):
    """Le refus central de G-27.

    `null` couvre « creee au premier plan, donc a l'utilisateur » ET « aucune
    origine n'a jamais ete enregistree ». Les deux produisent le meme octet.
    Dire « utilisateur » serait choisir, et choisir serait inferer."""
    _poser(foyer, "sonde")
    _ecrire_usage(foyer, {"sonde": {"created_by": None}})
    p = prov.provenance("sonde", foyer / "sonde")
    assert p.categorie == prov.SANS_MARQUEUR
    assert "utilisateur" not in p.categorie
    assert prov.SANS_MARQUEUR in prov.CATEGORIES


def test_une_competence_que_rien_ne_nomme_reste_inconnue(foyer):
    """« Inconnue » est une reponse, pas un echec — et jamais un defaut
    silencieux vers « locale »."""
    _poser(foyer, "sonde")
    _ecrire_usage(foyer, {})
    assert prov.provenance("sonde", foyer / "sonde").categorie == prov.INCONNUE


def test_aucune_categorie_hors_de_la_liste_bornee(foyer):
    """Une categorie inventee au fil de l'eau redeviendrait une affirmation
    d'interface. La liste est fermee, et le test la ferme."""
    _poser(foyer, "a")
    _poser(foyer, "b")
    _ecrire_usage(foyer, {"a": {"created_by": "quelque-chose-de-neuf"},
                          "b": {"created_by": "installed"}})
    for nom in ("a", "b", "absente"):
        assert prov.provenance(nom, foyer / nom).categorie in prov.CATEGORIES


# ── L'empreinte : une modification directe se voit ────────────────────

def test_une_competence_systeme_intacte_est_prouvee_par_ses_octets(foyer):
    """La categorie ne depend d'aucune declaration : elle recalcule
    l'empreinte du dossier et la compare a celle que la synchronisation a
    enregistree. C'est ce qui la rend refutable."""
    d = _poser(foyer, "sonde")
    (foyer / ".bundled_manifest").write_text(
        f"sonde:{_empreinte(d)}\n", encoding="utf-8")
    p = prov.provenance("sonde", d)
    assert p.categorie == prov.SYSTEME_INTACTE


def test_un_skill_md_modifie_hors_workflow_est_detecte(foyer):
    """Le point 8 du brief. Editer le fichier a la main, sans passer par
    `skill_manage`, ne laisse aucune trace dans `.usage.json` — mais change
    les octets, et l'empreinte d'origine ne colle plus."""
    d = _poser(foyer, "sonde")
    (foyer / ".bundled_manifest").write_text(
        f"sonde:{_empreinte(d)}\n", encoding="utf-8")
    assert prov.provenance("sonde", d).categorie == prov.SYSTEME_INTACTE

    (d / "SKILL.md").write_text(
        "---\nname: sonde\ndescription: sonde\n---\n\nAutre chose.\n",
        encoding="utf-8")
    p = prov.provenance("sonde", d)
    assert p.categorie == prov.SYSTEME_MODIFIEE
    assert "/" in p.preuve, "la preuve doit montrer les deux empreintes"


def test_sans_dossier_l_integrite_n_est_pas_supposee(foyer):
    """Ne pas pouvoir verifier n'est pas « verifie ». Une competence du
    manifeste dont on n'a pas le dossier reste `inconnue`."""
    _poser(foyer, "sonde")
    (foyer / ".bundled_manifest").write_text("sonde:abcdef\n", encoding="utf-8")
    assert prov.provenance("sonde", None).categorie == prov.INCONNUE


def test_un_manifeste_sans_empreinte_ne_prouve_rien(foyer):
    """Les manifestes v1 ne portent qu'un nom. Le nom seul dit « la
    synchronisation l'a posee un jour », pas « personne n'y a touche »."""
    d = _poser(foyer, "sonde")
    (foyer / ".bundled_manifest").write_text("sonde\n", encoding="utf-8")
    assert prov.provenance("sonde", d).categorie == prov.INCONNUE


# ── Le conflit de clef, rendu tel quel ────────────────────────────────

def test_deux_enregistrements_pour_un_dossier_ne_se_departagent_pas(foyer):
    """Mesure sur l'installation reelle : `documentation-verification`
    (`created_by: "agent"`) et `Documentation & Identity Verification`
    (`created_by: null`) designent le meme dossier.

    Preferer l'un serait exactement l'inference que ce module refuse. Les
    deux valeurs sortent, et l'ecran les montre."""
    d = _poser(foyer, "sonde-dossier", nom="Sonde Lisible")
    _ecrire_usage(foyer, {"Sonde Lisible": {"created_by": None},
                          "sonde-dossier": {"created_by": "agent"}})
    p = prov.provenance("Sonde Lisible", d)
    assert p.categorie == prov.CONFLIT
    assert p.conflit is not None and set(p.conflit) == {"None", "agent"}


def test_deux_enregistrements_concordants_ne_sont_pas_un_conflit(foyer):
    """Un conflit est un DESACCORD. Deux enregistrements qui disent la meme
    chose n'en sont pas un — sans quoi la categorie crierait au loup sur
    toute competence dont le dossier differe du nom."""
    d = _poser(foyer, "sonde-dossier", nom="Sonde Lisible")
    _ecrire_usage(foyer, {"Sonde Lisible": {"created_by": "agent"},
                          "sonde-dossier": {"created_by": "agent"}})
    assert prov.provenance("Sonde Lisible", d).categorie == prov.GENEREE_PAR_L_AGENT


# ── Ce que Hermes OS ne devient pas ───────────────────────────────────

def test_la_provenance_n_ecrit_rien():
    """Meme garde que `vue_skills` et `vue_agent` : lire la provenance de
    l'agent ne doit jamais devenir la tenir."""
    arbre = ast.parse((RACINE / "backend" / "skills"
                       / "provenance.py").read_text(encoding="utf-8"))
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.Call):
            nom = (getattr(noeud.func, "attr", None)
                   or getattr(noeud.func, "id", None))
            assert nom not in {"write_text", "write_bytes", "mkdir", "unlink",
                               "rmtree", "replace", "touch"}, (
                f"la provenance appelle `{nom}` : elle ecrirait chez l'agent")


def test_la_provenance_ne_devient_pas_une_seconde_verite():
    """`hermes.db` porte une table `skills` **vide**, avec une colonne
    `source_task_id`. La remplir avec les competences de l'agent en ferait
    une seconde verite — celle que HOS-274 est alle fermer."""
    source = (RACINE / "backend" / "skills"
              / "provenance.py").read_text(encoding="utf-8")
    arbre = ast.parse(source)
    litteraux = {n.value for n in ast.walk(arbre)
                 if isinstance(n, ast.Constant) and isinstance(n.value, str)}
    for interdit in ("INSERT", "hermes.db", "sqlite", "session.add"):
        assert not any(interdit.lower() in x.lower() for x in litteraux
                       if len(x) < 200), f"la provenance persiste `{interdit}`"


def test_le_piege_is_agent_created_n_est_pas_utilise():
    """Il ne lit jamais `created_by` : il rend « ni bundled ni hub ». Mesure
    — une competence creee au premier plan en ressort `True`. S'appuyer
    dessus ferait passer une competence de l'utilisateur pour une generee."""
    for module in ("backend/skills/provenance.py", "backend/skills/routes.py",
                   "backend/skills/registre.py"):
        source = (RACINE / module).read_text(encoding="utf-8")
        arbre = ast.parse(source)
        appels = {getattr(n.func, "attr", None) or getattr(n.func, "id", None)
                  for n in ast.walk(arbre) if isinstance(n, ast.Call)}
        assert "is_agent_created" not in appels, (
            f"{module} appelle `is_agent_created`, qui deduit de la "
            "localisation et non de l'enregistrement")


# ── La correlation, refusee et dite ───────────────────────────────────

def test_la_provenance_d_une_competence_installee_ne_porte_aucun_run():
    """Mesure G-27 : 0 des 75 enregistrements de l'agent porte `task_id` ou
    `session_id`. Les deux traversent le hook `on_skill_lifecycle`, consomme
    par un relais qui agrege sans identite locale.

    **Rescopee par G-34.** Cette garde s'appelait « aucune competence n'est
    rattachee a un Run » — un titre que G-33 a rendu faux sans que rien ne
    rougisse, parce qu'il decrivait le depot entier alors que la mesure ne
    portait que sur l'INVENTAIRE. La relation existe depuis, sur les
    mutations observees (`/skills/observations`), et elle ne vient pas
    d'ici : ni des fichiers de la competence, ni d'une deduction.

    Ce qu'elle tient reste exactement ce qu'elle tenait : `Provenance` ne
    gagne pas de champ de correlation, parce que rien dans les fichiers
    d'une competence installee ne nommerait le Run qui l'a posee."""
    arbre = ast.parse((RACINE / "backend" / "skills"
                       / "provenance.py").read_text(encoding="utf-8"))
    noms = {n.target.id for n in ast.walk(arbre)
            if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name)}
    noms |= {t.id for n in ast.walk(arbre) if isinstance(n, ast.Assign)
             for t in n.targets if isinstance(t, ast.Name)}
    assert "CORRELATION_IMPOSSIBLE" in noms
    assert not {"RUN_ID", "TASK_ID", "SESSION_ID"} & noms

    champs = {n.target.id for c in ast.walk(arbre)
              if isinstance(c, ast.ClassDef) and c.name == "Provenance"
              for n in c.body if isinstance(n, ast.AnnAssign)
              and isinstance(n.target, ast.Name)}
    assert not {"run", "run_id", "task_id", "session_id"} & champs, (
        "un champ de correlation existe alors que rien ne le remplit")


def test_la_route_dit_pourquoi_l_inventaire_ne_porte_pas_de_run():
    """Une absence sans explication se lit comme un oubli, et la passe
    suivante la « repare » en inventant un champ.

    G-34 ajoute la moitie qui manquait : l'ecran doit aussi dire OU la
    relation existe. Sans cela, l'explication de G-27 se lit comme « il n'y
    en a nulle part », ce qui a cesse d'etre vrai."""
    source = (RACINE / "backend" / "skills"
              / "routes.py").read_text(encoding="utf-8")
    assert "correlation_impossible" in source

    ecran = (RACINE / "frontend" / "src" / "features" / "skills"
             / "skills-center.tsx").read_text(encoding="utf-8")
    assert "correlation_impossible" in ecran, (
        "l'ecran tait pourquoi l'inventaire n'a pas de Run")
    assert "skillsClient.observations()" in ecran, (
        "l'ecran explique l'absence sans montrer ou la relation existe")


def test_l_ecran_ne_nomme_aucune_categorie_absente_du_backend():
    """Une etiquette « apprise » ou « approuvee » cote interface serait
    exactement l'affirmation non soutenue que le brief interdit."""
    ecran = (RACINE / "frontend" / "src" / "features" / "skills"
             / "skills-center.tsx").read_text(encoding="utf-8")
    debut = ecran.index("function EtiquetteProvenance")
    corps = ecran[debut:debut + 1400]
    for categorie in prov.CATEGORIES:
        assert categorie in corps, f"l'ecran ignore `{categorie}`"
    for inventee in ("apprise", "approuvee", "approuvée", "utilisateur"):
        assert inventee not in corps.lower(), (
            f"l'ecran affirme « {inventee} », qu'aucun fichier ne porte")


def test_chaque_categorie_rendue_porte_sa_preuve(foyer):
    """Une categorie sans sa source est une affirmation. Toutes en ont une."""
    d = _poser(foyer, "sonde")
    _ecrire_usage(foyer, {"sonde": {"created_by": "agent"}})
    for nom, dossier in (("sonde", d), ("absente", None), ("", None)):
        p = prov.provenance(nom, dossier)
        assert p.preuve and p.preuve.strip(), f"`{nom}` sans preuve"
