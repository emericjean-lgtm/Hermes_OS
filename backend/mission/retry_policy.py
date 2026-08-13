"""Turn a verification failure into a second, better-informed attempt (HOS-099).

HOS-092 gave missions a verdict the agent cannot talk its way out of: compare
the workspace before and after, and flag a mission that reports success while
having changed nothing. But a verdict is not a loop. The system noticed the
contradiction and stopped there, which is diagnosis without treatment.

This module closes it. Given a verification result it answers two questions:
should this mission run again, and what should it be told this time. The
second half matters more than the first — re-running the identical prompt
against a model that just failed it mostly reproduces the failure. The point
is to hand back *evidence*: what was expected, what the filesystem actually
shows, and that its own account of success was contradicted.

Deliberately mission-level, not per-node. Plenty of nodes legitimately
produce no file — "analyse the requirements", "choose an approach" — so a
node that writes nothing is not a failure signal. A whole mission that
touches nothing while claiming success is.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger("hermes_os.mission.retry")

#: One retry, not more. Measured on this deployment, a mission costs minutes
#: of local inference; a model that fails twice on the same evidence is not
#: going to succeed on the fifth attempt, it just burns the machine. Raising
#: this is a decision for whoever has measured that it helps.
DEFAULT_MAX_ATTEMPTS = 2


@dataclass(frozen=True)
class RetryDecision:
    """Whether to run again, and what to say."""

    should_retry: bool
    reason: str
    brief: Optional[str] = None
    attempt: int = 1


def decide(
    verification: Optional[dict],
    *,
    objective: str,
    attempts_made: int = 1,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
) -> RetryDecision:
    """Decide whether a completed mission deserves another attempt.

    Retries exactly one situation: the mission reported success and the
    filesystem contradicts it. Everything else is left alone, on purpose.

    A mission that genuinely failed is not retried here — it failed for a
    reason the verification layer cannot see (a timeout, an unavailable
    runtime), and re-running it blind would just repeat that. A mission that
    was never measured is not retried either: absence of evidence is not
    evidence of absence, and retrying on it would punish every workspace-less
    mission forever.
    """
    if verification is None:
        return RetryDecision(False, "no verification available")
    if not verification.get("measured"):
        return RetryDecision(False, "nothing was measured — no workspace to compare")
    if not verification.get("contradicted"):
        return RetryDecision(False, "verification agrees with the reported result")
    if attempts_made >= max_attempts:
        return RetryDecision(
            False,
            f"already attempted {attempts_made} time(s), limit is {max_attempts}",
        )
    return RetryDecision(
        should_retry=True,
        reason="reported success but the workspace did not change",
        brief=build_retry_brief(objective, verification),
        attempt=attempts_made + 1,
    )


def build_retry_brief(objective: str, verification: dict) -> str:
    """What to tell the agent on the second attempt.

    Three things, in this order: the original objective (it is being asked to
    do the same work), the evidence that it did not happen, and an
    instruction to verify its own output. The evidence is the part that makes
    this different from re-sending the same prompt — a model told only "try
    again" has no reason to behave differently.

    Phrased as fact rather than accusation. "The workspace is unchanged" is
    checkable; "you failed" invites the model to apologise and produce
    another confident paragraph, which is the behaviour being corrected.
    """
    workspace = verification.get("workspace") or "the workspace"
    lines = [
        objective.strip(),
        "",
        "IMPORTANT — this task was already attempted and did not take effect.",
        f"After that attempt, {workspace} was unchanged: "
        f"{verification.get('summary', 'no file was created, modified or deleted')}.",
        "",
        "A description of the work is not the work. Use your tools to make "
        "the change, then read back what you wrote to confirm it exists on "
        "disk before reporting success.",
    ]
    return "\n".join(lines)
