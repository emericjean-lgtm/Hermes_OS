# -*- coding: utf-8 -*-
"""La temperature du GPU, mesuree plutot qu'absente (HOS-284).

## Le defaut que ces gardes tiennent

`GPUInfo.temperature_celsius` existe depuis HOS-035 ; `allocation_policy`
refuse une admission au-dessus de `max_gpu_temp_c` ; `resource_manager`
publie une alerte a 85 degC ; la barre d'instruments a un thermometre.
**Rien ne remplissait le champ** : seule la branche `nvidia-smi` le posait,
et sur cette machine — AMD RX 6800 — `nvidia-smi` n'existe pas. Le seuil
etait un controle qui n'a jamais pu se declencher, et le thermometre un
composant que personne n'avait vu.

## Comment les capteurs ont ete identifies

Pas par leur index de documentation : en CHARGEANT la carte. Serie du
2026-09-10, `ADL2_New_QueryPMLogData_Get`, douze capteurs supportes :

    t(s)   [1]clk  [23]W   [8]     [27]
       0      243     26     28      29     repos
       3     2080    135     32      39     charge : horloge et puissance
      12     2026    139     37      44     sautent ; [8] et [27] montent
      15        0      7     30      30     fin : la puissance retombe
      36        0      7     28      29     d'un coup, la temperature non

L'inertie est le discriminant. Et `[27] >= [8]` a chacun des vingt-cinq
releves : la jonction est plus chaude que le bord, toujours.

Verifie de bout en bout par HTTP pendant une inference reelle :
37/44 degC en charge, 29/30 degC apres, VRAM a 3,78 Gio.
"""
from __future__ import annotations

import ast
from pathlib import Path

from backend.runtime.resources import temperature_gpu as tg
from backend.runtime.resources.gpu_monitor import GPUMonitor
from backend.runtime.resources.resource_models import GPUInfo

RACINE = Path(__file__).resolve().parents[2]


# ── Ce que la sonde ose affirmer ──────────────────────────────────────

def test_deux_capteurs_plausibles_donnent_une_temperature():
    t = tg.interpreter((1, 37), (1, 44))
    assert t is not None
    assert (t.edge, t.hotspot) == (37.0, 44.0)


def test_un_index_qui_glisse_sur_une_horloge_est_refuse():
    """Le garde-fou qui compte : un mauvais index rendrait un nombre
    parfaitement credible. Mesure — l'horloge monte a 2026 MHz et la
    puissance a 139 W pendant que la temperature est a 37 degC."""
    assert tg.interpreter((1, 2026), (1, 2030)) is None
    assert tg.interpreter((1, 139), (1, 140)) is None


def test_une_jonction_plus_froide_que_le_bord_est_refusee():
    """Physiquement impossible : si elle l'est, ce ne sont pas les
    capteurs qu'on croit. Rendre le couple afficherait un nombre faux."""
    assert tg.interpreter((1, 44), (1, 37)) is None


def test_l_egalite_reste_acceptee():
    """Au repos, bord et jonction se rejoignent — mesure : 28 et 28. Un
    garde-fou en `>` strict effacerait la temperature au repos, c'est-a-dire
    la plupart du temps."""
    assert tg.interpreter((1, 28), (1, 28)) == tg.TemperatureGPU(28.0, 28.0)


def test_un_capteur_non_supporte_ne_se_devine_pas():
    """Une carte d'une autre generation peut ne pas publier la jonction.
    Rendre le bord pour les deux serait inventer la seconde valeur."""
    assert tg.interpreter((0, 30), (1, 31)) is None
    assert tg.interpreter((1, 30), (0, 31)) is None


def test_zero_n_est_pas_une_temperature():
    """`0` est ce que rend un capteur eteint, pas une carte a 0 degC. La
    plage commence a 1 pour cette raison."""
    assert tg.interpreter((1, 0), (1, 0)) is None


