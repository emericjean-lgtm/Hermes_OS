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
