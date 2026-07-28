"""Architectural conftest — HOS-000 sentinel.

This conftest is loaded by pytest whenever a test under
``tests/architecture/`` is collected. Its purpose is twofold:

1. Make the project root importable so tests can import
   ``backend.ral``, ``backend.sds`` and friends *without* requiring
   the test runner to add the project root to ``sys.path`` ahead of
   time. This keeps the architecture tests runnable both via
   ``pytest tests/architecture/`` and via the dedicated capture
   script (see ``scripts/ci/capture_pytest_baseline.sh``).

2. Provide an autouse session-scoped sentinel fixture. The fixture
   itself does nothing — its presence proves the conftest was loaded,
   which HOS-001+ relies on when it adds more architectural
   invariants (RAL isolation, singleton discipline, etc.).

Project invariants enforced here :

* ``backend.ral`` and ``backend.sds`` must exist (HOS-000).
* Repo root must be importable from the test process.

Failure to load this conftest is detected by
``tests/architecture/test_foundation_sanity.py``.
"""
from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
import pytest_asyncio

_REPO_ROOT: Path = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


@pytest.fixture(scope="session", autouse=True)
def _architecture_sentinel() -> Iterator[None]:
    """Marker fixture that proves the conftest was loaded.

    The body is intentionally empty; the fixture exists so that a
    missing conftest shows up as a test collection error rather than
    an opaque ``ImportError`` later in the session.
    """
    yield


@pytest.fixture(scope="session")
def repo_root() -> Path:
    """Absolute path to the repository root."""
    return _REPO_ROOT


@pytest_asyncio.fixture
async def reset_eventbus():
    """Reset the module-level EventBusHolder singleton for test isolation.

    Stops the current bus (if any) and clears the global reference.
    Defined here (not in ``tests/sds/conftest``) because the SDS wiring
    tests reside under ``tests/architecture/``.
    """
    from backend.sds.runtime import _HOLDER

    holder = _HOLDER
    if holder is not None:
        await holder.stop()
    _HOLDER = None  # type: ignore[assignment]
    yield
    from backend.sds.runtime import _HOLDER as inner_holder

    if inner_holder is not None:
        try:
            await inner_holder.stop()
        except Exception:  # pragma: no cover
            pass
    # Re-reset after teardown
    _HOLDER = None  # type: ignore[assignment]
