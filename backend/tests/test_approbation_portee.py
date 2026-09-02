"""L'empreinte canonique et la portée d'approbation (HOS-224).

## Les deux défauts, mesurés avant d'écrire une ligne

**La description entrait dans l'identité.** Le module le justifiait par
un argument correct — « une approbation pour *Commit on feature/x* ne
doit pas autoriser *Commit on main* » — appuyé sur une hypothèse vraie
pour une partie seulement de ses appelants : *descriptions are generated
by the calling tool, not by a model*. Vrai pour `file_tools` et
`git_tools`. **Faux** pour l'outil MCP `aegis_check` et pour
`POST /api/v1/security/evaluate`.

    « Write to config.json to fix the port »  ->  24aa0d0bf698
    « Write config.json (port fix) »          ->  061db3be665d

Le « oui » de l'humain ne s'appliquait jamais, une seconde demande était
déposée, et rien ne disait pourquoi.

**Le chemin non plus n'était pas canonique.** Quatre écritures du même
fichier — `C:/p/x`, antislash, casse de lecteur, `..` — donnaient quatre
empreintes.

## Et ce qui manquait

Aucune portée. Trente écritures dans un dossier demandaient trente
approbations, ce qui condamne la fonctionnalité à être désactivée.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from sqlalchemy.orm import sessionmaker

from backend.memory.db import init_db, make_engine
from backend.security import approvals as A
from backend.security.empreinte import canoniser_chemin, couvre, empreinte


@pytest.fixture
def session(tmp_path):
    moteur = make_engine(str(tmp_path / "approbations.db"))
    init_db(moteur)
    fabrique = sessionmaker(bind=moteur)
    with fabrique() as ses:
        yield ses


@pytest.fixture
def racine(tmp_path) -> str:
    (tmp_path / "projet" / "src").mkdir(parents=True)
    return str(tmp_path / "projet")


def _accorde(session, chemin, *, action="file_write", description="w", **kw):
    entree = A.record_pending(session, action_type=action, description=description,
                              reason="autonomie trop basse", target_path=chemin)
    return A.decide(session, entree.id, approved=True, **kw)


# ═══ L'empreinte canonique ═══════════════════════════════════════════

def test_le_chemin_a_une_seule_ecriture():
    """Quatre écritures du même fichier donnaient quatre empreintes.

    Sur Windows ce n'est pas un cas de laboratoire : les chemins arrivent
    d'un `Path`, d'une chaîne JSON, d'une saisie.
    """
    reference = empreinte("file_write", "C:/p/config.json")
    for variante in ("C:" + chr(92) + "p" + chr(92) + "config.json",
                     "c:/p/config.json",
                     "C:/p/../p/config.json"):
        assert empreinte("file_write", variante) == reference, variante


def test_l_action_est_repliee_en_minuscules():
    assert empreinte("FILE_WRITE", "/x/a") == empreinte("file_write", "/x/a")


def test_un_chemin_inexistant_reste_canonisable():
    """Une approbation porte souvent sur un fichier à créer.

    Rejeter ce qui ne se résout pas rendrait le cas le plus courant —
    la création — impossible à approuver.
    """
    assert canoniser_chemin("C:/nexiste/pas/encore.txt")


def test_les_discriminants_ne_dependent_pas_de_l_ordre():
    """Sinon on aurait remplacé l'instabilité de la prose par celle
    d'un ordre d'insertion — ce qui n'aurait rien réparé."""
    assert (empreinte("git", "/r", discriminants={"a": 1, "b": 2})
            == empreinte("git", "/r", discriminants={"b": 2, "a": 1}))


def test_la_garantie_d_origine_tient_par_discriminant():
    """« Commit on feature/x » ne doit pas autoriser « commit on main ».

    C'était l'argument du commentaire d'origine, et il est juste. Ce qui
    change, c'est ce qui le porte : un champ nommé, pas une phrase.
    """
    sur = lambda b: empreinte("git_operation", "/r",
                              discriminants={"op": "commit", "branch": b})
    assert sur("feature/x") != sur("main")


