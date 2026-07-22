ATLAS ZERO — REMOVE RC1 FROM ACTIVE PROJECT

The script only runs when the latest RC2 production audit says:

Score: 100
Status: RC2_PRODUCTION_READY
Safe to remove RC1: true

It moves active RC1 source code and archived RC1 tools/tests into:

workspace/backups/removed_rc1_<timestamp>

Historical workspace exports are preserved.

RUN:

$env:PYTHONPATH = "$PWD\src"
python .\atlas_zero_remove_rc1\APPLY_REMOVE_RC1.py
python .\atlas_zero_remove_rc1\VERIFY_REMOVE_RC1.py
python .\atlas_zero_rc2_production_audit\RUN_RC2_PRODUCTION_AUDIT.py
