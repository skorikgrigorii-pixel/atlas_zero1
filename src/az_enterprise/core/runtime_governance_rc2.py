from __future__ import annotations

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True)
class RuntimeAuthority:
    name: str
    role: str
    may_advance_pipeline: bool
    deprecated: bool = False


CANONICAL_AUTHORITY: Final[RuntimeAuthority] = RuntimeAuthority(
    name="DirectorCoreRC2",
    role="canonical_orchestrator",
    may_advance_pipeline=True,
)

LEGACY_AUTHORITIES: Final[tuple[RuntimeAuthority, ...]] = (
    RuntimeAuthority("PipelineRunManager", "legacy_orchestrator", False, True),
    RuntimeAuthority("WorkflowEngine", "legacy_orchestrator", False, True),
    RuntimeAuthority("MovieRuntimeRC1", "legacy_service_adapter", False, True),
    RuntimeAuthority("ProductionDirector", "legacy_quality_adapter", False, True),
    RuntimeAuthority("DirectorAIRuntime", "legacy_analysis_adapter", False, True),
    RuntimeAuthority("StoryEngineRuntime", "legacy_story_adapter", False, True),
    RuntimeAuthority("FranklinE2ERuntime", "project_specific_adapter", False, True),
)


def governance_report() -> dict[str, object]:
    return {
        "schema_version": "2.1",
        "canonical_authority": CANONICAL_AUTHORITY.__dict__,
        "legacy_authorities": [item.__dict__ for item in LEGACY_AUTHORITIES],
        "orchestration_authorities": 1,
        "policy": (
            "Only DirectorCoreRC2 may advance canonical production stages. "
            "Legacy runtimes may be called only behind RC2 service adapters."
        ),
    }
