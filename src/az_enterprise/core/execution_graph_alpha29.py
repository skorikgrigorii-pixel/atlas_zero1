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
