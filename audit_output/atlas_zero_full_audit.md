# ATLAS ZERO — Full Repository Audit

Generated: `2026-07-22T19:18:10.706832+00:00`
Root: `C:\Users\3dtool\OneDrive\Документы\GitHub\atlas_zero1`

## Executive summary

- Python modules: **239**
- Python lines: **44781**
- Syntax errors: **16**
- Duplicate public symbols: **152**
- JSON readers: **46**
- JSON writers: **103**

## Critical findings

- DirectorCoreRC2 does not import visual_semantic_analyzer_rc2; upstream RC2 chain may be disconnected.
- DirectorCoreRC2 does not import event_discovery_engine_rc2; upstream RC2 chain may be disconnected.
- DirectorCoreRC2 does not import story_strategy_engine_rc2; upstream RC2 chain may be disconnected.

## Syntax errors

- `audit_rc2_production\target_files\project_config_rc2.py:1:1` — invalid non-printable character U+FEFF
- `audit_rc2_production\target_files\render_engine_rc2.py:1:1` — invalid non-printable character U+FEFF
- `audit_rc2_production\target_files\story_engine.py:1:1` — invalid non-printable character U+FEFF
- `rcaz_enterprisecoredirector_ai.py:2:19` — unexpected indent
- `src\az_enterprise\core\dependency_resolver_alpha31.py:1:1` — invalid non-printable character U+FEFF
- `src\az_enterprise\core\module_registry_alpha31.py:1:1` — invalid non-printable character U+FEFF
- `src\az_enterprise\core\story_engine.py:1:1` — invalid non-printable character U+FEFF
- `tests\test_rc2_state_authority.py:1:1` — invalid non-printable character U+FEFF
- `tools\audit_multimedia_assets.py:1:1` — invalid non-printable character U+FEFF
- `tools\autonomy_audit_rc2.py:1:1` — invalid non-printable character U+FEFF
- `tools\build_asset_contact_sheets.py:1:1` — invalid non-printable character U+FEFF
- `tools\director_core_rc1.py:1:1` — invalid non-printable character U+FEFF
- `tools\patch_render_nostdin.py:1:1` — invalid non-printable character U+FEFF
- `tools\patch_semantic_director_clip.py:1:1` — invalid non-printable character U+FEFF
- `tools\recover_franklin_multimedia_render.py:1:1` — invalid non-printable character U+FEFF
- `tools\visual_intelligence_v1_1_multimedia.py:1:1` — invalid non-printable character U+FEFF

## Duplicate public symbols

