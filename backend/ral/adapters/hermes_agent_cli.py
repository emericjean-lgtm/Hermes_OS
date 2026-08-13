"""Hermes Agent CLI runtime adapter.

This adapter is intentionally a thin bridge to the *installed* Hermes Agent
runtime. It does not talk to Ollama directly: Hermes Agent owns model routing,
tool loop behaviour, skills, memory, and its OpenAI-compatible Ollama backend.
Hermes OS only supplies mission context and supervises the result.

Known constraint — delegation does not survive this invocation mode
(HOS-094). Hermes Agent's ``delegate`` tool is *asynchronous*: the parent
dispatches subagents, answers immediately ("Background 2 tasks running —
I'll resume when they finish. Keep chatting."), and expects an interactive
session to stay open until they report back. This adapter runs the CLI
one-shot with ``--query``, so the process exits as soon as the parent
replies and the subagents die mid-request:

    [subagent-0] Interrupted during API call.
    [subagent-1] Interrupted during API call.
      x [1/2] Summarize SERVICE_A.md  (37.11s)
      x [2/2] Summarize SERVICE_B.md  (37.11s)

Measured, not inferred. The CLI exposes no flag to block on background
tasks, and ``--resume`` cannot help because there is nothing left to
resume. Parallel *tool* work inside a single agent is unaffected and works
(6 tool calls producing a correct multi-file synthesis in one run); it is
parallel *agents* that this mode cannot host.

Worth knowing before "fixing" it: merely mentioning delegation in a prompt
derails the local model. Same task, same model, same toolset — with "you
may delegate ... if you judge it useful" the run made 0 tool calls and
produced nothing in 5m13s; without that sentence it made 6 and wrote the
correct file in 1m46.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.ral.capabilities import ChatResponse, CapabilityInterface
from backend.ral.event_bus import EventBusInterface, Topic
from backend.ral.runtime import CapabilitySet, RuntimeStatus


class HermesAgentCliError(RuntimeError):
    """Raised when the installed Hermes Agent CLI cannot execute a task."""


@dataclass(frozen=True)
class HermesAgentCliConfig:
    """Location and execution settings for the installed Hermes Agent."""

    hermes_home: str = r"C:\Users\emeri\AppData\Local\hermes"
    agent_root: str = r"C:\Users\emeri\AppData\Local\hermes\hermes-agent"
    #: Hermes Agent's *own* interpreter, deliberately absolute — never
    #: sys.executable. Since HOS-103 Hermes OS runs in its own virtualenv
    #: (.venv), which has none of the agent's dependencies; resolving this
    #: from the running process would launch cli.py under an interpreter
    #: that cannot import it. The two environments are separate on purpose:
    #: that is what stops a `hermes update` from changing Hermes OS's
    #: dependency tree, as it did on 2026-08-13.
    python_exe: str = (
        r"C:\Users\emeri\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe"
    )
    cli_py: str = (
        r"C:\Users\emeri\AppData\Local\hermes\hermes-agent\cli.py"
    )
    model: str = "devstral"
    provider: str = "custom"
    base_url: str = "http://127.0.0.1:11434/v1"
    api_key: str = "hermes_ollama_projets"
    timeout_seconds: float = 300.0
    max_turns: int = 20


def _messages_to_prompt(messages: list[dict[str, Any]]) -> str:
    """Convert Hermes OS chat messages into one Hermes Agent task prompt."""

    parts: list[str] = []

    for message in messages:
        role = str(message.get("role") or "user").upper()
        content = str(message.get("content") or "").strip()

        if content:
            parts.append(f"{role}:\n{content}")

    return "\n\n".join(parts).strip()


def _format_context(runtime_ctx: dict[str, Any] | None) -> str:
    """Format Hermes OS runtime context for Hermes Agent."""

    if not runtime_ctx:
        return ""

    lines = ["Contexte fourni par Hermes OS:"]

    for key in (
        "mission_id",
        "task_id",
        "task_type",
        "workspace",
        "project_id",
        "skills",
        "policy",
    ):
        if key in runtime_ctx and runtime_ctx[key] not in (
            None,
            "",
            [],
            {},
        ):
            value = runtime_ctx[key]

            if isinstance(value, (dict, list, tuple)):
                value = json.dumps(
                    value,
                    ensure_ascii=False,
                )

            lines.append(f"- {key}: {value}")

    return "\n".join(lines)


def _read_usage_file(path: str) -> dict[str, Any]:
    """Read Hermes Agent usage metadata."""

    try:
        return json.loads(
            Path(path).read_text(encoding="utf-8")
        )
    except Exception:
        return {}


def _extract_session_id(stdout: str) -> str:
    """Extract the session id from Hermes Agent CLI output."""

    match = re.search(
        r"session_id:\s*([A-Za-z0-9_\-]+)",
        stdout,
    )

    return match.group(1) if match else ""


def _strip_session_footer(stdout: str) -> str:
    """Remove the optional session id footer from CLI output."""

    return re.sub(
        r"\n?\s*session_id:\s*[A-Za-z0-9_\-]+\s*$",
        "",
        stdout,
    ).strip()


def _normalise_toolsets(value: Any) -> list[str]:
    """Normalise runtime_ctx['toolsets'].

    Hermes OS normally provides a list of toolset names. A comma-separated
    string is also accepted for robustness.
    """

    if value is None:
        return []

    if isinstance(value, str):
        return [
            item.strip()
            for item in value.split(",")
            if item.strip()
        ]

    if isinstance(value, (list, tuple, set, frozenset)):
        return [
            str(item).strip()
            for item in value
            if str(item).strip()
        ]

    return []


class HermesAgentCliChatCapability:
    """Chat capability backed by Hermes Agent's native headless CLI."""

    name = "chat"

    def __init__(
        self,
        config: HermesAgentCliConfig,
        event_bus: EventBusInterface | None = None,
    ) -> None:
        self._config = config
        self._bus = event_bus

    async def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        runtime_ctx: dict[str, Any] | None = None,
    ) -> ChatResponse:
        """Execute one task through the installed Hermes Agent CLI."""

        ctx = runtime_ctx or {}

        # ---------------------------------------------------------------
        # Build prompt
        # ---------------------------------------------------------------

        prompt = _messages_to_prompt(messages)
        context = _format_context(runtime_ctx)

        if context:
            prompt = (
                f"{context}\n\n"
                f"Mission à exécuter:\n"
                f"{prompt}"
            )

        if not prompt:
            raise HermesAgentCliError(
                "empty Hermes Agent prompt"
            )

        # ---------------------------------------------------------------
        # Runtime overrides
        # ---------------------------------------------------------------

        model = str(
            ctx.get("model")
            or self._config.model
        )

        provider = str(
            ctx.get("provider")
            or self._config.provider
        )

        base_url = str(
            ctx.get("base_url")
            or self._config.base_url
        )

        toolsets = _normalise_toolsets(
            ctx.get("toolsets")
        )

        workspace = str(
            ctx.get("workspace")
            or os.getcwd()
        )

        max_turns = self._config.max_turns

        if ctx.get("max_turns") is not None:
            try:
                max_turns = int(ctx["max_turns"])
            except (TypeError, ValueError):
                max_turns = self._config.max_turns

        # ---------------------------------------------------------------
        # Workspace validation
        # ---------------------------------------------------------------

        workspace_path = Path(workspace)

        if not workspace_path.exists():
            raise HermesAgentCliError(
                f"Hermes Agent workspace does not exist: {workspace}"
            )

        if not workspace_path.is_dir():
            raise HermesAgentCliError(
                f"Hermes Agent workspace is not a directory: {workspace}"
            )

        # ---------------------------------------------------------------
        # Temporary usage file
        # ---------------------------------------------------------------

        fd, usage_path = tempfile.mkstemp(
            prefix="hermes_agent_usage_",
            suffix=".json",
        )
        os.close(fd)

        # ---------------------------------------------------------------
        # Hermes Agent environment
        # ---------------------------------------------------------------

        env = os.environ.copy()

        env["HERMES_HOME"] = self._config.hermes_home
        env["OPENAI_API_KEY"] = self._config.api_key
        env["HERMES_INFERENCE_MODEL"] = model
        env["PYTHONUTF8"] = "1"

        # ---------------------------------------------------------------
        # CLI command
        # ---------------------------------------------------------------

        cmd = [
            self._config.python_exe,
            self._config.cli_py,
            "--query",
            prompt,
            "--model",
            model,
            "--provider",
            provider,
            "--base_url",
            base_url,
            "--max_turns",
            str(max_turns),
        ]

        # IMPORTANT:
        # Do not pass "--toolsets" with an empty value.
        #
        # Hermes Agent must receive the option only when Hermes OS
        # explicitly supplies one or more toolsets.
        if toolsets:
            cmd.extend(
                [
                    "--toolsets",
                    ",".join(toolsets),
                ]
            )

        cmd.extend(
            [
                "--quiet",
                "--usage-file",
                usage_path,
            ]
        )

        task_id = ctx.get("task_id", "")

        self._publish(
            Topic.TASK_STARTED,
            {
                "runtime": "hermes-agent",
                "model": model,
                "task_id": task_id,
            },
        )

        proc: asyncio.subprocess.Process | None = None
        stdout_b = b""
        stderr_b = b""

        try:
            # -----------------------------------------------------------
            # Launch Hermes Agent
            # -----------------------------------------------------------

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=workspace,
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout_b, stderr_b = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=self._config.timeout_seconds,
                )

            except asyncio.TimeoutError as exc:
                # Never leave a Hermes Agent process running after the
                # runtime has timed out.
                if proc.returncode is None:
                    proc.kill()

                    try:
                        await proc.wait()
                    except Exception:
                        pass

                self._publish(
                    Topic.TASK_FAILED,
                    {
                        "runtime": "hermes-agent",
                        "model": model,
                        "reason": "timeout",
                        "timeout_seconds": (
                            self._config.timeout_seconds
                        ),
                        "task_id": task_id,
                    },
                )

                raise HermesAgentCliError(
                    "Hermes Agent execution timed out after "
                    f"{self._config.timeout_seconds} seconds"
                ) from exc

        except FileNotFoundError as exc:
            self._publish(
                Topic.TASK_FAILED,
                {
                    "runtime": "hermes-agent",
                    "model": model,
                    "reason": "executable_not_found",
                    "error": str(exc),
                    "task_id": task_id,
                },
            )

            raise HermesAgentCliError(
                "Unable to start Hermes Agent CLI: executable not found"
            ) from exc

        except OSError as exc:
            self._publish(
                Topic.TASK_FAILED,
                {
                    "runtime": "hermes-agent",
                    "model": model,
                    "reason": "process_start_failed",
                    "error": str(exc),
                    "task_id": task_id,
                },
            )

            raise HermesAgentCliError(
                f"Unable to start Hermes Agent CLI: {exc}"
            ) from exc

        finally:
            # -----------------------------------------------------------
            # Always collect usage information and clean the temp file.
            # -----------------------------------------------------------

            usage = _read_usage_file(usage_path)

            try:
                Path(usage_path).unlink(
                    missing_ok=True
                )
            except Exception:
                pass

        # ---------------------------------------------------------------
        # Decode process output
        # ---------------------------------------------------------------

        stdout = stdout_b.decode(
            "utf-8",
            errors="replace",
        )

        stderr = stderr_b.decode(
            "utf-8",
            errors="replace",
        )

        session_id = (
            _extract_session_id(stdout)
            or str(
                usage.get("session_id")
                or ""
            )
        )

        content = _strip_session_footer(stdout)

        returncode = (
            proc.returncode
            if proc is not None
            else -1
        )

        # ---------------------------------------------------------------
        # Hermes Agent failure
        # ---------------------------------------------------------------

        if returncode != 0:
            self._publish(
                Topic.TASK_FAILED,
                {
                    "runtime": "hermes-agent",
                    "model": model,
                    "returncode": returncode,
                    "stderr": stderr[-2000:],
                    "task_id": task_id,
                },
            )

            raise HermesAgentCliError(
                f"Hermes Agent exited with {returncode}: "
                f"{stderr.strip() or content}"
            )

        # ---------------------------------------------------------------
        # Empty response
        # ---------------------------------------------------------------

        if not content:
            self._publish(
                Topic.TASK_FAILED,
                {
                    "runtime": "hermes-agent",
                    "model": model,
                    "reason": "empty_response",
                    "task_id": task_id,
                },
            )

            raise HermesAgentCliError(
                "Hermes Agent returned an empty response"
            )

        # ---------------------------------------------------------------
        # Metadata
        # ---------------------------------------------------------------

        metadata = {
            "provider": "hermes-agent",
            "serving_provider": (
                usage.get("provider")
                or provider
            ),
            "model": (
                usage.get("model")
                or model
            ),
            "session_id": session_id,
            "prompt_tokens": (
                usage.get("input_tokens")
                or 0
            ),
            "completion_tokens": (
                usage.get("output_tokens")
                or 0
            ),
            "api_calls": usage.get("api_calls"),
            "completed": usage.get("completed"),
            "base_url": base_url,
            "workspace": workspace,
            "toolsets": toolsets,
            "max_turns": max_turns,
        }

        # ---------------------------------------------------------------
        # Completion event
        # ---------------------------------------------------------------

        self._publish(
            Topic.TASK_COMPLETED,
            {
                "runtime": "hermes-agent",
                "model": metadata["model"],
                "session_id": session_id,
                "task_id": task_id,
            },
        )

        return ChatResponse(
            content=content,
            metadata=metadata,
        )

    def _publish(
        self,
        topic: Topic,
        payload: dict[str, Any],
    ) -> None:
        if self._bus is not None:
            self._bus.publish(
                topic,
                payload,
                publisher="hermes-agent-cli",
            )


