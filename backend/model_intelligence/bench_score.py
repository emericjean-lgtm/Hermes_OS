"""Ramener chaque axe mesuré à une note sur 100 (HOS-108).

Le routage a besoin de comparer, l'onglet Modèles d'afficher. Or les axes
ne se mesurent pas de la même façon : l'agentique rend un taux de réussite,
le code un palier atteint, la capacité trois grandeurs hétérogènes.

**Une note par axe, jamais une note globale.** Une moyenne dirait que
gemma4 — excellent en vision, très faible en long contexte — vaut autant
qu'un modèle moyen partout, alors que leurs usages n'ont rien de commun.
Le catalogue existe pour distinguer des compétences, pas pour les fondre.

**La progression des paliers est accélérée, pas linéaire.** Neuf niveaux à
11,1 points chacun diraient que passer de `simple` à `moyen` vaut autant
que de `titan` à `mythique`. Mesuré : dix modèles sur dix passent `simple`,
trois atteignent `mythique`. Le haut de l'échelle sépare, le bas non — la
note doit le refléter, sinon le routage croira que tous se valent.
"""
from __future__ import annotations

from typing import Any, Optional

#: Note sur 100 par palier de code atteint. L'échelle à neuf niveaux
#: plafonne à 64 et non à 100 : trois modèles l'ont épuisée, et une échelle
#: dont le sommet est atteint par plusieurs candidats ne les classe plus.
#: Les 36 points restants viennent des épreuves de départage ci-dessous.
PALIERS_CODE: dict[str, int] = {
    "simple": 6, "moyen": 12, "complexe": 20, "expert": 28,
    "maitre": 36, "extreme": 44, "legende": 52, "titan": 58, "mythique": 64,
}

#: Au-delà de `mythique`, deux séries de trois épreuves indépendantes —
#: elles ne forment pas une échelle, on peut en réussir deux sur trois dans
#: n'importe quelle combinaison, et c'est justement ce qui les rend utiles
#: pour départager. Chacune vaut 6 points : 64 + 18 + 18 = 100.
#:
#: `extreme` demande de construire (un interpréteur, un cache O(1) strict,
#: une file bornée sûre entre threads) ; `abyssal` demande d'optimiser —
#: sur chacune, une solution juste mais naïve existe et échoue.
POINTS_PAR_EPREUVE = 6

#: Cinq niveaux d'extraction. Neuf modèles sur dix atteignent le dernier :
#: l'axe ne discrimine pas, et la note le dit en écrasant les écarts vers
#: le haut plutôt qu'en inventant une hiérarchie qui n'existe pas.
PALIERS_EXTRACTION: dict[str, int] = {
    "arbitrage": 40, "imbrication": 55, "calcul": 75,
    "distracteurs": 90, "negatif": 100,
}

#: Contexte servi rapporté à une note. 64k est le plancher opérationnel
#: (en dessous, les schémas d'outils sont tronqués — voir CLAUDE.md), donc
#: il vaut la moyenne et non zéro : un modèle à 64k est utilisable.
def note_capacite(contexte_servi: Optional[int], debordement: float = 0.0) -> Optional[int]:
    if not contexte_servi:
        return None
    if debordement > 0.02:
        # Un modèle qui déborde répond quand même, sans erreur, plusieurs
        # fois plus lentement et de façon erratique. Ce n'est pas une
        # pénalité graduelle : c'est disqualifiant.
        return 0
    if contexte_servi < 65536:
        return 25
    paliers = [(65536, 50), (131072, 75), (262144, 100)]
    note = 50
    for seuil, valeur in paliers:
        if contexte_servi >= seuil:
            note = valeur
    return note


def note_taux(verdict: str) -> Optional[int]:
    """« 3/3 », « 5/6 » -> note sur 100."""
    if "/" not in verdict:
        return None
    try:
        reussites, essais = verdict.split("/", 1)
        return round(100 * int(reussites) / int(essais)) if int(essais) else None
    except (ValueError, ZeroDivisionError):
        return None


def note_palier(verdict: str, bareme: dict[str, int]) -> Optional[int]:
    return bareme.get(verdict)


def note_code(verdict: str, detail: Any = None) -> Optional[int]:
    """Le palier atteint, plus les épreuves de départage réussies.

    Un modèle qui n'a jamais subi le départage garde la note de son palier.
    C'est voulu : sept des dix modèles plafonnent bien en dessous de
    `mythique`, les leur faire passer coûterait des heures de GPU pour
    confirmer ce que l'échelle a déjà dit.
    """
    base = PALIERS_CODE.get(verdict)
    if base is None:
        return None
    detail = detail or {}
    reussies = 0
    for serie in ("extremes", "abyssales"):
        epreuves = detail.get(serie) or []
        reussies += sum(1 for e in epreuves if e.get("reussi"))
    return min(100, base + POINTS_PAR_EPREUVE * reussies)


def noter_axe(axe: str, mesure: dict[str, Any]) -> Optional[int]:
    """La note sur 100 d'un axe, ou None si l'axe n'est pas mesurable ainsi.

    None n'est pas zéro : un axe non mesuré doit rester visiblement absent
    dans l'onglet, sinon un modèle jamais testé passerait pour mauvais.
    """
    verdict = (mesure or {}).get("verdict") or ""
    if axe == "code":
        return note_code(verdict, (mesure or {}).get("detail") or {})
    if axe == "extraction":
        return note_palier(verdict, PALIERS_EXTRACTION) or note_taux(verdict)
    if axe == "capacite":
        detail = (mesure or {}).get("detail") or {}
        servis = [t for t in (detail.get("tiers") or [])
                  if t.get("cpu_offload_ratio") is not None
                  and t["cpu_offload_ratio"] <= 0.02]
        if servis:
            meilleur = max(servis, key=lambda t: t.get("context_length") or t["num_ctx"])
            return note_capacite(meilleur.get("context_length") or meilleur["num_ctx"])
        # Pas de détail exploitable : retomber sur le verdict textuel (« 256k »).
        if verdict.endswith("k") and verdict[:-1].isdigit():
            return note_capacite(int(verdict[:-1]) * 1024)
        return None
    return note_taux(verdict)


def noter_modele(axes: dict[str, dict]) -> dict[str, Optional[int]]:
    """Toutes les notes d'un modèle, axe par axe. Aucune agrégation."""
    return {axe: noter_axe(axe, mesure) for axe, mesure in (axes or {}).items()}


def meilleur_pour(catalogue: list[dict], axe: str,
                  note_minimale: int = 1) -> list[tuple[str, int]]:
    """Les modèles capables sur un axe, du meilleur au moins bon.

    Le routage ne prend pas le premier : il prend le **moins coûteux** parmi
    ceux dont la note dépasse ce que la tâche exige. Cette fonction fournit
    la liste des candidats, pas la décision — mesuré, deux modèles à note
    identique en code peuvent différer d'un facteur 7 en temps.
    """
    classes = []
    for entree in catalogue:
        note = noter_axe(axe, (entree.get("axes") or {}).get(axe, {}))
        if note is not None and note >= note_minimale:
            classes.append((entree["model"], note))
    return sorted(classes, key=lambda c: -c[1])
