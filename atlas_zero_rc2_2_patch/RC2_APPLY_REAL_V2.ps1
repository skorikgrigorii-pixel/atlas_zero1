$ErrorActionPreference = "Stop"

$PatchRoot = (Resolve-Path (Split-Path -Parent $MyInvocation.MyCommand.Path)).Path
$ProjectRoot = (Resolve-Path (Get-Location)).Path

if (-not (Test-Path (Join-Path $ProjectRoot "src\az_enterprise\core"))) {
    throw "Run this script from the atlas_zero1 project root. Current directory: $ProjectRoot"
}

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backup = Join-Path $ProjectRoot "workspace\backups\rc2_stage1_v2_$timestamp"
$createdDestinations = New-Object System.Collections.Generic.List[string]
$backedUpDestinations = New-Object System.Collections.Generic.List[string]

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

function Restore-RC2Backup {
    Write-Host "Rolling back RC2 Stage 1 changes..." -ForegroundColor Yellow

    foreach ($destination in $createdDestinations) {
        if (Test-Path $destination) {
            Remove-Item $destination -Force -ErrorAction SilentlyContinue
        }
    }

    foreach ($destination in $backedUpDestinations) {
        $relative = $destination.Substring($ProjectRoot.Length).TrimStart('\')
        $backupFile = Join-Path $backup $relative
        if (Test-Path $backupFile) {
            New-Item -ItemType Directory -Path (Split-Path $destination -Parent) -Force | Out-Null
            Copy-Item $backupFile $destination -Force
        }
    }
}

try {
    New-Item -ItemType Directory -Path $backup -Force | Out-Null

    Write-Host "" 
    Write-Host "ATLAS ZERO — RC2 STAGE 1 V2" -ForegroundColor Cyan
    Write-Host "Project: $ProjectRoot"
    Write-Host "Patch:   $PatchRoot"
    Write-Host "Backup:  $backup"
    Write-Host ""

    foreach ($relative in $targets) {
        $source = Join-Path $PatchRoot $relative
        $destination = Join-Path $ProjectRoot $relative

        if (-not (Test-Path $source)) {
            throw "Patch file missing: $source"
        }

        $resolvedSource = (Resolve-Path $source).Path
        $resolvedDestination = $null
        if (Test-Path $destination) {
            $resolvedDestination = (Resolve-Path $destination).Path
        }

        if ($resolvedDestination -and ($resolvedSource -eq $resolvedDestination)) {
            Write-Host "[SKIP SAME FILE] $relative" -ForegroundColor Yellow
            continue
        }

        if (Test-Path $destination) {
            $sourceHash = (Get-FileHash $source -Algorithm SHA256).Hash
            $destinationHash = (Get-FileHash $destination -Algorithm SHA256).Hash

            if ($sourceHash -eq $destinationHash) {
                Write-Host "[ALREADY CURRENT] $relative" -ForegroundColor DarkGreen
                continue
            }

            $backupFile = Join-Path $backup $relative
            New-Item -ItemType Directory -Path (Split-Path $backupFile -Parent) -Force | Out-Null
            Copy-Item $destination $backupFile -Force
            $backedUpDestinations.Add($destination)
        }
        else {
            $createdDestinations.Add($destination)
        }

        New-Item -ItemType Directory -Path (Split-Path $destination -Parent) -Force | Out-Null
        Copy-Item $source $destination -Force
        Write-Host "[COPIED] $relative" -ForegroundColor Green
    }

    $env:PYTHONPATH = "src"

    Write-Host ""
    Write-Host "Compiling RC2 modules..." -ForegroundColor Cyan

    $compileTargets = @(
        "src\az_enterprise\core\project_config_rc2.py",
        "src\az_enterprise\core\production_state_rc2.py",
        "src\az_enterprise\core\asset_engine_rc2.py",
        "src\az_enterprise\core\assignment_engine_rc2.py",
        "src\az_enterprise\core\timeline_engine_rc2.py",
        "src\az_enterprise\core\render_engine_rc2.py",
        "src\az_enterprise\core\quality_gate_rc2.py",
        "src\az_enterprise\core\director_core_rc2.py",
        "src\az_enterprise\core\rc2_cli.py"
    )

    foreach ($relative in $compileTargets) {
        $file = Join-Path $ProjectRoot $relative
        & python -m py_compile $file
        if ($LASTEXITCODE -ne 0) {
            throw "Python compile failed: $file"
        }
        Write-Host "[COMPILE OK] $relative" -ForegroundColor DarkGreen
    }

    Write-Host ""
    Write-Host "Running RC2 foundation tests..." -ForegroundColor Cyan
    & python -m pytest -q "tests\test_rc2_foundation.py"
    if ($LASTEXITCODE -ne 0) {
        throw "RC2 foundation tests failed."
    }

    Write-Host ""
    Write-Host "Checking RC2 CLI import..." -ForegroundColor Cyan
    & python -c "from az_enterprise.core.director_core_rc2 import DirectorCoreRC2; from az_enterprise.core.rc2_cli import main; print('RC2 imports OK')"
    if ($LASTEXITCODE -ne 0) {
        throw "RC2 import verification failed."
    }

    $installReport = @{
        version = "2.1"
        state = "APPLIED_AND_VERIFIED"
        applied_at = (Get-Date).ToString("o")
        project_root = $ProjectRoot
        patch_root = $PatchRoot
        backup = $backup
        targets = $targets
    }

    $reportDir = Join-Path $ProjectRoot "workspace\exports\_system\rc2_stage1"
    New-Item -ItemType Directory -Path $reportDir -Force | Out-Null
    $installReport | ConvertTo-Json -Depth 5 | Set-Content (Join-Path $reportDir "install_report.json") -Encoding UTF8

    Write-Host ""
    Write-Host "ATLAS ZERO RC2 STAGE 1 V2 APPLIED AND VERIFIED" -ForegroundColor Green
    Write-Host "Backup: $backup" -ForegroundColor Cyan
    Write-Host "Report: workspace\exports\_system\rc2_stage1\install_report.json" -ForegroundColor Cyan
    Write-Host "Next safe command:" -ForegroundColor Cyan
    Write-Host "python -m az_enterprise.core.rc2_cli status franklin"
}
catch {
    Write-Host "" 
    Write-Host "RC2 Stage 1 V2 failed: $($_.Exception.Message)" -ForegroundColor Red
    Restore-RC2Backup
    throw
}
