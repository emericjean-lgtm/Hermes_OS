"""Le juge et les vérités-terrain de l'axe raisonnement (HOS-110).

Deux des quatre réponses attendues, posées de tête, étaient fausses. Elles
ont été corrigées par force brute avant qu'un modèle ne voie l'épreuve —
sans quoi la campagne aurait noté en échec tous ceux qui répondaient juste.
Les tests ci-dessous refont cette vérification à chaque exécution : une
vérité-terrain n'est pas un commentaire, c'est une affirmation qui se
démontre.
"""
from __future__ import annotations

import itertools
import math

import pytest

from backend.model_intelligence.reasoning_bench import EPREUVES, juge

ATTENDU = {nom: attendu for nom, _enonce, attendu in EPREUVES}


# ── les vérités-terrain, redémontrées ────────────────────────────────────

def test_l_enigme_de_deduction_a_exactement_une_solution():
    """L'incident : « bruno » avait été posé de tête. La force brute donne
    amel, et une seule disposition satisfait les six contraintes."""
    solutions = []
    for perm in itertools.permutations(PRENOMS := ("amel", "bruno", "chloe", "diego")):
        pos = {p: i + 1 for i, p in enumerate(perm)}
        if pos["chloe"] != pos["amel"] + 2:
            continue
        for metiers in itertools.permutations(
                ("comptable", "juriste", "graphiste", "dev")):
            m = {perm[i]: metiers[i] for i in range(4)}
            dev = next(p for p in m if m[p] == "dev")
            jur = next(p for p in m if m[p] == "juriste")
            gra = next(p for p in m if m[p] == "graphiste")
            if pos[dev] not in (1, 4) or pos[jur] != 3:
                continue
            if m["diego"] != "comptable" or m["amel"] == "dev":
                continue
            if abs(pos["bruno"] - pos[gra]) == 1:
                continue
            solutions.append(gra)

    assert len(solutions) == 1, f"{len(solutions)} solutions — l'énigme est mal posée"
    assert solutions[0] == ATTENDU["deduction"]


def test_l_atelier_rend_bien_479_pieces():
    """L'incident : 475 avait été posé de tête."""
    lundi = 7
    mardi = int(lundi * 1.4)
    mercredi = math.ceil(mardi / 2)
    total = (lundi + mardi + mercredi) * 24
    conformes = total - int(total * 0.05)

    assert conformes == int(ATTENDU["arithmetique"])


def test_l_ordre_temporel_est_le_seul_compatible():
    """La commande d'abord, le paiement juste après l'inspection,
    l'inspection après l'installation, l'installation après la livraison."""
    attendu = ATTENDU["temporel"].split(",")
    rang = {e: i for i, e in enumerate(attendu)}

    assert rang["commande"] == 0
    assert rang["paiement"] == rang["inspection"] + 1
    assert rang["inspection"] > rang["installation"]
    assert rang["installation"] > rang["livraison"]


def test_le_piege_repond_bien_cinq():
    """100 postes en parallèle pour 100 pièces : le temps est celui d'un
    seul cycle. La réponse intuitive — 100 — est fausse, et c'est le but."""
    assert ATTENDU["piege"] == "5"


# ── le juge ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("texte,attendu,veut", [
    ("504 - 25 = 479", "479", True),
    ("Il reste 479 pièces conformes.", "479", True),
    ("Total 504, rebut 25.\n\n**479**", "479", True),
    ("Total 504, rebut 25.\n\n475", "479", False),
    ("La réponse est 475.", "479", False),
    # Limite assumée : le bon nombre est là, mais pas en dernier.
    ("479 pièces conformes sur 504 produites.", "479", False),
])
def test_un_nombre_se_lit_en_fin_de_ligne_de_reponse(texte, attendu, veut):
    assert juge(texte, attendu) is veut


def test_le_piege_ne_se_valide_pas_par_un_cinq_de_calcul():
    """L'incident que ce test empêche : la première règle acceptait « le
    nombre attendu apparaît dans la ligne », et « 100 pièces / 5 = 20
    minutes » contient un 5. Une mauvaise réponse passait."""
    assert not juge("100 pièces / 5 = 20 minutes", "5")
    assert not juge("5 pièces en 5 min, donc 100 pièces en 100 min.", "5")
    assert juge("Chaque poste usine une pièce en 5 minutes.\n\n5", "5")


def test_un_prenom_se_lit_sur_la_ligne_de_conclusion():
    assert juge("Bruno est développeur, Diego comptable.\n\nAmel", "amel")
    assert not juge("Le graphiste est Bruno.", "amel")
    assert not juge("Amel est en 1, Chloe en 3.\n\nRéponse : Bruno", "amel")


def test_une_sequence_doit_etre_complete_et_dans_l_ordre():
    bon = "commande, livraison, installation, inspection, paiement"
    assert juge(f"L'installation suit la livraison.\n{bon}", ATTENDU["temporel"])
    assert not juge("commande, livraison, inspection, installation, paiement",
                    ATTENDU["temporel"])


def test_une_reponse_vide_echoue():
    """Un modèle qui a passé tout son budget dans son raisonnement rend un
    contenu vide — mesuré à 130 951 tokens sur qwen3.5-2b, sans un seul
    caractère de réponse."""
    for attendu in ATTENDU.values():
        assert not juge("", attendu)
        assert not juge("  \n\n ", attendu)
