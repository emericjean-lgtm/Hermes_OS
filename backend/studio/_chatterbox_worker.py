"""Le seul fichier qui tourne dans l'environnement Chatterbox (HOS-195).

## Pourquoi un environnement séparé

`chatterbox-tts` épingle `torch==2.6.0`. L'installer dans `.venv` — ou pire,
dans l'interpréteur embarqué de ComfyUI — remplacerait le torch ROCm 2.13
par une build CPU et casserait tous les rendus. `C:\\AI\\Apps\\chatterbox-venv`
hérite du torch de ComfyUI par un `.pth`, et Chatterbox y est installé
`--no-deps` pour ne jamais retirer ce torch. Vérifié après coup : ComfyUI
répond toujours, en ROCm, GPU actif.

C'est la même frontière que celle documentée dans
`backend/ral/adapters/hermes_agent_cli.py` pour Hermes Agent — deux
environnements Python, jamais confondus, jamais l'un ne réinstalle dans
l'autre.

## Ce que ce script fait, et où il s'arrête

Il lit une requête JSON sur stdin, charge le modèle **une fois**, synthétise
chaque segment demandé, écrit chaque WAV sur disque, et rend la liste des
chemins sur stdout. Un seul chargement pour plusieurs segments : le
chargement coûte 9 à 27 s mesurés, et une narration compte plusieurs
répliques.

Il ne décide de rien — ni du texte, ni du découpage en segments, ni des
réglages de voix. Tout arrive en paramètre. C'est `narration.py`, côté
backend principal, qui appelle ce script et qui reste le seul point où la
règle qui prime sur tout s'applique.
"""
from __future__ import annotations

import json
import os
import sys
import time


def main() -> None:
    requete = json.loads(sys.stdin.read())
    segments: list[dict] = requete["segments"]
    reference: str = requete["reference"]
    dossier: str = requete["dossier"]
    exaggeration = float(requete.get("exaggeration", 0.5))
    cfg_weight = float(requete.get("cfg_weight", 0.5))
    langue = str(requete.get("langue", "fr"))

    if not os.path.exists(reference):
        print(json.dumps({"erreur": f"référence introuvable : {reference}"}))
        return

    import soundfile as sf
    import torch
    from chatterbox.mtl_tts import ChatterboxMultilingualTTS

    appareil = "cuda" if torch.cuda.is_available() else "cpu"
    t0 = time.time()
    modele = ChatterboxMultilingualTTS.from_pretrained(device=appareil)
    charge_s = time.time() - t0

    os.makedirs(dossier, exist_ok=True)
    resultats = []
    for seg in segments:
        ident = str(seg["id"])
        texte = str(seg["texte"])
        t1 = time.time()
        try:
            onde = modele.generate(texte, language_id=langue,
                                   audio_prompt_path=reference,
                                   exaggeration=exaggeration,
                                   cfg_weight=cfg_weight)
        except Exception as e:
            resultats.append({"id": ident, "erreur": f"{type(e).__name__}: {e}"})
            continue
        chemin = os.path.join(dossier, f"{ident}.wav")
        sf.write(chemin, onde.detach().cpu().numpy().squeeze(), modele.sr)
        resultats.append({
            "id": ident, "chemin": chemin,
            "duree_s": round(onde.shape[-1] / modele.sr, 3),
            "synthese_s": round(time.time() - t1, 1),
        })

    print(json.dumps({"appareil": appareil, "charge_s": round(charge_s, 1),
                      "resultats": resultats}))


main()
