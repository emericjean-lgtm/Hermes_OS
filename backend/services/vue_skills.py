r"""Les Skills du cerveau agentique, vues depuis Hermes OS (HOS-274).

Une **vue**, comme `vue_agent`, et pour la même raison : les Skills sont
la mémoire procédurale de Hermes Agent, elles vivent sous
`%LOCALAPPDATA%\hermes\skills`, et Hermes OS n'en est pas l'autorité.

## Une seule surface ici : le catalogue distant

`skills.manage` porte cinq actions sous un seul nom de méthode, et elles
ne parlent pas du même monde. Mesuré le 2026-09-09 sur le runtime
v0.21.0 :

    list      65 skills, 14 categories   -> installation locale
    browse    5493 skills, 275 pages     -> catalogue du hub, distant
    inspect   resolu contre le hub       -> {} pour une skill installee

**Ce module ne sert que le catalogue.** La population installée a déjà sa
source depuis HOS-153 : `backend/skills/registre.py`, qui la lit sur le
disque *avec les descriptions* et sans payer le gateway. En offrir une
seconde par RPC créerait exactement les deux vérités que ce dépôt passe
son temps à défaire — et HOS-274 vient d'en corriger une : `registre.py`
lisait `hermes/hermes-agent/skills` au lieu de `hermes/skills`, soit
soixante noms contre soixante-cinq, **quarante en commun**. Les deux
concordent désormais exactement.

`inspect("github-pr-workflow")` — une skill pourtant installée — rend
`{}`, parce que `inspect_skill` résout l'identifiant contre les *sources*
du hub, pas contre le disque. `detail` appartient donc au catalogue, et à
lui seul.

## Une lecture qui ecrit, et il faut le dire

`browse`, `search` et `inspect` font rafraichir a l'agent son propre cache
d'index de hub — `skills/.hub/index-cache/*.json`, 705 Ko reecrits pendant
la mesure. C'est l'agent qui ecrit son cache par son propre chemin, pas
Hermes OS qui touche son disque, et la garde syntaxique reste vraie. Mais
« lecture seule » decrit ici l'autorite, pas l'absence d'effet, et la
confusion entre les deux est precisement ce que ce depot paie cher.

## Ce que ce module ne fait pas, et pourquoi

Pas d'installation. `skills.manage install` rend `{"installed": true}`
**sans regarder** ce que `do_install` a fait — mesuré : un nom qui
n'existe nulle part rend `installed: true`, et `do_install` sort en
`return None` sur six chemins distincts, dont celui où le scanner de
sécurité **bloque** l'installation. Câbler un bouton dessus livrerait un
faux succès garanti, et transformerait un refus de sécurité en réussite
affichée. C'est le défaut fondateur de ce dépôt sous une forme neuve.

Pas de création, d'édition ni de suppression. Le gateway rend `4017` sur
`create`, `edit`, `delete`, `pending`, `diff`, `approve` et `reject` : ces
gestes existent, mais comme **outil que l'agent s'appelle à lui-même**
(`tools/skill_manager_tool.py`), pas comme méthode que Hermes OS peut
demander. La même leçon que les Approvals (G-23).
"""

from __future__ import annotations

from typing import Any

from backend.services.vue_agent import _appeler

#: Le runtime plafonne `search` à 20 résultats (`limit=20` en dur dans
#: `_skills_search`). Le dire, plutôt que de laisser croire que 20 est le
#: nombre de skills qui correspondent — la leçon du `total` de HOS-266.
PLAFOND_RECHERCHE = 20

#: `browse` sert des pages de 20 par défaut côté gateway.
TAILLE_PAGE = 20


def catalogue(page: int = 1) -> dict[str, Any]:
    """Une page du hub distant.

    Ici `total` et `total_pages` viennent du runtime lui-même, donc pas de
    `tronque` deviné : la pagination est une donnée, pas une inférence.
    """
    numero = max(1, int(page or 1))
    enveloppe = _appeler("skills.manage",
                         {"action": "browse", "page": numero,
                          "page_size": TAILLE_PAGE})
    if not enveloppe["disponible"]:
        return {"disponible": False, "erreur": enveloppe["erreur"],
                "page": numero, "pages": 0, "total": 0, "elements": []}
    resultat = enveloppe["resultat"]
    elements = resultat.get("items")
    return {"disponible": True, "erreur": None,
            "page": int(resultat.get("page") or numero),
            "pages": int(resultat.get("total_pages") or 0),
            "total": int(resultat.get("total") or 0),
            "elements": elements if isinstance(elements, list) else []}


def rechercher(requete: str) -> dict[str, Any]:
    """Cherche dans le hub. `tronque` dit que le plafond a été atteint."""
    texte = (requete or "").strip()
    if not texte:
        return {"disponible": True, "erreur": None,
                "tronque": False, "total": 0, "elements": []}
    enveloppe = _appeler("skills.manage",
                         {"action": "search", "query": texte})
    if not enveloppe["disponible"]:
        return {"disponible": False, "erreur": enveloppe["erreur"],
                "tronque": False, "total": 0, "elements": []}
    elements = enveloppe["resultat"].get("results")
    if not isinstance(elements, list):
        elements = []
    return {"disponible": True, "erreur": None,
            "tronque": len(elements) >= PLAFOND_RECHERCHE,
            "total": len(elements), "elements": elements}


def detail(nom: str) -> dict[str, Any]:
    """Le détail d'une entrée **du catalogue**, jamais d'une skill locale.

    `connu` sépare deux choses qu'un dictionnaire vide confondrait : le
    hub ne connaît pas ce nom, et le gateway n'a pas répondu. Une skill
    installée hors hub tombe légitimement dans le premier cas, et ce n'est
    pas une panne.
    """
    identifiant = (nom or "").strip()
    if not identifiant:
        return {"disponible": True, "erreur": None, "connu": False,
                "info": {}}
    enveloppe = _appeler("skills.manage",
                         {"action": "inspect", "query": identifiant})
    if not enveloppe["disponible"]:
        return {"disponible": False, "erreur": enveloppe["erreur"],
                "connu": False, "info": {}}
    info = enveloppe["resultat"].get("info")
    if not isinstance(info, dict):
        info = {}
    return {"disponible": True, "erreur": None,
            "connu": bool(info), "info": info}
