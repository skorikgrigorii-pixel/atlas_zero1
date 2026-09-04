from pathlib import Path
import subprocess
import json
import re

ROOT = Path.cwd()

FILM = ROOT / "workspace/exports/gardner/rc2/ru_remount/gardner_RU_REMOUNT_V4.mp4"
PLAN = ROOT / "workspace/exports/gardner/rc2/ru_remount/gardner_RU_REMOUNT_V4.json"

OUTDIR = ROOT / "workspace/exports/gardner/rc2/ru_remount/final_qc"
OUTDIR.mkdir(parents=True, exist_ok=True)

REPORT_JSON = OUTDIR / "GARDNER_RU_V4_FINAL_QC.json"
REPORT_MD   = OUTDIR / "GARDNER_RU_V4_FINAL_QC.md"

TARGET = 1291.848
EXPECTED_VOICE = 1231.819
EXPECTED_MUSIC = 60.029

if not FILM.exists():
    raise FileNotFoundError(FILM)

# ------------------------------------------------------------
# COMMAND HELPERS
# ------------------------------------------------------------

def run(cmd):
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        errors="replace"
    )

def probe_json(path):
    p = run([
        "ffprobe", "-v", "error",
        "-show_streams",
        "-show_format",
        "-of", "json",
        str(path)
    ])
    if p.returncode != 0:
        raise RuntimeError(p.stderr)
    return json.loads(p.stdout)

probe = probe_json(FILM)

video = next(
    (x for x in probe["streams"] if x.get("codec_type") == "video"),
    None
)
audio = next(
    (x for x in probe["streams"] if x.get("codec_type") == "audio"),
    None
)

if video is None:
    raise RuntimeError("VIDEO STREAM MISSING")

if audio is None:
    raise RuntimeError("AUDIO STREAM MISSING")

vdur = float(video.get("duration") or probe["format"]["duration"])
adur = float(audio.get("duration") or probe["format"]["duration"])
fdur = float(probe["format"]["duration"])

fps_raw = video.get("avg_frame_rate", "0/1")
a, b = fps_raw.split("/")
fps = float(a) / float(b) if float(b) else 0.0

# ------------------------------------------------------------
# DECODE INTEGRITY
# ------------------------------------------------------------

decode = run([
    "ffmpeg", "-v", "error",
    "-i", str(FILM),
    "-map", "0:v:0",
    "-map", "0:a:0",
    "-f", "null", "-"
])

decode_errors = [
    x.strip()
    for x in decode.stderr.splitlines()
    if x.strip()
]

# ------------------------------------------------------------
# BLACK FRAME DETECTION
#
# Only sustained black sections >= 0.50 sec are interesting.
# ------------------------------------------------------------

black = run([
    "ffmpeg", "-hide_banner",
    "-i", str(FILM),
    "-vf", "blackdetect=d=0.50:pic_th=0.98:pix_th=0.10",
    "-an", "-f", "null", "-"
])

black_events = []

for line in black.stderr.splitlines():
    if "black_start:" in line:
        m = re.search(
            r"black_start:([0-9.]+).*?"
            r"black_end:([0-9.]+).*?"
            r"black_duration:([0-9.]+)",
            line
        )
        if m:
            black_events.append({
                "start": float(m.group(1)),
                "end": float(m.group(2)),
                "duration": float(m.group(3))
            })

# ------------------------------------------------------------
# FREEZE DETECTION
#
# Flag only freezes >= 2.0 sec.
# Documentary stills can naturally trigger this detector,
# therefore freezes are REVIEW items, not automatic failures.
# ------------------------------------------------------------

freeze = run([
    "ffmpeg", "-hide_banner",
    "-i", str(FILM),
    "-vf", "freezedetect=n=-55dB:d=2.0",
    "-an", "-f", "null", "-"
])

freeze_starts = []
freeze_ends = []

for line in freeze.stderr.splitlines():
    m = re.search(r"freeze_start:\s*([0-9.]+)", line)
    if m:
        freeze_starts.append(float(m.group(1)))

    m = re.search(r"freeze_end:\s*([0-9.]+)", line)
    if m:
        freeze_ends.append(float(m.group(1)))

