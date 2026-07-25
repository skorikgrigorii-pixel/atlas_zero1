# ATLAS ZERO RC1 Alpha 2.5 — Implementation Roadmap

## Scope

This document is a non-code implementation plan for upgrading the current RC1 Alpha 2.4 repository to RC1 Alpha 2.5 while preserving the existing modular architecture.

## 1. Repository audit summary

### Current state
- The repository is a modular monolith centered on a SQLite-backed pipeline, a Tkinter dashboard, and a set of domain modules under src/az_enterprise/core.
- The project already contains strong foundational modules for:
  - asset intelligence,
  - story engine,
  - director AI runtime,
  - quality control,
  - acceptance / handoff exports,
  - live API integration scaffolding,
  - operator console and testing center.
- The codebase is already large and feature-rich, but several integration points are incomplete or inconsistent.

### Overall assessment
The repository is not missing a full architecture; it is missing a consistent Alpha 2.5 integration layer across existing modules.

## 2. Unfinished or incomplete modules

The following areas should be treated as incomplete for Alpha 2.5 delivery:

### A. Director AI completeness integration
- Current state: Director AI exists, but the integration with Story Engine completeness signals and production task generation is only partially wired.
- Gap: the flow should be a real end-to-end loop from Story Engine -> completeness analysis -> Director AI tasks -> operator tasks -> pipeline visibility.
- Priority: critical

### B. Story Engine -> Director AI -> operator workflow linkage
- Current state: Story Engine writes scenes/shots and missing requirements, while Director AI runtime can analyze issues and tasks.
- Gap: the handoff between these stages is not yet fully consistent across the pipeline and the UI.
- Priority: critical

### C. Dashboard integration for Alpha 2.5 signals
- Current state: the Tkinter dashboard has a Director AI section, but it does not fully expose the new Alpha 2.5 completeness metrics and task generation state in a consistent way.
- Gap: the dashboard should present missing assets, issues, tasks, and pipeline impact in one place.
- Priority: high

### D. Pipeline integration consistency
- Current state: pipeline_runtime and workflow.py both orchestrate the pipeline, but their behavior is slightly divergent.
- Gap: Alpha 2.5 should have one consistent orchestration path and one consistent contract for the Director AI stage.
- Priority: high

### E. Test coverage for the new release level
- Current state: there is only a very small test file for the Alpha 2.5 Director AI concept.
- Gap: the repository needs regression tests around the core Alpha 2.5 flow, especially completeness analysis and task generation.
- Priority: high

### F. Documentation parity
- Current state: README and RC1 status were partially updated, but the project still references older release language in several places.
- Gap: the release narrative and run instructions should fully reflect Alpha 2.5.
- Priority: medium

## 3. Missing integrations between modules

### 3.1 Story Engine <-> Director AI
- Story Engine creates shots and missing requirements.
- Director AI should consume those outputs directly and use them as the source of truth for completeness analysis and task creation.
- Current integration is incomplete because the flow is not fully enforced and exposed through the same data contract in both the runtime and the dashboard.

### 3.2 Director AI runtime <-> operator console
- Director AI creates issues/tasks, but the operator console should reflect those tasks with the same status semantics and priority.
- Current integration is partially present, but it should be normalized so operator workflow is driven by the same task model.

### 3.3 Director AI runtime <-> pipeline runtime
- The pipeline step should not simply run a legacy helper; it should preserve a consistent result structure for downstream UI and export logic.
- Current pipeline contract is a little inconsistent with the more advanced Director AI runtime data model.

### 3.4 Dashboard <-> database-backed state
- The dashboard should rely on a stable summary contract from the database rather than ad hoc queries scattered across multiple UI methods.
- Current UI has some duplication and should be consolidated around a shared summary model.

### 3.5 Release gate / production state / acceptance center
- These modules overlap in their view of readiness and blockers.
- They should share a common interpretation of readiness and task impact for Alpha 2.5.

## 4. Duplicate logic

The following areas contain repeated or overlapping logic that should be consolidated in the Alpha 2.5 work:

