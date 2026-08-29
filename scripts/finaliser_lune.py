"""Terminer la production « Lune » sans reveiller personne (HOS-212).

Reprend la ou l'etat reel du disque le permet, et va jusqu'au fichier
final. Ce script est ecrit pour tourner seul plusieurs heures : chaque
etape verifie ce que la precedente a **reellement** produit, jamais ce
qu'elle a annonce.

## Ce qu'il refuse de faire

**Assembler ce qui manque.** Dix plans dont trois sont absents produisent
une video plus courte, avec le code 0. Le montage s'arrete et nomme les
absents.

**Relancer un plan rate.** Refaire une nuit entiere pour un defaut qu'un
œil regle en une minute est le mauvais echange. Les plans manquants sont
rapportes, pas refaits.

**Conclure que c'est bon.** Le rapport dit ce qui a ete mesure et ce qui
ne l'a pas ete. Le verdict de publication appartient a qui regarde.

## Ce qu'il surveille

Un decodage qui deborde ne leve pas d'erreur : il bascule sur la memoire
partagee et rampe — 38,5 s de processeur en 20 s, mesure cette nuit sur
un plan qui a tenu 39 minutes pour 22 attendues. La file coupe a 40 min
et marque le plan en echec ; le rapport le distingue d'un vrai
debordement, parce que ce n'est pas la meme chose.
"""

from __future__ import annotations

import json
import os
import sys
import time
from typing import Any

ICI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ICI)
sys.path.insert(0, os.path.dirname(ICI))

import production_lune as P  # noqa: E402

API = "http://127.0.0.1:8010/api/v1"
SORTIE = r"E:\YouTube\Generations\lune_v4"
NARRATION = r"E:\YouTube\Generations\lune\narration_v3.wav"
RAPPORT = os.path.join(SORTIE, "rapport_production.json")

#: Les plans deja rendus et valides a l'œil avant ce script. On ne les
#: refait pas : ref01 a demande quatre tentatives.
DEJA = {"ref01": os.path.join(SORTIE, "ref01_00001_.png")}

#: L'ordre dans lequel le reste doit passer. `p02a` ne peut pas declarer
#: `depend_de="p01"` puisque p01 n'est pas dans cette file — son image de
#: depart est posee explicitement.
RESTE = ["p02a", "p02b", "img03", "ref04", "p04a", "p04b",
         "img05", "ref06", "p06", "img07", "img08"]


