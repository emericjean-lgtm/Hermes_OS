"""Un rôle configuré sur un modèle absent (HOS-108).

L'incident : le tri des modèles a ramené 21 tags à 11 en inscrivant le
contexte réel dans chaque nom, et `config/models.yaml` n'a pas suivi. Onze
rôles sur douze pointaient vers un tag disparu.

La panne n'avait d'erreur nulle part où quelqu'un regardait. Ollama
répondait 404 sur `/api/chat` ; la route de chat enregistrait bien
`result="failed"` puis relevait l'exception — mais une réponse en flux
envoie son statut HTTP avant le premier fragment, donc le client voyait
200 et un corps vide. L'onglet Assistant affichait le silence.

La comparaison est pure : un test qui exigerait des modèles réellement
installés mesurerait la machine qui l'exécute, pas le code.
"""
from __future__ import annotations

from backend.runtime.model_guard import (
    check_residency, check_roles, normalise, report, report_residency,
)


def test_un_role_sur_un_modele_absent_est_signale():
    manquants = check_roles({"code": {"model": "qwen3.6:27b"}},
                            ["gpt-oss-20b-64k:latest"])

    assert [(m.role, m.model) for m in manquants] == [("code", "qwen3.6:27b")]


def test_un_role_sur_un_modele_installe_ne_l_est_pas():
    assert check_roles({"code": {"model": "gpt-oss-20b-64k"}},
                       ["gpt-oss-20b-64k:latest"]) == []


def test_le_suffixe_latest_ne_fait_pas_croire_a_une_absence():
    """Ollama liste ses tags avec un `:latest` explicite qu'un fichier de
    configuration n'écrit presque jamais. Comparer les chaînes brutes ferait
    passer tout rôle correctement configuré pour manquant — un garde-fou qui
    crie sur une installation saine se fait désactiver."""
    assert check_roles({"a": {"model": "ornith-9b-256k"}},
                       ["ornith-9b-256k:latest"]) == []
    assert check_roles({"a": {"model": "ornith-9b-256k:latest"}},
                       ["ornith-9b-256k:latest"]) == []


def test_normalise_ne_touche_pas_un_tag_explicite():
    """`qwen3-embedding:0.6b` porte une vraie étiquette de version, pas un
    `latest` implicite : la retirer inventerait un modèle qui n'existe pas."""
    assert normalise("qwen3-embedding:0.6b") == "qwen3-embedding:0.6b"


def test_les_roles_manquants_sortent_dans_l_ordre_du_fichier():
    """Pour que le rapport se lise à côté du fichier qu'il concerne."""
    manquants = check_roles(
        {"swift": {"model": "absent-a"}, "standard": {"model": "present"},
         "code": {"model": "absent-b"}},
        ["present"])

    assert [m.role for m in manquants] == ["swift", "code"]


def test_un_role_sans_modele_est_manquant():
    """Une clé `model` oubliée doit se voir, pas passer pour valide."""
    assert [m.role for m in check_roles({"code": {}}, ["present"])] == ["code"]


def test_la_remediation_nomme_le_role_et_le_tag():
    """« un modèle manque quelque part » ne se corrige pas ; « le rôle code
    pointe vers qwen3.6:27b » se corrige."""
    (manquant,) = check_roles({"code": {"model": "qwen3.6:27b"}}, ["autre"])
    remediation = manquant.as_event()["remediation"]

    assert "code" in remediation and "qwen3.6:27b" in remediation


def test_rien_a_signaler_rend_faux_et_ne_publie_rien():
    publies = []
    assert report([], publish=lambda *a: publies.append(a)) is False
    assert publies == []


def test_chaque_role_manquant_produit_son_propre_evenement():
    """Un compteur ne se corrige pas non plus : il faut une ligne par rôle."""
    publies = []
    manquants = check_roles(
        {"a": {"model": "x"}, "b": {"model": "y"}}, ["z"])

    assert report(manquants, publish=lambda nom, charge: publies.append(charge)) is True
    assert [p["role"] for p in publies] == ["a", "b"]


# ── résidence demandée contre résidence accordée ─────────────────────────

PINS = {"swift": {"model": "a", "always_loaded": True},
        "embedding": {"model": "b", "always_loaded": True},
        "code": {"model": "c"}}


def test_deux_roles_epingles_sur_un_seul_emplacement_est_une_contradiction():
    """L'incident. `always_loaded: true` envoie `keep_alive: -1`, ce qui
    empêche l'expiration par inactivité — mais pas l'éviction par un autre
    modèle. Avec OLLAMA_MAX_LOADED_MODELS=1, la configuration décrivait
    deux modèles chauds en permanence quand chaque requête évinçait le
    précédent."""
    assert check_residency(PINS, max_loaded=1) == ["swift", "embedding"]


def test_assez_d_emplacements_ne_signale_rien():
    assert check_residency(PINS, max_loaded=2) == []
    assert check_residency(PINS, max_loaded=3) == []


def test_une_limite_inconnue_ne_declenche_pas_d_alerte():
    """La variable est celle du serveur Ollama, pas forcément la nôtre.
    Deviner entraînerait à ignorer l'avertissement — même règle que
    ContextCheck, qui se tait quand aucun modèle n'est résident."""
    assert check_residency(PINS, max_loaded=None) == []
    assert check_residency(PINS, max_loaded=0) == []


def test_aucun_role_epingle_ne_signale_rien():
    assert check_residency({"code": {"model": "c"}}, max_loaded=1) == []


def test_le_message_nomme_la_variable_et_les_roles():
    publies = []
    assert report_residency(["swift", "embedding"], 1,
                            publish=lambda _n, charge: publies.append(charge)) is True
    assert publies[0]["roles"] == ["swift", "embedding"]
    assert publies[0]["max_loaded"] == 1


def test_rien_a_signaler_en_residence_rend_faux():
    assert report_residency([], 1) is False


def test_une_panne_de_telemetrie_ne_masque_pas_le_signal():
    """Le journal est le canal qui compte ; publier est un supplément."""
    manquants = check_roles({"a": {"model": "x"}}, ["z"])

    def publier_casse(*_a, **_k):
        raise RuntimeError("bus indisponible")

    assert report(manquants, publish=publier_casse) is True
