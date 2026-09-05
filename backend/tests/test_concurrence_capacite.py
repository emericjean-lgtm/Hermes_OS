"""La machine ne se sur-engage pas parce que deux missions décident seules
(R-3, R-4).

## Les deux défauts, mesurés avant correction

**R-3 — la borne était un chiffre écrit, pas une capacité.**
`mission_max_parallel_tasks = 2`. Mesuré : sur une carte simulée de
16 Gio, la même constante 2 valait pour 0 place réelle (carte pleine) et
pour 7 places (carte de 48 Gio). Elle ne suivait rien.

Avec l'empreinte **relevée** du rôle `reasoning` — 13,68 Gio,
`config/models.yaml` — la carte de 15,98 Gio en tient **une**. Le graphe
en lançait deux. Le second nœud occupait un fil, brûlait son attente
d'admission, puis échouait :

    t1   4.2 s  REFUSEE : no VRAM admission for 'qwen3.6-35b-128k'
    t2   4.2 s  REFUSEE : no VRAM admission for 'qwen3.6-35b-128k'

**R-4 — la borne était celle d'un appel, pas de la machine.**
`execute_step` ouvrait un `ThreadPoolExecutor` par appel. Deux missions
concurrentes sur le `GraphExecutor` **unique** du conteneur :

    _max_parallel par mission : 2
    pic de nœuds simultanés   : 4

## Ce que ce fichier ne prouve pas

Que la capacité soit exacte. `_empreinte_de_tache_octets` rend le **plus
lourd** des rôles configurés, parce qu'au moment où le graphe décide
combien de nœuds lancer, personne ne sait encore quel modèle chacun
prendra. Une mission de tâches légères obtiendra donc moins de places
qu'elle n'aurait pu en tenir. On sous-répartit parfois ; on ne
sur-répartit jamais.

Et le portillon n'autorise rien : le franchir ne donne aucun droit sur la
carte. C'est la réservation de §6.2 qui en donne, et elle peut refuser
après.
"""

from __future__ import annotations

import ast
import io
import threading
import time
from pathlib import Path

import pytest

from backend.mission.graph_executor import GraphExecutor, Portillon
from backend.mission.mission_models import Mission, MissionNode, MissionStatus
from backend.runtime.resources.resource_manager import ResourceManager
from backend.runtime.resources.resource_models import GPUInfo, ResourceType

RACINE = Path(__file__).resolve().parents[2]
GIO = 1024 ** 3

#: L'empreinte relevée du rôle `reasoning` (`config/models.yaml`).
EMPREINTE = int(13.68 * GIO)
CARTE = int(15.984 * GIO)


class _Carte:
    def __init__(self, total_gio: float = 15.984, utilise_gio: float = 0.0) -> None:
        self.total = int(total_gio * GIO)
        self.utilise = int(utilise_gio * GIO)
        self.mesuree = True

    def poll(self) -> GPUInfo:
        return GPUInfo(name="carte-de-test", vendor="test",
                       vram_total_bytes=self.total,
                       vram_used_bytes=self.utilise,
                       vram_free_bytes=max(0, self.total - self.utilise),
                       available=True, occupation_mesuree=self.mesuree)


class _Compteur:
    """Combien de nœuds sont dans `execute_node` au même instant.

    Un pic est la seule mesure qui compte : une moyenne, ou un total,
    laisseraient passer exactement le défaut de R-4.
    """

    def __init__(self, duree: float = 0.25) -> None:
        self.actifs = 0
        self.pic = 0
        self.total = 0
        self.echecs: list[str] = []
        self._verrou = threading.Lock()
        self.duree = duree

    def executer(self, node: MissionNode) -> bool:
        with self._verrou:
            self.actifs += 1
            self.total += 1
            self.pic = max(self.pic, self.actifs)
        try:
            time.sleep(self.duree)
            return True
        finally:
            with self._verrou:
                self.actifs -= 1


#: Le portillon attend au plus ce délai avant de déclarer un nœud saturé.
#: En production c'est `plafond_du_noeud()` — 1200 s ; ici, trois secondes.
#:
#: Sans ce réglage, une place jamais rendue **suspend** la suite au lieu de
#: la faire échouer : mesuré, la mutation « ne jamais rendre la place »
#: laissait le test attendre 1200 s et le délai de garde de pytest tuait la
#: session sans qu'aucun test ne soit compté rouge. Une garde qui pend n'est
#: pas une garde (HOS-112).
DELAI_PORTILLON_S = 3.0


