from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


@dataclass
class Interval:
    start: float
    end: float
    label: str = ""
    source: str = ""
    preserve: bool = False

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


def run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )


def ffprobe_duration(path: Path) -> float:
    result = run([
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(path),
    ])
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed for {path}:\n{result.stderr}")
    return float(result.stdout.strip())


def detect_silence(
    audio_path: Path,
    *,
    threshold_db: float,
    min_silence_sec: float,
) -> list[Interval]:
    result = run([
        "ffmpeg", "-hide_banner", "-nostats",
        "-i", str(audio_path),
        "-af", f"silencedetect=noise={threshold_db}dB:d={min_silence_sec}",
        "-f", "null", "-",
    ])
    text = (result.stderr or "") + "\n" + (result.stdout or "")

    starts = [
        float(value)
        for value in re.findall(r"silence_start:\s*([0-9.]+)", text)
    ]
    ends = [
        (float(end), float(duration))
        for end, duration in re.findall(
            r"silence_end:\s*([0-9.]+)\s*\|\s*silence_duration:\s*([0-9.]+)",
            text,
        )
    ]

    intervals: list[Interval] = []
    for index, (end, duration) in enumerate(ends):
        start = starts[index] if index < len(starts) else max(0.0, end - duration)
        intervals.append(Interval(start=start, end=end, source="voice_silence"))

    if len(starts) > len(ends):
        total = ffprobe_duration(audio_path)
        intervals.append(Interval(start=starts[-1], end=total, source="voice_silence"))

    return intervals


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def first_number(mapping: dict[str, Any], keys: Iterable[str]) -> float | None:
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value.replace(",", "."))
            except ValueError:
                pass
    return None


def first_text(mapping: dict[str, Any], keys: Iterable[str]) -> str:
    values: list[str] = []
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, str) and value.strip():
            values.append(value.strip())
        elif isinstance(value, list):
            parts = [str(x).strip() for x in value if str(x).strip()]
            if parts:
                values.append(", ".join(parts))
    return " | ".join(dict.fromkeys(values))


def walk_dicts(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_dicts(child)


def extract_intervals(payload: Any, *, source: str) -> list[Interval]:
    start_keys = (
        "timeline_start_sec", "start_sec", "start", "in_sec",
        "timeline_start", "shot_start_sec",
    )
    end_keys = (
        "timeline_end_sec", "end_sec", "end", "out_sec",
        "timeline_end", "shot_end_sec",
    )
    duration_keys = ("duration_sec", "duration")

    label_keys = (
        "scene_id", "shot_id", "event_id", "category", "event_type",
        "label", "title", "title_ru", "story_goal", "description",
        "description_ru", "semantic_context", "dominant_event",
    )

    intervals: list[Interval] = []
    seen: set[tuple[float, float, str]] = set()

    for item in walk_dicts(payload):
        start = first_number(item, start_keys)
        end = first_number(item, end_keys)
        if start is None:
            continue
        if end is None:
            duration = first_number(item, duration_keys)
            if duration is not None:
                end = start + duration
        if end is None or end <= start:
            continue

        label = first_text(item, label_keys)
        preserve = bool(
            item.get("preserve_sync")
            or item.get("natural_sound_window")
            or item.get("natural_sound_enabled")
            or item.get("preserve_natural_sound")
        )

        key = (round(start, 3), round(end, 3), label)
        if key in seen:
            continue
        seen.add(key)
        intervals.append(
            Interval(
                start=float(start),
                end=float(end),
                label=label,
                source=source,
                preserve=preserve,
            )
        )

    return sorted(intervals, key=lambda x: (x.start, x.end))


def overlap_seconds(a: Interval, b: Interval) -> float:
    return max(0.0, min(a.end, b.end) - max(a.start, b.start))


def merge_silences(intervals: list[Interval], gap_tolerance: float = 0.12) -> list[Interval]:
    if not intervals:
        return []
    intervals = sorted(intervals, key=lambda x: x.start)
    merged = [intervals[0]]
    for current in intervals[1:]:
        previous = merged[-1]
        if current.start <= previous.end + gap_tolerance:
            previous.end = max(previous.end, current.end)
        else:
            merged.append(current)
    return merged


def tc(seconds: float) -> str:
    seconds = max(0.0, seconds)
    whole = int(seconds)
    ms = int(round((seconds - whole) * 1000))
    if ms == 1000:
        whole += 1
        ms = 0
    hours = whole // 3600
    minutes = (whole % 3600) // 60
    secs = whole % 60
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}.{ms:03d}"
    return f"{minutes:02d}:{secs:02d}.{ms:03d}"


