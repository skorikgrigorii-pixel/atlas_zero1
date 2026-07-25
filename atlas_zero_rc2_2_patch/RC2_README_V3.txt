ATLAS ZERO RC2 STAGE 1 V3

Run from the atlas_zero1 project root with the virtual environment active:

python .\atlas_zero_rc2_2_patch\APPLY_RC2_V3.py

This installer is Python-based to avoid Windows PowerShell 5.1 encoding/parser problems.
It creates backups, copies only changed files, compiles modules, runs tests, checks imports,
and rolls back copied files if verification fails.
