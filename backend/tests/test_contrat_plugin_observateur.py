# -*- coding: utf-8 -*-
"""Le contrat de l'observateur de Skills, et ce qui l'empeche de deriver
(G-28, HOS-276).

## La decision que ces tests fixent

    le point d'observation `on_skill_lifecycle` et son proprietaire   ADOPT
    l'installation du plugin dans l'agent reel, aujourd'hui           DEFER

La faisabilite est **demontree**, pas supposee. Sur un `HERMES_HOME` de
substitution, avec le fichier de ce depot :

    created  g28-depot-a  task='tache-1'  session='sess-depot'  prov='local'
    created  g28-depot-b  task='tache-2'  session='sess-depot'  prov='local'
    patched  g28-depot-a  task='tache-4'  session='sess-depot'  prov='local'

`task_id` **differe d'une mutation a l'autre** : c'est la clef de jointure
qui manquait a G-27, et qu'aucun magasin natif ne persiste. Deux appels a
`bump_use` intercales n'ont rien laisse — `loaded` est ecarte.

## Pourquoi il n'est pas installe

Rien dans Hermes OS ne lit encore une relation Run ↔ Skill : l'installer
produirait un fichier qui grossit et que personne ne lit. Et
`plugin_compat.COMPAT_REMOVAL_DATE = 2026-09-14` retire dans quatre jours
la couche qui fait vivre les imports internes des plugins ; celui-ci n'en
a aucun — `scan_plugin()` rend « aucun » — mais le runtime d'apres n'a pas
ete mesure.

## Ce que l'agent garantit, mesure

`_emit_skill_lifecycle` **ignore** la valeur de retour du hook, et chaque
callback est isolee :

    plugin absent      non charge   has_hook=False   mutation OK
    plugin desactive   charge       has_hook=False   mutation OK
    callback qui leve  charge       has_hook=True    mutation OK

L'observateur ne peut donc pas devenir une autorite par construction. Ces
tests gardent l'autre moitie : qu'il ne le devienne pas par ecriture.
"""
from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parents[2]
PLUGIN = RACINE / "integrations" / "hermes-agent" / "observateur-skills"
SOURCE = PLUGIN / "__init__.py"


