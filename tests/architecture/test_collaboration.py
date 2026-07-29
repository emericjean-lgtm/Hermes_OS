"""Tests for the Multi-Agent Collaboration Engine (HOS-044)."""

from __future__ import annotations

import threading

import pytest

from backend.agents.collaboration.collaboration_engine import CollaborationEngine
from backend.agents.collaboration.collaboration_models import (
    ConflictType,
    ConsensusMode,
    ConsensusStatus,
    DelegationStatus,
    MessageType,
    ReviewStatus,
)
from backend.agents.collaboration.conflict_resolver import ConflictResolver
from backend.agents.collaboration.consensus_engine import ConsensusEngine
from backend.agents.collaboration.context_sharing import ContextSharing
from backend.agents.collaboration.delegation_manager import DelegationManager
from backend.agents.collaboration.message_bus import MessageBus


# ── Fixtures ─────────────────────────────────────────────────

@pytest.fixture
def message_bus() -> MessageBus:
    return MessageBus()


@pytest.fixture
def context_sharing() -> ContextSharing:
    return ContextSharing()


@pytest.fixture
def delegation_manager() -> DelegationManager:
    return DelegationManager()


@pytest.fixture
def consensus_engine() -> ConsensusEngine:
    return ConsensusEngine()


@pytest.fixture
def conflict_resolver() -> ConflictResolver:
    return ConflictResolver()


@pytest.fixture
def engine() -> CollaborationEngine:
    return CollaborationEngine()


# ── Message Bus Tests ────────────────────────────────────────

class TestMessageBus:
    def test_send_direct_message(self, message_bus):
        msg = message_bus.send("agent1", "agent2", "Hello", "Hi there!")
        assert msg.message_id
        assert msg.sender_id == "agent1"
        assert msg.recipient_id == "agent2"
        assert msg.type == MessageType.DIRECT

    def test_broadcast(self, message_bus):
        msg = message_bus.broadcast("agent1", "Announcement", "Hello all")
        assert msg.type == MessageType.BROADCAST
        assert msg.recipient_id == ""

    def test_send_group(self, message_bus):
        msgs = message_bus.send_group("agent1", ["a2", "a3"], "Group", "Hey")
        assert len(msgs) == 2
        assert msgs[0].recipient_id in ("a2", "a3")

    def test_request_help(self, message_bus):
        msg = message_bus.request_help(
            "agent1", "Need help", "Stuck on task",
            ["coding", "testing"],
        )
        assert msg.type == MessageType.HELP_REQUEST
        assert "coding" in msg.metadata["required_capabilities"]

    def test_respond_help(self, message_bus):
        original = message_bus.request_help("agent1", "Help", "Need", ["coding"])
        response = message_bus.respond_help("agent2", original.message_id, "I'll help!")
        assert response is not None
        assert response.type == MessageType.HELP_RESPONSE

    def test_get_inbox(self, message_bus):
        message_bus.send("a1", "a2", "Subj", "Body")
        message_bus.broadcast("a3", "Broad", "Cast")
        inbox = message_bus.get_inbox("a2")
        assert len(inbox) >= 1

    def test_get_unread(self, message_bus):
        message_bus.send("a1", "a2", "Subj", "Body")
        unread = message_bus.get_unread("a2")
        assert len(unread) >= 1

    def test_mark_read(self, message_bus):
        msg = message_bus.send("a1", "a2", "Subj", "Body")
        assert message_bus.mark_read(msg.message_id)
        assert message_bus.get(msg.message_id).read

    def test_acknowledge(self, message_bus):
        msg = message_bus.send("a1", "a2", "Subj", "Body")
        assert message_bus.acknowledge(msg.message_id)
        assert message_bus.get(msg.message_id).acknowledged

    def test_conversation_threading(self, message_bus):
        conv_id = "conv-001"
        m1 = message_bus.send("a1", "a2", "Q", "Question", conversation_id=conv_id)
        m2 = message_bus.send("a2", "a1", "Re: Q", "Answer", conversation_id=conv_id, reply_to=m1.message_id)
        conv = message_bus.get_conversation(conv_id)
        assert len(conv) == 2

    def test_get_by_mission(self, message_bus):
        message_bus.send("a1", "a2", "S", "B", mission_id="m1")
        msgs = message_bus.get_by_mission("m1")
        assert len(msgs) == 1

    def test_get_sent(self, message_bus):
        message_bus.send("a1", "a2", "Test", "Body")
        sent = message_bus.get_sent("a1")
        assert len(sent) >= 1

    def test_get_help_requests(self, message_bus):
        message_bus.request_help("a1", "Help", "Need", ["coding"])
        requests = message_bus.get_help_requests()
        assert len(requests) >= 1

    def test_stats(self, message_bus):
        message_bus.send("a1", "a2", "S", "B")
        stats = message_bus.stats()
        assert stats["total_messages"] >= 1


