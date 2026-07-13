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

TIMELINE_PATH = (
    ROOT
    / "workspace"
    / "exports"
    / PROJECT_ID
    / "movie_runtime_rc1"
    / "timeline.json"
)

OUTPUT_DIR = (
    ROOT
    / "workspace"
    / "exports"
    / PROJECT_ID
    / "semantic_director_v1_2_temporal"
)

REPORT_PATH = (
    OUTPUT_DIR
    / "temporal_assignment_report.json"
)

SUMMARY_PATH = (
    OUTPUT_DIR
    / "temporal_assignment_summary.json"
)

CATALOG_V12_PATH = (
    OUTPUT_DIR
    / "multimedia_semantic_catalog_v1_2.json"
)


# ----------------------------------------------------------------------
# Временные категории материалов
# ----------------------------------------------------------------------

HISTORICAL_ONLY_CLASSES = {
    "ship_in_ice",
    "ship_detail",
    "crew_command",
    "crew_working",
    "crew_survival",
    "ice_detail",
}

ARCHIVE_ONLY_CLASSES = {
    "archive_letter",
    "archive_map",
    "archive_records",
    "medical_records",
    "final_note",
}

MODERN_ONLY_CLASSES = {
    "underwater_robot",
    "sonar_scan",
}

MODERN_DISCOVERY_CLASSES = {
    "underwater_wreck",
}

TIME_NEUTRAL_CLASSES = {
    "arctic_aerial",
    "unclassified",
}


# ----------------------------------------------------------------------
# Ключевые слова временных фаз текста
# ----------------------------------------------------------------------

MODERN_KEYWORDS = {
    "modern",
    "today",
    "present day",
    "twenty-first century",
    "21st century",
    "robot",
    "rov",
    "remotely operated",
    "underwater vehicle",
    "underwater camera",
    "sonar",
    "scan",
    "scanning",
    "multibeam",
    "technology",
    "computer",
    "screen",
    "monitor",
    "digital",
    "3d",
    "archaeology",
    "archaeological",
    "seabed",
    "sea floor",
    "discovered",
    "discovery",
    "located",
    "found the wreck",
    "wreck was found",
    "parks canada",
    "2014",
    "2016",
}

ARCHIVE_KEYWORDS = {
    "archive",
    "archives",
    "record",
    "records",
    "document",
    "documents",
    "letter",
    "letters",
    "written",
    "note",
    "message",
    "map",
    "chart",
    "admiralty",
    "correspondence",
    "evidence",
    "report",
    "medical",
    "bones",
    "remains",
    "autopsy",
    "lead poisoning",
    "scurvy",
    "testimony",
    "researcher",
    "library",
}

HISTORICAL_KEYWORDS = {
    "1845",
    "1846",
    "1847",
    "1848",
    "nineteenth century",
    "victorian",
    "franklin",
    "captain",
    "commander",
    "officer",
    "crew",
    "sailors",
    "men",
    "expedition",
    "voyage",
    "erebus",
    "terror",
    "ship",
    "ships",
    "deck",
    "rigging",
    "hull",
    "bow",
    "ice",
    "frozen",
    "trapped",
    "drift",
    "abandoned",
    "sledge",
    "survival",
    "northwest passage",
}


def load_module(
    module_name: str,
    path: Path,
):
    if not path.exists():
        raise FileNotFoundError(path)

    spec = importlib.util.spec_from_file_location(
        module_name,
        path,
    )

    if spec is None or spec.loader is None:
        raise RuntimeError(
            f"Cannot load module: {path}"
        )

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    return module


def normalize_path(
    value: str | Path,
) -> str:
    return os.path.normcase(
        os.path.normpath(
            str(Path(value).resolve())
        )
    )


def asset_temporal_scope(
    asset: dict[str, Any],
) -> str:
    semantic_class = str(
        asset.get("semantic_class")
        or "unclassified"
    )

    if semantic_class in MODERN_ONLY_CLASSES:
        return "modern_only"

    if semantic_class in MODERN_DISCOVERY_CLASSES:
        return "modern_discovery"

    if semantic_class in ARCHIVE_ONLY_CLASSES:
        return "archive_only"

    if semantic_class in HISTORICAL_ONLY_CLASSES:
        return "historical_only"

    if semantic_class in TIME_NEUTRAL_CLASSES:
        return "time_neutral"

    return "time_neutral"


