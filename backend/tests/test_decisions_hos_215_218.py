"""Les deux décisions du cahier, gardées par du code (HOS-219).

Une décision écrite dans un document se contredit sans bruit six semaines
plus tard. Ces gardes la rendent coûteuse à contredire.

Les décisions elles-mêmes, avec leur raisonnement, vivent dans
`docs/cahier-des-charges-hermes-2.md` §8.
"""

from __future__ import annotations

import io
import re
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parents[2]
CAHIER = RACINE / "docs" / "cahier-des-charges-hermes-2.md"


def _cahier() -> str:
    return io.open(CAHIER, encoding="utf-8").read()


# ── Décision 1 : le pare-feu refuse par défaut ───────────────────────

def test_la_decision_du_pare_feu_est_ecrite():
    """Un défaut qui penche vers le refus doit être une décision assumée.

    L'asymétrie des erreurs le commande : classer trop haut coûte une
    gêne visible et réversible ; classer trop bas envoie un secret chez
    un tiers, définitivement, sans que personne le sache.
    """
    texte = _cahier()
    assert "refuse par défaut" in texte
    assert "le cloud est refusé" in texte


def test_le_refus_doit_etre_nomme_et_contournable_une_fois():
    """Trois garde-fous, sinon la décision devient insupportable à l'usage.

    Un pare-feu qu'on ne peut pas contourner finit par être désarmé
    globalement — ce qui est pire que pas de pare-feu, parce que
    personne ne s'en souvient.
    """
    texte = _cahier()
    for exigence in ("Le refus est nommé", "une fois, explicitement",
                     "Un contournement enseigne"):
        assert exigence in texte, f"garde-fou manquant : {exigence}"


# ── Décision 2 : structurer maintenant, sans authentification ────────

def test_la_decision_de_structuration_est_ecrite():
    texte = _cahier()
    assert "sans authentification" in texte
    assert "user_id" in texte


def test_aucune_authentification_n_est_promise_a_tort():
    """Hermes écoute sur 127.0.0.1 et n'authentifie personne.

    Le dire est honnête ; construire une authentification apparente le
    serait moins. Cette garde tombe le jour où une vraie authentification
    arrive — et c'est le moment de relire la décision.
    """
    routes = list((RACINE / "backend" / "api").rglob("*.py"))
    assert routes, "aucune route trouvée — la garde serait vide"

    reels = []
    for f in routes:
        texte = io.open(f, encoding="utf-8", errors="replace").read()
        # `Depends(...)` avec un vérificateur d'identité : c'est ça, une
        # authentification. Le mot « auth » dans une chaîne de caractères
        # ou un commentaire n'en est pas une.
        if re.search(r"Depends\(\s*(get_current_user|require_auth|verify_token)",
                     texte):
            reels.append(f.name)
    assert not reels, (
        f"une authentification est apparue dans {reels} — relire la "
        "décision §8.2 du cahier avant d'aller plus loin, et notamment "
        "la ligne à ne pas franchir sur `user_id`")


def test_user_id_ne_sert_pas_de_controle_d_acces():
    """La ligne à ne pas franchir.

    Tant qu'il n'y a pas d'authentification, `user_id` est un champ de
    traçabilité que n'importe quel appelant peut poser. Fonder un
    cloisonnement dessus donnerait une sécurité apparente — la tentation
    viendra d'elle-même le jour où quelqu'un voudra séparer deux projets.
    """
    suspects: list[str] = []
    for f in (RACINE / "backend").rglob("*.py"):
        if "tests" in f.parts:
            continue
        texte = io.open(f, encoding="utf-8", errors="replace").read()
        for motif in (r"if\s+.*user_id\s*!=", r"if\s+.*user_id\s*not in",
                      r"assert\s+.*user_id\s*=="):
            if re.search(motif, texte):
                suspects.append(f"{f.relative_to(RACINE)} : {motif}")
    assert not suspects, (
        "un contrôle d'accès semble fondé sur `user_id` : "
        + " | ".join(suspects[:3])
        + " — c'est un champ de traçabilité, pas une identité vérifiée")


# ── Les quatre jalons sont bien documentés ───────────────────────────

@pytest.mark.parametrize("module,jalon", [
    ("backend/core/etat.py", "HOS-215"),
    ("backend/memory/confiance.py", "HOS-216"),
    ("backend/security/derive_workspace.py", "HOS-217"),
    ("backend/security/surveillance_flux.py", "HOS-218"),
])
def test_chaque_jalon_nomme_l_incident_qu_il_empeche(module, jalon):
    """Une règle sans son pourquoi se fait supprimer au premier refactoring."""
    texte = io.open(RACINE / module, encoding="utf-8").read()
    assert jalon in texte
    assert len(texte.split('"""')[1]) > 400, (
        f"{module} n'explique pas assez ce qu'il empêche")