def _executeur(execute_node=None, places=None, **kw) -> GraphExecutor:
    kw.setdefault("step_timeout_s", DELAI_PORTILLON_S)
    if places is not None and "capacite_max" not in kw:
        kw["capacite_max"] = places if callable(places) else (lambda: places)
    return GraphExecutor(execute_node=execute_node, **kw)


def _mission(titre: str, n: int) -> tuple[Mission, list[MissionNode]]:
    m = Mission(title=titre, objective=titre)
    return m, [MissionNode(title=f"{titre}-{i}") for i in range(n)]


def _marcher(ex: GraphExecutor, mission, noeuds, passes_max: int = 8) -> None:
    ex.build_graph(mission, noeuds, [])
    ex.start_mission(mission)
    passes = 0
    while (mission.status not in (MissionStatus.COMPLETED, MissionStatus.FAILED)
           and passes < passes_max):
        if ex.execute_step(mission) == 0:
            break
        passes += 1


def _en_parallele(cibles) -> None:
    """Vraie concurrence : des fils relâchés ensemble par une barrière.

    Deux appels séquentiels ne prouveraient rien — c'est précisément ce
    que R-4 exigeait de mesurer.
    """
    barriere = threading.Barrier(len(cibles))

    def enveloppe(f):
        def _f():
            barriere.wait()
            f()
        return _f

    fils = [threading.Thread(target=enveloppe(c)) for c in cibles]
    for f in fils:
        f.start()
    for f in fils:
        f.join(timeout=60)
    assert all(not f.is_alive() for f in fils), "un fil n'a jamais rendu la main"


# ═══ Test 1 — capacité faible ═════════════════════════════════════════

def test_1_une_seule_place_serialise_les_noeuds():
    """Quatre nœuds prêts, une place : jamais deux à la fois."""
    c = _Compteur()
    ex = _executeur(c.executer, places=lambda: 1)
    m, n = _mission("solo", 4)

    _marcher(ex, m, n)

    assert c.total == 4, "des nœuds n'ont pas été exécutés du tout"
    assert c.pic == 1, f"{c.pic} nœuds simultanés pour une seule place"


def test_1_capacite_nulle_ne_fige_pas_la_machine():
    """Zéro place — carte pleine, ou occupation non mesurée (A-15) — ne
    veut pas dire « rien ne tourne ».

    Le refus appartient à l'admission de `RealTaskExecutor`, là où la
    taille réelle du modèle est connue. Le portillon, lui, ne refuse
    rien : il retiendrait la machine sans que personne ne puisse le lever.
    """
    c = _Compteur()
    ex = _executeur(c.executer, places=lambda: 0)
    m, n = _mission("vide", 2)

    _marcher(ex, m, n)

    assert c.total == 2
    assert c.pic == 1


# ═══ Test 2 — capacité suffisante ═════════════════════════════════════

def test_2_plusieurs_places_donnent_de_la_concurrence():
    c = _Compteur()
    ex = _executeur(c.executer, places=lambda: 3)
    m, n = _mission("large", 4)

    _marcher(ex, m, n)

    assert c.pic == 3, f"pic {c.pic} pour trois places annoncées"


# ═══ Test 3 — deux missions ═══════════════════════════════════════════

def test_3_deux_missions_ne_cumulent_pas_leurs_limites():
    """Le défaut R-4, rejoué.

    Deux missions de deux nœuds sur le `GraphExecutor` unique du
    conteneur donnaient quatre nœuds simultanés pour une borne de deux.
    """
    c = _Compteur()
    ex = _executeur(c.executer, places=lambda: 2)
    mA, nA = _mission("A", 2)
    mB, nB = _mission("B", 2)
    for m, n in ((mA, nA), (mB, nB)):
        ex.build_graph(m, n, [])
        ex.start_mission(m)

    _en_parallele([lambda: ex.execute_step(mA), lambda: ex.execute_step(mB)])

    assert c.total == 4, "les quatre nœuds n'ont pas tourné"
    assert c.pic <= 2, (
        f"{c.pic} nœuds simultanés : deux limites locales se sont "
        "additionnées, la borne n'est pas celle de la machine")


