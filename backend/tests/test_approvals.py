"""Human approvals queue — the §23 "vue sécurité" backend.

An approval turns a refusal into an allowance, so the tests that matter
most are the ones pinning down what it must *not* do: never unlock a
hard DENY, never survive a second use, never outlive its window, and
never match an action other than the one a human actually saw.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from backend.memory.db import Base, make_engine, make_session_factory
from backend.security import approvals
from backend.security.approvals import ApprovalStatus, fingerprint_for


@pytest.fixture
def session(tmp_path):
    engine = make_engine(str(tmp_path / "approvals.db"))
    Base.metadata.create_all(engine)
    with make_session_factory(engine)() as s:
        yield s


def _record(session, **overrides):
    payload = {
        "action_type": "file_write",
        "description": "Write to /projet/a.txt",
        "reason": "autonomy too low",
        "target_path": "/projet/a.txt",
        "requesting_agent": "atlas",
    }
    payload.update(overrides)
    return approvals.record_pending(session, **payload)


# ── the fingerprint is what makes consent specific ───────────────────
def test_fingerprint_is_stable_for_the_same_action():
    a = fingerprint_for("file_write", "/x/a.txt", "Write to /x/a.txt")
    b = fingerprint_for("file_write", "/x/a.txt", "Write to /x/a.txt")

    assert a == b


@pytest.mark.parametrize(
    ("action_type", "path", "description"),
    [
        ("file_delete", "/x/a.txt", "Write to /x/a.txt"),  # different action
        ("file_write", "/x/b.txt", "Write to /x/a.txt"),  # different target
        ("file_write", "/x/a.txt", "Commit on main"),  # different intent
    ],
)
def test_a_different_action_gets_a_different_fingerprint(action_type, path, description):
    """Approving "commit on feature/x" must never authorise "commit on
    main" — the description is part of the identity for that reason."""
    baseline = fingerprint_for("file_write", "/x/a.txt", "Write to /x/a.txt")

    assert fingerprint_for(action_type, path, description) != baseline


# ── queueing ─────────────────────────────────────────────────────────
def test_refused_action_is_queued(session):
    entry = _record(session)

    assert entry.status == ApprovalStatus.PENDING
    assert entry.reason == "autonomy too low"
    assert len(approvals.list_approvals(session, status="pending")) == 1


def test_retrying_the_same_action_does_not_pile_up(session):
    """An agent retrying in a loop would otherwise flood the queue and
    bury the entries a human needs to see."""
    first = _record(session)
    second = _record(session)

    assert first.id == second.id
    assert len(approvals.list_approvals(session)) == 1


def test_a_different_action_gets_its_own_entry(session):
    _record(session)
    _record(session, target_path="/projet/b.txt", description="Write to /projet/b.txt")

    assert len(approvals.list_approvals(session)) == 2


# ── consuming ────────────────────────────────────────────────────────
def test_approval_lets_exactly_one_retry_through(session):
    entry = _record(session)
    approvals.decide(session, entry.id, approved=True)

    first = approvals.consume_approval(
        session,
        action_type="file_write",
        target_path="/projet/a.txt",
        description="Write to /projet/a.txt",
    )
    second = approvals.consume_approval(
        session,
        action_type="file_write",
        target_path="/projet/a.txt",
        description="Write to /projet/a.txt",
    )

    assert first is not None
    assert first.status == ApprovalStatus.USED
    # Single use is the whole point: consent must not become a standing
    # permission just because nobody revoked it.
    assert second is None


def test_pending_approval_authorises_nothing(session):
    _record(session)

    assert (
        approvals.consume_approval(
            session,
            action_type="file_write",
            target_path="/projet/a.txt",
            description="Write to /projet/a.txt",
        )
        is None
    )


def test_refused_approval_authorises_nothing(session):
    entry = _record(session)
    approvals.decide(session, entry.id, approved=False)

    assert (
        approvals.consume_approval(
            session,
            action_type="file_write",
            target_path="/projet/a.txt",
            description="Write to /projet/a.txt",
        )
        is None
    )


def test_expired_approval_authorises_nothing(session):
    entry = _record(session)
    approvals.decide(session, entry.id, approved=True)
    entry.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    session.commit()

    consumed = approvals.consume_approval(
        session,
        action_type="file_write",
        target_path="/projet/a.txt",
        description="Write to /projet/a.txt",
    )

    assert consumed is None
    # Left visible rather than deleted, so the queue can show it lapsed.
    assert approvals.get_approval(session, entry.id).status == ApprovalStatus.APPROVED
    assert approvals.to_dict(approvals.get_approval(session, entry.id))["expired"] is True


def test_approval_does_not_cover_a_neighbouring_action(session):
    entry = _record(session)
    approvals.decide(session, entry.id, approved=True)

    assert (
        approvals.consume_approval(
            session,
            action_type="file_write",
            target_path="/projet/AUTRE.txt",
            description="Write to /projet/AUTRE.txt",
        )
        is None
    )


# ── deciding ─────────────────────────────────────────────────────────
def test_a_used_approval_cannot_be_re_approved(session):
    """One human action must not be able to mint a second consent."""
    entry = _record(session)
    approvals.decide(session, entry.id, approved=True)
    approvals.consume_approval(
        session,
        action_type="file_write",
        target_path="/projet/a.txt",
        description="Write to /projet/a.txt",
    )

    again = approvals.decide(session, entry.id, approved=True)

    assert again.status == ApprovalStatus.USED
    assert (
        approvals.consume_approval(
            session,
            action_type="file_write",
            target_path="/projet/a.txt",
            description="Write to /projet/a.txt",
        )
        is None
    )


