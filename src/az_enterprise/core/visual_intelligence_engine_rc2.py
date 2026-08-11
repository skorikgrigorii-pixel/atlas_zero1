from __future__ import annotations

import json
import math
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from PIL import Image


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def clean_text(value: Any) -> str:
    if value is None:
        return ""

    return " ".join(str(value).strip().split())


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def cosine_similarity(
    left: Sequence[float],
    right: Sequence[float],
) -> float:
    if len(left) != len(right):
        raise ValueError("Embedding dimensions do not match")

    numerator = sum(
        float(a) * float(b)
        for a, b in zip(left, right)
    )

    left_norm = math.sqrt(
        sum(float(value) ** 2 for value in left)
    )

    right_norm = math.sqrt(
        sum(float(value) ** 2 for value in right)
    )

    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0

    raw = numerator / (left_norm * right_norm)

    # CLIP cosine typically lies between -1 and 1.
    return clamp01((raw + 1.0) / 2.0)


@dataclass(frozen=True)
class ShotCardRC2:
    shot_id: str
    index: int
    block: str
    story_goal: str
    visual_need: str
    emotion: str
    start_sec: float
    end_sec: float

    def semantic_text(self) -> str:
        parts = [
            "Historical documentary visual.",
        ]

        if self.block:
            parts.append(f"Scene: {self.block}.")

        if self.story_goal:
            parts.append(
                f"Narrative context: {self.story_goal}."
            )

        if self.visual_need:
            parts.append(
                f"Required visual: {self.visual_need}."
            )

        if self.emotion:
            parts.append(
                f"Emotion and tone: {self.emotion}."
            )

        parts.append(
            "The image must accurately support this exact scene."
        )

        return " ".join(parts)

    def to_dict(self) -> dict[str, Any]:
        return {
            "shot_id": self.shot_id,
            "index": self.index,
            "block": self.block,
            "story_goal": self.story_goal,
            "visual_need": self.visual_need,
            "emotion": self.emotion,
            "start_sec": self.start_sec,
            "end_sec": self.end_sec,
            "semantic_text": self.semantic_text(),
        }


class ClipEmbeddingBackendRC2:
    NAME = "openai/clip-vit-base-patch32"

    def __init__(self) -> None:
        self._processor = None
        self._model = None
        self._torch = None

    def _load(self) -> None:
        if self._model is not None:
            return

        import torch
        from transformers import (
            CLIPModel,
            CLIPProcessor,
        )

        print(
            "[VISUAL-INTELLIGENCE][BACKEND] "
            f"loading {self.NAME} on cpu"
        )

        self._torch = torch
        self._processor = CLIPProcessor.from_pretrained(
            self.NAME
        )
        self._model = CLIPModel.from_pretrained(
            self.NAME
        )
        self._model.eval()

        print(
            "[VISUAL-INTELLIGENCE][BACKEND] ready"
        )

    def _extract_tensor(
        self,
        output: Any,
        *,
        preferred: Sequence[str],
    ) -> Any:
        """
        Normalize different Transformers return types to a tensor.

        Depending on the installed Transformers version,
        get_text_features/get_image_features may return either
        a Tensor or a ModelOutput object.
        """
        if self._torch is None:
            raise RuntimeError(
                "CLIP backend is not loaded"
            )

        if self._torch.is_tensor(output):
            return output

        for name in preferred:
            value = getattr(output, name, None)

            if self._torch.is_tensor(value):
                return value

        if isinstance(output, dict):
            for name in preferred:
                value = output.get(name)

                if self._torch.is_tensor(value):
                    return value

            for value in output.values():
                if self._torch.is_tensor(value):
                    return value

        if isinstance(output, (tuple, list)):
            for value in output:
                if self._torch.is_tensor(value):
                    return value

        raise TypeError(
            "Unsupported CLIP feature output type: "
            f"{type(output).__name__}"
        )

    def encode_texts(
        self,
        texts: Sequence[str],
    ) -> list[list[float]]:
        self._load()

        if not texts:
            return []

        assert self._processor is not None
        assert self._model is not None
        assert self._torch is not None

        inputs = self._processor(
            text=list(texts),
            return_tensors="pt",
            padding=True,
            truncation=True,
        )

        with self._torch.no_grad():
            output = self._model.get_text_features(
                **inputs
            )

        features = self._extract_tensor(
            output,
            preferred=(
                "text_embeds",
                "pooler_output",
                "last_hidden_state",
            ),
        )

        if features.ndim == 3:
            features = features[:, 0, :]

        features = features / features.norm(
            dim=-1,
            keepdim=True,
        ).clamp_min(1e-12)

        return features.detach().cpu().tolist()

    def encode_image(
        self,
        path: Path,
    ) -> list[float]:
        self._load()

        assert self._processor is not None
        assert self._model is not None
        assert self._torch is not None

        with Image.open(path) as image:
            image = image.convert("RGB")

            inputs = self._processor(
                images=image,
                return_tensors="pt",
            )

        with self._torch.no_grad():
            output = self._model.get_image_features(
                **inputs
            )

        features = self._extract_tensor(
            output,
            preferred=(
                "image_embeds",
                "pooler_output",
                "last_hidden_state",
            ),
        )

        if features.ndim == 3:
            features = features[:, 0, :]

        features = features / features.norm(
            dim=-1,
            keepdim=True,
        ).clamp_min(1e-12)

        return features[0].detach().cpu().tolist()