# ── Ce que la sonde n'importe pas ─────────────────────────────────────

def test_la_sonde_ne_depend_d_aucun_paquet_a_installer():
    """`atiadlxx.dll` est posee par le PILOTE. Une sonde qui exigerait
    `pyadl`, `wmi` ou LibreHardwareMonitor serait une dependance de plus
    a installer sur chaque machine — et un service a lancer."""
    arbre = ast.parse((RACINE / "backend" / "runtime" / "resources"
                       / "temperature_gpu.py").read_text(encoding="utf-8"))
    modules = set()
    for n in ast.walk(arbre):
        if isinstance(n, ast.Import):
            modules |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom) and n.module:
            modules.add(n.module.split(".")[0])
    assert modules <= {"__future__", "ctypes", "logging", "sys", "threading",
                       "dataclasses", "typing"}, modules


def test_la_sonde_ne_rend_jamais_un_chiffre_par_defaut():
    """Un `or 0`, un `except: return 0.0` — la faute de A-15 transposee au
    thermometre. Aucune constante numerique ne doit sortir d'un `return`."""
    source = (RACINE / "backend" / "runtime" / "resources"
              / "temperature_gpu.py").read_text(encoding="utf-8")
    for noeud in ast.walk(ast.parse(source)):
        if isinstance(noeud, ast.Return) and isinstance(noeud.value, ast.Constant):
            assert noeud.value.value is None, (
                f"un `return {noeud.value.value!r}` : une sonde qui invente")


# ── Le branchement sur le moniteur ────────────────────────────────────

def test_le_moniteur_pose_la_temperature_sans_ecraser_nvidia_smi(monkeypatch):
    """`nvidia-smi` rend deja `temperature.gpu`. Une sonde qui l'ecraserait
    ferait diverger deux chemins qui doivent dire la meme chose."""
    monkeypatch.setattr(tg, "temperatures",
                        lambda: tg.TemperatureGPU(edge=40.0, hotspot=50.0))
    depart = GPUInfo(name="carte", available=True, temperature_celsius=61.0)
    enrichi = GPUMonitor._avec_temperature(depart)
    assert enrichi.temperature_celsius == 61.0, "la mesure amont a ete ecrasee"
    assert enrichi.temperature_hotspot_celsius == 50.0


def test_le_moniteur_remplit_le_champ_vide(monkeypatch):
    monkeypatch.setattr(tg, "temperatures",
                        lambda: tg.TemperatureGPU(edge=40.0, hotspot=50.0))
    enrichi = GPUMonitor._avec_temperature(GPUInfo(name="carte", available=True))
    assert enrichi.temperature_celsius == 40.0
    assert enrichi.temperature_hotspot_celsius == 50.0


def test_une_sonde_muette_laisse_le_champ_absent(monkeypatch):
    """`None` veut dire « non mesuree », jamais « froide »."""
    monkeypatch.setattr(tg, "temperatures", lambda: None)
    enrichi = GPUMonitor._avec_temperature(GPUInfo(name="carte", available=True))
    assert enrichi.temperature_celsius is None
    assert enrichi.temperature_hotspot_celsius is None


def test_la_temperature_ne_depend_pas_de_l_occupation_lisible(monkeypatch):
    """Une carte dont la VRAM n'est pas lisible a tout de meme une
    temperature lisible : `occupation_mesuree=False` ne dit rien du
    thermometre. Les brancher ensemble perdrait la mesure disponible."""
    monkeypatch.setattr(tg, "temperatures",
                        lambda: tg.TemperatureGPU(edge=42.0, hotspot=48.0))
    aveugle = GPUInfo(name="carte", available=True, occupation_mesuree=False)
    enrichi = GPUMonitor._avec_temperature(aveugle)
    assert enrichi.temperature_celsius == 42.0
    assert enrichi.occupation_mesuree is False, "le drapeau A-15 a bouge"


