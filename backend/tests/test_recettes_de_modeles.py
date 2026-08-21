"""Un tag perdu ne doit pas être un modèle perdu (HOS-140).

Aucun modèle du catalogue n'existe sous son nom chez son éditeur : chaque
tag est **construit** par un Modelfile qui relève `num_ctx`, parce que
l'endpoint `/v1` qu'emprunte Hermes Agent ne transporte pas ce paramètre.
C'est donc dans le Modelfile, et nulle part ailleurs, que la fenêtre se
décide.

Ces recettes n'étaient écrites nulle part. Quand `ornith-9b-256k` a été
supprimé d'Ollama par erreur, plus rien dans le dépôt ne disait de quel
modèle de base il dérivait ni avec quelle quantification — il a fallu le
retrouver par recherche, puis déduire la quantification de la taille
affichée (6,6 Go → Q5_K_M, la seule des cinq qui tombe juste).

Ce test ne vérifie pas que les recettes sont justes : seul Ollama peut le
dire, et la suite est hermétique. Il vérifie qu'elles **existent** et
qu'elles portent ce qui a manqué le jour où l'une a été perdue.
"""
from __future__ import annotations

import io
from pathlib import Path

import pytest
import yaml

RECETTES = Path("config/modelfiles")


def _catalogue() -> dict:
    return yaml.safe_load(io.open("config/models.yaml", encoding="utf-8").read())


def _recettes_presentes() -> dict[str, str]:
    if not RECETTES.is_dir():
        return {}
    return {c.stem: c.read_text(encoding="utf-8")
            for c in RECETTES.glob("*.Modelfile")}


class TestLaRecetteDuRoleStandard:
    """Le rôle le plus sollicité, et celui dont la recette a manqué."""

    def test_elle_existe(self):
        assert "ornith-9b-256k" in _recettes_presentes(), (
            "la recette du modèle du rôle `standard` doit être versionnée : "
            "sans elle, une suppression accidentelle est irréversible")

    def test_elle_nomme_son_modele_de_base(self):
        """Le `FROM` est la seule information qu'aucune autre source ne
        porte. Sans lui, reconstruire demande une recherche."""
        recette = _recettes_presentes()["ornith-9b-256k"]

        lignes_from = [l for l in recette.splitlines()
                       if l.strip().upper().startswith("FROM ")]

        assert lignes_from, "aucun FROM : la recette ne dit pas d'où elle part"
        assert "Ornith-1.0-9B" in lignes_from[0]
        # La quantification decide de la taille et de la VRAM. L'omettre
        # laisserait choisir entre cinq variantes de 5,63 a 17,9 Gio.
        assert "Q5_K_M" in lignes_from[0]

    def test_elle_releve_le_contexte(self):
        """`num_ctx` est la raison d'être de ces tags : Ollama sert sa
        valeur par défaut tant qu'un Modelfile ne la relève pas, et `/v1`
        ne permet pas de la passer par requête."""
        recette = _recettes_presentes()["ornith-9b-256k"]
        catalogue = _catalogue()["roles"]["standard"]

        assert f"num_ctx {catalogue['num_ctx']}" in recette, (
            "le contexte de la recette doit être celui que le catalogue "
            "annonce, sinon les mesures du catalogue portent sur autre chose")


class TestLaCoherenceAvecLeCatalogue:
    def test_une_recette_correspond_a_un_role_connu(self):
        """Une recette orpheline signale un tag qu'on croit servir et que
        plus aucun rôle n'emploie — ou un renommage à moitié fait."""
        modeles = {spec.get("model") for spec in
                   _catalogue()["roles"].values()}

        for nom in _recettes_presentes():
            assert nom in modeles, (
                f"la recette {nom!r} ne correspond à aucun rôle du catalogue")

    @pytest.mark.parametrize("marqueur", ["RENDERER", "PARSER"])
    def test_le_formatage_de_tour_est_explicite(self, marqueur):
        """`TEMPLATE {{ .Prompt }}` seul envoie le prompt brut : ni balises
        de tour, ni extraction du raisonnement et des appels d'outils.
        Ollama ne les pose pas pour un GGUF tiré de HuggingFace — mesuré,
        le Modelfile généré ne portait que le template pass-through."""
        assert marqueur in _recettes_presentes()["ornith-9b-256k"]
