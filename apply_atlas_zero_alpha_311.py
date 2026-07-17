from __future__ import annotations

import argparse
import difflib
import py_compile
import shutil
from pathlib import Path

PIPELINE_PATH = Path("src/az_enterprise/core/pipeline_runtime.py")
BACKUP_PATH = PIPELINE_PATH.with_suffix(".py.alpha311.bak")
PATCH_PATH = Path("ATLAS_ZERO_RC1_ALPHA_3_1.patch")

IMPORT_ANCHOR = "from .paths import EXPORTS\n"
IMPORT_BLOCK = (
    "from .paths import EXPORTS\n"
    "from .module_registry_alpha31 import ModuleRegistryAlpha31\n"
    "from .dependency_resolver_alpha31 import DependencyResolverAlpha31\n"
)

INIT_ANCHOR = """        self.export_dir = EXPORTS / project_id
        self.export_dir.mkdir(parents=True, exist_ok=True)
"""
INIT_BLOCK = """        self.export_dir = EXPORTS / project_id
        self.export_dir.mkdir(parents=True, exist_ok=True)
        self.module_registry = ModuleRegistryAlpha31()
        self._register_runtime_modules()
        self.dependency_resolver = DependencyResolverAlpha31(self.module_registry)
"""

STEPS_START = "    def _steps(self) -> list[tuple[str, str, Callable[[], dict[str, Any]]]]:\n"
STEPS_END = "    # --- Real step wrappers. Each wrapper performs actual work and returns measured results.\n"

REGISTRY_BLOCK = """    def _register_runtime_modules(self) -> None:
        # Register the RC1 Alpha 3.1 runtime graph.
        # Dependencies preserve the legacy static execution order.
        modules = [
            ("preflight_start", "Preflight: проверка рабочей станции", self._step_preflight),
            ("scan_assets", "Анализ материалов: чтение файлов, хеши, метаданные", self._step_scan_assets),
            ("cv_model", "CV Runtime: OpenCV/Pillow анализ изображений", self._step_cv_model),
            ("visual_intelligence", "Visual Intelligence: профиль стиля", self._step_visual_intelligence),
            ("build_shots", "Story Engine: построение монтажной структуры", self._step_build_shots),
            ("director_ai", "Director AI 2.5: подбор материалов, проверка полноты и задачи", self._step_director_ai),
            ("story_runtime", "Story Engine 2.3: сцены и монтажный лист", self._step_story_runtime),
            ("director_ai_2_4", "Director AI 2.4: качество, решения, задачи", self._step_director_ai_runtime),
            ("live_api_test", "Live API: проверка ключей и read-only endpoints", self._step_live_api_test),
            ("integrations", "Integration Registry: состояние сервисов", self._step_integrations),
            ("api_queue", "API Queue: задания для недостающих кадров", self._step_api_queue),
            ("api_safe_run", "API Runner: dry/live-safe выполнение очереди", self._step_api_safe_run),
            ("quality", "Quality Control: готовность, повторы, дефицит", self._step_quality),
            ("readiness_gate", "Release Gate RC1: строгая проверка", self._step_readiness_gate),
            ("timeline_package", "Timeline Studio: монтажный пакет", self._step_timeline_package),
            ("native_timeline", "Native Timeline: модель треков", self._step_native_timeline),
            ("native_viewer", "Native Viewer RC: модель viewer", self._step_native_viewer),
            ("native_viewer_pro", "Native Viewer Pro 2.2: просмотр фильма и CV", self._step_native_viewer_pro),
            ("timeline_viewer_2", "Timeline Viewer 2: HTML/JSON viewer", self._step_timeline_viewer_2),
            ("cv_review_board", "CV Review Board: визуальная доска", self._step_cv_review_board),
            ("capcut_bridge", "CapCut Bridge: порядок укладки", self._step_capcut_bridge),
            ("final_assembly_pack", "Final Assembly Pack: handoff в монтаж", self._step_final_assembly_pack),
            ("montage_workbench", "Монтажная мастерская", self._step_montage_workbench),
            ("local_autopilot", "Local Autopilot: ближайшие действия", self._step_local_autopilot),
            ("operator_console", "Операторский центр", self._step_operator_console),
            ("acceptance", "Acceptance Center: Franklin local E2E", self._step_acceptance),
            ("test_center", "Центр тестирования RC1", self._step_test_center),
            ("production_state", "Production State: снимок состояния", self._step_production_state),
            ("working_state_audit", "Working State Auditor", self._step_working_state_audit),
            ("franklin_e2e", "Franklin E2E Runtime: финальная проверка проекта", self._step_franklin_e2e),
            ("export_all", "Export Engine: полный экспорт", self._step_export_all),
        ]

        previous: str | None = None
        for name, title, callback in modules:
            dependencies = [previous] if previous else []
            self.module_registry.register(
                name=name,
                title=title,
                callback=callback,
                dependencies=dependencies,
            )
            previous = name

    def _steps(self) -> list[tuple[str, str, Callable[[], dict[str, Any]]]]:
        order = self.dependency_resolver.resolve()
        return [
            (module.name, module.title, module.callback)
            for module in (self.module_registry.get(name) for name in order)
        ]

    def module_registry_snapshot(self) -> list[dict[str, Any]]:
        # Return a JSON-safe description of the active Alpha 3.1 graph.
        order = self.dependency_resolver.resolve()
        return [
            {
                "name": module.name,
                "title": module.title,
                "enabled": module.enabled,
                "dependencies": list(module.dependencies),
            }
            for module in (self.module_registry.get(name) for name in order)
        ]

"""

