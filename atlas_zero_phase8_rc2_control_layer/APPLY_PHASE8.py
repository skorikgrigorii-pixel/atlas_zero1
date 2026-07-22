from __future__ import annotations

import ast
import py_compile
import shutil
from datetime import datetime
from pathlib import Path


def repo_root() -> Path:
    for candidate in [Path.cwd().resolve(), *Path.cwd().resolve().parents]:
        if (candidate / "src" / "az_enterprise" / "core").is_dir():
            return candidate
    raise FileNotFoundError("ATLAS ZERO repository root was not found")


def patch_cli(text: str) -> str:
    text = text.replace("from .core.render_engine_rc1 import RenderEngineRC1\n", "")
    parser_block = (
        "    render_parser = subparsers.add_parser(\n"
        "        'render-rc1',\n"
        "        help='Deprecated compatibility render command.',\n"
        "    )\n"
        "    render_parser.add_argument('project_id')\n\n"
    )
    if parser_block not in text:
        raise RuntimeError("CLI legacy parser block was not found")
    text = text.replace(parser_block, "")
    start = text.find("    if args.command == 'render-rc1':")
    end = text.find("    if args.command == 'production-status':", start)
    if start < 0 or end < 0:
        raise RuntimeError("CLI legacy command block was not found")
    return text[:start] + text[end:]


def patch_media(text: str) -> str:
    text = text.replace(
        "from .movie_runtime_rc1 import run_movie as run_movie\n",
        "from .project_config_rc2 import ProjectConfigRC2\n"
        "from .timeline_engine_rc2 import TimelineEngineRC2\n"
        "from .render_engine_rc2 import RenderEngineRC2\n",
    )
    old = (
        '    if step_key == "video_ready":\n'
        '        return {"module": "video", "artifact": f"{project_id}/video/final.mp4", "status": "ready"}\n'
    )
    new = (
        '    if step_key == "video_ready":\n'
        '        config = ProjectConfigRC2(project_id=project_id)\n'
        '        timeline = TimelineEngineRC2(db, config).run()\n'
        '        render = RenderEngineRC2(config).run()\n'
        '        return {\n'
        '            "module": "video_rc2",\n'
        '            "authority": "RC2ControlLayer",\n'
        '            "timeline": timeline,\n'
        '            "render": render,\n'
        '            "artifact": render.get("output"),\n'
        '            "status": render.get("state", "ready"),\n'
        '        }\n'
    )
    if old not in text:
        raise RuntimeError("Media video adapter patch point was not found")
    return text.replace(old, new)


def patch_workflow(text: str) -> str:
    text = text.replace(
        "from .rc1_completion_planner import RC1CompletionPlanner\n",
        "from .control_layer_rc2 import RC2ReadinessPlanner\n",
    )
    replacements = {
        "rc1_gate = ReleaseGate(self.db, self.project_id).evaluate_rc1(); self._job('rc1_release_gate','done',rc1_gate)":
        "rc2_gate = RC2ReadinessPlanner(self.db, self.project_id).evaluate(); self._job('rc2_release_gate','done',rc2_gate)",
        "completion_plan = RC1CompletionPlanner(self.db, self.project_id).plan(); self._job('rc1_completion_plan','done',completion_plan)":
        "completion_plan = RC2ReadinessPlanner(self.db, self.project_id).plan(); self._job('rc2_completion_plan','done',completion_plan)",
        "rc1_gate_final = ReleaseGate(self.db, self.project_id).evaluate_rc1(); self._job('rc1_release_gate_final','done',rc1_gate_final)":
        "rc2_gate_final = RC2ReadinessPlanner(self.db, self.project_id).evaluate(); self._job('rc2_release_gate_final','done',rc2_gate_final)",
        "self.bus.emit('PIPELINE_FINISHED', {'readiness': gate['score'], 'rc1_ready': gate['ready']})":
        "self.bus.emit('PIPELINE_FINISHED', {'readiness': rc2_gate_final['score'], 'rc2_ready': rc2_gate_final['ready']})",
        "'rc1_gate': rc1_gate": "'rc2_gate': rc2_gate",
        "'rc1_gate_final': rc1_gate_final": "'rc2_gate_final': rc2_gate_final",
    }
    for old, new in replacements.items():
        if old not in text:
            raise RuntimeError(f"Workflow patch point missing: {old[:60]}")
        text = text.replace(old, new)
    return text


def patch_app(text: str) -> str:
    replacements = {
        "ATLAS ZERO Enterprise RC1 Alpha 2.4 — Director AI Runtime":
        "ATLAS ZERO Enterprise RC2 — Native Production Runtime",
        "ATLAS ZERO ENTERPRISE RC1": "ATLAS ZERO ENTERPRISE RC2",
        "'План RC1','Готовность RC1'": "'План RC2','Готовность RC2'",
        "elif name=='План RC1': self.rc1_plan()": "elif name=='План RC2': self.rc2_plan()",
        "elif name=='Готовность RC1': self.readiness()": "elif name=='Готовность RC2': self.readiness()",
        "    def rc1_plan(self):": "    def rc2_plan(self):",
        "from az_enterprise.core.rc1_completion_planner import RC1CompletionPlanner":
        "from az_enterprise.core.control_layer_rc2 import RC2ReadinessPlanner",
        "report = RC1CompletionPlanner(self.db).plan()":
        "report = RC2ReadinessPlanner(self.db).plan()",
    }
    for old, new in replacements.items():
        if old not in text:
            raise RuntimeError(f"UI patch point missing: {old}")
        text = text.replace(old, new)
    return text


def assert_no_rc1_imports(path: Path) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    bad = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            bad += [a.name for a in node.names if "rc1" in a.name.lower()]
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if "rc1" in module.lower():
                bad.append(module)
    if bad:
        raise RuntimeError(f"Active RC1 imports remain in {path}: {bad}")


def main() -> None:
    repo = repo_root()
    package = Path(__file__).resolve().parent
    backup = repo / "workspace" / "backups" / ("phase8_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
    backup.mkdir(parents=True, exist_ok=True)

    targets = {
        repo / "src" / "az_enterprise" / "cli.py": patch_cli,
        repo / "src" / "az_enterprise" / "core" / "media_orchestrator.py": patch_media,
        repo / "src" / "az_enterprise" / "core" / "workflow.py": patch_workflow,
        repo / "src" / "az_enterprise" / "ui" / "app.py": patch_app,
    }

    for target in targets:
        if not target.exists():
            raise FileNotFoundError(target)
        destination = backup / target.relative_to(repo)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target, destination)

    source_module = package / "payload" / "src" / "az_enterprise" / "core" / "control_layer_rc2.py"
    target_module = repo / "src" / "az_enterprise" / "core" / "control_layer_rc2.py"
    if target_module.exists():
        destination = backup / target_module.relative_to(repo)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target_module, destination)
    shutil.copy2(source_module, target_module)

    for target, patcher in targets.items():
        patched = patcher(target.read_text(encoding="utf-8-sig"))
        target.write_text(patched, encoding="utf-8")

    changed = [*targets.keys(), target_module]
    for path in changed:
        py_compile.compile(str(path), doraise=True)
        assert_no_rc1_imports(path)

    print("=" * 72)
    print("ATLAS ZERO — PHASE 8 RC2 CONTROL LAYER INSTALLED")
    print("=" * 72)
    print(f"Backup: {backup}")
    for path in changed:
        print(f"OK: {path.relative_to(repo)}")


if __name__ == "__main__":
    main()
