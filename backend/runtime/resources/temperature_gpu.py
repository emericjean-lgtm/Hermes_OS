r"""La température du GPU, lue au pilote AMD (HOS-284).

## Le défaut que ce module ferme

`GPUInfo.temperature_celsius` existe depuis HOS-035, `allocation_policy`
refuse une admission au-dessus de `max_gpu_temp_c`, `resource_manager`
publie une alerte à 85 °C, et la barre d'instruments a un thermomètre
prêt à s'afficher. **Rien ne remplissait le champ.** Seule la branche
`nvidia-smi` le posait — et sur cette machine, AMD, `nvidia-smi` n'existe
pas. Le seuil de température était donc un contrôle qui n'a jamais pu se
déclencher, et le thermomètre un composant que personne n'a jamais vu.

## D'où vient le chiffre

De `atiadlxx.dll`, l'AMD Display Library installée **par le pilote**. Pas
d'outil tiers, pas de service à démarrer, pas de dépendance à ajouter :
la carte est lue par la bibliothèque de son propre pilote, en `ctypes`.

Mesuré le 2026-09-10 sur cette machine : `rocm-smi`, `amd-smi` et
`nvidia-smi` sont tous absents ; `atiadlxx.dll` est présente et
`ADL2_Main_Control_Create` rend `0`.

## Comment les capteurs ont été identifiés

**Pas par leur index de documentation.** `ADL2_New_QueryPMLogData_Get`
rend un tableau de 256 capteurs dont 12 sont déclarés supportés ici, et
lire un index dans une entête serait exactement la supposition que ce
dépôt paie cher. Les deux températures ont été trouvées en **chargeant la
carte** et en regardant lesquels se comportent comme une température :

    t(s)   [1]clk  [23]W   [8]     [27]
       0      243     26     28      29     ← repos
       3     2080    135     32      39     ← charge : horloge et puissance
       6     1966    138     36      43       sautent d'un coup ; [8] et
      12     2026    139     37      44       [27] montent lentement
      15        0      7     30      30     ← fin : la puissance retombe
      21        0      7     29      29       instantanément, la
      36        0      7     28      29       température décroît

L'inertie est le discriminant : une puissance passe de 139 W à 7 W en
moins de trois secondes, une température non. `[27]` est resté ≥ `[8]` à
chacun des vingt-cinq relevés — la relation physique entre la jonction et
le bord de la puce.

`ADL2_OverdriveN_Temperature_Get` et `ADL2_Overdrive6_Temperature_Get`
rendent tous deux `-8` (*not supported*) sur RDNA2 : PMLog est le seul
chemin, et c'est pour cela qu'il est le seul implémenté.

## Ce que le module refuse de faire

Rendre un chiffre dont il n'est pas sûr. Un pilote qui renumérote ses
capteurs, une carte d'une autre génération, un `supported` à zéro : dans
tous ces cas le module rend `None`, et `None` veut dire « non mesurée »,
jamais « froide ». Deux garde-fous, parce qu'un mauvais index produirait
un nombre parfaitement crédible :

- la valeur doit tomber dans une plage physiquement plausible ;
- la jonction doit être au moins aussi chaude que le bord.

Un index qui glisserait sur une horloge (2026) ou une puissance (139)
échoue le premier ; un qui intervertirait les deux échoue le second.
"""

from __future__ import annotations

import ctypes
import logging
import sys
import threading
from ctypes import Structure, byref, c_char, c_int, c_void_p
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger("hermes_os.runtime.temperature_gpu")

#: Index des capteurs dans le tableau PMLog, **mesurés** sur RX 6800 le
#: 2026-09-10 (voir la série ci-dessus), pas lus dans une entête.
_CAPTEUR_EDGE = 8
_CAPTEUR_HOTSPOT = 27

