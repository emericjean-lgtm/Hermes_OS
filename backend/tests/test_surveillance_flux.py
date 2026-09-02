"""Ce qui sort d'un agent est surveillé pendant qu'il parle (HOS-218).

Le canary vient d'Agent OS (`runner.ts`, `monitorChild`) et c'est la
meilleure idée de leur code : on ne peut pas énumérer tout ce qu'un agent
ne doit pas dire, mais on peut savoir quand il dit **une chose précise**
qu'il n'aurait jamais dû voir.

Le report de 512 caractères vient du même endroit, et il n'est pas
décoratif : un flux arrive par blocs, et un secret coupé entre deux blocs
passerait sans lui.
"""

from __future__ import annotations

import pytest

from backend.security.surveillance_flux import (Alerte, Motif, REPORT,
                                                SurveillanceFlux,
                                                environnement_avec_canary,
                                                fabriquer_canary)


def _surveillance(**kw) -> SurveillanceFlux:
    kw.setdefault("canary", "hos-canary-abcdef0123456789")
    return SurveillanceFlux(**kw)


# ── Le canary ────────────────────────────────────────────────────────

def test_le_canary_ressorti_leve_une_alerte():
    s = _surveillance()
    assert s.bloc("tout va bien") is None
    a = s.bloc("mon environnement contient hos-canary-abcdef0123456789 tiens")
    assert a is not None and a.motif is Motif.CANARY
    assert s.coupee


def test_deux_canaries_ne_se_ressemblent_pas():
    """Un canary constant finirait dans un journal, puis dans un rapport
    de bogue, et déclencherait à tort."""
    assert fabriquer_canary() != fabriquer_canary()


def test_le_canary_a_la_forme_d_un_secret():
    c = fabriquer_canary()
    assert c.startswith("hos-canary-") and len(c) > 30


def test_le_canary_est_pose_sous_un_nom_qui_ressemble_a_un_secret():
    """Un agent qui filtre son environnement sur des noms sensibles doit
    l'attraper aussi, sinon le témoin ne témoigne de rien."""
    env = environnement_avec_canary({"PATH": "/usr/bin"}, "jeton")
    assert env["HERMES_CANARY_TOKEN"] == "jeton"
    assert env["PATH"] == "/usr/bin"


# ── Le report entre deux blocs ───────────────────────────────────────

def test_un_secret_coupe_entre_deux_blocs_est_vu():
    """Sans le report, celui-ci passe : aucun bloc ne le contient entier."""
    secret = "sk-" + "z" * 40
    s = _surveillance(secrets_connus=[secret])
    moitie = len(secret) // 2
    assert s.bloc("début " + secret[:moitie]) is None
    a = s.bloc(secret[moitie:] + " fin")
    assert a is not None and a.motif is Motif.SECRET


def test_le_report_reste_borne():
    """Il ne doit pas devenir un tampon qui grandit sans fin."""
    s = _surveillance()
    for _ in range(50):
        s.bloc("x" * 1000)
    assert len(s._report) == REPORT


def test_le_rapport_ne_contient_jamais_le_secret():
    """Un rapport de fuite qui contient le secret est une seconde fuite."""
    secret = "sk-" + "q" * 40
    s = _surveillance(secrets_connus=[secret])
    a = s.bloc(f"voici {secret}")
    assert secret not in a.detail
    assert str(len(secret)) in a.detail


# ── Ce qui ne doit pas déclencher ───────────────────────────────────

def test_une_valeur_trop_courte_n_est_pas_surveillee():
    """« 1 », « true », un identifiant de deux lettres se retrouvent
    partout dans une sortie normale. Une alarme qui sonne pour rien est
    débranchée dans la semaine."""
    s = _surveillance(secrets_connus=["1", "true", "abc"])
    assert s.bloc("le résultat est 1, true, abc") is None
    assert not s.coupee


def test_une_sortie_normale_ne_declenche_rien():
    s = _surveillance(secrets_connus=["sk-" + "y" * 40])
    for bloc in ("Analyse du dépôt…", "12 fichiers lus", "terminé"):
        assert s.bloc(bloc) is None
    assert not s.coupee


def test_un_bloc_vide_ne_fait_rien():
    s = _surveillance()
    assert s.bloc("") is None


# ── Le silence ───────────────────────────────────────────────────────

def test_un_silence_prolonge_est_un_evenement(monkeypatch):
    """Un agent qui se tait n'échoue pas, il attend — et l'attente
    ressemble au travail. C'est la leçon du décodage qui rampait
    quarante minutes sans lever d'erreur."""
    import backend.security.surveillance_flux as mod

    horloge = {"t": 1000.0}
    monkeypatch.setattr(mod.time, "monotonic", lambda: horloge["t"])

    s = _surveillance(silence_s=60.0)
    s.bloc("je commence")
    horloge["t"] += 30
    assert s.tic() is None
    horloge["t"] += 40
    a = s.tic()
    assert a is not None and a.motif is Motif.SILENCE


def test_le_silence_n_est_signale_qu_une_fois(monkeypatch):
    import backend.security.surveillance_flux as mod

    horloge = {"t": 0.0}
    monkeypatch.setattr(mod.time, "monotonic", lambda: horloge["t"])
    s = _surveillance(silence_s=10.0)
    s.bloc("début")
    horloge["t"] += 20
    assert s.tic() is not None
    horloge["t"] += 20
    assert s.tic() is None, "une alerte par silence, pas une par tic"


def test_une_sortie_reprise_rearme_le_silence(monkeypatch):
    import backend.security.surveillance_flux as mod

    horloge = {"t": 0.0}
    monkeypatch.setattr(mod.time, "monotonic", lambda: horloge["t"])
    s = _surveillance(silence_s=10.0)
    s.bloc("début")
    horloge["t"] += 20
    s.tic()
    s.bloc("je reparle")
    horloge["t"] += 20
    assert s.tic() is not None, "un second silence doit se signaler"


def test_le_silence_ne_compte_pas_comme_une_coupure():
    """Le silence appelle une décision ; ce n'est pas une fuite avérée."""
    s = _surveillance(silence_s=0.0)
    s.tic()
    assert not s.coupee


# ── Le coût ──────────────────────────────────────────────────────────

def test_le_cout_declenche_au_plafond():
    s = _surveillance(cout_max=0.50)
    assert s.tic(cout=0.49) is None
    a = s.tic(cout=0.51)
    assert a is not None and a.motif is Motif.COUT


def test_sans_plafond_le_cout_ne_declenche_pas():
    s = _surveillance()
    assert s.tic(cout=9999.0) is None


# ── Le rappel ────────────────────────────────────────────────────────

def test_l_appelant_est_prevenu():
    vues: list[Alerte] = []
    s = _surveillance(sur_alerte=vues.append)
    s.bloc("hos-canary-abcdef0123456789")
    assert [a.motif for a in vues] == [Motif.CANARY]
