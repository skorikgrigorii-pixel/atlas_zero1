from __future__ import annotations

import csv
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


CANONICAL_SCHEMA = "atlas_zero.leonardo_queue.rc2.v1"

ACTIVE_STATUSES = {
    "waiting_api",
    "ready_for_live_or_dry_run",
    "ready",
    "pending",
    "queued",
}

CLOSED_STATUSES = {
    "completed",
    "complete",
    "done",
    "generated",
    "cancelled",
    "canceled",
    "failed",
    "rejected",
    "obsolete",
    "superseded",
    "archived",
}

TEST_MARKERS = {
    "test",
    "debug",
    "sample",
    "demo",
    "probe",
    "diagnostic",
    "pronunciation",
}

SHOT_ID_KEYS = (
    "shot_id",
    "shot",
    "shotid",
    "visual_shot_id",
    "timeline_shot_id",
    "id",
)

SCENE_ID_KEYS = (
    "scene_id",
    "scene",
    "sceneid",
    "segment_id",
)

ASSET_PATH_KEYS = (
    "asset_path",
    "visual_path",
    "image_path",
    "video_path",
    "media_path",
    "source_path",
    "selected_asset_path",
    "assigned_asset_path",
    "file_path",
    "path",
)

PROMPT_KEYS = (
    "prompt",
    "generation_prompt",
    "visual_prompt",
    "image_prompt",
    "leonardo_prompt",
)

VISUAL_NEED_KEYS = (
    "visual_need",
    "required_visual",
    "visual_description",
    "shot_description",
    "description",
    "visual",
)

VALID_IMAGE_SUFFIXES = {
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".tif",
    ".tiff",
}

VALID_VIDEO_SUFFIXES = {
    ".mp4",
    ".mov",
    ".mkv",
    ".avi",
    ".webm",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def normalize_key(value: str) -> str:
    return re.sub(
        r"[^a-zа-я0-9]+",
        "_",
        value.strip().lower(),
        flags=re.IGNORECASE,
    ).strip("_")


def normalize_shot_id(value: Any) -> str | None:
    text = clean_text(value)

    if not text:
        return None

    text = text.replace("\\", "/").split("/")[-1]
    text = Path(text).stem
    text = normalize_key(text)

    match = re.search(
        r"(?:shot|sh|кадр)[_\-\s]*0*(\d+)",
        text,
        flags=re.IGNORECASE,
    )

    if match:
        return f"shot_{int(match.group(1)):04d}"

    if re.fullmatch(r"\d+", text):
        return f"shot_{int(text):04d}"

    if text.startswith("sc") and re.search(r"\d+", text):
        number = re.search(r"\d+", text)
        if number:
            return f"shot_{int(number.group()):04d}"

    return text or None


def parse_json_payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)

    if not isinstance(value, str):
        return {}

    text = value.strip()

    if not text:
        return {}

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return {}

    return parsed if isinstance(parsed, dict) else {}


def normalized_mapping(row: dict[str, Any]) -> dict[str, Any]:
    return {
        normalize_key(str(key)): value
        for key, value in row.items()
    }


def first_value(
    row: dict[str, Any],
    keys: Iterable[str],
) -> Any:
    normalized = normalized_mapping(row)

    for key in keys:
        normalized_key = normalize_key(key)
        value = normalized.get(normalized_key)

        if clean_text(value):
            return value

    return None


