from __future__ import annotations

import pytest
from sqlalchemy import create_engine

from backend.memory import skill_library as sl
from backend.memory.db import init_db, make_session_factory


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:", future=True)
    init_db(engine)
    factory = make_session_factory(engine)
    with factory() as s:
        yield s


def test_create_skill_defaults(session):
    skill = sl.create_skill(session, name="Fix flaky test", confidence=0.6)
    assert skill.uses == 0
    assert skill.successes == 0
    assert skill.decay == 0.0
    assert skill.tags_list == []
    assert skill.project_id is None


def test_create_skill_with_tags_and_project(session):
    skill = sl.create_skill(
        session, name="Deploy", confidence=0.5, tags=["ops", "ci"], project_id="proj-1"
    )
    assert skill.tags_list == ["ops", "ci"]
    assert skill.project_id == "proj-1"


def test_list_skills_filters_by_project_and_tag(session):
    sl.create_skill(session, name="A", confidence=0.5, project_id="proj-1", tags=["x"])
    sl.create_skill(session, name="B", confidence=0.5, project_id="proj-2", tags=["y"])
    sl.create_skill(session, name="C", confidence=0.5, project_id="proj-1", tags=["y"])

    assert {s.name for s in sl.list_skills(session, project_id="proj-1")} == {"A", "C"}
    assert {s.name for s in sl.list_skills(session, tag="y")} == {"B", "C"}


def test_list_skills_orders_by_confidence_descending(session):
    sl.create_skill(session, name="low", confidence=0.2)
    sl.create_skill(session, name="high", confidence=0.9)
    names = [s.name for s in sl.list_skills(session)]
    assert names == ["high", "low"]


def test_record_use_success_increases_confidence(session):
    skill = sl.create_skill(session, name="A", confidence=0.5)
    updated = sl.record_use(session, skill.id, success=True, reinforcement=0.1)
    assert updated.confidence == pytest.approx(0.6)
    assert updated.uses == 1
    assert updated.successes == 1


def test_record_use_failure_decreases_confidence(session):
    skill = sl.create_skill(session, name="A", confidence=0.5)
    updated = sl.record_use(session, skill.id, success=False, reinforcement=0.1)
    assert updated.confidence == pytest.approx(0.4)
    assert updated.uses == 1
    assert updated.successes == 0


def test_record_use_clamps_confidence_to_0_1_range(session):
    skill = sl.create_skill(session, name="A", confidence=0.98)
    updated = sl.record_use(session, skill.id, success=True, reinforcement=0.5)
    assert updated.confidence == 1.0

    skill2 = sl.create_skill(session, name="B", confidence=0.02)
    updated2 = sl.record_use(session, skill2.id, success=False, reinforcement=0.5)
    assert updated2.confidence == 0.0


def test_record_use_returns_none_for_unknown_skill(session):
    assert sl.record_use(session, "does-not-exist", success=True) is None


def test_apply_decay_reduces_confidence_for_every_skill(session):
    sl.create_skill(session, name="A", confidence=0.5)
    sl.create_skill(session, name="B", confidence=0.05)

    touched = sl.apply_decay(session, rate=0.1)

    assert touched == 2
    skills = {s.name: s for s in sl.list_skills(session)}
    assert skills["A"].confidence == pytest.approx(0.4)
    assert skills["A"].decay == pytest.approx(0.1)
    assert skills["B"].confidence == 0.0  # clamped, was 0.05 - 0.1


def test_delete_skill(session):
    skill = sl.create_skill(session, name="A", confidence=0.5)
    assert sl.delete_skill(session, skill.id) is True
    assert sl.get_skill(session, skill.id) is None
    assert sl.delete_skill(session, skill.id) is False


def test_status_for_thresholds():
    kwargs = {"min_confidence": 0.30, "auto_validate_threshold": 0.95}
    assert sl.status_for(0.10, **kwargs) == "below_floor"
    assert sl.status_for(0.30, **kwargs) == "in_review"
    assert sl.status_for(0.94, **kwargs) == "in_review"
    assert sl.status_for(0.95, **kwargs) == "validated"
    assert sl.status_for(1.0, **kwargs) == "validated"
