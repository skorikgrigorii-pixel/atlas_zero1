from __future__ import annotations

import ast
import importlib
import inspect
import json
import os
import re
import sys
import zipfile
from datetime import datetime
from pathlib import Path

ROOT = Path.cwd().resolve()
sys.path.insert(0, str(ROOT / "src"))

PROJECT = "db_cooper"
CORE = ROOT / "src" / "az_enterprise" / "core"
EXP = ROOT / "workspace" / "exports" / PROJECT
RC2 = EXP / "rc2"
OUT = ROOT / "audit_output"
OUT.mkdir(exist_ok=True)

STAMP = "20260824"
JS = OUT / f"RC2_E2E_READINESS_{PROJECT}_{STAMP}.json"
MD = OUT / f"RC2_E2E_READINESS_{PROJECT}_{STAMP}.md"
ZIP = OUT / f"RC2_E2E_READINESS_{PROJECT}_{STAMP}.zip"

# No API calls are made by this script.
# No production module run()/render()/publish() method is invoked.

MODULES = {
    "Director": [
        "az_enterprise.core.director_core_rc2",
        "az_enterprise.core.production_director",
        "az_enterprise.core.control_layer_rc2",
    ],
    "Story": [
        "az_enterprise.core.visual_semantic_analyzer_rc2",
        "az_enterprise.core.event_discovery_engine_rc2",
        "az_enterprise.core.story_strategy_engine_rc2",
        "az_enterprise.core.story_engine",
    ],
    "Voice": [
        "az_enterprise.core.voice_production_engine_rc2",
    ],
    "Assets": [
        "az_enterprise.core.asset_engine_rc2",
        "az_enterprise.core.assignment_engine_rc2",
        "az_enterprise.core.asset_intelligence",
    ],
    "Timeline": [
        "az_enterprise.core.timeline_engine_rc2",
    ],
    "Render": [
        "az_enterprise.core.render_engine_rc2",
        "az_enterprise.core.visual_renderer_rc2",
    ],
    "Quality": [
        "az_enterprise.core.quality_gate_rc2",
    ],
    "Promotion": [
        "az_enterprise.core.promotion_candidate_analyzer_rc1",
        "az_enterprise.core.promotion_narration_alignment_rc1",
        "az_enterprise.core.promotion_factory_rc1",
        "az_enterprise.core.promotion_render_runtime_rc1",
    ],
    "Instagram": [
        "az_enterprise.core.instagram_publication_runtime_rc1",
    ],
    "TikTok": [
        "az_enterprise.core.tiktok_connector_rc1",
        "az_enterprise.core.tiktok_oauth_rc1",
    ],
    "YouTube": [
        "az_enterprise.core.youtube_connector_rc1",
        "az_enterprise.core.youtube_oauth_rc1",
    ],
    "Learning": [
        "az_enterprise.core.director_learning_adapter_rc1",
    ],
}

ENV_GROUPS = {
    "OpenAI": ["OPENAI_API_KEY"],
    "ElevenLabs": ["ELEVENLABS_API_KEY", "ELEVENLABS_VOICE_ID"],
    "Leonardo": ["LEONARDO_API_KEY"],
    "Instagram": ["INSTAGRAM_ACCESS_TOKEN", "INSTAGRAM_USER_ID"],
    "TikTok": [
        "TIKTOK_CLIENT_KEY",
        "TIKTOK_CLIENT_SECRET",
        "TIKTOK_REDIRECT_URI",
        "TIKTOK_REFRESH_TOKEN",
    ],
    "YouTube": [
        "YOUTUBE_API_KEY",
        "YOUTUBE_CLIENT_ID",
        "YOUTUBE_CLIENT_SECRET",
        "YOUTUBE_REFRESH_TOKEN",
    ],
}

def load_env_names():
    env = ROOT / ".env"
    names = set()
    if not env.exists():
        return names
    for line in env.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        names.add(line.split("=", 1)[0].strip())
    return names

def safe_import(name):
    try:
        mod = importlib.import_module(name)
        public = []
        signatures = {}
        for n, obj in vars(mod).items():
            if n.startswith("_"):
                continue
            if inspect.isclass(obj) and getattr(obj, "__module__", None) == name:
                public.append(n)
                try:
                    signatures[n] = str(inspect.signature(obj))
                except Exception:
                    pass
        return {
            "ok": True,
            "classes": sorted(public),
            "signatures": signatures,
            "error": None,
        }
    except Exception as e:
        return {
            "ok": False,
            "classes": [],
            "signatures": {},
            "error": f"{type(e).__name__}: {e}",
        }

def newest_files(base, limit=20):
    if not base.exists():
        return []
    files = [p for p in base.rglob("*") if p.is_file()]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return [
        {
            "path": str(p.relative_to(ROOT)).replace("\\", "/"),
            "size_mb": round(p.stat().st_size / 1024 / 1024, 3),
            "mtime": datetime.fromtimestamp(p.stat().st_mtime).isoformat(),
        }
        for p in files[:limit]
    ]

