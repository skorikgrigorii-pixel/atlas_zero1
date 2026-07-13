from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from az_enterprise.core.database import Database
from az_enterprise.core.movie_runtime_rc1 import MovieRuntimeRC1


PROJECT_ID = "franklin"

EXPORT_DIR = (
    ROOT
    / "workspace"
    / "exports"
    / PROJECT_ID
    / "media_factory_rc1"
)

PROMPT_PACK_JSON = EXPORT_DIR / "missing_prompt_pack.json"
PROMPT_PACK_MD = EXPORT_DIR / "missing_prompt_pack.md"
ASSIGNMENT_REPORT = EXPORT_DIR / "roughcut_assignments.json"

STOP_WORDS = {
    "the", "and", "for", "with", "from", "into", "over",
    "under", "this", "that", "scene", "shot", "film",
    "история", "показать", "материал", "сцена", "кадр",
    "для", "как", "что", "это", "или", "при", "без",
}


def normalize_words(value: Any) -> set[str]:
    text = str(value or "").lower()

    words = re.findall(
        r"[a-zа-яё0-9]+",
        text,
        flags=re.IGNORECASE,
    )

    return {
        word
        for word in words
        if len(word) >= 3 and word not in STOP_WORDS
    }


def parse_tags(raw: Any) -> list[str]:
    if not raw:
        return []

    try:
        value = json.loads(raw)

        if isinstance(value, list):
            return [str(item) for item in value]
    except (TypeError, ValueError, json.JSONDecodeError):
        pass

    return [
        item.strip(" '\"")
        for item in str(raw).strip("[]").split(",")
        if item.strip()
    ]


def asset_text(asset: dict[str, Any]) -> str:
    return " ".join(
        [
            str(asset.get("filename") or ""),
            str(asset.get("category") or ""),
            str(asset.get("emotion") or ""),
            " ".join(parse_tags(asset.get("tags"))),
        ]
    )


def shot_text(shot: dict[str, Any]) -> str:
    return " ".join(
        [
            str(shot.get("visual_need") or ""),
            str(shot.get("story_goal") or ""),
            str(shot.get("emotion") or ""),
            str(shot.get("block") or ""),
        ]
    )


def score_candidate(
    shot: dict[str, Any],
    asset: dict[str, Any],
    usage: Counter[str],
) -> float:
    shot_words = normalize_words(shot_text(shot))
    asset_words = normalize_words(asset_text(asset))

    overlap = len(shot_words & asset_words)
    coverage = (
        overlap / max(len(shot_words), 1)
    )

    quality = float(asset.get("quality") or 0.0)

    emotion_bonus = 0.0

    if (
        shot.get("emotion")
        and asset.get("emotion")
        and str(shot["emotion"]).lower()
        == str(asset["emotion"]).lower()
    ):
        emotion_bonus = 0.15

    media_bonus = (
        0.04
        if asset.get("media_type") == "video"
        else 0.0
    )

    # Материалы можно повторять, но система распределяет их
    # по фильму, чтобы один файл не захватил весь монтаж.
    reuse_penalty = min(
        0.55,
        usage[str(asset["id"])] * 0.055,
    )

    duplicate_penalty = (
        0.25
        if asset.get("duplicate_of")
        else 0.0
    )

    score = (
        quality
        + coverage * 0.75
        + overlap * 0.08
        + emotion_bonus
        + media_bonus
        - reuse_penalty
        - duplicate_penalty
    )

    return round(score, 4)


def make_prompt(shot: dict[str, Any]) -> str:
    return (
        f"Create a cinematic historical documentary visual. "
        f"Visual requirement: {shot.get('visual_need')}. "
        f"Narrative purpose: {shot.get('story_goal')}. "
        f"Emotion: {shot.get('emotion')}. "
        f"Block: {shot.get('block')}. "
        f"Cold Arctic atmosphere, restrained realism, "
        f"period-accurate 1840s Franklin expedition, "
        f"cinematic lighting, no modern objects, "
        f"16:9, 1920x1080."
    )


def write_prompt_pack(
    missing_shots: list[dict[str, Any]],
) -> None:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)

    rows: list[dict[str, Any]] = []

    for shot in missing_shots:
        key = (
            str(shot.get("visual_need") or "unspecified")
            .strip()
            .lower()
        )

        item = {
            "shot_id": shot["id"],
            "shot_index": shot["idx"],
            "block": shot.get("block"),
            "visual_need": shot.get("visual_need"),
            "emotion": shot.get("emotion"),
            "story_goal": shot.get("story_goal"),
            "start_sec": shot.get("start_sec"),
            "end_sec": shot.get("end_sec"),
            "prompt": make_prompt(shot),
        }

        rows.append(item)
        groups[key].append(item)

    payload = {
        "project_id": PROJECT_ID,
        "missing_shots": len(rows),
        "unique_visual_needs": len(groups),
        "items": rows,
        "groups": {
            key: {
                "count": len(items),
                "shot_ids": [
                    item["shot_id"]
                    for item in items
                ],
                "master_prompt": items[0]["prompt"],
            }
            for key, items in sorted(groups.items())
        },
    }

    PROMPT_PACK_JSON.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    markdown = [
        "# ATLAS ZERO — Media Factory RC1",
        "",
        f"Project: {PROJECT_ID}",
        f"Missing shots: {len(rows)}",
        f"Unique visual needs: {len(groups)}",
        "",
        "## Generation groups",
        "",
    ]

    for index, (key, items) in enumerate(
        sorted(
            groups.items(),
            key=lambda pair: (
                -len(pair[1]),
                pair[0],
            ),
        ),
        start=1,
    ):
        markdown.extend(
            [
                f"### {index}. {key}",
                "",
                f"Shots: {len(items)}",
                "",
                f"Shot IDs: {', '.join(item['shot_id'] for item in items)}",
                "",
                "Prompt:",
                "",
                items[0]["prompt"],
                "",
            ]
        )

    PROMPT_PACK_MD.write_text(
        "\n".join(markdown),
        encoding="utf-8",
    )


