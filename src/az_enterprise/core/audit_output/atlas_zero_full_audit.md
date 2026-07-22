# ATLAS ZERO — Full Repository Audit

Generated: `2026-07-22T19:49:14.997170+00:00`
Root: `C:\Users\3dtool\OneDrive\Документы\GitHub\atlas_zero1\src\az_enterprise\core`

## Executive summary

- Python modules: **94**
- Python lines: **22021**
- Syntax errors: **3**
- Duplicate public symbols: **23**
- JSON readers: **13**
- JSON writers: **44**

## Critical findings

- DirectorCoreRC2 does not import visual_semantic_analyzer_rc2; upstream RC2 chain may be disconnected.
- DirectorCoreRC2 does not import event_discovery_engine_rc2; upstream RC2 chain may be disconnected.
- DirectorCoreRC2 does not import story_strategy_engine_rc2; upstream RC2 chain may be disconnected.

## Syntax errors

- `dependency_resolver_alpha31.py:1:1` — invalid non-printable character U+FEFF
- `module_registry_alpha31.py:1:1` — invalid non-printable character U+FEFF
- `story_engine.py:1:1` — invalid non-printable character U+FEFF

## Duplicate public symbols

- **function `run`** × 27: `agents\agent_registry.py`, `agents\base_agent.py`, `asset_engine_rc2.py`, `assignment_engine_rc2.py`, `assignment_policy_rc2.backup.py`, `assignment_policy_rc2.py`, `audio_composer_rc2.py`, `audio_renderer_rc2.py`, `director_core_rc2.py`, `director_supervisor_alpha292.py`, `event_discovery_engine_rc2.py`, `execution_graph_alpha29.py`, `live_api_test_suite.py`, `mux_engine_rc2.py`, `narrative_writer_rc2.py`, `pipeline_runtime.py`, `preflight.py`, `production_director.py`, `production_script_regenerator_rc2.py`, `quality_gate_rc2.py`, `render_engine_rc2.py`, `story_strategy_engine_rc2.py`, `test_center.py`, `timeline_engine_rc2.py`, `visual_asset_registrar.py`, `visual_renderer_rc2.py`, `voice_production_engine_rc2.py`
- **function `build`** × 16: `audio_timeline_rc2.py`, `camera_motion_rc2.py`, `capcut_bridge.py`, `cv_review_board.py`, `editorial_package_rc2.py`, `final_assembly_pack.py`, `final_timeline_viewer.py`, `local_autopilot.py`, `montage_workbench.py`, `native_timeline.py`, `native_viewer_pro.py`, `production_script_assembler_rc2.py`, `recommendation_engine_alpha28.py`, `story_engine_runtime.py`, `timeline_viewer_2.py`, `transition_engine_rc2.py`
- **function `to_dict`** × 14: `agents\base_agent.py`, `agents\task_model.py`, `audio_timeline_rc2.py`, `camera_motion_rc2.py`, `ducking_engine_rc2.py`, `event_discovery_engine_rc2.py`, `loudness_engine_rc2.py`, `narrative_writer_rc2.py`, `openai_adapter_rc2.py`, `project_model_alpha301.py`, `render_engine_rc2.py`, `story_strategy_contract_rc2.py`, `transition_engine_rc2.py`, `visual_understanding_contract_rc2.py`
- **function `validate`** × 9: `audio_timeline_rc2.py`, `camera_motion_rc2.py`, `editorial_package_rc2.py`, `narrative_writer_rc2.py`, `production_script_assembler_rc2.py`, `project_model_alpha301.py`, `story_strategy_contract_rc2.py`, `transition_engine_rc2.py`, `visual_understanding_contract_rc2.py`
- **function `analyze`** × 4: `cv_model.py`, `director_ai_runtime.py`, `postproduction_quality_rc2.py`, `visual_semantic_analyzer_rc2.py`
- **function `evaluate`** × 4: `control_layer_rc2.py`, `director_policy_alpha293.py`, `franklin_e2e_runtime.py`, `quality.py`
- **function `add`** × 3: `preflight.py`, `quality_gate_rc2.py`, `test_center.py`
- **function `live_enabled`** × 3: `live_api_layer.py`, `live_connectors.py`, `openai_adapter_rc2.py`
- **function `score`** × 3: `assignment_policy_rc2.backup.py`, `assignment_policy_rc2.py`, `director_policy_alpha293.py`
- **class `AssignmentPolicyRC2`** × 2: `assignment_policy_rc2.backup.py`, `assignment_policy_rc2.py`
- **class `Task`** × 2: `agents\task_model.py`, `project_model_alpha301.py`
- **function `build_filter`** × 2: `ducking_engine_rc2.py`, `loudness_engine_rc2.py`
- **function `build_profile`** × 2: `camera_motion_rc2.py`, `transition_engine_rc2.py`
- **function `export_report`** × 2: `live_api_layer.py`, `live_connectors.py`
- **function `get`** × 2: `module_registry_alpha29.py`, `project_context_alpha29.py`
- **function `normalize`** × 2: `camera_motion_rc2.py`, `transition_engine_rc2.py`
- **function `one`** × 2: `database.py`, `franklin_e2e_runtime.py`
- **function `plan`** × 2: `control_layer_rc2.py`, `director_core_rc2.py`
- **function `register`** × 2: `agents\agent_registry.py`, `module_registry_alpha29.py`
- **function `rows`** × 2: `database.py`, `timeline_studio.py`
- **function `run_project`** × 2: `director_supervisor_alpha292.py`, `media_orchestrator.py`
- **function `tc`** × 2: `acceptance_center.py`, `timeline_studio.py`
- **function `utc_now`** × 2: `production_state_rc2.py`, `project_model_alpha301.py`

