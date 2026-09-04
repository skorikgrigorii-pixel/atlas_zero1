from __future__ import annotations

import py_compile
import shutil
from datetime import datetime
from pathlib import Path


ROOT = Path.cwd()
TARGET = ROOT / "src" / "az_enterprise" / "core" / "render_engine_rc2.py"

if not TARGET.exists():
    raise FileNotFoundError(f"Target file is missing: {TARGET}")

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
backup = TARGET.with_name(
    f"{TARGET.name}.backup_before_source_audio_{timestamp}"
)

shutil.copy2(TARGET, backup)

text = TARGET.read_text(
    encoding="utf-8",
    errors="strict",
)


# ---------------------------------------------------------------------
# PATCH 1
# Correct legacy boolean natural_sound_window handling.
#
# Existing TimelineEngineRC2 writes:
#     natural_sound_window = True / False
#
# The parser expects a real interval. Convert True into a full-clip
# natural-sound window.
# ---------------------------------------------------------------------

old_window_block = '''        natural_windows = self._parse_natural_sound_windows(
            row.get("natural_sound_windows", row.get("natural_sound_window"))
        )
        natural_sound_enabled = self._as_bool(
            row.get("natural_sound_enabled", row.get("natural_audio_used")),
            default=bool(natural_windows),
        )
'''

new_window_block = '''        raw_natural_windows = row.get(
            "natural_sound_windows",
            row.get("natural_sound_window"),
        )

        # TimelineEngineRC2 historically emitted a boolean flag instead of
        # a concrete interval. True means that the complete rendered clip is
        # eligible for native source sound.
        if isinstance(raw_natural_windows, bool):
            natural_windows = (
                ((0.0, round(duration_sec, 3)),)
                if raw_natural_windows
                else tuple()
            )
        else:
            natural_windows = self._parse_natural_sound_windows(
                raw_natural_windows
            )

        natural_sound_enabled = self._as_bool(
            row.get(
                "natural_sound_enabled",
                row.get("natural_audio_used"),
            ),
            default=bool(natural_windows),
        )
'''

if old_window_block not in text:
    raise RuntimeError(
        "PATCH 1 anchor was not found. "
        "render_engine_rc2.py differs from the audited version."
    )

text = text.replace(
    old_window_block,
    new_window_block,
    1,
)


# ---------------------------------------------------------------------
# PATCH 2
# Replace silent-only Phase 4 mux with selective source-video audio.
# ---------------------------------------------------------------------

function_start = text.find(
    "    def _compose_phase4_audio(\n"
)

if function_start < 0:
    raise RuntimeError(
        "_compose_phase4_audio() was not found."
    )

function_end = text.find(
    "\n    @staticmethod\n"
    "    def _run_ffmpeg(",
    function_start,
)

if function_end < 0:
    raise RuntimeError(
        "_run_ffmpeg() anchor after _compose_phase4_audio() was not found."
    )

