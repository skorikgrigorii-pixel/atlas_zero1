# ATLAS ZERO AI Media Factory Architecture

## 1. Overall architecture

ATLAS ZERO is evolving from a Director AI orchestration project into an AI Media Factory.

The system remains a local-first, modular platform, but its purpose changes:

- accept a media production request,
- orchestrate multiple specialized modules,
- execute the production pipeline,
- publish the result,
- track analytics,
- and improve future runs.

The architecture is built around existing modules:

- Research
- Production Script
- Voice
- Visual
- Video
- Packaging
- Analytics

These modules remain the execution engines. The new orchestration layer coordinates them.

The architecture is intentionally layered:

1. Experience layer
   - Dashboard
   - operator controls
   - project views
   - task monitoring

2. Orchestration layer
   - Media Orchestrator
   - job queue
   - execution state machine
   - event bus
   - retry manager

3. Module layer
   - Research
   - Production Script
   - Voice
   - Visual
   - Video
   - Packaging
   - Analytics

4. Integration layer
   - YouTube publisher
   - future TikTok adapter
   - local file system and media storage
   - API connectors

5. Data layer
   - shared SQLite database
   - artifact storage
   - logs and event history

The guiding principle is simple:

- do not rewrite the existing modules,
- create the coordination layer that makes them work as one factory.

---

## 2. Media Orchestrator

The Media Orchestrator is the central controller for the entire factory.

It is responsible for:

- receiving a request such as “Create Movie”
- breaking the request into a pipeline plan
- dispatching work to the correct module
- tracking the state of each step
- handling failures and retries
- publishing status updates
- deciding when the pipeline has completed

The Orchestrator does not perform the creative work itself. It manages execution.

### Core responsibilities

- create a pipeline job for a new media project
- map the requested workflow to module steps
- assign jobs to workers
- monitor progress
- advance the execution state machine
- emit events after each stage
- surface failures to the operator

### Primary inputs

- user request
- project settings
- module capabilities
- current pipeline state

### Primary outputs

- job dispatches
- state transitions
- artifacts
- progress reports
- publish signals

---

## 3. Job Queue

The Job Queue provides asynchronous execution for the media pipeline.

It is the mechanism that turns a single user command into a coordinated set of tasks.

### Queue design

Each pipeline stage becomes a queue job:

- Research Job
- Script Job
- Voice Job
- Visual Job
- Video Job
- Packaging Job
- Publish Job
- Analytics Job

Each job should contain:

- project ID
- stage name
- module name
- input artifact references
- parameters
- priority
- retry count
- deadline
- callback event

### Queue responsibilities

- accept jobs from the orchestrator
- schedule them for execution
- support parallel execution where safe
- preserve order where required
- manage retry and failure handling

### Queue categories

- production queue
- publish queue
- analytics queue
- retry queue

The queue allows the factory to run work in the background instead of blocking the operator.

---

## 4. Shared SQLite database

The shared SQLite database remains the central source of truth for the factory.

It stores:

- projects
- pipeline runs
- jobs
- module status
- artifacts
- state history
- approvals
- errors
- retries
- analytics snapshots
- publish metadata

### Why SQLite is still appropriate

- local-first operation remains important
- the project is already structured around SQLite
- it is simple to inspect and debug
- it supports small-to-medium production workloads well

### Key database concepts

- one project has many jobs
- each job belongs to one stage
- each stage produces one or more artifacts
- each artifact is linked to a project and a job
- every state transition should be recorded in history

The database should not be treated as a temporary cache. It is the durable record of the factory.

---

## 5. Plugin system

The factory should support a plugin model so modules can be replaced or extended without changing the core orchestrator.

### Plugin categories

- research providers
- script providers
- voice providers
- visual providers
- video providers
- packaging providers
- publish providers
- analytics providers

### Plugin contract

Each plugin should expose a standard interface:

- register capability
- accept a job payload
- produce outputs
- emit status events
- report success or failure

### Why this matters

- existing modules can stay in place
- future modules can be added cleanly
- external services can be integrated later
- local and remote providers can coexist

The orchestrator should talk to modules through a stable interface, not directly to a specific implementation.

---

## 6. Module communication

Modules should communicate through structured contracts rather than ad hoc file handling alone.

### Communication model

- the orchestrator dispatches work
- each module receives a task payload
- the module produces structured output
- the output is stored and passed forward
- downstream modules consume the output through known artifact references

### Communication patterns

- file-based handoff for media assets
- database references for artifact state
- event notifications for progress and completion
- simple API payloads for service-based modules

### Recommended contract principles

- each module returns: status, output references, errors, metadata
- each module publishes a completion event
- each module writes its artifacts in a predictable place

This keeps the system modular and easy to debug.

---

## 7. Event bus

The Event Bus is the coordination backbone of the factory.

It carries status changes between the orchestrator, workers, modules, dashboard, and persistence layer.

### Example events

