"""Le relecteur doit savoir dire non (HOS-191).

Un plan vidéo se termine toujours. ComfyUI rend un MP4 valide même quand le
contenu n'a rien à voir avec la consigne, et à cinq minutes de calcul par
seconde de vidéo, s'en apercevoir au montage coûte une nuit.

Le relecteur existe pour cela. Mais un relecteur qui approuve tout ne mesure
rien : il **fabrique** de la confiance, ce qui est pire que de n'en
fabriquer aucune. Interrogé une première fois sur un plan réel, le modèle a
répondu « matches: true, confidence: 98 » en énumérant comme présents les
trois éléments de la consigne, dont de la vapeur que l'œil n'y trouvait pas.

Ces tests portent donc sur les quatre façons dont le relecteur peut mentir :
approuver ce qu'il n'a pas vu, rejeter faute d'avoir pu regarder, moyenner
un plan qui dérive, et prendre une réponse tronquée pour un refus.

La qualification du modèle lui-même — 4 refus sur 4 consignes fausses, dont
une rue de nuit en néons bleus qui partage l'ambiance sans le sujet — a été
faite sur la machine le 2026-08-27 et n'est pas rejouée ici : elle demande
Ollama et vingt secondes par image.
"""

from __future__ import annotations

import os
import subprocess

from backend.studio.relecteur import Verdict, relire


def _faux_juge(reponses: list[dict]):
    """Un interrogateur scripté, une réponse par image."""
    file = list(reponses)

    def poser(modele, consigne, image, url, delai):
        return file.pop(0) if file else {"matches": True, "confidence": 50}

    return poser


def _trois_images(monkeypatch, combien: int = 3):
    monkeypatch.setattr("backend.studio.relecteur.extraire",
                        lambda video, images=3: [f"/faux/{i}.png"
                                                 for i in range(combien)])


def test_un_plan_conforme_est_accepte(monkeypatch):
    _trois_images(monkeypatch)
    v = relire("/faux/plan.mp4", "une rue de nuit",
               interroge=_faux_juge([
                   {"matches": True, "confidence": 90, "present": ["rue"]},
                   {"matches": True, "confidence": 95, "present": ["nuit"]},
                   {"matches": True, "confidence": 92, "present": ["rue"]},
               ]))
    assert v.correspond is True
    assert v.a_pu_juger
    assert v.images_vues == 3
    assert v.confiance == 95, "la confiance retenue est la plus haute observée"
    assert v.present == ["rue", "nuit"], "les observations sont fusionnées sans doublon"


def test_une_seule_image_fautive_condamne_le_plan(monkeypatch):
    """Le verdict est conjonctif, et c'est délibéré.

    Un plan dont le dernier tiers dérive n'est pas utilisable. Une moyenne
    le ferait passer à deux voix contre une — et l'on découvrirait la
    dérive au montage, après avoir payé le rendu.
    """
    _trois_images(monkeypatch)
    v = relire("/faux/plan.mp4", "une rue de nuit",
               interroge=_faux_juge([
                   {"matches": True, "confidence": 90},
                   {"matches": True, "confidence": 90},
                   {"matches": False, "confidence": 80,
                    "defects": ["le plan dérive vers un intérieur"]},
               ]))
    assert v.correspond is False
    assert "1 image(s) sur 3" in v.raison
    assert "le plan dérive vers un intérieur" in v.defauts


def test_ne_pas_avoir_pu_regarder_nest_pas_un_refus(monkeypatch):
    """`None` et `False` ne sont pas la même chose.

    Les confondre ferait rejeter des plans corrects chaque fois qu'Ollama
    est occupé — et à ce prix de rendu, un rejet à tort coûte autant qu'une
    acceptation à tort.
    """
    _trois_images(monkeypatch)

    def tombe(*a, **k):
        raise ConnectionError("Ollama injoignable")

    v = relire("/faux/plan.mp4", "une rue", interroge=tombe)
    assert v.correspond is None
    assert not v.a_pu_juger
    assert "ConnectionError" in v.raison
    assert v.images_vues == 0


def test_une_reponse_tronquee_nest_pas_un_refus(monkeypatch):
    """`done_reason=length` veut dire que la fenêtre s'est fermée.

    Mesuré : borné à 300 jetons, ce modèle rend une réponse **vide** parce
    qu'il dépense son budget en raisonnement. Le compter comme un refus
    disqualifierait un modèle qui fonctionne — le défaut que ce dépôt
    documente sous « ni un échec sur parole ».
    """
    _trois_images(monkeypatch, 1)
    v = relire("/faux/plan.mp4", "une rue",
               interroge=_faux_juge([{"tronque": True}]))
    assert v.correspond is None
    assert "fenêtre" in v.raison


def test_une_reponse_illisible_est_nommee(monkeypatch):
    _trois_images(monkeypatch, 1)
    v = relire("/faux/plan.mp4", "une rue",
               interroge=_faux_juge([{"illisible": "Bien sûr ! Voici mon analyse…"}]))
    assert v.correspond is None
    assert "non analysable" in v.raison


