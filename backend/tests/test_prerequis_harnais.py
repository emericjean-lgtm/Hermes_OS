"""Un agent lancé sans backend est un agent sans outils (HOS-138).

L'incident, mesuré le 2026-08-21 : une session ACP s'ouvre normalement,
l'agent accepte le prompt, puis le tour ne revient jamais. Rien dans le
protocole ne le dit. La cause n'était visible que dans la sortie d'erreur
de l'agent :

    MCP server 'hermes-ollama' failed initial connection after 3 attempts
    [WinError 1225] Le système distant a refusé la connexion réseau
    MCP: registered 0 tool(s) from 0 server(s) (1 failed)

Le backend de Hermes OS était éteint. **La relation est bidirectionnelle** :
Hermes OS lance l'agent, et l'agent rappelle Hermes OS par MCP pour obtenir
ses outils. Backend démarré, le même agent enregistre 16 outils.

Ces tests protègent la seule chose que le module promet : nommer ce qui
manque, avant le blocage plutôt qu'après.
"""
from __future__ import annotations

import sys

from backend.ral.adapters import prerequis_harnais as pre


def _agent_credible(racine):
    """Une installation d'agent minimale mais plausible."""
    (racine / "acp_adapter").mkdir(parents=True)
    scripts = racine / "venv" / "Scripts"
    scripts.mkdir(parents=True)
    (scripts / "python.exe").write_bytes(b"MZ")
    return racine


class TestCeQuiManqueEstNomme:
    """Un « harnais indisponible » sans cause envoie chercher au mauvais
    endroit — c'est exactement ce qui a coûté la séance du 21 août."""

    def test_le_backend_eteint_est_dit_et_explique(self, tmp_path, monkeypatch):
        _agent_credible(tmp_path / "agent")
        config = tmp_path / "config.yaml"
        config.write_text("mcp_servers:\n  hermes-ollama:\n    url: x\n",
                          encoding="utf-8")

        etat = pre.verifier(
            # Port fermé : rien n'écoute, c'est la situation de l'incident.
            url_sante="http://127.0.0.1:1/health",
            racine_agent=str(tmp_path / "agent"),
            chemin_config=str(config))

        assert etat.pret is False
        assert etat.agent_installe and etat.mcp_declare
        assert etat.backend_joignable is False
        # La phrase doit porter le lien de cause : sans MCP, pas d'outils.
        assert "MCP" in etat.explication()

    def test_une_config_sans_mcp_est_dite(self, tmp_path):
        _agent_credible(tmp_path / "agent")
        config = tmp_path / "config.yaml"
        config.write_text("model: x\n", encoding="utf-8")

        etat = pre.verifier(url_sante="http://127.0.0.1:1/health",
                            racine_agent=str(tmp_path / "agent"),
                            chemin_config=str(config))

        assert etat.mcp_declare is False
        assert "sans outils" in etat.explication()

    def test_un_agent_absent_est_dit(self, tmp_path):
        etat = pre.verifier(url_sante="http://127.0.0.1:1/health",
                            racine_agent=str(tmp_path / "nulle-part"),
                            chemin_config=str(tmp_path / "rien.yaml"))

        assert etat.agent_installe is False
        assert "installé" in etat.explication()

    def test_une_config_illisible_ne_leve_pas(self, tmp_path):
        """Ce module est appelé sur un chemin de démarrage : s'il lève, il
        remplace un blocage lisible par une trace."""
        etat = pre.verifier(url_sante="http://127.0.0.1:1/health",
                            racine_agent=str(tmp_path),
                            chemin_config=str(tmp_path / "absent.yaml"))

        assert etat.pret is False


class TestQuandToutEstLa:
    def test_pret_exige_les_trois(self, tmp_path, monkeypatch):
        _agent_credible(tmp_path / "agent")
        config = tmp_path / "config.yaml"
        config.write_text("mcp_servers: {}\n", encoding="utf-8")
        monkeypatch.setattr(pre, "_backend_joignable",
                            lambda url: (True, "HTTP 200"))

        etat = pre.verifier(racine_agent=str(tmp_path / "agent"),
                            chemin_config=str(config))

        assert etat.pret is True
        assert etat.explication() == ""

    def test_une_redirection_compte_comme_joignable(self, monkeypatch):
        """Mesuré : `/mcp` rend 307. Exiger un 200 déclarerait le backend
        absent alors qu'il répond."""
        class _Reponse:
            status_code = 307

        module = type(sys)("requests")
        module.get = lambda url, timeout: _Reponse()
        monkeypatch.setitem(__import__("sys").modules, "requests", module)

        joignable, detail = pre._backend_joignable("http://127.0.0.1:8010/mcp")

        assert joignable is True
        assert "307" in detail


