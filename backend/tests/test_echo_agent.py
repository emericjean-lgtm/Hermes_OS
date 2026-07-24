from __future__ import annotations


def test_remember_and_list_memories(echo_agent):
    echo_agent.remember(type_="preference", content="reply in French")
    entries = echo_agent.list_memories(type_="preference")
    assert [e.content for e in entries] == ["reply in French"]


def test_remember_deduplicates(echo_agent):
    first = echo_agent.remember(type_="preference", content="reply in French")
    second = echo_agent.remember(type_="preference", content="reply in French")
    assert first.id == second.id


def test_forget_removes_entry(echo_agent):
    entry = echo_agent.remember(type_="decision", content="use qwen3-coder for code review")
    assert echo_agent.forget(entry.id) is True
    assert echo_agent.list_memories(type_="decision") == []


def test_forget_unknown_id_returns_false(echo_agent):
    assert echo_agent.forget("does-not-exist") is False


def test_remember_scopes_dedup_by_project(echo_agent):
    global_entry = echo_agent.remember(type_="preference", content="reply in French")
    project_entry = echo_agent.remember(
        type_="preference", content="reply in French", project_id="proj-1"
    )

    assert global_entry.id != project_entry.id
    assert project_entry.project_id == "proj-1"


def test_list_memories_filters_by_project_id(echo_agent):
    echo_agent.remember(type_="preference", content="a", project_id="proj-1")
    echo_agent.remember(type_="preference", content="b", project_id="proj-2")
    echo_agent.remember(type_="preference", content="c")

    assert [e.content for e in echo_agent.list_memories(project_id="proj-1")] == ["a"]


def test_memory_persists_across_agent_instances_via_same_sqlite_file(echo_agent, models_config, fake_ollama_client):
    from backend.agents.echo import EchoAgent
    from backend.core.router import ModelRouter

    echo_agent.remember(type_="preference", content="dark theme")

    # A second EchoAgent built against the same (env-isolated) SQLITE_PATH
    # should see the entry the first one wrote — proves it's actually
    # persisted to disk, not just held in memory on the instance.
    router = ModelRouter(models_config)
    second_agent = EchoAgent(fake_ollama_client, router, models_config)
    assert [e.content for e in second_agent.list_memories(type_="preference")] == ["dark theme"]


def test_remember_skill_and_list_skills(echo_agent):
    echo_agent.remember_skill(name="Fix flaky test", confidence=0.6)
    skills = echo_agent.list_skills()
    assert [s.name for s in skills] == ["Fix flaky test"]


def test_get_skill_returns_none_for_unknown_id(echo_agent):
    assert echo_agent.get_skill("does-not-exist") is None


def test_use_skill_updates_confidence(echo_agent):
    skill = echo_agent.remember_skill(name="Deploy", confidence=0.5)
    updated = echo_agent.use_skill(skill.id, success=True)
    assert updated.confidence > 0.5
    assert updated.uses == 1


def test_forget_skill_removes_it(echo_agent):
    skill = echo_agent.remember_skill(name="Deploy", confidence=0.5)
    assert echo_agent.forget_skill(skill.id) is True
    assert echo_agent.get_skill(skill.id) is None


def test_list_skills_filters_by_project_id(echo_agent):
    echo_agent.remember_skill(name="A", confidence=0.5, project_id="proj-1")
    echo_agent.remember_skill(name="B", confidence=0.5, project_id="proj-2")

    assert [s.name for s in echo_agent.list_skills(project_id="proj-1")] == ["A"]


def test_decay_skills_is_noop_when_disabled(echo_agent):
    echo_agent.remember_skill(name="A", confidence=0.5)
    # EBBINGHAUS_DECAY_ENABLED defaults to False in the walking skeleton.
    assert echo_agent.decay_skills() == 0
    assert echo_agent.get_skill(echo_agent.list_skills()[0].id).confidence == 0.5