# ── Context Sharing Tests ────────────────────────────────────

class TestContextSharing:
    def test_share_context(self, context_sharing):
        ctx = context_sharing.share("agent1", "m1", "Result", {"data": 42})
        assert ctx.share_id
        assert ctx.owner_id == "agent1"

    def test_visibility_permissions(self, context_sharing):
        ctx = context_sharing.share(
            "agent1", "m1", "Secret", {"x": 1},
            visible_to=["agent2"],
        )
        # agent2 can see
        assert context_sharing.get(ctx.share_id, "agent2") is not None
        # agent3 cannot
        assert context_sharing.get(ctx.share_id, "agent3") is None
        # owner always can
        assert context_sharing.get(ctx.share_id, "agent1") is not None

    def test_public_context(self, context_sharing):
        ctx = context_sharing.share("agent1", "m1", "Public", {"x": 1})
        # Empty visible_to means public
        assert context_sharing.get(ctx.share_id, "anyone") is not None

    def test_edit_permissions(self, context_sharing):
        ctx = context_sharing.share(
            "agent1", "m1", "Editable", {"x": 1},
            editable_by=["agent2"],
        )
        assert context_sharing.can_edit(ctx.share_id, "agent2")
        assert not context_sharing.can_edit(ctx.share_id, "agent3")

    def test_update_context(self, context_sharing):
        ctx = context_sharing.share("agent1", "m1", "Updatable", {"x": 1})
        assert context_sharing.update(ctx.share_id, "agent1", {"y": 2})
        updated = context_sharing.get(ctx.share_id, "agent1")
        assert updated.content == {"x": 1, "y": 2}

    def test_get_by_owner(self, context_sharing):
        context_sharing.share("agent1", "m1", "A", {})
        context_sharing.share("agent1", "m2", "B", {})
        contexts = context_sharing.get_by_owner("agent1")
        assert len(contexts) == 2

    def test_get_by_mission(self, context_sharing):
        context_sharing.share("agent1", "m1", "A", {})
        context_sharing.share("agent2", "m1", "B", {})
        contexts = context_sharing.get_by_mission("m1")
        assert len(contexts) == 2

    def test_get_visible_to(self, context_sharing):
        context_sharing.share("agent1", "m1", "Public", {})
        context_sharing.share("agent2", "m2", "Private", {}, visible_to=["agent3"])
        visible = context_sharing.get_visible_to("agent1")
        assert len(visible) >= 1  # at least the public one

    def test_remove(self, context_sharing):
        ctx = context_sharing.share("agent1", "m1", "ToRemove", {})
        assert context_sharing.remove(ctx.share_id, "agent1")
        assert context_sharing.get(ctx.share_id) is None


# ── Delegation Manager Tests ─────────────────────────────────

