from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
import zipfile
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path.cwd().resolve()
CORE = ROOT / "src" / "az_enterprise" / "core"
SRC = ROOT / "src" / "az_enterprise"
TESTS = ROOT / "tests"
TOOLS = ROOT / "tools"
WORKSPACE = ROOT / "workspace"
OUT = ROOT / "audit_output"
OUT.mkdir(parents=True, exist_ok=True)

STAMP = "20260824"
MD = OUT / f"ATLAS_ZERO_FULL_OS_AUDIT_{STAMP}.md"
JS = OUT / f"ATLAS_ZERO_FULL_OS_AUDIT_{STAMP}.json"
TEST_LOG = OUT / f"ATLAS_ZERO_TESTS_{STAMP}.txt"
COLLECT_LOG = OUT / f"ATLAS_ZERO_TEST_COLLECTION_{STAMP}.txt"
ZIP = OUT / f"ATLAS_ZERO_FULL_OS_AUDIT_{STAMP}.zip"

EXCLUDE_DIRS = {
    "__pycache__", ".git", ".venv", "venv", "env", "node_modules",
    "atlas_zero_rc2_1_patch", "atlas_zero_rc2_2_patch",
    "atlas_zero_rc2_stage2_patch", "atlas_zero_rc2_final_audit",
    "atlas_zero_rc2_finalization", "atlas_zero_rc2_production_audit",
    "audit_rc2_production", "phase5_payload",
    "atlas_zero_phase5_native_camera_motion",
    "atlas_zero_phase6_native_transition_engine",
    "atlas_zero_phase7_native_audio_composer",
    "atlas_zero_phase8_rc2_control_layer",
    "atlas_zero_phase9_production_cleanup",
}

DOMAINS = {
    "Director / Governance": [
        "director", "supervisor", "control_layer", "governance",
        "production_state", "project_config", "registry", "autopilot",
        "execution_graph", "operator_console"
    ],
    "Research / Story / Narrative": [
        "research", "event_discovery", "story", "narrative",
        "production_script", "editorial", "semantic_context"
    ],
    "Voice / Audio": [
        "voice", "elevenlabs", "audio", "ducking", "loudness", "mux", "sound"
    ],
    "Visual / Archive / Assets": [
        "visual", "asset", "archive", "image", "media", "generated_asset",
        "assignment", "camera_motion", "transition"
    ],
    "Timeline / Render / Movie": [
        "timeline", "render", "movie_runtime", "assembly", "ffmpeg"
    ],
    "Quality / Validation": [
        "quality", "preflight", "acceptance", "release_gate",
        "test_center", "validation"
    ],
    "Packaging / Promotion": [
        "packaging", "thumbnail", "title", "promotion", "candidate",
        "narration_alignment"
    ],
    "Publication / Integrations": [
        "instagram", "tiktok", "youtube", "publication", "oauth",
        "connector", "api"
    ],
    "Analytics / Learning": [
        "analytics", "learning", "knowledge", "recommendation", "feedback"
    ],
}

INTEGRATION_PATTERNS = {
    "OpenAI": [r"OPENAI_", r"openai"],
    "ElevenLabs": [r"ELEVENLABS_", r"elevenlabs"],
    "Instagram / Meta": [r"INSTAGRAM_", r"META_", r"instagram"],
    "TikTok": [r"TIKTOK_", r"tiktok"],
    "YouTube / Google": [r"YOUTUBE_", r"GOOGLE_", r"youtube"],
    "Leonardo": [r"LEONARDO_", r"leonardo"],
    "FFmpeg": [r"ffmpeg", r"ffprobe"],
}

def run(cmd, timeout=120):
    try:
        p = subprocess.run(
            cmd,
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=timeout,
            shell=isinstance(cmd, str),
            encoding="utf-8",
            errors="replace",
        )
        return {
            "returncode": p.returncode,
            "stdout": p.stdout,
            "stderr": p.stderr,
        }
    except Exception as e:
        return {"returncode": -999, "stdout": "", "stderr": repr(e)}

def rel(p: Path):
    try:
        return str(p.relative_to(ROOT)).replace("\\", "/")
    except Exception:
        return str(p)

def canonical_py_files():
    roots = [SRC, TESTS, TOOLS]
    files = []
    for base in roots:
        if not base.exists():
            continue
        for p in base.rglob("*.py"):
            if any(part in EXCLUDE_DIRS for part in p.parts):
                continue
            if p.name.endswith(".backup.py"):
                continue
            files.append(p)
    return sorted(set(files))

