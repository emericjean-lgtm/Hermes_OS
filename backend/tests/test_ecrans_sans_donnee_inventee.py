# -*- coding: utf-8 -*-
"""Aucun Center ne presente une donnee inventee comme mesuree (G-40, HOS-289).

## Le motif, quatre fois

    HOS-288  Security Center    4 menaces, 6 politiques, 6 profils
    HOS-289  System Center      12 composants avec latences et etats
    HOS-289  System Center      « 25 composants », « 42 aretes », « aucun cycle »
    HOS-289  Evolution Center   4 « patterns » avec frequences et gains

Les trois premiers avaient la meme signature, et elle explique pourquoi
personne ne les voyait : **un nettoyage anterieur avait retire les mocks
NOMMES et laisse les tableaux litteraux inlines dans le JSX**. Le Security
Center portait un commentaire disant que `MOCK_STATUS` etait parti ; le
System Center, un autre disant que les compteurs venaient desormais du
registre vivant. Les deux etaient vrais, et les deux ecrans mentaient
encore plus bas. On cherche `MOCK_` ; on ne cherche pas un tableau
d'objets.

## Ce que la garde distingue

Une donnee inventee n'a que des LITTERAUX. Un descripteur de presentation
— colonnes d'un tableau, onglets d'un Center, tuiles d'un `StatGrid` —
REFERENCE quelque chose : l'etat, une interpolation, du JSX, une fonction
de rendu. C'est le discriminant, et il tient sans liste blanche.

Trois details l'ont fait echouer avant de tenir :

- les **chaines** doivent etre retirees d'abord. Sans cela,
  `"agent.unknown_dev"` et `"tool.exec"` passent pour des acces de
  propriete, et deux des trois blocs du Security Center filaient.
- une description d'architecture est **legitimement** litterale. Elle est
  donc exemptee — mais seulement si le code le DIT.
- l'exemption elle-meme doit resister. Mesure du 2026-09-11 : poser
  `{/* description */}` au-dessus des quatre « patterns » inventes de
  l'Evolution Center suffisait a les faire passer. Un mot ne peut pas
  etre le seul verrou. L'exemption exige donc aussi que **tout nombre
  ecrit dans le bloc reste hors du rendu** : un descriptif decrit une
  structure, ses valeurs sont des chaines, et le seul nombre qu'il porte
  legitimement alimente une mise en page (`paddingLeft`, une classe).
  Un nombre qui atteint le texte affiche — ou qui ne sert a rien — est
  une quantite, et une quantite ecrite a la main se lit comme une mesure.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parents[2]
CENTERS = sorted(
    p for p in (RACINE / "frontend" / "src" / "features").rglob("*.tsx")
    if ".test." not in p.name
    and (p.name.endswith("-center.tsx") or p.name.endswith("-view.tsx")))

#: Un tableau d'objets pose dans le JSX et rendu par `.map()`.
_TABLEAU = re.compile(r"\{\[\s*\n(.*?)\n\s*\]\.map\(", re.DOTALL)
#: Les chaines d'abord — voir le docstring.
_CHAINES = re.compile(r'"[^"]*"|\'[^\']*\'|`[^`]*`')
#: Ce qui prouve qu'un tableau decrit la presentation et non des faits.
_VIVANT = re.compile(r"\$\{|<[A-Za-z]|=>|\b[A-Za-z_$][\w$]*\s*\.\s*[A-Za-z_$]")
#: La declaration explicite qui leve la garde. Elle doit etre dans un
#: COMMENTAIRE — une occurrence du mot ailleurs (un titre, un libelle) ne
#: vaut pas declaration — et proche du bloc, sans exiger l'adjacence : le
#: commentaire coiffe souvent une `<Card>` qui enveloppe le tableau.
_MARQUEUR = re.compile(r"/\*(?:(?!\*/).)*?\bdescription\b(?:(?!\*/).)*?\*/",
                       re.DOTALL | re.IGNORECASE)
#: A quelle distance du bloc le commentaire doit FINIR. La fenetre porte
#: sur la fin du commentaire, pas sur son texte : un commentaire long
#: serait sinon tronque de son `/*` ouvrant et cesserait d'etre reconnu.
_PORTEE_EXEMPTION = 420
#: Une cle dont la valeur est un nombre ecrit a la main.
_CLE_NUMERIQUE = re.compile(r"\b(\w+)\s*:\s*-?\d")
#: Combien de caracteres du corps de `.map()` sont lus pour savoir ce que
#: le bloc affiche reellement.
_PORTEE_CORPS = 1400


def _nombre_hors_mise_en_page(bloc: str, corps: str) -> list[str]:
    """Les cles numeriques du bloc qui n'alimentent pas la mise en page.

    Une valeur numerique ecrite a la main est tolerable quand elle ne sort
    jamais en texte : `level` positionne un `paddingLeft` et choisit une
    classe, il ne s'affiche pas. Tout le reste — affiche, ou jamais lu —
    est une quantite inventee.
    """
    fautives = []
    # Les chaines d'abord, ici aussi : un « 10 » dans un libelle n'est pas
    # une valeur numerique du bloc.
    for cle in sorted(set(_CLE_NUMERIQUE.findall(_CHAINES.sub('""', bloc)))):
        usages = [l for l in corps.splitlines()
                  if re.search(r"\.\s*" + re.escape(cle) + r"\b", l)]
        if not usages:
            fautives.append(cle)  # ecrite, jamais lue : un chiffre decoratif
            continue
        if not all(("style=" in l or "className=" in l) for l in usages):
            fautives.append(cle)  # atteint le texte affiche
    return fautives


def _declare_descriptif(source: str, debut: int) -> bool:
    """Un commentaire portant « description » se ferme-t-il juste avant ?"""
    return any(0 <= debut - c.end() <= _PORTEE_EXEMPTION
               for c in _MARQUEUR.finditer(source))


def _inventes(source: str) -> list[str]:
    trouves = []
    for m in _TABLEAU.finditer(source):
        bloc = m.group(1)
        if _VIVANT.search(_CHAINES.sub('""', bloc)):
            continue
        corps = source[m.end():m.end() + _PORTEE_CORPS]
        ligne = source[:m.start()].count("\n") + 1
        if _declare_descriptif(source, m.start()):
            fautives = _nombre_hors_mise_en_page(bloc, corps)
            if not fautives:
                continue  # declare descriptif, et rien n'y est chiffre
            trouves.append(
                "ligne %d : declare « description » mais chiffre %s"
                % (ligne, ", ".join("`%s`" % c for c in fautives)))
            continue
        trouves.append("ligne %d : %s"
                       % (ligne, bloc.strip().replace("\n", " ")[:60]))
    return trouves


@pytest.mark.parametrize("center", CENTERS, ids=lambda p: p.name)
def test_aucun_tableau_operationnel_ecrit_en_dur(center):
    """Une latence, un compteur d'evenements ou un etat « healthy » ecrits
    en dur sont indiscernables d'une mesure. Un tableau litteral qui decrit
    une architecture ne l'est pas — mais il doit le dire, et ne rien
    chiffrer."""
    inventes = _inventes(center.read_text(encoding="utf-8"))
    assert not inventes, (
        f"{center.name} rend un tableau de litteraux — " + " | ".join(inventes) +
        " — indiscernable d'une donnee mesuree. S'il decrit une "
        "architecture plutot qu'un etat, dites-le dans un commentaire "
        "portant le mot « description » juste avant le bloc — et n'y "
        "ecrivez aucun chiffre qui sorte en texte.")


@pytest.mark.parametrize("center", CENTERS, ids=lambda p: p.name)
def test_aucune_donnee_recuperee_n_est_jetee(center):
    """Recuperer une donnee puis afficher autre chose est pire que ne pas
    la recuperer : le reseau montre un appel qui reussit.

    Mesure du 2026-09-11 : `useSecurityThreats()` etait appele, sa donnee
    liee a `threats`, et l'ecran rendait quatre menaces inventees a la
    place. Corrige en HOS-288.
    """
    source = center.read_text(encoding="utf-8")
    orphelines = []
    for m in re.finditer(
            r"const (\w+) = [^;\n]*\b(?:data|Array\.isArray)\b[^;\n]*;", source):
        nom = m.group(1)
        if len(re.findall(r"\b" + re.escape(nom) + r"\b", source)) == 1:
            orphelines.append("ligne %d : `%s`"
                              % (source[:m.start()].count("\n") + 1, nom))
    assert not orphelines, (
        f"{center.name} lie une donnee recuperee et ne la rend jamais — " +
        " | ".join(orphelines))


def test_le_corpus_couvre_bien_les_centers():
    """Une garde parametree sur un corpus vide est verte et ne mesure rien.

    Le corpus se decouvre par un motif de nom (`*-center.tsx`,
    `*-view.tsx`). Un renommage, un deplacement de `features/`, et la
    garde s'applique a trois fichiers sans que rien ne le dise — pytest
    ne fait que signaler des parametres vides. Ce plancher rend cet
    effondrement bruyant.
    """
    noms = {p.name for p in CENTERS}
    assert len(CENTERS) >= 24, (
        "le corpus est tombe a %d fichiers : la garde ne couvre plus les "
        "Centers. Le motif de nom ou l'arborescence a change." % len(CENTERS))
    for attendu in ("system-center.tsx", "security-center.tsx",
                    "evolution-center.tsx", "governance-center.tsx"):
        assert attendu in noms, f"{attendu} est sorti du corpus de la garde"


def test_le_nombre_d_outils_mcp_affiche_est_celui_du_serveur():
    """« 71 outils » avait derive : le serveur en exposait 81.

    Le Tools Center oppose les outils DECLARES, qui ne s'executent pas, aux
    outils MCP, qui s'executent. Le contraste porte un nombre, et ce nombre
    etait juste le jour ou il a ete ecrit. Dix outils Studio plus tard il
    etait faux, affiche avec la meme assurance. Une garde vaut mieux ici
    qu'une route : le chiffre ne bouge qu'avec `_ALL_TOOLS`.
    """
    serveur = (RACINE / "backend" / "mcp_server" / "server.py").read_text(
        encoding="utf-8")
    liste = re.search(r"_ALL_TOOLS = \[(.*?)\n\]", serveur, re.DOTALL)
    assert liste, "`_ALL_TOOLS` est introuvable dans le serveur MCP"
    reel = len([n for n in (x.strip().rstrip(",")
                            for x in liste.group(1).split("\n"))
                if re.fullmatch(r"[A-Za-z_]\w*", n)])

    centre = (RACINE / "frontend" / "src" / "features" / "tools"
              / "tools-center.tsx").read_text(encoding="utf-8")
    affiche = re.search(r"(\d+) outils\s*</span>\s*\n?\s*du serveur MCP", centre)
    assert affiche, "le Tools Center n'annonce plus de nombre d'outils MCP"
    assert int(affiche.group(1)) == reel, (
        "le Tools Center annonce %s outils MCP, le serveur en expose %d"
        % (affiche.group(1), reel))


def test_le_system_center_ne_revendique_pas_le_graphe_de_dependances():
    """« 42 arêtes de dépendance suivies » n'avait aucune source.

    Trois lignes du System Center affirmaient un graphe analyse : « aucune
    dependance cyclique detectee », « 25 composants dans l'ordre
    topologique » (la liste juste a cote en montrait onze), « 42 aretes de
    dependance suivies ». `ServiceHealthProbe.health()` rend `status`,
    `services`, `by_status`, `unhealthy`, `silent`, `detail` — et rien
    d'autre. Un compteur sans producteur se lit comme une mesure ; une
    capacite annoncee sans producteur se lit comme une garantie.

    La garde ne porte que sur le CHIFFRE. Elle a d'abord cherche les mots
    eux-memes, et elle a signale le texte de remplacement — « aucune route
    n'en publie les aretes ni ne signale les cycles » — qui NIE la
    capacite. Un mot ne dit pas si la phrase affirme ou dement ; un nombre
    colle au mot, si. « 42 aretes » est une mesure, « les aretes » est du
    francais. La garde tient donc le lien quantifie, et la classe
    « affirmation de capacite sans producteur » reste hors de sa portee —
    inscrite comme telle dans les limites de couverture de HOS-289.
    """
    sante = (RACINE / "backend" / "core" / "bootstrap" / "health.py").read_text(
        encoding="utf-8")
    retour = re.search(r"def health\(self\).*?\n        return \{(.*?)\n        \}",
                       sante, re.DOTALL)
    assert retour, "la charge utile de `health()` est introuvable"
    cles = set(re.findall(r'"(\w+)":', retour.group(1)))

    centre = (RACINE / "frontend" / "src" / "features" / "system"
              / "system-center.tsx").read_text(encoding="utf-8")
    # Le texte rendu seulement : un commentaire qui RACONTE le retrait de
    # ces lignes ne doit pas etre lu comme leur retour.
    rendu = re.sub(r"/\*.*?\*/", "", centre, flags=re.DOTALL)

    for mot, cle in (("arêtes?", "edges"), ("cycliques?", "cycles"),
                     ("ordre topologique", "topological_order")):
        # Un nombre litteral colle au mot : « 42 arêtes », « 25 composants
        # dans l'ordre topologique ». Une interpolation `{x.length}` n'en
        # est pas un — elle a une source.
        chiffre = re.search(r"(?<!\{)\b\d[\d\s.,]*\s*[^<>{}\n]{0,40}?\b" + mot,
                            rendu, re.IGNORECASE)
        if chiffre:
            assert cle in cles, (
                "le System Center chiffre « %s » alors que `health()` ne rend "
                "que %s : la charge utile ne porte pas `%s`."
                % (chiffre.group(0).strip(), sorted(cles), cle))


def test_la_garde_attrape_les_defauts_connus():
    """Une garde se verifie sur les defauts qu'elle pretend fermer.

    Les blocs sont rejoues ici tels qu'ils etaient. Si la garde ne les
    attrape plus — parce qu'un motif a ete « simplifie », par exemple —
    elle ne mesure plus rien, et ces assertions le disent avant qu'un
    ecran ne recommence.
    """
    menaces = '''
        <Card title="Active Threats">
          <div>
            {[
              { type: "Unauthorized file access", level: "medium", source: "agent.unknown_dev", count: 3 },
              { type: "Sandbox violation attempt", level: "high", source: "agent.tool_x", count: 1 },
            ].map((threat, i) => (
              <div key={i}>{threat.type}</div>
            ))}
          </div>
        </Card>
'''
    assert _inventes(menaces), (
        "la garde ne retrouve plus les menaces inventees de HOS-288")

    # L'exemption ne doit pas se prendre avec un mot. Mesure du
    # 2026-09-11 : ce bloc-ci passait.
    exemption_abusive = '''
        {/* description */}
        <Card title="Optimization Patterns">
          {[
            { pattern: "High latency", freq: 12, rate: 0.85, gain: 22 },
          ].map((pt, i) => (<div key={i}>{pt.pattern}</div>))}
        </Card>
'''
    assert _inventes(exemption_abusive), (
        "un bloc chiffre se fait exempter par le seul mot « description »")

    # Et elle laisse passer un descripteur de presentation.
    legitime = '''
            {[
              { header: "Quand", cell: (o) => <span>{o.horodatage}</span> },
              { header: "Action", cell: (o) => <Badge>{o.action}</Badge> },
            ].map((c) => (
              <th key={c.header}>{c.header}</th>
            ))}
'''
    assert not _inventes(legitime), (
        "la garde attrape des colonnes de tableau : elle est trop large")

    # Et une description d'architecture qui se declare comme telle, dont
    # le seul chiffre sert la mise en page.
    decrite = '''
            {/* description des couches, pas une mesure */}
            {[
              { layer: "Core", items: "Event Hub", level: 0 },
              { layer: "Runtime", items: "EventBus", level: 1 },
            ].map((x) => (
              <div key={x.layer} style={{ paddingLeft: `${x.level * 16}px` }}>{x.layer}</div>
            ))}
'''
    assert not _inventes(decrite), (
        "un bloc declare descriptif, sans chiffre affiche, est encore refuse")
