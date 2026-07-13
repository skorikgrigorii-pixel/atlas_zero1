from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path.cwd()
SRC = ROOT / "src"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from az_enterprise.core.database import Database


PROJECT_ID = "franklin"

VIDEO_DIR = (
    ROOT
    / "workspace"
    / "projects"
    / PROJECT_ID
    / "03_Video"
)

IMAGE_CATALOG = (
    ROOT
    / "workspace"
    / "exports"
    / PROJECT_ID
    / "visual_intelligence_v1"
    / "asset_semantic_catalog.json"
)

OUTPUT_DIR = (
    ROOT
    / "workspace"
    / "exports"
    / PROJECT_ID
    / "visual_intelligence_v1_1"
)

FRAME_DIR = OUTPUT_DIR / "video_keyframes"
UNIFIED_CATALOG = OUTPUT_DIR / "multimedia_semantic_catalog.json"
REPORT_PATH = OUTPUT_DIR / "multimedia_intelligence_report.json"

VIDEO_EXTENSIONS = {
    ".mp4",
    ".mov",
    ".mkv",
    ".webm",
    ".avi",
    ".m4v",
}

SAMPLES_PER_VIDEO = 5


def load_visual_intelligence_module():
    module_path = ROOT / "tools" / "visual_intelligence_v1.py"

    if not module_path.exists():
        raise FileNotFoundError(
            f"Visual Intelligence module not found: {module_path}"
        )

    spec = importlib.util.spec_from_file_location(
        "visual_intelligence_v1",
        module_path,
    )

    if spec is None or spec.loader is None:
        raise RuntimeError(
            "Cannot load visual_intelligence_v1.py"
        )

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    return module


def find_tool(name: str) -> str:
    tool = shutil.which(name)

    if tool:
        return tool

    candidates = list(
        Path.home().rglob(
            f"{name}.exe"
        )
    )

    if not candidates:
        raise FileNotFoundError(
            f"{name} not found"
        )

    return str(candidates[0])


def run_command(
    cmd: list[str],
    step: str,
) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        cmd,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    if proc.returncode != 0:
        tail = "\n".join(
            proc.stderr.splitlines()[-20:]
        )

        raise RuntimeError(
            f"{step} failed:\n{tail}"
        )

    return proc


def probe_duration(
    ffprobe: str,
    path: Path,
) -> float:
    proc = run_command(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        f"ffprobe {path.name}",
    )

    return round(
        float(proc.stdout.strip()),
        3,
    )


def sample_times(
    duration: float,
    count: int,
) -> list[float]:
    if duration <= 0:
        return [0.0]

    if count <= 1:
        return [
            round(duration * 0.5, 3)
        ]

    # Не берём самый первый и последний кадр:
    # там часто находятся затемнения или переходы.
    return [
        round(
            duration * (index + 1) / (count + 1),
            3,
        )
        for index in range(count)
    ]


def extract_frames(
    ffmpeg: str,
    video_path: Path,
    duration: float,
) -> list[Path]:
    target_dir = (
        FRAME_DIR
        / video_path.stem
    )

    target_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    frames: list[Path] = []

    for index, timestamp in enumerate(
        sample_times(
            duration,
            SAMPLES_PER_VIDEO,
        ),
        start=1,
    ):
        output = (
            target_dir
            / f"frame_{index:02d}_{timestamp:.3f}.jpg"
        )

        run_command(
            [
                ffmpeg,
                "-nostdin",
                "-y",
                "-ss",
                str(timestamp),
                "-i",
                str(video_path),
                "-frames:v",
                "1",
                "-vf",
                "scale=1280:-2",
                "-q:v",
                "2",
                str(output),
            ],
            (
                f"extract frame {index} "
                f"from {video_path.name}"
            ),
        )

        if output.exists():
            frames.append(output)

    return frames


