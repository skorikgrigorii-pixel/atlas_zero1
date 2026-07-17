from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .production_script_assembler_rc2 import (
    ProductionScriptAssemblerRC2,
)
from .project_config_rc2 import ProjectConfigRC2


class ProductionScriptRegeneratorRC2:
    """Rebuild the canonical production script from current RC2 artifacts."""

    def __init__(
        self,
        config: ProjectConfigRC2,
    ) -> None:
        self.config = config

    def run(
        self,
        *,
        title: str | None = None,
    ) -> dict[str, Any]:
        editorial_path = (
            self._discover_editorial_package()
        )
        narrative_path = (
            self._discover_narrative_result()
        )

        editorial = self._read_json(
            editorial_path
        )
        narrative = self._read_json(
            narrative_path
        )

        project_title = (
            title
            or editorial.get(
                "project",
                {},
            ).get(
                "title",
                self.config.project_id,
            )
        )

        assembler = (
            ProductionScriptAssemblerRC2(
                project_id=
                    self.config.project_id,
                title=str(project_title),
            )
        )

        production_script = assembler.build(
            editorial_package=editorial,
            narrative_result=narrative,
        )

        output_dir = (
            self.config.project_dir
            / "script"
        )

        paths = assembler.export(
            production_script,
            output_dir,
        )

        return {
            "state":
                "PRODUCTION_SCRIPT_REGENERATED",
            "project_id":
                self.config.project_id,
            "scenes":
                production_script["scene_count"],
            "duration_sec":
                production_script["duration_sec"],
            "editorial_package_path":
                str(editorial_path),
            "narrative_result_path":
                str(narrative_path),
            "artifact_json":
                paths["json"],
            "artifact_txt":
                paths["txt"],
            "artifact_md":
                paths["md"],
            "voiceover_words":
                self._count_scene_words(
                    production_script
                ),
            "authority":
                "ProductionScriptRegeneratorRC2",
        }

    def _discover_editorial_package(
        self,
    ) -> Path:
        candidates = [
            (
                self.config.export_dir
                / "rc2"
                / "editorial_package"
                / (
                    "editorial_package_"
                    f"{self.config.project_id}.json"
                )
            ),
            (
                self.config.export_dir
                / "rc2"
                / "editorial_package"
                / "editorial_package.json"
            ),
        ]

        return self._first_existing(
            candidates,
            artifact_name=
                "Editorial Package",
        )

    def _discover_narrative_result(
        self,
    ) -> Path:
        narrative_dir = (
            self.config.export_dir
            / "rc2"
            / "narrative"
        )

        canonical = (
            narrative_dir
            / "narrative_result.json"
        )

        if canonical.exists():
            return canonical

        versioned = sorted(
            narrative_dir.glob(
                "narrative_result*.json"
            ),
            key=lambda path: (
                path.stat().st_mtime,
                path.name,
            ),
            reverse=True,
        )

        if versioned:
            return versioned[0]

        raise FileNotFoundError(
            "Narrative Result was not found for "
            f"project {self.config.project_id}"
        )

    @staticmethod
    def _first_existing(
        candidates: list[Path],
        *,
        artifact_name: str,
    ) -> Path:
        for path in candidates:
            if (
                path.exists()
                and path.is_file()
            ):
                return path

        raise FileNotFoundError(
            f"{artifact_name} was not found"
        )

    @staticmethod
    def _read_json(
        path: Path,
    ) -> dict[str, Any]:
        try:
            payload = json.loads(
                path.read_text(
                    encoding="utf-8"
                )
            )
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Invalid JSON: {path}"
            ) from exc

        if not isinstance(
            payload,
            dict,
        ):
            raise ValueError(
                f"JSON root must be an object: {path}"
            )

        return payload

    @staticmethod
    def _count_scene_words(
        production_script: dict[str, Any],
    ) -> int:
        return sum(
            len(
                str(
                    scene.get(
                        "voiceover",
                        {},
                    ).get(
                        "text",
                        "",
                    )
                ).split()
            )
            for scene in production_script.get(
                "scenes",
                [],
            )
        )