def test_sans_carte_detectable_rien_n_est_pose(monkeypatch):
    """`available=False` veut dire « pas de carte ». Y coller une
    temperature contredirait le champ d'a cote."""
    monkeypatch.setattr(tg, "temperatures",
                        lambda: tg.TemperatureGPU(edge=42.0, hotspot=48.0))
    enrichi = GPUMonitor._avec_temperature(GPUInfo(available=False))
    assert enrichi.temperature_celsius is None


# ── La chaine jusqu'a l'ecran ─────────────────────────────────────────

def test_la_vue_publie_les_deux_temperatures():
    """Le champ existait cote modele et n'atteignait pas le JSON : c'est
    exactement la moitie de chaine qui a fait vivre le defaut trois mois."""
    source = (RACINE / "backend" / "runtime" / "resources"
              / "resource_manager.py").read_text(encoding="utf-8")
    assert '"temperature_celsius"' in source
    assert '"temperature_hotspot_celsius"' in source


def test_la_barre_d_instruments_lit_le_champ():
    """Une sonde sans consommateur n'est pas une fonctionnalite."""
    barre = (RACINE / "frontend" / "src" / "components"
             / "instrument-bar.tsx").read_text(encoding="utf-8")
    assert "temperature_celsius" in barre
    assert "temperature_hotspot_celsius" in barre


def test_le_thermometre_ne_disparait_plus_quand_la_mesure_manque():
    """La barre annonce dans son propre commentaire qu'une lecture
    indisponible s'affiche « –– ». Le thermometre, lui, disparaissait —
    et un cadran absent se lit « rien a surveiller »."""
    barre = (RACINE / "frontend" / "src" / "components"
             / "instrument-bar.tsx").read_text(encoding="utf-8")
    assert "{temp !== null && (" not in barre, (
        "le thermometre est de nouveau conditionne a la mesure")


# ── La carte reelle, quand elle est la ────────────────────────────────

def test_si_le_pilote_repond_le_couple_d_index_designe_bien_deux_temperatures():
    """La garde qui manquait, trouvee par mutation.

    Intervertir `_CAPTEUR_EDGE` et `_CAPTEUR_HOTSPOT` ne rougissait rien :
    l'echange fait lire la jonction comme le bord, l'invariant
    `hotspot >= edge` se rompt, la sonde rend `None` — et une garde qui
    TOLERE `None` ne voit plus rien. Le filet du module masquait l'erreur
    qu'il devait signaler.

    Ce qu'elle prouve, et seulement cela : **si** le pilote publie les deux
    index interroges, alors la sonde doit rendre un couple. Sur une machine
    sans pilote AMD la premisse est fausse et la garde ne prouve rien — ce
    qui est dit ici plutot que decouvert plus tard."""
    bruts = tg.capteurs_bruts()
    if bruts is None:
        return
    assert tg._CAPTEUR_EDGE in bruts, f"capteur {tg._CAPTEUR_EDGE} non publie"
    assert tg._CAPTEUR_HOTSPOT in bruts, f"capteur {tg._CAPTEUR_HOTSPOT} non publie"
    assert tg.temperatures() is not None, (
        "le pilote publie les deux capteurs et la sonde ne rend rien : le "
        "couple d'index ne designe pas ce qu'on croit")


def test_si_la_sonde_repond_elle_respecte_ses_propres_invariants():
    """Ni `skip` ni faux vert : sur une machine sans ADL la sonde rend
    `None` et la garde passe en disant vrai. Sur celle-ci, elle repond, et
    ce qu'elle rend doit obeir aux regles que le module s'est donnees.

    Mesure du 2026-09-10 : 28/28 degC au repos, 37/44 degC en charge."""
    releve = tg.temperatures()
    if releve is None:
        return
    assert tg._PLAGE[0] <= releve.edge <= tg._PLAGE[1]
    assert tg._PLAGE[0] <= releve.hotspot <= tg._PLAGE[1]
    assert releve.hotspot >= releve.edge