#: Plage physiquement plausible pour une température de die, en °C. Elle
#: n'est pas là pour valider la carte : elle est là pour qu'un index qui
#: glisse sur une horloge ou une puissance ne passe pas pour une
#: température. Bornes larges à dessein — une carte gelée à 5 °C au
#: démarrage à froid reste lisible, une jonction à 110 °C aussi.
_PLAGE = (1.0, 130.0)

_ADL_OK = 0
_ADL_MAX_PATH = 256
_PMLOG_MAX_CAPTEURS = 256
_VENDEUR_AMD = 1002


@dataclass(frozen=True)
class TemperatureGPU:
    """Ce que la carte porte, et ce qu'on n'en sait pas.

    `hotspot` est la jonction — la grandeur qui gouverne l'étranglement
    thermique. `edge` est celle que les outils nomment « GPU temperature »
    et que `nvidia-smi` rend sous `temperature.gpu` ; c'est donc elle qui
    alimente `GPUInfo.temperature_celsius`, pour que les deux chemins
    disent la même chose.
    """

    edge: float
    hotspot: float


class _AdapterInfo(Structure):
    _fields_ = [
        ("iSize", c_int), ("iAdapterIndex", c_int),
        ("strUDID", c_char * _ADL_MAX_PATH),
        ("iBusNumber", c_int), ("iDeviceNumber", c_int),
        ("iFunctionNumber", c_int), ("iVendorID", c_int),
        ("strAdapterName", c_char * _ADL_MAX_PATH),
        ("strDisplayName", c_char * _ADL_MAX_PATH),
        ("iPresent", c_int), ("iExist", c_int),
        ("strDriverPath", c_char * _ADL_MAX_PATH),
        ("strDriverPathExt", c_char * _ADL_MAX_PATH),
        ("strPNPString", c_char * _ADL_MAX_PATH),
        ("iOSDisplayIndex", c_int),
    ]


class _Capteur(Structure):
    _fields_ = [("supported", c_int), ("value", c_int)]


class _SortiePMLog(Structure):
    _fields_ = [("size", c_int),
                ("sensors", _Capteur * _PMLOG_MAX_CAPTEURS)]


_MALLOC = ctypes.CFUNCTYPE(c_void_p, c_int)


@_MALLOC
def _allouer(taille: int):
    """L'allocateur que réclame `ADL2_Main_Control_Create`.

    Défini au niveau du module, et non dans la fonction qui ouvre le
    contexte : un `CFUNCTYPE` local serait collecté à la sortie de la
    fonction pendant que l'ADL en garde le pointeur.
    """
    return ctypes.cast(ctypes.create_string_buffer(taille), c_void_p).value


_verrou = threading.Lock()
#: `(bibliotheque, contexte, index_adaptateur)`, ouvert une fois. Ouvrir
#: et fermer un contexte ADL à chaque relevé coûterait plus cher que le
#: relevé lui-même, et la barre d'instruments interroge en continu.
_session: Optional[tuple] = None
#: `True` quand l'ouverture a déjà échoué : sur une machine sans pilote
#: AMD, réessayer à chaque appel chargerait une DLL absente en boucle.
_impossible = False


def _ouvrir() -> Optional[tuple]:
    """La bibliothèque, un contexte et l'adaptateur AMD, ou `None`."""
    global _impossible

    if _impossible:
        return None
    if not sys.platform.startswith("win"):
        # L'ADL est propre à Windows. Sous Linux, le pilote publie
        # `/sys/class/drm/card*/device/hwmon/hwmon*/temp1_input`, de même
        # sémantique — rien ici ne permet de l'exercer, et écrire une
        # sonde qu'on ne peut pas mesurer serait refaire la faute que
        # A-15 corrige. Même posture que `vram_physique`.
        _impossible = True
        return None
    try:
        adl = ctypes.CDLL("atiadlxx.dll")
        contexte = c_void_p()
        if adl.ADL2_Main_Control_Create(_allouer, 1, byref(contexte)) != _ADL_OK:
            _impossible = True
            return None
        nombre = c_int(0)
        if adl.ADL2_Adapter_NumberOfAdapters_Get(
                contexte, byref(nombre)) != _ADL_OK or nombre.value <= 0:
            _impossible = True
            return None
        tampon = (_AdapterInfo * nombre.value)()
        if adl.ADL2_Adapter_AdapterInfo_Get(
                contexte, tampon, ctypes.sizeof(tampon)) != _ADL_OK:
            _impossible = True
            return None
        for a in tampon:
            if a.iVendorID == _VENDEUR_AMD:
                return adl, contexte, a.iAdapterIndex
    except Exception:  # noqa: BLE001 - une sonde ne casse pas ce qu'elle mesure
        logger.debug("ADL indisponible", exc_info=True)
    _impossible = True
    return None