def test_commit_et_push_sur_la_meme_branche_different():
    """Sans discriminant d'opération, les cinq écritures git de
    `git_tools` s'effondraient sur `(git_operation, repo_path)`."""
    assert (empreinte("git_operation", "/r",
                      discriminants={"op": "commit", "branch": "main"})
            != empreinte("git_operation", "/r",
                         discriminants={"op": "push", "target": "main"}))


# ═══ Le confinement d'une portée ═════════════════════════════════════

def test_une_portee_couvre_ses_descendants():
    assert couvre("C:/projet", "C:/projet/src/a.py")
    assert couvre("C:" + chr(92) + "projet", "C:/projet/src/a.py")
    assert couvre("C:/projet", "C:/projet")


@pytest.mark.parametrize("evasion", [
    "C:/projet-bis/a.py",       # un `startswith` l'accepterait
    "C:/projet/../autre/a.py",  # remonte au-dessus de la racine
    "C:/autre/a.py",
])
def test_une_portee_ne_s_evade_pas(evasion):
    """`C:/projet-bis` sous `C:/projet` est l'évasion qu'un simple
    `startswith` laisse passer. La comparaison se fait sur des segments
    de chemin, après canonisation des deux côtés."""
    assert not couvre("C:/projet", evasion)


def test_une_portee_ne_remonte_pas():
    assert not couvre("C:/projet/src", "C:/projet/a.py")


# ═══ L'accord exact : rien ne change ═════════════════════════════════

def test_un_accord_exact_reste_a_usage_unique(session, racine):
    """La portée est un ajout, pas un assouplissement du défaut."""
    accord = _accorde(session, racine + "/a.txt")
    assert accord.portee == A.PORTEE_ACTION
    assert accord.usages_restants == 1

    assert A.consume_approval(session, action_type="file_write",
                              target_path=racine + "/a.txt") is not None
    assert A.consume_approval(session, action_type="file_write",
                              target_path=racine + "/a.txt") is None


def test_un_accord_survit_a_une_reformulation(session, racine):
    """Le défaut central, mesuré de bout en bout.

    Le modèle reformule, et le « oui » de l'humain s'applique quand
    même.
    """
    _accorde(session, racine + "/a.txt",
             description="Write to a.txt to fix the port")
    consomme = A.consume_approval(
        session, action_type="file_write", target_path=racine + "/a.txt",
        description="a.txt (correction du port)")
    assert consomme is not None


def test_un_accord_survit_a_une_reecriture_du_chemin(session, racine):
    _accorde(session, racine + "/a.txt")
    autre = (racine + "/a.txt").replace("/", chr(92)).upper()
    assert A.consume_approval(session, action_type="file_write",
                              target_path=autre) is not None


# ═══ La portée ═══════════════════════════════════════════════════════

def test_une_portee_ne_s_obtient_jamais_par_omission(session, racine):
    """« Oui à tout, partout, pour toujours » ne doit pas être ce qu'on
    obtient en cliquant vite."""
    assert _accorde(session, racine + "/a.txt").portee == A.PORTEE_ACTION


def test_une_portee_couvre_une_rafale_sous_sa_racine(session, racine):
    """Trente écritures dans un dossier demandaient trente approbations.

    Une fonctionnalité qui exige trente clics est une fonctionnalité
    désactivée.
    """
    _accorde(session, racine + "/src/x.py", portee=A.PORTEE_ARBORESCENCE,
             portee_racine=racine + "/src", usages=3)
    for nom in ("un.py", "deux.py", "trois.py"):
        assert A.consume_approval(
            session, action_type="file_write",
            target_path=racine + "/src/sous/" + nom) is not None, nom


