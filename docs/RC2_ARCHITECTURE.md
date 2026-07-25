# ATLAS ZERO RC2 Architecture Proposal

## 1. Overall system architecture

ATLAS ZERO RC2 is proposed as an evolution of the existing modular monolith rather than a rewrite. The system remains a local-first, SQLite-backed operating environment with a strong orchestration core, but it expands into a multi-stage autonomous media production platform.

The architecture is organized around five layers:

1. Experience layer
   - Operator dashboard
   - Project workspace UI
   - Monitoring and approvals

2. Orchestration layer
   - Pipeline runtime
   - Workflow scheduler
   - State machine engine
   - Event bus
   - Queue workers

3. Intelligence layer
   - Research AI
   - Script AI
   - Voice AI
   - Visual AI
   - Editing AI
   - Thumbnail AI
   - SEO AI
   - Analytics AI
   - Learning AI

4. Execution layer
   - API integrations
   - Local generators
   - Media processors
   - Upload connectors
   - Analytics collectors

5. Data and assets layer
   - Shared SQLite project database
   - Object storage / local media store
   - Artifact exports
   - Logs and audit traces

This design preserves the current repository structure while introducing RC2-specific concerns: autonomy, queue-driven execution, event-driven coordination, and feedback-driven learning.

---

## 2. Every core AI module

### 2.1 Trend Discovery AI
Responsibilities:
- Discover YouTube trends and topic opportunities
- Monitor platform signals and competitor activity
- Score topic potential by profitability, freshness, and fit

Outputs:
- candidate topics
- trend score
- topic ranking
- watchability forecasts

### 2.2 Research AI
Responsibilities:
- Gather factual and contextual research for topics
- Build structured knowledge packs
- Validate sources and synthesise briefing materials

Outputs:
- research briefs
- references
- fact checks
- source ledger

### 2.3 Script AI
Responsibilities:
- Generate scripts from research briefs
- Produce narrative structures, hooks, pacing, and CTA variants
- Support multiple formats and tones

Outputs:
- script drafts
- scene outlines
- voice cues
- metadata cues

### 2.4 Voice AI
Responsibilities:
- Generate narration and voiceover assets
- Select voice profiles and style settings
- Create voice-ready audio tracks

Outputs:
- narration files
- audio variants
- timing alignment files

### 2.5 Visual AI
Responsibilities:
- Generate or select visuals for scenes
- Produce thumbnails, B-rolls, overlays, and supporting assets
- Match visuals to the script and pacing

Outputs:
- image/video assets
- scene visual packs
- thumbnail candidates

### 2.6 Editing AI
Responsibilities:
- Assemble video sequences into complete videos
- Apply cuts, pacing, captions, transitions, and structure
- Produce draft edits and publish-ready versions

Outputs:
- edit drafts
- final video files
- subtitle tracks
- caption files

### 2.7 Thumbnail AI
Responsibilities:
- Create thumbnail variants
- Optimize for click-through potential and brand fit
- Evaluate candidate performance signals

Outputs:
- thumbnail files
- thumbnail scores
- selection recommendations

### 2.8 SEO AI
Responsibilities:
- Prepare title, description, tags, hashtags, keywords, and metadata
- Optimize for discoverability and channel consistency

Outputs:
- SEO metadata bundle
- title variants
- description variants
- tags and hashtags

### 2.9 Publishing AI
Responsibilities:
- Prepare upload payloads for YouTube
- Validate compliance and metadata completeness
- Trigger publishing workflow

Outputs:
- upload job payloads
- publishing status events
- post-publish validation artifacts

### 2.10 Analytics AI
Responsibilities:
- Monitor performance after publication
- Track CTR, retention, watch time, audience behavior, and revenue signals
- Report anomalies and opportunities

Outputs:
- performance summary
- insights
- optimization suggestions

### 2.11 Learning AI
Responsibilities:
- Learn from analytics outcomes
- Update generation preferences and content strategy rules
- Improve future topic selection and asset generation

Outputs:
- learned heuristics
- strategy updates
- model preference profiles

### 2.12 Director AI (RC2 role)
Responsibilities:
- Coordinate all modules in the pipeline
- Enforce state transitions and readiness rules
- Maintain global project state and decisions
- Escalate unresolved issues to the operator

Outputs:
- project state
- stage readiness
- blocking issues
- proposed next action

---

## 3. Responsibilities of each module

Each module owns one domain of execution and produces structured artifacts that feed downstream stages. The modules do not directly own the entire workflow; Director AI coordinates them.