@pytest.fixture
def observateur():
    """Le module du depot, charge tel quel.

    Il n'importe que la bibliotheque standard — c'est precisement ce que le
    test suivant verifie — donc le venv de Hermes OS suffit a l'executer.
    """
    spec = importlib.util.spec_from_file_location("_observateur_skills", SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Etat:
    """La facade `ctx.state` de l'agent, reduite a ce que le plugin emploie.

    `set` est atomique chez l'agent (verrou inter-processus + ecriture
    atomique) ; c'est la PAIRE `get`/`set` qui ne l'etait pas, et que la
    correction de G-31 a supprimee.
    """

    def __init__(self, leve=False):
        self.donnees = {}
        self.leve = leve
        self.ecritures = 0

    def get(self, cle, defaut=None):
        if self.leve:
            raise RuntimeError("etat illisible")
        return self.donnees.get(cle, defaut)

    def set(self, cle, valeur):
        if self.leve:
            raise RuntimeError("quota depasse")
        self.ecritures += 1
        self.donnees[cle] = valeur


class _Ctx:
    def __init__(self, leve=False):
        self.state = _Etat(leve)
        self.hooks = {}

    def register_hook(self, nom, rappel):
        self.hooks[nom] = rappel


def _fait(**extra):
    base = {"action": "created", "skill_name": "sonde", "provenance": "local",
            "task_id": "tache-1", "session_id": "sess-1", "use_count": None,
            "reused": None, "reuse_after_patch": None,
            "telemetry_schema_version": "hermes.observer.v1"}
    base.update(extra)
    return base


def _brancher(observateur, leve=False):
    ctx = _Ctx(leve)
    observateur.register(ctx)
    return ctx, ctx.hooks["on_skill_lifecycle"]


def _notes(observateur, ctx):
    """Les faits, lus par la facade du plugin — jamais par sa forme de clef."""
    return observateur.mutations(ctx.state.donnees)


# ── Ce qu'il note, et ce qu'il ecarte ─────────────────────────────────

def test_une_mutation_est_notee_avec_son_identite_complete(observateur):
    """C'est la seule raison d'etre du plugin : `task_id` et `session_id`
    traversent le hook et ne sont persistes nulle part cote agent (G-27,
    0 des 75 enregistrements les porte)."""
    ctx, hook = _brancher(observateur)
    hook(**_fait(task_id="tache-77", session_id="sess-xyz"))
    notes = _notes(observateur, ctx)
    assert len(notes) == 1
    assert notes[0]["task_id"] == "tache-77"
    assert notes[0]["session_id"] == "sess-xyz"
    assert notes[0]["skill_name"] == "sonde"
    assert notes[0]["provenance"] == "local"


def test_l_usage_n_est_pas_note(observateur):
    """`loaded` part a CHAQUE invocation de Skill ; les quatre autres sont
    des mutations, donc rares. Le noter ferait croitre l'etat au rythme de
    l'usage, et `PluginState` refuse d'ecrire au-dela de 10 Mio : un
    observateur qui remplit son quota cesse d'observer sans le dire."""
    ctx, hook = _brancher(observateur)
    for _ in range(50):
        hook(**_fait(action="loaded", use_count=3, reused=True))
    assert _notes(observateur, ctx) == []
    assert ctx.state.ecritures == 0


@pytest.mark.parametrize("action", ["created", "edited", "patched", "installed"])
def test_les_quatre_mutations_mesurees_sont_retenues(observateur, action):
    ctx, hook = _brancher(observateur)
    hook(**_fait(action=action))
    assert _notes(observateur, ctx)[0]["action"] == action


# ── Ce qu'il n'invente pas ────────────────────────────────────────────

def test_une_session_absente_reste_absente(observateur):
    """`agent/skill_commands.py` appelle `bump_use` sans `session_id`, et
    `_emit_skill_lifecycle` le rend alors `""`. Le completer fabriquerait
    la correlation que G-27 a refuse d'inventer."""
    ctx, hook = _brancher(observateur)
    hook(**_fait(session_id=""))
    assert _notes(observateur, ctx)[0]["session_id"] == ""


def test_une_provenance_inconnue_sort_telle_quelle(observateur):
    """Un runtime plus recent peut emettre une provenance qu'on ne connait
    pas. La traduire vers une categorie connue serait affirmer."""
    ctx, hook = _brancher(observateur)
    hook(**_fait(provenance="quelque-chose-de-neuf"))
    assert _notes(observateur, ctx)[0]["provenance"] == "quelque-chose-de-neuf"


def test_une_action_inconnue_est_notee_sans_traduction(observateur):
    ctx, hook = _brancher(observateur)
    hook(**_fait(action="archived"))
    assert _notes(observateur, ctx)[0]["action"] == "archived"


def test_aucun_champ_n_est_ajoute_hors_de_ce_que_l_agent_livre(observateur):
    """Un champ que l'agent n'a pas envoye serait une invention — meme un
    `run_id` vide inviterait la passe suivante a le remplir."""
    ctx, hook = _brancher(observateur)
    hook(**_fait())
    notes = _notes(observateur, ctx)[0]
    assert set(notes) == set(_fait()) | {"observe_a"}


# ── Ce qui l'empeche de casser l'agent ────────────────────────────────

def test_le_hook_rend_toujours_None(observateur):
    """Le retour est ignore par `_emit_skill_lifecycle`. Le rendre
    explicitement `None` dit que ce plugin ne pretend influencer aucune
    decision — et un mutant qui rendrait autre chose se verrait."""
    ctx, hook = _brancher(observateur)
    assert hook(**_fait()) is None
    assert hook(**_fait(action="loaded")) is None


def test_un_etat_qui_leve_ne_fait_pas_lever_le_hook(observateur):
    """Le quota peut etre atteint, le disque plein, le verrou pris. Une
    exception ici serait attrapee par l'agent — mais elle ferait perdre le
    fait sans que rien ne le dise, et sur `pre_tool_call` elle bloquerait
    l'outil. Un observateur reste silencieux."""
    _, hook = _brancher(observateur, leve=True)
    assert hook(**_fait()) is None


def test_sans_enregistrement_prealable_le_hook_ne_leve_pas(observateur):
    """`register` n'a pas ete appele : aucun `ctx`. Le hook doit rendre
    `None`, pas exploser."""
    assert observateur._on_skill_lifecycle(**_fait()) is None  # noqa: SLF001


def test_une_valeur_non_serialisable_ne_perd_pas_le_fait(observateur):
    ctx, hook = _brancher(observateur)
    hook(**_fait(reused=object()))
    note = _notes(observateur, ctx)[0]
    assert isinstance(note["reused"], str)
    assert note["task_id"] == "tache-1", "le reste du fait survit"


def test_deux_faits_simultanes_ne_s_ecrasent_pas(observateur):
    """Le defaut que G-31 a mesure, et la raison de la correction.

    La premiere version faisait `state.get("mutations")` puis
    `state.set("mutations")`. Chaque appel est atomique chez l'agent ; la
    PAIRE ne l'est pas. Deux tours ACP concurrents — chacun dans son
    `copy_context`, sur le meme executeur — ont perdu **un fait sur deux** :
    les deux threads avaient lu la meme liste avant que l'un ecrive.

    Un observateur qui perd silencieusement la moitie de ce qu'il observe
    est pire qu'absent : il donne une trace qu'on croit complete."""
    import threading

    ctx, hook = _brancher(observateur)
    barriere = threading.Barrier(8)

    def _poser(i):
        barriere.wait()
        hook(**_fait(skill_name=f"s{i}", task_id=f"t{i}"))

    fils = [threading.Thread(target=_poser, args=(i,)) for i in range(8)]
    for t in fils:
        t.start()
    for t in fils:
        t.join()

    notes = _notes(observateur, ctx)
    assert len(notes) == 8, f"{8 - len(notes)} fait(s) perdu(s)"
    assert {n["skill_name"] for n in notes} == {f"s{i}" for i in range(8)}


def test_les_faits_sont_ordonnes(observateur):
    """Un consommateur draine dans l'ordre ; des clefs non triables le
    forceraient a re-trier sur un champ que le plugin pourrait cesser
    d'emettre."""
    ctx, hook = _brancher(observateur)
    for i in range(5):
        hook(**_fait(skill_name=f"s{i}"))
    assert [n["skill_name"] for n in _notes(observateur, ctx)] == [
        f"s{i}" for i in range(5)]


def test_l_etat_est_persiste_et_non_garde_en_memoire(observateur):
    """Un accumulateur de module perdrait tout au redemarrage de l'agent —
    et la relation avec lui. Chaque fait passe par `ctx.state.set`."""
    ctx, hook = _brancher(observateur)
    hook(**_fait())
    assert ctx.state.ecritures == 1
    arbre = ast.parse(SOURCE.read_text(encoding="utf-8"))
    globales = {t.id for n in ast.walk(arbre) if isinstance(n, ast.Assign)
                for t in n.targets if isinstance(t, ast.Name)}
    assert not {"_FAITS", "_MUTATIONS", "_NOTES"} & globales, (
        "un accumulateur de module ne survit pas au redemarrage")


# ── Ce qui l'empeche de devenir une autorite ──────────────────────────

def test_le_plugin_n_importe_que_la_bibliotheque_standard():
    """`plugin_compat.COMPAT_REMOVAL_DATE = 2026-09-14` : ce jour-la, tout
    plugin externe important un module interne de l'agent est DESACTIVE.
    Mesure du 2026-09-10 : `scan_plugin()` sur ce repertoire rend « aucun ».
    La garde tient cette propriete, qui est la condition de survie du
    plugin a la mise a jour."""
    autorises = {"json", "os", "threading", "time", "__future__"}
    arbre = ast.parse(SOURCE.read_text(encoding="utf-8"))
    importes = set()
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.Import):
            importes |= {a.name.split(".")[0] for a in noeud.names}
        elif isinstance(noeud, ast.ImportFrom) and noeud.module:
            importes.add(noeud.module.split(".")[0])
    assert importes <= autorises, (
        f"imports hors bibliotheque standard : {sorted(importes - autorises)} — "
        "le plugin serait desactive apres le 2026-09-14")


