"""Assembler des plans retenus en une vidéo finie (HOS-191).

## Ce que ce module fait, et ce qu'il refuse de faire

Il enchaîne des plans, pose une narration, incruste des sous-titres, et
**vérifie le fichier obtenu**. Il ne choisit pas l'ordre des plans, n'écrit
pas le texte et ne décide pas du rythme : cela vient de l'appelant, comme
les graphes viennent de l'appelant dans `comfyui.py`. La règle qui prime
sur tout dans ce dépôt réserve ces décisions à Hermes Agent.

## Pourquoi la vérification n'est pas facultative

`ffmpeg` sort avec le code 0 dans des cas où le résultat n'est pas ce qu'on
croit : une liste de concaténation dont un fichier manque produit un
fichier plus court, sans erreur. Un filtre de sous-titres dont la police
est introuvable rend une vidéo **sans sous-titres**, sans erreur non plus.

On relit donc la durée du fichier produit et on la compare à la somme des
plans. C'est la transposition directe de la règle centrale : `exit 0`
n'est pas une preuve.

## Le décalage entre l'image et la voix

Une narration plus longue que les plans est le cas normal — on écrit le
texte avant de savoir combien de plans on gardera. Ce module ne l'étire
pas et ne le coupe pas en silence : il **le rapporte**. Étirer changerait
la voix, couper perdrait la fin, et les deux se découvriraient au
visionnage.
"""

from __future__ import annotations

import logging
import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from typing import Optional

from backend.studio.relecteur import duree_s, ffmpeg

logger = logging.getLogger("hermes_os.studio.montage")

#: Au-delà, l'écart entre l'image et la voix s'entend. En deçà, il tient
#: au fait qu'un plan dure un nombre entier d'images et pas la narration.
TOLERANCE_S = 0.5


@dataclass
class Montage:
    """Le fichier produit, et ce qu'on a pu en vérifier."""

    chemin: str = ""
    reussi: bool = False
    duree_s: float = 0.0
    duree_attendue_s: float = 0.0
    duree_narration_s: float = 0.0
    plans: int = 0
    sous_titres: bool = False
    #: Écart entre la narration et l'image. Positif : la voix déborde.
    ecart_voix_s: float = 0.0
    avertissements: list[str] = field(default_factory=list)
    erreur: str = ""

    @property
    def duree_conforme(self) -> bool:
        """La vidéo dure-t-elle ce que les plans annonçaient ?

        Faux aussi quand la durée n'a pas pu être lue : affirmer la
        conformité sans l'avoir mesurée serait le succès sur parole que
        ce module existe pour empêcher.
        """
        if not self.duree_s or not self.duree_attendue_s:
            return False
        return abs(self.duree_s - self.duree_attendue_s) <= TOLERANCE_S


