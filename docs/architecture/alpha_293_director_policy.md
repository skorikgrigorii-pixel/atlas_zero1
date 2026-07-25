# ATLAS ZERO Alpha 2.9.3 — Director Policy & Project Strategy

## Purpose

Alpha 2.9.3 gives Director AI an explicit project strategy instead of
hard-coded universal quality rules.

The policy defines:

- project type;
- primary objective;
- weighted quality criteria;
- release and rework thresholds;
- mandatory constraints;
- modules that may be targeted for rework.

## Architectural rule

Worker modules may:

- analyze;
- generate reports;
- recommend actions;
- produce candidate artifacts.

Worker modules may not:

- approve a project;
- reject a project;
- change project strategy;
- authorize release;
- directly trigger uncontrolled project mutation.

All project-level decisions belong to Director AI.

## Decision order

1. Validate mandatory constraints.
2. Calculate weighted quality score.
3. Compare the score with policy thresholds.
4. Validate proposed rework targets.
5. Emit one decision:
   - `APPROVE`
   - `REWORK`
   - `REJECT`
   - `ESCALATE`

## Deliberate limitations

This version does not add:

- Director Council;
- multiple internal agents;
- autonomous learning;
- persistent memory;
- dynamic policy generation.

The policy is explicit, deterministic, and testable.