## Pipeline stage coverage

### asset
- `acceptance_center.py`
- `agents\agent_registry.py`
- `asset_engine_rc2.py`
- `asset_intelligence.py`
- `assignment_policy_rc2.backup.py`
- `assignment_policy_rc2.py`
- `audio_renderer_rc2.py`
- `audio_timeline_rc2.py`
- `capcut_bridge.py`
- `cv_model.py`
- `cv_review_board.py`
- `database.py`
- `director_ai.py`
- `director_ai_runtime.py`
- `director_core_rc2.py`
- `editorial_package_rc2.py`
- `event_discovery_engine_rc2.py`
- `final_assembly_pack.py`
- `final_timeline_viewer.py`
- `franklin_e2e_runtime.py`
- `generated_asset_store_rc2.py`
- `live_api_layer.py`
- `local_autopilot.py`
- `montage_workbench.py`
- `narrative_writer_rc2.py`
- `native_timeline.py`
- `native_viewer_pro.py`
- `native_viewer_rc.py`
- `operator_console.py`
- `pipeline_runtime.py`
- `postproduction_quality_rc2.py`
- `preflight.py`
- `production_director.py`
- `production_script_assembler_rc2.py`
- `production_state.py`
- `project_config_rc2.py`
- `project_context_alpha29.py`
- `project_model_alpha301.py`
- `quality.py`
- `quality_gate_rc2.py`
- `recommendation_engine_alpha28.py`
- `release_gate.py`
- `render_engine_rc2.py`
- `story_engine_runtime.py`
- `story_strategy_contract_rc2.py`
- `story_strategy_engine_rc2.py`
- `test_center.py`
- `timeline_engine_rc2.py`
- `timeline_studio.py`
- `timeline_viewer_2.py`
- `visual_asset_registrar.py`
- `visual_dynamics_alpha272.py`
- `visual_intelligence.py`
- `visual_renderer_rc2.py`
- `visual_semantic_analyzer_rc2.py`
- `visual_understanding_contract_rc2.py`
- `workflow.py`
- `working_state_auditor.py`

### assignment
- `assignment_engine_rc2.py`
- `assignment_policy_rc2.backup.py`
- `assignment_policy_rc2.py`
- `cv_model.py`
- `director_ai.py`
- `director_ai_runtime.py`
- `director_core_rc2.py`
- `editorial_package_rc2.py`
- `final_timeline_viewer.py`
- `project_config_rc2.py`
- `visual_asset_registrar.py`

### audio
- `acceptance_center.py`
- `asset_intelligence.py`
- `audio_composer_rc2.py`
- `audio_renderer_rc2.py`
- `audio_timeline_rc2.py`
- `mux_engine_rc2.py`
- `native_timeline.py`
- `paths.py`
- `pipeline_runtime.py`
- `postproduction_quality_rc2.py`
- `preflight.py`
- `production_director.py`
- `project_config_rc2.py`
- `render_engine_rc2.py`
- `voice_production_engine_rc2.py`

