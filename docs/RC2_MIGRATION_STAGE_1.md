# ATLAS ZERO RC2 — Migration Stage 1

This patch is built from the uploaded ATLAS ZERO source snapshot.

It establishes:

- `DirectorCoreRC2` as the single RC2 orchestration authority.
- `ProductionStateStoreRC2` as the canonical atomically-written state.
- One public service each for asset indexing, assignment, timeline, rendering and quality.
- Atomic render publication only after `ffprobe` verification.
- Project-generic paths; no required `franklin` project id in the new core.
- Compatibility with the proven RC1 engines during migration.

## Deliberately not deleted yet

Legacy orchestrators and experimental scripts remain in place until:

1. Franklin passes the RC2 regression run.
2. A second independent film passes.
3. Their outputs match RC2 contracts.

After those tests, migration stage 2 removes or archives duplicate orchestrators and moves the remaining CLIP/temporal scoring logic from `tools` into `AssignmentEngineRC2`.
