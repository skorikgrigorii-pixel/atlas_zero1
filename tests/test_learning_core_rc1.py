import sqlite3

from az_enterprise.core.learning_core_rc1 import (
    LearningCoreRC1,
)


class DB:
    def __init__(self):
        self.conn = sqlite3.connect(":memory:")


def test_learning_core_rc1():
    db = DB()

    learning = LearningCoreRC1(
        db=db,
        project_id="test_movie",
    )

    first = learning.record_observation(
        scope="platform:youtube",
        key="ctr",
        value=0.05,
        confidence=0.6,
        evidence={"source": "test"},
    )

    assert (
        first["state"]
        == "LEARNING_OBSERVATION_RECORDED"
    )

    learning.record_observation(
        scope="platform:youtube",
        key="ctr",
        value=0.07,
        confidence=0.8,
        evidence={"source": "test2"},
    )

    profile = learning.profile(
        scope="platform:youtube",
        key="ctr",
    )

    assert profile is not None
    assert profile["evidence_count"] == 2
    assert 0 <= profile["confidence"] <= 1

    result = learning.learn_from_performance(
        {
            "state":
                "PERFORMANCE_SUMMARY_READY",
            "platform":
                "youtube",
            "latest": {
                "id": 2,
                "ctr": 0.07,
            },
            "engagement_rate":
                0.12,
            "deltas": {
                "views": 100,
            },
        }
    )

    assert result["state"] == "LEARNING_UPDATED"
    assert result["observations"] == 3