def aggregate_classification(
    analyzer,
    frame_paths: list[Path],
) -> tuple[
    str,
    float,
    dict[str, float],
    list[dict[str, Any]],
]:
    totals: defaultdict[str, float] = defaultdict(float)
    frame_results: list[dict[str, Any]] = []

    for frame_path in frame_paths:
        (
            semantic_class,
            confidence,
            scores,
        ) = analyzer.classify(frame_path)

        for label, score in scores.items():
            totals[label] += float(score)

        frame_results.append(
            {
                "frame": str(frame_path),
                "semantic_class": semantic_class,
                "confidence": confidence,
                "scores": scores,
            }
        )

    if not frame_results:
        return (
            "unclassified",
            0.0,
            {},
            [],
        )

    averaged = {
        label: round(
            value / len(frame_results),
            5,
        )
        for label, value in totals.items()
    }

    ranking = sorted(
        averaged.items(),
        key=lambda item: item[1],
        reverse=True,
    )

    best_class, best_score = ranking[0]

    return (
        best_class,
        best_score,
        dict(ranking[:5]),
        frame_results,
    )


def main() -> None:
    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    FRAME_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    if not IMAGE_CATALOG.exists():
        raise FileNotFoundError(
            f"Image catalog not found: {IMAGE_CATALOG}"
        )

    image_payload = json.loads(
        IMAGE_CATALOG.read_text(
            encoding="utf-8"
        )
    )

    image_assets = list(
        image_payload.get(
            "assets",
            [],
        )
    )

    video_paths = sorted(
        [
            path
            for path in VIDEO_DIR.rglob("*")
            if (
                path.is_file()
                and path.suffix.lower()
                in VIDEO_EXTENSIONS
            )
        ],
        key=lambda path: path.name.lower(),
    )

    if not video_paths:
        raise RuntimeError(
            "No video files found."
        )

    ffmpeg = find_tool("ffmpeg")
    ffprobe = find_tool("ffprobe")

    vie_module = (
        load_visual_intelligence_module()
    )

    analyzer = vie_module.ClipAnalyzer()

    if not analyzer.available:
        raise RuntimeError(
            "CLIP is not available: "
            + str(analyzer.error)
        )

    class_to_tags = (
        vie_module.CLASS_TO_TAGS
    )

    db = Database()
    db.init()

    print("=" * 72)
    print(
        "ATLAS ZERO — "
        "VISUAL INTELLIGENCE V1.1 MULTIMEDIA"
    )
    print("=" * 72)
    print("Image assets :", len(image_assets))
    print("Video assets :", len(video_paths))
    print("FFmpeg       :", ffmpeg)
    print("CLIP         : available")
    print()

    video_assets: list[
        dict[str, Any]
    ] = []

    for index, video_path in enumerate(
        video_paths,
        start=1,
    ):
        print(
            f"[{index:02d}/{len(video_paths):02d}] "
            f"Analyzing {video_path.name}"
        )

        duration = probe_duration(
            ffprobe,
            video_path,
        )

        frames = extract_frames(
            ffmpeg,
            video_path,
            duration,
        )

        (
            semantic_class,
            confidence,
            semantic_scores,
            frame_results,
        ) = aggregate_classification(
            analyzer,
            frames,
        )

        tags = class_to_tags.get(
            semantic_class,
            ["unclassified"],
        )

        asset_row = db.one(
            """
            SELECT id
            FROM assets
            WHERE project_id=?
              AND path=?
            """,
            (
                PROJECT_ID,
                str(video_path.resolve()),
            ),
        )

        if not asset_row:
            asset_row = db.one(
                """
                SELECT id
                FROM assets
                WHERE project_id=?
                  AND filename=?
                LIMIT 1
                """,
                (
                    PROJECT_ID,
                    video_path.name,
                ),
            )

        if not asset_row:
            raise RuntimeError(
                f"Video not registered in DB: "
                f"{video_path}"
            )

        asset_id = str(
            asset_row["id"]
        )

        representative_frame = (
            frames[len(frames) // 2]
            if frames
            else None
        )

        db.execute(
            """
            UPDATE assets
            SET
                duration_sec=?,
                category=?,
                tags=?,
                semantic_class=?,
                semantic_description=?,
                visual_group=?,
                semantic_confidence=?,
                max_use=?
            WHERE id=?
            """,
            (
                duration,
                semantic_class,
                json.dumps(
                    tags,
                    ensure_ascii=False,
                ),
                semantic_class,
                (
                    "animated video; "
                    + semantic_class.replace(
                        "_",
                        " ",
                    )
                    + "; "
                    + ", ".join(tags)
                ),
                semantic_class,
                confidence,
                4,
                asset_id,
            ),
        )

        video_asset = {
            "asset_id": asset_id,
            "filename": video_path.name,
            "path": str(
                video_path.resolve()
            ),
            "media_type": "video",
            "duration_sec": duration,
            "semantic_class": (
                semantic_class
            ),
            "semantic_confidence": (
                confidence
            ),
            "semantic_scores": (
                semantic_scores
            ),
            "tags": tags,
            "visual_group": semantic_class,
            "max_use": 4,
            "duplicate_of": None,
            "representative_frame": (
                str(
                    representative_frame.resolve()
                )
                if representative_frame
                else None
            ),
            "sample_frames": [
                str(frame.resolve())
                for frame in frames
            ],
            "frame_analysis": (
                frame_results
            ),
        }

        video_assets.append(
            video_asset
        )

        print(
            f"  duration = {duration:.3f} sec"
        )
        print(
            f"  class    = "
            f"{semantic_class}"
        )
        print(
            f"  confidence = "
            f"{confidence:.4f}"
        )
        print(
            f"  frames   = {len(frames)}"
        )

    normalized_images = []

    for item in image_assets:
        copy = dict(item)
        copy["media_type"] = "image"
        copy["duration_sec"] = None
        copy["representative_frame"] = (
            copy.get("path")
        )

        normalized_images.append(
            copy
        )

    all_assets = (
        normalized_images
        + video_assets
    )

    usable_assets = [
        asset
        for asset in all_assets
        if (
            int(
                asset.get("max_use")
                or 0
            )
            > 0
            and not asset.get(
                "duplicate_of"
            )
        )
    ]

    media_counts = Counter(
        asset["media_type"]
        for asset in all_assets
    )

    usable_media_counts = Counter(
        asset["media_type"]
        for asset in usable_assets
    )

    class_counts = Counter(
        asset.get(
            "semantic_class",
            "unclassified",
        )
        for asset in usable_assets
    )

    payload = {
        "version": "1.1",
        "project_id": PROJECT_ID,
        "state": "MULTIMEDIA_ANALYZED",
        "model": (
            "openai/clip-vit-base-patch32"
        ),
        "assets_total": len(
            all_assets
        ),
        "assets_usable": len(
            usable_assets
        ),
        "media_counts": dict(
            media_counts
        ),
        "usable_media_counts": dict(
            usable_media_counts
        ),
        "semantic_groups": len(
            class_counts
        ),
        "class_counts": dict(
            class_counts
        ),
        "assets": all_assets,
    }

    UNIFIED_CATALOG.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    report = {
        "project_id": PROJECT_ID,
        "state": (
            "MULTIMEDIA_ANALYZED"
        ),
        "images_total": len(
            normalized_images
        ),
        "videos_total": len(
            video_assets
        ),
        "usable_images": (
            usable_media_counts.get(
                "image",
                0,
            )
        ),
        "usable_videos": (
            usable_media_counts.get(
                "video",
                0,
            )
        ),
        "semantic_groups": len(
            class_counts
        ),
        "video_analysis": [
            {
                "filename": item[
                    "filename"
                ],
                "duration_sec": item[
                    "duration_sec"
                ],
                "semantic_class": item[
                    "semantic_class"
                ],
                "confidence": item[
                    "semantic_confidence"
                ],
                "representative_frame": (
                    item[
                        "representative_frame"
                    ]
                ),
            }
            for item in video_assets
        ],
        "catalog": str(
            UNIFIED_CATALOG
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

    print()
    print("=" * 72)
    print(
        "MULTIMEDIA INTELLIGENCE RESULT"
    )
    print("=" * 72)
    print(
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
