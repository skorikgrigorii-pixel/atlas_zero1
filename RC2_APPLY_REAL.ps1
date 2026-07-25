$ErrorActionPreference = "Stop"

$PatchRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = (Get-Location).Path

if (-not (Test-Path (Join-Path $ProjectRoot "src\az_enterprise\core"))) {
    throw "Run this script from the atlas_zero1 project root."
}

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backup = Join-Path $ProjectRoot "workspace\backups\rc2_stage1_$timestamp"
New-Item -ItemType Directory -Path $backup -Force | Out-Null

$targets = @(
    "src\az_enterprise\core\project_config_rc2.py",
    "src\az_enterprise\core\production_state_rc2.py",
    "src\az_enterprise\core\asset_engine_rc2.py",
    "src\az_enterprise\core\assignment_engine_rc2.py",
    "src\az_enterprise\core\timeline_engine_rc2.py",
    "src\az_enterprise\core\render_engine_rc2.py",
    "src\az_enterprise\core\quality_gate_rc2.py",
    "src\az_enterprise\core\director_core_rc2.py",
    "src\az_enterprise\core\rc2_cli.py",
    "tests\test_rc2_foundation.py",
    "docs\RC2_MIGRATION_STAGE_1.md"
)

foreach ($relative in $targets) {
    $destination = Join-Path $ProjectRoot $relative
    if (Test-Path $destination) {
        $backupFile = Join-Path $backup $relative
        New-Item -ItemType Directory -Path (Split-Path $backupFile -Parent) -Force | Out-Null
        Copy-Item $destination $backupFile -Force
    }

    $source = Join-Path $PatchRoot $relative
    if (-not (Test-Path $source)) {
        throw "Patch file missing: $source"
    }
    New-Item -ItemType Directory -Path (Split-Path $destination -Parent) -Force | Out-Null
    Copy-Item $source $destination -Force
}

Write-Host "RC2 files copied. Backup: $backup" -ForegroundColor Green

$env:PYTHONPATH = "src"

$compileFiles = Get-ChildItem "src\az_enterprise\core" -Filter "*_rc2.py"
foreach ($file in $compileFiles) {
    python -m py_compile $file.FullName
    if ($LASTEXITCODE -ne 0) {
        throw "Python compile failed: $($file.FullName)"
    }
}

python -m pytest -q tests\test_rc2_foundation.py
if ($LASTEXITCODE -ne 0) {
    throw "RC2 foundation tests failed."
}

Write-Host ""
Write-Host "ATLAS ZERO RC2 STAGE 1 APPLIED AND VERIFIED" -ForegroundColor Green
Write-Host "Next safe command:" -ForegroundColor Cyan
Write-Host "python -m az_enterprise.core.rc2_cli status franklin"
