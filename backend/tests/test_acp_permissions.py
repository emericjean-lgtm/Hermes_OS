"""L'agent peut écrire hors du workspace si on l'y autorise (HOS-137).

L'incident, mesuré le 2026-08-21 en branchant Hermes Agent en session ACP :

* session ouverte sur `C:\\...\\Temp\\perm_i307s8wt` ;
* l'agent demande la permission d'écrire `/Users/emeri/note.txt` ;
* la permission est accordée — sans regarder le chemin ;
* le fichier apparaît dans `C:\\Users\\emeri\\`, **hors du workspace**,
  pendant que le dossier confié reste vide.

La justification écrite dans la première version du module était fausse, et
la mesure l'a démentie en une heure :

    « Autoriser ici n'ouvre aucune porte. Le workspace est déjà contraint
      par le `cwd` de la session. »

**Le `cwd` d'une session ACP oriente l'agent ; il ne le contraint pas.** Et
rien en aval ne rattrape : l'agent écrit par ses propres outils, sans
repasser par Aegis ni `file_tools`. La frontière est dans le répondeur de
permissions, et nulle part ailleurs.

Le piège technique est le même que celui qui a coûté cinq correctifs côté
Hermes OS (HOS-129 à 133) : `/Users/emeri/note.txt` est **rooté sans lettre
de lecteur**, donc `Path.is_absolute()` rend `False` sous Windows. Un test
naïf le prendrait pour un chemin relatif et le croirait dans le workspace.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from backend.ral.adapters.hermes_agent_acp import HermesAgentACP, SessionAgent, Tour


@pytest.fixture
def session(tmp_path):
    espace = tmp_path / "workspace"
    espace.mkdir()
    return SessionAgent(cwd=str(espace))


def _demande(chemin: str) -> dict:
    return {"toolCall": {"content": [{"type": "diff", "path": chemin,
                                      "newText": "x"}]}}


class TestLaFrontiereDuWorkspace:
    def test_le_chemin_qui_s_est_reellement_echappe(self, session):
        """`/Users/emeri/note.txt` — rooté, sans lettre de lecteur. C'est
        le chemin exact qui a produit un fichier hors du workspace."""
        motif = HermesAgentACP._hors_workspace(session, _demande("/Users/emeri/note.txt"))

        assert motif, "ce chemin doit être refusé"
        assert "hors de" in motif

    def test_un_absolu_hors_racine_est_refuse(self, session):
        assert HermesAgentACP._hors_workspace(
            session, _demande("C:/Windows/system32/x.dll"))

    def test_une_remontee_est_refusee(self, session):
        """`..` résout hors du workspace ; le refus doit venir du chemin
        résolu, pas d'une recherche de motif dans la chaîne."""
        assert HermesAgentACP._hors_workspace(session, _demande("../../evade.txt"))

    def test_un_rooted_a_l_antislash_aussi(self, session):
        assert HermesAgentACP._hors_workspace(
            session, _demande(chr(92) + "Users" + chr(92) + "emeri" + chr(92) + "x.txt"))


class TestCeQuiResteAutorise:
    """Refuser trop bloquerait l'agent sur son propre travail — et un faux
    refus coûte autant qu'une fuite, à ceci près qu'il se voit."""

    def test_un_relatif_dans_le_workspace_passe(self, session):
        assert HermesAgentACP._hors_workspace(
            session, _demande("src/models/a.py")) == ""

    def test_un_absolu_dans_le_workspace_passe(self, session):
        cible = str(Path(session.cwd) / "note.txt")

        assert HermesAgentACP._hors_workspace(session, _demande(cible)) == ""

    def test_une_demande_sans_chemin_passe(self, session):
        """Un outil qui ne touche à aucun fichier n'a rien à situer."""
        assert HermesAgentACP._hors_workspace(
            session, {"toolCall": {"content": []}}) == ""

    def test_un_workspace_illisible_refuse_plutot_que_d_autoriser(self):
        """Ne pas savoir n'est pas une raison d'autoriser."""
        motif = HermesAgentACP._hors_workspace(
            SessionAgent(cwd="\x00illisible"), _demande("a.py"))

        assert motif


class TestLeTour:
    """`abouti` exige les deux conditions : ni l'une ni l'autre seule ne
    suffit — un tour interrompu porte du texte partiel, un tour vide peut
    s'annoncer terminé."""

    @pytest.mark.parametrize("tour,attendu", [
        (Tour(), False),
        (Tour(texte="x", stop="end_turn"), True),
        (Tour(texte="x", stop="cancelled"), False),
        (Tour(texte="   ", stop="end_turn"), False),
    ])
    def test_abouti(self, tour, attendu):
        assert tour.abouti is attendu


