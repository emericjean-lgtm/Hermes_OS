"""L'admission mesure l'occupation de la carte, pas les poids d'Ollama (A-15).

## Le défaut

`GPUMonitor` essayait `rocm-smi`, puis `nvidia-smi`, puis **retombait sur
`/api/ps`**. Sur la machine cible — Windows, AMD RX 6800 — les deux premiers
n'existent pas : le repli était le chemin **normal** de l'admission, et il
répondait sans erreur, ce qui est la raison pour laquelle il a survécu à
§6.2.

Or les deux mesures ne répondent pas à la même question. `rocm-smi` dit ce
qui est occupé sur la carte ; `/api/ps` dit ce que **pèsent les modèles
résidents d'Ollama** — sans cache KV, sans tampons de calcul, sans un octet
de ce que tient un autre processus.

## Mesuré, trois états de charge, même carte de 15,984 Gio

    état                     /api/ps    occupation réelle    écart
    aucun modèle              0,000            1,314        +1,314
    qwen3.6-35b résident     12,737           14,954        +2,216
    même modèle, cache KV    12,737           15,115        +2,377

L'écart va toujours dans le même sens et il **grandit** : `/api/ps` est resté
figé à 12,737 pendant que l'occupation montait de 161 Mio — ce qui montait
était le cache KV, qu'il ne voit pas.

Rejoué sur le vrai chemin d'admission, à l'état 3 :

    source           1,0 Gio   1,5 Gio   2,0 Gio
    /api/ps           ADMIS     ADMIS    refusé
    occupation réelle refusé   refusé    refusé

Il restait 0,870 Gio. Le modèle de 1,5 Gio admis aurait débordé en mémoire
système : il aurait répondu, dix fois plus lentement, **sans erreur**.

## Ce que ce fichier ne prouve pas

Que la mesure soit exacte au mégaoctet près. Elle somme les compteurs de
tous les adaptateurs : sur une machine à iGPU + carte discrète, elle
sur-estime l'occupation. C'est le sens acceptable — on refuse parfois ce qui
aurait tenu, jamais l'inverse.
"""

from __future__ import annotations

import ast
import io
import re
from pathlib import Path

import pytest

from backend.execution.task_executor import RealTaskExecutor, RuntimeUnavailableError
from backend.ral.capabilities import ChatResponse
from backend.runtime.resources import vram_physique
from backend.runtime.resources.gpu_monitor import GPUMonitor
from backend.runtime.resources.resource_manager import ResourceManager
from backend.runtime.resources.resource_models import GPUInfo, ResourceType

RACINE = Path(__file__).resolve().parents[2]
GIO = 1024 ** 3

# Les chiffres relevés sur la vraie carte, état 3 (cache KV rempli).
CARTE = int(15.984 * GIO)
OCCUPATION_REELLE = int(15.115 * GIO)
POIDS_API_PS = int(12.737 * GIO)


class _Sondes:
    """Un moniteur dont on choisit ce que chaque sonde répond.

    Les trois sondes sont remplacées, pas simulées à moitié : un test qui
    laisserait `_try_rocm_smi` appeler le vrai binaire mesurerait la machine
    de test, pas le contrat.
    """

    def __init__(self, *, rocm=None, nvidia=None, compteurs=None,
                 carte=("AMD Radeon RX 6800", CARTE)):
        self.moniteur = GPUMonitor()
        self.appels: list[str] = []
        self.moniteur._try_rocm_smi = self._sonde("rocm", rocm)
        self.moniteur._try_nvidia_smi = self._sonde("nvidia", nvidia)
        self.moniteur._try_compteurs_windows = self._sonde("compteurs", compteurs)
        self.moniteur._adapter_vram_total = lambda: carte

    def _sonde(self, nom, valeur):
        def sonde():
            self.appels.append(nom)
            return valeur
        return sonde

    def info(self) -> GPUInfo:
        return self.moniteur._poll_now()


