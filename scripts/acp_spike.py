"""Spike: can Hermes OS drive Hermes Agent over ACP with a live session?

Proves or refutes, before any adapter rewrite:
  1. spawn hermes-acp and complete the ACP handshake
  2. create a session bound to a workspace
  3. send a prompt and receive streamed updates
  4. verify a REAL artifact on disk (never the agent's own account)
  5. reuse the SAME session for a second prompt   <- impossible with the CLI
"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path

import logging
logging.basicConfig(level=logging.DEBUG, stream=__import__('sys').stderr)
import acp
from acp.schema import (
    ClientCapabilities,
    FileSystemCapabilities,
    Implementation,
    TextContentBlock,
)

HERMES_HOME = r"C:\Users\emeri\AppData\Local\hermes"
ACP_EXE = r"C:\Users\emeri\AppData\Local\hermes\hermes-agent\venv\Scripts\hermes-acp.exe"
MODEL = "lfm2.5-2.6b-128k"


def _loud(name):
    """Wrap a handler so its real exception is visible.

    ACP re-raises handler failures as an opaque "Internal error" with the
    original traceback discarded, which says nothing about which method
    failed or why.
    """
    def deco(fn):
        import functools

        @functools.wraps(fn)
        async def wrapper(*a, **kw):
            print(f'-> {name}', flush=True)
            try:
                return await fn(*a, **kw)
            except Exception as exc:
                import traceback
                print(f"!! handler {name} a leve: {type(exc).__name__}: {exc}", flush=True)
                traceback.print_exc()
                raise
        return wrapper
    return deco


class SpikeClient(acp.Client):
    """Minimal client: record what streams back, auto-approve permissions."""

    def __init__(self) -> None:
        self.updates: list[str] = []
        self.permission_requests = 0

    @_loud('session_update')
    async def session_update(self, session_id: str, update=None, **kwargs) -> None:
        kind = type(update).__name__ if update is not None else "?"
        self.updates.append(kind)

    @_loud('request_permission')
    async def request_permission(self, options, session_id: str, tool_call=None, **kwargs):
        self.permission_requests += 1
        options = options or []
        print(f'   options recues: {[(getattr(o,"option_id",None), getattr(o,"kind",None), getattr(o,"name",None)) for o in options]}', flush=True)
        # Pick the first allow-shaped option so the spike is non-interactive.
        for opt in options:
            kind = str(getattr(opt, "kind", "")).lower()
            if "allow" in kind:
                from acp.schema import AllowedOutcome, RequestPermissionResponse
                return RequestPermissionResponse(
                    outcome=AllowedOutcome(outcome='selected', option_id=opt.option_id))
        from acp.schema import DeniedOutcome, RequestPermissionResponse
        return RequestPermissionResponse(outcome=DeniedOutcome(outcome='cancelled'))

    @_loud('write_text_file')
    async def write_text_file(self, content: str, path: str, session_id: str, **kwargs):
        from acp.schema import WriteTextFileResponse
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(content, encoding="utf-8")
        return WriteTextFileResponse()

    @_loud('read_text_file')
    async def read_text_file(self, path: str, session_id: str, **kwargs):
        from acp.schema import ReadTextFileResponse
        try:
            return ReadTextFileResponse(content=Path(path).read_text(encoding="utf-8"))
        except OSError:
            return ReadTextFileResponse(content="")

    # Terminal methods: declared unsupported in capabilities, but implemented
    # defensively — an unimplemented handler surfaces as an opaque
    # "Internal error" that says nothing about which method was missing.
    @_loud('create_terminal')
    async def create_terminal(self, command: str, session_id: str, **kwargs):
        from acp.schema import CreateTerminalResponse
        self.updates.append("create_terminal(REFUSED)")
        return CreateTerminalResponse(terminal_id="unsupported")

    async def terminal_output(self, session_id: str, terminal_id: str, **kwargs):
        from acp.schema import TerminalOutputResponse
        return TerminalOutputResponse(output="", truncated=False)

    async def wait_for_terminal_exit(self, session_id: str, terminal_id: str, **kwargs):
        from acp.schema import TerminalExitStatus, WaitForTerminalExitResponse
        return WaitForTerminalExitResponse(exit_status=TerminalExitStatus(exit_code=1))

    async def kill_terminal(self, session_id: str, terminal_id: str, **kwargs):
        from acp.schema import KillTerminalResponse
        return KillTerminalResponse()

    async def release_terminal(self, session_id: str, terminal_id: str, **kwargs):
        from acp.schema import ReleaseTerminalResponse
        return ReleaseTerminalResponse()


async def main() -> int:
    workspace = Path(tempfile.mkdtemp(prefix="acp_spike_"))
    env = os.environ.copy()
    env.update({
        "HERMES_HOME": HERMES_HOME,
        "OPENAI_API_KEY": "hermes_ollama_projets",
        "PYTHONUTF8": "1",
    })

    client = SpikeClient()
    print(f"workspace: {workspace}")

    async with acp.spawn_agent_process(
        client, ACP_EXE, env=env, cwd=str(workspace),
    ) as (conn, process):
        init = await conn.initialize(
            protocol_version=acp.PROTOCOL_VERSION,
            client_capabilities=ClientCapabilities(
                fs=FileSystemCapabilities(read_text_file=True, write_text_file=True),
                terminal=True,
            ),
            client_info=Implementation(name="hermes-os", version="1.0.0"),
        )
        print(f"1. handshake OK — capabilities={bool(getattr(init, 'agent_capabilities', None))}")

        session = await conn.new_session(cwd=str(workspace), mcp_servers=[])
        sid = session.session_id
        print(f"2. session creee: {sid}")

        # Which model is this session about to use? Never specified in the
        # first attempt, so it fell back to the configured default — which
        # may be a remote provider that simply hangs without credentials.
        models = getattr(session, "models", None)
        available = getattr(models, "available_models", None) or []
        current = getattr(models, "current_model_id", None)
        print(f"2b. modele courant: {current}")
        print(f"2c. disponibles: {[getattr(m, 'model_id', m) for m in available][:8]}")

        local = next((m for m in available
                      if MODEL.split(':')[0] in str(getattr(m, 'model_id', m))), None)
        if local is not None:
            await conn.set_session_model(
                session_id=sid, model_id=getattr(local, "model_id", str(local)))
            print(f"2d. modele force: {getattr(local, 'model_id', local)}")
        else:
            print("2d. AUCUN modele local trouve dans la session")

        result = await conn.prompt(
            session_id=sid,
            prompt=[TextContentBlock(
                type="text",
                text="Create a file named ACP_SPIKE.md containing exactly one "
                     "line: 'acp ok'.",
            )],
        )
        print(f"3. prompt#1 stop_reason={getattr(result, 'stop_reason', '?')} "
              f"updates={len(client.updates)} permissions={client.permission_requests}")

        artifact = workspace / "ACP_SPIKE.md"
        ok1 = artifact.is_file() and "acp ok" in artifact.read_text(encoding="utf-8")
        print(f"4. artefact reel sur disque: {'OUI' if ok1 else 'NON'}")

        before = len(client.updates)
        result2 = await conn.prompt(
            session_id=sid,
            prompt=[TextContentBlock(
                type="text",
                text="Now append a second line 'second turn' to that same file.",
            )],
        )
        print(f"5. prompt#2 MEME session stop_reason={getattr(result2, 'stop_reason', '?')} "
              f"nouveaux_updates={len(client.updates) - before}")

        ok2 = artifact.is_file() and "second turn" in artifact.read_text(encoding="utf-8")
        print(f"6. session reutilisable (2 tours): {'OUI' if ok2 else 'NON'}")
        print()
        print("CONTENU FINAL:")
        print(artifact.read_text(encoding="utf-8") if artifact.is_file() else "(aucun fichier)")
        return 0 if ok1 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