def core_py_files():
    if not CORE.exists():
        return []
    return sorted(
        p for p in CORE.rglob("*.py")
        if not any(part in EXCLUDE_DIRS for part in p.parts)
        and not p.name.endswith(".backup.py")
    )

def parse_python(p: Path):
    raw = p.read_bytes()
    text = raw.decode("utf-8-sig", errors="replace")
    info = {
        "file": rel(p),
        "lines": len(text.splitlines()),
        "bytes": len(raw),
        "classes": [],
        "functions": [],
        "imports": [],
        "syntax_error": None,
    }
    try:
        tree = ast.parse(text, filename=str(p))
    except Exception as e:
        info["syntax_error"] = str(e)
        return info

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            info["classes"].append(node.name)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            info["functions"].append(node.name)
        elif isinstance(node, ast.Import):
            info["imports"].extend(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            info["imports"].append(module)
    return info

def file_text(p: Path):
    try:
        return p.read_text(encoding="utf-8-sig", errors="replace")
    except Exception:
        return ""

def classify_domain(filename: str):
    low = filename.lower()
    scores = {}
    for domain, keys in DOMAINS.items():
        scores[domain] = sum(1 for k in keys if k in low)
    best = max(scores, key=scores.get)
    return best if scores[best] else "Other"

def env_keys():
    result = []
    p = ROOT / ".env"
    if not p.exists():
        return result
    for line in file_text(p).splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        key = s.split("=", 1)[0].strip()
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            result.append(key)
    return sorted(set(result))

def workspace_projects():
    exports = WORKSPACE / "exports"
    if not exports.exists():
        return []
    result = []
    for project in sorted(p for p in exports.iterdir() if p.is_dir()):
        files = [p for p in project.rglob("*") if p.is_file()]
        exts = Counter(p.suffix.lower() for p in files)
        newest = sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)[:15]
        videos = []
        for p in files:
            if p.suffix.lower() in {".mp4", ".mov", ".mkv", ".webm"}:
                videos.append({
                    "path": rel(p),
                    "size_mb": round(p.stat().st_size / 1024 / 1024, 2),
                    "mtime": datetime.fromtimestamp(p.stat().st_mtime).isoformat(),
                })
        result.append({
            "project": project.name,
            "files": len(files),
            "extensions": dict(exts),
            "videos": sorted(videos, key=lambda x: x["mtime"], reverse=True)[:20],
            "newest_files": [
                {
                    "path": rel(p),
                    "size": p.stat().st_size,
                    "mtime": datetime.fromtimestamp(p.stat().st_mtime).isoformat(),
                }
                for p in newest
            ],
        })
    return result

def scan_integration_evidence(files):
    evidence = {k: {"files": [], "env_keys": []} for k in INTEGRATION_PATTERNS}
    keys = env_keys()
    for name, pats in INTEGRATION_PATTERNS.items():
        for key in keys:
            if any(re.search(p, key, re.I) for p in pats):
                evidence[name]["env_keys"].append(key)

    for p in files:
        txt = file_text(p)
        hay = p.name + "\n" + txt
        for name, pats in INTEGRATION_PATTERNS.items():
            if any(re.search(pat, hay, re.I) for pat in pats):
                evidence[name]["files"].append(rel(p))

    for name in evidence:
        evidence[name]["files"] = sorted(set(evidence[name]["files"]))
        evidence[name]["env_keys"] = sorted(set(evidence[name]["env_keys"]))
    return evidence

def git_info():
    return {
        "branch": run(["git", "branch", "--show-current"]),
        "status": run(["git", "status", "--short"]),
        "log": run(["git", "log", "-20", "--oneline", "--decorate"]),
        "remote": run(["git", "remote", "-v"]),
    }

all_py = canonical_py_files()
core_files = core_py_files()
parsed = [parse_python(p) for p in all_py]
core_parsed = [x for x in parsed if x["file"].startswith("src/az_enterprise/core/")]

syntax_errors = [x for x in parsed if x["syntax_error"]]

module_names = {}
for p in core_files:
    module_names[p.stem] = rel(p)

incoming = defaultdict(set)
outgoing = defaultdict(set)

