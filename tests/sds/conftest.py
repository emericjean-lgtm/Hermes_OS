"""SDS conftest — HOS-003 test fixtures.

Provides a ``reset_eventbus`` async fixture that fully tears down
the module-level EventBus singleton between test cases.
"""
from __future__ import annotations

import pytest_asyncio
from backend.sds.runtime import _HOLDER


@pytest_asyncio.fixture
async def reset_eventbus():
    """Reset the module-level EventBusHolder singleton.

    Stops the current bus (if any) and clears the global reference,
    ensuring test isolation.
    """
    global _HOLDER  # noqa: PLW0602
    holder = _HOLDER
    if holder is not None:
        await holder.stop()
    _HOLDER = None
    yield
    # Teardown: ensure the bus is stopped if a test left it running.
    if _HOLDER is not None:
        try:
            await _HOLDER.stop()
        except Exception:  # pragma: no cover
            pass
    _HOLDER = None
