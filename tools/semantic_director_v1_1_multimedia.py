from __future__ import annotations

import importlib.util
import json
import os
import shutil
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

import torch
from PIL import Image, ImageOps
from transformers import CLIPModel, CLIPProcessor


ROOT = Path.cwd()
SRC = ROOT / "src"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from az_enterprise.core.database import Database
from az_enterprise.core.movie_runtime_rc1 import MovieRuntimeRC1


PROJECT_ID = "franklin"
MODEL_NAME = "openai/clip-vit-base-patch32"

CATALOG_PATH = (
    ROOT
    / "workspace"
    / "exports"
    / PROJECT_ID
    / "visual_intelligence_v1_1"
    / "multimedia_semantic_catalog.json"
)

OUTPUT_DIR = (
    ROOT
    / "workspace"
    / "exports"
    / PROJECT_ID
    / "semantic_director_v1_1"
)

REPORT_PATH = (
    OUTPUT_DIR
    / "multimedia_assignment_report.json"
)

SUMMARY_PATH = (
    OUTPUT_DIR
    / "multimedia_assignment_summary.json"
)

TIMELINE_PATH = (
    ROOT
    / "workspace"
    / "exports"
    / PROJECT_ID
    / "movie_runtime_rc1"
    / "timeline.json"
)


def load_base_module():
    path = ROOT / "tools" / "semantic_director_v1.py"

    if not path.exists():
        raise FileNotFoundError(
            f"Base Semantic Director not found: {path}"
        )

    spec = importlib.util.spec_from_file_location(
        "semantic_director_v1",
        path,
    )

    if spec is None or spec.loader is None:
        raise RuntimeError(
            "Cannot load semantic_director_v1.py"
        )

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    return module


def normalize_path(value: str | Path) -> str:
    return os.path.normcase(
        os.path.normpath(
            str(Path(value).resolve())
        )
    )


def load_image(path: Path) -> Image.Image:
    with Image.open(path) as source:
        source = ImageOps.exif_transpose(source)
        return source.convert("RGB")


def extract_tensor(
    output: Any,
    preferred_attribute: str,
) -> torch.Tensor:
    if isinstance(output, torch.Tensor):
        return output

    if hasattr(output, preferred_attribute):
        return getattr(
            output,
            preferred_attribute,
        )

    if hasattr(output, "pooler_output"):
        return output.pooler_output

    if hasattr(output, "last_hidden_state"):
        return output.last_hidden_state[:, 0, :]

    raise TypeError(
        f"Unsupported CLIP output: {type(output)!r}"
    )


def encode_assets(
    model: CLIPModel,
    processor: CLIPProcessor,
    assets: list[dict[str, Any]],
) -> torch.Tensor:
    embeddings: list[torch.Tensor] = []

    for index, asset in enumerate(
        assets,
        start=1,
    ):
        visual_path = Path(
            asset.get("representative_frame")
            or asset["path"]
        )

        if not visual_path.exists():
            raise FileNotFoundError(
                f"Representative visual not found: {visual_path}"
            )

        image = load_image(
            visual_path
        )

        inputs = processor(
            images=image,
            return_tensors="pt",
        )

        with torch.no_grad():
            output = model.get_image_features(
                **inputs
            )

        feature = extract_tensor(
            output,
            "image_embeds",
        )

        feature = (
            feature
            / feature.norm(
                dim=-1,
                keepdim=True,
            ).clamp(min=1e-12)
        )

        embeddings.append(
            feature.cpu()
        )

        print(
            f"ASSET EMBEDDING "
            f"{index:03d}/{len(assets):03d} | "
            f"{asset['media_type']:<5} | "
            f"{asset['filename']}"
        )

    return torch.cat(
        embeddings,
        dim=0,
    )


def encode_texts(
    model: CLIPModel,
    processor: CLIPProcessor,
    texts: list[str],
) -> torch.Tensor:
    embeddings: list[torch.Tensor] = []
    batch_size = 24

    for start in range(
        0,
        len(texts),
        batch_size,
    ):
        batch = texts[
            start:start + batch_size
        ]

        inputs = processor(
            text=batch,
            return_tensors="pt",
            padding=True,
            truncation=True,
        )

        with torch.no_grad():
            output = model.get_text_features(
                **inputs
            )

        feature = extract_tensor(
            output,
            "text_embeds",
        )

        feature = (
            feature
            / feature.norm(
                dim=-1,
                keepdim=True,
            ).clamp(min=1e-12)
        )

        embeddings.append(
            feature.cpu()
        )

        print(
            f"TEXT EMBEDDING "
            f"{min(start + batch_size, len(texts)):03d}/"
            f"{len(texts):03d}"
        )

    return torch.cat(
        embeddings,
        dim=0,
    )


