"""Un fichier rendu doit être ouvrable (HOS-191).

L'historique de ComfyUI décrit ses sorties par `{filename, subfolder,
type}`. Aucun des trois ne désigne un fichier : la racine est dans les
arguments de lancement du serveur, qui écrit ici sur `E:`.

La première version ne gardait que `filename`. Le relecteur recevait donc
`rue_sodium_00001_.mp4`, n'en tirait aucune image, et le plan finissait
`indetermine` — alors que le rendu avait parfaitement abouti, 309 s et
7,61 Gio sur la carte, mesuré le 2026-08-27.

Ce défaut n'a rien fait tomber, et c'est ce qui le rend intéressant : la
file a dit « je n'ai pas pu vérifier » au lieu de « c'est réussi », ce qui
était exactement le comportement voulu. Il a donc fallu lire le rapport
pour le voir. Un chemin qui ne mène nulle part ne lève pas.
"""

from __future__ import annotations

import os

from backend.studio.comfyui import ComfyUI, EtatComfy, _fichiers_de

HISTORIQUE = {
    "outputs": {
        "14": {"images": [{"filename": "rue_sodium_00001_.mp4",
                           "subfolder": "nuit", "type": "output"}]}
    }
}


def test_le_chemin_rendu_porte_la_racine_et_le_sous_dossier():
    chemins = _fichiers_de(HISTORIQUE, r"E:\YouTube\Generations")
    assert chemins == [os.path.join(r"E:\YouTube\Generations", "nuit",
                                    "rue_sodium_00001_.mp4")]


def test_sans_racine_le_sous_dossier_est_quand_meme_conserve():
    """Perdre `subfolder` remettrait tous les plans à plat.

    La file écrit dans `nuit/`, les bancs dans `banc/` : deux plans
    homonymes de deux campagnes deviendraient le même fichier.
    """
    assert _fichiers_de(HISTORIQUE) == [os.path.join("nuit",
                                                     "rue_sodium_00001_.mp4")]


def test_une_sortie_sans_nom_de_fichier_est_ignoree():
    """Certains nœuds rendent des métadonnées, pas des fichiers."""
    assert _fichiers_de({"outputs": {"9": {"texte": [{"valeur": "x"}]}}}) == []


def test_la_racine_est_lue_dans_les_arguments_de_lancement(monkeypatch):
    """Lue, pas supposée.

    Supposer `<comfy>/output` rendrait un chemin qui **existe** mais où
    rien n'arrive jamais — plus trompeur qu'un chemin absent, puisqu'il
    passerait tous les tests d'existence.
    """
    comfy = ComfyUI()
    monkeypatch.setattr(comfy, "etat", lambda: EtatComfy(
        joignable=True,
        arguments=("main.py", "--use-quad-cross-attention",
                   "--output-directory", r"E:\YouTube\Generations",
                   "--port", "8188")))
    assert comfy.dossier_sortie() == r"E:\YouTube\Generations"


def test_sans_argument_de_sortie_la_racine_est_vide(monkeypatch):
    """Vide et non deviné : l'appelant doit pouvoir voir qu'on ne sait pas."""
    comfy = ComfyUI()
    monkeypatch.setattr(comfy, "etat", lambda: EtatComfy(
        joignable=True, arguments=("main.py", "--port", "8188")))
    assert comfy.dossier_sortie() == ""


def test_un_drapeau_de_sortie_sans_valeur_ne_leve_pas(monkeypatch):
    """`--output-directory` en dernière position n'a pas de suivant."""
    comfy = ComfyUI()
    monkeypatch.setattr(comfy, "etat", lambda: EtatComfy(
        joignable=True, arguments=("main.py", "--output-directory")))
    assert comfy.dossier_sortie() == ""
