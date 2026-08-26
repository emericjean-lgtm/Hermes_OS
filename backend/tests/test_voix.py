"""La voix : des reglages, et la verite sur les fournisseurs (HOS-173).

`backend/voice/` portait depuis HOS-064 deux interfaces et quatre classes
concretes — `WhisperProvider`, `PiperProvider` et leurs pendants cloud —
**sans un seul importateur**. Aucun ecran ne les presentait, aucun reglage
ne les gouvernait.

Le piege de ce module est de compter une classe pour une capacite. C'est
exactement la confusion que ce depot a deja payee sur la capacite `tools`
d'Ollama, annoncee jusque par un modele d'embedding : la moitie de ces
tests porte donc sur « declare » contre « mesure ».
"""
from __future__ import annotations

from backend.voice import preferences as vp


def _isole(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HERMES_DATA_DIR", str(tmp_path))


# -- les reglages ------------------------------------------------------

def test_les_defauts_ne_font_rien_parler(tmp_path, monkeypatch) -> None:
    """Une application qui parle seule au premier lancement est une
    mauvaise surprise, pas une fonctionnalite."""
    _isole(tmp_path, monkeypatch)

    p = vp.lire()

    assert p.lecture_automatique is False
    assert p.mains_libres is False
    assert p.langue == "fr-FR"


def test_les_reglages_survivent_a_un_redemarrage(tmp_path, monkeypatch) -> None:
    _isole(tmp_path, monkeypatch)

    vp.ecrire(vp.Preferences(langue="en-US", voix="Julie", debit=1.4))

    relu = vp.lire()
    assert relu.langue == "en-US"
    assert relu.voix == "Julie"
    assert relu.debit == 1.4


def test_une_valeur_hors_bornes_est_ramenee_et_non_refusee(tmp_path, monkeypatch) -> None:
    """Un reglage hors bornes vient d'un client qui a mal calcule.

    Le corriger coute moins qu'une 422 qui laisserait l'interface sans
    reglages du tout.
    """
    _isole(tmp_path, monkeypatch)

    retenu = vp.ecrire(vp.Preferences(debit=9.0, hauteur=-3.0))

    assert retenu.debit == 2.0
    assert retenu.hauteur == 0.5


def test_le_retour_porte_la_valeur_bornee(tmp_path, monkeypatch) -> None:
    """Sinon le client croirait son debit de 9 accepte."""
    _isole(tmp_path, monkeypatch)

    assert vp.ecrire(vp.Preferences(debit=9.0)).debit == 2.0


def test_un_champ_inconnu_est_ignore(tmp_path, monkeypatch) -> None:
    """Un client d'une autre version ne doit pas faire tomber la lecture."""
    _isole(tmp_path, monkeypatch)
    (tmp_path / vp.FICHIER).write_text(
        '{"langue": "de-DE", "inconnu": 42}', encoding="utf-8")

    assert vp.lire().langue == "de-DE"


def test_un_fichier_illisible_rend_les_defauts(tmp_path, monkeypatch) -> None:
    _isole(tmp_path, monkeypatch)
    (tmp_path / vp.FICHIER).write_text("pas du json", encoding="utf-8")

    assert vp.lire().langue == "fr-FR"


def test_un_dossier_non_inscriptible_ne_leve_pas(tmp_path, monkeypatch) -> None:
    """Des preferences non enregistrees valent mieux qu'une erreur."""
    monkeypatch.setenv("HERMES_DATA_DIR", str(tmp_path / "fichier.txt"))
    (tmp_path / "fichier.txt").write_text("x", encoding="utf-8")

    assert vp.ecrire(vp.Preferences(langue="es-ES")).langue == "es-ES"


# -- les capacites : mesurees, jamais declarees ------------------------

def test_le_navigateur_est_annonce_disponible() -> None:
    """La reconnaissance et la synthese vivent la, et elles marchent."""
    navigateur = [c for c in vp.capacites() if c.ou == "navigateur"]

    assert len(navigateur) == 2
    assert all(c.disponible for c in navigateur)


def test_un_fournisseur_serveur_sans_dependance_est_dit_absent() -> None:
    """Le point du module.

    `WhisperProvider` et `PiperProvider` existent comme classes concretes
    depuis HOS-064 ; toutes deux levent `NotImplementedError` et leur
    `is_available()` rend False. Les compter comme une capacite serait
    repeter la confusion `tools` d'Ollama.
    """
    serveur = [c for c in vp.capacites() if c.ou == "serveur"]

    assert len(serveur) == 2
    for c in serveur:
        assert not c.disponible, f"{c.nom} annonce sans etre installe"
        assert "is_available" in c.detail


def test_un_fournisseur_qui_leve_est_traite_comme_absent(monkeypatch) -> None:
    """Un fournisseur casse est absent, pas une panne du rapport."""
    from backend.voice import speech_to_text

    class _Explose(speech_to_text.SpeechToTextProvider):
        def transcribe(self, audio_path, language="fr"): return ""
        def is_available(self): raise RuntimeError("pilote absent")
        def get_name(self): return "explose"

    monkeypatch.setattr(speech_to_text, "_Explose", _Explose, raising=False)

    transcription = [c for c in vp.capacites()
                     if c.ou == "serveur" and c.genre == "transcription"]
    assert transcription and not transcription[0].disponible


def test_le_rapport_porte_les_deux_en_un_appel(tmp_path, monkeypatch) -> None:
    """Un seul ecran les affiche ensemble ; deux routes l'obligeraient a
    orchestrer deux requetes pour un rendu atomique."""
    _isole(tmp_path, monkeypatch)

    r = vp.rapport()

    assert "preferences" in r and "capacites" in r
    assert len(r["capacites"]) == 4