### director
- `acceptance_center.py`
- `asset_engine_rc2.py`
- `assignment_engine_rc2.py`
- `assignment_policy_rc2.backup.py`
- `assignment_policy_rc2.py`
- `control_layer_rc2.py`
- `database.py`
- `director_ai.py`
- `director_ai_runtime.py`
- `director_core_rc2.py`
- `director_knowledge_base_rc2.py`
- `director_policy_alpha293.py`
- `director_policy_evaluator_alpha293.py`
- `director_supervisor_alpha292.py`
- `final_timeline_viewer.py`
- `integrations.py`
- `montage_workbench.py`
- `native_timeline.py`
- `pipeline_runtime.py`
- `postproduction_quality_rc2.py`
- `production_director.py`
- `project_config_rc2.py`
- `quality.py`
- `rc2_cli.py`
- `runtime_governance_rc2.py`
- `story_engine_runtime.py`
- `timeline_engine_rc2.py`
- `timeline_studio.py`
- `workflow.py`

### event
- `acceptance_center.py`
- `agents\__init__.py`
- `agents\event_bus.py`
- `api_gateway.py`
- `asset_intelligence.py`
- `assignment_policy_rc2.backup.py`
- `assignment_policy_rc2.py`
- `audio_composer_rc2.py`
- `audio_renderer_rc2.py`
- `audio_timeline_rc2.py`
- `cv_model.py`
- `database.py`
- `director_ai.py`
- `director_ai_runtime.py`
- `editorial_package_rc2.py`
- `event_discovery_engine_rc2.py`
- `events.py`
- `final_timeline_viewer.py`
- `integrations.py`
- `live_api_layer.py`
- `live_connectors.py`
- `local_autopilot.py`
- `media_orchestrator.py`
- `montage_workbench.py`
- `narrative_writer_rc2.py`
- `native_viewer_rc.py`
- `operator_console.py`
- `pipeline_runtime.py`
- `preflight.py`
- `production_state.py`
- `project_context_alpha29.py`
- `project_profiles_alpha273.py`
- `project_state.py`
- `quality.py`
- `release_gate.py`
- `render_engine_rc2.py`
- `story_strategy_contract_rc2.py`
- `story_strategy_engine_rc2.py`
- `timeline_studio.py`
- `visual_intelligence.py`
- `visual_semantic_analyzer_rc2.py`
- `visual_understanding_contract_rc2.py`
- `workflow.py`
- `working_state_auditor.py`

### quality
- `acceptance_center.py`
- `asset_intelligence.py`
- `assignment_policy_rc2.backup.py`
- `assignment_policy_rc2.py`
- `capcut_bridge.py`
- `cv_model.py`
- `database.py`
- `director_ai.py`
- `director_ai_runtime.py`
- `director_core_rc2.py`
- `director_policy_alpha293.py`
- `director_policy_evaluator_alpha293.py`
- `final_timeline_viewer.py`
- `integrations.py`
- `native_timeline.py`
- `pipeline_runtime.py`
- `postproduction_quality_rc2.py`
- `production_state.py`
- `production_state_rc2.py`
- `project_config_rc2.py`
- `quality.py`
- `quality_gate_rc2.py`
- `recommendation_engine_alpha28.py`
- `render_engine_rc2.py`
- `runtime_governance_rc2.py`
- `story_engine_runtime.py`
- `test_center.py`
- `timeline_engine_rc2.py`
- `visual_asset_registrar.py`
- `visual_intelligence.py`
- `visual_semantic_analyzer_rc2.py`
- `workflow.py`

### render
- `audio_composer_rc2.py`
- `audio_renderer_rc2.py`
- `control_layer_rc2.py`
- `cv_model.py`
- `director_core_rc2.py`
- `media_orchestrator.py`
- `mux_engine_rc2.py`
- `native_viewer_rc.py`
- `preflight.py`
- `production_director.py`
- `project_config_rc2.py`
- `quality_gate_rc2.py`
- `render_engine_rc2.py`
- `visual_renderer_rc2.py`
- `voice_production_engine_rc2.py`

### semantic
- `assignment_policy_rc2.backup.py`
- `assignment_policy_rc2.py`
- `database.py`
- `director_core_rc2.py`
- `editorial_package_rc2.py`
- `event_discovery_engine_rc2.py`
- `generated_asset_store_rc2.py`
- `project_config_rc2.py`
- `quality_gate_rc2.py`
- `visual_semantic_analyzer_rc2.py`