def test_le_budget_d_une_portee_s_epuise(session, racine):
    """Sans plafond, « oui pour ce dossier » deviendrait une permission
    permanente que personne n'a décidée."""
    _accorde(session, racine + "/src/x.py", portee=A.PORTEE_ARBORESCENCE,
             portee_racine=racine + "/src", usages=2)
    for _ in range(2):
        assert A.consume_approval(session, action_type="file_write",
                                  target_path=racine + "/src/a.py") is not None
    assert A.consume_approval(session, action_type="file_write",
                              target_path=racine + "/src/a.py") is None


def test_une_portee_epuisee_passe_a_used(session, racine):
    """Le statut suit le compteur, il ne le devance pas.

    Passer à USED au premier usage annulerait la portée ; rester
    APPROVED après épuisement la rendrait éternelle.
    """
    accord = _accorde(session, racine + "/src/x.py",
                      portee=A.PORTEE_ARBORESCENCE,
                      portee_racine=racine + "/src", usages=2)
    A.consume_approval(session, action_type="file_write",
                       target_path=racine + "/src/a.py")
    assert A.get_approval(session, accord.id).status == A.ApprovalStatus.APPROVED
    A.consume_approval(session, action_type="file_write",
                       target_path=racine + "/src/b.py")
    assert A.get_approval(session, accord.id).status == A.ApprovalStatus.USED


def test_une_portee_ne_couvre_pas_hors_de_sa_racine(session, racine):
    _accorde(session, racine + "/src/x.py", portee=A.PORTEE_ARBORESCENCE,
             portee_racine=racine + "/src")
    assert A.consume_approval(session, action_type="file_write",
                              target_path=racine + "/autre/a.py") is None


def test_une_portee_ne_couvre_pas_une_autre_action(session, racine):
    """Approuver des écritures dans un dossier n'autorise pas à y
    supprimer. C'est la borne qui compte le plus."""
    _accorde(session, racine + "/src/x.py", portee=A.PORTEE_ARBORESCENCE,
             portee_racine=racine + "/src")
    assert A.consume_approval(session, action_type="file_delete",
                              target_path=racine + "/src/a.py") is None


def test_une_portee_sans_racine_est_refusee(session, racine):
    """Sans racine, elle couvrirait le disque."""
    entree = A.record_pending(session, action_type="file_write", description="w",
                              reason="r", target_path=racine + "/a.txt")
    with pytest.raises(ValueError, match="racine"):
        A.decide(session, entree.id, approved=True,
                 portee=A.PORTEE_ARBORESCENCE)


def test_une_portee_sans_usage_est_refusee(session, racine):
    entree = A.record_pending(session, action_type="file_write", description="w",
                              reason="r", target_path=racine + "/a.txt")
    with pytest.raises(ValueError, match="usage"):
        A.decide(session, entree.id, approved=True,
                 portee=A.PORTEE_ARBORESCENCE,
                 portee_racine=racine, usages=0)


def test_le_budget_est_plafonne(session, racine):
    """Demander mille usages n'en donne pas mille."""
    accord = _accorde(session, racine + "/src/x.py",
                      portee=A.PORTEE_ARBORESCENCE,
                      portee_racine=racine + "/src", usages=100000)
    assert accord.usages_restants == A.MAX_USAGES_PORTEE


def test_une_portee_expire_plus_vite_qu_un_accord(session, racine):
    """Elle autorise davantage, donc elle doit se périmer plus vite."""
    assert A.TTL_PORTEE_MINUTES < A.DEFAULT_TTL_MINUTES

    portee = _accorde(session, racine + "/src/x.py",
                      portee=A.PORTEE_ARBORESCENCE, portee_racine=racine + "/src")
    exact = _accorde(session, racine + "/a.txt")
    assert portee.expires_at < exact.expires_at


def test_une_portee_perimee_ne_couvre_plus(session, racine, monkeypatch):
    from datetime import timedelta

    _accorde(session, racine + "/src/x.py", portee=A.PORTEE_ARBORESCENCE,
             portee_racine=racine + "/src")
    vrai_maintenant = A._now()
    monkeypatch.setattr(A, "_now",
                        lambda: vrai_maintenant + timedelta(minutes=10))
    assert A.consume_approval(session, action_type="file_write",
                              target_path=racine + "/src/a.py") is None


