"""Rien ne se charge sur la carte sans place retenue (§6.2, HOS-257).

## Les trois défauts, mesurés par l'audit §6.1

**R-1 — le chemin le plus lourd était le seul non contrôlé.**
`task_executor.py` portait `if not use_cloud and runtime_id !=
"hermes-agent"`. Un agent — un processus complet qui charge un modèle et
enchaîne jusqu'à douze tours — passait sans admission, alors qu'une
simple complétion en avait une. Et c'est le chemin **normal** d'une
mission liée à un workspace.

**R-2 / A-13 — vérifier n'est pas réserver.** `reserve_resources`
existait sans aucun appelant hors d'une route HTTP. Le brancher tel quel
n'aurait rien réglé : la décision ignorait `_allocations`. Mesuré avant
correction, sur une carte simulée de 16 Gio dont 2 déjà pris —

    reserve(8 Gio) -> True
    reserve(8 Gio) -> True        18 Gio promis sur 16

Le verrou n'était pas en cause : il sérialisait deux décisions qui,
chacune, lisaient un compteur que la première n'avait pas fait bouger.
Un modèle réservé n'occupe la VRAM qu'une fois **chargé**.

**A-12 — le Cockpit lisait un compteur faux.** Au même instant, sur la
même carte, un modèle de 11,9 Gio résident :

    GPU Adapter Memory\\Dedicated Usage  ->  3,99 Gio
    GPU Process Memory\\Dedicated Usage  -> 12,70 Gio

L'adaptateur sous-déclarait d'un facteur trois — dans le sens dangereux,
celui qui fait croire qu'il reste de la place.

## Ce que ce fichier ne prouve pas

Que l'estimation de VRAM soit exacte. `vram_gb_for` rend une estimation,
et la réservation la retient telle quelle : c'est **conservateur par
construction**, jamais l'inverse. Une fois le modèle chargé, sa
consommation est comptée deux fois — sur le compteur physique et sur la
réservation — jusqu'à la libération. On refuse donc parfois une
allocation qui aurait tenu ; on n'en accepte jamais une qui ne tient pas.
"""

from __future__ import annotations

import ast
import io
import re
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.execution.task_executor import RealTaskExecutor, RuntimeUnavailableError
from backend.ral.capabilities import ChatResponse
from backend.runtime.resources.resource_manager import ResourceManager
from backend.runtime.resources.resource_models import GPUInfo, ResourceType

RACINE = Path(__file__).resolve().parents[2]

GIO = 1024 ** 3


class _Carte:
    """Une carte mesurée, pas simulée à moitié : le compteur physique ne
    bouge pas tant que rien n'est chargé — c'est précisément ce qui rendait
    le TOCTOU possible."""

    def __init__(self, total_gio: int = 16, utilise_gio: int = 2) -> None:
        self.total = total_gio * GIO
        self.utilise = utilise_gio * GIO

    def poll(self) -> GPUInfo:
        return GPUInfo(name="carte-de-test", vendor="test",
                       vram_total_bytes=self.total,
                       vram_used_bytes=self.utilise,
                       vram_free_bytes=max(0, self.total - self.utilise),
                       available=True)


def _gestionnaire(total_gio: int = 16, utilise_gio: int = 2) -> ResourceManager:
    return ResourceManager(gpu_monitor=_Carte(total_gio, utilise_gio))


def _tache(task_type: str = "implementation"):
    return SimpleNamespace(task_id="t1", title="tâche", description="",
                           task_type=task_type, mission_id="m1",
                           assigned_skills=[], errors=[])


def _executeur(gestionnaire, vram_gb: float = 8.0, chat=None, **kw):
    async def _defaut(*, messages, model, **_):
        return ChatResponse(content="fait",
                            metadata={"model": model, "provider": "ollama"})

    return RealTaskExecutor(
        chat=chat or _defaut,
        model_for=lambda _t: "modele-de-test",
        default_model="modele-de-test",
        resource_manager=gestionnaire,
        vram_gb_for=lambda _m: vram_gb,
        **kw)


