# -*- coding: utf-8 -*-
"""Les Skills du cerveau : ce qui est integrable, et ce qui ne l'est pas
(G-26, HOS-274).

## Ce que la mesure a etabli sur le runtime v0.21.0

`skills.manage` porte cinq actions. Sept autres — celles qui muteraient —
rendent `4017 unknown skills action` :

    list search install browse inspect                repondent
    create edit delete pending diff approve reject    4017

## Les deux vérités qui n'en font plus qu'une

Hermes OS lisait DEJA les competences de l'agent, depuis HOS-153, par
`backend/skills/registre.py`. Mais il lisait
`hermes/hermes-agent/skills` — les competences livrees avec le **depot**
de l'agent — au lieu du dossier **actif** `hermes/skills` que le runtime
resout, et il ignorait le champ `platforms:` que chaque `SKILL.md`
declare. Mesure du 2026-09-09 :

    registre.py (avant)   60 noms
    skills.manage list    65 noms
    en commun             40

Le Skills Center montrait donc `imessage`, `findmy` et `apple-notes` a un
agent **Windows** qui ne les chargera jamais, et taisait 25 competences
qu'il porte vraiment. Corrige, les deux concordent **exactement** : 65
contre 65, aucun ecart dans un sens ni dans l'autre.

C'est pourquoi `vue_skills` ne sert que le **catalogue distant**. Offrir
la population installee par RPC aurait recree la seconde verite que cette
passe vient de fermer — et sans les descriptions, que seul le disque
porte.

## Les deux defauts du runtime que ces tests consignent

**`install` rend un faux succes.** `_skills_install` appelle `do_install`
et jette sa valeur de retour ; `do_install` rend `None` sur six chemins,
dont celui ou le scanner de securite BLOQUE la pose. Mesure : un nom qui
n'existe nulle part rend `{"installed": true}`, sans quarantaine ni ligne
d'audit. Un bouton la-dessus transformerait un refus de securite en
reussite affichee.

**`list` est memoise pour la vie du processus.** Mesure sur un
`HERMES_HOME` de substitution :

    processus qui ecrit la skill   scan True  / liste False
    nouveau processus              scan True  / liste True

Et `skills.reload` ne rattrape pas : il annonce `added=['hos274-reload']`
pendant que `list` continue de l'ignorer dans le meme processus. La
persistance est reelle, la decouverte aussi — par un processus neuf.
"""
from __future__ import annotations

import ast
from pathlib import Path

from backend.services import vue_agent, vue_skills

RACINE = Path(__file__).resolve().parents[2]
CENTER = (RACINE / "frontend" / "src" / "features" / "skills"
          / "skills-center.tsx")


class _FauxPont:
    def __init__(self, reponses=None, leve=None):
        self.reponses = reponses or {}
        self.leve = leve
        self.params: list = []

    def appeler(self, methode, params=None, timeout=None):
        self.params.append((methode, params))
        if self.leve is not None:
            raise self.leve
        action = (params or {}).get("action")
        cle = f"{methode}:{action}" if action else methode
        return self.reponses.get(
            cle, {"error": {"code": 4017,
                            "message": f"unknown skills action: {action}"}})


def _brancher(monkeypatch, reponses=None, leve=None) -> _FauxPont:
    faux = _FauxPont(reponses, leve)
    monkeypatch.setattr(vue_agent, "_pont", lambda: faux)
    return faux


# ── Les deux populations ne se confondent jamais ──────────────────────

def test_une_skill_installee_hors_hub_n_est_pas_une_panne(monkeypatch):
    """Mesure : `inspect("github-pr-workflow")` rend `{}` alors que la
    skill est installee — `inspect_skill` resout contre les sources du
    hub, pas contre le disque.

    Un `{}` rendu tel quel donnerait un panneau vide indistinguable d'un
    gateway muet. `connu` porte la difference, comme `disponible` porte
    celle entre « zero » et « on n'a pas pu demander »."""
    _brancher(monkeypatch, {"skills.manage:inspect": {"result": {"info": {}}}})
    vue = vue_skills.detail("github-pr-workflow")
    assert vue["disponible"] is True, "le gateway a repondu"
    assert vue["connu"] is False, "le hub ignore ce nom"
    assert vue["erreur"] is None


