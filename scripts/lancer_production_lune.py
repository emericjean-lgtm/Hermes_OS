"""Dérouler la production « Lune » de bout en bout (HOS-211).

Rend la main seulement quand il y a un fichier à regarder, ou une raison
de ne pas en avoir. Trois étapes, dans cet ordre, parce que chacune a
besoin du résultat réel de la précédente :

1. la nuit — treize plans, dont six vidéos LTX enchaînées ;
2. l'animation des images fixes, en clips au format des autres ;
3. la narration, les sous-titres, le montage.

## Ce qu'il refuse de faire

**Assembler ce qui n'a pas été rendu.** Dix plans dont trois manquent
produisent une vidéo plus courte, avec le code 0. Le montage s'arrête et
nomme ce qui manque — c'est déjà la règle de `montage.assembler`, on ne la
contourne pas ici.

**Relancer un plan raté.** Le cahier des charges le demande
explicitement, et c'est juste : refaire une nuit entière pour un défaut
qu'un œil réglerait en une minute est le mauvais échange.

**Décider que c'est bon.** Le rapport dit ce qui a été mesuré et ce qui ne
l'a pas été. Le verdict de publication appartient à qui regarde.
"""

from __future__ import annotations

import json
import os
import sys
import time
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import production_lune as P  # noqa: E402

API = "http://127.0.0.1:8010/api/v1"
SORTIE = r"E:\YouTube\Generations\lune"
RAPPORT = os.path.join(SORTIE, "rapport_production.json")

#: Le silence après chaque réplique. Ajusté après mesure de la voix : la
#: narration lue d'affilée dure environ 25 s pour 38 s d'image, et ces
#: respirations sont ce qui rapproche les deux — en même temps qu'elles
#: sont ce que le cahier des charges demande pour le ton.
PAUSES_S = [1.6, 1.9, 1.5, 1.4, 1.6, 1.5]


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


# ── 1. La nuit ────────────────────────────────────────────────────────

def lancer_la_nuit() -> dict:
    reponse = _appel("/studio/night", {
        "plans": P.PLANS,
        # 45 min : un plan qui dépasse ça ne rampe pas, il est en panne.
        # Mesuré 20 min pour ce format ; le double laisse de la marge sans
        # laisser une nuit se perdre sur un seul plan.
        "minutes_par_plan": 45.0,
    })
    if not reponse.get("success"):
        raise SystemExit(f"la nuit n'a pas démarré : {reponse}")
    _dire(f"nuit lancée — {reponse['plans']} plans, journal {reponse['journal']}")
    return reponse


def attendre_la_nuit(periode_s: float = 60.0) -> dict:
    """Suivre le journal, pas une variable en mémoire.

    Le journal est écrit après chaque plan et survit à un redémarrage du
    backend. C'est la seule source qui reste vraie dans tous les cas.
    """
    dernier = -1
    while True:
        etat = _appel("/studio/night")
        plans = etat.get("plans") or []
        finis = sum(1 for p in plans
                    if p.get("etat") not in ("en_attente",))
        if finis != dernier:
            _dire(f"nuit : {finis}/{len(plans)} plans traités")
            dernier = finis
        if not etat.get("en_cours") and finis and finis >= len(plans):
            return etat
        if not etat.get("en_cours") and dernier >= 0 and finis == dernier:
            # Le fil est mort sans avoir tout traité : ne pas boucler
            # indéfiniment sur un journal qui ne bougera plus.
            if finis >= len(plans):
                return etat
            _dire("le fil de nuit s'est arrêté avant la fin")
            return etat
        time.sleep(periode_s)


# ── 2. Les images fixes deviennent des plans ──────────────────────────

