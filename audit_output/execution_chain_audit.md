# ATLAS ZERO RC2 — Execution Chain Audit

Root: `C:\Users\3dtool\OneDrive\Документы\GitHub\atlas_zero1\src\az_enterprise\core`

## Canonical chain

| Module | Exists | Imported by DirectorCore | Reads JSON | Writes JSON |
|---|---:|---:|---:|---:|
| `asset_engine_rc2.py` | True | True | False | False |
| `visual_semantic_analyzer_rc2.py` | True | True | True | True |
| `event_discovery_engine_rc2.py` | True | True | True | False |
| `story_strategy_engine_rc2.py` | True | True | True | False |
| `story_engine.py` | True | True | False | True |
| `assignment_engine_rc2.py` | True | True | False | False |
| `timeline_engine_rc2.py` | True | True | True | True |
| `voice_production_engine_rc2.py` | True | False | True | True |
| `audio_composer_rc2.py` | True | False | False | False |
| `render_engine_rc2.py` | True | True | True | True |
| `quality_gate_rc2.py` | True | True | True | True |

## Missing direct imports

- `voice_production_engine_rc2.py`
- `audio_composer_rc2.py`

## Orchestrator calls

### `director_core_rc2.py`

- `DirectorCoreRC2._run_story_stage` → `VisualSemanticAnalyzerRC2` (line 221)
- `DirectorCoreRC2._run_story_stage` → `semantic_report.get` (line 226)
- `DirectorCoreRC2._run_story_stage` → `semantic_report.get` (line 227)
- `DirectorCoreRC2._run_story_stage` → `EventDiscoveryEngineRC2` (line 238)
- `DirectorCoreRC2._run_story_stage` → `event_discovery.get` (line 239)
- `DirectorCoreRC2._run_story_stage` → `StoryStrategyEngineRC2` (line 250)
- `DirectorCoreRC2._run_story_stage` → `StoryEngine` (line 278)
- `DirectorCoreRC2._run_story_stage` → `story_result.get` (line 283)
- `DirectorCoreRC2._stage_services` → `AssetEngineRC2` (line 308)
- `DirectorCoreRC2._stage_services` → `AssignmentEngineRC2` (line 310)
- `DirectorCoreRC2._stage_services` → `TimelineEngineRC2` (line 314)
- `DirectorCoreRC2._stage_services` → `RenderEngineRC2` (line 318)
- `DirectorCoreRC2._stage_services` → `RenderEngineRC2` (line 322)
- `DirectorCoreRC2._stage_services` → `QualityGateRC2` (line 326)
- `DirectorCoreRC2.run_targets` → `quality.get` (line 407)
- `DirectorCoreRC2.run_targets` → `render.get` (line 432)
- `DirectorCoreRC2.run_targets` → `render.get` (line 441)
- `DirectorCoreRC2._generate_temporal_report` → `timeline_path.exists` (line 553)
- `DirectorCoreRC2._generate_temporal_report` → `timeline_path.read_text` (line 558)
- `DirectorCoreRC2._run_supervised_targets` → `self._rewrite_timeline_duration` (line 696)
- `DirectorCoreRC2._build_supervisor_report` → `quality.get` (line 836)
- `DirectorCoreRC2._build_supervisor_report` → `self._recommended_targets_from_quality` (line 852)
- `DirectorCoreRC2._build_supervisor_report` → `quality.get` (line 871)
- `DirectorCoreRC2.default_supervisor_policy` → `QualityProfile` (line 891)

### `production_director.py`

- `ProductionDirector._build_status` → `self._extract_timeline_rows` (line 54)
- `ProductionDirector._build_status` → `self._count_timeline_media` (line 80)
- `ProductionDirector._build_status` → `self._discover_voice_path` (line 86)
- `ProductionDirector._build_status` → `self._timeline_duration` (line 101)
- `ProductionDirector._build_status` → `render_output.exists` (line 115)
- `ProductionDirector._build_status` → `render_output.is_file` (line 116)
- `ProductionDirector._build_status` → `render_validation.get` (line 148)
- `ProductionDirector._build_status` → `self._render_duration` (line 160)
- `ProductionDirector._render_duration` → `render_report.get` (line 365)
- `ProductionDirector._render_duration` → `render_report.get` (line 369)
- `ProductionDirector._render_duration` → `render_report.get` (line 366)

### `control_layer_rc2.py`

- `RC2ReadinessPlanner.evaluate` → `self.config.timeline_path.exists` (line 24)
- `RC2ReadinessPlanner.evaluate` → `self.config.master_audio_path.exists` (line 25)
- `RC2ReadinessPlanner.evaluate` → `self.config.canonical_render_path.exists` (line 26)
- `RC2ReadinessPlanner.plan` → `self.evaluate` (line 46)
- `RC2ControlLayer.build_timeline` → `TimelineEngineRC2` (line 126)
- `RC2ControlLayer.build_voice` → `VoiceProductionEngineRC2` (line 129)
- `RC2ControlLayer.render` → `self.config.timeline_path.exists` (line 144)
- `RC2ControlLayer.render` → `self.build_timeline` (line 145)
- `RC2ControlLayer.render` → `self.config.master_audio_path.exists` (line 147)
- `RC2ControlLayer.render` → `self.build_voice` (line 148)
- `RC2ControlLayer.render` → `RenderEngineRC2` (line 150)
- `RC2ControlLayer.render` → `render_report.get` (line 159)
- `RC2ControlLayer.render` → `render_report.get` (line 160)
- `RC2ControlLayer.run` → `self.config.timeline_path.exists` (line 175)
- `RC2ControlLayer.run` → `self.build_timeline` (line 176)
- `RC2ControlLayer.run` → `self.config.master_audio_path.exists` (line 178)
- `RC2ControlLayer.run` → `self.build_voice` (line 179)
- `RC2ControlLayer.run` → `RenderEngineRC2` (line 181)
- `RC2ControlLayer.run` → `render_report.get` (line 188)
- `RC2ControlLayer.run` → `render_report.get` (line 198)
