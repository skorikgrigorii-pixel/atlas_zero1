# ATLAS ZERO RC2 Stage 1 V2

This package fixes the installer self-copy failure from Stage 1.

Key changes:
- package is contained in its own directory;
- source and destination paths are compared before copying;
- identical files are skipped safely;
- existing files are backed up;
- changes are rolled back after compile/test failure;
- explicit compile, test, import and install-report checks are included.

Run from the `atlas_zero1` project root:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
& ".\.venv\Scripts\Activate.ps1"
& ".\atlas_zero_rc2_1_patch\RC2_APPLY_REAL_V2.ps1"
```
