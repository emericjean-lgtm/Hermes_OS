"""Autonomous-suite conftest — keeps the unit tests hermetic (R-001).

``AutonomousOrchestrator`` now executes goals through ``MissionExecutor``, which
drives a real runtime. Without this fixture every goal test issues live LLM
requests, making the suite slow and dependent on a running Ollama.

Only the outbound inference call is replaced; the orchestrator, decision engine,
guard, memory loop, mission executor, validator and telemetry are all still the
production code paths. Real-execution coverage lives in
``tests/integration/test_real_execution.py``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def _no_live_inference(monkeypatch):
    from tests.support import fake_inference

    fake_inference.install(monkeypatch)