- **function `run`** × 58: `atlas_zero_phase5_native_camera_motion\phase5_payload\visual_renderer_rc2.py`, `atlas_zero_phase6_native_transition_engine\phase6_payload\visual_renderer_rc2.py`, `atlas_zero_phase7_native_audio_composer\phase7_payload\audio_composer_rc2.py`, `atlas_zero_phase7_native_audio_composer\phase7_payload\audio_renderer_rc2.py`, `atlas_zero_phase7_native_audio_composer\phase7_payload\mux_engine_rc2.py`, `atlas_zero_rc2_1_patch\src\az_enterprise\core\asset_engine_rc2.py`, `atlas_zero_rc2_1_patch\src\az_enterprise\core\assignment_engine_rc2.py`, `atlas_zero_rc2_1_patch\src\az_enterprise\core\director_core_rc2.py`, `atlas_zero_rc2_1_patch\src\az_enterprise\core\quality_gate_rc2.py`, `atlas_zero_rc2_1_patch\src\az_enterprise\core\render_engine_rc2.py`, `atlas_zero_rc2_1_patch\src\az_enterprise\core\timeline_engine_rc2.py`, `atlas_zero_rc2_2_patch\APPLY_RC2_V3.py`, `atlas_zero_rc2_2_patch\src\az_enterprise\core\asset_engine_rc2.py`, `atlas_zero_rc2_2_patch\src\az_enterprise\core\assignment_engine_rc2.py`, `atlas_zero_rc2_2_patch\src\az_enterprise\core\director_core_rc2.py`, `atlas_zero_rc2_2_patch\src\az_enterprise\core\quality_gate_rc2.py`, `atlas_zero_rc2_2_patch\src\az_enterprise\core\render_engine_rc2.py`, `atlas_zero_rc2_2_patch\src\az_enterprise\core\timeline_engine_rc2.py`, `atlas_zero_rc2_final_audit\RC2_E2E_INTEGRATION_TEST.py`, `atlas_zero_rc2_stage2_patch\APPLY_RC2_STAGE2.py`, `atlas_zero_rc2_stage2_patch\src\az_enterprise\core\director_core_rc2.py`, `atlas_zero_rc2_stage2_patch\src\az_enterprise\core\quality_gate_rc2.py`, `audit_rc2_production\target_files\asset_engine_rc2.py`, `audit_rc2_production\target_files\assignment_engine_rc2.py`, `audit_rc2_production\target_files\assignment_policy_rc2.py`, `audit_rc2_production\target_files\production_script_regenerator_rc2.py`, `audit_rc2_production\target_files\quality_gate_rc2.py`, `audit_rc2_production\target_files\render_engine_rc1.py`, `audit_rc2_production\target_files\timeline_engine_rc2.py`, `phase5_payload\visual_renderer_rc2.py`, `src\az_enterprise\core\agents\agent_registry.py`, `src\az_enterprise\core\agents\base_agent.py`, `src\az_enterprise\core\asset_engine_rc2.py`, `src\az_enterprise\core\assignment_engine_rc2.py`, `src\az_enterprise\core\assignment_policy_rc2.backup.py`, `src\az_enterprise\core\assignment_policy_rc2.py`, `src\az_enterprise\core\audio_composer_rc2.py`, `src\az_enterprise\core\audio_renderer_rc2.py`, `src\az_enterprise\core\director_core_rc2.py`, `src\az_enterprise\core\director_supervisor_alpha292.py`, `src\az_enterprise\core\event_discovery_engine_rc2.py`, `src\az_enterprise\core\execution_graph_alpha29.py`, `src\az_enterprise\core\live_api_test_suite.py`, `src\az_enterprise\core\mux_engine_rc2.py`, `src\az_enterprise\core\narrative_writer_rc2.py`, `src\az_enterprise\core\pipeline_runtime.py`, `src\az_enterprise\core\preflight.py`, `src\az_enterprise\core\production_director.py`, `src\az_enterprise\core\production_script_regenerator_rc2.py`, `src\az_enterprise\core\quality_gate_rc2.py`, `src\az_enterprise\core\render_engine_rc2.py`, `src\az_enterprise\core\story_strategy_engine_rc2.py`, `src\az_enterprise\core\test_center.py`, `src\az_enterprise\core\timeline_engine_rc2.py`, `src\az_enterprise\core\visual_asset_registrar.py`, `src\az_enterprise\core\visual_renderer_rc2.py`, `src\az_enterprise\core\voice_production_engine_rc2.py`, `tests\test_director_supervisor_alpha292.py`
- **function `main`** × 38: `APPLY_PHASE5.py`, `apply_atlas_zero_alpha_28.py`, `apply_atlas_zero_alpha_29.py`, `apply_atlas_zero_alpha_291.py`, `apply_atlas_zero_alpha_292.py`, `apply_atlas_zero_alpha_293.py`, `apply_atlas_zero_alpha_301.py`, `apply_atlas_zero_alpha_311.py`, `apply_director_ai_alpha_26.py`, `apply_director_ai_alpha_271.py`, `apply_director_ai_alpha_272.py`, `apply_director_ai_alpha_272_v2.py`, `apply_director_ai_alpha_272_v3.py`, `apply_director_ai_alpha_273.py`, `apply_director_ai_supervisor_alpha26.py`, `apply_director_knowledge_base_rc2.py`, `atlas_zero_full_audit.py`, `atlas_zero_phase5_native_camera_motion\APPLY_PHASE5.py`, `atlas_zero_phase6_native_transition_engine\APPLY_PHASE6.py`, `atlas_zero_phase7_native_audio_composer\APPLY_PHASE7.py`, `atlas_zero_phase8_rc2_control_layer\APPLY_PHASE8.py`, `atlas_zero_rc2_1_patch\src\az_enterprise\core\rc2_cli.py`, `atlas_zero_rc2_2_patch\APPLY_RC2_V3.py`, `atlas_zero_rc2_2_patch\src\az_enterprise\core\rc2_cli.py`, `atlas_zero_rc2_final_audit\RC2_DEPENDENCY_AUDIT.py`, `atlas_zero_rc2_final_audit\RC2_E2E_INTEGRATION_TEST.py`, `atlas_zero_rc2_final_audit\RUN_RC2_FINAL_AUDIT.py`, `atlas_zero_rc2_finalization\APPLY_RC2_FINALIZATION.py`, `atlas_zero_rc2_finalization\VERIFY_RC2_FINALIZATION.py`, `atlas_zero_rc2_production_audit\RC2_PRODUCTION_AUDIT.py`, `atlas_zero_rc2_production_audit\atlas_zero_full_audit.py`, `atlas_zero_rc2_stage2_patch\APPLY_RC2_STAGE2.py`, `atlas_zero_rc2_stage2_patch\src\az_enterprise\core\rc2_cli.py`, `atlas_zero_remove_rc1\APPLY_REMOVE_RC1.py`, `atlas_zero_remove_rc1\VERIFY_REMOVE_RC1.py`, `src\az_enterprise\cli.py`, `src\az_enterprise\core\rc2_cli.py`, `src\az_enterprise\timeline_viewer_app.py`
- **function `build`** × 22: `atlas_zero_phase5_native_camera_motion\phase5_payload\camera_motion_rc2.py`, `atlas_zero_phase6_native_transition_engine\phase6_payload\transition_engine_rc2.py`, `atlas_zero_phase7_native_audio_composer\phase7_payload\audio_timeline_rc2.py`, `audit_rc2_production\target_files\production_script_assembler_rc2.py`, `audit_rc2_production\target_files\story_engine_runtime.py`, `phase5_payload\camera_motion_rc2.py`, `src\az_enterprise\core\audio_timeline_rc2.py`, `src\az_enterprise\core\camera_motion_rc2.py`, `src\az_enterprise\core\capcut_bridge.py`, `src\az_enterprise\core\cv_review_board.py`, `src\az_enterprise\core\editorial_package_rc2.py`, `src\az_enterprise\core\final_assembly_pack.py`, `src\az_enterprise\core\final_timeline_viewer.py`, `src\az_enterprise\core\local_autopilot.py`, `src\az_enterprise\core\montage_workbench.py`, `src\az_enterprise\core\native_timeline.py`, `src\az_enterprise\core\native_viewer_pro.py`, `src\az_enterprise\core\production_script_assembler_rc2.py`, `src\az_enterprise\core\recommendation_engine_alpha28.py`, `src\az_enterprise\core\story_engine_runtime.py`, `src\az_enterprise\core\timeline_viewer_2.py`, `src\az_enterprise\core\transition_engine_rc2.py`
- **function `to_dict`** × 20: `atlas_zero_phase5_native_camera_motion\phase5_payload\camera_motion_rc2.py`, `atlas_zero_phase6_native_transition_engine\phase6_payload\transition_engine_rc2.py`, `atlas_zero_phase7_native_audio_composer\phase7_payload\audio_timeline_rc2.py`, `atlas_zero_phase7_native_audio_composer\phase7_payload\ducking_engine_rc2.py`, `atlas_zero_phase7_native_audio_composer\phase7_payload\loudness_engine_rc2.py`, `phase5_payload\camera_motion_rc2.py`, `src\az_enterprise\core\agents\base_agent.py`, `src\az_enterprise\core\agents\task_model.py`, `src\az_enterprise\core\audio_timeline_rc2.py`, `src\az_enterprise\core\camera_motion_rc2.py`, `src\az_enterprise\core\ducking_engine_rc2.py`, `src\az_enterprise\core\event_discovery_engine_rc2.py`, `src\az_enterprise\core\loudness_engine_rc2.py`, `src\az_enterprise\core\narrative_writer_rc2.py`, `src\az_enterprise\core\openai_adapter_rc2.py`, `src\az_enterprise\core\project_model_alpha301.py`, `src\az_enterprise\core\render_engine_rc2.py`, `src\az_enterprise\core\story_strategy_contract_rc2.py`, `src\az_enterprise\core\transition_engine_rc2.py`, `src\az_enterprise\core\visual_understanding_contract_rc2.py`
- **function `validate`** × 14: `atlas_zero_phase5_native_camera_motion\phase5_payload\camera_motion_rc2.py`, `atlas_zero_phase6_native_transition_engine\phase6_payload\transition_engine_rc2.py`, `atlas_zero_phase7_native_audio_composer\phase7_payload\audio_timeline_rc2.py`, `audit_rc2_production\target_files\production_script_assembler_rc2.py`, `phase5_payload\camera_motion_rc2.py`, `src\az_enterprise\core\audio_timeline_rc2.py`, `src\az_enterprise\core\camera_motion_rc2.py`, `src\az_enterprise\core\editorial_package_rc2.py`, `src\az_enterprise\core\narrative_writer_rc2.py`, `src\az_enterprise\core\production_script_assembler_rc2.py`, `src\az_enterprise\core\project_model_alpha301.py`, `src\az_enterprise\core\story_strategy_contract_rc2.py`, `src\az_enterprise\core\transition_engine_rc2.py`, `src\az_enterprise\core\visual_understanding_contract_rc2.py`
- **function `find_repo_root`** × 10: `atlas_zero_phase6_native_transition_engine\APPLY_PHASE6.py`, `atlas_zero_phase7_native_audio_composer\APPLY_PHASE7.py`, `atlas_zero_phase9_production_cleanup\APPLY_PHASE9.py`, `atlas_zero_phase9_production_cleanup\VERIFY_PHASE9.py`, `atlas_zero_rc2_finalization\APPLY_RC2_FINALIZATION.py`, `atlas_zero_rc2_finalization\VERIFY_RC2_FINALIZATION.py`, `atlas_zero_rc2_production_audit\RC2_PRODUCTION_AUDIT.py`, `atlas_zero_rc2_production_audit\RUN_RC2_PRODUCTION_AUDIT.py`, `atlas_zero_remove_rc1\APPLY_REMOVE_RC1.py`, `atlas_zero_remove_rc1\VERIFY_REMOVE_RC1.py`
- **function `add`** × 7: `atlas_zero_rc2_1_patch\src\az_enterprise\core\quality_gate_rc2.py`, `atlas_zero_rc2_2_patch\src\az_enterprise\core\quality_gate_rc2.py`, `atlas_zero_rc2_stage2_patch\src\az_enterprise\core\quality_gate_rc2.py`, `audit_rc2_production\target_files\quality_gate_rc2.py`, `src\az_enterprise\core\preflight.py`, `src\az_enterprise\core\quality_gate_rc2.py`, `src\az_enterprise\core\test_center.py`
- **function `analyze`** × 6: `audit_rc2_production\target_files\postproduction_quality_rc2.py`, `postproduction_quality_rc2.py`, `src\az_enterprise\core\cv_model.py`, `src\az_enterprise\core\director_ai_runtime.py`, `src\az_enterprise\core\postproduction_quality_rc2.py`, `src\az_enterprise\core\visual_semantic_analyzer_rc2.py`
- **function `create_backup`** × 6: `apply_atlas_zero_alpha_28.py`, `apply_atlas_zero_alpha_29.py`, `apply_director_ai_alpha_272.py`, `apply_director_ai_alpha_272_v2.py`, `apply_director_ai_alpha_272_v3.py`, `apply_director_ai_alpha_273.py`
- **function `run_tests`** × 6: `apply_atlas_zero_alpha_28.py`, `apply_atlas_zero_alpha_29.py`, `apply_director_ai_alpha_272.py`, `apply_director_ai_alpha_272_v2.py`, `apply_director_ai_alpha_272_v3.py`, `apply_director_ai_alpha_273.py`
- **class `QualityGateRC2`** × 5: `atlas_zero_rc2_1_patch\src\az_enterprise\core\quality_gate_rc2.py`, `atlas_zero_rc2_2_patch\src\az_enterprise\core\quality_gate_rc2.py`, `atlas_zero_rc2_stage2_patch\src\az_enterprise\core\quality_gate_rc2.py`, `audit_rc2_production\target_files\quality_gate_rc2.py`, `src\az_enterprise\core\quality_gate_rc2.py`
- **function `build_profile`** × 5: `atlas_zero_phase5_native_camera_motion\phase5_payload\camera_motion_rc2.py`, `atlas_zero_phase6_native_transition_engine\phase6_payload\transition_engine_rc2.py`, `phase5_payload\camera_motion_rc2.py`, `src\az_enterprise\core\camera_motion_rc2.py`, `src\az_enterprise\core\transition_engine_rc2.py`
- **function `evaluate`** × 5: `atlas_zero_phase8_rc2_control_layer\payload\src\az_enterprise\core\control_layer_rc2.py`, `src\az_enterprise\core\control_layer_rc2.py`, `src\az_enterprise\core\director_policy_alpha293.py`, `src\az_enterprise\core\franklin_e2e_runtime.py`, `src\az_enterprise\core\quality.py`
- **function `normalize`** × 5: `atlas_zero_phase5_native_camera_motion\phase5_payload\camera_motion_rc2.py`, `atlas_zero_phase6_native_transition_engine\phase6_payload\transition_engine_rc2.py`, `phase5_payload\camera_motion_rc2.py`, `src\az_enterprise\core\camera_motion_rc2.py`, `src\az_enterprise\core\transition_engine_rc2.py`
- **function `utc_now`** × 5: `atlas_zero_rc2_1_patch\src\az_enterprise\core\production_state_rc2.py`, `atlas_zero_rc2_2_patch\src\az_enterprise\core\production_state_rc2.py`, `atlas_zero_rc2_stage2_patch\src\az_enterprise\core\production_state_rc2.py`, `src\az_enterprise\core\production_state_rc2.py`, `src\az_enterprise\core\project_model_alpha301.py`
- **class `AssetEngineRC2`** × 4: `atlas_zero_rc2_1_patch\src\az_enterprise\core\asset_engine_rc2.py`, `atlas_zero_rc2_2_patch\src\az_enterprise\core\asset_engine_rc2.py`, `audit_rc2_production\target_files\asset_engine_rc2.py`, `src\az_enterprise\core\asset_engine_rc2.py`
- **class `AssignmentEngineRC2`** × 4: `atlas_zero_rc2_1_patch\src\az_enterprise\core\assignment_engine_rc2.py`, `atlas_zero_rc2_2_patch\src\az_enterprise\core\assignment_engine_rc2.py`, `audit_rc2_production\target_files\assignment_engine_rc2.py`, `src\az_enterprise\core\assignment_engine_rc2.py`
- **class `DirectorCoreRC2`** × 4: `atlas_zero_rc2_1_patch\src\az_enterprise\core\director_core_rc2.py`, `atlas_zero_rc2_2_patch\src\az_enterprise\core\director_core_rc2.py`, `atlas_zero_rc2_stage2_patch\src\az_enterprise\core\director_core_rc2.py`, `src\az_enterprise\core\director_core_rc2.py`
- **class `ProductionStateRC2`** × 4: `atlas_zero_rc2_1_patch\src\az_enterprise\core\production_state_rc2.py`, `atlas_zero_rc2_2_patch\src\az_enterprise\core\production_state_rc2.py`, `atlas_zero_rc2_stage2_patch\src\az_enterprise\core\production_state_rc2.py`, `src\az_enterprise\core\production_state_rc2.py`
- **class `ProductionStateStoreRC2`** × 4: `atlas_zero_rc2_1_patch\src\az_enterprise\core\production_state_rc2.py`, `atlas_zero_rc2_2_patch\src\az_enterprise\core\production_state_rc2.py`, `atlas_zero_rc2_stage2_patch\src\az_enterprise\core\production_state_rc2.py`, `src\az_enterprise\core\production_state_rc2.py`
- **class `ProjectConfigRC2`** × 4: `atlas_zero_rc2_1_patch\src\az_enterprise\core\project_config_rc2.py`, `atlas_zero_rc2_2_patch\src\az_enterprise\core\project_config_rc2.py`, `atlas_zero_rc2_stage2_patch\src\az_enterprise\core\project_config_rc2.py`, `src\az_enterprise\core\project_config_rc2.py`
- **class `StageState`** × 4: `atlas_zero_rc2_1_patch\src\az_enterprise\core\production_state_rc2.py`, `atlas_zero_rc2_2_patch\src\az_enterprise\core\production_state_rc2.py`, `atlas_zero_rc2_stage2_patch\src\az_enterprise\core\production_state_rc2.py`, `src\az_enterprise\core\production_state_rc2.py`
- **class `TimelineEngineRC2`** × 4: `atlas_zero_rc2_1_patch\src\az_enterprise\core\timeline_engine_rc2.py`, `atlas_zero_rc2_2_patch\src\az_enterprise\core\timeline_engine_rc2.py`, `audit_rc2_production\target_files\timeline_engine_rc2.py`, `src\az_enterprise\core\timeline_engine_rc2.py`
- **class `VisualRendererRC2`** × 4: `atlas_zero_phase5_native_camera_motion\phase5_payload\visual_renderer_rc2.py`, `atlas_zero_phase6_native_transition_engine\phase6_payload\visual_renderer_rc2.py`, `phase5_payload\visual_renderer_rc2.py`, `src\az_enterprise\core\visual_renderer_rc2.py`
- **function `build_filter`** × 4: `atlas_zero_phase7_native_audio_composer\phase7_payload\ducking_engine_rc2.py`, `atlas_zero_phase7_native_audio_composer\phase7_payload\loudness_engine_rc2.py`, `src\az_enterprise\core\ducking_engine_rc2.py`, `src\az_enterprise\core\loudness_engine_rc2.py`
- **function `build_parser`** × 4: `atlas_zero_rc2_1_patch\src\az_enterprise\core\rc2_cli.py`, `atlas_zero_rc2_2_patch\src\az_enterprise\core\rc2_cli.py`, `atlas_zero_rc2_stage2_patch\src\az_enterprise\core\rc2_cli.py`, `src\az_enterprise\core\rc2_cli.py`
- **function `canonical_render_path`** × 4: `atlas_zero_rc2_1_patch\src\az_enterprise\core\project_config_rc2.py`, `atlas_zero_rc2_2_patch\src\az_enterprise\core\project_config_rc2.py`, `atlas_zero_rc2_stage2_patch\src\az_enterprise\core\project_config_rc2.py`, `src\az_enterprise\core\project_config_rc2.py`
- **function `complete_stage`** × 4: `atlas_zero_rc2_1_patch\src\az_enterprise\core\production_state_rc2.py`, `atlas_zero_rc2_2_patch\src\az_enterprise\core\production_state_rc2.py`, `atlas_zero_rc2_stage2_patch\src\az_enterprise\core\production_state_rc2.py`, `src\az_enterprise\core\production_state_rc2.py`
- **function `export_dir`** × 4: `atlas_zero_rc2_1_patch\src\az_enterprise\core\project_config_rc2.py`, `atlas_zero_rc2_2_patch\src\az_enterprise\core\project_config_rc2.py`, `atlas_zero_rc2_stage2_patch\src\az_enterprise\core\project_config_rc2.py`, `src\az_enterprise\core\project_config_rc2.py`
- **function `fail_stage`** × 4: `atlas_zero_rc2_1_patch\src\az_enterprise\core\production_state_rc2.py`, `atlas_zero_rc2_2_patch\src\az_enterprise\core\production_state_rc2.py`, `atlas_zero_rc2_stage2_patch\src\az_enterprise\core\production_state_rc2.py`, `src\az_enterprise\core\production_state_rc2.py`
- **function `franklin_legacy_render_path`** × 4: `atlas_zero_rc2_1_patch\src\az_enterprise\core\project_config_rc2.py`, `atlas_zero_rc2_2_patch\src\az_enterprise\core\project_config_rc2.py`, `atlas_zero_rc2_stage2_patch\src\az_enterprise\core\project_config_rc2.py`, `src\az_enterprise\core\project_config_rc2.py`
- **function `legacy_render_path`** × 4: `atlas_zero_rc2_1_patch\src\az_enterprise\core\project_config_rc2.py`, `atlas_zero_rc2_2_patch\src\az_enterprise\core\project_config_rc2.py`, `atlas_zero_rc2_stage2_patch\src\az_enterprise\core\project_config_rc2.py`, `src\az_enterprise\core\project_config_rc2.py`
- **function `load`** × 4: `atlas_zero_rc2_1_patch\src\az_enterprise\core\production_state_rc2.py`, `atlas_zero_rc2_2_patch\src\az_enterprise\core\production_state_rc2.py`, `atlas_zero_rc2_stage2_patch\src\az_enterprise\core\production_state_rc2.py`, `src\az_enterprise\core\production_state_rc2.py`
- **function `patch_module`** × 4: `apply_director_ai_alpha_271.py`, `apply_director_ai_alpha_272.py`, `apply_director_ai_alpha_272_v2.py`, `apply_director_ai_alpha_272_v3.py`
- **function `plan`** × 4: `atlas_zero_phase8_rc2_control_layer\payload\src\az_enterprise\core\control_layer_rc2.py`, `atlas_zero_rc2_stage2_patch\src\az_enterprise\core\director_core_rc2.py`, `src\az_enterprise\core\control_layer_rc2.py`, `src\az_enterprise\core\director_core_rc2.py`
- **function `progress`** × 4: `atlas_zero_phase5_native_camera_motion\phase5_payload\camera_motion_rc2.py`, `phase5_payload\camera_motion_rc2.py`, `src\az_enterprise\cli.py`, `src\az_enterprise\core\camera_motion_rc2.py`
- **function `project_dir`** × 4: `atlas_zero_rc2_1_patch\src\az_enterprise\core\project_config_rc2.py`, `atlas_zero_rc2_2_patch\src\az_enterprise\core\project_config_rc2.py`, `atlas_zero_rc2_stage2_patch\src\az_enterprise\core\project_config_rc2.py`, `src\az_enterprise\core\project_config_rc2.py`
- **function `rc2_dir`** × 4: `atlas_zero_rc2_1_patch\src\az_enterprise\core\project_config_rc2.py`, `atlas_zero_rc2_2_patch\src\az_enterprise\core\project_config_rc2.py`, `atlas_zero_rc2_stage2_patch\src\az_enterprise\core\project_config_rc2.py`, `src\az_enterprise\core\project_config_rc2.py`
- **function `replace_once`** × 4: `apply_atlas_zero_alpha_311.py`, `apply_director_ai_alpha_271.py`, `apply_director_ai_alpha_272.py`, `apply_director_ai_supervisor_alpha26.py`
- **function `repo_root`** × 4: `atlas_zero_phase8_rc2_control_layer\APPLY_PHASE8.py`, `atlas_zero_rc2_final_audit\RC2_DEPENDENCY_AUDIT.py`, `atlas_zero_rc2_final_audit\RC2_E2E_INTEGRATION_TEST.py`, `atlas_zero_rc2_final_audit\RUN_RC2_FINAL_AUDIT.py`
- **function `save`** × 4: `atlas_zero_rc2_1_patch\src\az_enterprise\core\production_state_rc2.py`, `atlas_zero_rc2_2_patch\src\az_enterprise\core\production_state_rc2.py`, `atlas_zero_rc2_stage2_patch\src\az_enterprise\core\production_state_rc2.py`, `src\az_enterprise\core\production_state_rc2.py`
- **function `score`** × 4: `audit_rc2_production\target_files\assignment_policy_rc2.py`, `src\az_enterprise\core\assignment_policy_rc2.backup.py`, `src\az_enterprise\core\assignment_policy_rc2.py`, `src\az_enterprise\core\director_policy_alpha293.py`
- **function `start_stage`** × 4: `atlas_zero_rc2_1_patch\src\az_enterprise\core\production_state_rc2.py`, `atlas_zero_rc2_2_patch\src\az_enterprise\core\production_state_rc2.py`, `atlas_zero_rc2_stage2_patch\src\az_enterprise\core\production_state_rc2.py`, `src\az_enterprise\core\production_state_rc2.py`
- **function `state_path`** × 4: `atlas_zero_rc2_1_patch\src\az_enterprise\core\project_config_rc2.py`, `atlas_zero_rc2_2_patch\src\az_enterprise\core\project_config_rc2.py`, `atlas_zero_rc2_stage2_patch\src\az_enterprise\core\project_config_rc2.py`, `src\az_enterprise\core\project_config_rc2.py`
- **function `timeline_path`** × 4: `atlas_zero_rc2_1_patch\src\az_enterprise\core\project_config_rc2.py`, `atlas_zero_rc2_2_patch\src\az_enterprise\core\project_config_rc2.py`, `atlas_zero_rc2_stage2_patch\src\az_enterprise\core\project_config_rc2.py`, `src\az_enterprise\core\project_config_rc2.py`
- **function `workspace_dir`** × 4: `atlas_zero_rc2_1_patch\src\az_enterprise\core\project_config_rc2.py`, `atlas_zero_rc2_2_patch\src\az_enterprise\core\project_config_rc2.py`, `atlas_zero_rc2_stage2_patch\src\az_enterprise\core\project_config_rc2.py`, `src\az_enterprise\core\project_config_rc2.py`
- **class `AssignmentPolicyRC2`** × 3: `audit_rc2_production\target_files\assignment_policy_rc2.py`, `src\az_enterprise\core\assignment_policy_rc2.backup.py`, `src\az_enterprise\core\assignment_policy_rc2.py`
- **class `CameraMotionEngine`** × 3: `atlas_zero_phase5_native_camera_motion\phase5_payload\camera_motion_rc2.py`, `phase5_payload\camera_motion_rc2.py`, `src\az_enterprise\core\camera_motion_rc2.py`
- **class `FFmpegMotionBuilder`** × 3: `atlas_zero_phase5_native_camera_motion\phase5_payload\camera_motion_rc2.py`, `phase5_payload\camera_motion_rc2.py`, `src\az_enterprise\core\camera_motion_rc2.py`
- **class `MotionInterpolator`** × 3: `atlas_zero_phase5_native_camera_motion\phase5_payload\camera_motion_rc2.py`, `phase5_payload\camera_motion_rc2.py`, `src\az_enterprise\core\camera_motion_rc2.py`
- **class `MotionProfile`** × 3: `atlas_zero_phase5_native_camera_motion\phase5_payload\camera_motion_rc2.py`, `phase5_payload\camera_motion_rc2.py`, `src\az_enterprise\core\camera_motion_rc2.py`
- **class `MotionValidator`** × 3: `atlas_zero_phase5_native_camera_motion\phase5_payload\camera_motion_rc2.py`, `phase5_payload\camera_motion_rc2.py`, `src\az_enterprise\core\camera_motion_rc2.py`
- **class `PostProductionQualityRC2`** × 3: `audit_rc2_production\target_files\postproduction_quality_rc2.py`, `postproduction_quality_rc2.py`, `src\az_enterprise\core\postproduction_quality_rc2.py`
- **class `RenderEngineRC2`** × 3: `atlas_zero_rc2_1_patch\src\az_enterprise\core\render_engine_rc2.py`, `atlas_zero_rc2_2_patch\src\az_enterprise\core\render_engine_rc2.py`, `src\az_enterprise\core\render_engine_rc2.py`
- **function `clamp`** × 3: `atlas_zero_phase5_native_camera_motion\phase5_payload\camera_motion_rc2.py`, `phase5_payload\camera_motion_rc2.py`, `src\az_enterprise\core\camera_motion_rc2.py`
- **function `eased_progress`** × 3: `atlas_zero_phase5_native_camera_motion\phase5_payload\camera_motion_rc2.py`, `phase5_payload\camera_motion_rc2.py`, `src\az_enterprise\core\camera_motion_rc2.py`
- **function `interpolate`** × 3: `atlas_zero_phase5_native_camera_motion\phase5_payload\camera_motion_rc2.py`, `phase5_payload\camera_motion_rc2.py`, `src\az_enterprise\core\camera_motion_rc2.py`
- **function `live_enabled`** × 3: `src\az_enterprise\core\live_api_layer.py`, `src\az_enterprise\core\live_connectors.py`, `src\az_enterprise\core\openai_adapter_rc2.py`
- **function `prepare_db`** × 3: `tests\test_rc2_timeline_production_script.py`, `tests\test_rc2_timeline_project_discovery.py`, `tests\test_story_engine_semantic_rc26.py`
- **function `probe`** × 3: `atlas_zero_rc2_1_patch\src\az_enterprise\core\render_engine_rc2.py`, `atlas_zero_rc2_2_patch\src\az_enterprise\core\render_engine_rc2.py`, `src\az_enterprise\core\render_engine_rc2.py`
- **function `rel`** × 3: `atlas_zero_full_audit.py`, `atlas_zero_rc2_production_audit\RC2_PRODUCTION_AUDIT.py`, `atlas_zero_rc2_production_audit\atlas_zero_full_audit.py`
- **function `restore`** × 3: `apply_atlas_zero_alpha_28.py`, `apply_atlas_zero_alpha_29.py`, `apply_director_ai_alpha_273.py`
- **function `restore_file`** × 3: `apply_director_ai_alpha_272.py`, `apply_director_ai_alpha_272_v2.py`, `apply_director_ai_alpha_272_v3.py`
- **function `test_project_config_is_project_generic`** × 3: `atlas_zero_rc2_1_patch\tests\test_rc2_foundation.py`, `atlas_zero_rc2_2_patch\tests\test_rc2_foundation.py`, `tests\test_rc2_foundation.py`
- **function `test_state_store_writes_and_reads_atomically`** × 3: `atlas_zero_rc2_1_patch\tests\test_rc2_foundation.py`, `atlas_zero_rc2_2_patch\tests\test_rc2_foundation.py`, `tests\test_rc2_foundation.py`
- **function `total_frames`** × 3: `atlas_zero_phase5_native_camera_motion\phase5_payload\camera_motion_rc2.py`, `phase5_payload\camera_motion_rc2.py`, `src\az_enterprise\core\camera_motion_rc2.py`
- **class `AudioEventRC2`** × 2: `atlas_zero_phase7_native_audio_composer\phase7_payload\audio_timeline_rc2.py`, `src\az_enterprise\core\audio_timeline_rc2.py`
- **class `AudioRendererRC2`** × 2: `atlas_zero_phase7_native_audio_composer\phase7_payload\audio_renderer_rc2.py`, `src\az_enterprise\core\audio_renderer_rc2.py`
- **class `AudioTimelineBuilderRC2`** × 2: `atlas_zero_phase7_native_audio_composer\phase7_payload\audio_timeline_rc2.py`, `src\az_enterprise\core\audio_timeline_rc2.py`
- **class `AudioTimelineValidatorRC2`** × 2: `atlas_zero_phase7_native_audio_composer\phase7_payload\audio_timeline_rc2.py`, `src\az_enterprise\core\audio_timeline_rc2.py`
- **class `DuckingEngineRC2`** × 2: `atlas_zero_phase7_native_audio_composer\phase7_payload\ducking_engine_rc2.py`, `src\az_enterprise\core\ducking_engine_rc2.py`
- **class `DuckingProfileRC2`** × 2: `atlas_zero_phase7_native_audio_composer\phase7_payload\ducking_engine_rc2.py`, `src\az_enterprise\core\ducking_engine_rc2.py`
- **class `DuplicateRecord`** × 2: `atlas_zero_full_audit.py`, `atlas_zero_rc2_production_audit\atlas_zero_full_audit.py`
- **class `FFmpegTransitionGraphBuilder`** × 2: `atlas_zero_phase6_native_transition_engine\phase6_payload\transition_engine_rc2.py`, `src\az_enterprise\core\transition_engine_rc2.py`
- **class `LoudnessEngineRC2`** × 2: `atlas_zero_phase7_native_audio_composer\phase7_payload\loudness_engine_rc2.py`, `src\az_enterprise\core\loudness_engine_rc2.py`
- **class `LoudnessProfileRC2`** × 2: `atlas_zero_phase7_native_audio_composer\phase7_payload\loudness_engine_rc2.py`, `src\az_enterprise\core\loudness_engine_rc2.py`
- **class `ModuleRecord`** × 2: `atlas_zero_full_audit.py`, `atlas_zero_rc2_production_audit\atlas_zero_full_audit.py`
- **class `MuxEngineRC2`** × 2: `atlas_zero_phase7_native_audio_composer\phase7_payload\mux_engine_rc2.py`, `src\az_enterprise\core\mux_engine_rc2.py`
- **class `NativeAudioComposerRC2`** × 2: `atlas_zero_phase7_native_audio_composer\phase7_payload\audio_composer_rc2.py`, `src\az_enterprise\core\audio_composer_rc2.py`
- **class `PostProductionQualityRC2Test`** × 2: `test_postproduction_quality_rc2.py`, `tests\test_postproduction_quality_rc2.py`
- **class `ProductionScriptAssemblerRC2`** × 2: `audit_rc2_production\target_files\production_script_assembler_rc2.py`, `src\az_enterprise\core\production_script_assembler_rc2.py`
- **class `ProductionScriptRegeneratorRC2`** × 2: `audit_rc2_production\target_files\production_script_regenerator_rc2.py`, `src\az_enterprise\core\production_script_regenerator_rc2.py`
- **class `RC2ControlLayer`** × 2: `atlas_zero_phase8_rc2_control_layer\payload\src\az_enterprise\core\control_layer_rc2.py`, `src\az_enterprise\core\control_layer_rc2.py`
- **class `RC2ReadinessPlanner`** × 2: `atlas_zero_phase8_rc2_control_layer\payload\src\az_enterprise\core\control_layer_rc2.py`, `src\az_enterprise\core\control_layer_rc2.py`
- **class `RuntimeAuthority`** × 2: `atlas_zero_rc2_stage2_patch\src\az_enterprise\core\runtime_governance_rc2.py`, `src\az_enterprise\core\runtime_governance_rc2.py`
- **class `StageDefinition`** × 2: `atlas_zero_rc2_stage2_patch\src\az_enterprise\core\director_core_rc2.py`, `src\az_enterprise\core\director_core_rc2.py`
- **class `StoryEngineRuntime`** × 2: `audit_rc2_production\target_files\story_engine_runtime.py`, `src\az_enterprise\core\story_engine_runtime.py`
- **class `SyntaxErrorRecord`** × 2: `atlas_zero_full_audit.py`, `atlas_zero_rc2_production_audit\atlas_zero_full_audit.py`
- **class `Task`** × 2: `src\az_enterprise\core\agents\task_model.py`, `src\az_enterprise\core\project_model_alpha301.py`
- **class `TransitionEngineRC2`** × 2: `atlas_zero_phase6_native_transition_engine\phase6_payload\transition_engine_rc2.py`, `src\az_enterprise\core\transition_engine_rc2.py`
- **class `TransitionProfile`** × 2: `atlas_zero_phase6_native_transition_engine\phase6_payload\transition_engine_rc2.py`, `src\az_enterprise\core\transition_engine_rc2.py`
- **class `TransitionValidator`** × 2: `atlas_zero_phase6_native_transition_engine\phase6_payload\transition_engine_rc2.py`, `src\az_enterprise\core\transition_engine_rc2.py`
- **function `analyze_python`** × 2: `atlas_zero_full_audit.py`, `atlas_zero_rc2_production_audit\atlas_zero_full_audit.py`
- **function `backup`** × 2: `apply_director_ai_alpha_271.py`, `apply_director_knowledge_base_rc2.py`
- **function `backup_file`** × 2: `atlas_zero_phase9_production_cleanup\APPLY_PHASE9.py`, `atlas_zero_rc2_finalization\APPLY_RC2_FINALIZATION.py`
- **function `build_pipeline_findings`** × 2: `atlas_zero_full_audit.py`, `atlas_zero_rc2_production_audit\atlas_zero_full_audit.py`
- **function `build_timeline`** × 2: `atlas_zero_phase8_rc2_control_layer\payload\src\az_enterprise\core\control_layer_rc2.py`, `src\az_enterprise\core\control_layer_rc2.py`
- **function `call`** × 2: `atlas_zero_full_audit.py`, `atlas_zero_rc2_production_audit\atlas_zero_full_audit.py`
- **function `classify`** × 2: `src\az_enterprise\core\visual_semantic_analyzer_rc2.py`, `tests\test_visual_semantic_analyzer_rc2.py`
- **function `collect_duplicates`** × 2: `atlas_zero_full_audit.py`, `atlas_zero_rc2_production_audit\atlas_zero_full_audit.py`

