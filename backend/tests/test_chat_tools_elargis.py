"""L'Assistant voit enfin ce que Hermes OS sait déjà faire (HOS-115).

Le serveur MCP exposait douze opérations fichier à l'agent ; le chat en
offrait quatre. Renommer un fichier depuis la conversation était
impossible alors que `file_tools.move` existait, marchait, et passait déjà
par une validation humaine.

Ces tests portent sur deux choses, et pas sur les opérations elles-mêmes
(couvertes par test_file_tools) : que la porte de sécurité tienne, et que
le compte rendu fait au modèle ne mente jamais.
"""
from __future__ import annotations

import pytest

from backend.tools.file_tools import FileOpResult
from backend.tools.workspace_chat_tools import _rendre, workspace_tool_schemas


def _resultat(**champs) -> FileOpResult:
    base = {"success": True, "operation": "move", "path": "/x",
            "verdict": "allow", "reason": "", "verified": True}
    return FileOpResult(**{**base, **champs})


class TestLaPorteDeSecurite:
    def test_sans_projet_lie_aucun_outil_de_fichier(self):
        """C'est la garantie de ce chemin, pas un détail d'ergonomie : sans
        workspace actif et validé, le modèle ne se voit offrir aucun accès
        au disque."""
        from backend.conversation.routes import _conversation_tools

        assert [t["function"]["name"] for t in _conversation_tools(None)] == ["web_search"]

    def test_un_projet_lie_ouvre_les_fichiers_et_les_runners(self):
        from backend.conversation.routes import _conversation_tools

        noms = {t["function"]["name"] for t in _conversation_tools("C:/un/projet")}

        assert "workspace_move" in noms      # le renommage, absent jusqu'ici
        assert "verification_run" in noms    # npm test, absent jusqu'ici
        assert "web_search" in noms

    def test_les_runners_sont_soumis_a_la_meme_condition_que_les_fichiers(self):
        """Ils s'exécutent *dans* le workspace lié : sans projet, il n'y a
        pas de répertoire où lancer quoi que ce soit."""
        from backend.conversation.routes import _conversation_tools

        noms = {t["function"]["name"] for t in _conversation_tools(None)}
        assert not [n for n in noms if n.startswith("verification_")]


class TestLesSchemas:
    def test_les_douze_operations_fichier_sont_offertes(self):
        attendus = {
            "workspace_list", "workspace_exists", "workspace_read", "workspace_write",
            "workspace_search", "workspace_stat", "workspace_mkdir", "workspace_append",
            "workspace_copy", "workspace_move", "workspace_delete",
        }
        assert {t["function"]["name"] for t in workspace_tool_schemas()} == attendus

    def test_aucun_nom_en_double(self):
        """Deux schémas de même nom : le modèle en verrait un seul, et
        lequel dépendrait de l'ordre."""
        noms = [t["function"]["name"] for t in workspace_tool_schemas()]
        assert len(noms) == len(set(noms))

    @pytest.mark.parametrize("outil", workspace_tool_schemas(), ids=lambda t: t["function"]["name"])
    def test_chaque_outil_decrit_tous_ses_parametres(self, outil):
        """Un paramètre requis sans description laisse le modèle deviner ce
        qu'il doit y mettre."""
        params = outil["function"]["parameters"]
        for nom in params["required"]:
            assert params["properties"][nom].get("description"), nom

    def test_copy_et_move_demandent_source_et_destination(self):
        par_nom = {t["function"]["name"]: t for t in workspace_tool_schemas()}
        for nom in ("workspace_copy", "workspace_move"):
            requis = par_nom[nom]["function"]["parameters"]["required"]
            assert set(requis) == {"source", "destination"}, nom


class TestLeCompteRenduNeMentJamais:
    """La règle centrale du dépôt, appliquée à ce que le modèle lit :
    `success` est ce que le code croit avoir fait, `verified` ce qu'une
    relecture a constaté. Les confondre, c'est fabriquer un succès."""

    def test_une_operation_refusee_se_dit_refusee_avec_son_motif(self):
        rendu = _rendre(_resultat(success=False, verdict="require_human_validation",
                                  reason="en attente de validation"), "Déplacé")

        assert "Refusé" in rendu
        assert "require_human_validation" in rendu
        assert "en attente de validation" in rendu
        assert "Déplacé" not in rendu

    def test_une_operation_non_verifiee_n_est_pas_annoncee_reussie(self):
        rendu = _rendre(_resultat(verified=False), "Déplacé")

        assert "PAS pu être vérifiée" in rendu
        assert "Déplacé" not in rendu

    def test_seule_une_operation_verifiee_s_annonce_reussie(self):
        assert _rendre(_resultat(), "Déplacé : a -> b") == "Déplacé : a -> b"

    def test_le_champ_lu_est_bien_celui_de_FileOpResult(self):
        """La première version lisait `applied` — le champ de
        `propose_write`, pas celui-ci — via un `getattr` de repli. Chaque
        mkdir, copy et delete aurait été rapporté « refusé » sans que rien
        ne le signale."""
        assert not hasattr(_resultat(), "applied")
        assert _rendre(_resultat(), "ok") == "ok"
