"""Chaque appel du Cockpit doit viser une route qui existe (HOS-186).

`missionsClient.timeline` appelait `GET /missions/{id}/timeline` depuis des
mois. Le backend ne sert pas cette route — il en sert onze pour les
missions, pas celle-là. Le défaut n'a jamais été visible parce qu'aucun
écran n'appelait la méthode, et le seul test qui la mentionnait affirmait
`typeof missionsClient.timeline === "function"` : il vérifiait qu'un objet
que nous avions écrit contenait bien ce que nous y avions mis.

C'est la tautologie que `backend/mission/tests_tautologiques.py` traque dans
le code livré, arrivée cette fois dans notre propre suite.

Ce test compare des chaînes à un contrat. Il n'appelle rien, donc les verbes
destructeurs sont vérifiés comme les autres, et il n'a besoin d'aucun
serveur en marche : le schéma est construit depuis l'application elle-même.

Un chemin qui n'existe plus fait échouer ce test avec sa ligne dans
`client.ts` ; la réparation consiste à retirer l'appel ou à servir la route,
jamais à élargir la tolérance ci-dessous.
"""

from __future__ import annotations

import io
import os
import re

import pytest

RACINE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CLIENT = os.path.join(RACINE, "frontend", "src", "services", "client.ts")
PREFIXE = "/api/v1"

#: `fetchJSON<T>("/chemin", { method: "POST" })`, options facultatives.
ENVELOPPE = re.compile(
    r"""fetchJSON<[^>]*>\(\s*[`"']([^`"']+)[`"']\s*(?:,\s*\{(.*?)\})?\s*\)""",
    re.S,
)
#: `fetch(`${API_BASE}/chemin`, { … })` — les appels qui ne rendent pas du
#: JSON, comme la synthèse vocale qui rend un WAV.
BRUT = re.compile(r"""fetch\(\s*`\$\{API_BASE\}([^`]+)`\s*,\s*\{(.*?)\}\s*\)""", re.S)

VERBE = re.compile(r'method:\s*"(\w+)"')

#: Une interpolation *nommée* comme une chaîne de requête n'est pas un
#: segment de chemin. La confondre avec un paramètre transformait
#: `/skills${qs}` en `/skills/{x}` — neuf faux positifs au premier relevé.
#: L'inverse est pire : retirer toute interpolation finale faisait passer
#: `/autonomous/${goalId}` pour `/autonomous`, qui n'existe pas.
REQUETE = re.compile(r"\$\{(qs|query|params|search)\}$")


#: Une union TypeScript fermée : `type X = "a" | "b";`. Un segment interpolé
#: dont la variable porte le nom d'une telle union n'est pas un identifiant
#: mais un choix parmi des chemins littéraux — `/code-intelligence/${kind}`
#: vise quatre routes réelles, pas une route paramétrée. Les développer vaut
#: mieux que les exempter : c'est la seule façon de vérifier les quatre.
UNION = re.compile(r'export type (\w+)\s*=\s*((?:"\w[\w-]*"\s*\|\s*)+"\w[\w-]*")\s*;')


def _unions(source: str) -> dict[str, list[str]]:
    """nom de variable probable -> valeurs littérales."""
    trouvees: dict[str, list[str]] = {}
    for m in UNION.finditer(source):
        valeurs = re.findall(r'"([^"]+)"', m.group(2))
        # `CodeIntelligenceTaskKind` -> la variable s'appelle `kind`.
        mots = re.findall(r'[A-Z][a-z0-9]*', m.group(1))
        if mots:
            trouvees.setdefault(mots[-1].lower(), valeurs)
    return trouvees


def _developper(chemin: str, unions: dict[str, list[str]]) -> list[str]:
    """Un chemin, ou ses variantes quand un segment vient d'une union."""
    m = re.search(r"\$\{(\w+)\}", chemin)
    if m and m.group(1) in unions:
        return [chemin.replace(m.group(0), v) for v in unions[m.group(1)]]
    return [chemin]


def _gabarit(chemin: str) -> str:
    """Réduire un chemin à sa forme comparable.

    Les segments interpolés du client (`${id}`) et les paramètres nommés du
    contrat (`{mission_id}`) deviennent le même joker : c'est le seul moyen
    de rapprocher `/missions/${id}` de `/missions/{mission_id}`.
    """
    chemin = chemin.split("?")[0].rstrip("/")
    chemin = REQUETE.sub("", chemin).rstrip("/")
    chemin = re.sub(r"\$\{[^}]*\}", "{x}", chemin)
    chemin = re.sub(r"\{[^}]*\}", "{x}", chemin)
    return chemin or "/"


def _appels() -> list[tuple[int, str, str]]:
    """(ligne, verbe, chemin) pour chaque appel écrit dans client.ts."""
    if not os.path.exists(CLIENT):
        pytest.skip("frontend absent de cette copie de travail")
    source = io.open(CLIENT, encoding="utf-8").read()
    trouves: list[tuple[int, str, str]] = []
    for motif in (ENVELOPPE, BRUT):
        for m in motif.finditer(source):
            chemin, options = m.group(1), m.group(2) or ""
            v = VERBE.search(options)
            ligne = source[: m.start()].count("\n") + 1
            trouves.append((ligne, (v.group(1) if v else "GET").upper(), chemin))
    return trouves


def _contrat() -> dict[str, set[str]]:
    """Le schéma servi par l'application, sans serveur en marche."""
    from backend.main import app

    routes: dict[str, set[str]] = {}
    for chemin, verbes in app.openapi().get("paths", {}).items():
        routes.setdefault(_gabarit(chemin), set()).update(v.upper() for v in verbes)
    return routes


def test_aucun_appel_du_cockpit_ne_vise_une_route_absente():
    appels = _appels()
    assert len(appels) > 100, (
        f"seulement {len(appels)} appels relevés dans client.ts — la forme "
        "des appels a changé et ce test ne vérifie donc plus grand-chose"
    )

    connus = _contrat()
    unions = _unions(io.open(CLIENT, encoding="utf-8").read())

    # `${path}` est le paramètre de `fetchJSON` lui-même, pas un appel.
    fantomes = []
    for ligne, verbe, chemin in appels:
        if chemin.startswith("${"):
            continue
        for variante in _developper(chemin, unions):
            if _gabarit(PREFIXE + variante) not in connus:
                fantomes.append((ligne, verbe, variante))

    if fantomes:
        lignes = [f"  client.ts:{l}  {v} {c}" for l, v, c in sorted(fantomes, key=lambda x: x[2])]
        raise AssertionError(
            f"{len(fantomes)} appel(s) du Cockpit visent une route que le "
            "backend ne sert pas :\n" + "\n".join(lignes)
        )


def test_aucun_appel_du_cockpit_nutilise_le_mauvais_verbe():
    """Une route qui existe ne garantit pas qu'elle accepte ce verbe.

    Un `PATCH` sur une route qui n'expose que `GET` et `POST` rend 405, et
    le bouton qui le déclenche échoue en silence si personne ne regarde la
    console.
    """
    connus = _contrat()
    fautifs = []
    for ligne, verbe, chemin in _appels():
        if chemin.startswith("${"):
            continue
        for variante in _developper(chemin, _unions(io.open(CLIENT, encoding="utf-8").read())):
            g = _gabarit(PREFIXE + variante)
            if g in connus and verbe not in connus[g]:
                fautifs.append((ligne, verbe, variante, sorted(connus[g])))

    assert not fautifs, "\n".join(
        f"  client.ts:{l}  {v} {c} — le contrat accepte {', '.join(ok)}"
        for l, v, c, ok in fautifs
    )
