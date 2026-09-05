"""L'occupation VRAM réelle de la machine — source unique de l'admission (A-15).

## Le défaut que ce module ferme

`GPUMonitor` cherchait `rocm-smi`, puis `nvidia-smi`, puis **retombait sur
`/api/ps`**. Sur la machine cible — Windows, AMD RX 6800 — ni `rocm-smi` ni
`nvidia-smi` n'existent : le repli *était* le cas normal, et personne ne le
savait parce qu'il répondait sans erreur.

Or `/api/ps` ne mesure pas la même chose. Il donne les **poids des modèles
résidents d'Ollama**, et rien d'autre : ni le cache KV, ni les tampons de
calcul, ni un seul octet tenu par un autre processus. Mesuré ici, trois
états de charge sur la même carte de 15,98 Gio :

    état                     /api/ps    occupation réelle    écart
    aucun modèle              0,000            1,314        +1,314
    qwen3.6-35b résident     12,737           14,954        +2,216
    même modèle, cache KV    12,737           15,115        +2,377

L'écart va **toujours** dans le même sens et il **grandit** : `/api/ps` est
resté figé à 12,737 pendant que l'occupation montait de 161 Mio, parce que
ce qui montait était le cache KV, qu'il ne voit pas. À l'état 3, l'admission
croyait 3,25 Gio libres là où il en restait 0,87.

C'est le sens dangereux de l'erreur : celui qui fait croire qu'il reste de
la place. Un second modèle admis sur cette base déborde en mémoire système
et répond dix fois plus lentement — sans erreur, ce qui est précisément ce
qui rend le défaut coûteux à trouver.

## Ce que ce module mesure, exactement

La somme de `\\GPU Process Memory(*)\\Dedicated Usage` sur **tous** les
processus de la machine : la mémoire vidéo dédiée effectivement détenue,
quel que soit le détenteur — Ollama, le compositeur de bureau, un
navigateur. C'est la question que pose l'admission : « reste-t-il de la
place sur la carte », pas « combien Ollama en a-t-il pris ».

Le compteur par **processus** et non par **adaptateur** : mesuré ici, stable
sur trois relevés, l'adaptateur annonce 14,669 Gio là où la somme des
processus en compte 15,115. L'écart est petit (2,9 %) mais toujours dans le
sens dangereux, et le compteur par processus est celui que
`model_intelligence/model_bench.py` utilise déjà.

## Les limites, énoncées plutôt que découvertes plus tard

- **Windows seulement.** Ailleurs, `None` — et `None` ne veut pas dire
  « rien d'occupé », il veut dire « non mesuré ». L'appelant doit traiter
  les deux différemment, faute de quoi on retombe exactement dans A-15.

  Conséquence pour Linux sans `rocm-smi` : aucune sonde ne répond, et le
  registre qui donne la capacité est propre à Windows, si bien que l'état
  est « pas de carte détectable » — donc pas de contrainte. Le kernel AMD
  publie pourtant `/sys/class/drm/card*/device/mem_info_vram_used`, de
  même sémantique. Rien ici ne permet de l'exercer, et écrire une sonde
  qu'on ne peut pas mesurer serait refaire la faute que ce module
  corrige. Consigné **A-16**, non traité.
- **Somme sur tous les adaptateurs.** Une machine à iGPU + carte discrète
  compte les deux. L'erreur va vers la sur-estimation de l'occupation, donc
  vers le refus : c'est le sens acceptable.
- **Coût : ~1,6 s** par mesure (démarrage de PowerShell compris), contre
  0,02 s pour `/api/ps`. `GPUMonitor` la met en cache. Une tâche vit entre
  60 et 900 s ; une seconde et demie pour ne pas charger un modèle qui ne
  tient pas est le bon échange.
"""

from __future__ import annotations

import os
import subprocess
from typing import Optional

# Le compteur nomme ses instances `pid_<n>_luid_..._phys_<n>`. On somme
# tout : la question est l'occupation de la machine, pas celle d'un
# processus. `model_bench.gpu_dedicated_bytes` pose l'autre question — un
# processus nommé — et c'est pour cela qu'il a sa propre requête.
_REQUETE = (
    "(Get-Counter '\\GPU Process Memory(*)\\Dedicated Usage' -ErrorAction Stop)"
    ".CounterSamples | Measure-Object -Property CookedValue -Sum "
    "| Select-Object -ExpandProperty Sum"
)

_DELAI_S = 20.0


def occupation_physique_octets(
    executer=None,
) -> Optional[int]:
    """La VRAM dédiée détenue sur cette machine, en octets.

    Rend `None` quand la mesure n'a pas pu être faite — jamais `0`, qui
    signifierait « mesuré, et rien n'est pris ». Les deux mènent à des
    décisions opposées : `0` autorise, `None` doit faire refuser.

    `executer` permet aux tests de fournir la sortie de la commande sans
    qu'un compteur Windows soit présent ; en production, `None` prend le
    vrai chemin.
    """
    if executer is None:
        if os.name != "nt":
            return None
        executer = _powershell

    try:
        sortie = executer(_REQUETE)
    except Exception:
        return None

    if not sortie:
        return None
    texte = str(sortie).strip()
    if not texte:
        return None
    try:
        # Le compteur rend un flottant ; la virgule décimale suit la locale
        # de la machine, et une locale française rendrait `1,5E+10`.
        valeur = float(texte.replace(",", "."))
    except ValueError:
        return None
    return int(valeur) if valeur >= 0 else None


def _powershell(requete: str) -> Optional[str]:
    resultat = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", requete],
        capture_output=True, text=True, timeout=_DELAI_S,
    )
    if resultat.returncode != 0:
        return None
    return resultat.stdout