class TestDelegationManager:
    def test_delegate(self, delegation_manager):
        d = delegation_manager.delegate("a1", "a2", "m1", "n1", "Task title")
        assert d.delegation_id
        assert d.from_agent_id == "a1"
        assert d.to_agent_id == "a2"

    def test_accept_reject(self, delegation_manager):
        d = delegation_manager.delegate("a1", "a2", "m1", "n1", "Task")
        assert delegation_manager.accept(d.delegation_id, "a2")
        assert delegation_manager.get(d.delegation_id).status == DelegationStatus.ACCEPTED

    def test_complete_workflow(self, delegation_manager):
        d = delegation_manager.delegate("a1", "a2", "m1", "n1", "Task")
        delegation_manager.accept(d.delegation_id, "a2")
        delegation_manager.start(d.delegation_id, "a2")
        ok = delegation_manager.complete(d.delegation_id, "a2", "Done!")
        assert ok
        assert delegation_manager.get(d.delegation_id).status == DelegationStatus.COMPLETED

    def test_get_incoming(self, delegation_manager):
        delegation_manager.delegate("a1", "a2", "m1", "n1", "Task1")
        delegation_manager.delegate("a3", "a2", "m1", "n2", "Task2")
        incoming = delegation_manager.get_incoming("a2")
        assert len(incoming) == 2

    def test_get_outgoing(self, delegation_manager):
        delegation_manager.delegate("a1", "a2", "m1", "n1", "Task1")
        delegation_manager.delegate("a1", "a3", "m1", "n2", "Task2")
        outgoing = delegation_manager.get_outgoing("a1")
        assert len(outgoing) == 2

    def test_get_pending(self, delegation_manager):
        delegation_manager.delegate("a1", "a2", "m1", "n1", "Task")
        pending = delegation_manager.get_pending("a2")
        assert len(pending) == 1

    def test_request_expertise(self, delegation_manager):
        d = delegation_manager.request_expertise(
            "a1", "m1", "Need expert", "Complex task",
            ["security", "optimization"],
        )
        assert d.to_agent_id == ""
        assert len(d.required_capabilities) == 2

    def test_get_unmatched(self, delegation_manager):
        delegation_manager.request_expertise("a1", "m1", "Expert", "Need", ["coding"])
        unmatched = delegation_manager.get_unmatched()
        assert len(unmatched) >= 1

    def test_get_by_mission(self, delegation_manager):
        delegation_manager.delegate("a1", "a2", "m1", "n1", "Task")
        dlist = delegation_manager.get_by_mission("m1")
        assert len(dlist) == 1

    def test_stats(self, delegation_manager):
        delegation_manager.delegate("a1", "a2", "m1", "n1", "Task")
        stats = delegation_manager.stats()
        assert stats["total"] >= 1


# ── Consensus Engine Tests ───────────────────────────────────

class TestConsensusEngine:
    def test_propose(self, consensus_engine):
        p = consensus_engine.propose(
            "agent1", "m1", "n1", "Vote", "Pick one",
            ["optionA", "optionB"],
        )
        assert p.proposal_id
        assert p.proposer_id == "agent1"

    def test_vote_and_reach_majority(self, consensus_engine):
        p = consensus_engine.propose(
            "a1", "m1", "n1", "Vote", "Desc",
            ["A", "B"], mode=ConsensusMode.MAJORITY, minimum_voters=3,
        )
        consensus_engine.start_voting(p.proposal_id)
        consensus_engine.vote(p.proposal_id, "a1", "A")
        consensus_engine.vote(p.proposal_id, "a2", "A")
        consensus_engine.vote(p.proposal_id, "a3", "B")
        outcome = consensus_engine.try_resolve(p.proposal_id)
        assert outcome == "A"

    def test_unanimous(self, consensus_engine):
        p = consensus_engine.propose(
            "a1", "m1", "n1", "Unanimous", "Desc",
            ["X"], mode=ConsensusMode.UNANIMOUS, minimum_voters=2,
        )
        consensus_engine.start_voting(p.proposal_id)
        consensus_engine.vote(p.proposal_id, "a1", "X")
        consensus_engine.vote(p.proposal_id, "a2", "X")
        outcome = consensus_engine.try_resolve(p.proposal_id)
        assert outcome == "X"

    def test_not_enough_votes(self, consensus_engine):
        p = consensus_engine.propose(
            "a1", "m1", "n1", "Vote", "Desc",
            ["A", "B"], minimum_voters=3,
        )
        consensus_engine.start_voting(p.proposal_id)
        consensus_engine.vote(p.proposal_id, "a1", "A")
        outcome = consensus_engine.try_resolve(p.proposal_id)
        assert outcome is None

    def test_super_majority(self, consensus_engine):
        p = consensus_engine.propose(
            "a1", "m1", "n1", "Super", "Desc",
            ["A", "B"], mode=ConsensusMode.SUPER_MAJORITY, minimum_voters=3,
        )
        consensus_engine.start_voting(p.proposal_id)
        consensus_engine.vote(p.proposal_id, "a1", "A")
        consensus_engine.vote(p.proposal_id, "a2", "A")
        consensus_engine.vote(p.proposal_id, "a3", "B")
        outcome = consensus_engine.try_resolve(p.proposal_id)
        assert outcome == "A"  # 2/3 = super majority

    def test_cancel(self, consensus_engine):
        p = consensus_engine.propose("a1", "m1", "n1", "Vote", "D", ["A"])
        assert consensus_engine.cancel(p.proposal_id)

    def test_get_active(self, consensus_engine):
        consensus_engine.propose("a1", "m1", "n1", "Vote", "D", ["A"])
        active = consensus_engine.get_active()
        assert len(active) >= 1

    def test_stats(self, consensus_engine):
        consensus_engine.propose("a1", "m1", "n1", "Vote", "D", ["A"])
        stats = consensus_engine.stats()
        assert stats["total"] >= 1


