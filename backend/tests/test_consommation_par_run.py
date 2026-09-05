"""Ce qu'un run a coûté à la machine, et ce qu'on n'en sait pas (R-6).

## Le manque

Le registre portait les jetons et le coût monétaire d'un run depuis
HOS-221, et rien de physique. « Cette mission a-t-elle saturé la carte ? »
n'avait pas de réponse conservée, alors que la télémétrie existait
(A-15) — elle n'était simplement rattachée à aucun run.

## La question qui décide de tout : que sait-on vraiment attribuer ?

La source canonique somme `GPU Process Memory` sur **tous** les
processus, et le modèle vit dans le serveur Ollama, qui sert tous les runs
à la fois. Deux runs simultanés partagent le même processus : aucun
compteur ne dit lequel a pris quoi. Le chemin agentique n'aide pas — le
sous-processus de Hermes Agent ne détient presque pas de VRAM, c'est
Ollama qui la détient pour lui.

**L'attribution exacte est donc impossible ici**, et ce fichier vérifie
surtout que le système ne prétend pas le contraire :

- la **réservation** est exacte et propre au run — c'est une promesse ;
- l'**occupation** est mesurée mais appartient à la machine ;
- `exclusif` dit si l'écart entre les deux relevés est attribuable, et
  sans lui il ne l'est pas.

## Mesuré sur la vraie carte

    run 1, succès      début 1,148 Gio  pic 8,231 Gio  exclusif=True
    run 2, échec       début 8,231 Gio  pic 8,231 Gio  exclusif=True
    runs 3 et 4, en même temps           pic 8,231 Gio  exclusif=False

Les deux runs concurrents voient le même 8,231 Gio et **aucun des deux**
ne se le voit attribuer : c'est tout l'objet de `exclusif`.

## Ce que ce fichier ne prouve pas

Que le pic enregistré soit le vrai pic. Deux points de mesure seulement —
avant et après la tâche — parce que R-6 n'ouvre pas de fil de sondage. Le
chiffre est un **minorant**, et il est nommé pour ce qu'il est.
"""

from __future__ import annotations

import ast
import asyncio
import io
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.execution.task_executor import RealTaskExecutor, RuntimeUnavailableError
from backend.ral.capabilities import ChatResponse
from backend.runs.consommation import ObservationPhysique, agreger
from backend.runs.registre import Registre, Statut
from backend.runtime.resources.resource_manager import ResourceManager
from backend.runtime.resources.resource_models import GPUInfo
from backend.storage.database_manager import DatabaseConfig, DatabaseManager

RACINE = Path(__file__).resolve().parents[2]
GIO = 1024 ** 3

#: Les chiffres relevés sur la vraie carte pendant cette passe.
CARTE = int(15.984 * GIO)
DEBUT_REEL = 1232191488          # 1,148 Gio, machine au repos
PIC_REEL = 8837632000            # 8,231 Gio, modèle 256k résident
EMPREINTE = 2.05                 # `config/models.yaml`, rôle `swift`


class _Carte:
    """Une carte dont on pilote l'occupation, pour la faire bouger entre
    deux relevés comme elle bouge quand un modèle se charge."""

    def __init__(self, occupee: int = DEBUT_REEL, mesuree: bool = True) -> None:
        self.occupee = occupee
        self.mesuree = mesuree

    def poll(self) -> GPUInfo:
        return GPUInfo(name="RX 6800", vendor="AMD",
                       vram_total_bytes=CARTE,
                       vram_used_bytes=self.occupee,
                       vram_free_bytes=max(0, CARTE - self.occupee),
                       available=True, occupation_mesuree=self.mesuree)


def _gestionnaire(carte: _Carte | None = None) -> ResourceManager:
    return ResourceManager(gpu_monitor=carte or _Carte())


def _tache(nom: str = "t1"):
    return SimpleNamespace(task_id=nom, title=nom, description="",
                           task_type="implementation", mission_id="m1",
                           assigned_skills=[], errors=[],
                           ressources_physiques={})