def test_un_gateway_muet_se_distingue_d_un_nom_inconnu(monkeypatch):
    _brancher(monkeypatch, leve=OSError("gateway mort"))
    vue = vue_skills.detail("1password")
    assert vue["disponible"] is False and vue["connu"] is False
    assert vue["erreur"] and "gateway mort" in vue["erreur"]


# ── La pagination vient du runtime, elle n'est pas devinee ────────────

def test_la_pagination_du_catalogue_est_lue_et_non_inferee(monkeypatch):
    """HOS-266 avait affiche « 100 sur 200 » ou 200 etait le plafond du
    gateway. Ici `total` et `total_pages` sont des donnees du runtime."""
    _brancher(monkeypatch, {
        "skills.manage:browse": {"result": {"items": [{"name": "z"}],
                                            "page": 7, "total_pages": 275,
                                            "total": 5493}}})
    vue = vue_skills.catalogue(7)
    assert (vue["page"], vue["pages"], vue["total"]) == (7, 275, 5493)
    assert len(vue["elements"]) == 1, (
        "`total` decrit le catalogue, pas la page servie")


def test_le_plafond_de_recherche_est_annonce(monkeypatch):
    """`_skills_search` passe `limit=20` en dur. Vingt resultats ne veut
    donc pas dire « vingt correspondances »."""
    _brancher(monkeypatch, {
        "skills.manage:search": {"result": {"results": [{"name": str(i)}
                                                        for i in range(20)]}}})
    assert vue_skills.rechercher("git")["tronque"] is True
    _brancher(monkeypatch, {
        "skills.manage:search": {"result": {"results": [{"name": "a"}]}}})
    assert vue_skills.rechercher("git")["tronque"] is False


def test_une_recherche_vide_n_interroge_pas_le_hub(monkeypatch):
    """Le hub est distant ; une frappe vide ne doit pas le solliciter."""
    pont = _brancher(monkeypatch)
    assert vue_skills.rechercher("   ")["total"] == 0
    assert pont.params == []


# ── Ce qui n'est pas integre, et ne doit pas le devenir ───────────────

MUTATIONS_REFUSEES = ("install", "create", "edit", "delete", "patch",
                      "pending", "diff", "approve", "reject")


def _litteraux(chemin: Path) -> set:
    """Les chaines que le module *execute*, docstrings exclues.

    Une docstring qui cite `pending` documente ce que le runtime refuse ;
    elle ne nomme aucun chemin. Les confondre ferait echouer la garde sur
    le texte meme qui explique pourquoi elle existe — un garde-fou qui
    punit sa propre justification.
    """
    arbre = ast.parse(chemin.read_text(encoding="utf-8"))
    docs = set()
    for noeud in ast.walk(arbre):
        if isinstance(noeud, (ast.Module, ast.FunctionDef,
                              ast.AsyncFunctionDef, ast.ClassDef)):
            corps = getattr(noeud, "body", None) or []
            if (corps and isinstance(corps[0], ast.Expr)
                    and isinstance(corps[0].value, ast.Constant)
                    and isinstance(corps[0].value.value, str)):
                docs.add(id(corps[0].value))
    return {n.value for n in ast.walk(arbre)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
            and id(n) not in docs}


