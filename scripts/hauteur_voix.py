"""La hauteur mediane d'une voix, pour verifier un clonage (HOS-212).

HOS-195 avait etabli la regle : « le clonage a ete verifie, pas suppose ».
La hauteur mediane du clone se deplace vers celle de la reference — de
157 Hz (voix par defaut du modele) vers 82-102 Hz selon les reglages,
contre 91,2 Hz mesures sur la reference « Michael ».

Cette mesure existait alors sous forme de script jetable. La remettre ici
evite de la reecrire a chaque changement de voix, et evite surtout de
juger un clone a l'oreille — ce que ce depot a paye assez cher ailleurs.

## Ce que la methode vaut, et ce qu'elle ne vaut pas

Autocorrelation par trame, mediane sur les trames voisees seulement. Ce
n'est pas un estimateur d'etat de l'art ; c'est un estimateur **stable**,
sans dependance supplementaire, et suffisant pour la seule question
posee : la hauteur du clone est-elle celle de la reference, ou celle de
la voix par defaut du modele ?

Le nombre de trames voisees compte autant que la hauteur. Un clone qui
n'en produit que quatre sur une phrase entiere n'a pas une hauteur
« imprecise » : il n'a presque pas de voix. C'est exactement ce qu'avait
montre le premier echantillon de HOS-195, et une mediane seule l'aurait
masque.
"""

from __future__ import annotations

import os
import subprocess
import sys
import wave

import numpy as np

#: Bornes de la voix humaine parlee. Au-dela, l'autocorrelation attrape
#: des harmoniques ou du bruit et la mediane derive sans que rien ne le
#: dise.
HZ_MIN, HZ_MAX = 60.0, 350.0

#: Une trame est dite voisee au-dessus de ce pic d'autocorrelation
#: normalise. En dessous, c'est du silence ou une consonne : l'inclure
#: ferait entrer du bruit dans la mediane.
SEUIL_VOISE = 0.30

TRAME_S = 0.040
PAS_S = 0.020


def _en_wav_mono(chemin: str) -> str:
    """Tout passe par un WAV 24 kHz mono : le reste est du decodage."""
    if chemin.lower().endswith(".wav"):
        with wave.open(chemin, "rb") as w:
            if w.getnchannels() == 1 and w.getsampwidth() == 2:
                return chemin

    from backend.studio.relecteur import ffmpeg

    ff = ffmpeg()
    if not ff:
        raise RuntimeError("ffmpeg introuvable")
    cible = os.path.splitext(chemin)[0] + ".hauteur.wav"
    subprocess.run([ff, "-v", "error", "-i", chemin, "-ar", "24000",
                    "-ac", "1", "-c:a", "pcm_s16le", "-y", cible], check=True)
    return cible


def hauteur(chemin: str) -> dict:
    """Hauteur mediane, en Hz, et de quoi juger si elle veut dire quelque chose."""
    fichier = _en_wav_mono(chemin)
    with wave.open(fichier, "rb") as w:
        taux = w.getframerate()
        brut = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)

    x = brut.astype(np.float64) / 32768.0
    n_trame = int(TRAME_S * taux)
    n_pas = int(PAS_S * taux)
    lag_min, lag_max = int(taux / HZ_MAX), int(taux / HZ_MIN)

    hauteurs: list[float] = []
    trames = 0
    for debut in range(0, max(0, len(x) - n_trame), n_pas):
        trames += 1
        t = x[debut:debut + n_trame]
        t = t - t.mean()
        energie = float(np.dot(t, t))
        if energie < 1e-6:
            continue
        # `full` puis moitie droite : l'autocorrelation d'une trame courte
        # se calcule plus vite ainsi qu'avec une FFT, et sans fenetrage a
        # justifier.
        ac = np.correlate(t, t, mode="full")[n_trame - 1:]
        fenetre = ac[lag_min:lag_max + 1]
        if not len(fenetre):
            continue
        i = int(np.argmax(fenetre))
        pic = float(fenetre[i] / energie)
        if pic < SEUIL_VOISE:
            continue
        hauteurs.append(taux / (lag_min + i))

    if not hauteurs:
        return {"fichier": chemin, "hz_median": None, "trames_voisees": 0,
                "trames": trames}
    a = np.array(hauteurs)
    return {
        "fichier": chemin,
        "hz_median": round(float(np.median(a)), 1),
        "hz_ecart": round(float(np.std(a)), 1),
        "trames_voisees": len(hauteurs),
        "trames": trames,
        "part_voisee": round(len(hauteurs) / max(1, trames), 3),
    }


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage : hauteur_voix.py <audio> [<audio> ...]")
        return 2
    for chemin in argv[1:]:
        r = hauteur(chemin)
        nom = os.path.basename(r["fichier"])
        if r["hz_median"] is None:
            print(f"{nom:<34} aucune trame voisee sur {r['trames']} — "
                  "ce n'est pas une voix")
            continue
        print(f"{nom:<34} {r['hz_median']:>6.1f} Hz  "
              f"(ecart {r['hz_ecart']:.1f})  "
              f"{r['trames_voisees']}/{r['trames']} trames voisees "
              f"({r['part_voisee'] * 100:.0f} %)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
