"""GET /filesystem/browse — read-only, directories-only local browsing for
the "add a workspace" folder picker (Workspace/Filesystem tool layer,
Phase 10). Not Aegis-gated by design (see workspace_browse.py's module
docstring); these tests cover its own, narrower safety boundary instead:
directories only, no file contents, no descending into system paths.
"""
from __future__ import annotations


def test_browse_with_no_path_returns_starting_points(client):
    response = client.get("/filesystem/browse")

    assert response.status_code == 200
    body = response.json()
    assert body["path"] is None
    assert isinstance(body["directories"], list)
    assert len(body["directories"]) > 0


def test_browse_lists_real_subdirectories(client, tmp_path):
    # tmp_path also backs this test run's SQLITE_PATH/CHROMA_PATH (see
    # conftest.py's client fixture), so other real subdirectories the app
    # itself created (e.g. "chroma") may legitimately already be there —
    # assert the two directories we made are present, not an exact list.
    (tmp_path / "alpha").mkdir()
    (tmp_path / "beta").mkdir()
    (tmp_path / "a_file.txt").write_text("not a directory")

    response = client.get("/filesystem/browse", params={"path": str(tmp_path)})

    assert response.status_code == 200
    body = response.json()
    assert body["path"] == str(tmp_path.resolve())
    assert "alpha" in body["directories"]
    assert "beta" in body["directories"]
    assert "a_file.txt" not in body["directories"]


def test_browse_never_returns_file_contents(client, tmp_path):
    (tmp_path / "secret.txt").write_text("do not leak this")

    response = client.get("/filesystem/browse", params={"path": str(tmp_path)})

    assert "do not leak this" not in response.text
    assert "secret.txt" not in response.json()["directories"]


class TestPickFolderDialogueNatif:
    """POST /filesystem/pick-folder — corrige la liste illisible signalée
    par l'opérateur en ouvrant un vrai dialogue Windows (le backend tourne
    sur la même machine que le navigateur du Cockpit). Le dialogue lui-même
    n'est jamais réellement ouvert ici : `_ouvrir_dialogue_natif`, seul
    point qui lance PowerShell, est remplacé — ces tests couvrent le
    contrat de la route, pas le rendu d'une fenêtre Windows.
    """

    def test_un_chemin_choisi_est_rendu(self, client, monkeypatch):
        from backend.api.routes import workspace_browse

        monkeypatch.setattr(workspace_browse, "platform",
                            type("P", (), {"system": staticmethod(lambda: "Windows")}))
        monkeypatch.setattr(workspace_browse, "_ouvrir_dialogue_natif",
                            lambda start_dir: r"C:\Users\emeri\mon-projet")

        response = client.post("/filesystem/pick-folder", json={})

        assert response.status_code == 200
        body = response.json()
        assert body["path"] == r"C:\Users\emeri\mon-projet"
        assert body["cancelled"] is False

    def test_annuler_n_est_pas_une_erreur(self, client, monkeypatch):
        """Fermer le dialogue sans choisir est un résultat normal, pas un
        échec — `path: None`, `cancelled: True`, jamais un statut 4xx/5xx."""
        from backend.api.routes import workspace_browse

        monkeypatch.setattr(workspace_browse, "platform",
                            type("P", (), {"system": staticmethod(lambda: "Windows")}))
        monkeypatch.setattr(workspace_browse, "_ouvrir_dialogue_natif",
                            lambda start_dir: None)

        response = client.post("/filesystem/pick-folder", json={})

        assert response.status_code == 200
        body = response.json()
        assert body["path"] is None
        assert body["cancelled"] is True

    def test_un_dialogue_oublie_devient_une_annulation(self, client, monkeypatch):
        """Le sous-processus a son propre délai (10 min) : s'il expire, la
        route ne doit pas planter, elle traite ça comme une annulation."""
        import subprocess

        from backend.api.routes import workspace_browse

        def _expire(start_dir):
            raise subprocess.TimeoutExpired(cmd="powershell", timeout=600.0)

        monkeypatch.setattr(workspace_browse, "platform",
                            type("P", (), {"system": staticmethod(lambda: "Windows")}))
        monkeypatch.setattr(workspace_browse, "_ouvrir_dialogue_natif", _expire)

        response = client.post("/filesystem/pick-folder", json={})

        assert response.status_code == 200
        assert response.json() == {"path": None, "cancelled": True}

    def test_hors_windows_repond_501_pas_une_erreur_muette(self, client, monkeypatch):
        """Le repli côté frontend (`DirectoryBrowser`) déclenche sur une
        erreur — un 200 avec un chemin vide serait pris pour une
        annulation et cacherait que le dialogue natif n'existe pas ici."""
        from backend.api.routes import workspace_browse

        monkeypatch.setattr(workspace_browse, "platform",
                            type("P", (), {"system": staticmethod(lambda: "Linux")}))

        response = client.post("/filesystem/pick-folder", json={})

        assert response.status_code == 501

    def test_le_dossier_de_depart_est_transmis(self, client, monkeypatch):
        """Rouvrir le dialogue là où l'opérateur en était, pas toujours au
        même endroit par défaut."""
        from backend.api.routes import workspace_browse

        recu = {}

        def _capture(start_dir):
            recu["start_dir"] = start_dir
            return None

        monkeypatch.setattr(workspace_browse, "platform",
                            type("P", (), {"system": staticmethod(lambda: "Windows")}))
        monkeypatch.setattr(workspace_browse, "_ouvrir_dialogue_natif", _capture)

        client.post("/filesystem/pick-folder", json={"start_dir": r"D:\projets"})

        assert recu["start_dir"] == r"D:\projets"


def test_browse_missing_path_returns_404(client, tmp_path):
    response = client.get("/filesystem/browse", params={"path": str(tmp_path / "nope")})

    assert response.status_code == 404


def test_browse_file_not_directory_returns_400(client, tmp_path):
    f = tmp_path / "file.txt"
    f.write_text("hi")

    response = client.get("/filesystem/browse", params={"path": str(f)})

    assert response.status_code == 400


def test_browse_refuses_windows_system_directory(client):
    import platform
    if platform.system() != "Windows":
        return
    response = client.get("/filesystem/browse", params={"path": "C:\\Windows"})
    assert response.status_code == 403


def test_browse_parent_points_back_up(client, tmp_path):
    child = tmp_path / "child"
    child.mkdir()

    response = client.get("/filesystem/browse", params={"path": str(child)})

    assert response.json()["parent"] == str(tmp_path.resolve())