def main() -> int:
    EXPORT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    db = Database()
    db.init()

    missing_shots = [
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
                emotion,
                status
            FROM shots
            WHERE project_id=?
              AND (
                  status!='assigned'
                  OR assigned_asset_id IS NULL
              )
            ORDER BY idx
            """,
            (PROJECT_ID,),
        )
    ]

    assets = [
        dict(row)
        for row in db.rows(
            """
            SELECT *
            FROM assets
            WHERE project_id=?
              AND media_type IN ('image','video')
            ORDER BY filename
            """,
            (PROJECT_ID,),
        )
    ]

    print("=" * 68)
    print("ATLAS ZERO — MEDIA FACTORY RC1")
    print("=" * 68)
    print(f"Missing shots: {len(missing_shots)}")
    print(f"Available visual assets: {len(assets)}")

    if not missing_shots:
        print("Все шоты уже имеют материалы.")
        return 0

    if not assets:
        raise RuntimeError(
            "В базе нет изображений или видео."
        )

    write_prompt_pack(missing_shots)

    print()
    print("Пакет генерации создан:")
    print(PROMPT_PACK_JSON)
    print(PROMPT_PACK_MD)

    usage: Counter[str] = Counter()

    existing_assignments = db.rows(
        """
        SELECT assigned_asset_id, COUNT(*) AS c
        FROM shots
        WHERE project_id=?
          AND assigned_asset_id IS NOT NULL
        GROUP BY assigned_asset_id
        """,
        (PROJECT_ID,),
    )

    for row in existing_assignments:
        usage[str(row["assigned_asset_id"])] = int(
            row["c"] or 0
        )

    assignments: list[dict[str, Any]] = []

    print()
    print("Создаю временное покрытие чернового фильма...")

    for shot in missing_shots:
        ranked = sorted(
            (
                (
                    score_candidate(
                        shot=shot,
                        asset=asset,
                        usage=usage,
                    ),
                    asset,
                )
                for asset in assets
            ),
            key=lambda pair: pair[0],
            reverse=True,
        )

        score, selected = ranked[0]

        db.execute(
            """
            UPDATE shots
            SET assigned_asset_id=?,
                status='assigned'
            WHERE id=?
            """,
            (
                selected["id"],
                shot["id"],
            ),
        )

        usage[str(selected["id"])] += 1

        assignments.append(
            {
                "shot_id": shot["id"],
                "shot_index": shot["idx"],
                "visual_need": shot.get("visual_need"),
                "asset_id": selected["id"],
                "asset_filename": selected.get("filename"),
                "asset_path": selected.get("path"),
                "media_type": selected.get("media_type"),
                "score": score,
                "temporary": True,
                "replacement_prompt": make_prompt(shot),
            }
        )

    ASSIGNMENT_REPORT.write_text(
        json.dumps(
            {
                "project_id": PROJECT_ID,
                "mode": "roughcut_temporary_coverage",
                "assignments": assignments,
                "asset_usage": dict(usage),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    runtime = MovieRuntimeRC1(
        db,
        PROJECT_ID,
    )

    timeline_result = runtime._build_timeline()

    totals = db.one(
        """
        SELECT
            COUNT(*) AS total,
            SUM(
                CASE
                    WHEN status='assigned'
                     AND assigned_asset_id IS NOT NULL
                    THEN 1
                    ELSE 0
                END
            ) AS assigned
        FROM shots
        WHERE project_id=?
        """,
        (PROJECT_ID,),
    )

    total = int(totals["total"] or 0)
    assigned = int(totals["assigned"] or 0)
    missing = total - assigned

    print()
    print("=" * 68)
    print("MEDIA FACTORY RESULT")
    print("=" * 68)
    print(f"Total shots:     {total}")
    print(f"Assigned shots:  {assigned}")
    print(f"Missing shots:   {missing}")
    print(f"Temporary fills: {len(assignments)}")
    print(f"Timeline:        {timeline_result}")
    print(f"Assignment log:  {ASSIGNMENT_REPORT}")
    print("=" * 68)

    if missing:
        print("Покрытие неполное. Рендер пока запрещён.")
        return 2

    print()
    print("Все шоты закрыты.")
    print("Можно переходить к синхронизации звука и рендеру.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