def animer_les_fixes(rendus: dict[str, list[str]]) -> dict[str, str]:
    clips: dict[str, str] = {}
    for etape in P.MONTAGE:
        if etape["source"] != "anime":
            continue
        nom = etape["plan"]
        fichiers = rendus.get(nom) or []
        if not fichiers:
            _dire(f"  {nom} : aucune image rendue — plan absent du montage")
            continue
        cible = os.path.join(SORTIE, f"{nom}_anime.mp4")
        r = _appel("/studio/animate", {
            "image": fichiers[-1], "sortie": cible,
            "duree_s": etape["duree_s"], "sens": etape.get("sens", "avant"),
            "format": P.FORMAT_VIDEO,
        }, minutes=10.0)
        if r.get("success"):
            clips[nom] = cible
            _dire(f"  {nom} animé : {r['duree_s']} s")
        else:
            _dire(f"  {nom} : {r.get('error')}")
    return clips


# ── 3. La voix, les sous-titres, le montage ──────────────────────────

def narrer() -> str | None:
    from backend.studio.montage import coller_voix

    dossier = os.path.join(SORTIE, "voix")
    r = _appel("/studio/narrate", {
        "lignes": [{"id": i, "texte": t} for i, t in P.NARRATION],
        "dossier": dossier,
    }, minutes=30.0)
    if not r.get("success"):
        _dire(f"narration impossible : {r.get('error')}")
        return None

    segments = [s["chemin"] for s in r["segments"] if s.get("reussi")]
    if len(segments) != len(P.NARRATION):
        _dire(f"narration incomplète : {len(segments)}/{len(P.NARRATION)} "
              "répliques — elle n'est pas collée")
        return None

    voix = os.path.join(SORTIE, "narration.wav")
    m = coller_voix(segments, voix, pauses_s=PAUSES_S)
    if not m.reussi:
        _dire(f"collage impossible : {m.erreur}")
        return None
    _dire(f"narration : {m.duree_s} s, {len(segments)} répliques")
    return voix


def sous_titrer(voix: str) -> str | None:
    from backend.studio.montage import ecrire_srt, transcrire_en_segments

    segments = transcrire_en_segments(voix, langue="fr")
    if not segments:
        _dire("transcription indisponible — pas de sous-titres")
        return None
    srt = os.path.join(SORTIE, "sous_titres.srt")
    n = ecrire_srt(segments, srt)
    _dire(f"sous-titres : {n} segments")
    return srt if n else None


def monter(clips: dict[str, str], voix: str | None, srt: str | None) -> dict:
    ordre = [clips[e["plan"]] for e in P.MONTAGE if e["plan"] in clips]
    absents = [e["plan"] for e in P.MONTAGE if e["plan"] not in clips]
    if absents:
        _dire(f"plans absents du montage : {absents}")

    return _appel("/studio/assemble", {
        "plans": ordre,
        "sortie": os.path.join(SORTIE, "lune_v1.mp4"),
        **({"narration": voix} if voix else {}),
        **({"srt": srt} if srt else {}),
        # 1080 × 1920 : un agrandissement lanczos, pas un upscale. Les
        # plateformes ré-encodent de toute façon.
        "echelle": [1080, 1920],
    }, minutes=30.0)


def main() -> int:
    os.makedirs(SORTIE, exist_ok=True)
    debut = time.time()

    lancer_la_nuit()
    etat = attendre_la_nuit()

    rendus = {p["identifiant"]: p.get("fichiers") or []
              for p in etat.get("plans", [])}
    _dire("nuit terminée : " + json.dumps(
        {p["identifiant"]: p.get("etat") for p in etat.get("plans", [])},
        ensure_ascii=False))

    clips = {e["plan"]: rendus[e["plan"]][-1]
             for e in P.MONTAGE
             if e["source"] == "ltx" and rendus.get(e["plan"])}
    clips.update(animer_les_fixes(rendus))

    voix = narrer()
    srt = sous_titrer(voix) if voix else None
    montage = monter(clips, voix, srt)
    _dire("montage : " + json.dumps(montage, ensure_ascii=False))

    rapport = {
        "debut": debut, "duree_s": round(time.time() - debut, 1),
        "nuit": etat, "clips": clips, "narration": voix,
        "sous_titres": srt, "montage": montage,
    }
    with open(RAPPORT, "w", encoding="utf-8") as f:
        json.dump(rapport, f, indent=1, ensure_ascii=False)
    _dire(f"rapport écrit : {RAPPORT}")
    return 0 if montage.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