### story
- `acceptance_center.py`
- `assignment_policy_rc2.backup.py`
- `assignment_policy_rc2.py`
- `capcut_bridge.py`
- `database.py`
- `director_ai.py`
- `director_ai_runtime.py`
- `director_core_rc2.py`
- `director_knowledge_base_rc2.py`
- `director_supervisor_alpha292.py`
- `editorial_package_rc2.py`
- `event_discovery_engine_rc2.py`
- `final_assembly_pack.py`
- `final_timeline_viewer.py`
- `franklin_e2e_runtime.py`
- `integrations.py`
- `montage_workbench.py`
- `narrative_writer_rc2.py`
- `native_timeline.py`
- `native_viewer_pro.py`
- `native_viewer_rc.py`
- `pipeline_runtime.py`
- `production_director.py`
- `project_config_rc2.py`
- `project_profiles_alpha273.py`
- `quality_gate_rc2.py`
- `render_engine_rc2.py`
- `runtime_governance_rc2.py`
- `story_engine_runtime.py`
- `story_strategy_contract_rc2.py`
- `story_strategy_engine_rc2.py`
- `timeline_engine_rc2.py`
- `timeline_studio.py`
- `visual_semantic_analyzer_rc2.py`
- `visual_understanding_contract_rc2.py`
- `workflow.py`

### story_strategy
- `director_core_rc2.py`
- `editorial_package_rc2.py`
- `project_config_rc2.py`
- `story_strategy_contract_rc2.py`
- `story_strategy_engine_rc2.py`

### timeline
- `audio_composer_rc2.py`
- `audio_renderer_rc2.py`
- `audio_timeline_rc2.py`
- `capcut_bridge.py`
- `control_layer_rc2.py`
- `cv_model.py`
- `director_core_rc2.py`
- `final_assembly_pack.py`
- `final_timeline_viewer.py`
- `media_orchestrator.py`
- `montage_workbench.py`
- `native_timeline.py`
- `native_viewer_pro.py`
- `native_viewer_rc.py`
- `operator_console.py`
- `pipeline_runtime.py`
- `postproduction_quality_rc2.py`
- `production_director.py`
- `project_config_rc2.py`
- `project_context_alpha29.py`
- `quality.py`
- `quality_gate_rc2.py`
- `recommendation_engine_alpha28.py`
- `release_gate.py`
- `render_engine_rc2.py`
- `test_center.py`
- `timeline_engine_rc2.py`
- `timeline_studio.py`
- `timeline_viewer_2.py`
- `transition_engine_rc2.py`
- `visual_dynamics_alpha272.py`
- `workflow.py`
- `working_state_auditor.py`

### visual
- `acceptance_center.py`
- `agents\agent_registry.py`
- `assignment_policy_rc2.backup.py`
- `assignment_policy_rc2.py`
- `audio_composer_rc2.py`
- `capcut_bridge.py`
- `cv_model.py`
- `cv_review_board.py`
- `database.py`
- `director_ai.py`
- `director_ai_runtime.py`
- `director_core_rc2.py`
- `editorial_package_rc2.py`
- `event_discovery_engine_rc2.py`
- `final_assembly_pack.py`
- `final_timeline_viewer.py`
- `generated_asset_store_rc2.py`
- `integrations.py`
- `local_autopilot.py`
- `media_orchestrator.py`
- `montage_workbench.py`
- `mux_engine_rc2.py`
- `narrative_writer_rc2.py`
- `native_timeline.py`
- `native_viewer_pro.py`
- `native_viewer_rc.py`
- `operator_console.py`
- `pipeline_runtime.py`
- `postproduction_quality_rc2.py`
- `production_director.py`
- `production_script_assembler_rc2.py`
- `production_state.py`
- `production_visual_manager.py`
- `project_profiles_alpha273.py`
- `project_state.py`
- `quality.py`
- `recommendation_engine_alpha28.py`
- `release_gate.py`
- `render_engine_rc2.py`
- `story_engine_runtime.py`
- `story_strategy_contract_rc2.py`
- `story_strategy_engine_rc2.py`
- `timeline_engine_rc2.py`
- `timeline_studio.py`
- `timeline_viewer_2.py`
- `visual_asset_registrar.py`
- `visual_dynamics_alpha272.py`
- `visual_intelligence.py`
- `visual_renderer_rc2.py`
- `visual_semantic_analyzer_rc2.py`
- `visual_understanding_contract_rc2.py`
- `workflow.py`

### voice
- `agents\agent_registry.py`
- `asset_intelligence.py`
- `audio_renderer_rc2.py`
- `audio_timeline_rc2.py`
- `director_ai.py`
- `ducking_engine_rc2.py`
- `editorial_package_rc2.py`
- `integrations.py`
- `media_orchestrator.py`
- `narrative_writer_rc2.py`
- `production_director.py`
- `production_script_assembler_rc2.py`
- `production_script_regenerator_rc2.py`
- `project_config_rc2.py`
- `project_state.py`
- `render_engine_rc2.py`
- `timeline_engine_rc2.py`
- `timeline_viewer_2.py`
- `voice_production_engine_rc2.py`