# ── Conflict Resolver Tests ──────────────────────────────────

class TestConflictResolver:
    def test_detect_conflict(self, conflict_resolver):
        c = conflict_resolver.detect(
            ConflictType.DISAGREEMENT,
            ["a1", "a2"], "m1", "n1",
            "Disagreement", "Agents disagree",
        )
        assert c.conflict_id
        assert c.status.value == "detected"

    def test_propose_resolution(self, conflict_resolver):
        c = conflict_resolver.detect(
            ConflictType.DISAGREEMENT, ["a1", "a2"], "m1", "n1", "T", "D",
        )
        assert conflict_resolver.propose_resolution(c.conflict_id, "a1", "Use option A")
        assert "a1" in conflict_resolver.get(c.conflict_id).proposals

    def test_resolve(self, conflict_resolver):
        c = conflict_resolver.detect(
            ConflictType.DISAGREEMENT, ["a1", "a2"], "m1", "n1", "T", "D",
        )
        assert conflict_resolver.resolve(c.conflict_id, "Merged", "admin")
        resolved = conflict_resolver.get(c.conflict_id)
        assert resolved.status.value == "resolved"

    def test_escalate(self, conflict_resolver):
        c = conflict_resolver.detect(
            ConflictType.DISAGREEMENT, ["a1", "a2"], "m1", "n1", "T", "D",
        )
        assert conflict_resolver.escalate(c.conflict_id)
        assert conflict_resolver.get(c.conflict_id).status.value == "escalated"

    def test_auto_resolve_disagreement(self, conflict_resolver):
        c = conflict_resolver.detect(
            ConflictType.DISAGREEMENT, ["a1", "a2", "a3"], "m1", "n1", "T", "D",
        )
        conflict_resolver.propose_resolution(c.conflict_id, "a1", "Option A")
        conflict_resolver.propose_resolution(c.conflict_id, "a2", "Option A")
        conflict_resolver.propose_resolution(c.conflict_id, "a3", "Option B")
        assert conflict_resolver.auto_resolve(c.conflict_id)
        assert conflict_resolver.get(c.conflict_id).resolution == "Option A"

    def test_auto_resolve_resource(self, conflict_resolver):
        c = conflict_resolver.detect(
            ConflictType.RESOURCE_CONFLICT, ["a1", "a2"], "m1", "n1", "T", "D",
        )
        assert conflict_resolver.auto_resolve(c.conflict_id)

    def test_get_active(self, conflict_resolver):
        conflict_resolver.detect(ConflictType.DISAGREEMENT, ["a1"], "m1", "n1", "T", "D")
        active = conflict_resolver.get_active()
        assert len(active) >= 1

    def test_get_by_agent(self, conflict_resolver):
        conflict_resolver.detect(ConflictType.DISAGREEMENT, ["a1", "a2"], "m1", "n1", "T", "D")
        conflicts = conflict_resolver.get_by_agent("a1")
        assert len(conflicts) >= 1

    def test_get_by_mission(self, conflict_resolver):
        conflict_resolver.detect(ConflictType.DISAGREEMENT, ["a1"], "m1", "n1", "T", "D")
        conflicts = conflict_resolver.get_by_mission("m1")
        assert len(conflicts) >= 1

    def test_stats(self, conflict_resolver):
        conflict_resolver.detect(ConflictType.DISAGREEMENT, ["a1"], "m1", "n1", "T", "D")
        stats = conflict_resolver.stats()
        assert stats["total"] >= 1


# ── Collaboration Engine Tests ───────────────────────────────

