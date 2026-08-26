"""Transcription et synthèse locales, sur CPU (HOS-175).

## Pourquoi ces modèles-là

Le choix est dicté par le matériel, pas par les classements. Sur cette
machine, `gpt-oss-20b-64k` occupe **11,92 Gio des 16** de la RX 6800, et la
carte n'est joignable que par Vulkan — ROCm n'y fonctionne pas. Un modèle
vocal sur GPU disputerait donc sa place au cerveau des missions, ce que ce
projet a mesuré et payé plusieurs fois.

Les deux retenus tournent sur CPU et n'approchent jamais la carte :

* **Piper** — `fr_FR-siwis-medium`, 61 Mo d'ONNX. C'est la famille que
  HOS-064 avait déjà nommée sans jamais choisir de voix.
* **faster-whisper** — modèle `small` en int8, 464 Mo. Retenu plutôt
  qu'`openai-whisper`, que la classe de HOS-064 visait : celui-ci tire
  PyTorch (~2,5 Gio) pour être plus lent sur CPU, là où CTranslate2 pèse
  35 Mo.

## Ce que la mesure a donné

Aller-retour réel du 2026-08-26 — Piper prononce, Whisper relit :

    dit     : Mission lancée sur le cahier des charges, trois sections vérifiées.
    entendu : Mission lancée sur le cahier des charges, 3 sections vérifiées.

Mot pour mot ; « trois » devenu « 3 » est une normalisation, pas une faute.
1,5 s de transcription, 9,2 s de chargement une fois pour toutes, **356 Mio
de RAM et 0 de VRAM**.

Le modèle `medium` n'a pas été retenu : `small` transcrit déjà sans erreur
sur du français propre, et le triplement du coût CPU n'achèterait rien
d'observable ici.

## Les modèles sont chargés paresseusement

Neuf secondes de chargement au premier appel, zéro ensuite. Les charger au
démarrage retarderait chaque lancement de Hermes OS pour une capacité que
la plupart des sessions n'utilisent pas.
"""
from __future__ import annotations

import io
import logging
import os
import wave
from pathlib import Path
from typing import Any, Optional

from backend.voice.speech_to_text import SpeechToTextProvider
from backend.voice.text_to_speech import TextToSpeechProvider

logger = logging.getLogger("hermes_os.voice")

#: Où vivent les voix Piper. À côté de l'agent et des modèles, pas dans le
#: dépôt : ce sont des données, et 61 Mo n'ont rien à faire sous git.
def dossier_des_voix() -> Path:
    base = os.environ.get("VOIX_HERMES") or os.path.join(
        os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
        "hermes", "voices")
    return Path(base)


#: La voix par défaut, et la seule installée à ce jour.
VOIX_DEFAUT = "fr_FR-siwis-medium"

#: `small` plutôt que `medium` : mesuré sans erreur sur du français propre.
MODELE_WHISPER = "small"


class PiperLocal(TextToSpeechProvider):
    """Synthèse Piper, sur CPU."""

    def __init__(self, voix: str = VOIX_DEFAUT) -> None:
        self._voix = voix or VOIX_DEFAUT
        self._charge: Any = None

    def _modele(self) -> Any:
        if self._charge is None:
            from piper import PiperVoice

            self._charge = PiperVoice.load(str(self.chemin()))
        return self._charge

    def chemin(self) -> Path:
        return dossier_des_voix() / f"{self._voix}.onnx"

    def synthesize(self, text: str, voice: str = "default",
                   language: str = "fr") -> bytes:
        """Le WAV correspondant, prêt à être servi tel quel.

        Rend des octets WAV et non un chemin : l'appelant est une route
        HTTP, et écrire un fichier temporaire pour le relire aussitôt
        ajouterait une écriture disque par phrase.
        """
        tampon = io.BytesIO()
        with wave.open(tampon, "wb") as sortie:
            self._modele().synthesize_wav(text, sortie)
        return tampon.getvalue()

    def is_available(self) -> bool:
        try:
            import piper  # noqa: F401
        except ImportError:
            return False
        # La bibliothèque ne suffit pas : sans le fichier de voix, elle ne
        # peut rien dire. Annoncer « disponible » ici serait exactement la
        # confusion entre le contrat et la capacité que ce module corrige.
        return self.chemin().is_file()

    def get_name(self) -> str:
        return f"piper/{self._voix}"

    def get_voices(self, language: str = "fr") -> list[str]:
        dossier = dossier_des_voix()
        if not dossier.is_dir():
            return []
        return sorted(f.stem for f in dossier.glob("*.onnx"))


class WhisperLocal(SpeechToTextProvider):
    """Transcription faster-whisper, sur CPU, en int8."""

    def __init__(self, taille: str = MODELE_WHISPER) -> None:
        self._taille = taille
        self._charge: Any = None

    def _modele(self) -> Any:
        if self._charge is None:
            from faster_whisper import WhisperModel

            # `int8` et non `float16` : sans GPU, la quantification divise le
            # coût CPU sans perte mesurable sur du français propre.
            self._charge = WhisperModel(
                self._taille, device="cpu", compute_type="int8")
        return self._charge

    def transcribe(self, audio_path: str, language: str = "fr") -> str:
        segments, _ = self._modele().transcribe(
            audio_path, language=language or None)
        return " ".join(s.text for s in segments).strip()

    def is_available(self) -> bool:
        try:
            import faster_whisper  # noqa: F401
        except ImportError:
            return False
        return True

    def get_name(self) -> str:
        return f"faster-whisper/{self._taille}"


def fournisseurs() -> dict[str, Any]:
    """Les deux fournisseurs locaux, construits mais pas chargés.

    Construire ne coûte rien ; charger coûte neuf secondes. Cette
    séparation est ce qui permet au rapport de capacités d'interroger
    `is_available()` sans payer le chargement d'un modèle que personne
    n'a demandé.
    """
    return {"transcription": WhisperLocal(), "synthese": PiperLocal()}
