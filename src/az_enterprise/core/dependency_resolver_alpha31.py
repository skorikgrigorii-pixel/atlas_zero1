from __future__ import annotations

from collections import deque

from .module_registry_alpha31 import ModuleRegistryAlpha31


class DependencyResolverAlpha31:
    """
    Строит корректный порядок выполнения модулей по зависимостям.
    """

    def __init__(self, registry: ModuleRegistryAlpha31):
        self.registry = registry

    def resolve(self) -> list[str]:
        graph = {}
        indegree = {}

        for module in self.registry.enabled():
            graph[module.name] = []
            indegree[module.name] = 0

        for module in self.registry.enabled():
            for dep in module.dependencies:
                if dep not in graph:
                    raise RuntimeError(
                        f"Unknown dependency '{dep}' for module '{module.name}'"
                    )
                graph[dep].append(module.name)
                indegree[module.name] += 1

        queue = deque(sorted(name for name, deg in indegree.items() if deg == 0))
        result = []

        while queue:
            node = queue.popleft()
            result.append(node)

            for nxt in graph[node]:
                indegree[nxt] -= 1
                if indegree[nxt] == 0:
                    queue.append(nxt)

        if len(result) != len(graph):
            raise RuntimeError("Circular dependency detected")

        return result
