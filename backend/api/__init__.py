"""Hermes OS Mission Control API (HOS-028).

The official external API for Hermes OS, exposing :class:`MissionControlService`
through REST endpoints and a WebSocket event stream.

All routes live under the ``/api/v1`` prefix so they can coexist with
the existing Hermes API routes without conflicts.
"""

from backend.api.router import MissionControlRouter, MissionControlAPI

__all__ = [
    "MissionControlRouter",
    "MissionControlAPI",
]