def _executeur(gestionnaire, chat, **kw) -> RealTaskExecutor:
    kw.setdefault("vram_gb_for", lambda _m: EMPREINTE)
    kw.setdefault("vram_wait_s", 0.3)
    kw.setdefault("vram_poll_interval_s", 0.05)
    return RealTaskExecutor(chat=chat, model_for=lambda _t: "modele-de-test",
                            default_model="modele-de-test",
                            resource_manager=gestionnaire, **kw)


def _chat_ok(carte: _Carte | None = None, monte_a: int | None = None):
    """Un chat qui, comme un vrai chargement, fait monter l'occupation."""
    async def _chat(*, messages, model, **_):
        if carte is not None and monte_a is not None:
            carte.occupee = monte_a
        return ChatResponse(content="fait",
                            metadata={"model": model, "provider": "ollama"})
    return _chat


def _registre(tmp_path) -> Registre:
    return Registre(DatabaseManager(DatabaseConfig(name=str(tmp_path / "runs"))))


# ═══ Test 1 — un run simple conserve sa mesure ════════════════════════

def test_1_une_tache_conserve_ce_que_la_carte_portait():
    carte = _Carte(DEBUT_REEL)
    ex = _executeur(_gestionnaire(carte), _chat_ok(carte, PIC_REEL))
    t = _tache()

    ex.execute(t, SimpleNamespace(runtime_id="ollama"))

    m = t.ressources_physiques
    assert m["vram_machine_debut_octets"] == DEBUT_REEL
    assert m["vram_machine_pic_octets"] == PIC_REEL
    assert m["vram_reservee_octets"] == int(EMPREINTE * GIO)
    assert m["exclusif"] is True


def test_1_le_run_agrege_ce_que_ses_taches_ont_vu(tmp_path):
    """Bout en bout jusqu'à la colonne : c'est ce que R-6 demande."""
    reg = _registre(tmp_path)
    run = reg.ouvrir(mission="m1", objectif="essai")

    taches = [
        {"vram_reservee_octets": int(2.05 * GIO),
         "vram_machine_debut_octets": DEBUT_REEL,
         "vram_machine_pic_octets": PIC_REEL, "exclusif": True},
        {"vram_reservee_octets": int(13.68 * GIO),
         "vram_machine_debut_octets": PIC_REEL,
         "vram_machine_pic_octets": PIC_REEL, "exclusif": True},
    ]
    reg.mesurer(run.identifiant, **agreger(taches))

    relu = reg.lire(run.identifiant)
    assert relu.vram_reservee_octets == int(13.68 * GIO), (
        "les réservations ont été sommées : les tâches ne tiennent pas la "
        "carte en même temps, et la somme annoncerait une occupation qui "
        "n'a jamais existé")
    assert relu.vram_machine_debut_octets == DEBUT_REEL
    assert relu.vram_machine_pic_octets == PIC_REEL


# ═══ Test 2 — le pic domine les mesures intermédiaires ════════════════

def test_2_le_pic_est_le_maximum_des_releves():
    carte = _Carte(DEBUT_REEL)
    obs = ObservationPhysique()
    g = _gestionnaire(carte)

    obs.relever(g, ligne_de_base=True)
    for occupation in (PIC_REEL, DEBUT_REEL, PIC_REEL - GIO):
        carte.occupee = occupation
        obs.relever(g)

    assert obs.vram_machine_pic_octets == PIC_REEL
    assert obs.vram_machine_debut_octets == DEBUT_REEL
    assert obs.vram_machine_pic_octets >= obs.vram_machine_debut_octets


def test_2_une_occupation_qui_redescend_ne_baisse_pas_le_pic():
    carte = _Carte(PIC_REEL)
    obs = ObservationPhysique()
    g = _gestionnaire(carte)
    obs.relever(g, ligne_de_base=True)
    carte.occupee = DEBUT_REEL
    obs.relever(g)

    assert obs.vram_machine_pic_octets == PIC_REEL


def test_2_la_ligne_de_base_ne_se_reecrit_pas():
    """Un second relevé de base écraserait le point de départ du run."""
    carte = _Carte(DEBUT_REEL)
    obs = ObservationPhysique()
    g = _gestionnaire(carte)
    obs.relever(g, ligne_de_base=True)
    carte.occupee = PIC_REEL
    obs.relever(g, ligne_de_base=True)

    assert obs.vram_machine_debut_octets == DEBUT_REEL


