from __future__ import annotations

import pytest

from backend.core.message_bus import MessageBus, MessageType


def _bus(tmp_path) -> MessageBus:
    return MessageBus(str(tmp_path / "bus.db"))


def test_publish_persists_and_returns_message(tmp_path):
    bus = _bus(tmp_path)

    message = bus.publish(
        from_agent="atlas",
        to_agent="aegis",
        type_=MessageType.VALIDATION_REQUEST,
        payload={"action_type": "file_write"},
        task_id="task-1",
    )

    assert message.from_agent == "atlas"
    assert message.to_agent == "aegis"
    assert message.type == "VALIDATION_REQUEST"
    assert message.payload == {"action_type": "file_write"}
    assert message.task_id == "task-1"
    assert message.timestamp is not None


def test_publish_accepts_plain_string_type(tmp_path):
    bus = _bus(tmp_path)

    message = bus.publish(from_agent="a", to_agent="b", type_="TASK_RESULT")

    assert message.type == "TASK_RESULT"


def test_publish_rejects_unknown_type(tmp_path):
    bus = _bus(tmp_path)

    with pytest.raises(ValueError):
        bus.publish(from_agent="a", to_agent="b", type_="NOT_A_REAL_TYPE")


def test_publish_defaults_payload_to_empty_dict(tmp_path):
    bus = _bus(tmp_path)

    message = bus.publish(from_agent="a", to_agent="b", type_=MessageType.MEMORY_QUERY)

    assert message.payload == {}
    assert message.task_id is None


def test_to_dict_matches_spec_contract(tmp_path):
    bus = _bus(tmp_path)

    message = bus.publish(
        from_agent="atlas",
        to_agent="aegis",
        type_=MessageType.VALIDATION_REQUEST,
        payload={"x": 1},
        task_id="t1",
    )

    data = message.to_dict()

    assert set(data) == {
        "id",
        "from",
        "to",
        "type",
        "payload",
        "timestamp",
        "task_id",
        "project_id",
    }
    assert data["from"] == "atlas"
    assert data["to"] == "aegis"
    assert data["type"] == "VALIDATION_REQUEST"
    assert data["payload"] == {"x": 1}
    assert data["task_id"] == "t1"


def test_list_messages_filters_by_task_id(tmp_path):
    bus = _bus(tmp_path)
    bus.publish(from_agent="a", to_agent="b", type_=MessageType.TASK_DELEGATION, task_id="t1")
    bus.publish(from_agent="a", to_agent="b", type_=MessageType.TASK_RESULT, task_id="t2")

    messages = bus.list_messages(task_id="t1")

    assert len(messages) == 1
    assert messages[0].task_id == "t1"


def test_list_messages_filters_by_agent_matches_either_side(tmp_path):
    bus = _bus(tmp_path)
    bus.publish(from_agent="atlas", to_agent="aegis", type_=MessageType.VALIDATION_REQUEST)
    bus.publish(from_agent="aegis", to_agent="atlas", type_=MessageType.VALIDATION_GRANTED)
    bus.publish(from_agent="echo", to_agent="minerva", type_=MessageType.MEMORY_QUERY)

    messages = bus.list_messages(agent="atlas")

    assert len(messages) == 2
    assert all("atlas" in (m.from_agent, m.to_agent) for m in messages)


def test_list_messages_filters_by_project_id(tmp_path):
    bus = _bus(tmp_path)
    bus.publish(
        from_agent="a", to_agent="b", type_=MessageType.TASK_DELEGATION, project_id="proj-1"
    )
    bus.publish(
        from_agent="a", to_agent="b", type_=MessageType.TASK_RESULT, project_id="proj-2"
    )

    messages = bus.list_messages(project_id="proj-1")

    assert len(messages) == 1
    assert messages[0].project_id == "proj-1"


def test_list_messages_respects_limit(tmp_path):
    bus = _bus(tmp_path)
    for _ in range(5):
        bus.publish(from_agent="a", to_agent="b", type_=MessageType.TASK_DELEGATION)

    messages = bus.list_messages(limit=2)

    assert len(messages) == 2


def test_subscribe_is_notified_synchronously_on_publish(tmp_path):
    bus = _bus(tmp_path)
    received = []
    bus.subscribe(received.append)

    message = bus.publish(from_agent="a", to_agent="b", type_=MessageType.ESCALATION)

    assert received == [message]


def test_unsubscribe_stops_notifications(tmp_path):
    bus = _bus(tmp_path)
    received = []
    unsubscribe = bus.subscribe(received.append)
    unsubscribe()

    bus.publish(from_agent="a", to_agent="b", type_=MessageType.ESCALATION)

    assert received == []
