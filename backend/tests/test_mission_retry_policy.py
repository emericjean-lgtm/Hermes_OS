"""Closing the verification loop (HOS-099).

HOS-092 gave missions a verdict the agent cannot argue with. But noticing
that a mission reported success over an untouched workspace and then stopping
is diagnosis without treatment — the failure this whole line of work exists
to remove still happens, it is merely labelled now.

These tests pin two things: when a second attempt is warranted, and what the
agent is told. The second matters more. Re-sending an identical prompt to a
model that just failed it mostly reproduces the failure; the retry has to
carry the evidence.
"""
from __future__ import annotations

from backend.mission.retry_policy import DEFAULT_MAX_ATTEMPTS, build_retry_brief, decide

OBJECTIVE = "Create REPORT.md summarising the findings."


def _verification(**over):
    base = {
        "measured": True, "reported_success": True, "contradicted": True,
        "workspace": r"C:\ws", "summary": "no file was created, modified or deleted",
    }
    base.update(over)
    return base


def test_a_contradicted_success_is_retried():
    decision = decide(_verification(), objective=OBJECTIVE)

    assert decision.should_retry
    assert decision.attempt == 2
    assert decision.brief


def test_an_agreeing_verification_is_left_alone():
    assert not decide(_verification(contradicted=False), objective=OBJECTIVE).should_retry


def test_an_unmeasured_mission_is_not_retried():
    """Absence of evidence is not evidence of absence — retrying here would
    punish every workspace-less mission forever."""
    decision = decide(_verification(measured=False), objective=OBJECTIVE)

    assert not decision.should_retry
    assert "nothing was measured" in decision.reason


def test_a_missing_verification_is_not_retried():
    assert not decide(None, objective=OBJECTIVE).should_retry


def test_the_retry_budget_is_enforced():
    """A model that fails twice on the same evidence will not succeed on the
    fifth attempt; it just burns minutes of local inference."""
    assert decide(_verification(), objective=OBJECTIVE, attempts_made=1).should_retry
    assert not decide(
        _verification(), objective=OBJECTIVE, attempts_made=DEFAULT_MAX_ATTEMPTS,
    ).should_retry


def test_the_brief_carries_the_original_objective():
    """It is being asked to do the same work — dropping the objective would
    leave it guessing."""
    brief = build_retry_brief(OBJECTIVE, _verification())

    assert OBJECTIVE in brief


def test_the_brief_carries_the_filesystem_evidence():
    """This is what makes a retry different from re-sending the prompt: a
    model told only "try again" has no reason to behave differently."""
    brief = build_retry_brief(OBJECTIVE, _verification())

    assert r"C:\ws" in brief
    assert "no file was created, modified or deleted" in brief


def test_the_brief_asks_for_self_verification():
    brief = build_retry_brief(OBJECTIVE, _verification())

    assert "read back" in brief.lower()
    assert "disk" in brief.lower()


def test_the_brief_states_facts_rather_than_blame():
    """"You failed" invites another confident apology, which is the exact
    behaviour being corrected. "The workspace is unchanged" is checkable."""
    brief = build_retry_brief(OBJECTIVE, _verification()).lower()

    assert "unchanged" in brief
    assert "you failed" not in brief


def test_a_partially_changed_workspace_still_reads_its_own_summary():
    brief = build_retry_brief(
        OBJECTIVE, _verification(summary="1 created: NOTES.md"))

    assert "1 created: NOTES.md" in brief