freeze_events = []

for i, start in enumerate(freeze_starts):
    end = freeze_ends[i] if i < len(freeze_ends) else None
    freeze_events.append({
        "start": start,
        "end": end,
        "duration": (end - start) if end is not None else None
    })

# ------------------------------------------------------------
# SILENCE DETECTION
#
# We expect deliberate music/voice structure, but long digital
# silence would indicate a possible assembly problem.
# ------------------------------------------------------------

silence = run([
    "ffmpeg", "-hide_banner",
    "-i", str(FILM),
    "-af", "silencedetect=noise=-45dB:d=2.0",
    "-vn", "-f", "null", "-"
])

silence_starts = []
silence_ends = []

for line in silence.stderr.splitlines():
    m = re.search(r"silence_start:\s*([0-9.]+)", line)
    if m:
        silence_starts.append(float(m.group(1)))

    m = re.search(r"silence_end:\s*([0-9.]+)", line)
    if m:
        silence_ends.append(float(m.group(1)))

silence_events = []

for i, start in enumerate(silence_starts):
    end = silence_ends[i] if i < len(silence_ends) else None
    silence_events.append({
        "start": start,
        "end": end,
        "duration": (end - start) if end is not None else None
    })

# ------------------------------------------------------------
# AUDIO LOUDNESS
# ------------------------------------------------------------

loud = run([
    "ffmpeg", "-hide_banner",
    "-i", str(FILM),
    "-vn",
    "-af", "ebur128=peak=true",
    "-f", "null", "-"
])

def last_match(pattern, text):
    values = re.findall(pattern, text)
    return values[-1] if values else None

integrated = last_match(
    r"I:\s*(-?[0-9.]+)\s*LUFS",
    loud.stderr
)

lra = last_match(
    r"LRA:\s*([0-9.]+)\s*LU",
    loud.stderr
)

true_peak = last_match(
    r"Peak:\s*(-?[0-9.]+)\s*dBFS",
    loud.stderr
)

# ------------------------------------------------------------
# PLAN / LOCKED RUNTIME CHECK
# ------------------------------------------------------------

plan_info = {}

if PLAN.exists():
    p = json.loads(PLAN.read_text(encoding="utf-8-sig"))

    music = p.get("music_distribution", [])

    plan_info = {
        "target_duration_sec": p.get("target_duration_sec"),
        "music_distribution": music,
        "music_total": sum(float(x) for x in music) if music else None,
        "version": p.get("version"),
        "v4_replacements": len(p.get("v4_replacements", {}))
    }

# ------------------------------------------------------------
# QC DECISIONS
# ------------------------------------------------------------

checks = []

def check(name, ok, value, severity="BLOCKER"):
    checks.append({
        "name": name,
        "ok": bool(ok),
        "value": value,
        "severity": severity
    })

check(
    "Resolution 1920x1080",
    video.get("width") == 1920 and video.get("height") == 1080,
    f"{video.get('width')}x{video.get('height')}"
)

check(
    "Frame rate 30 fps",
    abs(fps - 30.0) < 0.01,
    fps
)

check(
    "Video runtime",
    abs(vdur - TARGET) <= 0.050,
    vdur
)

check(
    "Audio runtime",
    abs(adur - TARGET) <= 0.050,
    adur
)

check(
    "A/V duration delta",
    abs(vdur - adur) <= 0.050,
    abs(vdur - adur)
)

check(
    "Decode integrity",
    decode.returncode == 0 and len(decode_errors) == 0,
    decode_errors if decode_errors else "clean"
)

check(
    "No sustained black frames",
    len(black_events) == 0,
    black_events
)

check(
    "No unexpected >=2s silence",
    len(silence_events) == 0,
    silence_events
)

# Freeze is deliberately REVIEW, because Gardner contains stills.
check(
    "Freeze detector",
    True,
    freeze_events,
    severity="REVIEW"
)

if integrated is not None:
    check(
        "Integrated loudness available",
        True,
        f"{integrated} LUFS",
        severity="INFO"
    )

