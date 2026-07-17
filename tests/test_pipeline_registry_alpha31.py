from __future__ import annotations

import pytest

from az_enterprise.core.dependency_resolver_alpha31 import DependencyResolverAlpha31
from az_enterprise.core.module_registry_alpha31 import ModuleRegistryAlpha31


def noop():
    return {}


def test_resolver_preserves_dependency_order():
    registry = ModuleRegistryAlpha31()
    registry.register("a", "A", noop)
    registry.register("b", "B", noop, dependencies=["a"])
    registry.register("c", "C", noop, dependencies=["b"])
    assert DependencyResolverAlpha31(registry).resolve() == ["a", "b", "c"]


def test_unknown_dependency_is_rejected():
    registry = ModuleRegistryAlpha31()
    registry.register("a", "A", noop, dependencies=["missing"])
    with pytest.raises(RuntimeError, match="Unknown dependency"):
        DependencyResolverAlpha31(registry).resolve()


def test_cycle_is_rejected():
    registry = ModuleRegistryAlpha31()
    registry.register("a", "A", noop, dependencies=["b"])
    registry.register("b", "B", noop, dependencies=["a"])
    with pytest.raises(RuntimeError, match="Circular dependency"):
        DependencyResolverAlpha31(registry).resolve()


def test_disabled_module_is_removed_from_graph():
    registry = ModuleRegistryAlpha31()
    registry.register("a", "A", noop)
    registry.register("b", "B", noop, dependencies=["a"])
    registry.disable("b")
    assert DependencyResolverAlpha31(registry).resolve() == ["a"]
