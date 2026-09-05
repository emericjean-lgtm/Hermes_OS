"""Une empreinte déclarée doit couvrir ce qui sera réellement chargé (A-18).

## Le défaut

`config/models.yaml` déclare une `vram_gb` par rôle, et `_vram_gb_for` la
sert à l'admission — indexée par **tag**, jamais par rôle. Or une empreinte
n'est pas une propriété du modèle seul : le cache KV est alloué à la taille
de la fenêtre, donc elle dépend du **contexte servi**.

`swift` déclarait 2,05 Gio « measured at this num_ctx », avec
`num_ctx: 16384`. Mais ce 16 384 n'est demandé que par la route native, qui
transporte `options.num_ctx`. Le harnais de Hermes Agent passe par `/v1`,
**qui ne le transporte pas** (`backend/runtime/context_guard.py`), et Ollama
applique alors le `PARAMETER num_ctx 131072` du Modelfile.

Mesuré au compteur canonique (A-15), carte vidée entre chaque, même tag :

    num_ctx  16384 -> 2,02 Gio
    num_ctx 131072 -> 4,33 Gio        soit 2,1×

L'audit de la table entière montre que c'est le **seul** tag concerné :
tous les autres rôles déclarent un `num_ctx` égal à celui que leur
Modelfile sert (1,0×). C'est aussi pourquoi `vision` tombait juste dans la
mesure R-6 et `swift` non — les deux mesures n'étaient pas homogènes.

## Ce que ça coûtait, démontré

Réservation de 2,05 Gio pour une charge de 4,33 :

    carte à  8,00 Gio : 2 réservations accordées -> 16,66 Gio -> déborde de 0,68
    carte à 10,00 Gio : 2 réservations accordées -> 18,66 Gio -> déborde de 2,68

Le plafond de 90 % de la politique protégeait le chiffre **déclaré**, pas
le chiffre **servi**.

Aggravant : ce tag est `_HERMES_AGENT_FALLBACK_MODEL`, vers lequel tout
modèle non prouvé agentique est substitué — c'est-à-dire, aujourd'hui,
tous.

## Ce que ce fichier ne prouve pas

Que 4,33 Gio soit le pire cas absolu. C'est le pire cas **mesuré** pour la
fenêtre que le Modelfile sert. Un Modelfile réécrit plus large le
déplacerait, et rien ici ne le détecterait automatiquement : le test
`test_le_contexte_de_mesure_couvre_celui_du_role` vérifie la cohérence des
données déclarées, pas la recette du tag.
"""

from __future__ import annotations

import ast
import io
from pathlib import Path

import pytest

from backend.core.config import load_models_config

RACINE = Path(__file__).resolve().parents[2]
GIO = 1024 ** 3

#: Mesures relevées pendant A-18 sur `lfm2.5-2.6b-125k`, compteur canonique.
MESURE_16K = 2.02
MESURE_128K = 4.331


def _roles() -> dict:
    return {n: r for n, r in load_models_config().get("roles", {}).items()
            if isinstance(r, dict) and r.get("model")}


def _executeur_reel():
    """L'exécuteur tel que le bootstrap le construit, avec ses fermetures.

    Deux méthodes suffisent au conteneur : la fabrique ne demande qu'un
    répartiteur d'événements et laisse tout le reste à `None`. C'est ce
    qui permet de tester `_vram_gb_for` — une fermeture, donc inatteignable
    autrement — sur son comportement plutôt que sur le texte du module.
    """
    from backend.core.bootstrap.service_registry import _make_task_executor

    class _Repartiteur:
        def scoped(self, _source):
            return lambda *a, **k: None

    class _Conteneur:
        def get(self, cle):
            return _Repartiteur() if cle == "event_dispatcher" else None

        def try_get(self, _cle, defaut=None):
            return defaut

    return _make_task_executor(_Conteneur())


def _pire_cas(role: dict) -> float:
    """Ce que l'admission doit retenir pour ce rôle.

    `vram_gb_max` quand il est déclaré — le pire contexte que le **tag**
    puisse servir — sinon `vram_gb`, ce qui est correct pour les rôles dont
    la fenêtre demandée est celle que leur Modelfile sert déjà.
    """
    return float(role.get("vram_gb_max") or role.get("vram_gb") or 0.0)


# ═══ 1 — l'empreinte déclarée est bien celle que R-3 et l'admission lisent

def test_1_l_empreinte_lue_est_celle_du_fichier():
    from backend.core.bootstrap.service_registry import _empreinte_de_tache_octets

    declarees = [float(r["vram_gb"]) for r in _roles().values() if r.get("vram_gb")]
    assert _empreinte_de_tache_octets() == int(max(declarees) * GIO), (
        "R-3 ne dérive plus sa capacité du catalogue")


