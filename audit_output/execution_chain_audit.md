# ATLAS ZERO RC2 — Execution Chain Audit

Root: `C:\Users\3dtool\OneDrive\Документы\GitHub\atlas_zero1\src\az_enterprise\core`

## Canonical chain

| Module | Exists | Imported by DirectorCore | Reads JSON | Writes JSON |
|---|---:|---:|---:|---:|
| `asset_engine_rc2.py` | True | True | False | False |
| `visual_semantic_analyzer_rc2.py` | True | False | False | False |
| `event_discovery_engine_rc2.py` | True | False | True | False |
| `story_strategy_engine_rc2.py` | True | False | True | False |
| `story_engine.py` | True | True | False | True |
| `assignment_engine_rc2.py` | True | True | False | False |
| `timeline_engine_rc2.py` | True | True | True | True |
| `voice_production_engine_rc2.py` | True | False | True | True |
| `audio_composer_rc2.py` | True | False | False | False |
| `render_engine_rc2.py` | True | True | True | True |
| `quality_gate_rc2.py` | True | True | True | True |

## Missing direct imports

- `visual_semantic_analyzer_rc2.py`
- `event_discovery_engine_rc2.py`
- `story_strategy_engine_rc2.py`
- `voice_production_engine_rc2.py`
- `audio_composer_rc2.py`

## Orchestrator calls

### `director_core_rc2.py`

- `DirectorCoreRC2._run_story_stage` → `StoryEngine` (line 211)
- `DirectorCoreRC2._stage_services` → `AssetEngineRC2` (line 224)
- `DirectorCoreRC2._stage_services` → `AssignmentEngineRC2` (line 226)
- `DirectorCoreRC2._stage_services` → `TimelineEngineRC2` (line 230)
- `DirectorCoreRC2._stage_services` → `RenderEngineRC2` (line 234)
- `DirectorCoreRC2._stage_services` → `QualityGateRC2` (line 238)
- `DirectorCoreRC2.run_targets` → `quality.get` (line 300)
- `DirectorCoreRC2._generate_temporal_report` → `timeline_path.exists` (line 365)
- `DirectorCoreRC2._generate_temporal_report` → `timeline_path.read_text` (line 370)
- `DirectorCoreRC2._run_supervised_targets` → `self._rewrite_timeline_duration` (line 508)
- `DirectorCoreRC2._build_supervisor_report` → `quality.get` (line 647)
- `DirectorCoreRC2._build_supervisor_report` → `self._recommended_targets_from_quality` (line 663)
- `DirectorCoreRC2._build_supervisor_report` → `quality.get` (line 682)
- `DirectorCoreRC2.default_supervisor_policy` → `QualityProfile` (line 702)

### `pipeline_runtime.py`

- `PipelineRunManager._step_scan_assets` → `AssetIntelligence` (line 234)
- `PipelineRunManager._step_visual_intelligence` → `analyze_assets` (line 245)
- `PipelineRunManager._step_build_shots` → `StoryEngine` (line 249)
- `PipelineRunManager._step_story_runtime` → `StoryEngineRuntime` (line 253)
- `PipelineRunManager._step_director_ai` → `assign_assets` (line 259)
- `PipelineRunManager._step_quality` → `QualityCenter` (line 279)
- `PipelineRunManager._step_timeline_package` → `export_timeline_package` (line 285)
- `PipelineRunManager._step_timeline_package` → `TimelineStudio` (line 285)
- `PipelineRunManager._step_native_timeline` → `NativeTimelineModel` (line 288)
- `PipelineRunManager._step_timeline_viewer_2` → `TimelineViewer2` (line 297)
- `PipelineRunManager.run` → `self._event` (line 452)
- `PipelineRunManager.run` → `self._event` (line 469)
- `PipelineRunManager.run` → `self._event` (line 490)
- `PipelineRunManager.run` → `self._event` (line 501)
- `PipelineRunManager.run` → `self._event` (line 513)
- `PipelineRunManager.run` → `self._event` (line 526)
- `PipelineRunManager.run` → `self._event` (line 538)

### `media_orchestrator.py`

- `run_project` → `EventBus` (line 37)
- `run_project.execute_stage` → `event_bus.emit` (line 73)
- `_run_stage_adapter` → `TimelineEngineRC2` (line 121)
- `_run_stage_adapter` → `RenderEngineRC2` (line 122)
- `_run_stage_adapter` → `render.get` (line 128)
- `_run_stage_adapter` → `render.get` (line 129)

### `workflow.py`

- `WorkflowEngine.__init__` → `EventBus` (line 41)
- `WorkflowEngine.run_pipeline` → `AssetIntelligence` (line 53)
- `WorkflowEngine.run_pipeline` → `analyze_assets` (line 54)
- `WorkflowEngine.run_pipeline` → `StoryEngine` (line 55)
- `WorkflowEngine.run_pipeline` → `assign_assets` (line 56)
- `WorkflowEngine.run_pipeline` → `QualityCenter` (line 61)
- `WorkflowEngine.run_pipeline` → `QualityCenter` (line 62)
- `WorkflowEngine.run_pipeline` → `export_timeline_package` (line 63)
- `WorkflowEngine.run_pipeline` → `TimelineStudio` (line 63)
- `WorkflowEngine.run_pipeline` → `FinalTimelineViewer` (line 72)
- `WorkflowEngine.run_pipeline` → `NativeTimelineModel` (line 78)
- `WorkflowEngine.run_pipeline` → `TimelineViewer2` (line 85)
- `WorkflowEngine.export_all` → `timeline_csv.open` (line 97)

### `production_director.py`

- `ProductionDirector._build_status` → `asset_inventory.get` (line 47)
- `ProductionDirector._build_status` → `render_manifest.get` (line 58)

### `control_layer_rc2.py`

- `RC2ReadinessPlanner.evaluate` → `self.config.timeline_path.exists` (line 21)
- `RC2ReadinessPlanner.evaluate` → `self.config.canonical_render_path.exists` (line 22)
- `RC2ReadinessPlanner.plan` → `self.evaluate` (line 42)
- `RC2ControlLayer.build_timeline` → `TimelineEngineRC2` (line 95)
- `RC2ControlLayer.render` → `self.config.timeline_path.exists` (line 99)
- `RC2ControlLayer.render` → `self.build_timeline` (line 100)
- `RC2ControlLayer.render` → `RenderEngineRC2` (line 101)
- `RC2ControlLayer.render` → `render_report.get` (line 108)
- `RC2ControlLayer.render` → `render_report.get` (line 109)
