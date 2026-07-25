ATLAS ZERO — Phase 5 Native Camera Motion Engine

1. Extract archive into repository root.
2. Run: python APPLY_PHASE5.py
3. Verify:
   $env:PYTHONPATH = "$PWD\src"
   python -c "from az_enterprise.core.camera_motion_rc2 import CameraMotionEngine; from az_enterprise.core.visual_renderer_rc2 import VisualRendererRC2; print('PHASE 5 OK')"

Installer creates a timestamped backup in workspace/backups.