## Pipeline stage coverage

### asset
- `apply_atlas_zero_alpha_28.py`
- `apply_atlas_zero_alpha_291.py`
- `apply_atlas_zero_alpha_301.py`
- `apply_atlas_zero_alpha_311.py`
- `apply_director_ai_25.py`
- `apply_director_ai_alpha_26.py`
- `apply_director_ai_alpha_271.py`
- `apply_director_ai_alpha_272.py`
- `apply_director_ai_alpha_272_v2.py`
- `apply_director_ai_alpha_272_v3.py`
- `apply_director_ai_alpha_273.py`
- `apply_director_ai_supervisor_alpha26.py`
- `apply_director_supervisor_rc2_fix.py`
- `atlas_zero_full_audit.py`
- `atlas_zero_phase5_native_camera_motion\phase5_payload\visual_renderer_rc2.py`
- `atlas_zero_phase6_native_transition_engine\phase6_payload\visual_renderer_rc2.py`
- `atlas_zero_phase7_native_audio_composer\phase7_payload\audio_renderer_rc2.py`
- `atlas_zero_phase7_native_audio_composer\phase7_payload\audio_timeline_rc2.py`
- `atlas_zero_phase7_native_audio_composer\test_audio_phase7_rc2.py`
- `atlas_zero_phase9_production_cleanup\APPLY_PHASE9.py`
- `atlas_zero_phase9_production_cleanup\VERIFY_PHASE9.py`
- `atlas_zero_rc2_1_patch\src\az_enterprise\core\asset_engine_rc2.py`
- `atlas_zero_rc2_1_patch\src\az_enterprise\core\assignment_engine_rc2.py`
- `atlas_zero_rc2_1_patch\src\az_enterprise\core\director_core_rc2.py`
- `atlas_zero_rc2_1_patch\src\az_enterprise\core\project_config_rc2.py`
- `atlas_zero_rc2_1_patch\src\az_enterprise\core\quality_gate_rc2.py`
- `atlas_zero_rc2_1_patch\src\az_enterprise\core\timeline_engine_rc2.py`
- `atlas_zero_rc2_1_patch\tests\test_rc2_foundation.py`
- `atlas_zero_rc2_2_patch\APPLY_RC2_V3.py`
- `atlas_zero_rc2_2_patch\src\az_enterprise\core\asset_engine_rc2.py`
- `atlas_zero_rc2_2_patch\src\az_enterprise\core\assignment_engine_rc2.py`
- `atlas_zero_rc2_2_patch\src\az_enterprise\core\director_core_rc2.py`
- `atlas_zero_rc2_2_patch\src\az_enterprise\core\project_config_rc2.py`
- `atlas_zero_rc2_2_patch\src\az_enterprise\core\quality_gate_rc2.py`
- `atlas_zero_rc2_2_patch\src\az_enterprise\core\timeline_engine_rc2.py`
- `atlas_zero_rc2_2_patch\tests\test_rc2_foundation.py`
- `atlas_zero_rc2_finalization\APPLY_RC2_FINALIZATION.py`
- `atlas_zero_rc2_finalization\VERIFY_RC2_FINALIZATION.py`
- `atlas_zero_rc2_production_audit\atlas_zero_full_audit.py`
- `atlas_zero_rc2_stage2_patch\src\az_enterprise\core\director_core_rc2.py`
- `atlas_zero_rc2_stage2_patch\src\az_enterprise\core\project_config_rc2.py`
- `atlas_zero_rc2_stage2_patch\src\az_enterprise\core\quality_gate_rc2.py`
- `audit_rc2_production\target_files\asset_engine_rc2.py`
- `audit_rc2_production\target_files\assignment_policy_rc2.py`
- `audit_rc2_production\target_files\postproduction_quality_rc2.py`
- `audit_rc2_production\target_files\production_script_assembler_rc2.py`
- `audit_rc2_production\target_files\quality_gate_rc2.py`
- `audit_rc2_production\target_files\render_engine_rc1.py`
- `audit_rc2_production\target_files\story_engine_runtime.py`
- `audit_rc2_production\target_files\timeline_engine_rc2.py`
- `phase5_payload\visual_renderer_rc2.py`
- `postproduction_quality_rc2.py`
- `src\az_enterprise\cli.py`
- `src\az_enterprise\core\acceptance_center.py`
- `src\az_enterprise\core\agents\agent_registry.py`
- `src\az_enterprise\core\asset_engine_rc2.py`
- `src\az_enterprise\core\asset_intelligence.py`
- `src\az_enterprise\core\assignment_policy_rc2.backup.py`
- `src\az_enterprise\core\assignment_policy_rc2.py`
- `src\az_enterprise\core\audio_renderer_rc2.py`
- `src\az_enterprise\core\audio_timeline_rc2.py`
- `src\az_enterprise\core\capcut_bridge.py`
- `src\az_enterprise\core\cv_model.py`
- `src\az_enterprise\core\cv_review_board.py`
- `src\az_enterprise\core\database.py`
- `src\az_enterprise\core\director_ai.py`
- `src\az_enterprise\core\director_ai_runtime.py`
- `src\az_enterprise\core\director_core_rc2.py`
- `src\az_enterprise\core\editorial_package_rc2.py`
- `src\az_enterprise\core\event_discovery_engine_rc2.py`
- `src\az_enterprise\core\final_assembly_pack.py`
- `src\az_enterprise\core\final_timeline_viewer.py`
- `src\az_enterprise\core\franklin_e2e_runtime.py`
- `src\az_enterprise\core\generated_asset_store_rc2.py`
- `src\az_enterprise\core\live_api_layer.py`
- `src\az_enterprise\core\local_autopilot.py`
- `src\az_enterprise\core\montage_workbench.py`
- `src\az_enterprise\core\narrative_writer_rc2.py`
- `src\az_enterprise\core\native_timeline.py`
- `src\az_enterprise\core\native_viewer_pro.py`
- `src\az_enterprise\core\native_viewer_rc.py`
- `src\az_enterprise\core\operator_console.py`
- `src\az_enterprise\core\pipeline_runtime.py`
- `src\az_enterprise\core\postproduction_quality_rc2.py`
- `src\az_enterprise\core\preflight.py`
- `src\az_enterprise\core\production_director.py`
- `src\az_enterprise\core\production_script_assembler_rc2.py`
- `src\az_enterprise\core\production_state.py`
- `src\az_enterprise\core\project_config_rc2.py`
- `src\az_enterprise\core\project_context_alpha29.py`
- `src\az_enterprise\core\project_model_alpha301.py`
- `src\az_enterprise\core\quality.py`
- `src\az_enterprise\core\quality_gate_rc2.py`
- `src\az_enterprise\core\recommendation_engine_alpha28.py`
- `src\az_enterprise\core\release_gate.py`
- `src\az_enterprise\core\render_engine_rc2.py`
- `src\az_enterprise\core\story_engine_runtime.py`
- `src\az_enterprise\core\story_strategy_contract_rc2.py`
- `src\az_enterprise\core\story_strategy_engine_rc2.py`
- `src\az_enterprise\core\test_center.py`
- `src\az_enterprise\core\timeline_engine_rc2.py`
- `src\az_enterprise\core\timeline_studio.py`
- `src\az_enterprise\core\timeline_viewer_2.py`
- `src\az_enterprise\core\visual_asset_registrar.py`
- `src\az_enterprise\core\visual_dynamics_alpha272.py`
- `src\az_enterprise\core\visual_intelligence.py`
- `src\az_enterprise\core\visual_renderer_rc2.py`
- `src\az_enterprise\core\visual_semantic_analyzer_rc2.py`
- `src\az_enterprise\core\visual_understanding_contract_rc2.py`
- `src\az_enterprise\core\workflow.py`
- `src\az_enterprise\core\working_state_auditor.py`
- `src\az_enterprise\ui\app.py`
- `test_postproduction_quality_rc2.py`
- `tests\test_audio_phase7_rc2.py`
- `tests\test_director_ai_alpha25.py`
- `tests\test_director_ai_supervisor_alpha26.py`
- `tests\test_editorial_package_rc2.py`
- `tests\test_event_bus_consolidation.py`
- `tests\test_event_discovery_engine_rc2.py`
- `tests\test_generated_asset_store_rc2.py`
- `tests\test_narrative_writer_openai_rc2.py`
- `tests\test_narrative_writer_rc2.py`
- `tests\test_postproduction_quality_rc2.py`
- `tests\test_postproduction_rhythm_alpha271.py`
- `tests\test_postproduction_visual_alpha272.py`
- `tests\test_production_director.py`
- `tests\test_production_script_assembler_rc2.py`
- `tests\test_production_script_regenerator_rc2.py`
- `tests\test_project_model_alpha301.py`
- `tests\test_project_profiles_alpha273.py`
- `tests\test_rc2_asset_project_isolation.py`
- `tests\test_rc2_asset_schema_migration.py`
- `tests\test_rc2_assignment_authority.py`
- `tests\test_rc2_external_asset_source.py`
- `tests\test_rc2_foundation.py`
- `tests\test_rc2_render_authority.py`
- `tests\test_rc2_timeline_authority.py`
- `tests\test_rc2_timeline_production_script.py`
- `tests\test_rc2_timeline_project_discovery.py`
- `tests\test_recommendation_engine_alpha28.py`
- `tests\test_story_engine_semantic_rc26.py`
- `tests\test_story_strategy_contract_rc2.py`
- `tests\test_story_strategy_engine_rc2.py`
- `tests\test_visual_asset_registrar.py`
- `tests\test_visual_semantic_analyzer_rc2.py`
- `tests\test_visual_understanding_contract_rc2.py`

