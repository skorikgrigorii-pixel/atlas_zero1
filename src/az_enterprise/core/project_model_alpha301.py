"""ATLAS ZERO Alpha 3.0.1 — minimal Unified Project Model."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
import json
from typing import Any, Mapping
from uuid import uuid4


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ProjectStatus(str, Enum):
    DRAFT = "DRAFT"
    IN_PROGRESS = "IN_PROGRESS"
    REVIEW = "REVIEW"
    APPROVED = "APPROVED"
    PUBLISHED = "PUBLISHED"
    ARCHIVED = "ARCHIVED"


class SceneStatus(str, Enum):
    DRAFT = "DRAFT"
    READY = "READY"
    REWORK = "REWORK"
    APPROVED = "APPROVED"


class ExperienceStatus(str, Enum):
    OBSERVED = "OBSERVED"
    VALIDATED = "VALIDATED"
    REJECTED = "REJECTED"
    PROMOTED = "PROMOTED"


@dataclass(frozen=True)
class Asset:
    id: str
    kind: str
    uri: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.id or not self.kind or not self.uri:
            raise ValueError("asset id, kind and uri are required")


@dataclass(frozen=True)
class Scene:
    id: str
    title: str
    order: int
    duration_seconds: float
    narration: str = ""
    status: SceneStatus = SceneStatus.DRAFT
    asset_ids: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.id or not self.title:
            raise ValueError("scene id and title are required")
        if self.order < 0:
            raise ValueError("scene order cannot be negative")
        if self.duration_seconds < 0:
            raise ValueError("scene duration cannot be negative")


@dataclass(frozen=True)
class Task:
    id: str
    target: str
    description: str
    completed: bool = False

    def __post_init__(self) -> None:
        if not self.id or not self.target or not self.description:
            raise ValueError("task id, target and description are required")


@dataclass(frozen=True)
class Experience:
    id: str
    observation: str
    confidence: float
    source_project_ids: tuple[str, ...]
    status: ExperienceStatus = ExperienceStatus.OBSERVED
    evidence: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.id or not self.observation:
            raise ValueError("experience id and observation are required")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("experience confidence must be between 0 and 1")
        if not self.source_project_ids:
            raise ValueError("experience requires source projects")


@dataclass(frozen=True)
class Project:
    id: str
    title: str
    version: int = 1
    status: ProjectStatus = ProjectStatus.DRAFT
    scenes: tuple[Scene, ...] = ()
    assets: tuple[Asset, ...] = ()
    tasks: tuple[Task, ...] = ()
    experiences: tuple[Experience, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        if not self.id or not self.title:
            raise ValueError("project id and title are required")
        if self.version < 1:
            raise ValueError("project version must be at least 1")
        self.validate()

    def validate(self) -> None:
        self._ensure_unique("scene", [item.id for item in self.scenes])
        self._ensure_unique("asset", [item.id for item in self.assets])
        self._ensure_unique("task", [item.id for item in self.tasks])
        self._ensure_unique(
            "experience", [item.id for item in self.experiences]
        )

        asset_ids = {asset.id for asset in self.assets}
        missing = {
            asset_id
            for scene in self.scenes
            for asset_id in scene.asset_ids
            if asset_id not in asset_ids
        }
        if missing:
            raise ValueError(
                "scenes reference missing assets: " + ", ".join(sorted(missing))
            )

        orders = [scene.order for scene in self.scenes]
        if len(orders) != len(set(orders)):
            raise ValueError("scene order values must be unique")

    @staticmethod
    def _ensure_unique(label: str, values: list[str]) -> None:
        if len(values) != len(set(values)):
            raise ValueError(f"duplicate {label} ids are not allowed")

    def evolve(self, **changes: Any) -> "Project":
        changes.setdefault("version", self.version + 1)
        changes.setdefault("updated_at", utc_now())
        return replace(self, **changes)

    def add_scene(self, scene: Scene) -> "Project":
        return self.evolve(scenes=self.scenes + (scene,))

    def add_asset(self, asset: Asset) -> "Project":
        return self.evolve(assets=self.assets + (asset,))

    def add_task(self, task: Task) -> "Project":
        return self.evolve(tasks=self.tasks + (task,))

    def add_experience(self, experience: Experience) -> "Project":
        return self.evolve(experiences=self.experiences + (experience,))

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        for scene in data["scenes"]:
            scene["status"] = scene["status"].value
        for experience in data["experiences"]:
            experience["status"] = experience["status"].value
        return data

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Project":
        return cls(
            id=str(data["id"]),
            title=str(data["title"]),
            version=int(data.get("version", 1)),
            status=ProjectStatus(data.get("status", ProjectStatus.DRAFT.value)),
            scenes=tuple(
                Scene(
                    **{
                        **scene,
                        "status": SceneStatus(
                            scene.get("status", SceneStatus.DRAFT.value)
                        ),
                        "asset_ids": tuple(scene.get("asset_ids", ())),
                    }
                )
                for scene in data.get("scenes", ())
            ),
            assets=tuple(Asset(**asset) for asset in data.get("assets", ())),
            tasks=tuple(Task(**task) for task in data.get("tasks", ())),
            experiences=tuple(
                Experience(
                    **{
                        **experience,
                        "status": ExperienceStatus(
                            experience.get(
                                "status", ExperienceStatus.OBSERVED.value
                            )
                        ),
                        "source_project_ids": tuple(
                            experience.get("source_project_ids", ())
                        ),
                    }
                )
                for experience in data.get("experiences", ())
            ),
            metadata=data.get("metadata", {}),
            created_at=str(data.get("created_at", utc_now())),
            updated_at=str(data.get("updated_at", utc_now())),
        )

    @classmethod
    def from_json(cls, payload: str) -> "Project":
        return cls.from_dict(json.loads(payload))