- PROJECT_CREATED
- RESEARCH_STARTED
- RESEARCH_COMPLETED
- SCRIPT_STARTED
- SCRIPT_COMPLETED
- VOICE_STARTED
- VOICE_COMPLETED
- VISUAL_STARTED
- VISUAL_COMPLETED
- VIDEO_STARTED
- VIDEO_COMPLETED
- PACKAGING_STARTED
- PACKAGING_COMPLETED
- PUBLISH_STARTED
- PUBLISH_COMPLETED
- ANALYTICS_STARTED
- ANALYTICS_COMPLETED
- JOB_FAILED
- RETRY_SCHEDULED
- PROJECT_COMPLETED

### Event bus responsibilities

- notify the orchestrator of changes
- update the dashboard in real time
- record history in the database
- trigger downstream actions when needed

---

## 8. Execution state machine

Every media project should move through a formal execution state machine.

### Suggested states

- NEW
- RESEARCH_PENDING
- RESEARCH_DONE
- SCRIPT_PENDING
- SCRIPT_DONE
- VOICE_PENDING
- VOICE_DONE
- VISUAL_PENDING
- VISUAL_DONE
- VIDEO_PENDING
- VIDEO_DONE
- PACKAGING_PENDING
- PACKAGING_DONE
- PUBLISH_PENDING
- PUBLISHED
- ANALYTICS_PENDING
- ANALYTICS_DONE
- FAILED

### State machine rules

- transitions must be validated
- invalid transitions are rejected and logged
- each state change is recorded in the state history
- a failed state can lead to retry or operator intervention

The state machine makes the factory predictable and auditable.

---

## 9. Retry strategy

Failures should be handled without losing progress.

### Retry policy

- retry transient failures automatically
- use backoff between retries
- preserve the last successful artifact
- record all failure details
- escalate after a bounded number of retries

### Failure categories

- retryable failures
  - temporary connectivity issues
  - short-lived service errors
  - resource contention

- non-retryable failures
  - invalid input payload
  - missing required asset
  - policy violation
  - permanent configuration error

### Recovery behavior

The orchestrator should be able to resume from the last successful stage rather than restart the full pipeline unless required.

---

## 10. Logging

Logging must be central and structured.

### Logging requirements

- log each job start and completion
- log state transitions
- log errors with context
- log module outputs and artifact references
- log retries and escalations
- preserve logs for auditing

### Log targets

- file logs for local debugging
- database audit records for project-level history
- dashboard-visible activity stream

The logging system should make it easy to answer:

- what happened,
- when it happened,
- which module did it,
- and what artifact was produced.

---

## 11. Worker processes

Worker processes should execute module jobs independently of the main orchestrator process.

### Responsibilities of workers

- pick up queue jobs
- run a module implementation
- produce outputs
- report completion or failure
- emit events

### Worker model

- one worker pool for production stages
- one worker pool for publishing
- one worker pool for analytics
- one retry worker for failed jobs

This separation allows the factory to stay responsive while longer-running tasks run in the background.

---

## 12. API layer

The factory should expose a small API layer for internal and external use.

### API categories

- project management API
- job control API
- artifact access API
- publish API
- analytics API
- health API

### API responsibilities

- start a new movie production request
- query the status of a project
- inspect artifacts
- pause or resume the pipeline
- trigger retries
- retrieve logs and events

This API layer allows the Dashboard and future integrations to interact with the factory in a structured way.

---

## 13. Dashboard

The Dashboard is the operator control surface.

It should allow the user to:

- create a new movie request
- monitor pipeline progress
- inspect job status
- view artifact readiness
- see errors and retries
- trigger manual intervention
- monitor publish state
- inspect analytics summary

### Dashboard views

- project overview
- active pipeline view
- job queue view
- log view
- artifact browser
- analytics summary

The Dashboard should be readable and lightweight, not overloaded.

---

## 14. YouTube integration

YouTube integration is the first external publish path.

### Integration responsibilities

- prepare publish metadata
- create publish job
- upload the packaged asset
- attach title, description, tags, and thumbnail
- publish or schedule the release
- capture publish status and link

### Integration points

- metadata preparation
- upload handling
- publish status tracking
- analytics collection after publication

The integration should be treated as a plugin or connector so the core factory does not depend directly on YouTube-specific logic.

---

## 15. Future TikTok integration

TikTok support should be designed as a second publish channel from the start.

### Design expectation

The factory should support channel adapters for different platforms.

A TikTok adapter would provide:

- channel-specific metadata formatting
- upload or publish handling
- platform rules and constraints
- analytics collection

The important architectural choice is that TikTok integration should not require a rewrite of the core orchestrator. It should plug into the same pipeline and publish layer.

---

## 16. Architectural summary

The new ATLAS ZERO AI Media Factory architecture is centered on one principle:

existing media modules stay as specialists, and a new orchestration layer turns them into a coordinated production factory.

The core building blocks are:

- Media Orchestrator
- Job Queue
- Shared SQLite database
- Event Bus
- Execution State Machine
- Retry and Logging framework
- Worker processes
- API layer
- Dashboard
- Publish connectors such as YouTube

With this architecture, ATLAS ZERO can move from a single-pipeline assistant into a repeatable media production factory without rewriting the underlying creative modules.