# ═══ Test 3 — des octets, et rien d'autre ═════════════════════════════

def test_3_les_valeurs_sont_des_octets_entiers():
    carte = _Carte(DEBUT_REEL)
    ex = _executeur(_gestionnaire(carte), _chat_ok(carte, PIC_REEL))
    t = _tache()
    ex.execute(t, SimpleNamespace(runtime_id="ollama"))

    for cle in ("vram_reservee_octets", "vram_machine_debut_octets",
                "vram_machine_pic_octets"):
        valeur = t.ressources_physiques[cle]
        assert isinstance(valeur, int) and not isinstance(valeur, bool), (
            f"{cle} vaut {valeur!r} : ce n'est pas un compte d'octets")
        assert valeur > 1024 ** 2, (
            f"{cle} vaut {valeur} — un ordre de grandeur de mégaoctet ou "
            "moins trahit une conversion perdue")


def test_3_le_nom_des_colonnes_porte_l_unite():
    """« memory » ou « GiB » sans définition est la façon habituelle de
    perdre un facteur 1024 trois mois plus tard."""
    from backend.runs.registre import Run

    physiques = [n for n in Run.__dataclass_fields__ if "vram" in n]
    assert physiques, "le run ne porte plus rien de physique"
    for nom in physiques:
        assert nom.endswith("_octets"), (
            f"{nom} ne dit pas son unité")


def test_3_ce_qui_est_lu_est_ce_qui_est_ecrit():
    """Aucune conversion en route : la valeur du gestionnaire arrive telle
    quelle dans la comptabilité."""
    carte = _Carte(7_777_777_777)
    g = _gestionnaire(carte)
    obs = ObservationPhysique()
    obs.relever(g, ligne_de_base=True)

    assert obs.vram_machine_debut_octets == g.get_gpu_info().vram_used_bytes


# ═══ Test 4 — « non mesuré » n'est pas « zéro » ═══════════════════════

def test_4_une_carte_non_mesuree_ne_produit_pas_un_zero():
    """A-15 traverse : `occupation_mesuree=False` porte des zéros de
    prudence, et les enregistrer les transformerait en mesure."""
    carte = _Carte(0, mesuree=False)
    obs = ObservationPhysique()
    obs.relever(_gestionnaire(carte), ligne_de_base=True)

    assert obs.vram_machine_debut_octets is None
    assert obs.vram_machine_pic_octets is None
    assert "vram_machine_pic_octets" not in obs.to_dict()


def test_4_un_run_sans_mesure_garde_des_colonnes_vides(tmp_path):
    reg = _registre(tmp_path)
    run = reg.ouvrir(mission="m1", objectif="jamais exécuté")

    relu = reg.lire(run.identifiant)
    assert relu.vram_machine_pic_octets is None, (
        "un run qui n'a rien mesuré se présente comme ayant consommé zéro")
    assert relu.vram_reservee_octets is None
    assert relu.exclusif is None


def test_4_mesurer_avec_None_n_ecrit_rien(tmp_path):
    reg = _registre(tmp_path)
    run = reg.ouvrir(mission="m1", objectif="e")
    reg.mesurer(run.identifiant, vram_machine_pic_octets=PIC_REEL)
    reg.mesurer(run.identifiant, vram_machine_pic_octets=None)

    assert reg.lire(run.identifiant).vram_machine_pic_octets == PIC_REEL


def test_4_zero_reste_une_mesure(tmp_path):
    """Une carte réellement vide vaut zéro, et ce zéro-là doit s'écrire.

    `constater` filtre ses valeurs sur `if v` et ferait disparaître
    celle-ci ; c'est pour cela que `mesurer` existe à côté.
    """
    reg = _registre(tmp_path)
    run = reg.ouvrir(mission="m1", objectif="e")
    reg.mesurer(run.identifiant, vram_machine_debut_octets=0)

    assert reg.lire(run.identifiant).vram_machine_debut_octets == 0


