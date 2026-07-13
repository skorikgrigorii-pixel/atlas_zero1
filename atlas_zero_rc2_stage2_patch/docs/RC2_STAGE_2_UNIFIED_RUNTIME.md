# ATLAS ZERO RC2 Stage 2 — Unified Runtime

Stage 2 establishes governance rather than deleting working RC1 code.

- DirectorCoreRC2 is the sole canonical orchestration authority.
- ProductionStateStoreRC2 is the sole canonical runtime state.
- Concurrent Director Core runs are blocked by an exclusive lock.
- Completed resumable stages can be skipped safely.
- Quality Gate validates temporal reports and real rendered artifacts.
- Legacy runtimes remain available only as implementation adapters during migration.

Legacy modules are not deleted until Franklin and the second-film test pass.
