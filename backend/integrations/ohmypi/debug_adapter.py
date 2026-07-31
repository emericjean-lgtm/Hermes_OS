"""Debug Adapter (HOS-055C).

Integrates Oh My Pi's DAP debugger into Hermes.
Manages debug sessions, breakpoints, stack traces, variables.
Publishes events on EventBus.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Optional


@dataclass
class DebugBreakpoint:
    id: str = ""; file_path: str = ""; line: int = 0; condition: str = ""; enabled: bool = True

@dataclass
class StackFrame:
    frame_id: str = ""; function_name: str = ""; file_path: str = ""
    line: int = 0; column: int = 0; variables: dict[str, str] = field(default_factory=dict)

@dataclass
class DebugSession:
    session_id: str = ""; program: str = ""; debugger_type: str = ""
    status: str = "created"; breakpoints: list[DebugBreakpoint] = field(default_factory=list)
    stack_frames: list[StackFrame] = field(default_factory=list)
    incidents: list[dict] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class DebugAdapter:
    EVENTS = {"started": "ohmypi.debug.started", "breakpoint": "ohmypi.debug.breakpoint",
              "failed": "ohmypi.debug.failed", "completed": "ohmypi.debug.completed"}

    def __init__(self, on_event: Optional[Callable] = None) -> None:
        self._lock = threading.RLock()
        self._on_event = on_event
        self._sessions: dict[str, DebugSession] = {}
        self._session_counter = 0

    def create_session(self, program: str, debugger_type: str = "auto") -> DebugSession:
        self._session_counter += 1
        sid = f"dap_{self._session_counter}"
        session = DebugSession(session_id=sid, program=program, debugger_type=debugger_type)
        self._sessions[sid] = session
        self._publish(self.EVENTS["started"], {"session_id": sid, "program": program})
        return session

    def add_breakpoint(self, session_id: str, file_path: str, line: int, condition: str = "") -> Optional[DebugBreakpoint]:
        session = self._sessions.get(session_id)
        if not session: return None
        bp = DebugBreakpoint(id=f"bp_{len(session.breakpoints)+1}", file_path=file_path, line=line, condition=condition)
        session.breakpoints.append(bp)
        self._publish(self.EVENTS["breakpoint"], {"session_id": session_id, "file": file_path, "line": line})
        return bp

    def update_stack(self, session_id: str, frames: list[dict]) -> bool:
        session = self._sessions.get(session_id)
        if not session: return False
        session.stack_frames = [StackFrame(
            frame_id=f.get("id", ""), function_name=f.get("function", ""),
            file_path=f.get("file", ""), line=f.get("line", 0), column=f.get("column", 0),
            variables=f.get("variables", {})) for f in frames]
        return True

    def record_incident(self, session_id: str, incident: dict) -> bool:
        session = self._sessions.get(session_id)
        if not session: return False
        session.incidents.append(incident)
        if incident.get("type") == "error":
            self._publish(self.EVENTS["failed"], {"session_id": session_id, "error": incident.get("message", "")})
        return True

    def complete_session(self, session_id: str) -> bool:
        session = self._sessions.get(session_id)
        if not session: return False
        session.status = "completed"
        self._publish(self.EVENTS["completed"], {"session_id": session_id})
        return True

    def get_session(self, session_id: str) -> Optional[DebugSession]:
        return self._sessions.get(session_id)

    def get_stack_trace(self, session_id: str) -> list[StackFrame]:
        session = self._sessions.get(session_id)
        return session.stack_frames if session else []

    def get_variables(self, session_id: str) -> dict[str, str]:
        frames = self.get_stack_trace(session_id)
        result = {}
        for f in frames: result.update(f.variables)
        return result

    def stats(self) -> dict:
        return {"total_sessions": len(self._sessions),
                "completed": sum(1 for s in self._sessions.values() if s.status == "completed"),
                "active": sum(1 for s in self._sessions.values() if s.status == "created"),
                "total_breakpoints": sum(len(s.breakpoints) for s in self._sessions.values())}

    def _publish(self, event: str, payload: dict) -> None:
        if self._on_event:
            try: self._on_event(event, payload, severity="info")
            except Exception: pass
