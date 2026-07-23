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