for item in core_parsed:
    source = Path(item["file"]).stem
    for imp in item["imports"]:
        target = imp.split(".")[-1]
        if target in module_names and target != source:
            outgoing[source].add(target)
            incoming[target].add(source)

orphans = []
for mod, path in sorted(module_names.items()):
    if mod == "__init__":
        continue
    if not incoming.get(mod):
        orphans.append(path)

domain_map = defaultdict(list)
for p in core_files:
    domain_map[classify_domain(p.name)].append(rel(p))

integration = scan_integration_evidence(all_py)

# Entry-point/runtime evidence
entry_patterns = [
    "DirectorCoreRC2", "ProductionDirector", "RC2ControlLayer",
    "StoryEngine", "VoiceProductionEngineRC2", "TimelineEngineRC2",
    "RenderEngineRC2", "QualityGateRC2",
    "PromotionFactoryRC1", "PromotionCandidateAnalyzerRC1",
    "InstagramPublicationRuntimeRC1", "TikTok",
    "DirectorLearningAdapterRC1",
]
runtime_evidence = {}
for pat in entry_patterns:
    hits = []
    for p in core_files:
        txt = file_text(p)
        if pat.lower() in txt.lower() or pat.lower() in p.name.lower():
            hits.append(rel(p))
    runtime_evidence[pat] = sorted(set(hits))

# Test collection + execution
collect = run([sys.executable, "-m", "pytest", "--collect-only", "-q"], timeout=300)
COLLECT_LOG.write_text(
    collect["stdout"] + "\n--- STDERR ---\n" + collect["stderr"],
    encoding="utf-8",
)

tests = run([sys.executable, "-m", "pytest", "-q"], timeout=900)
TEST_LOG.write_text(
    tests["stdout"] + "\n--- STDERR ---\n" + tests["stderr"],
    encoding="utf-8",
)

data = {
    "generated_at": datetime.now().isoformat(),
    "root": str(ROOT),
    "python": sys.version,
    "git": git_info(),
    "inventory": {
        "canonical_python_files": len(all_py),
        "core_python_files": len(core_files),
        "python_lines": sum(x["lines"] for x in parsed),
        "core_python_lines": sum(x["lines"] for x in core_parsed),
        "syntax_errors": syntax_errors,
    },
    "domains": dict(domain_map),
    "modules": core_parsed,
    "dependency_graph": {
        "incoming": {k: sorted(v) for k, v in incoming.items()},
        "outgoing": {k: sorted(v) for k, v in outgoing.items()},
        "possible_orphans": orphans,
    },
    "runtime_evidence": runtime_evidence,
    "integrations": integration,
    "env_keys_redacted": env_keys(),
    "tests": {
        "collect_returncode": collect["returncode"],
        "run_returncode": tests["returncode"],
        "collection_log": rel(COLLECT_LOG),
        "test_log": rel(TEST_LOG),
    },
    "workspace_projects": workspace_projects(),
}

JS.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

lines = []
a = lines.append

a("# ATLAS ZERO — FULL OS AUDIT")
a("")
a(f"Generated: `{data['generated_at']}`")
a(f"Root: `{ROOT}`")
a(f"Python: `{sys.version.splitlines()[0]}`")
a("")

a("## 1. Git state")
a("")
a(f"Branch: `{data['git']['branch']['stdout'].strip()}`")
a("")
a("### Working tree")
a("```text")
a(data["git"]["status"]["stdout"].rstrip() or "CLEAN")
a("```")
a("")
a("### Recent commits")
a("```text")
a(data["git"]["log"]["stdout"].rstrip())
a("```")
a("")

a("## 2. Canonical runtime inventory")
a("")
a(f"- Canonical Python files: **{data['inventory']['canonical_python_files']}**")
a(f"- Core Python modules: **{data['inventory']['core_python_files']}**")
a(f"- Canonical Python lines: **{data['inventory']['python_lines']}**")
a(f"- Core Python lines: **{data['inventory']['core_python_lines']}**")
a(f"- Syntax errors: **{len(syntax_errors)}**")
a("")

if syntax_errors:
    a("### Syntax errors")
    for x in syntax_errors:
        a(f"- `{x['file']}` — {x['syntax_error']}")
    a("")

a("## 3. Functional domains")
a("")
for domain in DOMAINS:
    files = domain_map.get(domain, [])
    a(f"### {domain} — {len(files)} modules")
    for f in files:
        a(f"- `{f}`")
    a("")