def test_un_verdict_sans_booleen_est_refuse(monkeypatch):
    """Le modèle qui répond « probably » ne rend pas un verdict.

    L'accepter reviendrait à lire une hésitation comme un accord.
    """
    _trois_images(monkeypatch, 1)
    v = relire("/faux/plan.mp4", "une rue",
               interroge=_faux_juge([{"matches": "probably", "confidence": 70}]))
    assert v.correspond is None
    assert "pas rendu de verdict" in v.raison


def test_un_plan_illisible_ne_produit_pas_de_verdict(monkeypatch):
    """Sans image extraite, il n'y a rien à juger — et il faut le dire."""
    monkeypatch.setattr("backend.studio.relecteur.extraire",
                        lambda video, images=3: [])
    v = relire("/faux/absent.mp4", "une rue")
    assert v.correspond is None
    assert "aucune image" in v.raison


def test_le_verdict_vide_ne_pretend_rien():
    v = Verdict()
    assert v.correspond is None and not v.a_pu_juger
    assert v.present == [] and v.defauts == [] and v.confiance == 0


# ── Extraction ────────────────────────────────────────────────────────

def test_les_images_extraites_viennent_dinstants_distincts(monkeypatch, tmp_path):
    """Le défaut qui a rendu trois fois la même image.

    Le filtre `thumbnail` choisit une image par lot de cent ; un plan de
    quarante-neuf images n'en produisait donc qu'une. Le lot réduit à la
    longueur du plan n'a rien réglé : les trois fichiers sortaient
    **octet pour octet identiques**, et leurs tailles se ressemblaient
    assez pour ne pas alerter. Seule une empreinte l'a montré.

    Ce test porte donc sur ce qui est demandé à ffmpeg, pas sur ce qu'il
    rend : trois instants distincts, un appel chacun.
    """
    from backend.studio import relecteur

    instants: list[str] = []

    def faux_run(cmd, **kwargs):
        instants.append(cmd[cmd.index("-ss") + 1])
        (tmp_path / os.path.basename(cmd[-1])).write_bytes(b"png")
        os.replace(tmp_path / os.path.basename(cmd[-1]), cmd[-1])
        return subprocess.CompletedProcess(cmd, 0, b"", b"")

    monkeypatch.setattr(relecteur, "ffmpeg", lambda: "ffmpeg.exe")
    monkeypatch.setattr(relecteur, "duree_s", lambda v: 2.0)
    monkeypatch.setattr(relecteur.os.path, "exists", lambda p: True)
    monkeypatch.setattr(relecteur.subprocess, "run", faux_run)

    cadres = relecteur.extraire("/faux/plan.mp4", 3)
    assert len(cadres) == 3
    assert len(set(instants)) == 3, "trois instants, pas trois fois le même"


def test_les_instants_evitent_les_bords_du_plan():
    """Un plan qui ouvre ou ferme en fondu donnerait des images noires.

    Aucun relecteur ne peut juger une image noire, et il la refuserait —
    condamnant un plan correct au prix d'une nuit de rendu.
    """
    from backend.studio.relecteur import INSTANTS

    assert all(0 < f < 1 for f in INSTANTS)
    assert list(INSTANTS) == sorted(set(INSTANTS))


def test_un_plan_de_duree_inconnue_ne_produit_pas_dimages(monkeypatch):
    """Sans durée, les instants ne veulent rien dire — mieux vaut rien."""
    from backend.studio import relecteur

    monkeypatch.setattr(relecteur, "ffmpeg", lambda: "ffmpeg.exe")
    monkeypatch.setattr(relecteur.os.path, "exists", lambda p: True)
    monkeypatch.setattr(relecteur, "duree_s", lambda v: 0.0)
    assert relecteur.extraire("/faux/plan.mp4", 3) == []


def test_le_relecteur_rend_la_carte_des_qu_il_a_repondu():
    """Sinon il coute le plan suivant, et rien ne le dit.

    Ollama garde un modele resident cinq minutes par defaut. La relecture
    d'un plan tombe juste avant que le suivant ne charge ses poids : sur
    une carte de 16 Gio qui n'accepte qu'un locataire lourd, le rendu
    suivant bascule sur la memoire partagee et rampe.

    Mesure du 2026-08-30 : `p01` rendu en 1 358 s, relu, puis `p02a`
    lance 90 secondes plus tard a tenu 2 404 s sans aboutir. Le rendu ne
    debordait pas tout seul — il debordait de ce que le relecteur tenait
    encore.
    """
    import json
    from unittest.mock import patch

    from backend.studio import relecteur

    vu = {}

    class _Reponse:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return json.dumps({"response": "{}"}).encode()

    def _urlopen(req, timeout=0):
        vu.update(json.loads(req.data.decode()))
        return _Reponse()

    with patch("urllib.request.urlopen", _urlopen):
        relecteur._interroger("m", "consigne", __file__,
                              "http://127.0.0.1:11434", 10.0)

    assert vu.get("keep_alive") == 0, \
        "le relecteur doit rendre la carte, pas la garder cinq minutes"
