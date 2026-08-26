"""La voix : des reglages, et la verite sur les fournisseurs (HOS-173).

`backend/voice/` portait depuis HOS-064 deux interfaces et quatre classes
concretes — `WhisperProvider`, `PiperProvider` et leurs pendants cloud —
**sans un seul importateur**. Aucun ecran ne les presentait, aucun reglage
ne les gouvernait. Elles ont ete retirees en HOS-175, remplacees par des
implementations reelles adossees a des modeles mesures.

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


def test_un_fournisseur_sans_dependance_est_dit_absent(monkeypatch) -> None:
    """Le point du module, eprouve sur une absence simulee.

    Ce test affirmait l'absence **reelle** des fournisseurs serveur, ce qui
    etait vrai jusqu'a l'installation des modeles locaux (HOS-175). Le
    reecrire sur l'etat aurait fige une verite datee ; il porte donc sur la
    regle : une classe qui existe sans sa dependance ne compte pas.

    `WhisperProvider` et `PiperProvider` sont dans ce cas depuis HOS-064 —
    concretes, et levant `NotImplementedError`. Les compter comme une
    capacite serait repeter la confusion `tools` d'Ollama, annoncee jusque
    par un modele d'embedding.
    """
    from backend.voice import locale

    class _SansDependance:
        def is_available(self): return False

    monkeypatch.setattr(
        locale, "fournisseurs",
        lambda: {"transcription": _SansDependance(),
                 "synthese": _SansDependance()})

    serveur = [c for c in vp.capacites() if c.ou == "serveur"]

    assert len(serveur) == 2
    for c in serveur:
        assert not c.disponible, f"{c.nom} annonce sans etre installe"
        assert "is_available" in c.detail


def test_le_rapport_porte_les_deux_en_un_appel(tmp_path, monkeypatch) -> None:
    """Un seul ecran les affiche ensemble ; deux routes l'obligeraient a
    orchestrer deux requetes pour un rendu atomique."""
    _isole(tmp_path, monkeypatch)

    r = vp.rapport()

    assert "preferences" in r and "capacites" in r
    assert len(r["capacites"]) == 4


# -- les modeles locaux (HOS-175) --------------------------------------

def test_les_fournisseurs_locaux_sont_construits_sans_etre_charges() -> None:
    """Neuf secondes de chargement ne doivent pas etre payees pour un
    rapport de capacites que personne n'a demande."""
    from backend.voice import locale

    f = locale.fournisseurs()

    assert set(f) == {"transcription", "synthese"}
    # `_charge` reste None : construire ne charge rien.
    assert f["synthese"]._charge is None
    assert f["transcription"]._charge is None


def test_une_voix_absente_rend_le_fournisseur_indisponible(monkeypatch, tmp_path) -> None:
    """La bibliotheque ne suffit pas.

    Sans le fichier `.onnx`, Piper ne peut rien dire. Annoncer
    « disponible » sur la seule presence du paquet serait exactement la
    confusion entre le contrat et la capacite que ce module corrige.
    """
    from backend.voice import locale

    monkeypatch.setenv("VOIX_HERMES", str(tmp_path))

    assert not locale.PiperLocal().is_available()


def test_le_dossier_des_voix_suit_la_variable(monkeypatch, tmp_path) -> None:
    from backend.voice import locale

    monkeypatch.setenv("VOIX_HERMES", str(tmp_path))

    assert locale.dossier_des_voix() == tmp_path


def test_les_voix_installees_sont_listees_depuis_le_disque(monkeypatch, tmp_path) -> None:
    from backend.voice import locale

    monkeypatch.setenv("VOIX_HERMES", str(tmp_path))
    (tmp_path / "fr_FR-siwis-medium.onnx").write_bytes(b"x")
    (tmp_path / "en_US-amy-low.onnx").write_bytes(b"x")

    assert locale.PiperLocal().get_voices() == [
        "en_US-amy-low", "fr_FR-siwis-medium"]


def test_un_fournisseur_local_disponible_prime_dans_le_rapport(monkeypatch) -> None:
    """Le rapport doit nommer le modele local, pas la classe de HOS-064."""
    from backend.voice import locale

    class _Pret:
        def is_available(self): return True
        def get_name(self): return "faster-whisper/small"

    monkeypatch.setattr(locale, "fournisseurs",
                        lambda: {"transcription": _Pret(), "synthese": _Pret()})

    serveur = [c for c in vp.capacites() if c.ou == "serveur"]
    assert all(c.disponible for c in serveur)
    assert all("faster-whisper" in c.nom for c in serveur)
    # Le detail doit dire pourquoi c'est acceptable sur ce materiel.
    assert all("VRAM" in c.detail for c in serveur)


def test_un_fournisseur_local_qui_leve_ne_casse_pas_le_rapport(monkeypatch) -> None:
    from backend.voice import locale

    class _Explose:
        def is_available(self): raise RuntimeError("onnx absent")

    monkeypatch.setattr(locale, "fournisseurs",
                        lambda: {"transcription": _Explose(), "synthese": _Explose()})

    assert len(vp.capacites()) == 4
