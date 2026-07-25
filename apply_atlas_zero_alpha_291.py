from __future__ import annotations

from pathlib import Path
import textwrap

FILES = {
"src/az_enterprise/core/project_context_alpha29.py": '''
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Mapping, MutableMapping

@dataclass
class ProjectContext:
    project_id: str
    profile: str = "balanced"
    project: MutableMapping[str, Any] = field(default_factory=dict)
    timeline: MutableMapping[str, Any] = field(default_factory=dict)
    assets: list[dict[str, Any]] = field(default_factory=list)
    settings: MutableMapping[str, Any] = field(default_factory=dict)
    results: MutableMapping[str, Any] = field(default_factory=dict)
    diagnostics: list[dict[str, Any]] = field(default_factory=list)

    def require(self, key: str) -> Any:
        if key not in self.results:
            raise KeyError(f"Required context result is missing: {key}")
        return self.results[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self.results.get(key, default)

    def publish(self, key: str, value: Any, *, overwrite: bool = True) -> None:
        if not overwrite and key in self.results:
            raise KeyError(f"Context result already exists: {key}")
        self.results[key] = value

    def publish_many(self, values: Mapping[str, Any], *, overwrite: bool = True) -> None:
        for key, value in values.items():
            self.publish(key, value, overwrite=overwrite)

    def add_diagnostic(self, event: Mapping[str, Any]) -> None:
        self.diagnostics.append(dict(event))

    def snapshot(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "profile": self.profile,
            "project": dict(self.project),
            "timeline": dict(self.timeline),
            "assets": [dict(item) for item in self.assets],
            "settings": dict(self.settings),
            "results": dict(self.results),
            "diagnostics": [dict(item) for item in self.diagnostics],
        }
''',
"src/az_enterprise/core/module_registry_alpha29.py": '''
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Callable, Iterable
from az_enterprise.core.project_context_alpha29 import ProjectContext

ModuleRunner = Callable[[ProjectContext], Any]

@dataclass(frozen=True)
class ModuleDefinition:
    module_id: str
    runner: ModuleRunner
    requires: tuple[str, ...] = ()
    produces: tuple[str, ...] = ()
    description: str = ""

    def __post_init__(self) -> None:
        if not self.module_id.strip():
            raise ValueError("module_id must not be empty")
        if len(set(self.requires)) != len(self.requires):
            raise ValueError(f"Duplicate requirements in module: {self.module_id}")
        if len(set(self.produces)) != len(self.produces):
            raise ValueError(f"Duplicate products in module: {self.module_id}")

class ModuleRegistry:
    def __init__(self) -> None:
        self._modules: dict[str, ModuleDefinition] = {}

    def register(self, definition: ModuleDefinition, *, replace: bool = False) -> ModuleDefinition:
        if definition.module_id in self._modules and not replace:
            raise KeyError(f"Module already registered: {definition.module_id}")
        self._modules[definition.module_id] = definition
        return definition

    def get(self, module_id: str) -> ModuleDefinition:
        try:
            return self._modules[module_id]
        except KeyError as exc:
            raise KeyError(f"Unknown module: {module_id}") from exc

    def all(self) -> tuple[ModuleDefinition, ...]:
        return tuple(self._modules[key] for key in sorted(self._modules))

    def producers_for(self, product: str) -> tuple[ModuleDefinition, ...]:
        return tuple(item for item in self.all() if product in item.produces)

    def validate_unique_producers(self) -> None:
        owners: dict[str, str] = {}
        for item in self.all():
            for product in item.produces:
                if product in owners:
                    raise ValueError(f"Product {product!r} has multiple producers: {owners[product]!r}, {item.module_id!r}")
                owners[product] = item.module_id

    def extend(self, definitions: Iterable[ModuleDefinition]) -> None:
        for definition in definitions:
            self.register(definition)
''',
"src/az_enterprise/core/execution_graph_alpha29.py": '''
from __future__ import annotations
from dataclasses import asdict, dataclass
from time import perf_counter
from typing import Any, Iterable
from az_enterprise.core.module_registry_alpha29 import ModuleDefinition, ModuleRegistry
from az_enterprise.core.project_context_alpha29 import ProjectContext

@dataclass(frozen=True)
class ExecutionRecord:
    module_id: str
    status: str
    duration_ms: float
    produced: tuple[str, ...]
    error: str | None = None

class DependencyError(RuntimeError):
    pass

class ExecutionGraph:
    def __init__(self, registry: ModuleRegistry) -> None:
        self.registry = registry
        self.registry.validate_unique_producers()

    def build_order(self, targets: Iterable[str] | None = None, *, available_products: Iterable[str] = ()) -> tuple[ModuleDefinition, ...]:
        available = set(available_products)
        selected = self._select_modules(targets, available)
        producer_by_product = {product: item.module_id for item in selected for product in item.produces}
        dependencies = {item.module_id: set() for item in selected}
        for item in selected:
            for requirement in item.requires:
                if requirement in available:
                    continue
                producer = producer_by_product.get(requirement)
                if producer is None:
                    raise DependencyError(f"Module {item.module_id!r} requires unavailable product {requirement!r}")
                if producer != item.module_id:
                    dependencies[item.module_id].add(producer)
        order = []
        ready = sorted(module_id for module_id, deps in dependencies.items() if not deps)
        while ready:
            module_id = ready.pop(0)
            order.append(self.registry.get(module_id))
            done = {item.module_id for item in order}
            for candidate in sorted(dependencies):
                if module_id in dependencies[candidate]:
                    dependencies[candidate].remove(module_id)
                    if not dependencies[candidate] and candidate not in done and candidate not in ready:
                        ready.append(candidate)
                        ready.sort()
        if len(order) != len(selected):
            unresolved = sorted(module_id for module_id, deps in dependencies.items() if deps)
            raise DependencyError("Dependency cycle detected: " + ", ".join(unresolved))
        return tuple(order)

    def run(self, context: ProjectContext, targets: Iterable[str] | None = None) -> dict[str, Any]:
        order = self.build_order(targets, available_products=context.results.keys())
        records = []
        for item in order:
            started = perf_counter()
            try:
                result = item.runner(context)
                produced = self._publish_result(context, item, result)
                record = ExecutionRecord(item.module_id, "ok", round((perf_counter()-started)*1000, 3), produced)
            except Exception as exc:
                record = ExecutionRecord(item.module_id, "error", round((perf_counter()-started)*1000, 3), (), f"{type(exc).__name__}: {exc}")
                context.add_diagnostic(asdict(record))
                raise
            records.append(record)
            context.add_diagnostic(asdict(record))
        return {"engine": "execution_graph_alpha29", "version": "2.9.1", "status": "ok", "order": [r.module_id for r in records], "records": [asdict(r) for r in records], "results": dict(context.results)}

    def _select_modules(self, targets: Iterable[str] | None, available: set[str]) -> tuple[ModuleDefinition, ...]:
        if targets is None:
            return self.registry.all()
        selected = {}
        def include(module_id: str) -> None:
            if module_id in selected:
                return
            item = self.registry.get(module_id)
            selected[module_id] = item
            for requirement in item.requires:
                if requirement in available:
                    continue
                producers = self.registry.producers_for(requirement)
                if len(producers) != 1:
                    raise DependencyError(f"Expected one producer for {requirement!r}, found {len(producers)}")
                include(producers[0].module_id)
        for module_id in dict.fromkeys(targets):
            include(module_id)
        return tuple(selected[key] for key in sorted(selected))

    @staticmethod
    def _publish_result(context: ProjectContext, item: ModuleDefinition, result: Any) -> tuple[str, ...]:
        if not item.produces:
            return ()
        if len(item.produces) == 1:
            context.publish(item.produces[0], result)
            return item.produces
        if not isinstance(result, dict):
            raise TypeError(f"Module {item.module_id!r} must return a mapping")
        missing = [key for key in item.produces if key not in result]
        if missing:
            raise KeyError(f"Module {item.module_id!r} did not return: {', '.join(missing)}")
        for key in item.produces:
            context.publish(key, result[key])
        return item.produces
''',
"tests/test_execution_graph_alpha291.py": '''
from __future__ import annotations
import unittest
from az_enterprise.core.execution_graph_alpha29 import DependencyError, ExecutionGraph
from az_enterprise.core.module_registry_alpha29 import ModuleDefinition, ModuleRegistry
from az_enterprise.core.project_context_alpha29 import ProjectContext

class ExecutionGraphAlpha291Test(unittest.TestCase):
    def test_dependency_order(self):
        registry = ModuleRegistry()
        registry.register(ModuleDefinition("visual", lambda c: {"score": .75}, produces=("visual_analysis",)))
        registry.register(ModuleDefinition("director", lambda c: c.require("visual_analysis"), requires=("visual_analysis",), produces=("director_report",)))
        order = ExecutionGraph(registry).build_order(["director"])
        self.assertEqual([m.module_id for m in order], ["visual", "director"])

    def test_targeted_run(self):
        registry = ModuleRegistry()
        registry.register(ModuleDefinition("research", lambda c: "research", produces=("research",)))
        registry.register(ModuleDefinition("visual", lambda c: "visual", produces=("visual_analysis",)))
        registry.register(ModuleDefinition("director", lambda c: c.require("visual_analysis"), requires=("visual_analysis",), produces=("director_report",)))
        result = ExecutionGraph(registry).run(ProjectContext("hogueras"), ["director"])
        self.assertEqual(result["order"], ["visual", "director"])
        self.assertNotIn("research", result["results"])

    def test_cached_product_skips_producer(self):
        registry = ModuleRegistry()
        registry.register(ModuleDefinition("visual", lambda c: "new", produces=("visual_analysis",)))
        registry.register(ModuleDefinition("director", lambda c: c.require("visual_analysis"), requires=("visual_analysis",), produces=("director_report",)))
        context = ProjectContext("hogueras", results={"visual_analysis": "cached"})
        result = ExecutionGraph(registry).run(context, ["director"])
        self.assertEqual(result["order"], ["director"])
        self.assertEqual(result["results"]["director_report"], "cached")

    def test_missing_dependency(self):
        registry = ModuleRegistry()
        registry.register(ModuleDefinition("director", lambda c: None, requires=("quality_report",)))
        with self.assertRaises(DependencyError):
            ExecutionGraph(registry).build_order(["director"])

    def test_cycle(self):
        registry = ModuleRegistry()
        registry.register(ModuleDefinition("a", lambda c: "a", requires=("b_output",), produces=("a_output",)))
        registry.register(ModuleDefinition("b", lambda c: "b", requires=("a_output",), produces=("b_output",)))
        with self.assertRaises(DependencyError):
            ExecutionGraph(registry).build_order()

if __name__ == "__main__":
    unittest.main()
'''
}

def find_root(start: Path) -> Path:
    for candidate in (start.resolve(), *start.resolve().parents):
        if (candidate / "pyproject.toml").exists() and (candidate / "src").exists():
            return candidate
    raise FileNotFoundError("Запустите установщик из папки репозитория atlas_zero1")

def main() -> int:
    root = find_root(Path.cwd())
    print(f"ATLAS ZERO Alpha 2.9.1\nРепозиторий: {root}\n")
    for relative, content in FILES.items():
        target = root / relative
        if target.exists():
            print(f"ПРОПУЩЕН: {relative}")
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(textwrap.dedent(content).lstrip(), encoding="utf-8", newline="\n")
        print(f"СОЗДАН:   {relative}")
    print("\nПроверка:\npython -m pytest tests/test_execution_graph_alpha291.py -v")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