def _info(**kw) -> GPUInfo:
    base = dict(name="carte-de-test", vendor="test", vram_total_bytes=CARTE,
                vram_used_bytes=0, vram_free_bytes=CARTE, available=True)
    base.update(kw)
    if "vram_free_bytes" not in kw and "vram_used_bytes" in kw:
        base["vram_free_bytes"] = max(0, CARTE - kw["vram_used_bytes"])
    return GPUInfo(**base)


def _gestionnaire(info: GPUInfo) -> ResourceManager:
    return ResourceManager(gpu_monitor=type("F", (), {"poll": lambda _s: info})())


# ═══ Test A — la source d'admission a la sémantique attendue ══════════

def test_A_l_admission_lit_l_occupation_physique_pas_les_poids(monkeypatch):
    """Le compteur rend l'occupation de la **machine** ; c'est elle qui
    arrive dans `GPUInfo`, sans transformation ni moyenne avec autre chose."""
    monkeypatch.setattr(vram_physique, "occupation_physique_octets",
                        lambda **_: OCCUPATION_REELLE)
    m = GPUMonitor()
    m._adapter_vram_total = lambda: ("AMD Radeon RX 6800", CARTE)

    info = m._try_compteurs_windows()

    assert info is not None
    assert info.vram_used_bytes == OCCUPATION_REELLE
    assert info.vram_free_bytes == CARTE - OCCUPATION_REELLE
    assert info.occupation_mesuree is True


def test_A_l_occupation_inclut_ce_qui_n_appartient_pas_a_ollama(monkeypatch):
    """Au repos, aucun modèle résident, la carte portait quand même
    1,314 Gio — bureau, navigateur, compositeur. `/api/ps` en voyait zéro."""
    monkeypatch.setattr(vram_physique, "occupation_physique_octets",
                        lambda **_: int(1.314 * GIO))
    m = GPUMonitor()
    m._adapter_vram_total = lambda: ("AMD Radeon RX 6800", CARTE)

    info = m._try_compteurs_windows()

    assert info.vram_used_bytes > 0, (
        "aucun modèle chargé ne veut pas dire carte vide : ce qui est mesuré "
        "est l'occupation de la machine, pas celle d'Ollama")


def test_A_une_mesure_absente_n_est_pas_un_zero():
    """`None` et `0` mènent à des décisions opposées : `0` autorise."""
    assert vram_physique.occupation_physique_octets(executer=lambda _: "") is None
    assert vram_physique.occupation_physique_octets(executer=lambda _: None) is None
    assert vram_physique.occupation_physique_octets(executer=lambda _: "0") == 0

    def explose(_):
        raise OSError("compteur indisponible")
    assert vram_physique.occupation_physique_octets(executer=explose) is None


def test_A_une_locale_decimale_ne_fabrique_pas_un_chiffre():
    """Get-Counter suit la locale : `1,5E+10` sur une machine française.
    Mal lu, c'était 1 — soit « carte vide »."""
    assert vram_physique.occupation_physique_octets(
        executer=lambda _: "16234567168,5") == 16234567168


# ═══ Test B — `/api/ps` ne peut pas être lu comme de la VRAM physique ═══

def test_B_le_paquet_d_admission_n_interroge_aucun_runtime(monkeypatch):
    """Comportemental : le compteur échoue, Ollama serait joignable, et
    l'admission dit **je ne sais pas** au lieu de retomber sur les poids.

    C'est la mutation A — remettre `/api/ps` comme source — qui meurt ici :
    un repli rendrait `occupation_mesuree=True` et des chiffres plausibles.
    """
    monkeypatch.setattr(vram_physique, "occupation_physique_octets",
                        lambda **_: None)
    sondes = _Sondes(compteurs=None)
    sondes.moniteur._try_compteurs_windows = \
        GPUMonitor._try_compteurs_windows.__get__(sondes.moniteur)

    info = sondes.info()

    assert info.occupation_mesuree is False
    assert info.vram_used_bytes == 0
    assert info.vram_free_bytes == 0, (
        "une carte non mesurée ne se présente pas comme libre")


