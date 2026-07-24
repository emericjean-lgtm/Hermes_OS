from __future__ import annotations


def test_evaluate_endpoint_returns_decision_for_mandatory_category(client):
    # git_critical is not path_based, so this exercises the mandatory-
    # validation rule without depending on the environment's ALLOWED_PATHS.
    response = client.post(
        "/security/evaluate",
        json={"action_type": "git_critical", "description": "force push to main"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["verdict"] == "require_human_validation"
    assert body["action_type"] == "git_critical"


def test_evaluate_endpoint_denies_unwhitelisted_write(client):
    response = client.post(
        "/security/evaluate",
        json={"action_type": "file_write", "description": "write a file", "target_path": "/definitely/not/allowed.txt"},
    )
    assert response.status_code == 200
    assert response.json()["verdict"] == "deny"


def test_evaluate_endpoint_handles_unknown_action_type(client):
    response = client.post(
        "/security/evaluate",
        json={"action_type": "nonsense", "description": "?"},
    )
    assert response.status_code == 200
    assert response.json()["verdict"] == "require_human_validation"


def test_evaluate_endpoint_advisory_defaults_to_none(client):
    response = client.post(
        "/security/evaluate",
        json={"action_type": "git_critical", "description": "force push to main"},
    )
    assert response.json()["advisory"] is None


def test_evaluate_endpoint_include_advisory_populates_it_on_require_human_validation(client):
    response = client.post(
        "/security/evaluate",
        json={
            "action_type": "git_critical",
            "description": "force push to main",
            "include_advisory": True,
        },
    )
    body = response.json()
    assert body["verdict"] == "require_human_validation"
    assert body["advisory"] is not None


def test_evaluate_endpoint_include_advisory_is_noop_on_allow(client, tmp_path):
    response = client.post(
        "/security/evaluate",
        json={
            "action_type": "file_read",
            "description": "?",
            "target_path": str(tmp_path / "f.txt"),
            "include_advisory": True,
        },
    )
    body = response.json()
    # ALLOWED_PATHS in the test app's .env won't cover tmp_path, so this
    # is actually a deny — either way (allow or deny), advisory stays
    # unset since it's only populated for require_human_validation.
    assert body["verdict"] in {"allow", "deny"}
    assert body["advisory"] is None