def shot_text(
    shot: dict[str, Any],
) -> str:
    values = [
        shot.get("block"),
        shot.get("story_goal"),
        shot.get("visual_need"),
        shot.get("emotion"),
    ]

    return " ".join(
        str(value or "")
        for value in values
    ).lower()


def count_keyword_matches(
    text: str,
    keywords: set[str],
) -> int:
    return sum(
        1
        for keyword in keywords
        if keyword in text
    )


def infer_shot_temporal_phase(
    shot: dict[str, Any],
) -> tuple[str, dict[str, int]]:
    text = shot_text(shot)

    scores = {
        "modern": count_keyword_matches(
            text,
            MODERN_KEYWORDS,
        ),
        "archive": count_keyword_matches(
            text,
            ARCHIVE_KEYWORDS,
        ),
        "historical": count_keyword_matches(
            text,
            HISTORICAL_KEYWORDS,
        ),
    }

    # Современная технология имеет высший приоритет.
    if scores["modern"] > 0:
        phase = "modern_discovery"

    # Документы и архивы должны распознаваться раньше
    # общего исторического контекста.
    elif scores["archive"] > 0:
        phase = "archive_research"

    elif scores["historical"] > 0:
        phase = "historical_events"

    else:
        # Нейтральные шоты могут использовать лед,
        # Арктику и переходные планы.
        phase = "time_neutral"

    return phase, scores


def temporal_compatible(
    shot_phase: str,
    asset_scope: str,
) -> bool:
    compatibility = {
        "historical_events": {
            "historical_only",
            "time_neutral",
        },
        "archive_research": {
            "archive_only",
            "time_neutral",
            "historical_only",
        },
        "modern_discovery": {
            "modern_only",
            "modern_discovery",
            "time_neutral",
            "archive_only",
        },
        "time_neutral": {
            "historical_only",
            "archive_only",
            "modern_discovery",
            "time_neutral",
        },
    }

    return asset_scope in compatibility.get(
        shot_phase,
        {"time_neutral"},
    )


def temporal_affinity_bonus(
    shot_phase: str,
    asset_scope: str,
) -> float:
    if shot_phase == "historical_events":
        if asset_scope == "historical_only":
            return 0.24
        if asset_scope == "time_neutral":
            return 0.05

    if shot_phase == "archive_research":
        if asset_scope == "archive_only":
            return 0.26
        if asset_scope == "historical_only":
            return 0.04
        if asset_scope == "time_neutral":
            return 0.03

    if shot_phase == "modern_discovery":
        if asset_scope == "modern_only":
            return 0.30
        if asset_scope == "modern_discovery":
            return 0.25
        if asset_scope == "archive_only":
            return 0.02
        if asset_scope == "time_neutral":
            return 0.02

    if shot_phase == "time_neutral":
        if asset_scope == "time_neutral":
            return 0.12

    return 0.0


