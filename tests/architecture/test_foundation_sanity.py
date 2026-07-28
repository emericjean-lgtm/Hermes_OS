"""HOS-000 sentinelle — verifies the foundation deliverable is in place.

This test file is intentionally minimal and stable: its job is to
fail loudly if any HOS-000 deliverable is missing or broken, and to
provide a structural smoke-test before HOS-001+ starts adding
runtime contracts on top of these packages.

The tests are deliberately pure I/O (no async, no external services,
no FastAPI client) so they run in milliseconds and remain a reliable
gate in CI even on minimal runners.
"""
from __future__ import annotations

import importlib
from pathlib import Path

import pytest
import yaml


# ---- Helpers -------------------------------------------------------------


def _artifact(repo_root: Path, *parts: str) -> Path:
    return repo_root.joinpath(*parts)


# ---- Tests ---------------------------------------------------------------


def test_repository_root_is_resolvable(repo_root: Path) -> None:
    """The conftest-provided ``repo_root`` must point to a real directory."""
    assert repo_root.is_dir(), f"repo_root {repo_root} is not a directory"


def test_backend_ral_package_exists(repo_root: Path) -> None:
    target = _artifact(repo_root, "backend", "ral", "__init__.py")
    assert target.is_file(), f"missing HOS-000 deliverable: {target}"


def test_backend_ral_adapters_subpackage_exists(repo_root: Path) -> None:
    target = _artifact(repo_root, "backend", "ral", "adapters", "__init__.py")
    assert target.is_file(), f"missing HOS-000 deliverable: {target}"


def test_backend_sds_package_exists(repo_root: Path) -> None:
    target = _artifact(repo_root, "backend", "sds", "__init__.py")
    assert target.is_file(), f"missing HOS-000 deliverable: {target}"


def test_capability_graph_yaml_exists(repo_root: Path) -> None:
    target = _artifact(repo_root, "config", "capability_graph.yaml")
    assert target.is_file(), f"missing HOS-000 deliverable: {target}"


def test_capture_pytest_baseline_script_exists(repo_root: Path) -> None:
    target = _artifact(repo_root, "scripts", "ci", "capture_pytest_baseline.sh")
    assert target.is_file(), f"missing HOS-000 deliverable: {target}"


def test_capture_pytest_baseline_script_is_executable(repo_root: Path) -> None:
    target = _artifact(repo_root, "scripts", "ci", "capture_pytest_baseline.sh")
    if not target.is_file():  # pragma: no cover - guarded by I-0.3 AC-9
        pytest.skip(f"missing HOS-000 deliverable: {target}")
    import os

    mode = target.stat().st_mode
    assert mode & 0o111, f"{target} must be executable (chmod +x missing)"


def test_capability_graph_yaml_is_empty_skeleton(repo_root: Path) -> None:
    """The skeleton must parse, declare version 0.0.0, and hold no nodes/edges/rules."""
    target = _artifact(repo_root, "config", "capability_graph.yaml")
    payload = yaml.safe_load(target.read_text(encoding="utf-8"))
    assert isinstance(payload, dict), "YAML root must be a mapping"
    assert payload.get("version") == "0.0.0", "version must be 0.0.0 in HOS-000"
    assert payload.get("nodes") == [], "nodes must be empty in HOS-000"
    assert payload.get("edges") == [], "edges must be empty in HOS-000"
    assert payload.get("routing_rules") == [], "routing_rules must be empty in HOS-000"
    provenance = payload.get("provenance", {})
    assert provenance.get("introduced_by") == "HOS-000"
    assert provenance.get("superseded_by") == "HOS-006b"


def test_ral_package_is_importable_and_publishes_ral_api() -> None:
    """Importing the package must succeed and expose the HOS-001 RAL API.

    HOS-000 kept ``backend.ral`` intentionally empty. HOS-001 populates
    it with the public RAL contracts (RuntimeInterface, EventBusInterface,
    capabilities, ModelRouterInterface). This test is therefore updated
    by HOS-001 to reflect the new expected public surface.
    """
    ral = importlib.import_module("backend.ral")
    assert hasattr(ral, "__all__")
    assert "RuntimeInterface" in ral.__all__
    assert "EventBusInterface" in ral.__all__
    assert "ModelRouterInterface" in ral.__all__


def test_ral_adapters_subpackage_is_importable_as_empty_namespace() -> None:
    sub = importlib.import_module("backend.ral.adapters")
    assert hasattr(sub, "__all__")
    assert sub.__all__ == []


def test_sds_package_is_importable_as_empty_namespace() -> None:
    sds = importlib.import_module("backend.sds")
    assert hasattr(sds, "__all__")
    assert sds.__all__ == []