def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"Expected exactly one {label} anchor, found {count}")
    return text.replace(old, new, 1)

def build_updated_source(original: str) -> str:
    text = original.lstrip("\ufeff")

    if "from .module_registry_alpha31 import ModuleRegistryAlpha31" not in text:
        text = replace_once(text, IMPORT_ANCHOR, IMPORT_BLOCK, "import")

    if "self.module_registry = ModuleRegistryAlpha31()" not in text:
        text = replace_once(text, INIT_ANCHOR, INIT_BLOCK, "initialization")

    if "def _register_runtime_modules(self)" not in text:
        start = text.find(STEPS_START)
        end = text.find(STEPS_END, start)
        if start < 0 or end < 0:
            raise RuntimeError("Could not locate the legacy _steps block")
        text = text[:start] + REGISTRY_BLOCK + text[end:]

    text = text.replace("Enterprise RC1 Alpha 2.4 runtime.", "Enterprise RC1 Alpha 3.1 runtime.")
    text = text.replace('"version": "RC1 Alpha 2.4"', '"version": "RC1 Alpha 3.1"')
    text = text.replace("Версия: RC1 Alpha 2.4", "Версия: RC1 Alpha 3.1")
    return text

def compile_check(path: Path) -> None:
    py_compile.compile(str(path), doraise=True)
    py_compile.compile("src/az_enterprise/core/module_registry_alpha31.py", doraise=True)
    py_compile.compile("src/az_enterprise/core/dependency_resolver_alpha31.py", doraise=True)

def write_utf8_lf(path: Path, content: str) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(content)

def main() -> int:
    parser = argparse.ArgumentParser(description="Integrate ATLAS ZERO RC1 Alpha 3.1 runtime registry")
    parser.add_argument("--check", action="store_true", help="validate and print the diff without writing")
    args = parser.parse_args()

    if not PIPELINE_PATH.exists():
        raise SystemExit(f"Missing target: {PIPELINE_PATH}")

    original = PIPELINE_PATH.read_text(encoding="utf-8-sig")
    updated = build_updated_source(original)

    diff = "".join(
        difflib.unified_diff(
            original.splitlines(keepends=True),
            updated.splitlines(keepends=True),
            fromfile="a/src/az_enterprise/core/pipeline_runtime.py",
            tofile="b/src/az_enterprise/core/pipeline_runtime.py",
        )
    )

    if not diff:
        print("Alpha 3.1 integration is already applied.")
        compile_check(PIPELINE_PATH)
        return 0

    if args.check:
        print(diff)
        return 0

    if not BACKUP_PATH.exists():
        shutil.copy2(PIPELINE_PATH, BACKUP_PATH)
        print(f"Backup created: {BACKUP_PATH}")
    else:
        print(f"Backup already exists: {BACKUP_PATH}")

    write_utf8_lf(PIPELINE_PATH, updated)
    write_utf8_lf(PATCH_PATH, diff)
    compile_check(PIPELINE_PATH)

    print(f"Updated: {PIPELINE_PATH}")
    print(f"Patch created: {PATCH_PATH}")
    print("Alpha 3.1 registry integration completed successfully.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