def test_1_la_derivation_suit_le_catalogue(monkeypatch):
    """Le chiffre est **dérivé**, pas écrit dans le code.

    `test_1_l_empreinte_lue_est_celle_du_fichier` compare la dérivation au
    même fichier : une constante figée à la valeur du jour y passerait —
    mesuré, la mutation « l'empreinte devient une constante » restait
    verte. Ici on change le catalogue et on exige que le résultat bouge.
    """
    from backend.core.bootstrap.service_registry import _empreinte_de_tache_octets

    faux = {"roles": {
        "petit": {"model": "t1", "vram_gb": 1.5, "num_ctx": 4096},
        "gros": {"model": "t2", "vram_gb": 27.5, "num_ctx": 4096},
    }}
    monkeypatch.setattr("backend.core.config.load_models_config", lambda: faux)

    assert _empreinte_de_tache_octets() == int(27.5 * GIO), (
        "la dérivation ne suit pas le catalogue : une constante décide")


def test_1_un_catalogue_sans_empreinte_ne_rend_pas_un_chiffre(monkeypatch):
    """`None` laisse le graphe sur son repli documenté ; un chiffre inventé
    ferait dériver une capacité de rien."""
    from backend.core.bootstrap.service_registry import _empreinte_de_tache_octets

    monkeypatch.setattr("backend.core.config.load_models_config",
                        lambda: {"roles": {"a": {"model": "t", "num_ctx": 4096}}})
    assert _empreinte_de_tache_octets() is None


def test_1_le_tag_corrige_porte_ses_deux_chiffres():
    """Deux consommateurs, deux questions.

    Le routeur choisit un modèle en sachant qu'il le servira à 16k : pour
    lui, 2,05 est juste. Écraser `vram_gb` avec le pire cas fait échouer
    toute recommandation sous 4,33 Gio — mesuré, c'est exactement ce qu'a
    fait la première version de cette correction, et
    `test_recommend_with_vram_constraint` l'a dit.
    """
    for nom in ("swift", "double_check"):
        role = _roles()[nom]
        assert role["vram_gb"] == pytest.approx(MESURE_16K, abs=0.05), (
            f"{nom} : le coût à son propre num_ctx a changé")
        assert role["vram_gb_max"] == pytest.approx(MESURE_128K, abs=0.01), (
            f"{nom} : le pire cas ne couvre pas les {MESURE_128K} Gio "
            "mesurés à la fenêtre que /v1 sert")
        assert role["vram_gb_max_num_ctx"] == 131072


# ═══ 2 — unités ═══════════════════════════════════════════════════════

def test_2_les_empreintes_sont_des_gibioctets_plausibles():
    """Un facteur 1024 perdu se voit ici, et nulle part ailleurs avant la
    carte."""
    for nom, role in _roles().items():
        v = role.get("vram_gb")
        if v is None:
            continue
        assert isinstance(v, (int, float)) and not isinstance(v, bool)
        assert 0.1 <= float(v) <= 80.0, (
            f"{nom} déclare {v} — ni des gibioctets, ni des octets")


def test_2_la_conversion_en_octets_est_exacte():
    from backend.core.bootstrap.service_registry import _empreinte_de_tache_octets

    octets = _empreinte_de_tache_octets()
    assert octets == int(max(float(r["vram_gb"]) for r in _roles().values()
                             if r.get("vram_gb")) * 1024 ** 3)
    assert octets > 1024 ** 3, "l'empreinte est passée sous le gibioctet"


# ═══ 3 — la propriété de sûreté (§9) ══════════════════════════════════

def test_3_le_pire_cas_couvre_au_moins_le_cout_du_role():
    """La règle qui rend le piège impossible à recréer en silence.

    Un pire cas inférieur au coût courant serait une contradiction : la
    réservation retiendrait moins que ce que le rôle consomme déjà à sa
    propre fenêtre.
    """
    fautifs = []
    for nom, role in _roles().items():
        courant = float(role.get("vram_gb") or 0.0)
        if courant and _pire_cas(role) < courant:
            fautifs.append(f"{nom}: pire cas {_pire_cas(role)} < {courant}")
    assert not fautifs, f"pire cas incohérent : {fautifs}"