def test_3_deux_missions_a_un_seul_noeud_comptent_ensemble():
    """Le cas que le chemin séquentiel laissait passer.

    Avec une place, `execute_step` n'ouvre pas de pool et exécute dans le
    fil appelant. Sans portillon sur ce chemin-là, deux missions d'un nœud
    chacune tourneraient côte à côte sans que rien ne les compte : R-4
    avec un nœud de moins.
    """
    c = _Compteur()
    ex = _executeur(c.executer, places=lambda: 1)
    mA, nA = _mission("A", 1)
    mB, nB = _mission("B", 1)
    for m, n in ((mA, nA), (mB, nB)):
        ex.build_graph(m, n, [])
        ex.start_mission(m)

    _en_parallele([lambda: ex.execute_step(mA), lambda: ex.execute_step(mB)])

    assert c.total == 2
    assert c.pic == 1, f"{c.pic} nœuds simultanés sur le chemin séquentiel"


def test_3_trois_missions_respectent_la_meme_borne():
    c = _Compteur()
    ex = _executeur(c.executer, places=lambda: 2)
    missions = []
    for nom in ("A", "B", "C"):
        m, n = _mission(nom, 2)
        ex.build_graph(m, n, [])
        ex.start_mission(m)
        missions.append(m)

    _en_parallele([lambda m=m: ex.execute_step(m) for m in missions])

    assert c.total == 6
    assert c.pic <= 2, f"pic {c.pic} pour deux places"


# ═══ Test 4 — mission unique ══════════════════════════════════════════

def test_4_la_borne_reste_correcte_dans_une_mission_unique():
    for places in (1, 2, 3):
        c = _Compteur(duree=0.15)
        ex = _executeur(c.executer, places=lambda p=places: p)
        m, n = _mission(f"m{places}", 5)
        _marcher(ex, m, n)
        assert c.total == 5
        assert c.pic == places, f"pic {c.pic} pour {places} place(s)"


# ═══ Test 5 — libération ══════════════════════════════════════════════

def test_5_le_portillon_rend_la_place_sur_toutes_les_sorties():
    """La garde la plus directe, et la seule qui ne passe par aucune attente.

    ## Pourquoi elle existe

    Les autres tests de libération constatent l'effet : le nœud suivant
    passe. Sous la mutation « ne jamais rendre la place », ils le
    constatent aussi — mais en **attendant** le délai du portillon, une
    fois par nœud. Mesuré, cette attente a suffi à tuer la session par
    délai de garde, et le compteur de mutations a lu « zéro rouge ». Une
    garde qui pend n'est pas une garde (HOS-112) : celle-ci échoue tout de
    suite, et elle nomme ce qui est cassé.
    """
    portillon = Portillon()

    with portillon.place(1, 1.0) as obtenue:
        assert obtenue is True
        assert portillon.occupees == 1
    assert portillon.occupees == 0, "sortie normale : la place n'est pas rendue"

    with pytest.raises(RuntimeError):
        with portillon.place(1, 1.0):
            raise RuntimeError("le nœud a levé")
    assert portillon.occupees == 0, "sortie par exception : la place est perdue"

    # Une entrée refusée ne doit rien rendre — sinon le compteur descend
    # sous zéro et la limite devient une passoire.
    portillon._entrer(1, 1.0)
    with portillon.place(1, 0.05) as obtenue:
        assert obtenue is False
    assert portillon.occupees == 1
    portillon._sortir()
    assert portillon.occupees == 0


def test_5_une_place_liberee_laisse_passer_la_suivante():
    """Sans libération, le second nœud n'aurait jamais tourné."""
    c = _Compteur(duree=0.1)
    ex = _executeur(c.executer, places=lambda: 1)
    m, n = _mission("suite", 3)

    _marcher(ex, m, n)

    assert c.total == 3
    assert ex._portillon.occupees == 0, "des places sont restées prises"


# ═══ Test 6 — exception ═══════════════════════════════════════════════

def test_6_un_noeud_qui_leve_libere_sa_place():
    """Une place perdue à chaque échec condamnerait la machine en
    quelques nœuds, et rien ne viendrait la reprendre."""
    appels = {"n": 0}

    def explose(node):
        appels["n"] += 1
        raise RuntimeError("le modèle a rendu l'âme")

    ex = _executeur(explose, places=lambda: 1)
    m, n = _mission("casse", 3)
    _marcher(ex, m, n)

    assert appels["n"] >= 1
    assert ex._portillon.occupees == 0, (
        "une exception a emporté la place avec elle")

    # Et la machine accepte encore du travail après.
    c = _Compteur(duree=0.05)
    ex._execute_node = c.executer
    m2, n2 = _mission("apres", 2)
    _marcher(ex, m2, n2)
    assert c.total == 2


def test_6_un_noeud_qui_rend_False_libere_aussi():
    ex = _executeur(lambda n: False, places=lambda: 1)
    m, n = _mission("echec", 2)
    _marcher(ex, m, n)
    assert ex._portillon.occupees == 0


