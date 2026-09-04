from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
from collections import Counter
from pathlib import Path

ROOT = Path.cwd().resolve()
PROJECT_ID = "film_10_nepal_tibet_aftershock"
PROJECT = ROOT / "workspace" / "projects" / PROJECT_ID
DB = ROOT / "workspace" / "atlas_zero_enterprise.sqlite3"

TIMELINE_PATH = (
    PROJECT / "00_Production" / "rough_cut_v2"
    / "FILM10_ROUGH_CUT_TIMELINE_V2.json"
)

GAPS_PATH = (
    PROJECT / "00_Production" / "rough_cut_v2"
    / "FILM10_VISUAL_GAPS_V2.json"
)

OUT = PROJECT / "00_Production" / "canonical_import_v1"
OUT.mkdir(parents=True, exist_ok=True)

VOICE_DURATION = 1607.517

VISUAL_ROOTS = [
    PROJECT / "00_Research" / "visual_research" / "social_downloads",
    PROJECT / "02_Visuals" / "real" / "archive",
]

VIDEO_EXT = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
MEDIA_EXT = VIDEO_EXT | IMAGE_EXT


def load_json(path):
    with path.open("r", encoding="utf-8-sig") as f:
        return json.load(f)


def sha256_file(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def project_asset_id(digest, path):
    try:
        rel = path.resolve().relative_to(PROJECT.resolve())
        identity = rel.as_posix().lower()
    except Exception:
        identity = str(path.resolve()).lower()

    raw = PROJECT_ID + "\0" + digest + "\0" + identity
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def probe(path):
    result = {"width": 0, "height": 0, "duration_sec": 0.0}

    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries",
        "format=duration:stream=codec_type,width,height,duration",
        "-of", "json",
        str(path),
    ]

    try:
        p = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )

        if p.returncode:
            return result

        data = json.loads(p.stdout or "{}")

        for s in data.get("streams") or []:
            if s.get("codec_type") == "video":
                result["width"] = int(s.get("width") or 0)
                result["height"] = int(s.get("height") or 0)

                try:
                    result["duration_sec"] = float(s.get("duration") or 0)
                except Exception:
                    pass
                break

        try:
            d = float((data.get("format") or {}).get("duration") or 0)
            if d > 0:
                result["duration_sec"] = d
        except Exception:
            pass

    except Exception:
        pass

    return result


def visual_group(path):
    text = str(path).lower()

    if "social_downloads" in text:
        return "film10_social_research"

    if "archive" in text:
        return "film10_archive"

    return "film10_corpus"


def infer_visual_need(text, category):
    n = (text or "").lower()

    rules = [
        (("школ", "ученик", "учител", "автобус"),
         "SCHOOL_EVACUATION_BIDUR"),

        (("дрон", "съёмк", "обруш", "ледник"),
         "DRONE_COLLAPSE_LANGTANG_LIRUNG"),

        (("гиронг", "gyirong", "kyirong", "тибет", "границ"),
         "GYIRONG_TIBET_BORDER_DISASTER"),

        (("гэс", "гидроэлект", "электростанц", "туннел"),
         "HYDROPOWER_TUNNEL_RESCUE"),

        (("озер", "плотин", "дамб"),
         "SECONDARY_LAKE_NATURAL_DAM"),

        (("спутник", "landsat", "sentinel", "usgs"),
         "SATELLITE_SCIENCE_EVIDENCE"),

        (("карта", "100 км", "сто килом", "маршрут"),
         "MAP_DISASTER_PROPAGATION_ROUTE"),

        (("река", "кхола", "bhote", "trishuli", "тришули"),
         "RIVER_CHANNEL_DEBRIS_FLOW"),

        (("поток", "наводнен", "сел", "гряз", "разруш"),
         "FLOOD_DEBRIS_DESTRUCTION"),

        (("лангтанг", "лирунг", "склон", "ледник", "скал", "гора"),
         "LANGTANG_LIRUNG_MOUNTAIN_CONTEXT"),
    ]

    for words, need in rules:
        if any(w in n for w in words):
            return need

    mapping = {
        "DRONE_COLLAPSE": "DRONE_COLLAPSE_LANGTANG_LIRUNG",
        "SCHOOL": "SCHOOL_EVACUATION_BIDUR",
        "GYIRONG": "GYIRONG_TIBET_BORDER_DISASTER",
        "HYDROPOWER": "HYDROPOWER_TUNNEL_RESCUE",
        "FLOOD_DESTRUCTION": "FLOOD_DEBRIS_DESTRUCTION",
        "MAP_SCIENCE": "MAP_SATELLITE_SCIENCE",
        "RIVER": "RIVER_CHANNEL_DEBRIS_FLOW",
        "SECONDARY_LAKE": "SECONDARY_LAKE_NATURAL_DAM",
        "GENERAL_CONTEXT": "NEPAL_TIBET_DISASTER_CONTEXT",
    }

    return mapping.get(category, "NEPAL_TIBET_DISASTER_CONTEXT")


