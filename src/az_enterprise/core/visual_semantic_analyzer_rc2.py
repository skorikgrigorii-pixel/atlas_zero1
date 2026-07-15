from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol, Sequence

import numpy as np

from .database import Database
from .visual_understanding_contract_rc2 import (
    AssetUnderstandingRC2,
)


EVENT_LABELS: dict[str, tuple[str, ...]] = {
    "monument": (
        "a large colorful artistic festival monument "
        "in the streets of Alicante",
        "a giant satirical sculpture for Hogueras",
        "festival figures and ninots displayed outdoors",
    ),
    "parade": (
        "a Spanish festival parade with people walking",
        "musicians and costumed participants in a street parade",
        "crowds watching a festive procession",
    ),
    "flower_offering": (
        "people carrying flowers in a ceremonial procession",
        "a Spanish festival floral offering",
        "traditional costumes and bouquets of flowers",
    ),
    "mascleta": (
        "daytime pyrotechnic explosions with smoke in a city square",
        "a loud daytime fireworks display called mascleta",
        "crowds watching smoke and firecrackers during daylight",
    ),
    "fireworks": (
        "large fireworks exploding in the night sky",
        "night fireworks above a city or beach",
        "crowds watching a colorful fireworks display",
    ),
    "crema": (
        "a giant festival monument burning at night",
        "firefighters near a burning Hogueras sculpture",
        "a large public bonfire during a Spanish festival",
    ),
    "street_festival": (
        "busy decorated city streets during a festival",
        "crowds celebrating outdoors in Alicante",
        "street party with lights music and people",
    ),
    "music_band": (
        "a marching band playing instruments in the street",
        "musicians performing during a Spanish festival",
        "brass band and drums in a public procession",
    ),
    "beach_event": (
        "people celebrating on a Mediterranean beach",
        "festival gathering near the sea at night",
        "crowds and fireworks on a beach",
    ),
    "city_context": (
        "Alicante city streets and urban landmarks",
        "Spanish city architecture and public squares",
        "a wide establishing view of Alicante",
    ),
    "preparation": (
        "workers assembling a large festival sculpture",
        "artists preparing Hogueras monuments",
        "festival construction and preparation work",
    ),
    "firefighters": (
        "firefighters spraying water during a public festival",
        "fire crews protecting crowds near a large fire",
        "firefighters beside a burning monument",
    ),
    "crowd_reaction": (
        "excited crowd filming a public celebration",
        "people reacting to fireworks or a festival event",
        "spectators holding mobile phones in a crowd",
    ),
    "unrelated_private_content": (
        "a private indoor family photograph unrelated to a festival",
        "a household object or personal selfie",
        "an unrelated animal car food or private scene",
    ),
}


TIME_LABELS: dict[str, tuple[str, ...]] = {
    "morning": (
        "an outdoor scene in soft morning light",
    ),
    "day": (
        "a bright daytime outdoor scene",
        "an event taking place during daylight",
    ),
    "evening": (
        "an outdoor event around sunset or dusk",
        "city streets in evening light",
    ),
    "night": (
        "a dark nighttime outdoor scene with artificial lights",
        "a night event with fireworks or illuminated streets",
    ),
}


TOPIC_LABELS: dict[str, tuple[str, ...]] = {
    "relevant": (
        "Hogueras de Alicante festival",
        "Fogueres de Sant Joan celebration in Alicante",
        "Spanish public festival with monuments "
        "parades fireworks or bonfires",
    ),
    "off_topic": (
        "private everyday content unrelated to a public festival",
        "personal household travel or family media "
        "not connected with Hogueras",
        "an unrelated subject with no festival context",
    ),
}


@dataclass(frozen=True)
class SemanticPredictionRC2:
    label: str
    score: float
    scores: dict[str, float]


class SemanticBackendRC2(Protocol):
    name: str

    def classify(
        self,
        images: Sequence[Any],
        labels: dict[str, tuple[str, ...]],
    ) -> SemanticPredictionRC2:
        ...


