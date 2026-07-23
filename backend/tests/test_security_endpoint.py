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