### assignment
- `apply_director_ai_supervisor_alpha26.py`
- `apply_director_knowledge_base_rc2.py`
- `apply_director_supervisor_rc2_fix.py`
- `atlas_zero_full_audit.py`
- `atlas_zero_rc2_1_patch\src\az_enterprise\core\assignment_engine_rc2.py`
- `atlas_zero_rc2_1_patch\src\az_enterprise\core\director_core_rc2.py`
- `atlas_zero_rc2_2_patch\APPLY_RC2_V3.py`
- `atlas_zero_rc2_2_patch\src\az_enterprise\core\assignment_engine_rc2.py`
- `atlas_zero_rc2_2_patch\src\az_enterprise\core\director_core_rc2.py`
- `atlas_zero_rc2_production_audit\atlas_zero_full_audit.py`
- `atlas_zero_rc2_stage2_patch\src\az_enterprise\core\director_core_rc2.py`
- `atlas_zero_rc2_stage2_patch\src\az_enterprise\core\project_config_rc2.py`
- `audit_rc2_production\target_files\assignment_engine_rc2.py`
- `audit_rc2_production\target_files\assignment_policy_rc2.py`
- `src\az_enterprise\core\assignment_engine_rc2.py`
- `src\az_enterprise\core\assignment_policy_rc2.backup.py`
- `src\az_enterprise\core\assignment_policy_rc2.py`
- `src\az_enterprise\core\cv_model.py`
- `src\az_enterprise\core\director_ai.py`
- `src\az_enterprise\core\director_ai_runtime.py`
- `src\az_enterprise\core\director_core_rc2.py`
- `src\az_enterprise\core\editorial_package_rc2.py`
- `src\az_enterprise\core\final_timeline_viewer.py`
- `src\az_enterprise\core\project_config_rc2.py`
- `src\az_enterprise\core\visual_asset_registrar.py`
- `tests\test_director_ai_supervisor_alpha26.py`
- `tests\test_director_knowledge_base_rc2.py`
- `tests\test_rc2_assignment_authority.py`
- `tests\test_rc2_director_ai_authority.py`