### A. Readiness and blocker logic
- ReleaseGate, ProductionState, WorkingStateAuditor, AcceptanceCenter, and TestCenter each compute readiness and next actions in a similar but slightly different way.
- These should be unified around a single readiness contract.

### B. Task creation logic
- Director AI runtime and the lightweight DirectorAI helper both create task-related data in different parts of the system.
- This duplication should be reduced so there is one canonical task-generation path.

### C. Export generation logic
- Many modules create HTML/CSV/JSON artifacts independently.
- The output structure is similar, but the implementation is spread across several modules.
- This is not a blocker for Alpha 2.5 but should be treated as a cleanup priority.

### D. UI summary logic
- Dashboard sections often re-query the same underlying tables and format them separately.
- A shared summary helper would reduce drift.

## 5. Dead code / low-value code

The following items are candidates for deprecation or cleanup:

### A. Legacy workflow path
- workflow.py contains a large orchestration path that overlaps with pipeline_runtime.py.
- If both remain, they should be clearly separated or one should become the canonical engine.

### B. Standalone utility-style modules that are not used in the main path
- Some modules appear to be feature-complete but are not consistently integrated into the primary runtime flow.
- They should be reviewed for whether they are still part of the active feature set.

### C. Duplicate release/version labels
- Several modules describe the project as Alpha 1.8/1.6/2.4 in their generated reports and headers.
- These should be harmonized to Alpha 2.5 for consistency.

## 6. Missing tests

The current test coverage is insufficient for Alpha 2.5. Recommended tests:

### Priority 1
- Director AI completeness analysis with missing assets
- Story Engine -> Director AI task generation end to end
- Pipeline step output contract for Director AI

### Priority 2
- Readiness consistency across ReleaseGate, ProductionState, and WorkingStateAuditor
- Operator task propagation from Director AI issues/tasks
- Export artifact creation for the main Alpha 2.5 flow

### Priority 3
- UI-level smoke coverage for the dashboard summary cards
- Integration fallback behavior when live APIs are unavailable

## 7. Implementation roadmap by priority

### Priority 1 — Critical Alpha 2.5 foundation
1. Finalize the Director AI completeness loop
   - Story Engine output is the source of truth.
   - Missing shots/materials produce actionable issues and tasks.
2. Normalize task creation
   - Ensure Director AI issues create consistent director_tasks, operator_tasks, and api_jobs entries.
3. Make the pipeline contract consistent
   - pipeline_runtime and workflow.py should share the same stage result semantics.
4. Add regression tests for the Director AI completeness path.

### Priority 2 — Integration hardening
5. Unify readiness computations
   - ReleaseGate, ProductionState, WorkingStateAuditor, AcceptanceCenter, and TestCenter should use a shared interpretation of readiness.
6. Improve dashboard visibility
   - Expose Alpha 2.5 completeness, missing assets, issues, and tasks from the main dashboard.
7. Align export/report naming and version strings with Alpha 2.5.

### Priority 3 — Maintenance and cleanup
8. Reduce duplicate logic in task and readiness modules.
9. Review and trim dead or legacy code paths that are no longer part of the primary runtime.
10. Expand documentation and runbook content for the Alpha 2.5 workflow.

## 8. Suggested implementation order

1. Director AI completeness integration
2. Task propagation and operator workflow integration
3. Pipeline contract normalization
4. Dashboard contract and summary updates
5. Readiness / blocker normalization
6. Regression tests
7. Documentation and release polish

## 9. Risks and watch-outs

- The repository already has a large number of modules; changes should remain additive and preserve the existing architecture.
- The project uses SQLite and export artifacts heavily, so any refactor should keep backward compatibility with existing data and existing export paths.
- The current UI is feature-rich but not yet fully aligned with the new Alpha 2.5 semantics, so it should be updated carefully.

## 10. Definition of done for Alpha 2.5

Alpha 2.5 is complete when:
- Story Engine outputs are fully consumed by Director AI.
- Missing assets are detected automatically and turned into tasks.
- The dashboard and pipeline both reflect the same Alpha 2.5 state.
- Regression tests cover the new completeness path.
- Documentation and release versioning are consistent with Alpha 2.5.
