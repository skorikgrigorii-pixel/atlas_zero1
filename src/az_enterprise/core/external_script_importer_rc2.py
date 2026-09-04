from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


RUSSIAN_WORDS_PER_MINUTE = 132.0


@dataclass(frozen=True)
class ExternalScriptSceneRC2:
    scene_id: str
    title: str
    narration_ru: str = ""
    duration_sec: float | None = None

    # RC2 directorial handoff extension.
    # narration_ru remains for backward compatibility.
    narration: str = ""
    storytelling_mode: str = "NARRATION"
    visual_direction: str = ""
    audio_direction: str = ""
    voice_direction: str = ""
    pronunciation_hints: tuple[str, ...] = ()


class ExternalScriptImporterRC2:
    """Convert an operator-authored script into canonical RC2 narrative_result.

    Supported input formats:

    1. Markdown / plain text::

        # Film title
        ## SC01 — Opening
        Narration text...

        ## SC02 — Development
        Narration text...

    2. JSON with either ``scenes`` as a list or a scene-id mapping::

        {"scenes": [{"scene_id": "SC01", "narration_ru": "..."}]}

        {"SC01": "...", "SC02": "..."}

    Scene timing, source clusters and source assets remain authoritative in the
    Story Strategy. The imported file replaces narration only.
    """

    HEADING_RE = re.compile(
        r"^##\s+([^\s—–:|]+)(?:\s*[—–:|]\s*(.*))?$",
        re.MULTILINE,
    )

    def __init__(
        self,
        *,
        project_id: str,
        words_per_minute: float = RUSSIAN_WORDS_PER_MINUTE,
    ) -> None:
        self.project_id = str(project_id).strip()
        if not self.project_id:
            raise ValueError("project_id is required")
        self.words_per_minute = max(80.0, float(words_per_minute))

    def import_file(
        self,
        script_path: Path,
        *,
        story_strategy: dict[str, Any],
        title: str | None = None,
    ) -> dict[str, Any]:
        path = Path(script_path).expanduser().resolve()
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"External script was not found: {path}")

        text = self._read_text(path)
        parsed_title, imported = self._parse(text, suffix=path.suffix.lower())
        return self.build(
            story_strategy=story_strategy,
            imported_scenes=imported,
            source_path=path,
            title=title or parsed_title,
        )

    def build(
        self,
        *,
        story_strategy: dict[str, Any],
        imported_scenes: list[ExternalScriptSceneRC2],
        source_path: Path,
        title: str | None = None,
    ) -> dict[str, Any]:
        strategy = dict(story_strategy.get("strategy") or {})
        strategy_scenes = list(story_strategy.get("scenes") or [])
        if not strategy_scenes:
            raise ValueError("Story Strategy contains no scenes")

        by_id: dict[str, ExternalScriptSceneRC2] = {}
        for scene in imported_scenes:
            scene_id = scene.scene_id.strip()
            if not scene_id:
                raise ValueError("External script contains an empty scene_id")
            if scene_id in by_id:
                raise ValueError(f"Duplicate external scene_id: {scene_id}")
            narration = self._clean_narration(
                scene.narration or scene.narration_ru
            )

            storytelling_mode = str(
                scene.storytelling_mode or "NARRATION"
            ).strip().upper()

            valid_modes = {
                "NARRATION",
                "VISUAL_MUSIC",
                "VISUAL_SFX",
                "MUSIC_ONLY",
            }

            if storytelling_mode not in valid_modes:
                raise ValueError(
                    f"Unsupported storytelling_mode "
                    f"{storytelling_mode!r} for {scene_id}"
                )

            if (
                storytelling_mode == "NARRATION"
                and not narration
            ):
                raise ValueError(
                    f"External narration scene contains no "
                    f"narration: {scene_id}"
                )

            if (
                storytelling_mode != "NARRATION"
                and scene.duration_sec is None
            ):
                raise ValueError(
                    f"Non-narration scene {scene_id} "
                    f"requires explicit duration_sec"
                )

            by_id[scene_id] = ExternalScriptSceneRC2(
                scene_id=scene_id,
                title=scene.title.strip(),
                narration_ru=narration,
                duration_sec=scene.duration_sec,
                narration=narration,
                storytelling_mode=storytelling_mode,
                visual_direction=scene.visual_direction.strip(),
                audio_direction=scene.audio_direction.strip(),
                voice_direction=scene.voice_direction.strip(),
                pronunciation_hints=tuple(
                    scene.pronunciation_hints
                ),
            )

        required_ids = [str(scene.get("scene_id") or "").strip() for scene in strategy_scenes]
        if any(not scene_id for scene_id in required_ids):
            raise ValueError("Story Strategy contains a scene without scene_id")

        missing = [scene_id for scene_id in required_ids if scene_id not in by_id]
        extra = sorted(set(by_id) - set(required_ids))
        if missing:
            raise ValueError(
                "External script is missing required scenes: " + ", ".join(missing)
            )
        if extra:
            raise ValueError(
                "External script contains unknown scenes: " + ", ".join(extra)
            )

        current_time = 0.0
        result_scenes: list[dict[str, Any]] = []
        warnings: list[dict[str, Any]] = []

        for index, strategy_scene in enumerate(strategy_scenes, start=1):
            scene_id = required_ids[index - 1]
            imported = by_id[scene_id]
            duration_source = (
                imported.duration_sec
                if imported.duration_sec is not None
                else strategy_scene.get("duration_sec")
            )

            duration = self._positive_float(
                duration_source,
                field=f"duration_sec for {scene_id}",
            )
            start_sec = round(current_time, 3)
            end_sec = round(start_sec + duration, 3)
            actual_words = (
                self._word_count(imported.narration_ru)
                if imported.narration_ru.strip()
                else 0
            )
            planned_words = max(
                1,
                round(
                    duration / 60.0
                    * self.words_per_minute
                ),
            )
            estimated_voice_sec = round(
                actual_words
                / self.words_per_minute
                * 60.0,
                3,
            )
            utilization = round(
                estimated_voice_sec / duration,
                3,
            )

            if (
                imported.storytelling_mode == "NARRATION"
                and utilization > 1.10
            ):
                warnings.append({
                    "scene_id": scene_id,
                    "code": "VOICEOVER_LONGER_THAN_SCENE",
                    "duration_sec": duration,
                    "estimated_voice_sec": estimated_voice_sec,
                    "actual_words": actual_words,
                    "planned_words": planned_words,
                })
            elif (
                imported.storytelling_mode == "NARRATION"
                and utilization < 0.45
            ):
                warnings.append({
                    "scene_id": scene_id,
                    "code": "VOICEOVER_USES_LESS_THAN_45_PERCENT",
                    "duration_sec": duration,
                    "estimated_voice_sec": estimated_voice_sec,
                    "actual_words": actual_words,
                    "planned_words": planned_words,
                })

            title_value = (
                imported.title
                or str(strategy_scene.get("title_ru") or "").strip()
                or f"Сцена {index}"
            )
            sentences = self._sentences(imported.narration_ru)

            result_scenes.append({
                "scene_id": scene_id,
                "scene_title": title_value,
                "start_sec": start_sec,
                "end_sec": end_sec,
                "duration_sec": round(duration, 3),
                "target_words": actual_words,
                "planned_target_words": planned_words,
                "estimated_voice_sec": estimated_voice_sec,
                "voice_utilization": utilization,
                "narration_ru": imported.narration_ru,
                "opening_line_ru": sentences[0] if sentences else imported.narration_ru,
                "closing_line_ru": sentences[-1] if sentences else imported.narration_ru,
                "narrator_bridge_ru": "",
                "storytelling_mode":
                    imported.storytelling_mode,
                "visual_direction":
                    imported.visual_direction,
                "audio_direction":
                    imported.audio_direction,
                "voice_direction":
                    imported.voice_direction,
                "pronunciation_hints": list(
                    imported.pronunciation_hints
                ),
                "source_cluster_ids": [
                    str(value) for value in strategy_scene.get("cluster_ids", [])
                ] or [f"external:{scene_id}"],
                "source_asset_ids": [
                    str(value) for value in strategy_scene.get("asset_ids", [])
                ] or [f"external:{scene_id}"],
            })
            current_time = end_sec

        target_duration = self._optional_float(strategy.get("target_duration_sec"))
        if target_duration <= 0:
            target_duration = current_time

        full_narration = "\n\n".join(
            scene["narration_ru"] for scene in result_scenes
        ).strip()
        total_words = sum(int(scene["target_words"]) for scene in result_scenes)

        return {
            "engine": "external_script_importer_rc2",
            "state": "NARRATIVE_READY_WITH_WARNINGS" if warnings else "NARRATIVE_READY",
            "project_id": self.project_id,
            "language": str(strategy.get("language") or "ru"),
            "target_duration_sec": round(target_duration, 3),
            "total_target_words": total_words,
            "film_concept_ru": str(title or "").strip(),
            "generation_mode": "external_script",
            "provider_status": "external_script_loaded",
            "provider_model": "chatgpt_operator_handoff",
            "fallback_used": False,
            "external_script": {
                "source_path": str(source_path),
                "scene_count": len(result_scenes),
                "warnings": warnings,
            },
            "scenes": result_scenes,
            "full_narration_ru": full_narration,
        }

    def _parse(
        self,
        text: str,
        *,
        suffix: str,
    ) -> tuple[str, list[ExternalScriptSceneRC2]]:
        stripped = text.lstrip("\ufeff \t\r\n")
        if suffix == ".json" or stripped.startswith("{"):
            return self._parse_json(stripped)
        return self._parse_markdown(text)

    def _parse_json(self, text: str) -> tuple[str, list[ExternalScriptSceneRC2]]:
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError("External script contains invalid JSON") from exc
        if not isinstance(payload, dict):
            raise ValueError("External script JSON root must be an object")

        title = str(payload.get("title") or payload.get("film_concept_ru") or "").strip()
        raw_scenes = payload.get("scenes")
        scenes: list[ExternalScriptSceneRC2] = []

        if isinstance(raw_scenes, list):
            for item in raw_scenes:
                if not isinstance(item, dict):
                    raise ValueError("Each JSON scene must be an object")
                raw_duration = item.get("duration_sec")

                duration_sec = (

                    float(raw_duration)

                    if raw_duration not in (None, "")

                    else None

                )

                scenes.append(ExternalScriptSceneRC2(
                    scene_id=str(
                        item.get("scene_id") or ""
                    ).strip(),
                    title=str(
                        item.get("title")
                        or item.get("scene_title")
                        or ""
                    ).strip(),
                    narration_ru=str(
                        item.get("narration_ru")
                        or item.get("narration")
                        or item.get("voiceover")
                        or item.get("text")
                        or ""
                    ),
                    duration_sec=duration_sec,
                    narration=str(
                        item.get("narration")
                        or item.get("narration_ru")
                        or item.get("voiceover")
                        or item.get("text")
                        or ""
                    ),
                    storytelling_mode=str(
                        item.get("storytelling_mode")
                        or "NARRATION"
                    ).strip().upper(),
                    visual_direction=str(
                        item.get("visual_direction")
                        or ""
                    ).strip(),
                    audio_direction=str(
                        item.get("audio_direction")
                        or ""
                    ).strip(),
                    voice_direction=str(
                        item.get("voice_direction")
                        or ""
                    ).strip(),
                    pronunciation_hints=tuple(
                        str(value).strip()
                        for value in (
                            item.get("pronunciation_hints")
                            or []
                        )
                        if str(value).strip()
                    ),
                ))
        else:
            ignored = {
                "title", "film_concept_ru", "project_id", "language",
                "generation_mode", "provider_status", "provider_model",
                "full_narration_ru", "engine", "state",
            }
            for key, value in payload.items():
                if key in ignored:
                    continue
                if isinstance(value, str):
                    scenes.append(ExternalScriptSceneRC2(
                        scene_id=str(key).strip(),
                        title="",
                        narration_ru=value,
                    ))
                elif isinstance(value, dict):
                    raw_duration = value.get("duration_sec")

                    duration_sec = (

                        float(raw_duration)

                        if raw_duration not in (None, "")

                        else None

                    )

                    scenes.append(ExternalScriptSceneRC2(
                        scene_id=str(
                            value.get("scene_id")
                            or key
                        ).strip(),
                        title=str(
                            value.get("title")
                            or value.get("scene_title")
                            or ""
                        ).strip(),
                        narration_ru=str(
                            value.get("narration_ru")
                            or value.get("narration")
                            or value.get("voiceover")
                            or value.get("text")
                            or ""
                        ),
                        duration_sec=duration_sec,
                        narration=str(
                            value.get("narration")
                            or value.get("narration_ru")
                            or value.get("voiceover")
                            or value.get("text")
                            or ""
                        ),
                        storytelling_mode=str(
                            value.get("storytelling_mode")
                            or "NARRATION"
                        ).strip().upper(),
                        visual_direction=str(
                            value.get("visual_direction")
                            or ""
                        ).strip(),
                        audio_direction=str(
                            value.get("audio_direction")
                            or ""
                        ).strip(),
                        voice_direction=str(
                            value.get("voice_direction")
                            or ""
                        ).strip(),
                        pronunciation_hints=tuple(
                            str(item).strip()
                            for item in (
                                value.get("pronunciation_hints")
                                or []
                            )
                            if str(item).strip()
                        ),
                    ))

        if not scenes:
            raise ValueError("External script JSON contains no scenes")
        return title, scenes

    def _parse_markdown(self, text: str) -> tuple[str, list[ExternalScriptSceneRC2]]:
        title_match = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
        title = title_match.group(1).strip() if title_match else ""
        matches = list(self.HEADING_RE.finditer(text))
        if not matches:
            raise ValueError(
                "External script must contain scene headings like '## SC01 — Title'"
            )

        scenes: list[ExternalScriptSceneRC2] = []
        for index, match in enumerate(matches):
            body_start = match.end()
            body_end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            body = text[body_start:body_end].strip()
            scenes.append(ExternalScriptSceneRC2(
                scene_id=match.group(1).strip(),
                title=(match.group(2) or "").strip(),
                narration_ru=body,
            ))
        return title, scenes

    @staticmethod
    def _read_text(path: Path) -> str:
        for encoding in ("utf-8-sig", "utf-8", "cp1251"):
            try:
                return path.read_text(encoding=encoding)
            except UnicodeDecodeError:
                continue
        raise ValueError(f"Unable to decode external script: {path}")

    @staticmethod
    def _clean_narration(text: str) -> str:
        value = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
        value = re.sub(r"\n{3,}", "\n\n", value)
        return value.strip()

    @staticmethod
    def _word_count(text: str) -> int:
        return max(1, len(re.findall(r"[\wЁёА-Яа-я'-]+", text, flags=re.UNICODE)))

    @staticmethod
    def _sentences(text: str) -> list[str]:
        return [
            item.strip()
            for item in re.split(r"(?<=[.!?…])\s+", text.strip())
            if item.strip()
        ]

    @staticmethod
    def _positive_float(value: Any, *, field: str) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid {field}: {value!r}") from exc
        if number <= 0:
            raise ValueError(f"{field} must be > 0")
        return number

    @staticmethod
    def _optional_float(value: Any) -> float:
        try:
            return float(value or 0)
        except (TypeError, ValueError):
            return 0.0