## Compile check

- Return code: `0`
```text

```

## Tests

- State: **SKIPPED**
```text

```

## Git state

- Branch: `feature/rc2-duration-authority-2.6`
- HEAD: `daa0440d5508f9129aa15e15000e77763f439fad`
```text
D ../../../ATLAS_ZERO_RC1_ALPHA_3_1.patch
 D ../../../paceexportsfranklinmovie_runtime_rc1manual_edit_package.md
 M ../cli.py
 M asset_intelligence.py
 M assignment_policy_rc2.py
 M cv_model.py
 M director_core_rc2.py
 M director_policy_evaluator_alpha293.py
 M director_supervisor_alpha292.py
 M media_orchestrator.py
 D movie_runtime_rc1.py
 D movie_runtime_rc1.py.backup_duration_shots_20260712_202102
 D movie_runtime_rc1.py.backup_shot_mode_20260712_201034
 M narrative_writer_rc2.py
 M pipeline_runtime.py
 M project_config_rc2.py
 D rc1_completion_planner.py
 M release_gate.py
 D render_engine_rc1.py
 D render_engine_rc1.py.backup_before_master_audio
 D render_engine_rc1.py.backup_before_nostdin
 M render_engine_rc2.py
 M timeline_engine_rc2.py
 M workflow.py
 M ../ui/__pycache__/app.cpython-313.pyc
 M ../ui/app.py
 D ../../../tests/test_movie_runtime_rc1.py
 D ../../../tests/test_movie_runtime_rc1_assets.py
 D ../../../tests/test_render_engine_rc1.py
 D ../../../tools/franklin_autopilot.py
 D ../../../tools/media_factory_rc1.py
 D ../../../tools/render_franklin_roughcut.py
 D ../../../tools/repair_semantic_asset_ids.py
 D ../../../tools/semantic_director_v1.py
 D ../../../tools/semantic_director_v1_1_multimedia.py
 D ../../../tools/semantic_director_v1_2_temporal.py
 D ../../../tools/visual_intelligence_v1.py
?? ../../../APPLY_PHASE5.py
?? ../../../alpha26_full_pytest.txt
?? ../../../apply_director_knowledge_base_rc2.py
?? ../../../apply_director_supervisor_rc2_fix.py
?? ../../../atlas_zero_full_audit.py
?? ../../../atlas_zero_phase5_native_camera_motion/
?? ../../../atlas_zero_phase6_native_transition_engine/
?? ../../../atlas_zero_phase7_native_audio_composer/
?? ../../../atlas_zero_phase8_rc2_control_layer/
?? ../../../atlas_zero_phase9_production_cleanup/
?? ../../../atlas_zero_rc2_final_audit/
?? ../../../atlas_zero_rc2_finalization/
?? ../../../atlas_zero_rc2_production_audit/
?? ../../../atlas_zero_remove_rc1/
?? ../../../audit_output/
?? ../../../audit_rc2_production.zip
?? ../../../audit_rc2_production/
?? ../../../audit_rc2_production_contour.ps1
?? ../../../collect_diagnostic.txt
?? ../../../collect_errors.txt
?? ../../../collect_stderr.txt
?? ../../../collect_stdout.txt
?? ../../../editorial_intelligence_source.txt
?? ../../../hogueras_duration_audit.txt
?? ../../../phase5_payload/
?? audio_composer_rc2.py
?? audio_renderer_rc2.py
?? audio_timeline_rc2.py
?? camera_motion_rc2.py
?? control_layer_rc2.py
?? director_knowledge_base_rc2.py
?? director_policy_evaluator_alpha293.py.before_knowledge_base
?? ducking_engine_rc2.py
?? loudness_engine_rc2.py
?? mux_engine_rc2.py
?? transition_engine_rc2.py
?? visual_renderer_rc2.py
?? ../../../tests/test_audio_phase7_rc2.py
?? ../../../tests/test_director_knowledge_base_rc2.py
?? ../../../tests/test_phase8_control_layer_rc2.py
?? ../../../tests/test_transition_engine_rc2.py
?? ../../../timeline_code_search.txt
```

## Recommended remediation order

1. Fix syntax errors.
2. Restore one canonical RC2 chain from assets through quality.
3. Define every intermediate artifact in ProjectConfigRC2.
4. Persist outputs atomically and validate project/state at every boundary.
5. Quarantine duplicate orchestrators and legacy fallbacks.
6. Add contract tests for every stage boundary.
7. Run a clean-workspace end-to-end test.