class HuggingFaceClipBackendRC2:
    """Local HuggingFace CLIP zero-shot backend."""

    name = "huggingface_clip_vit_base_patch32"

    def __init__(
        self,
        model_name: str = "openai/clip-vit-base-patch32",
        local_files_only: bool = True,
    ) -> None:
        try:
            import torch
            from transformers import (
                CLIPModel,
                CLIPProcessor,
            )
        except ImportError as exc:
            raise RuntimeError(
                "torch and transformers are required"
            ) from exc

        self.torch = torch
        self.processor = CLIPProcessor.from_pretrained(
            model_name,
            local_files_only=local_files_only,
        )
        self.model = CLIPModel.from_pretrained(
            model_name,
            local_files_only=local_files_only,
        )
        self.model.eval()

        self.device = (
            "cuda"
            if torch.cuda.is_available()
            else "cpu"
        )
        self.model.to(self.device)

    def classify(
        self,
        images: Sequence[Any],
        labels: dict[str, tuple[str, ...]],
    ) -> SemanticPredictionRC2:
        if not images:
            raise ValueError(
                "At least one image is required"
            )

        prompts: list[str] = []
        prompt_labels: list[str] = []

        for label, descriptions in labels.items():
            for description in descriptions:
                prompts.append(description)
                prompt_labels.append(label)

        aggregate: dict[str, list[float]] = {
            label: []
            for label in labels
        }

        for image in images:
            inputs = self.processor(
                text=prompts,
                images=image,
                return_tensors="pt",
                padding=True,
            )

            inputs = {
                key: value.to(self.device)
                for key, value in inputs.items()
            }

            with self.torch.no_grad():
                outputs = self.model(**inputs)

            probabilities = (
                outputs.logits_per_image
                .softmax(dim=1)
                .detach()
                .cpu()
                .numpy()[0]
            )

            per_label: dict[str, list[float]] = {
                label: []
                for label in labels
            }

            for prompt_label, probability in zip(
                prompt_labels,
                probabilities,
            ):
                per_label[prompt_label].append(
                    float(probability)
                )

            for label, values in per_label.items():
                aggregate[label].append(max(values))

        scores = {
            label: float(np.mean(values))
            for label, values in aggregate.items()
        }

        total = sum(scores.values()) or 1.0
        normalized = {
            label: value / total
            for label, value in scores.items()
        }

        winner = max(
            normalized,
            key=normalized.get,
        )

        return SemanticPredictionRC2(
            label=winner,
            score=round(normalized[winner], 6),
            scores={
                key: round(value, 6)
                for key, value in normalized.items()
            },
        )