def choose_existing(root: Path, candidates: list[str]) -> Path:
    for relative in candidates:
        path = root / relative
        if path.exists() and path.is_file():
            return path
    raise FileNotFoundError(
        "None of the expected files were found:\n"
        + "\n".join(str(root / item) for item in candidates)
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit narration gaps against film timeline and natural sound."
    )
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--threshold-db", type=float, default=-45.0)
    parser.add_argument("--min-silence", type=float, default=1.5)
    parser.add_argument("--candidate-min", type=float, default=2.5)
    parser.add_argument("--natural-overlap-ratio", type=float, default=0.35)
    args = parser.parse_args()

    root = args.root.resolve()

    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        raise RuntimeError("ffmpeg and ffprobe must be available in PATH")

    voice = choose_existing(root, [
        r"workspace\projects\hogueras\01_Audio\voice_master_timeline.wav",
        r"workspace\projects\hogueras\01_Audio\voice_master.wav",
    ])

    video = choose_existing(root, [
        r"workspace\exports\hogueras\rc2\render\hogueras_RC2_with_narration.mp4",
        r"workspace\exports\hogueras\rc2\render\phase4_av_master_rc2.mp4",
        r"workspace\exports\hogueras\rc2\render\visual_master_rc2.mp4",
    ])

    timeline_path = choose_existing(root, [
        r"workspace\exports\hogueras\rc2\timeline\timeline.json",
    ])

    natural_path = choose_existing(root, [
        r"workspace\exports\hogueras\rc2\audio\audio_events_bound_rc2.json",
        r"workspace\exports\hogueras\rc2\audio\audio_report_rc2.json",
    ])

    voice_duration = ffprobe_duration(voice)
    video_duration = ffprobe_duration(video)

    raw_silences = detect_silence(
        voice,
        threshold_db=args.threshold_db,
        min_silence_sec=args.min_silence,
    )
    silences = [
        interval
        for interval in merge_silences(raw_silences)
        if interval.duration >= args.candidate_min
    ]

    timeline = extract_intervals(read_json(timeline_path), source="timeline")
    natural = extract_intervals(read_json(natural_path), source="natural_sound")

    results: list[dict[str, Any]] = []
    for gap in silences:
        natural_hits = [
            item for item in natural
            if overlap_seconds(gap, item) > 0.05
        ]
        visual_hits = [
            item for item in timeline
            if overlap_seconds(gap, item) > 0.05
        ]

        natural_overlap = sum(overlap_seconds(gap, item) for item in natural_hits)
        natural_ratio = min(1.0, natural_overlap / gap.duration) if gap.duration else 0.0
        preserve = any(item.preserve for item in natural_hits)

        action = (
            "KEEP_NATURAL_SOUND"
            if preserve or natural_ratio >= args.natural_overlap_ratio
            else "NARRATION_CANDIDATE"
        )

        visual_labels = list(dict.fromkeys(
            item.label for item in visual_hits if item.label
        ))[:6]
        natural_labels = list(dict.fromkeys(
            item.label for item in natural_hits if item.label
        ))[:6]

        results.append({
            "start_sec": round(gap.start, 3),
            "end_sec": round(gap.end, 3),
            "duration_sec": round(gap.duration, 3),
            "timecode": f"{tc(gap.start)}–{tc(gap.end)}",
            "recommended_action": action,
            "natural_overlap_ratio": round(natural_ratio, 3),
            "preserve_natural_sound": preserve,
            "visual_context": visual_labels,
            "natural_sound_context": natural_labels,
        })

    out_dir = root / "workspace" / "audits" / "hogueras_voice_gap_audit"
    out_dir.mkdir(parents=True, exist_ok=True)

    json_path = out_dir / "voice_gap_audit.json"
    md_path = out_dir / "VOICE_GAP_AUDIT.md"
    csv_path = out_dir / "voice_gap_candidates.csv"

    summary = {
        "schema": "atlas_zero.voice_gap_audit.v1",
        "project_id": "hogueras",
        "voice_source": str(voice),
        "video_reference": str(video),
        "timeline_source": str(timeline_path),
        "natural_sound_source": str(natural_path),
        "voice_duration_sec": round(voice_duration, 3),
        "video_duration_sec": round(video_duration, 3),
        "duration_difference_sec": round(voice_duration - video_duration, 3),
        "settings": {
            "threshold_db": args.threshold_db,
            "minimum_detected_silence_sec": args.min_silence,
            "minimum_candidate_sec": args.candidate_min,
            "natural_overlap_ratio": args.natural_overlap_ratio,
        },
        "gap_count": len(results),
        "narration_candidate_count": sum(
            1 for item in results
            if item["recommended_action"] == "NARRATION_CANDIDATE"
        ),
        "keep_natural_sound_count": sum(
            1 for item in results
            if item["recommended_action"] == "KEEP_NATURAL_SOUND"
        ),
        "gaps": results,
    }

    json_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    md_lines = [
        "# HOGUERAS — VOICE GAP AUDIT",
        "",
        f"- Voice source: `{voice}`",
        f"- Video reference: `{video}`",
        f"- Voice duration: **{voice_duration:.3f} sec**",
        f"- Video duration: **{video_duration:.3f} sec**",
        f"- Candidate gaps: **{summary['narration_candidate_count']}**",
        f"- Natural-sound gaps: **{summary['keep_natural_sound_count']}**",
        "",
        "## Gap map",
        "",
    ]

    for index, item in enumerate(results, start=1):
        md_lines.extend([
            f"### {index:02d}. {item['timecode']} — {item['duration_sec']:.3f} sec",
            "",
            f"**Decision:** `{item['recommended_action']}`",
            "",
            f"**Visual context:** {'; '.join(item['visual_context']) or 'not resolved'}",
            "",
            f"**Natural sound:** {'; '.join(item['natural_sound_context']) or 'none detected'}",
            "",
            f"**Natural overlap:** {item['natural_overlap_ratio']:.1%}",
            "",
        ])

    md_path.write_text("\n".join(md_lines).rstrip() + "\n", encoding="utf-8")

    import csv
    with csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "timecode", "start_sec", "end_sec", "duration_sec",
                "recommended_action", "natural_overlap_ratio",
                "preserve_natural_sound", "visual_context",
                "natural_sound_context",
            ],
        )
        writer.writeheader()
        for item in results:
            row = dict(item)
            row["visual_context"] = " | ".join(item["visual_context"])
            row["natural_sound_context"] = " | ".join(item["natural_sound_context"])
            writer.writerow(row)

    print("=" * 88)
    print("ATLAS ZERO — HOGUERAS VOICE GAP AUDIT")
    print("=" * 88)
    print(f"Voice: {voice}")
    print(f"Video: {video}")
    print(f"Voice duration: {voice_duration:.3f} sec")
    print(f"Video duration: {video_duration:.3f} sec")
    print(f"Gaps found: {len(results)}")
    print(f"Narration candidates: {summary['narration_candidate_count']}")
    print(f"Keep natural sound: {summary['keep_natural_sound_count']}")
    print("")
    print(f"Markdown: {md_path}")
    print(f"JSON:     {json_path}")
    print(f"CSV:      {csv_path}")
    print("")
    print("No OpenAI or ElevenLabs request was started.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