def main() -> None:
    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    if not CATALOG_PATH.exists():
        raise FileNotFoundError(
            f"Catalog not found: {CATALOG_PATH}"
        )

    base_director = load_module(
        "semantic_director_v1",
        ROOT
        / "tools"
        / "semantic_director_v1.py",
    )

    multimedia_director = load_module(
        "semantic_director_v1_1_multimedia",
        ROOT
        / "tools"
        / "semantic_director_v1_1_multimedia.py",
    )

    catalog_payload = json.loads(
        CATALOG_PATH.read_text(
            encoding="utf-8"
        )
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

    assets: list[dict[str, Any]] = []
    unresolved_assets: list[str] = []

    for source in catalog_payload.get(
        "assets",
        [],
    ):
        asset = dict(source)

        asset["media_type"] = str(
            asset.get("media_type")
            or "image"
        )

        if int(asset.get("max_use") or 0) <= 0:
            continue

        if asset.get("duplicate_of"):
            continue

        media_path = Path(asset["path"])

        representative_path = Path(
            asset.get("representative_frame")
            or media_path
        )

        if (
            not media_path.exists()
            or not representative_path.exists()
        ):
            continue

        database_asset = db_by_path.get(
            normalize_path(media_path)
        )

        if database_asset is None:
            matches = db_by_filename.get(
                str(asset["filename"]).lower(),
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

        asset["temporal_scope"] = (
            asset_temporal_scope(asset)
        )

        assets.append(asset)

    if unresolved_assets:
        raise RuntimeError(
            "Assets not resolved in DB: "
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
            f"Expected 149 shots, found {len(shots)}"
        )

    shot_phases = []

    for shot in shots:
        phase, phase_scores = (
            infer_shot_temporal_phase(shot)
        )

        shot["temporal_phase"] = phase
        shot["temporal_scores"] = phase_scores

        shot_phases.append(phase)

    catalog_v12 = dict(catalog_payload)
    catalog_v12["version"] = "1.2"
    catalog_v12["temporal_guard"] = True
    catalog_v12["assets"] = assets

    CATALOG_V12_PATH.write_text(
        json.dumps(
            catalog_v12,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    if TIMELINE_PATH.exists():
        timestamp = datetime.now().strftime(
            "%Y%m%d_%H%M%S"
        )

        backup_path = (
            TIMELINE_PATH.parent
            / (
                "timeline_before_temporal_guard_"
                f"{timestamp}.json"
            )
        )

        shutil.copy2(
            TIMELINE_PATH,
            backup_path,
        )

        print("TIMELINE BACKUP =", backup_path)

    print("=" * 72)
    print(
        "ATLAS ZERO — "
        "SEMANTIC DIRECTOR V1.2 TEMPORAL GUARD"
    )
    print("=" * 72)
    print("Shots          =", len(shots))
    print("Assets         =", len(assets))
    print("Images         =", sum(
        1
        for asset in assets
        if asset["media_type"] == "image"
    ))
    print("Videos         =", sum(
        1
        for asset in assets
        if asset["media_type"] == "video"
    ))
    print(
        "Shot phases    =",
        dict(Counter(shot_phases)),
    )
    print(
        "Asset scopes   =",
        dict(
            Counter(
                asset["temporal_scope"]
                for asset in assets
            )
        ),
    )

    model = CLIPModel.from_pretrained(
        MODEL_NAME
    )

    processor = CLIPProcessor.from_pretrained(
        MODEL_NAME
    )

    model.eval()

    asset_embeddings = (
        multimedia_director.encode_assets(
            model,
            processor,
            assets,
        )
    )

    prompts = [
        base_director.shot_prompt(shot)
        for shot in shots
    ]

    text_embeddings = (
        multimedia_director.encode_texts(
            model,
            processor,
            prompts,
        )
    )

    similarities = (
        text_embeddings
        @ asset_embeddings.T
    )

    usage: Counter[str] = Counter()
    media_usage: Counter[str] = Counter()
    group_usage: Counter[str] = Counter()
    phase_usage: Counter[str] = Counter()

    recent_assets: list[str] = []
    recent_groups: list[str] = []
    recent_media: list[str] = []

    assignments: list[
        dict[str, Any]
    ] = []

    db.execute(
        """
        DELETE FROM director_decisions
        WHERE project_id=?
        """,
        (PROJECT_ID,),
    )

    for shot_position, shot in enumerate(shots):
        prompt = prompts[shot_position]
        shot_phase = shot["temporal_phase"]

        candidates = []

        for asset_position, asset in enumerate(
            assets
        ):
            asset_scope = asset["temporal_scope"]

            # Главная функция Temporal Guard:
            # несовместимые материалы полностью исключаются.
            if not temporal_compatible(
                shot_phase,
                asset_scope,
            ):
                continue

            asset_id = asset[
                "database_asset_id"
            ]

            semantic_class = str(
                asset.get("semantic_class")
                or "unclassified"
            )

            media_type = asset["media_type"]

            limit = (
                multimedia_director.asset_limit(
                    asset
                )
            )

            current_use = usage[asset_id]

            if current_use >= limit:
                continue

            clip_score = float(
                similarities[
                    shot_position,
                    asset_position,
                ]
            )

            semantic_bonus = (
                base_director.group_bonus(
                    prompt,
                    semantic_class,
                )
            )

            temporal_bonus = (
                temporal_affinity_bonus(
                    shot_phase,
                    asset_scope,
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

            reuse_penalty = (
                base_director.reuse_penalty(
                    current_use,
                    limit,
                )
            )

            neighbor_penalty = (
                base_director.consecutive_penalty(
                    asset_id,
                    recent_assets,
                )
            )

            group_penalty = (
                base_director.group_sequence_penalty(
                    semantic_class,
                    recent_groups,
                )
            )

            motion_bonus = (
                multimedia_director.video_bonus(
                    asset,
                    current_use,
                    media_usage["video"],
                    recent_media,
                )
            )

            final_score = (
                clip_score
                + semantic_bonus
                + temporal_bonus
                + unused_bonus
                + diversity_bonus
                + motion_bonus
                - reuse_penalty
                - neighbor_penalty
                - group_penalty
            )

            candidates.append(
                (
                    final_score,
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
                        "temporal_bonus": round(
                            temporal_bonus,
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
                            reuse_penalty,
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

        if not candidates:
            raise RuntimeError(
                f"No temporally compatible asset "
                f"for shot {shot['idx']} "
                f"phase={shot_phase}"
            )

        candidates.sort(
            key=lambda item: item[0],
            reverse=True,
        )

        final_score, selected, components = (
            candidates[0]
        )

        asset_id = selected[
            "database_asset_id"
        ]

        media_type = selected[
            "media_type"
        ]

        semantic_class = str(
            selected.get("semantic_class")
            or "unclassified"
        )

        asset_scope = selected[
            "temporal_scope"
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
                "semantic_class": item[1].get(
                    "semantic_class"
                ),
                "temporal_scope": item[1][
                    "temporal_scope"
                ],
                "score": round(
                    item[0],
                    5,
                ),
            }
            for item in candidates[1:4]
        ]

        reason = (
            f"Temporal Semantic Director selected "
            f"{selected['filename']}; "
            f"shot_phase={shot_phase}; "
            f"asset_scope={asset_scope}; "
            f"class={semantic_class}; "
            f"media_type={media_type}; "
            f"score={round(final_score, 5)}."
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
                round(final_score, 5),
                reason,
                json.dumps(
                    alternatives,
                    ensure_ascii=False,
                ),
            ),
        )

        usage[asset_id] += 1
        media_usage[media_type] += 1
        group_usage[semantic_class] += 1
        phase_usage[shot_phase] += 1

        recent_assets.append(asset_id)
        recent_groups.append(semantic_class)
        recent_media.append(media_type)

        assignments.append(
            {
                "shot_id": shot["id"],
                "shot_index": shot["idx"],
                "start_sec": shot["start_sec"],
                "end_sec": shot["end_sec"],
                "visual_need": shot.get(
                    "visual_need"
                ),
                "story_goal": shot.get(
                    "story_goal"
                ),
                "temporal_phase": shot_phase,
                "temporal_phase_scores": shot[
                    "temporal_scores"
                ],
                "selected_asset_id": asset_id,
                "selected_filename": selected[
                    "filename"
                ],
                "selected_path": selected[
                    "path"
                ],
                "media_type": media_type,
                "semantic_class": semantic_class,
                "asset_temporal_scope": (
                    asset_scope
                ),
                "score": round(
                    final_score,
                    5,
                ),
                "score_components": components,
                "alternatives": alternatives,
            }
        )

        print(
            f"SHOT {shot['idx']:03d} | "
            f"{shot_phase:<18} | "
            f"{asset_scope:<17} | "
            f"{media_type:<5} | "
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

    assignment_by_shot = {
        item["shot_id"]: item
        for item in assignments
    }

    violations = []

    for timeline_item in timeline:
        assignment = assignment_by_shot.get(
            timeline_item["shot_id"]
        )

        if not assignment:
            violations.append(
                {
                    "shot_id": timeline_item[
                        "shot_id"
                    ],
                    "reason": (
                        "assignment_not_found"
                    ),
                }
            )
            continue

        if not temporal_compatible(
            assignment["temporal_phase"],
            assignment[
                "asset_temporal_scope"
            ],
        ):
            violations.append(
                {
                    "shot_id": assignment[
                        "shot_id"
                    ],
                    "shot_index": assignment[
                        "shot_index"
                    ],
                    "temporal_phase": assignment[
                        "temporal_phase"
                    ],
                    "asset_temporal_scope": (
                        assignment[
                            "asset_temporal_scope"
                        ]
                    ),
                    "filename": assignment[
                        "selected_filename"
                    ],
                    "reason": (
                        "temporal_incompatibility"
                    ),
                }
            )

    timeline_media = Counter(
        str(
            row.get("media_type")
            or "missing"
        )
        for row in timeline
    )

    unique_assets = {
        row.get("asset_path")
        for row in timeline
        if row.get("asset_path")
    }

    video_usage = Counter(
        Path(row["asset_path"]).name
        for row in timeline
        if (
            row.get("media_type") == "video"
            and row.get("asset_path")
        )
    )

    modern_assets_in_historical = [
        item
        for item in assignments
        if (
            item["temporal_phase"]
            == "historical_events"
            and item[
                "asset_temporal_scope"
            ]
            in {
                "modern_only",
                "modern_discovery",
            }
        )
    ]

    report = {
        "version": "1.2",
        "project_id": PROJECT_ID,
        "state": (
            "TEMPORALLY_VALIDATED"
            if not violations
            else "TEMPORAL_VALIDATION_FAILED"
        ),
        "shots_total": len(shots),
        "assets_available": len(assets),
        "unique_assets_used": len(
            unique_assets
        ),
        "media_usage": dict(
            timeline_media
        ),
        "video_usage": dict(
            video_usage
        ),
        "shot_phase_usage": dict(
            Counter(shot_phases)
        ),
        "asset_scope_usage": dict(
            Counter(
                assignment[
                    "asset_temporal_scope"
                ]
                for assignment
                in assignments
            )
        ),
        "temporal_violations": (
            violations
        ),
        "modern_assets_in_historical": (
            modern_assets_in_historical
        ),
        "assignments": assignments,
        "timeline_result": timeline_result,
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
        "version": "1.2",
        "project_id": PROJECT_ID,
        "state": report["state"],
        "shots_total": len(shots),
        "assets_available": len(assets),
        "unique_assets_used": len(
            unique_assets
        ),
        "media_usage": dict(
            timeline_media
        ),
        "video_usage": dict(
            video_usage
        ),
        "shot_phase_usage": dict(
            Counter(shot_phases)
        ),
        "asset_scope_usage": report[
            "asset_scope_usage"
        ],
        "temporal_violations": len(
            violations
        ),
        "modern_assets_in_historical": (
            len(
                modern_assets_in_historical
            )
        ),
        "report": str(
            REPORT_PATH
        ),
        "timeline": str(
            TIMELINE_PATH
        ),
        "catalog": str(
            CATALOG_V12_PATH
        ),
    }

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
        "TEMPORAL SEMANTIC DIRECTOR RESULT"
    )
    print("=" * 72)
    print(
        json.dumps(
            summary,
            ensure_ascii=False,
            indent=2,
        )
    )

    if violations:
        raise RuntimeError(
            f"Temporal violations detected: "
            f"{len(violations)}"
        )

    if modern_assets_in_historical:
        raise RuntimeError(
            "Modern assets remain in historical shots."
        )

    if len(timeline) != 149:
        raise RuntimeError(
            f"Invalid timeline length: "
            f"{len(timeline)}"
        )

    incomplete = [
        row
        for row in timeline
        if (
            row.get("status") != "assigned"
            or not row.get("asset_path")
        )
    ]

    if incomplete:
        raise RuntimeError(
            f"Incomplete shots: "
            f"{len(incomplete)}"
        )

    print()
    print("TEMPORAL CONSISTENCY VERIFIED.")
    print("RENDER NOT STARTED.")


if __name__ == "__main__":
    main()