# Les modules qui participent à la décision d'admission. `routes.py` en est
# exclu, et c'est délibéré : il expose l'inventaire des modèles résidents —
# le rôle que `/api/ps` garde légitimement — et ne décide de rien. Le test
# qui suit vérifie qu'il l'expose bien comme des **poids**.
_MODULES_DE_DECISION = ("gpu_monitor.py", "vram_physique.py",
                        "resource_manager.py", "allocation_policy.py",
                        "resource_models.py", "memory_manager.py")


def test_B_aucun_appel_a_un_runtime_dans_le_chemin_de_decision():
    """Structurel, sur une propriété : ce qui décide de l'admission ne parle
    à aucun serveur de modèles.

    L'assertion ne porte ni sur une chaîne exacte ni sur une mise en forme :
    on normalise (minuscules, séparateurs retirés) avant de chercher les
    marqueurs, pour qu'un `"/api/" + "ps"` ou un `f"{base}/api/ps"` ne passe
    pas au travers.
    """
    paquet = RACINE / "backend" / "runtime" / "resources"
    marqueurs = ("apips", "apitags", "apigenerate", "sizevram", "11434")
    fautifs: list[str] = []

    for f in sorted(paquet.glob("*.py")):
        if f.name not in _MODULES_DE_DECISION:
            continue
        arbre = ast.parse(io.open(f, encoding="utf-8").read())
        textes = [n.value for n in ast.walk(arbre)
                  if isinstance(n, ast.Constant) and isinstance(n.value, str)]
        nu = re.sub(r"[^a-z0-9]", "", " ".join(textes).lower())
        # Les docstrings de ce paquet *expliquent* pourquoi `/api/ps` n'y
        # est plus. On ne cherche donc les marqueurs que hors docstrings.
        docs = {id(ast.get_docstring(n, clean=False))
                for n in ast.walk(arbre)
                if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef,
                                  ast.AsyncFunctionDef))}
        hors_doc = [t for n, t in
                    ((n, n.value) for n in ast.walk(arbre)
                     if isinstance(n, ast.Constant) and isinstance(n.value, str))
                    if id(t) not in docs]
        nu = re.sub(r"[^a-z0-9]", "", " ".join(hors_doc).lower())
        touches = [m for m in marqueurs if m in nu]
        if touches:
            fautifs.append(f"{f.name}: {touches}")

        imports = {a.name.split(".")[0] for n in ast.walk(arbre)
                   if isinstance(n, ast.Import) for a in n.names}
        imports |= {(n.module or "").split(".")[0] for n in ast.walk(arbre)
                    if isinstance(n, ast.ImportFrom)}
        assert not ({"urllib", "requests", "httpx", "aiohttp"} & imports), (
            f"{f.name} ouvre une connexion réseau : le paquet qui décide de "
            "l'admission ne doit dépendre d'aucun serveur de modèles")

    assert not fautifs, (
        "un endpoint de runtime est revenu dans le chemin de décision — "
        f"c'est exactement A-15 : {fautifs}")


def test_B_l_inventaire_expose_des_poids_pas_de_la_vram_libre():
    """`/api/ps` garde son rôle : dire quels modèles sont résidents et ce
    qu'ils pèsent. Le contrat porte sur le **nom des champs** : un
    `vram_free` ou un `vram_available` construit à partir de `size_vram`
    referait A-15 dans l'API.
    """
    source = io.open(RACINE / "backend" / "runtime" / "resources" / "routes.py",
                     encoding="utf-8").read()
    arbre = ast.parse(source)

    # Les **clés des dictionnaires rendus**, pas toutes les chaînes du
    # fichier : une docstring qui contient « free » ne dit rien du contrat
    # exposé, et la première version de ce test échouait dessus.
    cles = {c.value for d in ast.walk(arbre) if isinstance(d, ast.Dict)
            for c in d.keys
            if isinstance(c, ast.Constant) and isinstance(c.value, str)}
    exposes = {c for c in cles if "vram" in c.lower()}

    assert exposes, "la route n'expose plus rien de la VRAM"
    for c in exposes:
        nu = re.sub(r"[^a-z]", "", c.lower())
        assert "free" not in nu and "libre" not in nu and "available" not in nu, (
            f"la route présente une mesure de poids sous le nom {c!r} : "
            "un lecteur y lira de la VRAM disponible")