class VisualSemanticAnalyzerRC2:
    """Understand individual image and video assets.

    This module does not create event clusters or story chronology.
    It produces one AssetUnderstandingRC2 record per source asset.
    """

    def __init__(
        self,
        db: Database,
        project_id: str,
        backend: SemanticBackendRC2 | None = None,
        video_frames: int = 4,
    ) -> None:
        self.db = db
        self.project_id = project_id
        self.backend = (
            backend
            if backend is not None
            else HuggingFaceClipBackendRC2()
        )
        self.video_frames = max(1, video_frames)

    def analyze(
        self,
        *,
        limit: int | None = None,
        asset_ids: Sequence[str] | None = None,
    ) -> dict[str, Any]:
        rows = self._load_assets(
            limit=limit,
            asset_ids=asset_ids,
        )

        results: list[AssetUnderstandingRC2] = []
        failures: list[dict[str, str]] = []

        total = len(rows)

        for index, row in enumerate(rows, start=1):
            try:
                result = self._analyze_asset(dict(row))
                results.append(result)

                print(
                    f"[SEMANTIC] {index}/{total} "
                    f"{row['filename']} "
                    f"=> {result.event_type} "
                    f"({result.event_confidence:.3f}) "
                    f"{result.relevance_status}"
                )

            except Exception as exc:
                failures.append({
                    "asset_id": str(row["id"]),
                    "filename": str(row["filename"]),
                    "error": str(exc),
                })

                print(
                    f"[SEMANTIC][FAILED] "
                    f"{index}/{total} "
                    f"{row['filename']} "
                    f"=> {exc}"
                )

        return {
            "engine": "visual_semantic_analyzer_rc2",
            "backend": self.backend.name,
            "project_id": self.project_id,
            "assets_requested": total,
            "assets_analyzed": len(results),
            "assets_failed": len(failures),
            "results": [
                item.to_dict()
                for item in results
            ],
            "failures": failures,
            "created_at": datetime.now(
                timezone.utc
            ).isoformat(),
        }

    def _load_assets(
        self,
        *,
        limit: int | None,
        asset_ids: Sequence[str] | None,
    ):
        parameters: list[Any] = [
            self.project_id,
        ]

        cv_table_exists = self.db.one(
            """
            SELECT 1
            FROM sqlite_master
            WHERE type='table'
              AND name='cv_asset_metadata'
            """
        ) is not None

        if cv_table_exists:
            cv_columns = """
                c.duration_sec AS cv_duration_sec,
                c.cinematic_grade,
                c.brightness,
                c.contrast,
                c.blur_score,
                c.quality_flags
            """

            cv_join = """
                LEFT JOIN cv_asset_metadata c
                  ON c.asset_id=a.id
                 AND c.project_id=a.project_id
            """
        else:
            cv_columns = """
                NULL AS cv_duration_sec,
                NULL AS cinematic_grade,
                NULL AS brightness,
                NULL AS contrast,
                NULL AS blur_score,
                NULL AS quality_flags
            """

            cv_join = ""

        sql = f"""
            SELECT
                a.id,
                a.filename,
                a.path,
                a.media_type,
                a.created_at,
                a.duration_sec,
                {cv_columns}
            FROM assets a
            {cv_join}
            WHERE a.project_id=?
        """

        if asset_ids:
            placeholders = ",".join(
                "?"
                for _ in asset_ids
            )

            sql += (
                f" AND a.id IN ({placeholders})"
            )

            parameters.extend(asset_ids)

        sql += " ORDER BY a.filename"

        if limit is not None:
            sql += " LIMIT ?"
            parameters.append(
                max(0, int(limit))
            )

        return self.db.rows(
            sql,
            parameters,
        )


    def _analyze_asset(
        self,
        asset: dict[str, Any],
    ) -> AssetUnderstandingRC2:
        path = Path(asset["path"])

        if not path.exists():
            raise FileNotFoundError(path)

        images = self._extract_images(
            path,
            str(asset["media_type"]),
        )

        event = self.backend.classify(
            images,
            EVENT_LABELS,
        )
        period = self.backend.classify(
            images,
            TIME_LABELS,
        )
        topic = self.backend.classify(
            images,
            TOPIC_LABELS,
        )

        relevant_score = float(
            topic.scores.get("relevant", 0.0)
        )
        off_topic_score = float(
            topic.scores.get("off_topic", 0.0)
        )

        if (
            event.label == "unrelated_private_content"
            and event.score >= 0.32
        ):
            off_topic_score = max(
                off_topic_score,
                event.score,
            )

        relevance_status = self._relevance_status(
            relevant_score=relevant_score,
            off_topic_score=off_topic_score,
            event_type=event.label,
        )

        story_value = self._story_value(
            event_type=event.label,
            event_score=event.score,
            relevant_score=relevant_score,
            cinematic_grade=asset.get(
                "cinematic_grade"
            ),
        )

        timestamp = self._timestamp_from_filename(
            str(asset["filename"])
        )

        detected_objects = self._objects_for_event(
            event.label
        )
        detected_actions = self._actions_for_event(
            event.label
        )

        description = (
            f"CLIP identified the material as "
            f"'{event.label}' with confidence "
            f"{event.score:.3f}; probable time period "
            f"is '{period.label}'."
        )

        evidence = {
            "backend": self.backend.name,
            "event_scores": event.scores,
            "time_scores": period.scores,
            "topic_scores": topic.scores,
            "frames_analyzed": len(images),
            "cinematic_grade": asset.get(
                "cinematic_grade"
            ),
            "quality_flags": asset.get(
                "quality_flags"
            ),
        }

        result = AssetUnderstandingRC2(
            asset_id=str(asset["id"]),
            filename=str(asset["filename"]),
            media_type=str(asset["media_type"]),
            event_type=event.label,
            event_confidence=event.score,
            relevance_status=relevance_status,
            relevance_score=round(
                relevant_score,
                6,
            ),
            off_topic_score=round(
                off_topic_score,
                6,
            ),
            time_period=period.label,
            description=description,
            story_value=story_value,
            detected_objects=detected_objects,
            detected_actions=detected_actions,
            location_hint=(
                "Alicante"
                if relevance_status != "OFF_TOPIC"
                else None
            ),
            chronology_timestamp=timestamp,
            evidence=evidence,
        )

        result.validate()
        return result

    def _extract_images(
        self,
        path: Path,
        media_type: str,
    ) -> list[Any]:
        if media_type == "image":
            from PIL import Image

            with Image.open(path) as image:
                return [
                    image.convert("RGB").copy()
                ]

        if media_type != "video":
            raise ValueError(
                f"Unsupported media type: {media_type}"
            )

        try:
            import cv2
            from PIL import Image
        except ImportError as exc:
            raise RuntimeError(
                "OpenCV and Pillow are required"
            ) from exc

        capture = cv2.VideoCapture(str(path))

        if not capture.isOpened():
            raise RuntimeError(
                f"Cannot open video: {path}"
            )

        frame_count = int(
            capture.get(
                cv2.CAP_PROP_FRAME_COUNT
            )
            or 0
        )

        if frame_count <= 0:
            capture.release()
            raise RuntimeError(
                f"Video has no readable frames: {path}"
            )

        positions = np.linspace(
            0,
            max(frame_count - 1, 0),
            num=min(
                self.video_frames,
                frame_count,
            ),
            dtype=int,
        )

        images: list[Any] = []

        try:
            for position in positions:
                capture.set(
                    cv2.CAP_PROP_POS_FRAMES,
                    int(position),
                )

                ok, frame = capture.read()

                if not ok or frame is None:
                    continue

                rgb = cv2.cvtColor(
                    frame,
                    cv2.COLOR_BGR2RGB,
                )

                images.append(
                    Image.fromarray(rgb)
                )

        finally:
            capture.release()

        if not images:
            raise RuntimeError(
                f"No keyframes extracted: {path}"
            )

        return images

    @staticmethod
    def _relevance_status(
        *,
        relevant_score: float,
        off_topic_score: float,
        event_type: str,
    ) -> str:
        if (
            off_topic_score >= 0.58
            or (
                event_type
                == "unrelated_private_content"
                and off_topic_score >= 0.42
            )
        ):
            return "OFF_TOPIC"

        margin = relevant_score - off_topic_score

        if (
            relevant_score >= 0.55
            and margin >= 0.12
        ):
            return "RELEVANT"

        return "UNCERTAIN"

    @staticmethod
    def _story_value(
        *,
        event_type: str,
        event_score: float,
        relevant_score: float,
        cinematic_grade: Any,
    ) -> float:
        event_importance = {
            "crema": 1.0,
            "fireworks": 0.94,
            "mascleta": 0.94,
            "monument": 0.90,
            "parade": 0.84,
            "flower_offering": 0.82,
            "preparation": 0.82,
            "firefighters": 0.82,
            "music_band": 0.72,
            "street_festival": 0.70,
            "crowd_reaction": 0.66,
            "city_context": 0.62,
            "beach_event": 0.60,
            "unrelated_private_content": 0.0,
        }.get(event_type, 0.45)

        try:
            grade = float(cinematic_grade)
        except (TypeError, ValueError):
            grade = 0.5

        value = (
            event_importance * 0.40
            + event_score * 0.25
            + relevant_score * 0.20
            + max(0.0, min(1.0, grade)) * 0.15
        )

        return round(
            max(0.0, min(1.0, value)),
            6,
        )

    @staticmethod
    def _timestamp_from_filename(
        filename: str,
    ) -> str | None:
        patterns = (
            r"(?P<y>20\d{2})[-_]"
            r"(?P<m>\d{2})[-_]"
            r"(?P<d>\d{2})[-_]"
            r"(?P<h>\d{2})"
            r"(?P<mi>\d{2})"
            r"(?P<s>\d{2})",
            r"(?P<y>20\d{2})"
            r"(?P<m>\d{2})"
            r"(?P<d>\d{2})[_-]"
            r"(?P<h>\d{2})"
            r"(?P<mi>\d{2})"
            r"(?P<s>\d{2})",
        )

        for pattern in patterns:
            match = re.search(
                pattern,
                filename,
            )

            if match is None:
                continue

            values = {
                key: int(value)
                for key, value
                in match.groupdict().items()
            }

            try:
                timestamp = datetime(
                    values["y"],
                    values["m"],
                    values["d"],
                    values["h"],
                    values["mi"],
                    values["s"],
                    tzinfo=timezone.utc,
                )
            except ValueError:
                continue

            return timestamp.isoformat()

        return None

    @staticmethod
    def _objects_for_event(
        event_type: str,
    ) -> tuple[str, ...]:
        return {
            "monument": (
                "festival_monument",
                "ninot",
            ),
            "parade": (
                "crowd",
                "participants",
                "street",
            ),
            "flower_offering": (
                "flowers",
                "traditional_costumes",
                "crowd",
            ),
            "mascleta": (
                "smoke",
                "pyrotechnics",
                "crowd",
            ),
            "fireworks": (
                "fireworks",
                "night_sky",
                "crowd",
            ),
            "crema": (
                "fire",
                "burning_monument",
                "crowd",
            ),
            "music_band": (
                "musicians",
                "instruments",
            ),
            "firefighters": (
                "firefighters",
                "water",
                "fire",
            ),
            "unrelated_private_content": (
                "unrelated_subject",
            ),
        }.get(event_type, (event_type,))

    @staticmethod
    def _actions_for_event(
        event_type: str,
    ) -> tuple[str, ...]:
        return {
            "parade": (
                "walking",
                "performing",
            ),
            "flower_offering": (
                "carrying_flowers",
                "procession",
            ),
            "mascleta": (
                "exploding",
                "watching",
            ),
            "fireworks": (
                "exploding",
                "watching",
                "filming",
            ),
            "crema": (
                "burning",
                "watching",
            ),
            "music_band": (
                "playing_music",
                "marching",
            ),
            "firefighters": (
                "spraying_water",
                "controlling_fire",
            ),
        }.get(event_type, ())