# ═══ Test 7 — annulation ══════════════════════════════════════════════

def test_7_une_mission_annulee_ne_retient_aucune_place():
    """`cancel_mission` n'interrompt pas un nœud engagé — c'est
    l'invariant du projet. Ce qui doit être vrai, c'est qu'aucune place ne
    survive au nœud lui-même."""
    c = _Compteur(duree=0.1)
    ex = _executeur(c.executer, places=lambda: 2)
    m, n = _mission("annulee", 4)
    ex.build_graph(m, n, [])
    ex.start_mission(m)
    ex.execute_step(m)

    ex.cancel_mission(m)

    assert ex._portillon.occupees == 0


# ═══ Test 8 — concurrence réelle, sur le portillon lui-même ══════════

def test_8_dix_fils_ne_depassent_jamais_la_limite():
    """Le portillon exercé directement, à une échelle où une fenêtre se
    verrait. Deux appels séquentiels ne prouveraient rien."""
    portillon = Portillon()
    barriere = threading.Barrier(10)
    pic = {"n": 0}
    actifs = {"n": 0}
    verrou = threading.Lock()

    def demander():
        barriere.wait()
        with portillon.place(3, 5.0) as obtenue:
            assert obtenue
            with verrou:
                actifs["n"] += 1
                pic["n"] = max(pic["n"], actifs["n"])
            time.sleep(0.05)
            with verrou:
                actifs["n"] -= 1

    fils = [threading.Thread(target=demander) for _ in range(10)]
    for f in fils:
        f.start()
    for f in fils:
        f.join(timeout=30)

    assert pic["n"] <= 3, f"{pic['n']} fils simultanés pour trois places"
    assert portillon.occupees == 0


def test_8_l_attente_est_bornee():
    """Une place jamais rendue ne doit pas retenir la machine pour
    toujours : l'attente expire, et le nœud est traité en échec comme un
    autre, avec sa raison publiée."""
    portillon = Portillon()
    obtenues = []

    def occuper():
        with portillon.place(1, 5.0) as a:
            obtenues.append(a)
            time.sleep(0.6)

    premier = threading.Thread(target=occuper)
    premier.start()
    time.sleep(0.1)

    debut = time.monotonic()
    with portillon.place(1, 0.2) as obtenue:
        attente = time.monotonic() - debut
        assert obtenue is False
    assert attente < 3.0, f"l'attente a duré {attente:.1f} s pour un délai de 0,2"
    premier.join(timeout=10)


def test_8_un_noeud_sature_est_signale_et_compte_en_echec():
    evenements: list[tuple] = []
    ex = _executeur(lambda n: True,
                       places=lambda: 1, step_timeout_s=0.2,
                       on_event=lambda t, p=None, **k: evenements.append((t, p)))
    # Une place déjà prise et jamais rendue par un fil extérieur.
    tenu = threading.Event()

    def occuper():
        with ex._portillon.place(1, 10.0):
            tenu.set()
            time.sleep(1.5)

    fil = threading.Thread(target=occuper, daemon=True)
    fil.start()
    tenu.wait(timeout=5)

    m, n = _mission("sature", 1)
    _marcher(ex, m, n)

    types = [t for t, _ in evenements]
    assert "mission.node_sature" in types, types
    assert "mission.node_failed" in types, types
    fil.join(timeout=10)


# ═══ Test 9 — la capacité décide, pas une constante cachée ════════════

def test_9_la_concurrence_suit_la_capacite_annoncee():
    """Le cœur de R-3 : on change la réponse du gestionnaire, la
    concurrence change avec elle."""
    observes = []
    for places in (1, 2, 4):
        c = _Compteur(duree=0.15)
        ex = _executeur(c.executer, places=lambda p=places: p)
        m, n = _mission(f"cap{places}", 6)
        _marcher(ex, m, n)
        observes.append(c.pic)

    assert observes == [1, 2, 4], (
        f"la concurrence observée {observes} ne suit pas la capacité "
        "annoncée [1, 2, 4] — une constante décide encore")


