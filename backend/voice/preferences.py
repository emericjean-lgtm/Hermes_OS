"""Les réglages de la voix, et ce que la machine sait vraiment faire (HOS-173).

## Ce qui existait

`backend/voice/` portait depuis HOS-064 deux interfaces et quatre classes
concrètes — `WhisperProvider`, `PiperProvider`, et leurs pendants cloud —
**sans un seul importateur**. Une première version de ce commentaire les
disait absentes : c'était faux, elles existent. Ce qu'elles n'ont pas, c'est
leur dépendance : chacune lève `NotImplementedError` et son `is_available()`
rend False.

La nuance importe, parce que compter une classe pour une capacité est
exactement la confusion que ce dépôt a déjà payée — la capacité `tools`
d'Ollama est annoncée jusque par un modèle d'embedding.

Le frontend, lui, dicte déjà — `voice-input.tsx` utilise la
`SpeechRecognition` du navigateur, qui existe et fonctionne. La capacité
était donc réelle **et** invisible : aucun écran ne la présentait, aucun
réglage ne la gouvernait.

## Ce que ce module fait, et ce qu'il refuse de faire

Il garde les préférences et **dit la vérité sur les fournisseurs**. Il ne
prétend pas transcrire : sur cette machine, un Whisper local disputerait les
16 Gio de VRAM au modèle qui porte les missions, et ce projet a mesuré ce
que coûte un second modèle qui réclame sa place.

La reconnaissance et la synthèse vivent donc dans le navigateur, qui les
offre sans rien coûter au GPU. Le rôle du serveur est de retenir les
réglages et de ne jamais annoncer une capacité qu'il n'a pas — la règle
appliquée partout ailleurs dans cette application.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("hermes_os.voice")

#: Où les préférences survivent à un redémarrage. Le même dossier que le
#: reste de l'état de Hermes OS, pour qu'une sauvegarde les emporte aussi.
FICHIER = "voix.json"


def _dossier() -> Path:
    base = os.environ.get("HERMES_DATA_DIR") or os.path.join(
        os.path.expanduser("~"), ".hermes_os")
    return Path(base)


@dataclass
class Preferences:
    """Ce que l'opérateur a choisi pour la voix.

    Les valeurs par défaut décrivent un usage francophone en mains libres
    désactivé : rien ne parle tant que personne ne l'a demandé. Une
    application qui se met à parler seule au premier lancement est une
    mauvaise surprise, pas une fonctionnalité.
    """

    #: Langue de la dictée, au format BCP-47 attendu par le navigateur.
    langue: str = "fr-FR"
    #: Nom de la voix de synthèse, tel que le navigateur l'expose. Vide =
    #: la voix par défaut du système, qui existe toujours.
    voix: str = ""
    #: Débit et hauteur, dans les bornes que l'API Web Speech accepte.
    debit: float = 1.0
    hauteur: float = 1.0
    #: Lire les réponses de l'Assistant à voix haute.
    lecture_automatique: bool = False
    #: Envoyer la dictée dès qu'un silence est détecté, sans clic.
    mains_libres: bool = False

    def valide(self) -> "Preferences":
        """Ramener chaque valeur dans ses bornes plutôt que refuser.

        Un réglage hors bornes vient d'un client qui a mal calculé, pas
        d'une intention. Le corriger coûte moins qu'une erreur 422 qui
        laisserait l'interface sans réglages du tout.
        """
        self.debit = min(max(float(self.debit), 0.5), 2.0)
        self.hauteur = min(max(float(self.hauteur), 0.5), 2.0)
        self.langue = (self.langue or "fr-FR").strip()[:16]
        self.voix = (self.voix or "").strip()[:120]
        self.lecture_automatique = bool(self.lecture_automatique)
        self.mains_libres = bool(self.mains_libres)
        return self


def lire() -> Preferences:
    """Les préférences enregistrées, ou celles par défaut."""
    chemin = _dossier() / FICHIER
    try:
        brut = json.loads(chemin.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return Preferences()
    connus = {c.name for c in Preferences.__dataclass_fields__.values()}
    return Preferences(**{k: v for k, v in brut.items()
                          if k in connus}).valide()


def ecrire(preferences: Preferences) -> Preferences:
    """Enregistrer, et rendre ce qui a réellement été retenu.

    Rend l'objet validé plutôt que celui reçu : le client voit alors la
    valeur bornée, au lieu de croire qu'un débit de 9 a été accepté.
    """
    valides = preferences.valide()
    dossier = _dossier()
    try:
        dossier.mkdir(parents=True, exist_ok=True)
        (dossier / FICHIER).write_text(
            json.dumps(asdict(valides), indent=2, ensure_ascii=False),
            encoding="utf-8")
    except OSError:
        # Des préférences non enregistrées valent mieux qu'une erreur : la
        # session en cours les garde, le prochain démarrage repartira des
        # valeurs par défaut.
        logger.warning("préférences vocales non enregistrées", exc_info=True)
    return valides


@dataclass
class Capacite:
    """Un fournisseur, et s'il est réellement là."""

    nom: str
    genre: str          # "transcription" | "synthese"
    ou: str             # "navigateur" | "serveur"
    disponible: bool
    detail: str