def project_count(conn, table):
    exists = conn.execute(
        "SELECT COUNT(*) n FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()["n"]

    if not exists:
        return None

    columns = {
        r["name"]
        for r in conn.execute("PRAGMA table_info({})".format(table))
    }

    if "project_id" not in columns:
        return None

    return conn.execute(
        "SELECT COUNT(*) n FROM {} WHERE project_id=?".format(table),
        (PROJECT_ID,),
    ).fetchone()["n"]


print("=" * 120)
print("ATLAS ZERO — FILM10 CANONICAL IMPORT V1.5")
print("=" * 120)
print("ROOT       :", ROOT)
print("DATABASE   :", DB)
print("PROJECT    :", PROJECT_ID)
print("LIVE API   : 0")
print("PAID CALLS : 0")

timeline_payload = load_json(TIMELINE_PATH)
gaps_payload = load_json(GAPS_PATH)

timeline = timeline_payload["shots"]
gaps = gaps_payload["gaps"]

print()
print("TIMELINE RECORDS :", len(timeline))
print("GAP RECORDS      :", len(gaps))

if len(timeline) != 260:
    raise RuntimeError("Expected 260 timeline records")

if len(gaps) != 222:
    raise RuntimeError("Expected 222 visual gaps")


# ----------------------------------------------------------------------
# Canonical shots
# ----------------------------------------------------------------------

shots = []

for idx, row in enumerate(timeline, 1):

    start = float(row["timeline_start"])
    end = float(row["timeline_end"])

    if end <= start:
        raise RuntimeError(
            "Invalid timing shot {}: {} -> {}".format(idx, start, end)
        )

    narration = str(row.get("narration") or "").strip()
    beat = str(row.get("beat_id") or "").strip()
    category = str(row.get("category") or "GENERAL_CONTEXT").strip().upper()

    shots.append({
        "id": "{}_shot_{:04d}".format(PROJECT_ID, idx),
        "idx": idx,
        "start_sec": start,
        "end_sec": end,
        "duration_sec": end - start,
        "block": beat,
        "story_goal": narration,
        "visual_need": infer_visual_need(narration, category),
        "emotion": "documentary",
        "status": "missing",
        "assigned_asset_id": None,
        "transition": "dissolve",
        "camera_motion": "slow push-in",
        "source_v2_shot_id": row.get("shot_id"),
        "source_v2_category": category,
        "source_v2_selection_reason": row.get("selection_reason"),
    })


start_gate = abs(shots[0]["start_sec"] - 0.0)
end_gate = abs(shots[-1]["end_sec"] - 1607.51746)

continuity_errors = []

for a, b in zip(shots, shots[1:]):
    delta = abs(a["end_sec"] - b["start_sec"])
    if delta > 0.001:
        continuity_errors.append((a["idx"], b["idx"], delta))

visual_duration = shots[-1]["end_sec"] - shots[0]["start_sec"]
voice_delta = abs(visual_duration - VOICE_DURATION)

nonempty = sum(1 for s in shots if s["story_goal"])

print()
print("SHOTS                 :", len(shots))
print("NONEMPTY STORY GOALS  :", nonempty)
print("START                  : {:.6f}".format(shots[0]["start_sec"]))
print("END                    : {:.6f}".format(shots[-1]["end_sec"]))
print("VISUAL DURATION        : {:.6f}".format(visual_duration))
print("VOICE DURATION         : {:.6f}".format(VOICE_DURATION))
print("VOICE DELTA            : {:.6f}".format(voice_delta))
print("CONTINUITY ERRORS      :", len(continuity_errors))

if nonempty != 260:
    raise RuntimeError("Not all 260 shots have narration/story_goal")

if start_gate > 0.001 or end_gate > 0.001:
    raise RuntimeError("Timeline boundary gate failed")

if continuity_errors:
    raise RuntimeError("Timeline continuity gate failed")

if voice_delta > 0.03:
    raise RuntimeError("Voice duration gate failed")


# ----------------------------------------------------------------------
# Build scenes from actual beat_id
# ----------------------------------------------------------------------

scene_groups = []

for shot in shots:
    if not scene_groups or scene_groups[-1]["block"] != shot["block"]:
        scene_groups.append({
            "block": shot["block"],
            "shots": [],
        })

    scene_groups[-1]["shots"].append(shot)


scenes = []

for idx, group in enumerate(scene_groups, 1):
    ss = group["shots"]

    narration = []
    for s in ss:
        if s["story_goal"] not in narration:
            narration.append(s["story_goal"])

    categories = Counter(s["source_v2_category"] for s in ss)
    category = categories.most_common(1)[0][0]

    scenes.append({
        "id": "{}_SC{:03d}".format(PROJECT_ID, idx),
        "idx": idx,
        "block": group["block"],
        "title": category,
        "start_sec": ss[0]["start_sec"],
        "end_sec": ss[-1]["end_sec"],
        "duration_sec": ss[-1]["end_sec"] - ss[0]["start_sec"],
        "target_shots": len(ss),
        "narrative_goal": " ".join(narration),
        "emotional_goal": "documentary",
        "visual_strategy":
            "Strict semantic and event relevance. Missing is preferable to wrong visual.",
        "required_assets": json.dumps(
            {
                "asset_ids": [],
                "cluster_ids": [],
                "use_existing_assets_only": False,
            },
            ensure_ascii=False,
        ),
        "status": "planned",
        "coverage": 0.0,
    })


print("CANONICAL SCENES       :", len(scenes))

if not 50 <= len(scenes) <= 120:
    raise RuntimeError(
        "Unexpected canonical scene count: {}".format(len(scenes))
    )


# ----------------------------------------------------------------------
# Corpus
# ----------------------------------------------------------------------

paths = []

for root in VISUAL_ROOTS:
    for p in root.rglob("*"):
        if p.is_file() and p.suffix.lower() in MEDIA_EXT:
            paths.append(p.resolve())

paths = sorted(set(paths), key=lambda p: str(p).lower())

print("CORPUS MEDIA FILES     :", len(paths))

if len(paths) != 60:
    raise RuntimeError(
        "Expected 60 Film10 corpus assets, found {}".format(len(paths))
    )


assets = []
seen_hash = {}

for p in paths:
    digest = sha256_file(p)
    asset_id = project_asset_id(digest, p)

    duplicate_of = seen_hash.get(digest)

    if digest not in seen_hash:
        seen_hash[digest] = asset_id

    meta = probe(p)

    assets.append({
        "id": asset_id,
        "project_id": PROJECT_ID,
        "path": str(p),
        "filename": p.name,
        "media_type": "video" if p.suffix.lower() in VIDEO_EXT else "image",
        "sha256": digest,
        "category": "film10_candidate",
        "tags": "[]",
        "emotion": "neutral",
        "quality": 0.55,
        "width": meta["width"],
        "height": meta["height"],
        "duration_sec": meta["duration_sec"],
        "duplicate_of": duplicate_of,
        "semantic_class": None,
        "semantic_description": None,
        "visual_group": visual_group(p),
        "perceptual_hash": None,
        "semantic_confidence": 0.0,
        "max_use": 3,
    })


unique_asset_ids = len({a["id"] for a in assets})
duplicate_files = sum(1 for a in assets if a["duplicate_of"])

print("UNIQUE ASSET IDS      :", unique_asset_ids)
print("CONTENT DUPLICATES    :", duplicate_files)

if unique_asset_ids != 60:
    raise RuntimeError(
        "Physical asset ID collision detected: "
        "{} unique IDs for 60 files".format(unique_asset_ids)
    )


# ----------------------------------------------------------------------
# Save import evidence
# ----------------------------------------------------------------------

(OUT / "FILM10_CANONICAL_SHOTS_V1_5.json").write_text(
    json.dumps(shots, ensure_ascii=False, indent=2),
    encoding="utf-8",
)

(OUT / "FILM10_CANONICAL_SCENES_V1_5.json").write_text(
    json.dumps(scenes, ensure_ascii=False, indent=2),
    encoding="utf-8",
)

(OUT / "FILM10_CANONICAL_ASSETS_V1_5.json").write_text(
    json.dumps(assets, ensure_ascii=False, indent=2),
    encoding="utf-8",
)


# ----------------------------------------------------------------------
# DB
# ----------------------------------------------------------------------

conn = sqlite3.connect(str(DB))
conn.row_factory = sqlite3.Row

try:

    existing = {
        "projects": conn.execute(
            "SELECT COUNT(*) n FROM projects WHERE id=?",
            (PROJECT_ID,),
        ).fetchone()["n"],

        "shots": conn.execute(
            "SELECT COUNT(*) n FROM shots WHERE project_id=?",
            (PROJECT_ID,),
        ).fetchone()["n"],

        "story_scenes": conn.execute(
            "SELECT COUNT(*) n FROM story_scenes WHERE project_id=?",
            (PROJECT_ID,),
        ).fetchone()["n"],

        "assets": conn.execute(
            "SELECT COUNT(*) n FROM assets WHERE project_id=?",
            (PROJECT_ID,),
        ).fetchone()["n"],
    }

    print()
    print("=" * 120)
    print("PRE-IMPORT STATE")
    print("=" * 120)

    for k, v in existing.items():
        print("{:<20}: {}".format(k, v))

    empty = all(v == 0 for v in existing.values())

    complete = (
        existing["projects"] == 1
        and existing["shots"] == 260
        and existing["story_scenes"] == len(scenes)
        and existing["assets"] == 60
    )

    if not empty and not complete:
        raise RuntimeError(
            "PARTIAL CANONICAL STATE DETECTED. "
            "No mutation performed: {}".format(existing)
        )

    if empty:

        conn.execute("BEGIN IMMEDIATE")

        try:
            conn.execute(
                """
                INSERT INTO projects(
                    id,title,status,duration_sec
                )
                VALUES(?,?,?,?)
                """,
                (
                    PROJECT_ID,
                    "Film 10 — Nepal/Tibet Aftershock",
                    "active",
                    VOICE_DURATION,
                ),
            )

            conn.executemany(
                """
                INSERT INTO story_scenes(
                    id,project_id,idx,block,title,
                    start_sec,end_sec,duration_sec,target_shots,
                    narrative_goal,emotional_goal,visual_strategy,
                    required_assets,status,coverage
                )
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                [
                    (
                        s["id"], PROJECT_ID, s["idx"], s["block"], s["title"],
                        s["start_sec"], s["end_sec"], s["duration_sec"],
                        s["target_shots"], s["narrative_goal"],
                        s["emotional_goal"], s["visual_strategy"],
                        s["required_assets"], s["status"], s["coverage"],
                    )
                    for s in scenes
                ],
            )

            conn.executemany(
                """
                INSERT INTO shots(
                    id,project_id,idx,start_sec,end_sec,block,
                    story_goal,visual_need,emotion,status,
                    assigned_asset_id,transition,camera_motion
                )
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                [
                    (
                        s["id"], PROJECT_ID, s["idx"],
                        s["start_sec"], s["end_sec"], s["block"],
                        s["story_goal"], s["visual_need"], s["emotion"],
                        "missing", None, s["transition"], s["camera_motion"],
                    )
                    for s in shots
                ],
            )

            conn.executemany(
                """
                INSERT INTO assets(
                    id,project_id,path,filename,media_type,sha256,
                    category,tags,emotion,quality,width,height,duration_sec,
                    duplicate_of,semantic_class,semantic_description,
                    visual_group,perceptual_hash,semantic_confidence,max_use
                )
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                [
                    (
                        a["id"], PROJECT_ID, a["path"], a["filename"],
                        a["media_type"], a["sha256"], a["category"],
                        a["tags"], a["emotion"], a["quality"],
                        a["width"], a["height"], a["duration_sec"],
                        a["duplicate_of"], a["semantic_class"],
                        a["semantic_description"], a["visual_group"],
                        a["perceptual_hash"], a["semantic_confidence"],
                        a["max_use"],
                    )
                    for a in assets
                ],
            )

            conn.commit()
            print()
            print("DATABASE TRANSACTION   : COMMITTED")

        except Exception:
            conn.rollback()
            raise

    else:
        print()
        print("CANONICAL STATE ALREADY COMPLETE — MUTATION SKIPPED")


    # ------------------------------------------------------------------
    # Verification
    # ------------------------------------------------------------------

    db_projects = conn.execute(
        "SELECT COUNT(*) n FROM projects WHERE id=?",
        (PROJECT_ID,),
    ).fetchone()["n"]

    db_shots = conn.execute(
        "SELECT COUNT(*) n FROM shots WHERE project_id=?",
        (PROJECT_ID,),
    ).fetchone()["n"]

    db_scenes = conn.execute(
        "SELECT COUNT(*) n FROM story_scenes WHERE project_id=?",
        (PROJECT_ID,),
    ).fetchone()["n"]

    db_assets = conn.execute(
        "SELECT COUNT(*) n FROM assets WHERE project_id=?",
        (PROJECT_ID,),
    ).fetchone()["n"]

    assigned = conn.execute(
        """
        SELECT COUNT(*) n
        FROM shots
        WHERE project_id=?
          AND assigned_asset_id IS NOT NULL
        """,
        (PROJECT_ID,),
    ).fetchone()["n"]

    missing = conn.execute(
        """
        SELECT COUNT(*) n
        FROM shots
        WHERE project_id=?
          AND status='missing'
        """,
        (PROJECT_ID,),
    ).fetchone()["n"]

    blank_goals = conn.execute(
        """
        SELECT COUNT(*) n
        FROM shots
        WHERE project_id=?
          AND (story_goal IS NULL OR TRIM(story_goal)='')
        """,
        (PROJECT_ID,),
    ).fetchone()["n"]

    learning = {
        t: project_count(conn, t)
        for t in (
            "learning_observations",
            "learning_profiles",
            "director_learning_advisories",
            "director_learning_cycles",
        )
    }

    gates = {
        "project_registered": db_projects == 1,
        "shots_260": db_shots == 260,
        "scenes_sane": 50 <= db_scenes <= 120,
        "assets_60": db_assets == 60,
        "zero_fake_assignments": assigned == 0,
        "all_shots_missing": missing == 260,
        "story_goals_present": blank_goals == 0,
        "timeline_continuous": not continuity_errors,
        "duration_matches_voice": voice_delta <= 0.03,
        "learning_observations_preserved":
            learning["learning_observations"] is None
            or learning["learning_observations"] >= 5,
        "learning_profiles_preserved":
            learning["learning_profiles"] is None
            or learning["learning_profiles"] >= 5,
        "advisory_preserved":
            learning["director_learning_advisories"] is None
            or learning["director_learning_advisories"] >= 1,
        "learning_cycle_preserved":
            learning["director_learning_cycles"] is None
            or learning["director_learning_cycles"] >= 1,
    }

    print()
    print("=" * 120)
    print("CANONICAL VERIFICATION")
    print("=" * 120)

    print("PROJECTS               :", db_projects)
    print("SHOTS                  :", db_shots)
    print("SCENES                 :", db_scenes)
    print("ASSETS                 :", db_assets)
    print("ASSIGNED               :", assigned)
    print("MISSING                :", missing)
    print("BLANK STORY GOALS      :", blank_goals)

    print()
    print("LEARNING:")
    for k, v in learning.items():
        print("  {:<31}: {}".format(k, v))

    print()
    print("=" * 120)
    print("GATES")
    print("=" * 120)

    failed = []

    for name, ok in gates.items():
        state = "PASS" if ok else "FAIL"
        print("{:<42}: {}".format(name, state))

        if not ok:
            failed.append(name)

    report = {
        "schema": "atlas_zero.film10_canonical_import.v1.5",
        "project_id": PROJECT_ID,
        "timeline_records": len(timeline),
        "visual_gap_records": len(gaps),
        "voice_duration_sec": VOICE_DURATION,
        "timeline_end_sec": shots[-1]["end_sec"],
        "visual_duration_sec": visual_duration,
        "voice_delta_sec": voice_delta,
        "shots": db_shots,
        "scenes": db_scenes,
        "assets": db_assets,
        "assigned": assigned,
        "missing": missing,
        "learning": learning,
        "gates": gates,
        "old_v2_assignments_imported": False,
        "next_stage": "VisualSemanticAnalyzerRC2",
    }

    (OUT / "FILM10_CANONICAL_IMPORT_REPORT_V1_5.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    if failed:
        raise RuntimeError(
            "CANONICAL IMPORT FAILED GATES: " + ", ".join(failed)
        )

finally:
    conn.close()


print()
print("=" * 120)
print("FILM10 CANONICAL IMPORT V1.5: PASS")
print("=" * 120)
print("260 canonical shots registered.")
print("60 Film10 assets registered.")
print("222 old V2 gaps NOT converted into assignments.")
print("0 fallback assignments imported.")
print("Next: VisualSemanticAnalyzerRC2 — NO RENDER.")