def _plausible(valeur: float) -> bool:
    return _PLAGE[0] <= valeur <= _PLAGE[1]


def interpreter(edge: tuple[int, int],
                hotspot: tuple[int, int]) -> Optional[TemperatureGPU]:
    """Deux couples `(supporte, valeur)` bruts, ou `None`.

    Separee de l'appel `ctypes` a dessein : c'est ici que se decide ce
    qu'on ose affirmer, et cette decision doit s'eprouver sans carte. Le
    reste du module n'est que du transport.
    """
    if not edge[0] or not hotspot[0]:
        return None
    e, h = float(edge[1]), float(hotspot[1])
    if not _plausible(e) or not _plausible(h):
        logger.debug("temperatures hors plage : edge=%s hotspot=%s", e, h)
        return None
    if h < e:
        # La jonction ne peut pas etre plus froide que le bord. Si elle
        # l'est, ce ne sont pas les capteurs qu'on croit : rendre le
        # couple serait afficher un nombre faux et credible.
        logger.debug("invariant rompu : hotspot=%s < edge=%s", h, e)
        return None
    return TemperatureGPU(edge=e, hotspot=h)


def capteurs_bruts() -> Optional[dict[int, int]]:
    """Les capteurs que le pilote declare supportes, index -> valeur.

    Sert au diagnostic et a une garde : si le pilote publie les deux index
    qu'on interroge et que `temperatures()` ne rend rien, c'est que le
    couple d'index ne designe pas ce qu'on croit. `None` = pas de pilote.
    """
    with _verrou:
        global _session

        if _session is None:
            _session = _ouvrir()
        if _session is None:
            return None
        adl, contexte, index = _session
        sortie = _SortiePMLog()
        try:
            if adl.ADL2_New_QueryPMLogData_Get(
                    contexte, index, byref(sortie)) != _ADL_OK:
                return None
        except Exception:  # noqa: BLE001
            logger.debug("releve PMLog impossible", exc_info=True)
            return None
        return {i: c.value for i, c in enumerate(sortie.sensors) if c.supported}


def temperatures() -> Optional[TemperatureGPU]:
    """La température de la carte, ou `None` si elle n'est pas mesurable.

    `None` couvre : pas de pilote AMD, pas de carte, capteur non déclaré
    supporté, valeur hors plage plausible, jonction plus froide que le
    bord. Tous appellent la même conduite — ne rien afficher — et aucun
    ne doit se lire « la carte est froide ».
    """
    with _verrou:
        global _session

        if _session is None:
            _session = _ouvrir()
        if _session is None:
            return None
        adl, contexte, index = _session

        sortie = _SortiePMLog()
        try:
            if adl.ADL2_New_QueryPMLogData_Get(
                    contexte, index, byref(sortie)) != _ADL_OK:
                return None
        except Exception:  # noqa: BLE001
            logger.debug("relevé PMLog impossible", exc_info=True)
            return None

        edge = sortie.sensors[_CAPTEUR_EDGE]
        hotspot = sortie.sensors[_CAPTEUR_HOTSPOT]
        return interpreter((edge.supported, edge.value),
                           (hotspot.supported, hotspot.value))