### audio
- `apply_director_ai_alpha_26.py`
- `apply_director_ai_alpha_271.py`
- `atlas_zero_full_audit.py`
- `atlas_zero_phase7_native_audio_composer\APPLY_PHASE7.py`
- `atlas_zero_phase7_native_audio_composer\phase7_payload\audio_composer_rc2.py`
- `atlas_zero_phase7_native_audio_composer\phase7_payload\audio_renderer_rc2.py`
- `atlas_zero_phase7_native_audio_composer\phase7_payload\audio_timeline_rc2.py`
- `atlas_zero_phase7_native_audio_composer\phase7_payload\mux_engine_rc2.py`
- `atlas_zero_phase7_native_audio_composer\test_audio_phase7_rc2.py`
- `atlas_zero_rc2_1_patch\src\az_enterprise\core\render_engine_rc2.py`
- `atlas_zero_rc2_2_patch\src\az_enterprise\core\render_engine_rc2.py`
- `atlas_zero_rc2_final_audit\RC2_DEPENDENCY_AUDIT.py`
- `atlas_zero_rc2_final_audit\RC2_E2E_INTEGRATION_TEST.py`
- `atlas_zero_rc2_production_audit\RC2_PRODUCTION_AUDIT.py`
- `atlas_zero_rc2_production_audit\atlas_zero_full_audit.py`
- `atlas_zero_rc2_stage2_patch\src\az_enterprise\core\project_config_rc2.py`
- `audit_rc2_production\target_files\postproduction_quality_rc2.py`
- `audit_rc2_production\target_files\render_engine_rc1.py`
- `postproduction_quality_rc2.py`
- `src\az_enterprise\core\acceptance_center.py`
- `src\az_enterprise\core\asset_intelligence.py`
- `src\az_enterprise\core\audio_composer_rc2.py`
- `src\az_enterprise\core\audio_renderer_rc2.py`
- `src\az_enterprise\core\audio_timeline_rc2.py`
- `src\az_enterprise\core\mux_engine_rc2.py`
- `src\az_enterprise\core\native_timeline.py`
- `src\az_enterprise\core\paths.py`
- `src\az_enterprise\core\pipeline_runtime.py`
- `src\az_enterprise\core\postproduction_quality_rc2.py`
- `src\az_enterprise\core\preflight.py`
- `src\az_enterprise\core\production_director.py`
- `src\az_enterprise\core\project_config_rc2.py`
- `src\az_enterprise\core\render_engine_rc2.py`
- `src\az_enterprise\core\voice_production_engine_rc2.py`
- `tests\test_audio_phase7_rc2.py`
- `tests\test_production_director.py`
- `tests\test_rc2_timeline_authority.py`

### director
- `APPLY_PHASE5.py`
- `apply_atlas_zero_alpha_28.py`
- `apply_atlas_zero_alpha_29.py`
- `apply_atlas_zero_alpha_291.py`
- `apply_atlas_zero_alpha_292.py`
- `apply_atlas_zero_alpha_293.py`
- `apply_atlas_zero_alpha_301.py`
- `apply_atlas_zero_alpha_311.py`
- `apply_director_ai_25.py`
- `apply_director_ai_alpha_26.py`
- `apply_director_ai_alpha_271.py`
- `apply_director_ai_alpha_272.py`
- `apply_director_ai_alpha_272_v2.py`
- `apply_director_ai_alpha_272_v3.py`
- `apply_director_ai_alpha_273.py`
- `apply_director_ai_supervisor_alpha26.py`
- `apply_director_knowledge_base_rc2.py`
- `apply_director_supervisor_rc2_fix.py`
- `atlas_zero_full_audit.py`
- `atlas_zero_phase5_native_camera_motion\APPLY_PHASE5.py`
- `atlas_zero_phase8_rc2_control_layer\APPLY_PHASE8.py`
- `atlas_zero_phase8_rc2_control_layer\payload\src\az_enterprise\core\control_layer_rc2.py`
- `atlas_zero_rc2_1_patch\src\az_enterprise\core\asset_engine_rc2.py`
- `atlas_zero_rc2_1_patch\src\az_enterprise\core\assignment_engine_rc2.py`
- `atlas_zero_rc2_1_patch\src\az_enterprise\core\director_core_rc2.py`
- `atlas_zero_rc2_1_patch\src\az_enterprise\core\rc2_cli.py`
- `atlas_zero_rc2_2_patch\APPLY_RC2_V3.py`
- `atlas_zero_rc2_2_patch\src\az_enterprise\core\asset_engine_rc2.py`
- `atlas_zero_rc2_2_patch\src\az_enterprise\core\assignment_engine_rc2.py`
- `atlas_zero_rc2_2_patch\src\az_enterprise\core\director_core_rc2.py`
- `atlas_zero_rc2_2_patch\src\az_enterprise\core\rc2_cli.py`
- `atlas_zero_rc2_finalization\APPLY_RC2_FINALIZATION.py`
- `atlas_zero_rc2_finalization\VERIFY_RC2_FINALIZATION.py`
- `atlas_zero_rc2_production_audit\atlas_zero_full_audit.py`
- `atlas_zero_rc2_stage2_patch\APPLY_RC2_STAGE2.py`
- `atlas_zero_rc2_stage2_patch\src\az_enterprise\core\director_core_rc2.py`
- `atlas_zero_rc2_stage2_patch\src\az_enterprise\core\project_config_rc2.py`
- `atlas_zero_rc2_stage2_patch\src\az_enterprise\core\rc2_cli.py`
- `atlas_zero_rc2_stage2_patch\src\az_enterprise\core\runtime_governance_rc2.py`
- `atlas_zero_rc2_stage2_patch\tests\test_rc2_stage2_unified_runtime.py`
- `atlas_zero_remove_rc1\APPLY_REMOVE_RC1.py`
- `audit_rc2_production\target_files\asset_engine_rc2.py`
- `audit_rc2_production\target_files\assignment_engine_rc2.py`
- `audit_rc2_production\target_files\assignment_policy_rc2.py`
- `audit_rc2_production\target_files\postproduction_quality_rc2.py`
- `audit_rc2_production\target_files\story_engine_runtime.py`
- `audit_rc2_production\target_files\timeline_engine_rc2.py`
- `postproduction_quality_rc2.py`
- `src\az_enterprise\cli.py`
- `src\az_enterprise\core\acceptance_center.py`
- `src\az_enterprise\core\asset_engine_rc2.py`
- `src\az_enterprise\core\assignment_engine_rc2.py`
- `src\az_enterprise\core\assignment_policy_rc2.backup.py`
- `src\az_enterprise\core\assignment_policy_rc2.py`
- `src\az_enterprise\core\control_layer_rc2.py`
- `src\az_enterprise\core\database.py`
- `src\az_enterprise\core\director_ai.py`
- `src\az_enterprise\core\director_ai_runtime.py`
- `src\az_enterprise\core\director_core_rc2.py`
- `src\az_enterprise\core\director_knowledge_base_rc2.py`
- `src\az_enterprise\core\director_policy_alpha293.py`
- `src\az_enterprise\core\director_policy_evaluator_alpha293.py`
- `src\az_enterprise\core\director_supervisor_alpha292.py`
- `src\az_enterprise\core\final_timeline_viewer.py`
- `src\az_enterprise\core\integrations.py`
- `src\az_enterprise\core\montage_workbench.py`
- `src\az_enterprise\core\native_timeline.py`
- `src\az_enterprise\core\pipeline_runtime.py`
- `src\az_enterprise\core\postproduction_quality_rc2.py`
- `src\az_enterprise\core\production_director.py`
- `src\az_enterprise\core\project_config_rc2.py`
- `src\az_enterprise\core\quality.py`
- `src\az_enterprise\core\rc2_cli.py`
- `src\az_enterprise\core\runtime_governance_rc2.py`
- `src\az_enterprise\core\story_engine_runtime.py`
- `src\az_enterprise\core\timeline_engine_rc2.py`
- `src\az_enterprise\core\timeline_studio.py`
- `src\az_enterprise\core\workflow.py`
- `src\az_enterprise\ui\app.py`
- `tests\test_director_ai_alpha25.py`
- `tests\test_director_ai_supervisor_alpha26.py`
- `tests\test_director_knowledge_base_rc2.py`
- `tests\test_director_policy_alpha293.py`
- `tests\test_director_supervisor_alpha292.py`
- `tests\test_execution_graph_alpha291.py`
- `tests\test_postproduction_rhythm_alpha271.py`
- `tests\test_postproduction_visual_alpha272.py`
- `tests\test_production_director.py`
- `tests\test_project_profiles_alpha273.py`
- `tests\test_rc2_assignment_authority.py`
- `tests\test_rc2_director_ai_authority.py`
- `tests\test_rc2_stage2_unified_runtime.py`
- `tools\smoke_test.py`

### event
- `apply_atlas_zero_alpha_291.py`
- `apply_atlas_zero_alpha_292.py`
- `apply_director_ai_alpha_273.py`
- `atlas_zero_full_audit.py`
- `atlas_zero_phase7_native_audio_composer\phase7_payload\audio_composer_rc2.py`
- `atlas_zero_phase7_native_audio_composer\phase7_payload\audio_renderer_rc2.py`
- `atlas_zero_phase7_native_audio_composer\phase7_payload\audio_timeline_rc2.py`
- `atlas_zero_phase7_native_audio_composer\test_audio_phase7_rc2.py`
- `atlas_zero_rc2_final_audit\RC2_E2E_INTEGRATION_TEST.py`
- `atlas_zero_rc2_finalization\APPLY_RC2_FINALIZATION.py`
- `atlas_zero_rc2_finalization\VERIFY_RC2_FINALIZATION.py`
- `atlas_zero_rc2_production_audit\atlas_zero_full_audit.py`
- `audit_rc2_production\target_files\assignment_policy_rc2.py`
- `src\az_enterprise\core\acceptance_center.py`
- `src\az_enterprise\core\agents\__init__.py`
- `src\az_enterprise\core\agents\event_bus.py`
- `src\az_enterprise\core\api_gateway.py`
- `src\az_enterprise\core\asset_intelligence.py`
- `src\az_enterprise\core\assignment_policy_rc2.backup.py`
- `src\az_enterprise\core\assignment_policy_rc2.py`
- `src\az_enterprise\core\audio_composer_rc2.py`
- `src\az_enterprise\core\audio_renderer_rc2.py`
- `src\az_enterprise\core\audio_timeline_rc2.py`
- `src\az_enterprise\core\cv_model.py`
- `src\az_enterprise\core\database.py`
- `src\az_enterprise\core\director_ai.py`
- `src\az_enterprise\core\director_ai_runtime.py`
- `src\az_enterprise\core\editorial_package_rc2.py`
- `src\az_enterprise\core\event_discovery_engine_rc2.py`
- `src\az_enterprise\core\events.py`
- `src\az_enterprise\core\final_timeline_viewer.py`
- `src\az_enterprise\core\integrations.py`
- `src\az_enterprise\core\live_api_layer.py`
- `src\az_enterprise\core\live_connectors.py`
- `src\az_enterprise\core\local_autopilot.py`
- `src\az_enterprise\core\media_orchestrator.py`
- `src\az_enterprise\core\montage_workbench.py`
- `src\az_enterprise\core\narrative_writer_rc2.py`
- `src\az_enterprise\core\native_viewer_rc.py`
- `src\az_enterprise\core\operator_console.py`
- `src\az_enterprise\core\pipeline_runtime.py`
- `src\az_enterprise\core\preflight.py`
- `src\az_enterprise\core\production_state.py`
- `src\az_enterprise\core\project_context_alpha29.py`
- `src\az_enterprise\core\project_profiles_alpha273.py`
- `src\az_enterprise\core\project_state.py`
- `src\az_enterprise\core\quality.py`
- `src\az_enterprise\core\release_gate.py`
- `src\az_enterprise\core\render_engine_rc2.py`
- `src\az_enterprise\core\story_strategy_contract_rc2.py`
- `src\az_enterprise\core\story_strategy_engine_rc2.py`
- `src\az_enterprise\core\timeline_studio.py`
- `src\az_enterprise\core\visual_intelligence.py`
- `src\az_enterprise\core\visual_semantic_analyzer_rc2.py`
- `src\az_enterprise\core\visual_understanding_contract_rc2.py`
- `src\az_enterprise\core\workflow.py`
- `src\az_enterprise\core\working_state_auditor.py`
- `src\az_enterprise\ui\app.py`
- `tests\test_audio_phase7_rc2.py`
- `tests\test_editorial_package_rc2.py`
- `tests\test_event_bus_consolidation.py`
- `tests\test_event_discovery_engine_rc2.py`
- `tests\test_project_profiles_alpha273.py`
- `tests\test_story_strategy_contract_rc2.py`
- `tests\test_story_strategy_engine_rc2.py`
- `tests\test_visual_semantic_analyzer_rc2.py`
- `tests\test_visual_understanding_contract_rc2.py`
- `tools\smoke_test.py`

