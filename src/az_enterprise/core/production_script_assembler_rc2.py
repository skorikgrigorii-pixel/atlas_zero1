from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class ProductionScriptAssemblerRC2:
    """Assemble a universal production script from RC2 artifacts."""

    def __init__(
        self,
        *,
        project_id: str,
        title: str,
    ) -> None:
        self.project_id = project_id
        self.title = title

    def build(
        self,
        *,
        editorial_package: dict[str, Any],
        narrative_result: dict[str, Any],
    ) -> dict[str, Any]:
        scenes = list(
            editorial_package.get(
                "scenes",
                [],
            )
        )

        narration_rows = {
            str(row["scene_id"]): row
            for row in narrative_result.get(
                "scenes",
                [],
            )
        }

        if not scenes:
            raise ValueError(
                "Editorial package contains no scenes"
            )

        if not narration_rows:
            raise ValueError(
                "Narrative result contains no scenes"
            )

        output_scenes = []

        current_time = 0.0

        for scene in scenes:
            scene_id = str(
                scene["scene_id"]
            )

            narration = narration_rows.get(
                scene_id
            )

            if narration is None:
                raise ValueError(
                    f"Missing narration for scene {scene_id}"
                )

            duration = float(
                scene["duration_sec"]
            )

            start_sec = round(
                current_time,
                3,
            )

            end_sec = round(
                current_time + duration,
                3,
            )

            output_scenes.append({
                "scene_id": scene_id,
                "act_id": scene.get(
                    "act_id",
                    "",
                ),
                "order": scene.get(
                    "order",
                    len(output_scenes) + 1,
                ),
                "title": scene.get(
                    "title_ru",
                    scene_id,
                ),
                "start_sec": start_sec,
                "end_sec": end_sec,
                "duration_sec": duration,
                "storytelling_mode": str(
                    narration.get(
                        "storytelling_mode",
                        "NARRATION",
                    )
                ).strip().upper(),
                "video": {
                    "asset_ids": list(
                        scene.get(
                            "asset_ids",
                            [],
                        )
                    ),
                    "cluster_ids": list(
                        scene.get(
                            "cluster_ids",
                            [],
                        )
                    ),
                    "visual_strategy": (
                        narration.get(
                            "visual_direction"
                        )
                        or scene.get(
                            "visual_strategy_ru",
                            "",
                        )
                    ),
                    "storytelling_mode":
                        narration.get(
                            "storytelling_mode",
                            "NARRATION",
                        ),
                    "available_assets": scene.get(
                        "available_assets",
                        len(
                            scene.get(
                                "asset_ids",
                                [],
                            )
                        ),
                    ),
                },
                "voiceover": {
                    "language": narrative_result.get(
                        "language",
                        editorial_package.get(
                            "project",
                            {},
                        ).get(
                            "language",
                            "ru",
                        ),
                    ),
                    "text": narration.get(
                        "narration_ru",
                        "",
                    ),
                    "target_words": narration.get(
                        "target_words",
                        0,
                    ),
                    "direction": narration.get(
                        "voice_direction",
                        "",
                    ),
                    "pronunciation_hints":
                        narration.get(
                            "pronunciation_hints",
                            [],
                        ),
                },
                "sound": {
                    "direction": narration.get(
                        "audio_direction",
                        "",
                    ),
                    "sfx": (
                        "Use natural production sound "
                        "from assigned source assets."
                    ),
                    "music": (
                        "Use project music policy; "
                        "preserve intelligibility of voice-over."
                    ),
                },
                "transition": self._transition_for(
                    scene_id,
                    editorial_package.get(
                        "transitions",
                        [],
                    ),
                ),
                "narrative_goal": scene.get(
                    "narrative_goal_ru",
                    "",
                ),
                "emotional_goal": scene.get(
                    "emotional_goal_ru",
                    "",
                ),
            })

            current_time = end_sec

        result = {
            "schema_version": "2.8",
            "artifact_type": "production_script",
            "project_id": self.project_id,
            "title": self.title,
            "language": narrative_result.get(
                "language",
                "ru",
            ),
            "duration_sec": round(
                current_time,
                3,
            ),
            "scene_count": len(
                output_scenes
            ),
            "scenes": output_scenes,
            "full_voiceover": narrative_result.get(
                "full_narration_ru",
                "",
            ),
            "production_constraints":
                editorial_package.get(
                    "production_constraints",
                    {},
                ),
        }

        self.validate(result)
        return result

    @staticmethod
    def _transition_for(
        scene_id: str,
        transitions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        for transition in transitions:
            if str(
                transition.get(
                    "from_scene_id",
                    "",
                )
            ) == scene_id:
                return {
                    "type": transition.get(
                        "transition_type",
                        "cut",
                    ),
                    "to_scene_id": transition.get(
                        "to_scene_id",
                    ),
                    "rationale": transition.get(
                        "rationale_ru",
                        "",
                    ),
                    "narrator_bridge_required":
                        bool(
                            transition.get(
                                "narrator_bridge_required",
                                False,
                            )
                        ),
                }

        return {
            "type": "end",
            "to_scene_id": None,
            "rationale": "",
            "narrator_bridge_required": False,
        }

    @staticmethod
    def validate(
        result: dict[str, Any],
    ) -> None:
        if not result["project_id"]:
            raise ValueError(
                "project_id is required"
            )

        if not result["scenes"]:
            raise ValueError(
                "Production script requires scenes"
            )

        if result["duration_sec"] <= 0:
            raise ValueError(
                "Production script duration must be > 0"
            )

        for scene in result["scenes"]:
            storytelling_mode = str(
                scene["video"].get(
                    "storytelling_mode",
                    "NARRATION",
                )
            ).strip().upper()

            if (
                storytelling_mode == "NARRATION"
                and not scene["voiceover"]["text"].strip()
            ):
                raise ValueError(
                    f"Empty voice-over in narration "
                    f"scene {scene['scene_id']}"
                )

            if not scene["video"]["asset_ids"]:
                raise ValueError(
                    f"No assets assigned to {scene['scene_id']}"
                )

    def export(
        self,
        result: dict[str, Any],
        output_dir: Path | str,
    ) -> dict[str, str]:
        output_dir = Path(
            output_dir
        )

        output_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        json_path = (
            output_dir
            / "production_script.json"
        )

        txt_path = (
            output_dir
            / "production_script.txt"
        )

        md_path = (
            output_dir
            / "production_script.md"
        )

        json_path.write_text(
            json.dumps(
                result,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        plain_lines = [
            result["title"],
            "",
        ]

        markdown_lines = [
            f"# {result['title']}",
            "",
        ]

        for scene in result["scenes"]:
            timecode = (
                f"{self._format_time(scene['start_sec'])}"
                f" - "
                f"{self._format_time(scene['end_sec'])}"
            )

            plain_lines.extend([
                scene["scene_id"],
                scene["title"],
                timecode,
                "",
                "VIDEO",
                scene["video"]["visual_strategy"],
                "Assets: "
                + ", ".join(
                    scene["video"]["asset_ids"]
                ),
                "",
                "VOICEOVER",
                scene["voiceover"]["text"],
                "",
                "SFX",
                scene["sound"]["sfx"],
                "",
                "MUSIC",
                scene["sound"]["music"],
                "",
                "TRANSITION",
                str(
                    scene["transition"]["type"]
                ),
                "",
                "=" * 72,
                "",
            ])

            markdown_lines.extend([
                (
                    f"## {scene['scene_id']} - "
                    f"{scene['title']}"
                ),
                "",
                f"**Time:** {timecode}",
                "",
                "### Video",
                scene["video"]["visual_strategy"],
                "",
                (
                    "**Assets:** "
                    + ", ".join(
                        scene["video"]["asset_ids"]
                    )
                ),
                "",
                "### Voice-over",
                scene["voiceover"]["text"],
                "",
                "### SFX",
                scene["sound"]["sfx"],
                "",
                "### Music",
                scene["sound"]["music"],
                "",
                "### Transition",
                str(
                    scene["transition"]["type"]
                ),
                "",
            ])

        txt_path.write_text(
            "\n".join(
                plain_lines
            ),
            encoding="utf-8",
        )

        md_path.write_text(
            "\n".join(
                markdown_lines
            ),
            encoding="utf-8",
        )

        return {
            "json": str(
                json_path
            ),
            "txt": str(
                txt_path
            ),
            "md": str(
                md_path
            ),
        }

    @staticmethod
    def _format_time(
        seconds: float,
    ) -> str:
        total = max(
            0,
            int(round(seconds)),
        )

        minutes, sec = divmod(
            total,
            60,
        )

        hours, minutes = divmod(
            minutes,
            60,
        )

        if hours:
            return (
                f"{hours:02d}:"
                f"{minutes:02d}:"
                f"{sec:02d}"
            )

        return (
            f"{minutes:02d}:"
            f"{sec:02d}"
        )