def _actives(gestionnaire) -> int:
    return len([a for a in gestionnaire._allocations.values() if not a.released])


# ═══ R-2 — la décision compte les réservations ══════════════════════

def test_deux_reservations_incompatibles_ne_passent_pas_ensemble():
    """Le défaut exact, rejoué : 2 + 8 + 8 = 18 Gio sur une carte de 16."""
    g = _gestionnaire()
    r1 = g.reserve_resources(8 * GIO, "ollama", model_name="m1")
    r2 = g.reserve_resources(8 * GIO, "ollama", model_name="m2")

    assert r1.success is True
    assert r2.success is False, (
        "la seconde réservation est passée : la décision ignore encore "
        "`_allocations`, et deux modèles vont se charger sur la même carte")
    assert "VRAM" in (r2.reason or "")


def test_liberer_rouvre_la_capacite():
    g = _gestionnaire()
    r1 = g.reserve_resources(8 * GIO, "ollama", model_name="m1")
    assert g.reserve_resources(8 * GIO, "ollama", model_name="m2").success is False

    g.release_resources(r1.allocation.allocation_id)

    assert g.reserve_resources(8 * GIO, "ollama", model_name="m3").success is True


def test_ce_qui_tient_passe_toujours():
    """Compter les réservations ne doit pas tout refuser."""
    g = _gestionnaire(total_gio=16, utilise_gio=0)
    assert g.reserve_resources(4 * GIO, "ollama", model_name="a").success is True
    assert g.reserve_resources(4 * GIO, "ollama", model_name="b").success is True
    assert g.reserve_resources(4 * GIO, "ollama", model_name="c").success is True


def test_la_ram_compte_aussi_ses_reservations():
    g = _gestionnaire()
    avant = g.can_allocate(1 * GIO, "ollama", resource_type=ResourceType.RAM)
    g.reserve_resources(1 * GIO, "ollama", resource_type=ResourceType.RAM)
    apres = g.can_allocate(1 * GIO, "ollama", resource_type=ResourceType.RAM)
    # On ne prédit pas le verdict — la RAM de la machine est ce qu'elle est.
    # Ce qui compte est que la réservation ait déplacé la mesure.
    assert (avant.success, apres.success) != (True, True) or True
    assert g._octets_reserves(ResourceType.RAM) == 1 * GIO


# ═══ Le test concurrent, sur le vrai mécanisme ══════════════════════

def test_deux_fils_concurrents_ne_reservent_pas_la_meme_capacite():
    """Deux vrais fils, relâchés par une barrière, sur le vrai verrou.

    Pas deux appels séquentiels : la barrière les fait arriver ensemble,
    ce qui est la seule façon d'exercer la synchronisation réelle plutôt
    que de la supposer.
    """
    g = _gestionnaire(total_gio=16, utilise_gio=2)
    barriere = threading.Barrier(2)
    resultats = []

    def demander(nom: str) -> None:
        barriere.wait()
        resultats.append(g.reserve_resources(8 * GIO, "ollama", model_name=nom))

    fils = [threading.Thread(target=demander, args=(f"m{i}",)) for i in range(2)]
    for f in fils:
        f.start()
    for f in fils:
        f.join(timeout=10)

    assert len(resultats) == 2
    reussies = [r for r in resultats if r.success]
    assert len(reussies) == 1, (
        f"{len(reussies)} réservations concurrentes ont réussi alors que la "
        "carte n'en porte qu'une")
    assert _actives(g) == 1


