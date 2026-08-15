"""Un fichier écrit qui ne compile pas doit le dire tout de suite (HOS-121).

L'incident, mesuré sur l'essai Skills360 : la mission a écrit

    \"\"\"Plusieurs Employees peuvent partager le même auth_uid ?\"

— docstring ouverte par trois guillemets, fermée par un seul. `pytest` s'est
arrêté à la collecte, code 2, et la mission a rapporté `success: True`.
Trente minutes se sont écoulées entre l'écriture et le moment où quelqu'un
l'a su, et ce quelqu'un était une mesure manuelle.

Deux raisons pour lesquelles le filet de HOS-119 n'a pas joué : il exige le
niveau d'autonomie `high` alors que la configuration livrée est `medium`, et
il ne tourne qu'à la fin. Cette porte-ci est gratuite, hors politique de
sécurité — elle n'exécute rien — et immédiate.
"""
from __future__ import annotations

import pytest

from backend.tools import syntaxe


class TestCeQuiEstDetecte:
    def test_l_incident_exact_de_l_essai_skills360(self):
        source = '''class T:
    def test_a(self):
        """Plusieurs Employees peuvent partager le même auth_uid ?"
        assert True
'''
        erreur = syntaxe.verdict("test_identity_extended.py", source)

        assert erreur is not None
        assert "ligne" in erreur

    def test_un_python_valide_ne_produit_aucune_erreur(self):
        assert syntaxe.verdict("m.py", "def f(a, b):\n    return a + b\n") is None

    def test_le_json_est_analyse_aussi(self):
        assert syntaxe.verdict("c.json", '{"a": 1}') is None
        assert syntaxe.verdict("c.json", '{"a": 1,}') is not None

    def test_un_octet_nul_ne_passe_pas_pour_du_python_valide(self):
        """`ast.parse` lève `ValueError`, pas `SyntaxError`. Sans la seconde
        branche, un fichier illisible serait déclaré bon."""
        assert syntaxe.verdict("m.py", "x = 1\x00\n") is not None


class TestCeQuiNEstPasAffirme:
    """« Je n'ai pas vérifié » et « c'est bon » sont deux verdicts. Les
    confondre est le défaut central de ce dépôt."""

    def test_une_extension_inconnue_ne_rend_pas_de_verdict(self):
        assert syntaxe.verdict("notes.md", "ceci n'est pas du code {{{") is None

    def test_aucun_message_n_est_ajoute_quand_rien_n_est_analyse(self):
        assert syntaxe.message("notes.md", "{{{ ") == ""

    def test_aucun_message_n_est_ajoute_quand_le_fichier_compile(self):
        """Le retour d'outil ne doit pas se remplir de « tout va bien » :
        le modèle lit ces textes, et le bruit y coûte du contexte."""
        assert syntaxe.message("m.py", "x = 1\n") == ""


class TestLeMessageEstActionnable:
    def test_il_dit_que_le_fichier_est_bien_sur_le_disque(self):
        """Prétendre le contraire serait faux : l'écriture a eu lieu et a
        été vérifiée. C'est la compilation qui a échoué, pas l'écriture."""
        message = syntaxe.message("m.py", "def f(:\n")

        assert "sur le disque" in message

    def test_il_porte_l_erreur_du_compilateur_et_pas_un_resume(self):
        message = syntaxe.message("m.py", 'x = """ouverte\n')

        assert "ligne" in message
        assert "Corrige" in message


class TestSurLeCheminReelDesOutils:
    """La porte ne sert à rien si elle n'est pas sur le trajet d'écriture.

    On passe par `execute_workspace_tool` lui-même — asynchrone, avec ses
    vrais arguments nommés — et on laisse `file_tools` écrire pour de vrai
    dans un `tmp_path`. Seul Aegis est neutralisé, parce qu'il exigerait un
    Project enregistré et validé qui n'a rien à voir avec ce qu'on mesure
    ici. Le premier jet de ce test posait un faux `file_tools` sur le
    module : il aurait pu passer au vert sans qu'une seule ligne du chemin
    réel ne soit exécutée — le défaut même que HOS-121 corrige ailleurs.
    """

    @staticmethod
    def _sans_aegis(monkeypatch, racine):
        from backend.security.aegis_engine import Verdict
        from backend.tools import workspace_chat_tools as outils

        class _Autorise:
            """Le seul contrat que `file_tools` attend d'une décision."""
            verdict = Verdict.ALLOW
            reason = "test"

        class _Aegis:
            def evaluate(self, request):
                return _Autorise()

        monkeypatch.setattr(outils, "_aegis", lambda: _Aegis())
        return outils

    @pytest.mark.asyncio
    async def test_workspace_write_signale_un_python_invalide(
            self, tmp_path, monkeypatch):
        outils = self._sans_aegis(monkeypatch, tmp_path)

        rendu = await outils.execute_workspace_tool(
            "workspace_write", {"path": "m.py", "content": "def f(:\n"},
            project_id="p", project_root=str(tmp_path))

        assert "ne compile pas" in rendu, rendu
        assert "vérifié" in rendu, "l'écriture a bien eu lieu, il faut le dire"
        assert (tmp_path / "m.py").exists(), "le fichier doit rester sur le disque"

    @pytest.mark.asyncio
    async def test_workspace_write_reste_silencieux_sur_du_python_correct(
            self, tmp_path, monkeypatch):
        outils = self._sans_aegis(monkeypatch, tmp_path)

        rendu = await outils.execute_workspace_tool(
            "workspace_write", {"path": "m.py", "content": "x = 1\n"},
            project_id="p", project_root=str(tmp_path))

        assert "ne compile pas" not in rendu, rendu

    @pytest.mark.asyncio
    async def test_un_ajout_qui_casse_un_fichier_valide_est_signale(
            self, tmp_path, monkeypatch):
        """C'est pour ce cas que l'ajout relit le fichier entier : le
        fragment ajouté est valide isolément, le fichier ne l'est plus."""
        outils = self._sans_aegis(monkeypatch, tmp_path)
        (tmp_path / "m.py").write_text("def f():\n    return 1\n",
                                       encoding="utf-8")

        rendu = await outils.execute_workspace_tool(
            "workspace_append", {"path": "m.py", "content": "  return 2\n"},
            project_id="p", project_root=str(tmp_path))

        assert "ne compile pas" in rendu, rendu
