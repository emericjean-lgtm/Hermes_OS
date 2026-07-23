from __future__ import annotations

import pytest

from backend.security.aegis_engine import ActionRequest, AegisEngine, Verdict
from backend.security.permission_matrix import PermissionMatrix


def _engine(security_config: dict, allowed_paths: list[str], autonomy_level: str | None = None) -> AegisEngine:
    config = dict(security_config)
    if autonomy_level is not None:
        config["autonomy_level"] = autonomy_level
    return AegisEngine(PermissionMatrix(config), allowed_paths)


def test_unknown_action_type_requires_validation(security_config):
    engine = _engine(security_config, allowed_paths=[])
    decision = engine.evaluate(ActionRequest(action_type="launch_missiles", description="?"))
    assert decision.verdict is Verdict.REQUIRE_HUMAN_VALIDATION


@pytest.mark.parametrize(
    "action_type",
    ["file_delete", "secret_modification", "git_critical", "deployment", "data_migration", "system_config", "system_command", "network_major"],
)
def test_mandatory_validation_categories_always_require_human(security_config, tmp_path, action_type):
    engine = _engine(security_config, allowed_paths=[str(tmp_path)], autonomy_level="high")
    target = str(tmp_path / "file.txt") if action_type in {"file_delete", "secret_modification"} else None
    decision = engine.evaluate(ActionRequest(action_type=action_type, description="?", target_path=target))
    assert decision.verdict is Verdict.REQUIRE_HUMAN_VALIDATION


def test_file_write_outside_whitelist_is_denied(security_config, tmp_path):
    engine = _engine(security_config, allowed_paths=[str(tmp_path / "allowed")], autonomy_level="high")
    decision = engine.evaluate(
        ActionRequest(action_type="file_write", description="?", target_path=str(tmp_path / "elsewhere" / "f.txt"))
    )
    assert decision.verdict is Verdict.DENY


def test_file_write_missing_target_path_is_denied(security_config, tmp_path):
    engine = _engine(security_config, allowed_paths=[str(tmp_path)], autonomy_level="high")
    decision = engine.evaluate(ActionRequest(action_type="file_write", description="?", target_path=None))
    assert decision.verdict is Verdict.DENY


def test_file_write_inside_whitelist_requires_validation_at_low_autonomy(security_config, tmp_path):
    engine = _engine(security_config, allowed_paths=[str(tmp_path)], autonomy_level="low")
    decision = engine.evaluate(
        ActionRequest(action_type="file_write", description="?", target_path=str(tmp_path / "f.txt"))
    )
    assert decision.verdict is Verdict.REQUIRE_HUMAN_VALIDATION


def test_file_write_inside_whitelist_auto_allowed_at_medium_autonomy(security_config, tmp_path):
    engine = _engine(security_config, allowed_paths=[str(tmp_path)], autonomy_level="medium")
    decision = engine.evaluate(
        ActionRequest(action_type="file_write", description="?", target_path=str(tmp_path / "f.txt"))
    )
    assert decision.verdict is Verdict.ALLOW


def test_file_read_inside_whitelist_always_allowed(security_config, tmp_path):
    engine = _engine(security_config, allowed_paths=[str(tmp_path)], autonomy_level="low")
    decision = engine.evaluate(
        ActionRequest(action_type="file_read", description="?", target_path=str(tmp_path / "f.txt"))
    )
    assert decision.verdict is Verdict.ALLOW


def test_file_read_outside_whitelist_is_denied(security_config, tmp_path):
    engine = _engine(security_config, allowed_paths=[str(tmp_path / "allowed")], autonomy_level="low")
    decision = engine.evaluate(
        ActionRequest(action_type="file_read", description="?", target_path=str(tmp_path / "elsewhere" / "f.txt"))
    )
    assert decision.verdict is Verdict.DENY


def test_no_allowed_paths_denies_every_path_based_action(security_config):
    engine = _engine(security_config, allowed_paths=[], autonomy_level="high")
    decision = engine.evaluate(ActionRequest(action_type="file_read", description="?", target_path="/anywhere"))
    assert decision.verdict is Verdict.DENY


def test_network_call_gated_by_high_autonomy(security_config):
    low = _engine(security_config, allowed_paths=[], autonomy_level="low")
    high = _engine(security_config, allowed_paths=[], autonomy_level="high")
    assert low.evaluate(ActionRequest(action_type="network_call", description="?")).verdict is Verdict.REQUIRE_HUMAN_VALIDATION
    assert high.evaluate(ActionRequest(action_type="network_call", description="?")).verdict is Verdict.ALLOW