# ═══ Test C — la télémétrie fiable prime, et est réellement utilisée ═══

def test_C_rocm_smi_prime_sur_les_compteurs():
    """L'ordre est une propriété observable : la sonde suivante n'est même
    pas appelée."""
    sondes = _Sondes(rocm=_info(vram_used_bytes=3 * GIO),
                     compteurs=_info(vram_used_bytes=9 * GIO))

    info = sondes.info()

    assert info.vram_used_bytes == 3 * GIO
    assert sondes.appels == ["rocm"], (
        f"la priorité est inversée ou une sonde inutile est payée : {sondes.appels}")


def test_C_les_compteurs_prennent_le_relais_quand_rocm_manque():
    """Le cas de cette machine : ni rocm-smi ni nvidia-smi."""
    sondes = _Sondes(rocm=None, nvidia=None,
                     compteurs=_info(vram_used_bytes=OCCUPATION_REELLE))

    info = sondes.info()

    assert info.vram_used_bytes == OCCUPATION_REELLE
    assert sondes.appels == ["rocm", "nvidia", "compteurs"]


def test_C_le_gestionnaire_decide_sur_la_source_retenue():
    """Bout en bout : ce que la sonde mesure est ce que l'admission compare.

    À 15,115 Gio occupés sur 15,984, le plafond de 90 % (14,386 Gio) est
    déjà franchi : **rien** ne passe, pas même 200 Mio. C'est la bonne
    réponse, et c'est ce qui rend le second cas nécessaire — sans lui, le
    test passerait aussi avec une politique qui refuse tout.
    """
    charge = _gestionnaire(_info(vram_used_bytes=OCCUPATION_REELLE))
    assert charge.can_allocate(int(1.5 * GIO), "ollama").success is False
    assert charge.can_allocate(int(0.2 * GIO), "ollama").success is False

    libre = _gestionnaire(_info(vram_used_bytes=int(1.3 * GIO)))
    assert libre.can_allocate(int(1.5 * GIO), "ollama").success is True


# ═══ Test D — sans télémétrie fiable, le comportement est défini ═══════

def test_D_carte_presente_mais_non_mesuree_refuse():
    """Fail-closed. Le refus reprend le mécanisme existant — un
    `ResourceAllocationResult(success=False)` — sans nouvelle politique."""
    g = _gestionnaire(_info(vram_used_bytes=0, vram_free_bytes=0,
                            occupation_mesuree=False))

    resultat = g.can_allocate(1 * GIO, "ollama", model_name="m")

    assert resultat.success is False
    assert "mesur" in (resultat.reason or "").lower(), resultat.reason


def test_D_pas_de_carte_du_tout_ne_contraint_rien():
    """La distinction qui manquait : « pas de carte » n'est pas « carte
    illisible ». Une machine sans GPU n'a pas de VRAM à protéger."""
    g = _gestionnaire(GPUInfo(available=False))

    assert g.can_allocate(8 * GIO, "ollama").success is True


def test_D_le_refus_remonte_jusqu_a_l_executeur():
    """Le contrat vu depuis la tâche : elle ne se lance pas, et elle le dit.

    Sans ce test, le refus pourrait rester enfermé dans la politique et
    l'exécuteur lancer quand même.
    """
    g = _gestionnaire(_info(vram_used_bytes=0, vram_free_bytes=0,
                            occupation_mesuree=False))

    async def chat(*, messages, model, **_):
        raise AssertionError("le modèle a été lancé sans admission")

    ex = RealTaskExecutor(chat=chat, model_for=lambda _t: "m", default_model="m",
                          resource_manager=g, vram_gb_for=lambda _m: 8.0,
                          vram_wait_s=0.2, vram_poll_interval_s=0.05)

    with pytest.raises(RuntimeUnavailableError) as capture:
        ex._admettre_et_reserver("m")

    assert "no VRAM admission" in str(capture.value)