def test_3_un_pire_cas_declare_dit_a_quelle_fenetre():
    """Un chiffre sans sa fenêtre est exactement ce qui a produit A-18."""
    for nom, role in _roles().items():
        if not role.get("vram_gb_max"):
            continue
        assert role.get("vram_gb_max_num_ctx"), (
            f"{nom} déclare un pire cas sans dire à quel contexte")
        assert int(role["vram_gb_max_num_ctx"]) > int(role.get("num_ctx") or 0), (
            f"{nom} : le pire cas est déclaré à une fenêtre qui n'est pas "
            "plus large que celle du rôle — il ne décrit alors rien de plus")


def test_3_un_tag_partage_ne_declare_pas_deux_empreintes():
    """Deux rôles sur un tag, deux chiffres : l'ordre de lecture déciderait
    lequel sert à réserver."""
    par_tag: dict[str, set] = {}
    for role in _roles().values():
        if role.get("vram_gb"):
            par_tag.setdefault(role["model"], set()).add(_pire_cas(role))
    divergents = {t: v for t, v in par_tag.items() if len(v) > 1}
    assert not divergents, (
        f"un tag porte deux empreintes contradictoires : {divergents}")


def test_3_l_admission_prend_le_maximum_d_un_tag_partage(monkeypatch):
    """Et si deux chiffres apparaissaient malgré tout, c'est le plus grand
    qui doit servir — jamais le dernier lu.

    Le test construit la table comme le bootstrap la construit, sur une
    configuration où les deux rôles divergent : sans la règle du maximum,
    le résultat dépend de l'ordre du dictionnaire.
    """
    # Le **plus lourd d'abord**, délibérément : avec le plus lourd en
    # dernier, « prendre le dernier lu » et « prendre le maximum » rendent
    # la même réponse et le test ne distingue rien — mesuré, la mutation
    # passait au vert. L'ordre est ici ce qui fait la preuve.
    faux = {"roles": {
        "a": {"model": "tag-partage", "vram_gb": 2.05, "vram_gb_max": 4.33,
              "vram_gb_max_num_ctx": 131072, "num_ctx": 16384},
        "b": {"model": "tag-partage", "vram_gb": 2.05, "num_ctx": 16384},
    }}
    monkeypatch.setattr("backend.core.config.load_models_config", lambda: faux)

    # La règle, sur le **comportement** de la vraie fabrique — pas sur une
    # copie de son code dans le test.
    #
    # Une première version cherchait `"max("` et `"_vram_by_model.get("`
    # dans le texte de la fonction. Les deux chaînes y existent ailleurs —
    # `_max_vram_mb_now`, `_vram_gb_for` — si bien que l'assertion restait
    # vraie après avoir retiré le maximum : mesuré, la mutation passait au
    # vert. Une garde écrite sur une sous-chaîne ne garde rien.
    executeur = _executeur_reel()
    assert executeur._vram_gb_for("tag-partage") == 4.33, (
        "la table a pris le dernier rôle lu : l'ordre du dictionnaire "
        "décide de ce qui sera réservé")


# ═══ 4 — la capacité dérivée reste juste ══════════════════════════════

def test_4_la_correction_ne_change_pas_le_maximum():
    """A-18 touche `swift`, qui n'est pas le rôle le plus lourd. La capacité
    dérivée de R-3 était donc juste avant, et le reste après — c'est le
    résultat qu'il fallait démontrer, pas supposer."""
    from backend.core.bootstrap.service_registry import _empreinte_de_tache_octets

    assert _empreinte_de_tache_octets() == int(13.68 * GIO)


def test_4_la_capacite_derivee_suit_la_carte():
    from backend.runtime.resources.resource_manager import ResourceManager
    from backend.runtime.resources.resource_models import GPUInfo

    class _Carte:
        def __init__(self, total_gio, utilise_gio=0.0):
            self.t, self.u = int(total_gio * GIO), int(utilise_gio * GIO)

        def poll(self):
            return GPUInfo(name="t", vendor="t", vram_total_bytes=self.t,
                           vram_used_bytes=self.u,
                           vram_free_bytes=max(0, self.t - self.u),
                           available=True)

    empreinte = int(4.33 * GIO)
    for total, attendu in ((15.984, 3), (48.0, 9)):
        g = ResourceManager(gpu_monitor=_Carte(total))
        assert g.places_disponibles(empreinte) == attendu, (
            f"carte de {total} Gio à {empreinte / GIO:.2f} Gio par tâche")


# ═══ 5 — une empreinte sous-estimée ne doit plus passer inaperçue ═════