if domain_map.get("Other"):
    a(f"### Other — {len(domain_map['Other'])} modules")
    for f in domain_map["Other"]:
        a(f"- `{f}`")
    a("")

a("## 4. Runtime dependency graph")
a("")
for mod in sorted(module_names):
    if mod == "__init__":
        continue
    outs = sorted(outgoing.get(mod, []))
    ins = sorted(incoming.get(mod, []))
    a(f"### `{mod}`")
    a(f"- Imported by: {', '.join(f'`{x}`' for x in ins) if ins else '**NONE DETECTED**'}")
    a(f"- Imports canonical core: {', '.join(f'`{x}`' for x in outs) if outs else 'none'}")
    a("")

a("## 5. Possible orphan runtime modules")
a("")
a("> Static-analysis warning only. A module may be invoked dynamically or from CLI/tools.")
a("")
for f in orphans:
    a(f"- `{f}`")
a("")

a("## 6. Key runtime components")
a("")
for key, hits in runtime_evidence.items():
    a(f"### {key}")
    for h in hits:
        a(f"- `{h}`")
    if not hits:
        a("- **NOT FOUND**")
    a("")

a("## 7. External integrations")
a("")
for name, ev in integration.items():
    a(f"### {name}")
    a(f"- Environment keys found: {', '.join(f'`{x}`' for x in ev['env_keys']) if ev['env_keys'] else 'none'}")
    a(f"- Code evidence: **{len(ev['files'])} files**")
    for f in ev["files"][:40]:
        a(f"  - `{f}`")
    if len(ev["files"]) > 40:
        a(f"  - ... +{len(ev['files'])-40} more")
    a("")

a("## 8. Environment configuration")
a("")
a("Only variable NAMES are shown. Values/secrets were not collected.")
a("")
for k in data["env_keys_redacted"]:
    a(f"- `{k}`")
a("")

a("## 9. Tests")
a("")
a(f"- pytest collection return code: **{collect['returncode']}**")
a(f"- pytest run return code: **{tests['returncode']}**")
a(f"- Collection log: `{rel(COLLECT_LOG)}`")
a(f"- Test log: `{rel(TEST_LOG)}`")
a("")
a("### Pytest tail")
a("```text")
tail = (tests["stdout"] + "\n" + tests["stderr"]).splitlines()[-120:]
a("\n".join(tail))
a("```")
a("")

a("## 10. Production workspace")
a("")
for pr in data["workspace_projects"]:
    a(f"### `{pr['project']}`")
    a(f"- Files: **{pr['files']}**")
    a(f"- Extensions: `{json.dumps(pr['extensions'], ensure_ascii=False)}`")
    if pr["videos"]:
        a("- Recent video outputs:")
        for v in pr["videos"][:10]:
            a(f"  - `{v['path']}` — {v['size_mb']} MB — {v['mtime']}")
    a("- Newest artifacts:")
    for f in pr["newest_files"][:10]:
        a(f"  - `{f['path']}` — {f['mtime']}")
    a("")

a("## 11. Detailed module inventory")
a("")
for x in core_parsed:
    a(f"### `{x['file']}`")
    a(f"- Lines: {x['lines']}")
    a(f"- Classes: {', '.join(f'`{c}`' for c in x['classes']) if x['classes'] else 'none'}")
    a(f"- Functions/methods detected: {len(x['functions'])}")
    if x["imports"]:
        a(f"- Imports: {', '.join(f'`{i}`' for i in x['imports'][:30])}")
    a("")

MD.write_text("\n".join(lines), encoding="utf-8")

with zipfile.ZipFile(ZIP, "w", compression=zipfile.ZIP_DEFLATED) as z:
    for p in [MD, JS, TEST_LOG, COLLECT_LOG]:
        z.write(p, arcname=p.name)

print()
print("============================================================")
print("ATLAS ZERO FULL OS AUDIT COMPLETE")
print("============================================================")
print(f"Markdown : {MD}")
print(f"JSON     : {JS}")
print(f"Tests    : {TEST_LOG}")
print(f"Package  : {ZIP}")
print()
print(f"Core modules : {len(core_files)}")
print(f"Syntax errors: {len(syntax_errors)}")
print(f"Pytest rc    : {tests['returncode']}")
print(f"Projects     : {len(data['workspace_projects'])}")
print("============================================================")
