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

La somme du compteur Windows par **adaptateur** (`_REQUETE` plus bas) sur
**tous** les adaptateurs de la machine : la mémoire vidéo dédiée effectivement détenue,
quel que soit le détenteur — Ollama, le compositeur de bureau, un
navigateur. C'est la question que pose l'admission : « reste-t-il de la
place sur la carte », pas « combien Ollama en a-t-il pris ». C'est aussi,
vérifié ici, exactement ce qu'affiche le Gestionnaire des tâches.

## Corrigé le 2026-09-12 : le compteur par processus dépassait la capacité

Ce module a porté le compteur Windows par **processus**, sommé sur tous les
processus, depuis §6.2/A-15 jusqu'à cette date. Le choix venait d'un
relevé unique, non reproduit depuis (CHANGELOG, HOS-258, 2026-09-05) :
avec un modèle de 11,9 Gio résident, l'adaptateur annonçait 3,99 Gio contre
12,70 pour la somme des processus — un facteur trois, dans le sens
dangereux. Remesuré trois fois le lendemain, l'écart n'était plus que de
2,9 % (14,669 contre 15,115) ; « la sonde d'origine n'a pas été conservée
et n'est plus auditable », et le choix du compteur par processus avait été
gardé par prudence malgré la non-reproduction.

Un signalement de l'opérateur a fait rejouer la mesure une troisième fois,
dans l'état réel de la machine plutôt que de s'arrêter à une conclusion de
2026-09-05 : Hermes OS annonçait 17,3 Gio d'occupation avec `gpt-oss-20b`
résident, sur une carte qui n'en porte que 15,98 — **une valeur physiquement
impossible** — quand le Gestionnaire des tâches indiquait 15,4 Gio,
cohérent. Rejoué au repos et avec un modèle chargé :

    état                    adaptateur   somme processus   écart
    au repos (aucun modèle)   1,237 Gio       3,144 Gio    +1,907
    lfm2.5-2.6b chargé        5,565 Gio       7,478 Gio    +1,913

L'écart est constant en valeur absolue (~1,9 Gio) aux deux états — la
contribution du modèle lui-même, mesurée par différence, est identique des
deux côtés (4,33 Gio, exactement la valeur déclarée par
`config/models.yaml`) — ce qui écarte un effet du modèle chargé. L'excédent
vient du bruit de fond : plusieurs fenêtres GPU-accélérées (navigateur,
Explorer, le compositeur DWM lui-même) se voient chacune attribuer, dans le
compteur par **processus**, la surface de composition que DWM recompose
pour leur compte — un artefact documenté de cette catégorie de compteur
Windows sommée sans filtrer. Il grandit avec le nombre de fenêtres
ouvertes et n'est borné par aucune capacité physique, d'où la valeur
supérieure à la carte lors du signalement.

Le compteur par **adaptateur**, lui, n'a pas cet artefact : chaque
allocation y est comptée une fois, au niveau du pilote, quel que soit le
nombre de processus qui la partagent — c'est la définition que retient le
Gestionnaire des tâches. Le facteur trois de §6.2 reste un fait mesuré,
non expliqué et non reproduit en trois occasions séparées (2026-09-05,
2026-09-12 à deux états) : le risque théorique d'un sous-relevé ponctuel du
compteur par adaptateur n'est donc pas écarté, mais rien de mesuré depuis
ne le montre, alors que le compteur par processus vient de produire une
valeur qui viole une contrainte physique — un défaut certain contre un
défaut qui ne s'est plus reproduit. `occupation_physique_octets` ne peut
pas, à elle seule, garantir `occupation <= total` si la source se
détraquait à nouveau : c'est `GPUMonitor._try_compteurs_windows` qui borne
`vram_used_bytes` à `vram_total_bytes` en dernier recours (voir ce module).

`model_intelligence/model_bench.py` garde son propre compteur par
**processus nommé** (`gpu_dedicated_bytes`) : il répond à une question
différente — « combien ce PID précis détient-il » — et un processus sans
fenêtre (le serveur Ollama) n'est pas sujet à l'artefact de composition,
puisque rien n'y recompose de surface pour son compte.

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

# Le compteur nomme ses instances `luid_..._phys_<n>`, une par adaptateur.
# On somme tout : la question est l'occupation de la machine, pas celle
# d'un processus. `model_bench.gpu_dedicated_bytes` pose l'autre
# question — un processus nommé, sur `GPU Process Memory` — et c'est pour
# cela qu'il a sa propre requête ; sommer ce compteur sur *tous* les
# processus, comme ce module le faisait avant le 2026-09-12, double-compte
# les surfaces que DWM recompose pour chaque fenêtre GPU-accélérée (voir
# « Corrigé le 2026-09-12 » plus haut).
_REQUETE = (
    "(Get-Counter '\\GPU Adapter Memory(*)\\Dedicated Usage' -ErrorAction Stop)"
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