def test_5_une_sous_estimation_fait_deborder_et_le_test_le_montre():
    """Le scénario mesuré, rejoué : réserver 2,05 pour une charge de 4,33.

    Ce test ne vérifie pas le code — il vérifie que la valeur déclarée
    aujourd'hui ne reproduit plus le débordement. Avec 2,05, deux
    réservations passent sur une carte à 8 Gio et la charge réelle dépasse
    la capacité ; avec 4,33, la seconde est refusée.
    """
    from backend.runtime.resources.resource_manager import ResourceManager
    from backend.runtime.resources.resource_models import GPUInfo

    CARTE = int(15.984 * GIO)
    OCCUPEE = int(8.0 * GIO)

    class _Carte:
        def poll(self):
            return GPUInfo(name="t", vendor="t", vram_total_bytes=CARTE,
                           vram_used_bytes=OCCUPEE,
                           vram_free_bytes=CARTE - OCCUPEE, available=True)

    def accordees(empreinte_gio):
        g = ResourceManager(gpu_monitor=_Carte())
        return sum(1 for i in range(2)
                   if g.reserve_resources(int(empreinte_gio * GIO), "ollama",
                                          model_name=f"m{i}").success)

    sous_estimee = accordees(2.05)
    reelle = accordees(MESURE_128K)

    charge_reelle = 8.0 + sous_estimee * MESURE_128K
    assert charge_reelle > CARTE / GIO, (
        "le témoin ne reproduit plus le débordement : le test suivant ne "
        "prouverait rien")
    assert 8.0 + reelle * MESURE_128K <= CARTE / GIO, (
        f"{reelle} réservation(s) à l'empreinte réelle débordent encore")
    assert reelle < sous_estimee


def test_5_l_empreinte_declaree_couvre_la_mesure_reelle():
    """La propriété de sûreté, énoncée sur la donnée : ce que le catalogue
    promet doit couvrir ce que le compteur a vu."""
    role = _roles()["swift"]
    assert _pire_cas(role) >= MESURE_128K - 0.01, (
        f"pire cas {_pire_cas(role)} Gio pour {MESURE_128K} Gio mesurés au "
        "contexte que /v1 sert")


# ═══ 6 — une surestimation reste permise, et coûte ═══════════════════

def test_6_surestimer_refuse_plus_tot_mais_ne_deborde_jamais():
    from backend.runtime.resources.resource_manager import ResourceManager
    from backend.runtime.resources.resource_models import GPUInfo

    CARTE = int(15.984 * GIO)

    class _Carte:
        def poll(self):
            return GPUInfo(name="t", vendor="t", vram_total_bytes=CARTE,
                           vram_used_bytes=0, vram_free_bytes=CARTE,
                           available=True)

    g = ResourceManager(gpu_monitor=_Carte())
    assert g.places_disponibles(int(4.33 * GIO)) == 3
    assert g.places_disponibles(int(8.0 * GIO)) == 1, (
        "surestimer doit réduire les places, pas les supprimer")


# ═══ 7 — le modèle lourd ══════════════════════════════════════════════

def test_7_le_role_le_plus_lourd_est_declare_a_son_contexte_servi():
    """Le rôle qui porte le maximum est celui dont la justesse décide de
    R-3. Sa fenêtre déclarée doit être celle à laquelle son empreinte a été
    relevée — sinon la capacité dérivée est fausse à la racine."""
    roles = _roles()
    lourd = max((r for r in roles.values() if r.get("vram_gb")),
                key=lambda r: float(r["vram_gb"]))
    assert not lourd.get("vram_gb_max"), (
        "le rôle le plus lourd déclare un pire cas distinct de son coût "
        "courant : la capacité dérivée par R-3 n'est alors plus la bonne")
    assert float(lourd["vram_gb"]) == pytest.approx(13.68, abs=0.01)


# ═══ 8 — tous les rôles ═══════════════════════════════════════════════

def test_8_chaque_role_declare_une_empreinte():
    """Un rôle sans `vram_gb` est invisible à l'admission : `_vram_gb_for`
    rend `None` et le contrôle devient un no-op pour ce modèle."""
    sans = [n for n, r in _roles().items() if not r.get("vram_gb")]
    assert not sans, f"rôles sans empreinte déclarée : {sans}"


def test_8_chaque_role_dit_a_quelle_fenetre_il_tourne():
    manquants = [n for n, r in _roles().items() if not r.get("num_ctx")]
    assert not manquants, (
        f"rôles sans fenêtre déclarée — leur empreinte ne veut alors rien "
        f"dire : {manquants}")


# ═══ 9 — modèle non mesurable ════════════════════════════════════════

