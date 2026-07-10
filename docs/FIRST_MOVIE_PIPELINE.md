# First Documentary Movie Pipeline

This document describes the minimum production path for the first fully AI-produced documentary film.

## Pipeline overview

The first movie travels through the system in a simple linear flow:

Research -> Production Script -> Voice Production -> Visual Production -> Video Production -> Packaging -> YouTube Publishing -> Analytics

## How the pipeline works

1. A project is created in the shared database.
2. The orchestrator records the initial project state and creates a workflow plan.
3. Each stage is executed as a discrete job.
4. Artifacts are written into the project workspace.
5. The orchestrator advances the state machine after each successful stage.
6. If a stage fails, the job is marked failed and the project moves to FAILED.
7. After publication, analytics are collected and summarized.

## Expected artifacts

- research brief
- script draft
- narration audio
- visual assets
- edited video
- packaged output
- YouTube publish metadata
- analytics summary

## Operational intent

The initial pipeline is deliberately minimal. It prioritizes a single successful publication over complex automation. The design can be expanded later into a full media factory without changing the core orchestration contract.