def test_4_faux_reste_un_fait(tmp_path):
    reg = _registre(tmp_path)
    run = reg.ouvrir(mission="m1", objectif="e")
    reg.mesurer(run.identifiant, exclusif=False)

    relu = reg.lire(run.identifiant)
    assert relu.exclusif is False, (
        "« ce run partageait la carte » a été perdu ; None dirait « on ne "
        "sait pas », ce qui est autre chose")


# ═══ Test 5 — un run en erreur conserve ce qu'il sait ════════════════

def test_5_une_exception_du_runtime_ne_perd_pas_la_comptabilite():
    """C'est justement le run en échec dont on veut savoir ce que la carte
    portait — et c'est le chemin qui sort avant `resources_used`."""
    carte = _Carte(PIC_REEL)

    async def casse(*, messages, model, **_):
        raise RuntimeError("le runtime a rendu l'âme")

    ex = _executeur(_gestionnaire(carte), casse)
    t = _tache()

    with pytest.raises(RuntimeUnavailableError):
        ex.execute(t, SimpleNamespace(runtime_id="ollama"))

    m = t.ressources_physiques
    assert m["vram_machine_debut_octets"] == PIC_REEL
    assert m["vram_reservee_octets"] == int(EMPREINTE * GIO)


def test_5_un_refus_d_admission_garde_la_ligne_de_base():
    """Rien n'a tourné, mais on sait ce que la carte portait quand on a
    renoncé — et c'est la seule chose qu'on sache."""
    carte = _Carte(int(15.5 * GIO))          # plus de place
    ex = _executeur(_gestionnaire(carte), _chat_ok())
    t = _tache()

    with pytest.raises(RuntimeUnavailableError):
        ex.execute(t, SimpleNamespace(runtime_id="ollama"))

    m = t.ressources_physiques
    assert m["vram_machine_debut_octets"] == int(15.5 * GIO)
    assert "vram_reservee_octets" not in m, (
        "une réservation refusée s'est inscrite comme accordée")


def test_5_un_delai_depasse_garde_la_comptabilite():
    carte = _Carte(DEBUT_REEL)

    async def lent(*, messages, model, **_):
        await asyncio.sleep(5)
        return ChatResponse(content="trop tard", metadata={})

    ex = _executeur(_gestionnaire(carte), lent, timeout_s=0.2)
    t = _tache()

    with pytest.raises(RuntimeUnavailableError):
        ex.execute(t, SimpleNamespace(runtime_id="ollama"))

    assert t.ressources_physiques["vram_machine_debut_octets"] == DEBUT_REEL


# ═══ Test 6 — un run annulé conserve ce qu'il sait ═══════════════════

def test_6_une_annulation_arrive_comme_une_panne_de_runtime():
    """Ce que l'annulation **est** réellement ici, mesuré et non supposé.

    Première version de ce test : « `CancelledError` descend de
    `BaseException`, elle traverse le `except Exception` et n'est retenue
    que par le `finally` ». C'est faux sur ce chemin. Mesuré, une
    `asyncio.CancelledError` levée dans la coroutine ressort d'`execute`
    en **`RuntimeUnavailableError`** : elle est convertie avant d'arriver
    au `finally`.

    La mutation qui retirait la capture « sur annulation » ne faisait donc
    rougir aucun test — parce qu'il n'y avait rien de distinct à retirer.
    Le test disait tester l'annulation et testait le chemin d'échec
    ordinaire sous un autre nom.

    Ce qui est vrai et vérifié ici : l'annulation est couverte par la
    famille du test 5, et le contrat de conversion est écrit noir sur
    blanc plutôt que supposé.
    """
    carte = _Carte(PIC_REEL)

    async def annule(*, messages, model, **_):
        raise asyncio.CancelledError()

    ex = _executeur(_gestionnaire(carte), annule)
    t = _tache()

    with pytest.raises(RuntimeUnavailableError):
        ex.execute(t, SimpleNamespace(runtime_id="ollama"))

    assert t.ressources_physiques.get("vram_machine_debut_octets") == PIC_REEL