def test_D_une_mesure_qui_revient_debloque_la_tache():
    """Le refus n'est pas définitif : `_check_vram_admission` re-sonde
    pendant toute l'attente. Une sonde qui revient rend la main sans
    intervention."""
    etat = {"mesuree": False, "tours": 0}

    class _Intermittent:
        def poll(self):
            etat["tours"] += 1
            if etat["tours"] >= 3:
                etat["mesuree"] = True
            return _info(vram_used_bytes=0 if etat["mesuree"] else 0,
                         vram_free_bytes=CARTE if etat["mesuree"] else 0,
                         occupation_mesuree=etat["mesuree"])

    g = ResourceManager(gpu_monitor=_Intermittent())
    ex = RealTaskExecutor(chat=None, model_for=lambda _t: "m", default_model="m",
                          resource_manager=g, vram_gb_for=lambda _m: 2.0,
                          vram_wait_s=5.0, vram_poll_interval_s=0.01)

    ex._check_vram_admission("m")  # ne lève pas

    assert etat["tours"] >= 3


# ═══ Test E — les réservations restent hors de la mesure physique ══════

def test_E_une_reservation_ne_touche_pas_la_telemetrie():
    """Deux grandeurs distinctes : ce que la carte porte, et ce qui est
    promis. Les confondre ferait disparaître l'une des deux."""
    info = _info(vram_used_bytes=2 * GIO)
    g = _gestionnaire(info)

    avant = g.get_gpu_info().vram_used_bytes
    g.reserve_resources(4 * GIO, "ollama", model_name="m")
    apres = g.get_gpu_info().vram_used_bytes

    assert avant == apres == 2 * GIO, (
        "la réservation a modifié la mesure physique : la télémétrie ne "
        "mesure plus la carte mais les intentions de Hermes")
    assert g._octets_reserves(ResourceType.VRAM) == 4 * GIO


def test_E_la_decision_additionne_les_deux_sans_les_melanger():
    """2 physiques + 4 réservés + 8 demandés = 14 sur 15,98, sous le
    plafond ; +12 demandés dépasse."""
    g = _gestionnaire(_info(vram_used_bytes=2 * GIO))
    g.reserve_resources(4 * GIO, "ollama", model_name="m1")

    assert g.can_allocate(8 * GIO, "ollama").success is True
    assert g.can_allocate(12 * GIO, "ollama").success is False


# ═══ Test F — la métrique exposée garde sa sémantique ═════════════════

def test_F_le_statut_dit_si_l_occupation_a_ete_mesuree():
    """Sans ce drapeau, le Cockpit lit `vram_used_bytes: 0` et affiche une
    carte libre pour une carte que personne n'a su lire."""
    g = _gestionnaire(_info(vram_used_bytes=0, vram_free_bytes=0,
                            occupation_mesuree=False))

    statut = g.get_status()

    assert statut["gpu"]["occupation_mesuree"] is False
    assert statut["gpu"]["vram_used_bytes"] == 0


def test_F_le_statut_normal_reste_mesure():
    g = _gestionnaire(_info(vram_used_bytes=OCCUPATION_REELLE))
    assert g.get_status()["gpu"]["occupation_mesuree"] is True


def test_F_les_recommandeurs_ne_lisent_pas_un_zero_de_prudence():
    """`vram_free_bytes == 0` sur une carte non mesurée veut dire « non
    mesuré », pas « pleine ». Un recommandeur qui le lit tel quel ne
    proposerait plus que le plus petit modèle du catalogue."""
    from backend.model_intelligence import routes as mi

    g = _gestionnaire(_info(vram_used_bytes=0, vram_free_bytes=0,
                            occupation_mesuree=False))
    precedent = mi._resource_manager
    try:
        mi.set_resource_manager(g)
        assert mi._real_vram_mb() is None, (
            "un zéro de prudence a été pris pour une mesure")
    finally:
        mi.set_resource_manager(precedent)