def asset_limit(
    asset: dict[str, Any],
) -> int:
    if asset["media_type"] == "video":
        return 3

    semantic_class = str(
        asset.get("semantic_class")
        or ""
    )

    if semantic_class in {
        "final_note",
        "medical_records",
        "archive_letter",
        "archive_map",
        "archive_records",
        "sonar_scan",
        "underwater_robot",
        "underwater_wreck",
    }:
        return 3

    if semantic_class in {
        "ship_in_ice",
        "ship_detail",
    }:
        return 6

    return 4


def video_bonus(
    asset: dict[str, Any],
    current_use: int,
    total_video_assignments: int,
    recent_media: list[str],
) -> float:
    if asset["media_type"] != "video":
        return 0.0

    if current_use >= asset_limit(asset):
        return -10.0

    bonus = 0.16

    # Первые девять видеошотов получают дополнительный приоритет:
    # три ролика допускаются максимум по три раза.
    if total_video_assignments < 9:
        bonus += 0.14

    # Не ставим видео слишком близко друг к другу.
    if "video" in recent_media[-3:]:
        bonus -= 0.40

    return bonus


def main() -> None:
    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    if not CATALOG_PATH.exists():
        raise FileNotFoundError(
            f"Multimedia catalog not found: {CATALOG_PATH}"
        )

    base = load_base_module()

    catalog = json.loads(
        CATALOG_PATH.read_text(
            encoding="utf-8"
        )
    )

    assets = []

    for source in catalog.get(
        "assets",
        [],
    ):
        asset = dict(source)

        asset["media_type"] = str(
            asset.get("media_type")
            or "image"
        )

        if int(
            asset.get("max_use")
            or 0
        ) <= 0:
            continue

        if asset.get(
            "duplicate_of"
        ):
            continue

        media_path = Path(
            asset["path"]
        )

        visual_path = Path(
            asset.get(
                "representative_frame"
            )
            or media_path
        )

        if (
            not media_path.exists()
            or not visual_path.exists()
        ):
            continue

        assets.append(asset)

    image_assets = [
        item
        for item in assets
        if item["media_type"] == "image"
    ]

    video_assets = [
        item
        for item in assets
        if item["media_type"] == "video"
    ]

    if not assets:
        raise RuntimeError(
            "No usable multimedia assets."
        )

    if not video_assets:
        raise RuntimeError(
            "No usable video assets in catalog."
        )

    db = Database()
    db.init()

    db_assets = [
        dict(row)
        for row in db.rows(
            """
            SELECT
                id,
                path,
                filename,
                media_type
            FROM assets
            WHERE project_id=?
              AND media_type IN ('image','video')
            """,
            (PROJECT_ID,),
        )
    ]

    db_by_path = {
        normalize_path(row["path"]): row
        for row in db_assets
    }

    db_by_filename: dict[
        str,
        list[dict[str, Any]]
    ] = {}

    for row in db_assets:
        db_by_filename.setdefault(
            str(row["filename"]).lower(),
            [],
        ).append(row)

    # Сразу заменяем каталожные идентификаторы
    # на реальные идентификаторы базы.
    unresolved_assets = []

    for asset in assets:
        database_asset = db_by_path.get(
            normalize_path(
                asset["path"]
            )
        )

        if database_asset is None:
            matches = db_by_filename.get(
                str(
                    asset["filename"]
                ).lower(),
                [],
            )

            if len(matches) == 1:
                database_asset = matches[0]

        if database_asset is None:
            unresolved_assets.append(
                asset["filename"]
            )
            continue

        asset["database_asset_id"] = str(
            database_asset["id"]
        )

    if unresolved_assets:
        raise RuntimeError(
            "Assets not resolved in database: "
            + ", ".join(unresolved_assets)
        )

    shots = [
        dict(row)
        for row in db.rows(
            """
            SELECT
                id,
                idx,
                start_sec,
                end_sec,
                block,
                story_goal,
                visual_need,
                emotion
            FROM shots
            WHERE project_id=?
            ORDER BY idx
            """,
            (PROJECT_ID,),
        )
    ]

    if len(shots) != 149:
        raise RuntimeError(
            f"Expected 149 shots, found {len(shots)}."
        )

    if TIMELINE_PATH.exists():
        timestamp = datetime.now().strftime(
            "%Y%m%d_%H%M%S"
        )

        backup = (
            TIMELINE_PATH.parent
            / (
                "timeline_before_multimedia_"
                f"{timestamp}.json"
            )
        )

        shutil.copy2(
            TIMELINE_PATH,
            backup,
        )

        print("TIMELINE BACKUP =", backup)

    print("=" * 72)
    print(
        "ATLAS ZERO — "
        "SEMANTIC DIRECTOR V1.1 MULTIMEDIA"
    )
    print("=" * 72)
    print("Shots         =", len(shots))
    print("Images usable =", len(image_assets))
    print("Videos usable =", len(video_assets))
    print("Assets total  =", len(assets))

    model = CLIPModel.from_pretrained(
        MODEL_NAME
    )

    processor = CLIPProcessor.from_pretrained(
        MODEL_NAME
    )

    model.eval()

    asset_embeddings = encode_assets(
        model,
        processor,
        assets,
    )

    prompts = [
        base.shot_prompt(shot)
        for shot in shots
    ]

    text_embeddings = encode_texts(
        model,
        processor,
        prompts,
    )

    similarities = (
        text_embeddings
        @ asset_embeddings.T
    )

    usage: Counter[str] = Counter()
    group_usage: Counter[str] = Counter()
    media_usage: Counter[str] = Counter()

    recent_assets: list[str] = []
    recent_groups: list[str] = []
    recent_media: list[str] = []

    assignments = []

    db.execute(
        """
        DELETE FROM director_decisions
        WHERE project_id=?
        """,
        (PROJECT_ID,),
    )

    for shot_position, shot in enumerate(
        shots
    ):
        prompt = prompts[
            shot_position
        ]

        candidates = []

        for asset_position, asset in enumerate(
            assets
        ):
            asset_id = asset[
                "database_asset_id"
            ]

            semantic_class = str(
                asset.get(
                    "semantic_class"
                )
                or "unclassified"
            )

            media_type = asset[
                "media_type"
            ]

            current_use = usage[
                asset_id
            ]

            limit = asset_limit(
                asset
            )

            if current_use >= limit:
                hard_limit_penalty = 5.0
            else:
                hard_limit_penalty = 0.0

            clip_score = float(
                similarities[
                    shot_position,
                    asset_position,
                ]
            )

            semantic_bonus = (
                base.group_bonus(
                    prompt,
                    semantic_class,
                )
            )

            unused_bonus = (
                0.11
                if current_use == 0
                else 0.0
            )

            diversity_bonus = (
                0.045
                / (
                    1
                    + group_usage[
                        semantic_class
                    ]
                )
            )

            repetition_penalty = (
                base.reuse_penalty(
                    current_use,
                    limit,
                )
            )

            neighbor_penalty = (
                base.consecutive_penalty(
                    asset_id,
                    recent_assets,
                )
            )

            group_penalty = (
                base.group_sequence_penalty(
                    semantic_class,
                    recent_groups,
                )
            )

            motion_bonus = video_bonus(
                asset,
                current_use,
                media_usage["video"],
                recent_media,
            )

            score = (
                clip_score
                + semantic_bonus
                + unused_bonus
                + diversity_bonus
                + motion_bonus
                - repetition_penalty
                - neighbor_penalty
                - group_penalty
                - hard_limit_penalty
            )

            candidates.append(
                (
                    score,
                    asset,
                    {
                        "clip_similarity": round(
                            clip_score,
                            5,
                        ),
                        "semantic_bonus": round(
                            semantic_bonus,
                            5,
                        ),
                        "unused_bonus": round(
                            unused_bonus,
                            5,
                        ),
                        "diversity_bonus": round(
                            diversity_bonus,
                            5,
                        ),
                        "video_bonus": round(
                            motion_bonus,
                            5,
                        ),
                        "reuse_penalty": round(
                            repetition_penalty,
                            5,
                        ),
                        "neighbor_penalty": round(
                            neighbor_penalty,
                            5,
                        ),
                        "group_penalty": round(
                            group_penalty,
                            5,
                        ),
                    },
                )
            )

        candidates.sort(
            key=lambda item: item[0],
            reverse=True,
        )

        score, selected, components = (
            candidates[0]
        )

        asset_id = selected[
            "database_asset_id"
        ]

        semantic_class = str(
            selected.get(
                "semantic_class"
            )
            or "unclassified"
        )

        media_type = selected[
            "media_type"
        ]

        db.execute(
            """
            UPDATE shots
            SET
                assigned_asset_id=?,
                status='assigned'
            WHERE project_id=?
              AND id=?
            """,
            (
                asset_id,
                PROJECT_ID,
                shot["id"],
            ),
        )

        alternatives = [
            {
                "filename": item[1][
                    "filename"
                ],
                "media_type": item[1][
                    "media_type"
                ],
                "semantic_class": (
                    item[1].get(
                        "semantic_class"
                    )
                ),
                "score": round(
                    item[0],
                    5,
                ),
            }
            for item in candidates[1:4]
        ]

        reason = (
            f"Multimedia Semantic Director selected "
            f"{selected['filename']}; "
            f"media_type={media_type}; "
            f"class={semantic_class}; "
            f"score={round(score, 5)}."
        )

        db.execute(
            """
            INSERT INTO director_decisions(
                project_id,
                shot_id,
                asset_id,
                score,
                reason,
                alternatives
            )
            VALUES(?,?,?,?,?,?)
            """,
            (
                PROJECT_ID,
                shot["id"],
                asset_id,
                round(score, 5),
                reason,
                json.dumps(
                    alternatives,
                    ensure_ascii=False,
                ),
            ),
        )

        usage[asset_id] += 1
        group_usage[
            semantic_class
        ] += 1
        media_usage[
            media_type
        ] += 1

        recent_assets.append(
            asset_id
        )
        recent_groups.append(
            semantic_class
        )
        recent_media.append(
            media_type
        )

        assignments.append(
            {
                "shot_id": shot["id"],
                "shot_index": shot["idx"],
                "selected_asset_id": (
                    asset_id
                ),
                "selected_filename": (
                    selected["filename"]
                ),
                "selected_path": (
                    selected["path"]
                ),
                "media_type": media_type,
                "semantic_class": (
                    semantic_class
                ),
                "score": round(
                    score,
                    5,
                ),
                "score_components": (
                    components
                ),
                "usage_after": (
                    usage[asset_id]
                ),
                "alternatives": (
                    alternatives
                ),
            }
        )

        print(
            f"SHOT {shot['idx']:03d} | "
            f"{media_type:<5} | "
            f"{semantic_class:<18} | "
            f"{selected['filename']}"
        )

    runtime = MovieRuntimeRC1(
        db,
        PROJECT_ID,
    )

    timeline_result = (
        runtime._build_timeline()
    )

    timeline = json.loads(
        TIMELINE_PATH.read_text(
            encoding="utf-8"
        )
    )

    timeline_media = Counter(
        str(
            row.get("media_type")
            or "missing"
        )
        for row in timeline
    )

    timeline_video_paths = Counter(
        str(row["asset_path"])
        for row in timeline
        if (
            row.get("media_type")
            == "video"
            and row.get("asset_path")
        )
    )

    unique_assets = {
        row.get("asset_path")
        for row in timeline
        if row.get("asset_path")
    }

    incomplete = [
        row
        for row in timeline
        if (
            row.get("status")
            != "assigned"
            or not row.get("asset_path")
        )
    ]

    report = {
        "version": "1.1",
        "project_id": PROJECT_ID,
        "state": (
            "MULTIMEDIA_SEMANTICALLY_ASSIGNED"
        ),
        "shots_total": len(shots),
        "assets_available": len(assets),
        "images_available": len(
            image_assets
        ),
        "videos_available": len(
            video_assets
        ),
        "unique_assets_used": len(
            unique_assets
        ),
        "media_usage": dict(
            timeline_media
        ),
        "unique_videos_used": len(
            timeline_video_paths
        ),
        "video_usage": [
            {
                "filename": Path(
                    path
                ).name,
                "uses": count,
            }
            for path, count
            in timeline_video_paths.most_common()
        ],
        "group_usage": dict(
            group_usage
        ),
        "incomplete": len(
            incomplete
        ),
        "assignments": assignments,
        "timeline_result": (
            timeline_result
        ),
    }

    REPORT_PATH.write_text(
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    summary = {
        key: value
        for key, value in report.items()
        if key != "assignments"
    }

    summary["report"] = str(
        REPORT_PATH
    )

    summary["timeline"] = str(
        TIMELINE_PATH
    )

    SUMMARY_PATH.write_text(
        json.dumps(
            summary,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print()
    print("=" * 72)
    print(
        "MULTIMEDIA SEMANTIC DIRECTOR RESULT"
    )
    print("=" * 72)
    print(
        json.dumps(
            summary,
            ensure_ascii=False,
            indent=2,
        )
    )

    if len(timeline) != 149:
        raise RuntimeError(
            "Timeline shot count is invalid."
        )

    if incomplete:
        raise RuntimeError(
            f"Incomplete timeline: {len(incomplete)}"
        )

    if timeline_media.get(
        "video",
        0,
    ) < 3:
        raise RuntimeError(
            "Too few video shots were assigned."
        )

    if len(
        timeline_video_paths
    ) != 3:
        raise RuntimeError(
            "Not all three videos were used."
        )


if __name__ == "__main__":
    main()