def test_un_seul_module_demande_une_mutation_de_skill():
    """**Rescopee par G-36.** Elle interdisait toute demande de mutation,
    parce qu'`install` rend `{"installed": true}` sans regarder ce que
    `do_install` a fait. La mesure de G-35 a precise le defaut : c'est le
    COMPTE RENDU qui est faux, pas l'ecriture — celle-ci se verifie a
    l'octet par l'empreinte du verrou. G-36 branche l'approbateur.

    Ce qui la remplace est plus etroit et plus utile : un seul module a le
    droit de demander, `backend/skills/installation.py`, et lui seul passe
    par Aegis. Une seconde voie contournerait la barriere sans que rien ne
    le dise — et les six autres actions n'existent toujours pas (`4017`).

    Sa portee : les modules qui nomment `skills.manage` litteralement. Un
    appelant qui composerait la methode a l'execution y echapperait — mais
    il echapperait aussi a toute lecture humaine, et ce n'est pas la forme
    que prend l'erreur qu'on veut empecher."""
    AUTORISE = "backend\\skills\\installation.py"
    coupables = []
    for module in (RACINE / "backend").rglob("*.py"):
        if "tests" in module.parts:
            continue
        source = module.read_text(encoding="utf-8", errors="replace")
        if "skills.manage" not in source:
            continue
        relatif = str(module.relative_to(RACINE))
        litteraux = _litteraux(module)
        for action in MUTATIONS_REFUSEES:
            if action in litteraux and relatif != AUTORISE:
                coupables.append(f"{relatif} -> {action}")
    assert not coupables, (
        "un module autre que `skills/installation.py` demande une mutation "
        "de Skill, donc sans passer par Aegis : " + ", ".join(coupables))

    # Et le module autorise DOIT passer par Aegis : sans cette moitie, la
    # garde ci-dessus se satisferait d'un module qui installe directement.
    source = (RACINE / "backend" / "skills"
              / "installation.py").read_text(encoding="utf-8")
    assert "_aegis()" in source and "Verdict.ALLOW" in source, (
        "le module autorise ne soumet pas son action a Aegis")


def test_le_pont_declare_la_pose_et_dit_ce_qu_elle_ecrit():
    """**Rescopee par G-36.** Elle disait « aucune methode `skills.*` n'y a
    sa place », et sa raison — « install n'ecrit pas de facon verifiable »
    — a ete corrigee par la mesure : l'ecriture se verifie a l'octet, c'est
    le compte rendu qui ne vaut rien.

    Ce qui reste garde est ce que `MUTATIONS_CONNUES` sert a dire : QUEL
    fichier de l'agent une methode change. Une entree qui ne le nommerait
    pas ne serait qu'une autorisation."""
    from backend.bridge.hermes_agent_bridge import MUTATIONS_CONNUES

    skills = [m for m in MUTATIONS_CONNUES if m.startswith("skills.")]
    assert skills == ["skills.manage"], skills
    assert "hermes-agent:" in MUTATIONS_CONNUES["skills.manage"]
    assert "skills" in MUTATIONS_CONNUES["skills.manage"]