class TestCollaborationEngine:
    def test_send_and_receive(self, engine):
        engine.send_message("coder", "reviewer", "Review", "Please review", mission_id="m1")
        inbox = engine.get_inbox("reviewer")
        assert len(inbox) >= 1

    def test_broadcast(self, engine):
        engine.broadcast_message("boss", "Standup", "Daily standup", mission_id="m1")
        msgs = engine.get_inbox("coder")
        assert len(msgs) >= 1

    def test_request_help(self, engine):
        engine.request_help("coder", "Stuck", "Need review", ["review"], mission_id="m1")
        inbox = engine.get_inbox("reviewer")
        assert len(inbox) >= 1

    def test_share_and_access_context(self, engine):
        ctx = engine.share_context("coder", "m1", "API Spec", {"endpoints": ["/users"]})
        visible = engine.get_visible_contexts("coder")
        assert len(visible) >= 1

    def test_delegate_complete(self, engine):
        d = engine.delegate_task("coder", "tester", "m1", "n1", "Write tests")
        assert engine.accept_delegation(d.delegation_id, "tester")
        assert engine.complete_delegation(d.delegation_id, "tester", "Tests done")

    def test_request_review(self, engine):
        r = engine.request_review("coder", "reviewer", "m1", "n1", "Review PR", {"diff": "..."})
        assert r.review_id
        assert engine.submit_review(r.review_id, "approved", "LGTM")

    def test_propose_and_vote_consensus(self, engine):
        p = engine.propose_consensus(
            "a1", "m1", "n1", "Architecture", "Choose approach",
            ["monolith", "microservices"],
            mode=ConsensusMode.MAJORITY, minimum_voters=3,
        )
        engine.vote(p.proposal_id, "a1", "microservices")
        engine.vote(p.proposal_id, "a2", "microservices")
        engine.vote(p.proposal_id, "a3", "monolith")
        result = engine.get_consensus(p.proposal_id)
        assert result.status == ConsensusStatus.REACHED
        assert result.winner == "microservices"

    def test_report_and_resolve_conflict(self, engine):
        c = engine.report_conflict(
            ConflictType.DISAGREEMENT, ["a1", "a2"],
            "m1", "n1", "Disagreement", "Two approaches",
        )
        # Add proposals for auto-resolution
        engine._conflicts.propose_resolution(c.conflict_id, "a1", "Option A")
        engine._conflicts.propose_resolution(c.conflict_id, "a2", "Option A")
        assert engine.auto_resolve_conflict(c.conflict_id)

    def test_mission_history(self, engine):
        engine.send_message("a1", "a2", "Test", "Body", mission_id="m1")
        engine.share_context("a1", "m1", "Result", {"x": 1})
        engine.delegate_task("a1", "a2", "m1", "n1", "Task")
        history = engine.get_mission_history("m1")
        assert history["mission_id"] == "m1"
        assert len(history["messages"]) >= 1
        assert len(history["contexts"]) >= 1
        assert len(history["delegations"]) >= 1

    def test_stats(self, engine):
        engine.send_message("a1", "a2", "S", "B")
        stats = engine.stats()
        assert "messages" in stats
        assert "contexts" in stats
        assert "delegations" in stats
        assert "consensus" in stats
        assert "conflicts" in stats


# ── Thread Safety Tests ──────────────────────────────────────

class TestThreadSafety:
    def test_concurrent_messages(self, message_bus):
        errors = []

        def worker(idx):
            try:
                message_bus.send(f"agent{idx}", f"agent{idx+1}", f"Subj{idx}", f"Body{idx}")
            except Exception as e:
                errors.append(f"Worker {idx}: {e}")

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, errors
        assert message_bus.stats()["total_messages"] >= 20

    def test_concurrent_context_sharing(self, context_sharing):
        errors = []

        def worker(idx):
            try:
                context_sharing.share("agent1", "m1", f"Result{idx}", {"i": idx})
            except Exception as e:
                errors.append(f"Worker {idx}: {e}")

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, errors
        contexts = context_sharing.get_by_owner("agent1")
        assert len(contexts) >= 10

    def test_concurrent_delegations(self, delegation_manager):
        errors = []

        def worker(idx):
            try:
                delegation_manager.delegate(f"from{idx}", f"to{idx}", "m1", f"n{idx}", f"Task{idx}")
            except Exception as e:
                errors.append(f"Worker {idx}: {e}")

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(15)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, errors
        assert delegation_manager.stats()["total"] >= 15
