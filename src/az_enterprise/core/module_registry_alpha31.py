from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List


@dataclass(slots=True)
class RuntimeModule:
    name: str
    title: str
    callback: Callable
    enabled: bool = True
    dependencies: List[str] = field(default_factory=list)


class ModuleRegistryAlpha31:
    """
    Alpha 3.1 Runtime Registry

    Центральный реестр всех модулей Pipeline.
    """

    def __init__(self):
        self._modules: Dict[str, RuntimeModule] = {}

    def register(
        self,
        name: str,
        title: str,
        callback: Callable,
        dependencies: List[str] | None = None,
        enabled: bool = True,
    ) -> None:

        self._modules[name] = RuntimeModule(
            name=name,
            title=title,
            callback=callback,
            enabled=enabled,
            dependencies=dependencies or [],
        )

    def has(self, name: str) -> bool:
        return name in self._modules

    def get(self, name: str) -> RuntimeModule:
        return self._modules[name]

    def all(self):
        return list(self._modules.values())

    def enabled(self):
        return [m for m in self._modules.values() if m.enabled]

    def disable(self, name: str):
        if name in self._modules:
            self._modules[name].enabled = False

    def enable(self, name: str):
        if name in self._modules:
            self._modules[name].enabled = True