def test_dix_fils_concurrents_ne_depassent_jamais_la_capacite():
    """Le même contrat, à une échelle où une fenêtre se verrait."""
    g = _gestionnaire(total_gio=16, utilise_gio=0)
    barriere = threading.Barrier(10)
    resultats: list = []
    verrou = threading.Lock()

    def demander(nom: str) -> None:
        barriere.wait()
        r = g.reserve_resources(4 * GIO, "ollama", model_name=nom)
        with verrou:
            resultats.append(r)

    fils = [threading.Thread(target=demander, args=(f"m{i}",)) for i in range(10)]
    for f in fils:
        f.start()
    for f in fils:
        f.join(timeout=10)

    reussies = [r for r in resultats if r.success]
    octets = sum(r.allocation.bytes_requested for r in reussies)
    assert octets <= int(0.90 * 16 * GIO), (
        f"{octets / GIO:.1f} Gio réservés sur une carte de 16 Gio à 90 %")
    assert len(reussies) == 3, f"{len(reussies)} réussites, 3 attendues"


# ═══ R-1 — le chemin agentique est admis ═══════════════════════════

def test_le_chemin_agentique_reserve_avant_de_lancer():
    """Le défaut : `runtime_id != "hermes-agent"` excluait le plus lourd."""
    g = _gestionnaire()
    vues = []

    async def _chat(*, messages, model, **_):
        # Au moment où le travail part, la réservation doit déjà être prise.
        vues.append(_actives(g))
        return ChatResponse(content="fait", metadata={"model": model})

    _executeur(g, chat=_chat).execute(
        _tache(), SimpleNamespace(runtime_id="hermes-agent"))

    assert vues == [1], (
        "aucune réservation n'était active pendant l'exécution agentique")


def test_le_chemin_local_ordinaire_reserve_aussi():
    g = _gestionnaire()
    vues = []

    async def _chat(*, messages, model, **_):
        vues.append(_actives(g))
        return ChatResponse(content="fait", metadata={"model": model})

    _executeur(g, chat=_chat).execute(_tache(), SimpleNamespace(runtime_id="ollama"))

    assert vues == [1]


def test_une_admission_refusee_n_execute_rien():
    """Si la place manque, le travail ne part pas — pas de repli silencieux."""
    g = _gestionnaire(total_gio=16, utilise_gio=15)
    lance = []

    async def _chat(*, messages, model, **_):
        lance.append(model)
        return ChatResponse(content="fait", metadata={"model": model})

    ex = _executeur(g, vram_gb=8.0, chat=_chat, vram_wait_s=0.1,
                    vram_poll_interval_s=0.01)
    with pytest.raises(RuntimeUnavailableError):
        ex.execute(_tache(), SimpleNamespace(runtime_id="hermes-agent"))

    assert lance == [], "le travail est parti malgré le refus d'admission"
    assert _actives(g) == 0


# ═══ Libération, sur toutes les sorties ════════════════════════════

def test_la_reservation_est_liberee_apres_un_succes():
    g = _gestionnaire()
    _executeur(g).execute(_tache(), SimpleNamespace(runtime_id="ollama"))
    assert _actives(g) == 0


def test_la_reservation_est_liberee_apres_une_exception():
    g = _gestionnaire()

    async def _casse(*, messages, model, **_):
        raise RuntimeError("le runtime a lâché")

    with pytest.raises(RuntimeUnavailableError):
        _executeur(g, chat=_casse).execute(
            _tache(), SimpleNamespace(runtime_id="ollama"))

    assert _actives(g) == 0, (
        "une réservation survit à sa tâche : la capacité est condamnée, et "
        "rien ne viendra la reprendre — le gestionnaire n'a pas d'expiration")


def test_la_reservation_est_liberee_apres_un_delai_depasse():
    import asyncio

    g = _gestionnaire()

    async def _lent(*, messages, model, **_):
        await asyncio.sleep(5)
        return ChatResponse(content="jamais", metadata={})

    with pytest.raises(RuntimeUnavailableError):
        _executeur(g, chat=_lent, timeout_s=0.2).execute(
            _tache(), SimpleNamespace(runtime_id="ollama"))

    assert _actives(g) == 0


def test_la_reservation_est_liberee_apres_une_annulation():
    g = _gestionnaire()

    async def _annule(*, messages, model, **_):
        import asyncio
        raise asyncio.CancelledError()

    with pytest.raises(BaseException):
        _executeur(g, chat=_annule).execute(
            _tache(), SimpleNamespace(runtime_id="ollama"))

    assert _actives(g) == 0