Module responsibility mapping:
- Trend Discovery AI: identify opportunity
- Research AI: create evidence base
- Script AI: create narrative plan
- Voice AI: create spoken delivery
- Visual AI: create visual assets
- Editing AI: assemble final video
- Thumbnail AI: create click-through assets
- SEO AI: create publication metadata
- Publishing AI: publish to YouTube
- Analytics AI: observe results
- Learning AI: improve future behavior
- Director AI: supervise and orchestrate everything

---

## 4. Data flow between modules

The RC2 pipeline should be treated as a directed workflow:

1. Trend Discovery AI produces topic candidates.
2. Research AI enriches the chosen topic into a knowledge brief.
3. Script AI converts the brief into a script structure.
4. Voice AI produces narration tied to script timing.
5. Visual AI produces scene assets and thumbnails.
6. Editing AI composes the final video and subtitle assets.
7. SEO AI generates metadata and upload packaging.
8. Publishing AI uploads to YouTube.
9. Analytics AI observes performance.
10. Learning AI updates model preferences and future strategies.

Each stage writes structured artifacts into the shared project database and to the asset store. Downstream stages may consume prior artifacts as input and may also emit issues or feedback to Director AI.

Example flow:

Topic -> Research Brief -> Script -> Voice Track -> Visual Assets -> Edit -> Thumbnail -> SEO Metadata -> Publish -> Analytics -> Learning

---

## 5. Internal event system

RC2 should keep the existing event-driven style but make it more explicit and more scalable.

Core event categories:
- lifecycle events
- module completion events
- module failure events
- state transition events
- queue events
- publish events
- analytics events
- learning events

Suggested event types:
- PROJECT_CREATED
- TOPIC_SELECTED
- RESEARCH_COMPLETED
- SCRIPT_READY
- VOICE_READY
- VISUAL_READY
- EDIT_READY
- THUMBNAIL_READY
- SEO_READY
- PUBLISHED
- ANALYTICS_RECEIVED
- LEARNING_UPDATED
- PROJECT_FAILED
- PROJECT_RETRY_SCHEDULED

The event bus remains the control backbone for the system. Director AI consumes these events to update project state and decide the next action.

---

## 6. Shared project database

The existing SQLite database remains the shared state layer. RC2 extends it with additional tables for:

- projects
- content_briefs
- topics
- research_items
- scripts
- voice_assets
- visual_assets
- edits
- thumbnails
- seo_metadata
- upload_jobs
- analytics_snapshots
- learning_profiles
- pipeline_runs
- worker_jobs
- state_history
- module_status
- approvals
- errors
- retries

The project database remains the source of truth for status, history, and auditability. Files and media remain stored in the workspace asset tree while database rows point to them.

---

## 7. Asset lifecycle

Each produced asset follows a standard lifecycle:

1. Draft
   - created by a module
   - stored in workspace
   - referenced in database

2. Reviewed
   - quality checks or operator inspection
   - status updated

3. Approved
   - accepted for downstream use

4. Published
   - uploaded or released

5. Archived
   - retained for audit and reuse

6. Retired
   - superseded by a better asset

Asset state should be versioned to preserve iteration history.

---

## 8. Pipeline lifecycle

The RC2 pipeline lifecycle is:

1. Intake
   - topic discovery and selection

2. Research
   - gather factual material

3. Production
   - script, narration, visuals, editing

4. Packaging
   - thumbnails, metadata, uploads

5. Publish
   - YouTube upload and release

6. Observe
   - analytics collection

7. Learn
   - feedback loop and future improvement

Each lifecycle stage is state-driven and may be re-entered if a failure or retry occurs.

---

## 9. Operator dashboard

The dashboard remains the operator control surface. In RC2 it should provide:

- active projects
- pipeline health
- queue overview
- module status
- approvals required
- failed jobs and retries
- publish status
- analytics summary
- learning insight feed

The operator can:
- approve or reject generated assets
- pause or resume automation
- change strategy preferences
- inspect event history
- manually trigger recovery actions

---

## 10. Plugin architecture

RC2 should support a plugin-based extension model for external capabilities without changing the core system.

Plugin categories:
- trend providers
- research providers
- script providers
- voice providers
- visual providers
- editing providers
- analytics providers
- publishing providers

The core architecture should define a standard plugin interface:
- register capability
- receive job payload
- produce artifact output
- emit events
- report success or failure

This allows local-first providers and external API providers to coexist.

---

## 11. API architecture

The API layer should expose two types of interfaces:

1. Internal API
   - used by the local runtime and background workers
   - synchronous and asynchronous operations
   - project state access
   - queue management