def test_9_la_capacite_vient_du_gestionnaire_de_ressources():
    """Bout en bout : une vraie carte, un vrai `ResourceManager`, et
    l'empreinte relevée du catalogue."""
    from backend.core.bootstrap.service_registry import (
        _capacite_de_la_machine,
        _empreinte_de_tache_octets,
    )

    empreinte = _empreinte_de_tache_octets()
    assert empreinte is not None
    assert empreinte == EMPREINTE, (
        f"l'empreinte du catalogue a changé : {empreinte / GIO:.2f} Gio")

    class _Conteneur:
        def __init__(self, g):
            self._g = g

        def try_get(self, cle, defaut=None):
            return self._g if cle == "resource_manager" else defaut

    for total, attendu in ((15.984, 1), (48.0, 3), (80.0, 5)):
        g = ResourceManager(gpu_monitor=_Carte(total_gio=total))
        assert _capacite_de_la_machine(_Conteneur(g)) == attendu, (
            f"carte de {total} Gio : {attendu} place(s) attendue(s)")


def test_9_la_capacite_suit_les_reservations_deja_prises():
    """La continuité avec §6.2 : une réservation active réduit les places,
    parce que `places_disponibles` passe par `can_allocate`."""
    g = ResourceManager(gpu_monitor=_Carte(total_gio=48.0))
    assert g.places_disponibles(EMPREINTE) == 3

    g.reserve_resources(EMPREINTE, "ollama", model_name="deja-la")

    assert g.places_disponibles(EMPREINTE) == 2, (
        "la réservation active n'a pas réduit les places : la capacité et "
        "les réservations se sont remises à diverger")


def test_9_une_carte_non_mesuree_n_offre_aucune_place():
    """A-15 traverse : `occupation_mesuree=False` rend zéro place, pas
    « autant qu'on veut »."""
    carte = _Carte()
    carte.mesuree = False
    g = ResourceManager(gpu_monitor=carte)

    assert g.places_disponibles(EMPREINTE) == 0


def test_9_une_empreinte_absurde_ne_rend_pas_de_places():
    g = ResourceManager(gpu_monitor=_Carte(total_gio=48.0))
    assert g.places_disponibles(0) == 0
    assert g.places_disponibles(-1) == 0
    assert g.places_disponibles(100 * GIO) == 0


def test_9_le_compte_est_borne():
    """Une carte immense ne doit pas faire tourner la boucle sans fin."""
    g = ResourceManager(gpu_monitor=_Carte(total_gio=100000.0))
    assert g.places_disponibles(EMPREINTE) == ResourceManager.PLACES_MAX


# ═══ Robustesse — les états dégradés ══════════════════════════════════

def test_une_capacite_qui_leve_retombe_sur_le_repli():
    def casse():
        raise RuntimeError("gestionnaire indisponible")

    ex = _executeur(places=casse)
    from backend.core.config import get_settings
    assert ex._limite_de_concurrence() == get_settings().mission_max_parallel_tasks


def test_une_capacite_inconnue_retombe_sur_le_repli():
    ex = _executeur(places=lambda: None)
    from backend.core.config import get_settings
    assert ex._limite_de_concurrence() == get_settings().mission_max_parallel_tasks


def test_la_borne_est_relue_a_chaque_etape():
    """Une capacité lue une fois au démarrage serait une constante de
    plus. Un modèle qui se charge, une réservation qui se libère : la
    borne doit suivre."""
    places = {"n": 3}
    c = _Compteur(duree=0.12)
    ex = _executeur(c.executer, places=lambda: places["n"])
    m, n = _mission("mouvante", 3)
    ex.build_graph(m, n, [])
    ex.start_mission(m)

    assert ex._limite_de_concurrence() == 3
    places["n"] = 1
    assert ex._limite_de_concurrence() == 1, (
        "la borne a été figée à la construction")


# ═══ Anti-contournement — une seule vérité de capacité ════════════════

def test_le_graphe_ne_calcule_aucune_capacite():
    """Le garde-fou de la mutation G.

    `GraphExecutor` doit poser la question, jamais y répondre. L'assertion
    porte sur ce que le module **nomme** : ni télémétrie GPU, ni compteur,
    ni endpoint de runtime, ni arithmétique sur des octets de VRAM.
    """
    source = io.open(RACINE / "backend/mission/graph_executor.py",
                     encoding="utf-8").read()
    arbre = ast.parse(source)

    imports = {a.name.split(".")[0] for x in ast.walk(arbre)
               if isinstance(x, ast.Import) for a in x.names}
    imports |= {(x.module or "") for x in ast.walk(arbre)
                if isinstance(x, ast.ImportFrom)}
    interdits = [m for m in imports
                 if "resources" in m or "gpu" in m.lower() or "monitoring" in m]
    assert not interdits, (
        f"le graphe importe une source de capacité : {interdits}")

    # Hors docstrings : aucun vocabulaire de mesure physique.
    docs = {id(ast.get_docstring(x, clean=False)) for x in ast.walk(arbre)
            if isinstance(x, (ast.Module, ast.ClassDef, ast.FunctionDef,
                              ast.AsyncFunctionDef))}
    hors_doc = " ".join(
        x.value for x in ast.walk(arbre)
        if isinstance(x, ast.Constant) and isinstance(x.value, str)
        and id(x.value) not in docs).lower()
    for mot in ("dedicated usage", "api/ps", "rocm-smi", "vram_used", "size_vram"):
        assert mot not in hors_doc, (
            f"le graphe manipule {mot!r} : seconde vérité de capacité")


