"""La suite n'écrit jamais dans l'état réel de l'utilisateur (HOS-252, T-20).

## Pourquoi ce fichier existe

L'isolation, elle, existait déjà : `conftest.py` pose `HERMES_DATA_DIR`
sur un répertoire temporaire pour toute la session, depuis HOS-215. Ce qui
manquait était la **vérification**, et son absence a coûté cher au
diagnostic plutôt qu'aux données.

Passe 18 a conclu que la suite lente écrivait dans
`AppData/Local/HermesOS`, sur la foi de deux missions bien réelles
trouvées là. Elles venaient de sondes autonomes, qui ne chargent aucun
`conftest` ; la suite était isolée depuis le début. Une passe entière a
été bâtie sur ce constat faux.

La garde de `conftest.py` rend l'erreur impossible dans les deux sens :
elle arrête tout avant le premier test si la suite pointait vraiment vers
l'état de l'utilisateur, et elle contredit qui l'affirmerait sans que ce
soit vrai.

Elle ne supprime rien et ne touche à aucun réglage : ce serait pire que le
problème.
"""

from __future__ import annotations

import os
from pathlib import Path

from backend.core.etat import _racine_systeme

from conftest import racines_confondues


def _canonique(chemin) -> Path:
    return Path(os.path.normcase(str(Path(chemin).expanduser().resolve())))


# ═══ Le positif : la suite est bien isolée ═══════════════════════════

def test_la_suite_ecrit_dans_un_repertoire_temporaire():
    essai = os.environ.get("HERMES_DATA_DIR")
    assert essai, "HERMES_DATA_DIR n'est pas posé : l'isolation n'existe plus"
    assert not racines_confondues(essai, _racine_systeme()), (
        f"racine de test {essai} / racine réelle {_racine_systeme()}")


def test_la_base_effectivement_ouverte_est_celle_du_temporaire():
    """Le chemin résolu, pas la variable — c'est ce que le code ouvre."""
    from backend.core.config import get_settings

    base = _canonique(get_settings().sqlite_path)
    assert _canonique(os.environ["HERMES_DATA_DIR"]) in base.parents, base


def test_le_magasin_de_missions_ne_voit_pas_les_missions_de_l_utilisateur():
    """La preuve par le contenu : un magasin isolé part vide."""
    from backend.mission.persistance import MagasinMissions

    assert MagasinMissions().nombre() == 0, (
        "le magasin voit des missions : la suite lit l'état réel")


# ═══ Le négatif : la garde mord ══════════════════════════════════════
#
# Sans jamais pointer la suite vers la vraie base : on exerce la **logique
# de comparaison**, pas l'effet de bord.

def test_la_garde_detecte_une_racine_identique():
    vraie = _racine_systeme()
    assert racines_confondues(vraie, vraie) is True


def test_la_garde_detecte_une_racine_imbriquee():
    """Écrire dans un sous-dossier de l'état réel le pollue tout autant."""
    vraie = _racine_systeme()
    assert racines_confondues(vraie / "db" / "tests", vraie) is True


def test_la_garde_ignore_la_casse_et_les_separateurs():
    """Sous Windows, `C:\\Users` et `c:/users` sont le même dossier et ne se
    ressemblent pas."""
    vraie = str(_racine_systeme())
    deguisee = vraie.swapcase().replace("\\", "/")
    assert racines_confondues(deguisee, _racine_systeme()) is True


def test_la_garde_laisse_passer_un_temporaire():
    import tempfile

    ailleurs = tempfile.mkdtemp(prefix="hermes_garde_")
    assert racines_confondues(ailleurs, _racine_systeme()) is False


def test_la_garde_laisse_passer_un_parent_commun_qui_n_est_pas_la_racine():
    """`%LOCALAPPDATA%/Temp/...` partage un ancêtre avec
    `%LOCALAPPDATA%/HermesOS` sans être dedans : la garde ne doit pas
    confondre voisinage et imbrication."""
    vraie = _racine_systeme()
    voisine = vraie.parent / "Temp" / "hermes_donnees_zzz"
    assert racines_confondues(voisine, vraie) is False