class HermesAgentCliRuntime:
    """RuntimeInterface-compatible wrapper around installed Hermes Agent."""

    name = "hermes-agent"
    version = "0.19.0"

    # These capabilities are owned by Hermes Agent itself.
    #
    # Hermes OS exposes them at runtime level so the orchestration layer
    # knows that this runtime supports them. Actual tool/skill/memory
    # execution remains inside Hermes Agent.
    capabilities = CapabilitySet(
        frozenset(
            {
                "chat",
                "tools",
                "skills",
                "memory",
            }
        )
    )

    def __init__(
        self,
        config: HermesAgentCliConfig | None = None,
        event_bus: EventBusInterface | None = None,
    ) -> None:
        self._config = (
            config
            or HermesAgentCliConfig()
        )

        self._bus = event_bus
        self._status = RuntimeStatus.STOPPED

        self._chat = HermesAgentCliChatCapability(
            self._config,
            event_bus,
        )

    @property
    def status(self) -> RuntimeStatus:
        return self._status

    async def start(self) -> None:
        """Validate the installed Hermes Agent runtime."""

        missing = [
            path
            for path in (
                self._config.python_exe,
                self._config.cli_py,
            )
            if not Path(path).exists()
        ]

        if missing:
            self._status = RuntimeStatus.ERROR

            raise HermesAgentCliError(
                "Hermes Agent installation is incomplete: "
                + ", ".join(missing)
            )

        self._status = RuntimeStatus.STARTED

        if self._bus is not None:
            self._bus.publish(
                Topic.RUNTIME_STARTED,
                {
                    "runtime": self.name,
                    "version": self.version,
                },
                publisher="hermes-agent-cli",
            )

    async def stop(self) -> None:
        """Stop the Hermes Agent runtime."""

        self._status = RuntimeStatus.STOPPED

        if self._bus is not None:
            self._bus.publish(
                Topic.RUNTIME_STOPPED,
                {
                    "runtime": self.name,
                    "version": self.version,
                },
                publisher="hermes-agent-cli",
            )

    def get(
        self,
        capability_name: str,
    ) -> CapabilityInterface | None:
        """Return the runtime capability implemented by this adapter."""

        if capability_name == "chat":
            return self._chat

        # tools / skills / memory are executed internally by Hermes Agent.
        # They are declared in the runtime capability set above but are not
        # exposed as independent Hermes OS capability objects.
        return None