def test_6_une_interruption_hors_Exception_ne_perd_pas_la_comptabilite():
    """La vraie propriété du `finally` : il retient ce qu'un
    `except Exception` laisserait passer.

    `KeyboardInterrupt` ne descend pas d'`Exception` et traverse donc tous
    les gestionnaires d'`execute`. Si la capture vivait dans un
    `except Exception` — la forme qu'on pourrait croire équivalente — elle
    serait perdue ici. C'est ce test, et lui seul, qui distingue les deux.
    """
    carte = _Carte(PIC_REEL)

    def interrompt(*, messages, model, **_):
        # Synchrone, et non `async` : levée depuis la boucle d'événements
        # de l'exécuteur, une `BaseException` tue ce fil et laisse
        # l'appelant sur `future.result(timeout=...)` jusqu'à son délai —
        # mesuré, le test pendait au lieu d'échouer. Ce comportement-là
        # appartient à `_run_coro` et n'est pas l'objet de R-6 ; ici on
        # veut seulement une `BaseException` qui traverse `execute`.
        raise KeyboardInterrupt()

    ex = _executeur(_gestionnaire(carte), interrompt, timeout_s=2.0)
    t = _tache()

    with pytest.raises(BaseException) as capture:
        ex.execute(t, SimpleNamespace(runtime_id="ollama"))
    assert not isinstance(capture.value, Exception), (
        "l'interruption a été convertie : le test ne prouve plus rien")

    assert t.ressources_physiques.get("vram_machine_debut_octets") == PIC_REEL


def test_6_un_run_annule_garde_sa_mesure_en_base(tmp_path):
    reg = _registre(tmp_path)
    run = reg.ouvrir(mission="m1", objectif="e")
    reg.mesurer(run.identifiant, vram_machine_pic_octets=PIC_REEL)
    reg.terminer(run.identifiant, Statut.ABANDONNE, raison="annulée")

    relu = reg.lire(run.identifiant)
    assert relu.statut is Statut.ABANDONNE
    assert relu.vram_machine_pic_octets == PIC_REEL


# ═══ Test 7 — deux runs simultanés ═══════════════════════════════════

def test_7_deux_taches_concurrentes_ne_se_voient_pas_attribuer_la_carte():
    """Le cœur de R-6 : la mesure globale est la même pour les deux, et
    celle qui a partagé la carte ne se l'attribue pas.

    ## Pourquoi le test n'affirme pas « toutes les deux `False` »

    Première version, mesurée : rouge une fois sur six. Le relevé final
    d'une tâche a lieu juste avant sa libération ; si l'autre a déjà libéré,
    elle ne voit plus personne et se déclare seule — ce qui est **exact**
    pour l'instant où elle a regardé. Exiger `False` des deux, c'est exiger
    que deux relevés indépendants tombent tous les deux dans la fenêtre de
    l'autre. Ce n'est pas une propriété du système, c'est une coïncidence,
    et un test qui l'exige rougit au hasard.

    Ce qui est garanti par construction : les deux tâches réservent avant
    que l'une ne relève (la barrière est **dans** le `chat`, donc après
    l'admission), et `c-court` relâche tout de suite pendant que `c-long`
    tient une demi-seconde. `c-court` relève donc forcément pendant que
    `c-long` détient sa réservation, et doit dire qu'elle partageait.
    """
    carte = _Carte(DEBUT_REEL)
    g = _gestionnaire(carte)
    resultats: dict[str, dict] = {}
    verrou = threading.Lock()
    #: Franchie une fois les deux réservations prises — donc après
    #: `_admettre_et_reserver`, ce qu'un `Barrier` posé avant `execute` ne
    #: garantirait pas.
    reserves = threading.Barrier(2, timeout=20)

    def chat_pour(tenue_s: float):
        async def _chat(*, messages, model, **_):
            carte.occupee = PIC_REEL
            reserves.wait()
            time.sleep(tenue_s)
            return ChatResponse(content="fait", metadata={"model": model})
        return _chat

    def executer(nom, tenue_s):
        ex = _executeur(g, chat_pour(tenue_s), vram_wait_s=5.0)
        t = _tache(nom)
        try:
            ex.execute(t, SimpleNamespace(runtime_id="ollama"))
        except Exception:
            pass
        with verrou:
            resultats[nom] = t.ressources_physiques

    fils = [threading.Thread(target=executer, args=a)
            for a in (("c-court", 0.0), ("c-long", 0.5))]
    for f in fils:
        f.start()
    for f in fils:
        f.join(timeout=30)

    assert set(resultats) == {"c-court", "c-long"}
    assert resultats["c-court"]["exclusif"] is False, (
        "une tâche s'est déclarée seule sur la carte alors que l'autre "
        "détenait encore sa réservation au moment du relevé")
    # La même occupation machine pour les deux — et c'est bien pour cela
    # qu'elle ne peut être attribuée à ni l'une ni l'autre.
    assert (resultats["c-court"]["vram_machine_pic_octets"]
            == resultats["c-long"]["vram_machine_pic_octets"] == PIC_REEL)