class LeonardoQueueBuilderRC2:
    def __init__(
        self,
        *,
        root: Path | str,
        project_id: str,
    ) -> None:
        self.root = Path(root).resolve()
        self.project_id = str(project_id).strip()

        self.workspace = self.root / "workspace"
        self.project_dir = (
            self.workspace / "projects" / self.project_id
        )
        self.export_dir = (
            self.workspace / "exports" / self.project_id
        )
        self.rc2_dir = self.export_dir / "rc2"

        self.legacy_queue_path = (
            self.export_dir / "очередь_api.json"
        )

        self.canonical_queue_path = (
            self.rc2_dir / "leonardo_queue_canonical.json"
        )

        self.report_path = (
            self.rc2_dir
            / "leonardo_queue_canonical_report.json"
        )

        self.review_csv_path = (
            self.rc2_dir
            / "leonardo_missing_shots_review.csv"
        )

    def montage_candidates(self) -> list[Path]:
        exact_names = (
            "монтажный_лист_story_engine.csv",
            "монтажный_лист.csv",
            "editing_sheet.csv",
            "shot_list.csv",
            "timeline.csv",
            "movie_timeline.csv",
        )

        candidates: list[Path] = []

        for name in exact_names:
            path = self.export_dir / name
            if path.is_file():
                candidates.append(path)

        for pattern in (
            "*монтаж*.csv",
            "*shot*.csv",
            "*timeline*.csv",
            "*montage*.csv",
        ):
            candidates.extend(
                self.export_dir.rglob(pattern)
            )

        unique = {
            path.resolve(): path.resolve()
            for path in candidates
            if path.is_file()
        }

        return sorted(
            unique.values(),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )

    def select_montage(self) -> Path:
        candidates = self.montage_candidates()

        if not candidates:
            raise FileNotFoundError(
                "No Franklin montage/shot-list CSV found"
            )

        priorities = (
            "монтажный_лист_story_engine.csv",
            "монтажный_лист.csv",
        )

        for preferred_name in priorities:
            matching = [
                path for path in candidates
                if path.name.lower()
                == preferred_name.lower()
            ]

            if matching:
                return max(
                    matching,
                    key=lambda path: path.stat().st_mtime,
                )

        return candidates[0]

    def read_csv(self, path: Path) -> list[dict[str, Any]]:
        encodings = (
            "utf-8-sig",
            "utf-8",
            "cp1251",
        )

        last_error: Exception | None = None

        for encoding in encodings:
            try:
                with path.open(
                    "r",
                    encoding=encoding,
                    newline="",
                ) as stream:
                    sample = stream.read(8192)
                    stream.seek(0)

                    try:
                        dialect = csv.Sniffer().sniff(
                            sample,
                            delimiters=",;\t|",
                        )
                    except csv.Error:
                        dialect = csv.excel

                    rows = list(
                        csv.DictReader(
                            stream,
                            dialect=dialect,
                        )
                    )

                return [
                    dict(row)
                    for row in rows
                    if isinstance(row, dict)
                ]

            except (UnicodeDecodeError, csv.Error) as exc:
                last_error = exc

        raise RuntimeError(
            f"Cannot read CSV {path}: {last_error}"
        )

    def extract_shots(
        self,
        rows: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        shots: list[dict[str, Any]] = []

        for index, row in enumerate(rows, start=1):
            raw_shot_id = first_value(
                row,
                SHOT_ID_KEYS,
            )

            raw_scene_id = first_value(
                row,
                SCENE_ID_KEYS,
            )

            shot_id = normalize_shot_id(raw_shot_id)

            if not shot_id:
                shot_id = f"shot_{index:04d}"

            scene_id = clean_text(raw_scene_id) or None

            asset_path = first_value(
                row,
                ASSET_PATH_KEYS,
            )

            prompt = first_value(
                row,
                PROMPT_KEYS,
            )

            visual_need = first_value(
                row,
                VISUAL_NEED_KEYS,
            )

            shots.append({
                "shot_id": shot_id,
                "source_index": index,
                "scene_id": scene_id,
                "asset_path": (
                    clean_text(asset_path) or None
                ),
                "prompt": clean_text(prompt),
                "visual_need": clean_text(visual_need),
                "source_row": row,
            })

        # Монтажный лист также может содержать дубли.
        # Оставляем первую актуальную запись на shot_id.
        deduplicated: dict[str, dict[str, Any]] = {}

        for shot in shots:
            deduplicated.setdefault(
                shot["shot_id"],
                shot,
            )

        return list(deduplicated.values())

    def existing_media_index(self) -> dict[str, list[str]]:
        roots = (
            self.project_dir,
            self.export_dir,
        )

        index: dict[str, list[str]] = {}

        for root in roots:
            if not root.is_dir():
                continue

            for path in root.rglob("*"):
                if not path.is_file():
                    continue

                suffix = path.suffix.lower()

                if (
                    suffix not in VALID_IMAGE_SUFFIXES
                    and suffix not in VALID_VIDEO_SUFFIXES
                ):
                    continue

                shot_id = normalize_shot_id(path.stem)

                if not shot_id:
                    continue

                index.setdefault(
                    shot_id,
                    [],
                ).append(str(path.resolve()))

        return index

    def resolve_declared_asset(
        self,
        raw_path: str | None,
    ) -> Path | None:
        if not raw_path:
            return None

        candidate = Path(raw_path)

        candidates = (
            candidate,
            self.root / candidate,
            self.project_dir / candidate,
            self.export_dir / candidate,
        )

        for path in candidates:
            try:
                resolved = path.resolve()
            except OSError:
                continue

            if resolved.is_file():
                return resolved

        return None

    def determine_missing_shots(
        self,
        shots: list[dict[str, Any]],
    ) -> tuple[
        list[dict[str, Any]],
        list[dict[str, Any]],
    ]:
        media_index = self.existing_media_index()

        missing: list[dict[str, Any]] = []
        covered: list[dict[str, Any]] = []

        for shot in shots:
            declared_asset = self.resolve_declared_asset(
                shot.get("asset_path")
            )

            indexed_assets = media_index.get(
                shot["shot_id"],
                [],
            )

            if declared_asset:
                row = dict(shot)
                row["coverage_reason"] = (
                    "DECLARED_ASSET_EXISTS"
                )
                row["resolved_assets"] = [
                    str(declared_asset)
                ]
                covered.append(row)

            elif indexed_assets:
                row = dict(shot)
                row["coverage_reason"] = (
                    "MATCHING_MEDIA_EXISTS"
                )
                row["resolved_assets"] = indexed_assets
                covered.append(row)

            else:
                row = dict(shot)
                row["coverage_reason"] = (
                    "NO_EXISTING_MEDIA"
                )
                row["resolved_assets"] = []
                missing.append(row)

        return missing, covered

    def load_legacy_jobs(self) -> list[dict[str, Any]]:
        if not self.legacy_queue_path.is_file():
            raise FileNotFoundError(
                self.legacy_queue_path
            )

        payload = json.loads(
            self.legacy_queue_path.read_text(
                encoding="utf-8-sig",
            )
        )

        if isinstance(payload, list):
            jobs = payload

        elif isinstance(payload, dict):
            jobs = (
                payload.get("jobs")
                or payload.get("api_jobs")
                or payload.get("queue")
                or payload.get("items")
                or []
            )

        else:
            raise RuntimeError(
                "Unsupported legacy queue format"
            )

        if not isinstance(jobs, list):
            raise RuntimeError(
                "Legacy queue jobs are not a list"
            )

        return [
            dict(job)
            for job in jobs
            if isinstance(job, dict)
        ]

    def normalize_job(
        self,
        job: dict[str, Any],
        queue_index: int,
    ) -> dict[str, Any] | None:
        service = clean_text(
            job.get("service")
        ).lower()

        job_type = clean_text(
            job.get("job_type")
        ).lower()

        status = clean_text(
            job.get("status")
        ).lower()

        if service and service != "leonardo":
            return None

        if status in CLOSED_STATUSES:
            return None

        if status not in ACTIVE_STATUSES:
            return None

        if job_type not in {
            "image_generation",
            "generate_asset",
        }:
            return None

        payload = parse_json_payload(
            job.get("payload")
        )

        if not payload:
            payload = {
                key: value
                for key, value in job.items()
                if key not in {
                    "payload",
                    "service",
                    "job_type",
                    "status",
                }
            }

        shot_id = normalize_shot_id(
            first_value(
                payload,
                SHOT_ID_KEYS,
            )
            or first_value(
                job,
                SHOT_ID_KEYS,
            )
        )

        scene_id = clean_text(
            first_value(
                payload,
                SCENE_ID_KEYS,
            )
            or first_value(
                job,
                SCENE_ID_KEYS,
            )
        ) or None

        prompt = clean_text(
            first_value(
                payload,
                PROMPT_KEYS,
            )
        )

        if not prompt:
            return None

        combined = " ".join(
            (
                shot_id or "",
                scene_id or "",
                prompt,
                clean_text(job.get("name")),
            )
        ).lower()

        if any(
            re.search(
                rf"\b{re.escape(marker)}\b",
                combined,
            )
            for marker in TEST_MARKERS
        ):
            return None

        created_at = (
            job.get("created_at")
            or job.get("created_at_utc")
            or job.get("updated_at")
            or job.get("timestamp")
        )

        return {
            "queue_index": queue_index,
            "shot_id": shot_id,
            "scene_id": scene_id,
            "service": "leonardo",
            "job_type": "image_generation",
            "status": "ready_for_live_or_dry_run",
            "source_status": status,
            "created_at": created_at,
            "payload": {
                "shot_id": shot_id,
                "scene_id": scene_id,
                "prompt": prompt,
                "negative_prompt": clean_text(
                    payload.get("negative_prompt")
                ),
                "aspect_ratio": (
                    clean_text(
                        payload.get("aspect_ratio")
                    )
                    or "16:9"
                ),
                "style": clean_text(
                    payload.get("style")
                ) or None,
            },
        }

    def score_job(
        self,
        job: dict[str, Any],
        shot: dict[str, Any],
    ) -> tuple[int, int]:
        score = 0

        if job.get("shot_id") == shot["shot_id"]:
            score += 100

        if (
            job.get("scene_id")
            and shot.get("scene_id")
            and normalize_key(job["scene_id"])
            == normalize_key(shot["scene_id"])
        ):
            score += 30

        prompt = clean_text(
            job.get("payload", {}).get("prompt")
        )

        if len(prompt) >= 80:
            score += 10

        if "franklin" in prompt.lower():
            score += 5

        if (
            job.get("source_status")
            == "ready_for_live_or_dry_run"
        ):
            score += 4

        # При одинаковом качестве выбирается более поздняя
        # запись в старой очереди.
        return score, int(job["queue_index"])

    def index_jobs(
        self,
        jobs: list[dict[str, Any]],
    ) -> tuple[
        dict[str, list[dict[str, Any]]],
        dict[str, list[dict[str, Any]]],
        dict[str, int],
    ]:
        by_shot: dict[str, list[dict[str, Any]]] = {}
        by_scene: dict[str, list[dict[str, Any]]] = {}
        reasons = Counter()

        for index, raw_job in enumerate(jobs):
            normalized = self.normalize_job(
                raw_job,
                index,
            )

            if normalized is None:
                reasons["discarded"] += 1
                continue

            shot_id = normalized.get("shot_id")
            scene_id = normalized.get("scene_id")

            if shot_id:
                by_shot.setdefault(
                    shot_id,
                    [],
                ).append(normalized)

            if scene_id:
                by_scene.setdefault(
                    normalize_key(scene_id),
                    [],
                ).append(normalized)

            if not shot_id and not scene_id:
                reasons["unmatchable"] += 1
            else:
                reasons["eligible"] += 1

        return by_shot, by_scene, dict(reasons)

    def fallback_prompt(
        self,
        shot: dict[str, Any],
    ) -> str:
        visual_need = (
            shot.get("visual_need")
            or "historical Arctic documentary scene"
        )

        scene = (
            shot.get("scene_id")
            or "Franklin Expedition"
        )

        return (
            "Ultra photorealistic cinematic historical "
            "documentary frame for ATLAS ZERO. "
            f"Scene: {scene}. "
            f"Required visual: {visual_need}. "
            "1845–1859 Franklin Expedition, historically "
            "accurate Victorian Arctic expedition, natural "
            "cold light, restrained blue-gray palette, "
            "realistic materials, BBC and Netflix documentary "
            "quality, no fantasy, no modern objects."
        )

    def build(self) -> dict[str, Any]:
        montage_path = self.select_montage()
        montage_rows = self.read_csv(montage_path)
        shots = self.extract_shots(montage_rows)

        missing, covered = (
            self.determine_missing_shots(shots)
        )

        legacy_jobs = self.load_legacy_jobs()

        by_shot, by_scene, filtering = (
            self.index_jobs(legacy_jobs)
        )

        canonical_jobs: list[dict[str, Any]] = []
        review_rows: list[dict[str, Any]] = []
        unmatched: list[dict[str, Any]] = []

        for shot in missing:
            candidates = list(
                by_shot.get(
                    shot["shot_id"],
                    [],
                )
            )

            if (
                not candidates
                and shot.get("scene_id")
            ):
                candidates = list(
                    by_scene.get(
                        normalize_key(
                            shot["scene_id"]
                        ),
                        [],
                    )
                )

            if candidates:
                selected = max(
                    candidates,
                    key=lambda job: self.score_job(
                        job,
                        shot,
                    ),
                )

                payload = dict(
                    selected["payload"]
                )
                payload["shot_id"] = shot["shot_id"]

                if (
                    not payload.get("scene_id")
                    and shot.get("scene_id")
                ):
                    payload["scene_id"] = (
                        shot["scene_id"]
                    )

                source = "LEGACY_QUEUE"

            else:
                payload = {
                    "shot_id": shot["shot_id"],
                    "scene_id": shot.get("scene_id"),
                    "prompt": (
                        shot.get("prompt")
                        or self.fallback_prompt(shot)
                    ),
                    "negative_prompt": (
                        "cartoon, illustration, CGI, fantasy, "
                        "modern objects, incorrect Victorian "
                        "details, distorted anatomy, duplicate "
                        "people, text, watermark, blurry, "
                        "low quality"
                    ),
                    "aspect_ratio": "16:9",
                    "style": (
                        "ultra photorealistic historical "
                        "documentary, cold blue-gray palette"
                    ),
                }
                source = "MONTAGE_FALLBACK"

                unmatched.append({
                    "shot_id": shot["shot_id"],
                    "scene_id": shot.get("scene_id"),
                })

            canonical_jobs.append({
                "service": "leonardo",
                "job_type": "image_generation",
                "status":
                    "ready_for_live_or_dry_run",
                "project_id": self.project_id,
                "shot_id": shot["shot_id"],
                "source": source,
                "payload": payload,
            })

            review_rows.append({
                "shot_id": shot["shot_id"],
                "scene_id": shot.get("scene_id"),
                "visual_need": shot.get(
                    "visual_need"
                ),
                "existing_asset": False,
                "queue_source": source,
                "prompt": payload["prompt"],
            })

        # Финальная гарантия уникальности.
        unique_jobs: dict[str, dict[str, Any]] = {}

        for job in canonical_jobs:
            unique_jobs[job["shot_id"]] = job

        canonical_jobs = list(
            unique_jobs.values()
        )

        queue_payload = {
            "schema": CANONICAL_SCHEMA,
            "state": "CANONICAL_QUEUE_READY",
            "authority":
                "LeonardoQueueBuilderRC2",
            "generated_at_utc": utc_now(),
            "project_id": self.project_id,
            "montage_source": str(
                montage_path.resolve()
            ),
            "legacy_queue_source": str(
                self.legacy_queue_path.resolve()
            ),
            "total_montage_shots": len(shots),
            "covered_shots": len(covered),
            "missing_shots": len(missing),
            "job_count": len(canonical_jobs),
            "jobs": canonical_jobs,
        }

        report = {
            "schema":
                "atlas_zero.leonardo_queue_report.rc2.v1",
            "state": "QUEUE_AUDITED",
            "generated_at_utc": utc_now(),
            "project_id": self.project_id,
            "montage_candidates": [
                str(path)
                for path in self.montage_candidates()
            ],
            "selected_montage": str(
                montage_path.resolve()
            ),
            "montage_rows": len(montage_rows),
            "unique_montage_shots": len(shots),
            "covered_shots": len(covered),
            "missing_shots": len(missing),
            "legacy_queue_jobs": len(legacy_jobs),
            "legacy_filtering": filtering,
            "canonical_jobs": len(canonical_jobs),
            "fallback_jobs": len(unmatched),
            "covered": [
                {
                    "shot_id": row["shot_id"],
                    "reason":
                        row["coverage_reason"],
                    "assets":
                        row["resolved_assets"],
                }
                for row in covered
            ],
            "fallback_job_shots": unmatched,
        }

        self.rc2_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.canonical_queue_path.write_text(
            json.dumps(
                queue_payload,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        self.report_path.write_text(
            json.dumps(
                report,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        with self.review_csv_path.open(
            "w",
            encoding="utf-8-sig",
            newline="",
        ) as stream:
            writer = csv.DictWriter(
                stream,
                fieldnames=(
                    "shot_id",
                    "scene_id",
                    "visual_need",
                    "existing_asset",
                    "queue_source",
                    "prompt",
                ),
            )
            writer.writeheader()
            writer.writerows(review_rows)

        return {
            "state": "CANONICAL_QUEUE_READY",
            "project_id": self.project_id,
            "selected_montage": str(
                montage_path.resolve()
            ),
            "montage_rows": len(montage_rows),
            "unique_shots": len(shots),
            "covered_shots": len(covered),
            "missing_shots": len(missing),
            "legacy_jobs": len(legacy_jobs),
            "canonical_jobs": len(canonical_jobs),
            "fallback_jobs": len(unmatched),
            "queue_path": str(
                self.canonical_queue_path.resolve()
            ),
            "report_path": str(
                self.report_path.resolve()
            ),
            "review_csv": str(
                self.review_csv_path.resolve()
            ),
        }