# ═══ Test G — un modèle lourd ne laisse pas croire à de la place ══════

def test_G_le_scenario_mesure_est_refuse():
    """La régression exacte, avec les chiffres relevés sur la carte.

    Occupation réelle 15,115 Gio sur 15,984 : il restait 0,870 Gio.
    `/api/ps` en annonçait 12,737 et laissait passer 1,5 Gio.
    """
    reel = _gestionnaire(_info(vram_used_bytes=OCCUPATION_REELLE))
    poids = _gestionnaire(_info(vram_used_bytes=POIDS_API_PS))

    assert poids.can_allocate(int(1.5 * GIO), "ollama").success is True, (
        "le témoin ne reproduit plus le défaut : sans lui, le test suivant "
        "ne prouve rien")
    assert reel.can_allocate(int(1.5 * GIO), "ollama").success is False
    assert reel.can_allocate(int(1.0 * GIO), "ollama").success is False


def test_G_l_ecart_grandit_avec_le_cache_kv():
    """`/api/ps` figé à 12,737 pendant que l'occupation montait : la
    différence n'est pas un décalage constant qu'on pourrait corriger par
    une marge fixe."""
    charge = int(14.954 * GIO)
    cache = OCCUPATION_REELLE

    assert cache > charge
    assert (cache - POIDS_API_PS) > (charge - POIDS_API_PS), (
        "si l'écart était constant, une marge forfaitaire suffirait et ce "
        "changement de source ne se justifierait pas")


# ═══ Test H — plusieurs modèles, plusieurs processus ══════════════════

def test_H_l_occupation_somme_tous_les_detenteurs(monkeypatch):
    """29 instances relevées sur la vraie machine : Ollama en tenait une.
    La somme est la seule réponse à « reste-t-il de la place »."""
    instances = [13.838, 0.590, 0.142, 0.079, 0.073, 0.067, 0.058]
    monkeypatch.setattr(vram_physique, "occupation_physique_octets",
                        lambda **_: int(sum(instances) * GIO))
    m = GPUMonitor()
    m._adapter_vram_total = lambda: ("AMD Radeon RX 6800", CARTE)

    info = m._try_compteurs_windows()

    assert info.vram_used_bytes > int(13.838 * GIO), (
        "seul le processus d'inférence a été compté : les autres détenteurs "
        "occupent la même carte")


def test_H_deux_modeles_residents_ne_passent_pas_ensemble():
    """Le contrat §6.2 tient sur la nouvelle source : réservations comptées
    au-dessus d'une occupation physique déjà réelle."""
    g = _gestionnaire(_info(vram_used_bytes=int(1.3 * GIO)))

    a = g.reserve_resources(int(7.0 * GIO), "ollama", model_name="a")
    b = g.reserve_resources(int(7.0 * GIO), "ollama", model_name="b")

    assert a.success is True
    assert b.success is False


# ═══ Anti-contournement — une seule autorité de mesure ════════════════