2. External API
   - used by plugins, connectors, and optional remote services
   - should be thin and contract-based
   - support authentication, retries, and audit logs

Suggested API domains:
- projects
- jobs
- assets
- approvals
- analytics
- publishing
- plugins
- health

---

## 12. Background workers

RC2 must use background workers to execute long running or asynchronous actions. Workers should be responsible for:

- trend polling
- research generation
- script generation
- voice generation
- visual generation
- editing jobs
- thumbnail generation
- SEO packaging
- upload jobs
- analytics pull requests
- learning updates

Workers should consume queued jobs and emit structured completion or failure events.

---

## 13. Queue system

A queue system is required for RC2 reliability.

Suggested queues:
- research_queue
- generation_queue
- review_queue
- publish_queue
- analytics_queue
- learning_queue
- retry_queue

Each queued job should contain:
- project_id
- module_name
- payload
- priority
- retries
- deadline
- callback event

The queue system should support:
- retry on failure
- backoff scheduling
- parallel execution where safe
- dead-letter handling for unrecoverable jobs

---

## 14. State machine

RC2 should use a formal state machine for every project.

Suggested project states:
- NEW
- TREND_DISCOVERED
- RESEARCH_READY
- SCRIPT_READY
- VOICE_READY
- VISUAL_READY
- EDIT_READY
- THUMBNAIL_READY
- SEO_READY
- PUBLISHED
- ANALYTICS_READY
- LEARNING_UPDATED
- FAILED

Transitions must be validated. Invalid transitions should be rejected and logged.

Each state change should write to:
- project state row
- state history table
- event bus

---

## 15. Future scaling strategy

The RC2 architecture should be capable of scaling over time without a redesign.

Near-term scaling plan:
- keep the modular monolith as the core runtime
- introduce async workers and queues
- isolate long-running operations behind worker processes
- introduce object storage for media assets
- add caching and indexing for faster lookups

Medium-term scaling plan:
- split worker pools by domain
- add distributed job execution
- move analytics and learning jobs to dedicated services
- support multi-project parallelism

Long-term scaling plan:
- introduce service-oriented boundaries for publishing, analytics, and learning
- support multi-region deployment
- add federated model and content strategy memory

---

## 16. Multi-channel support

RC2 must be designed for more than YouTube.

Planned channels:
- YouTube
- TikTok
- Instagram Reels
- Shorts
- Podcast distribution
- Web publishing

The architecture should support a channel adapter layer so each channel can define:
- upload requirements
- metadata conventions
- formatting rules
- publishing callbacks
- analytics schema

---

## 17. Quality control pipeline

RC2 should include a structured quality control pipeline before publication.

Suggested QC stages:
- factual validation
- script validation
- voice quality validation
- visual asset validation
- edit sanity checks
- metadata validation
- platform policy validation

QC results should be stored in the database and linked to the relevant asset or project.

---

## 18. Recovery and retry strategy

Failures must be handled without losing state.

Recovery policy:
- record the failure in the project history
- mark the job for retry with exponential backoff
- preserve the last successful artifact
- allow manual intervention when needed
- escalate only after a bounded number of retries

The system should support:
- retryable failures
- non-retryable failures
- operator override
- replay from the last successful stage

---

## 19. Autonomous decision loop

The core autonomy loop is:

1. Observe current project state
2. Evaluate best next action
3. Dispatch to the appropriate module or worker
4. Collect output and validation signals
5. Update project state and emit events
6. Decide whether to continue, retry, pause, or escalate

Director AI is the decision center for this loop. The loop should become progressively more autonomous over time as the learning layer improves the scoring model.

---

## 20. Roadmap from RC1 to RC2

### RC1 foundation
- existing local-first pipeline
- Director AI orchestration
- project database and artifact exports
- operator dashboard and pipeline runtime

### RC2 Phase 1
- formal project state machine
- queue-based execution model
- event-driven workflow orchestration
- module contracts and artifact schema

### RC2 Phase 2
- topic discovery and research modules
- script and narration generation
- visual generation and editing workflow

### RC2 Phase 3
- thumbnail generation and SEO packaging
- publishing and analytics integration
- operator approvals and review workflow

### RC2 Phase 4
- learning loop and autonomous optimization
- multi-channel support
- stronger plugin architecture and scaling infrastructure

---

## Design principles

- Preserve the current architecture and codebase.
- Keep local-first operation as a default path.
- Make intelligence modules pluggable.
- Make project state explicit and auditable.
- Make automation observable by the operator.
- Keep the system capable of safe human oversight.