def test_deciding_an_unknown_id_returns_none(session):
    assert approvals.decide(session, "inconnu", approved=True) is None


def test_refusal_sets_no_expiry(session):
    entry = _record(session)

    decided = approvals.decide(session, entry.id, approved=False)

    assert decided.status == ApprovalStatus.REFUSED
    assert decided.expires_at is None


def test_listing_can_be_scoped_to_a_project(session):
    _record(session, project_id="p1")
    _record(session, target_path="/b.txt", description="Write to /b.txt", project_id="p2")

    assert len(approvals.list_approvals(session, project_id="p1")) == 1


# ── integration with the live Aegis agent ────────────────────────────
def test_a_hard_deny_is_never_unlocked_by_an_approval(tmp_path, monkeypatch):
    """The load-bearing guarantee. ALLOWED_PATHS, project scoping and a
    missing target_path produce DENY, and consent must not reach them: a
    human clicking "approve" in a UI is not a reason to write outside the
    whitelist.
    """
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "aegis.db"))
    monkeypatch.setenv("ALLOWED_PATHS", str(tmp_path / "autorise"))
    from backend.core.config import get_settings

    get_settings.cache_clear()

    from backend.core.agent_registry import get_agent_registry
    from backend.security.aegis_engine import ActionRequest, Verdict

    get_agent_registry.cache_clear()
    aegis = get_agent_registry().get("aegis")

    outside = ActionRequest(
        action_type="file_write",
        description="Write to /etc/passwd",
        target_path="/etc/passwd",
        requesting_agent="atlas",
    )
    first = aegis.evaluate(outside)
    assert first.verdict is Verdict.DENY

    # A DENY must not even be queued — there is nothing to approve.
    queued = aegis.list_approvals()
    assert all(a["target_path"] != "/etc/passwd" for a in queued)

    # And it stays denied on retry, no matter what is in the queue.
    assert aegis.evaluate(outside).verdict is Verdict.DENY

    get_settings.cache_clear()
    get_agent_registry.cache_clear()


def test_queue_then_approve_then_retry_succeeds(tmp_path, monkeypatch):
    """The whole point, end to end: refused -> visible in the queue ->
    approved by a human -> the identical retry is allowed once."""
    allowed = tmp_path / "autorise"
    allowed.mkdir()
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "aegis2.db"))
    monkeypatch.setenv("ALLOWED_PATHS", str(allowed))
    from backend.core.config import get_settings

    get_settings.cache_clear()

    from backend.core.agent_registry import get_agent_registry
    from backend.security.aegis_engine import ActionRequest, Verdict

    get_agent_registry.cache_clear()
    aegis = get_agent_registry().get("aegis")

    target = str(allowed / "a.txt")
    action = ActionRequest(
        action_type="file_write",
        description=f"Write to {target}",
        target_path=target,
        requesting_agent="atlas",
    )

    # 1. Refused at the shipped autonomy level, and queued.
    assert aegis.evaluate(action).verdict is Verdict.REQUIRE_HUMAN_VALIDATION
    pending = [a for a in aegis.list_approvals(status="pending") if a["target_path"] == target]
    assert len(pending) == 1

    # 2. A human approves it.
    aegis.decide_approval(pending[0]["id"], approved=True)

    # 3. The identical retry now passes — once.
    assert aegis.evaluate(action).verdict is Verdict.ALLOW
    assert aegis.evaluate(action).verdict is Verdict.REQUIRE_HUMAN_VALIDATION

    get_settings.cache_clear()
    get_agent_registry.cache_clear()


# ── the REST surface ─────────────────────────────────────────────────
# These exist because the routes were shipped once with an undefined
# helper: 538 tests passed and both endpoints would have raised NameError
# on the first real call. Untested routes are unshipped routes.
def test_listing_approvals_over_rest(client):
    response = client.get("/security/approvals")

    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_status_filter_is_accepted(client):
    assert client.get("/security/approvals", params={"status": "pending"}).status_code == 200


def test_deciding_an_unknown_approval_is_404(client):
    response = client.post("/security/approvals/inconnu", json={"approved": True})

    assert response.status_code == 404


def test_full_rest_round_trip(client, tmp_path):
    """Refuse an action, find it in the queue, approve it over HTTP."""
    target = str(tmp_path / "hors-perimetre.txt")
    client.post(
        "/security/evaluate",
        json={
            "action_type": "git_critical",
            "description": "force push to main",
            "requesting_agent": "atlas",
        },
    )

    pending = client.get("/security/approvals", params={"status": "pending"}).json()
    queued = [a for a in pending if a["action_type"] == "git_critical"]
    assert queued, "a mandatory-validation action should be queued for a human"

    decided = client.post(
        f"/security/approvals/{queued[0]['id']}", json={"approved": True}
    ).json()

    assert decided["status"] == "approved"
    assert decided["expires_at"] is not None  # consent is time-limited


def test_a_refusal_is_per_attempt_not_permanent(session):
    """Documented consequence: refusing records the decision but does not
    permanently block. A later retry queues a fresh ask, because "no, not
    now" must not silently become an unrevokable "never"."""
    entry = _record(session)
    approvals.decide(session, entry.id, approved=False)

    again = _record(session)

    assert again.id != entry.id
    assert again.status == ApprovalStatus.PENDING
    # The earlier decision is still on record beside it.
    statuses = {a.status for a in approvals.list_approvals(session)}
    assert statuses == {ApprovalStatus.PENDING, ApprovalStatus.REFUSED}