def test_7_l_agregat_perd_l_exclusivite_des_qu_une_tache_partageait():
    assert agreger([{"exclusif": True}, {"exclusif": False}])["exclusif"] is False
    assert agreger([{"exclusif": True}, {"exclusif": True}])["exclusif"] is True
    assert "exclusif" not in agreger([{}, {}])


def test_7_exclusif_reste_inconnu_quand_rien_n_a_ete_regarde():
    obs = ObservationPhysique()
    assert obs.exclusif is None
    assert "exclusif" not in obs.to_dict()


def test_7_une_allocation_etrangere_suffit_a_retirer_l_exclusivite():
    g = _gestionnaire()
    g.reserve_resources(1 * GIO, "ollama", model_name="un-autre-run")

    obs = ObservationPhysique()
    obs.relever(g, ligne_de_base=True)

    assert obs.exclusif is False


# ═══ Test 8 — le chemin agentique ════════════════════════════════════

def test_8_le_chemin_agentique_conserve_la_comptabilite():
    """L'agent passe par la même admission depuis §6.2 (R-1) ; il passe
    donc par la même comptabilité, sans porte séparée."""
    carte = _Carte(DEBUT_REEL)
    ex = _executeur(_gestionnaire(carte), _chat_ok(carte, PIC_REEL),
                    agentic_capable_for=lambda _t: True)
    t = _tache()

    ex.execute(t, SimpleNamespace(runtime_id="hermes-agent"))

    m = t.ressources_physiques
    assert m["vram_machine_debut_octets"] == DEBUT_REEL
    assert m["vram_machine_pic_octets"] == PIC_REEL


def test_8_l_attribution_par_processus_n_est_pas_revendiquee():
    """La documentation doit dire que l'attribution exacte est impossible.

    Le serveur Ollama sert tous les runs : le compteur par processus ne
    sépare pas deux runs simultanés, et le sous-processus de l'agent ne
    détient pas la VRAM du modèle. Prétendre le contraire serait la donnée
    précise et fausse que R-6 s'interdit.
    """
    source = io.open(RACINE / "backend/runs/consommation.py",
                     encoding="utf-8").read()
    doc = ast.get_docstring(ast.parse(source)) or ""

    assert "Ollama" in doc and "processus" in doc, (
        "la limite d'attribution n'est plus expliquée là où elle vit")
    assert "exclusif" in doc


# ═══ Test 9 — le registre ne décide jamais ═══════════════════════════

