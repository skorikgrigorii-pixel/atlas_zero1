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



# ---------------------------------------------------------------------------
# ATLAS ZERO CHANGE VALUE GATE
#
# Canonical governance rule for every proposed OS change.
#
# No change begins until its current production value is explicitly known.
# This prevents technically interesting work from displacing film delivery.
# ---------------------------------------------------------------------------

CHANGE_VALUE_GATE: Final[dict[str, object]] = {
    "rule_id": "AZ_CHANGE_VALUE_GATE_V1",
    "status": "MANDATORY",
    "scope": "all_os_changes",
    "principle": "NO_CHANGE_WITHOUT_VALUE_GATE",
    "required_questions": (
        {
            "key": "CURRENT_STATE",
            "question": (
                "Where are we now? Define the concrete problem and its "
                "measurable current magnitude."
            ),
        },
        {
            "key": "FILM_IMPACT",
            "question": (
                "How does this action move the current film toward release? "
                "State the blocker, uncertainty or production work it removes."
            ),
        },
        {
            "key": "SYSTEM_VALUE",
            "question": (
                "What reusable value does ATLAS ZERO gain? Distinguish a "
                "one-film workaround from a general system improvement."
            ),
        },
        {
            "key": "MEASURABLE_EXIT",
            "question": (
                "What measurable before-to-after result proves that the "
                "change helped?"
            ),
        },
    ),
    "decision_rule": (
        "If a proposed change neither moves the current film toward release "
        "nor creates a demonstrable reusable system improvement, do not "
        "perform the change."
    ),
    "execution_rule": (
        "Evaluate and record the Change Value Gate before implementation, "
        "not retrospectively."
    ),
}


def governance_report() -> dict[str, object]:
    return {
        "schema_version": "2.2",
        "canonical_authority": CANONICAL_AUTHORITY.__dict__,
        "legacy_authorities": [item.__dict__ for item in LEGACY_AUTHORITIES],
        "orchestration_authorities": 1,
        "policy": (
            "Only DirectorCoreRC2 may advance canonical production stages. "
            "Legacy runtimes may be called only behind RC2 service adapters."
        ),
        "change_value_gate": CHANGE_VALUE_GATE,
    }
