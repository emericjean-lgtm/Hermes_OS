#!/usr/bin/env python3
"""Hermes Agent pre_tool_call hook: routes Hermes's own native risky
tools (terminal, process, patch, read_file) through Aegis (Hermes
Ollama's security gate) before they run.

Why this exists: disabling Hermes's terminal/file toolsets (see
config/hermes_agent_mcp.example.yaml) is the primary defense — this hook
is a second layer, in case those toolsets get re-enabled later (e.g. by
a config change or a Hermes update) without anyone remembering why they
were off. Hermes Ollama's own MCP tools (files_apply etc.) already call
Aegis internally regardless of this hook, see backend/tools/file_tools.py.

Wire this up in ~/.hermes/config.yaml:

    hooks:
      pre_tool_call:
        - matcher: "terminal|process|patch|read_file"
          command: "python3 /absolute/path/to/aegis_gate.py"
          timeout: 15

Reads the hook payload on stdin (Hermes's documented pre_tool_call
shape: {hook_event_name, tool_name, tool_input, session_id, cwd, extra}),
maps the tool call to one of Aegis's action_type categories
(config/security.yaml), calls this backend's POST /security/evaluate,
and prints a block/allow decision to stdout in Hermes's documented
shape ({} to allow, {"decision": "block", "reason": ...} to veto).
Requires the Hermes Ollama backend running and reachable at
AEGIS_GATE_URL below.

NOT verified against a live Hermes Agent install: hermes-agent.
nousresearch.com is unreachable from this development sandbox (network
policy), so this script is built strictly from Hermes Agent's published
hook contract, not exercised end-to-end. In particular, the exact
tool_input field names for patch/read_file/terminal/process (guessed
below as path/file_path/command/cmd) should be checked against what
Hermes actually sends — run `hermes tools` or add a debug line dumping
`payload` to a file on first use, and adjust _TOOL_ACTION_MAP if needed.
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

AEGIS_GATE_URL = "http://127.0.0.1:8000/security/evaluate"

# tool_name -> (aegis action_type, tool_input keys to try for a path)
_TOOL_ACTION_MAP: dict[str, tuple[str, tuple[str, ...]]] = {
    "terminal": ("system_command", ()),
    "process": ("system_command", ()),
    "patch": ("file_write", ("path", "file_path")),
    "read_file": ("file_read", ("path", "file_path")),
}

_COMMAND_KEYS = ("command", "cmd")


def _first_present(data: dict, keys: tuple[str, ...]) -> str | None:
    for key in keys:
        if key in data:
            return data[key]
    return None


def main() -> None:
    payload = json.load(sys.stdin)
    tool_name = payload.get("tool_name")
    tool_input = payload.get("tool_input") or {}

    mapping = _TOOL_ACTION_MAP.get(tool_name)
    if mapping is None:
        print("{}")  # not one of the tools we gate -> allow, no-op
        return

    action_type, path_keys = mapping
    target_path = _first_present(tool_input, path_keys)
    command = _first_present(tool_input, _COMMAND_KEYS)
    description = f"Hermes Agent native {tool_name!r} call: " + (
        command if command else json.dumps(tool_input)
    )

    request_body = json.dumps(
        {
            "action_type": action_type,
            "description": description,
            "target_path": target_path,
            "requesting_agent": f"hermes-agent:{tool_name}",
        }
    ).encode("utf-8")

    request = urllib.request.Request(
        AEGIS_GATE_URL, data=request_body, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            decision = json.load(response)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        # Fail closed: if Aegis can't be reached, block rather than let a
        # native terminal/file action through ungated.
        print(json.dumps({"decision": "block", "reason": f"Aegis unreachable: {exc}"}))
        return

    if decision.get("verdict") == "allow":
        print("{}")
    else:
        print(json.dumps({"decision": "block", "reason": decision.get("reason", "Denied by Aegis")}))


if __name__ == "__main__":
    main()