def test_une_seule_autorite_repond_a_la_question_des_places():
    """Personne d'autre que `ResourceManager` ne doit décider combien de
    tâches tiennent."""
    definitions = []
    for f in (RACINE / "backend").rglob("*.py"):
        if "tests" in f.parts:
            continue
        try:
            arbre = ast.parse(io.open(f, encoding="utf-8").read())
        except SyntaxError:
            continue
        for n in ast.walk(arbre):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                    and n.name == "places_disponibles":
                definitions.append(f.relative_to(RACINE).as_posix())

    assert definitions == ["backend/runtime/resources/resource_manager.py"], (
        f"la question des places a plusieurs réponses : {definitions}")


def test_le_portillon_n_est_pas_un_ordonnanceur():
    """Il retient, il ne classe pas.

    Un portillon qui se met à prioriser, à réordonner ou à préempter est
    un ordonnanceur — l'autorité que cette passe s'interdit d'introduire.
    """
    source = io.open(RACINE / "backend/mission/graph_executor.py",
                     encoding="utf-8").read()
    arbre = ast.parse(source)
    classe = next(n for n in ast.walk(arbre)
                  if isinstance(n, ast.ClassDef) and n.name == "Portillon")

    methodes = {n.name for n in classe.body
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    inattendues = methodes - {"__init__", "occupees", "place", "_entrer", "_sortir"}
    assert not inattendues, (
        f"le portillon a gagné des attributions : {inattendues}")

    # Sur les **noms** que la classe manipule, pas sur des sous-chaines du
    # fichier : la premiere version cherchait "sort" et trouvait
    # `_sortir`. Une garde qui se declenche sur une syllabe ne garde rien
    # et finit par etre affaiblie pour la faire taire.
    noms = {n.id for n in ast.walk(classe) if isinstance(n, ast.Name)}
    noms |= {n.attr for n in ast.walk(classe) if isinstance(n, ast.Attribute)}
    noms |= {a.arg for n in ast.walk(classe)
             if isinstance(n, ast.arguments) for a in n.args}
    ordonnancement = {"priority", "priorite", "preempt", "preemption",
                      "sorted", "sort", "heappush", "heappop", "queue",
                      "file_attente", "rang", "age", "aging"}
    fautifs = sorted(noms & ordonnancement)
    assert not fautifs, (
        f"le portillon s'est mis a ordonnancer : {fautifs}")


def test_le_graphe_demande_bien_la_capacite_avant_de_repartir():
    """Structurel, sur l'appel et non sur sa forme : `execute_step` doit
    consulter la borne, faute de quoi la répartition redevient locale."""
    import inspect
    import textwrap

    source = textwrap.dedent(inspect.getsource(GraphExecutor.execute_step))
    appels = {ast.unparse(n.func) for n in ast.walk(ast.parse(source))
              if isinstance(n, ast.Call)}

    assert any(a.endswith("_limite_de_concurrence") for a in appels), (
        "`execute_step` ne demande plus la borne")
    assert any(a.endswith("_executer_sous_portillon") for a in appels), (
        "un chemin d'exécution contourne le portillon")


def test_les_deux_chemins_d_execution_passent_par_le_portillon():
    """Comportemental, pas structurel : le chemin séquentiel comme le
    pool. C'est la moitié de R-4 qu'un test de forme aurait ratée."""
    import inspect
    import textwrap

    for methode in (GraphExecutor.execute_step, GraphExecutor._recolter_en_parallele):
        source = textwrap.dedent(inspect.getsource(methode))
        appels = {ast.unparse(n.func) for n in ast.walk(ast.parse(source))
                  if isinstance(n, ast.Call)}
        direct = [a for a in appels if a.endswith("_execute_node")]
        assert not direct, (
            f"{methode.__name__} appelle `_execute_node` sans portillon : {direct}")
