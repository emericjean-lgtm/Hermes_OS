"""Task Decomposer for the Intelligent Mission Planner (HOS-042).

Breaks down a high-level user request into a structured task hierarchy.

Two decomposition paths:

* **LLM-driven** (when an Ollama client is injected): asks the ``planning``
  role (``config/models.yaml``) for a JSON task list tailored to the actual
  request, in any language, instead of matching a fixed set of English
  substrings. This is the path the real app uses (see
  ``backend/core/bootstrap/service_registry.py``'s ``_make_mission_planner``).
* **Rule-based** (when no client is injected, or the LLM call/parse fails):
  the original keyword-matching decomposition. It never goes away — it is
  both the offline/unit-test behaviour (no Ollama client means zero network
  calls, exactly as before) and the safety net a malformed or unreachable
  LLM response falls back to, so a bad response degrades a plan instead of
  breaking one.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import threading
from typing import Any, Optional

from backend.mission.planner.planner_models import (
    PlanningRequest,
    TaskBreakdown,
    TaskCategory,
)

logger = logging.getLogger("hermes_os.mission.planner.task_decomposer")

# Categories the LLM is asked to choose from. PLANNING (this activity itself)
# and CUSTOM (a "we don't know" placeholder, not a real classification) are
# deliberately excluded from the prompt — CUSTOM is still a valid fallback
# for a response that names something else, resolved by the same
# `_classify_task` keyword scorer the rule-based path already uses.
_LLM_CATEGORIES: tuple[str, ...] = tuple(
    c.value for c in TaskCategory if c not in (TaskCategory.PLANNING, TaskCategory.CUSTOM)
)
_CATEGORY_BY_VALUE: dict[str, TaskCategory] = {c.value: c for c in TaskCategory}

_MAX_LLM_TASKS = 12

_DECOMPOSITION_SYSTEM_PROMPT = (
    "You are a technical project planner. Break the user's request into a "
    "short, ordered list of concrete engineering tasks, in the same "
    "language the request is written in.\n\n"
    "Respond with ONLY a JSON array — no prose, no markdown code fence, no "
    "explanation before or after it. Each element is an object with "
    "exactly these keys:\n"
    '  "title": short imperative task name (max 80 characters)\n'
    '  "description": one or two sentences describing the task\n'
    f'  "category": one of {list(_LLM_CATEGORIES)}\n'
    '  "depends_on": array of 0-based indices of earlier elements in this '
    "same array that must finish first (empty array if none)\n\n"
    "Produce between 3 and 8 tasks, ordered so earlier ones can run first. "
    'Only reference earlier indices in "depends_on". Do not include a '
    "final review/validation task — one is appended automatically after "
    "your list."
)

_JSON_ARRAY_RE = re.compile(r"\[.*\]", re.DOTALL)


def _build_user_prompt(request: PlanningRequest) -> str:
    parts = [f"Request: {request.user_request or request.objective}"]
    if request.objective and request.objective != request.user_request:
        parts.append(f"Objective: {request.objective}")
    if request.specification:
        parts.append(f"Specification: {request.specification}")
    if request.github_issue:
        parts.append(f"Reference: {request.github_issue}")
    if request.repository:
        parts.append(f"Repository: {request.repository}")
    if request.tags:
        parts.append(f"Tags: {', '.join(request.tags)}")
    return "\n".join(parts)


def _extract_json_array(text: str) -> Optional[list[Any]]:
    """Pull a JSON array out of a model response, tolerating the ways a
    model deviates from "respond with only JSON": a wrapping code fence, or
    a stray sentence before/after the array. Returns ``None`` — never
    raises — when nothing parseable is found, so a malformed response
    degrades to the rule-based fallback instead of crashing planning."""
    if not text or not text.strip():
        return None

    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`").strip()
        if stripped.lower().startswith("json"):
            stripped = stripped[4:].strip()

    try:
        parsed = json.loads(stripped)
        if isinstance(parsed, list):
            return parsed
    except (json.JSONDecodeError, ValueError):
        pass

    match = _JSON_ARRAY_RE.search(text)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
    except (json.JSONDecodeError, ValueError):
        return None
    return parsed if isinstance(parsed, list) else None


class TaskDecomposer:
    """Decomposes user requests into fine-grained task breakdowns."""

    # Keyword → category mapping for auto-classification
    _CATEGORY_KEYWORDS: dict[TaskCategory, list[str]] = {
        TaskCategory.ANALYSIS: [
            "analyse", "analyze", "audit", "review", "study", "investigate",
            "understand", "explore", "evaluate", "assess",
        ],
        TaskCategory.DESIGN: [
            "design", "architect", "plan", "structure", "blueprint",
            "schema", "model", "wireframe", "prototype",
        ],
        TaskCategory.IMPLEMENTATION: [
            "implement", "code", "build", "create", "develop", "write",
            "add", "install", "configure", "setup", "set up",
        ],
        TaskCategory.TESTING: [
            "test", "verify", "validate", "check", "ensure", "confirm",
            "debug", "fix", "ci", "pipeline",
        ],
        TaskCategory.DOCUMENTATION: [
            "document", "write docs", "readme", "comment", "api doc",
            "changelog", "guide",
        ],
        TaskCategory.DEPLOYMENT: [
            "deploy", "release", "publish", "launch", "ship",
            "production", "docker", "container",
        ],
        TaskCategory.REVIEW: [
            "review", "pr", "pull request", "merge", "approve",
        ],
        TaskCategory.INTEGRATION: [
            "integrate", "connect", "link", "bind", "hook up",
            "api", "auth", "oauth", "sso",
        ],
        TaskCategory.OPTIMIZATION: [
            "optimize", "improve", "enhance", "refactor", "speed",
            "performance", "cache", "tune",
        ],
        TaskCategory.SECURITY: [
            "secure", "security", "encrypt", "hash", "csrf",
            "xss", "sql injection", "vulnerability", "penetration",
        ],
    }

    # Known task patterns with subtasks
    _TASK_PATTERNS: dict[str, list[tuple[str, str, TaskCategory]]] = {
        "authentication": [
            ("Analyze auth requirements", "Study security needs, user flows, and compliance", TaskCategory.ANALYSIS),
            ("Design auth architecture", "Choose auth strategy: OAuth, JWT, sessions, SSO", TaskCategory.DESIGN),
            ("Implement backend auth", "Create auth endpoints, middleware, token management", TaskCategory.IMPLEMENTATION),
            ("Implement frontend auth", "Login/signup forms, session management, protected routes", TaskCategory.IMPLEMENTATION),
            ("Write auth tests", "Unit tests, integration tests, security tests", TaskCategory.TESTING),
            ("Document auth flow", "API docs, setup guide, security notes", TaskCategory.DOCUMENTATION),
        ],
        "database": [
            ("Analyze data requirements", "Entities, relationships, access patterns", TaskCategory.ANALYSIS),
            ("Design database schema", "Tables, indexes, migrations strategy", TaskCategory.DESIGN),
            ("Implement database layer", "Models, migrations, queries, ORM setup", TaskCategory.IMPLEMENTATION),
            ("Write database tests", "Model tests, migration tests, performance tests", TaskCategory.TESTING),
            ("Document data model", "ERD, schema docs, migration guide", TaskCategory.DOCUMENTATION),
        ],
        "api": [
            ("Analyze API requirements", "Endpoints, data formats, auth, rate limiting", TaskCategory.ANALYSIS),
            ("Design API contract", "OpenAPI spec, versioning strategy, error handling", TaskCategory.DESIGN),
            ("Implement API endpoints", "Routes, controllers, middleware, validation", TaskCategory.IMPLEMENTATION),
            ("Write API tests", "Unit tests, integration tests, contract tests", TaskCategory.TESTING),
            ("Document API", "OpenAPI docs, usage examples, SDK generation", TaskCategory.DOCUMENTATION),
        ],
        "frontend": [
            ("Analyze UI requirements", "User stories, wireframes, component tree", TaskCategory.ANALYSIS),
            ("Design UI/UX", "Layout, components, state management, routing", TaskCategory.DESIGN),
            ("Implement UI components", "Pages, components, hooks, styling", TaskCategory.IMPLEMENTATION),
            ("Write frontend tests", "Component tests, E2E tests, accessibility tests", TaskCategory.TESTING),
            ("Document UI", "Storybook, usage guide, component docs", TaskCategory.DOCUMENTATION),
        ],
        "deployment": [
            ("Analyze deployment needs", "Environment, scaling, monitoring requirements", TaskCategory.ANALYSIS),
            ("Design deployment pipeline", "CI/CD, environments, rollback strategy", TaskCategory.DESIGN),
            ("Implement CI/CD", "Build scripts, test pipelines, deployment automation", TaskCategory.IMPLEMENTATION),
            ("Test deployment", "Staging tests, smoke tests, rollback tests", TaskCategory.TESTING),
            ("Document deployment", "Runbook, troubleshooting guide, architecture diagram", TaskCategory.DOCUMENTATION),
        ],
    }

    # Generic development lifecycle pattern
    _GENERIC_PATTERN: list[tuple[str, str, TaskCategory]] = [
        ("Analyze requirements", "Study and document requirements and constraints", TaskCategory.ANALYSIS),
        ("Design solution architecture", "Design the high-level architecture and component structure", TaskCategory.DESIGN),
        ("Implement core logic", "Implement the main functionality", TaskCategory.IMPLEMENTATION),
        ("Write tests", "Create comprehensive test suite", TaskCategory.TESTING),
        ("Document the solution", "Write documentation, guides, and examples", TaskCategory.DOCUMENTATION),
    ]

    def __init__(
        self,
        ollama_client: Any = None,
        router: Any = None,
        models_config: Optional[dict] = None,
        timeout_s: float = 90.0,
        cloud_client: Any = None,
    ) -> None:
        """``ollama_client``/``router`` are optional on purpose: with none
        supplied (the default, and every existing caller/test before this
        change), ``decompose()`` behaves exactly as it always has — pure
        keyword matching, no network access. Only the real bootstrap wiring
        (``_make_mission_planner``) supplies both, which is what turns on
        the LLM path.

        ``cloud_client`` (HOS-066C) is an ``OpenRouterClient``-shaped object,
        optional and ``None`` by default — a resilience fallback tried only
        after a local LLM decomposition attempt has already failed, never a
        first choice. See ``_decompose_with_llm``.
        """
        self._ollama = ollama_client
        self._router = router
        self._models_config = models_config or {}
        self._timeout_s = timeout_s
        self._cloud_client = cloud_client

        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._loop_thread: Optional[threading.Thread] = None
        self._loop_lock = threading.Lock()

    # ── async/sync bridge ───────────────────────────────────────────
    #
    # decompose() is called synchronously from MissionPlanner.plan(), which
    # in turn is called directly (not awaited, not off-loaded to a
    # threadpool) from the async `/api/v1/missions` route — so this thread
    # already has a running event loop, and asyncio.run() would raise. Same
    # constraint, same fix as RealTaskExecutor (backend/execution/
    # task_executor.py): a dedicated background loop this class owns.

    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        with self._loop_lock:
            if self._loop is not None and not self._loop.is_closed():
                return self._loop

            ready = threading.Event()

            def runner() -> None:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                self._loop = loop
                ready.set()
                loop.run_forever()

            self._loop_thread = threading.Thread(
                target=runner, name="hermes-task-decomposer", daemon=True
            )
            self._loop_thread.start()
            ready.wait(timeout=10)
            if self._loop is None:  # pragma: no cover - thread start failure
                raise RuntimeError("could not start the task decomposer event loop")
            return self._loop

    def _run_coro(self, coro: Any, timeout: float) -> Any:
        loop = self._ensure_loop()
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result(timeout=timeout)

    def close(self) -> None:
        """Close the Ollama client (if owned) and stop the bridge loop.

        Called by the bootstrap's shutdown probe via ``MissionPlanner.close()``.
        """
        if self._ollama is not None:
            aclose = getattr(self._ollama, "aclose", None)
            if callable(aclose):
                try:
                    self._run_coro(aclose(), timeout=5.0)
                except Exception:
                    logger.debug("closing Ollama client failed", exc_info=True)

        with self._loop_lock:
            loop, thread = self._loop, self._loop_thread
            self._loop, self._loop_thread = None, None
        if loop is not None and not loop.is_closed():
            loop.call_soon_threadsafe(loop.stop)
        if thread is not None:
            thread.join(timeout=5)

    # ── LLM-driven decomposition ────────────────────────────────────

    async def _chat_once(
        self, model: str, messages: list[dict[str, Any]],
        temperature: Optional[float], top_p: Optional[float], think: bool,
        num_ctx: Optional[int] = None,
    ) -> str:
        content_parts: list[str] = []
        async for chunk in self._ollama.chat_events(
            model, messages, temperature=temperature, top_p=top_p, think=think,
            num_ctx=num_ctx,
        ):
            if chunk.kind == "content":
                content_parts.append(chunk.text)
        return "".join(content_parts)

    async def _chat_once_cloud(
        self, model: str, messages: list[dict[str, Any]],
        temperature: Optional[float], top_p: Optional[float],
    ) -> str:
        """Same shape as ``_chat_once`` but against ``self._cloud_client``
        (HOS-066C) — only ever called after a local attempt already failed,
        see ``_decompose_with_llm``."""
        content_parts: list[str] = []
        async for chunk in self._cloud_client.chat_events(
            model, messages, temperature=temperature, top_p=top_p,
        ):
            if chunk.kind == "content":
                content_parts.append(chunk.text)
        return "".join(content_parts)

    def _try_cloud_decompose(
        self, request: PlanningRequest, messages: list[dict[str, Any]], gen: dict,
    ) -> Optional[str]:
        """One retry against a cloud (OpenRouter free-model) fallback after
        the local ``planning`` role failed (HOS-066C) — never a first
        choice, and only attempted at all when a cloud client is wired
        (OPENROUTER_API_KEY configured) and AdaptiveRouter's own gate
        (Aegis authorization, real quota) allows it. Returns None on any
        failure or when no cloud option is available — the caller already
        has a safety net (rule-based decomposition), so this stays
        best-effort rather than raising.
        """
        if self._cloud_client is None:
            return None
        try:
            from backend.model_intelligence.routes import get_cloud_fallback_model

            cloud_model = get_cloud_fallback_model("planning")
            if cloud_model is None:
                return None
            return self._run_coro(
                self._chat_once_cloud(
                    cloud_model, messages, gen.get("temperature"), gen.get("top_p"),
                ),
                self._timeout_s,
            )
        except Exception:
            logger.warning(
                "cloud fallback decomposition also failed for request %s",
                request.request_id, exc_info=True,
            )
            return None

    def _decompose_with_llm(self, request: PlanningRequest) -> Optional[list[TaskBreakdown]]:
        if self._ollama is None or self._router is None:
            return None

        prompt_context = (
            request.user_request or request.objective or request.specification
            or request.github_issue
        ).strip()
        if not prompt_context:
            return None

        gen = self._models_config.get("generation_defaults", {}).get("standard", {})
        messages = [
            {"role": "system", "content": _DECOMPOSITION_SYSTEM_PROMPT},
            {"role": "user", "content": _build_user_prompt(request)},
        ]
        try:
            decision = self._router.select_model("planning")
            content = self._run_coro(
                self._chat_once(
                    decision.model, messages,
                    gen.get("temperature"), gen.get("top_p"), decision.thinking,
                    decision.num_ctx,
                ),
                self._timeout_s,
            )
        except Exception as exc:
            logger.warning(
                "local LLM decomposition failed for request %s (%s: %s)",
                request.request_id, type(exc).__name__, exc, exc_info=True,
            )
            content = self._try_cloud_decompose(request, messages, gen)
            if content is None:
                logger.warning(
                    "falling back to rule-based decomposition for request %s",
                    request.request_id,
                )
                return None

        items = _extract_json_array(content)
        if not items:
            logger.warning(
                "LLM decomposition for request %s returned no parseable JSON "
                "array; falling back to rule-based decomposition",
                request.request_id,
            )
            return None

        breakdowns: list[TaskBreakdown] = []
        for item in items[:_MAX_LLM_TASKS]:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title", "")).strip()[:200]
            if not title:
                continue
            category = _CATEGORY_BY_VALUE.get(
                str(item.get("category", "")).strip().lower(), TaskCategory.CUSTOM
            )
            raw_deps = item.get("depends_on")
            dep_indices = (
                [d for d in raw_deps if isinstance(d, int) and 0 <= d < len(breakdowns)]
                if isinstance(raw_deps, list) else []
            )
            breakdowns.append(TaskBreakdown(
                title=title,
                description=str(item.get("description", "")).strip()[:1000],
                category=category,
                order=len(breakdowns),
                depends_on=[breakdowns[d].task_id for d in dep_indices],
            ))

        return breakdowns or None

    # ── Public API ───────────────────────────────────────────────────

    def decompose(self, request: PlanningRequest) -> list[TaskBreakdown]:
        """Decompose a planning request into task breakdowns.

        Returns an ordered list of tasks ready for dependency building.
        Kept as the stable, list-returning public API every existing
        caller/test uses; see ``decompose_with_method`` for the same
        result plus which path actually produced it.
        """
        breakdowns, _method = self.decompose_with_method(request)
        return breakdowns

    def decompose_with_method(
        self, request: PlanningRequest,
    ) -> tuple[list[TaskBreakdown], str]:
        """Same as ``decompose``, plus which of three paths actually
        produced the breakdown: ``"llm"``, ``"pattern:<key>"``, or
        ``"generic_fallback"``.

        This exists because the generic fallback below is keyword-matched
        in English against ``_TASK_PATTERNS`` — a non-English request (or
        any local LLM call that times out / returns unparseable JSON) can
        silently produce a plan with zero connection to what was actually
        asked, indistinguishable at a glance from a real decomposition. A
        caller that discards this second value is choosing not to know;
        ``MissionPlanner.plan`` does not.
        """
        breakdowns = self._decompose_with_llm(request)
        method = "llm"

        if not breakdowns:
            text = (request.user_request + " " + request.objective + " " +
                    request.specification + " " + request.github_issue).lower()

            breakdowns = []
            seen_patterns: set[str] = set()

            # Try matching known patterns
            for pattern_key, subtasks in self._TASK_PATTERNS.items():
                if pattern_key in text and pattern_key not in seen_patterns:
                    seen_patterns.add(pattern_key)
                    for title, desc, cat in subtasks:
                        breakdowns.append(TaskBreakdown(
                            title=title,
                            description=desc,
                            category=cat,
                            order=len(breakdowns),
                        ))
            if breakdowns:
                method = "pattern:" + "+".join(sorted(seen_patterns))

            # If no patterns matched, use generic decomposition
            if not breakdowns:
                for title, desc, cat in self._GENERIC_PATTERN:
                    breakdowns.append(TaskBreakdown(
                        title=title,
                        description=desc,
                        category=cat,
                        order=len(breakdowns),
                    ))
                method = "generic_fallback"

        # Add a final validation task
        breakdowns.append(TaskBreakdown(
            title="Validation finale",
            description="Final validation: ensure all criteria are met and outputs are correct",
            category=TaskCategory.REVIEW,
            order=len(breakdowns),
            depends_on=[t.task_id for t in breakdowns],  # depends on all
        ))

        # Classify any remaining uncategorized tasks
        for bd in breakdowns:
            if bd.category == TaskCategory.CUSTOM:
                bd.category = self._classify_task(bd.title + " " + bd.description)

        return breakdowns, method

    def _classify_task(self, text: str) -> TaskCategory:
        """Auto-classify a task based on keyword matching."""
        text_lower = text.lower()
        best_category = TaskCategory.CUSTOM
        best_score = 0

        for category, keywords in self._CATEGORY_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in text_lower)
            if score > best_score:
                best_score = score
                best_category = category

        return best_category if best_score > 0 else TaskCategory.IMPLEMENTATION