### quality
- `apply_atlas_zero_alpha_28.py`
- `apply_atlas_zero_alpha_29.py`
- `apply_atlas_zero_alpha_291.py`
- `apply_atlas_zero_alpha_292.py`
- `apply_atlas_zero_alpha_293.py`
- `apply_atlas_zero_alpha_311.py`
- `apply_director_ai_25.py`
- `apply_director_ai_alpha_26.py`
- `apply_director_ai_alpha_271.py`
- `apply_director_ai_alpha_272.py`
- `apply_director_ai_alpha_272_v2.py`
- `apply_director_ai_alpha_272_v3.py`
- `apply_director_ai_alpha_273.py`
- `apply_director_ai_supervisor_alpha26.py`
- `apply_director_knowledge_base_rc2.py`
- `apply_director_supervisor_rc2_fix.py`
- `atlas_zero_full_audit.py`
- `atlas_zero_rc2_1_patch\src\az_enterprise\core\director_core_rc2.py`
- `atlas_zero_rc2_1_patch\src\az_enterprise\core\production_state_rc2.py`
- `atlas_zero_rc2_1_patch\src\az_enterprise\core\quality_gate_rc2.py`
- `atlas_zero_rc2_2_patch\APPLY_RC2_V3.py`
- `atlas_zero_rc2_2_patch\src\az_enterprise\core\director_core_rc2.py`
- `atlas_zero_rc2_2_patch\src\az_enterprise\core\production_state_rc2.py`
- `atlas_zero_rc2_2_patch\src\az_enterprise\core\quality_gate_rc2.py`
- `atlas_zero_rc2_production_audit\RC2_PRODUCTION_AUDIT.py`
- `atlas_zero_rc2_production_audit\atlas_zero_full_audit.py`
- `atlas_zero_rc2_stage2_patch\APPLY_RC2_STAGE2.py`
- `atlas_zero_rc2_stage2_patch\src\az_enterprise\core\director_core_rc2.py`
- `atlas_zero_rc2_stage2_patch\src\az_enterprise\core\production_state_rc2.py`
- `atlas_zero_rc2_stage2_patch\src\az_enterprise\core\project_config_rc2.py`
- `atlas_zero_rc2_stage2_patch\src\az_enterprise\core\quality_gate_rc2.py`
- `atlas_zero_rc2_stage2_patch\src\az_enterprise\core\runtime_governance_rc2.py`
- `audit_rc2_production\target_files\assignment_policy_rc2.py`
- `audit_rc2_production\target_files\postproduction_quality_rc2.py`
- `audit_rc2_production\target_files\quality_gate_rc2.py`
- `audit_rc2_production\target_files\story_engine_runtime.py`
- `audit_rc2_production\target_files\timeline_engine_rc2.py`
- `postproduction_quality_rc2.py`
- `src\az_enterprise\core\acceptance_center.py`
- `src\az_enterprise\core\asset_intelligence.py`
- `src\az_enterprise\core\assignment_policy_rc2.backup.py`
- `src\az_enterprise\core\assignment_policy_rc2.py`
- `src\az_enterprise\core\capcut_bridge.py`
- `src\az_enterprise\core\cv_model.py`
- `src\az_enterprise\core\database.py`
- `src\az_enterprise\core\director_ai.py`
- `src\az_enterprise\core\director_ai_runtime.py`
- `src\az_enterprise\core\director_core_rc2.py`
- `src\az_enterprise\core\director_policy_alpha293.py`
- `src\az_enterprise\core\director_policy_evaluator_alpha293.py`
- `src\az_enterprise\core\final_timeline_viewer.py`
- `src\az_enterprise\core\integrations.py`
- `src\az_enterprise\core\native_timeline.py`
- `src\az_enterprise\core\pipeline_runtime.py`
- `src\az_enterprise\core\postproduction_quality_rc2.py`
- `src\az_enterprise\core\production_state.py`
- `src\az_enterprise\core\production_state_rc2.py`
- `src\az_enterprise\core\project_config_rc2.py`
- `src\az_enterprise\core\quality.py`
- `src\az_enterprise\core\quality_gate_rc2.py`
- `src\az_enterprise\core\recommendation_engine_alpha28.py`
- `src\az_enterprise\core\render_engine_rc2.py`
- `src\az_enterprise\core\runtime_governance_rc2.py`
- `src\az_enterprise\core\story_engine_runtime.py`
- `src\az_enterprise\core\test_center.py`
- `src\az_enterprise\core\timeline_engine_rc2.py`
- `src\az_enterprise\core\visual_asset_registrar.py`
- `src\az_enterprise\core\visual_intelligence.py`
- `src\az_enterprise\core\visual_semantic_analyzer_rc2.py`
- `src\az_enterprise\core\workflow.py`
- `src\az_enterprise\ui\app.py`
- `test_postproduction_quality_rc2.py`
- `tests\test_director_ai_alpha25.py`
- `tests\test_director_policy_alpha293.py`
- `tests\test_director_supervisor_alpha292.py`
- `tests\test_execution_graph_alpha291.py`
- `tests\test_postproduction_quality_rc2.py`
- `tests\test_postproduction_rhythm_alpha271.py`
- `tests\test_postproduction_visual_alpha272.py`
- `tests\test_project_profiles_alpha273.py`
- `tests\test_rc2_asset_schema_migration.py`
- `tests\test_rc2_timeline_authority.py`
- `tests\test_rc2_timeline_production_script.py`
- `tests\test_rc2_timeline_project_discovery.py`
- `tests\test_recommendation_engine_alpha28.py`
- `tools\smoke_test.py`

### render
- `APPLY_PHASE5.py`
- `apply_director_ai_25.py`
- `apply_director_supervisor_rc2_fix.py`
- `atlas_zero_full_audit.py`
- `atlas_zero_phase5_native_camera_motion\APPLY_PHASE5.py`
- `atlas_zero_phase5_native_camera_motion\phase5_payload\visual_renderer_rc2.py`
- `atlas_zero_phase6_native_transition_engine\APPLY_PHASE6.py`
- `atlas_zero_phase6_native_transition_engine\phase6_payload\visual_renderer_rc2.py`
- `atlas_zero_phase7_native_audio_composer\APPLY_PHASE7.py`
- `atlas_zero_phase7_native_audio_composer\phase7_payload\audio_composer_rc2.py`
- `atlas_zero_phase7_native_audio_composer\phase7_payload\audio_renderer_rc2.py`
- `atlas_zero_phase7_native_audio_composer\phase7_payload\mux_engine_rc2.py`
- `atlas_zero_phase8_rc2_control_layer\APPLY_PHASE8.py`
- `atlas_zero_phase8_rc2_control_layer\VERIFY_PHASE8.py`
- `atlas_zero_phase8_rc2_control_layer\payload\src\az_enterprise\core\control_layer_rc2.py`
- `atlas_zero_phase8_rc2_control_layer\tests\test_phase8_control_layer_rc2.py`
- `atlas_zero_phase9_production_cleanup\APPLY_PHASE9.py`
- `atlas_zero_phase9_production_cleanup\VERIFY_PHASE9.py`
- `atlas_zero_rc2_1_patch\src\az_enterprise\core\director_core_rc2.py`
- `atlas_zero_rc2_1_patch\src\az_enterprise\core\project_config_rc2.py`
- `atlas_zero_rc2_1_patch\src\az_enterprise\core\quality_gate_rc2.py`
- `atlas_zero_rc2_1_patch\src\az_enterprise\core\render_engine_rc2.py`
- `atlas_zero_rc2_1_patch\tests\test_rc2_foundation.py`
- `atlas_zero_rc2_2_patch\APPLY_RC2_V3.py`
- `atlas_zero_rc2_2_patch\src\az_enterprise\core\director_core_rc2.py`
- `atlas_zero_rc2_2_patch\src\az_enterprise\core\project_config_rc2.py`
- `atlas_zero_rc2_2_patch\src\az_enterprise\core\quality_gate_rc2.py`
- `atlas_zero_rc2_2_patch\src\az_enterprise\core\render_engine_rc2.py`
- `atlas_zero_rc2_2_patch\tests\test_rc2_foundation.py`
- `atlas_zero_rc2_final_audit\RC2_DEPENDENCY_AUDIT.py`
- `atlas_zero_rc2_finalization\APPLY_RC2_FINALIZATION.py`
- `atlas_zero_rc2_finalization\VERIFY_RC2_FINALIZATION.py`
- `atlas_zero_rc2_production_audit\RC2_PRODUCTION_AUDIT.py`
- `atlas_zero_rc2_production_audit\atlas_zero_full_audit.py`
- `atlas_zero_rc2_stage2_patch\src\az_enterprise\core\director_core_rc2.py`
- `atlas_zero_rc2_stage2_patch\src\az_enterprise\core\project_config_rc2.py`
- `atlas_zero_rc2_stage2_patch\src\az_enterprise\core\quality_gate_rc2.py`
- `atlas_zero_rc2_stage2_patch\tests\test_rc2_stage2_unified_runtime.py`
- `atlas_zero_remove_rc1\APPLY_REMOVE_RC1.py`
- `atlas_zero_remove_rc1\VERIFY_REMOVE_RC1.py`
- `audit_rc2_production\target_files\quality_gate_rc2.py`
- `audit_rc2_production\target_files\render_engine_rc1.py`
- `phase5_payload\visual_renderer_rc2.py`
- `src\az_enterprise\cli.py`
- `src\az_enterprise\core\audio_composer_rc2.py`
- `src\az_enterprise\core\audio_renderer_rc2.py`
- `src\az_enterprise\core\control_layer_rc2.py`
- `src\az_enterprise\core\cv_model.py`
- `src\az_enterprise\core\director_core_rc2.py`
- `src\az_enterprise\core\media_orchestrator.py`
- `src\az_enterprise\core\mux_engine_rc2.py`
- `src\az_enterprise\core\native_viewer_rc.py`
- `src\az_enterprise\core\preflight.py`
- `src\az_enterprise\core\production_director.py`
- `src\az_enterprise\core\project_config_rc2.py`
- `src\az_enterprise\core\quality_gate_rc2.py`
- `src\az_enterprise\core\render_engine_rc2.py`
- `src\az_enterprise\core\visual_renderer_rc2.py`
- `src\az_enterprise\core\voice_production_engine_rc2.py`
- `src\az_enterprise\ui\app.py`
- `tests\test_phase8_control_layer_rc2.py`
- `tests\test_production_director.py`
- `tests\test_rc2_foundation.py`
- `tests\test_rc2_render_authority.py`
- `tests\test_rc2_stage2_unified_runtime.py`

### semantic
- `apply_director_supervisor_rc2_fix.py`
- `atlas_zero_full_audit.py`
- `atlas_zero_rc2_finalization\APPLY_RC2_FINALIZATION.py`
- `atlas_zero_rc2_finalization\VERIFY_RC2_FINALIZATION.py`
- `atlas_zero_rc2_production_audit\atlas_zero_full_audit.py`
- `atlas_zero_rc2_stage2_patch\src\az_enterprise\core\project_config_rc2.py`
- `atlas_zero_rc2_stage2_patch\src\az_enterprise\core\quality_gate_rc2.py`
- `audit_rc2_production\target_files\assignment_policy_rc2.py`
- `audit_rc2_production\target_files\quality_gate_rc2.py`
- `src\az_enterprise\core\assignment_policy_rc2.backup.py`
- `src\az_enterprise\core\assignment_policy_rc2.py`
- `src\az_enterprise\core\database.py`
- `src\az_enterprise\core\director_core_rc2.py`
- `src\az_enterprise\core\editorial_package_rc2.py`
- `src\az_enterprise\core\event_discovery_engine_rc2.py`
- `src\az_enterprise\core\generated_asset_store_rc2.py`
- `src\az_enterprise\core\project_config_rc2.py`
- `src\az_enterprise\core\quality_gate_rc2.py`
- `src\az_enterprise\core\visual_semantic_analyzer_rc2.py`
- `tests\test_editorial_package_rc2.py`
- `tests\test_generated_asset_store_rc2.py`
- `tests\test_rc2_asset_schema_migration.py`
- `tests\test_story_engine_semantic_rc26.py`
- `tests\test_visual_semantic_analyzer_rc2.py`