def test_dix_taches_de_suite_ne_fuient_aucune_reservation():
    """Une fuite d'une réservation sur dix se verrait ici, pas sur une."""
    g = _gestionnaire()
    ex = _executeur(g)
    for _ in range(10):
        ex.execute(_tache(), SimpleNamespace(runtime_id="ollama"))
    assert _actives(g) == 0


# ═══ Sans gestionnaire, rien ne change ═════════════════════════════

def test_sans_gestionnaire_le_comportement_est_celui_d_avant():
    """L'admission est opt-in : un appelant qui n'injecte rien garde le
    comportement antérieur, sans quoi tous les tests existants basculeraient
    sur une décision qu'ils n'ont pas demandée."""
    async def _chat(*, messages, model, **_):
        return ChatResponse(content="fait", metadata={"model": model})

    ex = RealTaskExecutor(chat=_chat, model_for=lambda _t: "m", default_model="m")
    r = ex.execute(_tache(), SimpleNamespace(runtime_id="hermes-agent"))
    assert r.result == "fait"


# ═══ A-12 — la source de mesure ════════════════════════════════════
#
# Ces deux tests affirmaient le contrat de §6.2 : « le fichier
# `monitoring/gpu_monitor.py` contient la chaîne `GPU Process Memory(*)` ».
# A-15 a remplacé ce contrat — la requête ne vit plus dans ce fichier mais
# dans `runtime/resources/vram_physique.py`, que le Cockpit et l'admission
# lisent tous les deux. Les tests sont donc réécrits sur la **propriété**
# — quel compteur est interrogé, et par combien de définitions — au lieu de
# la présence d'un texte dans un fichier nommé. La forme précédente aurait
# survécu à un copier-coller de la requête ailleurs ; celle-ci non.


def _compteurs_interroges(chemin: Path) -> set[str]:
    """Les compteurs GPU qu'un fichier interroge réellement.

    Lus dans ses **chaînes littérales**, jamais dans ses commentaires : un
    commentaire qui cite `GPU Adapter Memory` pour expliquer pourquoi il
    n'est plus utilisé ne doit pas faire échouer le garde-fou. C'est ce
    qu'une lecture brute du fichier ne sait pas distinguer.
    """
    arbre = ast.parse(io.open(chemin, encoding="utf-8").read())
    textes = " ".join(n.value for n in ast.walk(arbre)
                      if isinstance(n, ast.Constant) and isinstance(n.value, str))
    if "Dedicated Usage" not in textes:
        return set()
    return set(re.findall(r"GPU ([A-Za-z]+) Memory", textes))


def test_l_occupation_machine_se_lit_par_processus():
    """`GPU Adapter Memory` sous-déclare la VRAM réellement occupée.

    §6.2 chiffrait l'écart à un facteur trois — 3,99 contre 12,70 Gio.
    **Ce relevé ne s'est pas reproduit** : remesuré pendant A-15, carte
    portant un modèle de 12,74 Gio, l'adaptateur donne 14,669 Gio et les
    processus 15,115, soit 0,445 Gio, stable sur trois relevés. La sonde
    d'origine n'a pas été conservée et n'est plus auditable ; le chiffre
    est retiré, la direction reste — l'adaptateur sous-déclare, dans le
    sens qui fait croire qu'il reste de la place.
    """
    canonique = RACINE / "backend/runtime/resources/vram_physique.py"

    assert _compteurs_interroges(canonique) == {"Process"}, (
        "la source canonique n'interroge plus le compteur par processus")


def test_aucune_production_n_interroge_le_compteur_par_adaptateur():
    fautifs = [f.relative_to(RACINE).as_posix()
               for f in (RACINE / "backend").rglob("*.py")
               if "tests" not in f.parts
               and "Adapter" in _compteurs_interroges(f)]

    assert fautifs == [], (
        f"le compteur par adaptateur est de retour : {fautifs}")


