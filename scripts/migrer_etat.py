"""Sortir l'état de l'utilisateur du dépôt (HOS-215).

Déplace ce qui vivait sous `data/` — et `_memory_.db` à la racine — vers
la racine d'état résolue par `backend/core/etat.py`.

## Ce qu'il refuse de faire

**Écraser.** Si la cible existe déjà et diffère, le fichier est laissé en
place et signalé. Une migration qui écrase silencieusement est pire que
pas de migration : elle détruit ce qu'elle prétend sauver.

**Supprimer avant d'avoir vérifié.** Rien n'est effacé de la source tant
que la copie n'a pas été relue et comparée en taille. `--supprimer` ne
retire que ce qui a été vérifié identique.

**Deviner.** Un `--essai` montre ce qui serait fait, sans rien toucher.
C'est le mode par défaut.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.core.etat import RACINE_DEPOT, racine  # noqa: E402

#: Ce qui déménage, et où. La source est relative au dépôt.
#:
#: `data/workflows` n'y est pas : ses fichiers sont suivis par git,
#: donc livrés avec l'application. Les déplacer a vidé `/workflows`.
DEMENAGEMENTS = [
    ("data/db", "db"),
    ("data/logs", "logs"),
    ("data/snapshots", "snapshots"),
    ("data/eventbus", "eventbus"),
    ("data/autonomy_override.json", "config/autonomy_override.json"),
    ("_memory_.db", "memoire/_memory_.db"),
]


def _taille(chemin: Path) -> int:
    if chemin.is_file():
        return chemin.stat().st_size
    return sum(f.stat().st_size for f in chemin.rglob("*") if f.is_file())


def _copier(source: Path, cible: Path) -> tuple[bool, str]:
    """Copier, sans jamais écraser un contenu différent."""
    if cible.exists():
        if _taille(cible) == _taille(source):
            return True, "déjà présent, taille identique"
        # Un dossier **vide** n'est pas un conflit : `etat.racine()` crée
        # les sous-dossiers au premier import, donc la cible existe
        # toujours avant la migration. Refuser là-dessus bloquerait
        # exactement le cas normal.
        vide = cible.is_dir() and not any(cible.iterdir())
        if not vide:
            return False, (f"la cible existe et diffère "
                           f"({_taille(cible)} vs {_taille(source)} octets) — "
                           "laissé en place, à trancher à la main")
    cible.parent.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        shutil.copytree(source, cible, dirs_exist_ok=True)
    else:
        shutil.copy2(source, cible)
    # Vérifié après coup, pas d'après le code de retour de shutil.
    if not cible.exists() or _taille(cible) != _taille(source):
        return False, "la copie ne fait pas la taille de la source"
    return True, f"{_taille(source) / 2**20:.1f} Mio copiés"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--appliquer", action="store_true",
                        help="copier réellement (sinon : essai à blanc)")
    parser.add_argument("--supprimer", action="store_true",
                        help="retirer la source après une copie vérifiée")
    args = parser.parse_args(argv[1:])

    cible_racine = racine()
    print(f"dépôt  : {RACINE_DEPOT}")
    print(f"état   : {cible_racine}")
    print(f"mode   : {'APPLIQUÉ' if args.appliquer else 'essai à blanc'}\n")

    total = 0
    verifies: list[Path] = []
    for rel_source, rel_cible in DEMENAGEMENTS:
        source = RACINE_DEPOT / rel_source
        cible = cible_racine / rel_cible
        if not source.exists():
            continue
        taille = _taille(source)
        total += taille
        if not args.appliquer:
            print(f"  {rel_source:<32} → {rel_cible:<30} "
                  f"{taille / 2**20:>7.1f} Mio")
            continue
        ok, detail = _copier(source, cible)
        print(f"  {'ok  ' if ok else 'ÉCHEC'} {rel_source:<32} {detail}")
        if ok:
            verifies.append(source)

    print(f"\n  total : {total / 2**20:.1f} Mio")

    if not args.appliquer:
        print("\nRien n'a été touché. Relancer avec --appliquer.")
        return 0

    if args.supprimer:
        print()
        for source in verifies:
            if source.is_dir():
                shutil.rmtree(source)
            else:
                source.unlink()
            print(f"  source retirée : {source.relative_to(RACINE_DEPOT)}")
    else:
        print("\nLes sources sont laissées en place. Relancer avec "
              "--supprimer une fois la migration vérifiée.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
