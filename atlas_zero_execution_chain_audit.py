from __future__ import annotations
import argparse, ast, json
from pathlib import Path
from datetime import datetime, timezone

STAGES = [
    "asset_engine_rc2.py",
    "visual_semantic_analyzer_rc2.py",
    "event_discovery_engine_rc2.py",
    "story_strategy_engine_rc2.py",
    "story_engine.py",
    "assignment_engine_rc2.py",
    "timeline_engine_rc2.py",
    "voice_production_engine_rc2.py",
    "audio_composer_rc2.py",
    "render_engine_rc2.py",
    "quality_gate_rc2.py",
]
ORCHESTRATORS = [
    "director_core_rc2.py",
    "pipeline_runtime.py",
    "media_orchestrator.py",
    "workflow.py",
    "production_director.py",
    "control_layer_rc2.py",
]
TARGETS = set(STAGES + ORCHESTRATORS + [
    "project_config_rc2.py",
    "runtime_governance_rc2.py",
    "rc2_cli.py",
    "assignment_policy_rc2.py",
])

def dotted(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        left = dotted(node.value)
        return f"{left}.{node.attr}" if left else node.attr
    return ""

def analyze(path, root):
    src = path.read_bytes().decode("utf-8-sig")
    tree = ast.parse(src, filename=str(path))
    imports, calls, strings, funcs, classes = set(), [], set(), [], []

    class V(ast.NodeVisitor):
        def __init__(self):
            self.scope = []
        def visit_Import(self, node):
            imports.update(a.name for a in node.names)
            self.generic_visit(node)
        def visit_ImportFrom(self, node):
            imports.add("." * node.level + (node.module or ""))
            self.generic_visit(node)
        def visit_ClassDef(self, node):
            classes.append(node.name)
            self.scope.append(node.name)
            self.generic_visit(node)
            self.scope.pop()
        def visit_FunctionDef(self, node):
            funcs.append(node.name)
            self.scope.append(node.name)
            self.generic_visit(node)
            self.scope.pop()
        visit_AsyncFunctionDef = visit_FunctionDef
        def visit_Constant(self, node):
            if isinstance(node.value, str) and ".json" in node.value.lower():
                strings.add(node.value)
        def visit_Call(self, node):
            name = dotted(node.func)
            if name:
                calls.append({
                    "scope": ".".join(self.scope) or "<module>",
                    "callee": name,
                    "line": getattr(node, "lineno", 0),
                })
            self.generic_visit(node)

    V().visit(tree)
    low = src.lower()
    relevant = [
        c for c in calls
        if c["callee"].lower().endswith((".run", ".analyze", ".build", ".evaluate", ".render", ".plan"))
        or any(x in c["callee"].lower() for x in (
            "asset", "semantic", "event", "story", "assignment",
            "timeline", "voice", "audio", "render", "quality"
        ))
    ]
    return {
        "path": path.relative_to(root).as_posix(),
        "imports": sorted(imports),
        "classes": classes,
        "functions": funcs,
        "json_literals": sorted(strings),
        "reads_json": "json.load" in low or ".read_text(" in low,
        "writes_json": "json.dump" in low or ".write_text(" in low,
        "relevant_calls": relevant,
    }

def imported(imports, filename):
    stem = Path(filename).stem
    return any(i.lstrip(".").split(".")[-1] == stem for i in imports)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root", nargs="?", default="src/az_enterprise/core")
    ap.add_argument("--output", default="audit_output")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    if not root.exists():
        raise SystemExit(f"Not found: {root}")

    repo = next((p for p in [root, *root.parents] if (p / "src/az_enterprise/core").exists()), root)
    out = Path(args.output)
    if not out.is_absolute():
        out = repo / out
    out.mkdir(parents=True, exist_ok=True)

    modules, errors = {}, []
    for p in sorted(root.rglob("*.py")):
        if p.name not in TARGETS:
            continue
        try:
            modules[p.name] = analyze(p, root)
        except SyntaxError as e:
            errors.append({
                "path": p.relative_to(root).as_posix(),
                "line": e.lineno,
                "column": e.offset,
                "message": e.msg,
            })

    director = modules.get("director_core_rc2.py", {})
    chain = []
    for name in STAGES:
        m = modules.get(name)
        chain.append({
            "module": name,
            "exists": bool(m),
            "imported_by_director_core": imported(director.get("imports", []), name),
            "reads_json": m.get("reads_json") if m else None,
            "writes_json": m.get("writes_json") if m else None,
            "json_literals": m.get("json_literals", []) if m else [],
        })

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "root": str(root),
        "summary": {
            "modules_analyzed": len(modules),
            "syntax_errors": len(errors),
        },
        "canonical_orchestrator": "director_core_rc2.py",
        "canonical_chain": chain,
        "missing_direct_imports": [
            x["module"] for x in chain if x["exists"] and not x["imported_by_director_core"]
        ],
        "orchestrators": {
            name: modules.get(name) for name in ORCHESTRATORS if name in modules
        },
        "modules": modules,
        "syntax_errors": errors,
    }

    jp = out / "execution_chain_audit.json"
    mp = out / "execution_chain_audit.md"
    jp.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# ATLAS ZERO RC2 — Execution Chain Audit",
        "",
        f"Root: `{root}`",
        "",
        "## Canonical chain",
        "",
        "| Module | Exists | Imported by DirectorCore | Reads JSON | Writes JSON |",
        "|---|---:|---:|---:|---:|",
    ]
    for x in chain:
        lines.append(
            f"| `{x['module']}` | {x['exists']} | {x['imported_by_director_core']} | "
            f"{x['reads_json']} | {x['writes_json']} |"
        )
    lines += ["", "## Missing direct imports", ""]
    lines += [f"- `{x}`" for x in report["missing_direct_imports"]] or ["- None"]
    lines += ["", "## Orchestrator calls", ""]
    for name, data in report["orchestrators"].items():
        lines += [f"### `{name}`", ""]
        for c in data["relevant_calls"]:
            lines.append(f"- `{c['scope']}` → `{c['callee']}` (line {c['line']})")
        lines.append("")
    mp.write_text("\n".join(lines), encoding="utf-8")

    print(json.dumps(report["summary"], indent=2))
    print("Missing direct imports:")
    for x in report["missing_direct_imports"]:
        print("-", x)
    print("JSON:", jp)
    print("Markdown:", mp)

if __name__ == "__main__":
    main()