def libass_disponible() -> bool:
    """ffmpeg sait-il incruster des sous-titres ?

    Le filtre `subtitles` **est** libass : sans lui, ffmpeg refuse le
    graphe et le code de retour le dit. C'est donc une précondition qui
    se vérifie, là où l'absence de polices, elle, produirait une vidéo
    sans texte avec le code 0 — le cas qu'aucun appel ne rapporte.

    Vérifié sur cette machine le 2026-08-27 : la build Gyan porte
    `--enable-libass`, `--enable-fontconfig` et `--enable-libfreetype`, et
    l'incrustation a été constatée en comparant l'empreinte d'une image du
    montage à la même image du montage sans sous-titres.
    """
    binaire = ffmpeg()
    if not binaire:
        return False
    try:
        sortie = subprocess.run([binaire, "-hide_banner", "-filters"],
                                capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return False
    return any(ligne.split()[1:2] == ["subtitles"]
               for ligne in (sortie.stdout or "").splitlines()
               if len(ligne.split()) > 1)


def ecrire_srt(segments: list[dict], chemin: str) -> int:
    """Écrire un SRT, et rendre le nombre de sous-titres écrits.

    Chaque segment porte `debut`, `fin`, `texte`. Les segments dont la fin
    précède le début sont écartés : `ffmpeg` accepte un SRT incohérent et
    affiche alors des sous-titres qui ne disparaissent jamais.
    """
    lignes: list[str] = []
    rang = 0
    for s in segments:
        debut, fin = float(s.get("debut", 0)), float(s.get("fin", 0))
        texte = str(s.get("texte") or "").strip()
        if fin <= debut or not texte:
            continue
        rang += 1
        lignes.append(f"{rang}\n{_horodatage(debut)} --> {_horodatage(fin)}\n"
                      f"{texte}\n")

    os.makedirs(os.path.dirname(chemin) or ".", exist_ok=True)
    with open(chemin, "w", encoding="utf-8") as f:
        f.write("\n".join(lignes))
    return rang


def _horodatage(secondes: float) -> str:
    """`HH:MM:SS,mmm` — la virgule est celle du format SRT, pas un point."""
    ms = int(round(max(0.0, secondes) * 1000))
    h, reste = divmod(ms, 3_600_000)
    m, reste = divmod(reste, 60_000)
    s, ms = divmod(reste, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def assembler(
    plans: list[str],
    sortie: str,
    *,
    narration: Optional[str] = None,
    srt: Optional[str] = None,
    fps: float = 24.0,
) -> Montage:
    """Enchaîner les plans, poser la voix, incruster le texte, vérifier.

    Un seul passage ffmpeg : concaténer puis ré-encoder deux fois abîme
    l'image sans rien apporter. Le filtre `concat` accepte des plans de
    formats différents à condition qu'ils partagent leur résolution, ce
    que garantit un même graphe de rendu.
    """
    m = Montage(chemin=sortie, plans=len(plans))

    existants = [p for p in plans if os.path.exists(p)]
    if len(existants) != len(plans):
        # Ne pas assembler ce qui reste : la vidéo sortirait plus courte,
        # avec le code 0, et l'absence se verrait au visionnage.
        m.erreur = (f"{len(plans) - len(existants)} plan(s) introuvable(s) "
                    "— rien n'est assemblé plutôt qu'un montage amputé")
        return m
    if not existants:
        m.erreur = "aucun plan à assembler"
        return m

    m.duree_attendue_s = round(sum(duree_s(p) for p in existants), 3)
    if not m.duree_attendue_s:
        m.erreur = "durée des plans illisible — l'assemblage ne serait pas vérifiable"
        return m

    if narration:
        m.duree_narration_s = duree_s(narration)
        m.ecart_voix_s = round(m.duree_narration_s - m.duree_attendue_s, 2)
        if abs(m.ecart_voix_s) > TOLERANCE_S:
            # Rapporté, jamais corrigé en silence : étirer changerait la
            # voix, couper perdrait la fin, et l'appelant est le seul à
            # savoir lequel des deux il préfère.
            m.avertissements.append(
                f"la narration dure {m.duree_narration_s:.1f} s pour "
                f"{m.duree_attendue_s:.1f} s d'image "
                f"({m.ecart_voix_s:+.1f} s)")

    entrees: list[str] = []
    for p in existants:
        entrees += ["-i", p]
    if narration:
        entrees += ["-i", narration]

    n = len(existants)
    chaine = "".join(f"[{i}:v:0]" for i in range(n))
    filtre = f"{chaine}concat=n={n}:v=1:a=0[v]"

    nettoyer: list[str] = []
    if srt and not os.path.exists(srt):
        m.avertissements.append(f"sous-titres demandés mais introuvables : {srt}")
    elif srt and not libass_disponible():
        # Le cas silencieux que ce module doit intercepter : sans libass,
        # `subtitles` n'existe pas et ffmpeg refuse le graphe ; mais une
        # version qui l'a sans polices rendrait la vidéo **sans texte**,
        # code 0 et durée juste. Refuser d'annoncer des sous-titres qu'on
        # n'a pas pu produire vaut mieux que de les promettre.
        m.avertissements.append(
            "ffmpeg n'a pas libass : la vidéo sortira sans sous-titres")
        srt = None
    if srt and os.path.exists(srt):
        # `subtitles` veut un chemin échappé à sa façon : deux-points et
        # antislashs sont des séparateurs de filtre. Copier le SRT à côté
        # du travail et n'en donner que le nom évite toute cette syntaxe.
        dossier = tempfile.mkdtemp(prefix="hermes_montage_")
        local = os.path.join(dossier, "st.srt")
        with open(srt, encoding="utf-8") as src, \
                open(local, "w", encoding="utf-8") as dst:
            dst.write(src.read())
        nettoyer.append(dossier)
        filtre += ";[v]subtitles=st.srt[vs]"
        sortie_v = "[vs]"
        m.sous_titres = True
    else:
        sortie_v = "[v]"

    args = [*entrees, "-filter_complex", filtre, "-map", sortie_v]
    if narration:
        args += ["-map", f"{n}:a:0", "-c:a", "aac", "-b:a", "192k",
                 # L'image commande. Sans cela une narration plus longue
                 # allongerait la vidéo d'un écran noir.
                 "-shortest"]
    args += ["-r", str(fps), "-c:v", "libx264", "-preset", "medium",
             "-crf", "18", "-pix_fmt", "yuv420p", sortie]

    os.makedirs(os.path.dirname(sortie) or ".", exist_ok=True)
    # `cwd` sur le dossier du SRT : c'est ce qui permet de n'en donner que
    # le nom au filtre.
    ok, detail = _monter(args, nettoyer[0] if nettoyer else None)
    if not ok:
        m.erreur = detail
        return m

    # ── La vérification, qui est le point de ce module ────────────────
    if not os.path.exists(sortie) or os.path.getsize(sortie) == 0:
        m.erreur = "ffmpeg a rendu 0 mais aucun fichier n'existe"
        return m

    m.duree_s = duree_s(sortie)
    if not m.duree_s:
        m.erreur = "durée du montage illisible — rien ne prouve qu'il est bon"
        return m
    if not m.duree_conforme:
        m.erreur = (f"le montage dure {m.duree_s:.2f} s pour "
                    f"{m.duree_attendue_s:.2f} s de plans")
        return m

    m.reussi = True
    return m


def _monter(args: list[str], dossier: Optional[str]) -> tuple[bool, str]:
    binaire = ffmpeg()
    if not binaire:
        return False, "ffmpeg introuvable"
    try:
        r = subprocess.run([binaire, "-y", "-loglevel", "error", *args],
                           capture_output=True, text=True, timeout=3600,
                           cwd=dossier)
    except (OSError, subprocess.SubprocessError) as e:
        return False, f"{type(e).__name__}: {str(e)[:200]}"
    if r.returncode != 0:
        return False, (r.stderr or "").strip()[:400]
    return True, ""


def transcrire_en_segments(audio: str, langue: str = "fr",
                           modele: str = "small") -> list[dict]:
    """Les segments d'une narration, avec leurs bornes.

    `faster-whisper` rend nativement des bornes par mot ; mesuré sur cette
    machine le 2026-08-27, trente et un mots sans un seul recul, sans
    durée nulle et sans dépassement, à 4,2 fois le temps réel sur CPU.
    Une bibliothèque d'alignement supplémentaire n'apporterait rien ici.
    """
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        logger.debug("faster-whisper absent", exc_info=True)
        return []

    if not os.path.exists(audio):
        return []

    try:
        m = WhisperModel(modele, device="cpu", compute_type="int8")
        segments, _ = m.transcribe(audio, language=langue,
                                   word_timestamps=True)
        return [{"debut": float(s.start), "fin": float(s.end),
                 "texte": s.text.strip()} for s in segments]
    except Exception:
        logger.debug("transcription impossible", exc_info=True)
        return []


def sonde() -> dict[str, object]:
    """De quoi le montage dispose réellement sur cette machine.

    Existe pour que l'écran puisse dire « ffmpeg manque » plutôt que de
    laisser un montage échouer sans explication au bout d'une nuit.
    """
    binaire = ffmpeg()
    sortie: dict[str, object] = {"ffmpeg": binaire or ""}
    if binaire:
        sonde_p = binaire.replace("ffmpeg.exe", "ffprobe.exe").replace(
            "ffmpeg.EXE", "ffprobe.exe")
        sortie["ffprobe"] = sonde_p if os.path.exists(sonde_p) else ""
    sortie["libass"] = libass_disponible()
    try:
        import faster_whisper  # noqa: F401
        sortie["transcription"] = True
    except ImportError:
        sortie["transcription"] = False
    return sortie


__all__ = ["Montage", "assembler", "ecrire_srt", "libass_disponible", "sonde",
           "transcrire_en_segments", "TOLERANCE_S"]