def _appel(chemin: str, corps: dict | None = None, *,
           minutes: float = 5.0) -> dict:
    import urllib.request

    donnees = json.dumps(corps).encode("utf-8") if corps is not None else None
    requete = urllib.request.Request(
        API + chemin, data=donnees,
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(requete, timeout=minutes * 60) as r:
        return json.loads(r.read().decode("utf-8"))


def _dire(*mots: Any) -> None:
    print(time.strftime("[%H:%M:%S]"), *mots, flush=True)


def _rendu(identifiant: str) -> str | None:
    """Le fichier produit pour ce plan, **sur le disque**."""
    import glob

    for motif in (f"{identifiant}_*.mp4", f"{identifiant}_*.png"):
        trouves = sorted(glob.glob(os.path.join(SORTIE, motif)))
        if trouves:
            return trouves[-1]
    return None


# ── 1. Attendre p01, qui tourne deja ─────────────────────────────────

def attendre_p01(minutes_max: float = 45.0) -> str | None:
    """Attendre que la file **se termine**, pas que le fichier apparaisse.

    Le MP4 est ecrit avant la relecture : le voir sur le disque ne dit
    donc pas que la file a fini. Guette sur le fichier, ce script a
    enchaine trop tot et la file suivante a ete refusee — « une file de
    nuit tourne deja » — ce qui a coute toute la production.
    """
    limite = time.time() + minutes_max * 60
    while time.time() < limite:
        etat = _appel("/studio/night")
        if not etat.get("en_cours"):
            f = _rendu("p01")
            if f:
                _dire(f"p01 rendu : {os.path.basename(f)} "
                      f"({os.path.getsize(f)} octets)")
            else:
                _dire("la file s'est arretee sans produire p01")
            return f
        time.sleep(45)
    _dire(f"p01 n'a pas abouti en {minutes_max:.0f} min")
    return None


# ── 2. Le reste de la production ─────────────────────────────────────

def lancer_le_reste(p01: str | None) -> bool:
    par_nom = {p["identifiant"]: p for p in P.PLANS}
    plans: list[dict] = []

    for nom in RESTE:
        p = dict(par_nom[nom])
        p["parametres"] = dict(p["parametres"], prefixe=f"lune_v4/{nom}")

        if nom == "p02a":
            if not p01:
                _dire("p02a et p02b sautes : p01 manque")
                continue
            # L'image de depart est posee explicitement : p01 n'est pas
            # dans cette file, donc `depend_de` ne pourrait pas le voir.
            r = _appel("/studio/start-frame",
                       {"source": p01, "nom": "depart_p02a_v4"})
            if not r.get("success"):
                _dire(f"depart de p02a impossible : {r.get('error')}")
                continue
            p.pop("depend_de", None)
            p["parametres"]["image_depart"] = r["nom"]
            _dire(f"p02a repartira de {r['nom']}")

        plans.append(p)

    if not plans:
        _dire("aucun plan a lancer")
        return False

    # 40 min : au-dela, un plan ne rame pas, il est en panne. Mesure
    # 22 min pour ce format ; le double laisse de la marge sans laisser
    # la nuit se perdre sur un seul plan.
    r = _appel("/studio/night", {"plans": plans, "minutes_par_plan": 40.0})
    if not r.get("success"):
        _dire(f"la file n'a pas demarre : {r}")
        return False
    _dire(f"file lancee : {r['plans']} plans")
    return True


def attendre_la_file(depuis: float, attendu: int,
                     periode_s: float = 90.0) -> dict:
    dernier = -1
    while True:
        etat = _appel("/studio/night")
        rapport = etat.get("rapport") or {}
        # Un journal anterieur au lancement est celui de la file d'avant :
        # le lire donnerait un compte qui n'a rien a voir.
        if float(rapport.get("debut") or 0) < depuis - 5:
            rapport = {}
        plans = rapport.get("plans") or []
        faits = [p for p in plans if p.get("etat") != "en_attente"]
        if len(faits) != dernier:
            dernier = len(faits)
            dernier_nom = faits[-1] if faits else None
            suffixe = (f" — {dernier_nom['identifiant']} "
                       f"{dernier_nom['etat']}") if dernier_nom else ""
            _dire(f"file : {len(faits)}/{attendu}{suffixe}")
        if not etat.get("en_cours"):
            return rapport
        time.sleep(periode_s)


# ── 3. Les images fixes deviennent des plans ─────────────────────────

def animer_les_fixes() -> dict[str, str]:
    clips: dict[str, str] = {}
    for etape in P.MONTAGE:
        if etape["source"] != "anime":
            continue
        nom = etape["plan"]
        source = _rendu(nom)
        if not source:
            _dire(f"  {nom} : aucune image rendue")
            continue
        cible = os.path.join(SORTIE, f"{nom}_anime.mp4")
        r = _appel("/studio/animate", {
            "image": source, "sortie": cible, "duree_s": etape["duree_s"],
            "sens": etape.get("sens", "avant"), "format": P.FORMAT_VIDEO,
        }, minutes=15.0)
        if r.get("success"):
            clips[nom] = cible
            _dire(f"  {nom} anime : {r['duree_s']} s")
        else:
            _dire(f"  {nom} : {r.get('error')}")
    return clips


# ── 4. Sous-titres et montage ────────────────────────────────────────

def sous_titrer() -> str | None:
    from backend.studio.montage import ecrire_srt, transcrire_en_segments

    if not os.path.isfile(NARRATION):
        return None
    segments = transcrire_en_segments(NARRATION, langue="fr")
    if not segments:
        _dire("transcription indisponible — pas de sous-titres")
        return None
    srt = os.path.join(SORTIE, "sous_titres.srt")
    n = ecrire_srt(segments, srt)
    _dire(f"sous-titres : {n} segments")
    return srt if n else None


#: Au-dela, l'ecart entre la voix et l'image n'est plus un decalage a
#: rapporter : c'est la preuve que le montage n'est pas celui qu'on
#: croyait. Mesure une fois a +31,7 s — une narration de 35,7 s posee sur
#: 4,0 s d'image, parce qu'un seul plan sur dix avait ete assemble.
ECART_VOIX_MAX_S = 6.0


def monter(clips: dict[str, str], srt: str | None) -> dict:
    ordre = [clips[e["plan"]] for e in P.MONTAGE if e["plan"] in clips]
    absents = [e["plan"] for e in P.MONTAGE if e["plan"] not in clips]
    if not ordre:
        return {"success": False, "error": "aucun plan a assembler"}
    if absents:
        # `assembler` verifie que le montage dure ce que les plans qu'on
        # lui donne annoncaient — il n'a aucun moyen de savoir combien on
        # aurait DU lui en donner. Il a donc rendu `success: true` sur une
        # video de 4 s faite d'un plan sur dix. C'est ici que ca se
        # refuse : le montage amputé ressemble trop a un livrable.
        _dire(f"MONTAGE REFUSE — {len(absents)} plan(s) manquant(s) : {absents}")
        return {"success": False, "raison": "production_incomplete",
                "error": (f"{len(absents)} plan(s) sur {len(P.MONTAGE)} "
                          f"manquent : {', '.join(absents)}"),
                "absents": absents}

    return _appel("/studio/assemble", {
        "plans": ordre,
        "sortie": os.path.join(SORTIE, "lune_v1.mp4"),
        **({"narration": NARRATION} if os.path.isfile(NARRATION) else {}),
        **({"srt": srt} if srt else {}),
        # 1080 x 1920 : un agrandissement lanczos, pas un upscale.
        "echelle": [1080, 1920],
    }, minutes=45.0)


def main() -> int:
    os.makedirs(SORTIE, exist_ok=True)
    debut = time.time()

    p01 = attendre_p01()
    depart = time.time()
    if not lancer_le_reste(p01):
        rapport_file = {}
    else:
        attendu = len([n for n in RESTE
                       if p01 or n not in ("p02a", "p02b")])
        rapport_file = attendre_la_file(depart, attendu)

    _dire("rendus terminés")
    clips: dict[str, str] = {}
    for e in P.MONTAGE:
        if e["source"] == "ltx":
            f = _rendu(e["plan"])
            if f:
                clips[e["plan"]] = f
    clips.update(animer_les_fixes())

    srt = sous_titrer()
    montage = monter(clips, srt)
    ecart = abs(float(montage.get("ecart_voix_s") or 0))
    if montage.get("success") and ecart > ECART_VOIX_MAX_S:
        montage["success"] = False
        montage["raison"] = "ecart_voix"
        montage["error"] = (f"la voix et l'image different de {ecart:.1f} s — "
                            "au-dela de quelques secondes, ce n'est plus un "
                            "decalage mais un montage qui n'est pas celui "
                            "qu'on croit")
        _dire(f"MONTAGE REFUSE — {montage['error']}")
    _dire("montage : " + json.dumps(montage, ensure_ascii=False)[:400])

    rapport = {
        "debut": debut, "duree_s": round(time.time() - debut, 1),
        "p01": p01, "file": rapport_file, "clips": clips,
        "narration": NARRATION if os.path.isfile(NARRATION) else None,
        "sous_titres": srt, "montage": montage,
    }
    with open(RAPPORT, "w", encoding="utf-8") as f:
        json.dump(rapport, f, indent=1, ensure_ascii=False)
    _dire(f"rapport écrit : {RAPPORT}")
    return 0 if montage.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