def test_le_plugin_ne_mute_aucune_skill():
    """Observateur, jamais acteur. `skill_manage` et l'ecriture de fichiers
    en feraient une seconde autorite sur un contenu qui appartient a
    l'agent."""
    arbre = ast.parse(SOURCE.read_text(encoding="utf-8"))
    appels = {getattr(n.func, "attr", None) or getattr(n.func, "id", None)
              for n in ast.walk(arbre) if isinstance(n, ast.Call)}
    for interdit in ("skill_manage", "open", "write_text", "mkdir", "unlink",
                     "rmtree", "record_created", "bump_patch", "mark_agent_created"):
        assert interdit not in appels, f"le plugin appelle `{interdit}`"


def test_le_manifeste_ne_declare_que_l_observation():
    """Un hook de plus — `pre_tool_call`, `transform_llm_output` — ferait de
    ce plugin un acteur. Le manifeste est la surface qu'un relecteur lit en
    premier ; il doit dire la verite."""
    manifeste = (PLUGIN / "plugin.yaml").read_text(encoding="utf-8")
    declares = [l.strip().lstrip("- ").strip()
                for l in manifeste.split("hooks:")[1].splitlines() if l.strip()]
    assert declares == ["on_skill_lifecycle"], declares


def test_hermes_os_n_installe_pas_le_plugin():
    """DEFER veut dire DEFER. Aucun module du backend ne doit poser ce
    plugin chez l'agent : l'installation est une decision, pas un effet de
    bord d'un import."""
    coupables = []
    for module in (RACINE / "backend").rglob("*.py"):
        if "tests" in module.parts:
            continue
        source = module.read_text(encoding="utf-8", errors="replace")
        if "observateur-skills" in source or "hermes-os-observateur" in source:
            coupables.append(str(module.relative_to(RACINE)))
    assert not coupables, (
        "le backend nomme le plugin : " + ", ".join(coupables))