def test_l_accord_exact_est_depense_avant_la_portee(session, racine):
    """Sinon on consommerait le budget d'une portée pour une action qui
    avait déjà son propre « oui »."""
    portee = _accorde(session, racine + "/src/z.py",
                      portee=A.PORTEE_ARBORESCENCE,
                      portee_racine=racine + "/src", usages=5)
    _accorde(session, racine + "/src/a.py")

    A.consume_approval(session, action_type="file_write",
                       target_path=racine + "/src/a.py")
    assert A.get_approval(session, portee.id).usages_restants == 5


def test_une_action_sans_chemin_n_est_jamais_couverte(session, racine):
    """Une portée est une portée *de chemin*.

    L'appliquer à une action qui n'en a pas reviendrait à l'appliquer
    partout.
    """
    _accorde(session, racine + "/src/x.py", portee=A.PORTEE_ARBORESCENCE,
             portee_racine=racine + "/src")
    assert A.consume_approval(session, action_type="file_write",
                              target_path=None) is None


# ═══ Ce que le rapport doit montrer ══════════════════════════════════

def test_le_rapport_montre_la_portee_et_son_budget(session, racine):
    """« Approuvé » ne suffit pas quand la ligne autorise un dossier."""
    accord = _accorde(session, racine + "/src/x.py",
                      portee=A.PORTEE_ARBORESCENCE,
                      portee_racine=racine + "/src", usages=4)
    vue = A.to_dict(accord)
    assert vue["portee"] == A.PORTEE_ARBORESCENCE
    assert vue["usages_restants"] == 4
    assert vue["portee_racine"]


def test_le_rapport_d_un_accord_exact_le_dit_aussi(session, racine):
    assert A.to_dict(_accorde(session, racine + "/a.txt"))["portee"] == A.PORTEE_ACTION


# ═══ Les colonnes s'ajoutent sans migration ══════════════════════════

def test_les_colonnes_de_portee_sont_nullables():
    """`_add_missing_columns` (memory/db.py) n'ajoute au démarrage que
    des colonnes nullables, et refuse bruyamment les autres.

    Une base existante doit gagner ces colonnes sans migration, avec
    `None` partout — c'est-à-dire avec le comportement d'avant.
    """
    table = A.PendingApproval.__table__
    for nom in ("portee", "portee_racine", "usages_restants", "discriminants"):
        assert table.columns[nom].nullable is True, nom


# ═══ Le second moteur d'approbation reste débranché ══════════════════

def test_le_moteur_de_policy_reste_orphelin():
    """`backend/policy/approval_engine.py` n'est **pas** rebranché ici.

    La roadmap proposait de le faire. Mesuré : Aegis est la seule couche
    de gouvernance réellement sur le chemin des requêtes, et
    `backend/policy/*` ne sert que ses propres routes. Y ajouter une
    seconde porte vivante donnerait deux endroits où une action peut
    être autorisée, deux files, et la question « laquelle fait foi ? » à
    chaque incident — de la complexité neuve sans sécurité neuve.

    Ce test tombe le jour où quelqu'un le rebranche, et c'est le moment
    de relire ce raisonnement plutôt que de le contourner.
    """
    import io
    from pathlib import Path as _P

    racine = _P(__file__).resolve().parents[2]
    appelants: list[str] = []
    for fichier in (racine / "backend").rglob("*.py"):
        if "tests" in fichier.parts or "policy" in fichier.parts:
            continue
        texte = io.open(fichier, encoding="utf-8", errors="replace").read()
        if "approval_engine" in texte:
            appelants.append(str(fichier.relative_to(racine)))
    assert not appelants, (
        "backend/policy/approval_engine.py a été rebranché depuis "
        f"{appelants} — relire HOS-224 avant d'aller plus loin : deux "
        "portes vivantes valent moins qu'une")
