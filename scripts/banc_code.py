"""Noter un modele sur les neuf epreuves de code du depot.

    .venv/Scripts/python.exe scripts/banc_code.py gpt-oss-20b-64k
    .venv/Scripts/python.exe scripts/banc_code.py qwen38-27b-64k --num-ctx 65536

## Pourquoi cet outil existe

`code_bench.py` porte les epreuves et leurs assertions, mais **aucun point
d'entree** ne les enchainait : les bancs de `docs/release/` avaient ete
produits par un script ad hoc que personne n'avait garde. Meme absence que
pour les sondes agentiques avant HOS-143, et meme consequence — une question
simple, « ce modele code-t-il mieux que celui-la ? », demandait de reecrire
l'instrument.

Elle s'est posee le 2026-08-22 : Qwen3.8-27B venait d'obtenir 8/9, et le
catalogue notait gpt-oss « code 100 ». **Ces deux chiffres ne sont pas
comparables** — le second vient d'un bareme par paliers (`bench_score.py`),
le premier de ces neuf epreuves. Comparer deux modeles exige de les passer
au meme instrument.

## Ce que le banc mesure, et comment

Neuf epreuves de difficulte croissante, de `compter_mots` a
`compteur_concurrent`, jugees par des **assertions executees** — jamais par
la lecture de la reponse. Deux d'entre elles ne se contentent pas de la
justesse : `top_k_efficace` chronometre, `compteur_concurrent` verifie
l'exactitude sous contention reelle.

`done_reason == "length"` est releve separement : une reponse tronquee n'est
pas une erreur de raisonnement et ne doit pas se noter comme telle.

## Un modele a la fois

Sur 16 Go de VRAM, deux bancs simultanes mesurent la contention. Le temps
depend du debit : compter une heure pour un modele a 8,7 tok/s, dix minutes
pour un modele a 90.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.model_intelligence.code_bench import TASKS, run_code_task  # noqa: E402
from backend.model_intelligence.model_bench import (  # noqa: E402
    generate,
    gpu_dedicated_bytes,
    runtime_footprint,
    throughput_of,
)

GIO = 2 ** 30

#: Large : une epreuve de niveau « extreme » a demande 518 s a 8,7 tok/s. Un
#: plafond trop court transformerait un modele lent en modele incapable —
#: `generate` prend `timeout_s`, et passer `timeout` envoie la valeur dans
#: les options de generation d'Ollama sans rien plafonner du tout.
DELAI_S = 3600.0


def noter(modele: str, num_ctx: int) -> dict:
    print(f"=== {modele} a num_ctx={num_ctx} ({num_ctx // 1024}k) ===\n",
          flush=True)
    resultats, debits = [], []
    reussies = tronquees = 0
    empreinte: dict = {}
    gpu = 0

    for n, tache in enumerate(TASKS, 1):
        depart = time.monotonic()
        reponse = generate(modele, tache.prompt, num_ctx=num_ctx,
                           timeout_s=DELAI_S)
        duree = time.monotonic() - depart
        coupee = reponse.get("done_reason") == "length"
        tronquees += coupee

        verdict = run_code_task(tache, reponse.get("response") or "")
        ok = bool(getattr(verdict, "passed", False))
        reussies += ok
        detail = str(getattr(verdict, "detail", ""))[:60]

        debit = throughput_of(reponse)
        debits.append(debit.get("output_tokens_per_s", 0.0))
        if n == 1:
            # L'empreinte ne bouge plus une fois le modele charge : on la
            # lit au premier passage, quand il vient d'occuper sa place.
            empreinte = runtime_footprint(modele)
            gpu = gpu_dedicated_bytes() or 0

        print(f"  {n}/{len(TASKS)} {tache.level:8} {tache.name:22} "
              f"{'OK ' if ok else 'NON'} {duree:6.0f}s "
              f"{debit.get('output_tokens_per_s', 0):5.1f} tok/s"
              + ("  [TRONQUEE]" if coupee else "")
              + (f"  {detail}" if not ok else ""), flush=True)
        resultats.append({"tache": tache.name, "niveau": tache.level,
                          "reussi": ok, "detail": detail, "tronquee": coupee,
                          "duree_s": round(duree, 1),
                          "tok_s": round(debit.get("output_tokens_per_s", 0), 1)})

    poids = empreinte.get("size_bytes") or 0
    vram = empreinte.get("size_vram_bytes") or 0
    deport = poids - vram
    moyen = sum(debits) / len(debits) if debits else 0.0

    print(f"\n  occupation : {poids / GIO:.2f} Gio, dont "
          f"{deport / GIO:.2f} sur CPU "
          f"({100 * deport / poids if poids else 0:.1f} %) | "
          f"GPU reel {gpu / GIO:.2f} Gio")
    print(f"  debit      : {moyen:.1f} tok/s en moyenne")
    print(f"  NOTE       : {reussies}/{len(TASKS)}   "
          f"(tronquees : {tronquees})")

    return {"modele": modele, "num_ctx": num_ctx, "note": reussies,
            "total": len(TASKS), "tronquees": tronquees,
            "empreinte": empreinte, "gpu_dedicated_bytes": gpu,
            "deport_ratio": round(100 * deport / poids, 1) if poids else None,
            "tok_s_moyen": round(moyen, 1), "resultats": resultats}


def main() -> int:
    analyseur = argparse.ArgumentParser(description=__doc__)
    analyseur.add_argument("modele")
    analyseur.add_argument("--num-ctx", type=int, default=65536)
    analyseur.add_argument("--sortie", default="")
    args = analyseur.parse_args()

    banc = noter(args.modele, args.num_ctx)

    destination = Path(args.sortie or
                       f"docs/release/banc_code_{args.modele}.json")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(banc, ensure_ascii=False, indent=1),
                           encoding="utf-8")
    print(f"\n  banc ecrit : {destination}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
