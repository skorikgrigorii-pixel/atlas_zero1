ATLAS ZERO RC1 ALPHA 3.1 — Engineering package

Place the files in the repository root.

1. Preview:
   py apply_atlas_zero_alpha_311.py --check

2. Apply:
   py apply_atlas_zero_alpha_311.py

3. Copy the test:
   copy test_pipeline_registry_alpha31.py tests\test_pipeline_registry_alpha31.py

4. Test:
   py -m pytest tests/test_pipeline_registry_alpha31.py -q

5. Review:
   git diff
   git status

6. Commit:
   git add src/az_enterprise/core/pipeline_runtime.py
   git add tests/test_pipeline_registry_alpha31.py
   git add ATLAS_ZERO_RC1_ALPHA_3_1.patch
   git commit -m "Integrate Alpha 3.1 runtime registry"
   git push origin feature/director-ai-2.5-postproduction

The script creates a backup, updates pipeline_runtime.py, generates the real unified patch, and compiles the three runtime modules.
