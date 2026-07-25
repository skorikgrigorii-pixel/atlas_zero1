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