def _requetes_de_compteur(fichier: Path) -> list[str]:
    """Les chaînes littérales du fichier qui interrogent le compteur."""
    try:
        arbre = ast.parse(io.open(fichier, encoding="utf-8").read())
    except SyntaxError:
        return []
    # Une requête peut être écrite en plusieurs littéraux concaténés : on
    # recolle les constantes voisines avant de chercher, sans quoi couper
    # la chaîne en deux suffirait à passer sous le radar.
    textes = [n.value for n in ast.walk(arbre)
              if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    joint = " ".join(textes)
    return [joint] if "Dedicated Usage" in joint else []


def test_une_seule_requete_d_occupation_machine():
    """Le garde-fou de la mutation F.

    Deux écritures de la même question finissent par diverger : c'est ainsi
    que le Cockpit et l'admission ont lu deux compteurs différents pendant
    tout §6.2. La distinction n'est pas le nom du fichier mais la **question
    posée** — occupation de la machine, ou d'un processus nommé. Un module
    qui interroge le compteur sans filtrer sur un processus pose la première
    question, et il ne peut y en avoir qu'un.
    """
    canonique = RACINE / "backend" / "runtime" / "resources" / "vram_physique.py"
    filtres = ("pid_", "Get-Process", "InstanceName", "$ids")
    machine: list[str] = []

    for f in (RACINE / "backend").rglob("*.py"):
        if "tests" in f.parts or f == canonique:
            continue
        for requete in _requetes_de_compteur(f):
            if not any(marque in requete for marque in filtres):
                machine.append(f.relative_to(RACINE).as_posix())

    assert machine == [], (
        "une seconde mesure de l'occupation machine est apparue — l'admission "
        f"et l'observabilité vont diverger : {machine}")


def test_le_module_canonique_pose_bien_la_question_machine():
    """Le pendant du test précédent : il ne doit pas passer parce que le
    module canonique aurait cessé de mesurer quoi que ce soit."""
    requetes = _requetes_de_compteur(
        RACINE / "backend" / "runtime" / "resources" / "vram_physique.py")

    assert requetes, "le module canonique n'interroge plus le compteur"
    assert "GPU Process Memory" in requetes[0]
    assert "pid_" not in requetes[0], (
        "la source canonique s'est restreinte à un processus : elle ne "
        "répond plus à « reste-t-il de la place sur la carte »")


def test_le_cockpit_lit_la_meme_requete_que_l_admission():
    """Une seule définition, deux exécutions. Le Cockpit passe son propre
    lanceur de commande — injectable pour les tests — mais pas sa propre
    question."""
    source = io.open(RACINE / "backend" / "monitoring" / "gpu_monitor.py",
                     encoding="utf-8").read()
    arbre = ast.parse(source)

    appels = {ast.unparse(n.func) for n in ast.walk(arbre)
              if isinstance(n, ast.Call)}
    assert any(a.endswith("occupation_physique_octets") for a in appels), (
        "le Cockpit a repris une requête à lui : c'est la divergence qui "
        "revient")


def test_la_chaine_de_sondes_ne_se_termine_pas_par_un_chiffre():
    """Anti-bypass structurel : `_poll_now` doit finir sur un aveu, pas sur
    une valeur par défaut.

    L'assertion porte sur le comportement — toutes sondes muettes, carte
    présente — et non sur la forme du code, qu'une réécriture changerait
    sans changer le contrat.
    """
    sondes = _Sondes(rocm=None, nvidia=None, compteurs=None)

    info = sondes.info()

    assert info.occupation_mesuree is False
    assert info.vram_total_bytes == CARTE, (
        "la capacité est connue même sans occupation : c'est ce qui permet "
        "de distinguer « pas de carte » de « carte illisible »")


def test_sans_carte_ni_sonde_l_etat_reste_indisponible():
    sondes = _Sondes(rocm=None, nvidia=None, compteurs=None, carte=("", 0))

    info = sondes.info()

    assert info.available is False
    assert info.vram_total_bytes == 0


def test_F_les_seuils_ne_declarent_pas_saine_une_carte_non_mesuree():
    """`check_thresholds` divisait `vram_used / total` — soit 0 % sur une
    carte non mesurée, donc « sain ». Une surveillance qui rassure sans
    avoir regardé est pire que pas de surveillance."""
    non_mesuree = _gestionnaire(_info(vram_used_bytes=0, vram_free_bytes=0,
                                      occupation_mesuree=False))
    assert non_mesuree.check_thresholds() == []

    pleine = _gestionnaire(_info(vram_used_bytes=int(15.5 * GIO)))
    alertes = pleine.check_thresholds()
    assert any(t == "vram.limit_reached" for t, _ in alertes), alertes
