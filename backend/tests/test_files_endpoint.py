from __future__ import annotations

# These exercise the deny path via HTTP: tmp_path is virtually guaranteed
# not to be inside the real ALLOWED_PATHS the test app loads from .env, so
# every request here is expected to be blocked by Aegis. The ALLOW path
# (whitelist hit + autonomy gating) is already covered thoroughly at the
# file_tools unit level in test_file_tools.py, with a controlled whitelist.


def test_list_files_denied_outside_whitelist(client, tmp_path):
    response = client.get("/files", params={"path": str(tmp_path)})
    assert response.status_code == 403


def test_file_content_denied_outside_whitelist(client, tmp_path):
    f = tmp_path / "f.txt"
    f.write_text("hi")
    response = client.get("/files/content", params={"path": str(f)})
    assert response.status_code == 403


def test_diff_denied_outside_whitelist(client, tmp_path):
    response = client.post(
        "/files/diff", json={"path": str(tmp_path / "f.txt"), "new_content": "hi"}
    )
    assert response.status_code == 403


def test_apply_denied_outside_whitelist_returns_200_with_deny_verdict(client, tmp_path):
    target = tmp_path / "f.txt"
    response = client.post(
        "/files/apply", json={"path": str(target), "new_content": "hi"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["applied"] is False
    assert body["verdict"] == "deny"
    assert not target.exists()