class VisualIntelligenceEngineRC2:
    SCHEMA = "atlas_zero.visual_intelligence.rc2.v1"

    IMAGE_SUFFIXES = {
        ".png",
        ".jpg",
        ".jpeg",
        ".webp",
        ".bmp",
    }

    def __init__(
        self,
        *,
        root: Path | str,
        project_id: str,
        backend: ClipEmbeddingBackendRC2 | None = None,
    ) -> None:
        self.root = Path(root).resolve()
        self.project_id = clean_text(project_id)

        if not self.project_id:
            raise ValueError("project_id is required")

        self.db_path = (
            self.root
            / "workspace"
            / "atlas_zero_enterprise.sqlite3"
        )

        self.output_dir = (
            self.root
            / "workspace"
            / "exports"
            / self.project_id
            / "rc2"
            / "visual_intelligence"
        )

        self.report_path = (
            self.output_dir
            / "shot_asset_similarity_report.json"
        )

        self.review_csv_path = (
            self.output_dir
            / "shot_asset_similarity_review.csv"
        )

        self.backend = (
            backend
            if backend is not None
            else ClipEmbeddingBackendRC2()
        )

    def load_shot_cards(self) -> list[ShotCardRC2]:
        if not self.db_path.is_file():
            raise FileNotFoundError(self.db_path)

        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row

        try:
            rows = connection.execute(
                """
                SELECT
                    id,
                    idx,
                    block,
                    story_goal,
                    visual_need,
                    emotion,
                    start_sec,
                    end_sec
                FROM shots
                WHERE project_id=?
                ORDER BY idx
                """,
                (self.project_id,),
            ).fetchall()

        finally:
            connection.close()

        cards = [
            ShotCardRC2(
                shot_id=str(row["id"]),
                index=int(row["idx"]),
                block=clean_text(row["block"]),
                story_goal=clean_text(row["story_goal"]),
                visual_need=clean_text(
                    row["visual_need"]
                ),
                emotion=clean_text(row["emotion"]),
                start_sec=float(row["start_sec"]),
                end_sec=float(row["end_sec"]),
            )
            for row in rows
        ]

        if not cards:
            raise RuntimeError(
                f"No shots found for {self.project_id}"
            )

        return cards

    def load_assets(
        self,
        *,
        limit: int | None = None,
        only_unassigned: bool = False,
    ) -> list[dict[str, Any]]:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row

        query = """
            SELECT
                a.id,
                a.filename,
                a.path,
                a.media_type,
                a.quality,
                a.duplicate_of
            FROM assets a
            WHERE a.project_id=?
              AND (
                  a.duplicate_of IS NULL
                  OR TRIM(a.duplicate_of)=''
              )
        """

        parameters: list[Any] = [
            self.project_id,
        ]

        if only_unassigned:
            query += """
              AND NOT EXISTS (
                  SELECT 1
                  FROM shots s
                  WHERE s.project_id=a.project_id
                    AND s.assigned_asset_id=a.id
              )
            """

        query += " ORDER BY a.filename"

        if limit is not None:
            query += " LIMIT ?"
            parameters.append(int(limit))

        try:
            rows = connection.execute(
                query,
                tuple(parameters),
            ).fetchall()

        finally:
            connection.close()

        assets = []

        for row in rows:
            path = Path(str(row["path"] or ""))

            if (
                not path.is_file()
                or path.suffix.lower()
                not in self.IMAGE_SUFFIXES
            ):
                continue

            assets.append({
                "asset_id": str(row["id"]),
                "filename": str(row["filename"]),
                "path": str(path.resolve()),
                "media_type": str(
                    row["media_type"] or "image"
                ),
                "quality": row["quality"],
            })

        return assets

    def analyze(
        self,
        *,
        asset_limit: int | None = None,
        top_k: int = 5,
        only_unassigned_assets: bool = False,
    ) -> dict[str, Any]:
        if top_k < 1:
            raise ValueError("top_k must be >= 1")

        shots = self.load_shot_cards()
        assets = self.load_assets(
            limit=asset_limit,
            only_unassigned=only_unassigned_assets,
        )

        if not assets:
            raise RuntimeError(
                "No eligible image assets found"
            )

        self.output_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        print(
            "[VISUAL-INTELLIGENCE] "
            f"shots={len(shots)} assets={len(assets)}"
        )

        shot_texts = [
            shot.semantic_text()
            for shot in shots
        ]

        shot_vectors = self.backend.encode_texts(
            shot_texts
        )

        results = []

        for asset_index, asset in enumerate(
            assets,
            start=1,
        ):
            print(
                "[VISUAL-INTELLIGENCE][ASSET] "
                f"{asset_index}/{len(assets)} "
                f"{asset['filename']}"
            )

            try:
                image_vector = self.backend.encode_image(
                    Path(asset["path"])
                )

                scored = []

                for shot, shot_vector in zip(
                    shots,
                    shot_vectors,
                ):
                    similarity = cosine_similarity(
                        image_vector,
                        shot_vector,
                    )

                    visual_need_bonus = 0.0

                    filename_text = (
                        asset["filename"]
                        .replace("_", " ")
                        .replace("-", " ")
                        .casefold()
                    )

                    need_tokens = [
                        token.casefold()
                        for token in shot.visual_need.split()
                        if len(token) >= 4
                    ]

                    if need_tokens:
                        matched = sum(
                            1
                            for token in need_tokens
                            if token in filename_text
                        )

                        visual_need_bonus = min(
                            0.08,
                            matched
                            / max(1, len(need_tokens))
                            * 0.08,
                        )

                    final_score = clamp01(
                        similarity
                        + visual_need_bonus
                    )

                    scored.append({
                        "shot_id": shot.shot_id,
                        "shot_index": shot.index,
                        "similarity": round(
                            similarity,
                            6,
                        ),
                        "visual_need_bonus": round(
                            visual_need_bonus,
                            6,
                        ),
                        "final_score": round(
                            final_score,
                            6,
                        ),
                        "visual_need": shot.visual_need,
                        "block": shot.block,
                    })

                scored.sort(
                    key=lambda row: row["final_score"],
                    reverse=True,
                )

                results.append({
                    "asset_id": asset["asset_id"],
                    "filename": asset["filename"],
                    "path": asset["path"],
                    "status": "ANALYZED",
                    "best_matches": scored[:top_k],
                })

            except Exception as exc:
                results.append({
                    "asset_id": asset["asset_id"],
                    "filename": asset["filename"],
                    "path": asset["path"],
                    "status": "FAILED",
                    "error": str(exc),
                    "best_matches": [],
                })

        report = {
            "schema": self.SCHEMA,
            "state": "VISUAL_INTELLIGENCE_READY",
            "project_id": self.project_id,
            "backend": self.backend.NAME,
            "shot_count": len(shots),
            "asset_count": len(assets),
            "top_k": top_k,
            "created_at_utc": utc_now(),
            "shots": [
                shot.to_dict()
                for shot in shots
            ],
            "results": results,
        }

        self.report_path.write_text(
            json.dumps(
                report,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        self._write_review_csv(
            results=results,
        )

        return report

    def _write_review_csv(
        self,
        *,
        results: Sequence[dict[str, Any]],
    ) -> None:
        import csv

        with self.review_csv_path.open(
            "w",
            encoding="utf-8-sig",
            newline="",
        ) as stream:
            writer = csv.DictWriter(
                stream,
                fieldnames=[
                    "asset_id",
                    "filename",
                    "rank",
                    "shot_id",
                    "shot_index",
                    "final_score",
                    "similarity",
                    "visual_need_bonus",
                    "visual_need",
                    "block",
                    "status",
                ],
            )

            writer.writeheader()

            for result in results:
                matches = result.get(
                    "best_matches",
                    [],
                )

                if not matches:
                    writer.writerow({
                        "asset_id": result.get(
                            "asset_id"
                        ),
                        "filename": result.get(
                            "filename"
                        ),
                        "rank": "",
                        "shot_id": "",
                        "shot_index": "",
                        "final_score": "",
                        "similarity": "",
                        "visual_need_bonus": "",
                        "visual_need": "",
                        "block": "",
                        "status": result.get(
                            "status"
                        ),
                    })

                    continue

                for rank, match in enumerate(
                    matches,
                    start=1,
                ):
                    writer.writerow({
                        "asset_id": result["asset_id"],
                        "filename": result["filename"],
                        "rank": rank,
                        "shot_id": match["shot_id"],
                        "shot_index": match[
                            "shot_index"
                        ],
                        "final_score": match[
                            "final_score"
                        ],
                        "similarity": match[
                            "similarity"
                        ],
                        "visual_need_bonus": match[
                            "visual_need_bonus"
                        ],
                        "visual_need": match[
                            "visual_need"
                        ],
                        "block": match["block"],
                        "status": result["status"],
                    })
