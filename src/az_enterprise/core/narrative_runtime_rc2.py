from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .editorial_package_rc2 import EditorialPackageRC2
from .external_script_importer_rc2 import ExternalScriptImporterRC2
from .narrative_writer_rc2 import NarrativeWriterRC2
from .project_config_rc2 import ProjectConfigRC2


class NarrativeRuntimeRC2:
    """Canonical RC2 runtime for generated or externally authored narration."""

    VALID_MODES = {
        "openai_documentary",
        "openai_editorial",
        "local_fallback",
        "external_script",
    }

    def __init__(
        self,
        config: ProjectConfigRC2,
        *,
        mode: str = "openai_documentary",
        allow_paid: bool = True,
        external_script_path: Path | None = None,
    ) -> None:
        self.config = config
        self.mode = str(mode).strip()
        self.allow_paid = bool(allow_paid)
        self.external_script_path = (
            Path(external_script_path).expanduser()
            if external_script_path is not None
            else None
        )
        if self.mode not in self.VALID_MODES:
            raise ValueError(f"Unsupported narrative mode: {self.mode}")
        if self.mode == "external_script" and self.external_script_path is None:
            raise ValueError("external_script mode requires external_script_path")

    @property
    def narrative_dir(self) -> Path:
        return self.config.rc2_dir / "narrative"

    @property
    def narrative_result_path(self) -> Path:
        return self.narrative_dir / "narrative_result.json"

    @property
    def narrative_markdown_path(self) -> Path:
        return self.narrative_dir / "narrative_result.md"

    @property
    def narrative_report_path(self) -> Path:
        return self.narrative_dir / "narrative_report.json"

    def run(
        self,
        *,
        title: str | None = None,
        rebuild_editorial_package: bool = False,
    ) -> dict[str, Any]:
        started_at = datetime.now(timezone.utc)

        story_strategy = self._read_json(
            self.config.story_strategy_result_path,
            artifact_name="Story Strategy",
        )
        event_discovery = self._read_json(
            self.config.event_discovery_result_path,
            artifact_name="Event Discovery",
        )
        semantic_analysis = self._read_json(
            self.config.visual_semantic_report_path,
            artifact_name="Visual Semantic Report",
        )

        resolved_title = (
            str(title).strip()
            if title and str(title).strip()
            else self._discover_title(story_strategy, event_discovery)
        )

        editorial_path = self._discover_editorial_package()
        if rebuild_editorial_package or editorial_path is None:
            editorial_package = EditorialPackageRC2(
                project_id=self.config.project_id,
                title=resolved_title,
                language="ru",
                minimum_duration_sec=self._target_duration(story_strategy),
                use_existing_assets_only=True,
                allow_generated_visuals=False,
            ).build(
                story_strategy=story_strategy,
                event_discovery=event_discovery,
                semantic_analysis=semantic_analysis,
            )
            editorial_path = self._write_editorial_package(editorial_package)
        else:
            editorial_package = self._read_json(
                editorial_path,
                artifact_name="Editorial Package",
            )

        if self.mode == "external_script":
            assert self.external_script_path is not None
            payload = ExternalScriptImporterRC2(
                project_id=self.config.project_id,
            ).import_file(
                self.external_script_path,
                story_strategy=story_strategy,
                title=resolved_title,
            )
        else:
            writer = NarrativeWriterRC2(
                project_id=self.config.project_id,
                mode=self.mode,
                allow_paid=self.allow_paid,
            )
            narrative_result = writer.run(
                story_strategy,
                editorial_package=editorial_package,
                event_discovery=event_discovery,
                semantic_analysis=semantic_analysis,
            )
            payload = narrative_result.to_dict()

        if (
            self.mode != "local_fallback"
            and bool(payload.get("fallback_used"))
        ):
            raise RuntimeError(
                "Production narration is blocked: "
                f"mode={self.mode!r}, "
                f"provider_status={payload.get('provider_status')!r}. "
                "Import an approved external script or complete "
                "the configured documentary provider successfully."
            )

        self._validate_result(payload)
        self.narrative_dir.mkdir(parents=True, exist_ok=True)
        self._atomic_write_json(self.narrative_result_path, payload)
        self._atomic_write_text(
            self.narrative_markdown_path,
            self._to_markdown(payload, title=resolved_title),
        )

        finished_at = datetime.now(timezone.utc)
        report = {
            "schema": "atlas_zero.narrative_runtime.rc2.v2",
            "state": payload.get("state", "NARRATIVE_READY"),
            "project_id": self.config.project_id,
            "title": resolved_title,
            "mode": self.mode,
            "allow_paid": self.allow_paid,
            "provider_status": payload.get("provider_status"),
            "provider_model": payload.get("provider_model"),
            "fallback_used": payload.get("fallback_used"),
            "scene_count": len(payload.get("scenes", [])),
            "target_duration_sec": payload.get("target_duration_sec"),
            "total_target_words": payload.get("total_target_words"),
            "warnings": payload.get("external_script", {}).get("warnings", []),
            "started_at": started_at.isoformat(),
            "finished_at": finished_at.isoformat(),
            "duration_sec": round((finished_at - started_at).total_seconds(), 3),
            "inputs": {
                "story_strategy": str(self.config.story_strategy_result_path),
                "event_discovery": str(self.config.event_discovery_result_path),
                "visual_semantic": str(self.config.visual_semantic_report_path),
                "editorial_package": str(editorial_path),
                "external_script": (
                    str(self.external_script_path.resolve())
                    if self.external_script_path is not None
                    else None
                ),
            },
            "outputs": {
                "narrative_result": str(self.narrative_result_path),
                "narrative_markdown": str(self.narrative_markdown_path),
            },
            "authority": "NarrativeRuntimeRC2",
        }
        self._atomic_write_json(self.narrative_report_path, report)
        report["report_path"] = str(self.narrative_report_path)
        return report

    def _discover_editorial_package(self) -> Path | None:
        directory = self.config.rc2_dir / "editorial_package"
        candidates = [
            directory / f"editorial_package_{self.config.project_id}.json",
            directory / "editorial_package.json",
        ]
        for path in candidates:
            if path.exists() and path.is_file():
                return path
        versioned = sorted(
            directory.glob("editorial_package*.json"),
            key=lambda path: (path.stat().st_mtime, path.name),
            reverse=True,
        ) if directory.exists() else []
        return versioned[0] if versioned else None

    def _write_editorial_package(self, payload: dict[str, Any]) -> Path:
        directory = self.config.rc2_dir / "editorial_package"
        directory.mkdir(parents=True, exist_ok=True)
        canonical = directory / "editorial_package.json"
        versioned = directory / f"editorial_package_{self.config.project_id}.json"
        self._atomic_write_json(canonical, payload)
        self._atomic_write_json(versioned, payload)
        return versioned

    @staticmethod
    def _read_json(path: Path, *, artifact_name: str) -> dict[str, Any]:
        if not path.exists():
            raise FileNotFoundError(f"{artifact_name} was not found: {path}")
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON in {artifact_name}: {path}") from exc
        if not isinstance(payload, dict):
            raise ValueError(f"{artifact_name} root must be an object: {path}")
        return payload

    def _discover_title(
        self,
        story_strategy: dict[str, Any],
        event_discovery: dict[str, Any],
    ) -> str:
        candidates = [
            story_strategy.get("title"),
            story_strategy.get("title_ru"),
            story_strategy.get("strategy", {}).get("title"),
            story_strategy.get("strategy", {}).get("title_ru"),
            event_discovery.get("title"),
            event_discovery.get("topic"),
            self.config.project_id,
        ]
        for candidate in candidates:
            value = str(candidate or "").strip()
            if value:
                return value
        return self.config.project_id

    @staticmethod
    def _target_duration(story_strategy: dict[str, Any]) -> float:
        strategy = story_strategy.get("strategy", {})
        value = strategy.get("target_duration_sec", 0)
        try:
            duration = float(value)
        except (TypeError, ValueError):
            duration = 0.0
        if duration <= 0:
            duration = sum(
                float(scene.get("duration_sec", 0) or 0)
                for scene in story_strategy.get("scenes", [])
            )
        return max(duration, 1.0)

    @staticmethod
    def _validate_result(payload: dict[str, Any]) -> None:
        scenes = payload.get("scenes")
        if not isinstance(scenes, list) or not scenes:
            raise ValueError("Narrative result contains no scenes")
        seen: set[str] = set()
        previous_end = 0.0
        calculated_words = 0
        for scene in scenes:
            if not isinstance(scene, dict):
                raise ValueError("Narrative scene must be an object")
            scene_id = str(scene.get("scene_id", "")).strip()
            if not scene_id:
                raise ValueError("Narrative scene has no scene_id")
            if scene_id in seen:
                raise ValueError(f"Duplicate narrative scene_id: {scene_id}")
            seen.add(scene_id)
            narration = str(scene.get("narration_ru", "")).strip()
            if not narration:
                raise ValueError(f"Narrative scene has no narration_ru: {scene_id}")
            start_sec = float(scene.get("start_sec", 0) or 0)
            end_sec = float(scene.get("end_sec", 0) or 0)
            if end_sec <= start_sec:
                raise ValueError(f"Invalid scene timing: {scene_id}")
            if start_sec < previous_end - 0.001:
                raise ValueError(f"Narrative scene timing overlaps: {scene_id}")
            previous_end = end_sec
            calculated_words += int(scene.get("target_words", 0) or 0)
        if calculated_words != int(payload.get("total_target_words", 0) or 0):
            raise ValueError("total_target_words mismatch")
        if not str(payload.get("full_narration_ru", "")).strip():
            raise ValueError("Narrative result has no full_narration_ru")

    @staticmethod
    def _to_markdown(payload: dict[str, Any], *, title: str) -> str:
        lines = [
            f"# {title}",
            "",
            f"**Режим:** {payload.get('generation_mode', '')}",
            f"**Источник:** {payload.get('provider_status', '')}",
            "",
        ]
        for scene in payload.get("scenes", []):
            scene_id = scene.get("scene_id", "")
            scene_title = scene.get("scene_title", scene_id)
            lines.extend([
                f"## {scene_id} — {scene_title}",
                "",
                str(scene.get("narration_ru", "")).strip(),
                "",
            ])
        return "\n".join(lines).rstrip() + "\n"

    @staticmethod
    def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
        text = json.dumps(payload, ensure_ascii=False, indent=2)
        NarrativeRuntimeRC2._atomic_write_text(path, text + "\n")

    @staticmethod
    def _atomic_write_text(path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".partial")
        temporary.write_text(text, encoding="utf-8")
        temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build canonical ATLAS ZERO RC2 narration."
    )
    parser.add_argument("project_id", help="ATLAS ZERO project identifier")
    parser.add_argument("--title", default=None, help="Optional documentary title")
    parser.add_argument(
        "--mode",
        default="openai_documentary",
        choices=sorted(NarrativeRuntimeRC2.VALID_MODES),
    )
    parser.add_argument(
        "--script-file",
        type=Path,
        default=None,
        help="Markdown, TXT or JSON script for external_script mode",
    )
    parser.add_argument("--no-paid", action="store_true")
    parser.add_argument("--rebuild-editorial-package", action="store_true")
    args = parser.parse_args()

    if args.mode == "external_script" and args.script_file is None:
        parser.error("--script-file is required for --mode external_script")

    config = ProjectConfigRC2(project_id=args.project_id)
    report = NarrativeRuntimeRC2(
        config,
        mode=args.mode,
        allow_paid=not args.no_paid,
        external_script_path=args.script_file,
    ).run(
        title=args.title,
        rebuild_editorial_package=args.rebuild_editorial_package,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