if true_peak is not None:
    peak = float(true_peak)
    check(
        "True peak below -1 dBFS",
        peak <= -1.0,
        f"{peak} dBFS",
        severity="REVIEW"
    )

if plan_info.get("music_total") is not None:
    check(
        "Music total locked",
        abs(plan_info["music_total"] - EXPECTED_MUSIC) <= 0.010,
        plan_info["music_total"]
    )

blockers = [
    x for x in checks
    if x["severity"] == "BLOCKER" and not x["ok"]
]

status = (
    "PASS — RELEASE CANDIDATE"
    if not blockers
    else "FAIL — BLOCKERS DETECTED"
)

result = {
    "project": "gardner",
    "language": "ru",
    "version": "V4",
    "status": status,
    "film": str(FILM),
    "expected": {
        "runtime": TARGET,
        "voice": EXPECTED_VOICE,
        "music": EXPECTED_MUSIC
    },
    "streams": {
        "video_duration": vdur,
        "audio_duration": adur,
        "format_duration": fdur,
        "av_delta": abs(vdur - adur),
        "resolution": f"{video.get('width')}x{video.get('height')}",
        "fps": fps,
        "video_codec": video.get("codec_name"),
        "audio_codec": audio.get("codec_name"),
        "sample_rate": audio.get("sample_rate"),
        "channels": audio.get("channels")
    },
    "audio_analysis": {
        "integrated_lufs": integrated,
        "lra_lu": lra,
        "true_peak_dbfs": true_peak,
        "silence_events": silence_events
    },
    "visual_analysis": {
        "black_events": black_events,
        "freeze_events": freeze_events
    },
    "plan": plan_info,
    "checks": checks,
    "blockers": blockers
}

REPORT_JSON.write_text(
    json.dumps(result, ensure_ascii=False, indent=2),
    encoding="utf-8"
)

md = [
    "# ATLAS ZERO — GARDNER RU V4 FINAL QC",
    "",
    f"## STATUS: {status}",
    "",
    f"- Film: `{FILM}`",
    f"- Runtime: `{fdur:.3f}` sec",
    f"- Video: `{vdur:.3f}` sec",
    f"- Audio: `{adur:.3f}` sec",
    f"- A/V delta: `{abs(vdur-adur):.4f}` sec",
    f"- Resolution: `{video.get('width')}x{video.get('height')}`",
    f"- FPS: `{fps:.3f}`",
    "",
    "## AUDIO",
    "",
    f"- Integrated: `{integrated} LUFS`",
    f"- LRA: `{lra} LU`",
    f"- True peak: `{true_peak} dBFS`",
    f"- Silence events >=2 sec: `{len(silence_events)}`",
    "",
    "## VISUAL",
    "",
    f"- Sustained black events: `{len(black_events)}`",
    f"- Freeze events >=2 sec: `{len(freeze_events)}`",
    "",
    "## CHECKS",
    ""
]

for x in checks:
    mark = "PASS" if x["ok"] else "FAIL"
    md.append(
        f"- [{mark}] {x['name']} — {x['value']}"
    )

md += [
    "",
    "## BLOCKERS",
    ""
]

if blockers:
    for x in blockers:
        md.append(f"- {x['name']}: {x['value']}")
else:
    md.append("- NONE")

REPORT_MD.write_text(
    "\n".join(md),
    encoding="utf-8"
)

print()
print("=" * 76)
print("ATLAS ZERO — GARDNER RU V4 FINAL QC")
print("=" * 76)
print("STATUS :", status)
print(f"VIDEO  : {vdur:.6f}")
print(f"AUDIO  : {adur:.6f}")
print(f"DELTA  : {abs(vdur-adur):.6f}")
print(f"BLACK  : {len(black_events)}")
print(f"FREEZE : {len(freeze_events)}")
print(f"SILENCE: {len(silence_events)}")
print(f"LUFS   : {integrated}")
print(f"LRA    : {lra}")
print(f"PEAK   : {true_peak}")
print(f"BLOCKERS: {len(blockers)}")
print()
print("REPORT :", REPORT_MD)
print("JSON   :", REPORT_JSON)
print("=" * 76)