new_function = r'''    def _compose_phase4_audio(
        self,
        visual_source: Path,
        model: RenderModelRC2,
    ) -> tuple[Path, str]:
        """Build the RC2 programme soundtrack.

        Natural sound is read directly from selected source video files.
        No intermediate WAV files are required.

        Only a deterministic 35 percent of eligible event clips are used.
        Eligibility is limited to music bands, mascleta and fireworks.
        When narration exists, native sound is reduced underneath speech
        instead of being completely removed.
        """

        ffmpeg = shutil.which("ffmpeg")
        ffprobe = shutil.which("ffprobe")

        if not ffmpeg or not ffprobe:
            raise RuntimeError(
                "ffmpeg and ffprobe are not available in PATH"
            )

        output = (
            self.render_dir
            / "phase4_av_master_rc2.mp4"
        )
        output.unlink(missing_ok=True)

        event_keywords = {
            "music_band": (
                "music_band",
                "music band",
                "marching band",
                "brass band",
                "orchestra",
                "оркестр",
                "музыкальн",
                "band playing",
                "musicians",
            ),
            "mascleta": (
                "mascleta",
                "mascletà",
                "mascleta",
                "pyrotechnic explosions",
                "daytime pyrotechnic",
                "petard",
                "петард",
                "масклет",
            ),
            "fireworks": (
                "fireworks",
                "firework",
                "fuegos artificiales",
                "pyrotechnic display",
                "night pyrotechnic",
                "фейерверк",
                "салют",
            ),
        }

        def event_category(clip: RenderClipRC2) -> str | None:
            searchable = " ".join(
                str(value or "")
                for value in (
                    clip.scene_id,
                    clip.scene_title,
                    clip.block,
                    clip.story_goal,
                    clip.visual_need,
                    clip.emotion,
                    clip.asset_name,
                    clip.source_mode,
                )
            ).casefold()

            for category, keywords in event_keywords.items():
                if any(
                    keyword.casefold() in searchable
                    for keyword in keywords
                ):
                    return category

            return None

        def source_has_audio(path: Path) -> bool:
            process = subprocess.run(
                [
                    ffprobe,
                    "-v",
                    "error",
                    "-select_streams",
                    "a:0",
                    "-show_entries",
                    "stream=index",
                    "-of",
                    "csv=p=0",
                    str(path),
                ],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                check=False,
            )
            return (
                process.returncode == 0
                and bool(process.stdout.strip())
            )

        eligible: list[
            tuple[RenderClipRC2, str, Path]
        ] = []

        for clip in model.clips:
            if clip.media_type != "video":
                continue

            if not clip.natural_sound_enabled:
                continue

            category = event_category(clip)
            if category is None:
                continue

            source_path = Path(clip.asset_path)

            if not source_path.exists():
                continue

            if not source_has_audio(source_path):
                continue

            eligible.append(
                (
                    clip,
                    category,
                    source_path,
                )
            )

        # Exactly approximately 35 percent of eligible event shots.
        # Selection is deterministic and spread across the timeline.
        selected: list[
            tuple[RenderClipRC2, str, Path]
        ] = []

        if eligible:
            target_count = max(
                1,
                min(
                    len(eligible),
                    round(len(eligible) * 0.35),
                ),
            )

            if target_count >= len(eligible):
                selected = eligible
            elif target_count == 1:
                selected = [
                    eligible[len(eligible) // 2]
                ]
            else:
                selected_indexes: list[int] = []

                for position in range(target_count):
                    index = round(
                        position
                        * (len(eligible) - 1)
                        / (target_count - 1)
                    )

                    if index not in selected_indexes:
                        selected_indexes.append(index)

                # Rounding can theoretically reduce the count. Fill any
                # missing positions deterministically.
                if len(selected_indexes) < target_count:
                    for index in range(len(eligible)):
                        if index in selected_indexes:
                            continue
                        selected_indexes.append(index)
                        if len(selected_indexes) >= target_count:
                            break

                selected = [
                    eligible[index]
                    for index in sorted(
                        selected_indexes[:target_count]
                    )
                ]

        command: list[str] = [
            ffmpeg,
            "-y",
            "-i",
            str(visual_source),
        ]

        voice_input_index: int | None = None

        if model.voice_path:
            voice_input_index = len(command)  # informational only
            command.extend([
                "-i",
                str(model.voice_path),
            ])

        source_input_indexes: list[
            tuple[
                int,
                RenderClipRC2,
                str,
                Path,
                float,
                float,
            ]
        ] = []

        next_input_index = (
            2
            if model.voice_path
            else 1
        )

        for clip, category, source_path in selected:
            windows = (
                clip.natural_sound_windows
                or ((0.0, clip.duration_sec),)
            )

            # Current RC2 model normally contains one interval. Multiple
            # intervals are supported by opening the same source input again.
            for window_start, window_end in windows:
                bounded_start = max(
                    0.0,
                    min(
                        float(window_start),
                        clip.duration_sec,
                    ),
                )
                bounded_end = max(
                    bounded_start,
                    min(
                        float(window_end),
                        clip.duration_sec,
                    ),
                )

                window_duration = (
                    bounded_end
                    - bounded_start
                )

                if window_duration <= 0.05:
                    continue

                command.extend([
                    "-i",
                    str(source_path),
                ])

                source_input_indexes.append(
                    (
                        next_input_index,
                        clip,
                        category,
                        source_path,
                        bounded_start,
                        window_duration,
                    )
                )

                next_input_index += 1

        filters: list[str] = []
        natural_labels: list[str] = []

        for event_index, (
            input_index,
            clip,
            category,
            source_path,
            window_start,
            window_duration,
        ) in enumerate(
            source_input_indexes,
            start=1,
        ):
            source_start = (
                clip.source_in_sec
                + window_start
            )

            timeline_start = (
                clip.start_sec
                + window_start
            )

            delay_ms = max(
                0,
                int(round(timeline_start * 1000)),
            )

            fade_duration = min(
                0.18,
                window_duration / 4.0,
            )

            # Fireworks and mascleta need stronger presence than music-band
            # ambience, but all native sound remains below full-scale.
            gain_db = (
                -3.0
                if category in {
                    "mascleta",
                    "fireworks",
                }
                else -5.0
            )

            output_label = (
                f"[natural_{event_index}]"
            )

            chain = (
                f"[{input_index}:a:0]"
                f"atrim=start={source_start:.6f}:"
                f"duration={window_duration:.6f},"
                "asetpts=PTS-STARTPTS,"
                "aresample=48000,"
                "aformat=sample_fmts=fltp:"
                "channel_layouts=stereo,"
                f"volume={gain_db:.2f}dB"
            )

            if fade_duration > 0.01:
                fade_out_start = max(
                    0.0,
                    window_duration
                    - fade_duration,
                )
                chain += (
                    f",afade=t=in:st=0:"
                    f"d={fade_duration:.6f}"
                    f",afade=t=out:"
                    f"st={fade_out_start:.6f}:"
                    f"d={fade_duration:.6f}"
                )

            chain += (
                f",adelay={delay_ms}|{delay_ms}"
                f"{output_label}"
            )

            filters.append(chain)
            natural_labels.append(output_label)

        natural_mix_label: str | None = None

        if len(natural_labels) == 1:
            natural_mix_label = (
                "[natural_mix]"
            )
            filters.append(
                f"{natural_labels[0]}"
                "anull[natural_mix]"
            )
        elif len(natural_labels) > 1:
            natural_mix_label = (
                "[natural_mix]"
            )
            filters.append(
                "".join(natural_labels)
                + (
                    "amix="
                    f"inputs={len(natural_labels)}:"
                    "duration=longest:"
                    "dropout_transition=0:"
                    "normalize=0"
                    "[natural_mix]"
                )
            )

        final_audio_label: str | None = None

        if model.voice_path:
            voice_index = 1

            filters.append(
                f"[{voice_index}:a:0]"
                f"atrim=0:{model.expected_duration_sec:.6f},"
                "asetpts=PTS-STARTPTS,"
                "aresample=48000,"
                "aformat=sample_fmts=fltp:"
                "channel_layouts=stereo,"
                "asplit=2"
                "[voice_sidechain]"
                "[voice_programme]"
            )

            if natural_mix_label:
                # Native sound stays present under narration, but speech
                # reduces it dynamically instead of replacing it.
                filters.append(
                    f"{natural_mix_label}"
                    "[voice_sidechain]"
                    "sidechaincompress="
                    "threshold=0.025:"
                    "ratio=6:"
                    "attack=20:"
                    "release=450:"
                    "makeup=1"
                    "[natural_ducked]"
                )

                filters.append(
                    "[voice_programme]"
                    "[natural_ducked]"
                    "amix=inputs=2:"
                    "duration=longest:"
                    "dropout_transition=0:"
                    "normalize=0"
                    "[programme_mix]"
                )

                final_audio_label = (
                    "[programme_mix]"
                )
            else:
                final_audio_label = (
                    "[voice_programme]"
                )

        elif natural_mix_label:
            final_audio_label = natural_mix_label

        if final_audio_label:
            filters.append(
                f"{final_audio_label}"
                f"atrim=0:{model.expected_duration_sec:.6f},"
                f"apad=pad_dur={model.expected_duration_sec:.6f},"
                "alimiter=limit=0.95"
                "[audio_final]"
            )

            command.extend([
                "-filter_complex",
                ";".join(filters),
                "-map",
                "0:v:0",
                "-map",
                "[audio_final]",
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-b:a",
                "256k",
                "-ar",
                "48000",
                "-ac",
                "2",
                "-t",
                f"{model.expected_duration_sec:.6f}",
                "-movflags",
                "+faststart",
                str(output),
            ])

            if model.voice_path and natural_mix_label:
                mode = (
                    "voice_plus_selective_source_audio"
                )
            elif model.voice_path:
                mode = "voice_master"
            else:
                mode = (
                    "selective_source_audio"
                )

        else:
            # Compatibility silence remains only when there is genuinely no
            # usable programme audio: no narration and no eligible source
            # video with an audio stream.
            command.extend([
                "-f",
                "lavfi",
                "-i",
                (
                    "anullsrc="
                    "channel_layout=stereo:"
                    "sample_rate=48000"
                ),
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-b:a",
                "128k",
                "-t",
                f"{model.expected_duration_sec:.6f}",
                "-shortest",
                "-movflags",
                "+faststart",
                str(output),
            ])

            mode = (
                "silent_compatibility_track"
            )

        self._emit(
            "PHASE4_AUDIO_MUX_START",
            mode=mode,
            visual_source=str(visual_source),
            natural_sound_eligible=(
                len(eligible)
            ),
            natural_sound_selected=(
                len(selected)
            ),
            natural_sound_events=(
                len(source_input_indexes)
            ),
            natural_sound_ratio=(
                round(
                    len(selected)
                    / len(eligible),
                    4,
                )
                if eligible
                else 0.0
            ),
            natural_sound_categories={
                category: sum(
                    1
                    for _, selected_category, _
                    in selected
                    if selected_category
                    == category
                )
                for category
                in event_keywords
            },
        )

        self._run_ffmpeg(
            command,
            step=(
                "Phase 4 selective source "
                "audio composition"
            ),
        )

        if (
            not output.exists()
            or not output.is_file()
        ):
            raise FileNotFoundError(
                "Phase 4 audio mux output "
                f"missing: {output}"
            )

        self._emit(
            "PHASE4_AUDIO_MUX_COMPLETE",
            mode=mode,
            output=str(output),
            natural_sound_eligible=(
                len(eligible)
            ),
            natural_sound_selected=(
                len(selected)
            ),
            natural_sound_events=(
                len(source_input_indexes)
            ),
        )

        return output, mode
'''

text = (
    text[:function_start]
    + new_function
    + text[function_end:]
)

TARGET.write_text(
    text,
    encoding="utf-8",
)

try:
    py_compile.compile(
        str(TARGET),
        doraise=True,
    )
except Exception:
    shutil.copy2(
        backup,
        TARGET,
    )
    raise

print("=" * 88)
print("ATLAS ZERO RC2 — SELECTIVE SOURCE AUDIO PATCH")
print("=" * 88)
print(f"target={TARGET}")
print(f"backup={backup}")
print("syntax=OK")
print("source_audio_ratio=35%")
print("categories=music_band, mascleta, fireworks")
print("separate_audio_files=NO")
print("voice_ducking=ENABLED")
print("status=PATCH_APPLIED")
