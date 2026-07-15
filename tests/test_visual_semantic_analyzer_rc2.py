from pathlib import Path

from PIL import Image

from az_enterprise.core.database import Database
from az_enterprise.core.visual_semantic_analyzer_rc2 import (
    SemanticPredictionRC2,
    VisualSemanticAnalyzerRC2,
)


class FakeSemanticBackend:
    name = "fake_semantic_backend"

    def classify(self, images, labels):
        keys = set(labels)

        if "monument" in keys:
            return SemanticPredictionRC2(
                label="parade",
                score=0.8,
                scores={
                    key: (
                        0.8
                        if key == "parade"
                        else 0.2 / (len(keys) - 1)
                    )
                    for key in keys
                },
            )

        if "night" in keys:
            return SemanticPredictionRC2(
                label="day",
                score=0.9,
                scores={
                    key: (
                        0.9
                        if key == "day"
                        else 0.1 / (len(keys) - 1)
                    )
                    for key in keys
                },
            )

        return SemanticPredictionRC2(
            label="relevant",
            score=0.9,
            scores={
                "relevant": 0.9,
                "off_topic": 0.1,
            },
        )


class FakeOffTopicBackend(FakeSemanticBackend):
    def classify(self, images, labels):
        keys = set(labels)

        if "monument" in keys:
            return SemanticPredictionRC2(
                label="unrelated_private_content",
                score=0.7,
                scores={
                    key: (
                        0.7
                        if key
                        == "unrelated_private_content"
                        else 0.3 / (len(keys) - 1)
                    )
                    for key in keys
                },
            )

        if "night" in keys:
            return super().classify(images, labels)

        return SemanticPredictionRC2(
            label="off_topic",
            score=0.8,
            scores={
                "relevant": 0.2,
                "off_topic": 0.8,
            },
        )


def prepare_database(tmp_path):
    db = Database(tmp_path / "semantic.sqlite3")
    db.init()

    image_path = tmp_path / "20260621_171648.jpg"

    Image.new(
        "RGB",
        (64, 64),
        (200, 100, 50),
    ).save(image_path)

    db.execute(
        """
        INSERT INTO projects(
            id,
            title,
            duration_sec
        )
        VALUES(?,?,?)
        """,
        (
            "hogueras",
            "Hogueras",
            0,
        ),
    )

    db.execute(
        """
        INSERT INTO assets(
            id,
            project_id,
            path,
            filename,
            media_type
        )
        VALUES(?,?,?,?,?)
        """,
        (
            "asset-1",
            "hogueras",
            str(image_path),
            image_path.name,
            "image",
        ),
    )

    return db


def test_analyzer_returns_one_record_per_asset(
    tmp_path,
):
    db = prepare_database(tmp_path)

    analyzer = VisualSemanticAnalyzerRC2(
        db,
        "hogueras",
        backend=FakeSemanticBackend(),
    )

    result = analyzer.analyze()

    assert result["assets_requested"] == 1
    assert result["assets_analyzed"] == 1
    assert result["assets_failed"] == 0

    row = result["results"][0]

    assert row["asset_id"] == "asset-1"
    assert row["event_type"] == "parade"
    assert row["time_period"] == "day"
    assert row["relevance_status"] == "RELEVANT"


def test_filename_timestamp_is_extracted(
    tmp_path,
):
    db = prepare_database(tmp_path)

    analyzer = VisualSemanticAnalyzerRC2(
        db,
        "hogueras",
        backend=FakeSemanticBackend(),
    )

    result = analyzer.analyze()

    timestamp = result["results"][0][
        "chronology_timestamp"
    ]

    assert timestamp.startswith(
        "2026-06-21T17:16:48"
    )


def test_off_topic_material_is_detected(
    tmp_path,
):
    db = prepare_database(tmp_path)

    analyzer = VisualSemanticAnalyzerRC2(
        db,
        "hogueras",
        backend=FakeOffTopicBackend(),
    )

    result = analyzer.analyze()

    row = result["results"][0]

    assert row["relevance_status"] == "OFF_TOPIC"
    assert row["off_topic_score"] >= 0.5


def test_story_value_stays_in_valid_range(
    tmp_path,
):
    db = prepare_database(tmp_path)

    analyzer = VisualSemanticAnalyzerRC2(
        db,
        "hogueras",
        backend=FakeSemanticBackend(),
    )

    result = analyzer.analyze()

    value = result["results"][0]["story_value"]

    assert 0.0 <= value <= 1.0


def test_limit_is_respected(tmp_path):
    db = prepare_database(tmp_path)

    analyzer = VisualSemanticAnalyzerRC2(
        db,
        "hogueras",
        backend=FakeSemanticBackend(),
    )

    result = analyzer.analyze(limit=0)

    assert result["assets_requested"] == 0
    assert result["assets_analyzed"] == 0
