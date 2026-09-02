"""La commande de test documentee couvre-t-elle tout le depot ? (HOS-213)

`pytest.ini` declare `testpaths = backend/tests tests` depuis HOS-111,
apres qu'on eut decouvert 2 869 tests que personne n'executait. Mais un
argument de chemin passe en ligne de commande **ecrase** `testpaths` :
`pytest backend/tests` ne lance qu'un arbre sur deux.

C'est exactement ce que `CLAUDE.md` a documente, et l'angle mort s'est
rouvert. `tests/` est reste casse vingt-deux jours et trente-sept jalons
— un module qui ne s'importait plus, deux tests qui lançaient un vrai
sous-processus et bloquaient la suite entiere.

La configuration etait juste ; c'est la documentation qui la contournait.
Cette garde surveille la documentation.
"""

from __future__ import annotations

import configparser
import io
import re
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]


def _commandes_pytest_documentees() -> list[str]:
    texte = io.open(RACINE / "CLAUDE.md", encoding="utf-8").read()
    # Les blocs `bash` : c'est ce qu'un lecteur copie.
    blocs = re.findall(r"```bash\n(.*?)```", texte, re.S)
    lignes: list[str] = []
    for bloc in blocs:
        for ligne in bloc.splitlines():
            if "pytest" in ligne and not ligne.strip().startswith("#"):
                # Couper le commentaire de fin de ligne : « # ~6 min » n'est
                # pas un argument, et le compter en ferait un faux chemin.
                lignes.append(ligne.split("#", 1)[0].strip())
    return lignes


def test_pytest_ini_declare_bien_les_deux_arbres():
    cfg = configparser.ConfigParser()
    cfg.read(RACINE / "pytest.ini", encoding="utf-8")
    chemins = cfg["pytest"]["testpaths"].split()
    assert set(chemins) == {"backend/tests", "tests"}, (
        f"testpaths ne couvre plus les deux arbres : {chemins}")


def test_la_commande_documentee_n_ecrase_pas_testpaths():
    """Un chemin en argument annule `testpaths` — silencieusement.

    C'est le defaut a empecher : la commande devient plus etroite que la
    configuration, et la moitie du depot cesse d'etre testee sans qu'aucun
    signal ne le dise.
    """
    for commande in _commandes_pytest_documentees():
        apres = commande.split("pytest", 1)[1].split()
        # Ce qui reste apres « pytest » : on ecarte les options, leurs
        # valeurs, et les marqueurs — seul un chemin nu est fautif.
        chemins: list[str] = []
        precedent = ""
        for a in apres:
            if a.startswith("-"):
                precedent = a
                continue
            if precedent in {"-m", "-k", "-p", "--timeout"}:
                precedent = ""
                continue
            precedent = ""
            if "=" not in a:
                chemins.append(a)
        assert not chemins, (
            f"la commande documentee « {commande} » passe un chemin "
            f"({chemins}) qui ecrase `testpaths` et n'execute qu'une "
            "partie du depot")


def test_au_moins_une_commande_de_test_est_documentee():
    # Sinon la garde ci-dessus passerait sur un fichier qui n'en parle plus.
    assert _commandes_pytest_documentees(), (
        "CLAUDE.md ne documente plus aucune commande de test")