def test_aucune_route_n_offre_une_mutation_de_skill():
    """Le vrai joint n'est pas le composant : c'est la route.

    Le cockpit ne peut poser une Skill que si une route l'accepte. La
    garde porte donc sur le routeur — la lecon repetee de ce depot etant
    qu'une garde ecrite sur une *forme* (le nom d'un bouton, la presence
    d'un `fetch`) ne garde rien : elle se contourne en renommant."""
    source = (RACINE / "backend" / "api" / "routes"
              / "bridge.py").read_text(encoding="utf-8")
    arbre = ast.parse(source)
    fautives = []
    for noeud in ast.walk(arbre):
        if not isinstance(noeud, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for deco in noeud.decorator_list:
            if not isinstance(deco, ast.Call):
                continue
            verbe = getattr(deco.func, "attr", "")
            chemin = (deco.args[0].value
                      if deco.args and isinstance(deco.args[0], ast.Constant)
                      else "")
            if "skills" in str(chemin) and verbe != "get":
                appels = {getattr(c.func, "attr", None)
                          for c in ast.walk(noeud) if isinstance(c, ast.Call)}
                if "installer" not in appels:
                    fautives.append(f"{verbe.upper()} {chemin}")
    assert not fautives, (
        "une route mute les Skills sans passer par "
        "`installation.installer`, donc sans Aegis : " + ", ".join(fautives))


def _corps_de(source: str, nom: str) -> str:
    """Le corps d'un composant, borne au SUIVANT.

    Ces deux gardes decoupaient jusqu'a la fin du fichier : tout composant
    ajoute plus bas y entrait. G-36 l'a paye — la surface de demande
    d'installation, definie apres, faisait rougir le catalogue pour un
    `skillsClient` qui n'etait pas le sien. Une garde bornee par la fin du
    fichier grandit toute seule.
    """
    debut = source.index(f"function {nom}(")
    suite = source.find("\nfunction ", debut + 1)
    return source[debut:suite if suite > 0 else len(source)]


def test_le_cockpit_dit_pourquoi_il_n_installe_pas():
    """Une capacite absente sans explication se lit comme un oubli, et la
    passe suivante la « repare » en cablant `install`. L'ecran porte donc
    la raison, pas seulement le silence."""
    corps = _corps_de(CENTER.read_text(encoding="utf-8"), "OngletCatalogue")
    assert "Consultation seule" in corps
    assert "sans vérifier" in corps, (
        "l'ecran tait pourquoi l'installation n'est pas offerte")


def test_le_catalogue_ne_pretend_pas_dire_ce_qui_est_installe():
    """Le hub porte 5493 entrees, le disque 65 : un ecran qui melangerait
    les deux laisserait croire qu'une entree du catalogue est posee. Les
    deux onglets ont donc deux sources, et le catalogue n'appelle pas
    celle du disque."""
    corps = _corps_de(CENTER.read_text(encoding="utf-8"), "OngletCatalogue")
    assert "skillsClient" not in corps, (
        "le catalogue lit la source du disque : deux populations melangees")


# ── La verite unique de la population installee ───────────────────────

def test_le_registre_lit_le_dossier_actif_et_non_celui_du_depot(monkeypatch):
    """Il pointait `hermes/hermes-agent/skills` — les competences du
    **depot** de l'agent — quand le runtime resout `hermes/skills`. Mesure
    du 2026-09-09 : 60 noms contre 65, 40 en commun. Le segment de trop
    montrait vingt competences que le cerveau ne sert pas, et en taisait
    vingt-cinq qu'il sert.

    **`HERMES_HOME` est retire expres.** Ecrit sans, ce test passait sur
    cette machine pour la mauvaise raison : la variable y est posee, donc
    la lecture n'atteignait jamais le repli — et une mutation qui
    reintroduisait `hermes-agent` restait **verte**. La relecture n'a rien
    vu ; la mutation, si. Troisieme fois dans ce depot.
    """
    import importlib

    monkeypatch.delenv("HERMES_HOME", raising=False)
    from backend.skills import registre

    recharge = importlib.reload(registre)
    try:
        racine = recharge.racine_des_competences()
        assert racine.parts[-2:] == ("hermes", "skills"), racine
        assert "hermes-agent" not in str(racine), (
            "le registre lit les competences du depot, pas celles qui sont "
            "actives : elles different de vingt-cinq noms")
    finally:
        importlib.reload(registre)


def test_le_registre_suit_HERMES_HOME(tmp_path, monkeypatch):
    """Le runtime resout son foyer par `HERMES_HOME` avant le defaut de
    plateforme. Un registre qui l'ignorerait lirait un autre profil que
    celui que l'agent sert."""
    import importlib

    from backend.skills import registre

    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    recharge = importlib.reload(registre)
    try:
        assert recharge.racine_des_competences() == tmp_path / "skills"
    finally:
        monkeypatch.delenv("HERMES_HOME", raising=False)
        importlib.reload(registre)


def _poser(dossier, nom, entete=""):
    d = dossier / nom
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(
        f"---\nname: {nom}\ndescription: sonde\n{entete}---\n\nCorps.\n",
        encoding="utf-8")


def test_une_competence_d_une_autre_plateforme_n_est_pas_annoncee(tmp_path):
    """`platforms: [macos]` sur Windows veut dire : l'agent ne la chargera
    pas. L'ecran annoncait pourtant `imessage`, `findmy` et `apple-notes`.

    Lire ce champ n'est pas reimplementer la resolution du runtime — c'est
    lire ce que le fichier **declare**."""
    from backend.skills import registre

    base = tmp_path / "skills"
    _poser(base, "partout")
    _poser(base, "ailleurs", "platforms: [macos]\n")
    _poser(base, "ici", f"platforms: [{registre._PLATEFORME}]\n")  # noqa: SLF001

    noms = {c.nom for c in registre.lire(str(tmp_path))}
    assert noms == {"partout", "ici"}, noms


def test_une_declaration_de_plateforme_illisible_n_exclut_rien(tmp_path):
    """Le lecteur d'en-tete est volontairement primitif : il ne voit qu'un
    `platforms:` sur une ligne. Une forme qu'il ne sait pas lire doit
    laisser la competence visible — masquer sur un doute ferait disparaitre
    en silence ce que l'agent sert vraiment."""
    from backend.skills import registre

    base = tmp_path / "skills"
    _poser(base, "sur_plusieurs_lignes", "platforms:\n  - macos\n")
    noms = {c.nom for c in registre.lire(str(tmp_path))}
    assert noms == {"sur_plusieurs_lignes"}


def test_la_vue_skills_n_ecrit_rien():
    """La meme garde que `vue_agent` et `vue_operations` portent : une vue
    qui se met a ecrire devient une autorite concurrente sans que personne
    ne l'ait decide."""
    arbre = ast.parse((RACINE / "backend" / "services"
                       / "vue_skills.py").read_text(encoding="utf-8"))
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.Call):
            cible = noeud.func
            nom = getattr(cible, "attr", None) or getattr(cible, "id", None)
            assert nom not in {"open", "write_text", "mkdir", "unlink",
                               "rmtree", "replace"}, (
                f"la vue skills appelle `{nom}`")


