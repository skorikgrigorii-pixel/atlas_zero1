# ATLAS ZERO Alpha 3.0.1 — Minimal Unified Project Model

This version introduces one immutable project object as a future source of
truth without changing the existing Runtime or Director components.

Included entities:

- `Project`
- `Scene`
- `Asset`
- `Task`
- `Experience`

Principles:

- immutable state;
- every change creates a new project version;
- scene assets must exist in the project;
- identifiers and scene order must be unique;
- experiences are recorded but do not modify policy;
- JSON round-trip is supported.

Deliberately excluded:

- scene graph;
- knowledge engine;
- automatic learning;
- Runtime integration;
- Director integration;
- persistence layer.

These are deferred until the existing Hogueras test flow remains stable.