def find_files(patterns):
    found = []
    if not EXP.exists():
        return found
    for p in EXP.rglob("*"):
        if not p.is_file():
            continue
        low = p.name.lower()
        if any(re.search(ptn, low, re.I) for ptn in patterns):
            found.append(p)
    return sorted(found)

def describe(paths):
    return [
        {
            "path": str(p.relative_to(ROOT)).replace("\\", "/"),
            "size_mb": round(p.stat().st_size / 1024 / 1024, 3),
            "mtime": datetime.fromtimestamp(p.stat().st_mtime).isoformat(),
        }
        for p in paths
    ]

# Canonical artifact recognition.
ARTIFACTS = {
    "Research / source material": [
        r"research", r"source", r"fact", r"evidence"
    ],
    "Production script / narrative": [
        r"production_script", r"script", r"narrative", r"story"
    ],
    "Voice / narration audio": [
        r"voice.*\.(wav|mp3|m4a)$",
        r"narration.*\.(wav|mp3|m4a)$",
        r"master.*audio",
    ],
    "Visual / asset inventory": [
        r"asset.*\.json$", r"visual.*\.json$", r"semantic.*\.json$"
    ],
    "Timeline": [
        r"timeline.*\.json$"
    ],
    "Render": [
        r"\.mp4$", r"render.*\.json$"
    ],
    "Quality": [
        r"quality", r"qc", r"validation", r"probe"
    ],
    "Packaging": [
        r"thumbnail", r"packag", r"title"
    ],
    "Promotion": [
        r"promotion", r"promo", r"reel", r"short"
    ],
    "Publication": [
        r"publication", r"published", r"instagram", r"youtube", r"tiktok"
    ],
    "Analytics / Learning": [
        r"analytics", r"learning", r"advisory", r"feedback"
    ],
}

imports = {}
for domain, names in MODULES.items():
    imports[domain] = {}
    for name in names:
        imports[domain][name] = safe_import(name)

env_names = load_env_names()
env_status = {}
for group, keys in ENV_GROUPS.items():
    env_status[group] = {
        "required_or_known_keys": keys,
        "present": [k for k in keys if k in env_names],
        "missing": [k for k in keys if k not in env_names],
    }

artifact_status = {}
for stage, patterns in ARTIFACTS.items():
    matches = find_files(patterns)
    artifact_status[stage] = {
        "found": bool(matches),
        "count": len(matches),
        "examples": describe(matches[:15]),
    }

# Strong final-render recognition.
final_videos = []
if RC2.exists():
    for p in RC2.rglob("*.mp4"):
        n = p.name.lower()
        if any(x in n for x in ["final", "master", "render", "db_cooper"]):
            final_videos.append(p)

# Source inspection: discover dry-run/read-only support in orchestration files.
orchestration_sources = [
    CORE / "director_core_rc2.py",
    CORE / "production_director.py",
    CORE / "control_layer_rc2.py",
    CORE / "rc2_cli.py",
]
dry_run_evidence = []
for p in orchestration_sources:
    if not p.exists():
        continue
    text = p.read_text(encoding="utf-8-sig", errors="replace")
    for token in ["dry_run", "dry-run", "read_only", "readonly", "plan(", "evaluate("]:
        if token.lower() in text.lower():
            dry_run_evidence.append({
                "file": str(p.relative_to(ROOT)).replace("\\", "/"),
                "token": token,
            })

# Determine readiness without executing production actions.
stage_order = [
    "Research / source material",
    "Production script / narrative",
    "Voice / narration audio",
    "Visual / asset inventory",
    "Timeline",
    "Render",
    "Quality",
    "Packaging",
    "Promotion",
    "Publication",
    "Analytics / Learning",
]

readiness = []
for stage in stage_order:
    s = artifact_status[stage]
    readiness.append({
        "stage": stage,
        "artifact_evidence": s["found"],
        "artifact_count": s["count"],
    })

# Integration interpretation.
integration_readiness = {
    "Instagram": {
        "module_importable": all(v["ok"] for v in imports["Instagram"].values()),
        "credentials_configured":
            len(env_status["Instagram"]["missing"]) == 0,
    },
    "TikTok": {
        "module_importable": all(v["ok"] for v in imports["TikTok"].values()),
        "credentials_configured":
            len(env_status["TikTok"]["missing"]) == 0,
    },
    "YouTube": {
        "module_importable": all(v["ok"] for v in imports["YouTube"].values()),
        "credentials_configured":
            len(env_status["YouTube"]["missing"]) == 0,
    },
}

# Classify blockers conservatively.
blockers = []

for domain, mods in imports.items():
    failed = [m for m, x in mods.items() if not x["ok"]]
    if failed:
        blockers.append({
            "type": "MODULE_IMPORT_FAILURE",
            "domain": domain,
            "details": failed,
        })

if not final_videos:
    blockers.append({
        "type": "NO_FINAL_RENDER_DETECTED",
        "domain": "Render",
        "details": [],
    })