class TestLAssemblageDuTour:
    def test_le_texte_vient_des_notifications_pas_du_resultat(self):
        """Le résultat JSON-RPC ne porte que `stopReason` et `usage`. Une
        première sonde qui ignorait les notifications a conclu « la session
        ne tient pas » alors qu'elle tenait."""
        notifications = [
            {"params": {"update": {"sessionUpdate": "agent_message_chunk",
                                   "content": {"type": "text", "text": "BON"}}}},
            {"params": {"update": {"sessionUpdate": "agent_thought_chunk",
                                   "content": {"type": "text", "text": "je pense"}}}},
            {"params": {"update": {"sessionUpdate": "agent_message_chunk",
                                   "content": {"type": "text", "text": "JOUR"}}}},
        ]

        tour = HermesAgentACP.lire(
            {"result": {"stopReason": "end_turn",
                        "usage": {"inputTokens": 100, "outputTokens": 7}}},
            notifications)

        assert tour.texte == "BONJOUR"
        assert tour.pensee == "je pense"
        assert tour.jetons_entree == 100
        assert tour.abouti

    def test_le_raisonnement_ne_pollue_pas_la_reponse(self):
        """Mesuré : 256 morceaux de pensée pour 7 de réponse sur une
        question triviale. Les mélanger noierait la réponse."""
        notifications = [
            {"params": {"update": {"sessionUpdate": "agent_thought_chunk",
                                   "content": {"type": "text", "text": "bla"}}}}
            for _ in range(50)
        ]

        tour = HermesAgentACP.lire({"result": {"stopReason": "end_turn"}},
                                   notifications)

        assert tour.texte == ""
        assert len(tour.pensee) == 150
        assert tour.abouti is False


class TestLaDisponibilite:
    def test_elle_dit_pourquoi_elle_refuse(self, tmp_path):
        """Un appelant doit pouvoir **dire** pourquoi il retombe sur le
        mode jetable, au lieu de le faire en silence."""
        ok, raison = HermesAgentACP(racine=str(tmp_path)).disponible()

        assert ok is False
        assert "interpréteur" in raison or "acp_adapter" in raison


class TestLaGraphieGitBash:
    """Un faux refus coûte autant qu'une fuite (HOS-138).

    L'agent fait passer ses outils fichier par Git Bash sous Windows : il
    produit donc `/c/Users/...`, la graphie MSYS d'un lecteur. La frontière
    résolvait ce chemin contre la racine du lecteur et obtenait un segment
    `c` parasite — hors du workspace, donc refusé.

    Mesuré le 2026-08-21 sur une mission réelle : **trois refus
    consécutifs** sur une écriture parfaitement légitime, dans le workspace
    confié. L'agent a fini par contourner et le fichier a été écrit, si
    bien que le verdict final était vert et le défaut invisible — il n'était
    lisible que dans le journal.
    """

    def test_le_chemin_msys_du_workspace_est_accepte(self, session):
        espace = Path(session.cwd)
        lecteur = espace.drive.rstrip(":").lower()
        msys = "/" + lecteur + "/" + str(espace)[3:].replace(chr(92), "/") + "/notes.md"

        assert HermesAgentACP._hors_workspace(session, _demande(msys)) == ""

    def test_un_dossier_systeme_en_graphie_msys_reste_refuse(self, session):
        """La traduction ne relâche rien : elle précède la vérification,
        elle ne la remplace pas."""
        assert HermesAgentACP._hors_workspace(
            session, _demande("/c/Windows/system32/x.dll"))

    def test_un_chemin_posix_a_plusieurs_lettres_n_est_pas_un_lecteur(self):
        """`/etc/passwd` ne doit pas devenir un lecteur `E:`. Le motif exige
        une lettre unique, sans quoi la traduction inventerait des disques."""
        from backend.ral.adapters.hermes_agent_acp import _depuis_msys

        assert _depuis_msys("/etc/passwd") == "/etc/passwd"
        assert _depuis_msys("/Users/emeri/note.txt") == "/Users/emeri/note.txt"

    def test_le_motif_du_refus_cite_le_chemin_recu(self, session):
        """Traduit, le chemin ne ressemble plus à ce que l'agent a demandé.
        Un journal qui cite la forme interne envoie chercher un chemin que
        personne n'a écrit."""
        motif = HermesAgentACP._hors_workspace(
            session, _demande("/c/Windows/system32/x.dll"))

        assert "/c/Windows" in motif