def test_la_vue_skills_ne_touche_pas_au_disque_de_l_agent():
    """La file `pending/skills/*.json` existe cote agent et Hermes OS
    pourrait la lire — et la vider, puisque « rejeter » n'est qu'un
    `unlink`. Ce serait faire de Hermes OS un ecrivain de l'etat de
    l'agent par la porte de derriere. Rien ici ne nomme ce chemin."""
    litteraux = _litteraux(RACINE / "backend" / "services" / "vue_skills.py")
    for interdit in ("pending", "LOCALAPPDATA", ".hermes"):
        assert not any(interdit in x for x in litteraux), (
            f"la vue nomme `{interdit}` : elle lit le disque de l'agent")


def test_la_vue_n_emet_que_les_actions_qui_existent():
    """Cinq actions repondent, sept rendent `4017`. Une action inventee ne
    leverait pas : elle rendrait une enveloppe `disponible: false` que
    l'ecran afficherait comme une panne du gateway. Le defaut serait donc
    silencieux et mal attribue."""
    arbre = ast.parse((RACINE / "backend" / "services"
                       / "vue_skills.py").read_text(encoding="utf-8"))
    emises = set()
    for noeud in ast.walk(arbre):
        if not isinstance(noeud, ast.Dict):
            continue
        for cle, valeur in zip(noeud.keys, noeud.values):
            if (isinstance(cle, ast.Constant) and cle.value == "action"
                    and isinstance(valeur, ast.Constant)):
                emises.add(valeur.value)
    assert emises == {"browse", "search", "inspect"}, (
        f"actions emises : {sorted(emises)} — `install` repond mais ment, "
        "les sept autres n'existent pas, et `list` appartient au disque")