for platform, st in integration_readiness.items():
    if not st["module_importable"]:
        blockers.append({
            "type": "PLATFORM_CODE_NOT_IMPORTABLE",
            "domain": platform,
            "details": [],
        })
    elif not st["credentials_configured"]:
        blockers.append({
            "type": "PLATFORM_CREDENTIALS_INCOMPLETE",
            "domain": platform,
            "details": env_status[platform]["missing"],
        })

# OpenAI intentionally not treated as core blocker.
openai_active = len(env_status["OpenAI"]["missing"]) == 0

data = {
    "generated_at": datetime.now().isoformat(),
    "mode": "READ_ONLY_E2E_READINESS_SIMULATION",
    "project": PROJECT,
    "root": str(ROOT),
    "project_export_exists": EXP.exists(),
    "rc2_export_exists": RC2.exists(),
    "module_imports": imports,
    "environment": env_status,
    "artifacts": artifact_status,
    "final_videos": describe(final_videos),
    "dry_run_evidence": dry_run_evidence,
    "stage_readiness": readiness,
    "integration_readiness": integration_readiness,
    "openai_active": openai_active,
    "blockers": blockers,
    "newest_project_files": newest_files(EXP, 30),
}

JS.write_text(
    json.dumps(data, indent=2, ensure_ascii=False),
    encoding="utf-8"
)

L = []
a = L.append

a("# ATLAS ZERO RC2 — E2E READINESS SIMULATION")
a("")
a(f"Generated: `{data['generated_at']}`")
a(f"Project: **{PROJECT}**")
a("Mode: **READ ONLY — no API calls / no render / no publication**")
a("")

a("## Executive result")
a("")
a(f"- Project export detected: **{EXP.exists()}**")
a(f"- RC2 export detected: **{RC2.exists()}**")
a(f"- Final video candidates: **{len(final_videos)}**")
a(f"- Detected blockers: **{len(blockers)}**")
a("")

a("## Canonical module importability")
a("")
for domain, mods in imports.items():
    ok = sum(1 for v in mods.values() if v["ok"])
    a(f"### {domain}: {ok}/{len(mods)} importable")
    for name, res in mods.items():
        if res["ok"]:
            classes = ", ".join(res["classes"]) or "no local classes"
            a(f"- PASS `{name}` — {classes}")
        else:
            a(f"- FAIL `{name}` — {res['error']}")
    a("")

a("## Production artifact chain")
a("")
for row in readiness:
    mark = "PASS" if row["artifact_evidence"] else "MISSING/UNCONFIRMED"
    a(f"- **{mark}** — {row['stage']} — artifacts: {row['artifact_count']}")
a("")

a("## Platform integrations")
a("")
for platform, st in integration_readiness.items():
    a(f"### {platform}")
    a(f"- Code importable: **{st['module_importable']}**")
    a(f"- Known credential set complete: **{st['credentials_configured']}**")
    if env_status[platform]["missing"]:
        a("- Missing environment keys: " + ", ".join(
            f"`{x}`" for x in env_status[platform]["missing"]
        ))
    a("")

a("## Paid/optional providers")
a("")
a(f"- OpenAI configured: **{openai_active}**")
a("- OpenAI absence is not classified as a core RC2 code failure in this audit.")
a("")

a("## Final render evidence")
a("")
for f in describe(final_videos):
    a(f"- `{f['path']}` — {f['size_mb']} MB")
if not final_videos:
    a("- **None detected**")
a("")

a("## Dry-run/read-only orchestration evidence")
a("")
for x in dry_run_evidence:
    a(f"- `{x['file']}` contains `{x['token']}`")
if not dry_run_evidence:
    a("- No explicit dry-run marker detected by static scan.")
a("")

a("## Candidate E2E blockers")
a("")
if blockers:
    for b in blockers:
        a(f"- **{b['type']}** — {b['domain']} — {b['details']}")
else:
    a("- **NONE detected by read-only readiness simulation**")
a("")

a("## Newest project artifacts")
a("")
for f in data["newest_project_files"]:
    a(f"- `{f['path']}` — {f['mtime']}")

MD.write_text("\n".join(L), encoding="utf-8")

with zipfile.ZipFile(ZIP, "w", zipfile.ZIP_DEFLATED) as z:
    z.write(MD, MD.name)
    z.write(JS, JS.name)

print()
print("============================================================")
print("ATLAS ZERO RC2 — READ-ONLY E2E READINESS COMPLETE")
print("============================================================")
print(f"Project             : {PROJECT}")
print(f"RC2 export          : {RC2.exists()}")
print(f"Final video outputs : {len(final_videos)}")
print(f"E2E blockers        : {len(blockers)}")
print(f"Report              : {MD}")
print(f"Package             : {ZIP}")
print("============================================================")
print()

if blockers:
    print("BLOCKERS:")
    for b in blockers:
        print(f"- {b['type']} | {b['domain']} | {b['details']}")
else:
    print("NO READ-ONLY E2E BLOCKERS DETECTED")
