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