def test_le_README_dit_que_le_plugin_n_est_pas_installe():
    """Un plugin trouve dans un depot se lit comme un plugin actif. Sans
    cette phrase, la passe suivante le croit pose et batit dessus."""
    readme = (PLUGIN / "README.md").read_text(encoding="utf-8")
    assert "n'est pas installé" in readme
    assert "DEFER" in readme and "ADOPT" in readme


def test_aucun_module_hermes_os_ne_correle_depuis_les_compteurs():
    """G-27 l'a mesure : `.usage.json` ne porte ni `task_id` ni
    `session_id`. Un module qui pretendrait en tirer une relation Run ↔
    Skill inventerait — et remplirait `source_task_id` de rien."""
    for module in (RACINE / "backend").rglob("*.py"):
        if "tests" in module.parts:
            continue
        source = module.read_text(encoding="utf-8", errors="replace")
        if ".usage.json" not in source and "skill_usage" not in source:
            continue
        arbre = ast.parse(source)
        litteraux = {n.value for n in ast.walk(arbre)
                     if isinstance(n, ast.Constant) and isinstance(n.value, str)}
        for interdit in ("source_task_id", "run_id"):
            assert interdit not in litteraux, (
                f"{module.relative_to(RACINE)} lie les compteurs a un Run")