### story
- `apply_atlas_zero_alpha_292.py`
- `apply_atlas_zero_alpha_311.py`
- `apply_director_ai_alpha_273.py`
- `apply_director_ai_supervisor_alpha26.py`
- `apply_director_knowledge_base_rc2.py`
- `atlas_zero_full_audit.py`
- `atlas_zero_rc2_production_audit\RC2_PRODUCTION_AUDIT.py`
- `atlas_zero_rc2_production_audit\atlas_zero_full_audit.py`
- `atlas_zero_rc2_stage2_patch\src\az_enterprise\core\quality_gate_rc2.py`
- `atlas_zero_rc2_stage2_patch\src\az_enterprise\core\runtime_governance_rc2.py`
- `audit_rc2_production\target_files\assignment_policy_rc2.py`
- `audit_rc2_production\target_files\quality_gate_rc2.py`
- `audit_rc2_production\target_files\story_engine_runtime.py`
- `audit_rc2_production\target_files\timeline_engine_rc2.py`
- `src\az_enterprise\core\acceptance_center.py`
- `src\az_enterprise\core\assignment_policy_rc2.backup.py`
- `src\az_enterprise\core\assignment_policy_rc2.py`
- `src\az_enterprise\core\capcut_bridge.py`
- `src\az_enterprise\core\database.py`
- `src\az_enterprise\core\director_ai.py`
- `src\az_enterprise\core\director_ai_runtime.py`
- `src\az_enterprise\core\director_core_rc2.py`
- `src\az_enterprise\core\director_knowledge_base_rc2.py`
- `src\az_enterprise\core\director_supervisor_alpha292.py`
- `src\az_enterprise\core\editorial_package_rc2.py`
- `src\az_enterprise\core\event_discovery_engine_rc2.py`
- `src\az_enterprise\core\final_assembly_pack.py`
- `src\az_enterprise\core\final_timeline_viewer.py`
- `src\az_enterprise\core\franklin_e2e_runtime.py`
- `src\az_enterprise\core\integrations.py`
- `src\az_enterprise\core\montage_workbench.py`
- `src\az_enterprise\core\narrative_writer_rc2.py`
- `src\az_enterprise\core\native_timeline.py`
- `src\az_enterprise\core\native_viewer_pro.py`
- `src\az_enterprise\core\native_viewer_rc.py`
- `src\az_enterprise\core\pipeline_runtime.py`
- `src\az_enterprise\core\production_director.py`
- `src\az_enterprise\core\project_config_rc2.py`
- `src\az_enterprise\core\project_profiles_alpha273.py`
- `src\az_enterprise\core\quality_gate_rc2.py`
- `src\az_enterprise\core\render_engine_rc2.py`
- `src\az_enterprise\core\runtime_governance_rc2.py`
- `src\az_enterprise\core\story_engine_runtime.py`
- `src\az_enterprise\core\story_strategy_contract_rc2.py`
- `src\az_enterprise\core\story_strategy_engine_rc2.py`
- `src\az_enterprise\core\timeline_engine_rc2.py`
- `src\az_enterprise\core\timeline_studio.py`
- `src\az_enterprise\core\visual_semantic_analyzer_rc2.py`
- `src\az_enterprise\core\visual_understanding_contract_rc2.py`
- `src\az_enterprise\core\workflow.py`
- `src\az_enterprise\ui\app.py`
- `tests\test_director_ai_alpha25.py`
- `tests\test_director_ai_supervisor_alpha26.py`
- `tests\test_editorial_package_rc2.py`
- `tests\test_event_discovery_engine_rc2.py`
- `tests\test_production_director.py`
- `tests\test_rc2_timeline_authority.py`
- `tests\test_story_engine_semantic_rc26.py`
- `tests\test_story_strategy_contract_rc2.py`
- `tests\test_story_strategy_engine_rc2.py`
- `tests\test_visual_semantic_analyzer_rc2.py`
- `tests\test_visual_understanding_contract_rc2.py`
- `tools\smoke_test.py`

### story_strategy
- `atlas_zero_full_audit.py`
- `atlas_zero_rc2_production_audit\RC2_PRODUCTION_AUDIT.py`
- `atlas_zero_rc2_production_audit\atlas_zero_full_audit.py`
- `src\az_enterprise\core\director_core_rc2.py`
- `src\az_enterprise\core\editorial_package_rc2.py`
- `src\az_enterprise\core\project_config_rc2.py`
- `src\az_enterprise\core\story_strategy_contract_rc2.py`
- `src\az_enterprise\core\story_strategy_engine_rc2.py`
- `tests\test_editorial_package_rc2.py`
- `tests\test_story_strategy_contract_rc2.py`
- `tests\test_story_strategy_engine_rc2.py`

### timeline
- `apply_atlas_zero_alpha_28.py`
- `apply_atlas_zero_alpha_291.py`
- `apply_atlas_zero_alpha_292.py`
- `apply_atlas_zero_alpha_293.py`
- `apply_atlas_zero_alpha_311.py`
- `apply_director_ai_alpha_26.py`
- `apply_director_ai_alpha_271.py`
- `apply_director_ai_alpha_272.py`
- `apply_director_ai_alpha_272_v2.py`
- `apply_director_ai_alpha_272_v3.py`
- `apply_director_ai_alpha_273.py`
- `apply_director_ai_supervisor_alpha26.py`
- `apply_director_knowledge_base_rc2.py`
- `apply_director_supervisor_rc2_fix.py`
- `atlas_zero_full_audit.py`
- `atlas_zero_phase6_native_transition_engine\phase6_payload\transition_engine_rc2.py`
- `atlas_zero_phase7_native_audio_composer\APPLY_PHASE7.py`
- `atlas_zero_phase7_native_audio_composer\phase7_payload\audio_composer_rc2.py`
- `atlas_zero_phase7_native_audio_composer\phase7_payload\audio_renderer_rc2.py`
- `atlas_zero_phase7_native_audio_composer\phase7_payload\audio_timeline_rc2.py`
- `atlas_zero_phase7_native_audio_composer\test_audio_phase7_rc2.py`
- `atlas_zero_phase8_rc2_control_layer\APPLY_PHASE8.py`
- `atlas_zero_phase8_rc2_control_layer\payload\src\az_enterprise\core\control_layer_rc2.py`
- `atlas_zero_phase8_rc2_control_layer\tests\test_phase8_control_layer_rc2.py`
- `atlas_zero_phase9_production_cleanup\VERIFY_PHASE9.py`
- `atlas_zero_rc2_1_patch\src\az_enterprise\core\director_core_rc2.py`
- `atlas_zero_rc2_1_patch\src\az_enterprise\core\project_config_rc2.py`
- `atlas_zero_rc2_1_patch\src\az_enterprise\core\quality_gate_rc2.py`
- `atlas_zero_rc2_1_patch\src\az_enterprise\core\timeline_engine_rc2.py`
- `atlas_zero_rc2_2_patch\APPLY_RC2_V3.py`
- `atlas_zero_rc2_2_patch\src\az_enterprise\core\director_core_rc2.py`
- `atlas_zero_rc2_2_patch\src\az_enterprise\core\project_config_rc2.py`
- `atlas_zero_rc2_2_patch\src\az_enterprise\core\quality_gate_rc2.py`
- `atlas_zero_rc2_2_patch\src\az_enterprise\core\timeline_engine_rc2.py`
- `atlas_zero_rc2_final_audit\RC2_DEPENDENCY_AUDIT.py`
- `atlas_zero_rc2_final_audit\RC2_E2E_INTEGRATION_TEST.py`
- `atlas_zero_rc2_finalization\VERIFY_RC2_FINALIZATION.py`
- `atlas_zero_rc2_production_audit\RC2_PRODUCTION_AUDIT.py`
- `atlas_zero_rc2_production_audit\atlas_zero_full_audit.py`
- `atlas_zero_rc2_stage2_patch\src\az_enterprise\core\director_core_rc2.py`
- `atlas_zero_rc2_stage2_patch\src\az_enterprise\core\project_config_rc2.py`
- `atlas_zero_rc2_stage2_patch\src\az_enterprise\core\quality_gate_rc2.py`
- `atlas_zero_remove_rc1\VERIFY_REMOVE_RC1.py`
- `audit_rc2_production\target_files\postproduction_quality_rc2.py`
- `audit_rc2_production\target_files\quality_gate_rc2.py`
- `audit_rc2_production\target_files\render_engine_rc1.py`
- `audit_rc2_production\target_files\timeline_engine_rc2.py`
- `postproduction_quality_rc2.py`
- `src\az_enterprise\core\audio_composer_rc2.py`
- `src\az_enterprise\core\audio_renderer_rc2.py`
- `src\az_enterprise\core\audio_timeline_rc2.py`
- `src\az_enterprise\core\capcut_bridge.py`
- `src\az_enterprise\core\control_layer_rc2.py`
- `src\az_enterprise\core\cv_model.py`
- `src\az_enterprise\core\director_core_rc2.py`
- `src\az_enterprise\core\final_assembly_pack.py`
- `src\az_enterprise\core\final_timeline_viewer.py`
- `src\az_enterprise\core\media_orchestrator.py`
- `src\az_enterprise\core\montage_workbench.py`
- `src\az_enterprise\core\native_timeline.py`
- `src\az_enterprise\core\native_viewer_pro.py`
- `src\az_enterprise\core\native_viewer_rc.py`
- `src\az_enterprise\core\operator_console.py`
- `src\az_enterprise\core\pipeline_runtime.py`
- `src\az_enterprise\core\postproduction_quality_rc2.py`
- `src\az_enterprise\core\production_director.py`
- `src\az_enterprise\core\project_config_rc2.py`
- `src\az_enterprise\core\project_context_alpha29.py`
- `src\az_enterprise\core\quality.py`
- `src\az_enterprise\core\quality_gate_rc2.py`
- `src\az_enterprise\core\recommendation_engine_alpha28.py`
- `src\az_enterprise\core\release_gate.py`
- `src\az_enterprise\core\render_engine_rc2.py`
- `src\az_enterprise\core\test_center.py`
- `src\az_enterprise\core\timeline_engine_rc2.py`
- `src\az_enterprise\core\timeline_studio.py`
- `src\az_enterprise\core\timeline_viewer_2.py`
- `src\az_enterprise\core\transition_engine_rc2.py`
- `src\az_enterprise\core\visual_dynamics_alpha272.py`
- `src\az_enterprise\core\workflow.py`
- `src\az_enterprise\core\working_state_auditor.py`
- `src\az_enterprise\timeline_viewer_app.py`
- `src\az_enterprise\ui\app.py`
- `test_postproduction_quality_rc2.py`
- `tests\test_audio_phase7_rc2.py`
- `tests\test_director_ai_supervisor_alpha26.py`
- `tests\test_director_knowledge_base_rc2.py`
- `tests\test_director_policy_alpha293.py`
- `tests\test_director_supervisor_alpha292.py`
- `tests\test_phase8_control_layer_rc2.py`
- `tests\test_postproduction_quality_rc2.py`
- `tests\test_postproduction_rhythm_alpha271.py`
- `tests\test_postproduction_visual_alpha272.py`
- `tests\test_project_profiles_alpha273.py`
- `tests\test_rc2_render_authority.py`
- `tests\test_rc2_timeline_authority.py`
- `tests\test_rc2_timeline_production_script.py`
- `tests\test_rc2_timeline_project_discovery.py`
- `tests\test_recommendation_engine_alpha28.py`
- `tools\smoke_test.py`