def test_9_la_comptabilite_ne_demande_rien_au_gestionnaire():
    """Structurel, sur les appels : `consommation` lit, et c'est tout.

    Une comptabilité qui appellerait `can_allocate` ou `reserve_resources`
    serait entrée dans la boucle de décision — l'autorité que R-6
    s'interdit de créer.
    """
    arbre = ast.parse(io.open(RACINE / "backend/runs/consommation.py",
                              encoding="utf-8").read())
    appels = {n.func.attr for n in ast.walk(arbre)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    interdits = {"can_allocate", "reserve_resources", "release_resources",
                 "places_disponibles", "set_policy", "set_limit"}
    assert not (appels & interdits), (
        f"la comptabilité agit sur le gestionnaire : {sorted(appels & interdits)}")


def test_9_l_admission_ne_lit_jamais_le_registre():
    """L'inverse, et le plus important : aucune décision ne dépend de la
    trace. `ResourceManager` qui lirait `runs` fermerait la boucle."""
    for fichier in ("backend/runtime/resources/resource_manager.py",
                    "backend/runtime/resources/allocation_policy.py",
                    "backend/runtime/resources/gpu_monitor.py",
                    "backend/runtime/resources/vram_physique.py"):
        arbre = ast.parse(io.open(RACINE / fichier, encoding="utf-8").read())
        modules = {(n.module or "") for n in ast.walk(arbre)
                   if isinstance(n, ast.ImportFrom)}
        modules |= {a.name for n in ast.walk(arbre)
                    if isinstance(n, ast.Import) for a in n.names}
        fautifs = [m for m in modules if "runs" in m or "registre" in m]
        assert not fautifs, (
            f"{fichier} lit le registre : la comptabilité est devenue une "
            f"entrée de décision — {fautifs}")


def test_9_le_registre_n_expose_aucune_decision():
    """Le registre écrit et relit ; il ne répond à aucune question
    d'admission."""
    from backend.runs.registre import Registre as R

    methodes = {n for n in dir(R) if not n.startswith("_")}
    verbes_de_decision = {"can_allocate", "admettre", "autoriser", "reserver",
                          "places_disponibles", "peut_executer"}
    assert not (methodes & verbes_de_decision), (
        f"le registre a gagné un pouvoir de décision : "
        f"{sorted(methodes & verbes_de_decision)}")


# ═══ Test 10 — la donnée survit au redémarrage ═══════════════════════

def test_10_la_mesure_survit_a_la_reouverture(tmp_path):
    """Sans état en mémoire : c'est la règle du registre depuis HOS-221,
    et une comptabilité qui ne la respecterait pas disparaîtrait au premier
    redémarrage — le défaut exact que le registre existe pour fermer."""
    chemin = DatabaseConfig(name=str(tmp_path / "runs"))
    reg = Registre(DatabaseManager(chemin))
    run = reg.ouvrir(mission="m1", objectif="essai")
    reg.mesurer(run.identifiant,
                vram_reservee_octets=int(EMPREINTE * GIO),
                vram_machine_debut_octets=DEBUT_REEL,
                vram_machine_pic_octets=PIC_REEL,
                exclusif=True)
    reg.terminer(run.identifiant, Statut.REUSSI)
    del reg

    relu = Registre(DatabaseManager(chemin)).lire(run.identifiant)

    assert relu.vram_reservee_octets == int(EMPREINTE * GIO)
    assert relu.vram_machine_debut_octets == DEBUT_REEL
    assert relu.vram_machine_pic_octets == PIC_REEL
    assert relu.exclusif is True


def test_10_une_base_anterieure_gagne_les_colonnes_sans_perdre_ses_runs(tmp_path):
    """`CREATE TABLE IF NOT EXISTS` ne fait rien sur une base existante.

    Sans la migration additive, l'`INSERT` nommé d'`ouvrir()` échouerait et
    **plus aucun run ne s'ouvrirait** : une correction d'observabilité
    aurait cassé l'exécution. C'est déjà arrivé à HOS-240.
    """
    config = DatabaseConfig(name=str(tmp_path / "runs"))
    db = DatabaseManager(config)
    db.initialize()
    conn = db.get_connection()
    conn.executescript("""
        CREATE TABLE runs (
            identifiant TEXT PRIMARY KEY, mission TEXT NOT NULL DEFAULT '',
            parent TEXT, tentative INTEGER NOT NULL DEFAULT 1,
            objectif TEXT NOT NULL DEFAULT '', agent TEXT NOT NULL DEFAULT '',
            modele TEXT NOT NULL DEFAULT '', runtime TEXT NOT NULL DEFAULT '',
            fournisseur TEXT NOT NULL DEFAULT '', workspace TEXT NOT NULL DEFAULT '',
            utilisateur TEXT NOT NULL DEFAULT 'local', projet TEXT NOT NULL DEFAULT '',
            statut TEXT NOT NULL DEFAULT 'en_attente', cause TEXT,
            raison TEXT NOT NULL DEFAULT '', motif_de_reprise TEXT NOT NULL DEFAULT '',
            jetons_entree INTEGER NOT NULL DEFAULT 0,
            jetons_sortie INTEGER NOT NULL DEFAULT 0, cout REAL NOT NULL DEFAULT 0,
            contrat TEXT NOT NULL DEFAULT '', cree_le TEXT NOT NULL,
            demarre_le TEXT, fini_le TEXT);
        INSERT INTO runs (identifiant, mission, cree_le)
            VALUES ('ancien', 'm0', '2026-01-01T00:00:00+00:00');
    """)
    conn.commit()

    reg = Registre(db)
    nouveau = reg.ouvrir(mission="m1", objectif="après migration")

    ancien = reg.lire("ancien")
    assert ancien is not None, "la migration a perdu les runs déjà là"
    assert ancien.vram_machine_pic_octets is None, (
        "une ligne d'avant la colonne s'est vue attribuer une mesure")
    reg.mesurer(nouveau.identifiant, vram_machine_pic_octets=PIC_REEL)
    assert reg.lire(nouveau.identifiant).vram_machine_pic_octets == PIC_REEL


# ═══ Robustesse ══════════════════════════════════════════════════════

def test_un_run_cloud_n_invente_pas_une_consommation_locale():
    """Le modèle n'est pas sur cette carte : la bonne valeur est « rien de
    mesuré », pas un relevé qui n'a rien à voir avec lui."""
    carte = _Carte(DEBUT_REEL)

    async def nuage(*, messages, model, racines=None, **_):
        return ChatResponse(content="fait",
                            metadata={"model": model, "provider": "openrouter"})

    ex = _executeur(_gestionnaire(carte), None, cloud_chat=nuage,
                    runtime_for=lambda _t: "openrouter")
    t = _tache()
    ex.execute(t, SimpleNamespace(runtime_id="openrouter"))

    assert t.ressources_physiques == {}, (
        "un run cloud s'est vu attribuer une occupation de la carte locale")


def test_sans_gestionnaire_la_comptabilite_reste_vide():
    ex = RealTaskExecutor(chat=_chat_ok(), model_for=lambda _t: "m",
                          default_model="m")
    t = _tache()
    ex.execute(t, SimpleNamespace(runtime_id="ollama"))

    assert t.ressources_physiques == {}


def test_un_gestionnaire_qui_leve_ne_casse_pas_la_tache():
    """Une trace qui ferait échouer la tâche qu'elle décrit serait pire que
    pas de trace."""
    class _Casse:
        def get_gpu_info(self):
            raise RuntimeError("télémétrie disparue")

        def get_current_allocations(self):
            raise RuntimeError("télémétrie disparue")

    obs = ObservationPhysique()
    obs.relever(_Casse(), ligne_de_base=True)      # ne lève pas

    assert obs.to_dict() == {}


def test_une_reprise_n_herite_pas_des_mesures_de_son_parent(tmp_path):
    """Recopier ferait dire à la nouvelle tentative qu'elle a consommé ce
    que l'autre avait consommé, sans que rien ne l'ait mesuré."""
    reg = _registre(tmp_path)
    parent = reg.ouvrir(mission="m1", objectif="e")
    reg.mesurer(parent.identifiant, vram_machine_pic_octets=PIC_REEL,
                exclusif=True)
    reg.terminer(parent.identifiant, Statut.ECHOUE, raison="plantage")

    enfant = reg.reprendre(parent.identifiant, motif="nouvelle tentative")

    relu = reg.lire(enfant.identifiant)
    assert relu.vram_machine_pic_octets is None
    assert relu.exclusif is None


def test_agreger_ignore_les_taches_sans_mesure():
    assert agreger([{}, None, {"vram_machine_pic_octets": PIC_REEL}]) == {
        "vram_machine_pic_octets": PIC_REEL}
    assert agreger([]) == {}


def test_un_booleen_ne_se_glisse_pas_dans_un_compte_d_octets():
    """`isinstance(True, int)` vaut vrai en Python : un booléen qui
    arriverait dans une colonne d'octets y vaudrait 1, et 1 octet est un
    chiffre parfaitement crédible."""
    resultat = agreger([{"vram_machine_pic_octets": PIC_REEL, "exclusif": True}])

    assert resultat["vram_machine_pic_octets"] == PIC_REEL
    assert resultat["exclusif"] is True
    assert not isinstance(resultat["exclusif"], int) or resultat["exclusif"] is True