def test_9_un_tag_inconnu_rend_None_et_non_zero():
    """`_vram_gb_for` rend `None` pour un tag absent du catalogue.

    Les deux valeurs mènent au même no-op d'admission — `_admettre_et_
    reserver` sort sur `if not vram_gb` — donc la différence est de
    **contrat**, pas de comportement : `None` se lit « on ne sait pas »,
    `0.0` se lit « ce modèle ne coûte rien ». C'est la distinction que R-6
    a établie, et la docstring de `_vram_gb_for` la promet depuis HOS-069.

    Une première version testait un dictionnaire reconstruit dans le test,
    pas la vraie fermeture : la mutation qui rendait `0.0` restait verte.
    """
    executeur = _executeur_reel()

    assert executeur._vram_gb_for("un-tag-qui-n-existe-pas") is None
    assert executeur._vram_gb_for("lfm2.5-2.6b-125k") == 4.33


# ═══ 10 — comportement conservateur ══════════════════════════════════

def test_10_le_catalogue_ne_declare_aucune_empreinte_sous_sa_mesure():
    """La règle générale, appliquée à tout ce qu'on a mesuré.

    Seul `lfm2.5-2.6b-125k` a été mesuré aux deux fenêtres pendant A-18 ;
    les autres n'ont qu'un point, à leur contexte déclaré, et le test ne
    peut donc rien affirmer de plus pour eux. C'est dit ici plutôt que
    laissé croire.
    """
    mesures = {"lfm2.5-2.6b-125k": MESURE_128K}
    for tag, mesuree in mesures.items():
        pires = [_pire_cas(r) for r in _roles().values()
                 if r.get("model") == tag and r.get("vram_gb")]
        assert pires, f"{tag} n'est plus dans le catalogue"
        assert min(pires) >= mesuree - 0.01, (
            f"{tag} : pire cas {min(pires)} Gio pour {mesuree} mesurés")


# ═══ 11 — pas de second calcul de capacité ═══════════════════════════

def test_11_une_seule_fonction_derive_l_empreinte_de_tache():
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
                    and n.name == "_empreinte_de_tache_octets":
                definitions.append(f.relative_to(RACINE).as_posix())
    assert definitions == ["backend/core/bootstrap/service_registry.py"], (
        f"l'empreinte de tâche est dérivée à plusieurs endroits : {definitions}")


def test_11_le_catalogue_n_est_pas_une_source_de_mesure_gpu():
    """`vram_gb` est une **estimation déclarée**. La mesure, c'est A-15 pour
    la carte et R-6 pour un run. Confondre les trois est ce que CLAUDE.md
    nomme « quatre grandeurs, quatre noms »."""
    entete = io.open(RACINE / "config/models.yaml", encoding="utf-8").read()[:8000]
    assert "estimation" in entete.lower(), (
        "l'en-tête ne dit plus que `vram_gb` est une estimation déclarée")
    assert "R-6" in entete or "runs.vram" in entete, (
        "l'en-tête ne distingue plus l'empreinte déclarée de la mesure")
    assert "vram_gb_max" in entete, (
        "l'en-tête n'explique plus pourquoi il y a deux chiffres")


# ═══ 12 — pas de contournement du ResourceManager ════════════════════

def test_12_la_reservation_ne_prend_son_chiffre_que_de_l_empreinte_injectee():
    """Le catalogue fournit un chiffre ; c'est `ResourceManager` qui décide.

    ## Ce que ce test ne reproche pas

    Une première version interdisait à tout module hors bootstrap de lire
    `vram_gb`. Elle rougissait sur `core/router.py`,
    `planner/runtime_recommender.py`, `model_intelligence_models.py` et
    `api/routes/system.py` — qui lisent la taille pour **choisir** un
    modèle qui tienne, ou pour l'afficher. C'est le travail du RAL, pas
    une décision d'admission, et l'interdire aurait été une garde qui
    punit le bon comportement.

    La propriété réelle est plus étroite : sur le chemin de réservation,
    le nombre d'octets vient de `self._vram_gb_for` — l'empreinte injectée
    au bootstrap — et de rien d'autre. Un chiffre puisé ailleurs ici
    serait une seconde autorité.
    """
    import inspect
    import textwrap

    from backend.execution.task_executor import RealTaskExecutor

    source = textwrap.dedent(
        inspect.getsource(RealTaskExecutor._admettre_et_reserver))
    arbre = ast.parse(source)

    appels = {ast.unparse(n.func) for n in ast.walk(arbre)
              if isinstance(n, ast.Call)}
    assert any(a.endswith("_vram_gb_for") for a in appels), (
        "la réservation ne lit plus l'empreinte injectée")
    assert any(a.endswith("reserve_resources") for a in appels), (
        "la réservation ne passe plus par `ResourceManager`")

    interdits = [a for a in appels
                 if "load_models_config" in a or "get_settings" in a]
    assert not interdits, (
        f"la réservation puise un chiffre hors de l'empreinte injectée : "
        f"{interdits}")