### visual
- `APPLY_PHASE5.py`
- `apply_atlas_zero_alpha_28.py`
- `apply_atlas_zero_alpha_29.py`
- `apply_atlas_zero_alpha_291.py`
- `apply_atlas_zero_alpha_292.py`
- `apply_atlas_zero_alpha_293.py`
- `apply_atlas_zero_alpha_301.py`
- `apply_atlas_zero_alpha_311.py`
- `apply_director_ai_alpha_272.py`
- `apply_director_ai_alpha_272_v2.py`
- `apply_director_ai_alpha_272_v3.py`
- `apply_director_ai_alpha_273.py`
- `apply_director_ai_supervisor_alpha26.py`
- `apply_director_knowledge_base_rc2.py`
- `apply_director_supervisor_rc2_fix.py`
- `atlas_zero_full_audit.py`
- `atlas_zero_phase5_native_camera_motion\APPLY_PHASE5.py`
- `atlas_zero_phase5_native_camera_motion\phase5_payload\visual_renderer_rc2.py`
- `atlas_zero_phase6_native_transition_engine\APPLY_PHASE6.py`
- `atlas_zero_phase6_native_transition_engine\phase6_payload\visual_renderer_rc2.py`
- `atlas_zero_phase7_native_audio_composer\APPLY_PHASE7.py`
- `atlas_zero_phase7_native_audio_composer\phase7_payload\audio_composer_rc2.py`
- `atlas_zero_phase7_native_audio_composer\phase7_payload\mux_engine_rc2.py`
- `atlas_zero_rc2_final_audit\RC2_DEPENDENCY_AUDIT.py`
- `atlas_zero_rc2_final_audit\RC2_E2E_INTEGRATION_TEST.py`
- `atlas_zero_rc2_finalization\APPLY_RC2_FINALIZATION.py`
- `atlas_zero_rc2_finalization\VERIFY_RC2_FINALIZATION.py`
- `atlas_zero_rc2_production_audit\RC2_PRODUCTION_AUDIT.py`
- `atlas_zero_rc2_production_audit\atlas_zero_full_audit.py`
- `audit_rc2_production\target_files\assignment_policy_rc2.py`
- `audit_rc2_production\target_files\postproduction_quality_rc2.py`
- `audit_rc2_production\target_files\production_script_assembler_rc2.py`
- `audit_rc2_production\target_files\story_engine_runtime.py`
- `audit_rc2_production\target_files\timeline_engine_rc2.py`
- `phase5_payload\visual_renderer_rc2.py`
- `src\az_enterprise\cli.py`
- `src\az_enterprise\core\acceptance_center.py`
- `src\az_enterprise\core\agents\agent_registry.py`
- `src\az_enterprise\core\assignment_policy_rc2.backup.py`
- `src\az_enterprise\core\assignment_policy_rc2.py`
- `src\az_enterprise\core\audio_composer_rc2.py`
- `src\az_enterprise\core\capcut_bridge.py`
- `src\az_enterprise\core\cv_model.py`
- `src\az_enterprise\core\cv_review_board.py`
- `src\az_enterprise\core\database.py`
- `src\az_enterprise\core\director_ai.py`
- `src\az_enterprise\core\director_ai_runtime.py`
- `src\az_enterprise\core\director_core_rc2.py`
- `src\az_enterprise\core\editorial_package_rc2.py`
- `src\az_enterprise\core\event_discovery_engine_rc2.py`
- `src\az_enterprise\core\final_assembly_pack.py`
- `src\az_enterprise\core\final_timeline_viewer.py`
- `src\az_enterprise\core\generated_asset_store_rc2.py`
- `src\az_enterprise\core\integrations.py`
- `src\az_enterprise\core\local_autopilot.py`
- `src\az_enterprise\core\media_orchestrator.py`
- `src\az_enterprise\core\montage_workbench.py`
- `src\az_enterprise\core\mux_engine_rc2.py`
- `src\az_enterprise\core\narrative_writer_rc2.py`
- `src\az_enterprise\core\native_timeline.py`
- `src\az_enterprise\core\native_viewer_pro.py`
- `src\az_enterprise\core\native_viewer_rc.py`
- `src\az_enterprise\core\operator_console.py`
- `src\az_enterprise\core\pipeline_runtime.py`
- `src\az_enterprise\core\postproduction_quality_rc2.py`
- `src\az_enterprise\core\production_director.py`
- `src\az_enterprise\core\production_script_assembler_rc2.py`
- `src\az_enterprise\core\production_state.py`
- `src\az_enterprise\core\production_visual_manager.py`
- `src\az_enterprise\core\project_profiles_alpha273.py`
- `src\az_enterprise\core\project_state.py`
- `src\az_enterprise\core\quality.py`
- `src\az_enterprise\core\recommendation_engine_alpha28.py`
- `src\az_enterprise\core\release_gate.py`
- `src\az_enterprise\core\render_engine_rc2.py`
- `src\az_enterprise\core\story_engine_runtime.py`
- `src\az_enterprise\core\story_strategy_contract_rc2.py`
- `src\az_enterprise\core\story_strategy_engine_rc2.py`
- `src\az_enterprise\core\timeline_engine_rc2.py`
- `src\az_enterprise\core\timeline_studio.py`
- `src\az_enterprise\core\timeline_viewer_2.py`
- `src\az_enterprise\core\visual_asset_registrar.py`
- `src\az_enterprise\core\visual_dynamics_alpha272.py`
- `src\az_enterprise\core\visual_intelligence.py`
- `src\az_enterprise\core\visual_renderer_rc2.py`
- `src\az_enterprise\core\visual_semantic_analyzer_rc2.py`
- `src\az_enterprise\core\visual_understanding_contract_rc2.py`
- `src\az_enterprise\core\workflow.py`
- `src\az_enterprise\ui\app.py`
- `tests\test_director_ai_alpha25.py`
- `tests\test_director_ai_supervisor_alpha26.py`
- `tests\test_director_knowledge_base_rc2.py`
- `tests\test_director_policy_alpha293.py`
- `tests\test_director_supervisor_alpha292.py`
- `tests\test_editorial_package_rc2.py`
- `tests\test_execution_graph_alpha291.py`
- `tests\test_postproduction_visual_alpha272.py`
- `tests\test_production_director.py`
- `tests\test_production_script_assembler_rc2.py`
- `tests\test_production_script_regenerator_rc2.py`
- `tests\test_production_visual_manager.py`
- `tests\test_project_model_alpha301.py`
- `tests\test_rc2_timeline_authority.py`
- `tests\test_rc2_timeline_production_script.py`
- `tests\test_rc2_timeline_project_discovery.py`
- `tests\test_recommendation_engine_alpha28.py`
- `tests\test_story_engine_semantic_rc26.py`
- `tests\test_story_strategy_contract_rc2.py`
- `tests\test_story_strategy_engine_rc2.py`
- `tests\test_visual_asset_registrar.py`
- `tests\test_visual_semantic_analyzer_rc2.py`
- `tests\test_visual_understanding_contract_rc2.py`

### voice
- `atlas_zero_full_audit.py`
- `atlas_zero_phase7_native_audio_composer\phase7_payload\audio_renderer_rc2.py`
- `atlas_zero_phase7_native_audio_composer\phase7_payload\audio_timeline_rc2.py`
- `atlas_zero_phase7_native_audio_composer\phase7_payload\ducking_engine_rc2.py`
- `atlas_zero_phase7_native_audio_composer\test_audio_phase7_rc2.py`
- `atlas_zero_rc2_final_audit\RC2_E2E_INTEGRATION_TEST.py`
- `atlas_zero_rc2_production_audit\RC2_PRODUCTION_AUDIT.py`
- `atlas_zero_rc2_production_audit\atlas_zero_full_audit.py`
- `atlas_zero_rc2_stage2_patch\src\az_enterprise\core\project_config_rc2.py`
- `audit_rc2_production\target_files\production_script_assembler_rc2.py`
- `audit_rc2_production\target_files\production_script_regenerator_rc2.py`
- `audit_rc2_production\target_files\render_engine_rc1.py`
- `audit_rc2_production\target_files\timeline_engine_rc2.py`
- `src\az_enterprise\core\agents\agent_registry.py`
- `src\az_enterprise\core\asset_intelligence.py`
- `src\az_enterprise\core\audio_renderer_rc2.py`
- `src\az_enterprise\core\audio_timeline_rc2.py`
- `src\az_enterprise\core\director_ai.py`
- `src\az_enterprise\core\ducking_engine_rc2.py`
- `src\az_enterprise\core\editorial_package_rc2.py`
- `src\az_enterprise\core\integrations.py`
- `src\az_enterprise\core\media_orchestrator.py`
- `src\az_enterprise\core\narrative_writer_rc2.py`
- `src\az_enterprise\core\production_director.py`
- `src\az_enterprise\core\production_script_assembler_rc2.py`
- `src\az_enterprise\core\production_script_regenerator_rc2.py`
- `src\az_enterprise\core\project_config_rc2.py`
- `src\az_enterprise\core\project_state.py`
- `src\az_enterprise\core\render_engine_rc2.py`
- `src\az_enterprise\core\timeline_engine_rc2.py`
- `src\az_enterprise\core\timeline_viewer_2.py`
- `src\az_enterprise\core\voice_production_engine_rc2.py`
- `tests\test_audio_phase7_rc2.py`
- `tests\test_director_ai_alpha25.py`
- `tests\test_rc2_timeline_production_script.py`
- `tests\test_rc2_timeline_project_discovery.py`
- `tests\test_voice_production_engine_rc2.py`

## Compile check

- Return code: `1`
```text
*** Error compiling 'C:\\Users\\3dtool\\OneDrive\\���������\\GitHub\\atlas_zero1\\rcaz_enterprisecoredirector_ai.py'...
Sorry: IndentationError: unexpected indent (rcaz_enterprisecoredirector_ai.py, line 2)

C:\Users\3dtool\OneDrive\���������\GitHub\atlas_zero1\atlas_zero_rc2_finalization\APPLY_RC2_FINALIZATION.py:155: SyntaxWarning: invalid escape sequence '\s'
  print(r"$env:PYTHONPATH = ""$PWD\src""")
```

## Tests

- State: **PASSED**
```text

```

## Git state

- Branch: `feature/rc2-duration-authority-2.6`
- HEAD: `daa0440d5508f9129aa15e15000e77763f439fad`
```text
D ATLAS_ZERO_RC1_ALPHA_3_1.patch
 D paceexportsfranklinmovie_runtime_rc1manual_edit_package.md
 M src/az_enterprise/cli.py
 M src/az_enterprise/core/asset_intelligence.py
 M src/az_enterprise/core/assignment_policy_rc2.py
 M src/az_enterprise/core/cv_model.py
 M src/az_enterprise/core/director_core_rc2.py
 M src/az_enterprise/core/director_policy_evaluator_alpha293.py
 M src/az_enterprise/core/director_supervisor_alpha292.py
 M src/az_enterprise/core/media_orchestrator.py
 D src/az_enterprise/core/movie_runtime_rc1.py
 D src/az_enterprise/core/movie_runtime_rc1.py.backup_duration_shots_20260712_202102
 D src/az_enterprise/core/movie_runtime_rc1.py.backup_shot_mode_20260712_201034
 M src/az_enterprise/core/narrative_writer_rc2.py
 M src/az_enterprise/core/pipeline_runtime.py
 M src/az_enterprise/core/project_config_rc2.py
 D src/az_enterprise/core/rc1_completion_planner.py
 M src/az_enterprise/core/release_gate.py
 D src/az_enterprise/core/render_engine_rc1.py
 D src/az_enterprise/core/render_engine_rc1.py.backup_before_master_audio
 D src/az_enterprise/core/render_engine_rc1.py.backup_before_nostdin
 M src/az_enterprise/core/render_engine_rc2.py
 M src/az_enterprise/core/timeline_engine_rc2.py
 M src/az_enterprise/core/workflow.py
 M src/az_enterprise/ui/__pycache__/app.cpython-313.pyc
 M src/az_enterprise/ui/app.py
 D tests/test_movie_runtime_rc1.py
 D tests/test_movie_runtime_rc1_assets.py
 D tests/test_render_engine_rc1.py
 D tools/franklin_autopilot.py
 D tools/media_factory_rc1.py
 D tools/render_franklin_roughcut.py
 D tools/repair_semantic_asset_ids.py
 D tools/semantic_director_v1.py
 D tools/semantic_director_v1_1_multimedia.py
 D tools/semantic_director_v1_2_temporal.py
 D tools/visual_intelligence_v1.py
?? APPLY_PHASE5.py
?? alpha26_full_pytest.txt
?? apply_director_knowledge_base_rc2.py
?? apply_director_supervisor_rc2_fix.py
?? atlas_zero_full_audit.py
?? atlas_zero_phase5_native_camera_motion/
?? atlas_zero_phase6_native_transition_engine/
?? atlas_zero_phase7_native_audio_composer/
?? atlas_zero_phase8_rc2_control_layer/
?? atlas_zero_phase9_production_cleanup/
?? atlas_zero_rc2_final_audit/
?? atlas_zero_rc2_finalization/
?? atlas_zero_rc2_production_audit/
?? atlas_zero_remove_rc1/
?? audit_rc2_production.zip
?? audit_rc2_production/
?? audit_rc2_production_contour.ps1
?? collect_diagnostic.txt
?? collect_errors.txt
?? collect_stderr.txt
?? collect_stdout.txt
?? editorial_intelligence_source.txt
?? hogueras_duration_audit.txt
?? phase5_payload/
?? src/az_enterprise/core/audio_composer_rc2.py
?? src/az_enterprise/core/audio_renderer_rc2.py
?? src/az_enterprise/core/audio_timeline_rc2.py
?? src/az_enterprise/core/camera_motion_rc2.py
?? src/az_enterprise/core/control_layer_rc2.py
?? src/az_enterprise/core/director_knowledge_base_rc2.py
?? src/az_enterprise/core/director_policy_evaluator_alpha293.py.before_knowledge_base
?? src/az_enterprise/core/ducking_engine_rc2.py
?? src/az_enterprise/core/loudness_engine_rc2.py
?? src/az_enterprise/core/mux_engine_rc2.py
?? src/az_enterprise/core/transition_engine_rc2.py
?? src/az_enterprise/core/visual_renderer_rc2.py
?? tests/test_audio_phase7_rc2.py
?? tests/test_director_knowledge_base_rc2.py
?? tests/test_phase8_control_layer_rc2.py
?? tests/test_transition_engine_rc2.py
?? timeline_code_search.txt
```

## Recommended remediation order

1. Fix syntax errors.
2. Restore one canonical RC2 chain from assets through quality.
3. Define every intermediate artifact in ProjectConfigRC2.
4. Persist outputs atomically and validate project/state at every boundary.
5. Quarantine duplicate orchestrators and legacy fallbacks.
6. Add contract tests for every stage boundary.
7. Run a clean-workspace end-to-end test.