def capacites() -> list[Capacite]:
    """Ce que Hermes OS sait faire de la voix, sans rien enjoliver.

    Le côté serveur est interrogé pour de bon : une interface abstraite
    sans implémentation rend `disponible: False`, et le détail dit pourquoi.
    C'est la différence entre « nous pourrions » et « nous pouvons », et
    c'est exactement ce que ce module existe pour ne pas confondre.
    """
    trouvees = [
        Capacite(
            nom="Web Speech API",
            genre="transcription",
            ou="navigateur",
            disponible=True,
            detail="Reconnaissance fournie par Chrome et Edge. Aucun modèle "
                   "local, aucune VRAM consommée.",
        ),
        Capacite(
            nom="SpeechSynthesis",
            genre="synthese",
            ou="navigateur",
            disponible=True,
            detail="Voix installées sur le système, exposées par le "
                   "navigateur. Le choix réel dépend de la machine.",
        ),
    ]
    trouvees.append(_capacite_serveur("transcription"))
    trouvees.append(_capacite_serveur("synthese"))
    return trouvees


def _capacite_serveur(genre: str) -> Capacite:
    """Un fournisseur local existe-t-il vraiment pour ce genre ?

    On **demande**, on ne suppose pas. `is_available()` regarde la
    bibliotheque et le fichier de modele ; il ne charge rien, si bien que ce
    rapport ne paie jamais les neuf secondes d'un modele que personne n'a
    demande.

    Les souches de HOS-064 qui vivaient ici ont ete retirees en HOS-175 :
    elles annoncaient leur disponibilite sur un simple `import` et
    l'installation de `piper-tts` les a fait mentir d'un coup.
    """
    from backend.voice import locale

    fournisseur = locale.fournisseurs().get(genre)
    if fournisseur is not None:
        try:
            if fournisseur.is_available():
                return Capacite(
                    nom=fournisseur.get_name(), genre=genre, ou="serveur",
                    disponible=True,
                    detail="Modele local sur CPU — 0 de VRAM, donc aucune "
                           "concurrence avec le modele des missions.")
        except Exception:  # noqa: BLE001 - un fournisseur casse est absent
            logger.debug("fournisseur local %s inutilisable", genre,
                         exc_info=True)

    manque = ("le modele Piper (.onnx) n'est pas dans le dossier des voix"
              if genre == "synthese"
              else "`faster-whisper` n'est pas installe")
    return Capacite(
        nom="aucun fournisseur local", genre=genre, ou="serveur",
        disponible=False,
        detail=f"`is_available()` rend False : {manque}. Le navigateur fait "
               f"ce travail sans rien coûter au GPU.")


def rapport() -> dict[str, Any]:
    """Préférences et capacités en un seul appel, pour un seul écran."""
    return {
        "preferences": asdict(lire()),
        "capacites": [asdict(c) for c in capacites()],
    }
