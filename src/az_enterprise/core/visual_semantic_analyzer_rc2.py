from __future__ import annotations

from az_enterprise.core.visual_registry_writer_rc2 import (
    persist_visual_profile_rc2,
)

import gc
import json
import math
import os
import re
import time
import traceback
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
    """Memory-safe local HuggingFace CLIP zero-shot backend.

    CUDA is used only when explicitly enabled with
    ATLAS_ZERO_CLIP_DEVICE=cuda. CPU is the safe default for RC2 because
    native CUDA/driver failures can terminate Python without a traceback.
    """

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

        thread_count = max(
            1,
            int(os.getenv("ATLAS_ZERO_TORCH_THREADS", "1")),
        )
        try:
            torch.set_num_threads(thread_count)
            torch.set_num_interop_threads(1)
        except RuntimeError:
            pass

        requested_device = os.getenv(
            "ATLAS_ZERO_CLIP_DEVICE",
            "cpu",
        ).strip().lower()

        if requested_device == "cuda":
            if not torch.cuda.is_available():
                raise RuntimeError(
                    "ATLAS_ZERO_CLIP_DEVICE=cuda was requested, "
                    "but CUDA is not available"
                )
            self.device = "cuda"
        else:
            self.device = "cpu"

        print(
            "[SEMANTIC][BACKEND] "
            f"loading {model_name} on {self.device}"
        )

        self.processor = CLIPProcessor.from_pretrained(
            model_name,
            local_files_only=local_files_only,
        )

        self.model = CLIPModel.from_pretrained(
            model_name,
            local_files_only=local_files_only,
            low_cpu_mem_usage=True,
        )
        self.model.eval()
        self.model.requires_grad_(False)
        self.model.to(self.device)

        self._cleanup_memory()

        print(
            "[SEMANTIC][BACKEND] "
            f"ready on {self.device}"
        )

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
            inputs: dict[str, Any] | None = None
            outputs: Any = None
            probabilities: np.ndarray | None = None

            try:
                inputs = self.processor(
                    text=prompts,
                    images=image,
                    return_tensors="pt",
                    padding=True,
                )

                inputs = {
                    key: value.to(
                        self.device,
                        non_blocking=False,
                    )
                    for key, value in inputs.items()
                }

                with self.torch.inference_mode():
                    outputs = self.model(**inputs)

                probabilities = (
                    outputs.logits_per_image
                    .softmax(dim=1)
                    .detach()
                    .to("cpu")
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

            finally:
                del probabilities
                del outputs
                del inputs
                self._cleanup_memory()

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

        result = SemanticPredictionRC2(
            label=winner,
            score=round(normalized[winner], 6),
            scores={
                key: round(value, 6)
                for key, value in normalized.items()
            },
        )

        self._cleanup_memory()
        return result

    def cleanup(self) -> None:
        self._cleanup_memory()

    def _cleanup_memory(self) -> None:
        gc.collect()

        if (
            self.device == "cuda"
            and self.torch.cuda.is_available()
        ):
            self.torch.cuda.synchronize()
            self.torch.cuda.empty_cache()
            try:
                self.torch.cuda.ipc_collect()
            except RuntimeError:
                pass


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

        story_dir = Path(
            os.getenv(
                "ATLAS_ZERO_SEMANTIC_STORY_DIR",
                str(
                    Path("workspace")
                    / "exports"
                    / project_id
                    / "rc2"
                    / "story"
                ),
            )
        )
        self.checkpoint_path = Path(
            os.getenv(
                "ATLAS_ZERO_SEMANTIC_CHECKPOINT_PATH",
                str(story_dir / "visual_semantic_checkpoint.json"),
            )
        )
        self.partial_report_path = Path(
            os.getenv(
                "ATLAS_ZERO_SEMANTIC_PARTIAL_REPORT_PATH",
                str(story_dir / "visual_semantic_report.partial.json"),
            )
        )
        self.final_report_path = Path(
            os.getenv(
                "ATLAS_ZERO_SEMANTIC_REPORT_PATH",
                str(story_dir / "visual_semantic_report.json"),
            )
        )

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
        total = len(rows)
        run_started_at = datetime.now(timezone.utc).isoformat()

        if self._env_flag("ATLAS_ZERO_SEMANTIC_RESET"):
            self._remove_progress_files()
            print("[SEMANTIC][RESET] previous progress removed")

        checkpoint = self._load_checkpoint()
        restored_results = self._restore_results(
            checkpoint=checkpoint,
            rows=rows,
        )
        results_by_id: dict[str, dict[str, Any]] = {
            str(item["asset_id"]): item
            for item in restored_results
        }
        failures_by_id: dict[str, dict[str, Any]] = {}

        # A checkpoint may contain completed semantic results from an earlier
        # run even when the corresponding assets table fields are still empty.
        # Re-persist restored results so SQLite and the JSON checkpoint cannot
        # drift apart.
        for restored_result in restored_results:
            self._persist_semantic_payload(restored_result)

            persist_visual_profile_rc2(
                db=self.db,
                project_id=self.project_id,
                payload=restored_result,
            )

        if results_by_id:
            print(
                "[SEMANTIC][RESUME] "
                f"restored {len(results_by_id)}/{total} assets from checkpoint"
            )

        for index, row in enumerate(rows, start=1):
            asset = dict(row)
            asset_id = str(asset["id"])
            filename = str(asset["filename"])

            if asset_id in results_by_id:
                print(
                    f"[SEMANTIC][SKIP] "
                    f"{index}/{total} {filename} already completed"
                )
                continue

            started_at = time.monotonic()
            print(
                f"[SEMANTIC][START] "
                f"{index}/{total} {filename}"
            )

            try:
                result = self._analyze_asset(asset)
                self._persist_semantic_result(result)

                result_dict = result.to_dict()
                results_by_id[asset_id] = result_dict
                failures_by_id.pop(asset_id, None)

                elapsed = time.monotonic() - started_at
                print(
                    f"[SEMANTIC][DONE] "
                    f"{index}/{total} "
                    f"{filename} "
                    f"=> {result.event_type} "
                    f"({result.event_confidence:.3f}) "
                    f"{result.relevance_status} "
                    f"in {elapsed:.2f}s"
                )

            except Exception as exc:
                elapsed = time.monotonic() - started_at
                failure = self._classify_failure(
                    exc=exc,
                    asset=asset,
                    elapsed_sec=elapsed,
                )
                failures_by_id[asset_id] = failure

                print(
                    f"[SEMANTIC][FAILED] "
                    f"{index}/{total} "
                    f"{filename} "
                    f"=> {failure['failure_type']} "
                    f"action={failure['recommended_action']} "
                    f"error={failure['error']} "
                    f"after {elapsed:.2f}s"
                )

            finally:
                self._cleanup_after_asset()
                report = self._build_report(
                    rows=rows,
                    results_by_id=results_by_id,
                    failures_by_id=failures_by_id,
                    run_started_at=run_started_at,
                    status="RUNNING",
                )
                self._save_progress(
                    report=report,
                    rows=rows,
                )

        final_report = self._build_report(
            rows=rows,
            results_by_id=results_by_id,
            failures_by_id=failures_by_id,
            run_started_at=run_started_at,
            status=(
                "COMPLETED_WITH_ERRORS"
                if failures_by_id
                else "COMPLETED"
            ),
        )
        self._atomic_write_json(
            self.final_report_path,
            final_report,
        )
        self._safe_unlink(self.partial_report_path)
        self._safe_unlink(self.checkpoint_path)

        print(
            "[SEMANTIC][COMPLETE] "
            f"analyzed={final_report['assets_analyzed']} "
            f"failed={final_report['assets_failed']} "
            f"report={self.final_report_path}"
        )
        return final_report


    def _persist_semantic_result(
        self,
        result: AssetUnderstandingRC2,
    ) -> None:
        """Persist semantic output in assets and Visual Registry."""

        payload = result.to_dict()

        self._persist_semantic_payload(
            payload
        )

        persist_visual_profile_rc2(
            db=self.db,
            project_id=self.project_id,
            payload=payload,
        )


    def _persist_semantic_payload(
        self,
        payload: dict[str, Any],
    ) -> None:
        """Synchronize semantic analysis output with the assets table.

        Only the dedicated semantic columns are updated. Existing category,
        tags, quality and other asset metadata remain untouched.
        """
        asset_id = str(payload.get("asset_id", "")).strip()

        if not asset_id:
            raise ValueError(
                "Semantic result does not contain asset_id"
            )

        semantic_class = str(
            payload.get("event_type", "")
        ).strip()

        semantic_description = str(
            payload.get("description", "")
        ).strip()

        try:
            semantic_confidence = float(
                payload.get("event_confidence", 0.0)
            )
        except (TypeError, ValueError):
            semantic_confidence = 0.0

        semantic_confidence = max(
            0.0,
            min(1.0, semantic_confidence),
        )

        self.db.execute(
            """
            UPDATE assets
            SET
                semantic_class=?,
                semantic_description=?,
                semantic_confidence=?
            WHERE id=?
              AND project_id=?
            """,
            (
                semantic_class or None,
                semantic_description or None,
                semantic_confidence,
                asset_id,
                self.project_id,
            ),
        )

    def _classify_failure(
        self,
        *,
        exc: Exception,
        asset: dict[str, Any],
        elapsed_sec: float,
    ) -> dict[str, Any]:
        """Convert a raw exception into an RC2 recovery decision.

        The classification is intentionally deterministic and side-effect free
        so future Task Recovery and Health Monitor services can consume the
        same failure records without parsing log text.
        """
        exception_name = type(exc).__name__
        message = str(exc)
        lowered = message.lower()

        failure_type = "UNKNOWN_ERROR"
        recommended_action = "skip"
        retryable = False
        severity = "ERROR"

        if isinstance(exc, FileNotFoundError):
            failure_type = "SOURCE_MISSING"
            recommended_action = "skip"
        elif isinstance(exc, PermissionError):
            failure_type = "READ_ERROR"
            recommended_action = "retry"
            retryable = True
        elif isinstance(exc, TimeoutError):
            failure_type = "TIMEOUT_ERROR"
            recommended_action = "retry"
            retryable = True
        elif isinstance(exc, MemoryError) or any(
            marker in lowered
            for marker in (
                "out of memory",
                "cannot allocate memory",
                "cuda error: out of memory",
                "defaultcpuallocator",
            )
        ):
            failure_type = "OOM_ERROR"
            recommended_action = "abort"
            retryable = True
            severity = "CRITICAL"
        elif any(
            marker in lowered
            for marker in (
                "cannot identify image file",
                "truncated file",
                "corrupt",
                "invalid data found",
                "moov atom not found",
                "failed to decode",
                "decode error",
            )
        ):
            failure_type = "DECODE_ERROR"
            recommended_action = "skip"
        elif isinstance(exc, ValueError) and any(
            marker in lowered
            for marker in (
                "unsupported media type",
                "at least one image is required",
                "no frames",
            )
        ):
            failure_type = "MEDIA_ERROR"
            recommended_action = "skip"
        elif any(
            marker in lowered
            for marker in (
                "opencv",
                "videocapture",
                "pillow",
                "image.open",
                "failed to open",
                "cannot open",
            )
        ):
            failure_type = "READ_ERROR"
            recommended_action = "retry"
            retryable = True
        elif any(
            marker in lowered
            for marker in (
                "clipmodel",
                "clipprocessor",
                "transformers",
                "torch",
                "model",
                "tensor",
            )
        ):
            failure_type = "MODEL_ERROR"
            recommended_action = "retry"
            retryable = True
        elif isinstance(exc, (OSError, RuntimeError)):
            failure_type = "RUNTIME_ERROR"
            recommended_action = "retry"
            retryable = True

        return {
            "asset_id": str(asset.get("id", "")),
            "filename": str(asset.get("filename", "")),
            "path": str(asset.get("path", "")),
            "media_type": str(asset.get("media_type", "")),
            "failure_type": failure_type,
            "severity": severity,
            "recommended_action": recommended_action,
            "retryable": retryable,
            "exception_type": exception_name,
            "error": f"{exception_name}: {message}",
            "elapsed_sec": round(float(elapsed_sec), 6),
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "traceback": "".join(
                traceback.format_exception(
                    type(exc),
                    exc,
                    exc.__traceback__,
                )
            ),
        }

    def _build_report(
        self,
        *,
        rows: Sequence[Any],
        results_by_id: dict[str, dict[str, Any]],
        failures_by_id: dict[str, dict[str, Any]],
        run_started_at: str,
        status: str,
    ) -> dict[str, Any]:
        ordered_results: list[dict[str, Any]] = []
        ordered_failures: list[dict[str, Any]] = []

        for row in rows:
            asset_id = str(row["id"])
            if asset_id in results_by_id:
                ordered_results.append(results_by_id[asset_id])
            if asset_id in failures_by_id:
                ordered_failures.append(failures_by_id[asset_id])

        return {
            "engine": "visual_semantic_analyzer_rc2",
            "backend": self.backend.name,
            "project_id": self.project_id,
            "status": status,
            "assets_requested": len(rows),
            "assets_analyzed": len(ordered_results),
            "assets_failed": len(ordered_failures),
            "results": ordered_results,
            "failures": ordered_failures,
            "run_started_at": run_started_at,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

    def _save_progress(
        self,
        *,
        report: dict[str, Any],
        rows: Sequence[Any],
    ) -> None:
        checkpoint = {
            "schema_version": 1,
            "engine": "visual_semantic_analyzer_rc2",
            "backend": self.backend.name,
            "project_id": self.project_id,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "asset_signatures": {
                str(row["id"]): self._asset_signature(dict(row))
                for row in rows
            },
            "results": report["results"],
            "failures": report["failures"],
        }
        self._atomic_write_json(
            self.checkpoint_path,
            checkpoint,
        )
        self._atomic_write_json(
            self.partial_report_path,
            report,
        )
        print(
            "[SEMANTIC][CHECKPOINT] "
            f"saved={report['assets_analyzed']} "
            f"failed={report['assets_failed']}"
        )

    def _load_checkpoint(self) -> dict[str, Any] | None:
        if not self.checkpoint_path.exists():
            return None

        try:
            payload = json.loads(
                self.checkpoint_path.read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError) as exc:
            print(
                "[SEMANTIC][CHECKPOINT_INVALID] "
                f"cannot read {self.checkpoint_path}: "
                f"{type(exc).__name__}: {exc}"
            )
            return None

        if not isinstance(payload, dict):
            print("[SEMANTIC][CHECKPOINT_INVALID] root is not an object")
            return None
        if payload.get("project_id") != self.project_id:
            print("[SEMANTIC][CHECKPOINT_INVALID] project mismatch")
            return None
        if payload.get("backend") != self.backend.name:
            print("[SEMANTIC][CHECKPOINT_INVALID] backend mismatch")
            return None
        if payload.get("engine") != "visual_semantic_analyzer_rc2":
            print("[SEMANTIC][CHECKPOINT_INVALID] engine mismatch")
            return None
        return payload

    def _restore_results(
        self,
        *,
        checkpoint: dict[str, Any] | None,
        rows: Sequence[Any],
    ) -> list[dict[str, Any]]:
        if checkpoint is None:
            return []

        current_signatures = {
            str(row["id"]): self._asset_signature(dict(row))
            for row in rows
        }
        stored_signatures = checkpoint.get("asset_signatures", {})
        stored_results = checkpoint.get("results", [])
        if not isinstance(stored_signatures, dict):
            return []
        if not isinstance(stored_results, list):
            return []

        restored: list[dict[str, Any]] = []
        for item in stored_results:
            if not isinstance(item, dict):
                continue
            asset_id = str(item.get("asset_id", ""))
            if not asset_id:
                continue
            if current_signatures.get(asset_id) != stored_signatures.get(asset_id):
                print(
                    "[SEMANTIC][RESUME_INVALIDATED] "
                    f"asset_id={asset_id} source changed"
                )
                continue
            restored.append(item)
        return restored

    @staticmethod
    def _asset_signature(asset: dict[str, Any]) -> dict[str, Any]:
        path = Path(str(asset.get("path", "")))
        try:
            stat = path.stat()
            return {
                "path": str(path.resolve()),
                "size": int(stat.st_size),
                "mtime_ns": int(stat.st_mtime_ns),
            }
        except OSError:
            return {
                "path": str(path),
                "size": None,
                "mtime_ns": None,
            }

    @staticmethod
    def _atomic_write_json(
        path: Path,
        payload: dict[str, Any],
    ) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = path.with_name(path.name + ".tmp")
        serialized = json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=False,
        )
        try:
            with temporary_path.open("w", encoding="utf-8", newline="\n") as stream:
                stream.write(serialized)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_path, path)
        finally:
            if temporary_path.exists():
                try:
                    temporary_path.unlink()
                except OSError:
                    pass

    def _remove_progress_files(self) -> None:
        self._safe_unlink(self.checkpoint_path)
        self._safe_unlink(self.partial_report_path)

    @staticmethod
    def _safe_unlink(path: Path) -> None:
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:
            print(
                "[SEMANTIC][CLEANUP_WARNING] "
                f"cannot remove {path}: {type(exc).__name__}: {exc}"
            )

    @staticmethod
    def _env_flag(name: str) -> bool:
        return os.getenv(name, "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
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

    def _cleanup_after_asset(self) -> None:
        cleanup = getattr(
            self.backend,
            "cleanup",
            None,
        )

        if callable(cleanup):
            cleanup()
        else:
            gc.collect()


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

