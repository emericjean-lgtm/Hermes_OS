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

#: Alias : `animer` prend un parametre nomme `duree_s`, qui masquerait la
#: fonction dans son corps. Le renommer ici plutot que la, pour que la
#: signature reste lisible cote appelant.
duree_s_de = duree_s

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
    #: Un lit sonore a bien été mixé sous la voix (HOS-211). Faux quand il
    #: était demandé mais introuvable — un `avertissement` le dit alors.
    ambiance: bool = False
    #: La taille de sortie, quand elle diffère de celle des plans.
    echelle: tuple[int, int] | None = None
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
    ambiance: Optional[str] = None,
    volume_ambiance: float = 0.18,
    echelle: Optional[tuple[int, int]] = None,
) -> Montage:
    """Enchaîner les plans, poser la voix, incruster le texte, vérifier.

    Un seul passage ffmpeg : concaténer puis ré-encoder deux fois abîme
    l'image sans rien apporter. Le filtre `concat` accepte des plans de
    formats différents à condition qu'ils partagent leur résolution, ce
    que garantit un même graphe de rendu.

    `ambiance` est un lit sonore mixé **sous** la voix (HOS-211). Il est
    bouclé et coupé sur la durée de l'image, jamais l'inverse : une
    ambiance plus courte que la vidéo laisserait un silence, et une plus
    longue allongerait le montage d'un écran noir. La voix reste à plein
    niveau — `volume_ambiance` n'agit que sur le lit.

    `echelle` agrandit à la sortie, en lanczos et en un seul passage. Ce
    n'est **pas** un upscale : 704 × 1280 vers 1080 × 1920 est un facteur
    1,53 sans information nouvelle. C'est ce que demandent les plateformes,
    qui ré-encodent de toute façon ; l'appeler autrement serait mentir sur
    ce qu'on livre.
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

    if ambiance and not os.path.isfile(ambiance):
        m.avertissements.append(f"ambiance introuvable : {ambiance}")
        ambiance = None

    entrees: list[str] = []
    for p in existants:
        entrees += ["-i", p]
    n = len(existants)
    i_narration = i_ambiance = -1
    if narration:
        i_narration = n + len(entrees) * 0  # posé juste après les plans
        i_narration = n
        entrees += ["-i", narration]
    if ambiance:
        i_ambiance = n + (1 if narration else 0)
        # `-stream_loop -1` : l'ambiance tourne en boucle et c'est le
        # `-shortest` de l'image qui la coupe. Sans la boucle, un lit plus
        # court que la vidéo laisserait un silence à la fin — que rien
        # dans la durée du fichier ne signalerait.
        entrees += ["-stream_loop", "-1", "-i", ambiance]

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

    if echelle:
        # Après les sous-titres : les incruster puis agrandir les rendrait
        # flous, alors que les poser sur l'image agrandie les garde nets.
        filtre += (f";{sortie_v}scale={int(echelle[0])}:{int(echelle[1])}"
                   f":flags=lanczos[vf]")
        sortie_v = "[vf]"
        m.echelle = (int(echelle[0]), int(echelle[1]))

    piste_audio: Optional[str] = None
    if narration and ambiance:
        # `duration=first` : la voix commande la durée du mix, l'ambiance
        # n'a pas à la prolonger. `dropout_transition=0` évite la remontée
        # de gain automatique d'`amix`, qui ferait respirer le lit à
        # chaque silence de la narration.
        filtre += (f";[{i_ambiance}:a:0]volume={volume_ambiance:.3f}[amb];"
                   f"[{i_narration}:a:0][amb]amix=inputs=2:duration=first"
                   f":dropout_transition=0[a]")
        piste_audio = "[a]"
        m.ambiance = True
    elif narration:
        piste_audio = f"{i_narration}:a:0"
    elif ambiance:
        filtre += f";[{i_ambiance}:a:0]volume={volume_ambiance:.3f}[a]"
        piste_audio = "[a]"
        m.ambiance = True

    if piste_audio:
        # `-shortest` seul ne fait la moitié du travail : il coupe bien une
        # narration trop longue, mais il coupe aussi **l'image** quand la
        # voix est plus courte. Mesuré : trois plans de 6,0 s avec une voix
        # de 5,4 s rendaient une vidéo de 5,4 s — les six dernières
        # dixièmes de seconde d'image simplement absentes.
        #
        # `apad` complète l'audio de silence, `-shortest` coupe alors sur
        # l'image. C'est ainsi que « l'image commande » devient vrai dans
        # les deux sens.
        source_audio = (piste_audio if piste_audio.startswith("[")
                        else f"[{piste_audio}]")
        filtre += f";{source_audio}apad[ap]"
        piste_audio = "[ap]"

    args = [*entrees, "-filter_complex", filtre, "-map", sortie_v]
    if piste_audio:
        args += ["-map", piste_audio, "-c:a", "aac", "-b:a", "192k",
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


# ── L'image fixe qui devient un plan (HOS-211) ────────────────────────

#: Amplitude du zoom sur toute la durée d'un plan animé. 6 % : au-delà,
#: le mouvement se voit comme un effet ; en deçà, il ne se voit pas du
#: tout et l'image paraît figée entre deux plans qui bougent.
ZOOM_PAR_DEFAUT = 1.06

#: Le facteur d'agrandissement appliqué **avant** le zoom. `zoompan`
#: calcule sa fenêtre en entiers : sur l'image à sa taille finale, le
#: cadre saute d'un pixel entier d'une image à l'autre, ce qui produit
#: une saccade parfaitement visible. Agrandir d'abord rend ce pas huit
#: fois plus fin, et le mouvement redevient continu.
FINESSE = 8


def animer(image: str, sortie: str, *, duree_s: float = 4.0,
           largeur: int = 704, hauteur: int = 1280, fps: float = 24.0,
           zoom: float = ZOOM_PAR_DEFAUT,
           sens: str = "avant") -> Montage:
    """Faire un plan vidéo d'une image fixe, avec un mouvement lent.

    Quatre plans du cahier de production sont des images fixes qu'il faut
    faire respirer. Sans ça elles ne peuvent même pas entrer dans le
    montage : `concat` enchaîne des flux vidéo, et un PNG n'en est pas un.

    Le résultat est encodé exactement comme un plan LTX — même taille,
    même cadence, même profil — parce que `concat` exige que tous les
    plans partagent leur résolution, et qu'un plan qui diffère ferait
    échouer l'assemblage à la fin, après tout le reste.

    La durée est **vérifiée sur le fichier**, comme le montage : un
    `zoompan` dont le compte d'images est faux rend une vidéo plus courte
    avec le code 0, et le manque ne se verrait qu'au visionnage.
    """
    m = Montage(chemin=sortie, plans=1)
    if not os.path.isfile(image):
        m.erreur = f"image introuvable : {image}"
        return m

    ff = ffmpeg()
    if not ff:
        m.erreur = "ffmpeg introuvable"
        return m

    images = max(1, int(round(float(duree_s) * float(fps))))
    m.duree_attendue_s = round(images / float(fps), 3)

    # `z` va de 1 à `zoom` sur la durée, ou l'inverse. `on` est l'index de
    # l'image courante : l'exprimer ainsi plutôt qu'en incréments évite la
    # dérive d'arrondi qui fait finir le zoom avant la fin du plan.
    if sens == "arriere":
        expr_z = f"{zoom}-({zoom}-1)*on/{max(1, images - 1)}"
    else:
        expr_z = f"1+({zoom}-1)*on/{max(1, images - 1)}"

    filtre = (
        f"scale={largeur * FINESSE}:{hauteur * FINESSE}:flags=lanczos,"
        f"zoompan=z='{expr_z}':d={images}"
        f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
        f":s={largeur}x{hauteur}:fps={fps},"
        f"format=yuv420p")

    args = ["-loop", "1", "-i", image, "-vf", filtre,
            "-frames:v", str(images), "-r", str(fps),
            "-c:v", "libx264", "-preset", "medium", "-crf", "18",
            "-pix_fmt", "yuv420p", sortie]

    os.makedirs(os.path.dirname(sortie) or ".", exist_ok=True)
    ok, detail = _monter(args, None)
    if not ok:
        m.erreur = detail
        return m

    if not os.path.exists(sortie) or not os.path.getsize(sortie):
        m.erreur = "ffmpeg a rendu 0 mais aucun fichier n'existe"
        return m
    m.duree_s = duree_s_de(sortie)
    if not m.duree_s:
        m.erreur = "durée illisible — rien ne prouve que le plan est bon"
        return m
    if not m.duree_conforme:
        m.erreur = (f"le plan animé dure {m.duree_s:.2f} s pour "
                    f"{m.duree_attendue_s:.2f} s demandées")
        return m

    m.reussi = True
    return m


# ── La voix, recollée avec ses respirations (HOS-211) ─────────────────

#: Une pause de narration par défaut. Mesurée à l'oreille sur la voix
#: Michael : en deçà, la phrase suivante s'enchaîne comme une lecture ;
#: au-delà, le silence devient un trou.
PAUSE_PAR_DEFAUT_S = 0.55


def coller_voix(segments: list[str], sortie: str, *,
                pauses_s: Optional[list[float]] = None,
                pause_par_defaut_s: float = PAUSE_PAR_DEFAUT_S) -> Montage:
    """Enchaîner des répliques en une narration, avec des silences entre.

    `synthetiser` rend un fichier par réplique. Une narration continue
    demande de les recoller — et c'est le seul endroit où les respirations
    d'un texte peuvent exister : Chatterbox ne les produit pas, il lit ce
    qu'on lui donne.

    `pauses_s[i]` est le silence **après** la réplique `i`. Une liste plus
    courte est complétée au défaut ; la dernière valeur est ignorée, une
    narration ne se termine pas sur un silence.

    La durée obtenue est vérifiée contre la somme attendue : un `concat`
    audio dont une entrée manque rend un fichier plus court avec le code 0,
    et il faudrait écouter jusqu'au bout pour s'en apercevoir.
    """
    m = Montage(chemin=sortie, plans=len(segments))
    manquants = [s for s in segments if not os.path.isfile(s)]
    if manquants:
        m.erreur = (f"{len(manquants)} réplique(s) introuvable(s) — rien "
                    "n'est collé plutôt qu'une narration amputée")
        return m
    if not segments:
        m.erreur = "aucune réplique à coller"
        return m

    ff = ffmpeg()
    if not ff:
        m.erreur = "ffmpeg introuvable"
        return m

    pauses = list(pauses_s or [])
    pauses += [pause_par_defaut_s] * max(0, len(segments) - 1 - len(pauses))
    pauses = pauses[:max(0, len(segments) - 1)]

    attendue = sum(duree_s_de(s) for s in segments) + sum(pauses)
    if not attendue:
        m.erreur = "durée des répliques illisible — le collage ne serait pas vérifiable"
        return m
    m.duree_attendue_s = round(attendue, 3)

    entrees: list[str] = []
    for chemin in segments:
        entrees += ["-i", chemin]
    # Les silences sont des entrées `lavfi` à part entière, et non un
    # `apad` : `apad` allonge la dernière réplique et le décalage
    # s'accumulerait sans qu'aucune durée ne le dise.
    indices: list[str] = []
    n_silences = 0
    for i in range(len(segments)):
        indices.append(f"[{i}:a:0]")
        if i < len(pauses):
            entrees += ["-f", "lavfi", "-t", f"{pauses[i]:.3f}",
                        "-i", "anullsrc=channel_layout=mono:sample_rate=24000"]
            indices.append(f"[{len(segments) + n_silences}:a:0]")
            n_silences += 1

    filtre = "".join(indices) + f"concat=n={len(indices)}:v=0:a=1[a]"
    args = [*entrees, "-filter_complex", filtre, "-map", "[a]",
            "-c:a", "pcm_s16le", "-ar", "24000", "-ac", "1", sortie]

    os.makedirs(os.path.dirname(sortie) or ".", exist_ok=True)
    ok, detail = _monter(args, None)
    if not ok:
        m.erreur = detail
        return m

    if not os.path.exists(sortie) or not os.path.getsize(sortie):
        m.erreur = "ffmpeg a rendu 0 mais aucun fichier n'existe"
        return m
    m.duree_s = duree_s_de(sortie)
    if not m.duree_s:
        m.erreur = "durée du collage illisible"
        return m
    if not m.duree_conforme:
        m.erreur = (f"la narration collée dure {m.duree_s:.2f} s pour "
                    f"{m.duree_attendue_s:.2f} s attendues")
        return m

    m.reussi = True
    return m
