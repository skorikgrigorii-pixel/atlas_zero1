import sqlite3

from az_enterprise.core.events import EventBus

from az_enterprise.core.director_learning_adapter_rc1 import (
    DirectorLearningAdapterRC1,
)

from az_enterprise.core.learning_core_rc1 import (
    LearningCoreRC1,
)


class DB:
    def __init__(self):
        self.conn = sqlite3.connect(":memory:")

    def execute(self, sql, params=()):
        cursor = self.conn.execute(sql, params)
        self.conn.commit()
        return cursor

    def executemany(self, sql, params):
        cursor = self.conn.executemany(sql, params)
        self.conn.commit()
        return cursor

    def executescript(self, sql):
        cursor = self.conn.executescript(sql)
        self.conn.commit()
        return cursor


def test_director_learning_adapter_rc1():

    db = DB()

    bus = EventBus(
        db=None,
        project_id="movie",
    )

    learning = LearningCoreRC1(
        db=db,
        project_id="movie",
    )

    adapter = DirectorLearningAdapterRC1(
        db=db,
        project_id="movie",
        event_bus=bus,
    )

    learning.record_observation(
        scope="platform:youtube",
        key="ctr",
        value=0.065,
        confidence=0.80,
        evidence={
            "source": "test"
        },
    )

    bus.emit(
        "LEARNING_UPDATED",
        {
            "project_id": "movie",
        },
    )

    advisory = adapter.latest_advisory()

    assert advisory is not None

    assert (
        advisory["state"]
        == "DIRECTOR_LEARNING_ADVISORY_READY"
    )

    assert (
        advisory["decision_authority"]
        == "DirectorAI"
    )

    assert (
        advisory["permissions"][
            "override_director"
        ]
        is False
    )

    assert advisory["profile_count"] == 1