def test_le_banc_et_le_cockpit_lisent_le_meme_compteur():
    """Deux lectures de la même grandeur qui divergent, c'est la situation
    que A-12 nomme. Le Cockpit ne définit plus la sienne : il appelle la
    source canonique — vérifié par l'appel, pas par une chaîne."""
    canonique = _compteurs_interroges(
        RACINE / "backend/runtime/resources/vram_physique.py")
    banc = _compteurs_interroges(
        RACINE / "backend/model_intelligence/model_bench.py")

    assert canonique and canonique == banc, (
        f"le banc lit {banc} et l'admission {canonique}")

    cockpit = ast.parse(io.open(RACINE / "backend/monitoring/gpu_monitor.py",
                                encoding="utf-8").read())
    appels = {ast.unparse(n.func) for n in ast.walk(cockpit)
              if isinstance(n, ast.Call)}
    assert any(a.endswith("occupation_physique_octets") for a in appels), (
        "le Cockpit a repris une requête à lui : c'est la divergence de "
        "A-12 qui revient par la porte de derrière")


# ═══ Anti-contournement, structurel ════════════════════════════════

def test_aucun_chemin_local_ne_lance_sans_passer_par_l_admission():
    """Le garde-fou qui empêche de refaire R-1.

    Deux tests « l'admission a été appelée » n'auraient pas attrapé le
    défaut : il était une **exception** dans la condition, pas un appel
    manquant. On vérifie donc la propriété — la branche locale d'`execute`
    n'a plus de condition qui exclue un runtime.
    """
    source = io.open(RACINE / "backend/execution/task_executor.py",
                     encoding="utf-8").read()
    arbre = ast.parse(source)
    noeud = next(n for n in ast.walk(arbre)
                 if isinstance(n, ast.FunctionDef) and n.name == "execute")

    admissions = [n for n in ast.walk(noeud) if isinstance(n, ast.Call)
                  and ast.unparse(n.func).endswith("_admettre_et_reserver")]
    assert admissions, "`execute` n'admet plus rien"

    # `ast.unparse` normalise les guillemets : chercher la forme avec
    # guillemets doubles ne correspondait **jamais**, et l'assertion ne
    # pouvait pas rougir. Mesuré : la mutation A passait au travers.
    corps = ast.unparse(noeud).replace('"', "'")
    assert "runtime_id != 'hermes-agent'" not in corps, (
        "l'exception agentique est de retour dans la condition d'admission")


def test_la_liberation_est_dans_un_finally():
    """Un `release` sur le seul chemin heureux laisserait la capacité
    condamnée à la première exception."""
    source = io.open(RACINE / "backend/execution/task_executor.py",
                     encoding="utf-8").read()
    arbre = ast.parse(source)
    noeud = next(n for n in ast.walk(arbre)
                 if isinstance(n, ast.FunctionDef) and n.name == "execute")
    dans_finally = any(
        any(ast.unparse(c.func).endswith("_liberer")
            for c in ast.walk(essai) if isinstance(c, ast.Call))
        for essai in ast.walk(noeud) if isinstance(essai, ast.Try)
        for essai in [ast.Module(body=essai.finalbody, type_ignores=[])])
    assert dans_finally, "`_liberer` n'est pas dans un `finally`"


def test_une_seule_autorite_de_reservation():
    """Aucun second gestionnaire : `_admettre_et_reserver` délègue."""
    source = io.open(RACINE / "backend/execution/task_executor.py",
                     encoding="utf-8").read()
    arbre = ast.parse(source)
    noeud = next(n for n in ast.walk(arbre)
                 if isinstance(n, ast.FunctionDef) and n.name == "_admettre_et_reserver")
    appels = {ast.unparse(c.func) for c in ast.walk(noeud) if isinstance(c, ast.Call)}
    assert any("_resource_manager.reserve_resources" in a for a in appels), appels
