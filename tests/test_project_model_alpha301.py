from __future__ import annotations

import pytest

from az_enterprise.core.project_model_alpha301 import (
    Asset,
    Experience,
    Project,
    ProjectStatus,
    Scene,
    SceneStatus,
    Task,
)


def make_project() -> Project:
    return Project(id="project_1", title="Hogueras Test")


def test_project_starts_at_version_one():
    project = make_project()

    assert project.version == 1
    assert project.status is ProjectStatus.DRAFT


def test_add_asset_creates_new_version():
    project = make_project()
    updated = project.add_asset(
        Asset(id="asset_1", kind="video", uri="file://clip.mp4")
    )

    assert project.assets == ()
    assert updated.version == 2
    assert len(updated.assets) == 1


def test_add_scene_with_existing_asset():
    project = make_project().add_asset(
        Asset(id="asset_1", kind="video", uri="file://clip.mp4")
    )
    updated = project.add_scene(
        Scene(
            id="scene_1",
            title="Opening",
            order=0,
            duration_seconds=5.0,
            status=SceneStatus.READY,
            asset_ids=("asset_1",),
        )
    )

    assert updated.version == 3
    assert updated.scenes[0].asset_ids == ("asset_1",)


def test_missing_scene_asset_is_rejected():
    with pytest.raises(ValueError, match="missing assets"):
        Project(
            id="project_1",
            title="Broken",
            scenes=(
                Scene(
                    id="scene_1",
                    title="Opening",
                    order=0,
                    duration_seconds=5.0,
                    asset_ids=("missing",),
                ),
            ),
        )


def test_duplicate_scene_order_is_rejected():
    with pytest.raises(ValueError, match="order"):
        Project(
            id="project_1",
            title="Broken",
            scenes=(
                Scene("scene_1", "A", 0, 1.0),
                Scene("scene_2", "B", 0, 1.0),
            ),
        )


def test_task_can_be_added():
    project = make_project().add_task(
        Task(id="task_1", target="visual", description="Replace clip")
    )

    assert project.tasks[0].target == "visual"


def test_experience_requires_valid_confidence():
    with pytest.raises(ValueError, match="confidence"):
        Experience(
            id="exp_1",
            observation="Retention improved",
            confidence=1.2,
            source_project_ids=("project_1",),
        )


def test_json_round_trip():
    project = (
        make_project()
        .add_asset(Asset("asset_1", "video", "file://clip.mp4"))
        .add_scene(Scene("scene_1", "Opening", 0, 5.0, asset_ids=("asset_1",)))
        .add_experience(
            Experience(
                id="exp_1",
                observation="Fast opening improved retention",
                confidence=0.8,
                source_project_ids=("project_1",),
            )
        )
    )

    restored = Project.from_json(project.to_json())

    assert restored == project
